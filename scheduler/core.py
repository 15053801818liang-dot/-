"""Vyukov 有界 MPMC 无锁队列 + 分布式调度器"""

import ctypes
import struct
import time
import multiprocessing.shared_memory as shm
from typing import Optional, Any
from scheduler.atomic import cas32, cas64

# 槽位布局: sequence(8B) + data(8B)
SLOT_SIZE = 16
SEQ_OFFSET = 0
DATA_OFFSET = 8

# 共享内存头部布局: head(4) + tail(4) + capacity(4) + reserved(4) = 16 bytes
HEADER_SIZE = 16


class SharedMemoryMPMCQueue:
    """
    Vyukov 有界 MPMC 无锁队列，基于 SharedMemory + 硬件 CAS。
    支持跨进程，零拷贝，无锁。
    要求 capacity 为 2 的幂。
    capacity 存储在共享内存头部，跨进程 attach 时自动读取。
    """

    def __init__(self, capacity: int = 8192, shm_name: Optional[str] = None):
        self.shm_name = shm_name
        self._owned = False
        self._shm = None
        self._head_ptr = None
        self._tail_ptr = None

        if shm_name is None:
            if capacity & (capacity - 1) != 0:
                raise ValueError("capacity must be power of 2")
            total_size = HEADER_SIZE + capacity * SLOT_SIZE
            self._shm = shm.SharedMemory(create=True, size=total_size)
            self.shm_name = self._shm.name
            self._owned = True
            buf = self._shm.buf
            buf[:HEADER_SIZE] = b'\x00' * HEADER_SIZE
            # store capacity in header at offset 8
            struct.pack_into('I', buf, 8, capacity)
            for i in range(capacity):
                self._set_seq(i, i)
                self._set_data(i, 0)
        else:
            self._shm = shm.SharedMemory(name=shm_name)
            self._owned = False
            # read capacity from header
            capacity = struct.unpack_from('I', self._shm.buf, 8)[0]

        self.capacity = capacity
        self.mask = capacity - 1
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

    def _slot_ptr(self, idx: int):
        offset = HEADER_SIZE + idx * SLOT_SIZE
        return self._shm.buf[offset:offset + SLOT_SIZE]

    def _seq_ptr(self, idx: int):
        offset = HEADER_SIZE + idx * SLOT_SIZE + SEQ_OFFSET
        return ctypes.cast(
            ctypes.addressof(ctypes.c_int64.from_buffer(self._shm.buf, offset)),
            ctypes.POINTER(ctypes.c_int64)
        )

    def _data_ptr(self, idx: int):
        offset = HEADER_SIZE + idx * SLOT_SIZE + DATA_OFFSET
        return ctypes.cast(
            ctypes.addressof(ctypes.c_int64.from_buffer(self._shm.buf, offset)),
            ctypes.POINTER(ctypes.c_int64)
        )

    def _set_seq(self, idx: int, val: int):
        self._seq_ptr(idx).contents.value = val

    def _set_data(self, idx: int, val: int):
        self._data_ptr(idx).contents.value = val

    def _cas_seq(self, idx: int, expected: int, new: int) -> bool:
        return cas64(self._seq_ptr(idx), expected, new)

    def push(self, data: int) -> bool:
        """入队，返回 True 成功，False 队列满"""
        while True:
            tail = self._tail_ptr.contents.value
            if tail - self._head_ptr.contents.value >= self.capacity:
                return False  # 队列已满

            idx = tail & self.mask
            seq = self._seq_ptr(idx).contents.value

            if seq != tail:
                # tail 已被其他 producer 抢占，重新读取后重试
                continue

            if not cas32(self._tail_ptr, tail, tail + 1):
                continue  # CAS 竞争失败，重试

            self._set_data(idx, data)
            self._set_seq(idx, tail + 1)
            return True

    def steal(self) -> Optional[int]:
        """出队，返回数据或 None"""
        while True:
            head = self._head_ptr.contents.value
            if head >= self._tail_ptr.contents.value:
                return None  # 队列为空

            idx = head & self.mask
            seq = self._seq_ptr(idx).contents.value
            if seq != head + 1:
                # producer 已写入 tail 但尚未写完 seq，短暂自旋等待
                continue

            if not cas32(self._head_ptr, head, head + 1):
                continue  # CAS 竞争失败，重试

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


# Stub for DistributedSchedulerV3 referenced in __init__.py
class DistributedSchedulerV3:
    pass
