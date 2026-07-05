# 盘古 Windows IPC 队列

跨进程 MPMC 任务通道（Mutex 串行化环形队列 + 共享内存 + Event）。

## IPC 三元组

| 对象 | 名称 |
|------|------|
| 共享内存 | `Global\Pangu_MPMC_Shared_Mem` |
| Mutex | `Global\Pangu_Queue_Mutex` |
| Event | `Global\Pangu_Queue_Event` |

## 特性

- CRC32 校验（`Task.checksum`）
- Mutex 遗弃检测 + 紧急恢复（`Perform_Emergency_Recovery`）
- 混合 Watchdog：500ms 轮询 + Event 唤醒消费者（`Secure_PopWait`）
- Python 绑定：`queue_bridge.py`

## 编译（Developer Command Prompt）

```cmd
cd 盘古\native\windows
cl /LD /EHsc /O2 queue_core.cpp /Fe:queue_core.dll
```

## Python 冒烟

```cmd
python test_queue_bridge.py
```

## 返回值

| 函数 | 返回 |
|------|------|
| `Secure_Push` | 0 成功；-1 参数；-2 mutex；-3 满 |
| `Secure_Pop` | 0 成功；1 空；-4 损坏；-5 CRC 失败 |
| `Secure_PopWait` | 同 Pop，空队列时等待 Event（500ms 切片） |

## 生产扩展

- LKP checkpoint 文件：每次 Push/Pop 异步写 head/tail
- 审计：ReportEvent / 文件日志（当前 `OutputDebugString`）

## 注意

Cloud/Linux 环境**不能编译 DLL**；请在 Windows 本机编译后测试。
