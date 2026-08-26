---
key: open-source
path: open-source
title: Open Source
category: Getting Started
order: 4
---

# codePost is Open Source

**Rutgers has released codePost as source-available software.**
You can run your own instance for free, on your own infrastructure, and contribute to the project's development.

---

## The story

codePost began as the [codepost.io](https://codepost.io) SaaS platform for code review and autograding. The Rutgers Department of Computer Science adopted the platform, took over its codebase, and has since rebuilt and substantially extended it — a new testing and autograding framework, AI-assisted grading, single sign-on, a refreshed and accessible interface, and a Docker-based deployment model.

That work is now public. Anyone can read the source, self-host codePost, and help improve it.

---

## What this means for you

- **Free to self-host** — stand up a full deployment on your own servers at no cost.
- **Your data stays with you** — because you host it, your roster and student data never leave your infrastructure, which helps with privacy and FERPA considerations.
- **No vendor lock-in** — the platform, API, and SDKs are all open for inspection and extension.
- **Community-driven** — file issues, request features, and contribute code.

---

## License

codePost is released under the **Rutgers Non-Commercial License (RU-NCL)**. It is free to use and adapt for educational and other non-commercial purposes. Commercial use is not permitted. The full terms are in the [`LICENSE`](https://github.com/rutgers-lcsr/codePost/blob/main/LICENSE) file in each repository.

---

## Repositories

All source lives in the [`rutgers-lcsr`](https://github.com/rutgers-lcsr) organization on GitHub.

| Repository                                                        | What it is                                  |
| ----------------------------------------------------------------- | ------------------------------------------- |
| [codePost](https://github.com/rutgers-lcsr/codePost)              | Hub — start here for setup and quickstart   |
| [codePost-api](https://github.com/rutgers-lcsr/codePost-api)      | Django + DRF backend API                    |
| [codePost-ui](https://github.com/rutgers-lcsr/codePost-ui)        | React frontend                              |

---

## Self-host it

The hub repository's README walks you from `git clone` to a running instance.

**What you'll need:** a Linux host with Docker, a domain name, and a TLS certificate. A basic single-server instance can be up in well under an hour.

Get started: [github.com/rutgers-lcsr/codePost](https://github.com/rutgers-lcsr/codePost)

---

## Get involved

We welcome contributions from the community:

- **Report bugs or request features** via GitHub Issues.
- **Contribute code** — see each repository's `CONTRIBUTING.md` for setup and pull-request guidelines.
- **Report security issues** responsibly — see `SECURITY.md` for disclosure instructions.

---

> [!NOTE]
> Need institution-level deployment help? Contact us at [codepost@cs.rutgers.edu](mailto:codepost@cs.rutgers.edu).
