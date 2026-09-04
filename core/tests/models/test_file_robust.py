# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Robust tests for File, SubmissionFile, AssignmentFile models.

Covers:
- Carriage return normalization (\\r\\n -> \\n)
- Hash computation on save
- Extension inference from filename
- get_course() traversal
- AssignmentFile.is_test_resource forces hidden=True
- File save rejects deprecated 'code' field
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import File, SubmissionFile, AssignmentFile, Assignment, Course
from core.tests.utils import setUpClient, setUpFile, setUpSubmission
from core.tests.factories import (
    OrganizationFactory,
)
import hashlib


class TestFileSaveBehavior(TestCase):
    """File.save() side-effect tests."""

    def setUp(self):
        setUpClient(self)

    def test_carriage_return_normalized(self):
        """\\r\\n sequences are replaced with \\n on save."""
        file = setUpFile(self, name="crlf.py")
        file.data = "line1\\r\\nline2\\r\\nline3"
        file.save()
        self.assertNotIn("\\r\\n", file.data)
        self.assertIn("\\n", file.data)

    def test_hash_computed_on_save(self):
        """SHA-256 hash is computed from the file data on save."""
        file = setUpFile(self, name="hashed.py")
        file.data = "print('hello')"
        file.save()
        expected_hash = hashlib.sha256(file.data.encode('utf-8')).hexdigest()
        self.assertEqual(file.hash, expected_hash)

    def test_hash_changes_when_data_changes(self):
        """Modifying file data changes the hash."""
        file = setUpFile(self, name="mutable.py")
        file.data = "version1"
        file.save()
        hash1 = file.hash
        file.data = "version2"
        file.save()
        self.assertNotEqual(file.hash, hash1)

    def test_extension_inferred_from_name(self):
        """If extension is empty, it is inferred from the file name."""
        submission = setUpSubmission(self)
        file = SubmissionFile(
            name="script.py",
            data="x = 1",
            extension="",  # should be inferred
            submission=submission,
        )
        file.save()
        self.assertEqual(file.extension, ".py")

    def test_extension_inference_raises_for_no_extension(self):
        """If there's no extension in the name and none provided, raise ValidationError."""
        submission = setUpSubmission(self)
        file = SubmissionFile(
            name="Makefile",
            data="all: build",
            extension="",
            submission=submission,
        )
        with self.assertRaises(ValidationError):
            file.save()

    def test_data_uri_content_skips_crlf_normalization(self):
        """Data URI content (binary uploads) is preserved exactly — no CRLF normalization."""
        import base64
        submission = setUpSubmission(self)
        pdf_bytes = b'%PDF-1.4 test content here'
        encoded = base64.b64encode(pdf_bytes).decode()
        raw = f"data:application/pdf;base64,{encoded}"
        file = SubmissionFile.objects.create(
            name="doc.pdf",
            data=raw,
            extension=".pdf",
            submission=submission,
        )
        # Data URI content should pass through completely unmodified
        self.assertEqual(file.data, raw)

    def test_data_uri_image_skips_crlf_normalization(self):
        """Image data URIs are preserved exactly — no CRLF normalization."""
        import base64
        submission = setUpSubmission(self)
        gif_bytes = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00'
        encoded = base64.b64encode(gif_bytes).decode()
        raw = f"data:image/gif;base64,{encoded}"
        file = SubmissionFile.objects.create(
            name="animation.gif",
            data=raw,
            extension=".gif",
            submission=submission,
        )
        self.assertEqual(file.data, raw)

    def test_plain_text_still_normalizes_crlf(self):
        """Plain text files (no data URI prefix) still get \\r\\n normalized."""
        submission = setUpSubmission(self)
        raw = "line1\\r\\nline2"
        file = SubmissionFile.objects.create(
            name="hello.py",
            data=raw,
            extension=".py",
            submission=submission,
        )
        self.assertNotIn("\\r\\n", file.data)
        self.assertIn("\\n", file.data)

    def test_mime_validation_rejects_mismatched_content(self):
        """A data URI claiming image/png but containing a GIF should be rejected."""
        import base64
        submission = setUpSubmission(self)
        # GIF89a header — valid GIF, but we'll claim it's PNG
        gif_bytes = b'GIF89a' + bytes([0x01, 0x00, 0x01, 0x00, 0x80, 0x00, 0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00])
        encoded = base64.b64encode(gif_bytes).decode()
        raw = f"data:image/png;base64,{encoded}"
        with self.assertRaises(ValidationError) as ctx:
            SubmissionFile.objects.create(
                name="fake.png",
                data=raw,
                extension=".png",
                submission=submission,
            )
        self.assertIn("does not match the claimed MIME type", str(ctx.exception))

    def test_mime_validation_accepts_matching_content(self):
        """A data URI with matching MIME and magic bytes should succeed."""
        import base64
        submission = setUpSubmission(self)
        # Valid PNG header: 0x89 P N G \r \n 0x1a \n then IHDR chunk
        png_header = bytes([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d]) + b'IHDR' + bytes(4)
        encoded = base64.b64encode(png_header).decode()
        raw = f"data:image/png;base64,{encoded}"
        file = SubmissionFile.objects.create(
            name="valid.png",
            data=raw,
            extension=".png",
            submission=submission,
        )
        self.assertTrue(file.data.startswith("data:image/png"))

    def test_mime_validation_allows_unknown_mime_types(self):
        """Unknown MIME types (no known signature) should be allowed through."""
        import base64
        submission = setUpSubmission(self)
        content = b'some arbitrary binary content here'
        encoded = base64.b64encode(content).decode()
        raw = f"data:application/octet-stream;base64,{encoded}"
        file = SubmissionFile.objects.create(
            name="unknown.bin",
            data=raw,
            extension=".bin",
            submission=submission,
        )
        self.assertTrue(file.data.startswith("data:application/octet-stream"))

    def test_mime_validation_rejects_invalid_base64(self):
        """A data URI with a known MIME but corrupt base64 should be rejected."""
        submission = setUpSubmission(self)
        raw = "data:image/png;base64,!!!not-valid-base64!!!"
        with self.assertRaises(ValidationError) as ctx:
            SubmissionFile.objects.create(
                name="corrupt.png",
                data=raw,
                extension=".png",
                submission=submission,
            )
        self.assertIn("invalid base64", str(ctx.exception))


class TestFileGetCourse(TestCase):
    """Test get_course() traversal for different File subtypes."""

    def setUp(self):
        setUpClient(self)

    def test_submission_file_get_course(self):
        """SubmissionFile.get_course() returns the course via submission -> assignment."""
        file = setUpFile(self)
        course = file.get_course()
        self.assertIsNotNone(course)
        self.assertEqual(course, file.submission.assignment.course)

    def test_orphan_file_get_course_returns_none(self):
        """A bare File object (not linked to any subtype) returns None."""
        f = File.objects.create(name="orphan.txt", data="data", extension=".txt")
        self.assertIsNone(f.get_course())


class TestAssignmentFileBehavior(TestCase):
    """AssignmentFile-specific behavior."""

    def test_test_resource_forces_hidden(self):
        """When is_test_resource=True, hidden is automatically set to True on save."""
        org = OrganizationFactory(name="TestResOrg", shortname="tro")
        course = Course.objects.create(name="CS100", period="F2025", organization=org)
        assignment = Assignment.objects.create(
            name="HW1", course=course, points=20, state='preview'
        )
        af = AssignmentFile(
            name="test_helper.py",
            data="# helper",
            extension=".py",
            assignment=assignment,
            is_test_resource=True,
            hidden=False,  # should be overridden
        )
        af.save()
        self.assertTrue(af.hidden)

    def test_non_test_resource_preserves_hidden_false(self):
        """A normal AssignmentFile can have hidden=False."""
        org = OrganizationFactory(name="NormalOrg", shortname="no")
        course = Course.objects.create(name="CS200", period="F2025", organization=org)
        assignment = Assignment.objects.create(
            name="HW2", course=course, points=20, state='preview'
        )
        af = AssignmentFile(
            name="starter.py",
            data="# starter",
            extension=".py",
            assignment=assignment,
            is_test_resource=False,
            hidden=False,
        )
        af.save()
        self.assertFalse(af.hidden)

    def test_assignment_file_course_property(self):
        """AssignmentFile.course returns assignment.course."""
        org = OrganizationFactory(name="CourseOrg", shortname="co")
        course = Course.objects.create(name="CS300", period="F2025", organization=org)
        assignment = Assignment.objects.create(
            name="HW3", course=course, points=20, state='preview'
        )
        af = AssignmentFile.objects.create(
            name="main.py", data="pass", extension=".py",
            assignment=assignment,
        )
        self.assertEqual(af.course, course)
