import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;

// --- JSON Helper (Minimal) ---
class JsonSerializer {
    static String toJson(Object o) {
        if (o == null)
            return "null";
        if (o instanceof String)
            return "\"" + ((String) o).replace("\"", "\\\"").replace("\n", "\\n") + "\"";
        if (o instanceof Number || o instanceof Boolean)
            return o.toString();
        // Very basic list support
        if (o instanceof List) {
            List<?> l = (List<?>) o;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < l.size(); i++) {
                sb.append(toJson(l.get(i)));
                if (i < l.size() - 1)
                    sb.append(",");
            }
            sb.append("]");
            return sb.toString();
        }
        if (o instanceof TestResult) {
            TestResult tr = (TestResult) o;
            return String.format(
                    "{\"name\":%s,\"description\":%s,\"score\":%s,\"max_score\":%s,\"passed\":%s,\"status\":%s,\"error\":%s,\"output\":%s}",
                    toJson(tr.name), toJson(tr.description), toJson(tr.score), toJson(tr.max_score), toJson(tr.passed),
                    toJson(tr.status), toJson(tr.error), toJson(tr.output));
        }
        return "\"" + o.toString() + "\"";
    }
}

class TestResult {
    String name;
    String description;
    double score;
    double max_score;
    boolean passed;
    String status; // "passed", "failed", "error"
    String error;
    String output;

    public TestResult(String name, double max_score, String description) {
        this.name = name;
        this.description = description;
        this.max_score = max_score;
        this.score = 0;
        this.passed = false;
        this.status = "failed";
        this.error = null;
        this.output = "";
    }
}

// --- Annotation ---
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Test {
    String name()

    default "";double points()

    default 1.0;String description() default "";
}

public class TestRunner {

    // --- Injected Test Code ---
    // The student tests will be methods in this class

    #{TEST_CODE}

    // --- Runner Logic ---
    public static void main(String[] args) {
        List<TestResult> results = new ArrayList<>();

        Method[] methods = TestRunner.class.getDeclaredMethods();
        for (Method method : methods) {
            if (method.isAnnotationPresent(Test.class)) {
                Test annotation = method.getAnnotation(Test.class);
                String testName = annotation.name().isEmpty() ? method.getName() : annotation.name();
                double points = annotation.points();
                String description = annotation.description();

                TestResult result = new TestResult(testName, points, description);

                // Capture stdout/stderr
                PrintStream originalOut = System.out;
                PrintStream originalErr = System.err;
                ByteArrayOutputStream outContent = new ByteArrayOutputStream();
                ByteArrayOutputStream errContent = new ByteArrayOutputStream();

                try {
                    System.setOut(new PrintStream(outContent));
                    System.setErr(new PrintStream(errContent));

                    // Run Test
                    TestRunner instance = new TestRunner();
                    method.setAccessible(true);
                    method.invoke(instance);

                    result.passed = true;
                    result.score = points;
                    result.status = "passed";
                } catch (Exception e) {
                    result.passed = false;
                    result.score = 0;
                    result.status = "failed";
                    Throwable cause = e.getCause();
                    result.error = cause != null ? cause.toString() : e.toString();
                    // result.error += "\n" + getStackTrace(cause != null ? cause : e);
                } finally {
                    System.setOut(originalOut);
                    System.setErr(originalErr);
                    result.output = outContent.toString() + errContent.toString();
                }

                results.add(result);
            }
        }

        // Output JSON
        System.out.println(
                "<<<TEST_RESULT_JSON_START>>>" + JsonSerializer.toJson(results) + "<<<TEST_RESULT_JSON_END>>>");
    }

    // --- Helper Assertions ---
    public void assertTrue(boolean condition) {
        if (!condition)
            throw new AssertionError("Expected true, got false");
    }

    public void assertEquals(Object expected, Object actual) {
        if (expected == null && actual == null)
            return;
        if (expected != null && expected.equals(actual))
            return;
        throw new AssertionError("Expected " + expected + ", got " + actual);
    }
}
