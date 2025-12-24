"""
Code Execution Service

Handles execution of code files and Jupyter notebooks with proper sandboxing,
timeout handling, and output capture.

Security: Uses Docker containers for sandboxing to provide strong isolation
from the host system. Each execution runs in an isolated, disposable container.
"""

import threading
import warnings
# Suppress pkg_resources deprecation warning from coreapi
warnings.filterwarnings('ignore', message='pkg_resources is deprecated', category=UserWarning)
import base64
import abc
import tempfile
import json
import os
import shutil
import logging
import tarfile
import struct
import ast
import re
import time
from typing import Dict, List, Literal, Optional, Tuple, Any, TypedDict,Union
from pathlib import Path
from docker import DockerClient
from codepost.settings import DEBUG
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


# =============================================================================
# nbformat v4 Type Definitions
# These match the Jupyter Notebook format specification v4.5
# https://nbformat.readthedocs.io/en/latest/format_description.html
# =============================================================================

class NotebookCellOutput(TypedDict, total=False):
    """
    Output of a notebook cell (nbformat v4).
    
    Different output types use different fields:
    - stream: output_type, name, text
    - execute_result: output_type, data, metadata, execution_count
    - display_data: output_type, data, metadata
    - error: output_type, ename, evalue, traceback
    """
    output_type: Literal["stream", "execute_result", "display_data", "error"]
    # For stream output
    name: Literal["stdout", "stderr"]
    text: str  # Can also be List[str] but we normalize to str
    # For execute_result/display_data
    data: Dict[str, Any]  # MIME-type keyed, e.g. {"text/plain": "...", "image/png": "..."}
    metadata: Dict[str, Any]
    execution_count: Optional[int]
    # For error output
    ename: str
    evalue: str
    traceback: List[str]


class NotebookCell(TypedDict, total=False):
    """
    A cell in a Jupyter notebook (nbformat v4).
    
    Both code and markdown cells have:
    - cell_type: "code" | "markdown" | "raw"
    - source: The cell content (string or list of strings)
    - metadata: Cell-level metadata
    
    Code cells additionally have:
    - outputs: List of cell outputs after execution
    - execution_count: Order of execution (null if not executed)
    """
    cell_type: Literal["code", "markdown", "raw"]
    source: str  # Can also be List[str] but we normalize to str
    outputs: List[NotebookCellOutput]  # Code cells only
    execution_count: Optional[int]  # Code cells only
    metadata: Dict[str, Any]


class NotebookMetadata(TypedDict, total=False):
    """Notebook-level metadata (nbformat v4)."""
    kernelspec: Dict[str, str]  # {"name": "python3", "display_name": "Python 3"}
    language_info: Dict[str, Any]


class Notebook(TypedDict):
    """
    A complete Jupyter notebook (nbformat v4).
    
    This is the top-level structure that can be returned in
    ExecutionResult.output_data for notebook execution.
    """
    cells: List[NotebookCell]
    metadata: NotebookMetadata
    nbformat: int  # Should be 4
    nbformat_minor: int  # Typically 4 or 5


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
        system_logs: Optional[List[str]] = None,
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.err = err
        self.execution_time = execution_time
        self.output_data = output_data or {}
        self.system_logs = system_logs or []
    
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
        """Create an error ExecutionResult for notebooks, outputs_data in nbformatv4 format"""
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
            # Inject system logs into output_data for notebooks
            output_data["system_logs"] = self.system_logs
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
            "system_logs": self.system_logs,
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
    BUILD_CACHE_DIRECTORIES: List[str] = []
    
    
    # Security limits
    DEFAULT_TIMEOUT = 300  # seconds
    MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    # Docker resource limits
    MAX_MEMORY = "1g"  # 1GB memory limit
    MAX_MEMORY_SWAP = "1g"  # No swap
    CPU_QUOTA = 100000  # 1 CPU (100000/100000)
    CPU_PERIOD = 100000
    MAX_PIDS = 500  # Maximum number of processes
    
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
        "R": "r-base:latest",
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
        "R": ["Rscript"],
    }

    
    # Docker client (singleton)
    _docker_client: Optional[DockerClient] = None
    
    @classmethod
    def _demultiplex_logs(cls, logs_data: bytes) -> Tuple[str, str]:
        """
        Demultiplex Docker logs into stdout and stderr.
        Docker log format: [8 bytes header] [padding] [content]
        Header: [1 byte stream type] [3 bytes padding] [4 bytes payload length (big endian)]
        Stream type: 0: stdin, 1: stdout, 2: stderr
        """
        
        stdout_buffer = []
        stderr_buffer = []
        
        i = 0
        while i < len(logs_data):
            if i + 8 > len(logs_data):
                break
                
            header = logs_data[i: i+8]
            try:
                stream_type, len_payload = struct.unpack('>BxxxL', header)
            except struct.error:
                 # If we fail to unpack, it might be that TTY was enabled or data is corrupt
                 # Fallback: treat as stdout
                 stdout_buffer.append(logs_data[i:])
                 break
            
            payload = logs_data[i+8 : i+8+len_payload]
            
            if stream_type == 1:
                stdout_buffer.append(payload)
            elif stream_type == 2:
                stderr_buffer.append(payload)
            else:
                # 0 is stdin, or unexpected. Treat as stdout just in case? Or ignore.
                pass
            
            i += 8 + len_payload
            
        stdout = b"".join(stdout_buffer).decode('utf-8', errors='replace')
        stderr = b"".join(stderr_buffer).decode('utf-8', errors='replace')
        
        return stdout, stderr
    
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
            "NPM_CONFIG_CACHE": "/tmp/npm-cache",
            "NPM_CONFIG_LOGLEVEL": "warn",
            "PIP_ROOT_USER_ACTION": "ignore",
            "PIP_CACHE_DIR": "/tmp/pip-cache",
            "MPLBACKEND": "Agg",  # For matplotlib headless
            "GEM_HOME": "/tmp/gems", # Ruby gems
            "COMPOSER_CACHE_DIR": "/tmp/composer-cache", # PHP Composer
            "R_LIBS_USER": "/tmp/R/library", # R Packages
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
        Stage dataset files in the provided temporary directory for Docker mounting.
        """
        import os
        import shutil
        
        volume_mounts = {}
        
        if not self.datasets:
            return volume_mounts
        
        if not temp_dir:
            raise ValueError("Temporary directory is required for dataset staging")
        
        # We use the provided temp_dir directly. No subdirectories.
        # This temp_dir is already created in the correct location (shared root or tmp) by the caller.

        for dataset in self.datasets:
            if not dataset.is_active or not dataset.file:
                continue
            
            try:
                # Get the absolute file path on host (worker)
                host_file_path = os.path.abspath(dataset.file.path)
                
                # Check for Direct Host Mounting Optimization
                worker_dataset_root = os.environ.get('WORKER_DATASET_ROOT')
                host_dataset_root = os.environ.get('HOST_DATASET_ROOT')
                
                using_direct_mount = False
                bind_source_path = ""
                
                # Check if file is within the worker dataset root
                if worker_dataset_root and host_dataset_root and host_file_path.startswith(worker_dataset_root):
                     # Translate path: /assignment_datasets/X -> /mnt/nfs/datasets/X
                     # Remove worker root prefix
                     rel_path = os.path.relpath(host_file_path, worker_dataset_root)
                     bind_source_path = os.path.join(host_dataset_root, rel_path)
                     using_direct_mount = True
                     
                if not using_direct_mount:
                    # Fallback: Copy to staging
                    if not os.path.exists(host_file_path):
                        logger.warning(f"[DatasetMount] Dataset file not found: {host_file_path}")
                        continue
                    
                    # Get just the filename
                    filename = os.path.basename(host_file_path)
                    
                    # Destination in the staging directory
                    staged_path = os.path.join(temp_dir, filename)
                    
                    # Copy file to staging directory (Docker needs read access)
                    shutil.copy2(host_file_path, staged_path)
                    os.chmod(staged_path, 0o644)  # Ensure readable
                    
                    bind_source_path = staged_path
                
                
                # Get mount path in container
                mount_path = dataset.mount_path or f'shared/{dataset.name}'
                
                # If mount path ends with /, assume it's a directory and append filename
                filename = os.path.basename(host_file_path)
                if mount_path.endswith('/'):
                    mount_path = os.path.join(mount_path, filename)
                
                if mount_path.startswith('/'):
                    # Absolute path
                    container_path = mount_path
                else:
                    # Relative path - ensure it goes to /shared
                    if mount_path.startswith('shared/'):
                         mount_path = mount_path[7:]
                    container_path = os.path.join('/shared', mount_path)

                container_path = os.path.normpath(container_path)

                # Translate path for Docker-in-Docker (Staging Dir Translation)
                # Only needed if we are NOT using direct mount (which is already translated)
                # AND if we are using the shared staging root
                
                if not using_direct_mount:
                    worker_root = os.environ.get('WORKER_STAGING_ROOT')
                    host_root = os.environ.get('HOST_STAGING_ROOT')

                    if worker_root and host_root and bind_source_path.startswith(worker_root):
                        # Replace worker prefix with host prefix
                        bind_source_path = bind_source_path.replace(worker_root, host_root, 1)

                volume_mounts[bind_source_path] = {'bind': container_path, 'mode': 'ro'}
                
                logger.info(f"[DatasetMount] Mounting '{bind_source_path}' -> '{container_path}' (Direct: {using_direct_mount})")
            
            except Exception as e:
                logger.error(f"[DatasetMount] Failed to stage dataset '{dataset.name}': {e}")
                continue
        
        return volume_mounts

    def _create_staging_directory(self) -> str:
        """
        Create a temporary directory for staging files.
        Tries to use the shared staging root (WORKER_STAGING_ROOT) if available,
        otherwise falls back to local /tmp.
        """
        import tempfile
        import os
        
        worker_staging_root = os.environ.get('WORKER_STAGING_ROOT')
        
        if worker_staging_root and os.path.exists(worker_staging_root):
            try:
                temp_dir = tempfile.mkdtemp(prefix='codepost_staging_', dir=worker_staging_root)
                # Ensure directory is readable/traversable by other users (containers)
                os.chmod(temp_dir, 0o755)
                self.log(f"Created staging dir in shared root: {temp_dir}", "debug")
                return temp_dir
            except Exception as e:
                self.log(f"Failed to use shared staging root: {e}. Falling back to default.", "warning")
        
        # Fallback
        self.log("Using local /tmp for staging (shared root unavailable)", "debug")
        return tempfile.mkdtemp(prefix='codepost_staging_')

    def _get_volume_mounts(self, temp_staging_dir: str) -> Dict[str, Dict[str, str]]:
        """Get init volume mount with repo caches and dataset staging"""
        volumes = self.INIT_DOCKER_VOLUME.copy()
        if self.datasets:
            self.log("Preparing dataset staging for volume mounts")
            dataset_mounts = self._prepare_dataset_staging(temp_staging_dir)
            # dataset_mounts now returns {HOST_PATH: {'bind': CONTAINER_PATH, 'mode': 'ro'}}
            # Merging it directly into volumes which fits the Docker client syntax expectations
            volumes.update(dataset_mounts)
            
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
        # templates will do two things, install packages and add security to not allow new packages to be installed. 
            
            template = self._get_code_template(code, imports)
        
        # 4. Ensure Docker image
            client = self._get_docker_client()
            if not client:
                return ExecutionResult.error("Docker is not available")

            if not self._ensure_image(self.DOCKER_IMAGE):
                return ExecutionResult.error("Docker image is not available")

        # 5. Create temp directory and volume mounts
            if self.datasets:
                temp_staging_dir = self._create_staging_directory()
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
            
        if result and not result.success:
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
    
    def __init__(self, file:File, **kwargs):
        """Initialize executor with file and context"""
        self.file = file
        submission, assignment, course = file.get_file_info()


        # Setting the submission and assignment for the executor, 
        # Other files may be executed but we might want to refernece the submission and assignment
        self.submission = submission or None
        self.assignment = assignment or None
        self.course = course or None
        
        # Datasets priority: kwargs > assignment.active
        if 'datasets' in kwargs:
             self.datasets = kwargs['datasets']
        else:
             self.datasets = list(assignment.dataSets.filter(is_active=True)) if assignment else []

        # Input Data (Stdin)
        self.input_data = kwargs.get('input_data')
        
        additional_files = {}

        # 1. Load Assignment Files (Starter Code / Config / Data)
        # These are shared across all submissions for this assignment.
        if assignment:
            for assignment_file in assignment.files.all():
                if assignment_file.id == file.id:
                    continue
                
                if assignment_file.path:
                    full_path = os.path.join(assignment_file.path, assignment_file.name)
                else:
                    full_path = assignment_file.name
                
                if hasattr(assignment_file, 'data') and assignment_file.data:
                    additional_files[full_path] = assignment_file.data

        # 2. Load Submission Files (Student Work)
        # These overwrite assignment files if the paths collide (standard overlay behavior)
        if submission:
            all_files = submission.files.all()
            
            for other_file in all_files:
                if other_file.id == file.id:
                    continue  # Skip the main file being executed
                
                # Construct full path if path is provided
                if other_file.path:
                    full_path = os.path.join(other_file.path, other_file.name)
                else:
                    full_path = other_file.name
                
                if hasattr(other_file, 'data') and other_file.data:
                    additional_files[full_path] = other_file.data
        
        self.additional_files = additional_files
        self.custom_image_name = kwargs.get('image_name')
        
        # Pre-test script from Environment
        self.pre_script = None
        if assignment:
            try:
                env = assignment.environment
                if env:
                    if env.compileText:
                        self.pre_script = env.compileText
                    if env.image_name and not self.custom_image_name:
                        self.custom_image_name = env.image_name
            except Exception:
                pass  # Environment may not exist
        
        # target_cell_id for Notebook/Cell-based execution
        self.target_cell_id = kwargs.get('target_cell_id')
        
        self.executor_logs = []

    def _prepare_input_staging(self, temp_dir: str) -> Dict[str, str]:
        """Stage input data to a file for stdin redirection"""
        if not self.input_data:
            return {}
            
        input_path = os.path.join(temp_dir, 'stdin.txt')
        with open(input_path, 'w') as f:
            f.write(self.input_data)
        
        # Ensure world-readable so non-root container user can read it
        os.chmod(input_path, 0o644)
            
        # Mount to /tmp/stdin.txt
        return {'/tmp/stdin.txt': input_path}

    def _wrap_command_with_stdin(self, command: List[str] | str) -> List[str]:
        """Wrap command with sh -c '... < /tmp/stdin.txt' if input exists"""
        if not self.input_data:
            return command if isinstance(command, list) else command.split()
        
        # Join command if it's a list to form the command string
        cmd_str = " ".join(command) if isinstance(command, list) else command
        
        # Wrap in sh
        return ["sh", "-c", f"{cmd_str} < /tmp/stdin.txt"]

    @property
    def image(self) -> str:
        """Get the docker image to use"""
        return self.custom_image_name or self.DOCKER_IMAGE
    
    # Building code execution script from template
    
    def __repr__(self):
        return f"[{self.__class__.__name__}] [{self.image}] [{self.file.name}] [{self.LANGUAGE}]"
    
    def log(self, message: str, level: str = "info"):
        log_msg = f"{self.__repr__()} {message}"
        logger.log(getattr(logging, level.upper(), logging.INFO), log_msg)
        self.executor_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    
    def _get_code_template(self) -> Optional[str]:
        """Get code template for the executor"""
        template_file = self.TEMPLATE
        if not template_file:
            self.log("Missing template name", "error")
            return None

        template_path = os.path.join(os.path.dirname(__file__), "../templates", template_file)
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
        
        # Separate absolute (system paths) and relative (project paths) files
        relative_files = {}
        absolute_files = {}

        for filename, content in self.additional_files.items():
            if filename.startswith('/'):
                self.log(f"Detected absolute path file: {filename}")
                absolute_files[filename] = content
            else:
                self.log(f"Detected relative path file: {filename}")
                relative_files[filename] = content

        # Helper to inject files
        def inject_tar(files: Dict[str, str], dest_path: str):
            if not files:
                return
            
            tar_stream = BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                for filename, content in files.items():
                    # If absolute, strip leading slash for tar name (extracted relative to dest_path)
                    # When extracting to '/', stripping leading slash makes it work: /etc/foo -> etc/foo -> /etc/foo
                    tar_name = filename.lstrip('/') if filename.startswith('/') else filename
                    
                    self.log(f"Adding to tar: {tar_name} (from {filename})")
                    
                    content_bytes = content.encode('utf-8')
                    tarinfo = tarfile.TarInfo(name=tar_name)
                    tarinfo.size = len(content_bytes)
                    tarinfo.mode = 0o644
                    
                    tar.addfile(tarinfo, BytesIO(content_bytes))
            
            tar_stream.seek(0)
            container.put_archive(dest_path, tar_stream.read())
            self.log(f"Injected {len(files)} files into {dest_path}")

        # Inject relative files to /work
        inject_tar(relative_files, '/work')
        
        # Inject absolute files to / (root)
        inject_tar(absolute_files, '/')

    def add_pre_script(self, container: Any):
        """Inject pre_script as .pre_script.sh file into container"""
        if not self.pre_script:
            return
        from io import BytesIO
        self.log("Injecting pre-script as .pre_script.sh")
        
        # Create tar archive with the pre-script file
        tar_stream = BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            content_bytes = self.pre_script.encode('utf-8')
            tarinfo = tarfile.TarInfo(name='.pre_script.sh')
            tarinfo.size = len(content_bytes)
            tarinfo.mode = 0o755  # Executable
            tar.addfile(tarinfo, BytesIO(content_bytes))
        
        tar_stream.seek(0)
        tar_data = tar_stream.read()
        container.put_archive('/work', tar_data)

    def _wrap_command_with_pre_script(self, base_command: List[str]) -> List[str]:
        """
        Wrap a command with pre-script execution if pre_script exists.
        
        Flow: ./.pre_script.sh && chmod -x .pre_script.sh && <base_command>
        
        Args:
            base_command: The original command as a list (e.g., ["python", "-c", "code"])
            
        Returns:
            Wrapped command if pre_script exists, otherwise returns base_command unchanged.
        """
        if not self.pre_script:
            return base_command
        
        # Convert base command to shell string
        # Handle both simple commands and commands with complex arguments
        if len(base_command) == 1:
            base_cmd_str = base_command[0]
        elif base_command[0] in ["python", "python3", "Rscript", "node", "java"]:
            # For interpreter commands, properly escape the last argument
            if len(base_command) >= 3 and base_command[1] in ["-c", "-e"]:
                escaped_arg = base_command[2].replace("'", "'\"'\"'")
                base_cmd_str = f"{base_command[0]} {base_command[1]} '{escaped_arg}'"
            else:
                base_cmd_str = " ".join(base_command)
        else:
            base_cmd_str = " ".join(base_command)
        
        shell_command = f"./.pre_script.sh && chmod -x .pre_script.sh && {base_cmd_str}"
        self.log(f"Wrapping command with pre-script")
        return ["sh", "-c", shell_command]

    @classmethod
    @abc.abstractmethod
    def is_executable(cls, file_name: Optional[str] = None, extension: Optional[str] = None, code: Optional[str] = None) -> bool:
        """Check if the file is executable based on its extension"""
        pass
    
    @classmethod
    def _get_all_subclasses(cls) -> List["Executor"]:
        """Recursively get all subclasses (including grandchildren, etc.)"""
        all_subclasses = []
        for subclass in cls.__subclasses__():
            all_subclasses.append(subclass)
            all_subclasses.extend(subclass._get_all_subclasses())
        return all_subclasses
    
    @classmethod
    def factory(cls, file: File, image_name: Optional[str] = None) -> Optional['Executor']:
        """
        Factory method to get appropriate Executor subclass.
        
        Searches all subclasses recursively (including grandchildren like
        RNotebookExecutor and JavaNotebookExecutor).
        """
        for subclass in cls._get_all_subclasses():
            logger.info(f"Checking if {file.name} is executable by {subclass}")
            try:
                result = subclass.is_executable(file_name=file.name, extension=file.extension, code=file.data)
                if result:
                    return subclass(file, image_name=image_name)
            except:
                # Skip subclasses that can't be instantiated or have broken is_executable
                logger.exception("Failed to instantiate subclass")
                continue
        return None
    
    
    






class NotebookExecutor(Executor):
    """
    Base class for notebook executors.
    
    Subclasses should define:
    - LANGUAGE: str - Language name (e.g., 'python', 'r', 'java')
    - TEMPLATE: str - Template filename
    - DOCKER_IMAGE: str - Docker image to use
    - EXECUTABLE_EXTENSIONS: List[str] - File extensions this executor handles
    - EXECUTION_COMMAND: List[str] - Command prefix (e.g., ['python', '-c'] or ['Rscript', '-e'])
    """
    
    LANGUAGE: str = None
    TEMPLATE: str = None
    DOCKER_IMAGE: str = None
    EXECUTABLE_EXTENSIONS: List[str] = []
    EXECUTION_COMMAND: List[str] = []  # e.g., ['python', '-c'] or ['Rscript', '-e']

    @classmethod
    def get_kernel_name(cls, code: str) -> str:
        """
        Get the kernel name from the notebook code
        """
        import nbformat
        
        nb = nbformat.reads(code, as_version=4)
        kernel_name = nb['metadata']['kernelspec']['name']
        return kernel_name 
    

    @classmethod
    def prepare_notebook(cls, nb: nbformat.NotebookNode, format: str = "json") -> Union[List[dict], str]:
        """
        Returns an array of cells for execution in notebook
        
        format: "json" or "base64"
        """
        cells_data = []
        for idx, cell in enumerate(nb.cells):
            if cell.cell_type == "markdown":
                cells_data.append({
                    "idx": idx,
                    "type": "markdown",
                    "source": cell.source
                })
            elif cell.cell_type == "code":
                cells_data.append({
                    "idx": idx,
                    "type": "code",
                    "source": cell.source
                })

        if format == "json":
            return cells_data
        elif format == "base64":
            return base64.b64encode(json.dumps(cells_data).encode('utf-8')).decode('ascii')
        else:
            raise ValueError("Invalid format")
            
    @classmethod
    def extract_json_result(cls, stdout: str, stderr: str = "") -> ExecutionResult:
        """
        Templates are expected to return a result inside <<<RESULTS_START>>> and <<<RESULTS_END>>> as output from the container.
        """
        
        # check if the result is inside <<<RESULTS_START>>> and <<<RESULTS_END>>>
        if "<<<RESULTS_START>>>" not in stdout or "<<<RESULTS_END>>>" not in stdout:
            # Use the tail of stderr to see the most recent error/traceback
            stderr_preview = stderr[-1000:] if len(stderr) > 1000 else stderr
            return ExecutionResult.error(f"Failed to extract results: missing markers. Stdout preview: {stdout[:200]} Stderr tail: {stderr_preview}")

        try:
            results_stdout = stdout.split("<<<RESULTS_START>>>")[1].split("<<<RESULTS_END>>>")[0].strip()
            results_json = json.loads(results_stdout)
            
            # Create ExecutionResult from the parsed JSON
            return ExecutionResult(
                success=results_json.get("success", False),
                stdout=results_json.get("stdout", ""),
                stderr=results_json.get("stderr", "") or stderr,
                err=results_json.get("error"),
                execution_time=results_json.get("execution_time", 0.0),
                output_data=results_json.get("output_data", {})
            )
            
        except json.JSONDecodeError:
            return ExecutionResult.error("Failed to parse results JSON")
        except Exception as e:
            return ExecutionResult.error(f"Error processing results: {str(e)}")

    def _detect_imports(self, nb: nbformat.NotebookNode) -> List[str]:
        """
        Detect imported packages from notebook cells.
        
        Override in subclasses to detect language-specific imports.
        Default implementation returns empty list (no packages to install).
        """
        return []
    
    def _get_execution_command(self, template: str) -> List[str]:
        """
        Get the command to execute the template.
        
        Override in subclasses if needed.
        Default uses EXECUTION_COMMAND class attribute + template as argument.
        """
        return self.EXECUTION_COMMAND + [template]

    def execute(self) -> ExecutionResult:
        """
        Execute notebook in Docker container.
        
        This is the main execution flow shared by all notebook executors.
        """
        self.log(f"[{self.image}] [{self.file.name}] [{self.LANGUAGE}] Starting execution")
        self.log("Reading notebook data")
        if not self.file.data:
            return ExecutionResult.error("No notebook data found")
        
        nb = nbformat.reads(self.file.data, as_version=4)
        client = self._get_docker_client()
        if not client:
            return ExecutionResult.error("Docker is not available")
        
        image_name = self.image
        if not self._ensure_image(image_name):
            return ExecutionResult.error("Docker image is not available")
        timeout = self.DEFAULT_TIMEOUT
        
        temp_staging_dir = self._create_staging_directory()
        volumes = self._get_volume_mounts(temp_staging_dir)
        docker_env = self._get_docker_environment()
        
        # Prepare notebook cells data
        packages_to_install = self._detect_imports(nb)
        cells_b64 = self.prepare_notebook(nb, format="base64")
        
        template = self._get_code_template(cells_b64, packages_to_install)
        if not template:
            return ExecutionResult.error("Failed to get code template")

        needs_network = len(packages_to_install) > 0
        
        base_command = self._get_execution_command(template)
        command = self._wrap_command_with_pre_script(base_command)
        
        container = self.get_container(
            image_name=self.image,
            command=command,
            env=docker_env,
            volumes=volumes,
            needs_network=needs_network,
        )
        if not container:
            return ExecutionResult.error("Failed to create Docker container")
        
        self.add_additional_files(container)
        self.add_pre_script(container)  # Inject pre-script file if exists
        
        try:
            container.start()
            self.log("Container started, waiting for execution to complete")
            adjusted_timeout = timeout + (30 * len(packages_to_install))
            container.wait(timeout=adjusted_timeout)
            
            # Get output with proper error handling
            self.log(f"Fetching container logs...")
            try:
                container.reload()
                self.log(f"Container state: {container.status}")
            except Exception as e:
                self.log(f"Could not reload container: {e}")

            stdout = ""
            stderr = ""
            
            try:
                # Fetch stdout and stderr separately because demux=True is not supported 
                # and attach() can be flaky for exited containers.
                stdout_bytes = container.logs(stdout=True, stderr=False, timestamps=False, stream=False)
                stderr_bytes = container.logs(stdout=False, stderr=True, timestamps=False, stream=False)
                
                self.log(f"Docker logs API calls completed")
                
                stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

                self.log(f"Got stdout ({len(stdout)} bytes) and stderr ({len(stderr)} bytes)")
                
            except Exception as e:
                self.log(f"Failed to get container logs: {e}")
                try:
                    result_status = container.wait()
                except:
                    pass
            
            # Parse results from output
            self.log(f"Parsing execution results from stdout...")
            
            execution_result = self.extract_json_result(stdout, stderr)
            
            # Templates now output proper nbformat v4 format with cell_type
            # Just validate we got cells and return
            if execution_result.output_data and "cells" in execution_result.output_data:
                executed_cells = execution_result.output_data["cells"]
                self.log(f"Successfully parsed {len(executed_cells)} cells")
                execution_result.system_logs = self.executor_logs
                return execution_result
                
            elif execution_result.err:
                execution_result.system_logs = self.executor_logs
                return execution_result
            else:
                return ExecutionResult.error(f"Execution failed to produce valid results. Stdout preview: {stdout[:200]}")

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




