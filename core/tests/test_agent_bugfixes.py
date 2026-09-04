# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Regressions for the 2026-08 agent-tool bug batch.

Each test pins one reported bug:
1. get_quiz_status(view='needsGrading') filtered on a field the quiz
   serializer never emits, so it was always empty (same flaw in course_todo).
2. Assignment stats coerced None→0, making an ungraded assignment read as a
   real 0-point average.
3. list_submissions projected 'isLate', which exists on no serializer, so the
   column silently vanished.
4. Submissions with no dateUploaded fell out of every lateSubmissions bucket.
5. An empty gradeDistribution gave no reason (0 points vs nothing finalized).
6. Inert setting combinations were accepted silently.
8. Reading a file's content required a fake 'update with unchanged flags'.
"""
import datetime

import factory
import pytest
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient

MCP_URL = "/mcp"
V = "2025-06-18"


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs701", period="f2026", organization__name="TestOrg")


@pytest.fixture
def admin(course):
    return course.courseAdmins.first()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def key(api_client, course, admin):
    api_client.force_authenticate(user=admin)
    resp = api_client.post(f"/courses/{course.id}/apiKeys/",
                           {"name": "bugfix-key", "scope": "admin"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    api_client.force_authenticate(user=None)
    return resp.data["key"]


def call(api_client, key, name, arguments=None):
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=V)
    resp = api_client.post(MCP_URL, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }, format="json")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    return resp.data["result"]


@pytest.fixture
def ungraded_quiz(course):
    """A published quiz where one student's response awaits manual grading."""
    from core.models import Quiz, QuizAttempt
    quiz = Quiz.objects.create(course=course, title="Essay quiz", isPublished=True)
    QuizAttempt.objects.create(
        quiz=quiz, student=course.students.first(), attemptNumber=1,
        status="submitted", needsManualGrading=True)
    return quiz


class TestQuizNeedsGrading:

    def test_needs_grading_view_finds_the_quiz(self, api_client, key, course,
                                               ungraded_quiz):
        from core.models import Quiz
        Quiz.objects.create(course=course, title="No attempts", isPublished=True)

        result = call(api_client, key, "codepost_get_quiz_status",
                      {"view": "needsGrading"})
        assert result["isError"] is False
        rows = result["structuredContent"]["data"]["quizzes"]
        assert [r["id"] for r in rows] == [ungraded_quiz.id]
        assert rows[0]["needsGrading"] == 1

    def test_list_view_uses_real_serializer_fields(self, api_client, key,
                                                   ungraded_quiz):
        result = call(api_client, key, "codepost_get_quiz_status")
        row = result["structuredContent"]["data"]["quizzes"][0]
        assert row["isPublished"] is True
        assert "attemptsAllowed" in row
        # The phantom names the projection used to reference.
        for phantom in ("published", "availability", "maxAttempts"):
            assert phantom not in row

    def test_course_todo_surfaces_it(self, api_client, key, ungraded_quiz):
        result = call(api_client, key, "codepost_course_todo")
        rows = result["structuredContent"]["data"]["quizzesNeedingGrading"]
        assert [r["quizId"] for r in rows] == [ungraded_quiz.id]
        assert rows[0]["needsGrading"] == 1


class TestStatsNullNotZero:

    def test_ungraded_assignment_stats_are_null(self, api_client, admin, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, name="HW1", points=100)
        api_client.force_authenticate(user=admin)
        resp = api_client.get(f"/assignments/{a.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["stats_mean"] is None
        assert resp.data["stats_max"] is None
        assert resp.data["stats_min"] is None

    def test_graded_assignment_still_reports_real_numbers(self, api_client,
                                                          admin, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, name="HW2", points=100)
        # update() bypasses Submission.save()'s grade recomputation, pinning a
        # genuine 0-point finalized grade.
        a.submissions.update(grade=0, isFinalized=True,
                             grader=course.graders.first())
        api_client.force_authenticate(user=admin)
        resp = api_client.get(f"/assignments/{a.id}/")
        # A real 0 stays 0 — only absent data is null.
        assert resp.data["stats_mean"] == 0
        assert resp.data["stats_max"] == 0


class TestIsLateComputed:

    @pytest.fixture
    def due_assignment(self, course):
        from core.tests.factories import AssignmentFactory
        due = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, name="HW3", points=100,
                                  uploadDueDate=due)
        sub = a.submissions.first()
        sub.students.set([course.students.first()])
        sub.dateUploaded = due + datetime.timedelta(hours=2)
        with factory.django.mute_signals(post_save):
            sub.save()
        return a

    def test_list_submissions_computes_is_late(self, api_client, key,
                                               due_assignment):
        result = call(api_client, key, "codepost_list_submissions",
                      {"assignmentId": due_assignment.id,
                       "fields": ["id", "dateUploaded", "isLate"]})
        rows = result["structuredContent"]["data"]["rows"]
        assert rows and rows[0]["isLate"] is True

    def test_null_upload_date_reads_unknown_not_on_time(self, api_client, key,
                                                        due_assignment):
        sub = due_assignment.submissions.first()
        sub.dateUploaded = None
        with factory.django.mute_signals(post_save):
            sub.save()
        result = call(api_client, key, "codepost_list_submissions",
                      {"assignmentId": due_assignment.id,
                       "fields": ["id", "isLate"]})
        rows = result["structuredContent"]["data"]["rows"]
        assert rows and rows[0]["isLate"] is None

    def test_get_submission_includes_is_late(self, api_client, key,
                                             due_assignment):
        sub = due_assignment.submissions.first()
        result = call(api_client, key, "codepost_get_submission",
                      {"submissionId": sub.id})
        assert result["structuredContent"]["data"]["submission"]["isLate"] is True

    def test_late_submission_stats_count_unknown(self, api_client, admin,
                                                 due_assignment):
        sub = due_assignment.submissions.first()
        sub.dateUploaded = None
        with factory.django.mute_signals(post_save):
            sub.save()
        api_client.force_authenticate(user=admin)
        resp = api_client.get(f"/assignments/{due_assignment.id}/analytics/")
        assert resp.status_code == status.HTTP_200_OK
        late = resp.data["lateSubmissions"]
        assert late["unknown"] == 1


class TestEmptyDistributionExplained:

    def test_zero_points_reason(self, api_client, key, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, name="Ungradeable", points=0)
        result = call(api_client, key, "codepost_get_assignment_analytics",
                      {"assignmentId": a.id, "blocks": ["gradeDistribution"]})
        assert result["structuredContent"]["data"]["analytics"]["gradeDistribution"] == []
        assert any("0 points" in w for w in result["structuredContent"]["warnings"])

    def test_nothing_finalized_reason(self, api_client, key, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, name="Fresh", points=100)
        result = call(api_client, key, "codepost_get_assignment_analytics",
                      {"assignmentId": a.id, "blocks": ["gradeDistribution"]})
        assert any("finalized" in w for w in result["structuredContent"]["warnings"])


class TestInertComboWarnings:

    @pytest.fixture
    def assignment(self, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            return AssignmentFactory(course=course, name="HW4", points=100)

    def test_tests_affect_grade_without_tests_warns(self, api_client, key,
                                                    assignment):
        result = call(api_client, key, "codepost_update_assignment",
                      {"assignmentId": assignment.id, "testsAffectGrade": True})
        assert result["isError"] is False
        assert any("no test" in w for w in result["structuredContent"]["warnings"])

    def test_max_late_days_without_late_uploads_warns(self, api_client, key,
                                                      assignment):
        result = call(api_client, key, "codepost_update_assignment",
                      {"assignmentId": assignment.id, "maxLateDays": 3})
        assert any("allowLateUploads" in w
                   for w in result["structuredContent"]["warnings"])


class TestFileGetOp:

    def test_round_trip_content(self, api_client, key, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, name="HW5", points=100)
        added = call(api_client, key, "codepost_manage_assignment_files",
                     {"assignmentId": a.id, "op": "add", "name": "starter.py",
                      "content": "def solve():\n    pass\n"})
        assert added["isError"] is False, added["content"][0]["text"]
        file_id = added["structuredContent"]["data"]["file"]["id"]

        got = call(api_client, key, "codepost_manage_assignment_files",
                   {"assignmentId": a.id, "op": "get", "fileId": file_id})
        assert got["isError"] is False
        got_file = got["structuredContent"]["data"]["file"]
        assert got_file["content"] == "def solve():\n    pass\n"

        listed = call(api_client, key, "codepost_manage_assignment_files",
                      {"assignmentId": a.id, "op": "list"})
        assert any("op='get'" in w for w in listed["structuredContent"]["warnings"])
