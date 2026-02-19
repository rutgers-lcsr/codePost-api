from django.test import TestCase
from core.models import AssignmentDataSet, TestCategoryResource, TestCategory, TestCase as AssignmentTestCase, Assignment, Course, Organization

class DatasetCascadeTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", shortname="testorg")
        self.course = Course.objects.create(name="Test Course", period="F2023", organization=self.org)
        self.assignment = Assignment.objects.create(name="Test Assignment", course=self.course, points=100)

    def test_dataset_deletion_cascades_to_test_category_resource(self):
        """
        Verify that deleting an AssignmentDataSet deletes any linked TestCategoryResource.
        """
        # Create a dataset
        dataset = AssignmentDataSet.objects.create(
            assignment=self.assignment,
            name="test_dataset.csv",
            file="some/path.csv"
        )
        
        # Create a test category
        category = TestCategory.objects.create(
            assignment=self.assignment,
            name="Test Category 1"
        )
        
        # Create a resource linking the category to the dataset
        resource = TestCategoryResource.objects.create(
            category=category,
            dataset=dataset,
            target_path="input.csv"
        )
        
        self.assertTrue(TestCategoryResource.objects.filter(id=resource.id).exists())
        
        # Delete the dataset
        dataset.delete()
        
        # Check if resource is deleted
        self.assertFalse(TestCategoryResource.objects.filter(id=resource.id).exists())

    def test_dataset_deletion_sets_null_on_test_case(self):
        """
        Verify that deleting an AssignmentDataSet does not delete TestCase records.
        Dataset linkage now occurs through TestCategoryResource, not TestCase.dataSet.
        """
        # Create a dataset
        dataset = AssignmentDataSet.objects.create(
            assignment=self.assignment,
            name="test_dataset_2.csv",
            file="some/path_2.csv"
        )
        
        category = TestCategory.objects.create(
            assignment=self.assignment,
            name="Test Category 2"
        )
        
        # Create a test case in the category
        test_case = AssignmentTestCase.objects.create(
            testCategory=category,
            description="Test Case 1",
            type="io",
            pointsPass=1,
            pointsFail=0,
        )

        # Link dataset via TestCategoryResource (new model relationship)
        resource = TestCategoryResource.objects.create(
            category=category,
            dataset=dataset,
            target_path="input_2.csv"
        )
        
        # Delete the dataset
        dataset.delete()
        
        # Reload test case
        test_case.refresh_from_db()

        # TestCase should remain; resource should be deleted via cascade from dataset
        self.assertTrue(AssignmentTestCase.objects.filter(id=test_case.id).exists())
        self.assertFalse(TestCategoryResource.objects.filter(id=resource.id).exists())
