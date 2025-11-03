"""
Code Execution Service

Handles execution of code files and Jupyter notebooks with proper sandboxing,
timeout handling, and output capture.

Security: Uses Docker containers for sandboxing to provide strong isolation
from the host system. Each execution runs in an isolated, disposable container.
"""

from calendar import c
from email.mime import image
from sys import stderr
import threading
import warnings
# Suppress pkg_resources deprecation warning from coreapi
warnings.filterwarnings('ignore', message='pkg_resources is deprecated', category=UserWarning)

import abc
import tempfile
import json
import os
import shutil
import logging
import tarfile
import ast
import re
import time
from typing import Dict, List, Literal, Optional, Tuple, Any, TypedDict
from pathlib import Path
from docker import DockerClient

import nbformat
from datetime import datetime


from core.models import  File, User

try:
    import docker
    from docker.errors import DockerException, ImageNotFound, ContainerError, APIError
    from requests.exceptions import ReadTimeout
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None
    ReadTimeout = Exception  # Fallback

logger = logging.getLogger(__name__)





class ExecutionResult:
    """Result of a code execution"""

    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        err: Optional[str] = None,
        execution_time: float = 0.0,
        output_data: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.err = err
        self.execution_time = execution_time
        self.output_data = output_data or {}
    
    @classmethod
    def error(cls, message: str) :
        """Create an error ExecutionResult"""
        return cls(
            success=False,
            stdout="",
            stderr="",
            err=message,
            execution_time=0.0,
            output_data={}
        )
    @classmethod
    def error_notebook(cls, nb: nbformat.NotebookNode, message: str) :
        """Create an error ExecutionResult for notebooks"""
        return cls(
            success=False,
            err=message,
            execution_time=0.0,
            output_data={
                "cells": [{
                    "cell_type": "code",
                    "source": "",
                    "outputs": [{
                        "output_type": "error",
                        "ename": "ExecutionError",
                        "evalue": message,
                        "traceback": []
                    }],
                    "execution_count": None
                }],
                "notebook": "",
            }
        )
    
    def save_cache(self, file_obj, executed_by: Optional[User] = None):
        """Save execution result to cache"""
        from core.models import CachedExecutionResult
        
        
        # if cells in output_data, then thats the output, but if not we do .to_dict()
        if "cells" in self.output_data:
            output_data = self.output_data
        else:
            output_data = self.to_dict()
        
        CachedExecutionResult.save_execution_result(
            file=file_obj,
            output_data=output_data,
            executed_by=executed_by,
            execution_time=self.execution_time if hasattr(self, 'execution_time') else None
        )
        

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.err,
            "execution_time": self.execution_time,
            "output_data": self.output_data,
            "timestamp": datetime.now().isoformat(),
        }

class Executor(abc.ABC):
    
    """Abstract base class for code executors"""
    
    # Class-level constants Should be implemented in subclasses
    LANGUAGE = ""
    EXECUTABLE_EXTENSIONS = []
    TEMPLATE:str = ""
    DOCKER_IMAGE: str = ""
    LANGUAGE: str = ""
    INIT_DOCKER_VOLUME: Dict[str, Dict[str, str]] = {}
    
    
    # Security limits
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Docker resource limits
    MAX_MEMORY = "512m"  # 512MB memory limit
    MAX_MEMORY_SWAP = "512m"  # No swap
    CPU_QUOTA = 100000  # 1 CPU (100000/100000)
    CPU_PERIOD = 100000
    MAX_PIDS = 50  # Maximum number of processes
    
    # Docker client (singleton)
    _docker_client: Optional[DockerClient] = None
    

    NPM_CACHE_VOLUME_NAME = "codepost-npm-cache"
    # NPM package whitelist for Node.js/JavaScript
    NPM_PACKAGE_WHITELIST = [
        "lodash",
        "axios",
        "express",
        "moment",
        "underscore",
        "async",
        "request",
        "chalk",
        "commander",
        "debug",
    ]

    # Maven/Gradle package whitelist for Java
    JAVA_PACKAGE_WHITELIST = [
        "gson",
        "json",
        "commons-lang3",
        "junit",
        "guava",
        "jackson",
    ]

    # Maven/Gradle package mapping for Java
    JAVA_PACKAGE_MAPPING = {
        "gson": "com.google.code.gson",
        "json": "org.json",
        "commons-lang3": "org.apache.commons",
        "junit": "junit",
        "guava": "com.google.guava",
        "jackson": "com.fasterxml.jackson",
    }
    
    # Gem whitelist for Ruby
    RUBY_PACKAGE_WHITELIST = [
        "rails",
        "sinatra",
        "nokogiri",
        "httparty",
        "rspec",
    ]
    
    # Docker images for each language
    LANGUAGE_IMAGES = {
        "python": "python:3.12-slim",
        "python3": "python:3.12-slim",
        "javascript": "node:20-slim",
        "js": "node:20-slim",
        "java": "openjdk:17-slim",
        "c": "gcc:latest",
        "cpp": "gcc:latest",
        "ruby": "ruby:3.2-slim",
        "go": "golang:1.21-alpine",
        "rust": "rust:1.75-slim",
        "bash": "bash:latest",
        "sh": "bash:latest",
    }
    # Language-specific commands (run inside container)
    LANGUAGE_COMMANDS = {
        "python": ["python3", "-u"],  # -u for unbuffered output
        "python3": ["python3", "-u"],
        "javascript": ["node"],
        "js": ["node"],
        "java": ["java"],
        "c": ["sh", "-c", "gcc -o /tmp/a.out /code/code.c && /tmp/a.out"],
        "cpp": ["sh", "-c", "g++ -o /tmp/a.out /code/code.cpp && /tmp/a.out"],
        "ruby": ["ruby"],
        "go": ["go", "run"],
        "rust": ["sh", "-c", "rustc -o /tmp/a.out /code/code.rs && /tmp/a.out"],
        "bash": ["bash"],
        "sh": ["sh"],
    }

    
    # Docker client (singleton)
    _docker_client: Optional[DockerClient] = None
    
    
    # Common Docker Functions 
    @classmethod
    def _get_docker_client(cls):
        """Get or create Docker client"""
        if not DOCKER_AVAILABLE:
            return None
            
        if cls._docker_client is None:
            try:
                if not docker:
                    logger.error("Docker SDK not available")
                    return None
                cls._docker_client = docker.from_env()
                # Test connection
                cls._docker_client.ping()
            except Exception as e:
                logger.error(f"Failed to connect to Docker: {e}")
                return None
        return cls._docker_client
    
    @classmethod
    def _get_docker_environment(cls) -> Dict[str, str]:
        """Get Docker environment variables"""

        # Should have environment variables for package managers to use cache directories

        docker_env = {
            "NPM_CONFIG_CACHE": "/root/.npm",
            "NPM_CONFIG_LOGLEVEL": "warn",
            "PIP_ROOT_USER_ACTION": "ignore",
            "PIP_CACHE_DIR": "/root/.cache/pip",
            "MPLBACKEND": "Agg",  # For matplotlib headless
        }
        return docker_env
    
    @classmethod
    def _ensure_image(cls, image_name: str) -> bool:
        """
        Ensure Docker image is available locally
        
        Args:
            image_name: Docker image name
            
        Returns:
            True if image is available, False otherwise
        """
        client = cls._get_docker_client()
        if not client:
            return False
            
        try:
            client.images.get(image_name)
            return True
        except ImageNotFound:
            # Try to pull the image
            try:
                logger.info(f"Pulling Docker image: {image_name}")
                client.images.pull(image_name)
                return True
            except Exception as e:
                logger.error(f"Failed to pull image {image_name}: {e}")
                return False

    def get_container(self, image_name: str, command: List[str] | str, env: Dict[str, str], volumes: Dict[str, Dict[str, str]], needs_network: bool = False):
        """
        Get a Docker container for executing a command.

        Args:
            image_name: Docker image name.
            command: Command to run in the container.
            env: Environment variables for the container.
            volumes: Volume mounts for the container.
            needs_network: Whether the container needs network access.
        Returns:
            Docker container instance or None if failed to create.
        """
        client = self._get_docker_client()
        if not client:
            return None

        try:
            container = client.containers.run(
                image=image_name,
                command=command,
                volumes=volumes,
                working_dir="/work",
                # Network settings
                network_disabled=not needs_network,
                # Resource limits
                mem_limit=self.MAX_MEMORY,
                mem_swappiness=0,
                memswap_limit=self.MAX_MEMORY_SWAP,
                cpu_quota=self.CPU_QUOTA,
                cpu_period=self.CPU_PERIOD,
                pids_limit=self.MAX_PIDS,
                #Security options
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],  # Drop all capabilities
                tmpfs={"/tmp": "size=512m,mode=1777"} if not needs_network else {"/tmp": "size=2g,mode=1777"},
                environment=env,
                detach=True
            )
            return container
        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            return None

    def _prepare_dataset_staging(
        self,
        temp_dir: str
    ) -> Dict[str, str]:
        """
        Stage dataset files in a temporary directory for Docker mounting
        
        Creates symlinks in a temp directory that Docker can access, avoiding
        permission issues with direct file mounts.
    
            
        Returns:
            Dict mapping container paths to staged file paths
            Format: {'/root/shared/path/file.csv': '/tmp/staging/file.csv'}
        """
        import os
        import shutil
        
        volume_mounts = {}
        
        if not self.datasets:
            return volume_mounts
        if not temp_dir:
            raise ValueError("Temporary directory is required for dataset staging")
        
        # Create a staging directory for datasets
        staging_dir = os.path.join(temp_dir, 'datasets')
        os.makedirs(staging_dir, exist_ok=True)

        for dataset in self.datasets:
            if not dataset.is_active or not dataset.file:
                continue
            
            try:
                # Get the absolute file path on host
                host_file_path = os.path.abspath(dataset.file.path)
                
                if not os.path.exists(host_file_path):
                    logger.warning(f"[DatasetMount] Dataset file not found: {host_file_path}")
                    continue
                
                # Get mount path in container
                mount_path = dataset.mount_path or f'shared/{dataset.name}'
                
                # Ensure mount_path doesn't start with /
                if mount_path.startswith('/'):
                    mount_path = mount_path[1:]
                
                # Remove 'shared/' prefix if it exists (since we're already mounting at /root/shared)
                if mount_path.startswith('shared/'):
                    mount_path = mount_path[7:]  # Remove 'shared/' prefix
                
                # Get just the filename
                filename = os.path.basename(host_file_path)
                
                # Create a unique staging filename to avoid conflicts
                staged_filename = f"{dataset.id}_{filename}"
                staged_path = os.path.join(staging_dir, staged_filename)
                
                # Copy file to staging directory (Docker needs read access)
                shutil.copy2(host_file_path, staged_path)
                os.chmod(staged_path, 0o644)  # Ensure readable
                
                # Build full container path
                # If mount_path is empty or just the filename, mount directly at /root/shared/<filename>
                # Otherwise mount at /root/shared/<mount_path>
                if mount_path and mount_path != filename:
                    container_path = os.path.join('/root/shared', mount_path)
                else:
                    container_path = os.path.join('/root/shared', filename)
                container_path = os.path.normpath(container_path)
                
                volume_mounts[container_path] = staged_path
                
                logger.info(f"[DatasetMount] Staged '{host_file_path}' -> '{staged_path}'")
                logger.info(f"[DatasetMount] Will mount as '{container_path}'")
            
            except Exception as e:
                logger.error(f"[DatasetMount] Failed to stage dataset '{dataset.name}': {e}")
                continue
        
        return volume_mounts



    def _get_volume_mounts(self, temp_staging_dir: str) -> Dict[str, Dict[str, str]]:
        """Get init volume mount with repo caches and dataset staging"""
        volumes = self.INIT_DOCKER_VOLUME.copy()
        if self.datasets:
            self.log("Preparing dataset staging for volume mounts")
            dataset_mounts = self._prepare_dataset_staging(temp_staging_dir)
            for container_path, host_path in dataset_mounts.items():
                    volumes[host_path] = {'bind': container_path, 'mode': 'ro'}
        self.log(f"Volume mounts: {volumes}", "debug")
        return volumes
            
    @abc.abstractmethod
    def _detect_imports(self,code: str) -> List[str]:
        """
        Detect imported packages from code
        
        Args:
            code: Source code to analyze
        """
        pass
    @abc.abstractmethod
    def execute(self) -> ExecutionResult:
        """Execute code in a specific programming language"""
        """
        Example implementation steps:
        
        # 1. Check for file data and language
            if not self.file.data:
                return ExecutionResult.error("File has no data to execute")
        # 2. Get imports from file
            code = self.file.data
            imports = self._detect_imports(code)
        
        # 3. Prepare code with install commands
            template = self._get_code_template(code, imports)
        
        # 4. Ensure Docker image
            client = self._get_docker_client()
            if not client:
                return ExecutionResult.error("Docker is not available")

            if not self._ensure_image(self.DOCKER_IMAGE):
                return ExecutionResult.error("Docker image is not available")

        # 5. Create temp directory and volume mounts
            if self.datasets:
                temp_staging_dir = tempfile.mkdtemp(prefix='codepost_datasets_')
                
                volumes = self._get_volume_mounts(temp_staging_dir if self.datasets else "")
        
        # 6. Get docker environment
            docker_env = self._get_docker_environment()
        
        # 7. Create and run container
            container = self.get_container()
            self.add_additional_files(container)
        
        # 8. Capture output and handle errors
            try:
                exit_code = container.wait(timeout=self.DEFAULT_TIMEOUT)
                logs = container.logs(stdout=True, stderr=True, stream=False)
                # Process logs and return ExecutionResult
            except ReadTimeout:
                container.kill()
                return ExecutionResult.error("Execution timed out")
            except Exception as e:
                return ExecutionResult.error(f"Execution error: {str(e)}")
            finally:
                container.remove()
                if self.datasets:
                    shutil.rmtree(temp_staging_dir, ignore_errors=True)
        """
        
        pass
    
    # Streaming execution
    
    def execute_streaming(self, user) -> Any:
        """Execute code with streaming output (generator) Executed and saves to cache"""
    
        
        yield self._sse_message("progress", {
            "status": "executing",
            "message": "Running code..."
        })
        # Execute code
        result = None  # type: ignore
        execution_error = None
        execution_complete = threading.Event()
        
        def execute_notebook_thread():
            """Execute notebook in background thread"""
            nonlocal self, result, execution_error
            try:
                result = self.execute()
            except Exception as e:
                self.log(f"Execution error: {e}", "error")
                execution_error = e
            finally:
                execution_complete.set()
        
        # Start execution in background thread
        exec_thread = threading.Thread(target=execute_notebook_thread, daemon=True)
        exec_thread.start()
        
        
        # Send keepalive messages every 5 seconds while execution is running
        keepalive_count = 0
        while not execution_complete.is_set():
            if execution_complete.wait(timeout=1):  # Wait up to 1 second
                break
            keepalive_count += 1
            yield self._sse_message("progress", {
                "status": "executing",
                "message": f"Running... ({keepalive_count * 1}s)"
            })
        
        # Wait for thread to complete
        exec_thread.join(timeout=1)
        
        # Check if execution failed
        if execution_error:
            yield self._sse_message("error", {"error": f"Execution failed: {str(execution_error)}"})
        
        if result is None:
            yield self._sse_message("error", {"error": "Execution failed: No result returned"})
            
        if not result.success:
            yield self._sse_message("error", {"error": f"Execution failed: {result.error}"})
        
        yield self._sse_message("progress", {
            "status": "completed",
            "message": f"Complete! Processed {self.file.name}."
        })
        result: ExecutionResult = result  # type: ignore
        result.save_cache(self.file, user)
        
        submission,_,_ = self.file.get_file_info()
        try:
            response_data = {
                **result.to_dict(),
                "file_id": self.file.id,
                "file_name": self.file.name,
                "cached": False,
                "submission_id": submission.id if submission else None,
            }
            self.log(f"Execution complete, sending final data: {response_data['file_name']}", "debug")
            yield self._sse_message("complete", response_data)
        except Exception as e:
            self.log(f"Failed to send complete message: {e}", "error")
            yield self._sse_message("error", {"error": f"Failed to send complete message: {str(e)}"})
        finally:
            time.sleep(0.1)

        
    def _sse_message(self, event: str, data: dict) -> str:
        """
        Format a Server-Sent Event message
        
        Args:
            event: Event type (progress, complete, error)
            data: Event data as dictionary
            
        Returns:
            Formatted SSE message string
        """
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"
    
    # Initialization
    def __init__(self, file:File):
        """Initialize executor with file and context"""
        self.file = file
        submission, assignment, _ = file.get_file_info()
        
        # If submissions is provided, we can use it to get addictional files and datasets
        self.datasets = list(assignment.dataSets.filter(is_active=True)) if assignment else []
        additional_files = {}
        if submission:
            all_files = submission.files.all()
            
            for other_file in all_files:
                if other_file.id == file.id:
                    continue  # Skip the main file being executed
                if hasattr(other_file, 'data') and other_file.data:
                    additional_files[other_file.name] = other_file.data
        self.additional_files = additional_files
    
    # Building code execution script from template
    
    def __repr__(self):
        return f"[{self.__class__.__name__}] [{self.file.name}] [{self.LANGUAGE}]"
    
    def log(self, message: str, level: str = "info"):
        logger.log(getattr(logging, level.upper(), logging.INFO), f"{self.__repr__()} {message}")
    
    def _get_code_template(self) -> Optional[str]:
        """Get code template for the executor"""
        template_file = self.TEMPLATE
        if not template_file:
            self.log("Missing template name", "error")
            return None

        template_path = os.path.join(os.path.dirname(__file__), template_file)
        try:
            with open(template_path, 'r') as f:
                return f.read()
        except Exception as e:
            self.log(f"Failed to load template for: {e}", "error")
            return ""

    def add_additional_files(self, container: Any):
        if not self.additional_files:
            return
        from io import BytesIO
        self.log(f"Injecting {len(self.additional_files)} files into container")
                
        # Create tar archive in memory
        tar_stream = BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            for filename, content in self.additional_files.items():
                # Create tarinfo for this file
                content_bytes = content.encode('utf-8')
                tarinfo = tarfile.TarInfo(name=filename)
                tarinfo.size = len(content_bytes)
                tarinfo.mode = 0o644
                
                # Add file to tar
                tar.addfile(tarinfo, BytesIO(content_bytes))
        
        # Seek to beginning of stream
        tar_stream.seek(0)
        tar_data = tar_stream.read()
        
        # Inject files into container at /work
        container.put_archive('/work', tar_data)

    @classmethod
    @abc.abstractmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None) -> bool:
        """Check if the file is executable based on its extension"""
        pass
    
    @classmethod
    def factory(cls, file:File) -> Optional['Executor']:
        """Factory method to get appropriate Executor subclass"""
        for subclass in cls.__subclasses__():
            if subclass.is_executable(file_name=file.name):
                return subclass(file)
        return None
    
    @classmethod
    def is_executable_file(cls, file: str) -> bool:
        """Check if the given file is executable by any sub executor"""
        for subclass in cls.__subclasses__():
            if subclass.is_executable(file_name=file):
                return True
        return False
    
    



class PythonExecutor(Executor):
    LANGUAGE = "python"
    TEMPLATE = "template.py"
    DOCKER_IMAGE = "python:3.12-slim"

    EXECUTABLE_EXTENSIONS = [".py"]
        
    PIP_CACHE_VOLUME_NAME = "codepost-pip-cache"
    
    INIT_DOCKER_VOLUME = {
        PIP_CACHE_VOLUME_NAME: {
            "bind": "/root/.cache/pip",
            "mode": "rw"
        }
    }
   
    PIP_MODULE_TO_PACKAGE = {
        "sklearn": "scikit-learn",
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "bs4": "beautifulsoup4",
        "yaml": "pyyaml",
        "dateutil": "python-dateutil",
    }
    
    
    
    @classmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None) -> bool:
        if file_name is not None:
            extension = os.path.splitext(file_name)[1]

        if extension is not None and extension.lower() in cls.EXECUTABLE_EXTENSIONS:
            return True
        return False
    
    def _detect_imports(self, code) -> List[str]:
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
        except Exception as e:
            self.log(f"Error parsing Python code for imports: {e}")
        
        # Map module names to package names
        mapped_packages = set()
        for module_name in packages_to_install:
            package_name = self.PIP_MODULE_TO_PACKAGE.get(module_name, module_name)
            mapped_packages.add(package_name)
        packages_to_install = mapped_packages
        return list(packages_to_install)

    def _get_code_template(self, code: str, packages_to_install: List[str]) -> Optional[str]:
        template = super()._get_code_template()
        if not template:
            return None
        
        if template and packages_to_install:
            # Modify the template to include package installation
            template = template.replace("packages_to_install = []", f"packages_to_install = {repr(packages_to_install)}")
        
        template = template.replace("#{FILLER_CODE}", code)
        return template

    def execute(self) -> ExecutionResult:
        """Execute Python code in Docker container"""
        # Implementation of Python code execution
        timeout = self.DEFAULT_TIMEOUT
        start_time = datetime.now()
        
        if not self.file.data:
            return ExecutionResult.error("No code to execute")
        
        code = self.file.data
        
        # Detect imports
        packages_to_install = self._detect_imports(code)

        # Get code template
        template = self._get_code_template(code, packages_to_install)
        if not template:
            return ExecutionResult.error("Failed to get code template")

        # Execute code in Docker container
        
        client = self._get_docker_client()
        if not client:
            return ExecutionResult.error("Docker is not available")

        if not self._ensure_image(self.DOCKER_IMAGE):
            return ExecutionResult.error("Docker image is not available")


        if self.datasets:
            temp_staging_dir = tempfile.mkdtemp(prefix='codepost_datasets_')
            
        volumes = self._get_volume_mounts(temp_staging_dir if self.datasets else "")
                    
        command = ["python", "-c", template]
        
        docker_env = self._get_docker_environment()

        needs_network = True if len(packages_to_install) > 0 else False

        container = self.get_container(
            image_name=self.DOCKER_IMAGE,
            command=command,
            env=docker_env,
            volumes=volumes,
            needs_network=needs_network
        )
        if not container:
            return ExecutionResult.error("Failed to create Docker container")
        
        self.add_additional_files(container)
        try:
            container.start()
            self.log("Starting code execution in Docker container")
            adjusted_timeout = timeout + (30 * len(packages_to_install))
            result = container.wait(timeout=adjusted_timeout)
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            success = result.get('StatusCode', 1) == 0
            self.log(f"Execution completed in {execution_time:.2f}s with exit code {result.get('StatusCode', 1)}")

            # Truncate output if too large
            if len(stdout) > self.MAX_OUTPUT_SIZE:
                self.log("Truncating stdout due to size limit")
                stdout = "ERROR: Output truncated due to large output size\n" + stdout[:self.MAX_OUTPUT_SIZE] + "\n...[truncated stdout over limit]..."
            if len(stderr) > self.MAX_OUTPUT_SIZE:
                self.log("Truncating stderr due to size limit")
                stderr = "ERROR: Output truncated due to large output size\n" + stderr[:self.MAX_OUTPUT_SIZE] + "\n...[truncated stderr over limit]..."

            result = ExecutionResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                err=None if success else f"Non-zero exit code: {result.get('StatusCode', 1)}",
                execution_time=execution_time,
                output_data={}
            )

            return result
        except ReadTimeout:
            container.kill()
            return ExecutionResult.error("Execution timed out")
        except Exception as e:
            container.kill()
            return ExecutionResult.error(f"Execution failed: {e}")
        finally:
            self.log("Cleaning up Docker container")
            container.remove()
            if self.datasets:
                shutil.rmtree(temp_staging_dir, ignore_errors=True)
    TEMPLATES = "template.py"

class PythonNotebookExecutor(Executor):
    LANGUAGE = "python"

    TEMPLATE = "notebook_template.py"
    DOCKER_IMAGE = "python:3.12-slim"
    EXECUTABLE_EXTENSIONS = ['.ipynb']
       
    PIP_CACHE_VOLUME_NAME = PythonExecutor.PIP_CACHE_VOLUME_NAME
    
    INIT_DOCKER_VOLUME = PythonExecutor.INIT_DOCKER_VOLUME.copy()

    PIP_MODULE_TO_PACKAGE = PythonExecutor.PIP_MODULE_TO_PACKAGE.copy()

    @classmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None) -> bool:
        if file_name is not None:
            extension = os.path.splitext(file_name)[1]

        if extension is not None and extension.lower() in cls.EXECUTABLE_EXTENSIONS:
            return True
        return False

    def _detect_imports(self, nb:  nbformat.NotebookNode) -> List[str]:
        """
        Detect imported packages from all notebook cells

        Scans all code cells for import statements and maps them to pip package names.
        This allows us to pre-install packages before execution, avoiding slow retry loops.

        Args:
            nb: Parsed notebook
            
        Returns:
            List of package names to install (filtered by whitelist)
        """
        import re
        import ast


        packages_to_install = set()

        self.log(f"[NotebookImports] Scanning {len(nb.cells)} cells for import statements")

        # Scan all code cells for imports
        for cell_idx, cell in enumerate(nb.cells):
            if cell.cell_type != "code":
                continue
            
            cell_packages = set()
            
            try:
                # Try to parse the cell as Python AST (most reliable)
                tree = ast.parse(cell.source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            module_name = alias.name.split('.')[0]
                            cell_packages.add(module_name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            module_name = node.module.split('.')[0]
                            cell_packages.add(module_name)
            except SyntaxError:
                # If AST parsing fails, try regex as fallback
                # Matches: "import xyz", "from xyz import", "from xyz.abc import"
                import_matches = re.findall(
                    r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', 
                    cell.source, 
                    re.MULTILINE
                )
                cell_packages.update(import_matches)
            except Exception as e:
                logger.warning(f"[NotebookImports] Error parsing cell {cell_idx}: {e}")
                continue
            
            # Map module names to package names and add to set
            for module_name in cell_packages:
                package_name = self.PIP_MODULE_TO_PACKAGE.get(module_name, module_name)
                packages_to_install.add(package_name)

        packages = [pkg for pkg in packages_to_install ]

        self.log(f"Detected packages to install: {packages}", "debug")

        return packages
    def execute(self):
        self.log("Reading notebook data")
        if not self.file.data:
            return ExecutionResult.error("No notebook data found")
        
        nb = nbformat.reads(self.file.data, as_version=4)
        client = self._get_docker_client()
        if not client:
            return ExecutionResult.error("Docker is not available")
        
        image_name = self.DOCKER_IMAGE
        if not self._ensure_image(image_name):
            return ExecutionResult.error("Docker image is not available")
        timeout = self.DEFAULT_TIMEOUT
        
        
        import json
        import base64
        import tempfile
        temp_staging_dir = tempfile.mkdtemp(prefix='codepost_datasets_')
        volumes = self._get_volume_mounts(temp_staging_dir)
        docker_env = self._get_docker_environment()
        
        # Prepare notebook cells data
        cells_data = []
        for cell in nb.cells:
            if cell.cell_type == "markdown":
                cells_data.append({
                    "type": "markdown",
                    "source": cell.source
                })
            elif cell.cell_type == "code":
                cells_data.append({
                    "type": "code",
                    "source": cell.source
                })
                
        packages_to_install = self._detect_imports(nb)
        cells_json = json.dumps(cells_data)
        cells_b64 = base64.b64encode(cells_json.encode('utf-8')).decode('ascii')
        
        template = self._get_code_template(cells_b64, packages_to_install)
        if not template:
            return ExecutionResult.error("Failed to get code template")

        needs_network = True if len(packages_to_install) > 0 else False
        
        command = ["python", "-c", template]
        
        container = self.get_container(
            image_name=self.DOCKER_IMAGE,
            command=command,
            env=docker_env,
            volumes=volumes,
            needs_network=needs_network
        )
        if not container:
            return ExecutionResult.error("Failed to create Docker container")
        
        self.add_additional_files(container)
        
        try:
            container.start()
            self.log("Container started, waiting for execution to complete")
            adjusted_timeout = timeout + (30 * len(packages_to_install))
            container.wait(timeout=adjusted_timeout)
            # Get output with proper error handling
            self.log(f"Fetching container logs...")
            # Check container state first
            try:
                container.reload()
                self.log(f"Container state: {container.status}")
            except Exception as e:
                self.log(f"Could not reload container: {e}")

            stdout = ""
            stderr = ""
            
            try:
                # Get logs - note: this returns bytes
                # Use stream=False to get all logs at once (not a generator)
                logs = container.logs(stdout=True, stderr=True, timestamps=False, stream=False)
                self.log(f"Docker logs API call completed")
                
                if isinstance(logs, bytes):
                    # Decode to string
                    full_output = logs.decode("utf-8", errors="replace")
                    self.log(f"Got combined output ({len(full_output)} bytes)")
                    
                    # For notebook execution, stdout contains both stdout and stderr mixed
                    # We'll treat it all as stdout since that's where our JSON results are
                    stdout = full_output
                    stderr = ""  # Stderr is mixed into stdout by Docker
                else:
                    self.log(f"Unexpected logs type: {type(logs)}")
                    stdout = str(logs)
                    
            except Exception as e:
                self.log(f"Failed to get container logs: {e}")
                # Try to get status even if logs fail
                try:
                    result_status = container.wait()
                    self.log(f"Container status: {result_status}")
                except:
                    pass
            
            # Parse results from output
            self.log(f"Parsing execution results from stdout...")
            
            # Check if results markers are present
            if "<<<RESULTS_START>>>" in stdout and "<<<RESULTS_END>>>" in stdout:
                results_json = stdout.split("<<<RESULTS_START>>>")[1].split("<<<RESULTS_END>>>")[0].strip()
                
                try:
                    executed_cells = json.loads(results_json)
                    self.log(f"Successfully parsed {len(executed_cells)} cells")

                    # Convert type field to cell_type for consistency
                    for cell in executed_cells:
                        cell["cell_type"] = cell.pop("type")
                    
                    
                    results = self.format_notebook_execution_result(nb, executed_cells)
                    return results
                except json.JSONDecodeError as e:
                    self.log(f"JSON decode error: {e}")
                    self.log(f"Results JSON preview: {results_json[:500]}")
                    return self.format_notebook_execution_result(nb, [{
                        "cell_type": "code",
                        "source": "",
                        "outputs": [{
                            "output_type": "error",
                            "ename": "JSONDecodeError",
                            "evalue": f"Failed to parse execution results: {str(e)}",
                            "traceback": [str(e)]
                        }],
                        "execution_count": 1
                    }], error=True)
                except Exception as e:
                    self.log(f"Error processing results: {e}")
                    return self.format_notebook_execution_result(nb, [{
                        "cell_type": "code",
                        "source": "",
                        "outputs": [{
                            "output_type": "error",
                            "ename": "ResultProcessingError",
                            "evalue": f"Error processing execution results: {str(e)}",
                            "traceback": [str(e)]
                        }],
                        "execution_count": 1
                    }], error=True)
            else:
                # Execution failed
                self.log(f"No results markers found in output")
                self.log(f"stdout length: {len(stdout)}, stderr length: {len(stderr)}")
                self.log(f"stdout preview: {stdout[:500]}")
                return self.format_notebook_execution_result(nb, [{
                    "cell_type": "code",
                    "source": "",
                    "outputs": [{
                        "output_type": "error",
                        "ename": "ExecutionError",
                        "evalue": f"Failed to execute notebook: {stderr[:500]}",
                        "traceback": [stderr[:1000]]
                    }],
                    "execution_count": 1
                }], error=True)

        except ReadTimeout:
            container.kill()
            return ExecutionResult.error_notebook(nb, "Execution timed out")
        except Exception as e:
            container.kill()
            return ExecutionResult.error_notebook(nb, f"Execution failed: {e}")
        finally:
            self.log("Cleaning up Docker container")
            container.remove()
            shutil.rmtree(temp_staging_dir, ignore_errors=True)

    def format_notebook_execution_result(self, nb: nbformat.NotebookNode, executed_cells: List[Dict[str, Any]], error: bool = False) -> ExecutionResult:
        """Format executed notebook cells into ExecutionResult"""
        # For now, we just return the executed cells as output_data
        
                 
        # Check if any cell failed
        overall_success = True
        overall_error = None
        for cell in executed_cells:
            if cell.get("cell_type") == "code":
                for output in cell.get("outputs", []):
                    if output.get("output_type") == "error":
                        overall_success = False
                        overall_error = output.get("evalue")
                        break
                if not overall_success:
                    break
        
        # Create executed notebook
        executed_nb = nb.copy()
        
        # Update cells with outputs (only code cells)
        code_cell_idx = 0
        for i, cell in enumerate(executed_nb.cells):
            if cell.cell_type == "code":
                # Find corresponding executed cell
                for exec_cell in executed_cells:
                    if exec_cell.get("cell_type") == "code" and exec_cell["execution_count"] == code_cell_idx + 1:
                        # Update cell outputs
                        cell.outputs = []
                        for output_dict in exec_cell["outputs"]:
                            if output_dict["output_type"] == "stream":
                                cell.outputs.append(nbformat.v4.new_output(
                                    "stream",
                                    name=output_dict["name"],
                                    text=output_dict["text"]
                                ))
                            elif output_dict["output_type"] == "error":
                                cell.outputs.append(nbformat.v4.new_output(
                                    "error",
                                    ename=output_dict["ename"],
                                    evalue=output_dict["evalue"],
                                    traceback=output_dict["traceback"]
                                ))
                            elif output_dict["output_type"] == "display_data":
                                cell.outputs.append(nbformat.v4.new_output(
                                    "display_data",
                                    data=output_dict["data"],
                                    metadata=output_dict.get("metadata", {})
                                ))
                            elif output_dict["output_type"] == "execute_result":
                                cell.outputs.append(nbformat.v4.new_output(
                                    "execute_result",
                                    data=output_dict["data"],
                                    metadata=output_dict.get("metadata", {}),
                                    execution_count=output_dict.get("execution_count", 0)
                                ))
                        cell.execution_count = exec_cell["execution_count"]
                        break
                code_cell_idx += 1
        
        return ExecutionResult(
            success=not error,
            err=overall_error,
            output_data={
                "cells": executed_cells,
                "notebook": nbformat.writes(executed_nb),
                "kernel_used": "python3",
            },
        )

    def _get_code_template(self, code: str, packages_to_install: List[str]) -> Optional[str]:
        template = super()._get_code_template()
        if not template:
            return None
        
        # Replace installation packages
        if packages_to_install:
            template = template.replace("packages_to_install = []", f"packages_to_install = {repr(packages_to_install)}")

        template = template.replace('{cells_b64}', code)
        return template

