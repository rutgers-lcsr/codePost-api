# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import sys
import os
sys.path.append('/staff/users/mk1800/Development/codePost-api')

from autograder.testUtils.buildHelpers import createDockerFile

try:
    print("Testing createDockerFile...")
    output = createDockerFile(
        language="python-3.12",
        build_type="default",
        customDockerFile="",
        dependencies=["pip install pandas"],
        environmentID=1,
        dependencies_file_content="numpy==1.0.0"
    )
    print("Success!")
    print(output)
except Exception as e:
    print("Failed")
    import traceback
    traceback.print_exc()
