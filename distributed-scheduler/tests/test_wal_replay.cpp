// WAL 回放单元测试。
// 语义：崩溃恢复后 active_tasks 为空，所有未 DONE 的任务进入 pending。
// 损坏/截断的 WAL：保留损坏点之前的有效前缀，从第一个坏帧起停止回放。
#include "../src/wal.h"
#include "../src/shared_state.h"
#include "../src/worker_pool.h"
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <filesystem>

// 测试自带 g_state 定义（不链接 hub.cpp）。wal.cpp 只引用 g_state。
SharedState g_state;
IoContext   g_io_ctx;

static const char* WAL_PATH = "test_neuralhub.wal";

static void reset_shared_state() {
    g_state.pending_tasks.clear();
    g_state.active_tasks.clear();
    g_state.worker_pool = WorkerPool();
    g_state.task_archive.clear();
}

int main() {
    std::filesystem::remove(WAL_PATH);
    wal_set_path(WAL_PATH);

    // TEST 1: 正常全量回放
    reset_shared_state();
    wal_write(WalOp::SUBMIT, "task_001", R"({"task_id":"task_001","code":"test1"})", nullptr);
    wal_write(WalOp::ASSIGN, "task_001", nullptr, "worker_01");
    wal_write(WalOp::DONE,   "task_001", nullptr, "worker_01");
    wal_write(WalOp::SUBMIT, "task_002", R"({"task_id":"task_002","code":"test2"})", nullptr);
    wal_write(WalOp::ASSIGN, "task_002", nullptr, "worker_02");
    wal_close();

    wal_replay();
    assert(g_state.pending_tasks.size() == 1);            // task_002 未 DONE
    assert(g_state.active_tasks.empty());                 // 冷启动后无活跃会话
    assert(g_state.pending_tasks[0].task_id == "task_002");
    printf("TEST 1 PASSED: Normal replay\n");

    // TEST 2: 空文件 / 无文件
    reset_shared_state();
    std::filesystem::remove(WAL_PATH);
    wal_set_path(WAL_PATH);
    wal_replay();
    assert(g_state.pending_tasks.empty() && g_state.active_tasks.empty());
    printf("TEST 2 PASSED: Empty file\n");

    // TEST 3: 截断尾部 5 字节 —— 有效前缀(SUBMIT)保留，损坏的 ASSIGN 丢弃
    reset_shared_state();
    wal_write(WalOp::SUBMIT, "task_003", R"({"task_id":"task_003","code":"test3"})", nullptr);
    wal_write(WalOp::ASSIGN, "task_003", nullptr, "worker_03");
    wal_close();
    std::filesystem::resize_file(WAL_PATH, std::filesystem::file_size(WAL_PATH) - 5);
    wal_replay();
    assert(g_state.pending_tasks.size() == 1);            // SUBMIT 有效前缀保留
    assert(g_state.pending_tasks[0].task_id == "task_003");
    assert(g_state.active_tasks.empty());
    printf("TEST 3 PASSED: Truncated tail keeps valid prefix\n");

    // TEST 4: 非法 opcode —— 之前的有效帧恢复，坏字节处停止
    reset_shared_state();
    wal_write(WalOp::SUBMIT, "task_004", R"({"task_id":"task_004","code":"test4"})", nullptr);
    wal_close();
    {
        FILE* f = fopen(WAL_PATH, "ab");
        uint8_t bad_op = 0xFF;
        fwrite(&bad_op, 1, 1, f);
        fclose(f);
    }
    wal_replay();
    assert(g_state.pending_tasks.size() == 1);
    assert(g_state.pending_tasks[0].task_id == "task_004");
    printf("TEST 4 PASSED: Bad opcode\n");

    // TEST 5: DONE 擦除验证
    reset_shared_state();
    std::filesystem::remove(WAL_PATH);
    wal_set_path(WAL_PATH);
    wal_write(WalOp::SUBMIT, "task_030", R"({"task_id":"task_030","code":"test30"})", nullptr);
    wal_write(WalOp::ASSIGN, "task_030", nullptr, "worker_30");
    wal_write(WalOp::DONE,   "task_030", nullptr, "worker_30");
    wal_write(WalOp::SUBMIT, "task_031", R"({"task_id":"task_031","code":"test31"})", nullptr);
    wal_close();
    wal_replay();
    assert(g_state.active_tasks.find("task_030") == g_state.active_tasks.end());  // 已 DONE
    assert(g_state.task_archive.find("task_030") == g_state.task_archive.end());  // 归档清理
    assert(g_state.pending_tasks.size() == 1);
    assert(g_state.pending_tasks[0].task_id == "task_031");                       // 未 DONE
    printf("TEST 5 PASSED: DONE erase\n");

    // TEST 6: 幂等性 —— 两次回放状态一致
    reset_shared_state();
    std::filesystem::remove(WAL_PATH);
    wal_set_path(WAL_PATH);
    wal_write(WalOp::SUBMIT, "task_032", R"({"task_id":"task_032","code":"test32"})", nullptr);
    wal_write(WalOp::ASSIGN, "task_032", nullptr, "worker_32");
    wal_close();
    wal_replay();
    size_t pending_cnt = g_state.pending_tasks.size();
    size_t active_cnt  = g_state.active_tasks.size();
    reset_shared_state();
    wal_replay();
    assert(g_state.pending_tasks.size() == pending_cnt);
    assert(g_state.active_tasks.size()  == active_cnt);
    assert(pending_cnt == 1 && active_cnt == 0);
    printf("TEST 6 PASSED: Idempotency\n");

    std::filesystem::remove(WAL_PATH);
    printf("All WAL tests passed!\n");
    return 0;
}
