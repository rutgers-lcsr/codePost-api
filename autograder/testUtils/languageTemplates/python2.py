# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
# Params: importName, cmd, output, test
PYTHON2_IO_TEST = """
import json
import traceback
import os
import re

try:
    import sys
    sys.path.append('/files')
    import {fileName}
    isPassed = False
    errorLogs = ''

    codePostResult = {cmd}
    codePostExpected = {output}
    if ({isRegExp}):
        if (re.match(codePostExpected, codePostResult)):
            isPassed=True
        else:
            errorLogs = "\\n=============================\\nEXPECTED REGEX:\\n"+ str(codePostExpected)+ "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + str(codePostResult) + "\\n=============================\\n"
    else:
        resultToCompare = codePostResult
        expectedToCompare = codePostExpected
        if ({isFlexible} and isinstance(resultToCompare, str) and isinstance(expectedToCompare, str)):
            resultToCompare = resultToCompare.lower().replace(' ', '').replace('\\n', '')
            expectedToCompare = expectedToCompare.lower().replace(' ', '').replace('\\n', '')

        if (resultToCompare == expectedToCompare):
            isPassed=True
        else:
            isPassed=False
            errorLogs = "\\n=============================\\nEXPECTED OUTPUT:\\n"+str(expectedToCompare)+"\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + str(resultToCompare) + "\\n=============================\\n"
except Exception as e:
    isPassed=False
    errorLogs = traceback.format_exc()
f = open(\"/outputs/{test}.json\", \"w\")
json.dump({{\"id\": \"{test}\", \"passed\": isPassed, \"log\": str(errorLogs)}}, f)
f.close()
"""


# Params: importName, cmd, output, test
PYTHON2_IO_OUTPUT_TEST = """
import json
import traceback
import os
from cStringIO import StringIO
import sys
import re

old_stdout = sys.stdout
sys.stdout = mystdout = StringIO()
try:
    sys.path.append('/files')
    import {fileName}
    isPassed = False
    errorLogs = ''
    {cmd}
    codePostResult = mystdout.getvalue().strip()
    codePostExpected = {output}

    if ({isRegExp}):
        if (re.match(codePostExpected, codePostResult)):
            isPassed=True
        else:
            errorLogs = "\\n=============================\\nEXPECTED REGEX:\\n"+ str(codePostExpected)+ "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + str(codePostResult) + "\\n=============================\\n"
    else:
        resultToCompare = codePostResult
        expectedToCompare = codePostExpected
        if ({isFlexible} and isinstance(resultToCompare, str) and isinstance(expectedToCompare, str)):
            resultToCompare = resultToCompare.lower().replace(' ', '').replace('\\n', '')
            expectedToCompare = expectedToCompare.lower().replace(' ', '').replace('\\n', '')

        if (resultToCompare == expectedToCompare):
            isPassed=True
        else:
            isPassed=False
            errorLogs = "\\n=============================\\nEXPECTED OUTPUT:\\n"+ expectedToCompare +"\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + resultToCompare + "\\n=============================\\n"
except Exception as e:
    isPassed=False
    errorLogs = traceback.format_exc()
finally:
    sys.stdout = old_stdout
f = open(\"/outputs/{test}.json\", \"w\")
json.dump({{\"id\": \"{test}\", \"passed\": isPassed, \"log\": str(errorLogs)}}, f)
f.close()
"""

# Params: cmd, testName
PYTHON2_UNIT_TEST = """
import json
import traceback
import os

class TestOutput:
    def __init__(self, passed, logs):
        assert (isinstance(passed, bool))
        assert (isinstance(logs, str))
        self.passed = passed
        self.logs = logs

try:
    import sys
    sys.path.append('/files')
    {cmd}
    output = TestCase()
    assert(isinstance(output, TestOutput))
except Exception as e:
    errorLogs = traceback.format_exc()
    output = TestOutput(False, str(errorLogs))
f = open(\"/outputs/{test}.json\", \"w\")
json.dump({{\"id\": \"{test}\", \"passed\": output.passed, \"log\": output.logs}}, f)
f.close()
"""
