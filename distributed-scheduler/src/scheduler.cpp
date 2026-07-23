#include "scheduler.h"
#include "io_thread.h"
#include "shared_state.h"
#include "protocol.h"
#include "wal.h"
#include <nlohmann/json.hpp>
#include <thread>

static void send_frames(const std::string& identity, const std::string& payload) {
    std::vector<zmq::message_t> frames;
    frames.emplace_back(identity.data(), identity.size());
    frames.emplace_back(FRAME_DELIMITER, 0);
    frames.emplace_back(payload.data(), payload.size());
    send_to_io_thread(std::move(frames));
}

// 解析单条来自 worker/client 的消息。调用时不持有 g_state.mutex，
// 内部按需短暂加锁。
void dispatch_message(std::vector<zmq::message_t>& frames) {
    if (frames.size() < 2) return;   // 至少 identity + payload
    std::string identity(static_cast<char*>(frames.front().data()), frames.front().size());
    std::string payload(static_cast<char*>(frames.back().data()),  frames.back().size());

    auto j = nlohmann::json::parse(payload, nullptr, false);
    if (j.is_discarded()) return;

    std::string op = j.value("op", "");

    if (op == Op::WORKER_READY) {
        // Worker 存活是"活连接"状态，不是持久任务状态：崩溃后连接断开，
        // worker 必须重连并重新上报，故不写入 WAL（否则重放会造出幽灵 worker）。
        std::lock_guard<std::mutex> lk(g_state.mutex);
        g_state.worker_pool.add_or_update(identity);

    } else if (op == Op::HEARTBEAT) {
        {
            std::lock_guard<std::mutex> lk(g_state.mutex);
            g_state.worker_pool.add_or_update(identity);
        }
        send_frames(identity, R"({"op":"PONG"})");

    } else if (op == Op::SUBMIT_TASK) {
        std::string task_id = j.value("task_id", "");
        if (task_id.empty()) return;
        PendingTask task{task_id, j.value("manifest", ""), j.value("code", "")};
        {
            std::lock_guard<std::mutex> lk(g_state.mutex);
            g_state.task_archive[task_id] = task;
            g_state.pending_tasks.push_back(std::move(task));
            g_state.tasks_submitted++;
            wal_write(WalOp::SUBMIT, task_id.c_str(), payload.c_str(), nullptr);
        }
        g_state.cv.notify_one();

    } else if (op == Op::TASK_DONE) {
        std::string task_id = j.value("task_id", "");
        std::lock_guard<std::mutex> lk(g_state.mutex);
        auto it = g_state.active_tasks.find(task_id);
        if (it != g_state.active_tasks.end()) {
            std::string worker_id = it->second;
            g_state.worker_pool.mark_idle(worker_id);
            g_state.active_tasks.erase(it);
            g_state.task_archive.erase(task_id);
            g_state.tasks_completed++;
            wal_write(WalOp::DONE, task_id.c_str(), nullptr, worker_id.c_str());
        }

    } else if (op == Op::TASK_FAILED) {
        std::string task_id = j.value("task_id", "");
        std::lock_guard<std::mutex> lk(g_state.mutex);
        auto it = g_state.active_tasks.find(task_id);
        if (it != g_state.active_tasks.end()) {
            std::string worker_id = it->second;
            g_state.worker_pool.mark_idle(worker_id);
            auto archived = g_state.task_archive.find(task_id);
            if (archived != g_state.task_archive.end()) {
                g_state.pending_tasks.push_back(archived->second);   // 重新入队
            }
            g_state.active_tasks.erase(it);
            wal_write(WalOp::REQUEUE, task_id.c_str(), nullptr, worker_id.c_str());
        }

    } else if (op == Op::SHUTDOWN) {
        g_state.shutdown_requested = true;
        g_state.cv.notify_all();
    }
}

void scheduler_thread() {
    while (true) {
        std::unique_lock<std::mutex> lk(g_state.mutex);
        g_state.cv.wait(lk, [] {
            return !g_state.recv_queue.empty()
                || (!g_state.pending_tasks.empty() && g_state.worker_pool.has_idle())
                || g_state.shutdown_requested.load();
        });

        g_state.cv_wakes++;

        if (g_state.shutdown_requested.load()) break;

        // 先排空所有网络消息（dispatch 内部自行加锁，故这里先解锁）
        while (!g_state.recv_queue.empty()) {
            auto frames = std::move(g_state.recv_queue.front());
            g_state.recv_queue.pop_front();
            lk.unlock();
            dispatch_message(frames);
            lk.lock();
        }

        if (g_state.pending_tasks.empty() || !g_state.worker_pool.has_idle()) {
            continue;
        }

        // 调度一个任务
        auto worker_opt = g_state.worker_pool.find_and_mark_idle();
        if (!worker_opt) continue;

        auto task = std::move(g_state.pending_tasks.front());
        g_state.pending_tasks.pop_front();
        g_state.active_tasks[task.task_id] = *worker_opt;
        g_state.tasks_assigned++;

        nlohmann::json j = {
            {"op", Op::RUN_TASK},
            {"task_id", task.task_id},
            {"manifest", task.manifest},
            {"code", task.code}
        };
        std::string payload = j.dump();
        std::string worker_id = *worker_opt;
        wal_write(WalOp::ASSIGN, task.task_id.c_str(), payload.c_str(), worker_id.c_str());

        lk.unlock();
        send_frames(worker_id, payload);   // 无锁发送，避免阻塞调度
    }
}

void worker_watchdog_thread() {
    using namespace std::chrono;
    while (g_state.running.load()) {
        for (int i = 0; i < 50 && g_state.running.load(); ++i) {
            std::this_thread::sleep_for(milliseconds(100));   // 可及时响应退出
        }
        if (!g_state.running.load()) break;

        std::vector<std::string> dead_busy;
        {
            std::lock_guard<std::mutex> lock(g_state.mutex);
            g_state.worker_pool.reap_stale_idle(seconds(30));
            dead_busy = g_state.worker_pool.reap_stale_busy(seconds(120));

            // 繁忙 Worker 超时 -> 僵尸任务重建
            for (const auto& worker_id : dead_busy) {
                std::string zombie;
                for (const auto& [tid, wid] : g_state.active_tasks) {
                    if (wid == worker_id) { zombie = tid; break; }
                }
                if (!zombie.empty()) {
                    auto archived = g_state.task_archive.find(zombie);
                    if (archived != g_state.task_archive.end()) {
                        g_state.pending_tasks.push_back(archived->second);
                        g_state.active_tasks.erase(zombie);
                        wal_write(WalOp::REQUEUE, zombie.c_str(), nullptr, worker_id.c_str());
                    }
                }
            }
        }
        if (!dead_busy.empty()) g_state.cv.notify_one();
    }
}
