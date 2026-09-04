---
key: activity-log
path: activity-log
title: Course Activity Log
category: Reference
order: 20
---

# Course Activity Log

The Activity Log records who did what in a course — submission attempts, file views, regrade requests, autograder runs, and more. Use it to investigate disputes, audit unusual behavior, and understand how students are engaging with an assignment.

## Where to find it

1. Open the **Admin Console** for your course.
2. Open the **Activity Log** tab.

You must have the `view_audit_log` capability on the course (course admins by default; some grader roles may have it if your course customizes capabilities).

## Filtering events

Above the table, four filters narrow the view:

- **Student** — filter to a single student's events by email.
- **Assignment** — filter to one assignment.
- **Event type** — see the table below.
- **Date range** — pick start and end dates.

Filters combine with AND semantics. Clear a filter by clicking its **×**.

## Event types

| Event type             | When it fires                                                                |
| ---------------------- | ---------------------------------------------------------------------------- |
| `submission_attempt`   | A student uploaded files for an assignment.                                  |
| `submission_failed`    | A student's upload attempt failed validation (size, extension, etc.).        |
| `file_view`            | A user opened a file in the Code Console.                                    |
| `feedback_view`        | A student opened a graded submission to view feedback.                       |
| `regrade_request`      | A student submitted a regrade request or question.                           |
| `regrade_deleted`      | A student deleted their own regrade request before it was claimed.           |
| `autograder_triggered` | A test run was started (by a student, grader, or auto-run-on-submit policy). |
| `autograder_completed` | A test run finished successfully.                                            |
| `autograder_failed`    | A test run errored out (environment, timeout, or runtime error).             |
| `late_day_used`        | A submission consumed a late-day allowance.                                  |
| `comment_feedback`     | A student left thumbs-up/down on a rubric comment.                           |
| `assignment_state_changed` | The assignment's lifecycle status changed (e.g. published); scheduled publishes are marked. |
| `assignment_feedback_changed` | The assignment's feedback flow changed (e.g. released); scheduled releases are marked. |

### Quiz events

| Event type                       | When it fires                                                        |
| -------------------------------- | -------------------------------------------------------------------- |
| `quiz_created` / `quiz_updated` / `quiz_deleted` | A staff member created, edited, or deleted a quiz.   |
| `quiz_published` / `quiz_unpublished` | A quiz was made visible to students, or hidden again.           |
| `quiz_access_code_changed`       | A late-access code was generated, rotated, or removed.               |
| `quiz_attempt_started`           | A student started a quiz attempt.                                    |
| `quiz_attempt_started_late`      | A student started **after the close** using an access code.          |
| `quiz_attempt_submitted`         | A student submitted their attempt.                                   |
| `quiz_attempt_autosubmitted`     | An attempt was auto-submitted (timer expiry or a hard close).        |
| `quiz_attempts_reset`            | An admin deleted all attempts for a quiz.                            |
| `quiz_response_graded` / `quiz_response_grade_reopened` | A grader saved or reopened a manual grade.    |
| `quiz_generated_set_approved` / `_unapproved` / `_regenerated`, `quiz_generated_sets_published` | Staff actions on per-student AI-generated question sets. |

> [!NOTE]
> Sensitive admin actions (impersonation, capability changes, key edits) are recorded as **audit** events in the system log, not in the course Activity Log. Contact your organization admin or codePost staff to access those.

## Exporting

Click **Export CSV** in the top-right to download the currently-filtered view as a CSV. The export respects all active filters and is useful for offline analysis or sharing with a department chair during a dispute.

## When to use this

- A student claims they submitted before the deadline — check `submission_attempt` timestamps for that student.
- An assignment looks unusually high-traffic on the autograder — filter to `autograder_triggered` for that assignment.
- A regrade request seems to have vanished — filter to `regrade_deleted` for the student.
- Suspicious feedback-view patterns (e.g., many `feedback_view` events on other students) — surface via the per-student filter.
- A dispute about quiz timing or access — check `quiz_attempt_started` / `quiz_attempt_started_late` / `quiz_attempt_autosubmitted` timestamps for the student, and `quiz_access_code_changed` for when codes were rotated.

## Related docs

- [Grading, Release & Exports](/docs/instructor-grading-publishing)
- [Organization Admin Guide](/docs/organization)
