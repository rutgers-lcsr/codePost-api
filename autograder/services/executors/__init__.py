# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from .base import Executor, NotebookExecutor, ExecutionResult, NotebookCell  # noqa: F401
from .python import PythonExecutor, PythonNotebookExecutor  # noqa: F401
from .java import JavaExecutor, JavaNotebookExecutor  # noqa: F401
from .r import RExecutor, RNotebookExecutor  # noqa: F401

from .cpp import CPPExecutor, CPPNotebookExecutor  # noqa: F401
from .ruby import RubyExecutor, RubyNotebookExecutor  # noqa: F401
from .php import PHPExecutor, PHPNotebookExecutor  # noqa: F401
from .node import NodeExecutor, NodeNotebookExecutor  # noqa: F401
import re

# Language family (leading name, before any space, '-' or digit) -> executor. Matching is exact on the
# family so unsupported languages (typescript, scala, csharp, ...) are not routed to a
# supported executor by accident; they get the base Executor, which callers treat as
# "no sandbox available".
_EXECUTOR_FAMILIES = {
    'python': PythonExecutor, 'python3': PythonExecutor, 'data_science': PythonExecutor,
    'node': NodeExecutor, 'node.js': NodeExecutor, 'nodejs': NodeExecutor, 'javascript': NodeExecutor, 'js': NodeExecutor,
    'ruby': RubyExecutor,
    'php': PHPExecutor,
    'r': RExecutor,
    'java': JavaExecutor,
    'c/c++': CPPExecutor, 'c': CPPExecutor, 'cpp': CPPExecutor, 'c++': CPPExecutor,
    'g++': CPPExecutor, 'gcc': CPPExecutor, 'cplusplus': CPPExecutor,
}
_FAMILY_RE = re.compile(r'[a-z_/+#.]+')


def get_executor_class(language: str):
    """
    Get the executor class for a given language string (e.g. 'python-3.12', 'c/c++', 'R').
    """
    match = _FAMILY_RE.match((language or '').strip().lower())
    family = match.group(0).rstrip('.') if match else ''
    return _EXECUTOR_FAMILIES.get(family, Executor)
