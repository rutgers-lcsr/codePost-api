# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import (
    Assignment,
    AssignmentFile,
    Comment,
    Course,
    Environment,
    RubricCategory,
    RubricComment,
    Submission,
    SubmissionFile,
    TestCase,
    TestCategory,
    User,
)


# ── Sample file content ──────────────────────────────────────────────

PYTHON_HELLO = """\
def hello(name):
    \"\"\"Return a greeting.\"\"\"
    return f"Hello, {name}!"


def add(a, b):
    return a + b


if __name__ == "__main__":
    print(hello("world"))
"""

PYTHON_BROKEN = """\
def hello(name):
    # Bug: missing f-string prefix
    return "Hello, {name}!"


def add(a, b):
    return a - b  # Bug: should be addition


if __name__ == "__main__":
    print(hello("world"))
"""

JAVA_HELLO = """\
public class Hello {
    public static String greet(String name) {
        return "Hello, " + name + "!";
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(greet("world"));
    }
}
"""

MARKDOWN_README = """\
# My Project

This is a sample README for the demo submission.

## Features
- Feature A
- Feature B

## Usage
```python
from hello import hello
print(hello("world"))
```
"""

NOTEBOOK_CONTENT = """\
{
 "cells": [
  {"cell_type": "markdown", "metadata": {}, "source": ["# Demo Notebook\\n", "This is a sample notebook."]},
  {"cell_type": "code", "execution_count": 1, "metadata": {}, "outputs": [{"name": "stdout", "output_type": "stream", "text": ["Hello, world!\\n"]}], "source": ["print('Hello, world!')"]},
  {"cell_type": "code", "execution_count": 2, "metadata": {}, "outputs": [{"name": "stdout", "output_type": "stream", "text": ["42\\n"]}], "source": ["x = 42\\nprint(x)"]}
 ],
 "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.12.0"}},
 "nbformat": 4,
 "nbformat_minor": 5
}
"""


class Command(BaseCommand):
    help = "Creates a demo course with assignments covering every toggle/option, plus student submissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the existing demo course before recreating it.",
        )
        parser.add_argument(
            "--course-name",
            default="Demo Course",
            help="Name for the demo course (default: 'Demo Course').",
        )
        parser.add_argument(
            "--period",
            default="Spring 2026",
            help="Period for the demo course (default: 'Spring 2026').",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This command can only be run in DEBUG mode.")

        course_name = options["course_name"]
        period = options["period"]

        # ── Resolve org from first superuser ──────────────────────────
        admin_user = User.objects.filter(is_superuser=True).order_by("id").first()
        if not admin_user:
            raise CommandError("No superuser found. Run 'createsuperuser' first.")

        if not hasattr(admin_user, "profile") or not admin_user.profile.organization:
            raise CommandError(f"Superuser {admin_user.username} has no organization.")

        org = admin_user.profile.organization
        self.stdout.write(self.style.SUCCESS(f"Organization: {org.name}"))

        # ── Reset if requested ────────────────────────────────────────
        if options["reset"]:
            deleted, _ = Course.objects.filter(
                name=course_name, period=period, organization=org
            ).delete()
            if deleted:
                self.stdout.write(self.style.WARNING(f"Deleted existing '{course_name} | {period}'."))

        # ── Ensure test users exist ───────────────────────────────────
        student = self._ensure_user("student_only", "student_only@dev.edu", "Test", "Student", org)
        grader = self._ensure_user("grader_basic", "grader_basic@dev.edu", "Test", "Grader", org)
        cadmin = self._ensure_user("course_admin_only", "course_admin_only@dev.edu", "Test", "Admin", org)

        # ── Create course ─────────────────────────────────────────────
        course, created = Course.objects.get_or_create(
            name=course_name,
            period=period,
            organization=org,
            defaults={
                "sendReleasedSubmissionsToBack": True,
                "showStudentsStatistics": True,
                "emailNewUsers": False,
                "anonymousGradingDefault": False,
                "allowGradersToEditRubric": True,
                "minComments": 2,
                "noUnfinalize": False,
                "useStudentCaptions": True,
                "activateQueue": True,
                "inviteCodeEnabled": False,
                "studentsCanSeeGraders": True,
                "enableStudentFeedbackNotifications": True,
                "studentCaptions": {
                    "student_only@dev.edu": "Alice (Section A)",
                },
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created course: {course}"))
        else:
            self.stdout.write(f"Course already exists: {course}")

        # Enroll users
        course.students.add(student)
        course.graders.add(grader)
        course.courseAdmins.add(cadmin, admin_user)

        now = timezone.now()

        # ══════════════════════════════════════════════════════════════
        # Assignment 1 — Defaults (minimal config)
        # ══════════════════════════════════════════════════════════════
        a1 = self._ensure_assignment(course, "1. Defaults Only", points=100, sortKey=1)
        self._add_rubric(a1, deductive=True)
        self._add_submission(a1, student, grader, finalized=True, files=[
            ("hello.py", ".py", PYTHON_HELLO),
        ])

        # ══════════════════════════════════════════════════════════════
        # Assignment 2 — Student upload enabled, with due date & late policy
        # ══════════════════════════════════════════════════════════════
        a2 = self._ensure_assignment(course, "2. Student Upload", points=50, sortKey=2, extra={
            "allowStudentUpload": True,
            "allowStudentUploadWithPartners": True,
            "uploadDueDate": now + timedelta(days=7),
            "maxLateDays": 3,
            "allowLateUploads": True,
            "lateDeductions": [0, -5, -10, -15],
            "explanation": "Upload your hello.py file. Partners allowed. Late submissions accepted with deductions.",
        })
        # Template / required file
        AssignmentFile.objects.get_or_create(
            assignment=a2, name="hello.py",
            defaults={"extension": ".py", "data": PYTHON_HELLO, "required": True,
                       "description": "Main entry point — implement hello()"},
        )
        self._add_rubric(a2, deductive=True)
        self._add_submission(a2, student, grader, finalized=False, files=[
            ("hello.py", ".py", PYTHON_BROKEN),
        ])

        # ══════════════════════════════════════════════════════════════
        # Assignment 3 — Additive grading + anonymous + forced rubric
        # ══════════════════════════════════════════════════════════════
        a3 = self._ensure_assignment(course, "3. Additive+Anon+Forced", points=80, sortKey=3, extra={
            "additiveGrading": True,
            "anonymousGrading": True,
            "forcedRubricMode": True,
            "hideGrades": True,
            "isReleased": True,
            "feedbackReleased": True,
            "commentFeedback": True,
        })
        self._add_rubric(a3, deductive=False)
        sub3 = self._add_submission(a3, student, grader, finalized=True, files=[
            ("hello.py", ".py", PYTHON_HELLO),
            ("README.md", ".md", MARKDOWN_README),
        ])
        # Add a comment with feedback
        if sub3:
            sf = sub3.files.first()
            if sf and not Comment.objects.filter(file=sf).exists():
                rc = a3.rubricCategories.first()
                rubric_comment = rc.rubricComments.first() if rc else None
                Comment.objects.create(
                    file=sf, author=grader, text="This looks good but could be improved.",
                    startLine=0, endLine=2, startChar=0, endChar=0,
                    rubricComment=rubric_comment, feedback=1,
                )

        # ══════════════════════════════════════════════════════════════
        # Assignment 4 — Regrade requests + live feedback + collaborative rubric
        # ══════════════════════════════════════════════════════════════
        a4 = self._ensure_assignment(course, "4. Regrades+Live", points=100, sortKey=4, extra={
            "allowRegradeRequests": True,
            "regradeInstructions": "Explain which rubric comment you disagree with and why.\n\n**Be specific.**",
            "regradeDeadline": now + timedelta(days=14),
            "liveFeedbackMode": True,
            "collaborativeRubricMode": True,
            "isReleased": True,
            "feedbackReleased": True,
            "studentsCanSeeGraders": True,
        })
        self._add_rubric(a4, deductive=True)
        sub4 = self._add_submission(a4, student, grader, finalized=True, files=[
            ("hello.py", ".py", PYTHON_HELLO),
        ])
        if sub4 and not sub4.questionIsOpen:
            sub4.questionIsOpen = True
            sub4.questionIsRegrade = True
            sub4.questionText = "I think the -5 for style is unfair — my code follows PEP 8."
            sub4.questionDate = now
            sub4.save()

        # ══════════════════════════════════════════════════════════════
        # Assignment 5 — Template mode + frequently used rubric comments
        # ══════════════════════════════════════════════════════════════
        a5 = self._ensure_assignment(course, "5. Templates+FreqRC", points=100, sortKey=5, extra={
            "templateMode": True,
            "showFrequentlyUsedRubricComments": True,
            "gradersCanEditSubmissions": True,
        })
        AssignmentFile.objects.get_or_create(
            assignment=a5, name="template.py",
            defaults={"extension": ".py", "data": "# Template: students fill in below\ndef solve():\n    pass\n",
                       "required": False, "description": "Template — do not modify the function signature."},
        )
        AssignmentFile.objects.get_or_create(
            assignment=a5, name="hidden_helper.py",
            defaults={"extension": ".py", "data": "# Internal helper\nSECRET = 42\n",
                       "hidden": True, "description": "Hidden helper for tests"},
        )
        self._add_rubric(a5, deductive=True)
        self._add_submission(a5, student, grader, finalized=True, files=[
            ("template.py", ".py", "def solve():\n    return 42\n"),
        ])

        # ══════════════════════════════════════════════════════════════
        # Assignment 6 — Java assignment with autograder tests
        # ══════════════════════════════════════════════════════════════
        a6 = self._ensure_assignment(course, "6. Java+Autograder", points=100, sortKey=6, extra={
            "runTestsOnSubmit": True,
            "testsAffectGrade": True,
            "runFilesOnSubmit": True,
            "isReleased": True,
            "feedbackReleased": True,
        })
        # Environment
        Environment.objects.update_or_create(
            assignment=a6,
            defaults={
                "language": "java",
                "buildType": "default",
                "compileText": "javac Hello.java",
                "allowNetworkAccess": False,
                "maxStudentTestRuns": 5,
                "maxExposedFailedTests": 2,
                "requirements": "",
            },
        )
        AssignmentFile.objects.get_or_create(
            assignment=a6, name="Hello.java",
            defaults={"extension": ".java", "data": JAVA_HELLO, "required": True},
        )
        self._add_test_suite(a6)
        self._add_rubric(a6, deductive=True)
        self._add_submission(a6, student, grader, finalized=True, files=[
            ("Hello.java", ".java", JAVA_HELLO),
        ])

        # ══════════════════════════════════════════════════════════════
        # Assignment 7 — Python autograder + exposed tests
        # ══════════════════════════════════════════════════════════════
        a7 = self._ensure_assignment(course, "7. Python+Tests", points=60, sortKey=7, extra={
            "runTestsOnSubmit": True,
            "testsAffectGrade": True,
            "allowStudentUpload": True,
            "uploadDueDate": now + timedelta(days=5),
        })
        Environment.objects.update_or_create(
            assignment=a7,
            defaults={
                "language": "python-3.12",
                "buildType": "default",
                "requirements": "pytest\n",
                "allowNetworkAccess": False,
                "maxStudentTestRuns": 10,
            },
        )
        self._add_test_suite(a7, language="python")
        self._add_rubric(a7, deductive=True)
        self._add_submission(a7, student, grader, finalized=False, files=[
            ("hello.py", ".py", PYTHON_BROKEN),
        ])

        # ══════════════════════════════════════════════════════════════
        # Assignment 8 — Hidden assignment (not visible to students)
        # ══════════════════════════════════════════════════════════════
        self._ensure_assignment(course, "8. Hidden", points=100, sortKey=8, extra={
            "isVisible": False,
        })

        # ══════════════════════════════════════════════════════════════
        # Assignment 9 — Released & feedback released, grade frozen sub
        # ══════════════════════════════════════════════════════════════
        a9 = self._ensure_assignment(course, "9. Released+Frozen", points=100, sortKey=9, extra={
            "isReleased": True,
            "feedbackReleased": True,
            "hideGradersFromStudents": False,
        })
        self._add_rubric(a9, deductive=True)
        sub9 = self._add_submission(a9, student, grader, finalized=True, files=[
            ("hello.py", ".py", PYTHON_HELLO),
        ])
        if sub9:
            sub9.gradeFrozen = True
            sub9.grade = Decimal("85.00")
            sub9.save()

        # ══════════════════════════════════════════════════════════════
        # Assignment 10 — Notebook assignment
        # ══════════════════════════════════════════════════════════════
        a10 = self._ensure_assignment(course, "10. Notebook", points=50, sortKey=10, extra={
            "isReleased": True,
            "feedbackReleased": True,
            "allowStudentUpload": True,
            "uploadDueDate": now + timedelta(days=10),
        })
        Environment.objects.update_or_create(
            assignment=a10,
            defaults={"language": "python-3.12", "buildType": "default"},
        )
        self._add_rubric(a10, deductive=True)
        self._add_submission(a10, student, grader, finalized=True, files=[
            ("demo.ipynb", ".ipynb", NOTEBOOK_CONTENT),
        ])

        # ══════════════════════════════════════════════════════════════
        # Assignment 11 — Past due, late upload
        # ══════════════════════════════════════════════════════════════
        a11 = self._ensure_assignment(course, "11. Past Due", points=100, sortKey=11, extra={
            "allowStudentUpload": True,
            "uploadDueDate": now - timedelta(days=2),
            "maxLateDays": 5,
            "allowLateUploads": True,
            "lateDeductions": [0, -10, -20, -30, -40, -50],
        })
        self._add_rubric(a11, deductive=True)
        sub11 = self._add_submission(a11, student, grader, finalized=False, files=[
            ("hello.py", ".py", PYTHON_HELLO),
        ])
        if sub11:
            sub11.lateDayCreditsUsed = 2
            sub11.save()

        # ══════════════════════════════════════════════════════════════
        # Assignment 12 — Multi-file submission with colored comments
        # ══════════════════════════════════════════════════════════════
        a12 = self._ensure_assignment(course, "12. Multi-file+Colors", points=100, sortKey=12, extra={
            "isReleased": True,
            "feedbackReleased": True,
        })
        self._add_rubric(a12, deductive=True)
        sub12 = self._add_submission(a12, student, grader, finalized=True, files=[
            ("hello.py", ".py", PYTHON_HELLO),
            ("Hello.java", ".java", JAVA_HELLO),
            ("README.md", ".md", MARKDOWN_README),
        ])
        if sub12:
            for i, sf in enumerate(sub12.files.all()):
                if not Comment.objects.filter(file=sf).exists():
                    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1"]
                    Comment.objects.create(
                        file=sf, author=grader,
                        text=f"Comment on {sf.name}",
                        startLine=0, endLine=1, startChar=0, endChar=0,
                        pointDelta=Decimal("-2.00"),
                        color=colors[i % len(colors)],
                    )

        self.stdout.write(self.style.SUCCESS(
            f"\nDemo course ready: {course.name} | {course.period}\n"
            f"  Assignments: {course.assignments.count()}\n"
            f"  Student: student_only / password\n"
            f"  Grader:  grader_basic / password\n"
            f"  Admin:   course_admin_only / password"
        ))

    # ── Helpers ────────────────────────────────────────────────────────

    def _ensure_user(self, username, email, first_name, last_name, org):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "first_name": first_name, "last_name": last_name},
        )
        if created:
            user.set_password("password")
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user: {username}"))
        user.profile.organization = org
        user.profile.save()
        return user

    def _ensure_assignment(self, course, name, points, sortKey, extra=None):
        defaults = {"points": Decimal(str(points)), "sortKey": sortKey}
        if extra:
            defaults.update(extra)
        assignment, created = Assignment.objects.get_or_create(
            course=course, name=name, defaults=defaults,
        )
        if created:
            self.stdout.write(f"  + Assignment: {name}")
        return assignment

    def _add_rubric(self, assignment, deductive=True):
        """Add a standard rubric with categories and comments."""
        if assignment.rubricCategories.exists():
            return

        # Category 1: Correctness
        cat1, _ = RubricCategory.objects.get_or_create(
            assignment=assignment, name="Correctness",
            defaults={"pointLimit": None if deductive else 60, "sortKey": 0,
                       "helpText": "Does the code produce correct output?"},
        )
        if deductive:
            deltas = [("-5.00", "Off-by-one error"), ("-10.00", "Wrong return type"),
                      ("-15.00", "Crashes on edge case"), ("-20.00", "Incorrect algorithm")]
        else:
            deltas = [("10.00", "Correct for basic cases"), ("20.00", "Handles edge cases"),
                      ("30.00", "Fully correct")]
        for i, (delta, text) in enumerate(deltas):
            RubricComment.objects.get_or_create(
                category=cat1, text=text,
                defaults={"pointDelta": Decimal(delta), "sortKey": i,
                           "explanation": f"Student explanation: {text}"},
            )

        # Category 2: Style
        cat2, _ = RubricCategory.objects.get_or_create(
            assignment=assignment, name="Style",
            defaults={"pointLimit": 20 if deductive else None, "sortKey": 1,
                       "helpText": "Code readability and formatting.", "atMostOnce": False},
        )
        style_items = [
            ("-3.00" if deductive else "5.00", "Good variable names"),
            ("-5.00" if deductive else "5.00", "Proper indentation"),
            ("-2.00" if deductive else "5.00", "Adequate comments"),
        ]
        for i, (delta, text) in enumerate(style_items):
            RubricComment.objects.get_or_create(
                category=cat2, text=text,
                defaults={"pointDelta": Decimal(delta), "sortKey": i},
            )

        # Category 3: Completion (at-most-once)
        cat3, _ = RubricCategory.objects.get_or_create(
            assignment=assignment, name="Completion",
            defaults={"pointLimit": None, "sortKey": 2, "atMostOnce": True,
                       "helpText": "Was the assignment completed?"},
        )
        RubricComment.objects.get_or_create(
            category=cat3, text="Incomplete submission",
            defaults={"pointDelta": Decimal("-25.00"), "sortKey": 0,
                       "explanation": "Significant portions are missing.",
                       "instructionText": "Describe what is missing:",
                       "templateTextOn": True},
        )

    def _add_test_suite(self, assignment, language="java"):
        """Add test categories and cases."""
        if assignment.testCategories.exists():
            return

        cat, _ = TestCategory.objects.get_or_create(
            assignment=assignment, name="Unit Tests",
            defaults={"maxPoints": Decimal("40.00"), "sortKey": 0},
        )
        tests = [
            {"description": "Test hello('world')", "type": "script", "pointsPass": Decimal("10.00"),
             "exposed": True, "sortKey": 0},
            {"description": "Test hello('')", "type": "script", "pointsPass": Decimal("10.00"),
             "exposed": True, "sortKey": 1},
            {"description": "Test add(2,3)", "type": "script", "pointsPass": Decimal("10.00"),
             "exposed": False, "sortKey": 2},
            {"description": "Test add(-1,1)", "type": "script", "pointsPass": Decimal("10.00"),
             "exposed": False, "sortKey": 3},
        ]
        for t in tests:
            TestCase.objects.get_or_create(
                testCategory=cat, description=t["description"],
                defaults=t,
            )

        # A second category for integration tests
        cat2, _ = TestCategory.objects.get_or_create(
            assignment=assignment, name="Integration Tests",
            defaults={"maxPoints": Decimal("20.00"), "sortKey": 1},
        )
        TestCase.objects.get_or_create(
            testCategory=cat2, description="End-to-end run",
            defaults={"type": "script", "pointsPass": Decimal("20.00"),
                       "exposed": False, "sortKey": 0},
        )

    def _add_submission(self, assignment, student, grader, finalized, files):
        """Create a submission for the student with the given files. Returns the Submission or None if it already existed."""
        existing = Submission.objects.filter(assignment=assignment, students=student).first()
        if existing:
            return None

        sub = Submission.objects.create(
            assignment=assignment,
            grader=grader if finalized else None,
            isFinalized=finalized,
            dateUploaded=timezone.now(),
        )
        sub.students.add(student)

        for name, ext, data in files:
            SubmissionFile.objects.create(
                submission=sub, name=name, extension=ext, data=data,
            )

        # Apply a rubric comment to the first file if finalized
        if finalized:
            first_file = sub.files.first()
            first_rc = assignment.rubricCategories.first()
            if first_file and first_rc:
                rubric_comment = first_rc.rubricComments.first()
                if rubric_comment and not Comment.objects.filter(file=first_file).exists():
                    Comment.objects.create(
                        file=first_file, author=grader,
                        text="Applied via demo setup.",
                        startLine=0, endLine=0, startChar=0, endChar=0,
                        rubricComment=rubric_comment,
                    )
            # Trigger grade recalculation
            sub.save()

        return sub
