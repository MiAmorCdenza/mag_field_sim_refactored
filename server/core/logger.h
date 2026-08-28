// 统一 JSON 日志(C++ 侧,与 engine/logging.py 同 schema 同文件)。
//
// schema: {"ts","level","scope","event","msg","attr"} — JSON Lines 追加写
// logs/server.jsonl;控制台输出人类可读镜像。线程安全。
//
// 用法:
//   MFL("bake", "bake_applied", Info, "已应用", {{"seq", 5}, {"slots", 3}});
//   LOG_INFO("server", "startup", "服务器启动,端口 8001");
#pragma once

#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>

#include <nlohmann/json.hpp>

namespace mflog {

enum class Level : int { Trace = 0, Debug = 1, Info = 2, Warn = 3, Error = 4, Fatal = 5 };

inline const char* level_name(Level l) {
    switch (l) {
        case Level::Trace: return "trace";
        case Level::Debug: return "debug";
        case Level::Info:  return "info";
        case Level::Warn:  return "warn";
        case Level::Error: return "error";
        case Level::Fatal: return "fatal";
    }
    return "info";
}

inline Level level_from_name(const std::string& s) {
    if (s == "trace") return Level::Trace;
    if (s == "debug") return Level::Debug;
    if (s == "warn")  return Level::Warn;
    if (s == "error") return Level::Error;
    if (s == "fatal") return Level::Fatal;
    return Level::Info;
}

class Logger {
public:
    static Logger& instance() {
        static Logger inst;
        return inst;
    }

    void init(const std::string& log_dir, Level min_level) {
        std::lock_guard<std::mutex> g(m_);
        min_ = min_level;
        if (!log_dir.empty() && !file_.is_open()) {
            try {
                std::filesystem::create_directories(log_dir);
            } catch (...) {
                return;  // 目录不可用则仅控制台
            }
            std::string path = log_dir + "/server.jsonl";
            file_.open(path, std::ios::app);
            file_.sync_with_stdio(false);
        }
    }

    void log(Level lv, const std::string& scope, const std::string& event,
             const std::string& msg, const nlohmann::json& attr = nlohmann::json::object()) {
        if ((int)lv < (int)min_) return;
        std::string ts = timestamp();

        nlohmann::json entry{
            {"ts", ts},
            {"level", level_name(lv)},
            {"scope", scope},
            {"event", event},
            {"msg", msg},
            {"attr", attr.is_null() ? nlohmann::json::object() : attr},
        };

        std::lock_guard<std::mutex> g(m_);
        if (file_.is_open()) {
            file_ << entry.dump() << std::endl;
            file_.flush();
        }
        // 控制台人类可读镜像
        std::fprintf(stderr, "%s %-5s [%s.%s] %s%s%s\n",
                     ts.c_str() + 11, level_name(lv), scope.c_str(), event.c_str(),
                     msg.c_str(), attr.empty() ? "" : " ",
                     attr.empty() ? "" : attr.dump().c_str());
    }

private:
    Logger() = default;

    static std::string timestamp() {
        using namespace std::chrono;
        auto now = system_clock::now();
        auto ms = duration_cast<milliseconds>(now.time_since_epoch()) % 1000;
        std::time_t t = system_clock::to_time_t(now);
        std::tm tm{};
        localtime_s(&tm, &t);
        char buf[40];
        std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &tm);
        // 时区偏移(Windows: %z 受支持,但为稳妥手动计算)
        char off[8];
        std::strftime(off, sizeof(off), "%z", &tm);
        std::ostringstream os;
        os << buf << "." << std::setfill('0') << std::setw(3) << ms.count() << off;
        return os.str();
    }

    std::mutex m_;
    std::ofstream file_;
    Level min_ = Level::Info;
};

}  // namespace mflog

// 便捷宏
// MFL 的 attr 必须是 nlohmann::json 表达式:
//   MFL("bake", "bake_applied", Info, "已应用", nlohmann::json{{"seq", 5}});
#define LOG_RAW(lv, scope, event, msg, attr_json)                              \
    ::mflog::Logger::instance().log(::mflog::Level::lv, scope, event, msg,     \
                                    attr_json)
#define MFL(scope, event, lv, msg, attr)                                       \
    ::mflog::Logger::instance().log(::mflog::Level::lv, scope, event, msg, attr)
#define LOG_INFO(scope, event, msg)                                            \
    ::mflog::Logger::instance().log(::mflog::Level::Info, scope, event, msg)
#define LOG_WARN(scope, event, msg)                                            \
    ::mflog::Logger::instance().log(::mflog::Level::Warn, scope, event, msg)
#define LOG_ERROR(scope, event, msg)                                           \
    ::mflog::Logger::instance().log(::mflog::Level::Error, scope, event, msg)
