# Changelog

All notable changes to codePost are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> **License** — All source code and commits in this repository are made available under the
> [Rutgers Non-commercial License (RU-NCL)](./LICENSE). By using, downloading, or contributing
> to this repository you agree to be bound by its terms.

> **Branch note** — `main` is the default development branch. Production deploys from `release/*` branches.

---

## [Unreleased] — Outage robustness

### Added

- **`manage.py wait_for_db`**: bounded wait (default 300 s, exponential backoff) for the
  database. `init.sh` runs it before `migrate`, and the worker / AI worker / beat commands run
  it before `celery` — a database that comes up *after* the API or workers (host reboot order,
  a data-host redeploy) is now a delay instead of a restart-policy crash loop. The compose
  healthchecks gained `start_period: 330s` so autoheal does not restart a container mid-wait.
- **`GET /health-check/ready/`**: unauthenticated readiness probe — 200 when the database and
  the Celery broker answer, 503 + `Retry-After` otherwise. `/health-check/` stays an
  unconditional liveness 200 on purpose (compose and autoheal act on it, and a dependency
  outage must not trigger API restarts). Both deploy workflows now verify readiness after
  `docker compose up`.
- **`DependencyUnavailableMiddleware`**: a database or broker outage inside any view (DRF or
  plain Django) answers a JSON 503 + `Retry-After` instead of a bare 500, so the UI can tell
  "codePost is down" from "no network".
- **nginx JSON 503 fallback**: when the API container is down or restarting, `codepost-entry`
  (and the self-hosted installer's proxy) answers 502/503/504 with a JSON body, `Retry-After`
  and CORS headers instead of nginx's HTML page, which the cross-origin SPA could not read.
- **`reap_stale_autograder_state`** beat sweep (every 10 min): environments stuck at
  *Building* with no build progress for 30 min and quiz code runs stuck at *running* for
  10 min (a worker died mid-flight) are marked failed instead of hanging forever.

### Changed

- `RunSubmission`, `RunSubmissionVariant` and `RunQuizResponseCode` use
  `acks_late` + `reject_on_worker_lost`: a worker killed mid-run (OOM, docker restart) re-queues
  the task instead of dropping it. Deliberately not applied to unbounded or paid tasks.
- `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True` (pins the Celery 5 behaviour Celery 6
  drops) and a 5 s broker `socket_connect_timeout`, so a request-path `.delay()` against an
  unreachable Redis fails fast into the 503 path.
- The development deploy workflow now deploys data → API → workers in order with
  `--wait`, like production, instead of all three hosts in parallel; the
  `docker restart codepost-entry` workaround is gone (nginx already re-resolves upstreams).
- Webhook delivery has connect/read timeouts (5 s / 30 s) and hard task time limits; SSO
  userinfo lookups have a 10 s timeout.

### Fixed

- A broker outage while queueing a quiz code run, a question-suggestion job or an
  environment build no longer strands the row at *running* / *pending* / *Building*.
- The autograder executor re-checks its Docker client on every acquisition and drops a dead
  one, so a Docker daemon restart on a worker no longer fails every later run with a message
  blaming the assignment's mounts.
- `logEvent` no longer tries to email the admins once per request for the whole length of a
  database outage.

## [4.3.0] — Instructor Agents, Quiz Workflow & Section Staffing

### Added — MCP endpoint for instructor agents

- **`POST /mcp`**: a stateless MCP (Model Context Protocol, Streamable HTTP) endpoint, so
  instructors can drive their course from Claude Code / Claude Desktop. The JSON-RPC is
  hand-rolled in `core/mcp/` — Django's Channels ASGI stack can't deliver lifespan events
  to a mounted sub-app, and stateless JSON mode needs none of it. Excluded from the
  OpenAPI schema.
- **`core/agent/`**, the protocol-agnostic tool layer: a `@tool` registry, in-process
  dispatch that replays the caller's `Authorization` header through the real viewsets
  (never the ORM — the permission classes stay the single enforcement point), and response
  shaping under a hard size budget. Tool names are prefixed `codepost_`.
- A **course API key connects pinned** to its course, so no tool takes a `courseId`. A
  **personal instructor token connects unpinned**: `tools/list` adds
  `codepost_list_courses`, injects a required `courseId` into every course-bound schema,
  and each call checks `isCourseStaff`.
- Writes are audited — `agent_write` on success, `agent_write_denied` on refusal; repeated
  denials are the signal that a key leaked. Tool calls are throttled per course service
  account, with a tighter budget for writes.

### Added — course API key scopes

- **`CourseAPIKey.scope`** ∈ `read` / `write` / `admin`, defaulting to the safest option
  (`read`). Set at creation, returned by the read and create serializers, and carried on
  `request.auth` beside the course id so a caller resolves a key's tier without a second
  lookup.
- `tools/list` is filtered by scope, so a key never even sees the tools above its tier;
  `?scope=read|write` on the connect URL narrows any credential further.
- **Scope governs the agent tool layer**, not ordinary REST access. A `CourseKey` request
  outside `/mcp` is bounded by its course exactly as it was in 4.2.0 — treat a `write` or
  `admin` key as equivalent to a course-admin credential for direct API use.
- The course service account now carries **`canModifyRosters`**: roster endpoints check
  that flag on top of the courseAdmin role, and the account is created outside
  `add_admin_privileges()` — so without it a course key can never touch a roster.
- Enum pinned as `CourseAPIKeyScopeEnum` in `ENUM_NAME_OVERRIDES`; auto-naming lands on
  the far too generic `ScopeEnum`, which would collide the first time another model grows
  a `scope` field.

### Added — autograder execution stats

- **`AutograderExecutionEvent`**: one insert-only row per cache consultation or real
  execution, recorded from every path that can run code (submission runs, test runs, and
  the file-run task — plain, streaming, and their error handlers). Failures are bucketed
  by `error_classifier` into timeout / missing dependency / compile / runtime /
  marker-extraction / infra, so the failure mix is queryable instead of a pile of stderr.
- **`GET /dashboard/autograding_stats/`** (superadmin): cache-hit rate, failure counts,
  language usage, failures per language, and top errors over a date range, defaulting to
  the last 30 days.
- Course and assignment are `SET_NULL` on purpose — expired courses are hard-deleted
  hourly and platform stats must outlive them. A daily beat task prunes rows past a
  400-day window in pk batches (avoiding long MySQL locks), keeping year-over-year
  semester comparisons intact.

### Added — quiz authoring and grading console

- **Quiz setup wizard**: "New Quiz" opened a two-field modal, so every quiz was born with
  default availability, attempts, results, and security that instructors had to hunt down
  afterwards. It now opens a stepped wizard — Basics, Availability, Attempts, Results,
  Security, AI questions, Review — that creates the quiz already configured. Only the title
  is required; **Skip & create** ends the wizard at any step with the remaining defaults,
  and Review offers create-as-draft or create & publish.
- **Focused grader**: grading happened in a panel squeezed under the queue, and a grade was
  only recorded if the grader remembered to press Save — moving to the next response, or
  leaving, silently dropped the draft. The grader now opens in a full-height drawer and
  **every navigation path flushes a dirty draft first** (Next, prev/next, picking another
  response, Esc, mask, back), staying put if the save fails and warning when a
  feedback-only draft can't be saved. The points/feedback panel docks below or beside the
  question; the dock choice and its size persist per user, and the section filter persists
  per course.
- **Quiz Grading Progress page** (Quizzes → Grading Progress) over
  `courses/{id}/quizGradingProgress/`: per-quiz manual-grading counts and per-grader
  throughput with last-graded time, so an instructor running a grading push can see where
  it stands without opening each quiz.
- **Missing generated sets are surfaced where instructors look**: a student with no
  generated set can't open the quiz at all, but that was only discoverable from the Review
  tab. A red "N missing" tag now appears in the quiz list, with a banner and a red Review
  badge on every builder tab. Unpublished quizzes get the same grey Draft chip the
  assignments table uses.
- **Course Settings** gains the *Graders Can Grade Quizzes* toggle, and the Graders roster
  adapts: while every grader can grade, the per-grader Quiz Grader column is hidden behind
  an info banner pointing at the setting, and returns once an instructor restricts quiz
  grading.

### Added — roster and admin console

- **Section leaders are managed from the sections page.** Assigning TAs meant editing one
  section at a time, and every change to the Leaders select PATCHed the whole section —
  which, with the API replacing membership wholesale, could clobber a concurrent roster
  edit. Leaders now edit inline as a local draft saved with one leaders-only PATCH, and a
  new **graders × sections matrix** batches edits, saving one PATCH per changed section
  with per-section failure isolation and a *Distribute evenly* helper for unled sections.
- The **sections CSV import** gained an optional third `role` column
  (`leader`/`ta`/`grader`); two-column files parse exactly as before.
- **Create Course API Key** offers read / write / admin (defaulting to read), and the key
  table shows each key's scope as a colour-coded tag, so an instructor handing a key to an
  agent can see at a glance what it may do.
- **Autograding tab** on the superadmin dashboard over `dashboard/autograding_stats/`:
  cache-hit rate and execution counts for a date range, language usage, failures per
  language, and top error categories with a sample message.

### Changed — graders can grade quizzes by default

- **`Course.gradersCanGradeQuizzes` (default on)** lets every grader view and grade quiz
  attempts. Quiz grading was previously gated on the explicit `quizGraders` role, which
  locked a course's ordinary graders out of the queue and made every instructor maintain a
  second roster. The `GRADE_QUIZ` capability, the attempt/results reveal, and the run-code
  action all follow the same `canGradeQuiz` gate.
- **Courses that relied on the old default must act**: turning the setting off restores
  the previous behaviour, with `quizGraders` as the opt-in list. Existing `quizGraders`
  entries are preserved and take effect again once the flag is off.
- **`QuizResponse.gradedAt`** records when a manual grade was applied and is cleared on
  reopen; a data migration backfills existing graded responses from their attempt. It is
  exposed with `gradedBy` in the staff projection only — neither field is in the student
  serializer's fields, so the student view is structurally incapable of leaking who graded
  them.
- **`GET /courses/{id}/quizGradingProgress/`** builds on that provenance: per-quiz
  manual-grading counts and per-grader throughput across the course's published quizzes.
  Graders who left the course keep their rows — it is an accountability record, not a
  roster.

### Changed — quiz question generation

- **`Quiz.gradersCanGenerate` (default off)** opens the Generate-missing backfill to course
  staff, so a grader can run generate → review → release for their section instead of
  waiting on an admin. Generation spends AI credits, which is why it stays opt-in per quiz;
  the blast radius is bounded because `missing_only` never touches an existing set.
  Per-student generate and regenerate remain admin-only. The flag carries over when a quiz
  is copied to another course.

### Changed — internal

- **`CourseScopePermission` is removed from `DEFAULT_PERMISSION_CLASSES`.** It re-derived
  each object's owning course by walking relationships, duplicating isolation the
  per-viewset `TemplatePermission` subclasses already enforce: a course API key
  authenticates as the `course-<id>-api` service account, which is a `courseAdmin` of
  exactly one course, so every membership check already fails for any other course. No
  behavioural change; the scope-id lookup survives as the public `get_course_scope_id`,
  which views import to adjust behaviour for course-pinned credentials.

### Fixed

- **Sections: a PATCH without `students` no longer wipes memberships.** The "leave every
  other section of this course" sweep ran on every write, outside the `students` guard, so
  a PATCH touching only `name` or `leaders` still iterated `newData['students']` and
  removed students from their other sections. It also read `newData['course']`, absent on
  a PATCH that doesn't resend it. The sweep now runs inside the guard and resolves the
  course from `newFields`, which backfills from the instance on PATCH.
- **Quizzes: starter code is no longer snapshotted onto non-code questions.**
  `starterCode` is kept when a question's type changes away from `code`, so an essay or
  short-answer question can still carry leftover code. The attempt snapshot copied it
  unconditionally, seeding it as the student's answer — the question looked answered
  before they started, and the code was rendered in the essay box. Both snapshot paths
  (authored and generated) now guard on question type.
- **The console survives an iframe.** Its body was `calc(100vh - 49px)` under a
  `min-height: 100%` wrapper; in an iframe `100vh` is the iframe's own box, which can
  extend past what the embedding page shows, putting the bottom bar and pinned footers out
  of reach. The body is now sized from the resolved wrapper height.
- **Gradebook honours the saved default page size.** The table hard-coded 50 rows and showed
  a size changer that did nothing — picking a size re-rendered at 50. It now uses the shared
  `useDefaultPageSize` preference, matching the rest of the app's tables.
- **Untouched starter code no longer counts as a quiz answer.** A code question opens
  pre-filled with its starter code, which the server seeds as the response's answer, so the
  progress bar counted every code question as answered before the student typed anything.

### Documentation

- [`docs/embedding.md`](./docs/embedding.md) — embedding the console in an iframe (LMS
  integration), including the headers a host page needs.
- In-app docs refreshed for this release: quiz grading (the focused grader, the section
  filter, who may grade), section staffing (the leaders matrix and the CSV `role` column),
  and the course API key scopes.

---

## [4.2.0] — Assignment & Feedback Lifecycle, Exam Lockdown

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

### Added — feedback lifecycle (`feedbackStatus`)

- **The feedback axis is now a four-state flow**: `hidden` (default), `live` (feedback
  appears as it's written), **`per_student` (NEW — each student sees their grades,
  comments, and rubric as soon as their own submission is finalized, no global
  switch)**, and `released`. `hideGrades` remains an independent toggle masking numeric
  grades in any revealing state — including live, which the old model couldn't express
  losslessly.
- **Scheduled feedback release**: `releaseFeedbackAt` auto-releases from
  hidden/per-student via a one-shot, re-armable beat sweep
  (`run_scheduled_feedback_release`), with audit events.
- **Admin UI**: a Feedback column beside Status (colored tag + described state picker,
  same accessibility treatment), per-transition confirmation dialogs, feedback flow +
  schedule in assignment settings (Publishing tab), and a state selector in the mobile
  console. The "Live feedback mode" switch is replaced by the flow choice; "Hide
  grades" toggles stay.
- **Client accuracy fix**: the student console and upload dialog previously showed
  feedback as available whenever a submission was finalized, even while feedback was
  hidden; they now mirror the server's gates exactly.

### Changed — breaking (feedback axis)

- The `feedbackReleased`/`liveFeedbackMode` columns are dropped (migration 0142,
  lossless mapping); the API returns both as read-only values derived from
  `feedbackStatus` — writes fail with a 400 pointing at `feedbackStatus`.
- A new `assignment.feedbackStatus` webhook field event fires on transitions.
- **per_student × quizzes**: quizzes anchored on the whole-assignment feedback release
  (`after_feedback` trigger, `feedback_released` close event) are rejected on
  per-student assignments in both directions — use the self-paced
  `after_student_feedback` trigger instead.

### Added — Safe Exam Browser lockdown for quizzes

- **`Quiz.requireSebBrowser`** gates a quiz behind [Safe Exam Browser](https://safeexambrowser.org):
  starting, reading an in-progress attempt, answering, and submitting all require a valid
  `X-SafeExamBrowser-ConfigKeyHash` header. Blocked requests return a structured 403
  (`lockdownRequired`, `lockdownReason`) instead of a bare error, and are recorded as
  `quiz_seb_blocked` audit events.
- **One-click launch** — `POST /quizAttempts/sebLaunch/` mints a per-student `.seb`
  config whose `startURL` carries a short-lived one-time token; `POST /ott/exchange/`
  trades that token for a normal session inside SEB's fresh browser profile. The Config
  Key is derived from the generated config, so instructors do not have to distribute
  anything. `Quiz.sebConfigKey` remains available for institutions shipping their own
  `.seb` file; requests verify against the pasted key *or* any of the student's unexpired
  launch keys.
- **`QuizAccommodation.sebExempt`** exempts individual students (Linux/ChromeOS, assistive
  tech) from the requirement; their attempts are flagged `lockdownVerified=False` so staff
  can see which attempts were not verified.
- Config-key verification hashes both the URL Django reconstructs and `API_URL + path`,
  so it works behind the standard nginx deployment and on multi-host setups.

### Added — assignment description shown to students

- The instructor-written assignment description (`explanation`) is now actually rendered
  in the student console: the assignment row expands to show it (from Visible onward),
  and it appears above the files on the submission view. Previously it was returned by
  the API but only rendered inside the upload dialog's Instructions tab.

### Fixed — student API payloads no longer include staff-only fields

- After feedback release, students received the full staff serializer — including
  `aiSystemPrompt`, `aiSummaryPrompt`, `aiDescription`, `anonymousGrading`,
  `forcedRubricMode`, `gradersCanEditSubmissions`, and other grading internals. The
  post-feedback student serializers are now built on an explicit student-safe field
  list (kept: points, hideGrades, commentFeedback, additiveGrading, regrade settings,
  testsAffectGrade, and mean/median when course statistics are enabled). Scripts
  authenticating as students will no longer see the removed fields; the schema and
  generated clients are unchanged.

### Fixed — unrelated but adjacent

- Six email templates extended a nonexistent `emails/basic_template.html`
  (upload receipts, feedback notifications, regrade reminders, partner-added,
  test-complete) — rendering raised `TemplateDoesNotExist` in production since the
  templates were written. They now extend `emails/base_template.html`.
- Retrieving an assignment with a nonexistent ID now 404s instead of 500ing.
- New daily beat task `flush_expired_tokens` deletes expired JWT refresh-token rows
  from the SimpleJWT outstanding/blacklist tables (equivalent to
  `manage.py flushexpiredtokens`) — previously nothing ever pruned them.
- **Test resource datasets are no longer staged into normal execution runs** — the
  executor only stages a dataset when the run actually targets it, so an assignment's
  test-resource datasets stop leaking into ordinary student runs. Dataset visibility
  and selection in the assignment form were reworked to match.
- Production deploys take an explicit `branch` input (`release/<version>`) instead of
  inheriting the dispatching ref, which previously made it easy to silently re-deploy an
  older release branch.

---

## [4.1.0] — AI Provider Testing & Personalized Quizzes

Shipped to production 2026-08-06. This release completed the AI-authoring half of the
Quizzes work that [4.0.0] describes, and fixed the flaky production image build.

### Added

- **AI provider connection tests** — `POST /courses/{id}/testAIConnection/` and the
  organization equivalent verify a configured provider end to end, with an optional
  model override and custom prompt. The result reports the model the provider actually
  answered as (`reportedModel`), so a silently substituted model is visible. Usage is
  recorded under a new `provider_test` request type and broken out in the AI usage
  summary.
- **AI quiz-suggestion jobs** — suggestion generation runs as a tracked job with polling
  and status, replacing the fire-and-forget request; the UI reports progress and failures.
- **Personalized quiz questions** — the `personalized_quiz_generation` capability, the
  `QuizGeneratedSection` model, per-student generation over a student's own submission,
  and staff review/approve before anything becomes student-visible. **Default off** —
  enable "AI-Generated Quiz Questions" per course or organization after upgrading.
- **Manual generation and preview** for generated sections, so instructors can generate
  on demand and inspect the output before the quiz opens.
- **Dedicated AI worker container** (`codepost-ai-worker`) — AI tasks route to their own
  unprivileged queue and are the only workers given `FIELD_ENCRYPTION_KEY` (interpolated
  by compose, never written to `.env`), so the autograder sandbox never sees it.
- Database health-check metrics on the system health endpoint.

### Fixed

- **Flaky production image builds** — Poetry is now pinned (2.4.1) in its own virtualenv
  at `/opt/poetry` across all three Dockerfile stages. Installing Poetry unpinned into
  the system interpreter let its transitive dependencies conflict with `poetry.lock`
  pins, and the resulting parallel uninstall could crash mid-extraction
  (`module 'attr.setters' has no attribute 'pipe'`) — timing-dependent, so a plain
  re-run would sometimes pass.
- Course API key management permissions, and quiz taking is restricted to the browser.

---

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
