# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.test import SimpleTestCase
from unittest.mock import MagicMock
from core.models import dataset_upload_path, AssignmentDataSet

class TestDatasetPath(SimpleTestCase):
    def test_dataset_path_sanitization(self):
        # Setup: Create mock objects with potentially malicious names
        mock_org = MagicMock()
        mock_org.shortname = "Bad Org../Name"
        
        mock_course = MagicMock()
        mock_course.organization = mock_org
        mock_course.name = "Bad Course../Name"
        mock_course.period = "Fa/ll"
        
        mock_assignment = MagicMock()
        mock_assignment.course = mock_course
        mock_assignment.name = "Bad Assign../Name"
        
        mock_dataset = MagicMock(spec=AssignmentDataSet)
        mock_dataset.assignment = mock_assignment
        
        # Test filename with traversal
        filename = "bad_file../name.txt"
        
        # Call the function
        path = dataset_upload_path(mock_dataset, filename)
        
        print(f"Generated Path: {path}")
        
        # Verification Logic
        
        # 1. Check for directory traversal in path components
        # Current Vulnerable Implementation behavior:
        # replace(' ', '_') -> "Bad_Org../Name/Bad_Course../Name/Fa/ll/Bad_Assign../Name/bad_file../name.txt"
        
        # Safe Implementation behavior (with slugify):
        # slugify("Bad Org../Name") -> "bad-orgname"
        # slugify("Bad Course../Name") -> "bad-coursename"
        # slugify("Fa/ll") -> "fall"
        # slugify("Bad Assign../Name") -> "bad-assignname"
        # basename("bad_file../name.txt") -> "name.txt"
        
        # We verify that ".." is NOT in the path
        self.assertNotIn("..", path, "Path traversal sequence '..' found in path")
        
        # We verify that "/" is only used as a separator between strict components
        # The mocked strings had "/" in "Fa/ll". 
        # Ideally, component "Fa/ll" should become "Fall" or "Fa_ll" or similar, NOT "Fa/ll" (which creates a subdir)
        parts = path.split('/')
        
        # Expected components: org, course, period, assignment, filename
        self.assertEqual(len(parts), 5, f"Path {path} does not have 5 components")
        
        # Assert no component contains '..'
        for part in parts:
            self.assertNotIn('..', part)
            
        # Assert specific sanitization expectations (to be updated once we fix it)
        # For now, this test is expected to FAIL until we apply the fix.
        # self.assertEqual(parts[0], "bad-orgname") # Example expectation

