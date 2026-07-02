"""etcd 存储适配器"""

import logging

logger = logging.getLogger(__name__)


class EtcdStorage:
    def __init__(self, endpoint="localhost:2379"):
        self.endpoint = endpoint
        self.client = None

    def connect(self):
        import etcd3
        host, port = self.endpoint.split(":")
        self.client = etcd3.client(host=host, port=int(port))

    def put(self, key: str, value: str):
        self.client.put(key, value)

    def get(self, key: str):
        value, _ = self.client.get(key)
        return value.decode() if value else None

    def close(self):
        if self.client:
            self.client.close()
