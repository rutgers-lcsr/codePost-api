from celery import shared_task
from core.models import File, User, CachedExecutionResult
from autograder.services.executors import Executor
import logging

logger = logging.getLogger(__name__)

@shared_task(time_limit=300, soft_time_limit=250)  # Set time limits for the task
def run_file_task(file_id: int, user_id: int, timeout: int = 30, force_execute: bool = False, test_code: str = None, example_code: str = None, code_override: str = None):
    try:
        file_obj = File.objects.get(pk=file_id)
        user = User.objects.get(pk=user_id)
        
        # Check cache if not forced
        if not force_execute:
            cached = CachedExecutionResult.get_cached_result(file_obj)
            if cached:
                return cached.get_cached_formated_response(file_obj)

        executor = Executor.factory(file_obj, content_override=code_override, test_code=test_code, example_code=example_code)
        if not executor:
            return {"error": f"No executor found for file: {file_obj.name}"}
        
        # Execute (synchronous within the task)
        # Executor.execute() doesn't take timeout arg? 
        # Checking executor.py again... 
        # default timeout is class constant. 
        # Some implementations might use it. 
        # The base class execute signature is execute(self).
        # We can set DEFAULT_TIMEOUT? Or pass it if supported?
        # Looking at executor.py, run_container usually uses self.DEFAULT_TIMEOUT.
        # We might need to monkeypatch or update Executor to accept timeout.
        # But for now I'll stick to default call.
        
        result = executor.execute()
        
        # Save to cache
        result.save_cache(file_obj, user)
        
        return {
            **result.to_dict(),
            "file_id": file_obj.id,
            "file_name": file_obj.name,
            "cached": False
        }
    except Exception as e:
        logger.error(f"Task failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}

@shared_task(time_limit=600, soft_time_limit=550)  # Set time limits for the task
def run_test_task(submission_id: int, test_id: int = None, user_id: int = None, file_overrides: dict = None):
    try:
        from autograder.services.TestService import TestService
        
        if test_id:
            # Run single test
            result = TestService.run_test(test_id, submission_id, user_id=user_id, file_overrides=file_overrides)
            success = bool(result.get('success', False))
            return {
                "success": success,
                "result": result,
                "error": result.get("error") if not success else None,
            }
        else:
            # Run all tests (suite)
            results = TestService.run_suite(submission_id, user_id=user_id, file_overrides=file_overrides)
            success = all(r.get("success", True) for r in results)
            return {
                "success": success,
                "result": results,
                "error": None if success else "One or more tests failed",
            }
    except Exception as e:
        logger.error(f"Test Execution Task failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}
