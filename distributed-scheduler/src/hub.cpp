#include "shared_state.h"
#include "io_thread.h"
#include "scheduler.h"
#include "wal.h"
#include "protocol.h"
#include "prof.h"
#include <csignal>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <thread>
#include <unistd.h>

SharedState g_state;
IoContext   g_io_ctx;
int         g_poll_ms = POLL_TIMEOUT_MS;

// 异步信号安全的 metrics 输出（避免 iostream / malloc）
static void dump_metrics() {
    char buf[256];
    int len = snprintf(buf, sizeof(buf),
        "METRICS: submitted=%llu assigned=%llu completed=%llu wakes=%llu\n",
        (unsigned long long)g_state.tasks_submitted.load(),
        (unsigned long long)g_state.tasks_assigned.load(),
        (unsigned long long)g_state.tasks_completed.load(),
        (unsigned long long)g_state.cv_wakes.load());
    if (len > 0) { ssize_t n = write(STDOUT_FILENO, buf, (size_t)len); (void)n; }
}

static void signal_handler(int sig) {
    if (sig == SIGINT || sig == SIGTERM) {
        g_state.shutdown_requested = true;
        g_io_ctx.running = false;      // 唤醒 IO 线程
        g_state.cv.notify_all();
        dump_metrics();
    }
}

int main(int argc, char** argv) {
    std::string endpoint = "tcp://*:5555";
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--no-flush") == 0) {
            wal_set_flush(false);
        } else if (std::strcmp(argv[i], "--profile") == 0) {
            g_profile = true;
        } else if (std::strcmp(argv[i], "--poll-ms") == 0 && i + 1 < argc) {
            g_poll_ms = std::atoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            endpoint = std::string("tcp://*:") + argv[++i];
        }
    }

    std::signal(SIGINT,  signal_handler);
    std::signal(SIGTERM, signal_handler);

    wal_set_path("neuralhub.wal");
    int recovered = wal_replay();      // 崩溃恢复
    if (recovered > 0) printf("[HUB] WAL replay: %d records recovered\n", recovered);

    g_io_ctx.router.bind(endpoint);
    printf("[HUB] Started on %s\n", endpoint.c_str());
    fflush(stdout);

    std::thread io_th(io_thread_main);
    std::thread sched_th(scheduler_thread);
    std::thread watchdog_th(worker_watchdog_thread);

    sched_th.join();          // 收到 shutdown 后退出
    g_io_ctx.running = false;
    io_th.join();
    g_state.running = false;
    watchdog_th.join();

    prof_dump();
    wal_close();
    wal_truncate();
    printf("[HUB] Shutdown complete\n");
    return 0;
}
