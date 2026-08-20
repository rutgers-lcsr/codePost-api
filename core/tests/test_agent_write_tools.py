# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Phase 3 write tools: setup flows, guardrail tiers, and the audit trail.

Everything runs through /mcp so a pass covers the JSON-RPC envelope, the
executor's write gates (scope re-check, archived preflight, audit), and the
real viewset permissions behind the dispatch.
"""
import json

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
        return CourseFactory(name="cs501", period="f2026", organization__name="TestOrg")


@pytest.fixture
def admin(course):
    return course.courseAdmins.first()


@pytest.fixture
def api_client():
    return APIClient()


def _mint(api_client, course, admin, scope, name):
    api_client.force_authenticate(user=admin)
    resp = api_client.post(f"/courses/{course.id}/apiKeys/",
                           {"name": name, "scope": scope}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    api_client.force_authenticate(user=None)
    return resp.data["key"]


@pytest.fixture
def write_key(api_client, course, admin):
    return _mint(api_client, course, admin, "write", "w-key")


@pytest.fixture
def read_key(api_client, course, admin):
    return _mint(api_client, course, admin, "read", "r-key")


def call(api_client, key, name, arguments=None):
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=V)
    resp = api_client.post(MCP_URL, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }, format="json")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    return resp.data


def result_of(payload):
    return payload["result"]


def error_of(result):
    return json.loads(result["content"][0]["text"])["error"]


# ---------------------------------------------------------------------------
# Scope filtering
# ---------------------------------------------------------------------------

class TestWriteScope:

    def test_read_key_never_sees_write_tools(self, api_client, read_key):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {read_key}",
                               HTTP_MCP_PROTOCOL_VERSION=V)
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1,
                                         "method": "tools/list"}, format="json")
        names = {t["name"] for t in resp.data["result"]["tools"]}
        assert "codepost_create_assignment" not in names
        assert "codepost_create_quiz" not in names

    def test_read_key_calling_write_tool_gets_unknown_tool(self, api_client, read_key):
        """Hidden means hidden: the refusal must not confirm the tool exists."""
        payload = call(api_client, read_key, "codepost_create_assignment",
                       {"name": "X", "points": 10})
        assert payload["error"]["code"] == -32601

    def test_write_key_sees_write_tools(self, api_client, write_key):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {write_key}",
                               HTTP_MCP_PROTOCOL_VERSION=V)
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1,
                                         "method": "tools/list"}, format="json")
        names = {t["name"] for t in resp.data["result"]["tools"]}
        assert "codepost_create_assignment" in names
        assert "codepost_create_quiz" in names


# ---------------------------------------------------------------------------
# Assignment setup
# ---------------------------------------------------------------------------

class TestAssignmentSetup:

    def test_create_lands_as_hidden_draft(self, api_client, write_key, course):
        from core.models import Assignment
        result = result_of(call(api_client, write_key, "codepost_create_assignment",
                                {"name": "HW9", "points": 100,
                                 "allowStudentUpload": True}))
        assert result["isError"] is False, result
        data = result["structuredContent"]["data"]["assignment"]
        assert data["state"] == "draft"
        assert data["feedbackStatus"] == "hidden"
        row = Assignment.objects.get(pk=data["id"])
        assert row.state == "draft"

    def test_create_cannot_smuggle_state(self, api_client, write_key):
        payload = call(api_client, write_key, "codepost_create_assignment",
                       {"name": "HW10", "points": 10, "state": "published"})
        assert payload["error"]["code"] == -32602
        assert "state" in payload["error"]["message"]

    def test_update_cannot_touch_lifecycle_fields(self, api_client, write_key, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course)
        payload = call(api_client, write_key, "codepost_update_assignment",
                       {"assignmentId": a.id, "feedbackStatus": "released"})
        assert payload["error"]["code"] == -32602

    def test_stage_dry_run_previews_without_writing(self, api_client, write_key, course):
        from core.models import Assignment
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="draft")

        result = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                                {"assignmentId": a.id, "targetStage": "published"}))
        assert result["isError"] is False
        plan = result["structuredContent"]["data"]["plan"]
        assert plan["studentImpact"]["canSubmit"]["after"] is True
        assert plan["studentImpact"]["canSeeGradesOrComments"]["after"] is False
        # Nothing written
        assert Assignment.objects.get(pk=a.id).state == "draft"

    def test_stage_apply_moves_forward(self, api_client, write_key, course):
        from core.models import Assignment
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="draft")

        result = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                                {"assignmentId": a.id, "targetStage": "published",
                                 "dryRun": False}))
        assert result["isError"] is False, result
        assert Assignment.objects.get(pk=a.id).state == "published"

    def test_unpublish_with_submissions_is_blocked(self, api_client, write_key, course):
        from core.models import Assignment
        from core.tests.factories import AssignmentFactory, SubmissionFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="published")
            sub = SubmissionFactory(assignment=a)
            sub.students.set([course.students.first()])

        result = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                                {"assignmentId": a.id, "targetStage": "draft",
                                 "dryRun": False}))
        assert result["isError"] is True
        err = error_of(result)
        assert err["code"] == "ILLEGAL_TRANSITION"
        assert "closed" in err["remedy"]
        assert Assignment.objects.get(pk=a.id).state == "published"

    def test_zero_submission_unpublish_needs_confirm_token(
            self, api_client, write_key, course):
        from core.models import Assignment
        # Direct create: AssignmentFactory auto-seeds a submission, and this
        # test needs a genuinely submission-free published assignment.
        with factory.django.mute_signals(post_save):
            a = Assignment.objects.create(course=course, name="Empty1",
                                          points=10, state="published")

        first = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                               {"assignmentId": a.id, "targetStage": "draft"}))
        assert first["isError"] is True
        err = error_of(first)
        assert err["code"] == "CONFIRMATION_REQUIRED"
        token = err["context"]["confirmToken"]

        second = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                                {"assignmentId": a.id, "targetStage": "draft",
                                 "dryRun": False, "confirmToken": token}))
        assert second["isError"] is False, second
        assert Assignment.objects.get(pk=a.id).state == "draft"

    def test_confirm_token_does_not_transfer_between_operations(
            self, api_client, write_key, course):
        from core.models import Assignment
        with factory.django.mute_signals(post_save):
            a = Assignment.objects.create(course=course, name="EmptyA",
                                          points=10, state="published")
            b = Assignment.objects.create(course=course, name="EmptyB",
                                          points=10, state="published")

        first = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                               {"assignmentId": a.id, "targetStage": "draft"}))
        token = error_of(first)["context"]["confirmToken"]

        stolen = result_of(call(api_client, write_key, "codepost_set_assignment_stage",
                                {"assignmentId": b.id, "targetStage": "draft",
                                 "dryRun": False, "confirmToken": token}))
        assert stolen["isError"] is True
        assert error_of(stolen)["code"] == "CONFIRM_TOKEN_STALE"

    def test_feedback_release_warns_about_unfinalized(self, api_client, write_key, course):
        from core.tests.factories import AssignmentFactory, SubmissionFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="published")
            sub = SubmissionFactory(assignment=a, isFinalized=False)
            sub.students.set([course.students.first()])

        result = result_of(call(api_client, write_key, "codepost_set_feedback_stage",
                                {"assignmentId": a.id, "targetStage": "released"}))
        assert result["isError"] is False
        plan = result["structuredContent"]["data"]["plan"]
        assert plan["submissions"]["unfinalized"] >= 1
        assert any("not finalized" in w for w in plan["warnings"])

    def test_revoking_release_needs_token(self, api_client, write_key, course):
        from core.models import Assignment
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="published",
                                  feedbackStatus="released")

        first = result_of(call(api_client, write_key, "codepost_set_feedback_stage",
                               {"assignmentId": a.id, "targetStage": "hidden"}))
        assert error_of(first)["code"] == "CONFIRMATION_REQUIRED"
        token = error_of(first)["context"]["confirmToken"]

        second = result_of(call(api_client, write_key, "codepost_set_feedback_stage",
                                {"assignmentId": a.id, "targetStage": "hidden",
                                 "dryRun": False, "confirmToken": token}))
        assert second["isError"] is False, second
        assert Assignment.objects.get(pk=a.id).feedbackStatus == "hidden"


# ---------------------------------------------------------------------------
# Quiz setup
# ---------------------------------------------------------------------------

_QUIZ_QUESTIONS = [
    {"questionType": "multiple_choice", "text": "What is 2+2?", "points": 2,
     "choices": [{"text": "3"}, {"text": "4", "isCorrect": True}]},
    {"questionType": "true_false", "text": "The sky is blue.",
     "choices": [{"text": "True", "isCorrect": True}, {"text": "False"}]},
    {"questionType": "essay", "text": "Explain recursion."},
]


class TestQuizSetup:

    def test_dry_run_previews_plan(self, api_client, write_key):
        from core.models import Quiz
        result = result_of(call(api_client, write_key, "codepost_create_quiz",
                                {"title": "Week 1 Check", "questions": _QUIZ_QUESTIONS}))
        assert result["isError"] is False
        plan = result["structuredContent"]["data"]["plan"]
        assert plan["totalPoints"] == 4.0
        assert plan["manuallyGraded"] == 1
        assert Quiz.objects.count() == 0

    def test_keyless_auto_graded_question_is_rejected(self, api_client, write_key):
        result = result_of(call(api_client, write_key, "codepost_create_quiz",
                                {"title": "Bad", "questions": [
                                    {"questionType": "multiple_choice",
                                     "text": "Pick one",
                                     "choices": [{"text": "A"}, {"text": "B"}]}]}))
        assert result["isError"] is True
        assert error_of(result)["code"] == "PRECONDITION_NOT_MET"

    def test_create_composes_bank_questions_quiz_links(
            self, api_client, write_key, course):
        from core.models import Question, QuestionBank, Quiz, QuizQuestion
        result = result_of(call(api_client, write_key, "codepost_create_quiz",
                                {"title": "Week 1 Check",
                                 "questions": _QUIZ_QUESTIONS,
                                 "dryRun": False}))
        assert result["isError"] is False, result
        data = result["structuredContent"]["data"]["quiz"]

        quiz = Quiz.objects.get(pk=data["id"])
        assert quiz.isPublished is False
        assert quiz.course_id == course.id
        assert QuizQuestion.objects.filter(quiz=quiz).count() == 3
        assert QuestionBank.objects.filter(course=course, name="Week 1 Check").exists()
        # Order preserved
        links = list(QuizQuestion.objects.filter(quiz=quiz).order_by('sortKey'))
        assert links[0].question.text == "What is 2+2?"

    def test_create_attached_to_assignment(self, api_client, write_key, course):
        from core.models import Quiz
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course)

        result = result_of(call(api_client, write_key, "codepost_create_quiz",
                                {"title": "Attached", "assignmentId": a.id,
                                 "questions": _QUIZ_QUESTIONS[:1],
                                 "assignmentTrigger": "after_submission",
                                 "dryRun": False}))
        assert result["isError"] is False, result
        quiz = Quiz.objects.get(pk=result["structuredContent"]["data"]["quiz"]["id"])
        assert quiz.assignment_id == a.id
        assert quiz.assignmentTrigger == "after_submission"

    def test_publish_with_zero_questions_warns(self, api_client, write_key, course):
        from core.models import Quiz
        quiz = Quiz.objects.create(course=course, title="Empty")

        result = result_of(call(api_client, write_key, "codepost_update_quiz",
                                {"quizId": quiz.id, "publish": True}))
        assert result["isError"] is False
        assert any("ZERO questions" in w for w in result["structuredContent"]["warnings"])
        assert Quiz.objects.get(pk=quiz.id).isPublished is False   # dry run

    def test_publish_applies(self, api_client, write_key, course):
        from core.models import Quiz
        quiz = Quiz.objects.create(course=course, title="Ready")
        result = result_of(call(api_client, write_key, "codepost_update_quiz",
                                {"quizId": quiz.id, "publish": True,
                                 "dryRun": False}))
        assert result["isError"] is False, result
        assert Quiz.objects.get(pk=quiz.id).isPublished is True


# ---------------------------------------------------------------------------
# Central write gates
# ---------------------------------------------------------------------------

class TestWriteGates:

    def test_archived_course_blocks_every_write(self, api_client, course, admin):
        key = _mint(api_client, course, admin, "write", "arch-key")
        course.archived = True
        course.save()

        result = result_of(call(api_client, key, "codepost_create_assignment",
                                {"name": "Nope", "points": 1}))
        assert result["isError"] is True
        assert error_of(result)["code"] == "COURSE_ARCHIVED"

    def test_applied_write_records_agent_write_event(
            self, api_client, write_key, course):
        from core.models import CourseAuditEvent
        result = result_of(call(api_client, write_key, "codepost_create_assignment",
                                {"name": "Audited", "points": 5}))
        assert result["isError"] is False
        event = CourseAuditEvent.objects.filter(
            course=course, event_type="agent_write").latest("created")
        assert event.meta["tool"] == "codepost_create_assignment"
        assert event.meta["applied"] is True
        assert event.meta["origin"] == "mcp"

    def test_denied_write_records_denial_event(self, api_client, course, admin):
        from core.models import CourseAuditEvent
        key = _mint(api_client, course, admin, "write", "deny-key")
        course.archived = True
        course.save()

        call(api_client, key, "codepost_create_assignment", {"name": "X", "points": 1})
        event = CourseAuditEvent.objects.filter(
            course=course, event_type="agent_write_denied").latest("created")
        assert event.meta["deniedCode"] == "COURSE_ARCHIVED"

    def test_dry_run_is_not_recorded_as_applied(self, api_client, write_key, course):
        from core.models import CourseAuditEvent
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="draft")

        call(api_client, write_key, "codepost_set_assignment_stage",
             {"assignmentId": a.id, "targetStage": "visible"})
        event = CourseAuditEvent.objects.filter(
            course=course, event_type="agent_write").latest("created")
        assert event.meta["applied"] is False
