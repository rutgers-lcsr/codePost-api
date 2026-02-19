require 'json'
require 'base64'
require 'stringio'
require 'timeout'

CELLS_B64 = "{cells_b64}"
TEST_CODE_B64 = "{test_code_b64}"

def capture_output
  old_stdout = $stdout
  old_stderr = $stderr
  out = StringIO.new
  err = StringIO.new
  $stdout = out
  $stderr = err
  yield
  return out.string, err.string
ensure
  $stdout = old_stdout
  $stderr = old_stderr
end

cells_json = Base64.decode64(CELLS_B64)
cells = JSON.parse(cells_json)

results = []
execution_count = 0
# ============================================
# Shared Execution Context
# ============================================
$execution_context = Object.new

cells.each do |cell|
  if cell['type'] == 'markdown'
    results << {
      "cell_type" => "markdown",
      "source" => cell['source']
    }
  elsif cell['type'] == 'code'
    execution_count += 1
    source = cell['source']
    # Handle source as array or string
    source = source.join("") if source.is_a?(Array)
    outputs = []
    success = true
    result_val = nil
    error_obj = nil
    
    stdout_str, stderr_str = capture_output do
      begin
        # Execute in shared context
        result_val = $execution_context.instance_eval(source)
      rescue Exception => e
        success = false
        error_obj = e
        # Print error to stderr so we catch it
        $stderr.puts e.message
        $stderr.puts e.backtrace.join("\n")
      end
    end

    if !stdout_str.empty?
      outputs << {
        "output_type" => "stream",
        "name" => "stdout",
        "text" => stdout_str
      }
    end

    if !stderr_str.empty?
       # If failed, stderr usually contains trace
       if success
          outputs << {
            "output_type" => "stream",
            "name" => "stderr",
            "text" => stderr_str
          }
       end
    end

    if !success
      outputs << {
        "output_type" => "error",
        "ename" => error_obj.class.to_s,
        "evalue" => error_obj.message,
        "traceback" => error_obj.backtrace || []
      }
    elsif result_val != nil
       outputs << {
         "output_type" => "execute_result",
         "execution_count" => execution_count,
         "data" => {
           "text/plain" => result_val.inspect
         },
         "metadata" => {}
       }
    end

    results << {
      "cell_type" => "code",
      "source" => source,
      "outputs" => outputs,
      "execution_count" => execution_count
    }
  end
end

# ============================================
# Tester Framework for Ruby Notebooks
# ============================================
$test_results = []

# Define run_test at top level so it is a private method of Object
# instance_eval will follow inheritance chain and find it? 
# Actually, instance_eval sets self. calling run_test matches self.run_test.
# Since run_test is private on Object, and self is an Object, it works.
def run_test(name, points, description=nil, timeout=30, &block)
  if description.is_a?(Proc)
    block = description
    description = nil
  end
  if timeout.is_a?(Proc)
    block = timeout
    timeout = 30
  end

  result = {
    "name" => name,
    "max_score" => points,
    "description" => description,
    "message" => "",
    "score" => 0,
    "passed" => false,
    "status" => "failed",
    "error" => ""
  }
  
  begin
    ret = nil
    Timeout.timeout(timeout) do
      ret = block.call
    end

    if ret.is_a?(Numeric)
      result["score"] = [[ret, points].min, 0].max
      result["passed"] = result["score"] == points
      result["status"] = result["passed"] ? "passed" : "partial"
    elsif ret.is_a?(Array) && ret.length >= 2 && ret[0].is_a?(Numeric)
      result["score"] = [[ret[0], points].min, 0].max
      result["message"] = ret[1].nil? ? "" : ret[1].to_s
      result["passed"] = result["score"] == points
      result["status"] = result["passed"] ? "passed" : "partial"
    elsif ret.is_a?(String)
      result["message"] = ret
      result["passed"] = true
      result["score"] = points
      result["status"] = "passed"
    else
      result["passed"] = true
      result["score"] = points
      result["status"] = "passed"
    end
  rescue Exception => e
    result["error"] = e.message
    result["status"] = e.is_a?(Timeout::Error) ? "error" : "failed"
  end
  
  $test_results << result
end

def output_test_results
  puts "<<<TEST_RESULT_JSON_START>>>"
  puts JSON.generate($test_results)
  puts "<<<TEST_RESULT_JSON_END>>>"
end

# Make run_test public just in case instance_eval scope is tricky with private methods
public :run_test

# ============================================

# Execute test code if provided
if !TEST_CODE_B64.empty?
  begin
    test_code = Base64.decode64(TEST_CODE_B64)
    if !test_code.strip.empty?
      # Execute test code in the same context
      $execution_context.instance_eval(test_code)
    end
  rescue Exception => e
    # Manually create a failed result if the script itself blows up
    $test_results << {
        "name" => "Test Script Execution",
        "max_score" => 0,
        "score" => 0,
        "passed" => false,
        "status" => "failed",
        "error" => "Failed to run test script: #{e.message}"
    }
  end
end

# Output test results
output_test_results

final_result = {
  "success" => true,
  "stdout" => "",
  "stderr" => "",
  "execution_time" => 0,
  "output_data" => {
    "cells" => results,
    "notebook" => ""
  }
}

puts "<<<RESULTS_START>>>"
puts JSON.generate(final_result)
puts "<<<RESULTS_END>>>"
