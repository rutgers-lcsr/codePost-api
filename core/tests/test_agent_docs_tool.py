# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""codepost_search_docs — markdown docs search through /mcp."""
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
        return CourseFactory(name="cs950", period="f2026", organization__name="TestOrg")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def read_key(api_client, course):
    admin = course.courseAdmins.first()
    api_client.force_authenticate(user=admin)
    resp = api_client.post(f"/courses/{course.id}/apiKeys/",
                           {"name": "docs-key", "scope": "read"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data
    api_client.force_authenticate(user=None)
    return resp.data["key"]


def call(api_client, key, arguments=None):
    api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {key}",
                           HTTP_MCP_PROTOCOL_VERSION=V)
    resp = api_client.post(MCP_URL, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "codepost_search_docs", "arguments": arguments or {}},
    }, format="json")
    assert resp.status_code == status.HTTP_200_OK, resp.data
    return resp.data["result"]


class TestSearchDocs:

    def test_read_key_sees_the_tool(self, api_client, read_key):
        api_client.credentials(HTTP_AUTHORIZATION=f"CourseKey {read_key}",
                               HTTP_MCP_PROTOCOL_VERSION=V)
        resp = api_client.post(MCP_URL, {"jsonrpc": "2.0", "id": 1,
                                         "method": "tools/list"}, format="json")
        names = {t["name"] for t in resp.data["result"]["tools"]}
        assert "codepost_search_docs" in names

    def test_no_arguments_lists_pages(self, api_client, read_key):
        result = call(api_client, read_key)
        assert result["isError"] is False
        pages = result["structuredContent"]["data"]["pages"]
        assert len(pages) > 20
        assert all({"key", "title", "category"} <= set(p) for p in pages)

    def test_search_returns_markdown_sections(self, api_client, read_key):
        result = call(api_client, read_key, {"query": "release feedback"})
        assert result["isError"] is False
        data = result["structuredContent"]["data"]
        assert data["results"], "expected hits for a core workflow query"
        top = data["results"][0]
        # Raw markdown, not HTML
        assert "<" not in top["markdown"][:200] or "<Text" not in top["markdown"]
        assert top["markdown"].startswith("#") or top["markdown"][0].isalpha()
        assert result["structuredContent"]["meta"]["format"] == "markdown"

    def test_fetch_whole_page(self, api_client, read_key):
        listing = call(api_client, read_key)
        key = listing["structuredContent"]["data"]["pages"][0]["key"]
        result = call(api_client, read_key, {"page": key})
        assert result["isError"] is False
        assert len(result["structuredContent"]["data"]["markdown"]) > 100

    def test_unknown_page_names_available_keys(self, api_client, read_key):
        result = call(api_client, read_key, {"page": "not-a-page"})
        assert result["isError"] is True
        err = json.loads(result["content"][0]["text"])["error"]
        assert err["code"] == "NOT_FOUND"
        assert len(err["context"]["availableKeys"]) > 20

    def test_mcp_docs_page_is_searchable(self, api_client, read_key):
        """The instructor MCP guide itself should be findable — dogfood."""
        result = call(api_client, read_key, {"query": "confirmation code agent"})
        pages = {r["page"] for r in result["structuredContent"]["data"]["results"]}
        assert "instructor-mcp-agent" in pages
