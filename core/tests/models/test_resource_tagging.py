import pytest
from core.models import TestCategoryResource, AssignmentDataSet, AssignmentFile, TestCategory, Assignment, Course, Organization
import factory

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
def test_resource_creation_tags_file():
    category = TestCategoryFactory()
    file = AssignmentFileFactory(assignment=category.assignment)
    
    assert not file.is_test_resource
    assert not file.hidden
    
    TestCategoryResource.objects.create(
        category=category,
        file=file,
        target_path="linked_file.txt"
    )
    
    file.refresh_from_db()
    assert file.is_test_resource
    assert file.hidden

@pytest.mark.django_db
def test_resource_creation_tags_dataset():
    category = TestCategoryFactory()
    dataset = AssignmentDataSetFactory(assignment=category.assignment)
    
    assert not dataset.is_test_resource
    assert not dataset.hidden
    
    TestCategoryResource.objects.create(
        category=category,
        dataset=dataset,
        target_path="linked_dataset.csv"
    )
    
    dataset.refresh_from_db()
    assert dataset.is_test_resource
    assert dataset.hidden
