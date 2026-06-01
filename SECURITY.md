# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in codePost, please report it privately to **codepost@cs.rutgers.edu**.

Please do **not** open a public GitHub issue for security problems.

Include in your report:
- A description of the issue and its impact.
- Steps to reproduce, or proof-of-concept code.
- Any affected versions or deployments you are aware of.

We will acknowledge your report within 3 business days and work with you on a coordinated disclosure timeline.

## Supported Versions

Only the `main` branch of this repository receives security updates. If you are running a self-hosted instance, please track the latest tagged release.

## Scope

In-scope:
- This repository's source code.
- Default configurations shipped here.

Out of scope:
- Vulnerabilities in third-party dependencies (please report upstream).
- Issues that require physical access or a compromised host.
- Issues affecting the live `codepost.cs.rutgers.edu` instance — those should also be sent to the address above, but note that this is a Rutgers-operated deployment and not a public service.
