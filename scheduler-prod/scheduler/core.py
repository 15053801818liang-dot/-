import os
import sys
import time
import json
import struct
import uuid
import signal
import atexit
import logging
import multiprocessing
import multiprocessing.shared_memory as shm
from typing import Optional, Any, Dict, Callable
from dataclasses import dataclass

@dataclass
class PayloadRef:
    shm_name: str
    size: int

class SharedMemoryPool:
    HEADER_FORMAT = '<II'
    HEADER_SIZE = 8
    MAGIC = 0xDEADBEEF

    @staticmethod
    def allocate_and_write(payload: Any) -> PayloadRef:
        payload_bytes = json.dumps(payload).encode('utf-8')
        size = len(payload_bytes)
        total_size = SharedMemoryPool.HEADER_SIZE + size
        shm_name = f"payload_{uuid.uuid4().hex[:16]}"
        shm_block = shm.SharedMemory(create=True, size=total_size)
        try:
            struct.pack_into('<II', shm_block.buf, 0, SharedMemoryPool.MAGIC, size)
            shm_block.buf[SharedMemoryPool.HEADER_SIZE:SharedMemoryPool.HEADER_SIZE+size] = payload_bytes
        except Exception as e:
            shm_block.unlink()
            shm_block.close()
            raise RuntimeError(f"写入共享内存失败: {e}")
        return PayloadRef(shm_name=shm_name, size=size)

    @staticmethod
    def read_and_free(ref: PayloadRef) -> Any:
        try:
            shm_block = shm.SharedMemory(name=ref.shm_name)
            magic, size = struct.unpack_from('<II', shm_block.buf, 0)
            if magic != SharedMemoryPool.MAGIC:
                raise ValueError(f"共享内存块损坏: {ref.shm_name}")
            payload_bytes = bytes(shm_block.buf[SharedMemoryPool.HEADER_SIZE:SharedMemoryPool.HEADER_SIZE+size])
            return json.loads(payload_bytes.decode('utf-8'))
        finally:
            try:
                shm_block = shm.SharedMemory(name=ref.shm_name)
                shm_block.unlink()
                shm_block.close()
            except FileNotFoundError:
                pass

class SharedMemoryMPMCQueue:
    def __init__(self, capacity: int = 2048, shm_name: Optional[str] = None):
        self.capacity = capacity
        self.shm_name = shm_name
        self._owned = False
        self._shm = None
        self._head_ptr = None
        self._tail_ptr = None

        if shm_name is None:
            size = 8 + capacity * 8
            self._shm = shm.SharedMemory(create=True, size=size)
            self.shm_name = self._shm.name
            self._owned = True
            ctypes.memset(self._shm.buf, 0, size)
        else:
            self._shm = shm.SharedMemory(name=shm_name)
            self._owned = False

        self._bind_pointers()

    def _bind_pointers(self):
        import ctypes
        base = self._shm.buf
        self._head_ptr = ctypes.cast(ctypes.addressof(ctypes.c_int.from_buffer(base, 0)), ctypes.POINTER(ctypes.c_int))
        self._tail_ptr = ctypes.cast(ctypes.addressof(ctypes.c_int.from_buffer(base, 4)), ctypes.POINTER(ctypes.c_int))

    def _buffer_slot(self, idx: int):
        import ctypes
        offset = 8 + idx * 8
        return ctypes.cast(ctypes.addressof(ctypes.c_longlong.from_buffer(self._shm.buf, offset)), ctypes.POINTER(ctypes.c_longlong))

    def _cas_int(self, ptr, expected, new):
        import ctypes
        if ptr.contents.value == expected:
            ptr.contents.value = new
            return True
        return False

    def push(self, task_id: int) -> bool:
        spin = 0
        while spin < 2000:
            h = self._head_ptr.contents.value
            t = self._tail_ptr.contents.value
            if (t - h) >= self.capacity:
                return False
            self._buffer_slot(t & (self.capacity - 1)).contents.value = task_id
            if self._cas_int(self._tail_ptr, t, t + 1):
                if self._head_ptr.contents.value <= t + 1:
                    return True
                self._tail_ptr.value = t
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
            task = self._buffer_slot(h & (self.capacity - 1)).contents.value
            if self._cas_int(self._head_ptr, h, h + 1):
                return task
            spin += 1
            if spin % 50 == 0:
                time.sleep(0)
        return None

    def size(self) -> int:
        return self._tail_ptr.contents.value - self._head_ptr.contents.value

    def stats(self) -> dict:
        return {"head": self._head_ptr.contents.value, "tail": self._tail_ptr.contents.value, "size": self.size()}

    def close(self):
        if self._shm:
            self._shm.close()

    def unlink(self):
        if self._owned and self._shm:
            self._shm.unlink()
            self._owned = False

class DistributedLeaseManagerV2:
    def __init__(self, node_id: str, lease_key: str, ttl_sec: int, heartbeat_ms: int):
        self.node_id = node_id
        self.lease_key = lease_key
        self.ttl_sec = ttl_sec
        self.heartbeat_ms = heartbeat_ms
        self.storage_rpc = None
        self.current_epoch = 0
        self.active_token = None
        self.last_heartbeat = 0
        self._callbacks = {"acquired": [], "lost": []}
        self._running = False

    def on(self, event: str, callback):
        if event == "leader_acquired":
            self._callbacks["acquired"].append(callback)
        elif event == "leader_lost":
            self._callbacks["lost"].append(callback)

    def start(self):
        self._running = True
        self._simulate_acquire()

    def _simulate_acquire(self):
        import random
        self.active_token = random.randint(1, 100)
        self.current_epoch += 1
        for cb in self._callbacks["acquired"]:
            cb(self.active_token)

    def assert_active_leader_and_get_fence(self) -> int:
        if self.active_token is None:
            raise RuntimeError("Not leader")
        return self.active_token

    def stop(self):
        self._running = False
        self.active_token = None
        self.current_epoch += 1
        for cb in self._callbacks["lost"]:
            cb("stopped")

class DistributedSchedulerV3:
    def __init__(self, node_id: str, lease_key: str, storage_rpc: Any,
                 queue_capacity: int = 8192, lease_ttl_sec: int = 10, heartbeat_ms: int = 1500):
        self.node_id = node_id
        self.lease_manager = DistributedLeaseManagerV2(node_id, lease_key, lease_ttl_sec, heartbeat_ms)
        self.lease_manager.storage_rpc = storage_rpc
        self._queue: Optional[SharedMemoryMPMCQueue] = None
        self._queue_capacity = queue_capacity
        self._shm_name: Optional[str] = None
        self._is_leader = False
        self._current_epoch = 0
        self._stop_flag = False
        self._payload_store = {}

        self.lease_manager.on("leader_acquired", self._on_become_leader)
        self.lease_manager.on("leader_lost", self._on_lose_leader)
        atexit.register(self._cleanup)

    def _cleanup(self):
        if self._queue and self._is_leader:
            try:
                self._queue.unlink()
            except:
                pass

    def _on_become_leader(self, token: int):
        self._current_epoch = self.lease_manager.current_epoch
        self._is_leader = True
        if self._queue is None:
            self._queue = SharedMemoryMPMCQueue(capacity=self._queue_capacity)
            self._shm_name = self._queue.shm_name
            print(f"[Leader] 创建队列: {self._shm_name}")

    def _on_lose_leader(self, reason: str):
        self._is_leader = False
        self._current_epoch = self.lease_manager.current_epoch
        if self._queue:
            self._queue.close()

    def start(self):
        self.lease_manager.start()

    def stop(self):
        self._stop_flag = True
        self.lease_manager.stop()
        if self._queue and self._is_leader:
            self._queue.unlink()
            self._queue = None

    def submit_task(self, task_type: str, payload: Any) -> bool:
        if not self._is_leader:
            raise RuntimeError("Not leader")
        try:
            token = self.lease_manager.assert_active_leader_and_get_fence()
        except Exception as e:
            self._on_lose_leader(f"assert failed: {e}")
            raise RuntimeError(f"Lease失效: {e}")

        task_id = len(self._payload_store)
        self._payload_store[task_id] = {"type": task_type, "payload": payload, "token": token}
        return self._queue.push(task_id)

    def get_queue_name(self) -> Optional[str]:
        return self._shm_name

    def is_leader(self) -> bool:
        return self._is_leader

    def stats(self) -> dict:
        qstats = self._queue.stats() if self._queue else {"head": -1, "tail": -1, "size": -1}
        return {"node_id": self.node_id, "is_leader": self._is_leader, "epoch": self._current_epoch,
                "queue": qstats, "shm_name": self._shm_name, "task_count": len(self._payload_store)}

    def get_payload(self, task_id: int) -> Optional[Any]:
        return self._payload_store.get(task_id)
