---
key: student
path: student
title: Student Guide
category: Role Guides
order: 4
---

# Student Guide

## Dashboard Overview

When you log in to codePost, you will see the **Student Console**. This dashboard lists all the courses you are enrolled in.

### Course List

![The student dashboard showing a grid of enrolled courses](/assets/docs/student_dashboard.png)

- If you are enrolled in multiple courses, they will be displayed here.
- Click on a course to view its assignments.

## Assignments

For each course, you will see a table of assignments. The table includes:

![The assignment list view for a selected course](/assets/docs/student_assignment_list.png)

- **Assignment**: The name of the assignment.
- **Status**: Whether your submission is open, submitted, or graded (see details below).
- **Download**: A button to download assignment materials or starter code (if provided by the instructor). If the assignment has datasets, they are included in the zip in a `data/` folder.

### Statuses

- **Not published**: The assignment is announced but not yet open for submissions. You
  may still be able to read its description — and, once your instructor allows it,
  download the starter files.
- **No submission**: The assignment is open, but you haven't submitted anything yet.
- **Not reviewed yet**: You have submitted; grading isn't visible to you yet.
- **Grade available / Graded**: Your feedback is ready — click to see grades, comments,
  and the rubric. (Your instructor may release feedback all at once, per student as
  grading finishes, or live.)
- **Closed**: The deadline passed and the assignment no longer accepts submissions. If
  you submitted, you keep access to your work.

Expand an assignment row to read its **description**; it also appears above your files
while you work.

## Submitting Work

To submit an assignment:

1. Locate the assignment in the list.
2. Click the **Upload assignment** button (only available if the assignment is open for submission).
3. **Upload Files**:
   - You can drag and drop files into the upload area.
   - Or click to select files from your computer.
   - CodePost supports various file types including code files, PDFs, and Jupyter notebooks.
4. **Partners** (Optional):
   - If the assignment allows group submissions, you can add your partners by entering their email addresses.
   - Partners will also see the submission in their dashboard.
5. Click **Submit**.

### Best Practices

- **File Organization**: Submit the exact files requested (e.g., `main.py`). Avoid zipping files unless explicitly instructed.
- **Verification**: After uploading, you can download your files to ensure they are the correct versions and are not corrupted.

> [!NOTE]
> You can replace your submission as many times as you like before the deadline (or before grading begins, if the assignment has no deadline). Replacing a submission overwrites the previous files. Each file is capped at 10 MB.

## Viewing Feedback

Once an assignment is graded and released:

![Student view of a graded submission showing feedback and score](/assets/docs/student_feedback_view.png)

1. Click the **View Feedback** button on the assignment card.
2. You will be taken to the **Code Console**.
3. **Files**: Navigate through your submitted files using the file browser.
4. **Comments**:
   - Hover over highlighted code to see inline comments.
   - Review general comments and rubric scores in the sidebar.
5. **Grade**: Your final grade is displayed at the top or in the sidebar.

### Understanding the Code Console

The Code Console is where you review your graded work.

- **File Browser (Left)**: Switch between submitted files.
- **Code Viewer (Center)**:
  - **Highlights**: Specific lines of code may be highlighted. Hover over them to read the feedback.
- **Feedback Sidebar (Right)**:
  - **General Comments**: Overall feedback from the grader.
  - **Rubric**: Breakdown of points deducted or awarded.

## Regrade Requests

If enabled by your instructor, you may request a regrade or ask a question about your grade once your submission has been graded.

### Submitting a Request

1. Open the graded submission in the Code Console.
2. In the **Submission Info** panel on the right, look for the regrade request card.
3. Click **Submit Request**.
4. Choose whether this is a **Regrade Request** or a general **Question** using the toggle.
5. Write a clear explanation of which part of the grading you believe is incorrect and why.
6. Click **Submit**.

### Tracking Your Request

After submitting, the Submission Info panel shows the current status of your request:

- **Open**: Your request has been submitted and is waiting for a grader to review it.
- **Claimed**: A grader has picked up your request and is working on a response.
- **View Response**: The grader has responded. Click to read their reply.

### Deleting a Request

You can delete your request before a grader claims it by clicking the **Delete** button. Once a grader has claimed or responded to your request, it cannot be deleted.

### Deadlines

If your instructor has set a regrade deadline, you will not be able to submit a request after that date. The deadline is displayed in the regrade card.

> [!IMPORTANT]
> Use regrade requests responsibly. You can only submit one request per submission — make sure to include all relevant details. Frivolous requests may be penalized depending on course policy.

## Quizzes

Some courses use **quizzes** in codePost. A quiz may be **standalone** or **attached to an
assignment**.

### Finding a quiz

Quizzes show up in three places:

- **On the assignment card** — for quizzes attached to an assignment you're working on.
- **On the Quizzes page** — standalone quizzes live here, and attached quizzes also appear under
  "Assignment Quizzes."
- **On your dashboard** — a **"Quizzes to Take"** rail highlights open quizzes across all your
  courses.

If a quiz isn't open yet, it shows a **locked** state with a plain-language reason, such as "Opens
after you submit," "Opens after the assignment closes," or "Your quiz is being prepared."

### Missed the deadline?

If a quiz has already closed, you normally can't start it. But if your instructor gives you an
**access code**, use **Enter access code** on the closed quiz's card: a correct code starts your
attempt right away, with the quiz's normal time limit. If the code isn't accepted, check it with
your instructor — codes can be changed or removed at any time.

### Taking a quiz

- **Autosave** — your answers save as you go; you'll see a **"Saving… / Saved"** indicator, and the
  app warns you if you try to leave with unsaved changes.
- **Timer** — timed quizzes show a countdown that turns red in the final minute and **auto-submits**
  when it reaches zero.
- **One question at a time** — some quizzes step you through questions one at a time; depending on
  the settings you may or may not be able to go back.
- **Attempts** — some quizzes allow more than one attempt. When you have multiple, the quiz's
  scoring policy decides which one counts (highest, latest, or average).

### Quizzes that require Safe Exam Browser

Some instructors require a quiz to be taken in **Safe Exam Browser (SEB)** — a free
locked-down browser (Windows, macOS, iPad) that keeps the quiz as the only thing on your
screen. If a quiz requires it, opening the quiz in a normal browser shows a gate screen
instead of the questions:

![The Safe Exam Browser gate screen](/assets/docs/student_quiz_seb_gate.png)

1. If you don't have SEB yet, click **Download Safe Exam Browser** and install it (one
   time).
2. Click **Launch in Safe Exam Browser**. Your browser opens SEB automatically, and the
   quiz loads inside it with you already signed in — no setup or passwords to type.
3. Take the quiz as normal. When you submit, quit SEB and you're back in your regular
   browser.

If SEB doesn't open by itself, use the **Download the exam configuration** link on the
gate screen and open the downloaded file with Safe Exam Browser.

> [!NOTE]
> Launch links are single-use and expire after a few minutes — if a launch fails, go back
> to the quiz in your normal browser and press **Launch in Safe Exam Browser** again.
> Using Linux or ChromeOS (where SEB doesn't run)? Contact your instructor — they can
> exempt you so the quiz works in your normal browser.

### Reviewing your results

Once you've submitted (and if your instructor allows it), you can review your attempt: your
**score**, whether you **passed**, per-question **feedback** from graders, and — when the quiz
reveals them — the **correct answers**. If you had multiple attempts, an **attempt-history** list
shows each one and marks which attempt **counts toward your grade**.

> [!NOTE]
> Some questions (essays and code) are graded by a person, so part of your score may show as
> **"Awaiting grading"** until a grader gets to it.

Exactly what you see is up to your instructor's settings: results may be **held until the quiz
closes** (your score appears then, not at submit time), review may show your **answers or scores
only**, and some quizzes show just a **submission confirmation** with your score appearing on the
quiz card once results are released.

## Troubleshooting

- **Invite Code Invalid**: Double-check the code with your instructor.
- **Cannot Upload**: Check if the deadline has passed or if the file type is restricted.

## Related docs

- [Uploading Submissions](/docs/submission-upload)
- [FAQ](/docs/faq)
- [Instructor Overview](/docs/instructor)
