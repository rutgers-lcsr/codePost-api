require 'json'
require 'base64'
require 'stringio'

CELLS_B64 = "{cells_b64}"

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
binding_context = binding

cells.each do |cell|
  if cell['type'] == 'markdown'
    results << {
      "cell_type" => "markdown",
      "source" => cell['source']
    }
  elsif cell['type'] == 'code'
    execution_count += 1
    source = cell['source']
    outputs = []
    success = true
    result_val = nil
    error_obj = nil
    
    stdout_str, stderr_str = capture_output do
      begin
        result_val = binding_context.eval(source)
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
