"""
Vyukov bounded MPMC queue — sequence-based 无锁队列
内存布局: [head:i32][tail:i32][pad:8][seq0:i64][data0:i64][seq1:i64][data1:i64]...
每个槽 = sequence(8B) + data(8B) = 16B

push 三步:
  1. CAS 预留 tail 槽位 (seq 从 t 变 t+1 表示"被生产者占用")
  2. 写入 data
  3. 写入 seq = t+1 表示"数据就绪"

steal 三步:
  1. 读 head 槽的 seq,确认 == h+1 表示"数据就绪可消费"
  2. CAS head 从 h 推进到 h+1
  3. 写入 seq = h+capacity 表示"槽位回收,可被复用"
"""

import ctypes
import time
import multiprocessing.shared_memory as shm
from typing import Optional
from scheduler.atomic import cas_int


class SharedMemoryMPMCQueue:
    HEADER_SIZE = 16          # head(4) + tail(4) + pad(8)
    SLOT_SIZE = 16            # seq(8) + data(8)
    SEQ_OFFSET = 0
    DATA_OFFSET = 8

    def __init__(self, capacity: int = 8192, shm_name: Optional[str] = None):
        if capacity <= 0 or (capacity & (capacity - 1)) != 0:
            raise ValueError("capacity must be power of 2")
        self.capacity = capacity
        self.mask = capacity - 1
        self.shm_name = shm_name
        self._owned = False
        self._shm = None
        self._head_ptr = None
        self._tail_ptr = None
        self._base = None       # memoryview of slots region
        self._base_addr = 0     # absolute address of slots region

        total = self.HEADER_SIZE + capacity * self.SLOT_SIZE
        if shm_name is None:
            self._shm = shm.SharedMemory(create=True, size=total)
            self.shm_name = self._shm.name
            self._owned = True
            self._shm.buf[:] = b'\x00' * total
        else:
            self._shm = shm.SharedMemory(name=shm_name)
            self._owned = False

        self._bind_pointers()
        if shm_name is None:
            self._init_sequences()

    def _init_sequences(self):
        """初始化每个槽的 sequence = 槽索引 (slot[0].seq=0, slot[1].seq=1, ...)"""
        for i in range(self.capacity):
            addr = self._slot_addr(i) + self.SEQ_OFFSET
            ctypes.c_int64.from_address(addr).value = i

    def _bind_pointers(self):
        buf = self._shm.buf
        self._head_ptr = ctypes.cast(
            ctypes.addressof(ctypes.c_int.from_buffer(buf, 0)),
            ctypes.POINTER(ctypes.c_int))
        self._tail_ptr = ctypes.cast(
            ctypes.addressof(ctypes.c_int.from_buffer(buf, 4)),
            ctypes.POINTER(ctypes.c_int))
        # slots 区域的绝对地址 (用于 ctypes.from_address)
        buf_addr = ctypes.addressof(ctypes.c_char.from_buffer(buf, 0))
        self._base_addr = buf_addr + self.HEADER_SIZE
        self._base = buf[self.HEADER_SIZE:]

    def _slot_addr(self, idx: int) -> int:
        """返回槽 idx 的绝对地址"""
        return self._base_addr + idx * self.SLOT_SIZE

    def _read_seq(self, idx: int) -> int:
        return ctypes.c_int64.from_address(self._slot_addr(idx) + self.SEQ_OFFSET).value

    def _write_seq(self, idx: int, val: int):
        ctypes.c_int64.from_address(self._slot_addr(idx) + self.SEQ_OFFSET).value = val

    def _read_data(self, idx: int) -> int:
        return ctypes.c_int64.from_address(self._slot_addr(idx) + self.DATA_OFFSET).value

    def _write_data(self, idx: int, val: int):
        ctypes.c_int64.from_address(self._slot_addr(idx) + self.DATA_OFFSET).value = val

    def push(self, task_id: int) -> bool:
        """
        三步无锁 push:
        1. 读 tail,定位槽 = tail & mask
        2. 读槽 seq:
           - seq == tail: 槽空闲,可预留 → CAS seq: tail → tail+1
           - seq < tail:  槽被消费者标记回收了但 seq 滞后 → CAS 尝试
           - seq > tail:  队列满 (生产者已预留但未就绪) → return False
        3. 写 data,写 seq = tail+1 (就绪标记)
        """
        tail = self._tail_ptr.contents.value
        spins = 0
        while spins < 2000:
            idx = tail & self.mask
            seq = self._read_seq(idx)
            diff = seq - tail
            if diff == 0:
                # 槽空闲且就绪,尝试预留
                if cas_int(self._tail_ptr, tail, tail + 1):
                    break
                tail = self._tail_ptr.contents.value
            elif diff < 0:
                # 槽有数据未消费 (满) 或消费者已回收 seq 但未追上 tail
                # 需要确认:如果 head 已经推进到这个槽之后,说明消费者回收了
                # 此时 seq 会被设为 head+capacity,而 head+capacity > tail (因为 size<capacity)
                # 所以 diff < 0 只在队列真正满时出现
                return False
            else:
                # diff > 0: 生产者已预留但未完成
                return False
            spins += 1
            if spins % 50 == 0:
                time.sleep(0)
        else:
            return False

        # 预留成功:写数据 + 标记就绪
        self._write_data(idx, task_id)
        self._write_seq(idx, tail + 1)  # seq = tail+1 表示就绪
        return True

    def steal(self) -> Optional[int]:
        """
        三步无锁 steal:
        1. 读 head,定位槽 = head & mask
        2. 读槽 seq:
           - seq == head+1: 数据就绪,可消费 → CAS head: head → head+1
           - seq < head+1:  队列空 → return None
           - seq > head+1:  生产者预留了但数据未就绪 → return None
        3. 读 data,写 seq = head+capacity (回收槽位)
        """
        head = self._head_ptr.contents.value
        spins = 0
        while spins < 2000:
            idx = head & self.mask
            seq = self._read_seq(idx)
            diff = seq - (head + 1)
            if diff == 0:
                # 就绪,尝试消费
                if cas_int(self._head_ptr, head, head + 1):
                    break
                head = self._head_ptr.contents.value
            elif diff < 0:
                # 队列空
                return None
            else:
                # 生产者预留了但数据未就绪
                return None
            spins += 1
            if spins % 50 == 0:
                time.sleep(0)
        else:
            return None

        # 消费成功:读数据 + 回收槽位
        data = self._read_data(idx)
        self._write_seq(idx, head + self.capacity)  # 回收,seq 跳到下一轮
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
        # 先释放 ctypes 指针引用,否则 mmap 无法关闭
        self._head_ptr = None
        self._tail_ptr = None
        self._base = None
        if self._shm:
            try:
                self._shm.close()
            except BufferError:
                pass  # 指针引用已被 GC,忽略

    def unlink(self):
        if self._owned and self._shm:
            try:
                self._shm.unlink()
            except Exception:
                pass
            self._owned = False
