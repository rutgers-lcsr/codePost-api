# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Mock file helper for executor services."""

from typing import Optional, Tuple


class MockFile:
    """A minimal file-like object for executing code snippets without an actual file."""

    data: str
    name: str
    extension: str
    id: int
    path: Optional[str]

    def __init__(self, data: str, name: str, extension: Optional[str] = None):
        self.data = data
        self.name = name
        self.extension = extension or ""
        self.id = -1
        self.path = None

    def get_course(self):
        return None

    def get_file_info(self) -> Tuple[None, None, None]:
        return None, None, None
