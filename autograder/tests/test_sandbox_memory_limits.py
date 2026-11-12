# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Sandbox memory budget and OOM-kill reporting.

/tmp inside a sandbox is a tmpfs, and tmpfs pages are charged to the
container's memory cgroup. Install runs (needs_network) stage pip/npm
downloads and builds there, so their tmpfs must fit inside mem_limit or the
kernel kills the student's interpreter once /tmp fills up. That kill used to
surface as "missing markers" or a timeout; it must now be reported as a
memory-limit error so staff and the stats dashboard can see what happened.
"""
import re
from unittest import mock

import nbformat
from django.test import SimpleTestCase

from autograder.services.error_classifier import classify_error
from autograder.services.executors.base import Executor
from autograder.services.executors.cpp import CPPExecutor
from autograder.services.executors.java import JavaExecutor
from autograder.services.executors.mock_file import MockFile
from autograder.services.executors.node import NodeExecutor
from autograder.services.executors.php import PHPExecutor
from autograder.services.executors.python import PythonExecutor, PythonNotebookExecutor
from autograder.services.executors.r import RExecutor
from autograder.services.executors.ruby import RubyExecutor

_UNITS = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}


def _to_bytes(size: str) -> int:
    """'1g' / '512m' / 'size=2g,mode=1777' -> bytes."""
    match = re.search(r"(\d+)([kmg])", size.lower())
    assert match, size
    return int(match.group(1)) * _UNITS[match.group(2)]


def _mock_file(data: str, name: str, extension: str) -> MockFile:
    mf = MockFile(data=data, name=name, extension=extension)
    mf.get_course = lambda: None  # type: ignore[attr-defined]
    return mf


def _notebook_file() -> MockFile:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "language": "python", "display_name": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    nb.cells.append(nbformat.v4.new_code_cell("x = 1\n"))
    return _mock_file(nbformat.writes(nb), "notebook.ipynb", ".ipynb")


def _fake_container(status_code: int, oom_killed: bool) -> mock.Mock:
    container = mock.Mock()
    container.wait.return_value = {"StatusCode": status_code}
    container.logs.return_value = b""
    container.status = "exited"
    container.attrs = {"State": {"OOMKilled": oom_killed, "ExitCode": status_code}}
    return container


def _execute(executor: Executor, container: mock.Mock):
    client = mock.Mock()
    client.containers.create.return_value = container
    with mock.patch.object(Executor, "_get_docker_client", return_value=client), \
            mock.patch.object(Executor, "_ensure_image", return_value=True):
        return executor.execute(), client.containers.create.call_args.kwargs


class SandboxLimitTests(SimpleTestCase):

    def test_tmpfs_always_fits_inside_the_memory_limit(self):
        for needs_network in (False, True):
            limits = Executor.sandbox_limits(needs_network)
            mem = _to_bytes(limits["mem_limit"])
            tmpfs = _to_bytes(limits["tmpfs"]["/tmp"])
            self.assertLess(tmpfs, mem, msg=f"needs_network={needs_network}: tmpfs {tmpfs} >= mem_limit {mem}")
            # Room for the program itself, not just the scratch space.
            self.assertGreaterEqual(mem - tmpfs, _UNITS["m"] * 512, msg=f"needs_network={needs_network}")
            # No swap: memswap_limit equals mem_limit.
            self.assertEqual(limits["memswap_limit"], limits["mem_limit"])

    def test_install_runs_get_the_bigger_budget(self):
        plain = Executor.sandbox_limits(False)
        install = Executor.sandbox_limits(True)
        self.assertEqual(plain["mem_limit"], "1g")
        self.assertEqual(plain["tmpfs"], {"/tmp": "size=512m,mode=1777"})
        self.assertEqual(install["mem_limit"], "3g")
        self.assertEqual(install["tmpfs"], {"/tmp": "size=2g,mode=1777"})

    def test_get_container_applies_the_limits(self):
        for needs_network in (False, True):
            client = mock.Mock()
            executor = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"))
            with mock.patch.object(Executor, "_get_docker_client", return_value=client):
                executor.get_container("img", ["python", "x.py"], {}, {}, needs_network=needs_network)
            kwargs = client.containers.create.call_args.kwargs
            expected = Executor.sandbox_limits(needs_network)
            self.assertEqual(kwargs["mem_limit"], expected["mem_limit"])
            self.assertEqual(kwargs["memswap_limit"], expected["memswap_limit"])
            self.assertEqual(kwargs["tmpfs"], expected["tmpfs"])
            self.assertEqual(kwargs["network_disabled"], not needs_network)

    def test_python_file_run_with_packages_uses_install_budget(self):
        executor = PythonExecutor(_mock_file("import requests\n", "student.py", ".py"))
        with mock.patch.object(PythonExecutor, "_detect_imports", return_value=["requests"]):
            _, kwargs = _execute(executor, _fake_container(0, oom_killed=False))
        self.assertEqual(kwargs["mem_limit"], "3g")
        self.assertEqual(kwargs["tmpfs"], {"/tmp": "size=2g,mode=1777"})
        self.assertFalse(kwargs["network_disabled"])

    def test_shell_session_uses_the_same_limits(self):
        from autograder.services.executors import shell as shell_module
        env = mock.Mock(id=7, image_name="img", allowNetworkAccess=True)
        for needs_network in (False, True):
            client = mock.Mock()
            with mock.patch.object(Executor, "_get_docker_client", return_value=client), \
                    mock.patch.object(Executor, "_ensure_image", return_value=True), \
                    mock.patch.object(shell_module, "build_shell_context", return_value=(mock.Mock(pre_script=""), {}, {}, "")):
                shell_module.ShellExecutor.open_shell_session(env, False, False, 60, needs_network=needs_network)
            kwargs = client.containers.create.call_args.kwargs
            expected = Executor.sandbox_limits(needs_network)
            self.assertEqual(kwargs["mem_limit"], expected["mem_limit"])
            self.assertEqual(kwargs["memswap_limit"], expected["memswap_limit"])
            self.assertEqual(kwargs["tmpfs"], expected["tmpfs"])


class OomKillReportingTests(SimpleTestCase):

    def test_python_file_run_reports_memory_limit(self):
        executor = PythonExecutor(_mock_file("x = [0] * 10**9\n", "student.py", ".py"))
        result, _ = _execute(executor, _fake_container(137, oom_killed=True))
        self.assertFalse(result.success)
        self.assertEqual(result.err, "Execution exceeded the sandbox memory limit (1g) and was stopped.")
        self.assertEqual(classify_error(result.err)[0], "memory_limit")

    def test_install_run_names_the_bigger_limit(self):
        executor = PythonExecutor(_mock_file("import requests\n", "student.py", ".py"))
        with mock.patch.object(PythonExecutor, "_detect_imports", return_value=["requests"]):
            result, _ = _execute(executor, _fake_container(137, oom_killed=True))
        self.assertEqual(result.err, "Execution exceeded the sandbox memory limit (3g) and was stopped.")

    def test_oom_kill_overrides_a_clean_exit_code(self):
        # pip (a subprocess of the runner) was killed but the runner itself exited 0.
        executor = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"))
        result, _ = _execute(executor, _fake_container(0, oom_killed=True))
        self.assertFalse(result.success)
        self.assertIn("sandbox memory limit", result.err or "")

    def test_ordinary_failure_keeps_the_exit_code_message(self):
        executor = PythonExecutor(_mock_file("raise SystemExit(3)\n", "student.py", ".py"))
        result, _ = _execute(executor, _fake_container(3, oom_killed=False))
        self.assertFalse(result.success)
        self.assertEqual(result.err, "Non-zero exit code: 3")
        self.assertNotEqual(classify_error(result.err)[0], "memory_limit")

    def test_unreadable_container_state_does_not_break_the_run(self):
        container = _fake_container(0, oom_killed=False)
        container.reload.side_effect = RuntimeError("daemon went away")
        executor = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"))
        result, _ = _execute(executor, container)
        self.assertTrue(result.success)

    def test_notebook_run_reports_memory_limit(self):
        executor = PythonNotebookExecutor(_notebook_file())
        result, _ = _execute(executor, _fake_container(137, oom_killed=True))
        self.assertFalse(result.success)
        self.assertIn("sandbox memory limit (1g)", result.err or "")

    def test_every_file_executor_reports_memory_limit(self):
        cases = [
            RExecutor(_mock_file("x <- 1\n", "student.R", ".R")),
            NodeExecutor(_mock_file("const x = 1;\n", "student.js", ".js")),
            PHPExecutor(_mock_file("<?php $x = 1;\n", "student.php", ".php")),
            RubyExecutor(_mock_file("x = 1\n", "student.rb", ".rb")),
            JavaExecutor(_mock_file("public class Main { public static void main(String[] a) {} }\n", "Main.java", ".java")),
            CPPExecutor(_mock_file("int main() { return 0; }\n", "main.cpp", ".cpp")),
        ]
        for executor in cases:
            with self.subTest(executor=type(executor).__name__):
                result, _ = _execute(executor, _fake_container(137, oom_killed=True))
                self.assertFalse(result.success)
                self.assertIn("sandbox memory limit", result.err or "")


class ClassifierTests(SimpleTestCase):

    def test_memory_signals(self):
        for text in (
            "Execution exceeded the sandbox memory limit (3g) and was stopped.",
            "Traceback (most recent call last):\n  File x\nMemoryError",
            "fatal error: out of memory",
            "Memory cgroup out of memory: oom-kill task python",
        ):
            self.assertEqual(classify_error(text)[0], "memory_limit", msg=text)

    def test_existing_categories_unchanged(self):
        self.assertEqual(classify_error("Execution timeout or incomplete")[0], "timeout")
        self.assertEqual(classify_error("ModuleNotFoundError: No module named 'x'")[0], "missing_dependency")
        self.assertEqual(classify_error("Failed to extract results: missing markers")[0], "marker_extraction")
        self.assertEqual(classify_error("ZeroDivisionError: division by zero")[0], "runtime_error")
        self.assertEqual(classify_error("Room for improvement")[0], "runtime_error")
