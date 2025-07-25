# External libraries
import requests
from enum import Enum
import json
from django.contrib.auth.models import User

# Internal imports
from autograder.celery import app, logger
from codepost.settings import AUTOGRADER_URL
from autograder.testUtils.logging import (
    AutograderError,
    AutograderUsage,
    AutograderRunAllUsage,
    AutograderTestError,
    standardLog,
)

from core.models import (
    TestCase,
    SubmissionTest,
    Submission,
    Environment,
    TestCategory,
    SourceFile,
    File,
    SolutionFile,
    Assignment,
)
from core.serializers.submissionTest import SubmissionTestSerializer
from log.models import Event, TrackedAutograderRun

from core.permissions.helpers import isStaffOfSub
from autograder.testUtils.parse import parseTests, parseSourceFile, writeCmdScript

from core.emails import TestRunAllCompleteEmail, send_email_sendgrid, get_email_template_id, get_email_params

from rest_framework.response import Response

from datetime import datetime, timedelta
from django.utils import timezone
import pytz
import urllib

import re
import traceback


import copy

from util.slack import Slack

######################################### CELERY TASKS ###########################################################
# NOTE: task arguments can't be objects, only numbers or strings. Celery can't handle object serialization

testCase_types_to_exclude = ["file", "external"]
EMAIL_BASE_URL = "https://codepost.io"

MAX_LOG_LENGTH = 10000


@app.task
def add(x, y):
    logger.info(f"Adding {x} + {y}")
    return x + y


@app.task
def RunAll(environmentID, user, sendEmail=False):
    """
    This celery task takes an environment and runs all test on all submissions.
    It updates the progress of the task after each submission run.
    """
    environment = Environment.objects.get(id=environmentID)
    assignment = environment.assignment

    ######################## 1. Get Submissions ######################################
    submissions = environment.assignment.submissions.all()

    ######################## 2. Get TestFiles ######################################
    sourceFiles = environment.sourceFiles.all()
    tests = TestCase.objects.filter(testCategory__assignment=assignment).exclude(
        type__in=testCase_types_to_exclude
    )
    all_test_cases = TestCase.objects.filter(
        testCategory__assignment=assignment
    ).exclude(type="external")

    #####################
    start_time = datetime.now()
    AutograderRunAllUsage(
        str(user),
        "Run All Started for assignment {}".format(assignment.name),
        "Number of submissions: {}\nNumber of Tests: {}\n Time Started: {}".format(
            len(submissions),
            len(all_test_cases),
            start_time.strftime("%d/%m/%Y %H:%M:%S"),
        ),
    )

    map = {}
    allResults = []
    ######################## Loop through submissions######################################
    for s in submissions:
        ######################## 3. Run ######################################
        # If creating the submission tests fail (sql connection error), don't block other tests
        try:
            fileObjs = s.files.all()
            files = [
                {"name": f.name, "code": f.code, "path": f.path if f.path else ""}
                for f in fileObjs
            ]
            (response, logs) = _runTests(
                tests,
                sourceFiles,
                environment,
                files,
                user,
                s.id,
                assignment=assignment,
                submission=s,
                test_case_set="all",
                run_by_role="instructor",
            )

            # There is an erorr in the result the user receives. We want to log this to help user education
            if logs and "error" in logs.lower() or "Operation Timed Out." in logs:
                AutograderTestError(
                    str(user),
                    "Test logs contains an error: {}".format(str(s.students.first())),
                    logs,
                )

            ######################## 4. Parse results ######################################
            if isinstance(response, RunError):
                AutograderError(
                    str(user),
                    "RUN ERROR: {}".format(str(s.students.first())),
                    "RESPONSE: {}".format(response),
                )
                results = [
                    TestResult(t, t.testCategory, False, response, True)
                    for t in all_test_cases
                ]
            else:
                results = [_processResult(r, assignment, user) for r in response]
                # Filter out any empty results (e.g., if a test case is deleted mid-run)
                results = [r for r in results if r is not None]

            results = _addMissingTests(results, all_test_cases, response, logs)

            newSubmissionTests = [_createSubmissionTest(r, s) for r in results]

            ######################## 5. Check for run and dump  ######################################
            _runAndDump(environment, s, logs)
        except:
            AutograderError(
                str(user),
                "Run all - individual test failed: {}".format(str(s.students.first())),
                "Exception: {}".format(traceback.format_exc()),
            )
            newSubmissionTests = []

        ######################## 6. Update progress  ######################################
        map = _calculateProgress(newSubmissionTests, map)
        RunAll.update_state(state="PROGRESS", meta={"progress": map})

    ######################## 7. Turn off "isRunning" ######################################
    environment.isRunning = False
    environment.save()

    if sendEmail:

        TestRunAllCompleteEmail(user).send_email(assignment_name=assignment.name, course_name=assignment.course.name, course_period=assignment.course.period)
   

    end_time = datetime.now()
    msg = "Run All Completed for assignment {}".format(assignment.name)
    time = "Time Completed {}\n Time Taken {} ".format(
        end_time.strftime("%d/%m/%Y %H:%M:%S"), str(end_time - start_time)
    )
    AutograderRunAllUsage(str(user), msg, time)
    try:
        meta = {msg: msg, time: time}
        Event.objects.create(
            category="autograder",
            user=str(user),
            description="Autograder run all completed",
            courseID=assignment.course_id,
            meta=json.dumps(meta),
        )
    except:
        pass

    ######################## 8. Return ######################################
    return {}


class RunType(str, Enum):
    Submission = "SUBMISSION"
    TestCase = "TESTCASE"
    SourceFile = "SOURCEFILE"


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
    This celery task does a single run of tests on an object of type Submission, TestCase, or SourceFile
    For type TestCase or SourceFile, an optional submissionID can be passed in to be run on. If not, solution files will be used.
    For type Submission, all tests are run.

    Files: Submission(pk).files if type Submission else Submission(subID) if subID else SolutionFiles
    Tests: TestCase(pk) if type TestCase else SourceFile(pk) if type SourceFile else All Tests
    """
    environment = Environment.objects.get(id=environmentID)
    assignment = environment.assignment
    type = RunType(json.loads(type))

    start_time = datetime.now()
    AutograderUsage(
        str(user),
        "Run for assignment {}".format(assignment.name),
        "Type: {}".format(type),
    )

    ######################## 1. Get File Objects ######################################
    submissionID = pk if type == RunType.Submission else subID if subID else None
    submission = Submission.objects.get(id=submissionID) if submissionID else None

    if fileOverrides != None:
        files = fileOverrides
    else:
        # If there's no submission specified, use the solution files
        fileObjs = (
            submission.files.all() if submission else environment.solutionFiles.all()
        )
        files = [
            {"name": f.name, "code": f.code, "path": f.path if f.path else ""}
            for f in fileObjs
        ]

    ######################## 2. Get Test Objects ######################################
    if type == RunType.Submission:
        # Get all tests
        testCases = TestCase.objects.filter(
            testCategory__assignment=assignment
        ).exclude(type__in=testCase_types_to_exclude)

        sourceFiles = environment.sourceFiles.all()
        _tracked_autograder_run_test_case_set = "all"
    else:
        testCases = TestCase.objects.filter(id=pk) if type == RunType.TestCase else []
        sourceFiles = (
            SourceFile.objects.filter(id=pk) if type == RunType.SourceFile else []
        )
        _tracked_autograder_run_test_case_set = "partial"

    ######################## 3. Run ######################################
    (response, logs) = _runTests(
        testCases,
        sourceFiles,
        environment,
        files,
        user,
        subID if subID != None else "dummy",
        assignment=assignment,
        submission=submission,
        test_case_set=_tracked_autograder_run_test_case_set,
        run_by_role=run_by_role,
    )

    # There is an erorr in the result the user receives. We want to log this to help user education
    if logs and "error" in logs.lower() or "Operation Timed Out." in logs:
        AutograderTestError(
            str(user),
            "Test logs contains an error: {}".format(
                str(submission.students.first()) if submission else ""
            ),
            logs,
        )

    ######################## 4. Parse results ######################################
    if isinstance(response, RunError):
        # FIXME: parse error
        AutograderError(
            str(user),
            "RUN ERROR: {}".format(
                str(submission.students.first()) if submission else ""
            ),
            "RESPONSE: {}".format(response),
        )
        results = [
            TestResult(t, t.testCategory, False, response, True) for t in testCases
        ]
    else:
        results = [_processResult(r, assignment, user) for r in response]
        # Filter out any empty results (e.g., if a test case is deleted mid-run)
        results = [r for r in results if r is not None]

    ######################## 5. Check for run and dump ######################################
    _runAndDump(environment, submission, logs)

    end_time = datetime.now()
    msg = "Run completed for assignment {}".format(assignment.name)
    time = "Time Taken: {}\n".format(str(end_time - start_time))
    AutograderUsage(str(user), msg, time)
    try:
        meta = {msg: msg, time: time}
        Event.objects.create(
            category="autograder",
            user=str(user),
            description="Autograder run completed",
            courseID=assignment.course_id,
            meta=json.dumps(meta),
        )
    except:
        pass

    ######################## 6. Return ######################################
    if type == RunType.Submission and submission:
        results = _addMissingTests(
            results,
            TestCase.objects.filter(testCategory__assignment=assignment).exclude(
                type="external"
            ),
            response,
            logs,
        )
    if type == RunType.Submission and createSubmissionTests and submission:
        newSubmissionTests = [_createSubmissionTest(r, submission) for r in results]
        # Message is an optional message we want to feed back to students based on
        # conditions hit when parsing results
        message = ""

        if exposed_only:
            # If exposed_only, only return the serialized submission tests for exposed test cases
            (newSubmissionTests, message) = filterExposedSubmissionTests(
                newSubmissionTests, environment.maxExposedFailedTests
            )
            # Increment the times the submission has been run by the student
            submission.testRunsCompleted += 1
            submission.save()
        serializer = SubmissionTestSerializer(newSubmissionTests, many=True)

        # If the setting is turn on to epxose dumped logs to students, then we return it
        # We return none instead of a blank string in order to differentiate between results that have
        # empty logs and results where the exposeDumpLogs setting is turned off
        exposedLogs = logs if environment.exposeDumpLogs else None
        toRet = {
            "logs": exposedLogs,
            "submissionTests": serializer.data,
            "message": message,
        }
        return toRet
    else:
        # Returning overall logs, to enable "run and dump" while testing
        # If the logs map to a specific test case, we pass that into the formatting, else we pass in None
        formattedLogs = _formatLogs(
            logs, testCases[0] if type == RunType.TestCase else None
        )
        toRet = {
            "logs": formattedLogs,
            "results": [
                _formatResult(
                    r.testCase.id, r.testCategory.id, r.passed, r.logs, r.isError
                )
                for r in results
            ],
        }
        return toRet


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
class RunError(str, Enum):
    ConnectionError = "Request timed out"
    JsonParseError = "Something went wrong. Contact the team at team@codepost.io."
    EmptyOutputError = "Empty output received."


class TestResult:
    def __init__(self, testCase, testCategory, passed, logs, isError):
        self.testCase = testCase
        self.testCategory = testCategory
        self.passed = passed
        self.logs = logs
        self.isError = isError


## Main Run function
def _runTests(
    testCases,
    sourceFiles,
    environment,
    files,
    user,
    submissionID="dummy",
    *,
    assignment,
    submission,
    test_case_set,
    run_by_role,
):
    try:
        _user = User.objects.get(username=user)
    except:
        _user = None

    tracked_autograder_run = TrackedAutograderRun.objects.create(
        run_by=_user,
        assignment=assignment,
        submission=submission,
        test_case_set=test_case_set,
        run_by_role=run_by_role,
    )
    tracked_autograder_run.started = datetime.now()
    tracked_autograder_run.save()
    ########################### 1. Process files ###########################################
    helpers = [
        {"name": f.name, "code": f.code, "path": _parseFilePath(f.path)}
        for f in environment.helperFiles.all()
    ]

    ########################### 2. Process tests ###########################################
    caseTests = parseTests(testCases, environment.language)
    sourceFileTests = [parseSourceFile(sF) for sF in sourceFiles]

    ########################### 3. Create command script ###################################
    command = writeCmdScript(
        caseTests, sourceFileTests, environment.compileText, environment.language
    )

    ########################### 4. Send payload to autograder ##############################
    tests = caseTests + sourceFileTests
    payload = {
        "tests": tests,
        "files": files + helpers,
        "assignment": environment.assignment.id,
        "buildID": environment.buildID if environment.buildID > 0 else None,
        "submission": submissionID,
        "command": command,
        "allowNetworkAccess": environment.allowNetworkAccess,
    }

    # TMP
    # try:
    #     standardLog(str(user), "autograder input", json.dumps(payload), "#richard-test")
    # except:
    #     print('error with log')
    resp = requests.post(AUTOGRADER_URL + "/run/", json=payload)

    tracked_autograder_run.ended = datetime.now()
    tracked_autograder_run.save()

    ########################### 5. Check for erros #################################################
    try:
        r = resp.json()

        # TMP
        # try:
        #     standardLog(str(user), "autograder output", json.dumps(r), "#richard-test")
        # except:
        #     print('error with log')

    except:
        tracked_autograder_run.errors = resp.text
        tracked_autograder_run.save()

        if "ConnectionError" in resp.text:
            AutograderError(
                str(user),
                "Operation timed out. Language: {}".format(environment.language),
                "Response: {}".format(resp.text),
            )
            return (RunError.ConnectionError, "")
        else:
            AutograderError(
                str(user),
                "JSON parse error. Language: {}".format(environment.language),
                "Response: {}".format(resp.text),
            )
            return (RunError.JsonParseError, "")
    try:
        # Truncate logs to avoid db write timeouts for exceeding long logs
        return (r["results"], _truncateLogs(r["logs"]))
    except:
        tracked_autograder_run.errors = resp.text
        tracked_autograder_run.save()

        AutograderError(
            str(user),
            "Key Error {}".format(environment.language),
            "Response: {}".format(resp.text),
        )
        return (RunError.JsonParseError, "")


# Autograder requires trailing slash and no beinning slash
def _parseFilePath(path):
    if not path:
        return ""
    return path.strip("/") + "/"


def _addMissingTests(results, allTestCases, response, logs):
    reasonForMissing = (
        response
        if isinstance(response, RunError)
        else "Operation Timed Out. "
        if "Operation Timed Out." in logs
        else logs
    )
    existingTestIDs = {r.testCase.id for r in results}
    for t in allTestCases:
        if t.id not in existingTestIDs:
            results.append(
                TestResult(
                    t,
                    t.testCategory,
                    False,
                    reasonForMissing + "No output received",
                    True,
                )
            )
    return results


def _createSubmissionTest(result, submission):
    testQuerySet = SubmissionTest.objects.filter(
        submission=submission, testCase=result.testCase
    )
    # We truncate the logs so that there isn't a db write error for infinite loops with prints
    shortLogs = _truncateLogs(str(result.logs))
    if len(testQuerySet) == 1:
        newTest = testQuerySet[0]
        newTest.passed = result.passed
        newTest.logs = shortLogs
        newTest.isError = result.isError
    elif len(testQuerySet) > 1:
        # Delete all submission tests
        testQuerySet.delete()
        newTest = SubmissionTest.objects.create(
            submission=submission,
            testCase=result.testCase,
            passed=result.passed,
            logs=shortLogs,
            isError=result.isError,
        )
    else:
        newTest = SubmissionTest.objects.create(
            submission=submission,
            testCase=result.testCase,
            passed=result.passed,
            logs=shortLogs,
            isError=result.isError,
        )
    newTest.save()
    return newTest


testPattern = re.compile(r'^\d+$|^[^"]+?_@_[^"]+$')



def _processResult(result, assignment, user):
    # Check to make sure the result ID is in the proper format.
    if not testPattern.match(result["id"]):
        AutograderError(
            str(user),
            "Incorrect response format. Assignment: {}".format(assignment.id),
            "Result {}".format(str(result)),
        )
    else:
        if result["id"].isdigit():
            test_id = int(result["id"])
            try:
                testCase = TestCase.objects.get(id=test_id)
                testCategory = testCase.testCategory
            except:
                AutograderError(
                    str(user),
                    "Test id not found error: {}".format(assignment.id),
                    "Result".format(str(result)),
                )
                return
        else:
            # Case 2: TestOutput call in user-defined file
            # The id is a string of <testCategoryID>_@_<testDescription>
            # FIXME: This syntax feels ugly, but the user doesn't have ids to input
            [categoryName, testDescription] = result["id"].split("_@_")
            try:
                testCategory = TestCategory.objects.get(
                    name=categoryName, assignment=assignment
                )
            except:
                # This should already be created on the front end, but if not, create it
                testCategory = TestCategory.objects.create(
                    name=categoryName, assignment=assignment
                )
                testCategory.save()
            try:
                testCase = TestCase.objects.get(
                    testCategory=testCategory, description=testDescription
                )
            except:
                # This should already be created on the front end, but if not, create it
                testCase = TestCase.objects.create(
                    testCategory=testCategory,
                    description=testDescription,
                    type="file",
                    text="",
                )
                testCase.save()
        return TestResult(
            testCase,
            testCategory,
            result["passed"],
            _formatLogs(result["log"], testCase),
            result["isError"],
        )


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


## Format an individual testcase result
def _formatResult(caseID, categoryID, passed, logs, isError):
    return {
        "testCase": caseID,
        "testCategory": categoryID,
        "passed": passed,
        "logs": logs,
        "isError": isError,
    }


def _truncateLogs(logs):
    newLogs = (
        (logs[:MAX_LOG_LENGTH] + "... [Log length exceeded]")
        if len(logs) > MAX_LOG_LENGTH
        else logs
    )
    return newLogs


def _formatLogs(logs, testCase):
    # If we know the test case, then replace the test id with the test description
    if testCase:
        # check for regex of _test{id}.ext: line
        logs = re.sub(
            '(")?_test{}+.?.?.?.?.?"?(:|,)'.format(testCase.id),
            "[codePost Test] {}:".format(testCase.description),
            logs,
        )
        # check for regex of location: class _test51
        logs = re.sub(
            "location: class _test{}".format(testCase.id),
            "location: class [codePost Test] {}".format(testCase.description),
            logs,
        )
    # If we don't know the test case, replace it with a generic [codePost test]
    logs = re.sub(
        '(")?_test[0-9]+.?.?.?.?.?"?(:|,) line', "[codePost Test]: line", logs
    )
    logs = re.sub("_codePost_run.sh:", "Run Script:", logs)
    return logs


## Check for run and dump and, if so, output logs to a _tests.TXT file
def _runAndDump(environment, submission, logs):
    if environment.dumpMode and submission:
        try:
            testFile = File.objects.get(submission=submission, name="_tests.txt")
            testFile.code = logs
            testFile.save()
        except:
            testFile = File.objects.create(
                submission=submission,
                name="_tests.txt",
                extension=".txt",
                code=logs,
                path="",
                hiddenBeforePublish=True,
            )
            testFile.save()
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

#     sc = Slack()
#     sc.send_message("Upcoming Due Dates (24hrs)", attachments=attachments,
#                     channel="#user_notifications", logInDebug=True, debugChannel="richard-test")
