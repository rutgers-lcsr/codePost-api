# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for the Quizzes feature (Phase 1: authoring).

Covers authoring CRUD, copy/move questions between banks, attaching a quiz to an assignment,
staff-only permissions, Canvas QTI import, AI suggestions, and the cross-semester
refresh loop (regenerate from an existing question + accept-in-place).
"""
import io
import zipfile

import factory
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_save
from rest_framework import status


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def quiz_setup(db):
    from core.tests.factories import CourseFactory, AdminFactory

    with factory.django.mute_signals(post_save):
        course = CourseFactory(name="cos333", period="s2026", organization__name="Princeton")

    assignment = course.assignments.first()
    return {
        'course': course,
        'assignment': assignment,
        'admin': course.courseAdmins.first(),
        'grader': course.graders.first(),
        'student': course.students.first(),
        # A user who is not enrolled in the course at all.
        'outsider': AdminFactory(course='other', organization=course.organization, count=99),
    }


# Shared question/quiz builders live in quiz_helpers (used by all three quiz test files).
from core.tests.views.quiz_helpers import _enable_ai, _mc_question  # noqa: E402


def _canvas_zip_bytes():
    """A minimal Canvas QTI export with MC, T/F, short-answer, essay, and one unsupported type."""
    assessment = """<?xml version="1.0"?>
<questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2">
 <assessment ident="a1" title="Week 1 Quiz">
  <section ident="root">
   <item ident="q_mc" title="MC">
    <itemmetadata><qtimetadata>
      <qtimetadatafield><fieldlabel>question_type</fieldlabel><fieldentry>multiple_choice_question</fieldentry></qtimetadatafield>
      <qtimetadatafield><fieldlabel>points_possible</fieldlabel><fieldentry>2.0</fieldentry></qtimetadatafield>
    </qtimetadata></itemmetadata>
    <presentation>
      <material><mattext texttype="text/html">What is 2+2?</mattext></material>
      <response_lid ident="r1"><render_choice>
        <response_label ident="A"><material><mattext>3</mattext></material></response_label>
        <response_label ident="B"><material><mattext>4</mattext></material></response_label>
      </render_choice></response_lid>
    </presentation>
    <resprocessing><respcondition><conditionvar><varequal respident="r1">B</varequal></conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar></respcondition></resprocessing>
   </item>
   <item ident="q_sa" title="SA">
    <itemmetadata><qtimetadata>
      <qtimetadatafield><fieldlabel>question_type</fieldlabel><fieldentry>short_answer_question</fieldentry></qtimetadatafield>
    </qtimetadata></itemmetadata>
    <presentation><material><mattext>Capital of France?</mattext></material>
      <response_lid ident="r1"><render_fib><response_label ident="x"/></render_fib></response_lid></presentation>
    <resprocessing><respcondition><conditionvar><varequal respident="r1">Paris</varequal></conditionvar>
      <setvar action="Set" varname="SCORE">100</setvar></respcondition></resprocessing>
   </item>
   <item ident="q_essay" title="Essay">
    <itemmetadata><qtimetadata><qtimetadatafield><fieldlabel>question_type</fieldlabel><fieldentry>essay_question</fieldentry></qtimetadatafield></qtimetadata></itemmetadata>
    <presentation><material><mattext>Explain recursion.</mattext></material></presentation>
   </item>
   <item ident="q_match" title="Matching">
    <itemmetadata><qtimetadata><qtimetadatafield><fieldlabel>question_type</fieldlabel><fieldentry>matching_question</fieldentry></qtimetadatafield></qtimetadata></itemmetadata>
    <presentation><material><mattext>Match.</mattext></material></presentation>
   </item>
  </section>
 </assessment>
</questestinterop>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('imsmanifest.xml', '<?xml version="1.0"?><manifest/>')
        zf.writestr('a1/a1.xml', assessment)
        zf.writestr('a1/assessment_meta.xml', '<quiz title="Week 1 Quiz"/>')
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Authoring CRUD + permissions
# --------------------------------------------------------------------------- #

class TestAuthoringCRUD:
    def test_create_bank_and_question_with_nested_choices(self, api_client, quiz_setup):
        from core.models import Question
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']

        bank_resp = api_client.post('/questionBanks/', {'course': course.id, 'name': 'Midterm Pool'}, format='json')
        assert bank_resp.status_code == status.HTTP_201_CREATED
        bank_id = bank_resp.data['id']

        q_resp = api_client.post('/questions/', {
            'course': course.id,
            'bank': bank_id,
            'questionType': 'multiple_choice',
            'text': 'Pick the prime.',
            'points': 3,
            'choices': [
                {'text': '4', 'isCorrect': False, 'sortKey': 0},
                {'text': '7', 'isCorrect': True, 'sortKey': 1},
            ],
        }, format='json')
        assert q_resp.status_code == status.HTTP_201_CREATED

        question = Question.objects.get(id=q_resp.data['id'])
        assert question.choices.count() == 2
        assert question.choices.filter(isCorrect=True).first().text == '7'
        assert question.createdBy == quiz_setup['admin']
        assert question.bank_id == bank_id

    def test_copy_question_to_another_bank(self, api_client, quiz_setup):
        from core.models import QuestionBank
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']
        b1 = QuestionBank.objects.create(course=course, name='Bank A')
        b2 = QuestionBank.objects.create(course=course, name='Bank B')
        q = _mc_question(course, text='Sky is blue.', bank=b1)

        resp = api_client.post('/questions/copyToBank/',
                               {'questionIds': [q.id], 'bankId': b2.id}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        assert b1.questions.count() == 1        # original stays in Bank A
        assert b2.questions.count() == 1        # an independent copy landed in Bank B
        copy = b2.questions.first()
        assert copy.id != q.id
        assert copy.text == 'Sky is blue.'
        assert copy.choices.count() == q.choices.count()

    def test_move_question_to_another_bank(self, api_client, quiz_setup):
        from core.models import QuestionBank, Question
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']
        b1 = QuestionBank.objects.create(course=course, name='Bank A')
        b2 = QuestionBank.objects.create(course=course, name='Bank B')
        q = _mc_question(course, bank=b1)

        resp = api_client.post('/questions/moveToBank/',
                               {'questionIds': [q.id], 'bankId': b2.id}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert Question.objects.get(id=q.id).bank_id == b2.id   # re-pointed, not copied
        assert b1.questions.count() == 0

    def test_delete_bank_in_use_blocks_then_force(self, api_client, quiz_setup):
        from core.models import QuestionBank, Quiz, QuizQuestion, Question
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']
        bank = QuestionBank.objects.create(course=course, name='Used')
        q = _mc_question(course, bank=bank)
        quiz = Quiz.objects.create(course=course, title='Q1')
        QuizQuestion.objects.create(quiz=quiz, question=q)

        # In use → 409, bank kept, impacted quiz listed.
        resp = api_client.delete(f'/questionBanks/{bank.id}/')
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert any(iq['id'] == quiz.id for iq in resp.data['impactedQuizzes'])
        assert QuestionBank.objects.filter(id=bank.id).exists()

        # Force → deletes bank + its questions, detaching them from the quiz.
        resp = api_client.delete(f'/questionBanks/{bank.id}/?force=true')
        assert resp.status_code == status.HTTP_200_OK
        assert not QuestionBank.objects.filter(id=bank.id).exists()
        assert not Question.objects.filter(id=q.id).exists()
        assert not QuizQuestion.objects.filter(quiz=quiz, question_id=q.id).exists()

    def test_non_staff_cannot_create_question(self, api_client, quiz_setup):
        from core.models import QuestionBank
        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='B')
        api_client.force_authenticate(user=quiz_setup['student'])
        resp = api_client.post('/questions/', {
            'course': quiz_setup['course'].id, 'bank': bank.id, 'questionType': 'essay', 'text': 'x',
        }, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_course_questionBanks_list_is_staff_only(self, api_client, quiz_setup):
        from core.models import QuestionBank
        QuestionBank.objects.create(course=quiz_setup['course'], name='Bank A')
        url = f"/courses/{quiz_setup['course'].id}/questionBanks/"

        api_client.force_authenticate(user=quiz_setup['grader'])
        assert api_client.get(url).status_code == status.HTTP_200_OK

        api_client.force_authenticate(user=quiz_setup['student'])
        assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN

    def test_archived_course_blocks_edits(self, api_client, quiz_setup):
        from core.models import QuestionBank
        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='Bank A')
        quiz_setup['course'].archived = True
        quiz_setup['course'].save()

        api_client.force_authenticate(user=quiz_setup['admin'])
        resp = api_client.patch(f'/questionBanks/{bank.id}/', {'name': 'Renamed'}, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestQuizAuthoring:
    def test_create_quiz_attach_to_assignment_and_add_question(self, api_client, quiz_setup):
        from core.models import Quiz
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']
        assignment = quiz_setup['assignment']

        quiz_resp = api_client.post('/quizzes/', {'course': course.id, 'title': 'Quiz 1'}, format='json')
        assert quiz_resp.status_code == status.HTTP_201_CREATED
        quiz_id = quiz_resp.data['id']

        # Attach to an existing assignment.
        patch = api_client.patch(f'/quizzes/{quiz_id}/', {'assignment': assignment.id}, format='json')
        assert patch.status_code == status.HTTP_200_OK
        assert Quiz.objects.get(id=quiz_id).assignment_id == assignment.id

        # Add a question to the quiz.
        question = _mc_question(course)
        qq = api_client.post('/quizQuestions/', {'quiz': quiz_id, 'question': question.id, 'sortKey': 0}, format='json')
        assert qq.status_code == status.HTTP_201_CREATED

        # The assignment exposes its attached quizzes.
        listing = api_client.get(f'/assignments/{assignment.id}/quizzes/')
        assert listing.status_code == status.HTTP_200_OK
        assert any(q['id'] == quiz_id for q in listing.data)
        the_quiz = next(q for q in listing.data if q['id'] == quiz_id)
        assert len(the_quiz['quizQuestions']) == 1

    def test_quiz_settings_defaults_and_roundtrip(self, api_client, quiz_setup):
        from core.models import Quiz
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']

        resp = api_client.post('/quizzes/', {'course': course.id, 'title': 'Settings'}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        # Defaults.
        assert resp.data['assignmentTrigger'] == 'during'
        assert resp.data['attemptsAllowed'] == 1
        assert resp.data['isPublished'] is False
        assert resp.data['showCorrectAnswers'] is True
        assert resp.data['sealResultsUntilClose'] is False
        assert resp.data['timeLimitMinutes'] is None
        assert resp.data['passingScoreUnit'] == 'percent'
        assert resp.data['oneQuestionAtATime'] is False
        assert resp.data['allowBacktracking'] is True
        quiz_id = resp.data['id']

        patch = api_client.patch(f'/quizzes/{quiz_id}/', {
            'assignmentTrigger': 'after_feedback',
            'availableFrom': '2026-09-01T09:00:00Z',
            'availableUntil': '2026-09-08T23:59:00Z',
            'timeLimitMinutes': 30,
            'attemptsAllowed': 0,
            'shuffleQuestions': True,
            'oneQuestionAtATime': True,
            'allowBacktracking': False,
            'showCorrectAnswers': True,
            'sealResultsUntilClose': True,
            'passingScore': '70.00',
            'isPublished': True,
        }, format='json')
        assert patch.status_code == status.HTTP_200_OK

        quiz = Quiz.objects.get(id=quiz_id)
        assert quiz.assignmentTrigger == 'after_feedback'
        assert quiz.timeLimitMinutes == 30
        assert quiz.attemptsAllowed == 0
        assert quiz.shuffleQuestions is True
        assert quiz.oneQuestionAtATime is True
        assert quiz.allowBacktracking is False
        assert quiz.showCorrectAnswers is True
        assert quiz.sealResultsUntilClose is True
        assert str(quiz.passingScore) == '70.00'
        assert quiz.isPublished is True
        assert quiz.availableFrom is not None and quiz.availableUntil is not None

    def test_seal_results_requires_a_close(self, api_client, quiz_setup):
        # Holding results until close on a quiz that never closes would hide them forever.
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']
        # Standalone quiz with no end date → rejected.
        bad = api_client.post('/quizzes/', {
            'course': course.id, 'title': 'Sealed', 'sealResultsUntilClose': True,
        }, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        # With a close (availableUntil) it's allowed.
        ok = api_client.post('/quizzes/', {
            'course': course.id, 'title': 'Sealed OK', 'sealResultsUntilClose': True,
            'availableUntil': '2026-12-01T00:00:00Z',
        }, format='json')
        assert ok.status_code == status.HTTP_201_CREATED

    def test_quiz_availability_window_must_be_ordered(self, api_client, quiz_setup):
        from core.models import Quiz
        api_client.force_authenticate(user=quiz_setup['admin'])
        quiz = Quiz.objects.create(course=quiz_setup['course'], title='Window')

        resp = api_client.patch(f'/quizzes/{quiz.id}/', {
            'availableFrom': '2026-09-08T00:00:00Z',
            'availableUntil': '2026-09-01T00:00:00Z',
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_quiz_questions_action_lists_memberships_in_order(self, api_client, quiz_setup):
        from core.models import Quiz
        api_client.force_authenticate(user=quiz_setup['admin'])
        course = quiz_setup['course']
        quiz = Quiz.objects.create(course=course, title='Ordered')
        first = _mc_question(course, text='first')
        second = _mc_question(course, text='second', bank=first.bank)

        # Add out of insertion order; the action should return them sorted by sortKey.
        api_client.post('/quizQuestions/', {'quiz': quiz.id, 'question': second.id, 'sortKey': 1}, format='json')
        api_client.post('/quizQuestions/', {'quiz': quiz.id, 'question': first.id, 'sortKey': 0}, format='json')

        resp = api_client.get(f'/quizzes/{quiz.id}/questions/')
        assert resp.status_code == status.HTTP_200_OK
        assert [m['question'] for m in resp.data] == [first.id, second.id]

    def test_passing_score_percent_bounded_but_points_unbounded(self, api_client, quiz_setup):
        from core.models import Quiz
        api_client.force_authenticate(user=quiz_setup['admin'])
        quiz = Quiz.objects.create(course=quiz_setup['course'], title='Pass')

        # Percent (the default): above 100 is rejected.
        over = api_client.patch(f'/quizzes/{quiz.id}/', {'passingScore': '150.00'}, format='json')
        assert over.status_code == status.HTTP_400_BAD_REQUEST

        # Negative is always rejected.
        neg = api_client.patch(f'/quizzes/{quiz.id}/', {'passingScore': '-1.00'}, format='json')
        assert neg.status_code == status.HTTP_400_BAD_REQUEST

        # Points unit: an absolute threshold above 100 is allowed and round-trips.
        ok = api_client.patch(f'/quizzes/{quiz.id}/', {
            'passingScore': '150.00', 'passingScoreUnit': 'points',
        }, format='json')
        assert ok.status_code == status.HTTP_200_OK
        quiz.refresh_from_db()
        assert quiz.passingScoreUnit == 'points'
        assert str(quiz.passingScore) == '150.00'


# --------------------------------------------------------------------------- #
# Canvas QTI import
# --------------------------------------------------------------------------- #

class TestCanvasImport:
    def test_import_task_creates_questions_and_quiz(self, quiz_setup):
        from core.models import QuizImportJob, Question, Quiz
        from core.tasks import import_quiz_qti

        job = QuizImportJob.objects.create(
            course=quiz_setup['course'], createdBy=quiz_setup['admin'],
            file=SimpleUploadedFile('export.zip', _canvas_zip_bytes(), content_type='application/zip'),
        )
        import_quiz_qti(job.id, import_quizzes=True)
        job.refresh_from_db()

        assert job.status == 'completed'
        assert job.createdQuestionCount == 3      # MC, SA, essay (matching skipped)
        assert job.createdQuizCount == 1
        assert any(s['reason'].startswith('unsupported') for s in job.summary['skipped'])

        # Questions landed in the target bank, tagged as imported.
        assert job.targetBank is not None
        assert job.targetBank.questions.count() == 3
        assert Question.objects.filter(course=quiz_setup['course'], source='imported').count() == 3

        quiz = Quiz.objects.get(course=quiz_setup['course'], source='imported')
        assert quiz.title == 'Week 1 Quiz'
        assert quiz.quizQuestions.count() == 3

    def test_import_is_bank_only_by_default(self, quiz_setup):
        """Without import_quizzes, the export's questions are imported but no quiz is made."""
        from core.models import QuizImportJob, Question, Quiz
        from core.tasks import import_quiz_qti

        job = QuizImportJob.objects.create(
            course=quiz_setup['course'], createdBy=quiz_setup['admin'],
            file=SimpleUploadedFile('export.zip', _canvas_zip_bytes(), content_type='application/zip'),
        )
        import_quiz_qti(job.id)
        job.refresh_from_db()

        assert job.status == 'completed'
        assert job.createdQuestionCount == 3
        assert job.createdQuizCount == 0
        assert Question.objects.filter(course=quiz_setup['course'], source='imported').count() == 3
        assert not Quiz.objects.filter(course=quiz_setup['course'], source='imported').exists()

    def test_import_endpoint_runs_job(self, api_client, quiz_setup, monkeypatch):
        from core.tasks import import_quiz_qti

        class _Eager:
            id = 'eager-task'

        def _run(job_id, **kwargs):
            import_quiz_qti(job_id, **kwargs)
            return _Eager()

        monkeypatch.setattr('core.tasks.import_quiz_qti.delay', _run)

        api_client.force_authenticate(user=quiz_setup['admin'])
        upload = SimpleUploadedFile('export.zip', _canvas_zip_bytes(), content_type='application/zip')
        resp = api_client.post('/quizImportJobs/',
                               {'course': quiz_setup['course'].id, 'file': upload, 'bankName': 'Imported'},
                               format='multipart')
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert resp.data['status'] == 'completed'
        assert resp.data['createdQuestionCount'] == 3

    def test_import_endpoint_forbidden_for_student(self, api_client, quiz_setup):
        api_client.force_authenticate(user=quiz_setup['student'])
        upload = SimpleUploadedFile('export.zip', _canvas_zip_bytes(), content_type='application/zip')
        resp = api_client.post('/quizImportJobs/',
                               {'course': quiz_setup['course'].id, 'file': upload},
                               format='multipart')
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_html_stems_are_cleaned(self, quiz_setup):
        """Canvas HTML stems (texttype=text/html) are stripped to readable text."""
        from core.models import QuizImportJob, Question
        from core.tasks import import_quiz_qti

        item = """<?xml version="1.0"?>
<questestinterop xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2">
 <assessment ident="a1" title="HTML Quiz"><section ident="root">
  <item ident="q_html" title="HTML">
   <itemmetadata><qtimetadata>
     <qtimetadatafield><fieldlabel>question_type</fieldlabel><fieldentry>essay_question</fieldentry></qtimetadatafield>
   </qtimetadata></itemmetadata>
   <presentation><material><mattext texttype="text/html">&lt;div&gt;&lt;span&gt;What is &lt;b&gt;recursion&lt;/b&gt;?&lt;/span&gt;&lt;/div&gt;</mattext></material></presentation>
  </item>
 </section></assessment>
</questestinterop>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('imsmanifest.xml', '<?xml version="1.0"?><manifest/>')
            zf.writestr('a1/a1.xml', item)

        job = QuizImportJob.objects.create(
            course=quiz_setup['course'], createdBy=quiz_setup['admin'],
            file=SimpleUploadedFile('export.zip', buf.getvalue(), content_type='application/zip'),
        )
        import_quiz_qti(job.id)
        job.refresh_from_db()

        assert job.status == 'completed'
        q = Question.objects.get(course=quiz_setup['course'], source='imported')
        assert '<' not in q.text and '>' not in q.text
        assert q.text == 'What is recursion?'

    def test_duplicate_content_collapsed(self, quiz_setup):
        """The same question in a quiz file and a bank file (different idents) imports once."""
        from core.models import QuizImportJob, Question
        from core.tasks import import_quiz_qti

        def _item(ident):
            return (f'<item ident="{ident}" title="x"><itemmetadata><qtimetadata>'
                    '<qtimetadatafield><fieldlabel>question_type</fieldlabel>'
                    '<fieldentry>essay_question</fieldentry></qtimetadatafield></qtimetadata></itemmetadata>'
                    '<presentation><material><mattext>Explain recursion.</mattext></material></presentation></item>')
        ns = 'xmlns="http://www.imsglobal.org/xsd/ims_qtiasiv1p2"'
        quiz_xml = f'<questestinterop {ns}><assessment ident="a1" title="Quiz"><section ident="s">{_item("quiz_q")}</section></assessment></questestinterop>'
        bank_xml = f'<questestinterop {ns}><objectbank ident="b1">{_item("bank_q")}</objectbank></questestinterop>'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('imsmanifest.xml', '<manifest/>')
            zf.writestr('a1/a1.xml', quiz_xml)
            zf.writestr('non_cc_assessments/b1.xml', bank_xml)

        job = QuizImportJob.objects.create(
            course=quiz_setup['course'], createdBy=quiz_setup['admin'],
            file=SimpleUploadedFile('export.zip', buf.getvalue(), content_type='application/zip'),
        )
        import_quiz_qti(job.id)
        assert Question.objects.filter(course=quiz_setup['course'], source='imported').count() == 1

    def test_reimport_into_same_bank_is_idempotent(self, quiz_setup):
        from core.models import QuizImportJob, QuestionBank, Question
        from core.tasks import import_quiz_qti
        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='Pool')

        def _run():
            job = QuizImportJob.objects.create(
                course=quiz_setup['course'], createdBy=quiz_setup['admin'], targetBank=bank,
                file=SimpleUploadedFile('export.zip', _canvas_zip_bytes(), content_type='application/zip'),
            )
            import_quiz_qti(job.id)
            job.refresh_from_db()
            return job

        first = _run()
        count_after_first = Question.objects.filter(course=quiz_setup['course']).count()
        assert first.createdQuestionCount == 3

        second = _run()
        # Nothing new created; all reused.
        assert Question.objects.filter(course=quiz_setup['course']).count() == count_after_first
        assert second.createdQuestionCount == 0
        assert second.summary['reused_questions'] == 3


# --------------------------------------------------------------------------- #
# AI suggestions
# --------------------------------------------------------------------------- #

def _mock_ai(monkeypatch, json_text):
    """Make AIService report configured/enabled and return canned JSON (no real API)."""
    from core.services.ai_service import GenerationResult

    async def mock_generate(self, assignment=None, num_questions=5, question_types=None,
                            source_question=None, instructions=''):
        return GenerationResult(text=json_text, success=True, input_tokens=10, output_tokens=20)

    monkeypatch.setattr('core.services.ai_service.AIService.generate_quiz_questions', mock_generate)
    _enable_ai(monkeypatch)


class TestAISuggestions:
    def test_generate_task_creates_pending_suggestions(self, quiz_setup, monkeypatch):
        from core.models import SuggestedQuizQuestion
        from core.tasks import generate_quiz_question_suggestions

        _mock_ai(monkeypatch, """[
          {"type": "multiple_choice", "text": "Q1?", "points": 2,
           "choices": [{"text": "a", "is_correct": true}, {"text": "b", "is_correct": false}]},
          {"type": "essay", "text": "Explain.", "points": 5}
        ]""")

        generate_quiz_question_suggestions(
            requested_by_id=quiz_setup['admin'].id, assignment_id=quiz_setup['assignment'].id)

        pending = SuggestedQuizQuestion.objects.filter(assignment=quiz_setup['assignment'], status='pending')
        assert pending.count() == 2
        assert pending.filter(questionType='essay').exists()
        mc = pending.get(questionType='multiple_choice')
        assert mc.choicesData[0]['isCorrect'] is True

    def test_feature_flag_gates_generation(self, quiz_setup, monkeypatch):
        from core.models import SuggestedQuizQuestion
        from core.tasks import generate_quiz_question_suggestions

        _mock_ai(monkeypatch, "[]")
        monkeypatch.setattr('core.services.ai_service.AIService.is_feature_enabled', lambda self, key: False)

        generate_quiz_question_suggestions(
            requested_by_id=quiz_setup['admin'].id, assignment_id=quiz_setup['assignment'].id)
        assert not SuggestedQuizQuestion.objects.filter(assignment=quiz_setup['assignment']).exists()

    def test_generate_endpoint_permissions(self, api_client, quiz_setup, monkeypatch):
        monkeypatch.setattr('core.tasks.generate_quiz_question_suggestions.delay',
                            lambda *a, **kw: type('R', (), {'id': 'x'})())
        url = f"/assignments/{quiz_setup['assignment'].id}/generateQuizQuestions/"

        api_client.force_authenticate(user=quiz_setup['grader'])
        assert api_client.post(url, format='json').status_code == status.HTTP_202_ACCEPTED

        api_client.force_authenticate(user=quiz_setup['student'])
        assert api_client.post(url, format='json').status_code == status.HTTP_403_FORBIDDEN

    def test_accept_creates_question_authored_by_instructor(self, api_client, quiz_setup):
        from core.models import SuggestedQuizQuestion, Question, QuestionBank
        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='Target')
        suggestion = SuggestedQuizQuestion.objects.create(
            assignment=quiz_setup['assignment'], questionType='multiple_choice', text='Q?', points=2,
            choicesData=[{'text': 'a', 'isCorrect': True}, {'text': 'b', 'isCorrect': False}], status='pending')

        api_client.force_authenticate(user=quiz_setup['grader'])
        resp = api_client.post(f'/suggestedQuizQuestions/{suggestion.id}/accept/',
                               {'bankId': bank.id}, format='json')
        assert resp.status_code == status.HTTP_201_CREATED

        question = Question.objects.get(id=resp.data['id'])
        assert question.bank_id == bank.id                   # filed into the chosen bank
        assert question.createdBy == quiz_setup['grader']   # instructor is the author
        assert question.source == 'ai'                       # staff-internal provenance
        assert question.choices.filter(isCorrect=True).first().text == 'a'

        suggestion.refresh_from_db()
        assert suggestion.status == 'accepted'
        assert suggestion.acceptedQuestion_id == question.id

    def test_reject_suggestion(self, api_client, quiz_setup):
        from core.models import SuggestedQuizQuestion
        suggestion = SuggestedQuizQuestion.objects.create(
            assignment=quiz_setup['assignment'], questionType='essay', text='Q?', status='pending')
        api_client.force_authenticate(user=quiz_setup['grader'])
        resp = api_client.post(f'/suggestedQuizQuestions/{suggestion.id}/reject/', format='json')
        assert resp.status_code == status.HTTP_200_OK
        suggestion.refresh_from_db()
        assert suggestion.status == 'rejected'

    def test_student_cannot_see_suggestions(self, api_client, quiz_setup):
        from core.models import SuggestedQuizQuestion
        suggestion = SuggestedQuizQuestion.objects.create(
            assignment=quiz_setup['assignment'], questionType='essay', text='Q?', status='pending')
        api_client.force_authenticate(user=quiz_setup['student'])
        assert api_client.get(f'/suggestedQuizQuestions/{suggestion.id}/').status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# Cross-semester refresh loop
# --------------------------------------------------------------------------- #

class TestRefreshLoop:
    def test_regenerate_seeds_source_question(self, quiz_setup, monkeypatch):
        from core.models import SuggestedQuizQuestion
        from core.tasks import generate_quiz_question_suggestions

        question = _mc_question(quiz_setup['course'], text="Old question")
        _mock_ai(monkeypatch, """[{"type": "multiple_choice", "text": "Improved question",
          "choices": [{"text": "4", "is_correct": true}]}]""")

        generate_quiz_question_suggestions(
            requested_by_id=quiz_setup['admin'].id, source_question_id=question.id, num_questions=1)

        suggestion = SuggestedQuizQuestion.objects.get(sourceQuestion=question)
        assert suggestion.text == "Improved question"
        assert suggestion.status == 'pending'

    def test_regeneration_endpoint_returns_pending_and_replaces(self, api_client, quiz_setup, monkeypatch):
        from core.models import SuggestedQuizQuestion
        from core.tasks import generate_quiz_question_suggestions

        question = _mc_question(quiz_setup['course'], text="Old question")
        _mock_ai(monkeypatch, """[{"type": "multiple_choice", "text": "v1",
          "choices": [{"text": "a", "is_correct": true}]}]""")
        generate_quiz_question_suggestions(
            requested_by_id=quiz_setup['admin'].id, source_question_id=question.id, num_questions=1)

        # The fetch endpoint surfaces the pending refresh suggestion for review.
        api_client.force_authenticate(user=quiz_setup['grader'])
        resp = api_client.get(f'/questions/{question.id}/regenerationSuggestions/')
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1 and resp.data[0]['text'] == 'v1'
        # choicesData must serialize as a real JSON array (not a Python-repr string),
        # otherwise the frontend can't render the proposed choices.
        cd = resp.data[0]['choicesData']
        assert isinstance(cd, list) and cd[0]['text'] == 'a' and cd[0]['isCorrect'] is True

        # Re-regenerating replaces the prior pending refresh (single batch).
        _mock_ai(monkeypatch, """[{"type": "multiple_choice", "text": "v2",
          "choices": [{"text": "b", "is_correct": true}]}]""")
        generate_quiz_question_suggestions(
            requested_by_id=quiz_setup['admin'].id, source_question_id=question.id, num_questions=1)
        pending = SuggestedQuizQuestion.objects.filter(sourceQuestion=question, status='pending')
        assert pending.count() == 1 and pending.first().text == 'v2'

    def test_accept_refresh_updates_question_in_place(self, api_client, quiz_setup):
        from core.models import SuggestedQuizQuestion, QuestionBank

        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='Pool')
        question = _mc_question(quiz_setup['course'], text="Old text", bank=bank)
        question.createdBy = quiz_setup['admin']
        question.save()

        suggestion = SuggestedQuizQuestion.objects.create(
            sourceQuestion=question, questionType='multiple_choice', text='Updated text', points=3,
            choicesData=[{'text': '5', 'isCorrect': True}], status='pending')

        api_client.force_authenticate(user=quiz_setup['grader'])
        resp = api_client.post(f'/suggestedQuizQuestions/{suggestion.id}/accept/', format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data['id'] == question.id   # same question, updated in place

        question.refresh_from_db()
        assert question.text == 'Updated text'
        assert question.createdBy == quiz_setup['admin']        # original author preserved
        assert question.bank_id == bank.id  # bank preserved
        assert question.choices.count() == 1
        assert question.choices.first().text == '5'

        suggestion.refresh_from_db()
        assert suggestion.acceptedQuestion_id == question.id


# --------------------------------------------------------------------------- #
# Question groups (random draws from a bank)
# --------------------------------------------------------------------------- #

class TestQuestionGroups:
    def _quiz_and_bank(self, course):
        from core.models import Quiz, QuestionBank
        quiz = Quiz.objects.create(course=course, title='Quiz 1')
        bank = QuestionBank.objects.create(course=course, name='Pool')
        return quiz, bank

    def test_create_group_appears_on_quiz(self, api_client, quiz_setup):
        from core.models import QuizQuestionGroup
        quiz, bank = self._quiz_and_bank(quiz_setup['course'])
        api_client.force_authenticate(user=quiz_setup['admin'])

        resp = api_client.post('/quizQuestionGroups/', {
            'quiz': quiz.id, 'bank': bank.id, 'name': 'Pick 3', 'pickCount': 3, 'pointsPerQuestion': 5,
        }, format='json')
        assert resp.status_code == status.HTTP_201_CREATED
        assert QuizQuestionGroup.objects.filter(quiz=quiz, bank=bank, pickCount=3).exists()

        # The group is exposed on the quiz via the course quizzes action.
        listing = api_client.get(f"/courses/{quiz_setup['course'].id}/quizzes/")
        the_quiz = next(q for q in listing.data if q['id'] == quiz.id)
        assert len(the_quiz['questionGroups']) == 1
        assert the_quiz['questionGroups'][0]['pickCount'] == 3

    def test_group_bank_must_match_quiz_course(self, api_client, quiz_setup):
        import factory
        from django.db.models.signals import post_save
        from core.models import QuestionBank
        from core.tests.factories import CourseFactory
        quiz, _ = self._quiz_and_bank(quiz_setup['course'])
        with factory.django.mute_signals(post_save):
            other_course = CourseFactory(name='other', period='s2026', organization=quiz_setup['course'].organization)
        foreign_bank = QuestionBank.objects.create(course=other_course, name='Foreign')

        api_client.force_authenticate(user=quiz_setup['admin'])
        resp = api_client.post('/quizQuestionGroups/', {
            'quiz': quiz.id, 'bank': foreign_bank.id, 'pickCount': 2,
        }, format='json')
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_staff_cannot_create_group(self, api_client, quiz_setup):
        quiz, bank = self._quiz_and_bank(quiz_setup['course'])
        api_client.force_authenticate(user=quiz_setup['student'])
        resp = api_client.post('/quizQuestionGroups/', {
            'quiz': quiz.id, 'bank': bank.id, 'pickCount': 2,
        }, format='json')
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# Bank ↔ assignment auto-linking
# --------------------------------------------------------------------------- #

class TestBankAssignments:
    def _bank_with_question(self, course):
        from core.models import QuestionBank
        bank = QuestionBank.objects.create(course=course, name='Pool')
        q = _mc_question(course, bank=bank)
        return bank, q

    def test_autolink_when_question_added_to_attached_quiz(self, quiz_setup):
        from core.models import Quiz, QuizQuestion
        bank, q = self._bank_with_question(quiz_setup['course'])
        quiz = Quiz.objects.create(course=quiz_setup['course'], title='Q1', assignment=quiz_setup['assignment'])
        QuizQuestion.objects.create(quiz=quiz, question=q)
        assert quiz_setup['assignment'] in bank.assignments.all()

    def test_autolink_when_group_added_to_attached_quiz(self, quiz_setup):
        from core.models import Quiz, QuestionBank, QuizQuestionGroup
        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='Pool')
        quiz = Quiz.objects.create(course=quiz_setup['course'], title='Q1', assignment=quiz_setup['assignment'])
        QuizQuestionGroup.objects.create(quiz=quiz, bank=bank, pickCount=2)
        assert quiz_setup['assignment'] in bank.assignments.all()

    def test_autolink_when_quiz_later_attached(self, quiz_setup):
        from core.models import Quiz, QuizQuestion
        bank, q = self._bank_with_question(quiz_setup['course'])
        quiz = Quiz.objects.create(course=quiz_setup['course'], title='Q1')  # no assignment yet
        QuizQuestion.objects.create(quiz=quiz, question=q)
        assert quiz_setup['assignment'] not in bank.assignments.all()

        quiz.assignment = quiz_setup['assignment']
        quiz.save()
        assert quiz_setup['assignment'] in bank.assignments.all()

    def test_assignments_editable_via_api(self, api_client, quiz_setup):
        from core.models import QuestionBank
        bank = QuestionBank.objects.create(course=quiz_setup['course'], name='Pool')
        bank.assignments.add(quiz_setup['assignment'])

        api_client.force_authenticate(user=quiz_setup['admin'])
        resp = api_client.patch(f'/questionBanks/{bank.id}/', {'assignments': []}, format='json')
        assert resp.status_code == status.HTTP_200_OK
        assert bank.assignments.count() == 0
