# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Seed / reset the "QT · " test quizzes on a course for local quiz testing.

Everything created is prefixed ``QT · `` and a run first deletes the previous ``QT · ``
data, so it is idempotent and never touches your other course data.

    python manage.py seed_test_quizzes                  # rebuild the quizzes (clean slate)
    python manage.py seed_test_quizzes --attempts-only   # keep quizzes, just wipe the student's attempts
    python manage.py seed_test_quizzes --course-id 53 --student student_only@dev.edu
"""
import os
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import (
    Assignment, Course, Question, QuestionBank, Quiz, QuizAttempt,
    QuizQuestion, QuizQuestionGroup, Submission,
)

MARK = 'QT · '
DEFAULT_COURSE_ID = 53
DEFAULT_STUDENT = 'student_only@dev.edu'
DEFAULT_INSTRUCTOR = 'admin@example.com'


class Command(BaseCommand):
    help = "Seed/reset the 'QT · ' test quizzes on a course (and clear a student's attempts) for local testing."

    def add_arguments(self, parser):
        parser.add_argument('--course-id', type=int, default=DEFAULT_COURSE_ID,
                            help=f'Course to seed (default {DEFAULT_COURSE_ID}).')
        parser.add_argument('--course-name', default=None,
                            help='Select the course by name (with --course-period) instead of id — '
                                 'handy for the e2e demo course.')
        parser.add_argument('--course-period', default=None,
                            help='Course period, paired with --course-name.')
        parser.add_argument('--student', default=DEFAULT_STUDENT,
                            help=f'Student whose attempts to clear (default {DEFAULT_STUDENT}).')
        parser.add_argument('--attempts-only', action='store_true',
                            help="Don't rebuild the quizzes — only wipe the student's attempts on them.")
        parser.add_argument('--force', action='store_true',
                            help='Allow running when DEBUG is off (guarded by default).')

    def handle(self, *args, **opts):
        # Safety: only block when pointed at a real (production) database. Local dev uses
        # SQLite with no DB_HOSTNAME, so it runs freely.
        if 'DB_HOSTNAME' in os.environ and not opts['force']:
            raise CommandError('Refusing to run against a configured production database '
                               '(DB_HOSTNAME is set). Use --force to override.')

        if opts['course_name']:
            course = Course.objects.filter(name=opts['course_name'], period=opts['course_period']).first()
            if course is None:
                raise CommandError(f"No course named {opts['course_name']!r} / {opts['course_period']!r}.")
        else:
            course = Course.objects.filter(id=opts['course_id']).first()
            if course is None:
                raise CommandError(f"No course with id {opts['course_id']}.")
        student = course.students.filter(email=opts['student']).first()

        if opts['attempts_only']:
            self._clear_attempts(course, student)
        else:
            self._reseed(course, student)

    # ------------------------------------------------------------------ #

    def _clear_attempts(self, course, student):
        attempts = QuizAttempt.objects.filter(quiz__course=course, quiz__title__startswith=MARK)
        if student is not None:
            attempts = attempts.filter(student=student)
        count = attempts.count()
        attempts.delete()
        who = student.email if student is not None else 'all students'
        self.stdout.write(self.style.SUCCESS(f'Cleared {count} attempt(s) on QT quizzes for {who}.'))

    def _reseed(self, course, student):
        now = timezone.now()
        instructor = (course.courseAdmins.filter(email=DEFAULT_INSTRUCTOR).first()
                      or course.courseAdmins.first())
        if instructor is None:
            raise CommandError(f'Course {course.id} has no course admins to author the quizzes.')

        # Clear prior QT data (scoped to our marker; cascades away old attempts).
        Quiz.objects.filter(course=course, title__startswith=MARK).delete()
        QuestionBank.objects.filter(course=course, name__startswith=MARK).delete()
        Assignment.objects.filter(course=course, name__startswith=MARK).delete()

        bank = QuestionBank.objects.create(course=course, name=MARK + 'All Question Types', createdBy=instructor)

        def q(qtype, text, points='2', **kw):
            return Question.objects.create(course=course, bank=bank, questionType=qtype, text=text,
                                           points=Decimal(points), createdBy=instructor, **kw)

        def choices(question, items):
            for i, (t, correct) in enumerate(items):
                question.choices.create(text=t, isCorrect=correct, sortKey=i)

        mc = q('multiple_choice', 'What is `2 + 2`?')
        choices(mc, [('3', False), ('4', True), ('5', False), ('22', False)])
        ma = q('multiple_answers', 'Which of these are **prime**?')
        choices(ma, [('2', True), ('3', True), ('4', False), ('9', False)])
        tf = q('true_false', 'The Earth is flat.')
        choices(tf, [('True', False), ('False', True)])
        sa = q('short_answer', 'What is the capital of France?')
        choices(sa, [('Paris', True)])
        nu = q('numerical', 'What is the square root of 144?')
        choices(nu, [('12', True)])
        es = q('essay', 'Explain the difference between a **stack** and a **queue**.', points='5')
        code = q('code', 'Write a Python function `add(a, b)` that returns their sum.', points='5',
                 language='python', starterCode='def add(a, b):\n    # your code here\n    pass\n')

        ALL = [mc, ma, tf, sa, nu, es, code]
        AUTO = [mc, ma, tf, sa, nu]

        def make_quiz(title, questions, description='', groups=None, published=True, **kw):
            quiz = Quiz.objects.create(course=course, title=MARK + title, description=description,
                                       createdBy=instructor, isPublished=published, **kw)
            for i, question in enumerate(questions):
                QuizQuestion.objects.create(quiz=quiz, question=question, sortKey=i)
            for g in (groups or []):
                QuizQuestionGroup.objects.create(quiz=quiz, **g)
            return quiz

        # ---- standalone quizzes (the settings matrix) ----
        make_quiz('All question types', ALL,
                  description='One question of **every** type. Auto-graded types score on submit; '
                              'essay & code are saved and marked *pending grading*.',
                  showCorrectAnswers=True)
        make_quiz('Timed · sequential · 3 attempts', AUTO,
                  description='5-minute timer, **one question at a time**, no going back, shuffled. '
                              'Best of 3 attempts; pass at 70%.',
                  timeLimitMinutes=5, oneQuestionAtATime=True, allowBacktracking=False,
                  shuffleQuestions=True, attemptsAllowed=3, scoringPolicy='highest',
                  passingScore=Decimal('70'), passingScoreUnit='percent')
        make_quiz('Sequential · can go back', AUTO,
                  description='One question at a time, but you **can** navigate back.',
                  oneQuestionAtATime=True, allowBacktracking=True)
        make_quiz('Unlimited attempts · points pass', AUTO,
                  description='Unlimited attempts, pass at **6 points**. Scores show as soon as you submit.',
                  attemptsAllowed=0, passingScore=Decimal('6'), passingScoreUnit='points')
        make_quiz('Results sealed until close', AUTO,
                  description='Unlimited attempts, pass at **6 points**; scores and answers stay hidden '
                              'until the quiz closes (in 2 hours).',
                  attemptsAllowed=0, passingScore=Decimal('6'), passingScoreUnit='points',
                  sealResultsUntilClose=True, availableUntil=now + timedelta(hours=2))
        make_quiz('Random draw (2 from bank) + 1 fixed', [tf],
                  description='One fixed question, then **2 randomly drawn** from the bank (3 pts each). '
                              'Each attempt draws a different set.',
                  groups=[dict(bank=bank, name='Draw 2', pickCount=2, pointsPerQuestion=Decimal('3'))])
        make_quiz('Answers never shown', AUTO,
                  description='You get a score after submitting, but correct answers are **never** revealed.',
                  showCorrectAnswers=False)
        make_quiz('Essay · manual grading', [es],
                  description='A single **essay**, for staff manual-grading flows. Unlimited attempts; '
                              'pass at 3 points once graded.',
                  attemptsAllowed=0, passingScore=Decimal('3'), passingScoreUnit='points',
                  showCorrectAnswers=True)
        make_quiz('DRAFT — students should NOT see this', AUTO,
                  description='Unpublished draft. Only the instructor should see it.', published=False)

        # ---- attached quizzes (assignments in known states) ----
        def make_assignment(name, due=None, feedback=False):
            a = Assignment.objects.create(course=course, name=MARK + name,
                                          explanation='Seed assignment for quiz testing.', points=100,
                                          isReleased=True, isVisible=True, allowStudentUpload=True)
            if due is not None:
                a.uploadDueDate = due
            if feedback:
                a.feedbackReleased = True  # save() stamps feedbackReleasedAt
            a.save()
            return a

        a_open = make_assignment('Open assignment', due=now + timedelta(days=3))
        a_closed = make_assignment('Closed assignment (past due)', due=now - timedelta(days=1))
        a_submit = make_assignment('Assignment you submitted')
        a_feedback = make_assignment('Assignment with feedback released', due=now - timedelta(days=2), feedback=True)

        # Give the student a submission on a_submit so 'after_submission' opens (mute signals → no autograder).
        if student is not None and not a_submit.submissions.filter(students=student).exists():
            from factory.django import mute_signals  # dev-only dep; import lazily
            from django.db.models.signals import post_save
            with mute_signals(post_save):
                sub = Submission.objects.create(assignment=a_submit, questionText='', questionResponse='')
                sub.students.add(student)

        make_quiz('[Attached · during] open now, closes at deadline', AUTO, assignment=a_open,
                  assignmentTrigger='during', closeEvent='assignment_due', endAttemptsAtClose=True,
                  description='Attached to an **open** assignment: available now, closes at the deadline.')
        make_quiz('[Attached · after close] opens after the assignment closes', AUTO, assignment=a_closed,
                  assignmentTrigger='after_assignment',
                  description='Opens once the assignment deadline has passed.')
        make_quiz('[Attached · after submit] opens after you submit', AUTO, assignment=a_submit,
                  assignmentTrigger='after_submission', closeEvent='submission', closeOffsetMinutes=60,
                  endAttemptsAtClose=True,
                  description='Opens after you submit; closes 60 minutes after your submission.')
        make_quiz('[Attached · after feedback] opens after feedback', AUTO, assignment=a_feedback,
                  assignmentTrigger='after_feedback', closeEvent='feedback_released', closeOffsetMinutes=10080,
                  description='Opens once feedback is released; closes one week after.')
        make_quiz('[Attached · LOCKED] waiting for feedback', AUTO, assignment=a_open,
                  assignmentTrigger='after_feedback',
                  description='Open assignment but set to open **after feedback** (not released) — '
                              'should show LOCKED with a reason on the assignment card.')

        quizzes = Quiz.objects.filter(course=course, title__startswith=MARK)
        published = quizzes.filter(isPublished=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'Reseeded course {course.id} "{course.name} / {course.period}": '
            f'{quizzes.count()} quizzes ({published} published), '
            f'bank of {bank.questions.count()} question types, 4 assignments.'))
        self.stdout.write(f'  Instructor: {instructor.email}')
        self.stdout.write(f'  Student:    {student.email if student else "(not found — no submission created)"}')
        self.stdout.write('  Re-run with --attempts-only to just clear attempts and keep the same quizzes.')
