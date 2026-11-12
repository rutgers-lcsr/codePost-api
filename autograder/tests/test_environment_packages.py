# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""Auto-detect package lists: the listed requirements must be what the image is built from.

Regression net for the November 2026 audit: `requirements` was rewritten from each
submission's imports with no rebuild, the builder's stale save wiped the image history, the
converger's stability gate kept it from learning, and rollback had nothing to restore.
"""
from unittest import mock

import factory
from django.core.management import call_command
from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from autograder.run import BuildEnvironment, RebuildEnvironmentIfStale
from autograder.services import environment_packages as packages
from autograder.services.autodetector import Autodetector
from autograder.services.builder import Builder
from autograder.services.converger import Converger
from autograder.services.image_manager import ImageManager
from core.models import AssignmentFile, Environment, SubmissionFile, TestCategory
from core.tests.factories import AssignmentFactory, CourseFactory, SubmissionFactory

INSTALLED = "CODEPOST_AUTO_INSTALL_SUCCESS: {}\n"


def _pypi(exists=True):
    return mock.patch.object(Autodetector, 'check_pypi_existence', return_value=exists)


def _no_rebuild():
    return mock.patch.object(packages, 'schedule_rebuild', return_value=True)


class _EnvCase(TestCase):
    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.assignment = AssignmentFactory()
            self.submission = SubmissionFactory(assignment=self.assignment, files=None)
        SubmissionFile.objects.filter(submission__assignment=self.assignment).delete()  # the factory adds .java files
        self.env = Environment.objects.create(
            assignment=self.assignment, auto_detect=True, language='python-3.12')

    def _asg_file(self, name, data):
        with factory.django.mute_signals(post_save):
            return AssignmentFile.objects.create(
                assignment=self.assignment, name=name, data=data, extension=name.rsplit('.', 1)[-1])

    def _sub_file(self, name, data, submission=None):
        with factory.django.mute_signals(post_save):
            return SubmissionFile.objects.create(
                submission=submission or self.submission, name=name, data=data,
                extension=name.rsplit('.', 1)[-1])

    def _submissions(self, count):
        with factory.django.mute_signals(post_save):
            return [SubmissionFactory(assignment=self.assignment, files=None) for _ in range(count)]


class EffectiveRequirementsTests(_EnvCase):

    def test_union_of_the_lists_minus_excluded(self):
        self.env.detected_requirements = "numpy\npandas"
        self.env.learned_packages = ["scipy"]
        self.env.pinned_packages = ["requests"]
        self.env.excluded_packages = ["pandas"]
        self.assertEqual("numpy\nrequests\nscipy", packages.effective_requirements(self.env))

    def test_a_pinned_version_replaces_the_detected_line(self):
        self.env.detected_requirements = "numpy"
        self.env.pinned_packages = ["NumPy==1.26.4"]
        self.assertEqual("NumPy==1.26.4", packages.effective_requirements(self.env))

    def test_python_names_compare_case_and_separator_insensitively(self):
        self.env.detected_requirements = "scikit_learn"
        self.env.excluded_packages = ["Scikit-Learn"]
        self.assertEqual("", packages.effective_requirements(self.env))

    def test_each_package_reports_where_it_came_from(self):
        self.env.detected_requirements = "numpy"
        self.env.learned_packages = ["scipy"]
        self.env.pinned_packages = ["pandas<3"]
        packages.refresh_requirements(self.env)
        self.assertEqual(
            {"numpy": "detected", "scipy": "learned", "pandas": "pinned"},
            {p["name"]: p["origin"] for p in packages.describe_packages(self.env)})

    def test_validation_rejects_options_urls_and_other_languages(self):
        with _pypi():
            self.assertEqual("numpy>=1.26,<3", packages.validate_requirement('python-3.12', ' numpy >= 1.26, <3 '))
            for bad in ("--index-url http://x", "git+https://x/y", "numpy; rm -rf /", ""):
                with self.assertRaises(packages.InvalidPackage):
                    packages.validate_requirement('python-3.12', bad)
            with self.assertRaises(packages.InvalidPackage):
                packages.validate_requirement('java-17', 'gson')
        self.assertEqual("ggplot2", packages.validate_requirement('r-4', 'ggplot2'))

    def test_a_package_missing_from_pypi_is_refused_as_a_typo(self):
        with _pypi(False), self.assertRaises(packages.InvalidPackage) as ctx:
            packages.validate_requirement('python-3.12', 'pandass')
        self.assertIn('PyPI', str(ctx.exception))


class DetectionOwnsOnlyItsListTests(_EnvCase):

    def test_a_submissions_imports_do_not_rewrite_the_list(self):
        self._asg_file('starter.py', 'import numpy')
        self._sub_file('a.py', 'import pandas\nimport panda')

        with _pypi(), _no_rebuild():
            Autodetector.detect_and_update(self.submission)

        self.env.refresh_from_db()
        self.assertEqual('numpy', self.env.detected_requirements)
        self.assertEqual('numpy', self.env.requirements)

    def test_test_script_imports_are_detected(self):
        TestCategory.objects.create(assignment=self.assignment, name='t', testScript='import scipy')

        with _pypi(), _no_rebuild():
            Autodetector.detect_and_update(assignment=self.assignment)

        self.env.refresh_from_db()
        self.assertEqual('scipy', self.env.requirements)

    def test_redetection_keeps_learned_pinned_and_excluded(self):
        self._asg_file('starter.py', 'import numpy\nimport pandas')
        self.env.learned_packages = ['scipy']
        self.env.pinned_packages = ['requests==2.32.3']
        self.env.excluded_packages = ['pandas']
        self.env.save()

        with _pypi(), _no_rebuild():
            Autodetector.detect_and_update(assignment=self.assignment, force=True)

        self.env.refresh_from_db()
        self.assertEqual('numpy\nrequests==2.32.3\nscipy', self.env.requirements)

    def test_a_changed_list_queues_a_rebuild_but_the_build_itself_does_not(self):
        self._asg_file('starter.py', 'import numpy')

        with _pypi(), _no_rebuild() as schedule:
            Autodetector.detect_and_update(assignment=self.assignment)
            schedule.assert_called_once_with(self.env.id, "detected")
            schedule.reset_mock()

            Autodetector.detect_and_update(assignment=self.assignment)  # nothing changed
            self._asg_file('more.py', 'import scipy')
            Autodetector.detect_and_update(assignment=self.assignment, force=True)  # the build asking
            schedule.assert_not_called()

    def test_whole_file_manifests_still_read_the_submission(self):
        self.env.language = 'node-20'
        self.env.save()
        SubmissionFile.objects.filter(submission__assignment=self.assignment).delete()
        self._sub_file('a.js', "require('express')")

        with _no_rebuild() as schedule:
            Autodetector.detect_and_update(self.submission)

        self.env.refresh_from_db()
        self.assertIn('express', self.env.requirements)
        self.assertEqual('', self.env.detected_requirements)
        schedule.assert_not_called()


class LearnFromRunsTests(_EnvCase):

    def _run(self, submission, logs):
        return Converger.analyze_and_converge(self.env.id, logs, submission_id=submission.id)

    def test_three_distinct_submissions_teach_a_package_and_queue_one_rebuild(self):
        subs = self._submissions(3)
        with _pypi(), _no_rebuild() as schedule:
            for sub in subs[:2]:
                self.assertEqual((False, set(), []), self._run(sub, INSTALLED.format('pandas')))
            schedule.assert_not_called()

            self.assertEqual((False, {'pandas'}, []), self._run(subs[2], INSTALLED.format('pandas')))
            schedule.assert_called_once_with(self.env.id, "learned")

        self.env.refresh_from_db()
        self.assertEqual(['pandas'], self.env.learned_packages)
        self.assertEqual('pandas', self.env.requirements)
        self.assertEqual('learned', self.env.convergence_stats['pandas']['status'])

    def test_one_submission_rerun_many_times_counts_once(self):
        with _pypi(), _no_rebuild():
            for _ in range(5):
                self._run(self.submission, INSTALLED.format('pandas'))

        self.env.refresh_from_db()
        self.assertEqual([], self.env.learned_packages)
        self.assertEqual([{"name": "pandas", "count": 1, "status": "counting"}],
                         packages.pending_packages(self.env))

    def test_a_high_success_rate_no_longer_stops_learning(self):
        """The old stability gate: 5+ runs at 80% success returned before counting anything.
        A run-time install makes the run pass, so those were exactly the stale environments."""
        Environment.objects.filter(pk=self.env.pk).update(total_runs=272, successful_runs=267)
        with _pypi(), _no_rebuild():
            for sub in self._submissions(3):
                self._run(sub, INSTALLED.format('pandas'))

        self.env.refresh_from_db()
        self.assertEqual(['pandas'], self.env.learned_packages)

    def test_a_failed_import_maps_to_its_package_and_is_rerun_after_the_build(self):
        subs = self._submissions(3)
        with _pypi(), _no_rebuild():
            for sub in subs:
                self._run(sub, "ModuleNotFoundError: No module named 'sklearn'")

        self.env.refresh_from_db()
        self.assertEqual(['scikit-learn'], self.env.learned_packages)
        self.assertEqual(sorted(s.id for s in subs),
                         packages.settle_learned_packages(self.env.id, build_succeeded=True))
        self.env.refresh_from_db()
        self.assertEqual({}, self.env.convergence_stats)

    def test_excluded_listed_local_and_unknown_packages_are_not_learned(self):
        self._asg_file('helper.py', 'x = 1')
        self.env.excluded_packages = ['pandas']
        self.env.detected_requirements = 'numpy'
        self.env.requirements = 'numpy'
        self.env.built_requirements = 'numpy'
        self.env.image_name = 'codepost-env-1:1'
        self.env.save()
        logs = "".join(INSTALLED.format(p) for p in ('pandas', 'numpy', 'helper', 'seniors'))

        with _pypi(False), _no_rebuild() as schedule:
            for sub in self._submissions(3):
                self._run(sub, logs)
            schedule.assert_not_called()

        self.env.refresh_from_db()
        self.assertEqual([], self.env.learned_packages)
        self.assertEqual('numpy', self.env.requirements)
        self.assertEqual([{"name": "seniors", "count": 3, "status": "not_found"}],
                         packages.pending_packages(self.env))

    def test_installing_a_listed_package_at_run_time_means_the_image_is_behind(self):
        """Prod, cs210 'Classwork Submissions': the list said pandas, the image had none."""
        self.env.detected_requirements = 'pandas'
        self.env.requirements = 'pandas'
        self.env.image_name = 'codepost-env-77:1788884683'
        self.env.save()  # built_requirements unknown, as on every environment built before

        with _no_rebuild() as schedule:
            self._run(self.submission, INSTALLED.format('pandas'))
            schedule.assert_called_once_with(self.env.id, "out of date")

    def test_a_learned_package_that_breaks_the_build_is_dropped_and_not_relearned(self):
        self.env.detected_requirements = 'numpy'
        self.env.requirements = 'numpy'
        self.env.built_requirements = 'numpy'
        self.env.save()
        subs = self._submissions(4)
        with _pypi(), _no_rebuild():
            for sub in subs[:3]:
                self._run(sub, INSTALLED.format('brokenpkg'))

            self.assertEqual([], packages.settle_learned_packages(self.env.id, build_succeeded=False))
            self.env.refresh_from_db()
            self.assertEqual([], self.env.learned_packages)
            self.assertEqual('numpy', self.env.requirements)
            self.assertIn('brokenpkg', self.env.build_logs)

            self._run(subs[3], INSTALLED.format('brokenpkg'))

        self.env.refresh_from_db()
        self.assertEqual([], self.env.learned_packages)
        self.assertEqual('build_failed', packages.pending_packages(self.env)[0]['status'])

    def test_a_failed_build_with_other_changes_does_not_blame_the_learned_package(self):
        self.env.detected_requirements = 'numpy'
        self.env.built_requirements = 'numpy'
        self.env.pinned_packages = ['nosuchversion==99']
        self.env.save()
        with _pypi(), _no_rebuild():
            for sub in self._submissions(3):
                self._run(sub, INSTALLED.format('pandas'))
            packages.settle_learned_packages(self.env.id, build_succeeded=False)

        self.env.refresh_from_db()
        self.assertEqual(['pandas'], self.env.learned_packages)


class _FakeDocker:
    """Enough of the docker client for Builder.build to succeed."""

    def __init__(self, during_build=None):
        self.api = mock.Mock()
        self.api.build.side_effect = self._build
        self.containers = mock.Mock()
        self.containers.run.return_value = iter([b"VERIFICATION SUCCESS\n"])
        self.images = mock.Mock()
        self.images.list.return_value = []
        self.during_build = during_build

    def _build(self, **kwargs):
        if self.during_build:
            self.during_build()
        return iter([{"stream": "Step 1/1 : FROM python\n"}])


class BuildHistoryTests(_EnvCase):

    def _build(self, during_build=None, reason=""):
        client = _FakeDocker(during_build)
        with mock.patch('autograder.services.builder.docker.from_env', return_value=client), \
                mock.patch.object(ImageManager, '_get_docker_client', return_value=client):
            return Builder(self.env.id, reason=reason).build()

    def test_a_build_records_a_snapshot_that_survives_the_final_save(self):
        """Prod had 71 of 73 histories empty: the builder's stale instance saved [] over it."""
        Environment.objects.filter(pk=self.env.pk).update(requirements='numpy')

        result = self._build(reason="instructor")

        self.assertTrue(result["success"], result)
        self.env.refresh_from_db()
        self.assertEqual(1, len(self.env.image_history))
        entry = self.env.image_history[0]
        self.assertEqual(
            (1, self.env.image_name, 'numpy', 'instructor'),
            (entry['version'], entry['image_name'], entry['requirements'], entry['reason']))
        self.assertEqual('numpy', self.env.built_requirements)
        self.assertFalse(packages.image_out_of_date(self.env))

    def test_a_build_after_a_rollback_numbers_itself_after_the_newest_snapshot(self):
        history = [{"version": n, "image_name": f"img:{n}", "requirements": ""} for n in (1, 2, 3)]
        Environment.objects.filter(pk=self.env.pk).update(
            image_history=history, image_name='img:3', current_build_version=3)
        self.assertTrue(ImageManager.rollback_to_version(self.env.id, 1))

        self._build()

        self.env.refresh_from_db()
        self.assertEqual(4, self.env.current_build_version)
        self.assertEqual(4, self.env.image_history[-1]['version'])

    def test_versions_advance_and_legacy_images_count_as_one(self):
        Environment.objects.filter(pk=self.env.pk).update(image_name='codepost-env-1:1', current_build_version=1)

        self._build()
        with mock.patch('autograder.services.builder.timezone.now',
                        return_value=timezone.now() + timezone.timedelta(seconds=5)):
            self._build()

        self.env.refresh_from_db()
        self.assertEqual([2, 3], [e['version'] for e in self.env.image_history])
        self.assertEqual(3, self.env.current_build_version)

    def test_a_build_does_not_write_back_stale_lists_or_counters(self):
        def student_runs_finish_while_building():
            Environment.objects.filter(pk=self.env.pk).update(
                total_runs=9, successful_runs=8, learned_packages=['pandas'],
                requirements='pandas', convergence_stats={'pandas': {'status': 'learned'}})

        self._build(during_build=student_runs_finish_while_building)

        self.env.refresh_from_db()
        self.assertEqual((9, 8, ['pandas'], 'pandas'), (
            self.env.total_runs, self.env.successful_runs, self.env.learned_packages, self.env.requirements))
        # The image was built before pandas arrived, and says so.
        self.assertEqual('', self.env.built_requirements)
        self.assertTrue(packages.image_out_of_date(self.env))

    def test_cleanup_never_deletes_the_image_in_use_or_a_kept_snapshot(self):
        tags = [f'codepost-env-{self.env.id}:{n}' for n in (1, 2, 3, 4)]
        history = [{"version": n, "image_name": tag, "requirements": ""} for n, tag in enumerate(tags, 1)]
        Environment.objects.filter(pk=self.env.pk).update(
            image_history=history, image_name=tags[0], build_status=2)  # rolled back to the oldest
        client = mock.Mock()
        client.images.list.return_value = [mock.Mock(tags=[tag]) for tag in tags + ['codepost-env-999:1']]

        with mock.patch.object(ImageManager, '_get_docker_client', return_value=client), \
                mock.patch.object(ImageManager, 'delete_image', return_value=True) as delete:
            ImageManager.cleanup_old_images(self.env.id, keep_count=2)

        self.assertEqual([mock.call(tags[1])], delete.call_args_list)
        self.env.refresh_from_db()
        self.assertEqual([1, 3, 4], [e['version'] for e in self.env.image_history])


class RebuildSchedulingTests(_EnvCase):

    def test_only_one_rebuild_is_queued_at_a_time(self):
        with mock.patch.object(RebuildEnvironmentIfStale, 'apply_async') as queue:
            self.assertTrue(packages.schedule_rebuild(self.env.id, "learned"))
            self.assertFalse(packages.schedule_rebuild(self.env.id, "learned"))
        queue.assert_called_once_with(args=[self.env.id, "learned"], countdown=packages.REBUILD_DEBOUNCE_SECONDS)

    def test_learned_rebuilds_wait_out_the_interval_but_an_instructors_change_does_not(self):
        Environment.objects.filter(pk=self.env.pk).update(last_built=timezone.now())
        with mock.patch.object(RebuildEnvironmentIfStale, 'apply_async') as queue:
            packages.schedule_rebuild(self.env.id, "learned")
            self.assertGreater(queue.call_args.kwargs['countdown'], 500)

            Environment.objects.filter(pk=self.env.pk).update(rebuild_scheduled_at=None)
            packages.schedule_rebuild(self.env.id, "instructor", rate_limited=False)
            self.assertEqual(packages.REBUILD_DEBOUNCE_SECONDS, queue.call_args.kwargs['countdown'])

    def test_the_queued_task_builds_only_a_stale_or_missing_image(self):
        Environment.objects.filter(pk=self.env.pk).update(
            image_name='img:1', requirements='numpy', built_requirements='numpy',
            rebuild_scheduled_at=timezone.now())
        with mock.patch('autograder.run.BuildEnvironment') as build:
            with mock.patch.object(ImageManager, 'image_exists', return_value=True):
                self.assertEqual({"status": "up_to_date"}, RebuildEnvironmentIfStale(self.env.id, "learned"))
            build.assert_not_called()
            self.env.refresh_from_db()
            self.assertIsNone(self.env.rebuild_scheduled_at)

            with mock.patch.object(ImageManager, 'image_exists', return_value=False):  # rolled back, image gone
                RebuildEnvironmentIfStale(self.env.id, "rollback")
            build.assert_called_once_with(self.env.id, reason="rollback")

            Environment.objects.filter(pk=self.env.pk).update(requirements='numpy\npandas')
            with mock.patch.object(ImageManager, 'image_exists', return_value=True):
                RebuildEnvironmentIfStale(self.env.id, "learned")
            self.assertEqual(2, build.call_count)

    def test_the_queued_task_waits_for_a_build_in_progress(self):
        Environment.objects.filter(pk=self.env.pk).update(build_status=1)
        with mock.patch('autograder.run.BuildEnvironment') as build, \
                mock.patch.object(RebuildEnvironmentIfStale, 'apply_async') as retry:
            self.assertEqual({"status": "waiting_for_build"}, RebuildEnvironmentIfStale(self.env.id, "learned"))
        build.assert_not_called()
        retry.assert_called_once_with(args=[self.env.id, "learned", 1], countdown=60)

    def test_a_successful_build_reruns_the_submissions_that_lacked_a_learned_package(self):
        Environment.objects.filter(pk=self.env.pk).update(
            convergence_stats={'scipy': {'status': 'learned', 'submissions': [1, 2, 3], 'rerun': [2]}})
        with mock.patch('autograder.run.Builder') as builder, \
                mock.patch.object(Autodetector, 'detect_and_update'), \
                mock.patch('autograder.run.RunSubmission') as run:
            builder.return_value.build.return_value = {"success": True}
            BuildEnvironment(self.env.id, reason="learned")
        builder.assert_called_once_with(self.env.id, reason="learned")
        run.delay.assert_called_once_with(2)


class PackagesEndpointTests(APITestCase):

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="ag-pkgs", period="s2026", organization__name="PkgOrg")
            self.assignment = self.course.assignments.first()
        SubmissionFile.objects.filter(submission__assignment=self.assignment).delete()  # the factory adds .java files
        with factory.django.mute_signals(post_save):
            AssignmentFile.objects.create(
                assignment=self.assignment, name='starter.py', data='import numpy', extension='py')
        self.env = Environment.objects.create(
            assignment=self.assignment, auto_detect=True, language='python-3.12',
            detected_requirements='numpy', requirements='numpy')
        self.client.force_authenticate(user=self.course.courseAdmins.first())

    def _post(self, action, package):
        with _pypi(), _no_rebuild() as schedule:
            resp = self.client.post(f'/autograder/environments/{self.env.id}/packages/',
                                    {'action': action, 'requirement': package}, format='json')
        return resp, schedule

    def test_add_pins_the_package_and_queues_a_rebuild(self):
        resp, schedule = self._post('add', 'pandas==2.2.3')

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual('numpy\npandas==2.2.3', resp.data['requirements'])
        self.assertIn({"name": "pandas", "requirement": "pandas==2.2.3", "origin": "pinned"}, resp.data['packages'])
        schedule.assert_called_once_with(self.env.id, "instructor", rate_limited=False)

    def test_remove_excludes_and_restore_brings_it_back(self):
        resp, _ = self._post('remove', 'numpy')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(('', ['numpy']), (resp.data['requirements'], resp.data['excludedPackages']))

        with _pypi(), _no_rebuild():  # detection cannot put it back
            Autodetector.detect_and_update(assignment=self.assignment, force=True)
        self.env.refresh_from_db()
        self.assertEqual('', self.env.requirements)

        resp, _ = self._post('restore', 'numpy')
        self.assertEqual(('numpy', []), (resp.data['requirements'], resp.data['excludedPackages']))

    def test_a_typo_is_a_400_that_says_why(self):
        with _pypi(False), _no_rebuild() as schedule:
            resp = self.client.post(f'/autograder/environments/{self.env.id}/packages/',
                                    {'action': 'add', 'requirement': 'pandass'}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('PyPI', resp.data['detail'])
        schedule.assert_not_called()

    def test_manual_and_non_package_list_environments_are_refused(self):
        for change in ({'auto_detect': False}, {'language': 'java-17'}):
            Environment.objects.filter(pk=self.env.pk).update(auto_detect=True, language='python-3.12')
            Environment.objects.filter(pk=self.env.pk).update(**change)
            resp, _ = self._post('add', 'pandas')
            self.assertEqual(resp.status_code, 400, resp.content)
            self.assertIn('detail', resp.data)

    def test_graders_and_students_cannot_change_packages(self):
        for user in (self.course.graders.first(), self.course.students.first()):
            self.client.force_authenticate(user=user)
            resp, _ = self._post('add', 'pandas')
            self.assertEqual(resp.status_code, 403, resp.content)
        self.env.refresh_from_db()
        self.assertEqual([], self.env.pinned_packages)


class RollbackTests(APITestCase):

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.course = CourseFactory(name="ag-rollback", period="s2026", organization__name="RollOrg")
            self.assignment = self.course.assignments.first()
            AssignmentFile.objects.create(
                assignment=self.assignment, name='starter.py', data='import numpy', extension='py')
        SubmissionFile.objects.filter(submission__assignment=self.assignment).delete()  # the factory adds .java files
        self.env = Environment.objects.create(
            assignment=self.assignment, auto_detect=True, language='python-3.12',
            detected_requirements='numpy', learned_packages=['badpkg', 'pandas'],
            requirements='badpkg\nnumpy\npandas', built_requirements='badpkg\nnumpy\npandas',
            image_name='img:3', current_build_version=3,
            image_history=[
                {"version": 1, "image_name": "img:1", "requirements": "numpy\nscipy<2"},
                {"version": 2, "image_name": "img:2", "requirements": "numpy\npandas"},
                {"version": 3, "image_name": "img:3", "requirements": "badpkg\nnumpy\npandas"},
            ])
        self.client.force_authenticate(user=self.course.courseAdmins.first())

    def _rollback(self, body):
        with _no_rebuild() as schedule:
            resp = self.client.post(f'/autograder/environments/{self.env.id}/rollback/', body, format='json')
        return resp, schedule

    def test_rollback_restores_the_previous_image_and_list_and_sticks(self):
        resp, schedule = self._rollback({})

        self.assertEqual(resp.status_code, 200, resp.content)
        schedule.assert_called_once_with(self.env.id, "rollback", rate_limited=False)
        self.env.refresh_from_db()
        self.assertEqual(('img:2', 'numpy\npandas', 'numpy\npandas', ['badpkg'], 2), (
            self.env.image_name, self.env.requirements, self.env.built_requirements,
            self.env.excluded_packages, self.env.current_build_version))

        # Neither detection nor more student runs bring the package back.
        with _pypi(), _no_rebuild():
            Autodetector.detect_and_update(assignment=self.assignment, force=True)
            with factory.django.mute_signals(post_save):
                subs = [SubmissionFactory(assignment=self.assignment, files=None) for _ in range(3)]
            for sub in subs:
                Converger.analyze_and_converge(self.env.id, INSTALLED.format('badpkg'), submission_id=sub.id)
        self.env.refresh_from_db()
        self.assertEqual('numpy\npandas', self.env.requirements)

    def test_rollback_to_an_older_version_pins_what_it_had(self):
        resp, _ = self._rollback({'version': 1})

        self.assertEqual(resp.status_code, 200, resp.content)
        self.env.refresh_from_db()
        self.assertEqual(('img:1', 'numpy\nscipy<2'), (self.env.image_name, self.env.requirements))
        self.assertEqual(['scipy<2'], self.env.pinned_packages)

        # "Previous" is now relative to the image in use, and there is none before version 1.
        resp, _ = self._rollback({})
        self.assertEqual(resp.status_code, 400, resp.content)


class OneTimeRebuildCommandTests(_EnvCase):

    def setUp(self):
        super().setUp()
        self._asg_file('starter.py', 'import numpy')
        subs = self._submissions(3)
        for sub in subs:
            self._sub_file('hw.py', 'import pandas\nimport mytypo', submission=sub)
        self._sub_file('hw.py', 'import onlyme')
        Environment.objects.filter(pk=self.env.pk).update(
            requirements='matplotlib\nnumpy\npandas', image_name='codepost-env-1:1',
            convergence_stats={'scipy': {'count': 9, 'submissions': [s.id for s in subs]},
                               'seaborn': {'count': 4, 'submissions': [subs[0].id]}})

    def _pypi_knows(self, name):
        return name != 'mytypo'

    def test_dry_run_writes_and_builds_nothing(self):
        with mock.patch.object(Autodetector, 'check_pypi_existence', side_effect=self._pypi_knows), \
                mock.patch('core.management.commands.rebuild_autodetect_environments.BuildEnvironment') as build:
            call_command('rebuild_autodetect_environments', '--dry-run', stdout=mock.Mock())

        build.assert_not_called()
        self.env.refresh_from_db()
        self.assertEqual(('matplotlib\nnumpy\npandas', '', []), (
            self.env.requirements, self.env.detected_requirements, self.env.learned_packages))

    def test_rebuild_relists_from_instructor_files_and_what_three_submissions_needed(self):
        with mock.patch.object(Autodetector, 'check_pypi_existence', side_effect=self._pypi_knows), \
                mock.patch('core.management.commands.rebuild_autodetect_environments.BuildEnvironment',
                           return_value={"success": True, "image": "x"}) as build:
            call_command('rebuild_autodetect_environments', stdout=mock.Mock())

        build.assert_called_once_with(self.env.id, reason="one-time rebuild")
        self.env.refresh_from_db()
        self.assertEqual('numpy', self.env.detected_requirements)
        self.assertEqual(['pandas', 'scipy'], self.env.learned_packages)
        self.assertEqual('numpy\npandas\nscipy', self.env.requirements)
        self.assertEqual(['seaborn'], list(self.env.convergence_stats))

    def test_a_failed_build_is_retried_without_the_seeded_packages(self):
        with mock.patch.object(Autodetector, 'check_pypi_existence', side_effect=self._pypi_knows), \
                mock.patch('core.management.commands.rebuild_autodetect_environments.BuildEnvironment',
                           side_effect=[{"success": False, "error": "pip"}, {"success": True, "image": "x"}]) as build:
            call_command('rebuild_autodetect_environments', '--env', str(self.env.id), stdout=mock.Mock())

        self.assertEqual(2, build.call_count)
        self.env.refresh_from_db()
        self.assertEqual('numpy', self.env.requirements)
