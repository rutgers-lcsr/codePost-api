# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Text derived from an exception that leaves the process (task results, SSE frames,
websocket messages, stored run results, build logs).

Raw ``str(e)`` of an unexpected exception can carry file paths, connection strings or
SQL. A caller names the exception types whose message IS the diagnostic (for example a
Docker build failure shown to the instructor who started the build); everything else is
reduced to a fixed sentence plus the exception class, and the caller logs the detail.
"""
from typing import Tuple, Type


class RunUnavailable(Exception):
  """A run cannot start for a reason the user can act on (no executor, no language)."""


def safe_error_text(exc: BaseException, expected: Tuple[Type[BaseException], ...] = ()) -> str:
  """str(exc) for an expected domain error, else a fixed message naming only the class."""
  if isinstance(exc, expected):
    return str(exc)
  return f"An internal error occurred ({type(exc).__name__}). The details were recorded in the server log."
