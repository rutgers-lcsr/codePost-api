
import ast
import re
import json
import logging
from typing import List, Dict, Any, Tuple
from core.models import TestCategory, TestCase

logger = logging.getLogger(__name__)

class TestParsingService:
    @staticmethod
    def parse_script(test_category: TestCategory) -> List[Dict[str, Any]]:
        """
        Parse the test script to identify @test decorated functions or equivalents.
        Returns a list of test definitions {name, points, etc}.
        """
        script = test_category.testScript
        if not script:
            return []

        # Simple language detection (can be improved)
        if "def " in script and "@test" in script:
            return TestParsingService._parse_python(script)
        elif "@Test" in script and "public void" in script:
            return TestParsingService._parse_java(script)
        elif "#' @test" in script:
            return TestParsingService._parse_r(script)
        
        return []

    @staticmethod
    def _parse_python(script: str) -> List[Dict[str, Any]]:
        tests = []
        try:
            tree = ast.parse(script)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and getattr(decorator.func, 'id', '') == 'test':
                            # Found @test(...)
                            test_info = {'functionName': node.name, 'name': node.name, 'points': 0}
                            
                            # Parse args/keywords
                            if decorator.args:
                                # First arg is usually name
                                if isinstance(decorator.args[0], ast.Constant):
                                     test_info['name'] = decorator.args[0].value
                            
                            for keyword in decorator.keywords:
                                if keyword.arg == 'points':
                                    if isinstance(keyword.value, (ast.Constant, ast.Num)):
                                         test_info['points'] = getattr(keyword.value, 'value', getattr(keyword.value, 'n', 0))
                            
                            tests.append(test_info)
        except Exception as e:
            logger.error(f"Failed to parse Python script: {e}")
        return tests

    @staticmethod
    def _parse_java(script: str) -> List[Dict[str, Any]]:
        # Naive regex parsing for Java @Test
        tests = []
        # Pattern: @Test(name="...", points=5) public void testName()
        # This is a simplification; a real parser would be better but expensive
        pattern = r'@Test\s*\((.*?)\)\s*public\s+void\s+(\w+)'
        matches = re.finditer(pattern, script, re.DOTALL)
        
        for match in matches:
            params = match.group(1)
            func_name = match.group(2)
            test_info = {'functionName': func_name, 'name': func_name, 'points': 0}
            
            # Extract name
            name_match = re.search(r'name\s*=\s*"([^"]+)"', params)
            if name_match:
                test_info['name'] = name_match.group(1)
                
            # Extract points
            points_match = re.search(r'points\s*=\s*(\d+(\.\d+)?)', params)
            if points_match:
                test_info['points'] = float(points_match.group(1))
                
            tests.append(test_info)
            
        return tests

    @staticmethod
    def _parse_r(script: str) -> List[Dict[str, Any]]:
        # Naive regex for R #' @test(name="...", points=5)
        tests = []
        pattern = r"#'\s*@test\((.*?)\)\s*\n\s*(\w+)\s*<-"
        matches = re.finditer(pattern, script, re.DOTALL)
        
        for match in matches:
            params = match.group(1)
            func_name = match.group(2)
            test_info = {'functionName': func_name, 'name': func_name, 'points': 0}
            
            # Extract name
            name_match = re.search(r'name\s*=\s*"([^"]+)"', params)
            if name_match:
                test_info['name'] = name_match.group(1)
            
            # Extract points
            points_match = re.search(r'points\s*=\s*(\d+(\.\d+)?)', params)
            if points_match:
                test_info['points'] = float(points_match.group(1))
            
            tests.append(test_info)
        return tests

    @staticmethod
    def update_test_cases(test_category: TestCategory):
        """
        Sync execution of parse_script with the database TestCase objects.
        """
        parsed_tests = TestParsingService.parse_script(test_category)
        
        current_tests = {t.functionName: t for t in test_category.testCases.all() if t.functionName}
        
        for test_data in parsed_tests:
            fname = test_data['functionName']
            if fname in current_tests:
                # Update existing
                # Update existing
                t = current_tests[fname]
                description = test_data.get('name', fname)
                if description == fname:
                    description = fname.replace('_', ' ').title()
                t.description = description
                t.pointsPass = test_data.get('points', 0)
                t.save()
            else:
                # Create new
                # Humanize the description if it matches the function name (default behavior)
                description = test_data.get('name', fname)
                if description == fname:
                    # test_something_cool -> Test Something Cool
                    description = fname.replace('_', ' ').title()
                
                TestCase.objects.create(
                    testCategory=test_category,
                    functionName=fname,
                    description=description,
                    pointsPass=test_data.get('points', 0),
                    type='script' # Default type for script-based tests
                )
        
        # Calculate total max points from parsed tests
        total_points = sum(t.get('points', 0) for t in parsed_tests)
        
        # Update TestCategory maxPoints without triggering save signals
        TestCategory.objects.filter(pk=test_category.pk).update(maxPoints=total_points)
