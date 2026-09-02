// 端到端压测客户端：注册 N 个 worker + 提交 M 个任务，
// 走完整 submit -> 调度 -> RUN_TASK -> TASK_DONE 链路并统计吞吐。
#include <zmq.hpp>
#include <nlohmann/json.hpp>
#include <thread>
#include <atomic>
#include <vector>
#include <chrono>
#include <cstring>
#include <iostream>
#include <string>
#include "protocol.h"

using json = nlohmann::json;

static std::atomic<bool>     g_running{true};
static std::atomic<uint64_t> g_done{0};
static std::atomic<int>      g_created{0};   // 实际成功建立的 worker 连接数

static std::string endpoint = "tcp://localhost:5555";

// 收取一条完整多帧消息，返回最后一帧（payload）。无消息返回 false。
static bool recv_payload(zmq::socket_t& s, std::string& out) {
    zmq::message_t part;
    auto res = s.recv(part, zmq::recv_flags::dontwait);
    if (!res.has_value()) return false;
    out.assign(static_cast<char*>(part.data()), part.size());
    while (s.get(zmq::sockopt::rcvmore)) {
        zmq::message_t p;
        (void)s.recv(p, zmq::recv_flags::none);
        out.assign(static_cast<char*>(p.data()), p.size());
    }
    return true;
}

static void send_msg(zmq::socket_t& s, const std::string& payload) {
    zmq::message_t delim(FRAME_DELIMITER, 0);
    zmq::message_t body(payload.data(), payload.size());
    s.send(delim, zmq::send_flags::sndmore);
    s.send(body,  zmq::send_flags::none);
}

static void worker_thread(int start_id, int end_id) {
    zmq::context_t ctx(1);
    std::vector<zmq::socket_t> workers;
    workers.reserve(end_id - start_id);

    for (int i = start_id; i < end_id; ++i) {
        try {
            zmq::socket_t sock(ctx, zmq::socket_type::dealer);
            std::string identity = "worker_" + std::to_string(i);
            sock.set(zmq::sockopt::routing_id, identity);
            sock.set(zmq::sockopt::linger, 0);
            sock.connect(endpoint);
            send_msg(sock, R"({"op":"WORKER_READY"})");
            workers.push_back(std::move(sock));
            g_created.fetch_add(1, std::memory_order_relaxed);
        } catch (const zmq::error_t& e) {
            // 撞到 EMFILE / 资源上限：停止本线程继续建连，用已建成的部分参与压测
            static std::atomic<bool> reported{false};
            if (!reported.exchange(true))
                std::cerr << "[worker] socket create failed at ~" << i
                          << ": " << e.what() << " (errno=" << e.num() << ")\n";
            break;
        }
    }

    std::vector<zmq::pollitem_t> items;
    items.reserve(workers.size());
    for (auto& w : workers)
        items.push_back({ static_cast<void*>(w), 0, ZMQ_POLLIN, 0 });

    while (g_running.load()) {
        try {
            zmq::poll(items.data(), items.size(), std::chrono::milliseconds(POLL_TIMEOUT_MS));
            for (size_t i = 0; i < items.size(); ++i) {
                if (!(items[i].revents & ZMQ_POLLIN)) continue;
                std::string payload;
                while (recv_payload(workers[i], payload)) {
                    auto j = json::parse(payload, nullptr, false);
                    if (j.is_discarded()) continue;
                    if (j.value("op", "") == Op::RUN_TASK) {
                        json done = {{"op", Op::TASK_DONE}, {"task_id", j.value("task_id", "")}};
                        send_msg(workers[i], done.dump());
                        g_done.fetch_add(1, std::memory_order_relaxed);
                    }
                }
            }
        } catch (const zmq::error_t& e) {
            if (e.num() == EINTR) continue;
            if (e.num() == EMFILE || e.num() == ENFILE) break;   // FD 上限：本线程退出而非 abort
            throw;
        }
    }
}

int main(int argc, char** argv) {
    int total_workers = 200;
    int total_tasks   = 20000;
    if (argc > 1) total_workers = std::stoi(argv[1]);
    if (argc > 2) total_tasks   = std::stoi(argv[2]);
    if (argc > 3) endpoint      = argv[3];

    unsigned hw = std::thread::hardware_concurrency();
    int num_threads = std::max(1u, std::min(hw, (unsigned)std::max(1, total_workers / 50)));

    std::cout << "workers=" << total_workers << " tasks=" << total_tasks
              << " threads=" << num_threads << " endpoint=" << endpoint << "\n";

    std::vector<std::thread> threads;
    int per = total_workers / num_threads;
    for (int t = 0; t < num_threads; ++t) {
        int s = t * per;
        int e = (t == num_threads - 1) ? total_workers : s + per;
        threads.emplace_back(worker_thread, s, e);
    }

    // 让 worker 完成注册
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    std::cout << "workers connected: " << g_created.load() << "/" << total_workers
              << std::endl;   // 立即 flush，避免撞上限时缓冲丢失

    // 提交任务
    zmq::context_t ctx(1);
    zmq::socket_t submitter(ctx, zmq::socket_type::dealer);
    try {
        submitter.set(zmq::sockopt::routing_id, std::string("submitter"));
        submitter.set(zmq::sockopt::linger, 0);
        submitter.connect(endpoint);
    } catch (const zmq::error_t& e) {
        std::cout << "FD ceiling hit: cannot open submitter (" << e.what()
                  << "). connected=" << g_created.load()
                  << " — connection ceiling reached for this process." << std::endl;
        g_running.store(false);
        for (auto& th : threads) th.join();
        return 2;
    }

    auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < total_tasks; ++i) {
        json task = {
            {"op", Op::SUBMIT_TASK},
            {"task_id", "task_" + std::to_string(i)},
            {"manifest", ""},
            {"code", "noop"}
        };
        send_msg(submitter, task.dump());
    }

    std::chrono::steady_clock::time_point t1;
    if (total_tasks == 0) {
        // drain 模式：仅让 worker 消费 hub 侧已存在的 pending（如崩溃恢复后的任务），
        // 直到 800ms 内不再有新的完成为止。
        std::cout << "drain mode: consuming pre-existing pending tasks...\n";
        uint64_t last = 0;
        auto idle_since = std::chrono::steady_clock::now();
        while (true) {
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            uint64_t cur = g_done.load();
            auto now = std::chrono::steady_clock::now();
            if (cur != last) { last = cur; idle_since = now; }
            if (now - idle_since > std::chrono::milliseconds(800)) break;
        }
        t1 = std::chrono::steady_clock::now();
    } else {
        std::cout << "submitted " << total_tasks << " tasks, waiting for completion...\n";
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
        while (g_done.load() < (uint64_t)total_tasks &&
               std::chrono::steady_clock::now() < deadline) {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        t1 = std::chrono::steady_clock::now();
    }

    double secs = std::chrono::duration<double>(t1 - t0).count();
    uint64_t done = g_done.load();
    std::cout << "completed " << done << "/" << total_tasks
              << " in " << secs << "s -> "
              << (secs > 0 ? (done / secs) : 0.0) << " tasks/s\n";

    g_running.store(false);
    for (auto& th : threads) th.join();
    std::cout << "benchmark done\n";
    if (total_tasks == 0) return done > 0 ? 0 : 1;   // drain 模式
    return done == (uint64_t)total_tasks ? 0 : 1;
}
