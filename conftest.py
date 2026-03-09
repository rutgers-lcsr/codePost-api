# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.

"""
Root conftest.py — shared pytest fixtures for the codePost API test suite.

Provides reusable fixtures for authenticated API clients, courses with full
rosters, assignments, submissions, and other common test objects. These replace
the manual setUp() boilerplate that was duplicated across test files.

Usage:
    def test_example(api_client, course_with_roster):
        api_client.force_authenticate(user=course_with_roster.courseAdmins.first())
        response = api_client.get(f'/courses/{course_with_roster.id}/')
        assert response.status_code == 200
"""

import pytest
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from rest_framework.test import APIClient

import factory


@pytest.fixture
def api_client():
    """An unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def superuser(db):
    """A superuser with admin profile permissions."""
    user = User.objects.create_superuser(
        username='superuser@test.edu',
        email='superuser@test.edu',
        password='testpassword',
    )
    user.profile.canCreateCourses = True
    user.profile.canModifyRosters = True
    user.save()
    return user


@pytest.fixture
def authenticated_client(api_client, superuser):
    """An APIClient authenticated as a superuser."""
    api_client.force_authenticate(user=superuser)
    return api_client


@pytest.fixture
def course_with_roster(db):
    """
    A fully populated course with:
    - Organization ('Princeton')
    - 2 active + 2 inactive admins, graders, students, supergraders
    - 1 section
    - 1 assignment with submission, files, rubric, and comment

    Access members via:
        course.courseAdmins.first(), course.graders.first(),
        course.students.first(), course.assignments.first(), etc.
    """
    from core.tests.factories import CourseFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(
            name="cos126",
            period="s2020",
            organization__name="Princeton",
        )
    return course


@pytest.fixture
def second_course(db):
    """A second course in the same org, useful for cross-course permission tests."""
    from core.tests.factories import CourseFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(
            name="cos226",
            period="s2020",
            organization__name="Princeton",
        )
    return course


@pytest.fixture
def other_org_course(db):
    """A course in a different organization, for cross-org permission tests."""
    from core.tests.factories import CourseFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(
            name="cs101",
            period="s2020",
            organization__name="Harvard",
        )
    return course
