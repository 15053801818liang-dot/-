"""跨进程 MPMC 队列压测"""

import multiprocessing
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scheduler.core import SharedMemoryMPMCQueue


def producer(q_name, pid, n, results):
    q = SharedMemoryMPMCQueue(shm_name=q_name)
    pushed = 0
    for i in range(n):
        if q.push(pid * n + i):
            pushed += 1
    results[pid] = pushed
    q.close()


def consumer(q_name, cid, n, results):
    q = SharedMemoryMPMCQueue(shm_name=q_name)
    consumed = 0
    seen = set()
    deadline = time.time() + 30
    while consumed < n and time.time() < deadline:
        data = q.steal()
        if data is not None:
            seen.add(data)
            consumed += 1
    results[cid] = (consumed, len(seen))
    q.close()


def test_multiprocess():
    q = SharedMemoryMPMCQueue(capacity=2048)
    name = q.shm_name
    q.close()

    NUM_P = 4
    NUM_C = 4
    PER_P = 2500
    TOTAL = NUM_P * PER_P
    PER_C = TOTAL // NUM_C + 10

    manager = multiprocessing.Manager()
    prod_results = manager.dict()
    cons_results = manager.dict()
    procs = []

    start = time.time()

    for i in range(NUM_P):
        p = multiprocessing.Process(target=producer, args=(name, i, PER_P, prod_results))
        p.start()
        procs.append(p)

    for i in range(NUM_C):
        c = multiprocessing.Process(target=consumer, args=(name, i, PER_C, cons_results))
        c.start()
        procs.append(c)

    for p in procs:
        p.join(timeout=60)

    elapsed = time.time() - start

    total_pushed = sum(prod_results.values())
    total_consumed = sum(r[0] for r in cons_results.values())
    total_unique = sum(r[1] for r in cons_results.values())

    # 清理
    try:
        q2 = SharedMemoryMPMCQueue(shm_name=name)
        q2.unlink()
        q2.close()
    except Exception:
        pass

    print(f"耗时: {elapsed:.2f}s | 吞吐: {total_pushed/elapsed:.0f} ops/s")
    print(f"入队: {total_pushed} / {TOTAL}")
    print(f"出队: {total_consumed}")
    print(f"unique: {total_unique} / {TOTAL}")
    passed = total_pushed == TOTAL
    print(f"判定: {'✅ PASS' if passed else '❌ FAIL'}")
    return passed


if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)
    result = test_multiprocess()
    sys.exit(0 if result else 1)
