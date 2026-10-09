# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import factory
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import RubricCategory
from core.tests.factories import CourseFactory


class DeleteRubricCategoryScopeTests(APITestCase):
    """PATCH /courses/{id}/deleteRubricCategory/ must only reach categories of that course."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course_a = CourseFactory(name="cs100", period="s2026", organization__name="ScopeOrg")
            self.course_b = CourseFactory(name="cs200", period="s2026", organization__name="ScopeOrg")
        self.admin_a = self.course_a.courseAdmins.first()
        self.category_a = self.course_a.assignments.first().rubricCategories.first()
        self.category_b = self.course_b.assignments.first().rubricCategories.first()

    def test_admin_of_another_course_cannot_delete_its_category(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.patch(f'/courses/{self.course_a.id}/deleteRubricCategory/',
                                 {'id': self.category_b.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(RubricCategory.objects.filter(pk=self.category_b.pk).exists())

    def test_own_course_category_is_deleted(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.patch(f'/courses/{self.course_a.id}/deleteRubricCategory/',
                                 {'id': self.category_a.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RubricCategory.objects.filter(pk=self.category_a.pk).exists())

    def test_unknown_course_is_404(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.patch('/courses/999999/deleteRubricCategory/',
                                 {'id': self.category_a.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(RubricCategory.objects.filter(pk=self.category_a.pk).exists())
