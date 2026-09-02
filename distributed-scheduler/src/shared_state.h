#pragma once
#include <zmq.hpp>
#include <string>
#include <vector>
#include <deque>
#include <unordered_map>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include "worker_pool.h"

struct PendingTask {
    std::string task_id;
    std::string manifest;
    std::string code;
};

struct IoContext {
    zmq::context_t     ctx;
    zmq::socket_t      router;
    std::atomic<bool>  running{true};
    std::mutex         send_mutex;
    std::deque<std::vector<zmq::message_t>> send_queue;

    IoContext() : ctx(1), router(ctx, zmq::socket_type::router) {
        router.set(zmq::sockopt::sndhwm, 0);
        router.set(zmq::sockopt::rcvhwm, 0);
        router.set(zmq::sockopt::linger, 0);
    }
};

struct SharedState {
    std::mutex               mutex;
    std::condition_variable  cv;

    // 调度状态
    std::deque<PendingTask>                        pending_tasks;
    WorkerPool                                     worker_pool;
    std::unordered_map<std::string, std::string>   active_tasks;   // task_id -> worker_id

    // 任务归档（用于僵尸任务重建 / REQUEUE）
    std::unordered_map<std::string, PendingTask>   task_archive;

    // IO 线程 -> 调度线程 的接收队列
    std::deque<std::vector<zmq::message_t>>        recv_queue;

    // 生命周期
    std::atomic<bool> running{true};
    std::atomic<bool> shutdown_requested{false};

    // Metrics
    std::atomic<uint64_t> tasks_submitted{0};
    std::atomic<uint64_t> tasks_assigned{0};
    std::atomic<uint64_t> tasks_completed{0};
    std::atomic<uint64_t> cv_wakes{0};
};

extern SharedState g_state;
extern IoContext   g_io_ctx;
