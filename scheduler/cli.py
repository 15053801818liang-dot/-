"""命令行入口"""

import argparse
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Distributed Scheduler")
    parser.add_argument("--node-id", required=True, help="Node ID")
    parser.add_argument("--lease-key", required=True, help="etcd lease key")
    parser.add_argument("--etcd-endpoint", default="localhost:2379", help="etcd endpoint")
    parser.add_argument("--capacity", type=int, default=8192, help="Queue capacity (power of 2)")
    args = parser.parse_args()

    from scheduler.core import SharedMemoryMPMCQueue
    from scheduler.lease import EtcdLeaseManager

    q = SharedMemoryMPMCQueue(capacity=args.capacity)
    logger.info(f"Queue created: shm_name={q.shm_name}, capacity={args.capacity}")

    mgr = EtcdLeaseManager(node_id=args.node_id, lease_key=args.lease_key)
    mgr.connect(endpoint=args.etcd_endpoint)

    @mgr.on("acquired")
    def on_acquired(token):
        logger.info(f"Leader acquired, fencing token={token}")

    @mgr.on("lost")
    def on_lost(reason):
        logger.warning(f"Leader lost: {reason}")

    mgr.start()
    logger.info("Scheduler running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(5)
            logger.info(f"Queue stats: {q.stats()}")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        mgr.stop()
        q.unlink()
        q.close()


if __name__ == "__main__":
    main()
