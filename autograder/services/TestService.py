import logging
import re
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.utils import timezone

from core.models import TestCase, Submission, SubmissionTest, File, CachedExecutionResult
from autograder.services.executors import get_executor_class, ExecutionResult

logger = logging.getLogger(__name__)

class TestService:
    """
    Service to orchestrate test execution using the Modern Framework (Executors).
    Replaces the legacy parse.py -> external autograder flow.
    """

    @staticmethod
    def run_suite(submission_id: int, test_case_ids: Optional[List[int]] = None, user_id: str = None) -> List[Dict[str, Any]]:
        """
        Runs a suite of tests for a submission.
        
        Args:
            submission_id: ID of the submission to run tests for.
            test_case_ids: Optional list of specific test case IDs to run. 
                          If None, runs all active tests for the assignment.
            user_id: ID of the user triggering the run (for tracking/logging).
            
        Returns:
            List of result dictionaries (same format as run_test output).
        """
        results = []
        try:
            submission = Submission.objects.get(id=submission_id)
            assignment = submission.assignment
            
            if test_case_ids:
                test_cases = TestCase.objects.filter(id__in=test_case_ids)
            else:
                # Run all active tests for the assignment's category
                # Assuming tests are linked via TestCategory -> Assignment
                # Legacy logic: assignment.testCategory_set.all().testCase_set.all()
                test_cases = TestCase.objects.filter(testCategory__assignment=assignment)
                
            logger.info(f"Running suite of {test_cases.count()} tests for submission {submission_id}")
            
            # Optimization: 
            # We could group tests by target file to bulk-run or pre-cache the "No Input" run.
            # But run_test() already handles caching fairly well.
            # Let's trust run_test() for now and optimize if needed.
            
            for test_case in test_cases:
                # We reuse run_test logic to ensure consistency
                result = TestService.run_test(test_case.id, submission.id, user_id)
                
                # Append metadata needed for the frontend/legacy response format if necessary
                result['testCaseId'] = test_case.id
                result['testCaseDescription'] = test_case.description
                results.append(result)
                
            return results
            
        except Exception as e:
            logger.exception(f"Error running test suite for submission {submission_id}")
            # Identify if we should throw or return partial results
            # For now, return what we have? Or empty to signal catastrophe?
            return [{"success": False, "error": str(e)}]

    @staticmethod
    def run_test(test_case_id: int, submission_id: int, user_id: str = None) -> Dict[str, Any]:
        """
        Orchestrates the running of a single test case against a submission.
        """
        try:
            test_case = TestCase.objects.get(id=test_case_id)
            submission = Submission.objects.get(id=submission_id)
            
            # 1. Identify Target File
            target_file = TestService._get_target_file(submission, test_case)
            if not target_file:
                return {
                    "success": False,
                    "error": f"No suitable file found for test case targeting '{test_case.fileName}'"
                }

            # 2. Get Execution Result (Cached or Fresh)
            # Hybrid Logic: If test case has input or specific dataset, run ephemeral execution.
            if test_case.input or test_case.dataSet:
                execution_result = TestService._run_ephemeral_execution(target_file, test_case, user_id)
            else:
                execution_result = TestService._get_or_run_execution(target_file, user_id)
            
            # 3. Verify Result
            if test_case.type in ['io', 'io_cli']:
                 verification = TestService.verify_io_test(test_case, execution_result)
            elif test_case.type == 'unit':
                 verification = TestService.verify_unit_test(test_case, execution_result)
            else:
                return {"success": False, "error": f"Unsupported test type: {test_case.type}"}

            # 4. Save SubmissionTest Result
            # We use update_or_create to avoid duplicates for the same run
            submission_test, created = SubmissionTest.objects.update_or_create(
                submission=submission,
                testCase=test_case,
                defaults={
                    "passed": verification['passed'],
                    "logs": verification['logs'],
                    "isError": verification.get('isError', False),
                    # "execution_time": execution_result.execution_time # Pending model update
                }
            )

            return {
                "success": True,
                "passed": submission_test.passed,
                "logs": submission_test.logs,
                "isError": submission_test.isError,
                "cached": execution_result.get('cached', False),
                "output_data": execution_result.get('output_data', {})
            }

        except Exception as e:
            logger.exception(f"Error running test {test_case_id} for submission {submission_id}")
            return {
                "success": False, 
                "error": str(e)
            }

    @staticmethod
    def _get_target_file(submission: Submission, test_case: TestCase) -> Optional[File]:
        """
        Finds the file in the submission that this test case targets.
        """
        files = submission.files.all()
        
        # If explicit fileName is provided, look for it
        if test_case.fileName:
            for f in files:
                if f.name == test_case.fileName:
                    return f
        
        # Heuristic: Find first executable file (based on extension)
        # TODO: Refine this heuristic or enforce explicit selection
        for f in files:
            # Simple check for code files
            if any(f.name.endswith(ext) for ext in ['.py', '.java', '.c', '.cpp', '.js', '.R', '.ipynb']):
                return f
                
        return files.first() if files.exists() else None

    @staticmethod
    def _get_or_run_execution(file: File, user_id: str = None) -> Dict[str, Any]:
        """
        Retrieves cached result or runs the executor.
        Returns a dict resembling ExecutionResult but with a 'cached' flag.
        """
        # Check Cache
        cached = CachedExecutionResult.get_cached_result(file)
        if cached:
            return {
                "success": True, # Cached results imply successful execution, usually
                "stdout": cached.output_data.get('stdout', ''),
                "stderr": cached.output_data.get('stderr', ''),
                "output_data": cached.output_data,
                "execution_time": cached.execution_time_seconds,
                "cached": True
            }

        # Not Cached: Run Executor
        ExecutorClass = get_executor_class(file.name)
        if not ExecutorClass:
             raise ValueError(f"No executor found for file type: {file.name}")
             
        executor = ExecutorClass(file)
        result = executor.execute() # Synchronous execution
        
        # Save to Cache
        # We need the user object if possible, but can be None
        from core.models import User
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                pass
                
        result.save_cache(file, executed_by=user)
        
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
             "output_data": result.output_data,
             "execution_time": result.execution_time,
             "cached": False,
             "error": result.err
        }

    @staticmethod
    def _run_ephemeral_execution(file: File, test_case: TestCase, user_id: str = None) -> Dict[str, Any]:
        """
        Runs an ephemeral execution for a specific test case (with specific input/dataset).
        Does NOT save to the global cache (to avoid polluting it with test-specific runs).
        """
        ExecutorClass = get_executor_class(file.name)
        if not ExecutorClass:
             raise ValueError(f"No executor found for file type: {file.name}")
             
        # Prepare datasets
        datasets = []
        if test_case.dataSet:
             datasets.append(test_case.dataSet)
        
        # So passing [test_case.dataSet] overrides the default "all active".
        # This is desired for specific tests.
        executor = ExecutorClass(
            file, 
            datasets=datasets, 
            input_data=test_case.input,
            target_cell_id= getattr(test_case, 'targetCellId', None)
        )
        result = executor.execute()
        
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output_data": result.output_data,
            "execution_time": result.execution_time,
            "cached": False, 
            "error": result.err
        }

    @staticmethod
    def verify_io_test(test_case: TestCase, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifies I/O test criteria.
        """
        # 1. Output content check
        # For Notebooks, 'stdout' in execution_result relies on the template aggregating it.
        # Verified: notebook_template.py aggregates cells into 'stdout'.
        
        actual_output = execution_result.get('stdout', '')
        
        # Determine strictness
        is_flexible = test_case.isFlexible
        is_regexp = test_case.outputIsRegexp
        expected = test_case.expectedOutput or ""

        passed = False
        logs = actual_output # Default logs is the output
        
        if is_regexp:
            try:
                # Regex search
                if re.search(expected, actual_output, re.MULTILINE | re.DOTALL):
                    passed = True
            except re.error as e:
                return {
                    "passed": False,
                    "logs": f"Invalid Regular Expression in Test Case: {str(e)}",
                    "isError": True
                }
        else:
            # Exact Match (or Flexible)
            clean_actual = actual_output.strip() if is_flexible else actual_output
            clean_expected = expected.strip() if is_flexible else expected
            
            if clean_actual == clean_expected:
                passed = True
                
        # 2. Check Input (Not really 'verify', but we assume input was injected via STDIN if supported)
        # Note: Executors support STDIN injection, but current test_case.input is for that.
        # If we re-run, we need to pass input. But here we are using CACHED results.
        # CRITICAL TODO: If test_case has INPUT, we cannot reuse a generic "no-input" cached run.
        # We must detect if the cached run used the SAME input.
        # For now, we assume no-input or ignore this constraint until we add Input Hashing to Cache.
        
        # 3. Plot Verification
        if test_case.expectPlot:
             # Check for images in output_data
             output_data = execution_result.get('output_data', {})
             # Notebooks put images in 'cells', standard scripts put in 'images' key?
             # Standard executors often put images in output_data['images'] or similar?
             # Let's check: Executor base checks for images?
             # R script template puts it in output.
             # We need a unified way to check "has images".
             
             has_images = False
             
             # Check 'cells' for display_data
             if 'cells' in output_data:
                 for cell in output_data['cells']:
                     for output in cell.get('outputs', []):
                         if output.get('output_type') == 'display_data':
                             has_images = True
                             break
            
             # Check 'images' list (if used by some executors)
             if 'images' in output_data and output_data['images']:
                 has_images = True
                 
             if not has_images:
                 passed = False
                 logs += "\n[Test Error] Expected a plot, but none was generated."


        return {
            "passed": passed,
            "logs": logs,
            "isError": execution_result.get('error') is not None
        }

    @staticmethod
    def verify_unit_test(test_case: TestCase, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verifies Unit Tests (Java, Python unittest, etc).
        Relies on the executor returning success=True (exit code 0) for passing tests.
        """
        passed = execution_result.get('success', False)
        
        # Combine logs
        stdout = execution_result.get('stdout', '')
        stderr = execution_result.get('stderr', '')
        logs = f"{stdout}\n{stderr}".strip()
        
        # Check for error (infrastructure level)
        # However, for unit tests, if 'error' exists it usually means compilation failed or similar.
        # So passed should definitely be False if error exists.
        is_error = execution_result.get('error') is not None
        if is_error:
            passed = False
        
        return {
            "passed": passed,
            "logs": logs,
            "isError": is_error
        }
