# Quizzes

The quiz subsystem lets instructors author question banks and quizzes (optionally attached to
an assignment), students take timed, policy-gated attempts, and staff grade the results. It
also supports AI-generated questions (course-level suggestions and per-student personalized
sets), Canvas QTI import, and cloning alongside courses/assignments.

This document covers the domain model, the API surface, and the main workflows. For the
endpoint-level API reference (request/response schemas), use the generated OpenAPI docs at
`/api/schema/swagger-ui/` (or `/api/schema/elements/`).

All code lives in the `core/` app: models in `core/models.py`, one ViewSet per file in
`core/views/`, one serializer per file in `core/serializers/`, business logic in
`core/services/`, and Celery tasks in `core/tasks.py`.

---

## Domain model

The models split into three groups: **authoring** (instructor-created content), **taking**
(per-student runtime data — never cloned), and **AI / import**.

### Authoring

| Model | Purpose |
|---|---|
| `QuestionBank` | Course-level pool of questions. Unique per `(course, name)`. Auto-linked to assignments (M2M) when used in an assignment-attached quiz — this drives AI-generation context. |
| `Question` | Reusable question, belongs to exactly **one** bank (reuse across banks = copy). Types: `multiple_choice`, `multiple_answers`, `true_false`, `short_answer`, `numerical`, `essay`, `code`. Code questions add `language` / `starterCode` / `referenceSolution`. Supports `partialCredit` and `numericTolerance`. |
| `QuestionChoice` | Answer option. For `short_answer` / `numerical`, the accepted answers are the `isCorrect=True` choices; `essay` / `code` have none. |
| `Quiz` | The authoring container, optionally attached to one `Assignment`. Configuration: availability (`assignmentTrigger`, `availableFrom/Until`, `closeEvent` + `closeOffsetMinutes`, `endAttemptsAtClose`, `accessCode`), options (`timeLimitMinutes`, `attemptsAllowed`, `shuffleQuestions`, `oneQuestionAtATime` + `allowBacktracking`), reveal policy (`showCorrectAnswers`, `sealResultsUntilClose`, `showResponses`, `allowSubmissionReview`), scoring (`passingScore` + `passingScoreUnit`, `scoringPolicy`, `multiAttemptScoreMethod`), `isPublished` draft flag, and generated-question gates (`gradersCanReviewGenerated`, `autoPublishGenerated`). |
| `QuizQuestion` | Through model Quiz↔Question with `sortKey` + `pointsOverride`. Unique per `(quiz, question)`. |
| `QuizQuestionGroup` | Canvas-style random draw: pick `pickCount` questions from a `bank` at `pointsPerQuestion` each. |
| `QuizGeneratedSection` | Per-student AI generation config on a quiz: an instructor-authored `systemPrompt` template (with `{variables}`), `numQuestions`, `pointsPerQuestion`, optional `questionTypes`. |

### Taking (per-student runtime — never cloned)

| Model | Purpose |
|---|---|
| `QuizAttempt` | One student attempt. Unique per `(quiz, student, attemptNumber)`. Tracks status (`in_progress` / `submitted`), `startedAt` / `deadline` / `submittedAt`, `score` / `maxScore`, `needsManualGrading`, `passed`, `furthestIndex` (server-side sequential-navigation enforcement), `isOfficialOverride` (staff-pinned official score), and `closeBypassed` (started late via access code). |
| `QuizResponse` | One answer within an attempt. **`questionSnapshot` (JSON) is an immutable copy of the question as presented** — editing or deleting the live `Question` never disturbs in-flight or graded attempts. The `question` / `generatedQuestion` FKs are `SET_NULL` analytics links only. Holds `selectedChoiceKeys`, `answerText`, `pointsEarned`, `isCorrect`, `needsManualGrading`, `graderFeedback`, `gradedBy`, and `codeExecution` (staff sandbox run of code answers). |
| `QuizAccommodation` | Per-student, per-course `timeMultiplier` for timed quizzes. Unique per `(course, student)`. |

### AI and import

| Model | Purpose |
|---|---|
| `SuggestedQuizQuestion` | AI-suggested question (`pending` / `accepted` / `rejected`), generated from an assignment (fresh) or from an existing `sourceQuestion` (cross-semester refresh). Accepting creates/updates a real `Question`. |
| `GeneratedQuestionSet` | One student's generated questions for a quiz. Unique per `(quiz, student)`. Lifecycle: `pending` → `generating` → `ready` → `approved` (or `failed`). The quiz opens for a student only once their set is approved (or automatically via `Quiz.autoPublishGenerated`). `generationBatch` (UUID) discards stale task results. |
| `GeneratedQuizQuestion` | One generated question in a set. Staff-editable; not a bank `Question`. Its `referenceSolution` is grader-only and never snapshotted or shown to students. |
| `QuizImportJob` | Async Canvas QTI / Common Cartridge import tracking (`pending` / `running` / `completed` / `failed`), with `targetBank`, created counts, and a per-item `summary` of skipped/unsupported questions. |
| `QuizImage` | Instructor-uploaded Markdown image, served publicly at an unguessable token URL (browsers cannot send auth headers on `<img>`). |

---

## API surface

Resources are registered on the central router in `codepost/urls.py`. As everywhere in this
API, list endpoints are superuser-only — users reach resources through parent actions
(e.g. a course's quizzes, a quiz's attempts).

| Resource | ViewSet | Notable actions |
|---|---|---|
| `/questionBanks/` | `core/views/questionBank.py` | `GET questions` |
| `/questions/` | `core/views/question.py` | `POST moveToBank`, `POST copyToBank`, `POST regenerateSuggestion`, `GET regenerationSuggestions` |
| `/quizzes/` | `core/views/quiz.py` | `GET questions`, `GET attempts`, `GET results`, `POST resetAttempts`, `PATCH generateAccessCode`, `GET generatedSets`, `POST publishAllGenerated`, `POST generateForStudent`, `GET backfillPreview`, `POST generateMissing`, `GET promptVariables`, `GET promptTemplates` |
| `/quizQuestions/`, `/quizQuestionGroups/` | `core/views/quizQuestion.py`, `quizQuestionGroup.py` | plain CRUD |
| `/suggestedQuizQuestions/` | `core/views/suggestedQuizQuestion.py` | `POST accept`, `POST reject` |
| `/quizImportJobs/` | `core/views/quizImportJob.py` | `create` (multipart upload → 202, enqueues import task) |
| `/quizImages/` | `core/views/quizImage.py` | `create` (upload); public raw serving at `quizImages/raw/<token>/` |
| `/quizAttempts/` | `core/views/quizAttempt.py` | `PATCH saveAnswer`, `POST submit`, `POST gradeResponse`, `POST reopenResponse`, `POST runCode`, `POST setOfficial`, `GET myAttempts`, `GET availableQuizzes` |
| `/quizGeneratedSections/` | `core/views/generatedQuestions.py` | plain CRUD |
| `/generatedQuestionSets/` | `core/views/generatedQuestions.py` | retrieve-only + `POST approve`, `POST unapprove`, `POST regenerate` |
| `/generatedQuizQuestions/` | `core/views/generatedQuestions.py` | retrieve/update/destroy |

Serializers follow the one-file-per-resource convention in `core/serializers/`
(`quiz.py`, `question.py`, `questionBank.py`, `quizQuestionGroup.py`, `generatedQuiz.py`,
`quizImportJob.py`, `suggestedQuizQuestion.py`, `quizImage.py`); `studentQuiz.py` holds the
student- vs staff-facing attempt/response projections.

---

## Workflows

### Taking a quiz (availability, access codes, late start)

Implemented in `core/views/quizAttempt.py` + `core/services/quiz_grading.py` (attempt
materialization, grading, availability, answer reveal).

1. `POST /quizAttempts/` resumes an in-progress attempt (auto-submitting it first if
   expired) or starts a new one, after checking availability, remaining attempts, and that
   the quiz has content. The deadline comes from `compute_attempt_deadline`, honoring
   `QuizAccommodation.timeMultiplier` and `endAttemptsAtClose`.
2. **Late start** — if the quiz has closed and the quiz has an `accessCode` set, a student
   supplying the matching code (compared constant-time) starts with `closeBypassed=True`
   and the full time limit; otherwise the API returns 403 with `accessCodeRequired: true`.
   Staff mint/rotate/clear codes via `PATCH /quizzes/{id}/generateAccessCode` — the code is
   never writable through the normal quiz serializer.
3. `PATCH saveAnswer` autosaves one response (no-backtracking is enforced server-side via
   `furthestIndex`); `POST submit` finalizes and auto-grades. Auto-graded types:
   multiple choice/answers, true/false, short answer, numerical. Essay and code responses
   are flagged `needsManualGrading`.
4. Manual grading: `POST gradeResponse` / `POST reopenResponse`; `POST runCode` executes a
   code answer in the autograder sandbox (result stored on `QuizResponse.codeExecution`);
   `POST setOfficial` pins an attempt as the official score. The official score otherwise
   follows `scoringPolicy` / `multiAttemptScoreMethod`.
5. Attempt lifecycle and access-code changes are recorded as `CourseAuditEvent`s
   (`quiz_attempt_started`, `_started_late`, `_autosubmitted`, `_submitted`, access-code
   change events). Expired attempts are swept by the `finalize_expired_quiz_attempts` task.

What students see after submitting is controlled by the quiz's reveal policy
(`showCorrectAnswers`, `sealResultsUntilClose`, `showResponses`) via `answers_visible` /
`scores_visible` in `quiz_grading.py`.

### AI question generation

Two separate AI features are registered in `core/ai_features/`; prompt templates and
`{variable}` resolution live in `core/prompts/`.

- **Suggestions (`quiz_generation`, default on)** — `generate_quiz_question_suggestions`
  (Celery) produces `SuggestedQuizQuestion` rows from an assignment's context, or refreshes
  an existing question cross-semester (`sourceQuestion`). An instructor accepts via
  `POST /suggestedQuizQuestions/{id}/accept`, which creates/updates a real `Question`.
- **Personalized sets (`personalized_quiz_generation`, default off)** — a
  `QuizGeneratedSection` on the quiz holds the prompt template; on student submission (or
  eagerly, for submission-free prompts) `generate_personalized_quiz_sets` builds that
  student's `GeneratedQuestionSet`. Staff review, edit, and approve sets
  (`approve` / `unapprove` / `regenerate`; bulk via `publishAllGenerated`,
  `generateMissing`, `backfillPreview`); the quiz opens per-student only after approval
  unless `autoPublishGenerated` is set.

Two invariants hold everywhere: the **instructor is the author** — AI output becomes
student-visible content only after staff acceptance/approval (or an explicit auto-publish
opt-in) — and **students never see AI provenance** (reference solutions, prompts, and
generation metadata are staff-only).

### Canvas QTI import

`POST /quizImportJobs/` (multipart, size-capped) returns 202 and enqueues `import_quiz_qti`,
which parses IMS Common Cartridge / QTI 1.2 exports (`core/services/canvas_qti_import.py`,
XXE-safe via defusedxml) into `Question` / `QuestionChoice` rows in the target bank —
optionally recreating quizzes (`importQuizzes`). Duplicate questions are de-duplicated by
content signature; out-of-range or non-finite point values are clamped; unsupported item
types are recorded in the job's `summary`.

### Cloning

`core/services/quiz_cloning.py` is used by course cloning (`CourseSerializer.create` with
`cloneFrom`) and assignment cloning (`copy_assignment`). It copies instructor-authored
content only — banks/questions/choices, quiz configuration, fixed questions, groups,
generated-section prompts, and referenced images — never per-student data. Cloned quizzes
land unpublished.

---

## Permissions and safety invariants

- Authoring endpoints require course staff (see `core/permissions/` — the quiz permission
  classes authorize against the object's course); students only reach attempt endpoints
  and their own policy-gated results.
- Writable `course` / `quiz` / `bank` FKs are re-authorized against the **destination**
  course via `assert_authoring_course` (`core/serializers/template.py`) — object
  permissions only check the source course, so cross-course reassignment and moves into
  archived courses are blocked at validation time.
- `QuizResponse.questionSnapshot` isolates attempts from later edits to questions.
- Archived courses block all quiz edits (base serializer validation).
- Access codes and public image/file tokens are unguessable and compared/served without
  leaking through normal serializers.

## Testing

Behavior specs live in `core/tests/views/test_quizzes.py` (authoring, import, suggestions),
`test_quiz_attempts.py` (taking/grading), `test_generated_quizzes.py` (personalized
generation), `test_quiz_images.py`, and `core/tests/models/test_quiz_clone.py`, with shared
builders in `core/tests/views/quiz_helpers.py`. Seed data for manual testing:
`python manage.py seed_test_quizzes`.
