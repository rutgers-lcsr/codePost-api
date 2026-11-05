# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import json
import xml.dom.minidom
from unittest import mock

import factory
from django.db.models.signals import post_save
from django.test import TestCase

from autograder.services.autodetector import Autodetector
from autograder.services.converger import JavaConverger
from autograder.services.executors import (
    CPPExecutor, Executor, JavaExecutor, NodeExecutor, PHPExecutor,
    PythonExecutor, RExecutor, RubyExecutor, get_executor_class,
)
from core.models import AssignmentFile, Environment, SubmissionFile
from core.services.file_handlers.factory import FileHandlerFactory
from core.tests.factories import AssignmentFactory, SubmissionFactory


def _notebook(language, name=None):
    return json.dumps({
        'cells': [{'cell_type': 'code', 'source': ['x = 1'], 'metadata': {}}],
        'metadata': {'kernelspec': {'language': language, 'name': name or language}},
        'nbformat': 4, 'nbformat_minor': 5,
    })


class _File:
    def __init__(self, name, data, extension=None):
        self.name = name
        self.data = data
        self.extension = extension if extension is not None else name.rsplit('.', 1)[-1]


class DetectAndUpdateManifestTest(TestCase):
    """Whole-file manifests (pom.xml, package.json, ...) must survive detection intact."""

    def setUp(self):
        with factory.django.mute_signals(post_save):
            self.assignment = AssignmentFactory()
            self.submission = SubmissionFactory(assignment=self.assignment, files=None)
            self.env = Environment.objects.create(assignment=self.assignment, auto_detect=True, language='other')

    def _sub_file(self, name, data):
        with factory.django.mute_signals(post_save):
            return SubmissionFile.objects.create(
                submission=self.submission, name=name, data=data, extension=name.rsplit('.', 1)[-1])

    def _asg_file(self, name, data):
        with factory.django.mute_signals(post_save):
            return AssignmentFile.objects.create(
                assignment=self.assignment, name=name, data=data, extension=name.rsplit('.', 1)[-1])

    def test_java_generated_pom_is_valid_xml(self):
        self._sub_file('A.java', 'import org.junit.Test;\nclass A {}')
        self._sub_file('B.java', 'import com.google.gson.Gson;\nclass B {}')

        Autodetector.detect_and_update(self.submission)

        self.env.refresh_from_db()
        dom = xml.dom.minidom.parseString(self.env.requirements)
        artifacts = {n.firstChild.data for n in dom.getElementsByTagName('artifactId')}
        self.assertIn('junit', artifacts)
        self.assertIn('gson', artifacts)

    def test_node_generated_package_json_is_valid_json_with_all_deps(self):
        self._sub_file('a.js', "const e = require('express');")
        self._sub_file('b.js', "const l = require('lodash');")

        Autodetector.detect_and_update(self.submission)

        self.env.refresh_from_db()
        pkg = json.loads(self.env.requirements)
        self.assertEqual({'express', 'lodash'}, set(pkg['dependencies']))

    def test_python_requirements_still_line_merged(self):
        self._sub_file('a.py', 'import numpy\nimport pandas')
        self._sub_file('b.py', 'import numpy')

        with mock.patch.object(Autodetector, 'check_pypi_existence', return_value=True):
            Autodetector.detect_and_update(self.submission)

        self.env.refresh_from_db()
        self.assertEqual('numpy\npandas', self.env.requirements)


class MergeRequirementsTest(TestCase):
    """Line-oriented lists merge per line; whole-file manifests are never split."""

    def test_whole_file_manifests_are_kept_verbatim(self):
        gemfile = "source 'https://rubygems.org'\n\ngem 'rspec'\ngem 'json'\n"
        makefile = "all:\n\tg++ -o a a.cpp\n\nclean:\n\trm a\n"
        composer = json.dumps({'require': {'monolog/monolog': '^3.0'}}, indent=4)
        for language, blob in [('ruby', gemfile), ('c/c++', makefile), ('php', composer)]:
            with self.subTest(language=language):
                self.assertEqual(blob, Autodetector.merge_requirements(language, [blob]))

    def test_identical_manifests_collapse_to_one(self):
        blob = json.dumps({'name': 'hw', 'dependencies': {'chalk': '^5.0.0'}}, indent=2)
        self.assertEqual(blob, Autodetector.merge_requirements('node-20', [blob, blob]))

    def test_package_jsons_merge_dependencies(self):
        a = json.dumps({'name': 'hw', 'dependencies': {'chalk': '^5.0.0'}})
        b = json.dumps({'name': 'other', 'dependencies': {'lodash': '*'}})
        merged = json.loads(Autodetector.merge_requirements('node-20', [a, b]))
        self.assertEqual('hw', merged['name'])
        self.assertEqual({'chalk': '^5.0.0', 'lodash': '*'}, merged['dependencies'])

    def test_r_packages_merge_per_line(self):
        self.assertEqual('dplyr\nggplot2', Autodetector.merge_requirements('r-4', ['ggplot2\ndplyr', 'dplyr']))

    def test_nothing_to_merge_is_none(self):
        self.assertIsNone(Autodetector.merge_requirements('python-3.12', []))
        self.assertIsNone(Autodetector.merge_requirements('node-20', ['  ']))


class DetectFromFilesConsistencyTest(TestCase):
    """The assignment-file path must decide requirements the same way detect_and_update does."""

    def test_local_module_is_not_a_requirement(self):
        files = [
            {'name': 'main.py', 'data': 'import client\nimport numpy'},
            {'name': 'client.py', 'data': 'x = 1'},
        ]
        with mock.patch.object(Autodetector, 'check_pypi_existence', return_value=True):
            language, reqs = Autodetector.detect_from_files(files)  # type: ignore[misc]

        self.assertEqual('python-3.12', language)
        self.assertEqual('numpy', reqs)

    def test_unknown_pypi_package_is_not_a_requirement(self):
        files = [{'name': 'main.py', 'data': 'import notarealpkg\nimport numpy'}]
        with mock.patch.object(Autodetector, 'check_pypi_existence', side_effect=lambda p: p != 'notarealpkg'):
            _language, reqs = Autodetector.detect_from_files(files)  # type: ignore[misc]

        self.assertEqual('numpy', reqs)

    def test_node_files_merge_into_one_valid_package_json(self):
        files = [
            {'name': 'a.js', 'data': "require('express')"},
            {'name': 'b.js', 'data': "require('lodash')"},
        ]
        _language, reqs = Autodetector.detect_from_files(files)  # type: ignore[misc]

        self.assertEqual({'express', 'lodash'}, set(json.loads(reqs)['dependencies']))


class GetExecutorClassTest(TestCase):
    def test_supported_languages_route_to_their_executor(self):
        cases = {
            'python-3.12': PythonExecutor, 'python-2.7': PythonExecutor, 'python': PythonExecutor,
            'python3': PythonExecutor, 'data_science': PythonExecutor, 'Python': PythonExecutor,
            'java': JavaExecutor, 'java-17': JavaExecutor, 'java-11': JavaExecutor,
            'c/c++': CPPExecutor, 'c': CPPExecutor, 'cpp': CPPExecutor, 'c++': CPPExecutor,
            'node-20': NodeExecutor, 'node-18': NodeExecutor, 'node': NodeExecutor,
            'javascript': NodeExecutor, 'js': NodeExecutor,
            'r-4': RExecutor, 'r': RExecutor, 'R': RExecutor,
            'ruby': RubyExecutor, 'php': PHPExecutor,
        }
        for language, expected in cases.items():
            with self.subTest(language=language):
                self.assertIs(expected, get_executor_class(language))

    def test_unsupported_languages_are_rejected_not_routed_to_cpp(self):
        for language in ['typescript', 'scala', 'csharp', 'racket', 'clojure', 'matlab', 'rust', 'bash', 'cobol', '']:
            with self.subTest(language=language):
                self.assertIs(Executor, get_executor_class(language))


class NotebookKernelLanguageTest(TestCase):
    def _language(self, kernel_language):
        handler = FileHandlerFactory.get_handler(_File('nb.ipynb', _notebook(kernel_language)))
        return handler.get_language()

    def test_javascript_kernel_is_node_not_java(self):
        self.assertEqual('node-20', self._language('javascript'))

    def test_java_kernels_still_java(self):
        self.assertEqual('java-17', self._language('java'))
        self.assertEqual('java-17', self._language('Java'))

    def test_python_kernel_variants(self):
        self.assertEqual('python-3.12', self._language('python3'))

    def test_cpp_kernel_maps_to_cpp(self):
        self.assertEqual('c/c++', self._language('c++'))
        self.assertEqual('c/c++', self._language('C++17'))

    def test_php_kernel_maps_to_php(self):
        self.assertEqual('php', self._language('php'))

    def test_cpp_notebook_requirements_do_not_crash(self):
        handler = FileHandlerFactory.get_handler(_File('nb.ipynb', _notebook('c++')))
        self.assertIsNone(handler.get_requirements())


class JavaConvergerStdlibTest(TestCase):
    def test_only_real_jdk_packages_are_stdlib(self):
        logs = "\n".join(f"package {p} does not exist" for p in [
            'javassist', 'javafx.application', 'sunlabs.x', 'java.util', 'javax.swing',
            'sun.misc', 'com.sun.net', 'jdk.internal'])

        modules = JavaConverger.extract_missing_modules(logs)

        self.assertEqual({'javassist', 'javafx.application', 'sunlabs.x'}, modules)
