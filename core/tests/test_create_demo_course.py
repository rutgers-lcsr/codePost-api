# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""create_demo_course seeds point values with the platform's sign convention:
a positive pointDelta (or late deduction) takes points off, a negative one adds them."""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Comment, Course, Organization, RubricComment, calculate_grade


@override_settings(DEBUG=True)
class TestDemoCoursePointSigns(TestCase):

    @classmethod
    def setUpTestData(cls):
        org = Organization.objects.create(name="Demo Org", shortname="demo")
        su = User.objects.create_superuser("demo-su@dev.edu", "demo-su@dev.edu", "pw")
        su.profile.organization = org
        su.profile.save()
        # AssignmentFile saves queue environment auto-detection; no broker in tests.
        with override_settings(DEBUG=True), patch("autograder.run.AutoDetectEnvironment.apply_async"):
            call_command("create_demo_course", stdout=StringIO())
        cls.course = Course.objects.get(name="Demo Course")

    def _comments(self, additive):
        return RubricComment.objects.filter(category__assignment__course=self.course,
                                            category__assignment__additiveGrading=additive)

    def test_deductive_rubric_comments_take_points_off(self):
        bonuses = self._comments(additive=False).filter(pointDelta__lt=0)
        self.assertEqual(list(bonuses.values_list("category__assignment__name", "text")), [])

    def test_additive_rubric_awards_points_and_still_penalises_incomplete_work(self):
        comments = self._comments(additive=True)
        self.assertTrue(comments.exists())
        for rc in comments:
            if rc.text == "Incomplete submission":
                self.assertGreater(rc.pointDelta, 0, rc.text)
            else:
                self.assertLess(rc.pointDelta, 0, rc.text)

    def test_additive_category_caps_bound_the_points_earned(self):
        capped = RubricComment.objects.filter(
            category__assignment__course=self.course, category__assignment__additiveGrading=True,
            category__pointLimit__isnull=False).values_list("category__pointLimit", flat=True)
        self.assertTrue(capped)
        for limit in capped:
            self.assertLess(limit, 0)

    def test_late_deductions_take_points_off(self):
        for assignment in self.course.assignments.exclude(lateDeductions=[]):
            self.assertTrue(all(d >= 0 for d in assignment.lateDeductions), assignment.name)

    def test_free_text_comments_take_points_off(self):
        loose = Comment.objects.filter(file__submission__assignment__course=self.course,
                                       rubricComment__isnull=True, pointDelta__lt=0)
        self.assertEqual(loose.count(), 0)

    def test_no_graded_submission_scores_above_its_assignment(self):
        for assignment in self.course.assignments.all():
            for sub in assignment.submissions.filter(isFinalized=True):
                grade = calculate_grade(sub)
                self.assertLessEqual(grade, assignment.points, assignment.name)
                self.assertGreaterEqual(grade, 0, assignment.name)
