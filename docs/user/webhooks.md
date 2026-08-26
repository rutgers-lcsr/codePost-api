---
key: webhooks
path: webhooks
title: Webhooks
category: Reference
order: 21
---

# Webhooks

Webhooks let codePost notify an external service whenever something changes in a course — a new submission, a finalized grade, a published assignment, and so on. Use them to sync grades to an LMS, post alerts to Slack, kick off downstream jobs, or build custom integrations.

## How webhooks work

1. You register a **hook** with a target URL and an event name.
2. When that event fires in codePost, the platform sends a POST request to your target URL.
3. The request body is a JSON payload describing the changed object.
4. codePost records the last delivery time and HTTP status on the hook.

Hooks are scoped to a single **course** — they only fire for events in that course.

## Registering a hook

Hooks are managed through the REST API on the `webhooks/` endpoint. Course admins can create and manage hooks for their own courses.

```bash
curl -X POST https://codepost-api.cs.rutgers.edu/webhooks/ \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "course": 123,
    "event": "submission.added",
    "target": "https://hooks.example.com/codepost/new-submission"
  }'
```

Fields:

| Field                   | Description                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| `course`                | Course ID the hook belongs to.                                                             |
| `event`                 | Event name from the table below.                                                           |
| `target`                | Absolute HTTPS URL where the payload will be POSTed.                                       |
| `is_active`             | If `false`, the hook is registered but skipped at delivery time. Useful for pausing.       |
| `last_triggered_at`     | _(read-only)_ Timestamp of the most recent delivery.                                       |
| `last_triggered_status` | _(read-only)_ HTTP status code of the most recent delivery, or an error marker on failure. |

## Available events

Events follow a `<resource>.<change>` naming pattern. The most common ones:

### Course

- `course.changed` — any field on the course updated
- `course.name`, `course.period`, `course.archived` — specific field changes
- `course.students`, `course.graders`, `course.courseAdmins` — roster changed

### Section

- `section.added`, `section.changed`, `section.removed`, `section.name`

### Assignment

- `assignment.added`, `assignment.changed`, `assignment.removed`
- `assignment.name`, `assignment.points`, `assignment.explanation`
- `assignment.state` — lifecycle transition (draft/visible/preview/published/closed/archived)
- `assignment.feedbackStatus` — feedback flow transition (hidden/live/per_student/released)

### Rubric

- `rubricCategory.added` / `.changed` / `.removed`
- `rubricCategory.name`, `rubricCategory.pointLimit`, `rubricCategory.helpText`
- `rubricComment.added` / `.changed` / `.removed`
- `rubricComment.text`, `rubricComment.explanation`, `rubricComment.pointDelta`

### Submission

- `submission.added` — new submission uploaded
- `submission.changed` — any field changed
- `submission.removed` — submission deleted
- `submission.grader` — assigned grader changed
- `submission.isFinalized` — finalized / unfinalized
- `submission.questionIsOpen` — regrade question opened/closed

### File

- `file.added`, `file.changed`, `file.removed`
- `file.data`, `file.name`, `file.extension`

### Comment

- `comment.added`, `comment.changed`, `comment.removed`
- `comment.text`, `comment.pointDelta`, `comment.rubricComment`

### Test cases & environment

- `testCategory.added` / `.changed` / `.removed`
- `testCase.added` / `.changed` / `.removed` and per-field events (`testCase.pointsPass`, `testCase.exposed`, etc.)
- `submissionTest.added` — a test result was recorded
- `environment.added` / `.changed` / `.removed`, `environment.isRunning`

### Solution & helper files

- `solutionFile.added` / `.changed` / `.removed`
- `helperFile.added` / `.changed` / `.removed`
- `fileTemplate.added` / `.changed` / `.removed`

> [!NOTE]
> Per-field events (e.g. `assignment.name`) fire **in addition to** the generic `*.changed` event when that specific field is the one that changed. Subscribe to whichever is more useful for your integration.

## Payload format

Each delivery is a POST with `Content-Type: application/json`. The body is a serialized representation of the affected model.

Example payload for `submission.added`:

```json
{
  "event": "submission.added",
  "data": {
    "id": 4711,
    "assignment": 88,
    "students": ["student@university.edu"],
    "grader": null,
    "isFinalized": false,
    "grade": null,
    "created": "2026-05-21T15:30:00Z"
  }
}
```

> [!IMPORTANT]
> The exact shape of `data` mirrors the corresponding model serializer. Fields may be added over time, so write consumers that **tolerate unknown fields** rather than asserting a fixed schema.

## Reliability and retries

- Deliveries are asynchronous — codePost does not block the user-facing action waiting for your endpoint.
- The most recent delivery status is recorded on the hook (`last_triggered_status`).
- codePost does **not** currently retry failed deliveries automatically. If your endpoint returns a non-2xx status, no second attempt is made. Build idempotency on your side and reconcile by polling the API if you need guaranteed delivery.

## Security recommendations

- Use **HTTPS** for your target URL. codePost does not encrypt payloads beyond TLS.
- Treat the payload as untrusted input — validate it before acting.
- Restrict the receiving endpoint to expected traffic (IP allowlist, shared secret in the URL path, or a reverse-proxy auth layer).
- Rotate the URL/secret if you suspect leakage. Update the hook's `target` field via the API.

## Listing and managing hooks

```bash
# List all hooks you have access to
curl https://codepost-api.cs.rutgers.edu/webhooks/ \
  -H "Authorization: Token YOUR_API_TOKEN"

# Pause a hook
curl -X PATCH https://codepost-api.cs.rutgers.edu/webhooks/42/ \
  -H "Authorization: Token YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "is_active": false }'

# Delete a hook
curl -X DELETE https://codepost-api.cs.rutgers.edu/webhooks/42/ \
  -H "Authorization: Token YOUR_API_TOKEN"
```

## Common integrations

- **LMS grade sync** — listen to `assignment.feedbackStatus` (released) or `submission.isFinalized` and push grades to Canvas/Blackboard.
- **Slack notifications** — post to a channel on `submission.added` for staff-grading channels or `assignment.state` (published) for announcements.
- **Plagiarism pipelines** — kick off MOSS or a custom comparison job on `submission.added`.
- **Roster sync confirmation** — react to `course.students` / `course.graders` to mirror codePost roster changes into another system.

## Related docs

- [SDK Overview](/docs/sdk-overview) — programmatic access for batch operations
- [Programmatic Comments](/docs/programmatic-comments) — SDK examples for grading workflows
- [Course Activity Log](/docs/activity-log) — for user-action auditing (not for cross-system integration)
