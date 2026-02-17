"""
DEPRECATED: This module contains legacy parsing logic for autograder results.
Modern testing infrastructure uses TestService and Executor classes which handle parsing directly.
This file should be removed once all legacy specific-test-file logic is migrated.
"""

from autograder.testUtils.languageTemplates.bash import (
    BASH_TEST,
    BASH_TEST_GROUP,
    IO_CLI_TEST,
)
from autograder.testUtils.languageTemplates.python2 import (
    PYTHON2_IO_TEST,
    PYTHON2_UNIT_TEST,
    PYTHON2_IO_OUTPUT_TEST,
)
from autograder.testUtils.languageTemplates.python3 import (
    PYTHON3_IO_TEST,
    PYTHON3_UNIT_TEST,
    PYTHON3_IO_OUTPUT_TEST,
)
from autograder.testUtils.languageTemplates.java import (
    JAVA_IO_TEST,
    JAVA_IO_OUTPUT_TEST,
    JAVA_UNIT_TEST,
)
from autograder.testUtils.test_types import TestType

from core.models import TestCase


def parseTests(testCases, language):
    templates = []
    for t in testCases:
        test_type = TestType.get_type(t.type, language, t.checkReturn)
        extension = TestType.get_test_extension(test_type)
        templates.append(
            {
                "id": t.id,
                "category": t.testCategory.id,
                "name": "_test{}{}".format(t.id, extension),
                "code": _get_test_template(test_type, t),
                "errorIfMissing": True,
            }
        )
    return templates





def writeCmdScript(testTemplates, runBefore, language):
    commands = ["#!/bin/bash"]
    commands.append(
        "##########################################################################################"
    )
    commands.append(
        "# README: When you run tests on student code, this file is run. You can't edit it"
    )
    commands.append(
        "# directly, but it will update in response to changes you make to your environment"
    )
    commands.append("# and tests. Read more about each section below.")
    commands.append(
        "##########################################################################################\n\n"
    )

    if runBefore:
        commands.append(
            "##########################################################################################"
        )
        commands.append("# 1. Run Script: To edit this, go to the 'Environment' tab")
        commands.append(
            "##########################################################################################"
        )
        commands.append(runBefore)

    commands.append(
        "\n##########################################################################################"
    )
    commands.append(
        "# 2. Generated tests: These are created when you make new tests in the test editor"
    )
    commands.append(
        "##########################################################################################"
    )
    for t in sorted(
        testTemplates, key=lambda x: (x["category"], x["id"]), reverse=False
    ):
        # Figure out the run command based on the file
        commands.append(getCmd(t, language))

    commands.append(
        "\n##########################################################################################"
    )
    commands.append(
        "# 3. Test files: To add test files, click 'Add file', and create a 'Test file'."
    )
    commands.append("# They will be executed here.")
    commands.append(
        "##########################################################################################"
    )


    cmds_string = "\n".join(commands)
    return cmds_string


def getCmd(template, language):
    name = template["name"]
    if name.endswith(".py"):
        if language == "python-2.7":
            command = "python {}".format(name)
        else:
            command = "python3 {}".format(name)
    elif name.endswith(".java"):
        command = "javac -cp . {} && java -ea -cp . {}".format(
            name, name.replace(".java", "")
        )
    elif name.endswith(".sh"):
        command = "bash {}".format(name)
    else:
        command = 'echo "Test {} type not supported."'.format(name)
    return command


# fileCompare: are we comparing the output to a file?
def _bash_format_output(output, fileCompare=False):
    output = output.replace('"', "")
    if fileCompare:
        return "cat {}".format(output)
    return "echo '{}'".format(output)


# isPrint: are we checking for a a printed output or a return output
# fileCompare: are we comparing the output to a file?
def _python_format_output(output, isPrint=False, fileCompare=False, isRegExp=False):
    if fileCompare:
        return 'open("{}").read()'.format(output.replace('"', "").replace("'", ""))
    elif isPrint or isRegExp:
        return '"{}"'.format(output.replace('"', "").replace("'", ""))
    return "{}".format(output.replace('"', "'"))


# fileCompare: are we comparing the output to a file?
def _java_format_output(output, isPrint=False, fileCompare=False, isRegExp=False):
    if fileCompare:
        return 'String.valueOf(new String(Files.readAllBytes(Paths.get("{}")))).replaceAll("\\\\r", "")'.format(
            output.replace('"', "").replace("'", "")
        )
    elif isPrint or isRegExp:
        return '"{}"'.format(output.replace('"', "").replace("'", ""))
    return "{}".format(output.replace("'", '"'))


def _get_test_template(test_type, test):
    """
    Based on a test type and test specs, creates a file that executes those specs.
    Each test writes to a file named Test{id}.json in the local folder /tests/.
    The format for Test{id}.json is {"id": <string>, "passed": <boolean>, "logs": <string>}

    The /tests/ folder must be mounted as a Docker volume so the host can read the outputs.
    """

    #################################### Python2 ################################################################
    if test_type == TestType.PYTHON2_IO_RETURN:
        """
        Python functional test (no code). The user inputs the name of a function that they want to test
        and the expected output. This imports the file containing the function, and calls an assertion statement.
        """
        cmd = "{}.{}({})".format(test.fileName.split(".")[0], test.function, test.input)
        return PYTHON2_IO_TEST.format(
            fileName=test.fileName.split(".")[0],
            cmd=cmd,
            output=_python_format_output(
                test.expectedOutput, False, test.outputIsFile, test.outputIsRegexp
            ),
            test=test.id,
            isFlexible=test.isFlexible,
            isRegExp=test.outputIsRegexp,
        )

    if test_type == TestType.PYTHON2_IO_OUTPUT:
        """
        Python functional test (no code). The user inputs the name of a function that they want to test
        and the expected output. This imports the file containing the function, and calls an assertion statement.
        """
        cmd = "{}.{}({})".format(test.fileName.split(".")[0], test.function, test.input)
        return PYTHON2_IO_OUTPUT_TEST.format(
            fileName=test.fileName.split(".")[0],
            cmd=cmd,
            output=_python_format_output(
                test.expectedOutput, True, test.outputIsFile, test.outputIsRegexp
            ),
            test=test.id,
            isFlexible=test.isFlexible,
            isRegExp=test.outputIsRegexp,
        )

    if test_type == TestType.PYTHON2_UNIT:
        """
        Python unit test. The user inputs a function called Test() that contains an assert statement.
        This runs that function, and if it doesn't fail, it passes it.
        """
        # Add two tabs before every line in input
        cmd = "\t\t".join(test.text.splitlines(True))
        return PYTHON2_UNIT_TEST.format(cmd=cmd, test=test.id).replace("\t", "  ")

    #################################### Python3 ################################################################
    if test_type == TestType.PYTHON3_IO_RETURN:
        """
        Python functional test (no code). The user inputs the name of a function that they want to test
        and the expected output. This imports the file containing the function, and calls an assertion statement.
        """
        cmd = "{}.{}({})".format(test.fileName.split(".")[0], test.function, test.input)
        return PYTHON3_IO_TEST.format(
            fileName=test.fileName.split(".")[0],
            cmd=cmd,
            output=_python_format_output(
                test.expectedOutput, False, test.outputIsFile, test.outputIsRegexp
            ),
            test=test.id,
            isFlexible=test.isFlexible,
            isRegExp=test.outputIsRegexp,
            expectPlot=str(test.expectPlot),
        )

    if test_type == TestType.PYTHON3_IO_OUTPUT:
        """
        Python functional test (no code). The user inputs the name of a function that they want to test
        and the expected output. This imports the file containing the function, and calls an assertion statement.
        """
        cmd = "{}.{}({})".format(test.fileName.split(".")[0], test.function, test.input)
        return PYTHON3_IO_OUTPUT_TEST.format(
            fileName=test.fileName.split(".")[0],
            cmd=cmd,
            output=_python_format_output(
                test.expectedOutput, True, test.outputIsFile, test.outputIsRegexp
            ),
            test=test.id,
            isFlexible=test.isFlexible,
            isRegExp=test.outputIsRegexp,
            expectPlot=str(test.expectPlot),
        )

    if test_type == TestType.PYTHON3_UNIT:
        """
        Python unit test. The user inputs a function called Test() that contains an assert statement.
        This runs that function, and if it doesn't fail, it passes it.
        """
        # Add two tabs before every line in input
        cmd = "\t\t".join(test.text.splitlines(True))
        return PYTHON3_UNIT_TEST.format(cmd=cmd, test=test.id).replace("\t", "  ")

    #################################### Java ################################################################
    if test_type == TestType.JAVA_IO_RETURN:
        """
        Java functional test (no code). The user inputs the name of a function that they want to test
        and the expected output. This imports all the student files, and calls an assertion statement.
        """
        command = "{}.{}({})".format(
            test.fileName.split(".")[0], test.function, test.input
        )
        return JAVA_IO_TEST.format(
            test=test.id,
            command=command,
            output=_java_format_output(
                test.expectedOutput, False, test.outputIsFile, test.outputIsRegexp
            ),
            isFlexible=("true" if test.isFlexible else "false"),
            isRegExp=("true" if test.outputIsRegexp else "false"),
        )

    if test_type == TestType.JAVA_IO_OUTPUT:
        """
        Java functional test (no code). The user inputs the name of a function that they want to test
        and the expected output. This imports all the student files, and calls an assertion statement.
        """
        command = "{}.{}({})".format(
            test.fileName.split(".")[0], test.function, test.input
        )
        return JAVA_IO_OUTPUT_TEST.format(
            test=test.id,
            command=command,
            output=_java_format_output(
                test.expectedOutput, True, test.outputIsFile, test.outputIsRegexp
            ),
            isFlexible=("true" if test.isFlexible else "false"),
            isRegExp=("true" if test.outputIsRegexp else "false"),
        )

    if test_type == TestType.JAVA_UNIT:
        """
        Java unit test. The user inputs a function that does an operation and outputs the
        pass status and logs, formatted in a TestOutput object. Example syntax for the command is below:

            public static TestOutput TestCase() {
                if (hello.multiply() == 4){
                    TestOutput passed = new TestOutput(true, "good job");
                    return passed;
                }
                else {
                    TestOutput failed = new TestOutput(false, "base job");
                    return failed;
                }
            };
        """

        (imports, command) = test.text.split("class Test ")

        template = JAVA_UNIT_TEST.format(
            test=test.id,
            imports=imports,
            command="private static class Test {}".format(command),
        )
        return template

    #################################### Bash ################################################################
    if test_type == TestType.IO_CLI:
        return IO_CLI_TEST.format(
            test=test.id,
            command=test.text,
            output=_bash_format_output(test.expectedOutput, test.outputIsFile),
            isFlexible=("true" if test.isFlexible else "false"),
            isRegExp=("true" if test.outputIsRegexp else "false"),
        )
    if test_type == TestType.BASH:
        return BASH_TEST.format(test=test.id, command=test.text)
    ## FIXME: code should never reach here. Put some warning/error
    return
