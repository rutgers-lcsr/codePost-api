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

        // Check if too many cells
        if (cells.size() > MAX_CELLS) {
            templateLog("Too many cells: " + cells.size(), "ERROR");
            Map<String, Object> errorResult = new LinkedHashMap<>();
            errorResult.put("cell_type", "markdown");
            errorResult.put("source", "**Error:** Too many cells (" + cells.size() + "). Maximum allowed: " + MAX_CELLS
                    + "\n\nExecution stopped.");
            results.add(errorResult);
        } else {
            // Create JShell instance for executing cells
            JShell jshell = JShell.builder()
                    .out(new PrintStream(new ByteArrayOutputStream())) // We'll capture output ourselves
                    .err(new PrintStream(new ByteArrayOutputStream()))
                    .build();

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

                    // Capture stdout and stderr
                    ByteArrayOutputStream stdoutCapture = new ByteArrayOutputStream();
                    ByteArrayOutputStream stderrCapture = new ByteArrayOutputStream();
                    PrintStream originalOut = System.out;
                    PrintStream originalErr = System.err;

                    // Temporary file for plot capture
                    File plotFile = null;
                    try {
                        plotFile = File.createTempFile("plot_", ".png");
                    } catch (IOException e) {
                        templateLog("Failed to create temp file for plot: " + e.getMessage(), "WARNING");
                    }

                    try {
                        System.setOut(new PrintStream(stdoutCapture, true, StandardCharsets.UTF_8));
                        System.setErr(new PrintStream(stderrCapture, true, StandardCharsets.UTF_8));

                        // Execute the code using JShell
                        List<SnippetEvent> events = jshell.eval(cellSource);

                        StringBuilder evalResult = new StringBuilder();
                        for (SnippetEvent event : events) {
                            if (event.status() == Status.VALID) {
                                // Check if there's a value to display
                                String value = event.value();
                                if (value != null && !value.isEmpty() && !"null".equals(value)) {
                                    evalResult.append(value).append("\n");
                                }
                            } else if (event.status() == Status.REJECTED) {
                                success = false;
                                // Get diagnostics for the error
                                jshell.diagnostics(event.snippet()).forEach(diag -> {
                                    System.err.println(diag.getMessage(Locale.getDefault()));
                                });
                            }

                            // Check for exceptions
                            if (event.exception() != null) {
                                success = false;
                                StringWriter sw = new StringWriter();
                                event.exception().printStackTrace(new PrintWriter(sw));
                                errorMsg = event.exception().getMessage();
                                System.err.println(sw.toString());
                            }
                        }

                        // Print any expression results
                        if (evalResult.length() > 0) {
                            originalOut.print(evalResult.toString());
                            stdoutCapture.write(evalResult.toString().getBytes(StandardCharsets.UTF_8));
                        }

                    } catch (Exception e) {
                        success = false;
                        errorMsg = e.getMessage();
                        StringWriter sw = new StringWriter();
                        e.printStackTrace(new PrintWriter(sw));
                        try {
                            stderrCapture.write(sw.toString().getBytes(StandardCharsets.UTF_8));
                        } catch (IOException ignored) {
                        }
                    } finally {
                        System.setOut(originalOut);
                        System.setErr(originalErr);
                    }

                    String stdoutText = stdoutCapture.toString(StandardCharsets.UTF_8);
                    String stderrText = stderrCapture.toString(StandardCharsets.UTF_8);

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
                    if (plotFile != null) {
                        plotFile.delete();
                    }

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

    // Simple JSON array parser (handles nested objects)
    @SuppressWarnings("unchecked")
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
