---
key: grader
path: grader
title: Grader Guide
category: Role Guides
order: 5
---

# Grader Guide

This guide helps graders and TAs work efficiently in codePost while staying aligned with instructor policy.

## Before you start grading

1. Confirm you are in the correct course and assignment.
2. Review instructor grading policy (rubric rules, late policy, collaboration expectations).
3. Check whether grading is anonymous.
4. Confirm whether submission edits and test re-runs are allowed.

## Core grading workflow

1. Open **Submissions** and filter to your queue.
2. Open a submission in **Code Console**.
3. Review files and add inline comments.
4. Apply rubric items for consistent scoring.
5. Review test/output panels as needed.
6. Mark the submission **Finalized** when complete.

> [!IMPORTANT]
> Finalized submissions are ready for release — students see feedback once the instructor opens the assignment's **Feedback** flow. One exception: if the instructor set feedback to **Per student**, finalizing reveals that student's feedback immediately.

## Reviewing Jupyter notebooks

`.ipynb` files render in the Code Console as a notebook view — code cells, Markdown cells, and outputs (including images and rich displays) appear in the same order the student saw them.

- **Inline comments** attach to individual code cells. Hover a cell and click the comment icon, or place the cursor in a cell and press `Enter`.
- **Cell outputs** are rendered as-is from the notebook file. If a student didn't re-run the notebook before submitting, the outputs may be stale — flag this in feedback when scoring requires verified outputs.
- **Markdown cells** render with code blocks, math, and images. If an image is referenced by a path that wasn't uploaded with the notebook, it shows as broken.

> [!TIP]
> If you need to verify that a student's notebook actually produces the outputs shown, use the **Auto-Run** output panel — the autograder re-executes the notebook fresh and shows you what it actually produces, not what was saved in the file.

## Reviewing PDFs

PDFs (problem sets, written work) render with a built-in PDF viewer. Two kinds of comments are supported:

- **Text-offset comments** — select text inside the PDF, then leave a comment. The selection is highlighted in-place for the student.
- **Region comments** — `ALT` + drag a rectangle over any area of the page (figures, diagrams, handwritten work). The region is outlined and the comment attaches to that bounding box.

Region comments are the right choice for scanned handwritten work, diagrams, or anything where text selection isn't reliable. In the comment sidebar, region and text comments are interleaved by page order, not by selection time.

## Reviewing binary files

If a student submits a binary file (e.g. `.jar`, `.class`, `.exe`, `.docx`, compiled artifacts), the Code Console shows a **Binary Preview** panel instead of opening it in the code editor — those files aren't human-readable text and would garble the editor.

The panel shows:

- File name, size, and detected MIME type
- A **Download** button to save the file locally
- A **View as Hex** toggle that switches the panel into a side-scrollable hex/ASCII viewer

Use **View as Hex** when you need to confirm what a student actually submitted (e.g. checking magic bytes, spotting an empty file padded with whitespace, verifying a file isn't just a renamed text file). Use **Download** when you need to run the artifact locally to grade it.

> [!NOTE]
> The hex viewer is read-only — there is no way to annotate or comment on byte ranges. For grading feedback on binary submissions, leave a general comment on the submission rather than an inline one. Plans for more granular binary feedback are in the roadmap.

## Editing student submission files

You can edit a student's submission file directly in the Code Console — for example, to fix a stray syntax error so you can re-run tests against the rest of their code, or to demonstrate a small change inline.

- Edits are **saved server-side per file** as soon as you save, so they survive page reloads and are visible to other graders/instructors on the same submission.
- The **original student submission is never modified**. Your edit is stored alongside the file; the student's uploaded version is preserved untouched.
- Each saved edit records who last modified it.
- **Graders** can only save edits when the instructor has enabled **Graders can edit submissions** in the assignment settings. Course admins and instructors can always save edits.

> [!IMPORTANT]
> Check your course's policy before making functional changes to a student's code. For most courses, file edits are appropriate for debugging/probing only, not for adding code the student didn't write.

## Using comments effectively

- Be specific: reference behavior, location, and fix direction.
- Use reusable rubric comments for repeated patterns.
- Prefer actionable feedback over one-word notes.
- Keep tone professional and supportive.

## Rubric and scoring tips

- Apply rubric criteria consistently across all submissions.
- Use partial credit where policy allows.
- If a rubric item is ambiguous, flag it early for instructor clarification.
- Avoid hidden policy changes mid-stream.

### Rubric not saving or loading

- Use `Cmd/Ctrl + Shift + R` to hard refresh the Code Console.
- Ensure your internet connection is stable; rubric updates are real-time.

### Code not loading (spinner)

- If a file is too large, it may take moments to render.
- If it persists, check the browser console for errors and report to **Contact Us**.

## Keyboard Shortcuts

Efficient graders use hotkeys. Press `Cmd/Ctrl + /` to see the full list in the console.

- **General**:
  - `Alt + Shift + R` : Report an issue to the codePost team

- **Navigation**:
  - `Alt + [` / `]` : Next/Previous File
  - `Cmd/Ctrl + Shift + f` : Toggle File Browser
- **Grading**:
  - `Enter` : Start comment on selected line
  - `Cmd/Ctrl + Enter` : Save comment and jump to next
  - `Cmd/Ctrl + Shift + g` : Toggle Rubric

Use outputs and tests to inform feedback, not replace manual reasoning:

- **Auto-Run output** shows what code produced at run time.
- **Script-based tests** summarize test pass/fail and scoring behavior.
- If results look stale, request or perform a re-run based on course policy.

For test syntax and parser behavior, see [Testing Guide](/docs/testing-guide).

## Common grader scenarios

### I see a broken environment or missing dependency

1. Capture the error message.
2. Check if the issue is submission-specific or assignment-wide.
3. Escalate assignment-wide issues to instructors/admins.
4. Continue grading unaffected submissions when possible.

### Handling regrade requests

When a student submits a regrade request, it appears in two places:

- **Regrade Requests panel** (grader dashboard): Shows all assignments with open and closed requests. Click an assignment name to see the full list.
- **Submission Info** (Code Console sidebar): When viewing a submission with a regrade request, the request text, status, and action buttons appear directly in the sidebar.

#### From the Regrade Requests panel

1. Navigate to the **Regrade Requests** tab in the grader dashboard.
2. Click the assignment name to see all requests.
3. Use the **Claim** button to assign a request to yourself.
4. Click **Respond** to write your response, or **View** to open the submission in the Code Console.
5. After writing a response, choose **Save Draft** to keep working, or **Submit & Close** to finalize.
6. You can **Re-open** a closed request if needed.

#### From the Code Console

When viewing a submission that has a regrade request:

1. The **Submission Info** panel shows the request text and status.
2. Click **Claim** to assign it to yourself.
3. Click **Respond** to write your response inline.
4. Use **Submit & Close** to send your response and close the request.
5. Use **Release** if you want to unassign yourself.

> [!NOTE]
> Students can see your email as the responder once you submit a response. Keep your tone professional and constructive.

#### Tips

- Claim requests promptly so students know their request is being reviewed.
- Leave an audit trail — your response is visible to the student and the instructor.
- Avoid direct score edits without a written rationale in the response.
- If you are unsure about a regrade, escalate to the instructor rather than guessing.

### I cannot access a submission

- Verify you are assigned to the student/section.
- Ask an instructor/admin to confirm roster role and permissions.

---

## Grading quizzes

Some question types on a quiz — **essay** and **code** — can't be graded automatically and need a
person. Everything else (multiple choice, true/false, short answer, numerical) is scored the moment
the student submits, so you only ever see the responses that genuinely need a human.

> [!IMPORTANT]
> Graders can grade quizzes by default — if a **Quiz Grading** item appears in your grader
> navigation, you have access. Some courses restrict it: the instructor turns off *Graders Can
> Grade Quizzes* and grants the **Quiz Grader** role per grader in Roster → Graders. If you don't
> see the nav item, ask your instructor for that role.

To grade:

1. Open **Quiz Grading** and pick a quiz — its "needs grading" count is shown.
2. If the course uses sections, set the **section filter** to your own students. codePost remembers
   the choice per course, so you land on the same section next time.
3. Pick an attempt. The **focused grader** opens full-height on one response at a time: assign
   points and optionally leave **feedback** for the student.
4. Press **Next** (**Finish** on the last one) or `⌘/Ctrl + Enter` to save and move to the next
   response awaiting grading. **Skip** moves on without grading.
5. Use **Reopen** to undo a grade you already saved and send it back to the queue (your feedback is
   kept as a draft).

![The focused quiz grader, showing one response with the points and feedback panel](/assets/docs/instructor_quiz_focused_grader.png)

While you are in the focused grader:

- The header shows the student, their attempt number, the running score, and how far through the
  queue you are.
- The numbered **chips** jump to any other question in the same attempt — a dot means it still
  needs grading, a check means it is done.
- **Grade below** / **Grade beside** moves the points-and-feedback panel under the question or
  beside it; codePost remembers your choice and the panel size.
- **Answer key (graders only)** expands the expected answer where the instructor provided one.
  Students never see it.

> [!TIP]
> **You don't have to remember to save.** Navigating away — Next, a chip, back to the queue, or
> closing the grader — saves the grade you have typed first. If the save fails you stay put, so
> nothing is silently lost. The exception is feedback with no valid points, which can't be
> recorded: enter points to save the grade.

> [!TIP]
> **Run a student's code.** On a **Code** response, use **Run code** to execute the student's
> answer in the course's sandbox and see its output (stdout, errors, and any plots) right in the
> grading view — with their submission files and datasets staged, so answers that reference "their"
> data work. This is grader-only and never shown to the student.

If the quiz's instructor enabled **Graders can review generated**, you may also review the
AI-generated per-student question sets; otherwise that stays admin-only.

---

## AI tools

When the course instructor has enabled AI features, you have three AI tools available in the Code Console.

### AI comment generation (Generate button)

Every comment text area has a **Generate** button (robot icon, or press `Ctrl+G`).

1. Select one or more code lines and open a comment.
2. Optionally link a rubric item — the AI uses it as context.
3. Optionally type a draft — the AI will refine it.
4. Click **Generate**. The AI fills in the comment text based on the selected code, rubric item, and any draft you wrote.
5. Review and edit before saving.

Generated text is always a draft — nothing is auto-posted.

### AI suggested comments

When you open a submission, the AI may surface **Suggested Comments** in the sidebar — proactive feedback ideas based on the code, without requiring you to start a comment first.

Each suggestion card shows the proposed text and the code range it targets. Hover over a card to highlight the relevant lines in the editor.

- Click **Accept** to convert the suggestion into a real comment on that code range. You can edit it before saving.
- Click **Dismiss** to remove the suggestion from the list permanently.

You can leave a **thumbs up / thumbs down** on each suggestion. Thumbs down opens a short text box for optional feedback, which helps improve suggestions over time.

### AI submission summary

The **Submission Summary** panel in the sidebar gives you a quick AI-generated overview of the student's work before you start reviewing.

1. Open the **Submission Summary** panel in the sidebar.
2. Click **Generate Summary** if no summary exists yet.
3. The AI returns a Markdown summary covering what the code does, notable patterns, and areas to look at closely.
4. Click **Regenerate** at any time if you want a fresh summary (e.g., after a re-run).

Like suggested comments, the summary has a thumbs up / thumbs down widget for quality feedback.

> [!NOTE]
> AI features are configured by your course instructor. If you don't see the Generate button, suggested comments, or the summary panel, AI may not be enabled for this course. Contact your course admin.

For full details on AI configuration, see the [AI Settings & Usage Guide](/docs/ai-guide).

---

## Related docs

- [Instructor Overview](/docs/instructor)
- [Grading, Release & Exports](/docs/instructor-grading-publishing)
- [Student Guide](/docs/student)
- [FAQ](/docs/faq)
