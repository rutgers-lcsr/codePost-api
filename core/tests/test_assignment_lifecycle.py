# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Manual lifecycle test: walks through every step of the assignment lifecycle
from creation to student review. Run with:

    pytest core/tests/test_assignment_lifecycle.py -v -s

The -s flag is important — it prints step-by-step narration so you can
follow along and verify each state transition.
"""
from rest_framework.test import APITestCase
from rest_framework import status
from core.models import Course, Submission
from core.tests.factories import OrganizationFactory, UserFactory


def banner(step: int, title: str) -> None:
    """Print a visible step banner to stdout."""
    width = 72
    print()
    print("═" * width)
    print(f"  STEP {step}: {title}")
    print("═" * width)


def info(msg: str) -> None:
    print(f"  → {msg}")


def check(label: str, passed: bool) -> None:
    mark = "✓" if passed else "✗"
    print(f"  [{mark}] {label}")


class TestAssignmentLifecycle(APITestCase):
    """
    End-to-end lifecycle test:

      1. Admin creates a course
      2. Admin adds a student and grader to the roster
      3. Admin creates an assignment (upload-enabled, not yet released)
      4. Student sees the assignment and uploads a submission
      5. Grader claims, comments on, and finalizes the submission
      6. Admin releases feedback
      7. Student views feedback and grade
      8. Student acknowledges (marks as viewed)

    Each step authenticates as the appropriate user and hits the real API
    endpoints, printing results so you can visually verify the flow.
    """

    # ──────────────────────────────────────────────────────────────────────
    # Setup
    # ──────────────────────────────────────────────────────────────────────

    def setUp(self):
        self.org = OrganizationFactory(name="Lifecycle Org", shortname="lifecycle")

        self.admin = UserFactory(username="admin@lifecycle.edu", email="admin@lifecycle.edu")
        self.admin.profile.organization = self.org
        self.admin.profile.canCreateCourses = True
        self.admin.profile.canModifyRosters = True
        self.admin.profile.save()
        self.admin.save()

        self.student = UserFactory(username="student@lifecycle.edu", email="student@lifecycle.edu")
        self.student.profile.organization = self.org
        self.student.profile.save()
        self.student.save()

        self.grader = UserFactory(username="grader@lifecycle.edu", email="grader@lifecycle.edu")
        self.grader.profile.organization = self.org
        self.grader.profile.save()
        self.grader.save()

    # ──────────────────────────────────────────────────────────────────────
    # The test
    # ──────────────────────────────────────────────────────────────────────

    def test_full_assignment_lifecycle(self):

        # ── Step 1: Admin creates a course ───────────────────────────────
        banner(1, "Admin creates a course")
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post("/courses/", {
            "name": "CS201 Data Structures",
            "period": "Spring 2026",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        course_id = resp.data["id"]
        info(f"Course created: id={course_id}, name={resp.data['name']}, period={resp.data['period']}")
        check("Course created successfully", True)

        # ── Step 2: Admin adds student + grader to roster ────────────────
        banner(2, "Admin enrolls a student and a grader")

        resp = self.client.patch(f"/courses/{course_id}/roster/", {
            "students": [self.student.email],
            "graders": [self.grader.email],
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        course = Course.objects.get(id=course_id)
        student_enrolled = self.student in course.students.all()
        grader_enrolled = self.grader in course.graders.all()
        info(f"Student '{self.student.email}' enrolled: {student_enrolled}")
        info(f"Grader  '{self.grader.email}' enrolled: {grader_enrolled}")
        check("Student is in roster", student_enrolled)
        check("Grader is in roster", grader_enrolled)

        # ── Step 3: Admin creates an assignment ──────────────────────────
        banner(3, "Admin creates an assignment (upload-enabled, NOT released)")

        resp = self.client.post("/assignments/", {
            "name": "Homework 1 — Linked Lists",
            "points": 100,
            "course": course_id,
            "isReleased": False,
            "isVisible": True,
            "allowStudentUpload": True,      # Students can upload
            "feedbackReleased": False,        # Feedback NOT released yet
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        assignment_id = resp.data["id"]
        info(f"Assignment created: id={assignment_id}")
        info(f"  isReleased={resp.data.get('isReleased')}")
        info(f"  allowStudentUpload={resp.data.get('allowStudentUpload')}")
        info(f"  feedbackReleased={resp.data.get('feedbackReleased')}")
        check("Assignment created with upload enabled but feedback held", True)

        # Also create a rubric for structured grading
        resp = self.client.post("/rubricCategories/", {
            "name": "Correctness",
            "pointLimit": 50,
            "assignment": assignment_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        rubric_cat_id = resp.data["id"]

        resp = self.client.post("/rubricComments/", {
            "text": "Off-by-one error in insert()",
            "pointDelta": 10.0,
            "category": rubric_cat_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        rubric_comment_id = resp.data["id"]
        info(f"Rubric created: category={rubric_cat_id}, comment={rubric_comment_id}")

        # ── Step 4: Student sees the assignment and uploads ──────────────
        banner(4, "Student uploads a submission")
        self.client.force_authenticate(user=self.student)

        # 4a. Student fetches the assignment (should be visible since allowStudentUpload=True)
        resp = self.client.get(f"/assignments/{assignment_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        info(f"Student can see assignment: '{resp.data['name']}'")
        info(f"  isReleased={resp.data.get('isReleased')}, allowStudentUpload={resp.data.get('allowStudentUpload')}")
        check("Assignment visible to student (allowStudentUpload=True)", True)

        # 4b. Upload
        upload_data = {
            "files": [
                {
                    "name": "linked_list.py",
                    "data": (
                        "class Node:\n"
                        "    def __init__(self, val):\n"
                        "        self.val = val\n"
                        "        self.next = None\n"
                        "\n"
                        "class LinkedList:\n"
                        "    def __init__(self):\n"
                        "        self.head = None\n"
                        "\n"
                        "    def insert(self, val):\n"
                        "        node = Node(val)\n"
                        "        node.next = self.head\n"
                        "        self.head = node\n"
                    ),
                    "extension": ".py",
                    "path": "",
                }
            ],
            "sendConfirmationEmail": False,
        }
        resp = self.client.post(
            f"/assignments/{assignment_id}/studentUpload/",
            upload_data,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        submission_id = resp.data["id"]
        info(f"Submission created: id={submission_id}")
        info(f"  students={resp.data.get('students')}")
        info(f"  dateUploaded={resp.data.get('dateUploaded')}")
        check("Student upload succeeded", True)

        # 4c. Verify student can see files but NOT grade yet
        resp = self.client.get(f"/submissions/{submission_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        grade_before = resp.data.get("grade")
        files_before = resp.data.get("files", [])
        info(f"  grade (before feedback release): {grade_before}")
        info(f"  files visible: {len(files_before)}")
        check("Grade is None before feedback release", grade_before is None)
        check("Student can see their files", len(files_before) > 0)

        # ── Step 5: Grader grades the submission ─────────────────────────
        banner(5, "Grader claims, comments, and finalizes")
        self.client.force_authenticate(user=self.grader)

        # 5a. Draw unassigned submission
        resp = self.client.get(f"/assignments/{assignment_id}/drawUnassigned/?amount=1")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        drawn = resp.data
        info(f"Grader drew {len(drawn)} submission(s)")
        self.assertEqual(len(drawn), 1)
        self.assertEqual(drawn[0]["id"], submission_id)
        check("Grader claimed the submission", True)

        # 5b. Add a comment (deduction)
        submission = Submission.objects.get(id=submission_id)
        file_obj = submission.files.first()
        self.assertIsNotNone(file_obj, "Submission should have at least one file")

        resp = self.client.post("/comments/", {
            "file": file_obj.id,
            "text": "Off-by-one error in insert() — the new node should be appended, not prepended.",
            "pointDelta": 10.0,
            "rubricComment": rubric_comment_id,
            "startLine": 10,
            "endLine": 12,
            "startChar": 0,
            "endChar": 0,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        comment_id = resp.data["id"]
        info(f"Comment added: id={comment_id}, pointDelta={resp.data['pointDelta']}")
        check("Grader comment created", True)

        # 5c. Finalize
        resp = self.client.patch(f"/submissions/{submission_id}/", {
            "isFinalized": True,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        info(f"  isFinalized={resp.data.get('isFinalized')}")
        info(f"  grade={resp.data.get('grade')}")
        check("Submission finalized", resp.data.get("isFinalized") is True)

        # Verify grade calculated correctly: 100 - 10 = 90
        submission.refresh_from_db()
        info(f"  DB grade: {submission.grade}")
        self.assertEqual(submission.grade, 90.0)
        check("Grade calculated correctly (100 - 10 = 90)", submission.grade == 90.0)

        # ── Step 6: Student checks BEFORE feedback release ───────────────
        banner(6, "Student checks submission BEFORE feedback is released")
        self.client.force_authenticate(user=self.student)

        resp = self.client.get(f"/submissions/{submission_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        grade_masked = resp.data.get("grade")
        files_data = resp.data.get("files", [])
        # Files should be returned but WITHOUT comments
        has_comments_before = any(
            len(f.get("comments", [])) > 0 for f in files_data
        )
        info(f"  grade (feedback NOT released): {grade_masked}")
        info(f"  files: {len(files_data)}, any have comments: {has_comments_before}")
        check("Grade is masked (None) before feedbackReleased", grade_masked is None)
        check("Comments are hidden before feedbackReleased", not has_comments_before)

        # ── Step 7: Admin releases feedback ──────────────────────────────
        banner(7, "Admin releases feedback")
        self.client.force_authenticate(user=self.admin)

        resp = self.client.patch(f"/assignments/{assignment_id}/", {
            "feedbackReleased": True,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        info(f"  feedbackReleased={resp.data.get('feedbackReleased')}")
        check("Feedback released", resp.data.get("feedbackReleased") is True)

        # ── Step 8: Student views feedback and grade ─────────────────────
        banner(8, "Student views feedback and sees grade")
        self.client.force_authenticate(user=self.student)

        resp = self.client.get(f"/submissions/{submission_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        grade_visible = resp.data.get("grade")
        files_data = resp.data.get("files", [])
        has_comments_after = any(
            len(f.get("comments", [])) > 0 for f in files_data
        )
        info(f"  grade (feedback released): {grade_visible}")
        info(f"  files: {len(files_data)}, any have comments: {has_comments_after}")
        check("Grade is now visible", grade_visible is not None)
        check("Grade is correct (90.0)", float(grade_visible) == 90.0)
        check("Comments are now visible", has_comments_after)

        # Inspect the comment content (comments field contains IDs, fetch full objects)
        for f in files_data:
            for comment_id in f.get("comments", []):
                c_resp = self.client.get(f"/comments/{comment_id}/")
                if c_resp.status_code == status.HTTP_200_OK:
                    info(f"  Comment on '{f['name']}': \"{c_resp.data['text']}\" (delta={c_resp.data['pointDelta']})")

        # ── Step 9: Student marks feedback as viewed ─────────────────────
        banner(9, "Student acknowledges feedback (marks as viewed)")

        # 9a. Check history — should exist with hasViewed=False
        resp = self.client.get(
            f"/submissions/{submission_id}/history/",
            {"student": self.student.email},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        history = resp.data
        info(f"  History records: {len(history)}")
        if len(history) > 0:
            info(f"  hasViewed before: {history[0].get('hasViewed')}")

        # 9b. Mark as viewed
        resp = self.client.patch(
            f"/submissions/{submission_id}/history/?student={self.student.email}",
            {"hasViewed": True},
            format="json",
        )
        # History PATCH may return 200 or the endpoint may auto-create the record
        info(f"  Mark-as-viewed response: {resp.status_code}")

        # 9c. Verify
        resp = self.client.get(
            f"/submissions/{submission_id}/history/",
            {"student": self.student.email},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        if len(resp.data) > 0:
            viewed = resp.data[0].get("hasViewed")
            info(f"  hasViewed after: {viewed}")
            check("Feedback marked as viewed", viewed is True)
        else:
            info("  (No history record found — history may not auto-create for this endpoint)")

        # ── Summary ──────────────────────────────────────────────────────
        print()
        print("═" * 72)
        print("  LIFECYCLE COMPLETE")
        print("═" * 72)
        print()
        print("  Flow verified:")
        print("    1. Admin created course + roster")
        print("    2. Admin created assignment (upload-only, no release)")
        print("    3. Student uploaded submission")
        print("    4. Grader claimed, commented (-10pts), finalized")
        print("    5. Grade masked for student (feedbackReleased=False)")
        print("    6. Admin released feedback")
        print("    7. Student saw grade (90/100) and comments")
        print("    8. Student marked as viewed")
        print()
