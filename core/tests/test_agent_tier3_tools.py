# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tier-3 tools and the dashboard approval gate (the non-elicitation path).

The property under test throughout: the agent cannot confirm a Tier-3
operation by itself. Approval state can only be flipped by the dashboard
endpoints, which refuse the agent's own credential. (The in-chat elicitation
path is covered in test_mcp_elicitation.py.)
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


def dashboard_rows(api_client, course, admin):
    """What a human sees: the pending actions panel, signed in normally."""
    api_client.credentials()
    api_client.force_authenticate(user=admin)
    resp = api_client.get(f"/courses/{course.id}/pendingAgentActions/")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    api_client.force_authenticate(user=None)
    return resp.data


def dashboard_decide(api_client, course, admin, action_id, verb):
    api_client.credentials()
    api_client.force_authenticate(user=admin)
    resp = api_client.post(
        f"/courses/{course.id}/pendingAgentActions/{action_id}/{verb}/")
    api_client.force_authenticate(user=None)
    return resp


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


class TestDashboardApproval:

    def test_first_call_mints_pending_action_not_inline_token(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import PendingAgentAction

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id})["result"]
        assert result["isError"] is True
        err = error_of(result)
        assert err["code"] == "CONFIRMATION_REQUIRED"
        # The refusal must NOT carry anything redeemable — no code, no token.
        # The approveUrl is pure navigation, not a secret.
        assert "confirmToken" not in err.get("context", {})
        assert "code" not in err.get("context", {})
        assert "dashboard" in err["remedy"].lower()
        assert err["context"]["approveUrl"].endswith("?section=api-keys")

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

    def test_agents_own_key_cannot_approve(
            self, api_client, admin_key, course, empty_assignment):
        """The load-bearing security test: the agent's credential must never
        be able to flip a pending action to approved."""
        from core.models import PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)

        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {admin_key}")
        resp = api_client.post(
            f"/courses/{course.id}/pendingAgentActions/{row.id}/approve/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        row.refresh_from_db()
        assert row.approved_at is None

    def test_retry_while_pending_refuses_again(
            self, api_client, admin_key, course, empty_assignment):
        from core.models import Assignment

        for _ in range(2):
            result = call(api_client, admin_key, "codepost_delete_resource",
                          {"resourceType": "assignment",
                           "resourceId": empty_assignment.id})["result"]
            assert error_of(result)["code"] == "CONFIRMATION_REQUIRED"
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()

    def test_approve_then_retry_executes_once(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import Assignment, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})

        rows = dashboard_rows(api_client, course, admin)
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["plan"]["name"] == "Disposable"
        assert "code" not in rows[0]

        resp = dashboard_decide(api_client, course, admin, rows[0]["id"],
                                "approve")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id})["result"]
        assert result["isError"] is False, result["content"][0]["text"]
        assert not Assignment.objects.filter(pk=empty_assignment.id).exists()
        assert PendingAgentAction.objects.get(course=course).redeemed_at

    def test_approval_is_single_use(
            self, api_client, admin_key, course, admin, empty_assignment):
        """A consumed approval never authorises again — the claim is a
        conditional update, so a racing duplicate loses."""
        from core.models import PendingAgentAction
        from django.utils import timezone

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)
        PendingAgentAction.objects.filter(pk=row.pk).update(
            approved_at=timezone.now(), redeemed_at=timezone.now())

        # The direct claim (what a concurrent retry runs) must find 0 rows.
        claimed = PendingAgentAction.objects.filter(
            pk=row.pk, redeemed_at=None, denied_at=None,
            expires_at__gt=timezone.now()).update(redeemed_at=timezone.now())
        assert claimed == 0

    def test_deny_blocks_re_requests(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import Assignment, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        rows = dashboard_rows(api_client, course, admin)
        resp = dashboard_decide(api_client, course, admin, rows[0]["id"], "deny")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id})["result"]
        err = error_of(result)
        assert err["code"] == "CONFIRMATION_DENIED"
        assert err["retryable"] is False
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()
        # No fresh row minted while the denial holds; the panel shows nothing.
        assert PendingAgentAction.objects.filter(course=course).count() == 1
        assert dashboard_rows(api_client, course, admin) == []

    def test_approve_after_deny_conflicts(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)
        dashboard_decide(api_client, course, admin, row.id, "deny")
        resp = dashboard_decide(api_client, course, admin, row.id, "approve")
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_expired_request_is_gone(self, api_client, admin_key, course, admin,
                                     empty_assignment):
        from django.utils import timezone
        from core.models import Assignment, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)
        PendingAgentAction.objects.filter(pk=row.pk).update(
            approved_at=timezone.now(),
            expires_at=timezone.now() - timezone.timedelta(minutes=1))

        # An expired approval cannot authorise; a fresh request is minted.
        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id})["result"]
        assert error_of(result)["code"] == "CONFIRMATION_REQUIRED"
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()
        assert PendingAgentAction.objects.filter(course=course).count() == 2

    def test_repeat_preview_reuses_the_active_request(
            self, api_client, admin_key, course, empty_assignment):
        from core.models import PendingAgentAction

        for _ in range(3):
            call(api_client, admin_key, "codepost_delete_resource",
                 {"resourceType": "assignment",
                  "resourceId": empty_assignment.id})
        assert PendingAgentAction.objects.filter(course=course).count() == 1

    def test_stale_approval_dies_when_plan_drifts(
            self, api_client, admin_key, course, admin, empty_assignment):
        """An approval granted for one blast radius must not authorise a
        different one — the stale row is expired and a fresh request minted."""
        from django.utils import timezone
        from core.models import Assignment, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)
        PendingAgentAction.objects.filter(pk=row.pk).update(
            approved_at=timezone.now())
        # Drift the plan out from under the approval (name feeds the plan).
        Assignment.objects.filter(pk=empty_assignment.id).update(
            name="Disposable v2")

        result = call(api_client, admin_key, "codepost_delete_resource",
                      {"resourceType": "assignment",
                       "resourceId": empty_assignment.id})["result"]
        err = error_of(result)
        assert err["code"] == "CONFIRMATION_REQUIRED"
        assert "invalidated" in err["message"]
        assert Assignment.objects.filter(pk=empty_assignment.id).exists()
        row.refresh_from_db()
        assert not row.is_active                        # superseded, expired

    def test_dashboard_decisions_are_audited(
            self, api_client, admin_key, course, admin, empty_assignment):
        from core.models import CourseAuditEvent, PendingAgentAction

        call(api_client, admin_key, "codepost_delete_resource",
             {"resourceType": "assignment", "resourceId": empty_assignment.id})
        row = PendingAgentAction.objects.get(course=course)
        dashboard_decide(api_client, course, admin, row.id, "approve")
        event = CourseAuditEvent.objects.filter(
            course=course, event_type="agent_action_approved").first()
        assert event is not None
        assert event.meta["tool"] == "codepost_delete_resource"
        assert event.meta["origin"] == "dashboard"


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
