import json
from typing import Dict, Type
import logging

from core.models import File
from log.models import Event
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
        """
        Factory method to return the appropriate FileHandler based on file extension or content inference. Will use the extension field if available, but will also attempt to infer from the file name if extension is missing. If no specific handler is found, returns a DefaultHandler.
        """
        extension = file_obj.extension 
        if not extension and hasattr(file_obj, 'name') and '.' in file_obj.name:
            # if extension field is not populated, try to infer from name
            extension = file_obj.name.split('.')[-1]
        
        if extension:
            extension = extension.lower().replace('.', '')
            handler_class = cls._extension_map.get(extension)
            if handler_class:
                return handler_class(file_obj)
            return DefaultHandler(file_obj)
        
        # No extension available, and the name doesn't have an extension either. Try to infer from content if possible.
        content = getattr(file_obj, 'data', None) or ''
        for handler_cls in cls._extension_map.values():
            try:
                if handler_cls.infer(content):
                    return handler_cls(file_obj)
            except Exception as e:
                logger.error(f"Error during inference for handler {handler_cls.__name__}: {e}", exc_info=True)
                continue
        
        return DefaultHandler(file_obj)
    
    @classmethod
    def register_handler(cls, extension: str, handler_class: Type[BaseFileHandler]):
        cls._extension_map[extension.lower()] = handler_class
