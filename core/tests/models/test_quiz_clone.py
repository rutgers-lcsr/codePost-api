# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Tests for quiz / question-bank / quiz-image cloning (core.services.quiz_cloning)
and its integration with course cloning (CourseSerializer cloneFrom)."""
import io
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from core.models import (
    Assignment,
    Course,
    CourseFile,
    GeneratedQuestionSet,
    Organization,
    Question,
    QuestionBank,
    QuizAccommodation,
    QuizAttempt,
    QuizGeneratedSection,
    QuizImage,
    QuizImportJob,
    QuizQuestionGroup,
    SuggestedQuizQuestion,
    User,
)
from core.serializers.course import CourseSerializer
from core.services.quiz_cloning import (
    QuizImageRewriter,
    clone_course_files,
    clone_course_quizzes,
    clone_quizzes_for_assignment,
    copy_question_bank,
    copy_quiz,
)
from core.tests.views.quiz_helpers import _add, _bank, _essay, _mc, _quiz


class QuestionBankCloneTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Bank Clone Org", shortname="bankclone")
        self.source_course = Course.objects.create(name="Source", period="F2026", organization=self.org)
        self.destination_course = Course.objects.create(name="Destination", period="S2027", organization=self.org)

    def test_copies_questions_and_choices(self):
        bank = _bank(self.source_course)
        bank.description = "Chapter 1 pool"
        bank.save()
        mc = _mc(self.source_course, bank)
        mc.generalFeedback = "Basic arithmetic"
        mc.partialCredit = True
        mc.metadata = {"canvas_id": 7}
        mc.save()
        essay = _essay(self.source_course, bank)

        question_map = {}
        new_bank = copy_question_bank(bank, self.destination_course, question_map=question_map)

        self.assertEqual(new_bank.course_id, self.destination_course.id)
        self.assertEqual(new_bank.name, "Bank")
        self.assertEqual(new_bank.description, "Chapter 1 pool")
        self.assertNotEqual(new_bank.id, bank.id)
        self.assertEqual(new_bank.questions.count(), 2)

        new_mc = question_map[mc.id]
        self.assertEqual(new_mc.course_id, self.destination_course.id)
        self.assertEqual(new_mc.bank_id, new_bank.id)
        self.assertNotEqual(new_mc.id, mc.id)
        self.assertEqual(new_mc.text, mc.text)
        self.assertEqual(new_mc.points, mc.points)
        self.assertEqual(new_mc.generalFeedback, "Basic arithmetic")
        self.assertTrue(new_mc.partialCredit)
        self.assertEqual(new_mc.metadata, {"canvas_id": 7})

        new_choices = list(new_mc.choices.all())
        self.assertEqual([(c.text, c.isCorrect, c.sortKey) for c in new_choices],
                         [("3", False, 0), ("4", True, 1)])
        self.assertNotIn(new_choices[0].id, [c.id for c in mc.choices.all()])

        self.assertIn(essay.id, question_map)

    def test_bank_name_collision_gets_copy_suffix(self):
        bank = _bank(self.source_course)
        QuestionBank.objects.create(course=self.destination_course, name="Bank")

        new_bank = copy_question_bank(bank, self.destination_course, question_map={})

        self.assertEqual(new_bank.name, "Bank (copy 1)")
        self.assertEqual(new_bank.course_id, self.destination_course.id)


class QuizCloneTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Quiz Clone Org", shortname="quizclone")
        self.source_course = Course.objects.create(name="Source", period="F2026", organization=self.org)
        self.destination_course = Course.objects.create(name="Destination", period="S2027", organization=self.org)

    def test_quiz_reset_to_draft_but_config_verbatim(self):
        opens = timezone.now()
        quiz = _quiz(
            self.source_course,
            title="Midterm",
            description="Covers weeks 1-6",
            isPublished=True,
            availableFrom=opens,
            availableUntil=opens + timedelta(days=3),
            assignmentTrigger="after_feedback",
            closeEvent="fixed_date",
            closeOffsetMinutes=60,
            endAttemptsAtClose=True,
            timeLimitMinutes=30,
            attemptsAllowed=3,
            shuffleQuestions=True,
            oneQuestionAtATime=True,
            allowBacktracking=False,
            showCorrectAnswers=False,
            showResponses=False,
            sealResultsUntilClose=True,
            allowSubmissionReview=False,
            passingScore=Decimal("50"),
            passingScoreUnit="points",
            scoringPolicy="latest",
            multiAttemptScoreMethod="pooled",
            gradersCanReviewGenerated=True,
            autoPublishGenerated=True,
            metadata={"canvas_id": 3},
        )

        new_quiz = copy_quiz(quiz, self.source_course, assignment=None)

        self.assertFalse(new_quiz.isPublished)
        self.assertIsNone(new_quiz.availableFrom)
        self.assertIsNone(new_quiz.availableUntil)
        # The draft reset dropped the availableUntil this standalone quiz's seal relied on —
        # keeping the seal would hide results forever, so it is dropped with the window.
        self.assertFalse(new_quiz.sealResultsUntilClose)
        for field in ("title", "description", "assignmentTrigger", "closeEvent",
                      "closeOffsetMinutes", "endAttemptsAtClose", "timeLimitMinutes",
                      "attemptsAllowed", "shuffleQuestions", "oneQuestionAtATime",
                      "allowBacktracking", "showCorrectAnswers", "showResponses",
                      "allowSubmissionReview", "passingScore",
                      "passingScoreUnit", "scoringPolicy", "multiAttemptScoreMethod",
                      "gradersCanReviewGenerated", "autoPublishGenerated", "metadata",
                      "source", "createdBy_id"):
            self.assertEqual(getattr(new_quiz, field), getattr(quiz, field), field)

    def test_seal_kept_when_close_survives_the_reset(self):
        """A runtime close (assignment_due) doesn't depend on the reset availability window,
        so the seal is copied verbatim for attached quizzes that still close."""
        assignment = Assignment.objects.create(name="HW1", course=self.source_course, points=10)
        dest_assignment = Assignment.objects.create(name="HW1", course=self.destination_course,
                                                    points=10)
        quiz = _quiz(self.source_course, title="Sealed", assignment=assignment,
                     closeEvent="assignment_due", sealResultsUntilClose=True)

        new_quiz = copy_quiz(quiz, self.destination_course, assignment=dest_assignment,
                             question_map={}, bank_map={})
        self.assertTrue(new_quiz.sealResultsUntilClose)

        # But an attached quiz whose close was a fixed date loses that date in the reset —
        # the seal goes with it.
        quiz_fixed = _quiz(self.source_course, title="Sealed fixed", assignment=assignment,
                           closeEvent="fixed_date",
                           availableUntil=timezone.now() + timedelta(days=3),
                           sealResultsUntilClose=True)
        new_fixed = copy_quiz(quiz_fixed, self.destination_course, assignment=dest_assignment,
                              question_map={}, bank_map={})
        self.assertFalse(new_fixed.sealResultsUntilClose)

    def test_quiz_components_copied_with_remapping(self):
        bank = _bank(self.source_course)
        mc = _mc(self.source_course, bank)
        quiz = _quiz(self.source_course, title="Final")
        _add(quiz, mc, sortKey=4, points=Decimal("2.5"))
        QuizQuestionGroup.objects.create(quiz=quiz, bank=bank, name="Ch. 3 draw",
                                         pickCount=2, pointsPerQuestion=Decimal("1.5"), sortKey=1)
        QuizGeneratedSection.objects.create(quiz=quiz, name="About your code",
                                            systemPrompt="Ask about {submission_files}",
                                            numQuestions=4, pointsPerQuestion=Decimal("2"),
                                            questionTypes=["multiple_choice"], sortKey=2)

        question_map = {}
        new_bank = copy_question_bank(bank, self.destination_course, question_map=question_map)
        new_quiz = copy_quiz(quiz, self.destination_course, assignment=None,
                             question_map=question_map, bank_map={bank.id: new_bank})

        quiz_question = new_quiz.quizQuestions.get()
        self.assertEqual(quiz_question.question_id, question_map[mc.id].id)
        self.assertEqual(quiz_question.sortKey, 4)
        self.assertEqual(quiz_question.pointsOverride, Decimal("2.5"))

        group = new_quiz.questionGroups.get()
        self.assertEqual(group.bank_id, new_bank.id)
        self.assertEqual((group.name, group.pickCount, group.pointsPerQuestion, group.sortKey),
                         ("Ch. 3 draw", 2, Decimal("1.5"), 1))

        section = new_quiz.generatedSections.get()
        self.assertEqual(section.systemPrompt, "Ask about {submission_files}")
        self.assertEqual(section.numQuestions, 4)
        self.assertEqual(section.pointsPerQuestion, Decimal("2"))
        self.assertEqual(section.questionTypes, ["multiple_choice"])
        self.assertEqual(section.sortKey, 2)

    def test_same_course_copy_reuses_questions(self):
        bank = _bank(self.source_course)
        mc = _mc(self.source_course, bank)
        quiz = _quiz(self.source_course, title="Quiz 1")
        _add(quiz, mc)

        new_quiz = copy_quiz(quiz, self.source_course, assignment=None)

        self.assertEqual(new_quiz.quizQuestions.get().question_id, mc.id)
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(QuestionBank.objects.count(), 1)


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), (255, 0, 0)).save(buf, format='PNG')
    return buf.getvalue()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class QuizImageCloneTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Image Clone Org", shortname="imgclone")
        self.source_course = Course.objects.create(name="Source", period="F2026", organization=self.org)
        self.destination_course = Course.objects.create(name="Destination", period="S2027", organization=self.org)
        self.image = QuizImage.objects.create(
            course=self.source_course,
            image=SimpleUploadedFile("diagram.png", _png_bytes(), content_type="image/png"),
            originalName="diagram.png",
            contentType="image/png",
        )
        self.url = f"/quizImages/raw/{self.image.token}/"

    def test_image_copied_and_urls_rewritten(self):
        bank = _bank(self.source_course)
        mc = _mc(self.source_course, bank)
        mc.description = f"See the diagram: ![d]({self.url})"
        mc.save()
        quiz = _quiz(self.source_course, title="Quiz 1", description=f"Intro ![d]({self.url})")
        _add(quiz, mc)

        rewriter = QuizImageRewriter(self.source_course, self.destination_course)
        question_map = {}
        new_bank = copy_question_bank(bank, self.destination_course,
                                      question_map=question_map, rewriter=rewriter)
        new_quiz = copy_quiz(quiz, self.destination_course, assignment=None,
                             question_map=question_map, bank_map={bank.id: new_bank},
                             rewriter=rewriter)

        new_image = QuizImage.objects.get(course=self.destination_course)
        self.assertNotEqual(new_image.token, self.image.token)
        with new_image.image.open('rb') as f:
            self.assertEqual(f.read(), _png_bytes())

        new_url = f"/quizImages/raw/{new_image.token}/"
        self.assertIn(new_url, question_map[mc.id].description)
        self.assertNotIn(str(self.image.token), question_map[mc.id].description)
        self.assertIn(new_url, new_quiz.description)
        self.assertNotIn(str(self.image.token), new_quiz.description)

    def test_missing_image_file_leaves_url_unchanged(self):
        self.image.image.storage.delete(self.image.image.name)
        bank = _bank(self.source_course)
        mc = _mc(self.source_course, bank)
        mc.description = f"![d]({self.url})"
        mc.save()

        rewriter = QuizImageRewriter(self.source_course, self.destination_course)
        question_map = {}
        copy_question_bank(bank, self.destination_course,
                           question_map=question_map, rewriter=rewriter)

        self.assertEqual(question_map[mc.id].description, f"![d]({self.url})")
        self.assertFalse(QuizImage.objects.filter(course=self.destination_course).exists())

    def test_unknown_token_left_untouched(self):
        rewriter = QuizImageRewriter(self.source_course, self.destination_course)
        text = "![x](/quizImages/raw/00000000-0000-0000-0000-000000000000/)"
        self.assertEqual(rewriter.rewrite(text), text)


class CourseCloneQuizTests(TestCase):
    """Drives the real clone entry point: POST /courses/ with cloneFrom, via CourseSerializer."""

    def setUp(self):
        self.org = Organization.objects.create(name="Course Quiz Clone Org", shortname="cqclone")
        self.source_course = Course.objects.create(name="Source", period="F2026", organization=self.org)

        self.user = User.objects.create_user(username="admin@cqclone.org", email="admin@cqclone.org", password="pw")
        self.user.profile.organization = self.org
        self.user.profile.canCreateCourses = True
        self.user.profile.canModifyRosters = True
        self.user.profile.save()
        self.source_course.courseAdmins.add(self.user)

        self.assignment = Assignment.objects.create(name="HW1", course=self.source_course, points=10)
        self.bank = _bank(self.source_course)
        self.question = _mc(self.source_course, self.bank)
        self.attached_quiz = _quiz(self.source_course, title="HW1 Quiz", assignment=self.assignment)
        _add(self.attached_quiz, self.question, sortKey=1)
        self.standalone_quiz = _quiz(self.source_course, title="Syllabus Quiz")
        QuizQuestionGroup.objects.create(quiz=self.standalone_quiz, bank=self.bank, pickCount=1)

        # Per-student activity that must never be cloned.
        self.student = User.objects.create_user(username="stu@cqclone.org", email="stu@cqclone.org", password="pw")
        attempt = QuizAttempt.objects.create(quiz=self.attached_quiz, student=self.student)
        attempt.responses.create(question=self.question, questionSnapshot={"text": "2+2?"})
        QuizAccommodation.objects.create(course=self.source_course, student=self.student,
                                         timeMultiplier=Decimal("1.5"))
        GeneratedQuestionSet.objects.create(quiz=self.attached_quiz, student=self.student)

    def _clone(self):
        request = APIRequestFactory().post("/courses/", {})
        request.user = self.user
        request.auth = "a" * 40
        serializer = CourseSerializer(
            data={"name": "Cloned", "period": "S2027", "cloneFrom": self.source_course.id},
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        return serializer.save()

    def test_course_clone_copies_attached_and_standalone_quizzes(self):
        cloned_course = self._clone()

        # Exactly one copy of each quiz and bank — no double-copy through copy_assignment.
        self.assertEqual(cloned_course.quizzes.count(), 2)
        self.assertEqual(cloned_course.questionBanks.count(), 1)

        cloned_assignment = cloned_course.assignments.get(name="HW1")
        cloned_attached = cloned_course.quizzes.get(title="HW1 Quiz")
        self.assertEqual(cloned_attached.assignment_id, cloned_assignment.id)
        self.assertFalse(cloned_attached.isPublished)

        cloned_question = cloned_attached.quizQuestions.get().question
        self.assertEqual(cloned_question.course_id, cloned_course.id)
        self.assertNotEqual(cloned_question.id, self.question.id)

        cloned_standalone = cloned_course.quizzes.get(title="Syllabus Quiz")
        self.assertIsNone(cloned_standalone.assignment_id)
        cloned_group = cloned_standalone.questionGroups.get()
        self.assertEqual(cloned_group.bank.course_id, cloned_course.id)

    def test_course_clone_excludes_student_data(self):
        cloned_course = self._clone()

        self.assertFalse(QuizAttempt.objects.filter(quiz__course=cloned_course).exists())
        self.assertFalse(GeneratedQuestionSet.objects.filter(quiz__course=cloned_course).exists())
        self.assertFalse(QuizAccommodation.objects.filter(course=cloned_course).exists())

    def test_course_clone_copies_additional_settings(self):
        self.source_course.timezone = "US/Pacific"
        self.source_course.studentsCanSeeGraders = True
        self.source_course.useStudentCaptions = True
        self.source_course.enableStudentFeedbackNotifications = True
        self.source_course.activateQueue = False
        self.source_course.ai_feature_config = {"comment_generation": True}
        self.source_course.ai_feature_models = {"comment_generation": "gpt"}
        self.source_course.emailWhitelist = "@cqclone.org"
        self.source_course.inviteCodeEnabled = True
        self.source_course.save()

        cloned_course = self._clone()

        self.assertEqual(cloned_course.timezone, "US/Pacific")
        self.assertTrue(cloned_course.studentsCanSeeGraders)
        self.assertTrue(cloned_course.useStudentCaptions)
        self.assertTrue(cloned_course.enableStudentFeedbackNotifications)
        self.assertFalse(cloned_course.activateQueue)
        self.assertEqual(cloned_course.ai_feature_config, {"comment_generation": True})
        self.assertEqual(cloned_course.ai_feature_models, {"comment_generation": "gpt"})
        # Roster/invite settings intentionally stay at their defaults.
        self.assertEqual(cloned_course.emailWhitelist, "")
        self.assertFalse(cloned_course.inviteCodeEnabled)

    def test_attached_quiz_with_unmapped_assignment_cloned_standalone(self):
        destination = Course.objects.create(name="Direct Dest", period="S2027", organization=self.org)

        clone_course_quizzes(self.source_course, destination, assignment_map={})

        cloned_attached = destination.quizzes.get(title="HW1 Quiz")
        self.assertIsNone(cloned_attached.assignment_id)

    def test_course_clone_copies_ai_and_grading_settings(self):
        self.source_course.ai_provider = "openai"
        self.source_course.ai_api_key = "sk-test-123"
        self.source_course.ai_base_url = "https://llm.example.com"
        self.source_course.ai_model = "gpt-4"
        self.source_course.ai_disabled = True
        self.source_course.ai_comments_disabled = True
        self.source_course.ai_use_own_settings = True
        self.source_course.sendReleasedSubmissionsToBack = True
        self.source_course.showStudentsStatistics = True
        self.source_course.emailNewUsers = True
        self.source_course.anonymousGradingDefault = True
        self.source_course.allowGradersToEditRubric = True
        self.source_course.minComments = 2
        self.source_course.noUnfinalize = True
        self.source_course.lateDayCreditsAllowable = 3
        self.source_course.save()

        cloned_course = self._clone()

        for field in ("ai_provider", "ai_api_key", "ai_base_url", "ai_model", "ai_disabled",
                      "ai_comments_disabled", "ai_use_own_settings",
                      "sendReleasedSubmissionsToBack", "showStudentsStatistics", "emailNewUsers",
                      "anonymousGradingDefault", "allowGradersToEditRubric", "minComments",
                      "noUnfinalize", "lateDayCreditsAllowable"):
            self.assertEqual(getattr(cloned_course, field), getattr(self.source_course, field), field)

    def test_course_clone_remaps_curated_bank_assignment_links(self):
        # A manually curated bank->assignment link (no quiz involved, so the autolink
        # signals would NOT restore it) must be remapped to the cloned assignment.
        curated_assignment = Assignment.objects.create(name="HW2", course=self.source_course, points=5)
        self.bank.assignments.add(curated_assignment)

        cloned_course = self._clone()

        cloned_bank = cloned_course.questionBanks.get()
        cloned_hw2 = cloned_course.assignments.get(name="HW2")
        self.assertIn(cloned_hw2, cloned_bank.assignments.all())
        self.assertNotIn(curated_assignment, cloned_bank.assignments.all())

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_course_clone_copies_images_and_rewrites_tokens(self):
        image = QuizImage.objects.create(
            course=self.source_course,
            image=SimpleUploadedFile("diagram.png", _png_bytes(), content_type="image/png"),
            originalName="diagram.png",
            contentType="image/png",
        )
        url = f"/quizImages/raw/{image.token}/"
        self.question.description = f"![d]({url})"
        self.question.save()
        self.standalone_quiz.description = f"Intro ![d]({url})"
        self.standalone_quiz.save()

        cloned_course = self._clone()

        cloned_image = QuizImage.objects.get(course=cloned_course)
        self.assertNotEqual(cloned_image.token, image.token)
        new_url = f"/quizImages/raw/{cloned_image.token}/"

        cloned_question = cloned_course.questions.get()
        self.assertIn(new_url, cloned_question.description)
        self.assertNotIn(str(image.token), cloned_question.description)

        cloned_standalone = cloned_course.quizzes.get(title="Syllabus Quiz")
        self.assertIn(new_url, cloned_standalone.description)
        self.assertNotIn(str(image.token), cloned_standalone.description)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_course_clone_excludes_suggestions_import_jobs_and_quiz_graders(self):
        SuggestedQuizQuestion.objects.create(assignment=self.assignment, text="Suggested?")
        QuizImportJob.objects.create(
            course=self.source_course,
            file=SimpleUploadedFile("export.zip", b"PK\x03\x04"),
        )
        self.source_course.quizGraders.add(self.user)

        cloned_course = self._clone()

        self.assertFalse(SuggestedQuizQuestion.objects.filter(
            assignment__course=cloned_course).exists())
        self.assertFalse(QuizImportJob.objects.filter(course=cloned_course).exists())
        self.assertFalse(cloned_course.quizGraders.exists())

    def test_course_clone_quiz_standalone_when_assignment_clone_fails(self):
        # If an assignment can't be cloned, its quiz must survive as a standalone
        # draft rather than being dropped (or crashing the course clone).
        with mock.patch("core.utils.copy_assignment", return_value=None):
            cloned_course = self._clone()

        self.assertFalse(cloned_course.assignments.exists())
        self.assertEqual(cloned_course.quizzes.count(), 2)
        cloned_attached = cloned_course.quizzes.get(title="HW1 Quiz")
        self.assertIsNone(cloned_attached.assignment_id)
        self.assertFalse(cloned_attached.isPublished)

    def test_course_clone_resets_standalone_quiz_availability(self):
        opens = timezone.now()
        self.standalone_quiz.isPublished = True
        self.standalone_quiz.availableFrom = opens
        self.standalone_quiz.availableUntil = opens + timedelta(days=7)
        self.standalone_quiz.save()

        cloned_course = self._clone()

        cloned_standalone = cloned_course.quizzes.get(title="Syllabus Quiz")
        self.assertFalse(cloned_standalone.isPublished)
        self.assertIsNone(cloned_standalone.availableFrom)
        self.assertIsNone(cloned_standalone.availableUntil)

    def test_course_clone_copies_generated_sections(self):
        QuizGeneratedSection.objects.create(
            quiz=self.attached_quiz,
            name="About your code",
            systemPrompt="Ask about {submission_files}",
            numQuestions=3,
            pointsPerQuestion=Decimal("2"),
            questionTypes=["short_answer"],
        )

        cloned_course = self._clone()

        cloned_attached = cloned_course.quizzes.get(title="HW1 Quiz")
        cloned_section = cloned_attached.generatedSections.get()
        self.assertEqual(cloned_section.systemPrompt, "Ask about {submission_files}")
        self.assertEqual(cloned_section.numQuestions, 3)
        self.assertEqual(cloned_section.questionTypes, ["short_answer"])
        # The backfill signal fired for the cloned section must not create any
        # per-student sets (the cloned assignment has no submissions).
        self.assertFalse(GeneratedQuestionSet.objects.filter(quiz=cloned_attached).exists())

    def test_course_clone_copies_course_files(self):
        # Course files back {course_file:name} prompts, so a full course clone must carry
        # them over (fresh rows in the destination, not shared).
        CourseFile.objects.create(course=self.source_course, name="style.md",
                                  data="Use camelCase.", extension=".md")
        CourseFile.objects.create(course=self.source_course, name="topics.txt",
                                  data="recursion, trees", extension=".txt")

        cloned_course = self._clone()

        cloned_files = {f.name: f for f in cloned_course.files.all()}
        self.assertEqual(set(cloned_files), {"style.md", "topics.txt"})
        self.assertEqual(cloned_files["style.md"].data, "Use camelCase.")
        self.assertEqual(cloned_files["style.md"].extension, ".md")
        self.assertNotEqual(cloned_files["style.md"].course_id, self.source_course.id)


class CourseFileCloneTests(TestCase):
    """Course-file cloning (clone_course_files) and its use by cross-course assignment
    cloning so {course_file:name} prompts keep resolving in the destination course."""

    def setUp(self):
        self.org = Organization.objects.create(name="CF Clone Org", shortname="cfclone")
        self.source = Course.objects.create(name="Src", period="F2026", organization=self.org)
        self.dest = Course.objects.create(name="Dst", period="S2027", organization=self.org)

    def test_clone_all_files_dedups_by_name(self):
        CourseFile.objects.create(course=self.source, name="a.md", data="A", extension=".md")
        CourseFile.objects.create(course=self.source, name="b.md", data="B", extension=".md")
        # Destination already has a file named a.md — it must be left untouched, not duplicated.
        CourseFile.objects.create(course=self.dest, name="a.md", data="existing", extension=".md")

        created = clone_course_files(self.source, self.dest)

        self.assertEqual(created, 1)
        self.assertEqual(self.dest.files.filter(name="a.md").count(), 1)
        self.assertEqual(self.dest.files.get(name="a.md").data, "existing")
        self.assertEqual(self.dest.files.get(name="b.md").data, "B")

    def test_clone_files_limited_to_names(self):
        CourseFile.objects.create(course=self.source, name="used.md", data="U", extension=".md")
        CourseFile.objects.create(course=self.source, name="unused.md", data="X", extension=".md")

        clone_course_files(self.source, self.dest, names={"used.md"})

        self.assertEqual(set(self.dest.files.values_list("name", flat=True)), {"used.md"})

    def test_cross_course_assignment_clone_copies_referenced_files(self):
        # A source assignment whose attached quiz references a course file: cloning the
        # assignment into another course must bring the referenced file along (and only it).
        CourseFile.objects.create(course=self.source, name="rubric.md", data="Grade fairly.",
                                  extension=".md")
        CourseFile.objects.create(course=self.source, name="other.md", data="ignore", extension=".md")
        src_assignment = Assignment.objects.create(name="HW", course=self.source, points=10)
        quiz = _quiz(self.source, title="HW Quiz", assignment=src_assignment)
        QuizGeneratedSection.objects.create(
            quiz=quiz, name="From the rubric", systemPrompt="Base questions on {course_file:rubric.md}.",
            numQuestions=2, pointsPerQuestion=Decimal("3"))
        dest_assignment = Assignment.objects.create(name="HW", course=self.dest, points=10)

        clone_quizzes_for_assignment(src_assignment, dest_assignment)

        # Only the referenced file crossed over; the cloned prompt still points at it by name.
        self.assertEqual(set(self.dest.files.values_list("name", flat=True)), {"rubric.md"})
        cloned_quiz = self.dest.quizzes.get(title="HW Quiz")
        self.assertIn("{course_file:rubric.md}", cloned_quiz.generatedSections.get().systemPrompt)
