---
key: submission-upload
path: submission-upload
title: Uploading Submissions
category: Role Guides
order: 13
---

# Uploading Submissions

This guide covers how to upload student submissions to codePost, both for students and instructors.

## Student Uploads

When an assignment allows student uploads, students can submit their work directly through codePost.

### How to Submit

1. Navigate to the **Student Console**
2. Select your course and assignment
3. Click **Upload Files** or drag and drop files into the upload area
4. Add partners (if group submissions are allowed)
5. Click **Submit**

### Supported File Types

- Code files (`.py`, `.java`, `.cpp`, `.js`, etc.)
- PDF documents
- Jupyter notebooks (`.ipynb`)
- Text files

> [!NOTE]
> Your instructor may restrict which file types can be uploaded. Check the assignment requirements.

### Replacing a Submission

You can replace your submission at any time before the deadline (or before grading begins, if the assignment has no deadline). Simply upload new files — they will replace your previous submission.

---

## Instructor Bulk Upload

Instructors can upload multiple student submissions at once using the bulk upload feature.

### Folder Structure

Organize submissions in folders named by student email or identifier:

```
submissions.zip
└── submissions/
    ├── student1@email.com/
│   ├── file1.py
│   └── file2.py
├── student2@email.com/
│   ├── file1.py
│   └── file2.py
└── student3@email.com/
    └── file1.py
```

### How to Bulk Upload

1. Go to **Admin Console > Assignments > Overview**
2. Click on the assignment
3. Navigate to **Submissions** tab
4. Click **Upload Submissions**
5. Drag and drop your folder or select files
6. Verify the detected submissions
7. Click **Upload**

### Troubleshooting Uploads

- **File Size Limit**: Individual files are capped at **10 MB**. For larger files (e.g., datasets, reference inputs), use **Instructor Resources** or attach a [Data Set](/docs/instructor-environment-testing#data-sets) to the assignment.
- **Forbidden Extensions**: If a file fails, check if the assignment restriction excludes it (e.g., no `.exe`).
- **Encoding Errors**: Ensure filenames use standard UTF-8 characters.

### Partner Submissions

For group submissions, include all partner emails in the folder name or use a partners file:

```
student1@email.com+student2@email.com/
├── file1.py
└── file2.py
```

### API Upload

For automated workflows, you can use the codePost API to upload submissions programmatically. See the API documentation for details.

> [!TIP]
> Test your upload with a small batch first to verify the folder structure is correct.
