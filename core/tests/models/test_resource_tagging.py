# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import pytest
from core.models import TestCategoryResource
from core.tests.factories import (
    TestCategoryFactory,
    AssignmentDataSetFactory,
    AssignmentFileFactory,
)

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
