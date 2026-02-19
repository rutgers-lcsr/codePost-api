
import ast
import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from core.models import TestCategory, TestCase

logger = logging.getLogger(__name__)

class TestParsingService:
    @staticmethod
    def parse_script(test_category: TestCategory, language: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parse the test script to identify @test decorated functions or equivalents.
        Returns a list of test definitions {name, points, etc}.
        """
        script = test_category.testScript
        if not script:
            return []

        # Normalize language if provided
        normalized_language = (language or "").lower()

        # Use explicit language if provided, otherwise detect
        if normalized_language.startswith('python') or (not language and "def " in script and "@test" in script):
            return TestParsingService._parse_python(script)
        elif normalized_language == 'java' or normalized_language.startswith('java-') or (not language and "@Test" in script and "public" in script):
            return TestParsingService._parse_java(script)
        elif normalized_language == 'r' or normalized_language.startswith('r-') or (not language and "run_test(" in script):
            return TestParsingService._parse_r(script)
        elif any(token in normalized_language for token in ['node', 'javascript', 'js', 'typescript']):
            return TestParsingService._parse_node(script)
        elif normalized_language.startswith('php'):
            return TestParsingService._parse_php(script)
        elif normalized_language.startswith('ruby') or normalized_language.startswith('rb'):
            return TestParsingService._parse_ruby(script)
        elif normalized_language in ['c/c++', 'c++', 'cpp', 'c'] or 'c++' in normalized_language or 'cpp' in normalized_language:
            return TestParsingService._parse_cpp(script)
        
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
                                # First arg is usually name (title)
                                if isinstance(decorator.args[0], ast.Constant):
                                     test_info['name'] = decorator.args[0].value
                            
                            for keyword in decorator.keywords:
                                if keyword.arg == 'points':
                                    if isinstance(keyword.value, (ast.Constant, ast.Num)):
                                         test_info['points'] = getattr(keyword.value, 'value', getattr(keyword.value, 'n', 0))
                                elif keyword.arg == 'timeout':
                                    if isinstance(keyword.value, (ast.Constant, ast.Num)):
                                         test_info['timeout'] = int(getattr(keyword.value, 'value', getattr(keyword.value, 'n', 0)))
                                elif keyword.arg == 'description':
                                    if isinstance(keyword.value, ast.Constant):
                                         test_info['description'] = keyword.value.value
                                elif keyword.arg == 'name':
                                    if isinstance(keyword.value, ast.Constant):
                                         test_info['name'] = keyword.value.value
                            
                            tests.append(test_info)
        except Exception as e:
            logger.error(f"Failed to parse Python script: {e}")
        return tests

    @staticmethod
    def _parse_java(script: str) -> List[Dict[str, Any]]:
        # Naive regex parsing for Java @Test
        tests = []
        # Pattern: @Test(name="...", points=5) public <returnType> testName()
        # This is a simplification; a real parser would be better but expensive
        pattern = r'@Test\s*\((.*?)\)\s*public\s+[\w<>\[\]]+\s+(\w+)'
        matches = re.finditer(pattern, script, re.DOTALL)
        
        for match in matches:
            params = match.group(1)
            func_name = match.group(2)
            test_info = {'functionName': func_name, 'name': func_name, 'points': 0}
            
            # Extract name
            name_match = re.search(r'name\s*=\s*"([^"]+)"', params)
            if name_match:
                test_info['name'] = name_match.group(1)
            
            # Extract description
            desc_match = re.search(r'description\s*=\s*"([^"]+)"', params)
            if desc_match:
                test_info['description'] = desc_match.group(1)
                
            # Extract points
            points_match = re.search(r'points\s*=\s*(\d+(\.\d+)?)', params)
            if points_match:
                test_info['points'] = float(points_match.group(1))

            # Extract timeout
            timeout_match = re.search(r'timeout\s*=\s*(\d+(\.\d+)?)', params)
            if timeout_match:
                test_info['timeout'] = int(float(timeout_match.group(1)))
                
            tests.append(test_info)
            
        return tests

    @staticmethod
    def _parse_r(script: str) -> List[Dict[str, Any]]:
        # Canonical R parser support:
        # run_test("Name", 5, "Desc", function() { ... }, 30)
        tests = []

        # Runtime aligned style:
        # run_test("Name", 5, "Desc", function() { ... }, 30)
        run_test_pattern = r'run_test\s*\(\s*(["\'])(.*?)\1\s*,\s*(\d+(?:\.\d+)?)\s*(?:,\s*(["\'])(.*?)\4)?\s*(?:,\s*function\b|\s*\))'
        for match in re.finditer(run_test_pattern, script, re.DOTALL):
            test_info = {
                'functionName': re.sub(r'\W+', '_', match.group(2)).strip('_').lower() or 'run_test',
                'name': match.group(2),
                'points': float(match.group(3)),
                'description': match.group(5) or "",
            }
            tests.append(test_info)

        return tests

    @staticmethod
    def _parse_php(script: str) -> List[Dict[str, Any]]:
        tests = []
        # Pattern: Tester::test("Name", 10.0, "Desc", function() { ... }, 30)
        pattern = r"Tester::test\s*\(\s*([\"'])(.*?)\1\s*,\s*(\d+(?:\.\d+)?)\s*(?:,\s*([\"'])(.*?)\4)?\s*(?:,\s*function|\s*\))"
        matches = re.finditer(pattern, script, re.DOTALL)

        for match in matches:
            name = match.group(2)
            points = float(match.group(3))
            description = match.group(5) or ""

            tests.append({
                'functionName': re.sub(r'\W+', '_', name).strip('_').lower() or 'tester_test',
                'name': name,
                'points': points,
                'description': description,
            })

        return tests

    @staticmethod
    def _parse_ruby(script: str) -> List[Dict[str, Any]]:
        tests = []
        # Pattern: run_test("Name", 10, "Desc") do ... end
        #          run_test("Name", 10, "Desc", 30) do ... end
        pattern = r"run_test\s*\(\s*([\"'])(.*?)\1\s*,\s*(\d+(?:\.\d+)?)\s*(?:,\s*([\"'])(.*?)\4)?\s*(?:,\s*(\d+(?:\.\d+)?))?\s*\)"
        matches = re.finditer(pattern, script, re.DOTALL)

        for match in matches:
            name = match.group(2)
            points = float(match.group(3))
            description = match.group(5) or ""

            tests.append({
                'functionName': re.sub(r'\W+', '_', name).strip('_').lower() or 'run_test',
                'name': name,
                'points': points,
                'description': description,
                **({'timeout': int(float(match.group(6)))} if match.group(6) else {}),
            })

        return tests

    @staticmethod
    def _parse_node(script: str) -> List[Dict[str, Any]]:
        tests = []
        # Pattern (runtime-aligned):
        # test("Name", 5, "Desc", function() { ... });
        # test("Name", 5, "Desc", function() { ... }, 30);
        pattern = r"test\s*\(\s*([\"'])(.*?)\1\s*,\s*(\d+(?:\.\d+)?)\s*,\s*([\"'])(.*?)\4(?P<rest>[\s\S]*?)\)\s*;"
        matches = re.finditer(pattern, script, re.DOTALL)

        for match in matches:
            name = match.group(2)
            points = float(match.group(3))
            description = match.group(5) or ""
            rest = (match.group('rest') or '').strip()

            timeout_val = None
            timeout_match = re.search(r',\s*(\d+(?:\.\d+)?)\s*$', rest)
            if timeout_match:
                timeout_val = timeout_match.group(1)

            test_info = {
                'functionName': name,
                'name': name,
                'points': points,
                'description': description,
            }

            if timeout_val:
                test_info['timeout'] = int(float(timeout_val))

            tests.append(test_info)

        return tests

    @staticmethod
    def _parse_cpp(script: str) -> List[Dict[str, Any]]:
        tests = []

        # Parse in script order across all supported macro variants.
        combined_pattern = r'''
            TEST_DESC_TIMEOUT\s*\(\s*(\w+)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*"([^"]*)"\s*,\s*(\d+(?:\.\d+)?)\s*\)
            |TEST_TIMEOUT\s*\(\s*(\w+)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)
            |TEST_DESC\s*\(\s*(\w+)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*"([^"]*)"\s*\)
            |TEST\s*\(\s*(\w+)\s*,\s*(\d+(?:\.\d+)?)\s*\)
        '''

        for match in re.finditer(combined_pattern, script, re.DOTALL | re.VERBOSE):
            if match.group(1):
                # TEST_DESC_TIMEOUT(name, points, description, timeout)
                tests.append({
                    'functionName': match.group(1),
                    'name': match.group(1),
                    'points': float(match.group(2)),
                    'description': match.group(3),
                    'timeout': int(float(match.group(4)))
                })
            elif match.group(5):
                # TEST_TIMEOUT(name, points, timeout)
                tests.append({
                    'functionName': match.group(5),
                    'name': match.group(5),
                    'points': float(match.group(6)),
                    'timeout': int(float(match.group(7)))
                })
            elif match.group(8):
                # TEST_DESC(name, points, description)
                tests.append({
                    'functionName': match.group(8),
                    'name': match.group(8),
                    'points': float(match.group(9)),
                    'description': match.group(10)
                })
            elif match.group(11):
                # TEST(name, points)
                tests.append({
                    'functionName': match.group(11),
                    'name': match.group(11),
                    'points': float(match.group(12))
                })

        return tests

    @staticmethod
    def update_test_cases(test_category: TestCategory):
        """
        Sync execution of parse_script with the database TestCase objects.
        """
        language = None
        try:
            environment = getattr(getattr(test_category, 'assignment', None), 'environment', None)
            language = getattr(environment, 'language', None)
        except Exception:
            language = None

        parsed_tests = TestParsingService.parse_script(test_category, language=language)
        
        # Get existing tests (keyed by functionName to match script source)
        current_tests = {t.functionName: t for t in test_category.testCases.all() if t.functionName}
        parsed_fnames = set()
        
        for test_data in parsed_tests:
            fname = test_data['functionName']
            parsed_fnames.add(fname)
            
            # Prepare fields
            description = test_data.get('name', fname)
            if description == fname:
                description = fname.replace('_', ' ').title()
            
            explanation = test_data.get('description', "")

            if fname in current_tests:
                # Update existing
                t = current_tests[fname]
                t.description = description
                t.explanation = explanation
                t.pointsPass = test_data.get('points', 0)
                t.timeout = test_data.get('timeout', 30)
                t.save()
            else:
                # Create new
                TestCase.objects.create(
                    testCategory=test_category,
                    functionName=fname,
                    description=description,
                    explanation=explanation,
                    pointsPass=test_data.get('points', 0),
                    timeout=test_data.get('timeout', 30),
                    type='script' # Default type for script-based tests
                )
        
        # Delete obsolete tests
        # Tests that exist in DB (with functionName) but are NOT in the parsed script
        for fname, test_case in current_tests.items():
            if fname not in parsed_fnames:
                logger.info(f"Removing obsolete test case: {fname} (ID: {test_case.pk})")
                test_case.delete()
        
        # Calculate total max points from parsed tests
        total_points = sum(t.get('points', 0) for t in parsed_tests)
        
        # Update TestCategory maxPoints without triggering save signals
        TestCategory.objects.filter(pk=test_category.pk).update(maxPoints=total_points)
