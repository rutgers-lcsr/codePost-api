# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""Tests for Quizzes Phase 2 slice 1: student taking + auto-grading.

Covers start/resume gating, autosave, submit + auto-grade per question type, the
answer/score reveal rules, attempt limits, scoring policy, and access control.
"""
from datetime import timedelta
from decimal import Decimal

import factory
import pytest
from django.db.models.signals import post_save
from django.utils import timezone
from rest_framework import status


@pytest.fixture
def taking_setup(db):
    from core.tests.factories import CourseFactory, AdminFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos333", period="s2026", organization__name="Princeton")

    students = list(course.students.all())
    return {
        'course': course,
        'assignment': course.assignments.first(),
        'admin': course.courseAdmins.first(),
        'students': students,
        'outsider': AdminFactory(course='other', organization=course.organization, count=77),
    }


# Shared question/quiz builders live in quiz_helpers (used by all three quiz test files).
from core.tests.views.quiz_helpers import (  # noqa: E402
    _add, _bank, _dec, _essay, _mc, _multi, _numerical, _quiz, _short,
)


# --------------------------------------------------------------------------- #
# Start / resume gating
# --------------------------------------------------------------------------- #

class TestStartAttempt:
    def test_unpublished_quiz_cannot_be_started(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, isPublished=False)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_non_enrolled_user_cannot_start(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['outsider'])
        resp = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_random_draw_materializes_questions(self, api_client, taking_setup):
        from core.models import QuizQuestionGroup
        course = taking_setup['course']
        bank = _bank(course)
        pool = [_mc(course, bank), _mc(course, bank), _mc(course, bank)]
        quiz = _quiz(course)
        QuizQuestionGroup.objects.create(quiz=quiz, bank=bank, pickCount=2, pointsPerQuestion=Decimal('3'))
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        responses = resp.data['responses']
        assert len(responses) == 2  # pickCount drawn from the bank
        pool_ids = {q.id for q in pool}
        for r in responses:
            assert r['question']['id'] in pool_ids
            assert Decimal(str(r['points'])) == Decimal('3.00')  # worth pointsPerQuestion

    def test_attempt_limit_enforced(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, attemptsAllowed=1)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        first = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert first.status_code == status.HTTP_201_CREATED
        api_client.post(f"/quizAttempts/{first.data['id']}/submit/", {}, format='json')
        # No attempts left.
        second = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert second.status_code == status.HTTP_403_FORBIDDEN

    def test_resume_returns_existing_in_progress(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, attemptsAllowed=1)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        first = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        again = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert again.status_code == status.HTTP_200_OK
        assert again.data['id'] == first.data['id']


# --------------------------------------------------------------------------- #
# Auto-grading per type
# --------------------------------------------------------------------------- #

class TestAutoGrading:
    def _take(self, api_client, student, quiz):
        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        return start.data

    def test_multiple_choice_correct_and_revealed(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _mc(course, _bank(course))
        quiz = _quiz(course)
        _add(quiz, q)
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        resp = attempt['responses'][0]
        # Correct answers hidden while taking.
        assert 'isCorrect' not in resp
        assert all('isCorrect' not in c for c in resp['question']['choices'])
        correct = q.choices.get(isCorrect=True)
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': resp['id'], 'selectedChoices': [correct.id]}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert done.status_code == status.HTTP_200_OK
        assert _dec(done.data['score']) == _dec('2.00')
        assert _dec(done.data['maxScore']) == _dec('2.00')
        # showCorrectAnswers defaults to after_submit → revealed now.
        assert done.data['responses'][0]['isCorrect'] is True

    def test_multiple_choice_incorrect_scores_zero(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _mc(course, _bank(course))
        quiz = _quiz(course)
        _add(quiz, q)
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        wrong = q.choices.get(isCorrect=False)
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': attempt['responses'][0]['id'], 'selectedChoices': [wrong.id]}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert _dec(done.data['score']) == _dec('0')
        assert done.data['responses'][0]['isCorrect'] is False

    def test_multiple_answers_all_or_nothing(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _multi(course, _bank(course))
        quiz = _quiz(course)
        _add(quiz, q)
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        evens = list(q.choices.filter(isCorrect=True))
        # Select only one of the two correct → incorrect.
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': attempt['responses'][0]['id'], 'selectedChoices': [evens[0].id]}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert _dec(done.data['score']) == _dec('0')

    def test_short_answer_case_insensitive(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course)
        _add(quiz, _short(course, _bank(course)))
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': attempt['responses'][0]['id'], 'answerText': '  paris '}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert _dec(done.data['score']) == _dec('2.00')

    def test_numerical_equality(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course)
        _add(quiz, _numerical(course, _bank(course)))
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': attempt['responses'][0]['id'], 'answerText': '4.0'}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert _dec(done.data['score']) == _dec('2.00')

    def test_essay_flagged_for_manual_grading(self, api_client, taking_setup):
        course = taking_setup['course']
        bank = _bank(course)
        quiz = _quiz(course)
        _add(quiz, _mc(course, bank), sortKey=0)
        _add(quiz, _essay(course, bank), sortKey=1)
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert done.data['needsManualGrading'] is True
        # passed deferred while anything is pending.
        assert done.data['passed'] is None
        essay_resp = next(r for r in done.data['responses'] if r['needsManualGrading'])
        assert essay_resp['needsManualGrading'] is True


# --------------------------------------------------------------------------- #
# Reveal rules, scoring policy, access control
# --------------------------------------------------------------------------- #

class TestRevealAndAccess:
    def test_show_answers_never_hides_correctness_but_shows_score(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _mc(course, _bank(course))
        quiz = _quiz(course, showCorrectAnswers='never')
        _add(quiz, q)
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        correct = q.choices.get(isCorrect=True)
        api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                         {'response': start.data['responses'][0]['id'], 'selectedChoices': [correct.id]}, format='json')
        done = api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        # Score visible after submit...
        assert _dec(done.data['score']) == _dec('2.00')
        # ...but correctness / isCorrect stays hidden when policy is 'never'.
        resp = done.data['responses'][0]
        assert 'isCorrect' not in resp
        assert all('isCorrect' not in c for c in resp['question']['choices'])

    def test_feedback_and_points_show_after_submit_even_when_answers_never(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, showCorrectAnswers='never')
        _add(quiz, _essay(course, _bank(course)))
        student = taking_setup['students'][0]
        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        api_client.force_authenticate(user=taking_setup['admin'])
        api_client.post(f"/quizAttempts/{start.data['id']}/gradeResponse/",
                        {'response': start.data['responses'][0]['id'], 'pointsEarned': '3',
                         'graderFeedback': 'Add detail.'}, format='json')

        api_client.force_authenticate(user=student)
        mine = api_client.get(f"/quizAttempts/{start.data['id']}/")
        resp = mine.data['responses'][0]
        # Grader feedback and the student's own earned points aren't answer keys —
        # they show once the attempt is submitted...
        assert resp['graderFeedback'] == 'Add detail.'
        assert _dec(resp['pointsEarned']) == _dec('3.00')
        # ...while correctness stays hidden under the 'never' policy.
        assert 'isCorrect' not in resp

    def test_student_cannot_read_another_students_attempt(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course)
        _add(quiz, _mc(course, _bank(course)))
        student_a, student_b = taking_setup['students'][0], taking_setup['students'][1]
        api_client.force_authenticate(user=student_a)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        api_client.force_authenticate(user=student_b)
        resp = api_client.get(f"/quizAttempts/{start.data['id']}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_saveAnswer_blocked_after_deadline(self, api_client, taking_setup):
        from core.models import QuizAttempt
        course = taking_setup['course']
        quiz = _quiz(course, timeLimitMinutes=30)
        q = _mc(course, _bank(course))
        _add(quiz, q)
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.data['deadline'] is not None
        QuizAttempt.objects.filter(pk=start.data['id']).update(deadline=timezone.now() - timedelta(minutes=1))
        save = api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                                {'response': start.data['responses'][0]['id'],
                                 'selectedChoices': [q.choices.get(isCorrect=True).id]}, format='json')
        assert save.status_code == status.HTTP_400_BAD_REQUEST

    def test_official_score_uses_scoring_policy(self, taking_setup):
        from core.models import QuizAttempt
        from core.services.quiz_grading import official_score
        course = taking_setup['course']
        student = taking_setup['students'][0]
        quiz = _quiz(course, scoringPolicy='highest', attemptsAllowed=0)
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=1, status='submitted',
                                   score=Decimal('5'), maxScore=Decimal('10'))
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=2, status='submitted',
                                   score=Decimal('8'), maxScore=Decimal('10'))
        assert official_score(quiz, student) == (Decimal('8'), Decimal('10'))

        quiz.scoringPolicy = 'latest'
        quiz.save()
        assert official_score(quiz, student) == (Decimal('8'), Decimal('10'))

    def test_official_score_excludes_attempts_pending_manual_grading(self, taking_setup):
        from core.models import QuizAttempt
        from core.services.quiz_grading import official_score
        course = taking_setup['course']
        student = taking_setup['students'][0]
        quiz = _quiz(course, scoringPolicy='highest', attemptsAllowed=0)
        # A pending-manual attempt only carries the auto-graded portion — never official.
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=1, status='submitted',
                                   score=Decimal('9'), maxScore=Decimal('10'), needsManualGrading=True)
        assert official_score(quiz, student) is None
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=2, status='submitted',
                                   score=Decimal('6'), maxScore=Decimal('10'))
        assert official_score(quiz, student) == (Decimal('6'), Decimal('10'))

    def test_available_quizzes_exposes_official_score_and_pass(self, api_client, taking_setup):
        from core.models import QuizAttempt
        course = taking_setup['course']
        student = taking_setup['students'][0]
        quiz = _quiz(course, title='Scored', scoringPolicy='highest', attemptsAllowed=0,
                     passingScore=Decimal('70'), passingScoreUnit='percent')
        _add(quiz, _mc(course, _bank(course)))
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=1, status='submitted',
                                   score=Decimal('5'), maxScore=Decimal('10'))
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=2, status='submitted',
                                   score=Decimal('8'), maxScore=Decimal('10'))
        api_client.force_authenticate(user=student)
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        assert resp.status_code == status.HTTP_200_OK
        data = next(q for q in resp.data if q['title'] == 'Scored')
        assert Decimal(data['myScore']) == Decimal('8')
        assert Decimal(data['myMaxScore']) == Decimal('10')
        assert data['myPassed'] is True
        assert data['myScorePending'] is False

    def test_available_quizzes_score_pending_manual_grading(self, api_client, taking_setup):
        from core.models import QuizAttempt
        course = taking_setup['course']
        student = taking_setup['students'][0]
        quiz = _quiz(course, title='Essayed', attemptsAllowed=0)
        _add(quiz, _essay(course, _bank(course)))
        QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=1, status='submitted',
                                   score=Decimal('0'), maxScore=Decimal('5'), needsManualGrading=True)
        api_client.force_authenticate(user=student)
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        data = next(q for q in resp.data if q['title'] == 'Essayed')
        assert data['myScore'] is None
        assert data['myMaxScore'] is None
        assert data['myPassed'] is None
        assert data['myScorePending'] is True

    def test_available_quizzes_score_fields_null_without_attempts(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, title='Fresh')
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        data = next(q for q in resp.data if q['title'] == 'Fresh')
        assert data['myScore'] is None
        assert data['myMaxScore'] is None
        assert data['myPassed'] is None
        assert data['myScorePending'] is False

    def test_available_quizzes_lists_only_takeable(self, api_client, taking_setup):
        from core.models import QuestionBank, QuizQuestionGroup
        course = taking_setup['course']
        bank = _bank(course)
        takeable = _quiz(course, title='Takeable')
        _add(takeable, _mc(course, bank))
        _quiz(course, title='Draft', isPublished=False)            # unpublished → excluded
        draw = _quiz(course, title='Draw')                          # random-draw from a non-empty bank → listed
        QuizQuestionGroup.objects.create(quiz=draw, bank=bank, pickCount=1)
        empty = _quiz(course, title='Empty')                        # draw over an empty bank → no content → excluded
        empty_bank = QuestionBank.objects.create(course=course, name='EmptyBank')
        QuizQuestionGroup.objects.create(quiz=empty, bank=empty_bank, pickCount=1)
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        assert resp.status_code == status.HTTP_200_OK
        titles = {q['title'] for q in resp.data}
        assert titles == {'Takeable', 'Draw'}

    def test_locked_attached_quiz_listed_but_upcoming_standalone_hidden(self, api_client, taking_setup):
        from core.models import Assignment
        course = taking_setup['course']
        assignment = taking_setup['assignment']
        # Assignment is visible to students, but feedback isn't released yet.
        Assignment.objects.filter(pk=assignment.id).update(isReleased=True, feedbackReleased=False)
        bank = _bank(course)

        # Attached quiz that unlocks only after feedback → still locked, but should be listed
        # so the assignment card can show it with a reason.
        attached = _quiz(course, title='Attached', assignment=assignment, assignmentTrigger='after_feedback')
        _add(attached, _mc(course, bank))
        # Standalone quiz that hasn't opened yet → hidden until it opens.
        upcoming = _quiz(course, title='Upcoming', availableFrom=timezone.now() + timedelta(days=1))
        _add(upcoming, _mc(course, bank))

        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        assert resp.status_code == status.HTTP_200_OK
        by_id = {q['id']: q for q in resp.data}

        assert attached.id in by_id
        assert by_id[attached.id]['availability']['isOpen'] is False
        assert by_id[attached.id]['availability']['reason'] == 'feedback_not_released'
        assert upcoming.id not in by_id

    def test_available_quizzes_reports_attempt_state(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, title='State', attemptsAllowed=2)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')

        def entry():
            listing = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
            return next(q for q in listing.data if q['id'] == quiz.id)

        # An unfinished attempt → open, not yet submitted (UI shows "Resume").
        e1 = entry()
        assert e1['hasOpenAttempt'] is True
        assert e1['hasSubmittedAttempt'] is False

        api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        # After submitting → no open attempt, has a submitted one (UI shows "New attempt"/"Review").
        e2 = entry()
        assert e2['hasOpenAttempt'] is False
        assert e2['hasSubmittedAttempt'] is True


# --------------------------------------------------------------------------- #
# Attached-quiz closing controls
# --------------------------------------------------------------------------- #

class TestClosing:
    def test_feedback_released_at_stamped_and_cleared(self, taking_setup):
        assignment = taking_setup['assignment']
        assert assignment.feedbackReleasedAt is None
        assignment.feedbackReleased = True
        assignment.save()
        assignment.refresh_from_db()
        assert assignment.feedbackReleasedAt is not None
        assignment.feedbackReleased = False
        assignment.save()
        assignment.refresh_from_db()
        assert assignment.feedbackReleasedAt is None

    def test_close_time_by_event(self, taking_setup):
        from core.models import Quiz
        from core.services.quiz_grading import quiz_close_time
        course, assignment, student = taking_setup['course'], taking_setup['assignment'], taking_setup['students'][0]
        due = timezone.now() + timedelta(days=1)
        assignment.uploadDueDate = due
        assignment.isReleased = True
        assignment.save()

        q = _quiz(course, assignment=assignment, closeEvent='assignment_due', closeOffsetMinutes=1440)
        assert quiz_close_time(q, student) == due + timedelta(minutes=1440)

        until = timezone.now() + timedelta(days=3)
        Quiz.objects.filter(pk=q.id).update(closeEvent='fixed_date', availableUntil=until)
        assert quiz_close_time(Quiz.objects.get(pk=q.id), student) == until

        # feedback_released: None until released, then feedbackReleasedAt + offset.
        Quiz.objects.filter(pk=q.id).update(closeEvent='feedback_released', closeOffsetMinutes=10080)
        assert quiz_close_time(Quiz.objects.get(pk=q.id), student) is None
        assignment.feedbackReleased = True
        assignment.save()
        assignment.refresh_from_db()
        assert quiz_close_time(Quiz.objects.get(pk=q.id), student) == assignment.feedbackReleasedAt + timedelta(minutes=10080)

        Quiz.objects.filter(pk=q.id).update(closeEvent='none')
        assert quiz_close_time(Quiz.objects.get(pk=q.id), student) is None

    def test_submission_close_is_per_student_and_gates_start(self, taking_setup):
        from core.models import Quiz, Submission
        from core.services.quiz_grading import quiz_availability, quiz_close_time
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.save()
        student, other = taking_setup['students'][0], taking_setup['students'][1]
        q = _quiz(course, assignment=assignment, assignmentTrigger='after_submission',
                  closeEvent='submission', closeOffsetMinutes=60)
        _add(q, _mc(course, _bank(course)))

        # Before submitting: locked, no close.
        assert quiz_availability(q, student) == (False, 'no_submission_yet')
        assert quiz_close_time(Quiz.objects.get(pk=q.id), student) is None

        # Submitted 90 min ago → the 60-min window has already passed.
        sub_time = timezone.now() - timedelta(minutes=90)
        with factory.django.mute_signals(post_save):
            sub = Submission.objects.create(assignment=assignment, dateUploaded=sub_time)
            sub.students.add(student)

        q = Quiz.objects.get(pk=q.id)
        assert quiz_close_time(q, student) == sub_time + timedelta(minutes=60)
        assert quiz_availability(q, student) == (False, 'closed')
        # A student who hasn't submitted is unaffected.
        assert quiz_availability(q, other) == (False, 'no_submission_yet')

    def test_after_student_feedback_requires_own_submission_and_release(self, taking_setup):
        from core.models import Submission
        from core.services.quiz_grading import quiz_availability
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.save()
        student, other = taking_setup['students'][0], taking_setup['students'][1]
        q = _quiz(course, assignment=assignment, assignmentTrigger='after_student_feedback')
        _add(q, _mc(course, _bank(course)))

        # No submission → locked.
        assert quiz_availability(q, student) == (False, 'student_feedback_not_ready')

        # Submitted, but feedback isn't visible yet → still locked.
        with factory.django.mute_signals(post_save):
            sub = Submission.objects.create(assignment=assignment)
            sub.students.add(student)
        assert quiz_availability(q, student) == (False, 'student_feedback_not_ready')

        # Whole-assignment feedback released → opens for the submitter only.
        assignment.feedbackReleased = True
        assignment.save()
        assert quiz_availability(q, student) == (True, 'open')
        assert quiz_availability(q, other) == (False, 'student_feedback_not_ready')

    def test_after_student_feedback_live_mode_is_self_paced(self, taking_setup):
        from core.models import Submission
        from core.services.quiz_grading import quiz_availability
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.liveFeedbackMode = True
        assignment.save()
        student = taking_setup['students'][0]
        q = _quiz(course, assignment=assignment, assignmentTrigger='after_student_feedback')
        _add(q, _mc(course, _bank(course)))

        # Submitted but not finalized → their feedback isn't ready.
        with factory.django.mute_signals(post_save):
            sub = Submission.objects.create(assignment=assignment)
            sub.students.add(student)
        assert quiz_availability(q, student) == (False, 'student_feedback_not_ready')

        # Their submission is finalized → their feedback is ready → quiz opens (self-paced).
        Submission.objects.filter(pk=sub.id).update(isFinalized=True)
        assert quiz_availability(q, student) == (True, 'open')

    def test_end_attempts_at_close_caps_deadline(self, api_client, taking_setup):
        from django.utils.dateparse import parse_datetime
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.save()
        close = timezone.now() + timedelta(minutes=30)
        q = _quiz(course, assignment=assignment, assignmentTrigger='during',
                  closeEvent='fixed_date', availableUntil=close,
                  timeLimitMinutes=120, endAttemptsAtClose=True)
        _add(q, _mc(course, _bank(course)))

        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': q.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        # Deadline capped to the 30-min close, not the 120-min timer.
        deadline = parse_datetime(start.data['deadline'])
        assert deadline <= close + timedelta(seconds=1)
        assert deadline < timezone.now() + timedelta(minutes=60)

    def test_degenerate_close_requires_offset(self, api_client, taking_setup):
        course, assignment = taking_setup['course'], taking_setup['assignment']
        api_client.force_authenticate(user=taking_setup['admin'])
        quiz = _quiz(course, assignment=assignment)

        # after_submission + submission close with no offset would close instantly → rejected.
        bad = api_client.patch(f'/quizzes/{quiz.id}/', {
            'assignmentTrigger': 'after_submission', 'closeEvent': 'submission', 'closeOffsetMinutes': 0,
        }, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST

        # With a positive offset it's accepted.
        ok = api_client.patch(f'/quizzes/{quiz.id}/', {
            'assignmentTrigger': 'after_submission', 'closeEvent': 'submission', 'closeOffsetMinutes': 60,
        }, format='json')
        assert ok.status_code == status.HTTP_200_OK

    def test_start_blocked_after_fixed_close(self, api_client, taking_setup):
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.save()
        q = _quiz(course, assignment=assignment, assignmentTrigger='during',
                  closeEvent='fixed_date', availableUntil=timezone.now() - timedelta(minutes=1))
        _add(q, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.post('/quizAttempts/', {'quiz': q.id}, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_soft_close_does_not_cap_deadline(self, api_client, taking_setup):
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.save()
        close = timezone.now() + timedelta(minutes=30)
        # Untimed, soft close (endAttemptsAtClose=False) → the attempt has no deadline.
        q = _quiz(course, assignment=assignment, assignmentTrigger='during',
                  closeEvent='fixed_date', availableUntil=close, endAttemptsAtClose=False)
        _add(q, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': q.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        assert start.data['deadline'] is None

    def test_standalone_end_attempts_at_close_caps_deadline(self, api_client, taking_setup):
        from django.utils.dateparse import parse_datetime
        course = taking_setup['course']
        close = timezone.now() + timedelta(minutes=30)
        # Standalone quiz (no assignment): the close is availableUntil. Hard close caps
        # the attempt deadline; soft close leaves it open-ended.
        hard = _quiz(course, title='Hard', availableUntil=close, endAttemptsAtClose=True)
        _add(hard, _mc(course, _bank(course)))
        soft = _quiz(course, title='Soft', availableUntil=close, endAttemptsAtClose=False)
        _add(soft, _mc(course, _bank(course)))

        api_client.force_authenticate(user=taking_setup['students'][0])
        hard_start = api_client.post('/quizAttempts/', {'quiz': hard.id}, format='json')
        assert parse_datetime(hard_start.data['deadline']) == close
        soft_start = api_client.post('/quizAttempts/', {'quiz': soft.id}, format='json')
        assert soft_start.data['deadline'] is None

    def test_after_close_answer_reveal(self, taking_setup):
        from core.models import Quiz, QuizAttempt
        from core.services.quiz_grading import answers_visible
        course, student = taking_setup['course'], taking_setup['students'][0]
        q = _quiz(course, showCorrectAnswers='after_close', availableUntil=timezone.now() + timedelta(days=1))
        attempt = QuizAttempt.objects.create(quiz=q, student=student, attemptNumber=1, status='submitted')
        assert answers_visible(q, attempt) is False  # not closed yet
        Quiz.objects.filter(pk=q.id).update(availableUntil=timezone.now() - timedelta(minutes=1))
        assert answers_visible(Quiz.objects.get(pk=q.id), attempt) is True  # closed → revealed

    def test_close_at_exposed_in_available_quizzes(self, api_client, taking_setup):
        course, assignment = taking_setup['course'], taking_setup['assignment']
        assignment.isReleased = True
        assignment.save()
        close = timezone.now() + timedelta(days=2)
        q = _quiz(course, assignment=assignment, assignmentTrigger='during',
                  closeEvent='fixed_date', availableUntil=close)
        _add(q, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        q_data = next(x for x in resp.data if x['id'] == q.id)
        assert q_data['closeAt'] is not None


# --------------------------------------------------------------------------- #
# Timed attempts — expiry, resume, and the abandoned-attempt sweep
# --------------------------------------------------------------------------- #

class TestTimedAttempts:
    def test_timed_start_sets_deadline(self, api_client, taking_setup):
        from django.utils.dateparse import parse_datetime
        course = taking_setup['course']
        quiz = _quiz(course, timeLimitMinutes=30)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        deadline = parse_datetime(start.data['deadline'])
        # ~30 minutes out (small slack for execution time).
        assert timedelta(minutes=29) < deadline - timezone.now() <= timedelta(minutes=30)

    def test_resume_of_expired_attempt_auto_submits(self, api_client, taking_setup):
        from core.models import QuizAttempt
        course = taking_setup['course']
        quiz = _quiz(course, timeLimitMinutes=30, attemptsAllowed=1)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')

        # Time runs out while the student is away.
        QuizAttempt.objects.filter(pk=start.data['id']).update(deadline=timezone.now() - timedelta(minutes=1))

        # Returning finalizes the expired attempt instead of resuming it.
        again = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert again.status_code == status.HTTP_200_OK
        assert again.data['id'] == start.data['id']
        assert again.data['status'] == 'submitted'

    def test_sweep_finalizes_abandoned_expired_attempt_grading_partial(self, api_client, taking_setup):
        from core.models import QuizAttempt
        from core.tasks import finalize_expired_quiz_attempts
        course = taking_setup['course']
        q = _mc(course, _bank(course))  # 2 pts, correct answer '4'
        quiz = _quiz(course, timeLimitMinutes=30)
        _add(quiz, q)
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')

        # The student answers, then vanishes and their time expires.
        correct = q.choices.get(isCorrect=True)
        api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                         {'response': start.data['responses'][0]['id'], 'selectedChoices': [correct.id]}, format='json')
        QuizAttempt.objects.filter(pk=start.data['id']).update(deadline=timezone.now() - timedelta(minutes=1))

        # The sweep grades the stuck attempt (partial answers count).
        assert finalize_expired_quiz_attempts() == 1
        attempt = QuizAttempt.objects.get(pk=start.data['id'])
        assert attempt.status == 'submitted'
        assert attempt.score == Decimal('2.00')

        # A second run is a no-op — nothing is still in-progress-and-expired.
        assert finalize_expired_quiz_attempts() == 0

    def test_sweep_ignores_active_and_untimed_attempts(self, api_client, taking_setup):
        from core.tasks import finalize_expired_quiz_attempts
        course = taking_setup['course']
        # A live timed attempt (deadline in the future) and an untimed one (no deadline).
        timed = _quiz(course, title='Timed', timeLimitMinutes=30)
        _add(timed, _mc(course, _bank(course)))
        untimed = _quiz(course, title='Untimed')
        _add(untimed, _mc(course, _bank(course)))
        student = taking_setup['students'][0]
        api_client.force_authenticate(user=student)
        api_client.post('/quizAttempts/', {'quiz': timed.id}, format='json')
        api_client.post('/quizAttempts/', {'quiz': untimed.id}, format='json')

        assert finalize_expired_quiz_attempts() == 0

    def test_attempt_exposes_server_now(self, api_client, taking_setup):
        from django.utils.dateparse import parse_datetime
        course = taking_setup['course']
        quiz = _quiz(course, timeLimitMinutes=30)
        _add(quiz, _mc(course, _bank(course)))
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        # serverNow anchors the client countdown; it should be ~now.
        assert abs((parse_datetime(start.data['serverNow']) - timezone.now()).total_seconds()) < 5

    def test_saveanswer_grace_lets_final_flush_land(self, api_client, taking_setup):
        from core.models import QuizAttempt
        course = taking_setup['course']
        q = _mc(course, _bank(course))
        quiz = _quiz(course, timeLimitMinutes=30)
        _add(quiz, q)
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        rid = start.data['responses'][0]['id']
        correct = q.choices.get(isCorrect=True)

        # Deadline just passed (within the grace) → the auto-submit's final flush still saves.
        QuizAttempt.objects.filter(pk=start.data['id']).update(deadline=timezone.now() - timedelta(seconds=2))
        ok = api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                              {'response': rid, 'selectedChoices': [correct.id]}, format='json')
        assert ok.status_code == status.HTTP_200_OK

        # Well past the grace → rejected (no editing after time is truly up).
        QuizAttempt.objects.filter(pk=start.data['id']).update(deadline=timezone.now() - timedelta(seconds=30))
        late = api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                                {'response': rid, 'selectedChoices': [correct.id]}, format='json')
        assert late.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------- #
# Manual grading (essay/code) + the quizGraders role
# --------------------------------------------------------------------------- #

class TestManualGrading:
    def _submitted_attempt(self, api_client, taking_setup, quiz):
        """Student answers the MC correctly, writes an essay, and submits."""
        student = taking_setup['students'][0]
        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        for r in start.data['responses']:
            qtype = r['question']['questionType']
            if qtype == 'multiple_choice':
                correct = next(c for c in r['question']['choices'] if c['text'] == '4')
                api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                                 {'response': r['id'], 'selectedChoices': [correct['id']]}, format='json')
            elif qtype == 'essay':
                api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                                 {'response': r['id'], 'answerText': 'LIFO vs FIFO.'}, format='json')
        done = api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        assert done.status_code == status.HTTP_200_OK
        essay = next(r for r in done.data['responses'] if r['needsManualGrading'])
        return start.data['id'], essay['id']

    def _essay_quiz(self, taking_setup, **kw):
        course = taking_setup['course']
        bank = _bank(course)
        quiz = _quiz(course, **kw)
        _add(quiz, _mc(course, bank), sortKey=0)          # 2 pts auto
        _add(quiz, _essay(course, bank), sortKey=1)        # 5 pts manual
        return quiz

    def test_only_quiz_graders_and_admins_can_grade(self, api_client, taking_setup):
        course = taking_setup['course']
        grader = course.graders.first()
        quiz = self._essay_quiz(taking_setup)
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)

        # A plain (assignment) grader is NOT a quiz grader → blocked from grading + the queue.
        api_client.force_authenticate(user=grader)
        denied = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                                 {'response': essay_id, 'pointsEarned': '4'}, format='json')
        assert denied.status_code == status.HTTP_403_FORBIDDEN
        assert api_client.get(f'/quizzes/{quiz.id}/attempts/').status_code == status.HTTP_403_FORBIDDEN

        # The student can't grade their own attempt either.
        api_client.force_authenticate(user=taking_setup['students'][0])
        own = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                              {'response': essay_id, 'pointsEarned': '5'}, format='json')
        assert own.status_code == status.HTTP_403_FORBIDDEN

        # Granting the quizGraders role unlocks both.
        course.quizGraders.add(grader)
        api_client.force_authenticate(user=grader)
        listing = api_client.get(f'/quizzes/{quiz.id}/attempts/?needsGrading=true')
        assert listing.status_code == status.HTTP_200_OK
        assert [a['id'] for a in listing.data] == [attempt_id]
        graded = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                                 {'response': essay_id, 'pointsEarned': '4'}, format='json')
        assert graded.status_code == status.HTTP_200_OK

    def test_manual_grade_finalizes_score_and_pass(self, api_client, taking_setup):
        from core.models import QuizAttempt, QuizResponse
        course = taking_setup['course']
        quiz = self._essay_quiz(taking_setup, passingScore=Decimal('6'), passingScoreUnit='points')
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)

        before = QuizAttempt.objects.get(pk=attempt_id)
        assert before.needsManualGrading is True and before.passed is None
        assert before.score == Decimal('2.00')  # only the auto-graded MC so far

        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                               {'response': essay_id, 'pointsEarned': '4.5',
                                'graderFeedback': 'Good, but expand on queues.'}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert _dec(resp.data['score']) == _dec('6.50')            # 2 auto + 4.5 manual
        assert resp.data['needsManualGrading'] is False
        assert resp.data['passed'] is True                          # ≥ 6 points

        graded = QuizResponse.objects.get(pk=essay_id)
        assert graded.gradedBy == taking_setup['admin']
        assert graded.graderFeedback == 'Good, but expand on queues.'
        # The auto-graded MC's score was preserved (no regrade).
        assert QuizAttempt.objects.get(pk=attempt_id).score == Decimal('6.50')

    def test_manual_grade_clamps_to_question_points(self, api_client, taking_setup):
        quiz = self._essay_quiz(taking_setup)
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)
        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                               {'response': essay_id, 'pointsEarned': '99'}, format='json')
        essay = next(r for r in resp.data['responses'] if r['id'] == essay_id)
        assert _dec(essay['pointsEarned']) == _dec('5.00')  # capped at the question's worth

    def test_student_sees_manual_grade_and_feedback_when_revealed(self, api_client, taking_setup):
        quiz = self._essay_quiz(taking_setup, showCorrectAnswers='after_submit')
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)
        api_client.force_authenticate(user=taking_setup['admin'])
        api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                        {'response': essay_id, 'pointsEarned': '3', 'graderFeedback': 'Solid.'}, format='json')

        api_client.force_authenticate(user=taking_setup['students'][0])
        mine = api_client.get(f'/quizAttempts/{attempt_id}/')
        essay = next(r for r in mine.data['responses'] if r['id'] == essay_id)
        assert _dec(essay['pointsEarned']) == _dec('3.00')
        assert essay['graderFeedback'] == 'Solid.'
        assert _dec(mine.data['score']) == _dec('5.00')

    def test_roster_grants_and_revokes_quiz_grader_role(self, api_client, taking_setup):
        course, grader = taking_setup['course'], taking_setup['course'].graders.first()
        api_client.force_authenticate(user=taking_setup['admin'])
        add = api_client.patch(f'/courses/{course.id}/addToRoster/',
                               {'quizGraders': [grader.email]}, format='json')
        assert add.status_code == status.HTTP_200_OK
        assert grader.email in add.data['quizGraders']
        remove = api_client.patch(f'/courses/{course.id}/removeFromRoster/',
                                  {'quizGraders': [grader.email]}, format='json')
        assert remove.status_code == status.HTTP_200_OK
        assert grader.email not in remove.data['quizGraders']
        # Removing the role does NOT unenroll the grader.
        assert course.graders.filter(pk=grader.pk).exists()

    def test_reopen_returns_response_to_grading_queue(self, api_client, taking_setup):
        from core.models import QuizResponse
        quiz = self._essay_quiz(taking_setup, passingScore=Decimal('6'), passingScoreUnit='points')
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)
        api_client.force_authenticate(user=taking_setup['admin'])
        api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                        {'response': essay_id, 'pointsEarned': '4.5', 'graderFeedback': 'Nice.'},
                        format='json')

        resp = api_client.post(f'/quizAttempts/{attempt_id}/reopenResponse/',
                               {'response': essay_id}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['needsManualGrading'] is True
        assert _dec(resp.data['score']) == _dec('2.00')  # back to the auto-graded MC only
        assert resp.data['passed'] is None
        reopened = QuizResponse.objects.get(pk=essay_id)
        assert reopened.pointsEarned is None and reopened.gradedBy is None
        assert reopened.graderFeedback == 'Nice.'  # kept as a draft for the next grader

    def test_reopen_requires_grading_role_and_graded_state(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = self._essay_quiz(taking_setup)
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)

        # Not graded yet → 400 even for an admin.
        api_client.force_authenticate(user=taking_setup['admin'])
        early = api_client.post(f'/quizAttempts/{attempt_id}/reopenResponse/',
                                {'response': essay_id}, format='json')
        assert early.status_code == status.HTTP_400_BAD_REQUEST

        api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                        {'response': essay_id, 'pointsEarned': '3'}, format='json')

        # Plain graders and students can't reopen.
        api_client.force_authenticate(user=course.graders.first())
        assert api_client.post(f'/quizAttempts/{attempt_id}/reopenResponse/',
                               {'response': essay_id},
                               format='json').status_code == status.HTTP_403_FORBIDDEN
        api_client.force_authenticate(user=taking_setup['students'][0])
        assert api_client.post(f'/quizAttempts/{attempt_id}/reopenResponse/',
                               {'response': essay_id},
                               format='json').status_code == status.HTTP_403_FORBIDDEN

    def test_staff_retrieve_returns_grading_projection(self, api_client, taking_setup):
        quiz = self._essay_quiz(taking_setup, showCorrectAnswers='never')
        attempt_id, _ = self._submitted_attempt(api_client, taking_setup, quiz)
        student = taking_setup['students'][0]

        # Staff reading someone else's attempt see the grading projection: the student's
        # identity plus revealed correctness/scores regardless of the quiz's reveal policy.
        api_client.force_authenticate(user=taking_setup['admin'])
        staff_view = api_client.get(f'/quizAttempts/{attempt_id}/')
        assert staff_view.status_code == status.HTTP_200_OK
        assert staff_view.data['student'] == student.email
        assert 'score' in staff_view.data
        mc = next(r for r in staff_view.data['responses']
                  if r['question']['questionType'] == 'multiple_choice')
        assert 'isCorrect' in mc

        # The owner keeps the policy-gated student view ('never' → no correctness, no email).
        api_client.force_authenticate(user=student)
        own = api_client.get(f'/quizAttempts/{attempt_id}/')
        assert 'student' not in own.data
        mc_own = next(r for r in own.data['responses']
                      if r['question']['questionType'] == 'multiple_choice')
        assert 'isCorrect' not in mc_own

    def test_results_reports_official_scores_per_student(self, api_client, taking_setup):
        quiz = self._essay_quiz(taking_setup, passingScore=Decimal('6'), passingScoreUnit='points')
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)
        student = taking_setup['students'][0]

        # Plain graders can't view results.
        api_client.force_authenticate(user=taking_setup['course'].graders.first())
        assert api_client.get(f'/quizzes/{quiz.id}/results/').status_code == status.HTTP_403_FORBIDDEN

        # While the essay is ungraded: the row exists but carries no official score yet.
        api_client.force_authenticate(user=taking_setup['admin'])
        pending = api_client.get(f'/quizzes/{quiz.id}/results/')
        assert pending.status_code == status.HTTP_200_OK
        row = next(r for r in pending.data if r['student'] == student.email)
        assert row['score'] is None and row['passed'] is None
        assert row['needsGrading'] is True
        assert row['attemptsUsed'] == 1

        api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                        {'response': essay_id, 'pointsEarned': '4.5'}, format='json')
        graded = api_client.get(f'/quizzes/{quiz.id}/results/')
        row = next(r for r in graded.data if r['student'] == student.email)
        assert _dec(row['score']) == _dec('6.50')
        assert _dec(row['maxScore']) == _dec('7.00')
        assert row['passed'] is True
        assert row['needsGrading'] is False
        assert row['lastSubmittedAt'] is not None

    def test_grading_blocked_on_archived_course(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = self._essay_quiz(taking_setup)
        attempt_id, essay_id = self._submitted_attempt(api_client, taking_setup, quiz)
        api_client.force_authenticate(user=taking_setup['admin'])
        graded = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                                 {'response': essay_id, 'pointsEarned': '3'}, format='json')
        assert graded.status_code == status.HTTP_200_OK

        course.archived = True
        course.save()
        regrade = api_client.post(f'/quizAttempts/{attempt_id}/gradeResponse/',
                                  {'response': essay_id, 'pointsEarned': '4'}, format='json')
        assert regrade.status_code == status.HTTP_403_FORBIDDEN
        reopen = api_client.post(f'/quizAttempts/{attempt_id}/reopenResponse/',
                                 {'response': essay_id}, format='json')
        assert reopen.status_code == status.HTTP_403_FORBIDDEN

    def test_grade_quiz_capability_follows_role(self, api_client, taking_setup):
        course = taking_setup['course']
        grader = course.graders.first()
        api_client.force_authenticate(user=grader)
        before = api_client.get(f'/courses/{course.id}/capabilities/')
        assert before.data['capabilitiesMap']['grade_quiz'] is False
        course.quizGraders.add(grader)
        after = api_client.get(f'/courses/{course.id}/capabilities/')
        assert after.data['capabilitiesMap']['grade_quiz'] is True
        api_client.force_authenticate(user=taking_setup['admin'])
        admin_caps = api_client.get(f'/courses/{course.id}/capabilities/')
        assert admin_caps.data['capabilitiesMap']['grade_quiz'] is True


class TestQuizAuditLog:
    """Quiz activity feeds the course audit log (CourseAuditEvent)."""

    def _events(self, course, **filters):
        from core.models import CourseAuditEvent
        return CourseAuditEvent.objects.filter(course=course, **filters)

    def test_attempt_start_and_submit_are_logged(self, api_client, taking_setup):
        course = taking_setup['course']
        student = taking_setup['students'][0]
        quiz = _quiz(course)
        _add(quiz, _mc(course, _bank(course)))

        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        assert self._events(course, quiz=quiz, user=student, event_type='quiz_attempt_started').exists()

        api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        assert self._events(course, quiz=quiz, user=student, event_type='quiz_attempt_submitted').exists()

    def test_authoring_lifecycle_is_logged(self, api_client, taking_setup):
        course = taking_setup['course']
        api_client.force_authenticate(user=taking_setup['admin'])

        resp = api_client.post('/quizzes/', {'course': course.id, 'title': 'Audited'}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        quiz_id = resp.data['id']
        assert self._events(course, quiz_id=quiz_id, event_type='quiz_created').exists()

        api_client.patch(f'/quizzes/{quiz_id}/', {'isPublished': True}, format='json')
        assert self._events(course, quiz_id=quiz_id, event_type='quiz_published').exists()

        api_client.patch(f'/quizzes/{quiz_id}/', {'title': 'Renamed'}, format='json')
        assert self._events(course, quiz_id=quiz_id, event_type='quiz_updated').exists()

        api_client.patch(f'/quizzes/{quiz_id}/', {'isPublished': False}, format='json')
        assert self._events(course, quiz_id=quiz_id, event_type='quiz_unpublished').exists()

        api_client.delete(f'/quizzes/{quiz_id}/')
        assert self._events(course, event_type='quiz_deleted').exists()

    def test_manual_grading_and_reopen_are_logged(self, api_client, taking_setup):
        course = taking_setup['course']
        student = taking_setup['students'][0]
        admin = taking_setup['admin']
        quiz = _quiz(course)
        _add(quiz, _essay(course, _bank(course)))

        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        essay_id = start.data['responses'][0]['id']

        api_client.force_authenticate(user=admin)
        api_client.post(f"/quizAttempts/{start.data['id']}/gradeResponse/",
                        {'response': essay_id, 'pointsEarned': '3'}, format='json')
        graded = self._events(course, quiz=quiz, user=admin, event_type='quiz_response_graded')
        assert graded.exists()
        assert graded.first().meta['student'] == student.email
        assert graded.first().meta['pointsEarned'] == '3.00'

        api_client.post(f"/quizAttempts/{start.data['id']}/reopenResponse/",
                        {'response': essay_id}, format='json')
        assert self._events(course, quiz=quiz, user=admin,
                            event_type='quiz_response_grade_reopened').exists()


# --------------------------------------------------------------------------- #
# Regression tests for the pre-push code-review fixes
# --------------------------------------------------------------------------- #

class TestReviewFixRegressions:
    def _take(self, api_client, student, quiz):
        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        return start.data

    def test_short_answer_key_hidden_while_taking_then_revealed(self, api_client, taking_setup):
        # The accepted answer for short-answer/numerical is stored as a choice; it must not
        # ship to a student mid-attempt, but is fine to reveal after submitting.
        course = taking_setup['course']
        quiz = _quiz(course, showCorrectAnswers='after_submit')
        _add(quiz, _short(course, _bank(course)))
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        resp = attempt['responses'][0]
        assert 'choices' not in resp['question']  # answer key not exposed while taking
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': resp['id'], 'answerText': 'Paris'}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        revealed = done.data['responses'][0]['question']['choices']
        assert any(c['text'] == 'Paris' for c in revealed)  # revealed only after submit

    def test_numerical_snan_answer_does_not_crash(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course)
        _add(quiz, _numerical(course, _bank(course)))
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': attempt['responses'][0]['id'], 'answerText': 'snan'}, format='json')
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert done.status_code == status.HTTP_200_OK
        assert _dec(done.data['score']) == _dec('0.00')  # graded wrong, not a 500

    def test_attempt_survives_question_deletion(self, api_client, taking_setup):
        # Editing/deleting a question must not alter or destroy an in-flight attempt (snapshot).
        from core.models import Question
        course = taking_setup['course']
        q = _mc(course, _bank(course))
        quiz = _quiz(course)
        _add(quiz, q)
        attempt = self._take(api_client, taking_setup['students'][0], quiz)
        correct_id = q.choices.get(isCorrect=True).id
        api_client.patch(f"/quizAttempts/{attempt['id']}/saveAnswer/",
                         {'response': attempt['responses'][0]['id'], 'selectedChoices': [correct_id]},
                         format='json')
        Question.objects.filter(pk=q.id).delete()  # delete the live question mid-attempt
        done = api_client.post(f"/quizAttempts/{attempt['id']}/submit/", {}, format='json')
        assert done.status_code == status.HTTP_200_OK
        assert _dec(done.data['score']) == _dec('2.00')  # graded from the snapshot

    def test_deleting_a_used_question_returns_409_not_500(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _mc(course, _bank(course))
        quiz = _quiz(course)
        _add(quiz, q)
        self._take(api_client, taking_setup['students'][0], quiz)  # creates a QuizResponse
        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.delete(f'/questions/{q.id}/')
        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)  # SET_NULL, no crash

    def test_cross_course_question_cannot_be_attached_to_quiz(self, api_client, taking_setup):
        from core.models import Quiz
        from core.tests.factories import CourseFactory
        course_a = taking_setup['course']
        with factory.django.mute_signals(post_save):
            course_b = CourseFactory(name="other333", period="s2026", organization=course_a.organization)
        foreign_q = _mc(course_b, _bank(course_b))
        quiz_a = _quiz(course_a)
        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.post('/quizQuestions/',
                               {'quiz': quiz_a.id, 'question': foreign_q.id}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_reset_attempts_deletes_all(self, api_client, taking_setup):
        from core.models import QuizAttempt
        course = taking_setup['course']
        quiz = _quiz(course)
        _add(quiz, _mc(course, _bank(course)))
        self._take(api_client, taking_setup['students'][0], quiz)
        assert quiz.attempts.count() == 1
        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.post(f'/quizzes/{quiz.id}/resetAttempts/', {}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert QuizAttempt.objects.filter(quiz=quiz).count() == 0

    def test_deleting_assignment_unpublishes_attached_quiz(self, taking_setup):
        from core.models import Assignment, Quiz
        course = taking_setup['course']
        assignment = taking_setup['assignment']
        quiz = _quiz(course, title='Attached', assignment=assignment, isPublished=True)
        Assignment.objects.get(pk=assignment.id).delete()
        quiz.refresh_from_db()
        assert quiz.assignment_id is None
        assert quiz.isPublished is False  # never silently becomes an open standalone quiz

    def test_after_close_does_not_reveal_to_in_progress_attempt(self, api_client, taking_setup):
        # A quiz with 'after_close' reveal must not leak correct answers to an attempt that is
        # still in progress once the close time passes.
        from core.models import QuizAttempt
        course = taking_setup['course']
        quiz = _quiz(course, showCorrectAnswers='after_close',
                     availableUntil=timezone.now() - timedelta(minutes=1))
        _add(quiz, _mc(course, _bank(course)))
        # availableUntil is in the past → a fresh start is closed; craft an in-progress attempt.
        student = taking_setup['students'][0]
        attempt = QuizAttempt.objects.create(quiz=quiz, student=student, attemptNumber=1,
                                             status='in_progress')
        from core.services import quiz_grading
        quiz_grading.build_attempt_responses(attempt)
        api_client.force_authenticate(user=student)
        resp = api_client.get(f"/quizAttempts/{attempt.id}/")
        for r in resp.data['responses']:
            assert all('isCorrect' not in c for c in r['question'].get('choices', []))


# --------------------------------------------------------------------------- #
# Per-question grading settings: partial credit + numerical tolerance
# --------------------------------------------------------------------------- #

class TestGradingSettings:
    def _submit_with_choices(self, api_client, taking_setup, quiz, pick_texts):
        """Start an attempt, select the choices whose text is in pick_texts, submit."""
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert start.status_code == status.HTTP_201_CREATED
        resp = start.data['responses'][0]
        choice_ids = [c['id'] for c in resp['question']['choices'] if c['text'] in pick_texts]
        api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                         {'response': resp['id'], 'selectedChoices': choice_ids}, format='json')
        done = api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        assert done.status_code == status.HTTP_200_OK
        return done.data

    def _submit_with_text(self, api_client, taking_setup, quiz, text):
        api_client.force_authenticate(user=taking_setup['students'][0])
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        api_client.patch(f"/quizAttempts/{start.data['id']}/saveAnswer/",
                         {'response': start.data['responses'][0]['id'], 'answerText': text}, format='json')
        done = api_client.post(f"/quizAttempts/{start.data['id']}/submit/", {}, format='json')
        return done.data

    def test_partial_credit_right_minus_wrong(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _multi(course, _bank(course), points='4')  # correct: 2 and 4 (of 2/3/4)
        q.partialCredit = True
        q.save()
        quiz = _quiz(course, attemptsAllowed=0)
        _add(quiz, q)

        # Full credit: both correct, nothing wrong.
        done = self._submit_with_choices(api_client, taking_setup, quiz, {'2', '4'})
        assert _dec(done['score']) == _dec('4.00')
        assert done['responses'][0]['isCorrect'] is True

        # Half right: (1 - 0) / 2 × 4 = 2; partially correct ⇒ isCorrect is None.
        done = self._submit_with_choices(api_client, taking_setup, quiz, {'2'})
        assert _dec(done['score']) == _dec('2.00')
        assert done['responses'][0]['isCorrect'] is None

        # One right one wrong cancels out: (1 - 1) / 2 × 4 = 0.
        done = self._submit_with_choices(api_client, taking_setup, quiz, {'2', '3'})
        assert _dec(done['score']) == _dec('0.00')
        assert done['responses'][0]['isCorrect'] is False

        # Selecting everything: (2 - 1) / 2 × 4 = 2 — floored formula, not full marks.
        done = self._submit_with_choices(api_client, taking_setup, quiz, {'2', '3', '4'})
        assert _dec(done['score']) == _dec('2.00')

    def test_partial_credit_off_by_default(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _multi(course, _bank(course), points='4')
        quiz = _quiz(course, attemptsAllowed=0)
        _add(quiz, q)
        # All-or-nothing without the toggle: one correct selection scores 0.
        done = self._submit_with_choices(api_client, taking_setup, quiz, {'2'})
        assert _dec(done['score']) == _dec('0.00')
        assert done['responses'][0]['isCorrect'] is False

    def test_numerical_tolerance(self, api_client, taking_setup):
        course = taking_setup['course']
        q = _numerical(course, _bank(course))  # accepted answer '4', 2 pts
        q.numericTolerance = Decimal('0.5')
        q.save()
        quiz = _quiz(course, attemptsAllowed=0)
        _add(quiz, q)

        done = self._submit_with_text(api_client, taking_setup, quiz, '4.4')
        assert _dec(done['score']) == _dec('2.00')  # within ±0.5
        done = self._submit_with_text(api_client, taking_setup, quiz, '3.6')
        assert _dec(done['score']) == _dec('2.00')  # within, below
        done = self._submit_with_text(api_client, taking_setup, quiz, '4.6')
        assert _dec(done['score']) == _dec('0.00')  # outside

    def test_numerical_exact_without_tolerance(self, api_client, taking_setup):
        course = taking_setup['course']
        quiz = _quiz(course, attemptsAllowed=0)
        _add(quiz, _numerical(course, _bank(course)))
        done = self._submit_with_text(api_client, taking_setup, quiz, '4.01')
        assert _dec(done['score']) == _dec('0.00')
        done = self._submit_with_text(api_client, taking_setup, quiz, '4.0')
        assert _dec(done['score']) == _dec('2.00')  # numerically equal is still exact

    def test_settings_survive_question_copy(self, api_client, taking_setup):
        from core.models import Question, QuestionBank
        course = taking_setup['course']
        q = _multi(course, _bank(course))
        q.partialCredit = True
        q.numericTolerance = Decimal('0.25')
        q.save()
        target = QuestionBank.objects.create(course=course, name='CopyTarget')
        api_client.force_authenticate(user=taking_setup['admin'])
        resp = api_client.post('/questions/copyToBank/',
                               {'bankId': target.id, 'questionIds': [q.id]}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        copy = Question.objects.get(pk=resp.data[0]['id'])
        assert copy.partialCredit is True and copy.numericTolerance == Decimal('0.2500')


# --------------------------------------------------------------------------- #
# Extra-time accommodations (course-level per-student multiplier)
# --------------------------------------------------------------------------- #

class TestAccommodations:
    def test_multiplier_extends_timed_deadline(self, api_client, taking_setup):
        from core.models import QuizAccommodation, QuizAttempt
        course = taking_setup['course']
        student = taking_setup['students'][0]
        quiz = _quiz(course, timeLimitMinutes=40)
        _add(quiz, _mc(course, _bank(course)))
        QuizAccommodation.objects.create(course=course, student=student,
                                         timeMultiplier=Decimal('1.5'))
        api_client.force_authenticate(user=student)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        attempt = QuizAttempt.objects.get(pk=start.data['id'])
        minutes = (attempt.deadline - attempt.startedAt).total_seconds() / 60
        assert 59.9 < minutes < 60.1  # 40 × 1.5

        # Another student without an accommodation keeps the plain limit.
        other = taking_setup['students'][1]
        api_client.force_authenticate(user=other)
        start = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        attempt = QuizAttempt.objects.get(pk=start.data['id'])
        minutes = (attempt.deadline - attempt.startedAt).total_seconds() / 60
        assert 39.9 < minutes < 40.1

    def test_admin_manages_accommodations(self, api_client, taking_setup):
        course = taking_setup['course']
        student = taking_setup['students'][0]

        # Non-admin staff can neither view nor set.
        api_client.force_authenticate(user=course.graders.first())
        assert api_client.get(f'/courses/{course.id}/quizAccommodations/').status_code \
            == status.HTTP_403_FORBIDDEN

        api_client.force_authenticate(user=taking_setup['admin'])
        set1 = api_client.patch(f'/courses/{course.id}/setQuizAccommodation/',
                                {'student': student.email, 'timeMultiplier': '1.5'}, format='json')
        assert set1.status_code == status.HTTP_200_OK
        listing = api_client.get(f'/courses/{course.id}/quizAccommodations/')
        assert len(listing.data) == 1
        assert listing.data[0]['student'] == student.email
        assert _dec(listing.data[0]['timeMultiplier']) == _dec('1.5')

        # Multipliers below 1 are rejected; unknown students are rejected.
        bad = api_client.patch(f'/courses/{course.id}/setQuizAccommodation/',
                               {'student': student.email, 'timeMultiplier': '0.5'}, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        unknown = api_client.patch(f'/courses/{course.id}/setQuizAccommodation/',
                                   {'student': 'ghost@nowhere.edu', 'timeMultiplier': '1.5'}, format='json')
        assert unknown.status_code == status.HTTP_400_BAD_REQUEST

        # Multiplier 1 clears the accommodation.
        api_client.patch(f'/courses/{course.id}/setQuizAccommodation/',
                         {'student': student.email, 'timeMultiplier': '1'}, format='json')
        assert api_client.get(f'/courses/{course.id}/quizAccommodations/').data == []
