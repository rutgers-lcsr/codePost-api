# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Happy-path coverage for the Phase 2 read tools, driven through /mcp.

Each test goes through the full stack — JSON-RPC envelope, tool executor,
in-process dispatch, real viewset — so a passing test means the whole
credential-to-permission path works, not just the tool function.
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
        return CourseFactory(name="cs401", period="f2026", organization__name="TestOrg")


@pytest.fixture
def admin(course):
    return course.courseAdmins.first()


@pytest.fixture
def assignment(course):
    from core.tests.factories import AssignmentFactory
    with factory.django.mute_signals(post_save):
        return AssignmentFactory(course=course, name="HW1", points=100)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def key(api_client, course, admin):
    api_client.force_authenticate(user=admin)
    resp = api_client.post(f"/courses/{course.id}/apiKeys/",
                           {"name": "read-tools-key", "scope": "admin"}, format="json")
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


class TestReadTools:

    def test_gradebook_summary(self, api_client, key, course, assignment):
        result = call(api_client, key, "codepost_get_gradebook")
        assert result["isError"] is False
        data = result["structuredContent"]["data"]
        assert data["course"]["id"] == course.id
        cols = {c["column"] for c in data["perColumn"]}
        assert f"assignment:{assignment.id}" in cols

    def test_gradebook_rows_flatten_cells(self, api_client, key, course, assignment):
        result = call(api_client, key, "codepost_get_gradebook",
                      {"view": "rows", "limit": 5})
        assert result["isError"] is False
        rows = result["structuredContent"]["data"]["rows"]
        # CourseFactory seeds students; each row's grades are name-keyed.
        if rows:
            assert "HW1" in rows[0]["grades"]

    def test_analytics_requires_block_selection_to_stay_small(
            self, api_client, key, assignment):
        result = call(api_client, key, "codepost_get_assignment_analytics",
                      {"assignmentId": assignment.id,
                       "blocks": ["gradeDistribution"]})
        assert result["isError"] is False
        analytics = result["structuredContent"]["data"]["analytics"]
        assert set(analytics.keys()) == {"gradeDistribution"}

    def test_rubric_returns_category_and_comment_ids(
            self, api_client, key, course, assignment):
        from core.tests.factories import RubricCategoryFactory, RubricCommentFactory
        with factory.django.mute_signals(post_save):
            category = RubricCategoryFactory(assignment=assignment, name="Style")
            RubricCommentFactory(category=category, pointDelta=-2)

        result = call(api_client, key, "codepost_get_rubric",
                      {"assignmentId": assignment.id})
        assert result["isError"] is False
        data = result["structuredContent"]["data"]
        # AssignmentFactory seeds a default category, so search by name.
        names = {c["name"] for c in data["rubricCategories"]}
        assert "Style" in names
        assert any(c["pointDelta"] == -2 for c in data["rubricComments"])

    def test_audit_log_translates_snake_case_params(self, api_client, key, course):
        from core.services.audit import record_audit_event
        record_audit_event(course=course, event_type="assignment_state_changed",
                           meta={"from": "draft", "to": "visible"})

        result = call(api_client, key, "codepost_get_audit_log",
                      {"eventType": "assignment_state_changed"})
        assert result["isError"] is False
        events = result["structuredContent"]["data"]["events"]
        assert events and events[0]["eventType"] == "assignment_state_changed"

    def test_audit_log_group_by(self, api_client, key, course):
        from core.services.audit import record_audit_event
        for _ in range(3):
            record_audit_event(course=course, event_type="file_view")

        result = call(api_client, key, "codepost_get_audit_log",
                      {"groupBy": "eventType"})
        counts = result["structuredContent"]["data"]["counts"]
        assert counts.get("file_view") == 3

    def test_quiz_status_list_empty_course(self, api_client, key, course):
        result = call(api_client, key, "codepost_get_quiz_status")
        assert result["isError"] is False
        assert result["structuredContent"]["data"]["quizzes"] == []

    def test_quiz_results_without_quiz_id_self_corrects(self, api_client, key):
        result = call(api_client, key, "codepost_get_quiz_status",
                      {"view": "results"})
        assert result["isError"] is True
        payload = json.loads(result["content"][0]["text"])
        assert payload["error"]["retryable"] is True
        assert "quizId" in payload["error"]["message"]

    def test_submission_detail(self, api_client, key, course, assignment):
        from core.tests.factories import SubmissionFactory
        with factory.django.mute_signals(post_save):
            sub = SubmissionFactory(assignment=assignment)
            sub.students.set([course.students.first()])

        result = call(api_client, key, "codepost_get_submission",
                      {"submissionId": sub.id})
        assert result["isError"] is False
        data = result["structuredContent"]["data"]
        assert data["submission"]["id"] == sub.id
        # Files and comments must never ride along.
        assert "files" not in data["submission"]

    def test_poll_job_unknown_task_reports_pending(self, api_client, key):
        """An unknown Celery task id reads as PENDING — the tool must map that
        to a pending state rather than erroring."""
        result = call(api_client, key, "codepost_poll_job",
                      {"jobId": "no-such-task-id", "jobType": "autograderTask"})
        assert result["isError"] is False
        assert result["structuredContent"]["data"]["state"] == "pending"
