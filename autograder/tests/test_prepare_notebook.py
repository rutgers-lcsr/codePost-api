# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""NotebookExecutor.prepare_notebook: the cell list handed to every language template."""
import nbformat
from django.test import SimpleTestCase

from autograder.services.executors.base import NotebookExecutor


class PrepareNotebookTests(SimpleTestCase):

    def test_raw_cells_are_forwarded_with_their_index(self):
        """Raw cells must reach the template (it echoes them like markdown) so the executed
        notebook has the same cells, in the same positions, as the stored file."""
        nb = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell("### Task 4.10"),
            nbformat.v4.new_raw_cell("From the heatmap we can see..."),
            nbformat.v4.new_code_cell("x = 1"),
        ])
        cells = NotebookExecutor.prepare_notebook(nb, format="json")
        self.assertEqual(
            [(c["idx"], c["type"]) for c in cells],
            [(0, "markdown"), (1, "raw"), (2, "code")])
        self.assertEqual(cells[1]["source"], "From the heatmap we can see...")
