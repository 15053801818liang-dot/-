#pragma once
#include <atomic>
#include <cstdint>
#include <chrono>

// 轻量 per-op 打点。默认关闭（g_profile=false），仅 --profile 时开启，
// 生产路径零负担。用于"先量后优化"：量出每任务各段的真实耗时占比。
enum class Prof { JsonParse, JsonDump, WalWrite, ZmqEnqueue, COUNT };

extern bool g_profile;
void prof_add(Prof c, uint64_t ns);
void prof_dump();   // 打印各段 count / total / avg，以及每任务贡献

struct ScopedProf {
    Prof c;
    std::chrono::steady_clock::time_point t0;
    explicit ScopedProf(Prof cat) : c(cat) {
        if (g_profile) t0 = std::chrono::steady_clock::now();
    }
    ~ScopedProf() {
        if (g_profile) {
            auto dt = std::chrono::steady_clock::now() - t0;
            prof_add(c, (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(dt).count());
        }
    }
};
