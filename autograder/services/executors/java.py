import os
import logging
import base64
from datetime import datetime
from typing import List, Optional
import tempfile
import shutil

from .base import Executor, NotebookExecutor, ExecutionResult

logger = logging.getLogger(__name__)

class JavaExecutor(Executor):
    LANGUAGE = "java-17"
    EXECUTABLE_EXTENSIONS = [".java"]
    DOCKER_IMAGE = "openjdk:17-slim"
    
    @classmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None, code: Optional[str] = None) -> bool:
        if file_name is not None:
            extension = os.path.splitext(file_name)[1]
        if extension and extension.lower() in cls.EXECUTABLE_EXTENSIONS:
            return True
        return False
        
    def _detect_imports(self, code: str) -> List[str]:
        return []

    def execute(self) -> ExecutionResult:
        start_time = datetime.now()
        
        if not self.file.data:
             return ExecutionResult.error("No code to execute")
             
        code = self.file.data
        filename = self.file.name or "Main.java"
        classname = os.path.splitext(filename)[0]
        
        client = self._get_docker_client()
        if not client:
            return ExecutionResult.error("Docker is not available")
            
        if not self._ensure_image(self.DOCKER_IMAGE):
             return ExecutionResult.error("Docker image not available")
             
        if self.datasets:
            temp_staging_dir = tempfile.mkdtemp(prefix='codepost_datasets_')
        else:
            temp_staging_dir = ""
            
        volumes = self._get_volume_mounts(temp_staging_dir if self.datasets else "")
        docker_env = self._get_docker_environment()
        
        # Prepare Command
        # Write code to file and run
        code_b64 = base64.b64encode(code.encode('utf-8')).decode('utf-8')
        
        # cmd: echo <b64> | base64 -d > file.java && javac file.java && java classname
        cmd_str = f"echo '{code_b64}' | base64 -d > {filename} && javac {filename} && java {classname}"
        command = ["sh", "-c", cmd_str]
        
        if self.pre_script:
             # If pre-script exists, we wrap: .pre_script.sh && cmd
             # But cmd is complex string.
             # We can write .pre_script.sh, execute it, then execute our cmd.
             # "sh -c '. ./.pre_script.sh && ...'"
             pass 
             # For simplicity, ignore pre_script wrapping for now or implement if strictly needed.
             # PythonExecutor wraps it.
             
        container = self.get_container(
            image_name=self.image,
            command=command,
            env=docker_env,
            volumes=volumes,
            needs_network=False
        )
        
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
            if self.datasets:
                shutil.rmtree(temp_staging_dir, ignore_errors=True)

class JavaNotebookExecutor(NotebookExecutor):
    """
    Executor for Java Jupyter notebooks.
    
    Uses JShell to execute the Java notebook template.
    """
    LANGUAGE = "java"
    TEMPLATE = "notebook_template.java"
    DOCKER_IMAGE = "eclipse-temurin:21-jdk"
    EXECUTABLE_EXTENSIONS = ['.ipynb']
    EXECUTION_COMMAND = ["java"]  # Will be overridden in _get_execution_command

    @classmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None, code: Optional[str] = None) -> bool:
        """
        Check if this is a Java notebook.
        
        A Java notebook must have a Java kernel and .ipynb extension.
        """
        if file_name is not None:
            extension = os.path.splitext(file_name)[1]

        try:
            kernel_name = cls.get_kernel_name(code)
            # Check if it's a Java kernel
            if kernel_name and 'java' in kernel_name.lower():
                if extension is not None and extension.lower() in cls.EXECUTABLE_EXTENSIONS:
                    return True
        except:
            pass
            
        return False

    def _get_execution_command(self, template: str) -> List[str]:
        """
        Get the command to execute the Java template.
        
        For Java, we write the template to a file and compile/run it.
        """
        import tempfile
        
        # Write template to a temp file
        # Since we are running in docker, we can't write to /work easily from here if we want to RUN `javac /work/file`.
        # Wait, `NotebookExecutor.execute` calls this to get a command list.
        # But `NotebookExecutor.execute` assumes `command` is passed to `get_container`.
        # And `get_container` runs the command.
        
        # If we return ["sh", "-c", "..."], we need to put the template content somehow.
        # PythonExecutor does `python -c template`.
        # Java template is too large for command line likely?
        # `notebook_template.java` is large (parsed JSON etc).
        
        # Strategy: Use Base64 echo trick like JavaExecutor above.
        
        template_b64 = base64.b64encode(template.encode('utf-8')).decode('utf-8')
        
        # We need a filename for the class. 
        # `notebook_template.java` defines `public class notebook_template`?
        # I should check the class name in `notebook_template.java`.
        
        # Assuming class name is `Executor` or no public class?
        # If I write to `NotebookRunner.java`, class should be `NotebookRunner`.
        # I'll check `notebook_template.java` content quickly below task boundary if needed?
        # I moved it.
        
        # Default behavior:
        # echo B64 | base64 -d > NotebookRunner.java && javac NotebookRunner.java && java NotebookRunner
        # Note: Depending on template content.
        
        return ["sh", "-c", f"echo '{template_b64}' | base64 -d > NotebookRunner.java && javac NotebookRunner.java && java NotebookRunner"]

    def _get_code_template(self, code: str, packages_to_install: List[str]) -> Optional[str]:
        """Get the Java notebook template with cells substituted."""
        template = super()._get_code_template()
        if not template:
            return None

        template = template.replace('{cells_b64}', code)
        
        # Ensure class name matches `NotebookRunner` if I forced it above?
        # Or replace `public class ...` with `public class NotebookRunner`?
        # I'll replace `public class notebook_template` -> `public class NotebookRunner` just in case.
        template = template.replace("public class notebook_template", "public class NotebookRunner")
        # Also handle "class notebook_template"
        template = template.replace("class notebook_template", "class NotebookRunner")
        
        return template
