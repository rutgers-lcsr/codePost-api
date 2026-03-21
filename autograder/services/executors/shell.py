# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Shell session helpers for environment debugging.

Provides a lightweight ShellExecutor and helpers to build shell contexts and
start shell containers that expose an attached socket.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, cast

from django.utils import timezone

from autograder.services.executors import get_executor_class
from autograder.services.executors.base import ExecutionResult, Executor, FileLike
from core.models import Environment, File


class _ShellFile:
    """Minimal file-like object for building shell session context."""

    def __init__(self, assignment):
        self.id = -1
        self.name = "shell"
        self.extension = ".sh"
        self.data = ""
        self.path = None
        self._assignment = assignment

    def get_file_info(self):
        return None, self._assignment, self._assignment.course


class ShellExecutor(Executor):
    """Lightweight executor for shell sessions (no code execution)."""

    LANGUAGE = "shell"
    EXECUTABLE_EXTENSIONS = []
    TEMPLATE = ""
    DOCKER_IMAGE = "bash:latest"

    def _detect_imports(self, code: str):
        return []

    def execute(self) -> ExecutionResult:
        return ExecutionResult.error("ShellExecutor does not execute code")

    @classmethod
    def is_executable(cls, file_name=None, extension=None, code=None) -> bool:
        return False

    @classmethod
    def open_shell_session(
        cls,
        env: Environment,
        include_datasets: bool,
        include_assignment_files: bool,
        timeout_seconds: int,
        labels: Optional[Dict[str, str]] = None,
        tmpfs_size: str = "size=512m,mode=1777",
    ) -> Tuple[ShellExecutor, Dict[str, Dict[str, str]], Dict[str, str], str, Any, Any]:
        client = Executor._get_docker_client()
        if not client:
            raise RuntimeError("Docker is not available")

        if not Executor._ensure_image(env.image_name):
            raise RuntimeError("Docker image is not available")

        executor, volumes, docker_env, temp_staging_dir = build_shell_context(
            env=env,
            include_datasets=include_datasets,
            include_assignment_files=include_assignment_files,
        )

        default_labels = {
            "codepost.type": "shell_session",
            "codepost.staging_dir": temp_staging_dir or "",
            "codepost.created_at": timezone.now().isoformat(),
            "codepost.timeout_seconds": str(timeout_seconds),
            "codepost.env_id": str(env.id),
        }
        merged_labels = {**default_labels, **(labels or {})}

        container = client.containers.run(
            image=env.image_name,
            command=["sh", "-c", "bash || sh -i"],
            volumes=volumes,
            working_dir="/work",
            network_disabled=not env.allowNetworkAccess,
            mem_limit=Executor.MAX_MEMORY,
            mem_swappiness=0,
            memswap_limit=Executor.MAX_MEMORY_SWAP,
            cpu_quota=Executor.CPU_QUOTA,
            cpu_period=Executor.CPU_PERIOD,
            pids_limit=Executor.MAX_PIDS,
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
            tmpfs={"/tmp": tmpfs_size},
            environment=docker_env,
            detach=True,
            tty=True,
            stdin_open=True,
            labels=merged_labels,
        )
        executor.add_additional_files(container)
        executor.add_pre_script(container)

        sock = container.attach_socket(params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1})
        sock._sock.setblocking(True)  # type: ignore[attr-defined]  # Docker socket internal

        return executor, volumes, docker_env, temp_staging_dir, container, sock


def open_shell_session(
    env: Environment,
    include_datasets: bool,
    include_assignment_files: bool,
    timeout_seconds: int,
    labels: Optional[Dict[str, str]] = None,
    tmpfs_size: str = "size=512m,mode=1777",
) -> Tuple[ShellExecutor, Dict[str, Dict[str, str]], Dict[str, str], str, Any, Any]:
    """
    Start a shell session container and return (executor, volumes, docker_env, staging_dir, container, socket).
    """
    return ShellExecutor.open_shell_session(
        env=env,
        include_datasets=include_datasets,
        include_assignment_files=include_assignment_files,
        timeout_seconds=timeout_seconds,
        labels=labels,
        tmpfs_size=tmpfs_size,
    )


def build_shell_context(
    env: Environment,
    include_datasets: bool,
    include_assignment_files: bool,
) -> Tuple[ShellExecutor, Dict[str, Dict[str, str]], Dict[str, str], str]:
    """
    Build executor context for a shell session.
    Returns (executor, volumes, docker_env, temp_staging_dir).
    """
    assignment = env.assignment
    datasets = []
    if include_datasets and assignment:
        datasets = list(assignment.dataSets.filter(is_active=True))

    shell_file = _ShellFile(assignment)
    executor = ShellExecutor(cast(FileLike, shell_file), datasets=datasets, image_name=env.image_name)

    # Use language executor to inherit cache volumes
    executor_cls = get_executor_class(env.language)
    if executor_cls and hasattr(executor_cls, "INIT_DOCKER_VOLUME"):
        executor.INIT_DOCKER_VOLUME = executor_cls.INIT_DOCKER_VOLUME.copy()

    # Optionally remove assignment files
    if not include_assignment_files:
        executor.additional_files = {}

    temp_staging_dir = executor._create_staging_directory() if datasets else ""
    volumes = executor._get_volume_mounts(temp_staging_dir if datasets else "")
    docker_env = executor._get_docker_environment()

    # Merge environment vars configured for this environment
    if env.env_vars:
        docker_env.update(env.env_vars)

    return executor, volumes, docker_env, temp_staging_dir
