# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Shared builders for the quiz test files (test_quizzes / test_quiz_attempts /
test_generated_quizzes) — questions of every type, quizzes, and the AIService config
patches the AI-mocking helpers share."""
from decimal import Decimal


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


def _code(course, bank, points='5', language='r'):
    from core.models import Question
    return Question.objects.create(course=course, bank=bank, questionType='code',
                                   text='Write code that prints the mean.', points=Decimal(points),
                                   language=language)


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


def _mc_question(course, text="What is 2+2?", bank=None):
    """Create a saved multiple-choice Question (in a bank) with two choices."""
    from core.models import Question, QuestionBank
    if bank is None:
        bank, _ = QuestionBank.objects.get_or_create(course=course, name='Default Bank')
    q = Question.objects.create(course=course, bank=bank, questionType='multiple_choice', text=text)
    q.choices.create(text="3", isCorrect=False, sortKey=0)
    q.choices.create(text="4", isCorrect=True, sortKey=1)
    return q


def _enable_ai(monkeypatch):
    """Make AIService report configured + every feature enabled (no real provider in tests).
    The per-feature generate-method mocks stay in their test files — the two AI features
    mock different AIService methods."""
    monkeypatch.setattr('core.services.ai_service.AIService.is_configured', property(lambda self: True))
    monkeypatch.setattr('core.services.ai_service.AIService.is_globally_disabled', property(lambda self: False))
    monkeypatch.setattr('core.services.ai_service.AIService.is_feature_enabled', lambda self, key: True)
    monkeypatch.setattr('core.services.ai_service.AIService.record_usage', lambda *a, **kw: None)


def _feature_on(monkeypatch):
    """Creating a generated section requires the personalized_quiz_generation feature; tests
    run without an AI provider, so enable it explicitly where creation should succeed."""
    monkeypatch.setattr('core.services.ai_service.AIService.is_feature_enabled',
                        lambda self, key: True)
