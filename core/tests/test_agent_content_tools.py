# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Phase 3b: assignment content & autograder tools through /mcp."""
import json

import factory
import pytest
from django.db.models.signals import post_delete, post_save
from rest_framework import status
from rest_framework.test import APIClient

MCP_URL = "/mcp"
V = "2025-06-18"

SCRIPT = '''
from codepost_test import test

@test("Adds two numbers", 5)
def test_add(student):
    assert student.add(1, 2) == 3

@test("Handles negatives", points=3)
def test_negative(student):
    assert student.add(-1, -2) == -3
'''


@pytest.fixture
def course(db):
    from core.tests.factories import CourseFactory
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs701", period="f2026", organization__name="TestOrg")


@pytest.fixture
def admin(course):
    return course.courseAdmins.first()


@pytest.fixture
def assignment(course):
    from core.models import Assignment
    with factory.django.mute_signals(post_save):
        return Assignment.objects.create(course=course, name="HW1", points=100,
                                         state="draft")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def key(api_client, course, admin):
    api_client.force_authenticate(user=admin)
    resp = api_client.post(f"/courses/{course.id}/apiKeys/",
                           {"name": "content-key", "scope": "write"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    api_client.force_authenticate(user=None)
    raw = resp.data["key"]
    # Warm up the service account OUTSIDE any mute_signals block: its Profile is
    # auto-created by a post_save signal on first authentication, and tests that
    # mute signals around tool calls would otherwise create a profile-less user.
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {raw}")
    api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 0, "method": "ping"},
                    format="json")
    return raw


def call(api_client, key, name, arguments=None):
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=V)
    resp = api_client.post(MCP_URL, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }, format="json")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    return resp.data["result"]


def error_of(result):
    return json.loads(result["content"][0]["text"])["error"]


class TestAssignmentFiles:

    def test_add_and_list(self, api_client, key, course, assignment):
        from core.models import AssignmentFile
        with factory.django.mute_signals(post_save):
            result = call(api_client, key, "codepost_manage_assignment_files",
                          {"assignmentId": assignment.id, "op": "add",
                           "name": "starter.py",
                           "content": "def add(a, b):\n    pass  # TODO\n",
                           "description": "Starter code"})
        assert result["isError"] is False, result["content"][0]["text"]
        file_data = result["structuredContent"]["data"]["file"]
        assert file_data["name"] == "starter.py"
        assert file_data["extension"] == ".py"

        row = AssignmentFile.objects.get(pk=file_data["id"])
        assert "TODO" in row.data

        listing = call(api_client, key, "codepost_manage_assignment_files",
                       {"assignmentId": assignment.id, "op": "list"})
        files = listing["structuredContent"]["data"]["files"]
        assert any(f["name"] == "starter.py" for f in files)

    def test_required_file_warns_about_manifest(self, api_client, key, assignment):
        with factory.django.mute_signals(post_save):
            result = call(api_client, key, "codepost_manage_assignment_files",
                          {"assignmentId": assignment.id, "op": "add",
                           "name": "hw1.py", "content": "# submit this\n",
                           "required": True})
        warnings = result["structuredContent"].get("warnings") or []
        assert any("required" in w for w in warnings)

    def test_oversized_content_is_refused(self, api_client, key, assignment):
        result = call(api_client, key, "codepost_manage_assignment_files",
                      {"assignmentId": assignment.id, "op": "add",
                       "name": "big.txt", "content": "x" * 1_000_001})
        assert result["isError"] is True
        assert error_of(result)["code"] == "PRECONDITION_NOT_MET"


class TestTestCases:

    def test_preview_parses_without_saving(self, api_client, key, course, assignment):
        from core.models import TestCase, TestCategory
        result = call(api_client, key, "codepost_manage_test_cases",
                      {"assignmentId": assignment.id, "op": "preview",
                       "testScript": SCRIPT})
        assert result["isError"] is False, result["content"][0]["text"]
        data = result["structuredContent"]["data"]
        assert data["totalPoints"] == 8.0
        names = {t["functionName"] for t in data["parsedTests"]}
        assert names == {"test_add", "test_negative"}
        assert TestCategory.objects.filter(assignment=assignment).count() == 0
        assert TestCase.objects.count() == 0

    def test_zero_test_script_preview_warns(self, api_client, key, assignment):
        result = call(api_client, key, "codepost_manage_test_cases",
                      {"assignmentId": assignment.id, "op": "preview",
                       "testScript": "print('no tests here')"})
        warnings = result["structuredContent"].get("warnings") or []
        assert any("ZERO" in w for w in warnings)

    def test_set_script_creates_category_and_cases(self, api_client, key, assignment):
        from core.models import TestCase, TestCategory
        result = call(api_client, key, "codepost_manage_test_cases",
                      {"assignmentId": assignment.id, "op": "setScript",
                       "testScript": SCRIPT, "categoryName": "Unit tests",
                       "targetFileName": "hw1.py"})
        assert result["isError"] is False, result["content"][0]["text"]

        category = TestCategory.objects.get(assignment=assignment,
                                            name="Unit tests")
        cases = {c.functionName: c for c in TestCase.objects.filter(
            testCategory=category)}
        assert set(cases) == {"test_add", "test_negative"}
        assert float(cases["test_add"].pointsPass) == 5.0
        # maxPoints is auto-computed from the script on save
        assert float(TestCategory.objects.get(pk=category.pk).maxPoints) == 8.0

    def test_rewriting_script_names_removed_tests(self, api_client, key, assignment):
        call(api_client, key, "codepost_manage_test_cases",
             {"assignmentId": assignment.id, "op": "setScript",
              "testScript": SCRIPT, "categoryName": "Unit tests"})

        smaller = SCRIPT.replace(
            '@test("Handles negatives", points=3)\ndef test_negative(student):\n    assert student.add(-1, -2) == -3\n', '')
        result = call(api_client, key, "codepost_manage_test_cases",
                      {"assignmentId": assignment.id, "op": "setScript",
                       "testScript": smaller, "categoryName": "Unit tests"})
        warnings = result["structuredContent"].get("warnings") or []
        assert any("test_negative" in w for w in warnings)

        from core.models import TestCase
        assert not TestCase.objects.filter(functionName="test_negative").exists()

    def test_zero_test_set_script_is_refused(self, api_client, key, assignment):
        result = call(api_client, key, "codepost_manage_test_cases",
                      {"assignmentId": assignment.id, "op": "setScript",
                       "testScript": "x = 1"})
        assert result["isError"] is True
        assert error_of(result)["code"] == "PRECONDITION_NOT_MET"


class TestRunAutograder:

    def test_no_environment_is_a_clean_error(self, api_client, key, assignment):
        result = call(api_client, key, "codepost_run_autograder",
                      {"assignmentId": assignment.id, "op": "status"})
        assert result["isError"] is True
        err = error_of(result)
        assert err["code"] == "PRECONDITION_NOT_MET"
        assert "environment" in err["message"].lower()

    def test_run_all_requires_token_and_names_email_risk(
            self, api_client, key, course, assignment):
        from core.models import Environment
        with factory.django.mute_signals(post_save):
            Environment.objects.create(assignment=assignment, language="python-3.12")

        result = call(api_client, key, "codepost_run_autograder",
                      {"assignmentId": assignment.id, "op": "runAll",
                       "sendEmail": True})
        assert result["isError"] is True
        err = error_of(result)
        assert err["code"] == "CONFIRMATION_REQUIRED"
        assert "EMAILS EVERY STUDENT" in err["message"]
        assert "confirmToken" in err["context"]

    def test_status_reports_build_state(self, api_client, key, course, assignment):
        from core.models import Environment
        with factory.django.mute_signals(post_save):
            Environment.objects.create(assignment=assignment,
                                       language="python-3.12", build_status=3,
                                       build_logs="boom")
        result = call(api_client, key, "codepost_run_autograder",
                      {"assignmentId": assignment.id, "op": "status"})
        assert result["isError"] is False, result["content"][0]["text"]
        env = result["structuredContent"]["data"]["environment"]
        assert env["buildStatusLabel"] == "failed"
        assert "boom" in env["buildLogsTail"]
