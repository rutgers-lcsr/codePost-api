# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from .base import Executor, NotebookExecutor, ExecutionResult, NotebookCell  # noqa: F401
from .python import PythonExecutor, PythonNotebookExecutor  # noqa: F401
from .java import JavaExecutor, JavaNotebookExecutor  # noqa: F401
from .r import RExecutor, RNotebookExecutor  # noqa: F401

from .cpp import CPPExecutor, CPPNotebookExecutor  # noqa: F401
from .ruby import RubyExecutor, RubyNotebookExecutor  # noqa: F401
from .php import PHPExecutor, PHPNotebookExecutor  # noqa: F401
from .node import NodeExecutor, NodeNotebookExecutor  # noqa: F401

def get_executor_class(language: str):
    """
    Get the executor class for a given language string.
    """
    lang = language.lower()
    
    # Python
    if 'python' in lang or 'data_science' in lang:
        return PythonExecutor
        
    # Node/JS
    if 'node' in lang or 'javascript' in lang or 'js' in lang:
        return NodeExecutor
        
    # Ruby (Check before R to avoid containment issues if logic becomes fuzzy, though explicit checks below handle it)
    if 'ruby' in lang:
        return RubyExecutor
        
    # PHP
    if 'php' in lang:
        return PHPExecutor
        
    # R
    # Avoid matching 'ruby' or 'rust' if we add it, though rust doesn't share start.
    if 'r' in lang and 'ruby' not in lang and 'rust' not in lang:
         if lang == 'r' or lang.startswith('r-'):
             return RExecutor

    # Java
    if 'java' in lang:
        return JavaExecutor
        
    # C/C++
    if 'c' in lang or 'cpp' in lang:
        return CPPExecutor
        
    return Executor

