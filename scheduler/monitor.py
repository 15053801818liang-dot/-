"""Prometheus 监控指标"""

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    push_total = Counter("scheduler_push_total", "Total push operations")
    steal_total = Counter("scheduler_steal_total", "Total steal operations")
    queue_size = Gauge("scheduler_queue_size", "Current queue size")
    latency = Histogram("scheduler_latency_seconds", "Operation latency")
except ImportError:
    pass
