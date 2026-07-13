# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "codepost.settings")
django.setup()

from autograder.services.executors.python import PythonExecutor
import json

class MockHandler:
    def get_requirements(self):
        return "matplotlib"

# Mock File Object
class MockFile:
    def __init__(self, data, name="test.py"):
        self.data = data
        self.name = name
        self.id = 1
        self.handler = MockHandler()
        
    def get_file_info(self):
        return None, None, None

# Test Logic
def run_verification():
    print("Starting Verification...")
    
    # Combined Student Code + Test Code (as it would appear in a filled template)
    # Note: In real usage, the student code is injected into the template, 
    # and the test code is PART of the template or appended to it.
    # But wait, our template structure is:
    # 1. Framework
    # 2. Student Code (via filler)
    # 3. Test Runner
    
    # So if we want to define tests, we need to inject them into the student code?
    # NO. The USER request says "allows instructors to make their own scripts".
    # This implies the instructor provides the test script which imports/runs student code?
    # OR, the instructor provides a template?
    
    # Our `template.py` has `student_code = """#{FILLER_CODE}"""`.
    # And then it runs `exec(student_code)`.
    # And THEN it runs `TestRunner.get_instance().run_all()`.
    
    # So the tests must be defined EITHER:
    # A) Inside the student code (which is weird for grading)
    # B) Inside the TEMPLATE itself (modified by instructor)
    # C) Appended to the student code?
    
    # Current design assumes the Template IS the test script. 
    # But the `PythonExecutor` loads the standard `template.py` constant.
    
    # For this verification, we will mock the behavior where the input "code" 
    # contains both the student implementation AND the tests.
    # In a real scenario, the instructor would likely use a "Custom Template" 
    # or we would concat the student code with a test suite.
    
    # Let's verify by passing a code block that has both student logic and tests.
    
    # Define Student Code (implementation)
    student_code = """
def add(a, b):
    return a + b

import matplotlib.pyplot as plt
def make_plot():
    plt.plot([1,2,3])
    plt.show()
"""

    # Define Test Code (verification)
    test_code = """
@test("Addition Test", points=10)
def test_add():
    if add(1, 2) != 3:
        raise AssertionError("1+2 should be 3")

@test("Plot Test", points=5)
def test_plot():
    make_plot()
    assert_plots_generated(1)
"""

    mock_file = MockFile(student_code)
    # Pass test_code via kwargs
    executor = PythonExecutor(mock_file, test_code=test_code)
    
    print("Executing Python Script Verification...")
    py_result = executor.execute()
    
    print_result(py_result)

    # ---------------------------------------------------------
    # Notebook Verification
    # ---------------------------------------------------------
    print("\nExecuting Notebook Verification...")
    from autograder.services.executors.python import PythonNotebookExecutor
    
    # Create simple notebook JSON
    notebook_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["def square(x):\n", "    return x * x\n"]
            },
            {
                "cell_type": "code",
                "execution_count": 2,
                "metadata": {},
                "outputs": [],
                "source": ["import matplotlib.pyplot as plt\n", "plt.plot([1,2,3])\n", "plt.show()"]
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.8.5"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    notebook_json_str = json.dumps(notebook_content)
    
    # Mock file for notebook
    class MockNotebookFile(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")
            
    mock_nb_file = MockNotebookFile(notebook_json_str)
    
    # Test code for notebook
    nb_test_code = """
@test("Square Test", points=5)
def test_square():
    assert square(2) == 4
    assert square(3) == 9

@test("Notebook Plot Test")
def test_nb_plot():
    assert_plots_generated(1)

@test("Failing Test", points=5)
def test_failure():
    assert 1 == 2, "1 should be 2 (intentional failure)"
"""

    nb_executor = PythonNotebookExecutor(mock_nb_file, test_code=nb_test_code)
    nb_result = nb_executor.execute()
    
    print_result(nb_result)

    # ---------------------------------------------------------
    # Java Verification
    # ---------------------------------------------------------
    print("\nExecuting Java Verification...")
    from autograder.services.executors.java import JavaExecutor
    
    java_student_code = """
public class Main {
    public static int add(int a, int b) {
        return a + b;
    }
    public static void main(String[] args) {
        System.out.println("Hello from Java");
    }
}
"""
    mock_java_file = MockFile(java_student_code, name="Main.java")
    
    java_test_code = """
    @Test(name="Java Addition Test", points=10)
    public void testAdd() {
        if (Main.add(1, 2) != 3) {
            throw new AssertionError("1+2 should be 3");
        }
    }
    
    @Test(name="StdOut Test", points=5)
    public void testOutput() {
        System.out.println("Test Output");
    }
"""
    
    java_executor = JavaExecutor(mock_java_file, test_code=java_test_code)
    java_result = java_executor.execute()
    
    print_result(java_result)

    # ---------------------------------------------------------
    # C++ Verification
    # ---------------------------------------------------------
    print("\nExecuting C++ Verification...")
    from autograder.services.executors.cpp import CPPExecutor
    
    cpp_student_code = """
#include <iostream>

int add(int a, int b) {
    return a + b;
}

int main() {
    std::cout << "Hello from C++" << std::endl;
    return 0;
}
"""
    mock_cpp_file = MockFile(cpp_student_code, name="source.cpp")
    
    cpp_test_code = """
// Forward declaration of the function to be tested
int add(int a, int b);

TEST(AdditionTest, 10.0) {
    assertTrue(add(1, 2) == 3, "1+2 should be 3");
    assertTrue(add(2, 3) == 5, "2+3 should be 5");
}

TEST(FailureTest, 5.0) {
   // This is expected to fail to demonstrate failure capturing
   // assertTrue(add(1, 1) == 3, "1+1 should be 3 (intentional fail)");
}
"""
    
    cpp_executor = CPPExecutor(mock_cpp_file, test_code=cpp_test_code)
    cpp_result = cpp_executor.execute()
    
    print_result(cpp_result)

    # ---------------------------------------------------------
    # Java Notebook Verification
    # ---------------------------------------------------------
    print("\nExecuting Java Notebook Verification...")
    from autograder.services.executors.java import JavaNotebookExecutor
    
    java_nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["public class Utils {\n", "    public static int multiply(int a, int b) {\n", "        return a * b;\n", "    }\n", "}\n"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "Java", "language": "java", "name": "java"},
            "language_info": {"file_extension": ".java", "mimetype": "text/x-java-source", "name": "java", "version": "17"}
        },
        "nbformat": 4, "nbformat_minor": 4
    }
    
    java_nb_json = json.dumps(java_nb_content)
    
    class MockJavaNB(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")
            
    mock_java_nb = MockJavaNB(java_nb_json)
    
    java_nb_test = """
    public class Tester {
        @Test(name="Mult Test", points=5)
        public void testMult() {
            if (Utils.multiply(2, 3) != 6) throw new RuntimeException("2*3=6");
        }

        @Test(name="Fail Test", points=5)
        public void testFail() {
            if (Utils.multiply(2, 3) == 6) throw new RuntimeException("Intentional Failure");
        }
    }
    """
    
    jnb_executor = JavaNotebookExecutor(mock_java_nb, test_code=java_nb_test)
    jnb_result = jnb_executor.execute()
    print_result(jnb_result)


    # ---------------------------------------------------------
    # C++ Notebook Verification
    # ---------------------------------------------------------
    print("\nExecuting C++ Notebook Verification...")
    from autograder.services.executors.cpp import CPPNotebookExecutor
    
    cpp_nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["#include <iostream>\n", "int subtract(int a, int b) {\n", "    return a - b;\n", "}\n"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "C++", "language": "C++11", "name": "xcpp11"},
            "language_info": {"file_extension": ".cpp", "mimetype": "text/x-c++src", "name": "c++", "version": "11"}
        },
        "nbformat": 4, "nbformat_minor": 4
    }
    
    cpp_nb_json = json.dumps(cpp_nb_content)
    
    class MockCppNB(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")
            
    mock_cpp_nb = MockCppNB(cpp_nb_json)
    
    cpp_nb_test = """
    int subtract(int a, int b);
    
    TEST(SubTest, 5.0) {
        assertTrue(subtract(10, 3) == 7, "10-3 should be 7");
    }

    TEST(FailTest, 5.0) {
        assertTrue(subtract(10, 3) == 0, "10-3 should be 0 (intentional failure)");
    }
    """
    
    cnb_executor = CPPNotebookExecutor(mock_cpp_nb, test_code=cpp_nb_test)
    cnb_result = cnb_executor.execute()
    print_result(cnb_result)

    # ---------------------------------------------------------
    # PHP Notebook Verification
    # ---------------------------------------------------------
    print("\nExecuting PHP Notebook Verification...")
    from autograder.services.executors.php import PHPNotebookExecutor

    php_nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["<?php\n", "function add($a, $b) {\n", "    return $a + $b;\n", "}\n"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "PHP", "language": "php", "name": "php"},
            "language_info": {"file_extension": ".php", "mimetype": "text/x-php", "name": "php", "version": "8.2"}
        },
        "nbformat": 4, "nbformat_minor": 4
    }

    php_nb_json = json.dumps(php_nb_content)

    class MockPhpNB(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")

    mock_php_nb = MockPhpNB(php_nb_json)

    _php_test_code = """
    Tester::test("Addition Test", 10.0, function() {
        if (add(1, 2) !== 3) {
            throw new Exception("1+2 should be 3");
        }
    });

    Tester::test("Failure Test", 5.0, function() {
        if (add(1, 1) === 3) { // This condition is false, so it won't throw? Wait, I want it to fail.
             // If 1+1 (2) !== 3 (True).
             // Wait, I want to Assert FAIL.
             // throw new Exception("Intentional Failure");
             throw new Exception("Intentional Failure");
        }
    });
    """
    # Wait, the failure test should FAIL. logic above:
    # if (add(1,1) === 3) -> False. Code continues. Test PASSES?
    # I want it to FAIL.
    # So I should just throw Exception.
    
    php_test_code_corrected = """
    Tester::test("Addition Test", 10.0, function() {
        if (add(1, 2) !== 3) {
            throw new Exception("1+2 should be 3");
        }
    });
    
    Tester::test("Fail Test", 5.0, function() {
        throw new Exception("Intentional Failure");
    });
    """

    pnb_executor = PHPNotebookExecutor(mock_php_nb, test_code=php_test_code_corrected)
    pnb_result = pnb_executor.execute()
    print_result(pnb_result)

    # ---------------------------------------------------------
    # Node.js Notebook Verification
    # ---------------------------------------------------------
    print("\nExecuting Node.js Notebook Verification...")
    from autograder.services.executors.node import NodeNotebookExecutor

    js_nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["function multiply(a, b) {\n", "    return a * b;\n", "}\n"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "JavaScript", "language": "javascript", "name": "javascript"},
            "language_info": {"file_extension": ".js", "mimetype": "application/javascript", "name": "javascript", "version": "ES6"}
        },
        "nbformat": 4, "nbformat_minor": 4
    }

    js_nb_json = json.dumps(js_nb_content)

    class MockJsNB(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")

    mock_js_nb = MockJsNB(js_nb_json)

    js_test_code = """
    test("Multiply Test", 10.0, function() {
        if (multiply(2, 3) !== 6) {
            throw new Error("2*3 should be 6");
        }
    });
    
    test("Fail Test", 5.0, function() {
        throw new Error("Intentional Failure");
    });
    """

    jsnb_executor = NodeNotebookExecutor(mock_js_nb, test_code=js_test_code)
    jsnb_result = jsnb_executor.execute()
    print_result(jsnb_result)

    # ---------------------------------------------------------
    # R Notebook Verification
    # ---------------------------------------------------------
    print("\nExecuting R Notebook Verification...")
    from autograder.services.executors.r import RNotebookExecutor

    r_nb_content = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["add <- function(a, b) {\n", "    a + b\n", "}\n"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "R", "language": "R", "name": "ir"},
            "language_info": {"file_extension": ".r", "mimetype": "text/x-r-source", "name": "R", "version": "4.0"}
        },
        "nbformat": 4, "nbformat_minor": 4
    }

    r_nb_json = json.dumps(r_nb_content)

    class MockRNB(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")

    mock_r_nb = MockRNB(r_nb_json)

    r_test_code = """
    run_test("Addition Test", 10.0, function() {
        if (add(1, 2) != 3) {
            stop("1+2 should be 3")
        }
    })
    
    run_test("Fail Test", 5.0, function() {
        stop("Intentional Failure")
    })
    """

    rnb_executor = RNotebookExecutor(mock_r_nb, test_code=r_test_code)
    rnb_result = rnb_executor.execute()
    print_result(rnb_result)

    # ===============================================
    # Ruby Notebook Verification
    # ===============================================
    print("\nExecuting Ruby Notebook Verification...")
    from autograder.services.executors.ruby import RubyNotebookExecutor
    
    # Create mock Ruby notebook with a simple function
    ruby_nb_json = json.dumps({
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": ["def add(a, b)\n", "  a + b\n", "end\n"]
            }
        ],
        "metadata": {
            "kernelspec": {"display_name": "Ruby 3.0.0", "language": "ruby", "name": "ruby"},
            "language_info": {"file_extension": ".rb", "mimetype": "application/x-ruby", "name": "ruby", "version": "3.0.0"}
        },
        "nbformat": 4, "nbformat_minor": 4
    })
    
    class MockRubyNB(MockFile):
        def __init__(self, data):
            super().__init__(data, name="test.ipynb")
    
    mock_ruby_nb = MockRubyNB(ruby_nb_json)
    
    ruby_test_code = """
    run_test("Addition Test", 10) do
        result = add(1, 2)
        raise "1+2 should be 3, got #{result}" unless result == 3
    end
    
    run_test("Fail Test", 5) do
        raise "Intentional Failure"
    end
    """
    
    ruby_nb_executor = RubyNotebookExecutor(mock_ruby_nb, test_code=ruby_test_code)
    ruby_nb_result = ruby_nb_executor.execute()
    print_result(ruby_nb_result)

def print_result(result):
    print(f"Success: {result.success}")
    if result.err:
        print(f"Error: {result.err}")
    
    print(f"Stdout (Raw Repr): {repr(result.stdout)}")
    print(f"Stderr (Tail): {result.stderr[-200:]}")
        
    print(f"System Logs: {len(result.system_logs)} lines")
    
    if result.tests:
        print("\n--- Test Results ---")
        for t in result.tests:
            status_icon = "✓" if t['passed'] else "✗"
            print(f"{status_icon} {t['name']}: {t['score']}/{t['max_score']} - {t['status']}")
            if t['error']:
                print(f"   Error: {t['error']}")
    else:
        print("\nNo structured test results found.")
        print(f"Stdout head: {result.stdout[:200]}")
        print(f"Stderr:\n{result.stderr}")


if __name__ == "__main__":
    run_verification()
