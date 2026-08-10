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
- `feedbackReleased` (with `liveFeedbackMode` as its override) is an orthogonal axis —
  feedback can be released in any state.

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

## Legacy booleans (until Phase 4)

`isVisible` and `isReleased` still exist because downstream gates read them (rubric
categories, attached-quiz availability, submission-list access, full test cases).
`Assignment.save()` keeps them in sync:

- `state` is the source of truth: changing it re-derives both booleans
  (`isVisible = state in STUDENT_VISIBLE_STATES`, `isReleased = state in (published, closed)`).
- Legacy ORM writers that flip only the booleans get `state` re-derived via migration
  0140's mapping (hidden → `draft`; visible+unreleased+upload-off → `preview`;
  upload-on or released → `published`).
- **API writes to the booleans are rejected with a 400** pointing at `state`.

Retiring the booleans (and re-homing the gates that read `isReleased`) is deferred until
production data confirms the mapping — see the Phase 4 table in the implementation plan.

## Operational commands

- `manage.py audit_assignment_lifecycle [--course-id N]` — strictly read-only report:
  historically exposed assignments (hidden + upload-open) and their submissions,
  hideFrom leakage, migration bucket counts, attached-quiz blast radius. Run against a
  prod snapshot before and after migrating.
- `manage.py set_assignment_state --course-id N --state S [--assignment-id A]
  [--from-state S] [--dry-run]` — escape hatch to bulk-move a course's assignments if an
  instructor is surprised by the migration mapping. Uses `save()`, so sync, stamps, and
  signals all run.

## Timestamps

- `publishedAt` — stamped on entry to `published`; kept through `closed`/`archived`;
  cleared if the assignment moves back to a pre-published state.
- `scheduledPublishRanAt` — one-shot stamp of the publish sweep; read-only over the API.

## Audit trail

Every state transition records an `assignment_state_changed` course audit event with
`{from, to}` meta; sweep-driven publishes add `scheduled: true` and a null user.
