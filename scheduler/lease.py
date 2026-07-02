"""etcd 租约管理器（真实抢主 + 心跳 + Fencing Token）"""

import threading
import time
import logging
from scheduler.exceptions import NotLeaderError

logger = logging.getLogger(__name__)


class EtcdLeaseManager:
    def __init__(self, node_id: str, lease_key: str, ttl_sec: int = 10, heartbeat_ms: int = 1500):
        self.node_id = node_id
        self.lease_key = lease_key
        self.ttl_sec = ttl_sec
        self.heartbeat_interval = heartbeat_ms / 1000.0

        self.client = None
        self.lease = None
        self.active_token = None
        self.current_epoch = 0
        self._stop_flag = False
        self._lock = threading.Lock()
        self._callbacks = {"acquired": [], "lost": []}
        self._connected = False

    def connect(self, endpoint="localhost:2379"):
        import etcd3
        host, port = endpoint.split(":")
        self.client = etcd3.client(host=host, port=int(port))
        self._connected = True

    def on(self, event: str, callback):
        if event not in self._callbacks:
            raise ValueError(f"Unknown event: {event}")
        self._callbacks[event].append(callback)

    def start(self):
        if not self._connected:
            raise RuntimeError("Not connected to etcd")
        self._stop_flag = False
        while not self._stop_flag:
            try:
                self._acquire_leader()
                self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self._heartbeat_thread.start()
                return
            except Exception as e:
                logger.error(f"Acquire failed: {e}, retrying...")
                time.sleep(1)

    def _acquire_leader(self):
        lease = self.client.lease(self.ttl_sec)
        existing_value, _ = self.client.get(self.lease_key)

        new_token = 1
        if existing_value:
            parts = existing_value.decode().split(":")
            if len(parts) == 2:
                try:
                    new_token = int(parts[1]) + 1
                except ValueError:
                    pass

        value = f"{self.node_id}:{new_token}".encode()
        success, _ = self.client.transaction(
            compare=[self.client.transactions.value(self.lease_key) == b''],
            success=[self.client.transactions.put(self.lease_key, value, lease=lease)],
            failure=[]
        )

        if not success:
            lease.revoke()
            raise RuntimeError("Concurrent creation")

        self.lease = lease
        self.active_token = new_token
        self.current_epoch += 1
        logger.info(f"Leader acquired: {self.node_id}, token={new_token}")
        for cb in self._callbacks["acquired"]:
            cb(self.active_token)

    def _heartbeat_loop(self):
        while not self._stop_flag:
            try:
                if self.lease is None:
                    break
                self.lease.refresh()
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                self._lose_leader("heartbeat_failed")
                break

    def _lose_leader(self, reason: str):
        with self._lock:
            if self.active_token is None:
                return
            logger.warning(f"Lost leader: {reason}")
            self.active_token = None
            self.current_epoch += 1
            if self.lease:
                self.lease.revoke()
                self.lease = None
            for cb in self._callbacks["lost"]:
                cb(reason)
            if not self._stop_flag:
                threading.Thread(target=self.start, daemon=True).start()

    def assert_active_leader_and_get_fence(self) -> int:
        with self._lock:
            if self.active_token is None:
                value, _ = self.client.get(self.lease_key)
                if value:
                    parts = value.decode().split(":")
                    if len(parts) == 2 and parts[0] == self.node_id:
                        self.active_token = int(parts[1])
                        return self.active_token
                raise NotLeaderError("Not the current leader")
            return self.active_token

    def stop(self):
        self._stop_flag = True
        self._lose_leader("manual_stop")
        if self.client:
            self.client.close()
            self._connected = False
