# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from celery import shared_task
from core.models import File, User, CachedExecutionResult
from autograder.services.executors import Executor
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)

@shared_task(time_limit=300, soft_time_limit=250)  # Set time limits for the task
def run_file_task(file_id: int, user_id: int, timeout: int = 30, force_execute: bool = False, test_code: Optional[str] = None, example_code: Optional[str] = None, code_override: Optional[str] = None):
    try:
        file_obj = File.objects.get(pk=file_id)
        # CourseFile content lives on shared CourseFileContent — hydrate in-memory so
        # executors reading file.data see it (nothing on this path saves the object).
        file_obj.data = file_obj.effective_data()
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


@shared_task(time_limit=120, soft_time_limit=100)
def cleanup_images_task(environment_id: int, keep_count: int = 3):
    """Remove old Docker images for an environment. Runs on worker with Docker access."""
    try:
        from autograder.services.image_manager import ImageManager
        deleted = ImageManager.cleanup_old_images(environment_id, keep_count)
        return {"success": True, "deleted_count": deleted}
    except Exception as e:
        logger.error(f"Image cleanup task failed for env {environment_id}: {e}", exc_info=True)
        return {"error": str(e), "success": False}


def _get_redis_client():
    """Get a Redis client using the Celery broker URL."""
    import redis
    from django.conf import settings
    return redis.Redis.from_url(settings.CELERY_BROKER_URL)


def _publish_sse(redis_client, channel: str, event: str, data: dict):
    """Publish an SSE-formatted message to a Redis pub/sub channel."""
    message = json.dumps({"event": event, "data": data})
    redis_client.publish(channel, message)


@shared_task(time_limit=180, soft_time_limit=150)
def run_file_streaming_task(
    channel: str,
    file_id: int,
    user_id: int,
    timeout: int = 30,
    force_execute: bool = False,
    test_code: Optional[str] = None,
    code_override: Optional[str] = None,
):
    """
    Execute a file and publish SSE progress to a Redis pub/sub channel.
    The API view subscribes to this channel and relays events to the client.
    """
    r = _get_redis_client()
    try:
        file_obj = File.objects.get(pk=file_id)
        # CourseFile content lives on shared CourseFileContent — hydrate in-memory so
        # executors reading file.data see it (nothing on this path saves the object).
        file_obj.data = file_obj.effective_data()
        user = User.objects.get(pk=user_id)

        _publish_sse(r, channel, "progress", {"status": "executing", "message": "Running code..."})

        executor = Executor.factory(file_obj, content_override=code_override, test_code=test_code)
        if not executor:
            _publish_sse(r, channel, "error", {"error": f"No executor found for file: {file_obj.name}"})
            _publish_sse(r, channel, "_done", {})
            return

        executor.DEFAULT_TIMEOUT = timeout
        result = executor.execute()

        if result is None:
            _publish_sse(r, channel, "error", {"error": "Execution failed: No result returned"})
            _publish_sse(r, channel, "_done", {})
            return

        if not result.success:
            _publish_sse(r, channel, "error", {"error": f"Execution failed: {result.error}"})

        _publish_sse(r, channel, "progress", {
            "status": "completed",
            "message": f"Complete! Processed {file_obj.name}."
        })

        # Save to cache
        result.save_cache(file_obj, user)

        submission, _, _ = file_obj.get_file_info()
        response_data = {
            **result.to_dict(),
            "file_id": file_obj.id,
            "file_name": file_obj.name,
            "cached": False,
            "submission_id": submission.id if submission else None,
        }
        _publish_sse(r, channel, "complete", response_data)
    except Exception as e:
        logger.error(f"Streaming task failed for file {file_id}: {e}", exc_info=True)
        _publish_sse(r, channel, "error", {"error": f"Execution error: {str(e)}"})
    finally:
        _publish_sse(r, channel, "_done", {})
