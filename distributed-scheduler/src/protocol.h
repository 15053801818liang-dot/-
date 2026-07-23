#pragma once
#include <cstdint>

// ZMQ 空分隔帧（REQ/ROUTER 风格）。收发两端保持一致；
// 解析端只依赖 "identity = 第一帧, payload = 最后一帧"，因此
// 分隔帧存在与否都能正确解析。
constexpr char FRAME_DELIMITER[] = "";
constexpr int POLL_TIMEOUT_MS = 10;
extern int g_poll_ms;   // IO 线程 poll 超时(ms)，默认 10，--poll-ms 可调（用于诊断 send/poll 耦合）
constexpr int ZMQ_MAX_SOCKETS_CAP = 1023;

// 操作码定义（对齐 worker 端）
namespace Op {
    constexpr char WORKER_READY[] = "WORKER_READY";
    constexpr char HEARTBEAT[]    = "HEARTBEAT";
    constexpr char PONG[]         = "PONG";
    constexpr char SUBMIT_TASK[]  = "SUBMIT_TASK";
    constexpr char RUN_TASK[]     = "RUN_TASK";
    constexpr char TASK_DONE[]    = "TASK_DONE";
    constexpr char TASK_FAILED[]  = "TASK_FAILED";
    constexpr char SHUTDOWN[]     = "SHUTDOWN";
}

// WAL 操作码
enum class WalOp : uint8_t {
    SUBMIT       = 1,
    ASSIGN       = 2,
    DONE         = 3,
    FAILED       = 4,
    REQUEUE      = 5,
    WORKER_READY = 6
};
