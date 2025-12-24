import os
import logging
import base64
import json
import tempfile
import shutil
from datetime import datetime
from typing import Optional, List

from .base import Executor, NotebookExecutor, ExecutionResult

logger = logging.getLogger(__name__)

class CPPExecutor(Executor):
    LANGUAGE = "c_cpp"
    EXECUTABLE_EXTENSIONS = [".c", ".cpp", ".cc"]
    TEMPLATE = "template.cpp"
    DOCKER_IMAGE = "gcc:13"
    
    @classmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None, code: Optional[str] = None) -> bool:
        if file_name is not None:
            extension = os.path.splitext(file_name)[1]
        if extension and extension.lower() in cls.EXECUTABLE_EXTENSIONS:
            return True
        return False
        
    def _detect_imports(self, code: str) -> List[str]:
        return []

    def _get_code_template(self, code: str, packages_to_install: List[str] = None) -> Optional[str]:
        # For C++, we might not want to always wrap if the user provided safe code.
        # But for consistency, let's use the template if it's a snippet.
        # Simple heuristic: check for "int main"
        if "int main" in code:
            return code # Don't wrap if main exists
            
        template = super()._get_code_template()
        if not template:
            return code # Fallback
            
        # Replace filler
        template = template.replace("// FILLER_CODE", code)
        return template

    def execute(self) -> ExecutionResult:
        timeout = self.DEFAULT_TIMEOUT
        start_time = datetime.now()
        
        if not self.file.data:
            return ExecutionResult.error("No code to execute")
        
        code = self.file.data
        
        # Use template if needed
        final_code = self._get_code_template(code)
        
        # Prepare command
        code_b64 = base64.b64encode(final_code.encode('utf-8')).decode('utf-8')
        
        # Compile and run
        # We save as .cpp to force C++ compilation (even for .c for now, or respect extension)
        ext = self.file.extension or ".cpp"
        if ext and not ext.startswith("."):
            ext = f".{ext}"
        filename = f"source{ext}"
        output_bin = "program"
        
        # Compiler selection
        compiler = "gcc" if ext == ".c" else "g++"
        
        cmd_str = f"echo '{code_b64}' | base64 -d > {filename} && {compiler} {filename} -o {output_bin} && ./{output_bin}"
        command = ["sh", "-c", cmd_str]
        
        container = self.get_container(
            image_name=self.image,
            command=command,
            env=self._get_docker_environment(),
            volumes=self._get_volume_mounts("" if not self.datasets else self._create_staging_directory()),
            needs_network=False
        )
        # Note: Datasets temp dir handling logic is duplicated from base/python.
        # Ideally refactor `_prepare_execution` in base.
        
        if not container:
             return ExecutionResult.error("Failed to create container")
             
        self.add_additional_files(container)
        
        try:
            container.start()
            result = container.wait(timeout=self.DEFAULT_TIMEOUT)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')
            
            execution_time = (datetime.now() - start_time).total_seconds()
            success = result.get('StatusCode', 1) == 0
            
            return ExecutionResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                err=None if success else f"Exit Code: {result.get('StatusCode')}",
                execution_time=execution_time
            )
        except Exception as e:
            container.kill()
            return ExecutionResult.error(f"Execution failed: {e}")
        finally:
            container.remove()

class CPPNotebookExecutor(NotebookExecutor):
    LANGUAGE = "c/c++"
    TEMPLATE = "notebook_template.cpp"
    DOCKER_IMAGE = "gcc:latest"
    EXECUTABLE_EXTENSIONS = ['.ipynb']
    # Execution command generated dynamically via _get_execution_command
    
    @classmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None, code: Optional[str] = None) -> bool:
        if file_name is not None:
            extension = os.path.splitext(file_name)[1]

        try:
            kernel_name = cls.get_kernel_name(code)
            if kernel_name and ('c++' in kernel_name.lower() or 'cpp' in kernel_name.lower() or 'cling' in kernel_name.lower()):
                 return True
        except:
             pass
        return False
        
    def _get_code_template(self, code: str, packages_to_install: List[str]) -> Optional[str]:
        template = super()._get_code_template()
        if not template:
            return None
        
        # Parse notebook from base64 code
        try:
             json_str = base64.b64decode(code).decode('utf-8')
             nb = json.loads(json_str)
             
             source_code = ""
             for cell in nb.get('cells', []):
                 if cell['cell_type'] == 'code':
                     cell_source = "".join(cell.get('source', [])) if isinstance(cell.get('source'), list) else cell.get('source', "")
                     source_code += f"\n// Cell\n{cell_source}\n"
             
             template = template.replace("// FILLER_CODE", source_code)
             return template
        except Exception as e:
             logger.error(f"Failed to parse notebook: {e}")
             return None

    def _get_execution_command(self, template: str) -> List[str]:
        template_b64 = base64.b64encode(template.encode('utf-8')).decode('utf-8')
        return ["sh", "-c", f"echo '{template_b64}' | base64 -d > notebook.cpp && g++ -o notebook notebook.cpp && ./notebook"]
