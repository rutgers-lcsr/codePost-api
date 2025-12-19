import json
import logging
from typing import Set, Optional, Dict, List
from .base import BaseFileHandler
from .python import PythonHandler
from .node import NodeHandler
from .other_langs import RHandler, RubyHandler

logger = logging.getLogger(__name__)

class NotebookHandler(BaseFileHandler):
    """
    Handles Jupyter Notebooks (.ipynb).
    Acts as a dispatcher to specific language handlers based on kernel metadata.
    """
    
    # Map notebook kernel languages to our Handler classes
    KERNEL_HANDLER_MAP = {
        'python': PythonHandler,
        'python3': PythonHandler,
        'javascript': NodeHandler,
        'node': NodeHandler,
        'typescript': NodeHandler,
        'r': RHandler,
        'ruby': RubyHandler,
    }

    def _parse_notebook(self) -> Dict:
        try:
            return json.loads(self.content)
        except json.JSONDecodeError:
            return {}

    def _get_kernel_language(self, nb_data: Dict) -> Optional[str]:
        language = None
        if 'metadata' in nb_data:
            if 'kernelspec' in nb_data['metadata'] and 'language' in nb_data['metadata']['kernelspec']:
                language = nb_data['metadata']['kernelspec']['language'].lower()
            elif 'language_info' in nb_data['metadata'] and 'name' in nb_data['metadata']['language_info']:
                language = nb_data['metadata']['language_info']['name'].lower()
        return language

    def _get_delegate_handler_class(self, nb_data: Dict):
        lang = self._get_kernel_language(nb_data)
        if lang:
            # Normalize
            if 'python' in lang: lang = 'python'
            return self.KERNEL_HANDLER_MAP.get(lang)
        return None

    def get_language(self) -> str:
        nb_data = self._parse_notebook()
        handler_class = self._get_delegate_handler_class(nb_data)
        
        if handler_class:
            return handler_class(self.file).get_language()
            
        # Fallback if unknown kernel
        return 'unknown'

    def is_executable(self) -> bool:
        return True

    def get_requirements(self) -> Optional[str]:
        nb_data = self._parse_notebook()
        handler_class = self._get_delegate_handler_class(nb_data)
        
        if not handler_class:
            return None
            
        # Extract code cells
        code_content = self._extract_code(nb_data)
        
        # Delegate scanning to the specific language handler
        # We use the static method scan_content to avoid creating a fake File object
        imports = handler_class.scan_content(code_content)
        
        if not imports:
            return None

        # Re-use the specific handler logic to format requirements
        # Here we do need an instance or a static format method. 
        # For simplicity, we instantiate a dummy handler wrapper or duplicate the formatting logic?
        # Better: create a temporary instance with the code content to use its get_requirements
        
        # Create a mock/proxy File object with the code content
        class MockFile:
            def __init__(self, data, name):
                self.data = data
                self.name = f"notebook_extracted.{handler_class.__name__}" # dummy name
        
        mock_file = MockFile(code_content, "notebook_code")
        delegate_instance = handler_class(mock_file)
        return delegate_instance.get_requirements()

    def _extract_code(self, data: Dict) -> str:
        code_cells = []
        if 'cells' in data:
            for cell in data['cells']:
                if cell.get('cell_type') == 'code':
                    source = cell.get('source', [])
                    if isinstance(source, list):
                        code_cells.append("".join(source))
                    elif isinstance(source, str):
                        code_cells.append(source)
        return "\n".join(code_cells)
