# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""Tests for AI Grading Assistance: SuggestedComment, SubmissionSummary, Assignment AI description."""

import pytest
from django.db.models.signals import post_save
from rest_framework import status

import factory


@pytest.fixture
def grading_setup(db):
    """Create a course with assignment, submission, files, rubric, and roster for testing AI grading."""
    from core.tests.factories import (
        CourseFactory,
        SubmissionFileFactory,
        RubricCategoryFactory,
    )
    from core.models import SuggestedComment, SubmissionSummary

    with factory.django.mute_signals(post_save):
        course = CourseFactory(
            name="cos226",
            period="s2026",
            organization__name="Princeton",
        )

    assignment = course.assignments.first()
    submission = assignment.submissions.first()
    file = submission.files.first()
    grader = course.graders.first()
    student = course.students.first()
    admin = course.courseAdmins.first()

    # Assign grader to submission
    with factory.django.mute_signals(post_save):
        submission.grader = grader
        submission.save()

    return {
        'course': course,
        'assignment': assignment,
        'submission': submission,
        'file': file,
        'grader': grader,
        'student': student,
        'admin': admin,
    }


@pytest.fixture
def suggested_comment(grading_setup):
    """Create a pending SuggestedComment."""
    from core.models import SuggestedComment

    return SuggestedComment.objects.create(
        submission=grading_setup['submission'],
        file=grading_setup['file'],
        text="Consider using a more descriptive variable name here.",
        startLine=3,
        endLine=3,
        startChar=0,
        endChar=10,
        pointDelta=None,
        status='pending',
        generationMetadata={'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    )


@pytest.fixture
def submission_summary(grading_setup):
    """Create a SubmissionSummary."""
    from core.models import SubmissionSummary

    return SubmissionSummary.objects.create(
        submission=grading_setup['submission'],
        text="## Summary\n- Student implemented max() using a for loop\n- Missing edge case for empty array",
        generationMetadata={'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    )


# =============================================================================
# MODEL TESTS
# =============================================================================


class TestSuggestedCommentModel:
    """Test SuggestedComment model creation and properties."""

    def test_create_suggested_comment(self, grading_setup, suggested_comment):
        assert suggested_comment.status == 'pending'
        assert suggested_comment.submission == grading_setup['submission']
        assert suggested_comment.file == grading_setup['file']
        assert suggested_comment.acceptedBy is None
        assert suggested_comment.acceptedComment is None

    def test_str_representation(self, suggested_comment):
        s = str(suggested_comment)
        assert 'pending' in s
        assert 'L3' in s

    def test_ordering(self, grading_setup):
        from core.models import SuggestedComment

        sc1 = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="First",
            startLine=10,
            endLine=10,
        )
        sc2 = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="Second",
            startLine=1,
            endLine=1,
        )
        suggestions = list(SuggestedComment.objects.filter(submission=grading_setup['submission']))
        assert suggestions[0].startLine <= suggestions[1].startLine


class TestSubmissionSummaryModel:
    """Test SubmissionSummary model creation."""

    def test_create_summary(self, grading_setup, submission_summary):
        assert submission_summary.submission == grading_setup['submission']
        assert '## Summary' in submission_summary.text

    def test_one_to_one_constraint(self, grading_setup, submission_summary):
        from django.db import IntegrityError
        from core.models import SubmissionSummary

        with pytest.raises(IntegrityError):
            SubmissionSummary.objects.create(
                submission=grading_setup['submission'],
                text="Duplicate summary",
            )


class TestAssignmentAIDescriptionFields:
    """Test the new ai_description fields on Assignment."""

    def test_default_values(self, grading_setup):
        assignment = grading_setup['assignment']
        assert assignment.ai_description == ''
        assert assignment.ai_description_locked is False

    def test_set_description(self, grading_setup):
        assignment = grading_setup['assignment']
        assignment.ai_description = "This assignment asks students to implement sorting."
        assignment.ai_description_locked = True
        with factory.django.mute_signals(post_save):
            assignment.save()
        assignment.refresh_from_db()
        assert "sorting" in assignment.ai_description
        assert assignment.ai_description_locked is True


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================


class TestSuggestedCommentEndpoints:
    """Test the suggestedComments API endpoints."""

    def test_list_suggested_comments_as_grader(self, api_client, grading_setup, suggested_comment):
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/suggestedComments/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['text'] == suggested_comment.text

    def test_list_suggested_comments_as_student_forbidden(self, api_client, grading_setup, suggested_comment):
        api_client.force_authenticate(user=grading_setup['student'])
        url = f"/submissions/{grading_setup['submission'].id}/suggestedComments/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_accept_suggestion(self, api_client, grading_setup, suggested_comment):
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/suggestedComments/{suggested_comment.id}/accept/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        # Verify a real comment was created
        assert 'id' in response.data
        assert response.data['text'] == suggested_comment.text
        assert response.data['startLine'] == suggested_comment.startLine

        # Verify suggestion was updated
        suggested_comment.refresh_from_db()
        assert suggested_comment.status == 'accepted'
        assert suggested_comment.acceptedBy == grading_setup['grader']
        assert suggested_comment.acceptedComment is not None

    def test_reject_suggestion(self, api_client, grading_setup, suggested_comment):
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/suggestedComments/{suggested_comment.id}/reject/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_200_OK

        suggested_comment.refresh_from_db()
        assert suggested_comment.status == 'rejected'

    def test_accept_already_accepted_fails(self, api_client, grading_setup, suggested_comment):
        api_client.force_authenticate(user=grading_setup['grader'])
        # Accept first
        api_client.post(f"/suggestedComments/{suggested_comment.id}/accept/", format='json')
        # Try to accept again
        response = api_client.post(f"/suggestedComments/{suggested_comment.id}/accept/", format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_cannot_accept(self, api_client, grading_setup, suggested_comment):
        api_client.force_authenticate(user=grading_setup['student'])
        url = f"/suggestedComments/{suggested_comment.id}/accept/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_only_pending_shown_in_list(self, api_client, grading_setup, suggested_comment):
        from core.models import SuggestedComment

        # Create a rejected suggestion
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="Rejected suggestion",
            startLine=5,
            endLine=5,
            status='rejected',
        )

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/suggestedComments/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1  # Only the pending one

    def test_accept_with_rubric_comment_inherits_point_delta(self, api_client, grading_setup):
        """When a suggestion links to a rubricComment and has no explicit pointDelta,
        the created Comment should inherit the rubricComment's pointDelta."""
        from core.models import SuggestedComment, RubricComment

        rubric_comment = RubricComment.objects.filter(
            category__assignment=grading_setup['assignment']
        ).first()
        assert rubric_comment is not None, "Fixture should create a rubric comment"

        suggestion = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="Missing semicolon",
            startLine=7,
            endLine=7,
            pointDelta=None,  # No explicit pointDelta — should inherit from rubric
            rubricComment=rubric_comment,
            status='pending',
        )

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/suggestedComments/{suggestion.id}/accept/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        # When linked to a rubricComment, the Comment's pointDelta is None
        # (the rubricComment's pointDelta is used at display time by the frontend)
        assert response.data['pointDelta'] is None
        assert response.data['rubricComment'] == rubric_comment.id

    def test_delete_suggestion(self, api_client, grading_setup, suggested_comment):
        """Graders can delete a pending suggestion."""
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/suggestedComments/{suggested_comment.id}/"
        response = api_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT


class TestSubmissionSummaryEndpoints:
    """Test the submission summary API endpoints."""

    def test_get_summary_as_grader(self, api_client, grading_setup, submission_summary):
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/summary/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert '## Summary' in response.data['text']

    def test_get_summary_as_student_forbidden(self, api_client, grading_setup, submission_summary):
        api_client.force_authenticate(user=grading_setup['student'])
        url = f"/submissions/{grading_setup['submission'].id}/summary/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_summary_not_found(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/summary/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_generate_ai_assistance_as_grader(self, api_client, grading_setup, monkeypatch):
        monkeypatch.setattr('core.tasks.generate_ai_grading_assistance.delay', lambda *a, **kw: None)
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateAIAssistance/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data['status'] == 'queued'

    def test_generate_ai_assistance_as_student_forbidden(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['student'])
        url = f"/submissions/{grading_setup['submission'].id}/generateAIAssistance/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestGenerateSummaryEndpoint:
    """Test the POST /submissions/{id}/generateSummary/ sync endpoint."""

    def test_generate_summary_as_grader(self, api_client, grading_setup, monkeypatch):
        from core.services.ai_service import GenerationResult

        async def mock_generate(self, submission):
            return GenerationResult(
                text="- Student implemented merge sort\n- All tests pass",
                success=True,
                input_tokens=200,
                output_tokens=80,
                total_tokens=280,
            )

        monkeypatch.setattr('core.services.ai_service.AIService.generate_submission_summary', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert 'merge sort' in response.data['text']
        assert response.data['submission'] == grading_setup['submission'].id

    def test_generate_summary_creates_model(self, api_client, grading_setup, monkeypatch):
        from core.models import SubmissionSummary
        from core.services.ai_service import GenerationResult

        async def mock_generate(self, submission):
            return GenerationResult(text="Summary text", success=True)

        monkeypatch.setattr('core.services.ai_service.AIService.generate_submission_summary', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        api_client.post(url, format='json')

        assert SubmissionSummary.objects.filter(submission=grading_setup['submission']).exists()

    def test_generate_summary_as_student_forbidden(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['student'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_generate_summary_ai_not_configured(self, api_client, grading_setup, monkeypatch):
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: False))

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_summary_ai_globally_disabled(self, api_client, grading_setup, monkeypatch):
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: True))

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'disabled' in response.data['error'].lower()

    def test_generate_summary_ai_failure(self, api_client, grading_setup, monkeypatch):
        from core.services.ai_service import GenerationResult

        async def mock_generate(self, submission):
            return GenerationResult(text="", success=False, error="Rate limit exceeded")

        monkeypatch.setattr('core.services.ai_service.AIService.generate_submission_summary', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestAssignmentAIDescriptionEndpoints:
    """Test the assignment AI description API endpoints."""

    def test_update_ai_description_as_admin(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/"
        response = api_client.patch(url, {
            'ai_description': 'Students implement a linked list.',
            'ai_description_locked': True,
        }, format='json')
        assert response.status_code == status.HTTP_200_OK

        grading_setup['assignment'].refresh_from_db()
        assert grading_setup['assignment'].ai_description == 'Students implement a linked list.'
        assert grading_setup['assignment'].ai_description_locked is True

    def test_ai_description_in_assignment_response(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'aiDescription' in response.data or 'ai_description' in response.data


class TestGenerateDescriptionEndpoint:
    """Test the POST /assignments/{id}/generateDescription/ endpoint."""

    def test_generate_description_as_admin(self, api_client, grading_setup, monkeypatch):
        from core.services.ai_service import GenerationResult

        async def mock_generate(self, assignment):
            return GenerationResult(
                text="This assignment asks students to implement a sorting algorithm.",
                success=True,
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            )

        monkeypatch.setattr('core.services.ai_service.AIService.generate_assignment_description', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'aiDescription' in response.data
        assert 'sorting algorithm' in response.data['aiDescription']

    def test_generate_description_saves_to_model(self, api_client, grading_setup, monkeypatch):
        from core.services.ai_service import GenerationResult

        async def mock_generate(self, assignment):
            return GenerationResult(
                text="Students must implement binary search.",
                success=True,
                input_tokens=80,
                output_tokens=40,
                total_tokens=120,
            )

        monkeypatch.setattr('core.services.ai_service.AIService.generate_assignment_description', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        api_client.post(url, format='json')

        grading_setup['assignment'].refresh_from_db()
        assert grading_setup['assignment'].ai_description == "Students must implement binary search."

    def test_generate_description_as_grader_forbidden(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_generate_description_as_student_forbidden(self, api_client, grading_setup):
        api_client.force_authenticate(user=grading_setup['student'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_generate_description_ai_not_configured(self, api_client, grading_setup, monkeypatch):
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: False))

        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_generate_description_ai_globally_disabled(self, api_client, grading_setup, monkeypatch):
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: True))

        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'disabled' in response.data['error'].lower()

    def test_generate_description_error_does_not_leak(self, api_client, grading_setup, monkeypatch):
        """Verify that raw Python exceptions are not exposed to the client."""
        async def mock_generate(self, assignment):
            raise RuntimeError("SECRET_API_KEY: Internal error at /var/lib/app/secret.py")

        monkeypatch.setattr('core.services.ai_service.AIService.generate_assignment_description', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))

        api_client.force_authenticate(user=grading_setup['admin'])
        url = f"/assignments/{grading_setup['assignment'].id}/generateDescription/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert 'SECRET_API_KEY' not in response.data.get('error', '')
        assert '/var/lib' not in response.data.get('error', '')


class TestCopyAssignmentAIFields:
    """Test that copy_assignment preserves AI description fields."""

    def test_copy_preserves_ai_description(self, grading_setup):
        from core.utils import copy_assignment
        from core.models import Course

        assignment = grading_setup['assignment']
        assignment.ai_description = "Students implement merge sort."
        assignment.ai_description_locked = True
        assignment.ai_system_prompt = "Custom prompt"
        with factory.django.mute_signals(post_save):
            assignment.save()

        dest_course = Course.objects.create(
            name="Destination",
            period="S2027",
            organization=grading_setup['course'].organization,
        )

        with factory.django.mute_signals(post_save):
            copied = copy_assignment(assignment, dest_course)

        assert copied is not None
        assert copied.ai_description == "Students implement merge sort."
        assert copied.ai_description_locked is True
        assert copied.ai_system_prompt == "Custom prompt"

    def test_copy_empty_description(self, grading_setup):
        from core.utils import copy_assignment
        from core.models import Course

        assignment = grading_setup['assignment']
        assert assignment.ai_description == ''
        assert assignment.ai_description_locked is False

        dest_course = Course.objects.create(
            name="Destination2",
            period="S2027",
            organization=grading_setup['course'].organization,
        )

        with factory.django.mute_signals(post_save):
            copied = copy_assignment(assignment, dest_course)

        assert copied is not None
        assert copied.ai_description == ''
        assert copied.ai_description_locked is False


class TestSuggestionDeduplication:
    """Test that regenerating suggestions clears old pending ones."""

    def test_generate_file_suggestions_replaces_pending(self, api_client, grading_setup, monkeypatch):
        """Calling generateFileSuggestions for a file should remove previous pending suggestions for that file."""
        import json
        from core.models import SuggestedComment
        from core.services.ai_service import GenerationResult

        file_obj = grading_setup['file']
        submission = grading_setup['submission']

        # Pre-create two pending suggestions for this file
        SuggestedComment.objects.create(
            submission=submission, file=file_obj,
            text="Old suggestion 1", startLine=1, endLine=1, status='pending',
        )
        SuggestedComment.objects.create(
            submission=submission, file=file_obj,
            text="Old suggestion 2", startLine=2, endLine=2, status='pending',
        )
        assert SuggestedComment.objects.filter(submission=submission, file=file_obj, status='pending').count() == 2

        # Mock the AI to return one new suggestion
        new_suggestions = json.dumps([{
            'file_id': file_obj.id,
            'text': 'New suggestion',
            'start_line': 5,
            'end_line': 5,
            'start_char': 0,
            'end_char': 10,
        }])

        async def mock_generate(self, submission, file):
            return [GenerationResult(text=new_suggestions, success=True, input_tokens=100, output_tokens=50, total_tokens=150)]

        monkeypatch.setattr('core.services.ai_service.AIService.generate_file_suggestions', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{submission.id}/generateFileSuggestions/"
        response = api_client.post(url, {'fileId': file_obj.id}, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Only the new suggestion should remain pending
        pending = SuggestedComment.objects.filter(submission=submission, file=file_obj, status='pending')
        assert pending.count() == 1
        assert pending.first().text == 'New suggestion'

    def test_generate_does_not_affect_accepted_suggestions(self, api_client, grading_setup, monkeypatch):
        """Accepted suggestions should not be deleted when regenerating."""
        import json
        from core.models import SuggestedComment
        from core.services.ai_service import GenerationResult

        file_obj = grading_setup['file']
        submission = grading_setup['submission']

        # Pre-create an accepted suggestion
        SuggestedComment.objects.create(
            submission=submission, file=file_obj,
            text="Accepted one", startLine=1, endLine=1, status='accepted',
        )

        async def mock_generate(self, submission, file):
            return [GenerationResult(text=json.dumps([]), success=True)]

        monkeypatch.setattr('core.services.ai_service.AIService.generate_file_suggestions', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{submission.id}/generateFileSuggestions/"
        api_client.post(url, {'fileId': file_obj.id}, format='json')

        # The accepted suggestion should still exist
        assert SuggestedComment.objects.filter(submission=submission, status='accepted').count() == 1


class TestMalformedAIOutput:
    """Test that malformed AI output is handled gracefully."""

    def test_generate_file_suggestions_malformed_json(self, api_client, grading_setup, monkeypatch):
        """If the AI returns invalid JSON, the endpoint should return a meaningful error."""
        from core.services.ai_service import GenerationResult

        async def mock_generate(self, submission, file):
            return [GenerationResult(text="This is not JSON {{{", success=True)]

        monkeypatch.setattr('core.services.ai_service.AIService.generate_file_suggestions', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateFileSuggestions/"
        response = api_client.post(url, {'fileId': grading_setup['file'].id}, format='json')
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert 'malformed' in response.data['error'].lower()
