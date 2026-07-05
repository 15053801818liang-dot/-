"""Python ctypes 绑定 — Windows queue_core.dll"""

from __future__ import annotations

import ctypes
import sys
from ctypes import c_int, c_uint32, c_uint8, POINTER

MAX_TASK_SIZE = 4096


class QueueBridge:
    """跨进程任务队列桥接（仅 Windows）。"""

    def __init__(self, dll_path: str = "queue_core.dll") -> None:
        if sys.platform != "win32":
            raise RuntimeError("QueueBridge 仅支持 Windows")
        self.dll = ctypes.CDLL(dll_path)
        self._bind()

    def _bind(self) -> None:
        self.dll.Py_InitQueue.argtypes = []
        self.dll.Py_InitQueue.restype = c_int

        self.dll.Py_SecurePush.argtypes = [POINTER(c_uint8), c_uint32]
        self.dll.Py_SecurePush.restype = c_int

        self.dll.Py_SecurePop.argtypes = [ctypes.c_char_p, POINTER(c_uint32)]
        self.dll.Py_SecurePop.restype = c_int

        self.dll.Py_SecurePopWait.argtypes = [ctypes.c_char_p, POINTER(c_uint32), c_uint32]
        self.dll.Py_SecurePopWait.restype = c_int

        self.dll.Py_GetQueueStatus.argtypes = [POINTER(c_uint32), POINTER(c_uint32), POINTER(c_uint32)]
        self.dll.Py_GetQueueStatus.restype = c_int

        self.dll.Py_GetWatchdogState.argtypes = []
        self.dll.Py_GetWatchdogState.restype = c_int

        self.dll.Py_CleanupQueue.argtypes = []
        self.dll.Py_CleanupQueue.restype = None

    def init(self) -> bool:
        return self.dll.Py_InitQueue() == 0

    def push(self, data: bytes) -> int:
        """0 成功；-1 参数；-2 mutex；-3 队列满"""
        if not data:
            return -1
        buf = (c_uint8 * len(data)).from_buffer_copy(data)
        return int(self.dll.Py_SecurePush(buf, len(data)))

    def pop(self, block_ms: int = 0) -> tuple[int, bytes]:
        """返回 (code, data)。code=0 成功，1 空，<0 错误"""
        out = ctypes.create_string_buffer(MAX_TASK_SIZE)
        length = c_uint32(MAX_TASK_SIZE)

        if block_ms == 0:
            ret = self.dll.Py_SecurePop(out, ctypes.byref(length))
        else:
            wait = c_uint32(0xFFFFFFFF if block_ms < 0 else block_ms)
            ret = self.dll.Py_SecurePopWait(out, ctypes.byref(length), wait)

        if ret == 0:
            return 0, bytes(out.raw[: length.value])
        return int(ret), b""

    def status(self) -> tuple[int, int, int]:
        head = c_uint32()
        tail = c_uint32()
        recoveries = c_uint32()
        self.dll.Py_GetQueueStatus(
            ctypes.byref(head), ctypes.byref(tail), ctypes.byref(recoveries)
        )
        return head.value, tail.value, recoveries.value

    def watchdog_state(self) -> int:
        return int(self.dll.Py_GetWatchdogState())

    def cleanup(self) -> None:
        self.dll.Py_CleanupQueue()
