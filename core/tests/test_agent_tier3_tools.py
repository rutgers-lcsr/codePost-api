# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tier-3 tools and the out-of-band confirmation-code gate.

The property under test throughout: the agent cannot confirm a Tier-3
operation by itself. The code lives only in the dashboard endpoint, which
refuses the agent's own credential.
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
        return CourseFactory(name="cs901", period="f2026", organization__name="TestOrg")


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
    raw = resp.data["key"]
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw}")
    api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 0, "method": "ping"},
                    format="json")
    return raw


@pytest.fixture
def admin_key(api_client, course, admin):
    return _mint(api_client, course, admin, "admin", "t3-key")


@pytest.fixture
def write_key(api_client, course, admin):
    return _mint(api_client, course, admin, "write", "t3-write-key")


def call(api_client, key, name, arguments=None):
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=V)
    resp = api_client.post(MCP_URL, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }, format="json")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    return resp.data


def error_of(result):
    return json.loads(result["content"][0]["text"])["error"]


def dashboard_code(api_client, course, admin):
    """What a human does: read the code from the dashboard, signed in normally."""
    api_client.credentials()
    api_client.force_authenticate(user=admin)
    resp = api_client.get(f"/courses/{course.id}/pendingAgentActions/")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    api_client.force_authenticate(user=None)
    return resp.data


@pytest.fixture
def empty_assignment(course):
    from core.models import Assignment
    with factory.django.mute_signals(post_save):
        return Assignment.objects.create(course=course, name="Disposable",
                                         points=10, state="draft")


class TestScopeGate:

    def test_write_key_never_sees_tier3_tools(self, api_client, write_key):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {write_key}",
                               HTTP_MCP_PROTOCOL_VERSION=V)
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1,
                                         "method": "tools/list"}, format="json")
        names = {t["name"] for t in resp.data["result"]["tools"]}
        assert "codepost_delete_resource" not in names
        assert "codepost_reset_quiz_attempts" not in names
        assert "codepost_notify_students_feedback_ready" not in names

    def test_write_key_calling_gets_unknown_tool(self, api_client, write_key,
                                                 empty_assignment):
        payload = call(api_client, write_key, "codepost_delete_resource",
                       {"resourceType": "assignment",
                        "resourceId": empty_assignment.id})
        assert payload["error"]["code"] == -32601


class TestConfirmationCodes:

    def test_first_call_mints_dashboard_code_not_inline_token(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import PendingAgentAction

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id})["result"]
        assert result["isError"] is True
        err = error_of(result)
        assert err["code"] == "CONFIRMATION_REQUIRED"
        # The refusal must NOT carry anything redeemable — no code, no token.
        assert "confirmToken" not in err.get("context", {})
        assert "code" not in err.get("context", {})
        assert "dashboard" in err["remedy"].lower()

        row = PendingAgentAction.objects.get(course=course)
        assert row.tool == "codepost_delete_resource"
        assert row.is_active

    def test_agents_own_key_cannot_read_the_dashboard(
            self, api_client, admin_key, course, empty_assignment):
        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        # Same credential the agent holds → must be refused.
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}")
        resp = api_client.get(f"/courses/{course.id}/pendingAgentActions/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "course-scoped" in resp.data["detail"]

    def test_human_reads_code_and_agent_redeems_it_once(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import Assignment, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})

        rows = dashboard_code(api_client, course, admin)
        assert len(rows) == 1
        code = rows[0]["code"]
        assert rows[0]["plan"]["name"] == "Disposable"

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id,
                       "confirmationCode": code})["result"]
        assert result["isError"] is False, result["content"][0]["text"]
        assert not Assignment.objects.filter(pk=empty_assignment.id).exists()
        assert PendingAgentAction.objects.get(course=course).redeemed_at

    def test_wrong_or_stale_code_is_refused(self, api_client, admin_key, course,
                                            empty_assignment):
        from core.models import Assignment

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id,
                       "confirmationCode": "XXX-XXX"})["result"]
        assert error_of(result)["code"] == "CONFIRMATION_CODE_INVALID"
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()

    def test_denying_from_dashboard_kills_the_code(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import Assignment

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        rows = dashboard_code(api_client, course, admin)
        code, action_id = rows[0]["code"], rows[0]["id"]

        api_client.force_authenticate(user=admin)
        resp = api_client.post(
            f"/courses/{course.id}/pendingAgentActions/{action_id}/deny/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        api_client.force_authenticate(user=None)

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id,
                       "confirmationCode": code})["result"]
        assert error_of(result)["code"] == "CONFIRMATION_CODE_INVALID"
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()

    def test_expired_code_is_refused(self, api_client, admin_key, course, admin,
                                     empty_assignment):
        from django.utils import timezone
        from core.models import Assignment, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)
        code = row.code
        PendingAgentAction.objects.filter(pk=row.pk).update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1))

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id,
                       "confirmationCode": code})["result"]
        assert error_of(result)["code"] == "CONFIRMATION_CODE_INVALID"
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()

    def test_repeat_preview_reuses_the_active_code(
            self, api_client, admin_key, course, empty_assignment):
        from core.models import PendingAgentAction

        for _ in range(3):
            call(api_client, admin_key, "codepost_delete_resource",
                 {"resourceType": "assignment",
                  "resourceId": empty_assignment.id})
        assert PendingAgentAction.objects.filter(course=course).count() == 1


class TestTier3Tools:

    def test_delete_assignment_with_submissions_is_refused_outright(
            self, api_client, admin_key, course):
        from core.tests.factories import AssignmentFactory
        with factory.django.mute_signals(post_save):
            a = AssignmentFactory(course=course, state="published")

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment", "resourceId": a.id})["result"]
        err = error_of(result)
        assert err["code"] == "PRECONDITION_NOT_MET"
        assert "archived" in err["remedy"]

    def test_reset_attempts_plan_counts_graded_work(
            self, api_client, admin_key, course):
        from core.models import Quiz
        quiz = Quiz.objects.create(course=course, title="Resettable")

        result = call(api_client, admin_key, "codepost_reset_quiz_attempts",
                      {"quizId": quiz.id})["result"]
        err = error_of(result)
        assert err["code"] == "CONFIRMATION_REQUIRED"
        assert err["context"]["plan"]["studentsWithAttempts"] == 0

    def test_notify_requires_open_feedback(self, api_client, admin_key, course):
        from core.models import Assignment
        with factory.django.mute_signals(post_save):
            a = Assignment.objects.create(course=course, name="Hidden", points=5,
                                          state="published",
                                          feedbackStatus="hidden")
        result = call(api_client, admin_key,
                      "codepost_notify_students_feedback_ready",
                      {"assignmentId": a.id})["result"]
        err = error_of(result)
        assert err["code"] == "PRECONDITION_NOT_MET"
        assert "codepost_set_feedback_stage" in err["remedy"]
