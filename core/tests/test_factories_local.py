# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

import factory
from core.models import TestCategory, AssignmentDataSet, AssignmentFile
from core.tests.factories import AssignmentFactory

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
