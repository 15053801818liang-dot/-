"""业务客户端 SDK"""

from typing import Optional
from scheduler.core import SharedMemoryMPMCQueue


class SchedulerClient:
    def __init__(self, shm_name: str):
        self.shm_name = shm_name
        self._queue = None

    def _ensure_queue(self):
        if self._queue is None:
            self._queue = SharedMemoryMPMCQueue(shm_name=self.shm_name)
        return self._queue

    def steal(self) -> Optional[int]:
        q = self._ensure_queue()
        return q.steal()

    def close(self):
        if self._queue:
            self._queue.close()
            self._queue = None
