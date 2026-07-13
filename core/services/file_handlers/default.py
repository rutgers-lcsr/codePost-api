# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from .base import BaseFileHandler

class DefaultHandler(BaseFileHandler):
    """
    Fallback handler for unknown file types.
    """

    def get_language(self) -> str:
        return 'unknown'

    def is_executable(self) -> bool:
        return False
