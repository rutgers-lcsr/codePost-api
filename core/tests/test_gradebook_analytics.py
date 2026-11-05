# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Regressions for the assignment analytics / late-day export / class statistics bugs.

Worked examples use exact numbers. The single late-day rule is the one
LateSubmissionHandler charges students with: days late = floor(delta / 24h) + 1,
and a first-day submission less than GRACE_PERIOD_HOURS (2h) late is on time.
"""
import csv
import datetime
import io
import tempfile
from decimal import Decimal

import factory
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth.models import User

from core.models import Submission
from core.tests.factories import AssignmentFactory, CourseFactory

DUE = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=datetime.timezone.utc)
H = datetime.timedelta(hours=1)


@pytest.fixture
def course(db):
    with factory.django.mute_signals(post_save):
        return CourseFactory(name="cs801", period="f2026", organization__name="GbOrg")


@pytest.fixture
def admin(course):
    return course.courseAdmins.first()


@pytest.fixture
def api_client(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def make_assignment(course, name="HW", points=20, **kwargs):
    with factory.django.mute_signals(post_save):
        return AssignmentFactory(course=course, name=name, points=points,
                                 submissions=None, **kwargs)


def make_sub(assignment, student, grade=None, finalized=False, uploaded=None):
    """A submission for `student`; grade/isFinalized pinned with update() so
    Submission.save() does not recompute the grade."""
    with factory.django.mute_signals(post_save):
        sub = Submission.objects.create(assignment=assignment, dateUploaded=uploaded)
    sub.students.set([student])
    Submission.objects.filter(pk=sub.pk).update(
        grade=grade, isFinalized=finalized,
        grader=assignment.course.graders.first() if finalized else None)
    return sub


def students_of(course, n):
    """The first n students by email, enrolling extra ones if the fixture has fewer."""
    for i in range(course.students.count(), n):
        with factory.django.mute_signals(post_save):
            course.students.add(User.objects.create_user(f"extra{i}@gborg.edu", f"extra{i}@gborg.edu", "pw"))
    return list(course.students.all().order_by('email'))[:n]


class TestAttempts:

    def test_mixed_null_upload_date_does_not_500(self, api_client, course):
        a = make_assignment(course)
        s = students_of(course, 1)[0]
        make_sub(a, s, uploaded=DUE)
        make_sub(a, s, uploaded=None)
        resp = api_client.get(f"/assignments/{a.id}/analytics/")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["submissionAttempts"]["totalStudents"] == 1
        assert resp.data["submissionAttempts"]["studentsWithMultipleAttempts"] == 1

    def test_students_with_multiple_attempts_counts_students(self, api_client, course):
        a = make_assignment(course)
        s1, s2 = students_of(course, 2)
        for s in (s1, s2):
            make_sub(a, s, uploaded=DUE)
            make_sub(a, s, uploaded=DUE + H)
        resp = api_client.get(f"/assignments/{a.id}/analytics/")
        attempts = resp.data["submissionAttempts"]
        assert attempts["attemptDistribution"] == [{"attempts": 2, "studentCount": 2}]
        assert attempts["studentsWithMultipleAttempts"] == 2

    def test_students_with_multiple_attempts_across_attempt_counts(self, api_client, course):
        a = make_assignment(course)
        s1, s2 = students_of(course, 2)
        make_sub(a, s1, uploaded=DUE)
        make_sub(a, s1, uploaded=DUE)
        for _ in range(3):
            make_sub(a, s2, uploaded=DUE)
        resp = api_client.get(f"/assignments/{a.id}/analytics/")
        assert resp.data["submissionAttempts"]["studentsWithMultipleAttempts"] == 2

    def test_single_attempt_student_is_not_a_multiple_attempt_student(self, api_client, course):
        a = make_assignment(course)
        s1, s2, s3 = students_of(course, 3)
        make_sub(a, s1, uploaded=DUE)
        make_sub(a, s2, uploaded=DUE)
        make_sub(a, s2, uploaded=DUE + H)
        make_sub(a, s3, uploaded=DUE)
        resp = api_client.get(f"/assignments/{a.id}/analytics/")
        attempts = resp.data["submissionAttempts"]
        assert attempts["attemptDistribution"] == [
            {"attempts": 1, "studentCount": 2}, {"attempts": 2, "studentCount": 1}]
        assert attempts["studentsWithMultipleAttempts"] == 1
        assert attempts["totalStudents"] == 3


class TestGradeDistribution:

    def test_negative_grade_lands_in_lowest_bucket(self, api_client, course):
        a = make_assignment(course, points=20)
        s1, s2 = students_of(course, 2)
        make_sub(a, s1, grade=Decimal('-5'), finalized=True)
        make_sub(a, s2, grade=Decimal('10'), finalized=True)
        make_sub(a, s2, grade=Decimal('20'), finalized=True)
        resp = api_client.get(f"/assignments/{a.id}/analytics/?buckets=2")
        dist = resp.data["gradeDistribution"]
        assert [d["count"] for d in dist] == [1, 2]
        assert sum(d["count"] for d in dist) == 3


class TestClassStatistics:

    def _grades(self, course, a, grades):
        studs = list(course.students.all())
        for i, g in enumerate(grades):
            make_sub(a, studs[i % len(studs)], grade=Decimal(g), finalized=True)

    def test_odd_median_and_mean_served_live(self, api_client, course):
        a = make_assignment(course, points=100)
        self._grades(course, a, [2, 4, 6])
        resp = api_client.get(f"/assignments/{a.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert Decimal(str(resp.data["median"])) == Decimal('4')
        assert Decimal(str(resp.data["mean"])) == Decimal('4')

    def test_even_median_averages_middle_pair(self, api_client, course):
        a = make_assignment(course, points=100)
        self._grades(course, a, [1, 2, 3, 4])
        resp = api_client.get(f"/assignments/{a.id}/")
        assert Decimal(str(resp.data["median"])) == Decimal('2.5')
        assert Decimal(str(resp.data["mean"])) == Decimal('2.5')

    def test_stats_follow_later_grade_changes(self, api_client, course):
        a = make_assignment(course, points=100)
        self._grades(course, a, [2])
        assert Decimal(str(api_client.get(f"/assignments/{a.id}/").data["mean"])) == Decimal('2')
        self._grades(course, a, [6])
        resp = api_client.get(f"/assignments/{a.id}/")
        assert Decimal(str(resp.data["mean"])) == Decimal('4')
        assert Decimal(str(resp.data["median"])) == Decimal('4')

    def test_no_finalized_submissions_reads_null(self, api_client, course):
        a = make_assignment(course, points=100)
        resp = api_client.get(f"/assignments/{a.id}/")
        assert resp.data["mean"] is None and resp.data["median"] is None

    def test_null_grade_finalized_submission_is_ungraded_not_a_500(self, api_client, course):
        a = make_assignment(course, points=100)
        s1, s2, s3 = students_of(course, 3)
        make_sub(a, s1, grade=Decimal('2'), finalized=True)
        make_sub(a, s2, grade=Decimal('4'), finalized=True)
        make_sub(a, s3, grade=None, finalized=True)
        resp = api_client.get(f"/assignments/{a.id}/")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert Decimal(str(resp.data["mean"])) == Decimal('3')
        assert Decimal(str(resp.data["median"])) == Decimal('3')

    def test_only_null_grades_reads_null(self, api_client, course):
        a = make_assignment(course, points=100)
        make_sub(a, students_of(course, 1)[0], grade=None, finalized=True)
        resp = api_client.get(f"/assignments/{a.id}/")
        assert resp.status_code == status.HTTP_200_OK, resp.data
        assert resp.data["mean"] is None and resp.data["median"] is None

    def test_course_assignments_query_count_does_not_grow_with_stats(self, api_client, course):
        """Serving mean/median for every assignment in the listing must not add queries
        per assignment: the pre-fix base cost 6 queries per assignment without stats."""
        studs = students_of(course, 2)

        def count_queries():
            api_client.get(f"/courses/{course.id}/assignments/")  # warm caches
            with CaptureQueriesContext(connection) as ctx:
                resp = api_client.get(f"/courses/{course.id}/assignments/")
            assert resp.status_code == status.HTTP_200_OK
            return len(ctx)

        def add(n, start):
            for i in range(start, start + n):
                a = make_assignment(course, name=f"Q{i}", points=100)
                make_sub(a, studs[0], grade=Decimal('3'), finalized=True)
                make_sub(a, studs[1], grade=Decimal('4'), finalized=True)

        add(2, 0)
        few = count_queries()
        add(3, 2)
        many = count_queries()
        assert (many - few) / 3 <= 6, (few, many)

    def test_course_assignments_endpoint_also_live(self, api_client, course):
        a = make_assignment(course, points=100)
        self._grades(course, a, [1, 2, 3])
        resp = api_client.get(f"/courses/{course.id}/assignments/")
        row = next(r for r in resp.data if r["id"] == a.id)
        assert Decimal(str(row["median"])) == Decimal('2')


class TestLateDays:

    def _late_stats(self, api_client, course, offset):
        a = make_assignment(course, uploadDueDate=DUE)
        make_sub(a, students_of(course, 1)[0], uploaded=DUE + offset)
        resp = api_client.get(f"/assignments/{a.id}/analytics/")
        return resp.data["lateSubmissions"]

    def test_exactly_24h_late_is_day_two(self, api_client, course):
        late = self._late_stats(api_client, course, 24 * H)
        assert late["lateByDay"] == [{"day": 2, "count": 1}]

    def test_within_grace_is_on_time(self, api_client, course):
        late = self._late_stats(api_client, course, H)
        assert late["onTime"] == 1 and late["late"] == 0

    def test_two_hours_late_is_day_one(self, api_client, course):
        late = self._late_stats(api_client, course, 2 * H)
        assert late["lateByDay"] == [{"day": 1, "count": 1}]

    def test_early_upload_is_on_time(self, api_client, course):
        late = self._late_stats(api_client, course, -5 * H)
        assert late["onTime"] == 1 and late["late"] == 0 and late["lateByDay"] == []

    def _export(self, course):
        with tempfile.NamedTemporaryFile("r+", suffix=".csv") as f:
            call_command("export_late_days", course_id=course.id, output=f.name)
            f.seek(0)
            rows = list(csv.reader(io.StringIO(f.read())))
        assert rows[0] == ["user_email", "days_late"]
        return {email: int(days) for email, days in rows[1:]}

    def test_export_agrees_with_analytics_on_24h_boundary(self, course):
        a = make_assignment(course, uploadDueDate=DUE)
        s = students_of(course, 1)[0]
        make_sub(a, s, uploaded=DUE + 24 * H)
        assert self._export(course)[s.email] == 2

    def test_export_grace_period_not_charged(self, course):
        a = make_assignment(course, uploadDueDate=DUE)
        s = students_of(course, 1)[0]
        make_sub(a, s, uploaded=DUE + H)
        assert self._export(course)[s.email] == 0

    def test_export_early_upload_not_charged(self, course):
        a = make_assignment(course, uploadDueDate=DUE)
        s = students_of(course, 1)[0]
        make_sub(a, s, uploaded=DUE - 5 * H)
        assert self._export(course)[s.email] == 0

    def test_export_charges_best_submission_once_per_assignment(self, course):
        a = make_assignment(course, uploadDueDate=DUE)
        s1, s2 = students_of(course, 2)
        # s1: finalized older (1 day late) beats the unfinalized newer (3 days late).
        make_sub(a, s1, grade=Decimal('5'), finalized=True, uploaded=DUE + 12 * H)
        make_sub(a, s1, uploaded=DUE + 50 * H)
        # s2: nothing finalized -> the newest upload (3 days late) counts, once.
        make_sub(a, s2, uploaded=DUE + 12 * H)
        make_sub(a, s2, uploaded=DUE + 30 * H)
        make_sub(a, s2, uploaded=DUE + 50 * H)
        totals = self._export(course)
        assert totals[s1.email] == 1
        assert totals[s2.email] == 3

    def test_export_sums_across_assignments(self, course):
        s = students_of(course, 1)[0]
        a1 = make_assignment(course, name="A1", uploadDueDate=DUE)
        a2 = make_assignment(course, name="A2", uploadDueDate=DUE)
        make_sub(a1, s, uploaded=DUE + 12 * H)
        make_sub(a2, s, uploaded=DUE + 30 * H)
        assert self._export(course)[s.email] == 3

    def test_export_partner_submission_charges_both(self, course):
        a = make_assignment(course, uploadDueDate=DUE)
        s1, s2 = students_of(course, 2)
        sub = make_sub(a, s1, uploaded=DUE + 12 * H)
        sub.students.add(s2)
        totals = self._export(course)
        assert totals[s1.email] == 1 and totals[s2.email] == 1
