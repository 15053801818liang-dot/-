import os
import time
import json
import struct
import ctypes
import uuid
import multiprocessing
import multiprocessing.shared_memory as shm
import threading
import logging
from typing import Optional, Any, Dict
from scheduler.atomic import cas_int

logger = logging.getLogger(__name__)

class SharedMemoryMPMCQueue:
    HEADER_SIZE = 8

    def __init__(self, capacity: int = 8192, shm_name: Optional[str] = None):
        self.capacity = capacity
        self.shm_name = shm_name
        self._owned = False
        self._shm = None
        self._head_ptr = None
        self._tail_ptr = None
        self._slots = None

        if shm_name is None:
            size = self.HEADER_SIZE + capacity * 8
            self._shm = shm.SharedMemory(create=True, size=size)
            self.shm_name = self._shm.name
            self._owned = True
            self._shm.buf[:] = b'\x00' * size
        else:
            self._shm = shm.SharedMemory(name=shm_name)
            self._owned = False

        self._bind_pointers()

    def _bind_pointers(self):
        base = self._shm.buf
        head_addr = ctypes.addressof(ctypes.c_int.from_buffer(base, 0))
        self._head_ptr = ctypes.cast(head_addr, ctypes.POINTER(ctypes.c_int))
        tail_addr = ctypes.addressof(ctypes.c_int.from_buffer(base, 4))
        self._tail_ptr = ctypes.cast(tail_addr, ctypes.POINTER(ctypes.c_int))
        self._slots = base[8:]

    def _slot_ptr(self, idx: int):
        offset = idx * 8
        addr = ctypes.addressof(ctypes.c_longlong.from_buffer(self._slots, offset))
        return ctypes.cast(addr, ctypes.POINTER(ctypes.c_longlong))

    def push(self, task_id: int) -> bool:
        spin = 0
        while spin < 2000:
            h = self._head_ptr.contents.value
            t = self._tail_ptr.contents.value
            if (t - h) >= self.capacity:
                return False
            self._slot_ptr(t & (self.capacity - 1)).contents.value = task_id
            if cas_int(self._tail_ptr, t, t + 1):
                if self._head_ptr.contents.value <= t + 1:
                    return True
                else:
                    self._tail_ptr.contents.value = t
                    return False
            spin += 1
            if spin % 50 == 0:
                time.sleep(0)
        return False

    def steal(self) -> Optional[int]:
        spin = 0
        while spin < 2000:
            h = self._head_ptr.contents.value
            t = self._tail_ptr.contents.value
            if h >= t:
                return None
            task = self._slot_ptr(h & (self.capacity - 1)).contents.value
            if cas_int(self._head_ptr, h, h + 1):
                return task
            spin += 1
            if spin % 50 == 0:
                time.sleep(0)
        return None

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
            self._shm.close()

    def unlink(self):
        if self._owned and self._shm:
            self._shm.unlink()
            self._owned = False
