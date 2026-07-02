#!/usr/bin/env python3
"""多进程压测: 4 生产者进程 + 4 消费者进程, 跨进程 SharedMemory + CAS"""
import multiprocessing
import time
import sys
sys.path.insert(0, "/workspace/scheduler-prod")
from scheduler.core import SharedMemoryMPMCQueue


def producer(shm_name, capacity, pid, count, result_dict):
    q = SharedMemoryMPMCQueue(capacity=capacity, shm_name=shm_name)
    pushed = 0
    i = 0
    while i < count:
        if q.push(pid * 1000000 + i):
            pushed += 1
            i += 1
        else:
            time.sleep(0.0001)
    result_dict[pid] = pushed


def consumer(shm_name, capacity, cid, count, result_list):
    q = SharedMemoryMPMCQueue(capacity=capacity, shm_name=shm_name)
    consumed = 0
    local = []
    while consumed < count:
        t = q.steal()
        if t is not None:
            consumed += 1
            local.append(t)
        else:
            time.sleep(0.0001)
    result_list.extend(local)


def main():
    capacity = 4096
    NP, NC = 4, 4
    TOTAL = 10000
    PER_P = TOTAL // NP
    PER_C = TOTAL // NC

    q = SharedMemoryMPMCQueue(capacity=capacity)
    shm_name = q.shm_name
    print(f"队列创建: {shm_name}")

    manager = multiprocessing.Manager()
    result_dict = manager.dict()
    result_list = manager.list()

    procs = []
    for i in range(NP):
        p = multiprocessing.Process(
            target=producer, args=(shm_name, capacity, i, PER_P, result_dict))
        procs.append(p)
    for i in range(NC):
        c = multiprocessing.Process(
            target=consumer, args=(shm_name, capacity, i, PER_C, result_list))
        procs.append(c)

    start = time.time()
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    elapsed = time.time() - start

    total_pushed = sum(result_dict.values())
    total_consumed = len(result_list)
    stats = q.stats()
    unique = len(set(result_list))

    print(f"\n4P/4C 多进程压测 (跨进程 shm + CAS):")
    print(f"  耗时: {elapsed:.2f}s | 吞吐: {TOTAL/elapsed:.0f} ops/s")
    print(f"  入队: {total_pushed} / {TOTAL}")
    print(f"  出队: {total_consumed}")
    print(f"  队列残留: {stats['size']}")
    print(f"  unique: {unique} / {TOTAL}")

    ok = (total_pushed == TOTAL and total_consumed == TOTAL
          and stats['size'] == 0 and unique == TOTAL)
    print(f"  判定: {'✅ PASS — 跨进程无锁队列验证通过' if ok else '❌ FAIL'}")

    q.unlink()


if __name__ == "__main__":
    main()
