"""
Performance monitoring and metrics collection for Graph API operations
Story 2.1 Task 8: Performance Optimization and Connection Management
"""

import time
import asyncio
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import structlog

# Optional monitoring dependencies
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

logger = structlog.get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a single operation"""
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    status: str = "pending"  # pending, success, error
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self, status: str = "success", error_type: Optional[str] = None) -> None:
        """Mark operation as complete and calculate duration"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.status = status
        self.error_type = error_type


@dataclass
class ConnectionPoolStats:
    """Connection pool statistics"""
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    max_connections: int = 100
    connection_reuse_count: int = 0
    connection_creation_count: int = 0
    connection_errors: int = 0


class PerformanceMonitor:
    """
    Performance monitoring system for Graph API operations
    Tracks response times, throughput, error rates, and connection pool usage
    """

    def __init__(self,
                 enable_prometheus: bool = True,
                 enable_opentelemetry: bool = True,
                 metrics_retention_minutes: int = 60):
        self.enable_prometheus = enable_prometheus and PROMETHEUS_AVAILABLE
        self.enable_opentelemetry = enable_opentelemetry and OPENTELEMETRY_AVAILABLE
        self.metrics_retention_minutes = metrics_retention_minutes

        # In-memory metrics storage
        self._metrics_history: deque = deque(maxlen=10000)
        self._operation_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "total_duration": 0.0,
            "error_count": 0,
            "last_execution": None
        })

        # Connection pool tracking
        self._connection_stats = ConnectionPoolStats()

        # Thread-safe access
        self._lock = threading.Lock()

        # Initialize Prometheus metrics if available
        if self.enable_prometheus:
            self._init_prometheus_metrics()

        # Initialize OpenTelemetry tracer if available
        if self.enable_opentelemetry:
            self._tracer = trace.get_tracer(__name__)

        logger.info("Performance monitor initialized",
                   prometheus=self.enable_prometheus,
                   opentelemetry=self.enable_opentelemetry)

    def _init_prometheus_metrics(self) -> None:
        """Initialize Prometheus metrics"""
        self.prometheus_request_duration = Histogram(
            'graph_api_request_duration_seconds',
            'Duration of Graph API requests',
            ['operation', 'status', 'endpoint']
        )

        self.prometheus_request_total = Counter(
            'graph_api_requests_total',
            'Total Graph API requests',
            ['operation', 'status', 'endpoint']
        )

        self.prometheus_active_connections = Gauge(
            'graph_api_active_connections',
            'Number of active HTTP connections'
        )

        self.prometheus_connection_pool_size = Gauge(
            'graph_api_connection_pool_size',
            'Current connection pool size'
        )

        self.prometheus_error_rate = Gauge(
            'graph_api_error_rate',
            'Current error rate percentage',
            ['operation']
        )

    @asynccontextmanager
    async def track_operation(self, operation_name: str, metadata: Dict[str, Any] = None):
        """Context manager to track operation performance"""
        metadata = metadata or {}
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            start_time=time.time(),
            metadata=metadata
        )

        # Start OpenTelemetry span if available
        span = None
        if self.enable_opentelemetry:
            span = self._tracer.start_span(operation_name)
            span.set_attributes(metadata)

        try:
            yield metrics
            metrics.complete("success")

            if span:
                span.set_status(Status(StatusCode.OK))

        except Exception as e:
            error_type = type(e).__name__
            metrics.complete("error", error_type)

            if span:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

            raise

        finally:
            # Record metrics
            self._record_metrics(metrics)

            if span:
                span.end()

    def _record_metrics(self, metrics: PerformanceMetrics) -> None:
        """Record performance metrics"""
        with self._lock:
            # Add to history
            self._metrics_history.append(metrics)

            # Update operation statistics
            stats = self._operation_stats[metrics.operation_name]
            stats["count"] += 1
            stats["total_duration"] += metrics.duration or 0
            stats["last_execution"] = datetime.now(timezone.utc)

            if metrics.status == "error":
                stats["error_count"] += 1

        # Update Prometheus metrics if available
        if self.enable_prometheus and metrics.duration:
            endpoint = metrics.metadata.get("endpoint", "unknown")

            self.prometheus_request_duration.labels(
                operation=metrics.operation_name,
                status=metrics.status,
                endpoint=endpoint
            ).observe(metrics.duration)

            self.prometheus_request_total.labels(
                operation=metrics.operation_name,
                status=metrics.status,
                endpoint=endpoint
            ).inc()

            # Update error rate
            stats = self._operation_stats[metrics.operation_name]
            if stats["count"] > 0:
                error_rate = (stats["error_count"] / stats["count"]) * 100
                self.prometheus_error_rate.labels(
                    operation=metrics.operation_name
                ).set(error_rate)

    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """Get statistics for a specific operation"""
        with self._lock:
            stats = self._operation_stats[operation_name].copy()

        if stats["count"] > 0:
            stats["average_duration"] = stats["total_duration"] / stats["count"]
            stats["error_rate"] = (stats["error_count"] / stats["count"]) * 100
        else:
            stats["average_duration"] = 0.0
            stats["error_rate"] = 0.0

        return stats

    def get_all_operation_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all operations"""
        return {
            operation: self.get_operation_stats(operation)
            for operation in self._operation_stats.keys()
        }

    def get_recent_metrics(self, minutes: int = 5) -> List[PerformanceMetrics]:
        """Get metrics from the last N minutes"""
        cutoff_time = time.time() - (minutes * 60)

        with self._lock:
            return [
                metric for metric in self._metrics_history
                if metric.start_time >= cutoff_time
            ]

    def update_connection_stats(self,
                               active: int = None,
                               idle: int = None,
                               total: int = None,
                               reuse_count: int = None,
                               creation_count: int = None,
                               error_count: int = None) -> None:
        """Update connection pool statistics"""
        with self._lock:
            if active is not None:
                self._connection_stats.active_connections = active
            if idle is not None:
                self._connection_stats.idle_connections = idle
            if total is not None:
                self._connection_stats.total_connections = total
            if reuse_count is not None:
                self._connection_stats.connection_reuse_count = reuse_count
            if creation_count is not None:
                self._connection_stats.connection_creation_count = creation_count
            if error_count is not None:
                self._connection_stats.connection_errors = error_count

        # Update Prometheus metrics
        if self.enable_prometheus:
            self.prometheus_active_connections.set(
                self._connection_stats.active_connections
            )
            self.prometheus_connection_pool_size.set(
                self._connection_stats.total_connections
            )

    def get_connection_stats(self) -> ConnectionPoolStats:
        """Get current connection pool statistics"""
        with self._lock:
            return ConnectionPoolStats(
                active_connections=self._connection_stats.active_connections,
                idle_connections=self._connection_stats.idle_connections,
                total_connections=self._connection_stats.total_connections,
                max_connections=self._connection_stats.max_connections,
                connection_reuse_count=self._connection_stats.connection_reuse_count,
                connection_creation_count=self._connection_stats.connection_creation_count,
                connection_errors=self._connection_stats.connection_errors
            )

    def calculate_percentiles(self, operation_name: str, percentiles: List[float] = None) -> Dict[str, float]:
        """Calculate response time percentiles for an operation"""
        if percentiles is None:
            percentiles = [50.0, 95.0, 99.0]

        recent_metrics = self.get_recent_metrics(minutes=self.metrics_retention_minutes)
        operation_durations = [
            m.duration for m in recent_metrics
            if m.operation_name == operation_name and m.duration is not None
        ]

        if not operation_durations:
            return {f"p{p}": 0.0 for p in percentiles}

        operation_durations.sort()
        result = {}

        for p in percentiles:
            index = int((p / 100.0) * len(operation_durations))
            if index >= len(operation_durations):
                index = len(operation_durations) - 1
            result[f"p{p}"] = operation_durations[index]

        return result

    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health metrics"""
        recent_metrics = self.get_recent_metrics(minutes=5)

        if not recent_metrics:
            return {
                "status": "unknown",
                "total_requests": 0,
                "error_rate": 0.0,
                "average_response_time": 0.0
            }

        total_requests = len(recent_metrics)
        error_count = sum(1 for m in recent_metrics if m.status == "error")
        error_rate = (error_count / total_requests) * 100 if total_requests > 0 else 0.0

        valid_durations = [m.duration for m in recent_metrics if m.duration is not None]
        avg_response_time = sum(valid_durations) / len(valid_durations) if valid_durations else 0.0

        # Determine health status
        status = "healthy"
        if error_rate > 10.0:
            status = "unhealthy"
        elif error_rate > 5.0 or avg_response_time > 2.0:
            status = "degraded"

        return {
            "status": status,
            "total_requests": total_requests,
            "error_rate": error_rate,
            "average_response_time": avg_response_time,
            "connection_stats": self.get_connection_stats().__dict__
        }

    async def cleanup_old_metrics(self) -> None:
        """Clean up old metrics to prevent memory growth"""
        cutoff_time = time.time() - (self.metrics_retention_minutes * 60)

        with self._lock:
            # Remove old metrics from history
            while (self._metrics_history and
                   self._metrics_history[0].start_time < cutoff_time):
                self._metrics_history.popleft()

        logger.debug("Cleaned up old performance metrics")

    def start_prometheus_server(self, port: int = 8000) -> None:
        """Start Prometheus metrics server"""
        if self.enable_prometheus:
            try:
                start_http_server(port)
                logger.info("Prometheus metrics server started", port=port)
            except Exception as e:
                logger.error("Failed to start Prometheus server", error=str(e))
        else:
            logger.warning("Prometheus not available - metrics server not started")


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get or create global performance monitor instance"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def track_operation(operation_name: str, metadata: Dict[str, Any] = None):
    """Decorator to track function performance"""
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                monitor = get_performance_monitor()
                async with monitor.track_operation(operation_name, metadata):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                monitor = get_performance_monitor()
                # For sync functions, we can't use async context manager
                metrics = PerformanceMetrics(
                    operation_name=operation_name,
                    start_time=time.time(),
                    metadata=metadata or {}
                )
                try:
                    result = func(*args, **kwargs)
                    metrics.complete("success")
                    return result
                except Exception as e:
                    metrics.complete("error", type(e).__name__)
                    raise
                finally:
                    monitor._record_metrics(metrics)
            return sync_wrapper
    return decorator