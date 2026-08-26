---
key: ai-guide
path: ai-guide
title: AI Settings & Usage
category: Reference
order: 18
---

# AI Settings & Usage Guide

This guide covers how to configure AI features at the **organization** and **course** levels, how inheritance works between them, and how to monitor AI usage across your platform.

---

## Overview

codePost integrates with multiple AI providers to power these features:

- **AI Comment Generation** — graders can draft a comment and use AI to refine it for clarity, tone, and helpfulness.
- **AI Suggested Comments** — the AI proactively surfaces comment suggestions while a grader reviews a submission. Graders can accept or dismiss each suggestion.
- **AI Submission Summaries** — the AI generates an on-demand Markdown overview of a submission, giving graders a quick understanding of what the student did before diving in.
- **AI Test Script Generation** — instructors can generate test scripts from assignment specifications and example code.

AI settings can be configured at two levels:

| Level            | Who configures it | Scope                                                |
| ---------------- | ----------------- | ---------------------------------------------------- |
| **Organization** | Org admins        | Shared API key & model for all (or selected) courses |
| **Course**       | Course admins     | Per-course key, or inherit from the org              |

---

## Organization-Level AI Settings

Organization administrators can set up a shared AI configuration that courses can inherit, eliminating the need for every course admin to manage their own API key.

### Configuring Organization AI

1. Go to the **Organization Dashboard**.
2. Click the **AI Settings** tab.
3. Fill in:
   - **Provider** — Gemini, OpenAI, Ollama, Portkey, or Custom.
   - **API Key** — your provider API key (stored encrypted). After saving, a masked hint (e.g., `sk-…abc1`) is displayed so you can verify which key is active without exposing it.
   - **Base URL** — required for Ollama, Portkey, or Custom providers.
   - **Model** — select from the dropdown, which auto-populates with curated models and, when credentials are configured, live models fetched from your provider. You can also type to search.
4. Set the **Course Access Policy**:
   - **All courses** — every course in the org can use the shared key.
   - **Selected courses** — only courses you explicitly add to the list.
   - **Disabled** — no courses inherit; each course must use its own key.
5. Optionally toggle:
   - **AI Enabled** — master switch for all AI features org-wide.
   - **AI Comment Generation** — toggle comment generation independently.
6. Optionally expand **Custom Token Rates** to override the per-model cost rates used for usage estimates (see [Token Rate Overrides](#token-rate-overrides) below).
7. Click **Save**.

> [!IMPORTANT]
> Setting the course access policy to **Disabled** does not affect courses that have their own API key configured — it only controls whether courses can _inherit_ the organization's key.

---

## Course-Level AI Settings

Course admins configure AI for their specific course under **Course Settings > General > AI Features**.

### Using Organization Settings (Recommended)

If your organization has already configured AI and your course is allowed:

1. A banner will appear: **"Organization AI is available."**
2. Leave **Use own API key** toggled _off_.
3. The course will automatically use the organization's provider, model, and key.
4. You can still toggle AI features on/off for this course independently.

### Using Your Own API Key

If you prefer to use a different provider or key:

1. Toggle **Use own API key** _on_.
2. Enter your **Provider**, **API Key**, **Base URL** (if needed), and **Model**.
3. After saving the API key, a masked hint (e.g., `sk-…abc1`) appears below the key field so you can confirm which key is in use.
4. Optionally configure **Custom Token Rates** for cost tracking.
5. Click **Save**.

### AI Feature Toggles

Regardless of where the key comes from, each course has two independent toggles:

- **AI Enabled** — master switch for all AI features in this course.
- **AI Comment Generation** — specifically controls whether graders can use AI comment refinement.

> [!NOTE]
> If a course uses the organization key, disabling AI at the org level will disable it for the course. However, if a course has **Use own API key** enabled, it is completely independent of organization settings.

---

## AI Suggested Comments

AI Suggested Comments are proactive feedback cards surfaced by the AI while a grader is reviewing a submission. Unlike the **Generate** button (which refines a comment the grader is already writing), suggested comments appear automatically as a list in the Code Console sidebar — no prompt from the grader required.

### How suggestions appear

When a grader opens a submission, the AI analyzes the code and surfaces zero or more comment suggestions. Each suggestion card shows:

- The suggested comment text.
- The file and line range it applies to.
- The rubric item it is linked to (if any).

Hovering over a suggestion highlights the corresponding code lines in the editor. Clicking the card scrolls the highlight into view.

### Accepting and dismissing

| Action      | What happens                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------------- |
| **Accept**  | The suggestion is converted into a real comment on the submission. The grader can edit the text before saving. |
| **Dismiss** | The suggestion is marked as rejected and removed from the list. It does not become a comment.                  |

Graders always have final control — accepted text is a draft that can be edited before saving, not an auto-posted comment.

### Grader feedback

Each suggestion card has a **thumbs up / thumbs down** widget. Thumbs down opens a short text box ("What could be better?") for optional elaboration. This feedback is used to improve the AI prompts over time.

> [!NOTE]
> Suggested comments are generated when the submission is opened. If the assignment's AI features are disabled at the course level, or if the course has no AI configured, the suggestions panel will be empty.

---

## AI Submission Summaries

The AI Submission Summary gives graders a concise, AI-generated overview of a student's submission before they start reviewing. It appears as a collapsible panel in the Code Console sidebar.

### Generating a summary

1. Open a submission in the Code Console.
2. In the sidebar, locate the **Submission Summary** panel.
3. Click **Generate Summary**.
4. The AI analyzes all files in the submission and returns a Markdown summary.

The summary typically includes a brief description of what the student's code does, notable patterns or issues, and areas that may need closer attention.

### Regenerating

If you want a fresh summary (e.g., after editing or re-running a submission), click **Regenerate** in the panel header. The previous summary is replaced.

### Feedback

Like suggested comments, the summary panel includes a **thumbs up / thumbs down** widget. Providing feedback helps refine the underlying prompts.

> [!NOTE]
> Generating a summary counts as an AI call and is reflected in usage tracking. The **Request type** recorded is `submission_summary`.

---

## Usage Tracking & Analytics

Every AI API call is recorded with token counts, cost estimates, and metadata. Usage data is available at three levels.

### Course-Level Usage

Course admins can view AI usage for their course:

1. Go to **Course Settings**.
2. Select the **AI Usage** section in the settings navigation.
3. View total requests, tokens, estimated cost, projected cost, and breakdowns by assignment and by model.
4. Use the date range picker and granularity selector (hourly, daily, monthly) to zoom in.

### Organization-Level Usage

Org admins can view aggregated usage across all courses:

1. Go to **Organization Dashboard > AI Usage** tab.
2. View totals and charts for the entire organization.
3. The **Usage by Course** table shows per-course usage (including the course period for disambiguation).
4. The **Usage by Model** table shows token and cost totals broken down by which AI model was called.

### Platform-Level Usage (Superusers)

Platform staff can view usage across the entire platform:

1. Go to the **codePost Admin** dashboard.
2. Click the **AI Usage** tab.
3. View platform-wide totals with per-organization breakdown.
4. Optionally filter by a specific organization.

### What's Tracked

Each AI call records:

| Field              | Description                                                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Provider**       | Which AI provider was used (Gemini, OpenAI, etc.)                                                                                                |
| **Model**          | The specific model (e.g., `gpt-4o-mini`)                                                                                                         |
| **Request type**   | One of: `comment_generation`, `suggested_comments`, `submission_summary`, `assignment_description`, `test_generation`, `code_review`, `feedback` |
| **Input tokens**   | Tokens sent to the model                                                                                                                         |
| **Output tokens**  | Tokens returned by the model                                                                                                                     |
| **Estimated cost** | USD cost estimate, frozen at request time using the rates configured at that moment                                                              |
| **Status**         | `success` or `error`                                                                                                                             |
| **User**           | The grader or instructor who triggered it                                                                                                        |

---

## Supported Providers

| Provider          | Key required | Base URL                                              | Notes                                                       |
| ----------------- | ------------ | ----------------------------------------------------- | ----------------------------------------------------------- |
| **Google Gemini** | Yes          | No                                                    | Default: `gemini-2.5-flash`                                 |
| **OpenAI**        | Yes          | No                                                    | Default: `gpt-4o-mini`                                      |
| **Ollama**        | No           | Yes (e.g., `http://localhost:11434`)                  | Self-hosted, no cost tracking by default (add custom rates) |
| **Portkey**       | Optional     | Yes (e.g., `http://portkey-gateway.example.com:8787`) | AI gateway — key sent as `x-portkey-api-key` header         |
| **Custom**        | Yes          | Yes                                                   | Any OpenAI-compatible API (e.g., Azure, LiteLLM)            |

### Model Selection

When you select a provider, the **Model** dropdown automatically populates with:

1. **Curated models** — a hand-picked list of well-known models for that provider.
2. **Live models** — fetched in real-time from your provider's API using your credentials (when available).

You can also type in the dropdown to search or enter a custom model identifier (e.g., `gemini-2.5-flash`) not in the list.

---

## Cost Estimation

Cost estimates are calculated from per-model token pricing and recorded alongside each usage record. Self-hosted models (Ollama) and unknown models report $0 unless you add a custom rate.

Default rates are built in for common models:

- **Gemini**: `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `o3-mini`

> [!NOTE]
> Default rates are approximate and may lag behind provider pricing changes. They are intended for budgeting visibility, not billing.

Gateway providers (such as Portkey) often report model names with a provider prefix, like `my-gateway/gemini-2.5-flash`. Rate lookup first tries the full name, then falls back to the part after the last `/` — so prefixed models still match built-in defaults, and you can key a custom rate by either form (the full name wins if both exist).

### Estimated vs. Projected Cost

The usage dashboards show two cost figures:

- **Estimated Cost** — the sum of the cost recorded on each AI call *at the time it was made*. Calls made before a rate was configured are recorded at $0 and stay that way; this figure is a historical record and is never rewritten.
- **Projected Cost** — computed live from the recorded token counts using the *currently configured* rates. Use it to answer "what would this usage cost at today's prices?" — for example, after setting a rate for a model that previously showed $0, or to compare a past date range against new pricing.

Projected cost appears as a summary card, a dashed line on the cost chart, and a column in every breakdown table. At the course level it uses the course's effective rates (course overrides, then org rates, then defaults); the platform dashboard applies each organization's own rates.

### Token Rate Overrides

Organization and course admins can override the default token rates — useful for self-hosted models, volume-discounted pricing, or models not in the built-in list.

1. In the AI settings card (org or course level), expand the **Custom Token Rates** collapsible section.
2. The table shows all known models with their default input/output rates (in $/1M tokens).
3. Click **Edit** next to any model to override its rates.
4. To add a rate for a model not in the list, type the model name in the text field at the bottom and click **Add model**.
5. Overrides are shown with a blue "override" badge. Click the delete icon to revert to the default rate.
6. Click **Save** to persist your changes.

Rates set at the organization level flow down to every course automatically: in a course's rate table, org-configured models appear as read-only rows with a purple **org default** badge (built-in rates show a plain **default** badge). When the org adds a rate for a new model, it shows up in all its courses without any action on the course side. Clicking **Edit** on an org default creates a course-level override, which takes precedence for that course only.

Rate lookup precedence:

1. **Course custom rates** — if the course has a rate for the model, it wins.
2. **Organization custom rates** — if not set at course level, the org rate is used.
3. **Built-in defaults** — the hardcoded rates listed above.
4. **$0.00** — for completely unknown models with no overrides.

At each step, the full model name is tried first, then its name after the last `/` for gateway-prefixed models.

---

## Frequently Asked Questions

**Q: Can a course use AI without an organization key?**
Yes. Toggle **Use own API key** on and enter the course's credentials directly.

**Q: What happens if the org disables AI after courses are already using it?**
Courses that inherit the organization key will lose AI access immediately. Courses that have configured **Use own API key** are unaffected and will continue using their own credentials.

**Q: Is the API key visible to course admins?**
No. API keys are write-only — they can be set but never read back via the API or UI. A masked hint (e.g., `sk-…abc1`) is shown so admins can verify which key is configured.

**Q: Does AI usage affect grading performance?**
No. Usage recording is asynchronous and wrapped in error handling — a failure to record never blocks the grading workflow.

**Q: How do I track costs for self-hosted models (Ollama)?**
By default, self-hosted models report $0 because there are no API charges. If you want to track internal costs (e.g., GPU time), add a custom token rate override — see [Token Rate Overrides](#token-rate-overrides).

**Q: Can I see which model is consuming the most tokens?**
Yes. The usage dashboard includes a **Usage by Model** breakdown table showing token counts, costs, and request counts for each model used.

**Q: I set a token rate but Estimated Cost still shows $0. Why?**
Estimated cost is frozen into each usage record when the call is made, so usage recorded before the rate existed keeps its original $0. Check the **Projected Cost** figure instead — it reprices all recorded usage (including historical) at the currently configured rates. New calls made after you save the rate will record a correct estimated cost going forward.
