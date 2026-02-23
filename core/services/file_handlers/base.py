# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import abc
import stat
from typing import Optional, Set, Any, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from core.models import File

class BaseFileHandler(abc.ABC):
    """
    Abstract base class for all file handlers.
    Handlers encapsulate language-specific logic for files.
    """
    
    def __init__(self, file_obj: 'File'):
        self.file = file_obj

    @property
    def content(self) -> str:
        """Safely retrieves file content."""
        # Handle both File models and potential dict usage if we expand later
        # For now, assuming File model
        return getattr(self.file, 'data', None) or ''

    @abc.abstractmethod
    def get_language(self) -> str:
        """Returns the internal codePost language code (e.g., 'python-3.12')."""
        pass

    @abc.abstractmethod
    def is_executable(self) -> bool:
        """Returns True if this file type is considered executable/runnable."""
        pass

    def get_requirements(self) -> Optional[str]:
        """
        Scans the file for requirements/dependencies.
        Returns a string suitable for installation (e.g., requirements.txt content),
        or None if no requirements found/applicable.
        """
        return None

    @classmethod
    def scan_content(cls, content: str) -> Set[str]:
        """
        Static method to scan raw content for dependencies.
        Used by NotebookHandler to delegate scanning without creating dummy File objects.
        """
        return set()

    @staticmethod
    def infer(data:str)-> bool:
        """
        Infer if the code/data is of the type this handler can process. Used for cases where extension may not be reliable.
        """
        return False