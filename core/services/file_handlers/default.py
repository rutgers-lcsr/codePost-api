from .base import BaseFileHandler

class DefaultHandler(BaseFileHandler):
    """
    Fallback handler for unknown file types.
    """

    def get_language(self) -> str:
        return 'unknown'

    def is_executable(self) -> bool:
        return False
