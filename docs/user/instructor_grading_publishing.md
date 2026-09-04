---
key: instructor-grading-publishing
path: instructor-grading-publishing
title: Grading, Release & Exports
category: Instructor Workflows
order: 10
---

# Grading, Release & Exports

Use this page for day-to-day grading operations and release management.

## Grading in Code Console

![The instructor grading interface showing the code editor and file browser](/assets/docs/instructor_grading_interface.png)

### Submission views

In **Submissions**, use the view that matches your workflow:

- **By Student** for per-student progress
- **By Grader** for workload balancing

### Submission statuses

- **Unfinalized**: actively being graded
- **Finalized**: grading complete and ready for release

### Core grading sequence

1. Open submission in Code Console.
2. Review files and comments.
3. **Rubric Scoring**:
   - Click rubric items to apply them.
   - Use the search bar to find specific criteria.
   - Custom comments can be added for feedback not covered by the rubric.

![The rubric panel allows graders to apply predefined criteria to submissions](/assets/docs/instructor_grading_rubric_panel.png)

4. **Review**: Check test outputs and code execution results.
5. **Finalize**: Toggle the "Finalized" switch when grading is complete. This signals to admins that the submission is ready.

### Keyboard Shortcuts

Speed up your grading with these hotkeys:

- **General**:
  - `Cmd/Ctrl + /`: Show Shortcuts Guide
  - `Cmd/Ctrl + i`: Toggle Dark Mode
  - `Alt + Shift + R`: Report an issue to the codePost team
- **Navigation**:
  - `Cmd/Ctrl + Shift + f`: Toggle File Tab
  - `Cmd/Ctrl + Shift + g`: Toggle Rubric Tab
  - `Cmd/Ctrl + Shift + d`: Toggle Test Tab
- **Grading**:
  - `Enter`: Activate comment on highlighted line
  - `Shift + Enter`: Save comment
  - `Cmd/Ctrl + Enter`: Save and move to next

## Releasing feedback

Students do not see grades, comments, or the rubric until you open the **Feedback**
badge on the assignment row (next to Status) and pick a mode:

![The feedback picker](/assets/docs/instructor_feedback_picker.png)

| Feedback | What students see |
| --- | --- |
| **Hidden** (default) | Nothing — grade at your own pace. |
| **Live** | Feedback appears immediately as it's written — office hours, ungraded exercises. |
| **Per student** | Each student sees their grades, comments, and rubric as soon as *their own* submission is finalized — a rolling release with no global switch. |
| **Released** | Everything is out for all finalized submissions at once. |

Two extras:

- **Hide grades** (the `#` button on the row, or Settings > Publishing) masks numeric
  grades in any revealing mode — students see comments and the rubric but no number.
- **Release at** (Settings > Publishing) schedules an automatic move to Released —
  "grades out Friday 5pm" without being at a keyboard.

> [!IMPORTANT]
> Treat a global release as a coordinated event. Confirm policy checks (late
> submissions, exceptions, regrade queue) first — the pre-release checklist below helps.

> [!NOTE]
> Under **Per student**, finalizing a submission *is* the release for that student —
> make sure graders know their finalize toggle reveals feedback immediately.

## Export workflow

To export grades:

1. Open assignment or course grade export action.
2. Download CSV.
3. Validate student identifiers and totals before external upload.

## Operational playbook

### Before releasing

- Confirm finalization threshold reached
- Resolve obvious missing grades
- Spot-check rubric consistency

### After releasing

- Monitor regrade requests
- Track known rubric clarifications
- Export and archive grade snapshots

## Related docs

- [Grader Guide](/docs/grader)
- [Assignment Workflow](/docs/instructor-assignment-workflow)
- [Student Guide](/docs/student)
