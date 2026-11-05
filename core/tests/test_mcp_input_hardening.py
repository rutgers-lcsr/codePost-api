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



