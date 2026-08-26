---
key: instructor-mcp-agent
path: instructor-mcp-agent
title: AI Agents (MCP)
category: Instructor Workflows
order: 13
---

# Managing your course with an AI agent

codePost has a built-in [MCP](https://modelcontextprotocol.io) server, so you can connect
an AI assistant — Claude Code, Claude Desktop, or any MCP client — to your course and ask
for things in plain language:

- *"Who hasn't submitted HW3, and are they all in the same section?"*
- *"Set up HW4 like HW3 but due two weeks later, and write starter code for it."*
- *"Create a 5-question quiz on recursion attached to HW3, available after students submit."*
- *"Give this student time-and-a-half on quizzes."*
- *"What needs my attention this week?"*

The agent works through the same permission system as everything else in codePost: it can
never see another course, and it can never do more than the credential you hand it allows.

## Connecting

**1. Create an API key.** In *Course Settings → Course API Keys*, create a key and choose
its scope:

| Scope | What the agent can do |
| --- | --- |
| `read` *(default)* | Look things up: roster, grading progress, gradebook, submissions, quizzes, analytics. Nothing else. |
| `write` | Everything in `read`, plus course setup: create and edit assignments and quizzes, author autograder tests, upload starter files, manage the rubric, sections, and grading assignments, publish work and release feedback (each with a preview step). |
| `admin` | Everything in `write`, plus the destructive operations — deleting things, resetting quiz attempts, removing roster members, emailing students. **Every one of these also requires a confirmation code from you** (see below). |

The key is shown once — copy it immediately.

**2. Connect your client.** For Claude Code:

```bash
claude mcp add --transport http codepost https://codepost-api.cs.rutgers.edu/mcp \
  --header "Authorization: CourseKey cpk_..."
```

For Claude Desktop, use the standard `mcp-remote` bridge in your MCP settings:

```json
{
  "mcpServers": {
    "codepost": {
      "command": "npx",
      "args": ["mcp-remote", "https://codepost-api.cs.rutgers.edu/mcp",
               "--transport", "http-only",
               "--header", "Authorization:CourseKey cpk_..."]
    }
  }
}
```

You can also connect with your **personal API token** (*Account → Request API Token*)
instead of a course key. The agent then asks which of your courses to work on and can
switch between them mid-conversation.

## How destructive actions are protected

Anything the agent cannot undo — deleting an assignment, resetting quiz attempts,
emailing every student — is refused on the first try, no matter the key scope. Instead, a
**confirmation code** appears under *Course Settings → Pending agent actions*, along with
exactly what the agent wants to do and how much it affects.

Read the code there and paste it into the chat to approve, or press **Deny** to kill it.
Codes work once, expire after 10 minutes, and die automatically if the situation changes
between the preview and your approval (for example, a TA finalizes more submissions in
the meantime). The agent cannot read the code itself — the panel refuses the agent's own
credential — so nothing irreversible happens without a human in the loop.

Less dangerous changes (publishing an assignment, releasing feedback) use a lighter
protection: the agent's first call is always a preview of exactly what students would
gain or lose, and it must call again explicitly to apply.

## Good to know

- Every change an agent makes is recorded in the course **Activity Log**, marked as
  agent-initiated, alongside the normal audit events.
- Revoking the API key (or deactivating it) cuts the agent off immediately.
- The agent sees student emails and grades if you give it a `read`-or-above key — treat
  the key like you would treat your own login.
- Agent traffic is rate-limited per course, so a runaway agent cannot affect the rest of
  codePost.
