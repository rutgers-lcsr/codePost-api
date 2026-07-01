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


# --------------------------------------------------------------------------- #
# Question / quiz builders
# --------------------------------------------------------------------------- #

def _bank(course):
    from core.models import QuestionBank
    bank, _ = QuestionBank.objects.get_or_create(course=course, name='Bank')
    return bank


def _mc(course, bank, points='2'):
    from core.models import Question
    q = Question.objects.create(course=course, bank=bank, questionType='multiple_choice',
                                text='2+2?', points=Decimal(points))
    q.choices.create(text='3', isCorrect=False, sortKey=0)
    q.choices.create(text='4', isCorrect=True, sortKey=1)
    return q


def _multi(course, bank, points='2'):
    from core.models import Question
    q = Question.objects.create(course=course, bank=bank, questionType='multiple_answers',
                                text='Pick the even numbers', points=Decimal(points))
    q.choices.create(text='2', isCorrect=True, sortKey=0)
    q.choices.create(text='3', isCorrect=False, sortKey=1)
    q.choices.create(text='4', isCorrect=True, sortKey=2)
    return q


def _short(course, bank, points='2'):
    from core.models import Question
    q = Question.objects.create(course=course, bank=bank, questionType='short_answer',
                                text='Capital of France?', points=Decimal(points))
    q.choices.create(text='Paris', isCorrect=True, sortKey=0)
    return q


def _numerical(course, bank, points='2'):
    from core.models import Question
    q = Question.objects.create(course=course, bank=bank, questionType='numerical',
                                text='2+2?', points=Decimal(points))
    q.choices.create(text='4', isCorrect=True, sortKey=0)
    return q


def _essay(course, bank, points='5'):
    from core.models import Question
    return Question.objects.create(course=course, bank=bank, questionType='essay',
                                   text='Explain recursion.', points=Decimal(points))


def _quiz(course, **kwargs):
    from core.models import Quiz
    opts = {'title': 'Quiz', 'isPublished': True}
    opts.update(kwargs)
    return Quiz.objects.create(course=course, **opts)


def _add(quiz, question, sortKey=0, points=None):
    from core.models import QuizQuestion
    return QuizQuestion.objects.create(quiz=quiz, question=question, sortKey=sortKey, pointsOverride=points)


def _dec(v):
    return Decimal(str(v))


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

    def test_random_draw_quiz_not_yet_takeable(self, api_client, taking_setup):
        from core.models import QuizQuestionGroup
        course = taking_setup['course']
        quiz = _quiz(course)
        bank = _bank(course)
        _add(quiz, _mc(course, bank))
        QuizQuestionGroup.objects.create(quiz=quiz, bank=bank, pickCount=1)
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.post('/quizAttempts/', {'quiz': quiz.id}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

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

    def test_available_quizzes_lists_only_takeable(self, api_client, taking_setup):
        from core.models import QuizQuestionGroup
        course = taking_setup['course']
        bank = _bank(course)
        takeable = _quiz(course, title='Takeable')
        _add(takeable, _mc(course, bank))
        _quiz(course, title='Draft', isPublished=False)            # unpublished → excluded
        draw = _quiz(course, title='Draw')                          # random-draw → excluded
        QuizQuestionGroup.objects.create(quiz=draw, bank=bank, pickCount=1)
        api_client.force_authenticate(user=taking_setup['students'][0])
        resp = api_client.get(f'/quizAttempts/availableQuizzes/?course={course.id}')
        assert resp.status_code == status.HTTP_200_OK
        titles = {q['title'] for q in resp.data}
        assert titles == {'Takeable'}
