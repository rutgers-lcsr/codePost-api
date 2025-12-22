from celery import shared_task
from core.models import File, User, CachedExecutionResult
from autograder.services.executors import Executor
import logging

logger = logging.getLogger(__name__)

@shared_task
def run_file_task(file_id: int, user_id: int, timeout: int = 30, force_execute: bool = False):
    try:
        file_obj = File.objects.get(pk=file_id)
        user = User.objects.get(pk=user_id)
        
        # Check cache if not forced
        if not force_execute:
            cached = CachedExecutionResult.get_cached_result(file_obj)
            if cached:
                return cached.get_cached_formated_response(file_obj)

        executor = Executor.factory(file_obj)
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
