// Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
package autograder.services.templates;
// This is a template for running Java Jupyter notebook code cells inside a Docker container.

// To use this template replace the placeholder {cells_b64} with a base64-encoded JSON array of cells,
// Requires Java 11+ for JShell API

import jdk.jshell.*;
import jdk.jshell.Snippet.Status;
import jdk.jshell.SnippetEvent;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.Base64;

// JSON handling (minimal implementation to avoid external dependencies)
class JSONBuilder {
    public static String escape(String s) {
        if (s == null)
            return "null";
        StringBuilder sb = new StringBuilder();
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"':
                    sb.append("\\\"");
                    break;
                case '\\':
                    sb.append("\\\\");
                    break;
                case '\b':
                    sb.append("\\b");
                    break;
                case '\f':
                    sb.append("\\f");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    if (c < ' ') {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.toString();
    }

    public static String toJsonString(String s) {
        return "\"" + escape(s) + "\"";
    }
}

public class notebook_template {

    private static final int MAX_CELLS = 500;
    private static final int NBS_OUTPUT_LIMIT = 10000;
    private static PrintWriter logWriter;

    public static void templateLog(String message, String level) {
        System.err.println("[" + level + "] " + message);
    }

    public static void main(String[] args) {
        long startTime = System.currentTimeMillis();
        templateLog("Template started.", "INFO");
        templateLog("Initial working directory: " + System.getProperty("user.dir"), "DEBUG");

        // Check if /work exists
        File workDir = new File("/work");
        templateLog("/work exists: " + workDir.exists(), "DEBUG");

        File sharedDir = new File("/root/shared");
        templateLog("/root/shared exists: " + sharedDir.exists(), "DEBUG");

        // Change to /work if it exists
        if (workDir.exists() && workDir.isDirectory()) {
            System.setProperty("user.dir", "/work");
            templateLog("Working directory set to: /work", "DEBUG");
        } else {
            templateLog("/work directory does not exist.", "ERROR");
            System.exit(1);
        }

        // Decode cells from base64
        String cellsB64 = "{cells_b64}";
        String testCodeB64 = "{test_code_b64}"; // New placeholder
        String cellsJson;
        try {
            byte[] decoded = Base64.getDecoder().decode(cellsB64);
            cellsJson = new String(decoded, StandardCharsets.UTF_8);
        } catch (Exception e) {
            templateLog("Failed to decode cells: " + e.getMessage(), "ERROR");
            System.exit(1);
            return;
        }

        // Parse cells (simple JSON parsing)
        List<Map<String, Object>> cells = parseJsonArray(cellsJson);
        if (cells == null) {
            templateLog("Invalid cells JSON.", "ERROR");
            System.exit(1);
            return;
        }

        List<Map<String, Object>> results = new ArrayList<>();
        boolean studentCodeSyntaxInvalid = false;
        String studentCodeSyntaxErrorMsg = "";

        // Check if too many cells
        if (cells.size() > MAX_CELLS) {
            templateLog("Too many cells: " + cells.size(), "ERROR");
            Map<String, Object> errorResult = new LinkedHashMap<>();
            errorResult.put("cell_type", "markdown");
            errorResult.put("source", "**Error:** Too many cells (" + cells.size() + "). Maximum allowed: " + MAX_CELLS
                    + "\n\nExecution stopped.");
            results.add(errorResult);
        } else {
            // Create JShell instance with captured streams
            ByteArrayOutputStream jshellOut = new ByteArrayOutputStream();
            ByteArrayOutputStream jshellErr = new ByteArrayOutputStream();
            PrintStream psOut = new PrintStream(jshellOut, true, StandardCharsets.UTF_8);
            PrintStream psErr = new PrintStream(jshellErr, true, StandardCharsets.UTF_8);

            JShell jshell = JShell.builder()
                    .out(psOut)
                    .err(psErr)
                    .build();

            // --- Inject Test Framework (Annotations & Classes) ---
            jshell.eval("import java.util.*;");
            jshell.eval("import java.lang.annotation.*;");
            jshell.eval("import java.lang.reflect.*;");
            jshell.eval("import java.util.concurrent.*;");

            // Define Test Annotation
            jshell.eval(
                    "@Retention(RetentionPolicy.RUNTIME) @Target(ElementType.METHOD) @interface Test { String name() default \"\"; double points() default 1.0; String description() default \"\"; int timeout() default 30; boolean hidden() default false; String[] objectives() default {}; }");

            // Define TestResult Class
            jshell.eval(
                    "class TestResult { String name; String description; String message; double score; double max_score; boolean passed; String status; String error; String output; "
                            +
                            "public TestResult(String n, double m, String d) { name=n; max_score=m; description=d; message=\"\"; score=0; passed=false; status=\"failed\"; output=\"\"; } }");

            // Define Assertions (polyfilled for simple use)
            jshell.eval("void assertTrue(boolean cond, String msg) { if (!cond) throw new AssertionError(msg); }");

            int executionCount = 0;

            for (Map<String, Object> cell : cells) {
                String cellType = (String) cell.get("type");

                if ("markdown".equals(cellType)) {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("cell_type", "markdown");
                    result.put("source", cell.get("source"));
                    results.add(result);
                } else if ("code".equals(cellType)) {
                    executionCount++;
                    String cellSource = (String) cell.get("source");

                    List<Map<String, Object>> outputs = new ArrayList<>();
                    boolean success = true;
                    String errorMsg = null;

                    // Reset streams for this cell
                    jshellOut.reset();
                    jshellErr.reset();

                    // Temporary file for plot capture
                    File plotFile = null;
                    try {
                        plotFile = File.createTempFile("plot_", ".png");
                    } catch (IOException e) {
                        templateLog("Failed to create temp file for plot: " + e.getMessage(), "WARNING");
                    }

                    try {
                        StringBuilder evalResult = new StringBuilder();
                        boolean[] successRef = new boolean[] { success };
                        String[] errorMsgRef = new String[] { errorMsg };

                        evaluateCellSource(jshell, cellSource, psErr, evalResult, successRef, errorMsgRef);
                        success = successRef[0];
                        errorMsg = errorMsgRef[0];

                        if (!success && isLikelySyntaxCompilationIssue(errorMsg,
                                jshellErr.toString(StandardCharsets.UTF_8))) {
                            studentCodeSyntaxInvalid = true;
                            if (errorMsg != null && !errorMsg.isEmpty()) {
                                studentCodeSyntaxErrorMsg = errorMsg;
                            } else {
                                studentCodeSyntaxErrorMsg = jshellErr.toString(StandardCharsets.UTF_8);
                            }
                        }

                        // Append expression values to output
                        if (evalResult.length() > 0) {
                            psOut.print(evalResult.toString());
                        }

                    } catch (Exception e) {
                        success = false;
                        errorMsg = e.getMessage();
                        e.printStackTrace(psErr);
                    }

                    String stdoutText = jshellOut.toString(StandardCharsets.UTF_8);
                    String stderrText = jshellErr.toString(StandardCharsets.UTF_8);

                    // Check for plot output (if code generated a BufferedImage and saved it)
                    // This is a simplified check - real implementation would need to hook into
                    // graphics calls
                    if (plotFile != null && plotFile.exists() && plotFile.length() > 1000) {
                        try {
                            byte[] imageBytes = Files.readAllBytes(plotFile.toPath());
                            String imageBase64 = Base64.getEncoder().encodeToString(imageBytes);

                            Map<String, Object> displayData = new LinkedHashMap<>();
                            displayData.put("output_type", "display_data");
                            Map<String, String> dataMap = new LinkedHashMap<>();
                            dataMap.put("image/png", imageBase64);
                            displayData.put("data", dataMap);
                            displayData.put("metadata", new LinkedHashMap<>());
                            outputs.add(displayData);
                        } catch (IOException e) {
                            stderrText += "\nPlot capture error: " + e.getMessage() + "\n";
                        }
                    }

                    // Clean up temp file
                    if (plotFile != null)
                        plotFile.delete();

                    // Truncate stdout if too long
                    if (stdoutText.length() > NBS_OUTPUT_LIMIT) {
                        stdoutText = stdoutText.substring(0, NBS_OUTPUT_LIMIT) + "\n...[ERROR output truncated]\n";
                    }

                    // Truncate stderr if too long
                    if (stderrText.length() > NBS_OUTPUT_LIMIT) {
                        stderrText = stderrText.substring(0, NBS_OUTPUT_LIMIT) + "\n...[ERROR output truncated]\n";
                    }

                    // Build outputs list
                    if (!stdoutText.isEmpty()) {
                        Map<String, Object> output = new LinkedHashMap<>();
                        output.put("output_type", "stream");
                        output.put("name", "stdout");
                        output.put("text", stdoutText);
                        outputs.add(output);
                    }

                    if (!stderrText.isEmpty()) {
                        Map<String, Object> output = new LinkedHashMap<>();
                        output.put("output_type", "stream");
                        output.put("name", "stderr");
                        output.put("text", stderrText);
                        outputs.add(output);
                    }

                    if (!success) {
                        // Truncate error message if too long
                        if (errorMsg != null && errorMsg.length() > NBS_OUTPUT_LIMIT) {
                            errorMsg = errorMsg.substring(0, NBS_OUTPUT_LIMIT) + "\n...[ERROR message truncated]\n";
                        }

                        Map<String, Object> errorOutput = new LinkedHashMap<>();
                        errorOutput.put("output_type", "error");
                        errorOutput.put("ename", "ExecutionError");
                        errorOutput.put("evalue", errorMsg != null ? errorMsg : stderrText);
                        List<String> traceback = new ArrayList<>();
                        traceback.add(stderrText);
                        errorOutput.put("traceback", traceback);
                        outputs.add(errorOutput);
                    }

                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("cell_type", "code");
                    result.put("source", cellSource);
                    result.put("outputs", outputs);
                    result.put("execution_count", executionCount);
                    results.add(result);
                }
            }

            // --- Run Test Code (if any) ---
            templateLog("Checking test code injection...", "INFO");
            templateLog("testCodeB64 value: "
                    + (testCodeB64.length() > 50 ? testCodeB64.substring(0, 50) + "..." : testCodeB64), "INFO");
            boolean condition = !testCodeB64.equals("{" + "test_code_b64" + "}") && !testCodeB64.isEmpty();
            // templateLog("Injection Condition: " + condition, "INFO");

            if (condition) {
                templateLog("Test code found. Length: " + testCodeB64.length(), "INFO");
                try {
                    byte[] testDecoded = Base64.getDecoder().decode(testCodeB64);
                    String testCode = new String(testDecoded, StandardCharsets.UTF_8);

                    List<SnippetEvent> testEvents = jshell.eval(testCode);
                    for (SnippetEvent e : testEvents) {
                        if (e.status() == Status.REJECTED) {
                            templateLog("Test definition failed: " + e.snippet().source(), "ERROR");
                            jshell.diagnostics(e.snippet())
                                    .forEach(d -> templateLog(d.getMessage(Locale.getDefault()), "ERROR"));
                        }
                    }

                    // Dynamic Test Class Discovery
                    StringBuilder _classChecks = new StringBuilder();
                    jshell.snippets()
                            .filter(s -> s.kind() == Snippet.Kind.TYPE_DECL && jshell.status(s) == Status.VALID)
                            .map(s -> ((TypeDeclSnippet) s).name())
                            .forEach(name -> {
                                if (Arrays.asList("Tester", "Tests", "Main").contains(name)) {
                                    _classChecks.append("try { _targetArr[0] = " + name + ".class; ");
                                    _classChecks.append("_sb.append(\"Found: \" + _targetArr[0].getName() + \" \"); ");
                                    _classChecks.append(
                                            "} catch(Throwable t){ _sb.append(\"Err:\"+t+\" \"); } ");
                                }
                            });

                    // 2. Run Test Logic
                    String escapedSyntaxMsg = studentCodeSyntaxErrorMsg == null ? ""
                            : studentCodeSyntaxErrorMsg
                                    .replace("\\", "\\\\")
                                    .replace("\"", "\\\"")
                                    .replace("\n", "\\n")
                                    .replace("\r", "\\r");

                    jshell.eval("boolean CODEPOST_STUDENT_SYNTAX_INVALID = "
                            + (studentCodeSyntaxInvalid ? "true" : "false") + ";");
                    jshell.eval("String CODEPOST_STUDENT_SYNTAX_ERROR_MSG = \"" + escapedSyntaxMsg + "\";");

                    List<SnippetEvent> supplierEvents = jshell.eval("   java.util.function.Supplier<String> __runTests = () -> { " +
                            "       StringBuilder _sb = new StringBuilder(); " +
                            "       List<TestResult> _results = new ArrayList<>(); Class<?>[] _targetArr = new Class<?>[]{null}; " +
                            " " + _classChecks.toString() + " " +
                            "   Class<?> _target = _targetArr[0]; " +
                            "   _sb.append(\"Target: \" + (_target==null?\"null\":_target.getName()) + \" \"); " +
                            "   if (_target != null) { " +
                            "       _sb.append(\"DEBUG: Target=\" + _target.getName() + \" Methods=\" + _target.getDeclaredMethods().length + \" \"); "
                            +
                            "       Object[] _instArr = new Object[]{null}; " +
                            "       try { _instArr[0] = _target.getDeclaredConstructor().newInstance(); } catch(Throwable t) {} "
                            +
                            "       final Object _instance = _instArr[0]; " +
                            "       for (Method _m : _target.getDeclaredMethods()) { " +
                            "           if (_m.isAnnotationPresent(Test.class)) { " +
                            "               Test _ann = _m.getAnnotation(Test.class); " +
                            "               TestResult _tr = new TestResult(_ann.name().isEmpty() ? _m.getName() : _ann.name(), _ann.points(), _ann.description()); "
                            +
                            "               if (false && CODEPOST_STUDENT_SYNTAX_INVALID) { " +
                            "                   String _base = \"Student code syntax was invalid. Fix syntax errors before running tests.\"; "
                            +
                            "                   _tr.passed = false; _tr.score = 0; _tr.status = \"error\"; _tr.message = _base; "
                            +
                            "                   _tr.error = (CODEPOST_STUDENT_SYNTAX_ERROR_MSG==null || CODEPOST_STUDENT_SYNTAX_ERROR_MSG.isEmpty()) ? _base : (_base + \"\\n\" + CODEPOST_STUDENT_SYNTAX_ERROR_MSG); "
                            +
                            "                   _results.add(_tr); " +
                            "                   continue; " +
                            "               } " +
                            "               ExecutorService _exec = Executors.newSingleThreadExecutor(); " +
                            "               Future<Object> _future = _exec.submit(() -> { " +
                            "                   try { _m.setAccessible(true); return _m.invoke(_instance); } " +
                            "                   catch (Throwable _ex) { throw new RuntimeException(_ex.getCause() != null ? _ex.getCause() : _ex); } "
                            +
                            "               }); " +
                            "               try { " +
                            "                   Object _ret = _future.get(_ann.timeout(), TimeUnit.SECONDS); " +
                            "                   if (_ret instanceof Number) { " +
                            "                       double _score = ((Number) _ret).doubleValue(); " +
                            "                       _tr.score = Math.max(0, Math.min(_score, _tr.max_score)); " +
                            "                       _tr.passed = _tr.score == _tr.max_score; _tr.status = _tr.passed ? \"passed\" : \"partial\"; "
                            +
                            "                   } else if (_ret instanceof Object[] && ((Object[])_ret).length >= 2 && ((Object[])_ret)[0] instanceof Number) { "
                            +
                            "                       Object[] _arr = (Object[]) _ret; " +
                            "                       double _score = ((Number) _arr[0]).doubleValue(); " +
                            "                       _tr.score = Math.max(0, Math.min(_score, _tr.max_score)); " +
                            "                       _tr.message = _arr[1] != null ? _arr[1].toString() : \"\"; " +
                            "                       _tr.passed = _tr.score == _tr.max_score; _tr.status = _tr.passed ? \"passed\" : \"partial\"; "
                            +
                            "                   } else if (_ret instanceof List && ((List)_ret).size() >= 2 && ((List)_ret).get(0) instanceof Number) { "
                            +
                            "                       List _list = (List) _ret; " +
                            "                       double _score = ((Number) _list.get(0)).doubleValue(); " +
                            "                       _tr.score = Math.max(0, Math.min(_score, _tr.max_score)); " +
                            "                       _tr.message = _list.get(1) != null ? _list.get(1).toString() : \"\"; "
                            +
                            "                       _tr.passed = _tr.score == _tr.max_score; _tr.status = _tr.passed ? \"passed\" : \"partial\"; "
                            +
                            "                   } else if (_ret instanceof String) { " +
                            "                       _tr.message = _ret.toString(); _tr.passed = true; _tr.score = _tr.max_score; _tr.status = \"passed\"; "
                            +
                            "                   } else { " +
                            "                       _tr.passed = true; _tr.score = _tr.max_score; _tr.status = \"passed\"; "
                            +
                            "                   } " +
                            "               } catch (TimeoutException _te) { " +
                            "                   _tr.error = \"Test timed out after \" + _ann.timeout() + \"s\"; _tr.status = \"error\"; _future.cancel(true); "
                            +
                            "               } catch (Throwable _t) { " +
                            "                   Throwable _cause = _t.getCause() != null ? _t.getCause() : _t; " +
                            "                   _tr.error = _cause.getMessage(); " +
                            "                   if (_cause instanceof AssertionError) { _tr.status = \"failed\"; } " +
                            "                   else { _tr.status = \"error\"; } " +
                            "               } finally { _exec.shutdownNow(); } " +
                            "               _results.add(_tr); " +
                            "           } " +
                            "       } " +
                            "   } " +
                            "   _sb.append(\"<<<TEST_RESULT_JSON_START>>>[\"); " +
                            "   for (int _i=0; _i<_results.size(); _i++) { " +
                            "       TestResult _r = _results.get(_i); " +
                            "       _sb.append(\"{\\\"name\\\":\\\"\" + _r.name + \"\\\",\"); " +
                            "       _sb.append(\"\\\"description\\\":\\\"\" + (_r.description==null?\"\":_r.description) + \"\\\",\"); "
                            +
                            "       String msg = _r.message==null ? \"\" : _r.message.replaceAll(\"[^a-zA-Z0-9 .,:;!?()_\\\\-=\\\\[\\\\]]\", \"?\"); "
                            +
                            "       _sb.append(\"\\\"message\\\":\\\"\" + msg + \"\\\",\"); "
                            +
                            "       _sb.append(\"\\\"score\\\":\" + _r.score + \",\"); " +
                            "       _sb.append(\"\\\"max_score\\\":\" + _r.max_score + \",\"); " +
                            "       _sb.append(\"\\\"passed\\\":\" + _r.passed + \",\"); " +
                            "       _sb.append(\"\\\"status\\\":\\\"\" + _r.status + \"\\\",\"); " +
                            "       String err = _r.error==null ? \"\" : _r.error.replaceAll(\"[^a-zA-Z0-9 .,:;!?()_\\\\-=\\\\[\\\\]]\", \"?\"); "
                            +
                            "       _sb.append(\"\\\"error\\\":\\\"\" + err + \"\\\",\"); " +
                            "       String out = _r.output==null ? \"\" : _r.output.replaceAll(\"[^a-zA-Z0-9 .,:;!?()_\\\\-=\\\\[\\\\]\\\\n]\", \"?\"); "
                            +
                            "       _sb.append(\"\\\"output\\\":\\\"\" + out + \"\\\"}\"); " +
                            "       if (_i < _results.size()-1) _sb.append(\",\"); " +
                            "   } " +
                            "   _sb.append(\"]<<<TEST_RESULT_JSON_END>>>\"); " +
                            "       return _sb.toString(); " +
                            "   }; ");

                    for (SnippetEvent se : supplierEvents) {
                        if (se.status() == Status.REJECTED) {
                            templateLog("__runTests definition REJECTED: " + se.snippet().source().substring(0, Math.min(200, se.snippet().source().length())), "ERROR");
                            jshell.diagnostics(se.snippet())
                                    .forEach(d -> templateLog("  Diagnostic: " + d.getMessage(Locale.getDefault()), "ERROR"));
                        }
                    }

                    // Reset captured stream for test output
                    jshellOut.reset();

                    List<SnippetEvent> execEvents = jshell.eval("__runTests.get()");
                    String testSnippetValue = "";
                    for (SnippetEvent e : execEvents) {
                        if (e.status() == Status.VALID) {
                            if (e.exception() != null) {
                                templateLog("Test execution exception (VALID): " + e.exception().getMessage(), "ERROR");
                                e.exception().printStackTrace(psErr);
                            }
                            if (e.value() != null) {
                                templateLog("Snippet Event Value: " + e.value(), "INFO");
                                testSnippetValue = e.value();
                            }
                        } else {
                            if (e.status() == Status.REJECTED) {
                                templateLog("Test execution snippet failed: " + e.snippet().source(), "ERROR");
                                jshell.diagnostics(e.snippet())
                                        .forEach(d -> templateLog(d.getMessage(Locale.getDefault()), "ERROR"));
                            }
                            if (e.exception() != null) {
                                templateLog("Test execution exception: " + e.exception().getMessage(), "ERROR");
                                e.exception().printStackTrace(psErr);
                            }
                        }
                    }

                    templateLog("Final snippet value: " + testSnippetValue, "INFO");

                    if (testSnippetValue.startsWith("\"") && testSnippetValue.endsWith("\"")) {
                        String unquoted = testSnippetValue.substring(1, testSnippetValue.length() - 1);
                        StringBuilder sbUnescaped = new StringBuilder();
                        for (int i = 0; i < unquoted.length(); i++) {
                            char c = unquoted.charAt(i);
                            if (c == '\\' && i + 1 < unquoted.length()) {
                                char next = unquoted.charAt(i + 1);
                                if (next == '\"') {
                                    sbUnescaped.append('\"');
                                    i++;
                                } else if (next == '\\') {
                                    sbUnescaped.append('\\');
                                    i++;
                                } else if (next == 'n') {
                                    sbUnescaped.append('\n');
                                    i++;
                                } else if (next == 'r') {
                                    sbUnescaped.append('\r');
                                    i++;
                                } else {
                                    sbUnescaped.append(c);
                                }
                            } else {
                                sbUnescaped.append(c);
                            }
                        }
                        String finalOutput = sbUnescaped.toString();
                        System.out.println(finalOutput);
                    } else if (!testSnippetValue.isEmpty()) {
                        System.out.println(testSnippetValue);
                    } else {
                        System.out.print(jshellOut.toString(StandardCharsets.UTF_8));
                    }

                } catch (Exception e) {
                    templateLog("Failed to run notebook tests: " + e.getMessage(), "ERROR");
                    // Emit synthetic crash result so the backend knows the test script failed
                    String errMsg = e.getMessage() != null ? e.getMessage().replace("\"", "\\\"").replace("\n", "\\n")
                            : "Unknown error";
                    System.out.println(
                            "<<<TEST_RESULT_JSON_START>>>[{\"name\":\"Test Script Execution\",\"description\":\"\",\"message\":\"\",\"score\":0,\"max_score\":0,\"passed\":false,\"status\":\"error\",\"error\":\"Test script failed to load: "
                                    + errMsg + "\",\"output\":\"\"}]<<<TEST_RESULT_JSON_END>>>");
                }
            }

            // Close JShell
            jshell.close();
        }

        long endTime = System.currentTimeMillis();
        double executionTime = (endTime - startTime) / 1000.0;

        Map<String, Object> finalResult = new LinkedHashMap<>();
        finalResult.put("success", true);
        finalResult.put("stdout", "");
        finalResult.put("stderr", "");
        finalResult.put("error", null);
        finalResult.put("execution_time", executionTime);

        Map<String, Object> outputData = new LinkedHashMap<>();
        outputData.put("cells", results);
        finalResult.put("output_data", outputData);

        // Output results as JSON
        System.out.println("<<<RESULTS_START>>>");
        System.out.println(toJson(finalResult));
        System.out.println("<<<RESULTS_END>>>");

        if (logWriter != null) {
            logWriter.close();
        }
    }

    private static void evaluateCellSource(
            JShell jshell,
            String cellSource,
            PrintStream psErr,
            StringBuilder evalResult,
            boolean[] successRef,
            String[] errorMsgRef) {
        SourceCodeAnalysis sourceCodeAnalysis = jshell.sourceCodeAnalysis();
        String remaining = cellSource == null ? "" : cellSource;
        int guard = 0;

        while (remaining != null && !remaining.trim().isEmpty()) {
            if (guard++ > 2000) {
                successRef[0] = false;
                psErr.println("Cell execution aborted: too many snippets in one cell.");
                return;
            }

            SourceCodeAnalysis.CompletionInfo completion = sourceCodeAnalysis.analyzeCompletion(remaining);
            String snippet = completion.source();
            String nextRemaining = completion.remaining();

            // Fallback for parser edge-cases where JShell cannot split further.
            if (snippet == null || snippet.trim().isEmpty()) {
                snippet = remaining;
                nextRemaining = "";
            }

            List<SnippetEvent> events = jshell.eval(snippet);
            processSnippetEvents(jshell, events, psErr, evalResult, successRef, errorMsgRef);

            if (nextRemaining == null || nextRemaining.equals(remaining)) {
                break;
            }

            remaining = nextRemaining;
        }
    }

    private static void processSnippetEvents(
            JShell jshell,
            List<SnippetEvent> events,
            PrintStream psErr,
            StringBuilder evalResult,
            boolean[] successRef,
            String[] errorMsgRef) {
        for (SnippetEvent event : events) {
            if (event.status() == Status.VALID) {
                String value = event.value();
                if (value != null && !value.isEmpty() && !"null".equals(value)) {
                    evalResult.append(value).append("\n");
                }
            } else if (event.status() == Status.REJECTED) {
                successRef[0] = false;
                StringBuilder firstDiag = new StringBuilder();
                jshell.diagnostics(event.snippet()).forEach(diag -> {
                    String message = diag.getMessage(Locale.getDefault());
                    psErr.println(message);
                    if (firstDiag.length() == 0) {
                        firstDiag.append(message);
                    }
                });

                if (errorMsgRef[0] == null || errorMsgRef[0].isEmpty()) {
                    errorMsgRef[0] = firstDiag.length() > 0
                            ? "Compilation error: " + firstDiag
                            : "Compilation error in notebook cell";
                }
            }

            if (event.exception() != null) {
                successRef[0] = false;
                event.exception().printStackTrace(psErr);
                errorMsgRef[0] = event.exception().getMessage();
            }
        }
    }

    private static boolean isLikelySyntaxCompilationIssue(String errorMsg, String stderrText) {
        String combined = ((errorMsg == null ? "" : errorMsg) + "\n" + (stderrText == null ? "" : stderrText))
                .toLowerCase();

        return combined.contains("compilation error")
                || combined.contains("cannot find symbol")
                || combined.contains("';' expected")
                || combined.contains("not a statement")
                || combined.contains("illegal start")
                || combined.contains("reached end of file")
                || combined.contains("class, interface, enum")
                || combined.contains("expected");
    }

    // Simple JSON array parser (handles nested objects)
    private static List<Map<String, Object>> parseJsonArray(String json) {
        try {
            json = json.trim();
            if (!json.startsWith("[") || !json.endsWith("]")) {
                return null;
            }

            List<Map<String, Object>> result = new ArrayList<>();
            json = json.substring(1, json.length() - 1).trim();

            if (json.isEmpty()) {
                return result;
            }

            // Parse each object
            int depth = 0;
            int start = 0;
            boolean inString = false;
            char prevChar = 0;

            for (int i = 0; i < json.length(); i++) {
                char c = json.charAt(i);

                if (c == '"' && prevChar != '\\') {
                    inString = !inString;
                } else if (!inString) {
                    if (c == '{' || c == '[') {
                        depth++;
                    } else if (c == '}' || c == ']') {
                        depth--;
                    } else if (c == ',' && depth == 0) {
                        String objStr = json.substring(start, i).trim();
                        Map<String, Object> obj = parseJsonObject(objStr);
                        if (obj != null) {
                            result.add(obj);
                        }
                        start = i + 1;
                    }
                }
                prevChar = c;
            }

            // Last element
            String objStr = json.substring(start).trim();
            if (!objStr.isEmpty()) {
                Map<String, Object> obj = parseJsonObject(objStr);
                if (obj != null) {
                    result.add(obj);
                }
            }

            return result;
        } catch (Exception e) {
            templateLog("JSON parse error: " + e.getMessage(), "ERROR");
            return null;
        }
    }

    private static Map<String, Object> parseJsonObject(String json) {
        json = json.trim();
        if (!json.startsWith("{") || !json.endsWith("}")) {
            return null;
        }

        Map<String, Object> result = new LinkedHashMap<>();
        json = json.substring(1, json.length() - 1).trim();

        if (json.isEmpty()) {
            return result;
        }

        // Simple key-value parsing
        int depth = 0;
        int start = 0;
        boolean inString = false;
        char prevChar = 0;

        for (int i = 0; i < json.length(); i++) {
            char c = json.charAt(i);

            if (c == '"' && prevChar != '\\') {
                inString = !inString;
            } else if (!inString) {
                if (c == '{' || c == '[') {
                    depth++;
                } else if (c == '}' || c == ']') {
                    depth--;
                } else if (c == ',' && depth == 0) {
                    parseKeyValue(json.substring(start, i), result);
                    start = i + 1;
                }
            }
            prevChar = c;
        }

        // Last key-value
        parseKeyValue(json.substring(start), result);

        return result;
    }

    private static void parseKeyValue(String kv, Map<String, Object> result) {
        kv = kv.trim();
        int colonIndex = -1;
        boolean inString = false;
        char prevChar = 0;

        for (int i = 0; i < kv.length(); i++) {
            char c = kv.charAt(i);
            if (c == '"' && prevChar != '\\') {
                inString = !inString;
            } else if (c == ':' && !inString) {
                colonIndex = i;
                break;
            }
            prevChar = c;
        }

        if (colonIndex == -1)
            return;

        String key = kv.substring(0, colonIndex).trim();
        String value = kv.substring(colonIndex + 1).trim();

        // Remove quotes from key
        if (key.startsWith("\"") && key.endsWith("\"")) {
            key = unescapeString(key.substring(1, key.length() - 1));
        }

        // Parse value
        result.put(key, parseJsonValue(value));
    }

    private static Object parseJsonValue(String value) {
        value = value.trim();

        if (value.equals("null")) {
            return null;
        } else if (value.equals("true")) {
            return true;
        } else if (value.equals("false")) {
            return false;
        } else if (value.startsWith("\"") && value.endsWith("\"")) {
            return unescapeString(value.substring(1, value.length() - 1));
        } else if (value.startsWith("[")) {
            return parseJsonArray(value);
        } else if (value.startsWith("{")) {
            return parseJsonObject(value);
        } else {
            // Try to parse as number
            try {
                if (value.contains(".")) {
                    return Double.parseDouble(value);
                } else {
                    return Long.parseLong(value);
                }
            } catch (NumberFormatException e) {
                return value;
            }
        }
    }

    private static String unescapeString(String s) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\\' && i + 1 < s.length()) {
                char next = s.charAt(i + 1);
                switch (next) {
                    case '"':
                        sb.append('"');
                        i++;
                        break;
                    case '\\':
                        sb.append('\\');
                        i++;
                        break;
                    case 'n':
                        sb.append('\n');
                        i++;
                        break;
                    case 'r':
                        sb.append('\r');
                        i++;
                        break;
                    case 't':
                        sb.append('\t');
                        i++;
                        break;
                    case 'b':
                        sb.append('\b');
                        i++;
                        break;
                    case 'f':
                        sb.append('\f');
                        i++;
                        break;
                    case 'u':
                        if (i + 5 < s.length()) {
                            String hex = s.substring(i + 2, i + 6);
                            sb.append((char) Integer.parseInt(hex, 16));
                            i += 5;
                        }
                        break;
                    default:
                        sb.append(c);
                        break;
                }
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    // Convert results to JSON string
    @SuppressWarnings("unchecked")
    private static String toJson(Object obj) {
        if (obj == null) {
            return "null";
        } else if (obj instanceof String) {
            return JSONBuilder.toJsonString((String) obj);
        } else if (obj instanceof Number) {
            return obj.toString();
        } else if (obj instanceof Boolean) {
            return obj.toString();
        } else if (obj instanceof List) {
            List<?> list = (List<?>) obj;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < list.size(); i++) {
                if (i > 0)
                    sb.append(",");
                sb.append(toJson(list.get(i)));
            }
            sb.append("]");
            return sb.toString();
        } else if (obj instanceof Map) {
            Map<String, Object> map = (Map<String, Object>) obj;
            StringBuilder sb = new StringBuilder("{");
            boolean first = true;
            for (Map.Entry<String, Object> entry : map.entrySet()) {
                if (!first)
                    sb.append(",");
                first = false;
                sb.append(JSONBuilder.toJsonString(entry.getKey()));
                sb.append(":");
                sb.append(toJson(entry.getValue()));
            }
            sb.append("}");
            return sb.toString();
        }
        return JSONBuilder.toJsonString(obj.toString());
    }
}
