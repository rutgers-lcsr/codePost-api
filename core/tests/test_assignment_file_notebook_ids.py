# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Notebook cell ids are injected on every AssignmentFile write that carries notebook data."""
import json

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.factories import OrganizationFactory, UserFactory

NB = json.dumps({
    "nbformat": 4, "nbformat_minor": 5, "metadata": {},
    "cells": [{"cell_type": "code", "source": ["x=1"], "metadata": {}, "outputs": [], "execution_count": None}],
})


class TestNotebookCellIds(APITestCase):
    def setUp(self):
        org = OrganizationFactory(name="NbOrg", shortname="NO")
        self.admin = UserFactory(username="admin@no.edu", email="admin@no.edu")
        self.admin.profile.organization = org
        self.admin.profile.canCreateCourses = True
        self.admin.save()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post('/courses/', {"name": "CS Nb", "period": "F2026"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        resp = self.client.post('/assignments/', {"name": "HW", "points": 10, "course": resp.data['id']})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assignment_id = resp.data['id']

    def _ids(self, data):
        return [c.get('metadata', {}).get('id') for c in json.loads(data)['cells']]

    def _create(self, extension):
        body = {"name": "nb.ipynb", "path": "", "assignment": self.assignment_id, "data": NB}
        if extension is not None:
            body["extension"] = extension
        resp = self.client.post('/assignmentFiles/', body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return resp

    def test_create_with_dotted_extension(self):
        resp = self._create(".ipynb")
        self.assertTrue(all(self._ids(resp.data['data'])))

    def test_create_with_undotted_extension(self):
        resp = self._create("ipynb")
        self.assertTrue(all(self._ids(resp.data['data'])))

    def test_patch_data_only_injects_ids(self):
        created = self._create(".ipynb")
        resp = self.client.patch(f"/assignmentFiles/{created.data['id']}/", {"data": NB}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(all(self._ids(resp.data['data'])))

    def test_non_notebook_data_untouched(self):
        resp = self.client.post('/assignmentFiles/', {
            "name": "a.json", "extension": ".json", "path": "", "assignment": self.assignment_id, "data": NB,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['data'], NB)

    def test_patch_submitted_extension_overrides_stored_one(self):
        created = self._create(".ipynb")
        resp = self.client.patch(f"/assignmentFiles/{created.data['id']}/", {"extension": ".json", "data": NB}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['data'], NB)
