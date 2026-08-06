# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Quiz, question-bank, and quiz-image cloning primitives, used by course cloning
(CourseSerializer.create with cloneFrom) and assignment cloning (copy_assignment).

Only instructor-authored content is ever copied: banks/questions/choices, quiz
configuration, fixed questions, random-draw groups, generated-section prompt
templates, and referenced description images. Per-student data (attempts,
responses, generated sets/questions, accommodations, AI suggestions, import
jobs) is never copied, and cloned quizzes always land as unpublished drafts.
"""
import logging
import os
import re

from django.core.files.base import ContentFile
from django.db import transaction

from core.models import (
    Assignment, Course, CourseFile, Question, QuestionBank, Quiz, QuizGeneratedSection,
    QuizImage, QuizQuestion, QuizQuestionGroup,
)
from core.services.quiz_grading import quiz_never_closes

logger = logging.getLogger(__name__)

# Matches the public image URLs embedded in quiz/question/bank Markdown
# (see QuizImageSerializer: '/quizImages/raw/<dashed-uuid>/').
QUIZ_IMAGE_URL_RE = re.compile(
    r'/quizImages/raw/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/')

BANK_NAME_DEDUP_LIMIT = 50


class QuizImageRewriter:
  """Rewrites /quizImages/raw/<token>/ URLs in copied Markdown so they point at fresh
  copies of the source course's images (QuizImage rows CASCADE-delete with their course,
  so cloned text must not keep referencing the source course's tokens).

  Each source image is cloned lazily and at most once per rewriter instance. Unknown
  tokens, tokens belonging to other courses, and unreadable files leave the URL
  unchanged — the source image keeps serving publicly for as long as its course exists.
  """

  def __init__(self, source_course: Course, destination_course: Course):
    self.source_course = source_course
    self.destination_course = destination_course
    self._cache: dict[str, QuizImage | None] = {}

  def rewrite(self, text: str | None) -> str | None:
    if not text:
      return text
    return QUIZ_IMAGE_URL_RE.sub(self._substitute, text)

  def _substitute(self, match: re.Match) -> str:
    token = match.group(1).lower()
    if token not in self._cache:
      self._cache[token] = self._clone_image(token)
    new_image = self._cache[token]
    if new_image is None:
      return match.group(0)
    return f'/quizImages/raw/{new_image.token}/'

  def _clone_image(self, token: str) -> QuizImage | None:
    source = QuizImage.objects.filter(course=self.source_course, token=token).first()
    if source is None:
      return None
    try:
      with source.image.open('rb') as f:
        data = f.read()
      new_image = QuizImage(
          course=self.destination_course,
          originalName=source.originalName,
          contentType=source.contentType,
          uploadedBy=source.uploadedBy,
      )
      # quiz_image_upload_path derives the storage path from the NEW token, so this
      # writes a fresh physical file rather than sharing the source one.
      new_image.image.save(os.path.basename(source.image.name), ContentFile(data), save=True)
      return new_image
    except Exception as e:
      logger.warning(
          f"Failed to clone quiz image {token} into course {self.destination_course.id}: {e}")
      return None


def clone_course_files(source_course: Course, destination_course: Course, *,
                       names: set[str] | None = None) -> int:
  """Share course-level files (CourseFile) from source into destination_course. These back
  the {course_file:name} prompt variable, so a cloned quiz's generated-section prompts keep
  resolving. Returns the number of files created.

  The destination row points at the SAME CourseFileContent — no data copy, same token,
  same isPublic — so public URLs embedded in cloned markdown keep working. A physical
  copy only materializes when one course later diverges (edits data or toggles
  isPublic); see core.services.course_file.update_course_file_content.

  ``names`` limits the share to those file names (used by cross-course assignment cloning,
  which only needs the files its quizzes reference); None shares every file (full course
  clone). Files are matched to prompts by name, so a name already present in the
  destination is left as-is — never duplicated — making repeat/overlapping clones safe.
  """
  source_files = source_course.files.all()
  if names is not None:
    source_files = source_files.filter(name__in=names)
  existing_names = set(destination_course.files.values_list('name', flat=True))
  created = 0
  # .values(...) so file data is never loaded — the clone shares content, never copies it.
  for cf in source_files.values('name', 'extension', 'path', 'content_id',
                                'description', 'studentVisible'):
    if cf['name'] in existing_names:
      continue
    CourseFile.objects.create(
        course=destination_course, name=cf['name'], extension=cf['extension'],
        path=cf['path'], content_id=cf['content_id'],
        description=cf['description'], studentVisible=cf['studentVisible'])
    existing_names.add(cf['name'])
    created += 1
  return created


def copy_question_bank(bank: QuestionBank, destination_course: Course, *,
                       question_map: dict[int, Question],
                       rewriter: QuizImageRewriter | None = None,
                       assignment_map: dict[int, Assignment] | None = None) -> QuestionBank:
  """Copy a bank and all of its questions/choices into destination_course.

  Accumulates source-question-id -> new Question into the caller-supplied question_map
  so several bank copies can share one map. Authorship/provenance (createdBy, source)
  is preserved verbatim — unlike QuestionViewSet.copyToBank, which reassigns authorship
  to the requesting user. (course, name) is unique, so a colliding name gets a
  " (copy N)" suffix.
  """
  rw = rewriter.rewrite if rewriter else (lambda text: text)

  existing_names = set(
      QuestionBank.objects.filter(course=destination_course).values_list('name', flat=True))
  name = bank.name
  count = 0
  while name in existing_names and count < BANK_NAME_DEDUP_LIMIT:
    count += 1
    name = f"{bank.name} (copy {count})"

  new_bank = QuestionBank.objects.create(
      course=destination_course,
      name=name,
      description=rw(bank.description),
      source=bank.source,
      createdBy=bank.createdBy,
  )
  if assignment_map:
    # Preserve manually curated bank->assignment links (used as AI-generation context);
    # the autolink signals only restore the links implied by attached quizzes.
    new_bank.assignments.set(
        [assignment_map[a.id] for a in bank.assignments.all() if a.id in assignment_map])

  for question in bank.questions.all():
    new_question = Question.objects.create(
        course=destination_course,
        bank=new_bank,
        questionType=question.questionType,
        text=rw(question.text),
        description=rw(question.description),
        points=question.points,
        generalFeedback=rw(question.generalFeedback),
        partialCredit=question.partialCredit,
        numericTolerance=question.numericTolerance,
        language=question.language,
        starterCode=question.starterCode,
        referenceSolution=question.referenceSolution,
        source=question.source,
        createdBy=question.createdBy,
        metadata=dict(question.metadata or {}),
    )
    for choice in question.choices.all():
      new_question.choices.create(
          text=rw(choice.text),
          isCorrect=choice.isCorrect,
          sortKey=choice.sortKey,
          feedback=rw(choice.feedback),
      )
    question_map[question.id] = new_question

  return new_bank


def copy_quiz(quiz: Quiz, destination_course: Course, *,
              assignment: Assignment | None,
              question_map: dict[int, Question] | None = None,
              bank_map: dict[int, QuestionBank] | None = None,
              rewriter: QuizImageRewriter | None = None) -> Quiz:
  """Copy a quiz (configuration, fixed questions, random-draw groups, and generated
  sections) into destination_course, reset to an unpublished draft.

  question_map/bank_map of None mean "link the SAME Question/QuestionBank rows"
  (same-course clone; questions are course-scoped and shareable across quizzes). With
  maps, a component whose source rows were not cloned is skipped with a warning rather
  than linked across courses.
  """
  rw = rewriter.rewrite if rewriter else (lambda text: text)

  new_quiz = Quiz.objects.create(
      course=destination_course,
      assignment=assignment,
      title=quiz.title,
      description=rw(quiz.description),
      source=quiz.source,
      createdBy=quiz.createdBy,
      metadata=dict(quiz.metadata or {}),
      assignmentTrigger=quiz.assignmentTrigger,
      closeEvent=quiz.closeEvent,
      closeOffsetMinutes=quiz.closeOffsetMinutes,
      endAttemptsAtClose=quiz.endAttemptsAtClose,
      timeLimitMinutes=quiz.timeLimitMinutes,
      attemptsAllowed=quiz.attemptsAllowed,
      requireSebBrowser=quiz.requireSebBrowser,
      sebConfigKey=quiz.sebConfigKey,
      shuffleQuestions=quiz.shuffleQuestions,
      oneQuestionAtATime=quiz.oneQuestionAtATime,
      allowBacktracking=quiz.allowBacktracking,
      showCorrectAnswers=quiz.showCorrectAnswers,
      showResponses=quiz.showResponses,
      # The draft reset below drops the availability window. If the seal relied on it to
      # ever release results (standalone quizzes, or a fixed_date close), keeping it would
      # recreate the sealed-but-never-closes state QuizSerializer.validate blocks — results
      # hidden forever. Drop the seal too; the instructor re-seals when setting a new close.
      sealResultsUntilClose=quiz.sealResultsUntilClose and not quiz_never_closes(
          assignment, None, quiz.closeEvent),
      allowSubmissionReview=quiz.allowSubmissionReview,
      passingScore=quiz.passingScore,
      passingScoreUnit=quiz.passingScoreUnit,
      scoringPolicy=quiz.scoringPolicy,
      multiAttemptScoreMethod=quiz.multiAttemptScoreMethod,
      gradersCanReviewGenerated=quiz.gradersCanReviewGenerated,
      autoPublishGenerated=quiz.autoPublishGenerated,
      # generationDate is semester-specific (like the availability window) and is left
      # unset; the mode itself carries over.
      manualGeneration=quiz.manualGeneration,
      # Draft reset: nothing goes live in the destination course by accident, and the
      # availability window is semester-specific (mirrors copy_assignment's date resets).
      isPublished=False,
      availableFrom=None,
      availableUntil=None,
  )

  for quiz_question in quiz.quizQuestions.all():
    question = (quiz_question.question if question_map is None
                else question_map.get(quiz_question.question_id))
    if question is None:
      logger.warning(
          f"Skipping quiz question {quiz_question.id} while cloning quiz {quiz.id}: "
          f"source question {quiz_question.question_id} was not cloned")
      continue
    QuizQuestion.objects.create(quiz=new_quiz, question=question,
                                sortKey=quiz_question.sortKey,
                                pointsOverride=quiz_question.pointsOverride)

  for group in quiz.questionGroups.all():
    group_bank = group.bank if bank_map is None else bank_map.get(group.bank_id)
    if group_bank is None:
      logger.warning(
          f"Skipping question group {group.id} while cloning quiz {quiz.id}: "
          f"source bank {group.bank_id} was not cloned")
      continue
    QuizQuestionGroup.objects.create(quiz=new_quiz, bank=group_bank, name=group.name,
                                     pickCount=group.pickCount,
                                     pointsPerQuestion=group.pointsPerQuestion,
                                     sortKey=group.sortKey)

  # Creating a section fires the backfill_personalized_quiz_sets signal; that task is a
  # no-op here because the destination assignment has no submissions yet.
  for section in quiz.generatedSections.all():
    QuizGeneratedSection.objects.create(quiz=new_quiz, name=section.name,
                                        systemPrompt=rw(section.systemPrompt),
                                        numQuestions=section.numQuestions,
                                        pointsPerQuestion=section.pointsPerQuestion,
                                        questionTypes=list(section.questionTypes or []),
                                        sortKey=section.sortKey)

  return new_quiz


def clone_course_quizzes(source_course: Course, destination_course: Course,
                         assignment_map: dict[int, Assignment]) -> None:
  """Copy every question bank and quiz from source_course into destination_course.

  Called by CourseSerializer.create after its assignment loop; assignment_map maps
  source assignment ids to their clones so attached quizzes stay attached. A quiz whose
  assignment failed to clone is copied as standalone rather than dropped. Each object
  clones inside its own savepoint and failures are logged, so one bad object never
  aborts the rest of the course clone.
  """
  rewriter = QuizImageRewriter(source_course, destination_course)
  question_map: dict[int, Question] = {}
  bank_map: dict[int, QuestionBank] = {}

  # Course files back {course_file:name} prompts; copy them all so cloned quizzes resolve.
  try:
    with transaction.atomic():
      clone_course_files(source_course, destination_course)
  except Exception as e:
    logger.warning(
        f"Failed to clone course files into course {destination_course.id}: {e}")

  for bank in source_course.questionBanks.all():
    # Merge into the shared maps only on success so a rolled-back bank can't leak
    # references to nonexistent rows into later quiz copies.
    bank_questions: dict[int, Question] = {}
    try:
      with transaction.atomic():
        new_bank = copy_question_bank(bank, destination_course, question_map=bank_questions,
                                      rewriter=rewriter, assignment_map=assignment_map)
      bank_map[bank.id] = new_bank
      question_map.update(bank_questions)
    except Exception as e:
      logger.warning(
          f"Failed to clone question bank {bank.id} into course {destination_course.id}: {e}")

  for quiz in source_course.quizzes.all():
    new_assignment = assignment_map.get(quiz.assignment_id) if quiz.assignment_id else None
    if quiz.assignment_id and new_assignment is None:
      logger.warning(
          f"Quiz {quiz.id} is attached to assignment {quiz.assignment_id}, which was not "
          f"cloned into course {destination_course.id}; copying it as a standalone quiz")
    try:
      with transaction.atomic():
        copy_quiz(quiz, destination_course, assignment=new_assignment,
                  question_map=question_map, bank_map=bank_map, rewriter=rewriter)
    except Exception as e:
      logger.warning(
          f"Failed to clone quiz {quiz.id} into course {destination_course.id}: {e}")


def clone_quizzes_for_assignment(source_assignment: Assignment,
                                 new_assignment: Assignment) -> None:
  """Copy the quizzes attached to source_assignment onto new_assignment (the
  assignment-clone endpoint; course cloning handles quizzes at the course level).

  Same-course clones link the new quizzes to the EXISTING Question/QuestionBank rows —
  no content duplication. Cross-course clones first copy every bank the quizzes
  reference (in full, so random draws keep their pool), then remap.
  """
  quizzes = list(source_assignment.quizzes.all())
  if not quizzes:
    return

  if new_assignment.course_id == source_assignment.course_id:
    for quiz in quizzes:
      copy_quiz(quiz, new_assignment.course, assignment=new_assignment)
    return

  from core.prompts.variables import referenced_course_files

  rewriter = QuizImageRewriter(source_assignment.course, new_assignment.course)
  referenced_banks: dict[int, QuestionBank] = {}
  referenced_files: set[str] = set()
  for quiz in quizzes:
    for quiz_question in quiz.quizQuestions.select_related('question__bank'):
      referenced_banks[quiz_question.question.bank_id] = quiz_question.question.bank
    for group in quiz.questionGroups.select_related('bank'):
      referenced_banks[group.bank_id] = group.bank
    for section in quiz.generatedSections.all():
      referenced_files |= referenced_course_files(section.systemPrompt)

  # Carry along the course files the cloned prompts reference so {course_file:name} still
  # resolves in the destination course.
  if referenced_files:
    clone_course_files(source_assignment.course, new_assignment.course, names=referenced_files)

  question_map: dict[int, Question] = {}
  bank_map: dict[int, QuestionBank] = {}
  for bank_id in sorted(referenced_banks):  # deterministic "(copy N)" suffixes
    bank_map[bank_id] = copy_question_bank(referenced_banks[bank_id], new_assignment.course,
                                           question_map=question_map, rewriter=rewriter)

  for quiz in quizzes:
    copy_quiz(quiz, new_assignment.course, assignment=new_assignment,
              question_map=question_map, bank_map=bank_map, rewriter=rewriter)
