# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import logging
from core.models import Assignment, Environment
from autograder.services.autodetector import Autodetector
from autograder.run import BuildEnvironment
from log.models import Event
import json
import time

logger = logging.getLogger(__name__)

def detect_from_assignment_files(assignment_id):
    """
    Scans all files in an assignment to detect the environment language.
    Updates the environment and triggers a build if a new language is detected.
    """
    try:
        assignment = Assignment.objects.get(id=assignment_id)
        
        # 1. Thread-safe Environment Retrieval/Creation
        # Use get_or_create to prevent race conditions from concurrent file uploads
        environment, created = Environment.objects.get_or_create(assignment=assignment)
        
        if created:
            logger.info(f"[AutoDetect] Created missing environment for assignment {assignment.id}")
            try:
                meta = {
                    "event": "environment_created",
                    "assignment_id": assignment.id,
                    "timestamp": time.time()
                }
                Event.objects.create(
                    category="autodetector",
                    user="system",
                    description=f"Created missing environment for assignment {assignment.id}",
                    courseID=assignment.course.id,
                    meta=json.dumps(meta)
                )
            except Exception:
                pass

        if not environment.auto_detect:
            logger.info("[AutoDetect] Auto-detect is disabled for environment.")
            return

        files = list(assignment.files.all())
        if not files:
            logger.info("[AutoDetect] No files found for assignment.")
            return
            
        logger.info(f"[AutoDetect] Scanning {len(files)} assignment files for Env {environment.id}")
        
        result = Autodetector.detect_from_files(files, assignment=assignment)
        
        if not result:
            logger.info("[AutoDetect] No detected language from files.")
            return

        final_language, requirements = result
        logger.info(f"[AutoDetect] Detected language: {final_language}")
        
        # Logic matches RunSubmission: Update if Changed or Unbuilt
        # Prevent update if already building (1) or valid (2) AND everything matches
        is_building_or_done = environment.build_status in [1, 2]
        language_match = (final_language == environment.language)
        
        # Also check requirements if detected
        reqs_match = True
        if requirements:
            reqs_match = (requirements == environment.requirements)
            if not reqs_match:
                logger.info(f"[AutoDetect] Requirements changed (New: {len(requirements)} chars)")

        should_update = not (is_building_or_done and language_match and reqs_match)
        
        if should_update:
            logger.info(f"[AutoDetect] Updating Environment to {final_language} and building.")
            
            # Log Event for Scan Update
            try:
                meta = {
                    "event": "scan_update",
                    "language": final_language,
                    "requirements_detected": bool(requirements),
                    "timestamp": time.time()
                }
                Event.objects.create(
                    category="autodetector",
                    user="system",
                    description=f"Scanned files and updated Env {environment.id} to {final_language}",
                    courseID=assignment.course.id,
                    meta=json.dumps(meta)
                )
            except Exception:
                pass

            environment.language = final_language
            if requirements:
                environment.requirements = requirements
            environment.auto_detect = True
            environment.build_status = 1 # Mark as building immediately
            environment.save(update_fields=['language', 'requirements', 'auto_detect', 'build_status'])
            
            BuildEnvironment.delay(environment.id)
            
    except Exception as e:
        logger.error(f"[AutoDetect] Error detecting from assignment files: {e}", exc_info=True)

def detect_environment_bootstrap(assignment_id):
    """
    Called when an environment is reset to Auto-Detect.
    Attempts to immediately populate the environment from:
    1. Assignment Files (Starter Code)
    2. Latest Submission (if no starter code or detection failed)
    
    This provides a better UX than leaving the environment blank ("Pending").
    """
    try:
        assignment = Assignment.objects.get(id=assignment_id)
        logger.info(f"[AutoDetect] Bootstrapping environment for assignment {assignment.id}")
        
        # 1. Try Assignment Files
        detect_from_assignment_files(assignment.id)
        
        # Reload environment to check if detection succeeded
        environment = Environment.objects.get(assignment=assignment)
        if environment.language:
            logger.info(f"[AutoDetect] Bootstrap success via Assignment Files: {environment.language}")
            return

        # 2. Fallback: Try Latest Submission
        latest_submission = Submission.objects.filter(assignment=assignment).order_by('-created').first()
        if latest_submission:
            logger.info(f"[AutoDetect] Bootstrap fallback: Checking latest submission {latest_submission.id}")
            updated = Autodetector.detect_and_update(latest_submission)
            if updated:
                logger.info(f"[AutoDetect] Bootstrap success via Submission {latest_submission.id}")
            else:
                 logger.info(f"[AutoDetect] Bootstrap failed via Submission {latest_submission.id}")
        else:
             logger.info("[AutoDetect] No submissions available for bootstrap.")

    except Exception as e:
        logger.error(f"[AutoDetect] Error during environment bootstrap: {e}", exc_info=True)
