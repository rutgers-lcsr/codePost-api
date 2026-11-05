# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.test import SimpleTestCase
import unittest.mock
from core.models import File
from core.services.file_handlers.factory import FileHandlerFactory
from core.services.file_handlers.python import PythonHandler
from core.services.file_handlers.java import JavaHandler
from core.services.file_handlers.node import NodeHandler
from core.services.file_handlers.notebook import NotebookHandler

class FileHandlerTests(SimpleTestCase):
    
    def test_factory_python(self):
        f = File(name="test.py", extension="py", data="import os")
        handler = FileHandlerFactory.get_handler(f)
        self.assertIsInstance(handler, PythonHandler)
        self.assertEqual(handler.get_language(), "python-3.12")
        
    def test_python_requirements(self):
        code = "import numpy\nfrom pandas import DataFrame"
        f = File(name="test.py", extension="py", data=code)
        handler = FileHandlerFactory.get_handler(f)
        reqs = handler.get_requirements()
        self.assertIn("numpy", reqs)
        self.assertIn("pandas", reqs)
        
    def test_factory_java(self):
        f = File(name="Test.java", extension="java", data="import java.util.List;")
        handler = FileHandlerFactory.get_handler(f)
        self.assertIsInstance(handler, JavaHandler)
        self.assertEqual(handler.get_language(), "java-17")

    def test_java_requirements_pom(self):
        # Test pom generation from imports
        code = "import org.junit.Test;"
        f = File(name="Test.java", extension="java", data=code)
        handler = FileHandlerFactory.get_handler(f)
        reqs = handler.get_requirements()
        self.assertIn("<groupId>junit</groupId>", reqs)
        self.assertIn("<artifactId>junit</artifactId>", reqs)

    def test_node_requirements(self):
        code = "import axios from 'axios';"
        f = File(name="test.js", extension="js", data=code)
        
        # Mock the scanning logic to avoid dependency on esprima being installed
        with unittest.mock.patch('core.services.file_handlers.node.NodeHandler.scan_content', return_value={'axios'}):
            handler = FileHandlerFactory.get_handler(f)
            self.assertIsInstance(handler, NodeHandler)
            reqs = handler.get_requirements()
            
            self.assertIsNotNone(reqs)
            self.assertIn("axios", reqs)
            self.assertIn("dependencies", reqs.lower())

    def test_notebook_delegation_python(self):
        # Mock a python notebook
        nb_content = '''
        {
         "metadata": {
          "kernelspec": {
           "display_name": "Python 3",
           "language": "python",
           "name": "python3"
          }
         },
         "cells": [
          {
           "cell_type": "code",
           "source": ["import numpy"]
          }
         ]
        }
        '''
        f = File(name="test.ipynb", extension="ipynb", data=nb_content)
        handler = FileHandlerFactory.get_handler(f)
        self.assertIsInstance(handler, NotebookHandler)
        self.assertEqual(handler.get_language(), "python-3.12")
        
        reqs = handler.get_requirements()
        self.assertIn("numpy", reqs)

    def test_notebook_delegation_r(self):
        # Mock an R notebook
        nb_content = '''
        {
         "metadata": {
          "kernelspec": {
           "language": "R",
           "name": "ir"
          }
         },
         "cells": [
          {
           "cell_type": "code",
           "source": ["library(ggplot2)"]
          }
         ]
        }
        '''
        f = File(name="test.ipynb", extension="ipynb", data=nb_content)
        handler = FileHandlerFactory.get_handler(f)
        self.assertEqual(handler.get_language(), "r-4")
        
        reqs = handler.get_requirements()
        self.assertIn("ggplot2", reqs)


class JavaImportMappingTests(SimpleTestCase):

    def _pom(self, imports):
        code = "".join(f"import {i};\n" for i in imports) + "class A {}"
        return FileHandlerFactory.get_handler(File(name="A.java", extension="java", data=code)).get_requirements()

    def test_junit5_import_maps_to_jupiter_not_junit4(self):
        pom = self._pom(["org.junit.jupiter.api.Test"])
        self.assertIn("junit-jupiter", pom)
        self.assertNotIn("<artifactId>junit</artifactId>", pom)

    def test_longest_prefix_wins_regardless_of_coordinate_length(self):
        class Handler(JavaHandler):
            MAPPING = {'a.b': 'short-prefix:but:very-long-coordinate', 'a.b.c': 'x:y:1'}
        self.assertEqual(Handler(File(name="A.java", extension="java", data=""))._generate_pom_dependencies({'a.b.c.D'}), {'x:y:1'})

    def test_junit4_import_still_maps_to_junit4(self):
        pom = self._pom(["org.junit.Test"])
        self.assertIn("<artifactId>junit</artifactId>", pom)
        self.assertIn("4.13.2", pom)


class NodeImportScanTests(SimpleTestCase):

    def _deps(self, code, name="a.js"):
        reqs = NodeHandler(File(name=name, extension=name.rsplit('.', 1)[1], data=code)).get_requirements()
        if reqs is None:
            return None
        import json
        return set(json.loads(reqs)["dependencies"])

    def test_builtins_and_node_scheme_are_not_dependencies(self):
        code = "const fs = require('fs');\nimport 'node:path';\nimport os from 'os';\nconst e = require('express');"
        self.assertEqual(self._deps(code), {"express"})

    def test_subpaths_and_scopes_reduce_to_package_name(self):
        code = "import f from 'lodash/fp';\nimport x from '@scope/pkg/sub';\nimport y from '@a/b';"
        self.assertEqual(self._deps(code), {"lodash", "@scope/pkg", "@a/b"})

    def test_relative_and_absolute_paths_are_ignored(self):
        code = "import a from './a';\nimport b from '../b';\nimport c from '/abs/x';\nimport d from 'chalk';"
        self.assertEqual(self._deps(code), {"chalk"})

    def test_non_string_specifier_is_ignored(self):
        self.assertEqual(self._deps("require(5);\nconst e = require('express');"), {"express"})

    def test_modern_syntax_is_still_scanned(self):
        self.assertEqual(self._deps("const m = await import('lodash');\nimport e from 'express';"), {"lodash", "express"})
        self.assertEqual(self._deps("#!/usr/bin/env node\nconst e = require('express');"), {"express"})
        self.assertEqual(self._deps("class A { #x = 1 }\nconst e = require('express');"), {"express"})

    def test_typescript_is_still_scanned(self):
        code = "import express from 'express';\nconst x: number = 1;\nfunction f(a: string): void {}\nconst l = require('lodash');"
        self.assertEqual(self._deps(code, "a.ts"), {"express", "lodash"})


class NotebookUnexpectedJsonTests(SimpleTestCase):

    def _handler(self, data):
        return NotebookHandler(File(name="t.ipynb", extension="ipynb", data=data))

    def test_non_dict_json_degrades_to_unknown(self):
        for data in ("null", "5", "[]", '"x"'):
            h = self._handler(data)
            self.assertEqual(h.get_language(), "unknown", data)
            self.assertIsNone(h.get_requirements(), data)

    def test_bad_metadata_shapes_degrade_to_unknown(self):
        for data in ('{"metadata": null}', '{"metadata": []}',
                     '{"metadata": {"kernelspec": null}}',
                     '{"metadata": {"kernelspec": {"language": null}}}',
                     '{"metadata": {"kernelspec": {"language": 5}}}',
                     '{"metadata": {"language_info": {"name": null}}}'):
            self.assertEqual(self._handler(data).get_language(), "unknown", data)

    def test_odd_cells_do_not_crash_requirements(self):
        for cells in ("[1, null]", '{"a": 1}', '"x"'):
            data = '{"metadata": {"kernelspec": {"language": "python"}}, "cells": %s}' % cells
            self.assertIsNone(self._handler(data).get_requirements(), cells)

    def test_good_cells_survive_alongside_bad_ones(self):
        data = ('{"metadata": {"kernelspec": {"language": "python"}}, "cells": '
                '[1, {"cell_type": "code", "source": ["import numpy"]}]}')
        self.assertIn("numpy", self._handler(data).get_requirements())

    def test_inject_cell_ids_skips_non_dict_cells_but_ids_the_rest(self):
        import json
        out = json.loads(NotebookHandler.inject_cell_ids('{"cells": [1, null, {"cell_type": "code", "source": []}]}'))
        self.assertEqual(out["cells"][:2], [1, None])
        self.assertTrue(out["cells"][2]["metadata"]["id"])

    def test_inject_cell_ids_leaves_content_untouched_when_ids_exist_or_json_is_odd(self):
        has_ids = '{"cells":[{"metadata":{"id":"a"}}]}'
        self.assertEqual(NotebookHandler.inject_cell_ids(has_ids), has_ids)
        for data in ("null", "5", "[]", "not json"):
            self.assertEqual(NotebookHandler.inject_cell_ids(data), data)
