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

### 规模压测（真跑，找瓶颈）

原文声称「2000w / 5 万 Worker 已验证」。实测在本机（4 核 / 16GB / `ulimit -n` 硬上限
**4096**，无权提高）把真实天花板压了出来：

| requested | connected | completed | throughput |
|---|---|---|---|
| 500  | 500/500   | 50000/50000 | **50k tasks/s** |
| 1000 | 1000/1000 | 50000/50000 | 45k tasks/s |
| 2000 | 2000/2000 | 50000/50000 | 38k tasks/s |
| 2400 | 2283/2400 | 超时（部分连接建不起来） | — |
| 3000 | 2551/3000 | 超时 | — |
| 4000 | 2391/4000 | 超时 | — |

结论：

- **硬天花板 ≈ 2000 并发 worker / 进程**。libzmq 每条 DEALER 连接在 Linux 上约占 **2 个 fd**
  （1 个 eventfd signaler + 1 个 TCP fd），4096 / 2 ≈ 2000。超过后触发 `EMFILE (errno 24)`。
  **5 万在本机物理上不可能**（约差 25 倍），需要 `ulimit -n` 提到 ~120k 且多机分摊。
- **吞吐是调度器瓶颈，不是 worker 瓶颈**：单锁单调度线程串行派发，worker 越多不增吞吐；
  相反 50k→38k 略降，因为更多 socket 带来更多 `poll`/上下文切换开销（4 核）。
- **FD 耗尽下优雅降级**：加固后，撞上限的 worker 线程与 Hub 的 IO 线程捕获 `EMFILE/ENFILE`
  退出/继续，而不是 `terminate` 崩溃（加固前两端都会 abort，见修复项 17）。

### 调度器优化：空闲 worker O(1) 索引（先量后优化）

原实现 `has_idle()` / `find_and_mark_idle()` 是对 worker map 的 O(n) 线性扫描。
先加计数器实测，再决定是否优化：

- 2000 worker × 50000 任务下，扫描累计 **49.4M** 次迭代。虽然短路（命中第一个空闲即返回），
  但 `has_idle()` 在 CV 谓词里每次唤醒/复查都调用，saturation 突发时会扫得很深。
- 引入 `unordered_set<identity> idle_ids_`（不变量：`id ∈ idle_ids_ ⟺ 存在且空闲`），
  `has_idle()`→`!empty()`、`find_and_mark_idle()`→取集合首元素，均降为 **O(1)**。

A/B（best-of-3，`--no-flush`）：

| workers | 优化前 O(n) | 优化后 O(1) | 扫描迭代 |
|---|---|---|---|
| 500  | 45.3k tasks/s | **51.9k** | 22.4M → **0** |
| 2000 | 38.8k tasks/s | **48.0k** | 49.4M → **0** |

结论：2000 worker 吞吐 **+24%**，且吞吐随 worker 数下降的曲线**基本被抹平**（2000w 追平 500w）。
即"吞吐随规模下降"主要就是这个 O(n) 扫描，而非单锁本身。**这也说明在做高风险的拆锁之前，
应先量出瓶颈**——本例数据表明单锁尚未成为墙，下一个真实开销更可能是每任务的 JSON `dump`/`parse`
与 WAL 写入，或单 IO 线程。

### per-task 耗时打点（`--profile`，先量后优化）

`hub --profile` 开启后，退出时打印每任务各段耗时（`json parse/dump`、`wal_write`、`zmq enqueue`）。
默认关闭，生产路径零负担。2000 worker × 50000 任务实测：

| section | flush OFF (ns/task) | flush ON (ns/task) |
|---|---|---|
| json_parse | 2010 | 2102 |
| json_dump | 1891 | 1869 |
| wal_write | 1341 | **3408** |
| zmq_enqueue | 863* | 1158* |
| **SUM/task** | **6104** | **8537** |
| 吞吐 | 36.9k/s | 33.3k/s |

\* zmq_enqueue 被 `clock_gettime` 开销放大约 2×。

结论：
1. **JSON parse+dump ≈ 3.9μs/task = 调度线程 CPU 的 64%**（flush-off）。二进制序列化可削这块。
2. **WAL `fflush` 是被抓到的吞吐杀手**：flush ON 使 `wal_write` 1341→3408 ns/task，吞吐 −10%。
   元凶是 `wal_write` 在 **`g_state.mutex` 临界区内**做 fflush syscall，把 DONE 流水线串行化。
   → 下一步高确定性优化：把 flush 挪出全局锁 / 批量刷盘（注意崩溃丢失窗口的权衡）。
3. SUM/task 仅 6.1μs，而 wall ≈ 27μs/task —— 大量 wall 时间在**未打点的单 IO 线程 poll/transport**
   与 worker 往返上。选项「IO 线程拆分」打的是这块，需单独 profile io_thread 才能定论。

### IO 线程 profile + 瓶颈定位（把「拆 IO 线程」证伪了）

对 io_thread 加 `io_poll/io_send/io_recv` 打点，并测 poll 超时敏感度与 per-thread CPU（2000w）：

- **IO 线程只有 22% 忙**（`(send+recv)/(poll+send+recv)`），78% 在 poll 等待。
- **poll 超时越小吞吐越低**（best-of-3）：10ms=47.6k → 5ms=45.7k → 1ms=41.7k → 0ms(busy-spin)=37.4k。
  降低 poll 反而更差——说明 send **并没有**被 poll 卡死；busy-spin 抢 CPU 且加剧 `g_state.mutex`
  竞争（recv 入队要拿这把锁），把调度线程拖慢了。
- **没有任何资源饱和**：稳态只用 **1.6 / 4 核**；per-thread：`scheduler 0.82` / `io_thread 0.29` /
  `ZMQbg/IO/0 0.16` 核——**最忙的线程也就 0.82 核，没打满**。

结论（重要，且**修正了我自己之前偏向拆 IO 的判断**）：

> 系统是 **latency/handoff-bound**，不是 CPU-bound 也不是单线程饱和。核有富余、无线程打满，
> 吞吐却卡在 ~35–47k/s（同机负载生成器 + 2000 条本地 TCP 连接的测量混淆占主导，run 间方差也大）。
> **因此 IO 线程拆分、WAL 写线程、JSON 二进制序列化在当前测试台上都不成立**——它们都不打向饱和资源，
> 而 poll-ms 扫描已实测「加 IO 活动反而更差」。要真做吞吐优化，得先移除混淆（负载生成器搬到别的机器），
> 否则就是过早优化。当前更该做的是**生产健壮性（fd 背压）**，而不是追这台机器上并不受资源限制的吞吐。

诊断开关：`hub --profile`（打点）、`hub --poll-ms N`（IO poll 超时，默认 10）。

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

17. **FD 耗尽下崩溃（规模压测发现）**：连接数逼近 `ulimit -n` 时，libzmq 的 `poll`/`send`
    抛出 `EMFILE`，原代码未捕获 → worker 端与 **Hub** 双双 `terminate` abort（压测中 Hub 直接挂掉、
    无 METRICS 输出）。已加固：worker 线程遇 `EMFILE/ENFILE` 退出该线程、Hub IO 线程捕获并继续
    服务已建立的连接，实现优雅降级。

此外：全面移植到现代 cppzmq API（`set(sockopt::…)` / `recv(msg, recv_flags)` / `send(msg, send_flags)` / `poll(ptr,n,timeout)`），消除废弃接口告警。

## 已知限制 / 后续方向

- ✅ 空闲 worker O(1) 索引（已做，见上，2000w +24%）。
- 单 IO 线程 `poll`：极高连接数下为瓶颈，可拆 recv/send 双线程。
- 单全局锁：可按 worker_pool / queue / wal 拆分——但实测单锁尚非瓶颈，
  拆锁前应先量（JSON/WAL 每任务开销可能更值得先优化）。
- `bench.sh` 崩溃恢复阶段的 drain 以「800ms 无新完成」为收敛条件，尾部可能残留极少量
  已派发未确认的任务（仍安全留存于 pending/WAL，不丢失）。
