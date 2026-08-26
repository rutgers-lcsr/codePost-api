---
key: instructor-sections
path: instructor-sections
title: Managing Sections
category: Instructor Workflows
order: 8
---

# Managing Sections

Sections let you divide the course roster into named groups (e.g., recitation sections, lab slots, lecture tracks). You can assign graders as section **leaders** and use sections to scope grading work or filter the submission view.

## Where to find it

Go to **Roster > Sections** in your course admin panel.

## Creating a section

1. Click **Add section**.
2. Enter a unique section name (e.g., `Section A`, `Lab 01`, `R04`).
3. Click **Create** — the section appears in the table immediately.

Section names must be unique within the course. The dialog takes a name only; add students
and leaders afterwards from the sections table.

## Adding students to a section

Click the student count in a section row to open the section drawer. There are two ways to add students:

### Select from course roster

Switch to the **Select** tab, choose one or more students from the dropdown, then click **Add Selected**. Only students already enrolled in the course appear in the list.

### Paste a list of emails

Switch to the **Paste** tab, paste a newline- or comma-separated list of email addresses, and click **Add Pasted**. Emails that do not match enrolled students are silently skipped.

> [!NOTE]
> Students can only belong to one section at a time. If a student is already in another section, enable **Allow section reassignment** in the drawer before adding them. Without this toggle, students who already belong to a section are skipped.

## Bulk CSV import

To populate many sections at once, click **Import from CSV** above the sections table.

**Expected file format** (CSV or TSV, with or without a header row):

```
section,email,role
Section A,student1@university.edu
Section A,student2@university.edu
Section A,ta1@university.edu,leader
Section B,student3@university.edu
```

- Column order: section name first, email second, and an **optional** third `role` column.
- The `role` column marks the row's email as a section leader — use `leader` (`ta` and `grader`
  work too). Omit it, or use anything else, and the email is treated as a student. Existing
  two-column files therefore keep importing exactly as before.
- Headers are auto-detected and optional.
- Sections that do not yet exist are created automatically.
- Emails that are not on the course roster are skipped — and an email in a leader row is only
  applied if that person is already a **grader** on the course. A warning tells you how many
  were skipped.
- Before importing you get a preview table: each section with a **new** or **exists** tag, plus
  its student and leader counts.
- Students are assigned in batches; a live progress bar tracks the operation.
- Click **Cancel Import** mid-run to abort without losing work already done.

## Assigning leaders

Section leaders are graders responsible for a section. There are two ways to assign them.

### One section at a time

Click the pencil icon in the **Leaders** column, pick one or more graders from the dropdown —
each option shows how many sections that grader already leads, so you can spread the load — then
click the **check** button to save, or the **×** to discard your changes. Saving writes only the
leaders, so it will not disturb a roster edit someone else is making to the same section at the
same time.

### All sections at once

Click **Assign graders** above the sections table to open the **Assign Graders to Sections**
matrix: one row per grader, one column per section, and a checkbox where they meet. It is built
for staffing a whole term in one pass.

![The Assign Graders to Sections matrix, with a checkbox per grader and section](/assets/docs/instructor_section_leaders.png)

- A banner at the top tells you how many sections have **no leader**, and how many unsaved
  changes you are holding.
- Each section column header shows its leader count, with a red warning icon at zero.
- The **Sections** column counts how many sections each grader leads, tagged with the `+`/`-`
  change your edits would make.
- **Distribute evenly** fills in every section that currently has no leader — one grader each,
  round-robin from the least-loaded graders. It only stages the change; nothing is written until
  you save.
- Edits are local until you press **Save (N sections)**, which writes one leaders-only update per
  changed section. If one section fails, the rest still save and the failed one keeps its pending
  edit. **Cancel** drops all staged changes.

> [!NOTE]
> Leading a section is not a role by itself — a leader must also be a grader on the course
> (**Roster > Graders**). For someone who *is* a grader, leading a section grants access to the
> submissions of the students in that section, in addition to submissions assigned to them
> directly.

## Removing a student from a section

Open the section drawer and click the **×** icon next to a student's email. The student remains enrolled in the course — only their section membership is cleared.

## Deleting a section

Click the trash icon in the **Actions** column and confirm. Deleting a section does not remove the students from the course, but it clears their section assignment.

## Tips

- Set up sections before grading starts so you can use section filters in grading views.
- For large courses, CSV import is far faster than adding students one by one.
- Name sections consistently across terms (e.g., `R01`, `R02`) to simplify bulk uploads and reporting.
- If your enrollment manager exports a roster CSV with a section column, you can usually adapt it to the format above with minimal editing — the `role` column is optional, so `section,email` is enough.

## Related docs

- [Course Setup & Roster](/docs/instructor-course-setup)
- [Grader Guide](/docs/grader)
- [Uploading Submissions](/docs/submission-upload)
