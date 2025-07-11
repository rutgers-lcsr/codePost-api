from core.models import Environment, TestCase, TestCategory, Submission
from autograder.serializers.environment import EnvironmentSerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from autograder.permissions.permissions import EnvironmentPermissions

from rest_framework.decorators import action
from core.permissions.helpers import isAuthenticated
from core.permissions.helpers import (
    returnNotAuthorized,
    returnForbidden,
    returnNotFound,
)
from core.permissions.helpers import isCourseAdmin, isStudentOfSub, isStaffOfSub
from rest_framework import serializers
from rest_framework.response import Response

from codepost.settings import AUTOGRADER_URL
from autograder.testUtils.compileTemplates import get_compile_template

from autograder.testUtils.parse import parseTests, parseSourceFile, writeCmdScript
from autograder.testUtils.logging import AutograderError, AutograderBuild

from autograder.run import RunAll, Run, RunType

from autograder.testUtils.buildHelpers import createDockerFile, buildSpecs

import requests
import json


class EnvironmentViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the testFiles.

    create:
    Create a new testFile.

    retrieve:
    Return the given testFile.

    update:
    Update a testFile.

    partial_update:
    Update a testFile.

    delete:
    Delete a testFile.
    """

    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = (IsAuthenticated, EnvironmentPermissions)

    #################################### Build ###############################################
    @action(detail=True, methods=["PATCH"])
    def build(self, request, pk=None):
        user = self.request.user
        environment = self.get_object()
        assignment = environment.assignment
        dependencies = environment.dockerRunInstructions
        customDockerCommands = environment.dockerfile

        old_language = environment.language
        language = request.data["language"]
        environment.language = language
        environment.save()

        buildType = environment.buildType
        dockerfile = createDockerFile(
            language, buildType, customDockerCommands, dependencies, environment.id
        )

        # We pass in a build counter higher than the current counter to tag the image if it builds successfully
        payload = {
            "dockerfile": dockerfile,
            "assignment": assignment.id,
            "buildID": environment.buildID + 1,
        }
        r = requests.post(AUTOGRADER_URL + "/build/", json=payload)

        try:
            r = r.json()
        except:
            AutograderError(
                str(request.user),
                "Build Failed {};{}".format(environment.id, language),
                r.text,
            )

        environment.buildID = environment.buildID + 1
        if (
            not environment.compileText
            or environment.compileText == get_compile_template(old_language)
        ):
            # If the user has already set a compile text, we don't want to reset it
            environment.compileText = get_compile_template(language)

        environment.save()
        return Response({})

    @action(detail=True, methods=["GET"])
    def status(self, request, pk=None):
        user = self.request.user
        environment = self.get_object()
        assignment = environment.assignment

        r = requests.post(
            AUTOGRADER_URL + "/buildStatus/", json={"assignment": assignment.id}
        )

        try:
            r = r.json()
        except:
            AutograderError(
                str(request.user),
                "Build status not json {};{}".format(
                    environment.id, environment.language
                ),
                r.text,
            )

        return Response(r)

    #################################### Run ###############################################
    @action(detail=True, methods=["PATCH"])
    def runAll(self, request, pk=None):
        user = self.request.user
        environment = self.get_object()
        assignment = environment.assignment
        course = assignment.course
        sendEmail = (
            request.data["sendEmail"]
            if "sendEmail" in request.data
            and isinstance(request.data["sendEmail"], bool)
            else False
        )

        if not environment.language:
            raise serializers.ValidationError(
                "Language has not been specified for this environment."
            )

        environment.isRunning = True
        environment.save()

        x = RunAll.delay(environment.id, str(request.user), sendEmail)
        return Response({"task": x.task_id})

    @action(detail=True, methods=["PATCH"])
    def run(self, request, pk=None):
        user = self.request.user
        environment = Environment.objects.get(id=pk)
        assignment = environment.assignment
        course = assignment.course
        submission = self.request.data.get("submission", None)
        simulate = self.request.data.get("simulate", True)
        fileOverrides = None
        # an optional parameter for admins to pass in if they want tests to be run as a student
        # For students, this parameter does not apply: tests are always run in exposed only mode
        exposedOnly = self.request.data.get("exposedOnly", False)

        if not isAuthenticated(user):
            return returnNotAuthorized()

        if submission:
            try:
                submission = Submission.objects.get(id=submission)
            except:
                raise serializers.ValidationError("Not a valid submission.")

        if not (
            isCourseAdmin(user, course)
            or (submission and isStudentOfSub(user, submission))
            or isStaffOfSub(user, submission)
        ):
            return returnForbidden()

        if not environment.language:
            raise serializers.ValidationError(
                "Environment has not been created for this asignment."
            )

        # Check for file overrides. Here we don't check for the assignment setting for simplicity
        # There's no attack vector in allowing students to submit file overrides. They can't change their code
        fileOverrides = self.request.data.get("files", None)
        if fileOverrides != None:
            fileOverrides = json.loads(fileOverrides)

        if submission:
            # If simulate is on or there are file overrides, don't actually create submission tests
            createSubmissionTests = (
                False if (simulate or fileOverrides != None) else True
            )
            if isCourseAdmin(user, course) or isStaffOfSub(user, submission):
                x = Run.delay(
                    user=str(request.user),
                    environmentID=environment.id,
                    type=json.dumps(RunType.Submission),
                    pk=submission.id,
                    createSubmissionTests=createSubmissionTests,
                    exposed_only=exposedOnly,
                    run_by_role="instructor",
                )
                return Response({"task": x.task_id})
            elif isStudentOfSub(user, submission):
                # Check to see if test runs have been exceeded. If so, return a validation error
                if (
                    environment.maxStudentTestRuns
                    and submission.testRunsCompleted >= environment.maxStudentTestRuns
                ):
                    raise serializers.ValidationError(
                        "Number of allowable test runs for this submission has hit the max."
                    )

                x = Run.delay(
                    user=str(request.user),
                    environmentID=environment.id,
                    type=json.dumps(RunType.Submission),
                    pk=submission.id,
                    createSubmissionTests=createSubmissionTests,
                    exposed_only=True,
                    fileOverrides=fileOverrides,
                    run_by_role="student",
                )
                return Response({"task": x.task_id})

        # Running on solution code
        x = Run.delay(
            user=str(request.user),
            environmentID=environment.id,
            type=json.dumps(RunType.Submission),
            pk=None,
            run_by_role="instructor",
        )
        return Response({"task": x.task_id})

    #################################### Export ###############################################
    @action(detail=True, methods=["GET"])
    def dockerfile(self, request, pk=None):
        user = self.request.user
        environment = self.get_object()
        dockerfile = createDockerFile(
            environment.language,
            environment.buildType,
            environment.dockerfile,
            environment.dockerRunInstructions,
            environment.id,
        )
        return Response(dockerfile)

    @action(detail=True, methods=["GET"])
    def eject(self, request, pk=None):
        user = self.request.user
        environment = self.get_object()
        assignment = environment.assignment

        files = []
        for f in environment.solutionFiles.all():
            files.append({"name": f.name, "code": f.code})

        # Get all non external and file-defined test cases
        testCase_types_to_exclude = ["file", "external"]
        tests = TestCase.objects.filter(testCategory__assignment=assignment).exclude(
            type__in=testCase_types_to_exclude
        )
        templates = parseTests(tests, environment.language)

        sourceFiles = environment.sourceFiles.all()
        sourceFileTemplates = [parseSourceFile(sF) for sF in sourceFiles]

        script = writeCmdScript(
            templates,
            sourceFileTemplates,
            environment.compileText,
            environment.language,
        )

        toRet = {
            "templates": templates + sourceFileTemplates,
            "main": script,
            "id": environment.id,
        }

        return Response(toRet)
