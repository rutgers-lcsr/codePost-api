# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""Tests for the Behavioral Feedback system: prompt variant tracking on suggestions,
generation batches, first_viewed_at stamping, regeneration counting, behavioral
metrics aggregation, and auto-promotion gates."""

import json
import uuid

import factory
import pytest
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.utils import timezone
from rest_framework import status

from core.services.ai_service import GenerationResult


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def grading_setup(db):
    """Course with assignment, submission, file, grader, student, admin."""
    from core.tests.factories import CourseFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos226", period="s2026", organization__name="Princeton")

    assignment = course.assignments.first()
    submission = assignment.submissions.first()
    file = submission.files.first()
    grader = course.graders.first()
    student = course.students.first()
    admin = course.courseAdmins.first()

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
def superuser(db):
    """A superuser for prompt experiment management."""
    return User.objects.create_superuser(
        username='superadmin', email='super@test.com', password='test',
    )


@pytest.fixture
def prompt_variants(db):
    """Two SystemPromptVariant instances for A/B testing."""
    from core.models import SystemPromptVariant

    # Retire any existing active variant to avoid unique constraint violation
    SystemPromptVariant.objects.filter(
        prompt_type='suggested_comments', status='active',
    ).update(status='retired')

    variant_a = SystemPromptVariant.objects.create(
        prompt_type='suggested_comments',
        name='Control Prompt',
        text='You are a helpful grader. {assignment_name}',
        status='active',
        version=1,
    )
    variant_b = SystemPromptVariant.objects.create(
        prompt_type='suggested_comments',
        name='Challenger Prompt',
        text='You are a concise grader. {assignment_name}',
        status='candidate',
        version=2,
    )
    return {'a': variant_a, 'b': variant_b}


@pytest.fixture
def experiment(prompt_variants, superuser):
    """A running PromptExperiment comparing variant A and B."""
    from core.models import PromptExperiment

    return PromptExperiment.objects.create(
        name='Suggested Comments Test',
        prompt_type='suggested_comments',
        variant_a=prompt_variants['a'],
        variant_b=prompt_variants['b'],
        status='running',
        sample_rate=0.5,
        started_by=superuser,
    )


# =============================================================================
# PHASE 1: DATA INTEGRITY — NEW FIELDS ON SUGGESTED COMMENT
# =============================================================================


class TestSuggestedCommentNewFields:
    """Verify prompt_variant FK, generation_batch UUID, and first_viewed_at are set correctly."""

    def test_generate_file_suggestions_populates_prompt_variant_and_batch(
        self, api_client, grading_setup, prompt_variants, monkeypatch,
    ):
        """generateFileSuggestions should set promptVariant and generationBatch on created suggestions."""
        from core.models import SuggestedComment

        file_obj = grading_setup['file']
        variant = prompt_variants['a']

        suggestions_json = json.dumps([{
            'file_id': file_obj.id,
            'text': 'Use clearer variable names.',
            'start_line': 3, 'end_line': 3,
            'start_char': 0, 'end_char': 20,
        }, {
            'file_id': file_obj.id,
            'text': 'Add docstring.',
            'start_line': 1, 'end_line': 1,
            'start_char': 0, 'end_char': 5,
        }])

        async def mock_generate(self, submission, file, variant_id_override=None):
            return [GenerationResult(
                text=suggestions_json, success=True,
                input_tokens=100, output_tokens=50, total_tokens=150,
                variant_id=variant.id,
            )]

        monkeypatch.setattr('core.services.ai_service.AIService.generate_file_suggestions', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)
        monkeypatch.setattr('core.services.ai_service.AIService.check_experiment', lambda pt: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateFileSuggestions/"
        response = api_client.post(url, {'fileId': file_obj.id}, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        pending = SuggestedComment.objects.filter(
            submission=grading_setup['submission'], file=file_obj, status='pending',
        )
        assert pending.count() == 2

        # All suggestions should share the same batch UUID and variant FK
        batch_ids = set(pending.values_list('generationBatch', flat=True))
        assert len(batch_ids) == 1
        assert batch_ids.pop() is not None  # UUID should be set

        for sc in pending:
            assert sc.promptVariant_id == variant.id

    def test_first_viewed_at_null_on_creation(self, grading_setup):
        """Newly created suggestions should have firstViewedAt=None."""
        from core.models import SuggestedComment

        sc = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="test",
            startLine=1, endLine=1,
        )
        assert sc.firstViewedAt is None

    def test_list_suggestions_stamps_first_viewed_at(self, api_client, grading_setup):
        """Fetching suggestions via the list endpoint should stamp firstViewedAt."""
        from core.models import SuggestedComment

        sc = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="test",
            startLine=1, endLine=1,
            status='pending',
        )
        assert sc.firstViewedAt is None

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/suggestedComments/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        sc.refresh_from_db()
        assert sc.firstViewedAt is not None

    def test_first_viewed_at_not_overwritten_on_second_fetch(self, api_client, grading_setup):
        """Second fetch should not overwrite the original firstViewedAt timestamp."""
        from core.models import SuggestedComment

        sc = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="test",
            startLine=1, endLine=1,
            status='pending',
        )

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/suggestedComments/"

        # First fetch
        api_client.get(url)
        sc.refresh_from_db()
        first_viewed = sc.firstViewedAt
        assert first_viewed is not None

        # Second fetch
        api_client.get(url)
        sc.refresh_from_db()
        assert sc.firstViewedAt == first_viewed  # Should not change

    def test_serializer_exposes_new_fields(self, api_client, grading_setup, prompt_variants):
        """The SuggestedComment serializer should include the new fields."""
        from core.models import SuggestedComment

        sc = SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="test",
            startLine=1, endLine=1,
            status='pending',
            promptVariant=prompt_variants['a'],
            generationBatch=uuid.uuid4(),
        )

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/suggestedComments/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data[0]
        assert 'promptVariant' in data
        assert 'generationBatch' in data
        assert 'firstViewedAt' in data
        assert data['promptVariant'] == prompt_variants['a'].id


# =============================================================================
# PHASE 2: REGENERATION TRACKING ON SUBMISSION SUMMARY
# =============================================================================


class TestRegenerationCount:
    """Verify regeneration_count increments on summary regeneration."""

    def test_first_generation_has_zero_count(self, api_client, grading_setup, monkeypatch):
        from core.models import SubmissionSummary

        async def mock_generate(self, submission, variant_id_override=None):
            return GenerationResult(text="First summary", success=True)

        monkeypatch.setattr('core.services.ai_service.AIService.generate_submission_summary', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)
        monkeypatch.setattr('core.services.ai_service.AIService.check_experiment', lambda pt: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        summary = SubmissionSummary.objects.get(submission=grading_setup['submission'])
        assert summary.regenerationCount == 0

    def test_regeneration_increments_count(self, api_client, grading_setup, monkeypatch):
        from core.models import SubmissionSummary

        call_count = {'n': 0}

        async def mock_generate(self, submission, variant_id_override=None):
            call_count['n'] += 1
            return GenerationResult(text=f"Summary v{call_count['n']}", success=True)

        monkeypatch.setattr('core.services.ai_service.AIService.generate_submission_summary', mock_generate)
        monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
        monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))
        monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)
        monkeypatch.setattr('core.services.ai_service.AIService.check_experiment', lambda pt: None)

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/generateSummary/"

        # Generate first time
        api_client.post(url, format='json')
        summary = SubmissionSummary.objects.get(submission=grading_setup['submission'])
        assert summary.regenerationCount == 0

        # Regenerate
        api_client.post(url, format='json')
        summary.refresh_from_db()
        assert summary.regenerationCount == 1

        # Regenerate again
        api_client.post(url, format='json')
        summary.refresh_from_db()
        assert summary.regenerationCount == 2

    def test_regeneration_count_in_serializer(self, api_client, grading_setup):
        from core.models import SubmissionSummary

        SubmissionSummary.objects.create(
            submission=grading_setup['submission'],
            text="Summary",
            regenerationCount=3,
        )

        api_client.force_authenticate(user=grading_setup['grader'])
        url = f"/submissions/{grading_setup['submission'].id}/summary/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['regenerationCount'] == 3


# =============================================================================
# PHASE 3: BEHAVIORAL METRICS AGGREGATION
# =============================================================================


class TestBehavioralMetrics:
    """Test the behavioral metrics in the experiment results endpoint."""

    def _create_suggestions(self, grading_setup, variant, count=5, batch_id=None, status='pending'):
        """Helper to create SuggestedComment records for a variant."""
        from core.models import SuggestedComment

        batch = batch_id or uuid.uuid4()
        suggestions = []
        for i in range(count):
            suggestions.append(SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"Suggestion {i} from {variant.name}",
                startLine=i + 1, endLine=i + 1,
                status=status,
                promptVariant=variant,
                generationBatch=batch,
                firstViewedAt=timezone.now() if status != 'pending' else None,
            ))
        return suggestions

    def test_results_include_behavioral_section(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """The results endpoint should return a 'behavioral' key."""
        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/results/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert 'behavioral' in response.data

        behavioral = response.data['behavioral']
        assert 'variantA' in behavioral
        assert 'variantB' in behavioral
        assert 'variantAConfident' in behavioral
        assert 'variantBConfident' in behavioral

    def test_empty_behavioral_data(
        self, api_client, superuser, experiment,
    ):
        """When no suggestions exist, all rates should be null."""
        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/results/"
        response = api_client.get(url)

        behavioral = response.data['behavioral']
        assert behavioral['variantA']['total'] == 0
        assert behavioral['variantA']['acceptanceRate'] is None
        assert behavioral['variantAConfident'] is False

    def test_acceptance_rate_calculation(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """Acceptance rate should be computed correctly from accepted/rejected suggestions."""
        from core.models import SuggestedComment

        variant_a = prompt_variants['a']
        batch = uuid.uuid4()
        now = timezone.now()

        # Create 4 suggestions for variant A: 3 accepted, 1 rejected
        for i in range(3):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"Accepted {i}",
                startLine=i + 1, endLine=i + 1,
                status='accepted',
                promptVariant=variant_a,
                generationBatch=batch,
                firstViewedAt=now,
            )
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="Rejected",
            startLine=4, endLine=4,
            status='rejected',
            promptVariant=variant_a,
            generationBatch=batch,
            firstViewedAt=now,
        )

        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/results/"
        response = api_client.get(url)
        behavioral = response.data['behavioral']

        assert behavioral['variantA']['total'] == 4
        assert behavioral['variantA']['accepted'] == 3
        assert behavioral['variantA']['rejected'] == 1
        assert behavioral['variantA']['acceptanceRate'] == 0.75  # 3/4

    def test_edit_rate_detection(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """Edit rate should detect when accepted suggestion text differs from the resulting comment text."""
        from core.models import SuggestedComment, Comment

        variant_a = prompt_variants['a']
        now = timezone.now()

        # Accepted suggestion where grader kept the text
        comment_unchanged = Comment.objects.create(
            text="Unchanged text",
            author=grading_setup['grader'],
            file=grading_setup['file'],
            startLine=1, endLine=1,
            startChar=0, endChar=0,
        )
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="Unchanged text",
            startLine=1, endLine=1,
            status='accepted',
            promptVariant=variant_a,
            acceptedComment=comment_unchanged,
            acceptedBy=grading_setup['grader'],
            firstViewedAt=now,
        )

        # Accepted suggestion where grader edited the text
        comment_edited = Comment.objects.create(
            text="Edited by grader",
            author=grading_setup['grader'],
            file=grading_setup['file'],
            startLine=2, endLine=2,
            startChar=0, endChar=0,
        )
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="Original AI text",
            startLine=2, endLine=2,
            status='accepted',
            promptVariant=variant_a,
            acceptedComment=comment_edited,
            acceptedBy=grading_setup['grader'],
            firstViewedAt=now,
        )

        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/results/"
        response = api_client.get(url)

        # 1 of 2 accepted was edited → edit rate = 0.5
        assert response.data['behavioral']['variantA']['editRate'] == 0.5

    def test_confidence_thresholds(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """Confidence should be False when below the minimum sample threshold."""
        self._create_suggestions(grading_setup, prompt_variants['a'], count=5, status='accepted')

        api_client.force_authenticate(user=superuser)
        # Default threshold is 30 — 5 suggestions should be insufficient
        url = f"/promptExperiments/{experiment.id}/results/"
        response = api_client.get(url)
        assert response.data['behavioral']['variantAConfident'] is False

        # With a lower threshold, it should be confident
        url = f"/promptExperiments/{experiment.id}/results/?minSamplesPerVariant=3"
        response = api_client.get(url)
        assert response.data['behavioral']['variantAConfident'] is True

    def test_distinct_assignments_threshold(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """Confidence should require suggestions from multiple assignments."""
        # All suggestions are from the same assignment
        self._create_suggestions(grading_setup, prompt_variants['a'], count=40, status='accepted')

        api_client.force_authenticate(user=superuser)
        # With minAssignments=2, one assignment is not enough
        url = f"/promptExperiments/{experiment.id}/results/?minSamplesPerVariant=5&minAssignments=2"
        response = api_client.get(url)
        assert response.data['behavioral']['variantAConfident'] is False

        # With minAssignments=1, it should be confident
        url = f"/promptExperiments/{experiment.id}/results/?minSamplesPerVariant=5&minAssignments=1"
        response = api_client.get(url)
        assert response.data['behavioral']['variantAConfident'] is True

    def test_batch_acceptance_rate(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """Batch acceptance rate should average across batches."""
        from core.models import SuggestedComment

        variant = prompt_variants['a']
        now = timezone.now()

        # Batch 1: 2 of 3 accepted
        batch1 = uuid.uuid4()
        for i in range(2):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"B1 acc {i}", startLine=i, endLine=i,
                status='accepted', promptVariant=variant, generationBatch=batch1,
                firstViewedAt=now,
            )
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="B1 rej", startLine=3, endLine=3,
            status='rejected', promptVariant=variant, generationBatch=batch1,
            firstViewedAt=now,
        )

        # Batch 2: 1 of 2 accepted
        batch2 = uuid.uuid4()
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="B2 acc", startLine=5, endLine=5,
            status='accepted', promptVariant=variant, generationBatch=batch2,
            firstViewedAt=now,
        )
        SuggestedComment.objects.create(
            submission=grading_setup['submission'],
            file=grading_setup['file'],
            text="B2 rej", startLine=6, endLine=6,
            status='rejected', promptVariant=variant, generationBatch=batch2,
            firstViewedAt=now,
        )

        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/results/"
        response = api_client.get(url)

        # Batch 1 rate = 2/3 ≈ 0.6667, Batch 2 rate = 1/2 = 0.5
        # Average ≈ 0.5833
        batch_rate = response.data['behavioral']['batchAcceptanceRateA']
        assert batch_rate is not None
        assert abs(batch_rate - 0.5833) < 0.01


# =============================================================================
# PHASE 4: AUTO-PROMOTION WITH BEHAVIORAL GATES
# =============================================================================


class TestAutoPromotionGates:
    """Test that the complete action uses behavioral data to gate promotion."""

    def test_complete_promotes_when_both_agree(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """When explicit and behavioral both favor the same variant, promotion should succeed."""
        from core.models import PromptFeedback, SuggestedComment, SystemPromptVariant

        variant_a = prompt_variants['a']
        variant_b = prompt_variants['b']
        now = timezone.now()

        # Explicit feedback: A wins (3 vs 1)
        for _ in range(3):
            PromptFeedback.objects.create(
                experiment=experiment, variant_used=variant_a,
                chosen_variant=variant_a, user=superuser, rating=1,
                prompt_type='suggested_comments',
            )
        PromptFeedback.objects.create(
            experiment=experiment, variant_used=variant_b,
            chosen_variant=variant_b, user=superuser, rating=1,
            prompt_type='suggested_comments',
        )

        # Behavioral: A also has higher acceptance (40 suggestions, all accepted)
        batch = uuid.uuid4()
        for i in range(40):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"A-{i}", startLine=i, endLine=i,
                status='accepted', promptVariant=variant_a, generationBatch=batch,
                firstViewedAt=now,
            )
        # B: only 10 of 40 accepted
        batch_b = uuid.uuid4()
        for i in range(10):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"B-acc-{i}", startLine=50 + i, endLine=50 + i,
                status='accepted', promptVariant=variant_b, generationBatch=batch_b,
                firstViewedAt=now,
            )
        for i in range(30):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"B-rej-{i}", startLine=60 + i, endLine=60 + i,
                status='rejected', promptVariant=variant_b, generationBatch=batch_b,
                firstViewedAt=now,
            )

        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/complete/?promoteWinner=true"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get('promotedVariant') == variant_a.id

        # Variant A should now be active
        variant_a.refresh_from_db()
        assert variant_a.status == 'active'

    def test_complete_blocks_when_disagreement(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """When explicit and behavioral disagree, promotion should be blocked with a warning."""
        from core.models import PromptFeedback, SuggestedComment

        variant_a = prompt_variants['a']
        variant_b = prompt_variants['b']
        now = timezone.now()

        # Explicit feedback: A wins
        for _ in range(3):
            PromptFeedback.objects.create(
                experiment=experiment, variant_used=variant_a,
                chosen_variant=variant_a, user=superuser, rating=1,
                prompt_type='suggested_comments',
            )
        PromptFeedback.objects.create(
            experiment=experiment, variant_used=variant_b,
            chosen_variant=variant_b, user=superuser, rating=1,
            prompt_type='suggested_comments',
        )

        # Behavioral: B has higher acceptance rate (40 accepted out of 40)
        batch_b = uuid.uuid4()
        for i in range(40):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"B-{i}", startLine=i, endLine=i,
                status='accepted', promptVariant=variant_b, generationBatch=batch_b,
                firstViewedAt=now,
            )
        # A: only 10 of 40 accepted
        batch_a = uuid.uuid4()
        for i in range(10):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"A-acc-{i}", startLine=50 + i, endLine=50 + i,
                status='accepted', promptVariant=variant_a, generationBatch=batch_a,
                firstViewedAt=now,
            )
        for i in range(30):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"A-rej-{i}", startLine=60 + i, endLine=60 + i,
                status='rejected', promptVariant=variant_a, generationBatch=batch_a,
                firstViewedAt=now,
            )

        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/complete/?promoteWinner=true"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_200_OK

        # Promotion should be blocked
        assert 'promotedVariant' not in response.data
        assert 'promotionWarning' in response.data
        assert 'disagree' in response.data['promotionWarning'].lower()

    def test_complete_warns_on_low_confidence(
        self, api_client, superuser, experiment, grading_setup, prompt_variants,
    ):
        """With insufficient behavioral data, promotion should proceed with a low-confidence warning."""
        from core.models import PromptFeedback, SuggestedComment

        variant_a = prompt_variants['a']
        variant_b = prompt_variants['b']

        # Explicit feedback: A wins
        for _ in range(3):
            PromptFeedback.objects.create(
                experiment=experiment, variant_used=variant_a,
                chosen_variant=variant_a, user=superuser, rating=1,
                prompt_type='suggested_comments',
            )
        PromptFeedback.objects.create(
            experiment=experiment, variant_used=variant_b,
            chosen_variant=variant_b, user=superuser, rating=1,
            prompt_type='suggested_comments',
        )

        # Only 5 suggestions for variant A (below default threshold of 30)
        for i in range(5):
            SuggestedComment.objects.create(
                submission=grading_setup['submission'],
                file=grading_setup['file'],
                text=f"A-{i}", startLine=i, endLine=i,
                status='accepted', promptVariant=variant_a,
            )

        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/complete/?promoteWinner=true"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_200_OK

        # Should still promote (behavioral data insufficient, falls through)
        assert response.data.get('promotedVariant') == variant_a.id
        assert 'promotionWarning' in response.data
        assert 'insufficient' in response.data['promotionWarning'].lower()

    def test_complete_without_promote_flag(
        self, api_client, superuser, experiment,
    ):
        """Completing without promoteWinner should not promote anything."""
        api_client.force_authenticate(user=superuser)
        url = f"/promptExperiments/{experiment.id}/complete/"
        response = api_client.post(url, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'promotedVariant' not in response.data
        assert 'promotionWarning' not in response.data


# =============================================================================
# PHASE 1: record_usage() FIX
# =============================================================================


class TestRecordUsagePopulatesVariant:
    """Test that AIService.record_usage() now populates prompt_variant and experiment."""

    def test_record_usage_sets_prompt_variant(self, grading_setup, prompt_variants):
        from core.models import AIUsageRecord
        from core.services.ai_service import AIService

        course = grading_setup['course']
        assignment = grading_setup['assignment']
        variant = prompt_variants['a']

        # Configure the course with a provider so AIService can init
        with factory.django.mute_signals(post_save):
            course.organization.ai_provider = 'gemini'
            course.organization.ai_api_key = 'test-key'
            course.organization.save()

        service = AIService(course, assignment)
        result = GenerationResult(
            text="test", success=True,
            input_tokens=10, output_tokens=5, total_tokens=15,
            variant_id=variant.id,
        )

        service.record_usage(result, grading_setup['grader'], request_type='suggested_comments')

        record = AIUsageRecord.objects.last()
        assert record is not None
        assert record.prompt_variant_id == variant.id

    def test_record_usage_sets_experiment(self, grading_setup, prompt_variants, experiment):
        from core.models import AIUsageRecord
        from core.services.ai_service import AIService

        course = grading_setup['course']
        assignment = grading_setup['assignment']

        with factory.django.mute_signals(post_save):
            course.organization.ai_provider = 'gemini'
            course.organization.ai_api_key = 'test-key'
            course.organization.save()

        service = AIService(course, assignment)
        result = GenerationResult(
            text="test", success=True,
            input_tokens=10, output_tokens=5, total_tokens=15,
            variant_id=prompt_variants['a'].id,
        )

        service.record_usage(result, grading_setup['grader'], experiment=experiment)

        record = AIUsageRecord.objects.last()
        assert record is not None
        assert record.experiment_id == experiment.id

    def test_record_usage_null_variant_when_no_variant_id(self, grading_setup):
        from core.models import AIUsageRecord
        from core.services.ai_service import AIService

        course = grading_setup['course']
        assignment = grading_setup['assignment']

        with factory.django.mute_signals(post_save):
            course.organization.ai_provider = 'gemini'
            course.organization.ai_api_key = 'test-key'
            course.organization.save()

        service = AIService(course, assignment)
        result = GenerationResult(text="test", success=True, variant_id=None)

        service.record_usage(result, grading_setup['grader'])

        record = AIUsageRecord.objects.last()
        assert record is not None
        assert record.prompt_variant is None
        assert record.experiment is None
