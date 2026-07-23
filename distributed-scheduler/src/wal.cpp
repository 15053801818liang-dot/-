#include "wal.h"
#include "shared_state.h"
#include <nlohmann/json.hpp>
#include <cstdio>
#include <cstring>
#include <filesystem>

static FILE*       g_wal_file = nullptr;
static std::string g_wal_path;
static bool        g_wal_flush = true;

void wal_set_flush(bool enabled) { g_wal_flush = enabled; }

// 二进制写辅助（uint32_t 长度前缀，避免 size_t 跨平台差异）
static void write_string(FILE* f, const char* s) {
    uint32_t len = s ? static_cast<uint32_t>(strlen(s)) : 0;
    fwrite(&len, sizeof(len), 1, f);
    if (len > 0) fwrite(s, 1, len, f);
}

static bool read_string(FILE* f, std::string& out) {
    uint32_t len;
    if (fread(&len, sizeof(len), 1, f) != 1) return false;
    out.resize(len);
    if (len > 0 && fread(&out[0], 1, len, f) != len) return false;
    return true;
}

void wal_set_path(const char* path) {
    g_wal_path = path;
}

int wal_write(WalOp op, const char* task_id, const char* data, const char* worker_id) {
    if (!g_wal_file) {
        g_wal_file = fopen(g_wal_path.c_str(), "ab");   // 二进制追加
        if (!g_wal_file) return -1;
    }
    uint8_t op_byte = static_cast<uint8_t>(op);
    fwrite(&op_byte, 1, 1, g_wal_file);
    write_string(g_wal_file, task_id);
    write_string(g_wal_file, data);
    write_string(g_wal_file, worker_id);
    if (g_wal_flush) fflush(g_wal_file);   // 强制刷盘（--no-flush 可关闭）
    return 0;
}

int wal_replay() {
    if (!std::filesystem::exists(g_wal_path)) return 0;

    FILE* f = fopen(g_wal_path.c_str(), "rb");
    if (!f) return -1;

    int recovered = 0;
    while (true) {
        uint8_t op_byte;
        if (fread(&op_byte, 1, 1, f) != 1) break;   // EOF

        WalOp op = static_cast<WalOp>(op_byte);
        if (op_byte < 1 || op_byte > static_cast<uint8_t>(WalOp::WORKER_READY)) {
            break;   // 非法操作码：终止回放（后续帧不可信）
        }

        std::string task_id, data, worker_id;
        if (!read_string(f, task_id) || !read_string(f, data) || !read_string(f, worker_id)) {
            break;   // 截断帧：终止回放
        }

        std::lock_guard<std::mutex> lock(g_state.mutex);

        // 从 pending 队列按 id 删除（DONE/FAILED 用）
        auto erase_pending = [&](const std::string& id) {
            for (auto it = g_state.pending_tasks.begin(); it != g_state.pending_tasks.end(); ++it) {
                if (it->task_id == id) { g_state.pending_tasks.erase(it); return true; }
            }
            return false;
        };
        auto pending_has = [&](const std::string& id) {
            for (const auto& t : g_state.pending_tasks)
                if (t.task_id == id) return true;
            return false;
        };

        // 崩溃恢复语义：重启后没有任何存活 worker 会话，因此
        //  - 已 SUBMIT 但未 DONE 的任务一律进入 pending，等待重新派发；
        //  - active_tasks 在回放期间保持为空（运行期才会填充）。
        switch (op) {
            case WalOp::SUBMIT: {
                auto j = nlohmann::json::parse(data, nullptr, false);
                if (j.is_discarded() || !j.contains("task_id")) break;
                std::string tid = j["task_id"].get<std::string>();
                if (pending_has(tid)) break;                 // 幂等
                PendingTask task{tid, j.value("manifest", ""), j.value("code", "")};
                g_state.task_archive[tid] = task;            // 归档（拷贝）
                g_state.pending_tasks.push_back(std::move(task));
                recovered++;
                break;
            }
            case WalOp::ASSIGN:
                // 派发过但未确认完成：重启后仍需重跑，pending 中已存在，无需改动。
                break;
            case WalOp::DONE:
            case WalOp::FAILED:
                erase_pending(task_id);
                g_state.active_tasks.erase(task_id);
                g_state.task_archive.erase(task_id);
                recovered++;
                break;
            case WalOp::REQUEUE: {
                auto archived = g_state.task_archive.find(task_id);
                if (archived != g_state.task_archive.end() && !pending_has(task_id)) {
                    g_state.pending_tasks.push_back(archived->second);
                    recovered++;
                }
                g_state.active_tasks.erase(task_id);
                break;
            }
            case WalOp::WORKER_READY:
                // 向后兼容：旧 WAL 可能含此记录，回放时忽略（worker 会重连上报）。
                break;
        }
    }

    fclose(f);
    return recovered;
}

int wal_truncate() {
    wal_close();
    if (std::filesystem::exists(g_wal_path)) {
        return std::filesystem::remove(g_wal_path) ? 0 : -1;
    }
    return 0;
}

void wal_flush() {
    if (g_wal_file) fflush(g_wal_file);
}

void wal_close() {
    if (g_wal_file) {
        fclose(g_wal_file);
        g_wal_file = nullptr;
    }
}
