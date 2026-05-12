# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Robust tests for calculate_grade function.

Covers:
- Deductive grading (default): starts at assignment.points, subtracts
- Additive grading: starts at 0, adds bonuses
- Category point limits (caps)
- Comments with and without rubric links
- Test results affecting grade
- Frozen grade prevents recalculation
- Multiple files, multiple versions
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User

from core.models import (
    calculate_grade, getCurrentFiles,
    Assignment, Course, Submission, SubmissionFile,
    RubricCategory, RubricComment, Comment,
    TestCategory, TestCase as TestCaseModel, SubmissionTest,
)
from core.tests.factories import OrganizationFactory


class TestCalculateGradeDeductive(TestCase):
    """Deductive grading: grade = points - deductions."""

    def setUp(self):
        self.org = OrganizationFactory(name="GradeOrg1", shortname="go1")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(
            course=self.course, name="HW1", points=20, additiveGrading=False
        )
        self.submission = Submission.objects.create(assignment=self.assignment, gradeFrozen=True)
        self.file = SubmissionFile.objects.create(
            submission=self.submission, name="hello.py", extension=".py", data="print('hi')"
        )
        self.grader = User.objects.create_user("grader-gc@test.edu", password="pass")

    def test_no_comments_full_grade(self):
        """No comments = full points."""
        grade = calculate_grade(self.submission)
        self.assertEqual(grade, Decimal("20"))

    def test_plain_comment_deduction(self):
        """Comment with pointDelta deducts from total."""
        Comment.objects.create(
            file=self.file, author=self.grader, text="Bug",
            pointDelta=5, startLine=0, endLine=0, startChar=0, endChar=1,
        )
        grade = calculate_grade(self.submission)
        self.assertEqual(grade, Decimal("15"))

    def test_rubric_comment_deduction(self):
        """Rubric comment's pointDelta used for deduction."""
        cat = RubricCategory.objects.create(assignment=self.assignment, name="General")
        rc = RubricComment.objects.create(category=cat, text="Missing semicolon", pointDelta=3)
        Comment.objects.create(
            file=self.file, author=self.grader, text="",
            rubricComment=rc, startLine=0, endLine=0, startChar=0, endChar=1,
        )
        grade = calculate_grade(self.submission)
        self.assertEqual(grade, Decimal("17"))

    def test_category_point_limit_caps_deduction(self):
        """pointLimit caps the total deduction for a category."""
        cat = RubricCategory.objects.create(
            assignment=self.assignment, name="Style", pointLimit=-5
        )
        rc1 = RubricComment.objects.create(category=cat, text="Bad naming", pointDelta=-3)
        rc2 = RubricComment.objects.create(category=cat, text="No docs", pointDelta=-4)
        Comment.objects.create(
            file=self.file, author=self.grader, text="",
            rubricComment=rc1, startLine=0, endLine=0, startChar=0, endChar=1,
        )
        Comment.objects.create(
            file=self.file, author=self.grader, text="",
            rubricComment=rc2, startLine=1, endLine=1, startChar=0, endChar=1,
        )
        grade = calculate_grade(self.submission)
        # Without cap: -3 + -4 = -7 deduction -> 20 - (-7) = 27
        # With cap: max(-7, -5) = -5 -> 20 - (-5) = 25
        self.assertEqual(grade, Decimal("25"))

    def test_mixed_rubric_and_plain_comments(self):
        """Both rubric-linked and plain comments apply correctly."""
        cat = RubricCategory.objects.create(assignment=self.assignment, name="General")
        rc = RubricComment.objects.create(category=cat, text="Error", pointDelta=2)
        # Rubric comment
        Comment.objects.create(
            file=self.file, author=self.grader, text="",
            rubricComment=rc, startLine=0, endLine=0, startChar=0, endChar=1,
        )
        # Plain comment
        Comment.objects.create(
            file=self.file, author=self.grader, text="Also bad",
            pointDelta=3, startLine=1, endLine=1, startChar=0, endChar=1,
        )
        grade = calculate_grade(self.submission)
        # 20 - 2 (rubric) - 3 (plain) = 15
        self.assertEqual(grade, Decimal("15"))


class TestCalculateGradeAdditive(TestCase):
    """Additive grading: grade = sum of (negative) deductions inverted + test points."""

    def setUp(self):
        self.org = OrganizationFactory(name="GradeOrg2", shortname="go2")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(
            course=self.course, name="HW1", points=20, additiveGrading=True
        )
        self.submission = Submission.objects.create(assignment=self.assignment, gradeFrozen=True)
        self.file = SubmissionFile.objects.create(
            submission=self.submission, name="hello.py", extension=".py", data="print('hi')"
        )
        self.grader = User.objects.create_user("grader-gc2@test.edu", password="pass")

    def test_no_comments_zero_grade(self):
        """Additive: no comments = 0 points."""
        grade = calculate_grade(self.submission)
        self.assertEqual(grade, Decimal("0"))

    def test_negative_point_delta_adds_points(self):
        """In additive mode, negative deductions become points added."""
        Comment.objects.create(
            file=self.file, author=self.grader, text="bonus",
            pointDelta=-5, startLine=0, endLine=0, startChar=0, endChar=1,
        )
        grade = calculate_grade(self.submission)
        # additive: -1 * (-5) = 5
        self.assertEqual(grade, Decimal("5"))


class TestCalculateGradeWithTests(TestCase):
    """Test results affecting grade."""

    def setUp(self):
        self.org = OrganizationFactory(name="GradeOrg3", shortname="go3")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(
            course=self.course, name="HW1", points=20, testsAffectGrade=True
        )
        self.submission = Submission.objects.create(assignment=self.assignment, gradeFrozen=True)
        self.file = SubmissionFile.objects.create(
            submission=self.submission, name="hello.py", extension=".py", data="print('hi')"
        )
        self.category = TestCategory.objects.create(assignment=self.assignment, name="Tests")

    def test_passed_test_adds_points(self):
        tc = TestCaseModel.objects.create(
            testCategory=self.category, description="Test1",
            type="io", pointsFail=0, pointsPass=5,
        )
        SubmissionTest.objects.create(
            submission=self.submission, testCase=tc,
            logs="ok", passed=True,
        )
        grade = calculate_grade(self.submission)
        # 20 (base) + 5 (test pass) = 25
        self.assertEqual(grade, Decimal("25"))

    def test_failed_test_adds_fail_points(self):
        tc = TestCaseModel.objects.create(
            testCategory=self.category, description="Test1",
            type="io", pointsFail=-2, pointsPass=5,
        )
        SubmissionTest.objects.create(
            submission=self.submission, testCase=tc,
            logs="fail", passed=False,
        )
        grade = calculate_grade(self.submission)
        # 20 (base) + (-2) (test fail) = 18
        self.assertEqual(grade, Decimal("18"))

    def test_tests_disabled_for_assignment(self):
        """testsAffectGrade=False means tests don't change grade."""
        self.assignment.testsAffectGrade = False
        self.assignment.save()
        tc = TestCaseModel.objects.create(
            testCategory=self.category, description="Test1",
            type="io", pointsFail=0, pointsPass=10,
        )
        SubmissionTest.objects.create(
            submission=self.submission, testCase=tc,
            logs="ok", passed=True,
        )
        grade = calculate_grade(self.submission)
        self.assertEqual(grade, Decimal("20"))

    def test_score_based_test(self):
        """Tests with score/maxScore use those instead of pointsPass/pointsFail."""
        tc = TestCaseModel.objects.create(
            testCategory=self.category, description="Scored Test",
            type="script", pointsFail=0, pointsPass=0,
        )
        SubmissionTest.objects.create(
            submission=self.submission, testCase=tc,
            logs="partial", passed=True,
            score=Decimal("3.50"), maxScore=Decimal("5.00"),
        )
        grade = calculate_grade(self.submission)
        # 20 + 3.50 = 23.50
        self.assertEqual(grade, Decimal("23.50"))


class TestGetCurrentFiles(TestCase):
    """getCurrentFiles returns latest version per path."""

    def setUp(self):
        self.org = OrganizationFactory(name="GradeOrg4", shortname="go4")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)
        self.submission = Submission.objects.create(assignment=self.assignment, gradeFrozen=True)

    def test_single_file(self):
        SubmissionFile.objects.create(
            submission=self.submission, name="main.py", extension=".py", data="x=1"
        )
        files = getCurrentFiles(self.submission)
        self.assertEqual(len(files), 1)

    def test_multiple_versions_returns_latest(self):
        """Two files with same name - latest created wins."""
        _f1 = SubmissionFile.objects.create(
            submission=self.submission, name="main.py", extension=".py", data="v1"
        )
        _f2 = SubmissionFile.objects.create(
            submission=self.submission, name="main.py", extension=".py", data="v2"
        )
        files = getCurrentFiles(self.submission)
        self.assertEqual(len(files), 1)
        # The latest should be f2
        self.assertEqual(files[0].data, "v2")

    def test_different_names_returns_both(self):
        SubmissionFile.objects.create(
            submission=self.submission, name="main.py", extension=".py", data="x=1"
        )
        SubmissionFile.objects.create(
            submission=self.submission, name="util.py", extension=".py", data="y=2"
        )
        files = getCurrentFiles(self.submission)
        self.assertEqual(len(files), 2)


class TestFrozenGrade(TestCase):
    """gradeFrozen prevents recalculation on save."""

    def setUp(self):
        self.org = OrganizationFactory(name="GradeOrg5", shortname="go5")
        self.course = Course.objects.create(name="CS101", period="F2020", organization=self.org)
        self.assignment = Assignment.objects.create(course=self.course, name="HW1", points=20)

    def test_frozen_grade_not_recalculated(self):
        sub = Submission.objects.create(assignment=self.assignment, gradeFrozen=True, grade=Decimal("15"))
        sub.isFinalized = True
        sub.save()
        sub.refresh_from_db()
        # Grade should not have been recalculated
        self.assertEqual(sub.grade, Decimal("15.00"))

    def test_unfrozen_grade_recalculated_on_save(self):
        sub = Submission.objects.create(assignment=self.assignment, gradeFrozen=False)
        sub.refresh_from_db()
        # No comments = full points
        self.assertEqual(sub.grade, Decimal("20.00"))
