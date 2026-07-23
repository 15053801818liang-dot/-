#include "prof.h"
#include "shared_state.h"
#include <cstdio>
#include <array>

bool g_profile = false;

static std::array<std::atomic<uint64_t>, (size_t)Prof::COUNT> g_ns{};
static std::array<std::atomic<uint64_t>, (size_t)Prof::COUNT> g_cnt{};

void prof_add(Prof c, uint64_t ns) {
    g_ns[(size_t)c].fetch_add(ns, std::memory_order_relaxed);
    g_cnt[(size_t)c].fetch_add(1, std::memory_order_relaxed);
}

void prof_dump() {
    if (!g_profile) return;
    static const char* names[] = {"json_parse", "json_dump", "wal_write", "zmq_enqueue"};
    uint64_t tasks = g_state.tasks_completed.load();
    if (tasks == 0) tasks = 1;

    double per_task_total_ns = 0;
    printf("PROFILE (--profile):\n");
    printf("  %-12s %10s %12s %10s %14s\n", "section", "count", "total(ms)", "avg(ns)", "ns/task");
    for (size_t i = 0; i < (size_t)Prof::COUNT; ++i) {
        uint64_t n = g_cnt[i].load(), ns = g_ns[i].load();
        double per_task = (double)ns / tasks;
        per_task_total_ns += per_task;
        printf("  %-12s %10llu %12.1f %10.0f %14.0f\n",
               names[i], (unsigned long long)n, ns / 1e6,
               n ? (double)ns / n : 0.0, per_task);
    }
    printf("  %-12s %10s %12s %10s %14.0f\n", "SUM/task", "", "", "", per_task_total_ns);
    printf("  (note: zmq_enqueue avg is inflated by ~2x clock_gettime overhead)\n");
}
