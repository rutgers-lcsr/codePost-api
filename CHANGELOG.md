# Changelog

All notable changes to codePost are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> **License** — All source code and commits in this repository are made available under the
> [Rutgers Non-commercial License (RU-NCL)](./LICENSE). By using, downloading, or contributing
> to this repository you agree to be bound by its terms.

> **Branch note** — `master` is the current production branch; `render` is the active development branch.

---

## [3.1.1]

### Added

- User-facing changelog page integrated into the docs system (`/docs/changelog`).
- `LICENSE` file added to the repository — all code and commits are under the Rutgers Non-commercial License (RU-NCL).

### Changed

- Increased Nginx upload/body size limit to 6 MB for larger submissions.
- Switched API runtime from WSGI to ASGI for WebSocket support.
- Updated codePost admin panel configuration.

### Fixed

- Fixed an issue where users could not generate API tokens.
- Reduced intermittent 502 errors by forcing Nginx restart in deployment flow.
- Fixed assignment settings not loading notebook editor for notebook-based assignments.

---

## [3.1.0] — Testing Framework & Developer Tooling

This release introduces the **new testing framework**, the single largest feature addition since the initial 0.1.0 release. Instructors can now author, preview, and execute test cases directly inside codePost.

### Added — Testing Framework (new)

- **Test case authoring** — create, edit, and organize test cases per assignment.
- **Test script preview** — run and preview test scripts before publishing.
- **Language-specific testing** — added multi-language test runner support.
- **Test resources** — mount files and datasets as test resources; hidden from students by default.
- Cross-environment course copy script (`npm run populate:cross-env-course`) for migrating courses between servers.
- Tree-sitter integration for improved code parsing and syntax highlighting.

### Changed

- Migrated to generated API client instead of hand-written API calls.
- Updated SDK and documentation links across the platform.
- Added `.mjs` file format support.
- Updated brand color palette.

### Fixed

- Fixed test-save workflow requiring Ctrl+S before changes persisted.
- Fixed `hidden` state being checked instead of `isTestResource` for resource visibility.
- Resolved syntax errors in test-related UI flow.
- Fixed page sizing issues on list and table views.

---

## [3.0.0] — Platform Modernization

A major release that modernized the entire codebase, rebuilt the UI with Vite, and added AI-assisted grading, a new documentation system, and full accessibility improvements.

### Added — AI & Grading

- AI-assisted comment generation for graders with configurable system prompts per assignment.
- Pinned comments for graders.
- Grader rubric editor — instructors can grant graders permission to manage rubrics.
- Redux state management for the code-console rubric.
- Release feedback button (renamed from "Release Submission" for clarity).

### Added — Docs, Organization & Admin

- Built-in documentation system (`/docs`) with searchable sidebar, markdown rendering, and table of contents.
- Organization dashboard with SSO integration.
- SuperAdmin dashboard with `isOrgStaff` user setting.
- Course cloning now copies AI settings automatically.

### Added — Student Experience

- Students receive full assignment file data instead of only IDs.
- Improved student console layout and navigation.

### Changed — UI Modernization

- Migrated build system from Create React App to **Vite**.
- Converted most class components to functional components with hooks.
- Upgraded to React Router v7 (removed legacy prop-based routing).
- Removed the command bar in favor of streamlined navigation.
- Updated role selection page.
- Updated rubric UI and assignment management views.
- Comprehensive accessibility improvements (WCAG/Axe compliance, ARIA labels, color contrast fixes, heading hierarchy).
- Added sidebar tooltips in admin navigation.
- Updated dependencies across the stack.

### Changed — Backend & Infrastructure

- Multi-VM production deployment with `docker-compose` (Data / Backend / Worker / Frontend VMs).
- Environment setup script (`scripts/create_env.py`) with interactive and non-interactive modes.
- Bearer token authentication (replaced legacy JWT header format).
- Deployment README with full end-to-end setup guide.

### Fixed

- Fixed superadmin panel being cut off and content overlapping sidebar.
- Fixed admin count display errors on the dashboard.
- Fixed comments not deleting properly.
- Fixed download-grades returning empty CSV.
- Fixed sidebar overflow issues in student console.
- Fixed markdown backtick handling causing unexpected newlines in comments.
- Fixed binary file upload error messages for assignment files.

---

## [0.1.0] — Initial Self-Hosted Release

The baseline open-source release forked from the original codePost.io SaaS platform for self-hosted deployment at Rutgers.

### Included

- Django REST API with JWT authentication.
- React frontend (Create React App).
- Course, assignment, submission, and rubric management.
- Code review console with inline commenting.
- Autograder integration (Celery workers).
- Student, grader, and course-admin role system.
- Docker Compose deployment.
- Nginx reverse proxy with TLS.
- Health-check endpoint.
- Basic admin panel.
