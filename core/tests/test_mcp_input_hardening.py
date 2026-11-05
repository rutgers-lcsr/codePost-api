# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Malformed or awkward MCP input must yield a JSON-RPC error or an isError
result the model can recover from — never an HTTP 500 — and must not corrupt
the lookups the tools replay through the real viewsets."""
import json

import factory
import pytest
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient

MCP_URL = "/mcp"
V = "2025-06-18"
INVALID_PARAMS = -32602


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs801", period="f2026", organization__name="TestOrg")


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
                           {"name": "hardening-key", "scope": "admin"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    api_client.force_authenticate(user=None)
    return resp.data["key"]


def rpc(api_client, key, method, params):
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=V)
    return api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1, "method": method,
                                     "params": params}, format="json")


def call_raw(api_client, key, name, arguments):
    return rpc(api_client, key, "tools/call", {"name": name, "arguments": arguments})


def call(api_client, key, name, arguments):
    resp = call_raw(api_client, key, name, arguments)
    assert resp.status_code == status.HTTP_200_OK, resp.content
    return resp.data["result"]


@pytest.fixture
def draft(course):
    from core.models import Assignment
    with factory.django.mute_signals(post_save):
        return Assignment.objects.create(course=course, name="HWX", points=10,
                                         state="draft")



@pytest.fixture
def roster_assignment(course):
    from core.models import Submission
    from core.tests.factories import AssignmentFactory
    from django.contrib.auth.models import User
    with factory.django.mute_signals(post_save):
        a = AssignmentFactory(course=course, name="HWM", state="published")
        a.submissions.all().delete()
        users = {}
        for name in ("alpha", "beta", "plus+tag"):
            u = User.objects.create(username=name, email=f"{name}@uni.example")
            course.students.add(u)
            users[name] = u
        s = Submission.objects.create(assignment=a)
        s.students.set([users["alpha"]])
        s.grader = course.graders.first()
        s.save()
        # Plus-tagged student submits too.
        p = Submission.objects.create(assignment=a)
        p.students.set([users["plus+tag"]])
    return a, users


def alias_of(course, email):
    from core.agent.privacy import alias_for
    return alias_for(course.id, email)



class TestNonObjectParams:

    @pytest.mark.parametrize("method", ["initialize", "tools/call", "tools/list"])
    @pytest.mark.parametrize("params", [["x"], "str", 5])
    def test_params_must_be_an_object(self, api_client, key, method, params):
        resp = rpc(api_client, key, method, params)
        assert resp.status_code == status.HTTP_200_OK, resp.content
        assert resp.data["error"]["code"] == INVALID_PARAMS



class TestArgumentTypes:

    def test_string_for_array_is_invalid_params(self, api_client, key, draft):
        resp = call_raw(api_client, key, "codepost_edit_rubric",
                        {"assignmentId": draft.id, "categories": "abc"})
        assert resp.status_code == status.HTTP_200_OK, resp.content
        assert resp.data["error"]["code"] == INVALID_PARAMS

    def test_non_object_item_is_invalid_params(self, api_client, key, draft):
        resp = call_raw(api_client, key, "codepost_edit_rubric",
                        {"assignmentId": draft.id, "categories": ["x"]})
        assert resp.status_code == status.HTTP_200_OK, resp.content
        assert resp.data["error"]["code"] == INVALID_PARAMS

    def test_nested_required_key_is_invalid_params(self, api_client, key, draft):
        resp = call_raw(api_client, key, "codepost_edit_rubric",
                        {"assignmentId": draft.id, "categories": [{"name": "x"}]})
        assert resp.status_code == status.HTTP_200_OK, resp.content
        assert resp.data["error"]["code"] == INVALID_PARAMS

    def test_string_for_integer_is_invalid_params(self, api_client, key):
        resp = call_raw(api_client, key, "codepost_get_assignment",
                        {"assignmentId": "abc"})
        assert resp.status_code == status.HTTP_200_OK, resp.content
        assert resp.data["error"]["code"] == INVALID_PARAMS

    def test_null_for_an_optional_argument_still_means_omitted(
            self, api_client, key, roster_assignment):
        a, _ = roster_assignment
        result = call(api_client, key, "codepost_list_submissions",
                      {"assignmentId": a.id, "student": None, "grader": None,
                       "fields": None})
        assert result["isError"] is False, result["content"][0]["text"]

    def test_boolean_is_not_an_integer(self, api_client, key):
        resp = call_raw(api_client, key, "codepost_get_assignment",
                        {"assignmentId": True})
        assert resp.data["error"]["code"] == INVALID_PARAMS



class TestEditRubricMissingId:

    @pytest.mark.parametrize("field,item", [
        ("categories", {"op": "delete"}),
        ("categories", {"op": "update", "name": "x"}),
        ("comments", {"op": "delete"}),
        ("comments", {"op": "update", "text": "x"}),
    ])
    def test_update_or_delete_without_id_is_a_tool_error_and_applies_nothing(
            self, api_client, key, draft, field, item):
        from core.models import RubricCategory
        before = RubricCategory.objects.filter(assignment=draft).count()
        result = call(api_client, key, "codepost_edit_rubric", {
            "assignmentId": draft.id,
            # A valid create earlier in the batch must NOT be applied.
            "categories": [{"op": "create", "name": "Early", "pointLimit": 1}]
                          + ([item] if field == "categories" else []),
            **({"comments": [item]} if field == "comments" else {}),
        })
        assert result["isError"] is True
        assert json.loads(result["content"][0]["text"])["error"]["retryable"] is True
        assert RubricCategory.objects.filter(assignment=draft).count() == before

    def test_create_needs_no_id(self, api_client, key, draft):
        from core.models import RubricCategory
        result = call(api_client, key, "codepost_edit_rubric", {
            "assignmentId": draft.id,
            "categories": [{"op": "create", "name": "Style", "pointLimit": 2}]})
        assert result["isError"] is False, result["content"][0]["text"]
        assert RubricCategory.objects.filter(assignment=draft, name="Style").exists()



class TestListSubmissionsFilters:

    def test_missing_with_student_filter_is_rejected_not_wrong(
            self, api_client, key, course, roster_assignment):
        a, _ = roster_assignment
        result = call(api_client, key, "codepost_list_submissions",
                      {"assignmentId": a.id, "status": "missing",
                       "student": alias_of(course, "alpha@uni.example")})
        assert result["isError"] is True
        assert json.loads(result["content"][0]["text"])["error"]["retryable"] is True

    def test_missing_with_grader_filter_is_rejected_not_wrong(
            self, api_client, key, course, roster_assignment):
        a, _ = roster_assignment
        result = call(api_client, key, "codepost_list_submissions",
                      {"assignmentId": a.id, "status": "missing",
                       "grader": course.graders.first().email})
        assert result["isError"] is True

    def test_plus_addressed_student_filter_matches(
            self, api_client, key, course, roster_assignment):
        a, _ = roster_assignment
        result = call(api_client, key, "codepost_list_submissions",
                      {"assignmentId": a.id,
                       "student": alias_of(course, "plus+tag@uni.example")})
        assert result["isError"] is False, result["content"][0]["text"]
        rows = result["structuredContent"]["data"]["rows"]
        assert len(rows) == 1



class TestAuditRedaction:

    def test_short_student_args_are_not_stored_verbatim(
            self, api_client, key, course):
        from core.models import CourseAuditEvent
        call(api_client, key, "codepost_manage_sections",
             {"op": "setMembers", "sectionId": 999999, "dryRun": True,
              "students": ["jane.doe@scarletmail.rutgers.edu"]})
        events = CourseAuditEvent.objects.filter(course=course,
                                                 event_type__startswith="agent_write")
        assert events.exists()
        for e in events:
            blob = json.dumps(e.meta).lower()
            assert "jane.doe" not in blob
            assert "scarletmail" not in blob



    def test_roster_student_is_aliased_and_staff_email_stays_readable(
            self, api_client, key, course):
        from core.models import CourseAuditEvent
        student = course.students.first()
        staff = course.graders.first().email
        call(api_client, key, "codepost_manage_sections",
             {"op": "setMembers", "sectionId": 999999, "dryRun": True,
              "students": [student.email], "leaders": [staff]})
        event = CourseAuditEvent.objects.filter(
            course=course, event_type__startswith="agent_write").latest("id")
        assert event.meta["args"]["students"] == [alias_of(course, student.email)]
        assert event.meta["args"]["leaders"] == [staff]


class TestCheckValue:
    """The schema slice the tool schemas use, pinned directly where no
    registered tool exercises it."""

    def test_array_without_items_accepts_any_elements(self):
        from core.mcp.protocol import _check_value
        assert _check_value([1, "a"], {"type": "array"}, "x") is None

    def test_nested_property_types_are_enforced(self):
        from core.mcp.protocol import _check_value
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        assert _check_value({"n": 1}, schema, "x") is None
        assert _check_value({"n": "1"}, schema, "x") == \
            "x.n must be of type integer; got str"
