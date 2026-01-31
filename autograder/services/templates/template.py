# The following is a template for running code which is meant to be used by the autograder,
# This will run inline inside a docker container.

# START OF PACKAGE INSTALLATION TEMPLATE
import subprocess
import sys
import os
import time
import site
import json
import inspect
import traceback
import io
import contextlib
import base64
import typing
from typing import List, Dict, Any, Optional, Callable, Union
import signal

# Set environment for pip
os.environ['PIP_ROOT_USER_ACTION'] = 'ignore'
if 'PIP_CACHE_DIR' not in os.environ:
    os.environ['PIP_CACHE_DIR'] = '/tmp/pip-cache'
os.environ['MPLBACKEND'] = 'Agg'  # For matplotlib headless


def template_log(message: str, level:str) -> None:
    # Write to stderr with a prefix/format that can be tracked if needed, 
    print(f"[{level}] {message}", file=sys.stderr)

# Packages to install
packages_to_install = []

# Debug: Check if pip cache is mounted
pip_cache_path = os.environ.get('PIP_CACHE_DIR', '/tmp/pip-cache')
if os.path.exists(pip_cache_path):
    try:
        cache_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, dirnames, filenames in os.walk(pip_cache_path)
                        for filename in filenames)
        # template_log(f"Current cache size: {cache_size / 1024 / 1024:.2f} MB", "DEBUG")
    except Exception as e:
        template_log(f"Could not calculate cache size: {str(e)}", "DEBUG")

# Check which packages are already installed
import importlib.util
needs_install = []
for package in packages_to_install:
    try:
        __import__(package)
    except ImportError:
        needs_install.append(package)

if needs_install:
    template_log(f"Installing {len(needs_install)} package(s): {', '.join(needs_install)}", "INFO")
    
    # Install packages with progress feedback
    failed_packages = []
    for i, package in enumerate(needs_install, 1):
        template_log(f"[{i}/{len(needs_install)}] Installing {package}...", "INFO")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--user', package],
                capture_output=True,
                text=True
            )
            elapsed = time.time() - start_time
            
            if result.returncode == 0:
                template_log(f"[{i}/{len(needs_install)}] ✓ {package} installed ({elapsed:.1f}s)", "INFO")
                # Log to stderr so Converger picks it up
                print(f"CODEPOST_AUTO_INSTALL_SUCCESS: {package}", file=sys.stderr)
            else:
                template_log(f"Pip output: {result.stdout}\n{result.stderr}", "DEBUG")
                raise subprocess.CalledProcessError(result.returncode, result.args)
        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            template_log(f"[{i}/{len(needs_install)}] ✗ {package} failed ({elapsed:.1f}s)", "ERROR")
            failed_packages.append(package)
        
        sys.stderr.flush()

    # Refresh sys.path
    try:
        from importlib import reload
        reload(site)
        if site.getusersitepackages() not in sys.path:
             site.addsitedir(site.getusersitepackages())
    except Exception as e:
        template_log(f"Failed to refresh sys.path: {e}", "WARNING")

sys.stderr.flush()
print("", file=sys.stderr)

# END OF PACKAGE INSTALLATION TEMPLATE

# ==========================================
# TEST FRAMEWORK IMPLEMENTATION
# ==========================================

# Global storage for captured plots
_CAPTURED_PLOTS: List[str] = []

def _codepost_plot_hook(*args, **kwargs):
    """Hook to capture matplotlib plots"""
    try:
        import matplotlib.pyplot as plt
        if plt.get_fignums():
            fig = plt.gcf()
            buf = io.BytesIO()
            fig.savefig(buf, format='png')
            buf.seek(0)
            img_data = base64.b64encode(buf.read()).decode('utf-8')
            _CAPTURED_PLOTS.append(img_data)
            
            # Print specifically for the frontend to see, if legacy mode is needed
            # But primarily we store it for the Test object to access
            print(f"\n<<<CODEPOST_PLOT:{img_data}>>>\n") 
            plt.close(fig)
    except Exception as e:
        print(f"Error capturing plot: {e}", file=sys.stderr)

# Setup Plot Capture
try:
    import matplotlib
    import matplotlib.pyplot as plt
    
    # Monkeypatch
    plt.show = _codepost_plot_hook
except ImportError:
    pass

class TestResult:
    def __init__(self, name: str, max_score: float = 1.0, description: Optional[str] = None):
        self.name = name
        self.max_score = max_score
        self.description = description
        self.score = 0.0
        self.passed = False
        self.error: Optional[str] = None
        self.message: Optional[str] = None
        self.output: str = ""
        self.status: str = "failed" # passed, failed, error

    def to_json(self) -> str:
        data = {
            "name": self.name,
            "max_score": self.max_score,
            "description": self.description,
            "score": self.score,
            "passed": self.passed,
            "error": self.error,
            "message": self.message,
            "output": self.output,
            "status": self.status
        }
        return f"<<<TEST_RESULT_JSON_START>>>{json.dumps(data)}<<<TEST_RESULT_JSON_END>>>"

class TestCase:
    """
    Base class for defining tests.
    Users can use the @test decorator or manually create instances.
    """
    def __init__(self, func: Callable, name: Optional[str] = None, points: float = 1.0, description: Optional[str] = None, timeout: Optional[int] = None):
        self.func = func
        self.name = name or func.__name__
        self.points = points
        self.description = description
        
        # Determine timeout
        # 1. Check for global override (from DB/UI)
        global_timeouts = globals().get('CODEPOST_TEST_TIMEOUTS', {})
        
        if self.name in global_timeouts:
            self.timeout = global_timeouts[self.name]
        elif timeout is not None:
             self.timeout = timeout
        else:
             self.timeout = 30 # Default 30s

        
    def run(self) -> TestResult:
        result = TestResult(self.name, self.points, self.description)
        
        # Capture stdout/stderr during test execution
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                # Execute the test function
                # The test function should raise AssertionError or Exception on failure
                # It can return a number for partial credit
                
                # Setup timeout handler
                def handler(signum, frame):
                    raise TimeoutError(f"Test timed out after {self.timeout} seconds")
                
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(self.timeout)
                
                try:
                    return_value = self.func()
                finally:
                    signal.alarm(0)

            
            # Check if return value is a number (partial credit)
            if isinstance(return_value, (int, float)):
                # Clamp score to [0, max_score]
                result.score = max(0, min(return_value, self.points))
                result.passed = result.score == self.points
                result.status = "passed" if result.passed else "partial"
            elif isinstance(return_value, (tuple, list)) and len(return_value) >= 2:
                # Handle [score, message]
                score_val = return_value[0]
                msg_val = str(return_value[1])
                
                if isinstance(score_val, (int, float)):
                    result.score = max(0, min(float(score_val), self.points))
                    result.passed = result.score == self.points
                    result.status = "passed" if result.passed else "partial"
                
                if msg_val:
                    result.message = msg_val
            else:
                # No return value or non-numeric = full credit
                result.passed = True
                result.score = self.points
                result.status = "passed"
            
            result.output = stdout_capture.getvalue()
            
        except AssertionError as e:
            result.passed = False
            result.score = 0
            result.status = "failed"
            result.error = str(e)
            result.output = stdout_capture.getvalue()
            result.output = stdout_capture.getvalue()
        except TimeoutError as e:
            result.passed = False
            result.score = 0
            result.status = "error"
            result.error = str(e)
            result.output = stdout_capture.getvalue()
            result.message = "Test timed out"
        except Exception as e:
            result.passed = False
            result.score = 0
            result.status = "error"
            result.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            result.output = stdout_capture.getvalue()

            
        return result

class TestRunner:
    _instance = None
    
    def __init__(self):
        self.tests: List[TestCase] = []
    
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = TestRunner()
        return cls._instance
    
    def add_test(self, test: TestCase):
        self.tests.append(test)
        
    def run_all(self):
        for test in self.tests:
            result = test.run()
            # Flush result to stderr for the parent process (Executor) to pick up
            print(result.to_json(), file=sys.stderr)
            sys.stderr.flush()

# Public Decorator
def test(name: Optional[str] = None, points: float = 1.0, description: Optional[str] = None, timeout: Optional[int] = None):
    def decorator(func):
        test_case = TestCase(func, name=name, points=points, description=description, timeout=timeout)
        TestRunner.get_instance().add_test(test_case)
        return func
    return decorator


# Helper assertions
def assert_plots_generated(count: int = 1):
    """Assert that a specific number of plots were generated."""
    if len(_CAPTURED_PLOTS) < count:
        raise AssertionError(f"Expected {count} plots, but found {len(_CAPTURED_PLOTS)}")

def get_plots() -> List[str]:
    """Get raw base64 strings of captured plots."""
    return _CAPTURED_PLOTS

# ==========================================
# END TEST FRAMEWORK
# ==========================================

# START OF USER CODE
# The student code will be injected here. 
# We wrap it in a try/except to separate runtime errors from test errors, 
# although often we want the student code to define functions that the tests call.
# If the student code is a script that runs immediately, we let it run.

print("<<<RESULT>>>", file=sys.stderr) # Marker for legacy log separation

try:
    # Inject student code here
    # We use exec() to run the student code in the current global scope
    # This allows the test functions (defined below) to access student functions
    
    student_code = """#{FILLER_CODE}"""
    exec(student_code, globals())
    
except Exception as e:
    # If the student code crashes at top-level, we print the error
    # but we still proceed to run tests (which will likely fail if they depend on defined functions)
    print(f"Student Code Runtime Error:\n{traceback.format_exc()}", file=sys.stderr)

try:
    # Inject instructor tests here
    test_code = """#{TEST_CODE}"""
    if test_code.strip():
        print(f"SCRIPT_DEBUG: {test_code[:500]}", file=sys.stderr)
        exec(test_code, globals())
except Exception as e:
    print(f"Test Script Error:\n{traceback.format_exc()}", file=sys.stderr)


# Run all registered tests
if TestRunner.get_instance().tests:
    print("\nRunning Tests...", file=sys.stdout)
    TestRunner.get_instance().run_all()

