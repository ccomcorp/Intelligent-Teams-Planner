"""
Monitoring and logging implementation for MCPO Proxy
Task 6: Monitoring and logging implementation
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import defaultdict, deque
from dataclasses import dataclass, field

import structlog
from fastapi import Request, Response

try:
    from .mcp_client import MCPClient
    from .cache import ProxyCache
except ImportError:
    # For testing
    from mcp_client import MCPClient
    from cache import ProxyCache

logger = structlog.get_logger(__name__)


@dataclass
class RequestMetrics:
    """Metrics for individual requests"""
    request_id: str
    method: str
    path: str
    start_time: float
    end_time: Optional[float] = None
    status_code: Optional[int] = None
    response_size: Optional[int] = None
    user_id: Optional[str] = None
    tool_name: Optional[str] = None
    error_type: Optional[str] = None
    mcp_request_time: Optional[float] = None
    translation_time: Optional[float] = None


@dataclass
class SystemMetrics:
    """System-wide metrics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    active_connections: int = 0
    mcp_server_health: str = "unknown"
    cache_hit_rate: float = 0.0
    error_rate: float = 0.0
    uptime: float = 0.0
    memory_usage: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsCollector:
    """Collect and aggregate performance metrics"""

    def __init__(self):
        self.start_time = time.time()
        self.request_metrics: Dict[str, RequestMetrics] = {}
        self.recent_requests: deque = deque(maxlen=1000)  # Keep last 1000 requests
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.tool_usage_counts: Dict[str, int] = defaultdict(int)
        self.response_times: List[float] = []
        self.system_metrics = SystemMetrics()

    def start_request_tracking(self, request: Request) -> str:
        """Start tracking a new request"""
        request_id = f"req_{uuid.uuid4().hex[:8]}"

        metrics = RequestMetrics(
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            start_time=time.time(),
            user_id=getattr(request.state, 'user_id', None)
        )

        self.request_metrics[request_id] = metrics
        logger.debug("Started request tracking", request_id=request_id, path=metrics.path)

        return request_id

    def end_request_tracking(
        self,
        request_id: str,
        response: Response,
        tool_name: str = None,
        error_type: str = None
    ):
        """Complete request tracking"""
        if request_id not in self.request_metrics:
            logger.warning("Request ID not found for tracking", request_id=request_id)
            return

        metrics = self.request_metrics[request_id]
        metrics.end_time = time.time()
        metrics.status_code = response.status_code
        metrics.tool_name = tool_name
        metrics.error_type = error_type

        # Calculate response time
        response_time = metrics.end_time - metrics.start_time
        metrics.response_size = int(response.headers.get("content-length", 0))

        # Update aggregated metrics
        self.recent_requests.append(metrics)
        self.response_times.append(response_time)

        # Keep only recent response times for average calculation
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-1000:]

        # Update counters
        self.system_metrics.total_requests += 1

        if 200 <= response.status_code < 300:
            self.system_metrics.successful_requests += 1
        else:
            self.system_metrics.failed_requests += 1
            if error_type:
                self.error_counts[error_type] += 1

        if tool_name:
            self.tool_usage_counts[tool_name] += 1

        # Update average response time
        if self.response_times:
            self.system_metrics.average_response_time = sum(self.response_times) / len(self.response_times)

        # Calculate error rate
        if self.system_metrics.total_requests > 0:
            self.system_metrics.error_rate = (
                self.system_metrics.failed_requests / self.system_metrics.total_requests
            ) * 100

        # Update system metrics timestamp
        self.system_metrics.last_updated = datetime.now(timezone.utc)

        logger.info(
            "Request completed",
            request_id=request_id,
            response_time=response_time,
            status_code=response.status_code,
            tool_name=tool_name
        )

        # Clean up old request metrics
        del self.request_metrics[request_id]

    def record_mcp_request_time(self, request_id: str, mcp_time: float):
        """Record MCP server request time"""
        if request_id in self.request_metrics:
            self.request_metrics[request_id].mcp_request_time = mcp_time

    def record_translation_time(self, request_id: str, translation_time: float):
        """Record protocol translation time"""
        if request_id in self.request_metrics:
            self.request_metrics[request_id].translation_time = translation_time

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        uptime = time.time() - self.start_time
        self.system_metrics.uptime = uptime

        return {
            "system_metrics": {
                "total_requests": self.system_metrics.total_requests,
                "successful_requests": self.system_metrics.successful_requests,
                "failed_requests": self.system_metrics.failed_requests,
                "error_rate_percent": round(self.system_metrics.error_rate, 2),
                "average_response_time_ms": round(self.system_metrics.average_response_time * 1000, 2),
                "uptime_seconds": round(uptime, 2),
                "requests_per_second": round(
                    self.system_metrics.total_requests / max(uptime, 1), 2
                ),
                "mcp_server_health": self.system_metrics.mcp_server_health,
                "cache_hit_rate_percent": round(self.system_metrics.cache_hit_rate, 2)
            },
            "tool_usage": dict(self.tool_usage_counts),
            "error_breakdown": dict(self.error_counts),
            "recent_activity": {
                "last_10_requests": [
                    {
                        "path": req.path,
                        "method": req.method,
                        "status_code": req.status_code,
                        "response_time_ms": round(
                            (req.end_time - req.start_time) * 1000, 2
                        ) if req.end_time else None,
                        "tool_name": req.tool_name,
                        "timestamp": datetime.fromtimestamp(req.start_time, timezone.utc).isoformat()
                    }
                    for req in list(self.recent_requests)[-10:]
                ]
            },
            "performance": {
                "response_time_percentiles": self._calculate_percentiles(),
                "active_requests": len(self.request_metrics)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _calculate_percentiles(self) -> Dict[str, float]:
        """Calculate response time percentiles"""
        if not self.response_times:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0}

        sorted_times = sorted(self.response_times)
        length = len(sorted_times)

        return {
            "p50": round(sorted_times[int(length * 0.5)] * 1000, 2),
            "p90": round(sorted_times[int(length * 0.9)] * 1000, 2),
            "p95": round(sorted_times[int(length * 0.95)] * 1000, 2),
            "p99": round(sorted_times[int(length * 0.99)] * 1000, 2)
        }


class HealthChecker:
    """Monitor health of system dependencies"""

    def __init__(self, mcp_client: MCPClient, cache: ProxyCache):
        self.mcp_client = mcp_client
        self.cache = cache
        self.health_history: deque = deque(maxlen=100)
        self.last_check_time = 0
        self.check_interval = 30  # seconds

    async def check_system_health(self, force: bool = False) -> Dict[str, Any]:
        """Check health of all system components"""
        current_time = time.time()

        # Use cached result if recent check (unless forced)
        if not force and (current_time - self.last_check_time) < self.check_interval:
            if self.health_history:
                return self.health_history[-1]

        health_result = {
            "overall_status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {},
            "uptime": current_time - metrics_collector.start_time,
            "checks_performed": len(self.health_history) + 1
        }

        # Check MCP server
        try:
            mcp_status = await self.mcp_client.health_check()
            health_result["components"]["mcp_server"] = {
                "status": mcp_status,
                "response_time": None  # Could add timing here
            }
            if mcp_status != "healthy":
                health_result["overall_status"] = "degraded"
        except Exception as e:
            health_result["components"]["mcp_server"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_result["overall_status"] = "unhealthy"

        # Check cache
        try:
            cache_status = await self.cache.health_check()
            health_result["components"]["cache"] = {
                "status": cache_status,
                "response_time": None
            }
            if cache_status != "healthy":
                health_result["overall_status"] = "degraded"
        except Exception as e:
            health_result["components"]["cache"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            if health_result["overall_status"] != "unhealthy":
                health_result["overall_status"] = "degraded"

        # Check internal metrics
        try:
            internal_health = self._check_internal_health()
            health_result["components"]["internal"] = internal_health
            if internal_health["status"] != "healthy":
                health_result["overall_status"] = "degraded"
        except Exception as e:
            health_result["components"]["internal"] = {
                "status": "unhealthy",
                "error": str(e)
            }

        # Store result
        self.health_history.append(health_result)
        self.last_check_time = current_time

        # Update metrics collector
        metrics_collector.system_metrics.mcp_server_health = health_result["components"]["mcp_server"]["status"]

        logger.info("Health check completed", overall_status=health_result["overall_status"])

        return health_result

    def _check_internal_health(self) -> Dict[str, Any]:
        """Check internal system health indicators"""
        try:
            # Check error rate
            error_rate = metrics_collector.system_metrics.error_rate
            avg_response_time = metrics_collector.system_metrics.average_response_time

            status = "healthy"
            issues = []

            if error_rate > 50:  # 50% error rate
                status = "unhealthy"
                issues.append(f"High error rate: {error_rate}%")
            elif error_rate > 10:  # 10% error rate
                status = "degraded"
                issues.append(f"Elevated error rate: {error_rate}%")

            if avg_response_time > 5:  # 5 seconds
                status = "degraded"
                issues.append(f"High response time: {avg_response_time}s")

            return {
                "status": status,
                "error_rate_percent": round(error_rate, 2),
                "average_response_time": round(avg_response_time, 2),
                "total_requests": metrics_collector.system_metrics.total_requests,
                "issues": issues
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    def get_health_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent health check history"""
        return list(self.health_history)[-limit:]


class AlertManager:
    """Manage alerts and notifications for system issues"""

    def __init__(self):
        self.alert_rules = {
            "high_error_rate": {"threshold": 10, "window": 300},  # 10% in 5 minutes
            "slow_response": {"threshold": 2, "window": 300},     # 2s average in 5 minutes
            "mcp_server_down": {"threshold": 1, "window": 60},    # MCP down for 1 minute
            "high_request_rate": {"threshold": 1000, "window": 60}  # 1000 req/min
        }
        self.active_alerts: Dict[str, Dict[str, Any]] = {}
        self.alert_history: deque = deque(maxlen=1000)

    def check_alert_conditions(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check if any alert conditions are met"""
        new_alerts = []

        # Check error rate
        error_rate = metrics["system_metrics"]["error_rate_percent"]
        if error_rate > self.alert_rules["high_error_rate"]["threshold"]:
            alert = self._create_alert(
                "high_error_rate",
                f"Error rate is {error_rate}% (threshold: {self.alert_rules['high_error_rate']['threshold']}%)",
                "warning"
            )
            new_alerts.append(alert)

        # Check response time
        avg_response_time = metrics["system_metrics"]["average_response_time_ms"] / 1000
        if avg_response_time > self.alert_rules["slow_response"]["threshold"]:
            alert = self._create_alert(
                "slow_response",
                f"Average response time is {avg_response_time}s "
                f"(threshold: {self.alert_rules['slow_response']['threshold']}s)",
                "warning"
            )
            new_alerts.append(alert)

        # Check MCP server health
        mcp_health = metrics["system_metrics"]["mcp_server_health"]
        if mcp_health != "healthy":
            alert = self._create_alert(
                "mcp_server_down",
                f"MCP server health is {mcp_health}",
                "critical"
            )
            new_alerts.append(alert)

        # Store new alerts
        for alert in new_alerts:
            self.active_alerts[alert["id"]] = alert
            self.alert_history.append(alert)

        return new_alerts

    def _create_alert(self, alert_type: str, message: str, severity: str) -> Dict[str, Any]:
        """Create a new alert"""
        return {
            "id": f"{alert_type}_{int(time.time())}",
            "type": alert_type,
            "severity": severity,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False
        }

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an active alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id]["acknowledged"] = True
            self.active_alerts[alert_id]["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return list(self.active_alerts.values())


# Global instances
metrics_collector = MetricsCollector()
alert_manager = AlertManager()


class CorrelationIDMiddleware:
    """Middleware to add correlation IDs to requests for tracing"""

    @staticmethod
    def add_correlation_id(request: Request) -> str:
        """Add correlation ID to request"""
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = f"mcpo_{uuid.uuid4().hex[:12]}"

        # Store in request state for use in handlers
        request.state.correlation_id = correlation_id
        return correlation_id

    @staticmethod
    def get_correlation_id(request: Request) -> str:
        """Get correlation ID from request"""
        return getattr(request.state, 'correlation_id', f"mcpo_{uuid.uuid4().hex[:12]}")


def setup_structured_logging():
    """Configure enhanced structured logging"""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True
    )
