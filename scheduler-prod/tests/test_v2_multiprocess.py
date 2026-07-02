#!/usr/bin/env python3
"""用户v2版测试: producer 不重试, push 失败就丢"""
import multiprocessing
import time
import sys
sys.path.insert(0, "/workspace/scheduler-prod")
from scheduler.core_v2 import SharedMemoryMPMCQueue


def producer(q_name, capacity, pid, n, results):
    q = SharedMemoryMPMCQueue(capacity=capacity, shm_name=q_name)
    pushed = 0
    for i in range(n):
        if q.push(pid * n + i):
            pushed += 1
    results[pid] = pushed


def consumer(q_name, capacity, cid, n, results):
    q = SharedMemoryMPMCQueue(capacity=capacity, shm_name=q_name)
    consumed = 0
    seen = set()
    while consumed < n:
        data = q.steal()
        if data is not None:
            seen.add(data)
            consumed += 1
    results[cid] = (consumed, len(seen))


def main():
    q = SharedMemoryMPMCQueue(capacity=2048)
    name = q.shm_name

    NP, NC = 4, 4
    PER_P = 2500
    TOTAL = NP * PER_P
    PER_C = TOTAL // NC + 10

    manager = multiprocessing.Manager()
    prod_results = manager.dict()
    cons_results = manager.dict()
    procs = []

    start = time.time()
    for i in range(NP):
        p = multiprocessing.Process(target=producer, args=(name, 2048, i, PER_P, prod_results))
        p.start()
        procs.append(p)
    for i in range(NC):
        c = multiprocessing.Process(target=consumer, args=(name, 2048, i, PER_C, cons_results))
        c.start()
        procs.append(c)
    for p in procs:
        p.join(timeout=30)
    elapsed = time.time() - start

    tp = sum(prod_results.values())
    tc = sum(r[0] for r in cons_results.values())
    tu = sum(r[1] for r in cons_results.values())

    print(f"用户v2版多进程 (producer不重试):")
    print(f"  入队: {tp} / {TOTAL} (丢失 {TOTAL - tp})")
    print(f"  出队: {tc}")
    print(f"  unique: {tu}")
    ok = tp == TOTAL and tc == TOTAL and tu == TOTAL
    print(f"  判定: {'✅ PASS' if ok else '❌ FAIL'}")

    q2 = SharedMemoryMPMCQueue(shm_name=name)
    q2.close()
    q.unlink()  # 原 owner 才能真正 unlink


if __name__ == "__main__":
    main()
