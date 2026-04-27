# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from celery import shared_task
from core.models import File, User, CachedExecutionResult
from autograder.services.executors import Executor
from typing import Optional
import logging

logger = logging.getLogger(__name__)

@shared_task(time_limit=300, soft_time_limit=250)  # Set time limits for the task
def run_file_task(file_id: int, user_id: int, timeout: int = 30, force_execute: bool = False, test_code: Optional[str] = None, example_code: Optional[str] = None, code_override: Optional[str] = None):
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
            return {"error": f"No executor found for file: {file_obj.name}, unsupported file type or language. If you'd like to request support for this file type, please contact codePost.", "success": False}
        
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
def run_test_task(submission_id: int, test_id: Optional[int] = None, user_id: Optional[int] = None, file_overrides: Optional[dict] = None):
    try:
        from autograder.services.TestService import TestService
        
        if test_id:
            # Route single test through run_suite for consistent crash handling
            results = TestService.run_suite(submission_id, test_case_ids=[test_id], user_id=str(user_id) if user_id else None, file_overrides=file_overrides)
            success = all(r.get("success", True) for r in results)
            return {
                "success": success,
                "result": results[0] if len(results) == 1 else results,
                "error": None if success else "Test failed",
            }
        else:
            # Run all tests (suite)
            results = TestService.run_suite(submission_id, user_id=str(user_id) if user_id else None, file_overrides=file_overrides)
            success = all(r.get("success", True) for r in results)
            return {
                "success": success,
                "result": results,
                "error": None if success else "One or more tests failed",
            }
    except Exception as e:
        logger.error(f"Test Execution Task failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}
