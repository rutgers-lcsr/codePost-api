---
key: organization
path: organization
title: Organization Guide
category: Role Guides
order: 12
---

# Organization Admin Guide

This guide is designed for **Organization Administrators**. It covers how to manage your organization's settings, users, and courses within codePost.

## Overview

The Organization Dashboard provides a high-level view of your organization's activity.

- **Organization Details:** View your organization's name, short name, and SSO status.
- **Analytics:** Monitor key metrics such as Total Users, Active Users (30d), Total Courses, Active Courses, and Submission counts.

## Managing Users

Navigate to the **Users** tab to manage the members of your organization.

### User Actions

You can perform the following actions on users:

- **Approve/Decline:** For users in "Pending" status who have requested to join.
- **Promote to Org Staff:** Grant a user administrative privileges within the organization.
- **Demote:** Remove administrative privileges from a staff member.
- **Reset Password:** Send a password reset email to a user (only for non-SSO users).
- **Remove:** Permanently remove a user from the organization.

You can also search for specific users by email using the search bar.

### Pending admin requests

When someone signs up as an **instructor** with an email that matches your organization, their account is created with pending verification — they cannot log in or create courses until an admin approves them.

1. Open the **Pending Admins** tab in your organization dashboard. The tab shows a count badge when there are open requests.
2. Each row shows the user's email, name, signup date, and the organization they signed up under.
3. Click **Approve** to activate the account. The user immediately gains the ability to create courses and modify rosters, and receives an activation email.
4. Click **Deny** to reject the request. The user is removed; nothing is sent.

> [!IMPORTANT]
> Approval is irreversible in the sense that the user is now an active instructor — if they shouldn't be, you can demote them, remove their access from specific courses, or remove them from the organization entirely. Deny **before** approving when in doubt.

### Impersonating users

For support and debugging, organization admins can impersonate users within their own organization. Impersonation issues a fresh JWT and logs the event as an **audit** record (visible in system logs, not in the course Activity Log).

**Permission scope:**

- **Org admins / staff / superusers:** can impersonate any user in the organization.
- **Course admins:** can only impersonate students and graders in courses they administer.
- **Course-scoped requests (API keys):** can only impersonate members of the scoped course.

#### Users

Users are the backbone of the codePost system. Users can be added to the organization by adding their email to a course. A user will automatically be created next time they sign in. If an Organization uses SSO, codePost assumes SSO handles user authentication.

## Managing Courses

The **Courses** tab lists all courses within your organization.

### Creating and Editing Courses

You can manage specific settings for each course:

- **Basic Info:** Name, Period (e.g., Fall 2023), Timezone, and Archive status.
- **Settings:**
  - **Email New Users:** Toggle whether new students receive welcome emails.
  - **Invite Code:** Enable/Disable and reset the invite code for student self-registration.
  - **Students Can See Graders:** Toggle visibility of grader identities.
- **Grading:** Configure anonymous grading defaults and rubric editing permissions.

## Organization Settings

The **Settings** tab allows you to configure global preferences, particularly security and integrations.

### Email Settings

- **Primary Email Domain:** The default domain associated with this organization (e.g., `university.edu`). Used to route SSO logins and to set the default sender for organization emails.

  > [!IMPORTANT]
  > The primary domain is used to create new users via SSO — make sure the domain is valid and deliverable, and that your IdP issues identities under that domain.

- **Allowed Email Domains:** A list of **additional** domains that should also map to this organization. Useful when an institution has multiple valid email domains (e.g. `rutgers.edu` plus the student subdomain `scarletmail.rutgers.edu`, or `university.edu` plus an affiliated college). A user signing in via SSO with any of these domains is routed to your org.

  Edit the list inline in the Settings tab — comma- or newline-separated. Adding a domain takes effect immediately for new logins; existing users are not migrated automatically.

- **Send Welcome Emails:** When on, users added via roster upload receive a welcome email with their account details. When off, accounts are still created but no email is sent — useful when you handle onboarding through a separate channel (e.g. LMS announcement). Course admins can also override this per course in Course Settings.

### Single Sign-On (SSO)

You can configure SSO to allow users to log in with your university or corporate credentials. Supported providers include:

- **CAS:** Central Authentication Service (requires Server URL and Version).
- **Azure AD:** Requires Tenant ID, Client ID, and Client Secret.
- **OIDC:** OpenID Connect (requires Discovery URL).
- **Google Workspace:** Google OAuth integration.

Enable **SSO Activation** to automatically activate new users who log in via SSO.

### AI Settings

Organization admins can configure a shared AI provider and API key that courses can inherit, centralizing AI management and cost tracking.

1. Go to the **AI Settings** tab in the Organization Dashboard.
2. Select a **Provider** (Gemini, OpenAI, Ollama, or Custom) and enter your **API Key**.
3. Set the **Course Access Policy** to control which courses can use the shared key:
   - **All courses** — every course inherits automatically.
   - **Selected courses** — only courses you explicitly add.
   - **Disabled** — courses must use their own keys.

See the [AI Settings & Usage Guide](/docs/ai-guide) for full details on configuration, inheritance, and usage tracking.

## Quizzes

Quizzes are a **course-level** feature that instructors build and grade themselves — there is no
organization-level quiz management. Two things you control at the org level do affect them, though:

- **AI provider & key** — the AI that drafts quiz questions and generates per-student questions runs
  on the shared AI provider you configure above (or a course's own key). If courses have no AI
  access, instructors simply author quiz questions manually. Quiz AI usage is included in the same
  usage tracking as other AI features.
- **Course access** — quizzes follow the normal course roster and roles; the per-course **Quiz
  Grader** role is managed by each course's admins.

For the full authoring and grading workflow, see the instructor [Quizzes](/docs/instructor-quizzes)
guide.
