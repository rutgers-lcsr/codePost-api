# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
"""
Chat Tool Definitions for the Agentic Grading Assistant.

Each tool is defined as a JSON Schema compatible with OpenAI / Gemini function-calling.
Tools are categorized as:
  - **server-side**: Executed on the backend (read-only, no user approval needed).
  - **client-side**: Returned to the frontend for user approval + execution.

To add a new tool:
  1. Add a TOOL_* dict below with the schema.
  2. Add an executor function if it's server-side.
  3. Add it to ALL_TOOLS and (optionally) SERVER_SIDE_TOOLS.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.db.models import Prefetch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schema definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_APPLY_RUBRIC_COMMENT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "apply_rubric_comment",
        "description": (
            "Apply a rubric comment to the submission. This will add a grading "
            "comment linked to the specified rubric item at the given location."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rubric_comment_id": {
                    "type": "integer",
                    "description": "The ID of the rubric comment to apply.",
                },
                "file_id": {
                    "type": "integer",
                    "description": "The ID of the submission file to apply the comment to.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "The starting line number (1-indexed). For notebook (.ipynb) files, this is the 0-indexed cell index instead (Cell 1 = index 0).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "The ending line number (1-indexed). Defaults to start_line. For notebook (.ipynb) files, this is the 0-indexed cell index. Only set this higher than start_line if the issue genuinely spans multiple lines/cells.",
                },
                "start_char": {
                    "type": "integer",
                    "description": "The starting character offset within the start line (0-indexed). Use this for highlighting a specific portion of a line rather than the whole line.",
                },
                "end_char": {
                    "type": "integer",
                    "description": "The ending character offset within the end line (0-indexed). Use together with start_char to highlight a specific range.",
                },
            },
            "required": ["rubric_comment_id", "file_id", "start_line"],
        },
    },
}

TOOL_CREATE_INLINE_COMMENT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_inline_comment",
        "description": (
            "Create a new inline comment on a specific line range of a file. "
            "Use this to provide feedback to the student."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "The ID of the submission file.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "The starting line number (1-indexed). For notebook (.ipynb) files, this is the 0-indexed cell index instead (Cell 1 = index 0).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "The ending line number (1-indexed). Defaults to start_line. For notebook (.ipynb) files, this is the 0-indexed cell index. Only set this higher than start_line if the feedback genuinely applies to a whole block of lines/cells.",
                },
                "text": {
                    "type": "string",
                    "description": "The comment text to display to the student.",
                },
                "point_delta": {
                    "type": "number",
                    "description": "Points to add (positive) or deduct (negative).",
                },
                "start_char": {
                    "type": "integer",
                    "description": "The starting character offset within the start line (0-indexed). Use this for highlighting a specific portion of a line rather than the whole line.",
                },
                "end_char": {
                    "type": "integer",
                    "description": "The ending character offset within the end line (0-indexed). Use together with start_char to highlight a specific range.",
                },
            },
            "required": ["file_id", "start_line", "text"],
        },
    },
}

TOOL_READ_FILE_CONTENTS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_file_contents",
        "description": (
            "Read the full contents of a submission file. Use this to examine "
            "the student's code in detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "The ID of the submission file to read.",
                },
            },
            "required": ["file_id"],
        },
    },
}

TOOL_VIEW_TEST_RESULTS: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "view_test_results",
        "description": (
            "View the autograder test results for this submission. Shows which "
            "tests passed, failed, and their output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "submission_id": {
                    "type": "integer",
                    "description": "The ID of the submission.",
                },
            },
            "required": ["submission_id"],
        },
    },
}

TOOL_NAVIGATE_TO_LOCATION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "navigate_to_location",
        "description": (
            "Navigate the code viewer to a specific file and line. Use this to "
            "direct the grader's attention to a relevant section of code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "The ID of the submission file to navigate to.",
                },
                "line": {
                    "type": "integer",
                    "description": "The line number to scroll to (1-indexed). For notebook (.ipynb) files, this is the 0-indexed cell index instead (Cell 1 = index 0).",
                },
            },
            "required": ["file_id", "line"],
        },
    },
}

TOOL_GREP_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "grep_file",
        "description": (
            "Search for lines matching a pattern in a submission file. Returns "
            "matching lines with their line numbers. Useful for quickly finding "
            "relevant code without reading the entire file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "The ID of the submission file to search.",
                },
                "pattern": {
                    "type": "string",
                    "description": "The search pattern (case-insensitive substring match).",
                },
            },
            "required": ["file_id", "pattern"],
        },
    },
}

TOOL_READ_FILE_LINES: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_file_lines",
        "description": (
            "Read a specific range of lines from a submission file. Use this "
            "instead of read_file_contents when you only need a portion of the "
            "file, such as a specific function or section."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "description": "The ID of the submission file to read.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "The first line to read (1-indexed, inclusive).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "The last line to read (1-indexed, inclusive).",
                },
            },
            "required": ["file_id", "start_line", "end_line"],
        },
    },
}

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_TOOLS: list[dict[str, Any]] = [
    TOOL_APPLY_RUBRIC_COMMENT,
    TOOL_CREATE_INLINE_COMMENT,
    TOOL_READ_FILE_CONTENTS,
    TOOL_READ_FILE_LINES,
    TOOL_GREP_FILE,
    TOOL_VIEW_TEST_RESULTS,
    TOOL_NAVIGATE_TO_LOCATION,
]

# Tools whose results are computed server-side (no user approval needed)
SERVER_SIDE_TOOLS: set[str] = {"read_file_contents", "read_file_lines", "grep_file", "view_test_results"}

# Tools that modify state and require user approval on the frontend
CLIENT_SIDE_TOOLS: set[str] = {"apply_rubric_comment", "create_inline_comment", "navigate_to_location"}


# ---------------------------------------------------------------------------
# Server-side tool executors
# ---------------------------------------------------------------------------

async def execute_server_tool(tool_name: str, tool_args: dict[str, Any], submission_id: int) -> str:
    """Execute a server-side tool and return the result as a string."""
    if tool_name == "read_file_contents":
        return await _execute_read_file(tool_args, submission_id)
    elif tool_name == "read_file_lines":
        return await _execute_read_file_lines(tool_args, submission_id)
    elif tool_name == "grep_file":
        return await _execute_grep_file(tool_args, submission_id)
    elif tool_name == "view_test_results":
        return await _execute_view_tests(tool_args, submission_id)
    else:
        return f"Unknown server-side tool: {tool_name}"


async def _execute_read_file(args: dict[str, Any], submission_id: int) -> str:
    """Read the contents of a submission file."""
    from core.models import SubmissionFile, Submission
    from asgiref.sync import sync_to_async

    file_id = args.get("file_id")
    if not file_id:
        return "Error: file_id is required."

    try:
        sub_file = await sync_to_async(
            lambda: SubmissionFile.objects.select_related('submission').get(
                pk=file_id, submission_id=submission_id
            )
        )()
        content = sub_file.data or ""
        name = sub_file.name or f"file_{file_id}"

        # Parse notebooks into a structured cell-by-cell format
        if name.endswith('.ipynb'):
            return _format_notebook(content, name)

        return f"**{name}**\n```\n{content}\n```"
    except Exception as e:
        logger.warning(f"read_file_contents failed: {e}")
        return f"Error: Could not read file {file_id}."


async def _execute_read_file_lines(args: dict[str, Any], submission_id: int) -> str:
    """Read a specific range of lines from a submission file."""
    from core.models import SubmissionFile
    from asgiref.sync import sync_to_async

    file_id = args.get("file_id")
    start_line = args.get("start_line")
    end_line = args.get("end_line")
    if not file_id or not start_line or not end_line:
        return "Error: file_id, start_line, and end_line are required."

    try:
        sub_file = await sync_to_async(
            lambda: SubmissionFile.objects.select_related('submission').get(
                pk=file_id, submission_id=submission_id
            )
        )()
        content = sub_file.data or ""
        name = sub_file.name or f"file_{file_id}"
        lines = content.splitlines()

        # Clamp to valid range
        start = max(1, int(start_line))
        end = min(len(lines), int(end_line))
        if start > len(lines):
            return f"Error: file only has {len(lines)} lines."

        selected = lines[start - 1:end]
        numbered = "\n".join(
            f"{i}: {line}" for i, line in enumerate(selected, start=start)
        )
        return f"**{name}** (lines {start}-{end} of {len(lines)})\n```\n{numbered}\n```"
    except Exception as e:
        logger.warning(f"read_file_lines failed: {e}")
        return f"Error: Could not read file {file_id}."


async def _execute_grep_file(args: dict[str, Any], submission_id: int) -> str:
    """Search for lines matching a pattern in a submission file."""
    from core.models import SubmissionFile
    from asgiref.sync import sync_to_async

    file_id = args.get("file_id")
    pattern = args.get("pattern")
    if not file_id or not pattern:
        return "Error: file_id and pattern are required."

    try:
        sub_file = await sync_to_async(
            lambda: SubmissionFile.objects.select_related('submission').get(
                pk=file_id, submission_id=submission_id
            )
        )()
        content = sub_file.data or ""
        name = sub_file.name or f"file_{file_id}"
        lines = content.splitlines()

        pattern_lower = str(pattern).lower()
        matches = [
            f"{i}: {line}"
            for i, line in enumerate(lines, start=1)
            if pattern_lower in line.lower()
        ]

        if not matches:
            return f"No matches for '{pattern}' in **{name}**."

        result = "\n".join(matches[:200])  # Cap at 200 matches
        header = f"**{name}** — {len(matches)} match{'es' if len(matches) != 1 else ''} for '{pattern}'"
        if len(matches) > 200:
            header += " (showing first 200)"
        return f"{header}\n```\n{result}\n```"
    except Exception as e:
        logger.warning(f"grep_file failed: {e}")
        return f"Error: Could not search file {file_id}."


def _format_notebook(raw_content: str, name: str) -> str:
    """Format a .ipynb notebook into a structured cell-by-cell representation."""
    try:
        notebook = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        return f"**{name}** (notebook — could not parse)\n```\n{raw_content[:2000]}\n```"

    cells = notebook.get('cells', [])
    if not cells:
        return f"**{name}** (empty notebook)"

    parts = [f"**{name}** (Jupyter notebook — {len(cells)} cells)"]
    parts.append("*When commenting on this file, use the cell index (0-indexed) as start_line.*\n")

    for i, cell in enumerate(cells):
        cell_type = cell.get('cell_type', 'code')
        source = cell.get('source', [])
        content = "".join(source) if isinstance(source, list) else str(source)

        parts.append(f"### Cell {i} ({cell_type})")
        if cell_type == 'markdown':
            parts.append(content.strip())
        else:
            parts.append(f"```\n{content.strip()}\n```")

        # Include outputs for code cells
        if cell_type == 'code':
            outputs = cell.get('outputs', [])
            output_texts = []
            for output in outputs:
                otype = output.get('output_type', '')
                if otype == 'stream':
                    text = output.get('text', [])
                    output_texts.append("".join(text) if isinstance(text, list) else str(text))
                elif otype in ('execute_result', 'display_data'):
                    data = output.get('data', {})
                    if 'text/plain' in data:
                        text = data['text/plain']
                        output_texts.append("".join(text) if isinstance(text, list) else str(text))
                    elif 'image/png' in data:
                        output_texts.append("[Image output]")
                elif otype == 'error':
                    output_texts.append(f"Error: {output.get('ename', '')}: {output.get('evalue', '')}")
            if output_texts:
                parts.append(f"**Output:**\n```\n{''.join(output_texts).strip()}\n```")

        parts.append("")  # blank line between cells

    return "\n".join(parts)


async def _execute_view_tests(args: dict[str, Any], submission_id: int) -> str:
    """View test results for a submission."""
    from core.models import SubmissionTest, TestCase, TestCategory
    from asgiref.sync import sync_to_async

    sid = args.get("submission_id", submission_id)
    try:
        tests = await sync_to_async(
            lambda: list(
                SubmissionTest.objects.filter(submission_id=sid)
                .select_related('testCase', 'testCase__testCategory')
                .order_by('testCase__testCategory__name', 'testCase__name')
            )
        )()

        if not tests:
            return "No test results available for this submission."

        lines = ["**Test Results:**\n"]
        current_category = None
        for t in tests:
            tc = t.testCase
            cat_name = tc.testCategory.name if tc.testCategory else "Uncategorized"
            if cat_name != current_category:
                current_category = cat_name
                lines.append(f"\n**{cat_name}:**")

            status = "✅ PASS" if t.passed else "❌ FAIL"
            max_score = tc.pointsPass if t.passed else tc.pointsFail
            score_str = f" ({t.score}/{max_score})" if max_score else ""
            lines.append(f"- {status} {tc.description}{score_str}")
            if t.logs and not t.passed:
                # Truncate long logs
                log_preview = t.logs[:300]
                if len(t.logs) > 300:
                    log_preview += "..."
                lines.append(f"  ```\n  {log_preview}\n  ```")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"view_test_results failed: {e}", exc_info=True)
        return f"Error: Could not retrieve test results."
