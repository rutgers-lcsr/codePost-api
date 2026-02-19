<?php

$CELLS_B64 = "{cells_b64}";
$TEST_CODE_B64 = "{test_code_b64}";

$cells_json = base64_decode($CELLS_B64);
$cells = json_decode($cells_json, true);

if (json_last_error() !== JSON_ERROR_NONE) {
    echo "Invalid JSON";
    exit(1);
}

// ============= Tester Framework =============
class Tester {
    private static $results = [];
    
    public static function test(string $name, float $points, $description, $fn = null, $timeout = 30): void {
        if (is_callable($description)) {
            $fn = $description;
            $description = null;
            $timeout = 30;
        }
        if (is_callable($timeout)) {
            $fn = $timeout;
            $timeout = 30;
        }

        $result = [
            "name" => $name,
            "max_score" => $points,
            "description" => $description,
            "message" => "",
            "score" => 0.0,
            "passed" => false,
            "status" => "failed",
            "error" => ""
        ];
        
        try {
            if (function_exists('pcntl_signal') && function_exists('pcntl_alarm')) {
                pcntl_signal(SIGALRM, function() use ($timeout) {
                    throw new Exception("Test timed out after {$timeout}s");
                });
                pcntl_alarm((int)$timeout);
            }

            $ret = $fn();

            if (function_exists('pcntl_alarm')) {
                pcntl_alarm(0);
            }

            if (is_numeric($ret)) {
                $score = max(0, min(floatval($ret), $points));
                $result["score"] = $score;
                $result["passed"] = $score == $points;
                $result["status"] = $result["passed"] ? "passed" : "partial";
            } elseif (is_array($ret)) {
                if (isset($ret['score']) && is_numeric($ret['score'])) {
                    $score = max(0, min(floatval($ret['score']), $points));
                    $result["score"] = $score;
                    $result["message"] = isset($ret['message']) ? strval($ret['message']) : "";
                    $result["passed"] = $score == $points;
                    $result["status"] = $result["passed"] ? "passed" : "partial";
                } elseif (count($ret) >= 2 && is_numeric($ret[0])) {
                    $score = max(0, min(floatval($ret[0]), $points));
                    $result["score"] = $score;
                    $result["message"] = isset($ret[1]) ? strval($ret[1]) : "";
                    $result["passed"] = $score == $points;
                    $result["status"] = $result["passed"] ? "passed" : "partial";
                } else {
                    $result["passed"] = true;
                    $result["score"] = $points;
                    $result["status"] = "passed";
                }
            } elseif (is_string($ret)) {
                $result["message"] = $ret;
                $result["passed"] = true;
                $result["score"] = $points;
                $result["status"] = "passed";
            } else {
                $result["passed"] = true;
                $result["score"] = $points;
                $result["status"] = "passed";
            }
        } catch (Throwable $e) {
            $result["error"] = $e->getMessage();
            $result["status"] = stripos($result["error"], "timed out") !== false ? "error" : "failed";
        }
        
        self::$results[] = $result;
    }
    
    public static function getResults(): array {
        return self::$results;
    }
    
    public static function outputResults(): void {
        echo "<<<TEST_RESULT_JSON_START>>>";
        echo json_encode(self::$results);
        echo "<<<TEST_RESULT_JSON_END>>>";
    }
}
// ============================================

$results = [];
$execution_count = 0;

foreach ($cells as $cell) {
    if ($cell['type'] === 'markdown') {
        $results[] = [
            "cell_type" => "markdown",
            "source" => $cell['source']
        ];
    } elseif ($cell['type'] === 'code') {
        $execution_count++;
        $source = $cell['source'];
        $outputs = [];
        $success = true;
        $error_obj = null;
        
        ob_start();
        $start_err = error_get_last();
        
        try {
            // Strip PHP opening/closing tags for eval
            $clean_source = preg_replace('/<\?php\s*/', '', $source);
            $clean_source = preg_replace('/<\?\s*/', '', $clean_source);
            $clean_source = preg_replace('/\?>\s*/', '', $clean_source);
            $result_val = eval($clean_source);
            if ($result_val === false && ($err = error_get_last()) && $err !== $start_err) {
                 throw new Exception($err['message']);
            }
        } catch (Throwable $e) {
            $success = false;
            $error_obj = $e;
            echo "\nError: " . $e->getMessage();
        }
        
        $stdout_str = ob_get_clean();
        
        if (!empty($stdout_str)) {
             $outputs[] = [
                "output_type" => "stream",
                "name" => "stdout",
                "text" => $stdout_str
             ];
        }
        
        if (!$success) {
            $outputs[] = [
                "output_type" => "error",
                "ename" => get_class($error_obj),
                "evalue" => $error_obj->getMessage(),
                "traceback" => explode("\n", $error_obj->getTraceAsString())
            ];
        }
        
        $results[] = [
            "cell_type" => "code",
            "source" => $source,
            "outputs" => $outputs,
            "execution_count" => $execution_count
        ];
    }
}

// Execute test code if provided
if (!empty($TEST_CODE_B64)) {
    $test_code = base64_decode($TEST_CODE_B64);
    if ($test_code !== false && !empty(trim($test_code))) {
        try {
            eval($test_code);
        } catch (Throwable $e) {
            Tester::test("Test Script Execution", 0, function() use ($e) {
                throw new Exception("Failed to run test script: " . $e->getMessage());
            });
        }
    }
}

// Output test results
Tester::outputResults();

$final_result = [
  "success" => true,
  "stdout" => "",
  "stderr" => "",
  "execution_time" => 0,
  "output_data" => [
    "cells" => $results,
    "notebook" => ""
  ]
];

echo "<<<RESULTS_START>>>\n";
echo json_encode($final_result);
echo "\n<<<RESULTS_END>>>\n";
