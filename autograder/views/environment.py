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

from autograder.testUtils.parse import parseTests, writeCmdScript
from autograder.testUtils.ag_logging import AutograderError, AutograderBuild

from autograder.run import RunAll, Run, RunType, BuildEnvironment

from autograder.testUtils.buildHelpers import createDockerFile

import requests
import json


from autograder.services.builder import Builder

class EnvironmentViewSet(ListProtectedViewSet):
    """
    list:
    Return a list of all the testFiles.
    """

    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = (IsAuthenticated, EnvironmentPermissions)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        from autograder.services.detection import detect_environment_bootstrap
        """
        Custom update behavior:
        If switching to Auto-Detect (auto_detect=True), explicitly clear key fields
        to trigger the 'Cold Start' heuristic logic in RunSubmission.
        """
        validated_data = serializer.validated_data
        
        # Check if auto_detect is explicitly being set to True
        if validated_data.get('auto_detect') is True:
            # We must clear 'language' so RunSubmission logic (if not env.language) activates
            # We must clear 'image_name' so it rebuilds
            # We reset 'build_status' to 0 (Pending) to reflect 'Not Built'
            environment = serializer.save(
                language="", # Empty string matches NOT NULL constraint, and is falsy for checks
                image_name=None,
                build_status=0,
                build_logs="Reset for Auto-Detection...",
                dockerfile="", # Clear manual dockerfile if any
                requirements="" # Reset requirements to allow cleaner convergence? Or keep? -> Clear for full reset.
            )
            
            # Use bootstrap logic to try and detect immediately from assignment files or submissions
            detect_environment_bootstrap(environment.assignment.id)
        else:
            serializer.save()

    #################################### Build ###############################################
    @action(detail=True, methods=["PATCH"])
    def build(self, request, pk=None):
        environment = self.get_object()
        
        # Update language if provided
        if "language" in request.data:
            environment.language = request.data["language"]
        
        # Update other fields if provided (e.g. requirements, dockerfile)
        if "requirements" in request.data:
            environment.requirements = request.data["requirements"]
        if "dockerfile" in request.data:
            environment.dockerfile = request.data["dockerfile"]
        if "dockerRunInstructions" in request.data:
            environment.dockerRunInstructions = request.data["dockerRunInstructions"]
        if "buildType" in request.data:
            environment.build_type = request.data["buildType"]
        if "autoDetect" in request.data:
            environment.auto_detect = request.data["autoDetect"]
            
        # Set status to building immediately so UI reflects it
        environment.build_status = 1
        environment.build_logs = "Queued for build...\n"
        environment.save()

        # Run Builder asynchronously via Celery
        try:
            x = BuildEnvironment.delay(environment.id)
            return Response({"task": x.task_id, "status": "queued"})
        except Exception as e:
            return Response({"task": "async_failed", "error": str(e)}, status=500)

    @action(detail=True, methods=["GET"])
    def build_status(self, request, pk=None):
        try:
            environment = self.get_object()
            
            # Helper to generate the full dockerfile content logic
            full_date_dockerfile = createDockerFile(
                environment.language,
                environment.buildType,
                environment.dockerfile,
                environment.dockerRunInstructions,
                environment.id,
            )

            # Return status directly from the database fields we added
            # Serialize status
            data = {
                "inProgress": bool(environment.build_status == 1),
                "isSuccess": bool(environment.build_status == 2),
                "logs": environment.build_logs or "",
                "dockerfile": full_date_dockerfile or "",
                "lastBuilt": environment.last_built
            }
            return Response(data)
        except Exception as e:
            return Response({"error": str(e), "inProgress": False, "isSuccess": False, "logs": f"Error fetching status: {e}"}, status=500)

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
            dependencies_file_content=environment.requirements,
        )
        return Response(dockerfile)

    @action(detail=True, methods=["POST"])
    def preview(self, request, pk=None):
        """
        Generate a preview of the Dockerfile based on provided parameters,
        without saving changes to the database.
        """
        try:
            environment = self.get_object()
            
            # Use provided data or fall back to current environment state
            language = request.data.get("language", environment.language)
            build_type = request.data.get("buildType", environment.buildType)
            custom_dockerfile = request.data.get("dockerfile", environment.dockerfile)
            
            # dockerRunInstructions might be passed as a list of strings
            # or we might need to parse them if passed differently.
            # Assuming list of strings as per EnvironmentSerializer/frontend
            docker_run_instructions = request.data.get("dockerRunInstructions", [])
            if not isinstance(docker_run_instructions, list):
                docker_run_instructions = []
                
            requirements_content = request.data.get("requirements", environment.requirements)

            preview_content = createDockerFile(
                language or "python-3.7",
                build_type or "default",
                custom_dockerfile or "",
                docker_run_instructions,
                environment.id,
                dependencies_file_content=requirements_content or "",
            )
            return Response(preview_content)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(str(e), status=400)

    @action(detail=True, methods=["GET"])
    def eject(self, request, pk=None):
        """
        Generates a "Reproduction Kit" for debugging locally.
        Returns the components needed to run tests exactly as the autograder does.
        """
        user = self.request.user
        environment = self.get_object()
        assignment = environment.assignment

        # 1. Dockerfile
        dockerfile = createDockerFile(
            environment.language,
            environment.buildType,
            environment.dockerfile,
            environment.dockerRunInstructions,
            environment.id,
            dependencies_file_content=environment.requirements,
        )

        # 2. Test Definitions (serialized)
        testCase_types_to_exclude = ["file", "external"]
        tests_query = TestCase.objects.filter(testCategory__assignment=assignment).exclude(
            type__in=testCase_types_to_exclude
        )
        
        # Simple serialization for the kit
        tests_data = []
        for t in tests_query:
            tests_data.append({
                "id": t.id,
                "description": t.description,
                "type": t.type,
                "command": t.command, # meaningful for CLI tests
                "input": t.input,
                "expectedOutput": t.expectedOutput,
                "fileName": t.fileName,
                # "targetCellId": t.targetCellId # Future: support notebook
            })

        # 3. Runner Script (Python)
        # This script mimics the basic behavior of the PythonExecutor/JavaExecutor
        # but simplified for local running via subprocess.
        runner_script = r'''import json
import subprocess
import os
import sys

IMAGE_NAME = "codepost-debug-env"

def run_command(cmd, input_str=None):
    """Runs a shell command and returns stdout/stderr"""
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True
    )
    stdout, stderr = process.communicate(input=input_str)
    return process.returncode, stdout, stderr

def main():
    print(f"--- codePost Debug Kit ---")
    
    # 1. Build Image
    if not os.path.exists("Dockerfile"):
        print("Error: Dockerfile not found.")
        return

    print(f"Building Docker image '{IMAGE_NAME}' (this may take a moment)...")
    try:
        subprocess.check_call(["docker", "build", "-t", IMAGE_NAME, "."])
    except subprocess.CalledProcessError:
        print("Error: Docker build failed.")
        return

    # 2. Load Tests
    try:
        with open("tests.json") as f:
            tests = json.load(f)
    except FileNotFoundError:
        print("Error: tests.json not found.")
        return

    # 3. Run Tests
    for test in tests:
        print(f"\nRunning Test: {test['description']} ({test['type']})")
        
        # Command Construction logic (Simplified)
        # Assuming generic run command or filename execution
        # Note: This logic needs to match the Executor's logic for the specific language!
        # For now, implementing a generic runner that tries to run the file.
        
        target_file = test.get('fileName')
        if not target_file:
            # Try to find a file in directory?
            print("  Skipping: No target file inferred.")
            continue
            
        # Docker Run Command
        # Mount current directory to /work
        # Run the command based on file extension (naive implementation for kit)
        
        base_cmd = ""
        if target_file.endswith(".py"):
             base_cmd = f"python {target_file}"
        elif target_file.endswith(".java"):
             # Compile and run
             cls = os.path.splitext(target_file)[0]
             base_cmd = f"javac {target_file} && java {cls}"
        elif target_file.endswith(".c"):
             base_cmd = f"gcc {target_file} -o main && ./main"
        else:
             base_cmd = f"./{target_file}" # Try execution
             
        # Inject inputs if I/O test
        input_data = test.get('input', '')
        
        docker_cmd = f"docker run --rm -i -v \"$(pwd):/work\" -w /work {IMAGE_NAME} sh -c '{base_cmd}'"
        
        print(f"  Command: {docker_cmd}")
        ret, stdout, stderr = run_command(docker_cmd, input_str=input_data)
        
        print(f"  Result: {'PASS' if ret == 0 else 'FAIL'} (Exit Code: {ret})")
        print(f"  Stdout:\n{stdout}")
        print(f"  Stderr:\n{stderr}")

if __name__ == "__main__":
    main()
'''

        toRet = {
            "Dockerfile": dockerfile,
            "tests.json": json.dumps(tests_data, indent=2),
            "run_tests.py": runner_script
        }

        return Response(toRet)
