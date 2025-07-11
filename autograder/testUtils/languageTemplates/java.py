# Params: cmd, output, testName
JAVA_IO_TEST = """
import java.io.FileWriter;
import java.io.IOException;

import java.io.StringWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;


public class _test{test} {{
    public static void main(String[] args) throws IOException {{
      boolean isPassed = false;
      String logs = \"\";
      try {{
        Object actual = {command};
        Object expected = {output};
        if ({isRegExp}) {{
            String regexp = (String) expected;
            if (!(actual instanceof String)) {{
                logs =  "=============================\\nEXPECTED REGEX:\\n" + regexp + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n Ouput is not a string. Must be string to do regexp.\\n=============================\\n";
            }}
            else {{
                String codePostResult = (String) actual;
                if (codePostResult.matches(regexp)) {{
                    isPassed = true;
                }}
                else {{
                    logs = "=============================\\nEXPECTED REGEX:\\n" + regexp + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + codePostResult +"\\n=============================\\n";
                }}
            }}
        }}
        else {{
            if ((expected instanceof String) && (actual instanceof String)) {{
                String codePostResult = (String) actual;
                String codePostExpected = (String) expected;
                if ({isFlexible}) {{
                  codePostResult = codePostResult.replaceAll("\\\\s","").toLowerCase();
                  codePostExpected = codePostExpected.replaceAll("\\\\s","").toLowerCase();
                }}
                int var1 = codePostExpected.compareTo(codePostResult);
                if (var1 == 0) {{
                  isPassed = true;
                }}
                else {{
                  logs = "=============================\\nEXPECTED OUTPUT:\\n" + codePostExpected + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + codePostResult +"\\n=============================\\n";
                }}
            }} else {{
                assert({command} == {output});
                isPassed = true;
            }}
        }}
      }}
      catch (AssertionError e) {{
        logs = "=============================\\nEXPECTED OUTPUT:\\n" + String.valueOf({output}) + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + String.valueOf({command}) +"\\n=============================\\n";
      }}
      catch (Exception e) {{
        isPassed = false;
        StringWriter errors = new StringWriter();
        e.printStackTrace(new PrintWriter(errors));
        logs = errors.toString();
      }}
      try {{
            FileWriter file = new FileWriter(\"/outputs/{test}.txt\");
            String thisStr = String.format("{{\\\"id\\\":\\\"%s\\\", \\\"passed\\\": %s, \\\"log\\\": \\\"%s\\\"}}", {test}, isPassed, logs);
            file.write(thisStr);
				if (file != null) {{
					file.flush();
					file.close();
				}}
			}} catch (IOException e) {{
				e.printStackTrace();
			}}
   }}
}}
"""

JAVA_IO_OUTPUT_TEST = """
import java.io.*;
import java.nio.file.Files;
import java.nio.file.Paths;


public class _test{test} {{
    public static void main(String[] args) throws IOException {{
      boolean isPassed = false;
      String logs = \"\";
      ByteArrayOutputStream baos = new ByteArrayOutputStream();
      System.setOut(new PrintStream(baos));
      try {{
          {command};
          String actual = baos.toString();
          String output = {output};
          if ({isRegExp}) {{
              if (actual.matches(output)) {{
                  isPassed = true;
              }}
              else {{
                  logs = "=============================\\nEXPECTED REGEX:\\n" + output + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + actual +"\\n=============================\\n";
              }}
          }}
          else {{
              if ({isFlexible}) {{
                actual = actual.replaceAll("\\\\s","").toLowerCase();
                output = output.replaceAll("\\\\s","").toLowerCase();
              }}
              int var1 = actual.compareTo(output);
              if (var1 == 0) {{
                isPassed = true;
              }}
              else {{
                logs = "=============================\\nEXPECTED OUTPUT:\\n" + output + "\\n------------------------------------------------------------\\nACTUAL OUTPUT:\\n" + actual +"\\n=============================\\n";
              }}
          }}
      }}
      catch (Exception e) {{
        isPassed = false;
        StringWriter errors = new StringWriter();
        e.printStackTrace(new PrintWriter(errors));
        logs = errors.toString();
      }}
      try {{
            System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.out)));
            FileWriter file = new FileWriter(\"/outputs/{test}.txt\");
            String thisStr = String.format("{{\\\"id\\\":\\\"%s\\\", \\\"passed\\\": %s, \\\"log\\\": \\\"%s\\\"}}", {test}, isPassed, logs);
            file.write(thisStr);
				if (file != null) {{
					file.flush();
					file.close();
				}}
			}} catch (IOException e) {{
				e.printStackTrace();
			}}
   }}
}}
"""



JAVA_UNIT_TEST = """
import java.io.FileWriter;
import java.io.IOException;

{imports}

public class _test{test} {{
    {command}

    private static class TestOutput {{
        String log;
        Boolean passed;

        public TestOutput(Boolean passedA, String logA) {{
            log = logA;
            passed = passedA;
        }}
    }}
    public static void main(String[] args) {{
      TestOutput output = Test.Test();
      try {{
        FileWriter file = new FileWriter(\"/outputs/{test}.txt\");
        String thisStr = String.format("{{\\\"id\\\":\\\"%s\\\", \\\"passed\\\": %s, \\\"log\\\": \\\"%s\\\"}}", {test}, output.passed, output.log);
        file.write(thisStr);
    	if (file != null) {{
    		file.flush();
    		file.close();
    	}}
      }}
      catch (IOException e) {{
    	e.printStackTrace();
      }}
   }}
}}
"""
