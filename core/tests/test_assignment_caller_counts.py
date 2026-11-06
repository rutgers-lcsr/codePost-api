# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""The caller's queue counts (queueLength / myFinalizedCount / myUnfinalizedCount) on the
staff assignment serializers: the grader console's summary tables used to read the
admin-only summary fields and print zeros for every grader."""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Submission
from core.tests.factories import AssignmentFactory, CourseFactory, StudentFactory, SubmissionFactory

CALLER_FIELDS = ('queueLength', 'myFinalizedCount', 'myUnfinalizedCount')


class CallerQueueCountsTests(APITestCase):

    def setUp(self):
        self.course = CourseFactory(name="queuecounts")
        self.admin = self.course.courseAdmins.first()
        graders = list(self.course.graders.filter(username__startswith='grader_'))
        self.grader, self.other_grader = graders[0], graders[1]
        self.student = self.course.students.first()
        self.inactive = self.course.inactive_students.first()
        for i in range(10, 17):
            self.course.students.add(StudentFactory(course=self.course.name, organization=self.course.organization, count=i))
        self.actives = list(self.course.students.exclude(id=self.student.id))

        self.assignment = AssignmentFactory(course=self.course, name="Q1", points=20)
        # AssignmentFactory adds one submission with no students: unclaimed, but not queued.
        self._sub(self.actives[0])                                            # queued
        self._sub(self.actives[1])                                            # queued
        self._sub(self.actives[2], self.actives[3])                           # queued once (group)
        self._sub(self.inactive)                                              # unclaimed, not queued
        self._sub(self.actives[4], grader=self.grader, finalized=True, grade=10)
        self._sub(self.actives[5], self.actives[6], grader=self.other_grader, finalized=True, grade=20)  # group
        self._sub(self.student, grader=self.grader, finalized=False)
        self._sub(self.actives[2], grader=self.other_grader, finalized=True, grade=20, assignment=self._second())

    def _second(self):
        if not hasattr(self, 'second'):
            self.second = AssignmentFactory(course=self.course, name="Q2", points=20)
        return self.second

    def _sub(self, *students, grader=None, finalized=False, grade=None, assignment=None):
        sub = SubmissionFactory(assignment=assignment or self.assignment, grader=grader, isFinalized=finalized)
        sub.students.add(*students)
        if grade is not None:
            # save() derives the grade from the (empty) rubric; set the fixture grade underneath it.
            Submission.objects.filter(pk=sub.pk).update(grade=grade)
        return sub

    def _bulk_row(self, user, assignment):
        self.client.force_authenticate(user=user)
        resp = self.client.get(f'/courses/{self.course.id}/assignments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return next(r for r in resp.data if r['id'] == assignment.id)

    def test_grader_bulk_payload_carries_the_callers_counts(self):
        row = self._bulk_row(self.grader, self.assignment)
        self.assertEqual(
            {k: row[k] for k in CALLER_FIELDS},
            {'queueLength': 3, 'myFinalizedCount': 1, 'myUnfinalizedCount': 1})
        # No course-wide statistics for a plain grader.
        self.assertNotIn('submissions_count', row)
        self.assertNotIn('stats_mean', row)

    def test_counts_are_per_caller(self):
        row = self._bulk_row(self.other_grader, self.assignment)
        self.assertEqual(
            {k: row[k] for k in CALLER_FIELDS},
            {'queueLength': 3, 'myFinalizedCount': 1, 'myUnfinalizedCount': 0})

    def test_bulk_matches_queue_length_endpoint_and_retrieve(self):
        row = self._bulk_row(self.grader, self.assignment)
        resp = self.client.get(f'/assignments/{self.assignment.id}/queueLength/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(
            (resp.data['unclaimed'], resp.data['finalized'], resp.data['unfinalized']),
            (row['queueLength'], row['myFinalizedCount'], row['myUnfinalizedCount']))
        resp = self.client.get(f'/assignments/{self.assignment.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual({k: resp.data[k] for k in CALLER_FIELDS}, {k: row[k] for k in CALLER_FIELDS})

    def test_admin_gets_both_summaries_and_an_unweighted_mean(self):
        row = self._bulk_row(self.admin, self.assignment)
        self.assertEqual(
            {k: row[k] for k in CALLER_FIELDS},
            {'queueLength': 3, 'myFinalizedCount': 0, 'myUnfinalizedCount': 0})
        # The course-wide unclaimed count also counts the inactive-only and student-less
        # submissions the queue never serves.
        self.assertEqual(row['submissions_unclaimed_count'], 5)
        # Finalized grades 10 and 20 (the 20 is a two-student group submission). The mean
        # must stay unweighted: the queue length is a subquery, not a students join that
        # would hand the aggregates one row per student.
        self.assertEqual(row['submissions_finalized_count'], 2)
        self.assertEqual(Decimal(str(row['stats_mean'])), Decimal('15'))
        resp = self.client.get(f'/assignments/{self.assignment.id}/')
        self.assertEqual({k: resp.data[k] for k in CALLER_FIELDS}, {k: row[k] for k in CALLER_FIELDS})

    def test_students_never_see_the_counts(self):
        self.assignment.state = 'published'
        self.assignment.save()
        row = self._bulk_row(self.student, self.assignment)
        for k in CALLER_FIELDS:
            self.assertNotIn(k, row)

    def test_counts_add_no_per_assignment_queries(self):
        """The base serializer already reads environment, files, sections and datasets per
        assignment (4 queries); the counts must ride the one annotated query."""
        def count_queries():
            self.client.get(f'/courses/{self.course.id}/assignments/')  # warm caches
            with CaptureQueriesContext(connection) as ctx:
                resp = self.client.get(f'/courses/{self.course.id}/assignments/')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            return len(ctx)

        self.client.force_authenticate(user=self.grader)
        few = count_queries()
        for i in range(3):
            AssignmentFactory(course=self.course, name=f"Extra {i}", points=20)
        many = count_queries()
        self.assertLessEqual((many - few) / 3, 4, (few, many))
