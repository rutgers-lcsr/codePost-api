# Assignment lifecycle

Assignments move through an explicit, server-enforced lifecycle stored in
`Assignment.state`. It replaces the old `isVisible`/`isReleased` booleans, which gated
almost nothing on the write path (students could submit to and download hidden or
unreleased assignments).

All code lives in the `core/` app: the model in `core/models.py`, access predicates in
`core/permissions/helpers.py`, capability wiring in `core/permissions/capabilities.py`,
and the scheduled-publish sweep in `core/tasks.py`.

---

## States

| State | Students see it | Download files | Submit | View own submission | Notes |
|---|---|---|---|---|---|
| `draft` | ✗ | ✗ | ✗ | ✗ | Instructor-only. **Default for new assignments.** |
| `visible` | ✓ | ✗ | ✗ | ✗ | Announcement: name, due date, points, explanation. |
| `preview` | ✓ | ✓ | ✗ | ✗ | Students can read the spec and set up, not submit. |
| `published` | ✓ | ✓ | ✓* | ✓ | *also requires the `allowStudentUpload` setting. |
| `closed` | ✓ | ✓ | ✗ | ✓ | Usually **derived** (see below); storable for early close. |
| `archived` | ✗ | ✗ | ✗ | ✗ | Terminal; retires the assignment mid-course. Staff unaffected. |

Two things are deliberately **not** lifecycle states:

- `allowStudentUpload` is a per-assignment *setting* ("does this assignment accept
  student uploads at all"), applied on top of `published`.
- feedback is an orthogonal axis with its own lifecycle — see "The feedback axis
  (`feedbackStatus`)" below; feedback can open in any work-axis state.

`hideFrom` (per-section hiding) is enforced server-side on top of every state: a student
in a hidden section gets no assignment ID from `GET /courses/{id}/` and a 403 from every
assignment endpoint.

## Derived close (`effective_state`)

`Assignment.effective_state()` returns the stored state, except a stored-`published`
assignment whose submission deadline has passed reads as `closed`. The deadline comes
from `Assignment.submission_deadline()` — `uploadDueDate`, extended by `maxLateDays`
when `allowLateUploads` is on — which is also the boundary the `studentUpload` view
enforces, so the badge and the rejection can never disagree.

The API exposes this as the read-only `effectiveState` field; clients render it as the
status badge and must not reimplement the deadline math. Storing `state='closed'`
closes early regardless of the clock; extending the due date reopens a derived close.

## Scheduled publish

`publishAt` auto-publishes a `visible` or `preview` assignment (never a draft) via the
`run_scheduled_assignment_publish` beat task (every 5 minutes, registered in
`CELERY_BEAT_SCHEDULE`). `scheduledPublishRanAt` makes the run one-shot; moving
`publishAt` forward past the stamp re-arms it. The sweep mirrors
`run_scheduled_quiz_generation`: ids snapshotted, stamp written before the transition,
per-row error isolation.

**Deployment requirement:** a single `celery beat` process must run. The
`codepost-beat` service exists in `docker-compose-standalone.yml` (always on) and
`docker-compose-worker.yml` (behind `--profile beat` — start it on exactly **one** node;
the sweeps rely on single-scheduler semantics).

## Legacy booleans (retired — Phase 4)

The `isVisible`/`isReleased` columns were dropped in migration 0141. The API still
*returns* both as read-only values derived from state (`isVisible = state in
STUDENT_VISIBLE_STATES`, `isReleased = state in (published, closed)`) so external
readers keep working; **writes are rejected with a 400** pointing at `state`. The
`assignment.isVisible` / `assignment.isReleased` webhook field events were retired in
favor of `assignment.state`.

Every internal gate now reads `state` or `feedbackReleased` directly:

| Gate | Axis |
|---|---|
| Students list their own submissions | `state in (published, closed)` or `liveFeedbackMode` |
| Attached quiz availability + student quiz list | `state in (published, closed)` — closed included so `after_assignment`/`after_feedback` triggers open once the assignment is done |
| Rubric categories (structure) | `feedbackReleased` or `liveFeedbackMode` — unified with rubric comments |
| Full test-case list (finalized submission) | `feedbackReleased` |
| Opening a finalized submission's tests/results | `feedbackReleased` + `isFinalized`, or `liveFeedbackMode` |
| Stats-bearing student assignment serializers | `feedbackReleased` or `liveFeedbackMode` |
| Notify-students-of-feedback email | `feedbackReleased` |

The last product decision here: the rubric structure and graded-work reveals key on
**feedback release**, not publish — publishing opens *work* (files + submitting), and
one separate switch reveals *grading* (rubric, full tests, finalized submissions,
grades/comments).

## Operational commands

- `manage.py audit_assignment_lifecycle [--course-id N]` — strictly read-only report:
  historically exposed assignments (hidden + upload-open) and their submissions,
  hideFrom leakage, migration bucket counts, attached-quiz blast radius. Run against a
  prod snapshot before and after migrating.
- `manage.py set_assignment_state --course-id N --state S [--assignment-id A]
  [--from-state S] [--dry-run]` — escape hatch to bulk-move a course's assignments if an
  instructor is surprised by the migration mapping. Uses `save()`, so sync, stamps, and
  signals all run.

## The feedback axis (`feedbackStatus`)

Orthogonal to the work-axis `state`: `hidden → live / per_student / released`, plus the
independent `hideGrades` modifier (masks numeric grades in any revealing status).

| feedbackStatus | Comments/rubric/tests | Notes |
|---|---|---|
| `hidden` (default) | ✗ | grading in progress |
| `live` | ✓ immediately as written | office hours; re-uploads definalize |
| `per_student` | ✓ once THAT submission is finalized | rolling release, no global switch |
| `released` | ✓ for finalized submissions | global release; stamps `feedbackReleasedAt` |

Predicates live in `core/permissions/helpers.py` (`feedbackOpenForSubmission`,
`gradesVisibleForSubmission`, `testResultsVisibleForSubmission`,
`assignmentFeedbackOpen`) — every gate reads them. `releaseFeedbackAt` schedules
`hidden/per_student → released` via `run_scheduled_feedback_release` (same one-shot,
re-armable beat pattern as publishing). The legacy `feedbackReleased`/`liveFeedbackMode`
booleans are API-compat method fields (read-only; writes 400 → `feedbackStatus`).

**per_student × quizzes:** there is no global `feedbackReleasedAt` in per_student, so
the `after_feedback` quiz trigger and `feedback_released` close event are rejected by
validation in both directions (quiz serializer, and the assignment serializer blocks the
switch to per_student while such quizzes exist). The self-paced
`after_student_feedback` trigger is the per_student-compatible option. Course
`noUnfinalize` doubles as "graders can't revoke a student's reveal" under per_student.

## Timestamps

- `publishedAt` — stamped on entry to `published`; kept through `closed`/`archived`;
  cleared if the assignment moves back to a pre-published state.
- `feedbackReleasedAt` — stamped on entry to `released`; cleared on leaving it (anchors
  quiz close events).
- `scheduledPublishRanAt` / `scheduledFeedbackReleaseRanAt` — one-shot sweep stamps;
  read-only over the API.

## Audit trail

Every state transition records an `assignment_state_changed` course audit event with
`{from, to}` meta; sweep-driven publishes add `scheduled: true` and a null user.
