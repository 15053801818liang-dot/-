"""DistributedSchedulerV3 单元测试"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from scheduler.core import DistributedSchedulerV3
from scheduler.exceptions import NotLeaderError


def test_push_steal_without_lease_manager():
    """未配置 lease_manager 时，push/steal 直接操作队列（单机模式）。"""
    sched = DistributedSchedulerV3(capacity=16)
    try:
        assert sched.push(42) is True
        assert sched.size() == 1
        assert sched.steal() == 42
        assert sched.size() == 0
    finally:
        sched.unlink()
        sched.close()


def test_push_requires_leadership():
    """配置了 lease_manager 但当前不是 Leader 时，push 应抛出 NotLeaderError。"""

    class FakeLeaseManager:
        def assert_active_leader_and_get_fence(self):
            raise NotLeaderError("Not the current leader")

        def start(self):
            pass

        def stop(self):
            pass

    sched = DistributedSchedulerV3(capacity=16, lease_manager=FakeLeaseManager())
    try:
        with pytest.raises(NotLeaderError):
            sched.push(1)
        # steal 不需要 Leader 身份，队列为空返回 None
        assert sched.steal() is None
    finally:
        sched.unlink()
        sched.close()


def test_push_succeeds_when_leader():
    """当前节点是 Leader 时，push 正常写入队列。"""

    class FakeLeaseManager:
        def __init__(self):
            self.token = 7

        def assert_active_leader_and_get_fence(self):
            return self.token

        def start(self):
            pass

        def stop(self):
            pass

    sched = DistributedSchedulerV3(capacity=16, lease_manager=FakeLeaseManager())
    try:
        assert sched.push(99) is True
        assert sched.steal() == 99
    finally:
        sched.unlink()
        sched.close()


def test_stats_and_shm_name():
    sched = DistributedSchedulerV3(capacity=32)
    try:
        assert sched.shm_name == sched.queue.shm_name
        stats = sched.stats()
        assert stats["capacity"] == 32
        assert stats["size"] == 0
    finally:
        sched.unlink()
        sched.close()
