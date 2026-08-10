# Changelog

All notable changes to codePost are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> **License** — All source code and commits in this repository are made available under the
> [Rutgers Non-commercial License (RU-NCL)](./LICENSE). By using, downloading, or contributing
> to this repository you agree to be bound by its terms.

> **Branch note** — `main` is the default development branch. Production deploys from `release/*` branches.

---

## [Unreleased] — Assignment lifecycle

See [`docs/assignment_lifecycle.md`](./docs/assignment_lifecycle.md) for the full
documentation (states, derived close, scheduled publish, migration notes).

### Security — students could submit to unpublished assignments

- **Fixed: the `upload_submission` capability ignored assignment visibility** — a student
  could create submissions against a hidden (`isVisible=False`) assignment as long as
  `allowStudentUpload` was on. Cloned assignments landed in exactly that state (clones
  reset visibility but not `allowStudentUpload`, with no due date — accepting uploads
  forever).
- **Fixed: `studentUpload`/`beforeStudentUpload` bypassed object permissions** by fetching
  the assignment with a raw manager lookup instead of `get_object()`.
- **Fixed: `hideFrom` (per-section hiding) was enforced only in the browser** — the server
  never read it. It is now enforced in permissions, capabilities, and the course payload's
  assignment ID list.
- **Fixed: partner-link acceptance** (a state-mutating GET) had no visibility check and a
  double-add race; the invitee must now be able to submit to the assignment themselves,
  and the add is atomic.

### Added — six-state lifecycle

- **`Assignment.state`**: `draft → visible → preview → published → closed → archived`,
  replacing the `isVisible`/`isReleased` booleans as the source of truth. Visible =
  announcement only; Preview = files readable, no submitting; Published = open for work;
  Closed = derived automatically once the submission deadline (incl. the late window)
  passes, or set manually for an early close; Archived = retired mid-course.
- **Scheduled publish**: `publishAt` auto-publishes a Visible/Preview assignment via a
  one-shot, re-armable beat sweep (`run_scheduled_assignment_publish`, every 5 min).
  A `codepost-beat` compose service now exists — exactly one instance must run.
- Read-only `effectiveState` API field (clients render it as the badge), `publishedAt`
  stamp, `assignment_state_changed` audit events, `AssignmentStateEnum` in the schema.
- Admin UI: six-state status control and derived Closed badge, bulk Un-publish, a
  "Publish at" scheduler in assignment settings, and reconciled status copy (the row
  tooltip and bulk bar previously described "Published" contradictorily).
- Read-only `audit_assignment_lifecycle` and `set_assignment_state` management commands
  for pre/post-migration auditing and per-course fixes.

### Changed — breaking

- **`isVisible`/`isReleased` are read-only over the API** (still returned, derived from
  `state`; writes fail with a 400 pointing at `state`). External scripts that PATCH these
  fields must switch to `state`.
- **Phase 4: the `isVisible`/`isReleased` database columns are dropped** and every
  internal gate reads `state`/`feedbackReleased`. The `assignment.isVisible` /
  `assignment.isReleased` webhook field events are retired in favor of
  `assignment.state`.
- **Grading reveals now key on feedback release, not publish**: rubric categories, the
  full test-case list, and a finalized submission's tests/results become visible to
  students when feedback is released (or in live-feedback mode) — publishing opens
  files + submitting only. Previously all of these unlocked with the old `isReleased`
  flag; courses that relied on students seeing the rubric while working should use
  live-feedback mode or release feedback early.
- **New assignments default to `draft`** (previously effectively visible).
- **Visible no longer implies downloadable** — starter files require Preview or later.
- **Clones reset `allowStudentUpload`/`allowStudentUploadWithPartners`** along with the
  lifecycle state; re-enable upload after cloning.
- Migration `0140` maps existing rows behavior-preservingly: hidden → draft;
  visible+unreleased without student upload → preview; upload-open or released → published.

### Fixed — unrelated but adjacent

- Six email templates extended a nonexistent `emails/basic_template.html`
  (upload receipts, feedback notifications, regrade reminders, partner-added,
  test-complete) — rendering raised `TemplateDoesNotExist` in production since the
  templates were written. They now extend `emails/base_template.html`.
- Retrieving an assignment with a nonexistent ID now 404s instead of 500ing.

## [4.0.0] — Quizzes

First release of the **Quizzes** subsystem — see [`docs/quizzes.md`](./docs/quizzes.md) for the
full feature documentation (domain model, API surface, workflows).

### Added — Quiz authoring & taking

- **Question banks and questions** — course-level `QuestionBank` pools with reusable
  `Question`s (multiple choice/answers, true/false, short answer, numerical, essay, code) and
  per-question options (partial credit, numeric tolerance, starter code / reference solution
  for code questions). Move/copy questions between banks.
- **Quizzes** — optionally attached to an assignment, with availability triggers and close
  events, time limits (+ per-student `QuizAccommodation` multipliers), attempt limits and
  scoring policies, question shuffling, one-question-at-a-time with optional backtracking,
  random-draw question groups, and a results reveal policy (`showCorrectAnswers`,
  `sealResultsUntilClose`, `showResponses`).
- **Attempts and grading** — server-enforced deadlines and navigation, immutable
  per-response question snapshots, auto-grading for keyed types, manual grading with
  feedback and reopen, sandboxed execution of code answers, official-score selection
  (highest/latest/average) with staff override.
- **Late-access codes** — staff can mint/rotate a quiz access code
  (`PATCH /quizzes/{id}/generateAccessCode`); students supplying it may start after close
  (tracked via `closeBypassed`, compared constant-time). Attempt lifecycle, late starts, and
  access-code changes are recorded as course audit events.

### Added — AI generation & import

- **AI-suggested questions** (`quiz_generation` feature) — suggestions generated from
  assignment context or refreshed from existing questions; instructors accept/reject
  (accepting creates a real `Question`).
- **Personalized quiz questions** (`personalized_quiz_generation` capability, off by
  default) — per-student question sets generated from instructor prompt templates
  (`QuizGeneratedSection`) over the student's own submission; staff review/edit/approve
  before the quiz opens for that student (or auto-publish opt-in). Backfill and
  generate-missing bulk operations included. AI output is never student-visible without
  staff approval, and students never see AI provenance (prompts, reference solutions,
  generation metadata are staff-only).
- **Canvas QTI import** — `POST /quizImportJobs/` asynchronously imports IMS Common
  Cartridge / QTI 1.2 exports into a question bank (optionally recreating quizzes), with
  XXE-safe parsing, upload size caps, content-signature de-duplication, and point/tolerance
  clamping.
- **Quiz images** — instructor-uploaded Markdown images served at unguessable token URLs.
- **Cloning** — course/assignment cloning copies instructor-authored quiz content (never
  per-student data); cloned quizzes land unpublished.

### Added — CourseFile public access

- **`CourseFile.token` + `isPublic`** — course files can be served publicly at an
  unguessable token URL for embedding in quiz/assignment content.

### Security & fixes (pre-release hardening)

- **Cross-course reassignment guard** — writable `course`/`quiz`/`bank` FKs are
  re-authorized against the *destination* course (`assert_authoring_course`) across all quiz
  serializers, including `QuizGeneratedSection`; destination courses that are archived are
  rejected as well.
- **Legacy-data tolerance** — the quiz assignment↔course consistency check only fires when a
  change *introduces* the mismatch, so pre-existing records stay editable (matches the
  `sealResultsUntilClose` carve-out).
- **QTI points clamping** — non-finite imported point values (`NaN`, `-Infinity`) clamp to 0
  instead of the 9999.99 maximum; only `+Infinity` and finite over-max values clamp high.

---

## [3.4.0] — Testing Framework Improvements & Persisted File Edits

### Added — Testing Framework

- **Hidden test cases** — `TestCase.hidden` (boolean) lets instructors mark tests whose name, logs, and explanation are stripped from student-facing test-result responses. Point totals still apply.
- **Learning Objectives** — new `LearningObjective` model (per assignment) and many-to-many link from `TestCase`. Each objective has:
  - `shortId` — identifier used in test scripts (e.g. `recursion`).
  - `visibilityMode` — `always`, `on_pass`, `on_fail`, or `never` (admin only) controlling when students see the objective.
  - `aggregationMode` — `all`, `any`, `percentage`, or `points_weighted` for computing whether an objective is met from its linked test results.
- **New test decorator/annotation parameters** — `hidden` and `objectives` are now extracted by `TestParsingService` for every supported language:
  - **Python / Notebook Python** — `@test(name=..., points=..., hidden=True, objectives=["recursion"])` (decorator signature updated in `template.py` / `notebook_template.py`).
  - **Java / JShell** — `@Test(name=..., points=..., hidden=true, objectives={"recursion"})` (annotation extended in `TestRunner.java` / `notebook_template.java`).
  - **R, C/C++, Node/JS/TS, Ruby, PHP** — inline `@codepost` parser directives in the comment immediately preceding a test (e.g. `// @codepost hidden objectives=recursion,edge-cases`). Supports `//`, `#`, `--`, and `/* */` comment styles.
- **Auto-creation of `LearningObjective` records** — when a script references an objective by `shortId` that does not yet exist on the assignment, `TestParsingService._sync_test_objectives` creates it on first parse.
- **`/learningObjectives/` resource** — new ViewSet (`LearningObjectiveViewSet`) registered on the default router. CRUD restricted to course admins via `LearningObjectivePermissions`; course staff have read access.
- **`/assignments/{id}/learningObjectives/` action** — returns all learning objectives for an assignment (course staff only).
- **Persisted edits to submission files** — new `SubmissionFileEdit` model (one-to-one with `SubmissionFile`) backs a `PATCH /submissions/{id}/saveFileEdit/` action. Requires the `grade_submission` capability; course admins may always save edits, while graders may save only when the assignment's `gradersCanEditSubmissions` flag is True. Previously, instructor/grader edits in the code-review panel were not persisted server-side.

### Changed

- **`/submissions/{id}/submissionTestResults/`** — response now includes a `learningObjectives` array summarizing each objective's `met`, `score`, and `aggregationMode`. For student views, hidden tests have their `logs`/`results` blanked, and objectives are filtered by their `visibilityMode`.
- **`/testCategories/{id}/preview/`** — preview rows now carry the parsed `hidden` flag and `objectives` list so the UI can surface them before saving.
- **`TestCaseSerializer` / `TestCaseStudentSerializer`** — both now expose `hidden` and `learningObjectives`.
- **Submission retrieve queryset** — prefetches `files__edit` so the new persisted edit is delivered with the submission payload.

### Fixed / Infra

- `pre_script` is now removed after invocation so it does not persist into subsequent test runs.
- Autograder no longer needs the host Docker socket mounted directly on the API container.
- Anonymous routes are rate-limited; SSO token lookups are cached.
- Binary file detection switched from extension allow-list to encoding-based detection.

---

## [3.3.0] — AI Assistance, Analytics & Capabilities

### Added

- **AI suggested comments** — AI can now generate suggested comments, descriptions, and assignment summaries for graders and instructors.
- **Assignment analytics** — new analytics endpoints and data for assignment-level usage and grading insights.
- **Capabilities system** — introduced a capabilities framework for feature gating and progressive rollout.
- **Prompt feedback for AB testing** — added behavioral feedback tracking on AI prompts to support AB testing and prompt development.
- **Course audit log** — new audit log support for tracking course-level events and changes.

### Fixed

- **`view_test_results` permission** — added missing permission so students and graders can view test results as intended.

---

## [3.2.0] — AI Settings & Usage Analytics

### Added — AI Configuration

- **Organization-level AI settings** — org admins can configure a shared AI provider, API key, base URL, and model for the entire organization.
- **Course access policy** — org admins control which courses can inherit the org's AI key (`all`, `selected`, or `none`).
- **Course AI inheritance** — courses can use the org's AI configuration or opt to use their own key with a single toggle (`aiUseOwnSettings`).
- **AI usage tracking** — every AI API call (comment generation, test generation) records provider, model, token counts, estimated cost, and status.
- **Usage analytics endpoints** — new API endpoints for course-level (`/courses/{id}/aiUsage/`), org-level (`/organizations/{id}/aiUsage/`), and platform-level (`/system/aiUsage/`) usage summaries with configurable granularity (hourly, daily, monthly).
- **Cost estimation** — per-model USD cost estimates tracked for Gemini and OpenAI families.
- **AI Settings & Usage docs page** — comprehensive documentation added to `/docs/ai-guide`.

### Changed

- `AIService.record_usage()` consolidates all usage recording logic in one place.
- `AIService.estimate_cost()` provides static cost estimation for any provider/model combination.
- `AIService.__init__` now resolves effective AI config from org-level when course inherits.
- Course AI settings endpoint now returns `aiUseOwnSettings` and `orgAiAvailable` fields.

---

## [3.1.1]

### Added

- User-facing changelog page integrated into the docs system (`/docs/changelog`).
- `LICENSE` file added to the repository — all code and commits are under the Rutgers Non-commercial License (RU-NCL).

### Changed

- Increased Nginx upload/body size limit to 6 MB for larger submissions.
- Switched API runtime from WSGI to ASGI for WebSocket support.
- Updated codePost admin panel configuration.
- Tests now check syntax of code before saving to prevent syntax errors in test cases.

### Fixed

- Fixed an issue where users could not generate API tokens.
- Reduced intermittent 502 errors by forcing Nginx restart in deployment flow.
- Fixed assignment settings not loading notebook editor for notebook-based assignments.

---

## [3.1.0] — Testing Framework & Developer Tooling

This release introduces the **new testing framework**, the single largest feature addition since the initial 0.1.0 release. Instructors can now author, preview, and execute test cases directly inside codePost.

### Added — Testing Framework (new)

- **Test case authoring** — create, edit, and organize test cases per assignment.
- **Test script preview** — run and preview test scripts before publishing.
- **Language-specific testing** — added multi-language test runner support.
- **Test resources** — mount files and datasets as test resources; hidden from students by default.
- Cross-environment course copy script (`npm run populate:cross-env-course`) for migrating courses between servers.
- Tree-sitter integration for improved code parsing and syntax highlighting.

### Changed

- Migrated to generated API client instead of hand-written API calls.
- Updated SDK and documentation links across the platform.
- Added `.mjs` file format support.
- Updated brand color palette.

### Fixed

- Fixed test-save workflow requiring Ctrl+S before changes persisted.
- Fixed `hidden` state being checked instead of `isTestResource` for resource visibility.
- Resolved syntax errors in test-related UI flow.
- Fixed page sizing issues on list and table views.

---

## [3.0.0] — Platform Modernization

A major release that modernized the entire codebase, rebuilt the UI with Vite, and added AI-assisted grading, a new documentation system, and full accessibility improvements.

### Added — AI & Grading

- AI-assisted comment generation for graders with configurable system prompts per assignment.
- Pinned comments for graders.
- Grader rubric editor — instructors can grant graders permission to manage rubrics.
- Redux state management for the code-console rubric.
- Release feedback button (renamed from "Release Submission" for clarity).

### Added — Docs, Organization & Admin

- Built-in documentation system (`/docs`) with searchable sidebar, markdown rendering, and table of contents.
- Organization dashboard with SSO integration.
- SuperAdmin dashboard with `isOrgStaff` user setting.
- Course cloning now copies AI settings automatically.

### Added — Student Experience

- Students receive full assignment file data instead of only IDs.
- Improved student console layout and navigation.

### Changed — UI Modernization

- Migrated build system from Create React App to **Vite**.
- Converted most class components to functional components with hooks.
- Upgraded to React Router v7 (removed legacy prop-based routing).
- Removed the command bar in favor of streamlined navigation.
- Updated role selection page.
- Updated rubric UI and assignment management views.
- Comprehensive accessibility improvements (WCAG/Axe compliance, ARIA labels, color contrast fixes, heading hierarchy).
- Added sidebar tooltips in admin navigation.
- Updated dependencies across the stack.

### Changed — Backend & Infrastructure

- Multi-VM production deployment with `docker-compose` (Data / Backend / Worker / Frontend VMs).
- Environment setup script (`scripts/create_env.py`) with interactive and non-interactive modes.
- Bearer token authentication (replaced legacy JWT header format).
- Deployment README with full end-to-end setup guide.

### Fixed

- Fixed superadmin panel being cut off and content overlapping sidebar.
- Fixed admin count display errors on the dashboard.
- Fixed comments not deleting properly.
- Fixed download-grades returning empty CSV.
- Fixed sidebar overflow issues in student console.
- Fixed markdown backtick handling causing unexpected newlines in comments.
- Fixed binary file upload error messages for assignment files.

---

## [0.1.0] — Initial Self-Hosted Release

The baseline open-source release forked from the original codePost.io SaaS platform for self-hosted deployment at Rutgers.

### Included

- Django REST API with JWT authentication.
- React frontend (Create React App).
- Course, assignment, submission, and rubric management.
- Code review console with inline commenting.
- Autograder integration (Celery workers).
- Student, grader, and course-admin role system.
- Docker Compose deployment.
- Nginx reverse proxy with TLS.
- Health-check endpoint.
- Basic admin panel.
