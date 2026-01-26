#include <iostream>
#include <string>
#include <vector>
#include <sstream>
#include <functional>
#include <cmath>

// --- JSON Serialization Helper ---
std::string json_escape(const std::string& s) {
    std::string res = "\"";
    for (char c : s) {
        if (c == '"') res += "\\\"";
        else if (c == '\n') res += "\\n";
        else res += c;
    }
    res += "\"";
    return res;
}

struct TestResult {
    std::string name;
    std::string description;
    double score;
    double max_score;
    bool passed;
    std::string status;
    std::string error;
    std::string output;
    
    std::string to_json() const {
        std::stringstream ss;
        ss << "{"
           << "\"name\":" << json_escape(name) << ","
           << "\"description\":" << json_escape(description) << ","
           << "\"score\":" << score << ","
           << "\"max_score\":" << max_score << ","
           << "\"passed\":" << (passed ? "true" : "false") << ","
           << "\"status\":" << json_escape(status) << ","
           << "\"error\":" << json_escape(error) << ","
           << "\"output\":" << json_escape(output)
           << "}";
        return ss.str();
    }
};

class TestRegistry {
public:
    struct Test {
        std::string name;
        double points;
        std::string description;
        std::function<void()> func;
    };
    
    static TestRegistry& instance() {
        static TestRegistry inst;
        return inst;
    }
    
    void register_test(std::string name, double points, std::string description, std::function<void()> func) {
        tests.push_back({name, points, description, func});
    }
    
    std::vector<Test> tests;
};

// Macro to register tests
// TEST(TestName, Points) { ... }
#define TEST(name, points) TEST_DESC(name, points, "")

#define TEST_DESC(name, points, description) \
    void _test_func_##name(); \
    struct _test_reg_##name { \
        _test_reg_##name() { \
            TestRegistry::instance().register_test(#name, points, description, _test_func_##name); \
        } \
    } _test_reg_inst_##name; \
    void _test_func_##name()

// Assertion Helper
void assertTrue(bool condition, const std::string& msg = "Assertion failed") {
    if (!condition) throw std::runtime_error(msg);
}

// Injected Test Code
// This will likely contain TEST(...) blocks
#{TEST_CODE}


int main(int argc, char** argv) {
    std::vector<TestResult> results;
    
    for (const auto& test : TestRegistry::instance().tests) {
        TestResult res;
        res.name = test.name;
        res.max_score = test.points;
        res.score = 0;
        res.passed = false;
        res.status = "failed";
        
        // Capture stdout/stderr? 
        // Standard C++ cannot easily capture stdout buffer portably without platform specific or pipe logic.
        // For now, we leave output empty or rely on the container capture for the whole execution.
        // Or redirects cout rdbuf.
        
        std::stringstream buffer;
        std::streambuf* old = std::cout.rdbuf(buffer.rdbuf());
        
        try {
            test.func();
            res.passed = true;
            res.score = test.points;
            res.status = "passed";
        } catch (const std::exception& e) {
            res.error = e.what();
        } catch (...) {
            res.error = "Unknown Error";
        }
        
        std::cout.rdbuf(old);
        res.output = buffer.str();
        results.push_back(res);
    }
    
    std::cout << "<<<TEST_RESULT_JSON_START>>>[";
    for (size_t i = 0; i < results.size(); ++i) {
        std::cout << results[i].to_json();
        if (i < results.size() - 1) std::cout << ",";
    }
    std::cout << "]<<<TEST_RESULT_JSON_END>>>" << std::endl;
    
    return 0;
}
