# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
# Params: cmd, testName, isFlexible, isRegExp
IO_CLI_TEST = """
#!/bin/bash

function TestOutput {{
    logs=${{2:-""}}
    logs=${{logs//\\\"/\\\\\\\"}}
    JSON_FMT=\'{{\"id\":\"%s\",\"passed\": %s, \"log\":\"%s\"}}\'
    printf \"$JSON_FMT\" \"{test}\" $1 \"$logs\"  > ../outputs/{test}.txt
}}


result=$({command})
output=$({output})

if {isRegExp};
then
    if [[ "$result" =~ $output ]]
        then TestOutput true ""
    else
        TestOutput false "\\n=============================\\nEXPECTED REGEX:\\n$output\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n$result\\n=============================\\n"
    fi
else
    output=$({output})

    if {isFlexible};
    then
        result=$(echo -e "$result" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' | tr -d '\n' | tr -d "\n\r" )
        output=$(echo -e "$output" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' | tr -d '\n' | tr -d "\n\r" )
    fi

    if [ "$result" == "$output" ]
        then TestOutput true ""
    else
        TestOutput false "\\n=============================\\nEXPECTED OUTPUT:\\n$output\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n$result\\n=============================\\n"
    fi
fi
"""



# Params: cmd, testName
BASH_TEST = """
#!/bin/bash

function TestOutput {{
    logs=${{2:-""}}
    logs=${{logs//\\\"/\\\\\\\"}}
    JSON_FMT=\'{{\"id\":\"%s\",\"passed\": %s, \"log\":\"%s\"}}\'
    printf \"$JSON_FMT\" \"{test}\" $1 \"$logs\"  > ../outputs/{test}.txt
}}

{command}
"""


BASH_TEST_GROUP = """
TestOutput () {
    logs=${4:-""}
    JSON_FMT=\'{\"id\":\"%s_@_%s\",\"passed\": %s, \"log\":\"%s\"}\\n\'
    logs=${logs//\\\\/\\\\\\\\}
    logs=${logs//\\\"/\\\\\\\"}
    printf \"$JSON_FMT\" \"$1\" \"$2\" \"$3\" \"$logs\"  >> ../outputs/user_tests.txt
}

export -f TestOutput
"""
