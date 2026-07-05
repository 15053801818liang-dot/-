// queue_core.cpp — Windows 原生 IPC 队列（共享内存 + Mutex + Event）
// 盘古跨进程任务通道：CRC32 校验、Mutex 遗弃恢复、混合 Watchdog
//
// 编译 (Developer Command Prompt):
//   cl /LD /EHsc /O2 queue_core.cpp /Fe:queue_core.dll

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "kernel32.lib")

#define SHARED_MEM_NAME   L"Global\\Pangu_MPMC_Shared_Mem"
#define MUTEX_NAME        L"Global\\Pangu_Queue_Mutex"
#define EVENT_NAME        L"Global\\Pangu_Queue_Event"
#define QUEUE_CAPACITY    1024u
#define MAX_TASK_SIZE     4096u
#define WATCHDOG_INTERVAL 500u
#define POP_WAIT_MS       500u

typedef struct {
    uint32_t len;
    uint32_t checksum;
    uint8_t  data[MAX_TASK_SIZE];
} Task;

typedef struct {
    volatile uint32_t head;
    volatile uint32_t tail;
    volatile uint32_t recovery_count;
    Task tasks[QUEUE_CAPACITY];
    uint8_t pad[64];
} SharedQueue;

typedef enum {
    FSM_IDLE = 0,
    FSM_BUSY,
    FSM_RECOVERY_PENDING,
    FSM_ROLLBACK
} WatchdogState;

static HANDLE       g_hMutex    = NULL;
static HANDLE       g_hEvent    = NULL;
static HANDLE       g_hMapFile  = NULL;
static HANDLE       g_hWatchdog = NULL;
static volatile LONG g_watchdog_stop = 0;
static SharedQueue* g_pQueue    = NULL;
static WatchdogState g_state    = FSM_IDLE;
static int          g_is_creator = 0;

static uint32_t crc32_table[256];
static int crc32_ready = 0;

static void init_crc32_table(void) {
    if (crc32_ready) return;
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t crc = i;
        for (int j = 0; j < 8; j++) {
            crc = (crc & 1u) ? (crc >> 1) ^ 0xEDB88320UL : crc >> 1;
        }
        crc32_table[i] = crc;
    }
    crc32_ready = 1;
}

static uint32_t calc_crc32(const uint8_t* data, size_t len) {
    init_crc32_table();
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc = crc32_table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFFu;
}

static void audit_log(const char* msg) {
    OutputDebugStringA(msg);
    OutputDebugStringA("\n");
}

static int reopen_mutex(void) {
    if (g_hMutex) {
        CloseHandle(g_hMutex);
        g_hMutex = NULL;
    }
    g_hMutex = CreateMutexW(NULL, FALSE, MUTEX_NAME);
    return g_hMutex ? 0 : -1;
}

static void perform_emergency_recovery(void) {
    audit_log("[PanguQueue] RECOVERY_PENDING: mutex abandoned");
    g_state = FSM_RECOVERY_PENDING;

    if (g_pQueue) {
        /* v0: 丢弃未完成任务；生产环境从 LKP 文件恢复 head/tail */
        g_pQueue->tail = g_pQueue->head;
        InterlockedIncrement((LONG*)&g_pQueue->recovery_count);
    }

    reopen_mutex();

    if (g_hEvent) {
        ResetEvent(g_hEvent);
        SetEvent(g_hEvent);
    }

    g_state = FSM_IDLE;
    audit_log("[PanguQueue] recovery complete");
}

static int acquire_mutex(DWORD timeout_ms) {
    if (!g_hMutex) return -1;
    DWORD wait = WaitForSingleObject(g_hMutex, timeout_ms);
    if (wait == WAIT_ABANDONED) {
        perform_emergency_recovery();
        wait = WaitForSingleObject(g_hMutex, INFINITE);
    }
    if (wait == WAIT_OBJECT_0) return 0;
    if (wait == WAIT_TIMEOUT) return 1;
    return -2;
}

static DWORD WINAPI watchdog_thread(LPVOID unused) {
    (void)unused;
    while (InterlockedCompareExchange(&g_watchdog_stop, 0, 0) == 0) {
        int rc = acquire_mutex(0);
        if (rc == 0) {
            ReleaseMutex(g_hMutex);
        } else if (rc < 0) {
            perform_emergency_recovery();
        }

        if (g_pQueue && g_pQueue->tail != g_pQueue->head && g_hEvent) {
            SetEvent(g_hEvent);
        }

        Sleep(WATCHDOG_INTERVAL);
    }
    return 0;
}

static int start_watchdog(void) {
    if (g_hWatchdog) return 0;
    g_watchdog_stop = 0;
    g_hWatchdog = CreateThread(NULL, 0, watchdog_thread, NULL, 0, NULL);
    return g_hWatchdog ? 0 : -1;
}

static void stop_watchdog(void) {
    if (!g_hWatchdog) return;
    InterlockedExchange(&g_watchdog_stop, 1);
    WaitForSingleObject(g_hWatchdog, 5000);
    CloseHandle(g_hWatchdog);
    g_hWatchdog = NULL;
}

int InitQueue(void) {
    DWORD last_err;

    g_hMapFile = CreateFileMappingW(
        INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE,
        0, (DWORD)sizeof(SharedQueue), SHARED_MEM_NAME);
    if (!g_hMapFile) return -1;

    last_err = GetLastError();
    g_is_creator = (last_err != ERROR_ALREADY_EXISTS);

    g_pQueue = (SharedQueue*)MapViewOfFile(g_hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (!g_pQueue) return -2;

    if (reopen_mutex() != 0) return -3;

    g_hEvent = CreateEventW(NULL, FALSE, FALSE, EVENT_NAME);
    if (!g_hEvent) return -4;

    if (g_is_creator) {
        memset(g_pQueue, 0, sizeof(SharedQueue));
    }

    return start_watchdog();
}

static int secure_push_inner(const uint8_t* data, uint32_t len) {
    uint32_t head, next;
    Task* t;
    uint32_t crc;

    if (!g_pQueue || !data || len == 0 || len > MAX_TASK_SIZE) return -1;

    head = g_pQueue->head;
    next = (head + 1) % QUEUE_CAPACITY;
    if (next == g_pQueue->tail) return -3;

    crc = calc_crc32(data, len);
    t = &g_pQueue->tasks[head];
    t->len = len;
    t->checksum = crc;
    memcpy(t->data, data, len);

    MemoryBarrier();
    g_pQueue->head = next;
    return 0;
}

int Secure_Push(const uint8_t* data, uint32_t len) {
    int rc, push_rc;

    rc = acquire_mutex(INFINITE);
    if (rc != 0) return -2;

    push_rc = secure_push_inner(data, len);
    ReleaseMutex(g_hMutex);

    if (push_rc == 0 && g_hEvent) {
        SetEvent(g_hEvent);
    }
    return push_rc;
}

static int secure_pop_inner(uint8_t* out_buf, uint32_t* out_len) {
    uint32_t tail;
    Task* t;
    uint32_t calc;

    if (!g_pQueue || !out_buf || !out_len) return -1;

    tail = g_pQueue->tail;
    if (tail == g_pQueue->head) return 1;

    t = &g_pQueue->tasks[tail];
    if (t->len == 0 || t->len > MAX_TASK_SIZE) {
        g_pQueue->tail = (tail + 1) % QUEUE_CAPACITY;
        return -4;
    }

    calc = calc_crc32(t->data, t->len);
    if (calc != t->checksum) {
        audit_log("[PanguQueue] CRC mismatch — skipping slot");
        g_pQueue->tail = (tail + 1) % QUEUE_CAPACITY;
        return -5;
    }

    memcpy(out_buf, t->data, t->len);
    *out_len = t->len;
    g_pQueue->tail = (tail + 1) % QUEUE_CAPACITY;
    return 0;
}

int Secure_Pop(uint8_t* out_buf, uint32_t* out_len) {
    int rc, pop_rc;

    rc = acquire_mutex(INFINITE);
    if (rc != 0) return -2;

    pop_rc = secure_pop_inner(out_buf, out_len);
    ReleaseMutex(g_hMutex);
    return pop_rc;
}

int Secure_PopWait(uint8_t* out_buf, uint32_t* out_len, uint32_t wait_ms) {
    if (wait_ms == INFINITE) {
        for (;;) {
            int pop_rc = Secure_Pop(out_buf, out_len);
            if (pop_rc != 1) return pop_rc;
            if (!g_hEvent) return 1;
            WaitForSingleObject(g_hEvent, POP_WAIT_MS);
        }
    }

    DWORD deadline = GetTickCount() + wait_ms;

    for (;;) {
        int pop_rc;
        DWORD remain, slice;
        DWORD ev;

        pop_rc = Secure_Pop(out_buf, out_len);
        if (pop_rc != 1) return pop_rc;

        remain = deadline - GetTickCount();
        if ((int32_t)remain <= 0) return 1;

        slice = (remain > POP_WAIT_MS) ? POP_WAIT_MS : remain;
        if (!g_hEvent) return 1;

        ev = WaitForSingleObject(g_hEvent, slice);
        if (ev == WAIT_OBJECT_0 || ev == WAIT_TIMEOUT) {
            if ((int32_t)(deadline - GetTickCount()) <= 0) return 1;
            continue;
        }
        return -2;
    }
}

void CleanupQueue(void) {
    stop_watchdog();

    if (g_pQueue) {
        UnmapViewOfFile(g_pQueue);
        g_pQueue = NULL;
    }
    if (g_hMapFile) {
        CloseHandle(g_hMapFile);
        g_hMapFile = NULL;
    }
    if (g_hMutex) {
        CloseHandle(g_hMutex);
        g_hMutex = NULL;
    }
    if (g_hEvent) {
        CloseHandle(g_hEvent);
        g_hEvent = NULL;
    }
}

#ifdef __cplusplus
extern "C" {
#endif

__declspec(dllexport) int Py_InitQueue(void) { return InitQueue(); }
__declspec(dllexport) int Py_SecurePush(const uint8_t* data, uint32_t len) { return Secure_Push(data, len); }
__declspec(dllexport) int Py_SecurePop(uint8_t* out_buf, uint32_t* out_len) { return Secure_Pop(out_buf, out_len); }
__declspec(dllexport) int Py_SecurePopWait(uint8_t* out_buf, uint32_t* out_len, uint32_t wait_ms) {
    return Secure_PopWait(out_buf, out_len, wait_ms);
}
__declspec(dllexport) void Py_CleanupQueue(void) { CleanupQueue(); }
__declspec(dllexport) int Py_GetQueueStatus(uint32_t* head, uint32_t* tail, uint32_t* recoveries) {
    if (!g_pQueue || !head || !tail) return -1;
    *head = g_pQueue->head;
    *tail = g_pQueue->tail;
    if (recoveries) *recoveries = g_pQueue->recovery_count;
    return 0;
}
__declspec(dllexport) int Py_GetWatchdogState(void) { return (int)g_state; }

#ifdef __cplusplus
}
#endif
