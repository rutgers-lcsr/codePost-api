#include <iostream>
#include <string>
#include <vector>
#include <sstream>
#include <functional>
#include <cmath>
#include <future>
#include <chrono>

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
    std::string message;
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
           << "\"message\":" << json_escape(message) << ","
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

const int DEFAULT_TIMEOUT_SECONDS = 30;

struct PartialResult {
    double score;
    std::string message;
};

inline PartialResult return_score(double score, const std::string& message = "") {
    return PartialResult{score, message};
}

template <typename T>
struct is_pair : std::false_type {};

template <typename A, typename B>
struct is_pair<std::pair<A, B>> : std::true_type {};

template <typename T>
struct is_tuple : std::false_type {};

template <typename... Args>
struct is_tuple<std::tuple<Args...>> : std::true_type {};

template <typename Func>
std::function<void(TestResult&)> wrap_test(Func func) {
    return [func](TestResult& res) {
        using Ret = decltype(func());
        if constexpr (std::is_void_v<Ret>) {
            func();
            res.passed = true;
            res.score = res.max_score;
            res.status = "passed";
        } else if constexpr (std::is_arithmetic_v<Ret>) {
            double score = static_cast<double>(func());
            res.score = std::max(0.0, std::min(score, res.max_score));
            res.passed = res.score == res.max_score;
            res.status = res.passed ? "passed" : "partial";
        } else if constexpr (std::is_same_v<Ret, PartialResult>) {
            PartialResult pr = func();
            res.score = std::max(0.0, std::min(pr.score, res.max_score));
            res.message = pr.message;
            res.passed = res.score == res.max_score;
            res.status = res.passed ? "passed" : "partial";
        } else if constexpr (is_pair<Ret>::value) {
            auto pr = func();
            if constexpr (std::is_arithmetic_v<decltype(pr.first)>) {
                res.score = std::max(0.0, std::min(static_cast<double>(pr.first), res.max_score));
                res.message = pr.second;
                res.passed = res.score == res.max_score;
                res.status = res.passed ? "passed" : "partial";
            } else {
                res.passed = true;
                res.score = res.max_score;
                res.status = "passed";
            }
        } else if constexpr (is_tuple<Ret>::value && std::tuple_size<Ret>::value >= 2) {
            auto pr = func();
            if constexpr (std::is_arithmetic_v<decltype(std::get<0>(pr))>) {
                res.score = std::max(0.0, std::min(static_cast<double>(std::get<0>(pr)), res.max_score));
                res.message = std::get<1>(pr);
                res.passed = res.score == res.max_score;
                res.status = res.passed ? "passed" : "partial";
            } else {
                res.passed = true;
                res.score = res.max_score;
                res.status = "passed";
            }
        } else if constexpr (std::is_convertible_v<Ret, std::string>) {
            res.message = func();
            res.passed = true;
            res.score = res.max_score;
            res.status = "passed";
        } else {
            func();
            res.passed = true;
            res.score = res.max_score;
            res.status = "passed";
        }
    };
}

class TestRegistry {
public:
    struct Test {
        std::string name;
        double points;
        std::string description;
        int timeout;
        std::function<void(TestResult&)> runner;
    };
    
    static TestRegistry& instance() {
        static TestRegistry inst;
        return inst;
    }
    
    template <typename Func>
    void register_test(std::string name, double points, std::string description, int timeout, Func func) {
        tests.push_back({name, points, description, timeout, wrap_test(func)});
    }
    
    std::vector<Test> tests;
};

// Macro to register tests
// TEST(TestName, Points) { ... }
// TEST_TIMEOUT(TestName, Points, TimeoutSeconds) { ... }
// TEST_DESC(TestName, Points, "Description") { ... }
// TEST_DESC_TIMEOUT(TestName, Points, "Description", TimeoutSeconds) { ... }
#define TEST(name, points) TEST_DESC_TIMEOUT(name, points, "", DEFAULT_TIMEOUT_SECONDS)

#define TEST_TIMEOUT(name, points, timeout) TEST_DESC_TIMEOUT(name, points, "", timeout)

#define TEST_DESC(name, points, description) TEST_DESC_TIMEOUT(name, points, description, DEFAULT_TIMEOUT_SECONDS)

#define TEST_DESC_TIMEOUT(name, points, description, timeout) \
    auto _test_func_##name(); \
    struct _test_reg_##name { \
        _test_reg_##name() { \
            TestRegistry::instance().register_test(#name, points, description, timeout, _test_func_##name); \
        } \
    } _test_reg_inst_##name; \
    auto _test_func_##name()

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
        res.message = "";
        
        // Capture stdout/stderr? 
        // Standard C++ cannot easily capture stdout buffer portably without platform specific or pipe logic.
        // For now, we leave output empty or rely on the container capture for the whole execution.
        // Or redirects cout rdbuf.
        
        std::stringstream buffer;
        std::streambuf* old = std::cout.rdbuf(buffer.rdbuf());
        
        try {
            auto future = std::async(std::launch::async, [&test, &res]() {
                test.runner(res);
            });
            if (future.wait_for(std::chrono::seconds(test.timeout)) == std::future_status::timeout) {
                res.error = "Test timed out after " + std::to_string(test.timeout) + "s";
                res.status = "error";
            } else {
                future.get();
            }
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
