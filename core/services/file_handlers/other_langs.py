# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import re
import logging
from typing import Set, Optional
from .base import BaseFileHandler

logger = logging.getLogger(__name__)

class RubyHandler(BaseFileHandler):
    def get_language(self) -> str:
        return 'ruby'

    def is_executable(self) -> bool:
        return True

    def get_requirements(self) -> Optional[str]:
        if self.file.name == 'Gemfile':
            return self.content
            
        _imports = self.scan_content(self.content)
        # We don't auto-generate Gemfiles from requires currently in the plan,
        # but the interface allows it. For now returning None effectively.
        return None

    @classmethod
    def scan_content(cls, code: str) -> Set[str]:
        matches = re.findall(r"gem\s+['\"](.+?)['\"]", code)
        return set(matches)

class RHandler(BaseFileHandler):
    def get_language(self) -> str:
        return 'r-4'

    def is_executable(self) -> bool:
        return True

    def get_requirements(self) -> Optional[str]:
        imports = self.scan_content(self.content)
        filtered = {p for p in imports if p not in ['base', 'stats', 'utils', 'graphics', 'grDevices', 'methods', 'datasets']}
        if filtered:
             return "\n".join(sorted(filtered))
        return None

    @classmethod
    def scan_content(cls, code: str) -> Set[str]:
        # Capture library() and require()
        matches = set(re.findall(r"(?:library|require)\s*\((?:package\s*=\s*)?['\"]?([a-zA-Z0-9\.]+)['\"]?\)", code))
        # Capture install.packages('pkg')
        # Matches install.packages("pkg", ...)
        matches.update(re.findall(r"install\.packages\s*\(\s*['\"]([a-zA-Z0-9\.]+)['\"]", code))
        return matches


class PHPHandler(BaseFileHandler):
    def get_language(self) -> str:
        return 'php'

    def is_executable(self) -> bool:
        return True
        
    def get_requirements(self) -> Optional[str]:
         if self.file.name == 'composer.json':
              return self.content
         return None


class CPPHandler(BaseFileHandler):
    def get_language(self) -> str:
        return 'c/c++'

    def is_executable(self) -> bool:
        return True
        
    def get_requirements(self) -> Optional[str]:
        if self.file.name == 'Makefile':
             return self.content
        return None
