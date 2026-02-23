# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import TestCategory, TestCase, Submission
from core.serializers.testCategory import TestCategorySerializer
from core.views.template import ListProtectedViewSet
from rest_framework.permissions import IsAuthenticated
from core.permissions.permissions import TestCategoryPermissions
from rest_framework.decorators import action
from rest_framework.response import Response
from autograder.services.TestParsingService import TestParsingService

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
        
        # Format for UI preview (aligning with what update_test_cases produces)
        preview_data = []
        for test in parsed_tests:
            fname = test.get('functionName')
            name = test.get('name', fname)
            
            # Replicate the humanizing logic from update_test_cases
            if name == fname:
                name = fname.replace('_', ' ').title()
                
            preview_data.append({
                'functionName': fname,
                'name': name, # This will be the Title
                'description': test.get('description', ''), # This will be the Explanation/Body
                'points': test.get('points', 0),
                'timeout': test.get('timeout')
            })
            
        return Response(preview_data)
    except Exception as e:
        return Response({'error': str(e)}, status=400)



