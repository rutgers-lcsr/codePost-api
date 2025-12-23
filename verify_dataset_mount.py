
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add path to sys.path to allow imports
import sys
sys.path.append(os.getcwd())
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from autograder.services.executors.base import Executor
from core.models import AssignmentDataSet, File

class TestExecutor(Executor):
    def _detect_imports(self, code):
        return []
    def execute(self):
        pass
    def is_executable(self):
        return True

class TestDatasetMount(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.host_file = os.path.join(self.temp_dir, 'dataset.json')
        with open(self.host_file, 'w') as f:
            f.write('{"data": 123}')
            
        # Create dataset mock
        self.file_mock = MagicMock(spec=File)
        self.file_mock.path = self.host_file
        
        self.dataset = MagicMock(spec=AssignmentDataSet)
        self.dataset.name = 'dataset.json'
        self.dataset.file = self.file_mock
        self.dataset.is_active = True
        self.dataset.id = 1
        
        # Executor mock
        self.executor_file = MagicMock(spec=File)
        self.executor_file.get_file_info.return_value = (None, None, None)
        self.executor = TestExecutor(self.executor_file, datasets=[self.dataset])

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_absolute_mount_path_directory(self):
        """Test absolute mount path ending in slash (directory)"""
        # User case: /srv/share/test/
        self.dataset.mount_path = '/srv/share/test/'
        
        mounts = self.executor._prepare_dataset_staging(self.temp_dir)
        
        # Expected: /srv/share/test/dataset.json -> staged_file
        expected_path = '/srv/share/test/dataset.json'
        self.assertIn(expected_path, mounts)
        staged_path = mounts[expected_path]
        
        print(f"Verified directory path mount: {expected_path} -> {staged_path}")

    def test_relative_mount_path_directory(self):
        """Test relative mount path ending in slash"""
        self.dataset.mount_path = 'mydata/'
        
        mounts = self.executor._prepare_dataset_staging(self.temp_dir)
        
        # Expected: /shared/mydata/dataset.json -> staged_file
        expected_path = '/shared/mydata/dataset.json'
        self.assertIn(expected_path, mounts)
        staged_path = mounts[expected_path]
        print(f"Verified relative directory path mount: {expected_path} -> {staged_path}")

if __name__ == '__main__':
    unittest.main()
