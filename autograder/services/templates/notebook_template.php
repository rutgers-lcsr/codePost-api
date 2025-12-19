<?php

$CELLS_B64 = "{cells_b64}";

$cells_json = base64_decode($CELLS_B64);
$cells = json_decode($cells_json, true);

if (json_last_error() !== JSON_ERROR_NONE) {
    echo "Invalid JSON";
    exit(1);
}

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
            // Remove opening <?php tag if present as eval doesn't like it usually, 
            // but users might include it. 
            // Actually eval in PHP executes code as PHP without tags except if ?\> is used.
            // But typical PHP notebook cells are just code.
            // Handling "return" for last value is tricky in PHP eval.
            
            // Allow variable sharing: eval runs in current scope.
            // But strict types etc might affect it.
            
            $result_val = eval($source);
            if ($result_val === false && ($err = error_get_last()) && $err !== $start_err) {
                 // Eval returned false and error occurred
                 throw new Exception($err['message']);
            }
        } catch (Throwable $e) {
            $success = false;
            $error_obj = $e;
            echo "\nError: " . $e->getMessage();
        }
        
        $stdout_str = ob_get_clean();
        
        // PHP stderr is hard to capture cleanly separated from stdout in CLI usually goes to display
        // unless config log_errors?
        // For simplicity, treat captured output as stdout.
        
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
