---
key: instructor-course-setup
path: instructor-course-setup
title: Course Setup & Roster
category: Instructor Workflows
order: 7
---

# Course Setup & Roster

Use this page when launching a new course or preparing for a new term.

## Course setup checklist

1. Create the course with clear name and period.
2. Set timezone and general course defaults.
3. Configure invite code behavior.
4. Decide whether students can see grader identities.
5. Configure grader/rubric editor permissions.

## Managing roster

Go to **Roster** and choose the role tab:

- **Students**: add/invite students and manage sections.
- **Graders**: add TAs and assign permissions.
- **Admins**: add instructor-level users.

### Enrollment methods

- Direct invite by email
- Invite code self-join (if enabled)
- Bulk workflows where supported by your process

### Sections and staffing

- Group students by section for assignment and grading workflows.
- Align grader assignments to section ownership early.
- Reconcile drops/adds weekly during active enrollment windows.

## Policy defaults to lock in early

- Anonymous grading defaults
- Rubric editing permissions
- Late policy and deadlines strategy
- Student upload eligibility

> [!TIP]
> Write a short “grading playbook” for your graders and pin it in course communications. Consistency beats heroics.

## Course API keys

A **course API key** lets an external tool — a script, a Jupyter integration, an AI assistant —
work with this course's data without anyone sharing a personal password. Each key is scoped to the
one course that issued it and cannot reach any other course.

Find them under **Course Settings > API Keys**. Creating and revoking keys is restricted to course
admins.

### Creating a key

1. Click **Create Key**.
2. Give it a name that says where it will be used (e.g., `gradebook-sync`, `Jupyter notebook`).
3. Choose a **scope** — see below.
4. Copy the key from the confirmation dialog. **It is shown once and never again**; if you lose it,
   revoke the key and create another. **Copy Full Token** gives you the whole `CourseKey …` header
   value, **Copy Key Only** just the key itself.

Use it as an `Authorization` header:

```
Authorization: CourseKey cpk_<course_id>_<secret>
```

### Scopes

| Scope | What an assistant connected with this key may do |
| ----- | ------------------------------------------------ |
| **Read only** | Answer questions about the course. The recommended default. |
| **Read & write** | Also manage assignments and settings — no deletes, and no emailing students. |
| **Full admin** | Also deletes, quiz attempt resets, and emailing students. |

> [!NOTE]
> The scope governs what an **AI assistant connected with the key** is allowed to do — a read-only
> key never even sees the tools that would change anything. It is not a second permission system
> for ordinary API and SDK requests, which remain limited to this one course. Pick the narrowest
> scope that does the job, and prefer a separate key per integration so you can revoke one without
> breaking the others.

> [!TIP]
> To connect Claude Code, Claude Desktop, or another MCP client to your course with one of these
> keys, see [AI Agents (MCP)](/docs/mcp-agents).

### Managing existing keys

The table lists each key with its scope, status, and creation date.

- **Disable** switches a key off without deleting it — useful while you track down what is using it.
  **Enable** turns it back on.
- The **trash** icon permanently revokes a key. Anything using it stops working immediately, and the
  key cannot be restored.

## Archiving a course

At the end of a term, **archive** the course rather than deleting it. Archived courses are preserved read-only — students can still view their feedback and instructors can still export grades, but no further edits are accepted on the course or any of its assignments, rubrics, submissions, or comments.

### To archive

1. Open **Course Settings > Behavior**.
2. Toggle **Archive Course** on.
3. Confirm. The course is immediately marked archived.

### What archiving does

- Disables editing on the course and all attached resources (rubrics, assignments, submissions, comments, environments).
- Keeps the course visible in dashboards under an **Archived** filter.
- Stops Auto-Run, autograder runs, and webhook deliveries triggered by changes (no edits = no events).
- Frees up the course name/period combo for the next term (you can clone assignments from an archived course into a new active one).

### Un-archiving

Toggle **Archive Course** off in Course Settings > Behavior. The course returns to fully editable state. Un-archive only when you genuinely need to fix data — re-opening an old term's course for the original students is rarely the right move (clone into a new course instead).

> [!IMPORTANT]
> Once a course is archived, in-flight regrade requests cannot be responded to. Resolve open regrade requests **before** archiving.

## Related docs

- [Managing Sections](/docs/instructor-sections)
- [Assignment Workflow](/docs/instructor-assignment-workflow)
- [Grader Guide](/docs/grader)
- [Organization Admin Guide](/docs/organization)
