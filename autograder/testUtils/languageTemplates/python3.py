# Params: importName, cmd, output, test
PYTHON3_IO_TEST = """
import json
import traceback
import os
import re

# Plot verification setup
plot_generated = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    _orig_show = plt.show
    def _mock_show(*args, **kwargs):
        global plot_generated
        plot_generated = True
        return _orig_show(*args, **kwargs)
    
    plt.show = _mock_show
except ImportError:
    pass

try:
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
            errorLogs = "\\n=============================\\nEXPECTED OUTPUT:\\n" + str(expectedToCompare) + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + str(resultToCompare) + "\\n=============================\\n"

    # Plot verification check
    if {expectPlot}:
        if not plot_generated:
            isPassed = False
            errorLogs += "\\n[Failure] Expected a plot to be generated, but none was detected (via plt.show())."

except Exception as e:
    isPassed=False
    errorLogs = traceback.format_exc()

f = open(\"/outputs/{test}.json\", \"w\")
json.dump({{\"id\": \"{test}\", \"passed\": isPassed, \"log\": str(errorLogs)}}, f)
f.close()
"""

# Params: importName, cmd, output, test
PYTHON3_IO_OUTPUT_TEST = """
import json
import traceback
import os
from io import StringIO
import sys
import re

# Plot verification setup
plot_generated = False
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    _orig_show = plt.show
    def _mock_show(*args, **kwargs):
        global plot_generated
        plot_generated = True
        return _orig_show(*args, **kwargs)
    
    plt.show = _mock_show
except ImportError:
    pass

old_stdout = sys.stdout
sys.stdout = mystdout = StringIO()
try:
    import {fileName}
    isPassed = False
    errorLogs = ''
    {cmd}
    codePostExpected = {output}
    codePostResult = mystdout.getvalue().strip()

    if ({isRegExp}):
        if (re.match(codePostExpected, codePostResult)):
            isPassed=True
        else:
            errorLogs = "\\n=============================\\nEXPECTED REGEX:\\n"+ codePostExpected+ "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + codePostResult + "\\n=============================\\n"
    else:
        resultToCompare = codePostResult
        expectedToCompare = codePostExpected
        if ({isFlexible}):
            resultToCompare = resultToCompare.lower().replace(' ', '').replace('\\n', '')
            expectedToCompare = expectedToCompare.lower().replace(' ', '').replace('\\n', '')

        if (resultToCompare == expectedToCompare):
            isPassed=True
        else:
            isPassed=False
            errorLogs = "\\n=============================\\nEXPECTED OUTPUT:\\n"+ expectedToCompare+ "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + resultToCompare + "\\n=============================\\n"

    # Plot verification check
    if {expectPlot}:
        if not plot_generated:
            isPassed = False
            errorLogs += "\\n[Failure] Expected a plot to be generated, but none was detected (via plt.show())."

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
PYTHON3_UNIT_TEST = """
import json
import traceback
import os

class TestOutput:
    def __init__(self, passed, logs):
        assert (isinstance(passed, bool))
        assert (isinstance(logs, str))
        self.passed = passed
        self.logs = logs

# Plot verification setup
# For Unit Tests, we don't automatically check for plots unless specified, 
# but usually unit tests return TestOutput directly.
# If expectPlot support is needed here, we'd need to thread it through.
# For now, leaving as-is or adding safe mock.

try:
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
