# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from enum import Enum
from rest_framework import serializers


class TestType(Enum):
    __test__ = False
    PYTHON2_IO_OUTPUT = 0
    PYTHON2_IO_RETURN = 1
    PYTHON2_UNIT = 2
    PYTHON3_IO_OUTPUT = 3
    PYTHON3_IO_RETURN = 4
    PYTHON3_UNIT = 5
    JAVA_UNIT = 6
    JAVA_IO_OUTPUT = 7
    JAVA_IO_RETURN = 8
    IO_CLI = 9
    BASH = 10
    BASH_GROUP = 11

    def get_type(test_type_string, language, isReturn):
        """
        Returns an enum based on given language name and test type inputs
        """
        if test_type_string == "shell":
            return TestType.BASH
        if test_type_string == "file":
            return TestType.BASH_GROUP
        if test_type_string == "io_cli":
            return TestType.IO_CLI
        if language.startswith("python-3"):
            if test_type_string == "io" and isReturn:
                return TestType.PYTHON3_IO_RETURN
            if test_type_string == "io":
                return TestType.PYTHON3_IO_OUTPUT
            if test_type_string == "unit":
                return TestType.PYTHON3_UNIT
        if language == "python-2.7":
            if test_type_string == "io" and isReturn:
                return TestType.PYTHON2_IO_RETURN
            if test_type_string == "io":
                return TestType.PYTHON2_IO_OUTPUT
            if test_type_string == "unit":
                return TestType.PYTHON2_UNIT
        if language.startswith("java"):
            if test_type_string == "io" and isReturn:
                return TestType.JAVA_IO_RETURN
            if test_type_string == "io":
                return TestType.JAVA_IO_OUTPUT
            if test_type_string == "unit":
                return TestType.JAVA_UNIT

        raise serializers.ValidationError("Test Type not supported")

    def get_test_extension(test_type):
        if test_type in [
            TestType.PYTHON2_IO_RETURN,
            TestType.PYTHON2_IO_OUTPUT,
            TestType.PYTHON3_IO_RETURN,
            TestType.PYTHON3_IO_OUTPUT,
            TestType.PYTHON2_UNIT,
            TestType.PYTHON3_UNIT,
        ]:
            return ".py"
        elif test_type in [
            TestType.JAVA_IO_RETURN,
            TestType.JAVA_IO_OUTPUT,
            TestType.JAVA_UNIT,
        ]:
            return ".java"
        else:
            return ".sh"
