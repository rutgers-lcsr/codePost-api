# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import ast
import re
from typing import Set, Optional
from .base import BaseFileHandler

class PythonHandler(BaseFileHandler):
    
    PIP_MODULE_TO_PACKAGE = {
        "sklearn": "scikit-learn",
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "bs4": "beautifulsoup4",
        "yaml": "pyyaml",
        "dateutil": "python-dateutil",
    }

    def get_language(self) -> str:
        return 'python-3.12'

    def is_executable(self) -> bool:
        return True

    def get_requirements(self) -> Optional[str]:
        imports = self.scan_content(self.content)
        if not imports:
            return None
            
        # Filter standard library (simplified list)
        std_lib = {
            'os', 'sys', 're', 'math', 'json', 'time', 'datetime', 'random', 'typing', 'collections',
            'abc', 'argparse', 'ast', 'asyncio', 'base64', 'binascii', 'calendar', 'cmath', 'copy',
            'csv', 'ctypes', 'dataclasses', 'decimal', 'difflib', 'enum', 'functools', 'gc', 'glob',
            'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'importlib', 'inspect', 'io', 'ipaddress',
            'itertools', 'logging', 'marshal', 'mmap', 'multiprocessing', 'netrc', 'numbers', 'operator',
            'pathlib', 'pickle', 'platform', 'pprint', 'profile', 'pstats', 'queue', 'quopri', 'sched',
            'secrets', 'select', 'shlex', 'shutil', 'signal', 'socket', 'socketserver', 'sqlite3', 'ssl',
            'stat', 'statistics', 'string', 'struct', 'subprocess', 'tempfile', 'textwrap', 'threading',
            'traceback', 'types', 'unittest', 'urllib', 'uuid', 'warnings', 'weakref', 'xml', 'zipfile',
            'zlib'
        }
        filtered = sorted(list(imports - std_lib))
        if not filtered:
            return None
            
        return '\n'.join(filtered)

    @classmethod
    def scan_content(cls, code: str) -> Set[str]:
        packages_to_install = set()
        try:
            # Try to parse as Python AST (most reliable)
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]
                        packages_to_install.add(module_name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split('.')[0]
                        packages_to_install.add(module_name)
        except SyntaxError:
            # If AST parsing fails, try regex as fallback
            import_matches = re.findall(
                r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', 
                code, 
                re.MULTILINE
            )
            packages_to_install.update(import_matches)
        
        # Map module names to package names
        mapped_packages = set()
        for module_name in packages_to_install:
            package_name = cls.PIP_MODULE_TO_PACKAGE.get(module_name, module_name)
            mapped_packages.add(package_name)
            
        return mapped_packages

    @staticmethod
    def infer(data: str) -> bool:
        """
        Infer if the code/data is of the type this handler can process. Used for cases where extension may not be reliable.
        """
        try:
            ast.parse(data)
            return True
        except SyntaxError:
            return False
        except Exception:
            return False