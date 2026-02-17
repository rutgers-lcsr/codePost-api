import pytest
import factory
from core.models import TestCategoryResource, AssignmentDataSet, AssignmentFile, TestCategory, Assignment, Course, Organization
from core.serializers.testCategoryResource import TestCategoryResourceSerializer
from core.serializers.assignmentDataSet import AssignmentDataSetCreateSerializer

class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization
    name = "Test Org"
    shortname = "testorg"

class CourseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Course
    name = "Test Course"
    period = "F2023"
    organization = factory.SubFactory(OrganizationFactory)

class AssignmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Assignment
    name = "Test Assignment"
    course = factory.SubFactory(CourseFactory)
    points = 100
    isReleased = True

class TestCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TestCategory
    name = "Test Category"
    assignment = factory.SubFactory(AssignmentFactory)

class AssignmentDataSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AssignmentDataSet
    name = "dataset.csv"
    assignment = factory.SubFactory(AssignmentFactory)
    file = "path/to/dataset.csv"

class AssignmentFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AssignmentFile
    name = "test.txt"
    assignment = factory.SubFactory(AssignmentFactory)

@pytest.mark.django_db
def test_create_resource_with_camelCase_targetPath():
    category = TestCategoryFactory()
    file = AssignmentFileFactory(assignment=category.assignment)
    
    data = {
        'category': category.id,
        'file': file.id,
        'targetPath': 'camel/case/path.txt'
    }
    
    serializer = TestCategoryResourceSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    resource = serializer.save()
    
    assert resource.target_path == 'camel/case/path.txt'
    assert resource.category == category
    assert resource.file == file

@pytest.mark.django_db
def test_serialize_resource_return_camelCase_fields():
    category = TestCategoryFactory()
    file = AssignmentFileFactory(assignment=category.assignment, name="test.txt", data="content")
    resource = TestCategoryResource.objects.create(
        category=category,
        file=file,
        target_path='stored/path.txt'
    )
    
    from django.test import RequestFactory
    request = RequestFactory().get('/')
    serializer = TestCategoryResourceSerializer(resource, context={'request': request})
    data = serializer.data
    
    assert 'targetPath' in data
    assert data['targetPath'] == 'stored/path.txt'
    assert 'fileDetails' in data
    assert data['fileDetails']['name'] == 'test.txt'
    # Check that snake_case fields are NOT present
    assert 'target_path' not in data
    assert 'file_details' not in data
    assert 'dataset_details' not in data
    assert 'datasetDetails' in data # Should be present but null/None since we didn't set dataset

@pytest.mark.django_db
def test_create_dataset_with_is_test_resource_field():
    assignment = AssignmentFactory()
    
    # Mock file upload
    from django.core.files.uploadedfile import SimpleUploadedFile
    file_content = b"test content"
    uploaded_file = SimpleUploadedFile("test.csv", file_content, content_type="text/csv")

    data = {
        'assignment': assignment.id,
        'name': 'Test Resource Dataset',
        'file': uploaded_file,
        'isTestResource': True
    }
    
    serializer = AssignmentDataSetCreateSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    dataset = serializer.save()
    
    assert dataset.is_test_resource is True
