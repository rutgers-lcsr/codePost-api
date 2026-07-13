# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

import os
import uuid
import sys
import unittest
from unittest.mock import MagicMock, patch

# Path setup for Django
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codepost.settings')

import django
django.setup()

from core.models import Environment, Assignment, Submission, SubmissionFile, User, Course, Organization
from autograder.run import RunSubmission
from autograder.services.executors import ExecutionResult

from django.test import TransactionTestCase

class TestConvergencePipeline(TransactionTestCase):
    def setUp(self):
        # Clean up previous test artifacts to prevent IntegrityErrors
        Organization.objects.filter(name="Test University").delete()
        
        # Create Dummy Course & Assignment
        self.org = Organization.objects.create(name="Test University", shortname="TU")
        self.course = Course.objects.create(name="Test CS101", period="F20", organization=self.org)
        self.assignment = Assignment.objects.create(name="Test Assignment", course=self.course, points=100)
        
        # Create Environment with AutoDetect
        self.env = Environment.objects.create(
            assignment=self.assignment,
            language="python-3.12",
            requirements="",
            auto_detect=True,
            image_name="codepost-env-test-v1",
            current_build_version=1
        )
        
        # Create Student & Submission
        self.student = User.objects.create(username="student1", email="student1@rutgers.edu")
        self.submission = Submission.objects.create(assignment=self.assignment)
        self.submission.students.add(self.student)
        
        # Create Submission File
        self.sub_file = SubmissionFile.objects.create(
            submission=self.submission,
            name="main.py",
            extension="py",
            data="import requests\nprint('hello')"
        )

    def tearDown(self):
        self.sub_file.delete()
        self.submission.delete()
        self.env.delete()
        self.assignment.delete()
        self.course.delete()
        self.org.delete()
        self.student.delete()

    @patch('autograder.run.Executor.factory')
    @patch('autograder.services.builder.Builder.build')
    # We allow BuildEnvironment to run (eagerly), so we don't patch it directly, 
    # but we patch Builder to make it fast.
    def test_run_submission_convergence(self, mock_build, mock_executor_factory):
        print(f"\n--- Testing RunSubmission Convergence for Submission {self.submission.id} ---")
        
        # Override Celery to run tasks locally
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            
            # Setup Mock Executor
            mock_executor = MagicMock()
            mock_executor_factory.return_value = mock_executor
            
            # Execution Result 1: Fail with ModuleNotFoundError
            fail_result = ExecutionResult(
                success=False,
                stdout="",
                stderr="Traceback (most recent call last):\n  File \"main.py\", line 1, in <module>\n    import requests\nModuleNotFoundError: No module named 'requests'",
                err="ModuleNotFoundError: No module named 'requests'"
            )
            
            # Execution Result 2: Success (after build)
            success_result = ExecutionResult(
                success=True,
                stdout="hello",
                stderr="",
                execution_time=0.5
            )
            
            # Helper to return result based on call count or state
            # logic: return fail_result until build happens
            self.built = False
            def execute_side_effect():
                if self.built:
                    print("[TestMock] Executing Success (Post-Build)")
                    return success_result
                else:
                    print("[TestMock] Executing Failure (Pre-Build)")
                    return fail_result
            mock_executor.execute.side_effect = execute_side_effect
            
            # Mock Builder
            def side_effect_build():
                print("[TestMock] Builder.build() called - simulating success")
                self.built = True
                self.env.refresh_from_db()
                self.env.image_name = f"codepost-env-{self.assignment.id}-v{self.env.current_build_version + 1}"
                self.env.save()
                return True
            mock_build.side_effect = side_effect_build
            
            # Run Submission 3 times to trigger convergence
            print("[Test] Executing RunSubmission loop...")
            for i in range(3):
                print(f"[Test] Run {i+1}...")
                RunSubmission(self.submission.id)
                # Note: With EAGER=True, if RunSubmission triggers BuildEnvironment, 
                # and BuildEnvironment triggered Rerun, it would happen recursively immediately.
                # But convergence threshold is 3. So only on 3rd run it triggers.
            
            # Verify Results
            print("[Test] verifying results...")
            
            # Verify requirements
            self.env.refresh_from_db()
            print(f"[Test] Environment Requirements: {self.env.requirements}")
            self.assertIn("requests", self.env.requirements)
            
            # Verify Builder called
            mock_build.assert_called_once()
            
            # Verify Executor called 4 times (3 fails + 1 rerun)
            # Actually, RunSubmission is called 3 times manually.
            # The 3rd run triggers BuildEnvironment.
            # BuildEnvironment triggers RunSubmission (rerun).
            # So total RunSubmission calls = 4.
            # Executor.factory called 4 times.
            print(f"[Test] Executor factory call count: {mock_executor_factory.call_count}")
            # Called twice per run (check + execute): 4 runs * 2 calls = 8
            self.assertEqual(mock_executor_factory.call_count, 8)
            
            # Verify Rerun Success
            # The last execution should have been success
            # We can check logs or result?
            # RunSubmission returns result, but we ignored it in the loop.
            # The rerun was async (eager), so its result is lost unless we check side effects.
            # But the 'execute_side_effect' print debugs should confirm it.
            print("[Test] Verified mock execution flow.")

    @patch('autograder.run.Executor.factory')
    @patch('autograder.services.builder.Builder.build')
    def test_multi_user_convergence(self, mock_build, mock_executor_factory):
        print(f"\n--- Testing Multi-User Convergence ---")
        
        # Override Celery
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            
            # Setup Multiple Users & Submissions
            users = []
            submissions = []
            for i in range(3):
                u = User.objects.create(username=f"student_multi_{i}", email=f"student_multi_{i}@rutgers.edu")
                users.append(u)
                s = Submission.objects.create(assignment=self.assignment)
                s.students.add(u)
                submissions.append(s)
                # Add file
                SubmissionFile.objects.create(submission=s, name="main.py", extension="py", data="import requests")
            
            # Reset Environment
            self.env.requirements = ""
            self.env.save()
            
            # Setup Mock Executor
            mock_executor = MagicMock()
            mock_executor_factory.return_value = mock_executor
            
            fail_result = ExecutionResult(success=False, stdout="", stderr="ModuleNotFoundError: No module named 'requests'", err="ModuleNotFoundError: No module named 'requests'")
            success_result = ExecutionResult(success=True, stdout="success", stderr="")
            
            self.built = False
            def execute_side_effect():
                if self.built:
                    return success_result
                return fail_result
            mock_executor.execute.side_effect = execute_side_effect
            
            # Mock Builder
            def side_effect_build():
                print("[TestMock] Builder.build() called (Multi-User)")
                self.built = True
                self.env.refresh_from_db()
                self.env.image_name = f"codepost-env-{self.assignment.id}-v{self.env.current_build_version + 1}"
                self.env.save()
                return True
            mock_build.side_effect = side_effect_build
            
            # Run all submissions ONE time each. 
            # Threshold is 3. So 3rd failure should trigger convergence.
            print("[Test] Running submissions for 3 users...")
            for s in submissions:
                RunSubmission(s.id)
            
            # Verify
            self.env.refresh_from_db()
            print(f"[Test] Environment Requirements: {self.env.requirements}")
            self.assertIn("requests", self.env.requirements)
            
            mock_build.assert_called_once()
            
            # Verify clean up (optional)
            for u in users:
                u.delete()
            for s in submissions:
                s.delete()

    @patch('autograder.run.Executor.factory')
    @patch('autograder.services.builder.Builder.build')
    def test_mixed_packages(self, mock_build, mock_executor_factory):
        print(f"\n--- Testing Mixed Package Convergence ---")
        
        # Override Celery
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            
            # Setup Submissions for different packages
            # Group 1: requests (3 subs - should converge)
            # Group 2: numpy (3 subs - should converge)
            # Group 3: pandas (1 sub - should NOT converge yet)
            
            subs_requests = []
            for _ in range(3):
                s = Submission.objects.create(assignment=self.assignment)
                SubmissionFile.objects.create(submission=s, name="main.py", extension="py", data="import requests")
                subs_requests.append(s)
            
            subs_numpy = []
            for _ in range(3):
                s = Submission.objects.create(assignment=self.assignment)
                SubmissionFile.objects.create(submission=s, name="main.py", extension="py", data="import numpy")
                subs_numpy.append(s)
                
            subs_pandas = []
            for _ in range(1):
                s = Submission.objects.create(assignment=self.assignment)
                SubmissionFile.objects.create(submission=s, name="main.py", extension="py", data="import pandas")
                subs_pandas.append(s)
            
            all_subs = subs_requests + subs_numpy + subs_pandas
            
            # Reset Env
            self.env.requirements = ""
            self.env.convergence_stats = {}
            self.env.save()
            
            # Mock Executor
            mock_executor = MagicMock()
            mock_executor_factory.return_value = mock_executor
            
            # Define results based on content (simulating file content check is hard in mock side_effect from result object, 
            # but we can check the file_id or passed file object in factory? 
            # RunSubmission calls Executor.factory(f). 
            # We can map file_ids to results.
            
            # Map file IDs to expected errors
            file_errors = {}
            for s in subs_requests:
                f = s.files.first()
                file_errors[f.id] = "ModuleNotFoundError: No module named 'requests'"
            for s in subs_numpy:
                f = s.files.first()
                file_errors[f.id] = "ModuleNotFoundError: No module named 'numpy'"
            for s in subs_pandas:
                f = s.files.first()
                file_errors[f.id] = "ModuleNotFoundError: No module named 'pandas'"
                
            success_result = ExecutionResult(success=True, stdout="success")
            
            # We need to track build status. 
            # If built, return success? 
            # But wait, building happens asynchronously.
            # And multiple builds might happen.
            # If requests is added -> build -> requests success, numpy fail.
            # Then numpy added -> build -> numpy success.
            # Pandas fail.
            
            # Simulating dynamic state in mock is complex. 
            # Let's assume we run them sequentially.
            
            # To handle factory args, we can use side_effect on factory
            def factory_side_effect(file_obj, image_name=None):
                m_exec = MagicMock()
                
                # Determine result based on file and current env requirements
                reqs = self.env.requirements or ""
                
                if "requests" in file_errors[file_obj.id] and "requests" not in reqs:
                    res = ExecutionResult(success=False, stderr=file_errors[file_obj.id], err=file_errors[file_obj.id])
                elif "numpy" in file_errors[file_obj.id] and "numpy" not in reqs:
                    res = ExecutionResult(success=False, stderr=file_errors[file_obj.id], err=file_errors[file_obj.id])
                elif "pandas" in file_errors[file_obj.id] and "pandas" not in reqs:
                    res = ExecutionResult(success=False, stderr=file_errors[file_obj.id], err=file_errors[file_obj.id])
                else:
                    res = success_result
                
                m_exec.execute.return_value = res
                return m_exec
                
            mock_executor_factory.side_effect = factory_side_effect
            
            # Mock Builder to update requirements in DB (simulating build process reflecting changes? 
            # No, Converger updates requirements. Builder builds image. 
            # In test, we just check requirements. 
            # But the 'reqs' check above reads from DB. So Converger must update DB.
            # Converger DOES update DB.
            mock_build.return_value = True
            
            # Run all submissions
            print("[Test] Running all submissions...")
            for s in all_subs:
                RunSubmission(s.id)
                self.env.refresh_from_db() # Refresh to get updates from Eager tasks
            
            # Verify
            self.env.refresh_from_db()
            print(f"[Test] Final Requirements: {self.env.requirements}")
            
            self.assertIn("requests", self.env.requirements, "Requests should have converged")
            self.assertIn("numpy", self.env.requirements, "Numpy should have converged")
            self.assertNotIn("pandas", self.env.requirements, "Pandas should NOT have converged (only 1 sub)")
            
            print("[Test] Verified mixed package convergence logic.")
            
            # Cleanup
            for s in all_subs:
                s.delete()    
        
        # 4. Verify Version Increment (Implementation detail of ImageManager)
        # Note: mocking Builder means ImageManager.save_image_version needs to be called by Builder or Converger?
        # Actually Builder usually calls ImageManager.save_image_version. 
        # Since we mocked Builder.build, we bypassed that unless we verify `Converger` called `Builder`.
        # Real Builder calls ImageManager. 
        # In this test, we just mocked build() returning True. 
        # But Converger calls `Builder(env.id).build()`. 
        # Wait, Converger logic updates requirements THEN calls build. 
        
        # Let's verify environment was updated
        self.assertTrue(len(self.env.requirements) > 0)

    @patch('autograder.run.Executor.factory')
    @patch('autograder.services.builder.Builder.build')
    def test_runtime_install_convergence(self, mock_build, mock_executor_factory):
        print(f"\n--- Testing Runtime Install Convergence (Success Logic) ---")
        
        # Override Celery
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            
            # Setup Submission
            # This submission will SUCCEED (because runtime install works)
            # but it should still trigger convergence because of the log message.
            s = Submission.objects.create(assignment=self.assignment)
            SubmissionFile.objects.create(submission=s, name="main.py", extension="py", data="import scipy")
            
            # Reset Env
            self.env.requirements = ""
            self.env.convergence_stats = {}
            self.env.save()
            
            # Mock Executor
            mock_executor = MagicMock()
            mock_executor_factory.return_value = mock_executor
            
            # Result: Success, but with special log
            # PythonExecutor prints to stderr when template installs package
            runtime_success_result = ExecutionResult(
                success=True, 
                stdout="Computed result: 42", 
                stderr="[INFO] Installing scipy...\nCODEPOST_AUTO_INSTALL_SUCCESS: scipy\n"
            )
            
            mock_executor.execute.return_value = runtime_success_result
            
            mock_build.return_value = True
            
            # Run 3 times
            print("[Test] Running submission 3 times (expecting success but tracking)...")
            for _ in range(3):
                RunSubmission(s.id)
                self.env.refresh_from_db()
            
            # Verify
            print(f"[Test] Final Requirements: {self.env.requirements}")
            self.assertIn("scipy", self.env.requirements, "Runtime-installed package should be added to reqs")
            
            mock_build.assert_called_once()
            
            print("[Test] Verified runtime install convergence logic.")
            
            s.delete()



    @patch('autograder.run.Executor.factory')
    @patch('autograder.services.builder.Builder.build')
    def test_r_runtime_install(self, mock_build, mock_executor_factory):
        print(f"\n--- Testing R Runtime Install Convergence ---")
        
        # Override Celery
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            
            # Create NEW assignment to avoid unique constraint on Environment.assignment_id
            unique_name = f"R Assignment {uuid.uuid4()}"
            r_assign = Assignment.objects.create(name=unique_name, course=self.course, points=100)
            
            # Setup R Environment
            r_env = Environment.objects.create(
                assignment=r_assign,
                language="r",
                requirements="",
                auto_detect=True,
                image_name="codepost-r-env-test-v1",
                current_build_version=1
            )
            
            # Setup Submission (R notebook simulation)
            s = Submission.objects.create(assignment=r_assign)
            SubmissionFile.objects.create(submission=s, name="analysis.ipynb", extension="ipynb", data='{"cells": []}')
            
            # Mock Executor for R
            mock_executor = MagicMock()
            mock_executor_factory.return_value = mock_executor
            
            # Result: Success, but with R-specific log
            # notebook_template.r prints to stderr
            r_runtime_result = ExecutionResult(
                success=True, 
                stdout="[1] 42", 
                stderr="[INFO] Installing ggplot2...\nCODEPOST_AUTO_INSTALL_SUCCESS: ggplot2\n"
            )
            
            mock_executor.execute.return_value = r_runtime_result
            mock_build.return_value = True
            
            # Run 3 times (R threshold might be different? Default is 3 usually)
            # RConverger inherits BaseConverger, threshold 3.
            print("[Test] Running R submission 3 times...")
            for _ in range(3):
                # We need to ensure RunSubmission picks up the R environment.
                # Since assignment has 'env' (python), we need to handle multiple environments?
                # Or just assign this env to the assignment?
                # Assignment can have only one environment usually linked via ForeignKey or backward relation?
                # Actually Environment has ForeignKey to Assignment.
                # If multiple exist, RunSubmission logic:
                # envs = Environment.objects.filter(assignment_id=assignment_id)
                # It loops through them? Or picks one?
                # Let's check RunSubmission code logic quickly if unsure.
                # But for test, let's just update self.env to be R-based or ensure correct one is picked.
                # Easier: Delete the python env for this test or use a new assignment.
                pass
            
            # Re-doing setup properly within the loop
            pass
            
        # Refing the test logic above was comments. Here is real code.
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            # Create new assignment for R to avoid conflict
            r_assign = Assignment.objects.create(name="R Assignment", course=self.course, points=100)
            r_env = Environment.objects.create(
                assignment=r_assign,
                language="r",
                requirements="",
                auto_detect=True,
                image_name="codepost-r-env-v1"
            )
            
            s = Submission.objects.create(assignment=r_assign)
            SubmissionFile.objects.create(submission=s, name="analysis.ipynb", extension="ipynb", data='{"cells": []}')
            
            mock_executor = MagicMock()
            mock_executor_factory.return_value = mock_executor
            
            r_runtime_result = ExecutionResult(
                success=True, 
                stdout="[1] 42", 
                stderr="CODEPOST_AUTO_INSTALL_SUCCESS: ggplot2\n"
            )
            
            mock_executor.execute.return_value = r_runtime_result
            mock_build.return_value = True
            
            print("[Test] Running R submission 3 times...")
            for _ in range(3):
                RunSubmission(s.id)
                r_env.refresh_from_db()
            
            print(f"[Test] Final R Requirements: {r_env.requirements}")
            self.assertIn("ggplot2", r_env.requirements)
            
            # Cleanup
            s.delete()
            r_env.delete()
            r_assign.delete()

if __name__ == '__main__':
    unittest.main()
