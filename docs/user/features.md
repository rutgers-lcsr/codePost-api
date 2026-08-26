---
key: features
path: features
title: Features
category: Reference
order: 17
---

# Features Guide

This guide covers advanced features available in codePost.

## Anonymous Grading

Anonymous grading mode hides student identities from graders to reduce bias in grading.

### Enabling Anonymous Grading

1. Go to **Admin Console > Assignments**
2. Click the **Settings** icon for the assignment
3. Navigate to the **Grading** tab
4. Toggle **Anonymous Grading Mode** on

### How It Works

When enabled:

- Graders see submissions labeled with anonymous IDs (e.g., "Student A", "Student B")
- Student names and emails are hidden during grading
- Admins can still view student identities
- Anonymization is removed when feedback is released

> [!IMPORTANT]
> Enable anonymous grading before grading begins. Graders who have already seen submissions will have seen the student names.

---

## Supported Languages

The codePost auto-run environment supports many programming languages. See [Environment & Testing Ops](/docs/instructor-environment-testing) for configuration guidance.

### Common Languages

- Python 3
- R
- Java

#### May work

The following are languages where some features may not work as expected:

- C/C++
- JavaScript/Node.js
- Ruby
- PHP

> [!IMPORTANT]
> codePost relies on your feedback to improve the auto-run environment. If you find that a language is not supported, please let us know at [codepost@cs.rutgers.edu](mailto:codepost@cs.rutgers.edu).

### Environment Detection

When Auto Detect Environment mode is enabled, codePost will:

1. Analyze submitted files
2. Detect the programming language
3. Set up appropriate build/run commands
4. Install detected dependencies

### Custom Environments

If your course requires specific libraries or language versions not covered by the default environment:

1. Go to **Assignment Settings > Environment**.
2. Select **Custom Docker Image**.
3. Provide a Dockerfile or pull from a registry.
   This ensures your autograder runs exactly as expected.

## AI-Assisted Grading

codePost integrates with AI providers to power several grading and course-setup features:

- **AI Suggested Comments** — the AI proactively surfaces comment suggestions in the Code Console sidebar while a grader reviews a submission. Graders can accept or dismiss each suggestion.
- **AI Submission Summaries** — on-demand AI overview of a student's submission, giving graders a quick understanding of what the student did before reviewing code.
- **AI Comment Generation** — graders can draft a comment and use AI to refine it for clarity, tone, and helpfulness.
- **AI Test Script Generation** — instructors can generate test scripts from assignment specifications and example code.

Instructors retain full control over the AI environment:

- **System Prompts**: customizing how the AI behaves.
- **AI Context Description**: per-assignment context that tells the AI what the assignment requires (can be auto-generated from your files, tests, and rubric).
- **Context**: deciding what information (code, rubric, etc.) is shared with the AI.
- **Model Choice**: configuring your preferred provider and model.

> [!IMPORTANT]
> **Enabling AI Features**
>
> 1. Go to **Course Settings > General**.
> 2. Scroll to **AI Features**.
> 3. Enter your **AI Provider**, **API Key**, and **Model Name**.
> 4. Click **Save**.
> 5. Enable **AI Comment Generation**.
> 6. Click **Save**.
>
> Once enabled, AI features are available in the grader interface. For suggested comments and submission summaries, also configure an **AI Context Description** in the assignment's **AI tab** (Assignment Settings > AI).
>
> ![AI Features configuration in Course Settings](/assets/docs/instructor_ai_settings.png)

For organization-level AI configuration, per-course inheritance, and usage analytics, see the [AI Settings & Usage Guide](/docs/ai-guide).

### AI Suggested Comments

When a grader opens a submission, the AI analyzes the code and surfaces comment suggestions as cards in the sidebar. Graders can **Accept** a suggestion (it becomes a draft comment on the relevant code) or **Dismiss** it. Both actions include a thumbs up/down feedback widget to help improve suggestions over time.

### AI Submission Summaries

The Submission Summary panel in the grading sidebar lets graders generate an AI overview of the full submission on demand. Click **Generate Summary** to produce a Markdown summary covering what the code does, notable patterns, and areas that may need close review. Summaries can be regenerated at any time.

### AI Context Description

Each assignment has an **AI Context Description** — a plain-text summary of what the assignment requires. The AI uses this when generating suggested comments and summaries. You can write it manually in Assignment Settings > AI, or auto-generate it from your assignment files, tests, and rubric by clicking the **Generate from Assignment Materials** button. Use the **Lock** toggle to prevent future auto-generations from overwriting a finalized description.

### Autograding and Tests Generation

codePost can automatically generate test cases and autograding scripts based on your assignment specifications. This feature uses AI to analyze your assignment description, provided code, and any sample tests you have to create comprehensive test suites.

To enable AI-generated tests:

1. Go to **Admin Console > Environment & Tests**.
2. Ensure the **Target File** is set for your assignment.
3. Open a test category and click **Generate (AI)** in the Test Script editor.
4. Review the generated script and adjust as needed.

### AI Comment Assistance

Graders can use AI to refine their feedback.

1. Highlight code to leave a comment.
2. Draft your thought (e.g., "function is too long").
3. Click **Generate** (robot icon) or press `Ctrl+G`.
4. The AI suggests a more constructive phrasing (e.g., "Consider refactoring this function into smaller helpers to improve readability.").

> [!NOTE]
> AI-generated tests are a starting point. You can always edit the script or use the builder to refine cases.

---

## Tests ✅

codePost supports script-based autograding that lets instructors define tests directly in the Test Script editor.

### Where to find it

1. Go to **Admin Console > Assignments > Environment**.
2. Select an assignment in **Environment & Tests**.
3. Select a **Test Category** or create a new one.
4. Use the **Test Script** editor (Code, Split Preview, or Builder).

### How it works

- Each test is defined in the script using a language-specific test decorator or macro.
- The backend parses your script and creates test cases automatically.
- The **Preview** panel shows how your tests will appear to graders.
- Total points are computed from the `points` values in your test definitions.
- Learning objectives can be tagged to tests for outcome tracking.

> [!IMPORTANT]
> Make sure each test includes a **name** and **points**. This keeps preview and scoring consistent.

### Dedicated Testing Guide

The full syntax reference, examples, and language-by-language patterns now live in the **Testing Guide**:

- [Testing Guide](/docs/testing-guide)

Use this as the source of truth for supported script formats and examples.
