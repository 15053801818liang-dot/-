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
    static const char* names[] = {"json_parse", "json_dump", "wal_write", "zmq_enqueue",
                                  "io_poll", "io_send", "io_recv"};
    uint64_t tasks = g_state.tasks_completed.load();
    if (tasks == 0) tasks = 1;

    auto row = [&](size_t i) {
        uint64_t n = g_cnt[i].load(), ns = g_ns[i].load();
        printf("  %-12s %10llu %12.1f %10.0f %14.0f\n",
               names[i], (unsigned long long)n, ns / 1e6,
               n ? (double)ns / n : 0.0, (double)ns / tasks);
    };

    printf("PROFILE (--profile):\n");
    printf("  %-12s %10s %12s %10s %14s\n", "section", "count", "total(ms)", "avg(ns)", "ns/task");

    // 调度线程 per-task 段
    double sched_per_task = 0;
    for (size_t i = 0; i <= (size_t)Prof::ZmqEnqueue; ++i) {
        row(i);
        sched_per_task += (double)g_ns[i].load() / tasks;
    }
    printf("  %-12s %10s %12s %10s %14.0f  [scheduler thread]\n",
           "SUM/task", "", "", "", sched_per_task);

    // IO 线程段（独立线程，不并入调度 per-task）
    printf("  --- IO thread (separate thread) ---\n");
    for (size_t i = (size_t)Prof::IoPoll; i <= (size_t)Prof::IoRecv; ++i) row(i);
    uint64_t poll = g_ns[(size_t)Prof::IoPoll].load();
    uint64_t send = g_ns[(size_t)Prof::IoSend].load();
    uint64_t recv = g_ns[(size_t)Prof::IoRecv].load();
    double busy = (poll + send + recv) ? (double)(send + recv) / (poll + send + recv) : 0.0;
    printf("  IO busy fraction = (send+recv)/(poll+send+recv) = %.1f%%\n", busy * 100.0);
    printf("  (io_poll total 含 poll 等待；busy 高=IO 线程饱和是瓶颈，低=IO 有余量)\n");
    printf("  (note: zmq_enqueue/io avg 被 ~2x clock_gettime 开销放大)\n");
}
