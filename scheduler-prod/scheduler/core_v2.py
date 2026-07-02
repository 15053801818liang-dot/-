"""Vyukov 有界 MPMC 无锁队列 + 分布式调度器 (用户v2版本)"""

import ctypes
import time
import multiprocessing.shared_memory as shm
from typing import Optional, Any
from scheduler.atomic_v2 import cas32, cas64

SLOT_SIZE = 16
SEQ_OFFSET = 0
DATA_OFFSET = 8

class SharedMemoryMPMCQueue:
    def __init__(self, capacity: int = 8192, shm_name: Optional[str] = None):
        if capacity & (capacity - 1) != 0:
            raise ValueError("capacity must be power of 2")

        self.capacity = capacity
        self.mask = capacity - 1
        self.shm_name = shm_name
        self._owned = False
        self._shm = None
        self._head_ptr = None
        self._tail_ptr = None

        total_size = 8 + capacity * SLOT_SIZE
        if shm_name is None:
            self._shm = shm.SharedMemory(create=True, size=total_size)
            self.shm_name = self._shm.name
            self._owned = True
            buf = self._shm.buf
            buf[:8] = b'\x00' * 8
            for i in range(capacity):
                self._set_seq(i, i)
                self._set_data(i, 0)
        else:
            self._shm = shm.SharedMemory(name=shm_name)
            self._owned = False

        self._bind_pointers()

    def _bind_pointers(self):
        base = self._shm.buf
        self._head_ptr = ctypes.cast(
            ctypes.addressof(ctypes.c_int32.from_buffer(base, 0)),
            ctypes.POINTER(ctypes.c_int32)
        )
        self._tail_ptr = ctypes.cast(
            ctypes.addressof(ctypes.c_int32.from_buffer(base, 4)),
            ctypes.POINTER(ctypes.c_int32)
        )

    def _seq_ptr(self, idx: int):
        offset = 8 + idx * SLOT_SIZE + SEQ_OFFSET
        return ctypes.cast(
            ctypes.addressof(ctypes.c_int64.from_buffer(self._shm.buf, offset)),
            ctypes.POINTER(ctypes.c_int64)
        )

    def _data_ptr(self, idx: int):
        offset = 8 + idx * SLOT_SIZE + DATA_OFFSET
        return ctypes.cast(
            ctypes.addressof(ctypes.c_int64.from_buffer(self._shm.buf, offset)),
            ctypes.POINTER(ctypes.c_int64)
        )

    def _set_seq(self, idx: int, val: int):
        self._seq_ptr(idx).contents.value = val

    def _set_data(self, idx: int, val: int):
        self._data_ptr(idx).contents.value = val

    def push(self, data: int) -> bool:
        while True:
            tail = self._tail_ptr.contents.value
            if tail - self._head_ptr.contents.value >= self.capacity:
                return False
            idx = tail & self.mask
            seq = self._seq_ptr(idx).contents.value
            if seq != tail:
                return False
            if not cas32(self._tail_ptr, tail, tail + 1):
                continue
            self._set_data(idx, data)
            self._set_seq(idx, tail + 1)
            return True

    def steal(self) -> Optional[int]:
        while True:
            head = self._head_ptr.contents.value
            if head >= self._tail_ptr.contents.value:
                return None
            idx = head & self.mask
            seq = self._seq_ptr(idx).contents.value
            if seq != head + 1:
                return None
            if not cas32(self._head_ptr, head, head + 1):
                continue
            data = self._data_ptr(idx).contents.value
            self._set_seq(idx, head + self.capacity)
            return data

    def size(self) -> int:
        return self._tail_ptr.contents.value - self._head_ptr.contents.value

    def stats(self) -> dict:
        return {
            "head": self._head_ptr.contents.value,
            "tail": self._tail_ptr.contents.value,
            "size": self.size(),
            "capacity": self.capacity,
        }

    def close(self):
        if self._shm:
            self._head_ptr = None
            self._tail_ptr = None
            self._shm.close()
            self._shm = None

    def unlink(self):
        if self._owned and self._shm:
            self._shm.unlink()
            self._owned = False
