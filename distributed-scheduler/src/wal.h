#pragma once
#include "protocol.h"

// WAL 接口（C-ABI 风格，无回调，直接操作 g_state）
void wal_set_path(const char* path);
void wal_set_flush(bool enabled);   // 关闭后 wal_write 不再每条 fflush（压测用）
int  wal_write(WalOp op, const char* task_id, const char* data, const char* worker_id);
int  wal_replay();
int  wal_truncate();
void wal_flush();
void wal_close();   // 关闭当前写句柄（下次 write 会重新打开）
