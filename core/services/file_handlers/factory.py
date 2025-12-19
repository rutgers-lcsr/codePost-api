from typing import Dict, Type
import logging
from .base import BaseFileHandler
from .default import DefaultHandler
from .python import PythonHandler
from .notebook import NotebookHandler
from .java import JavaHandler
from .node import NodeHandler
from .other_langs import RubyHandler, RHandler, PHPHandler, CPPHandler

logger = logging.getLogger(__name__)

class FileHandlerFactory:
    """
    Factory to create the appropriate FileHandler for a given file.
    """
    
    _extension_map: Dict[str, Type[BaseFileHandler]] = {
        'py': PythonHandler,
        'ipynb': NotebookHandler,
        'java': JavaHandler,
        'js': NodeHandler,
        'ts': NodeHandler,
        'mjs': NodeHandler,
        'cjs': NodeHandler,
        'rb': RubyHandler,
        'r': RHandler,
        'php': PHPHandler,
        'c': CPPHandler,
        'cpp': CPPHandler,
        'h': CPPHandler,
    }

    @classmethod
    def get_handler(cls, file_obj: 'File') -> BaseFileHandler:
        # Determine extension
        extension = file_obj.extension
        if not extension:
            # Try to infer from name if extension field is empty using models.File logic re-implementation
            # Or rely on models.File having populated it. 
            # Ideally models.File.save ensures extension is set.
            if hasattr(file_obj, 'name') and '.' in file_obj.name:
                extension = file_obj.name.split('.')[-1]
        
        if extension:
            extension = extension.lower().replace('.', '')
            handler_class = cls._extension_map.get(extension)
            if handler_class:
                return handler_class(file_obj)
        
        return DefaultHandler(file_obj)
    
    @classmethod
    def register_handler(cls, extension: str, handler_class: Type[BaseFileHandler]):
        cls._extension_map[extension.lower()] = handler_class
