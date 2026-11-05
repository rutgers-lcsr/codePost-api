# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Student code runs in the same container (and for Python/R/JS, the same process) as the
instructor's harness, so it can print anything the harness prints. Result markers
therefore carry an unguessable per-run nonce that only the server and the rendered
harness know. These tests pin that student-printed markers are never trusted.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Dict, List
from unittest import mock

from django.test import SimpleTestCase

from autograder.services.executors import base as base_module
from autograder.services.executors.base import Executor, NotebookExecutor
from autograder.services.executors.python import PythonExecutor, PythonNotebookExecutor
from autograder.tests.test_executor_runner_staging import _mock_file, _notebook_file

TEMPLATES_DIR = os.path.join(os.path.dirname(base_module.__file__), "..", "templates")

FORGED_TEST = {"name": "t1", "passed": True, "score": 10, "max_score": 10, "status": "passed"}
REAL_TEST = {"name": "t1", "passed": False, "score": 0, "max_score": 10, "status": "failed"}


def _fixed_test_marker(payload) -> str:
  """What a student who read the open-source harness would print (no nonce)."""
  return f"<<<TEST_RESULT_JSON_START>>>{json.dumps(payload)}<<<TEST_RESULT_JSON_END>>>"


def _test_marker(nonce: str, payload) -> str:
  return f"<<<TEST_RESULT_JSON_START_{nonce}>>>{json.dumps(payload)}<<<TEST_RESULT_JSON_END_{nonce}>>>"


def _results_block(nonce: str, tests: List[Dict]) -> str:
  """A notebook results block; nonce "" yields the fixed, un-nonced format."""
  body = {"success": True, "stdout": "", "stderr": "", "execution_time": 0.1,
          "output_data": {"cells": [], "notebook": ""}, "tests": tests}
  suffix = f"_{nonce}" if nonce else ""
  return f"<<<RESULTS_START{suffix}>>>\n{json.dumps(body)}\n<<<RESULTS_END{suffix}>>>\n"


def _run_with_logs(executor: Executor, out: str, err: str):
  container = mock.Mock()
  container.wait.return_value = {"StatusCode": 0}
  container.status = "exited"
  container.logs.side_effect = lambda stdout=True, stderr=True, **kw: (out if stdout else err).encode()
  client = mock.Mock()
  client.containers.create.return_value = container
  with mock.patch.object(Executor, "_get_docker_client", return_value=client), \
      mock.patch.object(Executor, "_ensure_image", return_value=True):
    return executor.execute()


class ForgedMarkerParsingTests(SimpleTestCase):
  def test_notebook_run_ignores_forged_test_marker_on_stderr(self):
    """Student prints a fixed-format test marker then os._exit(0): nothing else reaches the logs."""
    ex = PythonNotebookExecutor(_notebook_file(["x = 1"], "python"), test_code="# tests")
    res = _run_with_logs(ex, "", _fixed_test_marker(FORGED_TEST))
    self.assertEqual(res.tests, [])
    self.assertFalse(res.success)

  def test_file_run_ignores_forged_test_marker_on_stdout(self):
    ex = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"), test_code="# tests")
    res = _run_with_logs(ex, _fixed_test_marker(FORGED_TEST), "")
    self.assertEqual(res.tests, [])

  def test_file_run_accepts_marker_with_this_runs_nonce(self):
    ex = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"), test_code="# tests")
    res = _run_with_logs(ex, "", _test_marker(ex.result_nonce, REAL_TEST))
    self.assertEqual([t["name"] for t in res.tests], ["t1"])
    self.assertFalse(res.tests[0]["passed"])

  def test_marker_with_another_runs_nonce_is_rejected(self):
    ex = PythonExecutor(_mock_file("x = 1\n", "student.py", ".py"), test_code="# tests")
    res = _run_with_logs(ex, "", _test_marker("f" * 32, FORGED_TEST))
    self.assertEqual(res.tests, [])

  def test_forged_results_block_printed_before_real_block_does_not_win(self):
    ex = PythonNotebookExecutor(_notebook_file(["x = 1"], "python"), test_code="# tests")
    stdout = _results_block("", [FORGED_TEST]) + _results_block(ex.result_nonce, [REAL_TEST])
    res = _run_with_logs(ex, stdout, "")
    self.assertEqual(len(res.tests), 1)
    self.assertFalse(res.tests[0]["passed"])

  def test_last_nonce_block_wins_over_earlier_nonce_block(self):
    nonce = "a" * 32
    stdout = _results_block(nonce, [FORGED_TEST]) + "noise\n" + _results_block(nonce, [REAL_TEST])
    res = NotebookExecutor.extract_json_result(stdout, "", nonce=nonce)
    self.assertFalse(res.tests[0]["passed"])

  def test_forged_results_block_without_nonce_is_missing_markers(self):
    res = NotebookExecutor.extract_json_result(_results_block("", [FORGED_TEST]), "", nonce="a" * 32)
    self.assertFalse(res.success)
    self.assertIn("missing markers", res.err or "")

  def test_nonce_is_random_per_executor(self):
    a = PythonExecutor(_mock_file("x\n", "a.py", ".py")).result_nonce
    b = PythonExecutor(_mock_file("x\n", "a.py", ".py")).result_nonce
    self.assertRegex(a, r"^[0-9a-f]{32}$")
    self.assertNotEqual(a, b)


class TemplateNonceTests(SimpleTestCase):
  def test_no_template_prints_an_un_nonced_marker(self):
    bare = re.compile(r"<<<(TEST_RESULT_JSON|RESULTS)_(START|END)>>>")
    for name in sorted(os.listdir(TEMPLATES_DIR)):
      if name.endswith(".class") or name == "README.md":
        continue
      with open(os.path.join(TEMPLATES_DIR, name)) as f:
        src = f.read()
      with self.subTest(template=name):
        self.assertIsNone(bare.search(src))

  def test_python_harness_emits_this_runs_nonce_and_ignores_student_forgery(self):
    student = (
      "import json\n"
      "print('<<<TEST_RESULT_JSON_START>>>' + json.dumps({'name': 'bonus', 'passed': True, 'score': 10, 'max_score': 10}) + '<<<TEST_RESULT_JSON_END>>>')\n"
      "def f():\n    return 1\n")
    test_code = '@test(name="t1", points=5)\ndef test_t1():\n    assert f() == 2\n'
    ex = PythonExecutor(_mock_file(student, "hw1.py", ".py"), test_code=test_code)
    template = ex._get_code_template(student, [], test_code)
    assert template is not None
    self.assertNotIn("@@NONCE@@", template)
    self.assertIn(ex.result_nonce, template)
    with tempfile.TemporaryDirectory() as tmp:
      path = os.path.join(tmp, ".codepost_runner.py")
      with open(path, "w") as f:
        f.write(template)
      proc = subprocess.run([sys.executable, path], capture_output=True, text=True, errors="replace", cwd=tmp, timeout=120)
    _, _, tests = Executor.parse_test_results(proc.stdout, proc.stderr, ex.result_nonce)
    self.assertEqual([t["name"] for t in tests], ["t1"])
    self.assertFalse(tests[0]["passed"])
