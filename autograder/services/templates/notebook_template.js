const fs = require("fs");
const vm = require("vm");

// Placeholder for base64 encoded cells
const cellsB64 = "{cells_b64}";
const testCodeB64 = "{test_code_b64}";

// Decode cells
const cellsJson = Buffer.from(cellsB64, "base64").toString("utf-8");
let cells;
try {
    cells = JSON.parse(cellsJson);
} catch (e) {
    console.error("Failed to parse cells JSON");
    process.exit(1);
}

// ============= Tester Framework =============
const testResults = [];

function test(name, points, description, fn) {
    if (typeof description === 'function') {
        fn = description;
        description = null;
    }
    const result = {
        name: name,
        max_score: points,
        description: description,
        score: 0,
        passed: false,
        status: "failed",
        error: ""
    };

    try {
        fn();
        result.passed = true;
        result.score = points;
        result.status = "passed";
    } catch (e) {
        result.error = e.message || String(e);
    }

    testResults.push(result);
}

function outputTestResults() {
    console.log("<<<TEST_RESULT_JSON_START>>>");
    console.log(JSON.stringify(testResults));
    console.log("<<<TEST_RESULT_JSON_END>>>");
}
// ============================================

const results = [];
const context = vm.createContext({
    console: {
        log: (...args) => {
            if (currentStdout) currentStdout.push(args.map((a) => String(a)).join(" "));
            else process.stdout.write(args.map((a) => String(a)).join(" ") + "\n");
        },
        error: (...args) => {
            if (currentStderr) currentStderr.push(args.map((a) => String(a)).join(" "));
            else process.stderr.write(args.map((a) => String(a)).join(" ") + "\n");
        },
        warn: (...args) => {
            if (currentStderr) currentStderr.push("WARN: " + args.map((a) => String(a)).join(" "));
        },
    },
    require: require,
    process: process,
    Buffer: Buffer,
    test: test, // Expose test function to VM context
});

let currentStdout = null;
let currentStderr = null;
let executionCount = 0;

async function run() {
    for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        if (cell.type === "markdown") {
            results.push({
                cell_type: "markdown",
                source: cell.source,
            });
        } else if (cell.type === "code") {
            executionCount++;
            currentStdout = [];
            currentStderr = [];

            const cellSource = cell.source;
            let success = true;
            let resultValue = null;
            let errorVal = null;

            try {
                // Use vm.runInContext to maintain state between cells
                resultValue = vm.runInContext(cellSource, context);
            } catch (e) {
                success = false;
                errorVal = e;
            }

            const outputs = [];

            // Collect stdout
            if (currentStdout.length > 0) {
                outputs.push({
                    output_type: "stream",
                    name: "stdout",
                    text: currentStdout.join("\n") + "\n",
                });
            }

            // Collect stderr
            if (currentStderr.length > 0) {
                outputs.push({
                    output_type: "stream",
                    name: "stderr",
                    text: currentStderr.join("\n") + "\n",
                });
            }

            if (!success) {
                outputs.push({
                    output_type: "error",
                    ename: errorVal.name || "Error",
                    evalue: errorVal.message || String(errorVal),
                    traceback: errorVal.stack ? errorVal.stack.split("\n") : [],
                });
            } else if (resultValue !== undefined) {
                outputs.push({
                    output_type: "execute_result",
                    execution_count: executionCount,
                    data: {
                        "text/plain": String(resultValue),
                    },
                    metadata: {},
                });
            }

            results.push({
                cell_type: "code",
                source: cellSource,
                outputs: outputs,
                execution_count: executionCount,
            });
        }
    }

    // Execute test code if provided
    if (testCodeB64 && testCodeB64.length > 0) {
        try {
            const testCode = Buffer.from(testCodeB64, "base64").toString("utf-8");
            if (testCode.trim().length > 0) {
                vm.runInContext(testCode, context);
            }
        } catch (e) {
            test("Test Script Execution", 0, () => {
                throw new Error("Failed to run test script: " + (e.message || e));
            });
        }
    }

    // Output test results
    outputTestResults();

    const finalResult = {
        success: true,
        stdout: "",
        stderr: "",
        execution_time: 0,
        output_data: {
            cells: results,
            notebook: "",
        },
    };

    console.log("<<<RESULTS_START>>>");
    console.log(JSON.stringify(finalResult));
    console.log("<<<RESULTS_END>>>");
}

run();
