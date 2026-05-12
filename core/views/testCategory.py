# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import TestCategory, TestCase
from core.serializers.testCategory import TestCategorySerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import TestCategoryPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from autograder.services.TestParsingService import TestParsingService
import logging

logger = logging.getLogger(__name__)

class TestCategoryViewSet(ListProtectedViewSet):
  """
  list:
  Return a list of all the testCategories.

  create:
  Create a new testCategories.

  retrieve:
  Return the given testCategories.

  update:
  Update a testCategories.

  partial_update:
  Update a testCategories.

  delete:
  Delete a testCategories.
  """
  queryset = TestCategory.objects.all()
  serializer_class = TestCategorySerializer
  permission_classes = (IsAuthenticated, TestCategoryPermissions)

  @action(detail=False, methods=['post'], url_path='preview-script')
  def preview_script(self, request):
    """
    Preview the tests that would be generated from a script.
    """
    script = request.data.get('testScript', request.data.get('script', ''))
    language = request.data.get('language', 'python')

    # Mock a TestCategory object since parse_script expects one
    mock_category = TestCategory(testScript=script)
    
    # We can rely on parse_script implementation which uses the category's script/lang
    try:
        parsed_tests = TestParsingService.parse_script(mock_category, language=language)
        
        # Match the exact field mapping from update_test_cases so the preview
        # accurately reflects what will be stored in the database.
        desc_max_length = TestCase._meta.get_field('description').max_length or 255


        preview_data = []
        for test in parsed_tests:
            fname = test.get('functionName', '')
            name = test.get('name', fname)
            
            # Replicate the humanizing logic from update_test_cases
            if name == fname and fname:
                name = fname.replace('_', ' ').title()

            # Show if the title would be truncated when saved
            truncated = len(name) > desc_max_length
            if truncated:
                name = name[:desc_max_length]

            preview_data.append({
                'functionName': fname,
                'name': name,  # Maps to TestCase.description (Title)
                'description': test.get('description', ''),  # Maps to TestCase.explanation (Body)
                'points': test.get('points', 0),
                'timeout': test.get('timeout'),
                'truncated': truncated,
            })
            
        return Response(preview_data)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

  @action(detail=True, methods=['post'], url_path='sync-tests')
  def sync_tests(self, request, pk=None):
    """
    Manually trigger test case sync from the category's testScript.
    Use this if test cases were not created automatically on save.
    """
    test_category = self.get_object()
    try:
        TestParsingService.update_test_cases(test_category)
        test_cases = list(test_category.testCases.values('id', 'functionName', 'description', 'pointsPass'))
        return Response({
            'success': True,
            'testCasesCreated': len(test_cases),
            'testCases': test_cases,
        })
    except Exception as e:
        logger.exception(f"Failed to sync test cases for TestCategory {pk}")
        return Response({
            'success': False,
            'error': str(e),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



