# distributed-scheduler (NeuralHub)

单机多线程任务调度 Hub，基于 ZeroMQ ROUTER/DEALER，带 WAL 崩溃恢复。
线程模型：**IO 线程**（非阻塞收发）+ **调度线程**（CV 驱动，单锁）+ **watchdog**（超时回收）。

> 本目录是对一份原始 Windows 源码的**移植 + 修复版**。原始代码无法编译、
> 运行即崩溃、单测无法链接、压测不产生任何负载。下面「已修复的问题」一节
> 列出全部 16 处缺陷。所有结论均由**真实编译与运行**得出，见「实测结果」。

## 构建（Linux）

```bash
sudo apt-get install -y libzmq3-dev cppzmq-dev nlohmann-json3-dev cmake g++
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

依赖版本（实测通过）：libzmq 4.3.5 / cppzmq 4.10.0 / nlohmann-json 3.11.3 / g++ 13.3 / cmake 3.28。
`CMakeLists.txt` 保留了 `if(WIN32)` 分支，Windows + vcpkg 亦可构建。

## 运行

```bash
# WAL 单元测试（6 场景）
./build/test_wal_replay

# 手动跑 Hub
./build/hub [--port 5555] [--no-flush]

# 一键压测 + 崩溃恢复冒烟
./bench.sh 200 20000

# 端到端压测：<workers> <tasks> [endpoint]
./build/worker_bench 200 20000 tcp://localhost:5555
# drain 模式（tasks=0）：只消费 Hub 侧已有 pending，用于验证崩溃恢复
./build/worker_bench 50 0 tcp://localhost:5555
```

## 实测结果（本仓库 Linux 沙箱）

| 项目 | 结果 |
|---|---|
| 编译 | hub / test_wal_replay / worker_bench 全部通过，无 error |
| WAL 单测 | 6/6 场景通过（正常回放 / 空文件 / 尾部截断 / 非法 opcode / DONE 擦除 / 幂等） |
| 端到端吞吐 | 200 worker × 20000 任务 → `submitted==assigned==completed==20000`，≈ **48k tasks/s** |
| 调度效率 | 每次 CV 唤醒批量排空 recv 队列，唤醒数 ≈ 消息数 × 0.5，无空转 |
| 崩溃恢复 | `kill -9` 后 WAL（~1.6MB）完好；重启回放 17522 条 pending，新 worker 接入后 drain 至完成，`assigned==completed`，无任务丢失、无幽灵 worker |

> 关于规模：原文声称「2000w / 5 万 Worker 已验证」。本沙箱实测为 200 worker / 2 万任务
> 量级的**真实**端到端数字。5 万条 DEALER 连接涉及 FD 上限与 TCP 资源，属另一量级，
> 本环境未验证——不做未经测试的规模声明。

## 线协议

DEALER(worker/client) 发送 `[空分隔帧, JSON]`；ROUTER 自动前置 identity。
解析端只依赖「identity = 首帧，payload = 末帧」，因此分隔帧存在与否都能正确解析。

| op | 方向 | 说明 |
|---|---|---|
| `WORKER_READY` | worker→hub | 注册/上报存活（**不写 WAL**，属活连接状态） |
| `HEARTBEAT` / `PONG` | 双向 | 心跳 |
| `SUBMIT_TASK` | client→hub | 提交任务，写 WAL(SUBMIT) |
| `RUN_TASK` | hub→worker | 派发，写 WAL(ASSIGN) |
| `TASK_DONE` / `TASK_FAILED` | worker→hub | 完成/失败(重入队)，写 WAL(DONE/REQUEUE) |
| `SHUTDOWN` | client→hub | 优雅退出 |

## WAL 与崩溃恢复语义

二进制格式：`op(1B) | len(4B)+task_id | len(4B)+data | len(4B)+worker_id`，逐条 `fflush`
（`--no-flush` 可关）。回放规则：

- **保留有效前缀**：遇到截断帧或非法 opcode，即从该点停止，之前的完整记录全部生效。
- **冷启动语义**：重启后没有存活 worker 会话，故 `active_tasks` 回放期间恒为空；
  所有 SUBMIT 过、未 DONE 的任务一律进入 `pending` 等待重新派发。
- **幂等**：重复回放同一 WAL 得到相同状态。

## 已修复的问题（相对原始源码）

编译/链接阻断：
1. `dispatch_message` 读 `frames[2]` 作 payload，但 IO 线程产出 `[identity,payload]`（分隔帧已单独消费）→ **每条消息越界/崩溃**。改为 identity=首帧、payload=末帧。
2. `IoContext.send_queue` 元素是 `vector<message_t>`，IO 线程却访问 `msg.frames.*` → 无此成员，**编译失败**。
3. `wal.cpp` 用了 `nlohmann::json` 却未 include → **编译失败**。
4. 单测调用 `wal_close()`，但该函数**从未定义** → 编译失败。已实现（并修正：flush+close 保证回放读到已提交字节）。
5. 单测既不链接 `hub.cpp` 也无 `g_state` 定义 → **链接失败**（undefined reference）。改为测试自带 `g_state`。
6. `hub.cpp` `#include "hub.h"`，该头**从未提供** → 编译失败。已移除。
7. 使用 Windows 专有 `<io.h>` / `_write` / `_fileno` / 链接 `ws2_32` → Linux 无法构建。移植为 POSIX，`ws2_32` 仅在 `if(WIN32)` 链接。
8. `%llu` 打印 `uint64_t`（LP64 下为 `unsigned long`）→ 格式不匹配。已 cast。

运行期正确性：
9. PONG 回复写死长度 11，而 `{"op":"PONG"}` 为 13 字节 → 截断成 `{"op":"PON`，非法 JSON。
10. WAL SUBMIT 回放在 `std::move(task)` 后又用 `task.task_id` → **use-after-move**，归档键为空。
11. `worker_bench` 发送裸字符串 `"WORKER_READY"`/`"TASK_DONE"`，而 Hub 按 JSON 解析 → 全部丢弃，**worker 从不注册，压测跑空**。
12. `worker_bench` 所有帧带 `SNDMORE` 且无终止帧 → 消息**永不发出**。
13. `worker_bench` 把 `ZMQ_RCVMORE` 当 recv flag 用（它是 socket option）；`setsockopt(ZMQ_IDENTITY,...)` 已废弃。
14. **原压测根本不产生负载**：只注册 worker，无任何 `SUBMIT_TASK`，Hub 全程空转。重写为真实 submit→dispatch→done 负载生成器并统计吞吐。
15. 回放语义与单测自相矛盾：原代码把「已派发未完成」放入 `active_tasks`，单测却断言其在 `pending`；且原 TEST 3 断言「截断→pending 为空」与 TEST 4「坏 opcode→保留有效帧」互斥。统一为崩溃正确语义并修正 TEST 3 断言。
16. **实跑发现的恢复缺陷**：`WORKER_READY` 被写入并回放 WAL，重启后凭空造出「幽灵空闲 worker」，任务被派发给已不存在的 identity（要等 120s busy-reaper 才重入队）。worker 存活属活连接状态，已从 WAL 移除。

此外：全面移植到现代 cppzmq API（`set(sockopt::…)` / `recv(msg, recv_flags)` / `send(msg, send_flags)` / `poll(ptr,n,timeout)`），消除废弃接口告警。

## 已知限制 / 后续方向

- 单 IO 线程 `poll`：极高连接数下为瓶颈，可拆 recv/send 双线程。
- 单全局锁：可按 worker_pool / queue / wal 拆分细化并发。
- `bench.sh` 崩溃恢复阶段的 drain 以「800ms 无新完成」为收敛条件，尾部可能残留极少量
  已派发未确认的任务（仍安全留存于 pending/WAL，不丢失）。
