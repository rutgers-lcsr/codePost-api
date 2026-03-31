# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
# External libraries
import os
import threading
import time
from celery import shared_task
from enum import Enum
import json

# Internal imports
from autograder.celery import app, logger
from autograder.services.executors import ExecutionResult, Executor
from autograder.services.TestService import TestService
from autograder.testUtils.ag_logging import (
    AutograderError,
    AutograderRunAllUsage,
)

from core.models import (
    File,
    SubmissionFile,
    TestCase,
    SubmissionTest,
    Submission,
    Environment,
    TestCategory,
    Assignment,
    User,
)
from log.models import Event

from core.permissions.helpers import isStaffOfSub

from core.emails import TestRunAllCompleteEmail

from datetime import datetime
from typing import Any, cast

import traceback


######################################### CELERY TASKS ###########################################################
# NOTE: task arguments can't be objects, only numbers or strings. Celery can't handle object serialization

testCase_types_to_exclude = ["file", "external"]
EMAIL_BASE_URL = "https://codepost.io"

MAX_LOG_LENGTH = 10000


@app.task
def add(x, y):
    logger.info(f"Adding {x} + {y}")
    return x + y

from autograder.services.builder import Builder

@app.task(priority=0)
def AutoDetectEnvironment(assignment_id):
    """
    Celery task to run auto-detection on assignment files.
    """
    try:
        from autograder.services.detection import detect_from_assignment_files
        detect_from_assignment_files(assignment_id)
    except Exception as e:
        logger.error(f"[AutoDetect] Task failed for assignment {assignment_id}: {e}")

@app.task(priority=0)
def BuildEnvironment(environmentID, rerun_submission_ids: list[int] | None = None):
    """
    Builds the Docker environment for a given Environment ID.
    Optionally reruns submissions after successful build.
    """
    
    # --- AUTO-DETECT UPDATE TRIGGER ---
    # When building explicitly, we should refresh auto-detected requirements.
    # This handles "Update & Build" clicks and AssignmentFile updates.
    try:
        env = Environment.objects.get(id=environmentID)
        if env.auto_detect:
            from autograder.services.autodetector import Autodetector
            logger.info(f"[BuildEnvironment] Triggering auto-detection for env {environmentID}")
            Autodetector.detect_and_update(assignment=env.assignment, force=True)
            # Re-fetch env to get updated requirements
            env.refresh_from_db()
    except Exception as e:
        logger.error(f"[BuildEnvironment] Auto-detect failed: {e}")
    # ----------------------------------

    builder = Builder(environmentID)
    result = builder.build()
    
    if result.get("success") and rerun_submission_ids:
        logger.info(f"[BuildEnvironment] Triggering reruns for {len(rerun_submission_ids)} submissions")
        for sub_id in rerun_submission_ids:
            cast(Any, RunSubmission).delay(sub_id)
            logger.info(f"[BuildEnvironment] Queued rerun for submission {sub_id}")
    
    return result


@app.task
def CleanupOldImages(environment_id: int, keep_count: int = 3):
    """
    Celery task to cleanup old Docker images for an environment.
    Keeps the most recent `keep_count` versions.
    """
    from autograder.services.image_manager import ImageManager
    deleted = ImageManager.cleanup_old_images(environment_id, keep_count)
    logger.info(f"[CleanupOldImages] Cleaned up {deleted} images for env {environment_id}")
    return {"deleted_count": deleted}


@app.task
def DeleteEnvironmentImages(environment_id: int):
    """
    Celery task to delete all Docker images for a deleted environment.
    """
    from autograder.services.image_manager import ImageManager
    deleted = ImageManager.delete_all_images_for_env(environment_id)
    logger.info(f"[DeleteEnvironmentImages] Deleted {deleted} images for env {environment_id}")
    return {"deleted_count": deleted}


@app.task
def ValidateConvergence(environment_id: int):
    """
    Celery task to validate if convergence was successful.
    Called after submissions have been rerun with new dependencies.
    
    If success rate >= 80%: Promote and cleanup old images
    If success rate < 50% after min runs: Rollback and notify admin
    """
    from autograder.services.image_manager import ImageManager
    
    try:
        env = Environment.objects.get(pk=environment_id)
        
        if not env.convergence_pending:
            logger.info(f"[ValidateConvergence] No pending convergence for env {environment_id}")
            return {"status": "no_pending"}
        
        # Need minimum runs to validate
        MIN_RUNS_FOR_VALIDATION = 5
        if env.total_runs < MIN_RUNS_FOR_VALIDATION:
            logger.info(f"[ValidateConvergence] Not enough runs yet ({env.total_runs}/{MIN_RUNS_FOR_VALIDATION})")
            return {"status": "waiting_for_runs", "runs": env.total_runs}
        
        success_rate = env.successful_runs / env.total_runs if env.total_runs > 0 else 0
        
        if success_rate >= 0.8:
            # Success! Promote convergence
            ImageManager.promote_pending_convergence(environment_id)
            logger.info(f"[ValidateConvergence] Convergence successful for env {environment_id} ({success_rate:.0%})")
            return {"status": "promoted", "success_rate": success_rate}
        
        elif success_rate < 0.5 and env.total_runs >= MIN_RUNS_FOR_VALIDATION:
            # Failed! Rollback and notify admin
            history = env.image_history or []
            if len(history) >= 2:
                # Rollback to previous version
                previous_version = history[-2]["version"]
                ImageManager.rollback_to_version(environment_id, previous_version)
                logger.warning(f"[ValidateConvergence] Rolled back env {environment_id} to v{previous_version}")
            
            # Notify admin
            if not env.convergence_failed_notified:
                NotifyConvergenceFailure.delay(environment_id, success_rate)
            
            return {"status": "rolled_back", "success_rate": success_rate}
        
        else:
            # Still inconclusive
            logger.info(f"[ValidateConvergence] Inconclusive for env {environment_id} ({success_rate:.0%})")
            return {"status": "inconclusive", "success_rate": success_rate}
            
    except Exception as e:
        logger.error(f"[ValidateConvergence] Error for env {environment_id}: {e}")
        return {"status": "error", "error": str(e)}


@app.task
def NotifyConvergenceFailure(environment_id: int, success_rate: float):
    """
    Celery task to notify course admin of convergence failure.
    """

    try:
        env = Environment.objects.get(pk=environment_id)
        assignment = env.assignment
        course = assignment.course
        
        # Mark as notified
        env.convergence_failed_notified = True
        env.save(update_fields=['convergence_failed_notified'])
        
        # Build notification
        subject = f"[codePost] Auto-detect environment update failed - {assignment.name}"
        body = f"""
The auto-detect environment update for assignment "{assignment.name}" in course "{course.name}" has failed.

Current success rate: {success_rate:.0%}

The environment has been automatically rolled back to the previous working version.

Pending modules that could not be resolved:
{', '.join(env.convergence_stats.keys()) if env.convergence_stats else 'None'}

Please review the environment settings and consider:
1. Manually adding the required dependencies
2. Converting to manual configuration
3. Reviewing student submissions for issues

Environment Admin URL: {os.environ.get('CODEPOST_CLIENT_URL', 'http://localhost:3000')}/admin/tests/{assignment.id}

Best,
codePost Autograder
"""
        
        # Send to course admins
        admins = course.courseAdmins.all()
        for admin in admins:
            try:
                admin.email_user(subject, body)
                logger.info(f"[NotifyConvergenceFailure] Emailed {admin.email}")
            except Exception as e:
                logger.error(f"[NotifyConvergenceFailure] Failed to email {admin.email}: {e}")
        
        return {"status": "notified", "admins_count": admins.count()}
        
    except Exception as e:
        logger.error(f"[NotifyConvergenceFailure] Error for env {environment_id}: {e}")
        return {"status": "error", "error": str(e)}



@app.task
def RunAll(environmentID, user_id, sendEmail=False):
    """
    Autograder Run All Task
    This celery task takes an environment and runs all tests on all submissions.
    It updates the progress of the task after each submission run.
    
    Args:
        environmentID: The environment ID
        user_id: The ID (int) of the requesting user
        sendEmail: Whether to send a completion email
    """
    environment = Environment.objects.get(id=environmentID)
    assignment = environment.assignment

    # Look up the user object from the ID
    try:
        user = User.objects.get(id=user_id)
        user_str = str(user)
    except User.DoesNotExist:
        user = None
        user_str = str(user_id)

    ######################## 1. Get Submissions ######################################
    submissions = environment.assignment.submissions.all()

    ######################## 2. Get TestFiles ######################################
    tests = TestCase.objects.filter(testCategory__assignment=assignment).exclude(
        type__in=testCase_types_to_exclude
    )
    all_test_cases = TestCase.objects.filter(
        testCategory__assignment=assignment
    ).exclude(type="external")

    #####################
    start_time = datetime.now()
    AutograderRunAllUsage(
        user_str,
        "Run All Started for assignment {}".format(assignment.name),
        "Number of submissions: {}\nNumber of Tests: {}\n Time Started: {}".format(
            len(submissions),
            len(all_test_cases),
            start_time.strftime("%d/%m/%Y %H:%M:%S"),
        ),
    )

    progress_map = {}
    ######################## Loop through submissions######################################
    for s in submissions:
        ######################## 3. Run ######################################
        # If creating the submission tests fail (sql connection error), don't block other tests
        try:
            try:
                # Use Modern TestService Unified Architecture
                results = TestService.run_suite(s.id, user_id=user_id)
                
                # Check for suite-level error
                if results and isinstance(results[0], dict) and not results[0].get('success') and 'error' in results[0] and 'testCaseId' not in results[0]:
                     # Catastrophic failure
                     logs = results[0]['error']
                     raise Exception(logs)

                # Fetch the created/updated SubmissionTest objects for progress tracking
                newSubmissionTests = list(SubmissionTest.objects.filter(
                    submission=s, 
                    testCase__in=all_test_cases
                ))
                
                logs = "Run Suite Completed via TestService"

            except Exception as e:
                AutograderError(
                    user_str,
                    "Run all - individual test failed: {}".format(str(s.students.first())),
                    "Exception: {}".format(traceback.format_exc()),
                )
                newSubmissionTests = []
                logs = str(e)

            ######################## 5. Check for run and dump  ######################################
            _runAndDump(environment, s, logs)
        except:
            AutograderError(
                user_str,
                "Run all - individual test failed: {}".format(str(s.students.first())),
                "Exception: {}".format(traceback.format_exc()),
            )
            newSubmissionTests = []

        ######################## 6. Update progress  ######################################
        progress_map = _calculateProgress(newSubmissionTests, progress_map)
        RunAll.update_state(state="PROGRESS", meta={"progress": progress_map})

    ######################## 7. Turn off "isRunning" ######################################
    setattr(environment, "isRunning", False)
    environment.save()

    if sendEmail and user:
        TestRunAllCompleteEmail(user).send_email(assignment_name=assignment.name, course_name=assignment.course.name, course_period=assignment.course.period)

    end_time = datetime.now()
    msg = "Run All Completed for assignment {}".format(assignment.name)
    time = "Time Completed {}\n Time Taken {} ".format(
        end_time.strftime("%d/%m/%Y %H:%M:%S"), str(end_time - start_time)
    )
    AutograderRunAllUsage(user_str, msg, time)
    try:
        meta = {msg: msg, time: time}
        Event.objects.create(
            category="autograder",
            user=user_str,
            description="Autograder run all completed",
            courseID=assignment.course.id,
            meta=json.dumps(meta),
        )
    except:
        pass

    ######################## 8. Return ######################################
    return {}


class RunType(str, Enum):
    Submission = "SUBMISSION"
    TestCase = "TESTCASE"


@shared_task(bind=True, max_retries=3, default_retry_delay=60, time_limit=600,soft_time_limit=550)
def RunSubmission(self, submissionID: int):
    """
    This celery task handles on-submit execution for a submission in two phases:
    
    1. **File execution** (if ``runFilesOnSubmit`` is True): Runs all executable files
       and caches execution results so they don't need to be re-executed later.
    2. **Test execution** (if ``runTestsOnSubmit`` is True): Runs the full test suite
       via ``TestService.run_suite()`` against the submission.
    
    The two-phase approach ensures cached outputs are available before tests evaluate them.
    Either phase can be independently enabled/disabled per assignment.
    
    The task will automatically retry up to 3 times if it fails, with a 60-second delay between retries.
    
    Args:
        submissionID (int): The ID of the submission to run.
        
    Returns:
        dict: Summary of execution and test results
        
    Raises:
        Submission.DoesNotExist: If submission ID is invalid
        Exception: If execution fails after all retries
    """
    try:
        submission = Submission.objects.get(id=submissionID)
        assignment_id = submission.assignment.id
        logger.info(f"[RunSubmission] Processing submission {submission.id} for assignment {assignment_id}")
        
        # Explicitly get environment using assignment_id to avoid descriptor ambiguity
        environment = Environment.objects.get(assignment_id=assignment_id)
        logger.info(f"[RunSubmission] Found environment {environment.id} (image: {environment.image_name})")

        # Record autograder triggered audit event
        try:
            from core.services.audit import record_audit_event
            course = submission.assignment.course
            ag_user = submission.students.first()
            record_audit_event(
                course=course,
                event_type='autograder_triggered',
                user=ag_user,
                assignment=submission.assignment,
                submission=submission,
            )
        except Exception:
            pass
        
    except Submission.DoesNotExist:
        logger.error(f"Submission {submissionID} not found")
        return {"success": False, "error": "Submission not found"}
    except Environment.DoesNotExist:
        logger.error(f"Environment for assignment {submission.assignment.id} not found")
        return {"success": False, "error": "Environment not found"}

    # Wait for build if pending
    if environment.build_status == 1: # Building
        logger.info(f"[RunSubmission] Environment {environment.id} is building. Waiting...")
        import time
        # Wait up to 300 seconds
        for _ in range(30):
            time.sleep(10)
            environment.refresh_from_db()
            if environment.build_status != 1:
                break
        logger.info(f"[RunSubmission] Environment {environment.id} wait finished. Status: {environment.build_status}")

    # --- Phase 1: Execute files and cache output ---
    run_files = getattr(submission.assignment, 'runFilesOnSubmit', True)

    file_objs = submission.files.all()
    
    if not file_objs or len(file_objs) == 0:
        logger.info(f"No files found for submission {submissionID}")
        if not getattr(submission.assignment, 'runTestsOnSubmit', False):
            return {"success": True, "message": "No files to execute", "files_processed": 0}
    
    # Look for file with executable extension
    files: list[SubmissionFile] = []


    for f in file_objs:
        executor = Executor.factory(cast(Any, f))
        if executor:
            files.append(f)
    
    
    # If no executable file found, skip file execution but may still run tests
    if not files or len(files) == 0:
        logger.info(f"No executable file found for submission {submissionID}")
        if not getattr(submission.assignment, 'runTestsOnSubmit', False):
            return {"success": True, "message": "No executable files found", "files_processed": 0}

    logger.info(f"Running submission {submissionID} with {len(files)} executable files out of {len(file_objs)} total files")

    results = []
    successful = 0
    failed = 0
    
    # Cold Start Candidate Collection REMOVED - using Autodetector
    # language_candidates = {} REMOVED
    
    # Get required files for heuristic
    required_filenames = set()
    try:
        assignment = environment.assignment
        required_files = assignment.files.filter(required=True)
        required_filenames = {rf.name for rf in required_files}
    except Exception:
        pass
    
    if not run_files:
        logger.debug(f"[RunSubmission] runFilesOnSubmit disabled for assignment {submission.assignment.id}. Skipping file execution.")
    elif not files:
        logger.debug(f"[RunSubmission] No executable files to run.")
    else:
      try:
        for f in files:
            result: ExecutionResult = None  # type: ignore[ExecutionResult]
            execution_error = None
            execution_complete = threading.Event()

            # Retrieve custom image name if built
            image_name = environment.image_name if environment.image_name else None
            executor = Executor.factory(cast(Any, f), image_name=image_name)
            
            if not executor:
                logger.info(f"File {f.id} has no executor, skipping.")
                failed += 1
                results.append({"file_id": f.id, "file_name": f.name, "success": False, "error": "No executor available"})
                continue
            
            def execute_thread():
                """Execute in background thread"""
                nonlocal executor, result, execution_error
                try:
                    if not executor:
                        raise ValueError("No executor found for file.")
                    result = executor.execute()
                except Exception as e:
                    logger.error(f"[RunSubmission] Execution failed: {e}", exc_info=True)
                    execution_error = e
                finally:
                    execution_complete.set()
            
            # Start execution in background thread
            exec_thread = threading.Thread(target=execute_thread, daemon=True)
            exec_thread.start()
            
            # Wait for thread to complete (with reasonable timeout)
            exec_thread.join(timeout=300)  # 5 minutes max per file

            if execution_error:
                logger.error(f"[RunSubmission] Execution error for file {f.id}: {execution_error}", exc_info=True)
                failed += 1
                results.append({"file_id": f.id, "file_name": f.name, "success": False, "error": str(execution_error)})
                continue

            if result is None:
                logger.warning(f"[RunSubmission] Execution did not complete for file {f.id}")
                failed += 1
                results.append({"file_id": f.id, "file_name": f.name, "success": False, "error": "Execution timeout or incomplete"})
                continue
            
            # Save the cached result
            # The try block is intended to catch errors during saving/processing the result, not the execution itself.
            # This ensures that if saving fails, the main loop can continue.
            try:
                result.save_cache(f)
                successful += 1
                results.append({"file_id": f.id, "file_name": f.name, "success": True, "execution_time": result.execution_time})
                logger.info(f"[RunSubmission] Successfully cached execution for file {f.id}")


                
                # Convergence Hook: Analyze stderr for missing dependencies
                if result.stderr or (not result.success and result.err):
                    try:
                        from autograder.services.converger import Converger
                        logs_to_analyze = f"{result.stderr or ''}\n{result.err or ''}"
                        
                        # Track the run result
                        if result.success:
                            Converger.record_successful_run(environment.id)
                        else:
                            Converger.record_failed_run(environment.id)
                        
                        # Analyze with submission ID for tracking
                        should_converge, added_modules, subs_to_rerun = Converger.analyze_and_converge(
                            environment.id, logs_to_analyze, submission_id=submissionID
                        )
                        
                        if should_converge and added_modules:
                            logger.info(f"[RunSubmission] Convergence added {added_modules}")
                            results[-1]["converged_modules"] = list(added_modules)
                            
                            # Trigger build and queue reruns
                            if subs_to_rerun:
                                logger.info(f"[RunSubmission] Triggering build and queueing reruns for {len(subs_to_rerun)} submissions")
                                # Use delay to run asynchronously
                                BuildEnvironment.delay(environment.id, rerun_submission_ids=subs_to_rerun)
                            else:
                                # Start build even if no reruns (e.g. just detected something)
                                logger.info(f"[RunSubmission] Triggering build for env {environment.id}")
                                BuildEnvironment.delay(environment.id)
                                
                    except Exception as conv_err:
                        logger.warning(f"[RunSubmission] Converger failed: {conv_err}")
                        
            except Exception as e:
                logger.error(f"[RunSubmission] Failed to save cache for file {f.id}: {e}")
                failed += 1
                results.append({"file_id": f.id, "file_name": f.name, "success": False, "error": f"Cache save failed: {str(e)}"})
    
      except Exception as e:
        logger.error(f"[RunSubmission] Unexpected error processing submission {submissionID}: {e}", exc_info=True)
        # Retry the task if we hit an unexpected error
        raise self.retry(exc=e)
    
    # --- Cold Start: Update Environment Language ---
    try:
        from autograder.services.autodetector import Autodetector
        Autodetector.detect_and_update(submission)
    except Exception as e:
        logger.error(f"[ColdStart] Error running Autodetector: {e}")
    # -----------------------------------------------

    # --- Run Tests (if enabled for this assignment) ---
    test_results = []
    run_tests = getattr(submission.assignment, 'runTestsOnSubmit', False)
    if run_tests:
        try:
            test_results = TestService.run_suite(submissionID)
            test_passed = sum(1 for r in test_results if r.get('passed'))
            test_failed = len(test_results) - test_passed
            logger.info(
                f"[RunSubmission] Test suite for submission {submissionID}: "
                f"{test_passed} passed, {test_failed} failed out of {len(test_results)} tests"
            )
        except Exception as e:
            logger.error(
                f"[RunSubmission] Test suite failed for submission {submissionID}: {e}",
                exc_info=True
            )
    else:
        logger.debug(f"[RunSubmission] runTestsOnSubmit disabled for assignment {submission.assignment.id}. Skipping tests.")
    # -----------------------------------------------
    
    summary = {
        "success": True,
        "submission_id": submissionID,
        "files_processed": len(files),
        "successful": successful,
        "failed": failed,
        "results": results,
        "tests_run": run_tests,
        "test_results_count": len(test_results),
    }
    
    logger.info(f"[RunSubmission] Completed submission {submissionID}: {successful} successful, {failed} failed")

    # Record autograder completed/failed audit event
    try:
        from core.services.audit import record_audit_event
        course = submission.assignment.course
        ag_user = submission.students.first()
        if failed > 0:
            record_audit_event(
                course=course,
                event_type='autograder_failed',
                user=ag_user,
                assignment=submission.assignment,
                submission=submission,
                meta={'successful': successful, 'failed': failed, 'test_results_count': len(test_results)},
            )
        else:
            record_audit_event(
                course=course,
                event_type='autograder_completed',
                user=ag_user,
                assignment=submission.assignment,
                submission=submission,
                meta={'successful': successful, 'test_results_count': len(test_results)},
            )
    except Exception:
        pass

    # --- Trigger AI grading assistance (suggested comments + summary) ---
    try:
        from core.tasks import generate_ai_grading_assistance
        generate_ai_grading_assistance.delay(submissionID)
        logger.info(f"[RunSubmission] Queued AI grading assistance for submission {submissionID}")
    except Exception as e:
        logger.warning(f"[RunSubmission] Failed to queue AI grading assistance: {e}")

    return summary


@app.task
def Run(
    user,
    environmentID,
    type,
    pk,
    subID=None,
    createSubmissionTests=False,
    exposed_only=False,
    fileOverrides=None,
    run_by_role="unknown",
):
    """
    Deprecated!
    Removing Autograder Run Task
    
    This celery task does a single run of tests on an object of type Submission, TestCase, or SourceFile
    For type TestCase or SourceFile, an optional submissionID can be passed in to be run on. If not, solution files will be used.
    For type Submission, all tests are run.

    Files: Submission(pk).files if type Submission else Submission(subID) if subID else SolutionFiles
    Tests: TestCase(pk) if type TestCase else All Tests
    """
    return False


def filterExposedSubmissionTests(submissionTests, maxFailedTests=None):
    # Message is an optional message we want to feed back to students based on
    # conditions hit when parsing results
    message = ""
    if maxFailedTests == None:
        return ([t for t in submissionTests if t.testCase.exposed], "")

    # The user has set a limit on the number of failed tests to show
    newSubmissionTests = []
    numFailed = {}

    submissionTests.sort(key=lambda x: x.testCase.id)
    for t in submissionTests:
        if t.testCase.exposed:
            if t.passed:
                newSubmissionTests.append(t)
            else:
                # check to see if we can report the results of this test
                categoryID = t.testCase.testCategory.id

                # initialize, if we need to
                if categoryID not in numFailed:
                    numFailed[categoryID] = 0

                if numFailed[categoryID] < maxFailedTests:
                    newSubmissionTests.append(t)
                    numFailed[categoryID] += 1
                else:
                    message = "Your instructor has set a limit on the amount of failed tests that are exposed to you, so some tests you failed will show up as HIDDEN."

    return (newSubmissionTests, message)


##################################################################################################################
######################################### HELPER FUNCTONS ########################################################
##################################################################################################################


## Helper: Parse created submission tests to get progress
def _calculateProgress(submissionTests, map):
    for t in submissionTests:
        _id = t.testCase.id
        if _id not in map:
            map[_id] = {"passed": 0, "failed": 0, "error": 0}
        if t.passed:
            map[_id]["passed"] += 1
        elif t.isError:
            map[_id]["error"] += 1
        else:
            map[_id]["failed"] += 1
    return map


## Check for run and dump and, if so, output logs to a _tests.TXT file
def _runAndDump(environment, submission, logs):
    try:
        testFile = SubmissionFile.objects.get(submission=submission, name="_tests.txt")
        testFile.data = logs
        testFile.save()
    except SubmissionFile.DoesNotExist:
        SubmissionFile.objects.create(
            submission=submission,
            name="_tests.txt",
            extension=".txt",
            data=logs,
            path="",
            hiddenBeforePublish=True,
        )
    return


# @app.task
# def daily_assignment_check():
#     """
#     FIXME: Move Celery config to /codepost and fix celery.py autodiscover
#     """
#     now = timezone.now()
#     tomorrow = now + timedelta(days=1)
#     assignments = Assignment.objects.filter(uploadDueDate__range=(now, tomorrow)).order_by('uploadDueDate')

#     eastern = pytz.timezone('US/Eastern')

#     attachments = []

#     for assignment in assignments:
#         firstAdmin = assignment.course.courseAdmins.first().email

#         attachments.append({
#             "title": "{} | {} ({})".format(assignment.course.name, assignment.course.period, firstAdmin),
#             "text": "{} ({} students)".format(assignment.name, assignment.course.students.count()),
#             "footer": assignment.uploadDueDate.astimezone(eastern).strftime('%a, %d %b %Y %H:%M:%S %z (%Z)')
#         })

