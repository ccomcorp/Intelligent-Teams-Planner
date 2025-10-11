"""
Sync Health Monitoring and Recovery Mechanisms
Story 8.1 Task 2.4: Advanced sync health monitoring and automatic recovery

Implements comprehensive health monitoring, alerting, and automatic recovery
for Microsoft Planner synchronization operations.
"""

import asyncio
import json
import uuid
from typing import Dict, List, Any, Optional, Set, Callable
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
import structlog

from ..database import Database
from ..cache import CacheService
from .status_tracker import SyncStatusTracker, SyncHealth, SyncStatus, SyncType
from .conflict_resolver import ConflictManager

logger = structlog.get_logger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthCheckType(str, Enum):
    """Types of health checks"""

    SYNC_PERFORMANCE = "sync_performance"
    RESOURCE_INTEGRITY = "resource_integrity"
    CACHE_HEALTH = "cache_health"
    DATABASE_CONNECTION = "database_connection"
    API_CONNECTIVITY = "api_connectivity"
    CONFLICT_RESOLUTION = "conflict_resolution"
    WEBHOOK_STATUS = "webhook_status"


class RecoveryAction(str, Enum):
    """Types of recovery actions"""

    RETRY_OPERATION = "retry_operation"
    RESET_CACHE = "reset_cache"
    FORCE_FULL_SYNC = "force_full_sync"
    RESTART_WEBHOOKS = "restart_webhooks"
    RESOLVE_CONFLICTS = "resolve_conflicts"
    SCALE_RESOURCES = "scale_resources"
    NOTIFY_ADMIN = "notify_admin"


@dataclass
class HealthCheck:
    """Individual health check definition"""

    check_id: str
    check_type: HealthCheckType
    name: str
    description: str
    interval_seconds: int
    timeout_seconds: int
    enabled: bool = True
    critical: bool = False
    recovery_actions: List[RecoveryAction] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResult:
    """Result of a health check"""

    check_id: str
    status: str  # "healthy", "warning", "error", "critical"
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_ms: Optional[float] = None
    recovery_suggestions: List[RecoveryAction] = field(default_factory=list)


@dataclass
class Alert:
    """Health monitoring alert"""

    alert_id: str
    level: AlertLevel
    check_type: HealthCheckType
    title: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    recovery_actions_taken: List[str] = field(default_factory=list)
    auto_resolved: bool = False


@dataclass
class RecoveryOperation:
    """Automatic recovery operation"""

    operation_id: str
    action: RecoveryAction
    trigger_alert_id: str
    status: str  # "pending", "running", "completed", "failed"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    recovery_data: Dict[str, Any] = field(default_factory=dict)


class HealthMonitor:
    """Main health monitoring and recovery system"""

    def __init__(
        self,
        database: Database,
        cache_service: CacheService,
        status_tracker: SyncStatusTracker,
        conflict_manager: ConflictManager,
        graph_client: Any = None
    ):
        self.database = database
        self.cache_service = cache_service
        self.status_tracker = status_tracker
        self.conflict_manager = conflict_manager
        self.graph_client = graph_client

        # Health check registry
        self.health_checks: Dict[str, HealthCheck] = {}
        self.check_results: Dict[str, HealthResult] = {}

        # Alert management
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_handlers: Dict[AlertLevel, List[Callable]] = {
            AlertLevel.INFO: [],
            AlertLevel.WARNING: [],
            AlertLevel.ERROR: [],
            AlertLevel.CRITICAL: []
        }

        # Recovery management
        self.active_recoveries: Dict[str, RecoveryOperation] = {}
        self.recovery_handlers: Dict[RecoveryAction, Callable] = {}

        # Background tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None

        # Configuration
        self.monitoring_enabled = os.getenv("SYNC_MONITORING_ENABLED", "true").lower() == "true"
        self.auto_recovery_enabled = os.getenv("SYNC_AUTO_RECOVERY_ENABLED", "true").lower() == "true"
        self.alert_cooldown_seconds = int(os.getenv("SYNC_ALERT_COOLDOWN", "300"))
        self.max_recovery_attempts = int(os.getenv("SYNC_MAX_RECOVERY_ATTEMPTS", "3"))

    async def initialize(self) -> None:
        """Initialize health monitoring system"""
        if not self.monitoring_enabled:
            logger.info("Health monitoring disabled")
            return

        await self._ensure_monitoring_tables()
        await self._register_default_health_checks()
        await self._register_default_recovery_handlers()
        await self._load_active_alerts()

        # Start monitoring tasks
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        self._recovery_task = asyncio.create_task(self._recovery_loop())

        logger.info("Health monitoring system initialized")

    async def shutdown(self) -> None:
        """Shutdown health monitoring system"""
        if self._monitor_task:
            self._monitor_task.cancel()
        if self._recovery_task:
            self._recovery_task.cancel()

        await asyncio.gather(
            self._monitor_task,
            self._recovery_task,
            return_exceptions=True
        )

        logger.info("Health monitoring system shutdown completed")

    def register_health_check(self, health_check: HealthCheck) -> None:
        """Register a custom health check"""
        self.health_checks[health_check.check_id] = health_check
        logger.info("Health check registered", check_id=health_check.check_id)

    def register_alert_handler(self, level: AlertLevel, handler: Callable) -> None:
        """Register alert handler for specific level"""
        self.alert_handlers[level].append(handler)
        logger.info("Alert handler registered", level=level)

    def register_recovery_handler(self, action: RecoveryAction, handler: Callable) -> None:
        """Register recovery action handler"""
        self.recovery_handlers[action] = handler
        logger.info("Recovery handler registered", action=action)

    async def run_health_check(self, check_id: str) -> HealthResult:
        """Run a specific health check manually"""
        if check_id not in self.health_checks:
            raise ValueError(f"Unknown health check: {check_id}")

        health_check = self.health_checks[check_id]
        return await self._execute_health_check(health_check)

    async def get_overall_health(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get overall system health status"""
        try:
            # Get recent check results
            recent_results = {
                check_id: result for check_id, result in self.check_results.items()
                if (datetime.now(timezone.utc) - result.timestamp).total_seconds() < 3600
            }

            # Calculate health scores
            total_checks = len(recent_results)
            healthy_checks = sum(1 for r in recent_results.values() if r.status == "healthy")
            warning_checks = sum(1 for r in recent_results.values() if r.status == "warning")
            error_checks = sum(1 for r in recent_results.values() if r.status == "error")
            critical_checks = sum(1 for r in recent_results.values() if r.status == "critical")

            # Overall health score (0-100)
            if total_checks == 0:
                health_score = 100
            else:
                health_score = (
                    (healthy_checks * 100 + warning_checks * 75 + error_checks * 25 + critical_checks * 0)
                    / total_checks
                )

            # Determine overall status
            if critical_checks > 0:
                overall_status = "critical"
            elif error_checks > 0:
                overall_status = "error"
            elif warning_checks > 0:
                overall_status = "warning"
            else:
                overall_status = "healthy"

            # Get sync health
            sync_health = await self.status_tracker.get_sync_health(tenant_id)

            # Get active alerts
            tenant_alerts = [
                alert for alert in self.active_alerts.values()
                if not tenant_id or alert.tenant_id == tenant_id
            ]

            return {
                "overall_status": overall_status,
                "health_score": round(health_score, 2),
                "check_summary": {
                    "total": total_checks,
                    "healthy": healthy_checks,
                    "warning": warning_checks,
                    "error": error_checks,
                    "critical": critical_checks
                },
                "sync_health": asdict(sync_health),
                "active_alerts": len(tenant_alerts),
                "active_recoveries": len(self.active_recoveries),
                "last_check_time": max(
                    [r.timestamp for r in recent_results.values()],
                    default=datetime.now(timezone.utc)
                ).isoformat(),
                "monitoring_enabled": self.monitoring_enabled,
                "auto_recovery_enabled": self.auto_recovery_enabled
            }

        except Exception as e:
            logger.error("Error getting overall health", error=str(e))
            return {
                "overall_status": "error",
                "health_score": 0,
                "error": str(e)
            }

    async def get_health_history(
        self,
        hours: int = 24,
        check_types: Optional[List[HealthCheckType]] = None
    ) -> List[Dict[str, Any]]:
        """Get health check history"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

            query = """
            SELECT check_id, check_type, status, message, metrics, timestamp, response_time_ms
            FROM health_check_results
            WHERE timestamp >= $1
            """
            params = [cutoff_time]

            if check_types:
                placeholders = ",".join(f"${i+2}" for i in range(len(check_types)))
                query += f" AND check_type IN ({placeholders})"
                params.extend(check_types)

            query += " ORDER BY timestamp DESC"

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            history = []
            for row in rows:
                result = dict(row)
                if result["metrics"]:
                    result["metrics"] = json.loads(result["metrics"])
                history.append(result)

            return history

        except Exception as e:
            logger.error("Error getting health history", error=str(e))
            return []

    async def trigger_recovery(
        self,
        action: RecoveryAction,
        trigger_alert_id: str,
        recovery_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Manually trigger a recovery action"""
        operation_id = str(uuid.uuid4())

        recovery = RecoveryOperation(
            operation_id=operation_id,
            action=action,
            trigger_alert_id=trigger_alert_id,
            status="pending",
            recovery_data=recovery_data or {}
        )

        self.active_recoveries[operation_id] = recovery
        await self._store_recovery_operation(recovery)

        logger.info("Recovery operation triggered", operation_id=operation_id, action=action)
        return operation_id

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while True:
            try:
                if not self.monitoring_enabled:
                    await asyncio.sleep(60)
                    continue

                # Run scheduled health checks
                current_time = datetime.now(timezone.utc)

                for health_check in self.health_checks.values():
                    if not health_check.enabled:
                        continue

                    # Check if it's time to run this check
                    last_result = self.check_results.get(health_check.check_id)
                    if last_result:
                        time_since_last = (current_time - last_result.timestamp).total_seconds()
                        if time_since_last < health_check.interval_seconds:
                            continue

                    # Execute health check
                    try:
                        result = await self._execute_health_check(health_check)
                        self.check_results[health_check.check_id] = result

                        # Store result in database
                        await self._store_health_result(result)

                        # Process result for alerts
                        await self._process_health_result(result, health_check)

                    except Exception as e:
                        logger.error(
                            "Health check execution failed",
                            check_id=health_check.check_id,
                            error=str(e)
                        )

                # Sleep for a short interval before next iteration
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in monitoring loop", error=str(e))
                await asyncio.sleep(30)

    async def _recovery_loop(self) -> None:
        """Recovery operations loop"""
        while True:
            try:
                if not self.auto_recovery_enabled:
                    await asyncio.sleep(30)
                    continue

                # Process pending recovery operations
                pending_recoveries = [
                    recovery for recovery in self.active_recoveries.values()
                    if recovery.status == "pending"
                ]

                for recovery in pending_recoveries:
                    try:
                        await self._execute_recovery_operation(recovery)
                    except Exception as e:
                        logger.error(
                            "Recovery operation failed",
                            operation_id=recovery.operation_id,
                            error=str(e)
                        )

                        recovery.status = "failed"
                        recovery.error_message = str(e)
                        recovery.completed_at = datetime.now(timezone.utc)

                        await self._store_recovery_operation(recovery)

                await asyncio.sleep(15)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in recovery loop", error=str(e))
                await asyncio.sleep(30)

    async def _execute_health_check(self, health_check: HealthCheck) -> HealthResult:
        """Execute a specific health check"""
        start_time = datetime.now(timezone.utc)

        try:
            # Execute check based on type
            if health_check.check_type == HealthCheckType.SYNC_PERFORMANCE:
                result = await self._check_sync_performance(health_check)
            elif health_check.check_type == HealthCheckType.RESOURCE_INTEGRITY:
                result = await self._check_resource_integrity(health_check)
            elif health_check.check_type == HealthCheckType.CACHE_HEALTH:
                result = await self._check_cache_health(health_check)
            elif health_check.check_type == HealthCheckType.DATABASE_CONNECTION:
                result = await self._check_database_connection(health_check)
            elif health_check.check_type == HealthCheckType.API_CONNECTIVITY:
                result = await self._check_api_connectivity(health_check)
            elif health_check.check_type == HealthCheckType.CONFLICT_RESOLUTION:
                result = await self._check_conflict_resolution(health_check)
            elif health_check.check_type == HealthCheckType.WEBHOOK_STATUS:
                result = await self._check_webhook_status(health_check)
            else:
                result = HealthResult(
                    check_id=health_check.check_id,
                    status="error",
                    message=f"Unknown check type: {health_check.check_type}"
                )

            # Calculate response time
            end_time = datetime.now(timezone.utc)
            result.response_time_ms = (end_time - start_time).total_seconds() * 1000

            return result

        except asyncio.TimeoutError:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message="Health check timed out",
                response_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message=f"Health check failed: {str(e)}",
                response_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

    async def _check_sync_performance(self, health_check: HealthCheck) -> HealthResult:
        """Check synchronization performance metrics"""
        try:
            # Get sync health for all tenants
            sync_health = await self.status_tracker.get_sync_health(None)

            # Determine status based on metrics
            status = "healthy"
            issues = []

            if sync_health.consecutive_failures >= 3:
                status = "critical"
                issues.append(f"Consecutive failures: {sync_health.consecutive_failures}")

            elif sync_health.success_rate_24h and sync_health.success_rate_24h < 90:
                status = "error"
                issues.append(f"Low success rate: {sync_health.success_rate_24h:.1f}%")

            elif sync_health.success_rate_24h and sync_health.success_rate_24h < 95:
                status = "warning"
                issues.append(f"Moderate success rate: {sync_health.success_rate_24h:.1f}%")

            if sync_health.resources_with_conflicts > 10:
                if status == "healthy":
                    status = "warning"
                issues.append(f"High conflict count: {sync_health.resources_with_conflicts}")

            message = "Sync performance healthy" if status == "healthy" else "; ".join(issues)

            return HealthResult(
                check_id=health_check.check_id,
                status=status,
                message=message,
                details=asdict(sync_health),
                metrics={
                    "success_rate": sync_health.success_rate_24h or 0,
                    "consecutive_failures": sync_health.consecutive_failures,
                    "avg_duration": sync_health.avg_sync_duration_24h or 0,
                    "conflicts": sync_health.resources_with_conflicts
                },
                recovery_suggestions=[
                    RecoveryAction.FORCE_FULL_SYNC,
                    RecoveryAction.RESOLVE_CONFLICTS
                ] if status in ["error", "critical"] else []
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message=f"Failed to check sync performance: {str(e)}"
            )

    async def _check_resource_integrity(self, health_check: HealthCheck) -> HealthResult:
        """Check resource data integrity"""
        try:
            # Check for orphaned resources
            orphaned_tasks_query = """
            SELECT COUNT(*) as count FROM tasks t
            WHERE NOT EXISTS (
                SELECT 1 FROM plans p WHERE p.graph_id = t.plan_graph_id
            )
            """

            # Check for missing etags
            missing_etags_query = """
            SELECT COUNT(*) as count FROM tasks
            WHERE task_metadata->>'etag' IS NULL
            """

            async with self.database._connection_pool.acquire() as conn:
                orphaned_result = await conn.fetchrow(orphaned_tasks_query)
                missing_etags_result = await conn.fetchrow(missing_etags_query)

            orphaned_count = orphaned_result["count"]
            missing_etags_count = missing_etags_result["count"]

            # Determine status
            status = "healthy"
            issues = []

            if orphaned_count > 0:
                status = "warning"
                issues.append(f"Orphaned tasks: {orphaned_count}")

            if missing_etags_count > 10:
                if status == "healthy":
                    status = "warning"
                issues.append(f"Missing etags: {missing_etags_count}")

            message = "Resource integrity healthy" if status == "healthy" else "; ".join(issues)

            return HealthResult(
                check_id=health_check.check_id,
                status=status,
                message=message,
                metrics={
                    "orphaned_tasks": orphaned_count,
                    "missing_etags": missing_etags_count
                },
                recovery_suggestions=[
                    RecoveryAction.FORCE_FULL_SYNC
                ] if orphaned_count > 0 else []
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message=f"Failed to check resource integrity: {str(e)}"
            )

    async def _check_cache_health(self, health_check: HealthCheck) -> HealthResult:
        """Check cache system health"""
        try:
            # Test cache operations
            test_key = f"health_check_{datetime.now().timestamp()}"
            test_value = {"test": True, "timestamp": datetime.now().isoformat()}

            # Test write
            await self.cache_service.set(test_key, test_value, ttl=60)

            # Test read
            cached_value = await self.cache_service.get(test_key)

            # Test delete
            await self.cache_service.delete(test_key)

            # Verify operations
            if cached_value != test_value:
                return HealthResult(
                    check_id=health_check.check_id,
                    status="error",
                    message="Cache read/write verification failed"
                )

            return HealthResult(
                check_id=health_check.check_id,
                status="healthy",
                message="Cache operations successful",
                metrics={
                    "cache_available": 1
                }
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="critical",
                message=f"Cache system unavailable: {str(e)}",
                recovery_suggestions=[RecoveryAction.RESET_CACHE]
            )

    async def _check_database_connection(self, health_check: HealthCheck) -> HealthResult:
        """Check database connectivity and performance"""
        try:
            start_time = datetime.now(timezone.utc)

            # Test basic query
            async with self.database._connection_pool.acquire() as conn:
                result = await conn.fetchrow("SELECT 1 as test, NOW() as timestamp")

            end_time = datetime.now(timezone.utc)
            query_time_ms = (end_time - start_time).total_seconds() * 1000

            # Check query performance
            status = "healthy"
            message = "Database connection healthy"

            if query_time_ms > 1000:  # 1 second
                status = "warning"
                message = f"Slow database response: {query_time_ms:.1f}ms"
            elif query_time_ms > 5000:  # 5 seconds
                status = "error"
                message = f"Very slow database response: {query_time_ms:.1f}ms"

            return HealthResult(
                check_id=health_check.check_id,
                status=status,
                message=message,
                metrics={
                    "query_time_ms": query_time_ms,
                    "connection_available": 1
                }
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="critical",
                message=f"Database connection failed: {str(e)}",
                recovery_suggestions=[RecoveryAction.NOTIFY_ADMIN]
            )

    async def _check_api_connectivity(self, health_check: HealthCheck) -> HealthResult:
        """Check Microsoft Graph API connectivity"""
        try:
            if not self.graph_client:
                return HealthResult(
                    check_id=health_check.check_id,
                    status="warning",
                    message="Graph client not configured"
                )

            start_time = datetime.now(timezone.utc)

            # Test API call
            response = await self.graph_client.get("/me")

            end_time = datetime.now(timezone.utc)
            api_time_ms = (end_time - start_time).total_seconds() * 1000

            # Check API performance
            status = "healthy"
            message = "API connectivity healthy"

            if api_time_ms > 2000:  # 2 seconds
                status = "warning"
                message = f"Slow API response: {api_time_ms:.1f}ms"

            return HealthResult(
                check_id=health_check.check_id,
                status=status,
                message=message,
                metrics={
                    "api_response_time_ms": api_time_ms,
                    "api_available": 1
                }
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message=f"API connectivity failed: {str(e)}",
                recovery_suggestions=[RecoveryAction.NOTIFY_ADMIN]
            )

    async def _check_conflict_resolution(self, health_check: HealthCheck) -> HealthResult:
        """Check conflict resolution system health"""
        try:
            # Get pending manual resolutions
            pending_conflicts = await self.conflict_manager.get_pending_manual_resolutions()

            # Get conflict statistics
            stats = await self.conflict_manager.get_conflict_statistics(days=7)

            # Determine status
            status = "healthy"
            issues = []

            pending_count = len(pending_conflicts)
            if pending_count > 20:
                status = "error"
                issues.append(f"High pending conflicts: {pending_count}")
            elif pending_count > 10:
                status = "warning"
                issues.append(f"Moderate pending conflicts: {pending_count}")

            message = "Conflict resolution healthy" if status == "healthy" else "; ".join(issues)

            return HealthResult(
                check_id=health_check.check_id,
                status=status,
                message=message,
                details=stats,
                metrics={
                    "pending_conflicts": pending_count,
                    "total_conflicts_7d": stats.get("total_conflicts", 0)
                },
                recovery_suggestions=[
                    RecoveryAction.RESOLVE_CONFLICTS
                ] if pending_count > 20 else []
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message=f"Failed to check conflict resolution: {str(e)}"
            )

    async def _check_webhook_status(self, health_check: HealthCheck) -> HealthResult:
        """Check webhook system health"""
        try:
            # This would integrate with the webhook manager from webhooks.py
            # For now, return a basic check
            return HealthResult(
                check_id=health_check.check_id,
                status="healthy",
                message="Webhook status check not implemented",
                metrics={"webhooks_active": 0}
            )

        except Exception as e:
            return HealthResult(
                check_id=health_check.check_id,
                status="error",
                message=f"Failed to check webhook status: {str(e)}"
            )

    async def _process_health_result(self, result: HealthResult, health_check: HealthCheck) -> None:
        """Process health check result and generate alerts if needed"""
        try:
            # Determine if alert is needed
            should_alert = False
            alert_level = AlertLevel.INFO

            if result.status == "critical":
                should_alert = True
                alert_level = AlertLevel.CRITICAL
            elif result.status == "error":
                should_alert = True
                alert_level = AlertLevel.ERROR
            elif result.status == "warning":
                should_alert = True
                alert_level = AlertLevel.WARNING

            if should_alert:
                await self._create_alert(result, health_check, alert_level)

            # Trigger automatic recovery if configured
            if self.auto_recovery_enabled and result.recovery_suggestions:
                for action in result.recovery_suggestions:
                    if action in health_check.recovery_actions:
                        await self._auto_trigger_recovery(action, result, health_check)

        except Exception as e:
            logger.error("Error processing health result", error=str(e))

    async def _create_alert(
        self,
        result: HealthResult,
        health_check: HealthCheck,
        level: AlertLevel
    ) -> None:
        """Create and process an alert"""
        try:
            # Check for alert cooldown
            alert_key = f"{health_check.check_id}_{result.status}"
            cooldown_key = f"alert_cooldown:{alert_key}"

            if await self.cache_service.get(cooldown_key):
                return  # Alert is in cooldown

            alert_id = str(uuid.uuid4())

            alert = Alert(
                alert_id=alert_id,
                level=level,
                check_type=health_check.check_type,
                title=f"{health_check.name} - {result.status.upper()}",
                message=result.message,
                details={
                    "check_result": asdict(result),
                    "health_check": asdict(health_check)
                }
            )

            self.active_alerts[alert_id] = alert
            await self._store_alert(alert)

            # Set cooldown
            await self.cache_service.set(cooldown_key, True, ttl=self.alert_cooldown_seconds)

            # Process alert handlers
            for handler in self.alert_handlers[level]:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error("Alert handler failed", handler=str(handler), error=str(e))

            logger.info(
                "Alert created",
                alert_id=alert_id,
                level=level,
                check_id=health_check.check_id,
                status=result.status
            )

        except Exception as e:
            logger.error("Error creating alert", error=str(e))

    async def _auto_trigger_recovery(
        self,
        action: RecoveryAction,
        result: HealthResult,
        health_check: HealthCheck
    ) -> None:
        """Automatically trigger recovery action"""
        try:
            # Check if recovery is already in progress for this check
            existing_recovery = None
            for recovery in self.active_recoveries.values():
                if (recovery.action == action and
                    recovery.recovery_data.get("check_id") == health_check.check_id and
                    recovery.status in ["pending", "running"]):
                    existing_recovery = recovery
                    break

            if existing_recovery:
                logger.debug("Recovery already in progress", action=action, check_id=health_check.check_id)
                return

            # Create recovery operation
            operation_id = str(uuid.uuid4())

            recovery = RecoveryOperation(
                operation_id=operation_id,
                action=action,
                trigger_alert_id="auto_recovery",
                status="pending",
                recovery_data={
                    "check_id": health_check.check_id,
                    "check_result": asdict(result),
                    "auto_triggered": True
                }
            )

            self.active_recoveries[operation_id] = recovery
            await self._store_recovery_operation(recovery)

            logger.info(
                "Auto recovery triggered",
                operation_id=operation_id,
                action=action,
                check_id=health_check.check_id
            )

        except Exception as e:
            logger.error("Error triggering auto recovery", action=action, error=str(e))

    async def _execute_recovery_operation(self, recovery: RecoveryOperation) -> None:
        """Execute a recovery operation"""
        try:
            recovery.status = "running"
            await self._store_recovery_operation(recovery)

            # Execute recovery action
            if recovery.action in self.recovery_handlers:
                handler = self.recovery_handlers[recovery.action]
                await handler(recovery)
            else:
                # Default recovery actions
                if recovery.action == RecoveryAction.RETRY_OPERATION:
                    await self._recovery_retry_operation(recovery)
                elif recovery.action == RecoveryAction.RESET_CACHE:
                    await self._recovery_reset_cache(recovery)
                elif recovery.action == RecoveryAction.FORCE_FULL_SYNC:
                    await self._recovery_force_full_sync(recovery)
                elif recovery.action == RecoveryAction.RESOLVE_CONFLICTS:
                    await self._recovery_resolve_conflicts(recovery)
                else:
                    raise ValueError(f"Unknown recovery action: {recovery.action}")

            recovery.status = "completed"
            recovery.completed_at = datetime.now(timezone.utc)

            logger.info("Recovery operation completed", operation_id=recovery.operation_id)

        except Exception as e:
            recovery.status = "failed"
            recovery.error_message = str(e)
            recovery.completed_at = datetime.now(timezone.utc)

            logger.error(
                "Recovery operation failed",
                operation_id=recovery.operation_id,
                error=str(e)
            )

        finally:
            await self._store_recovery_operation(recovery)

    async def _recovery_retry_operation(self, recovery: RecoveryOperation) -> None:
        """Recovery action: Retry failed operation"""
        # Implementation depends on specific operation type
        logger.info("Executing retry recovery", operation_id=recovery.operation_id)

    async def _recovery_reset_cache(self, recovery: RecoveryOperation) -> None:
        """Recovery action: Reset cache"""
        try:
            # Clear all cache entries
            await self.cache_service.clear()
            logger.info("Cache reset completed", operation_id=recovery.operation_id)

        except Exception as e:
            logger.error("Cache reset failed", operation_id=recovery.operation_id, error=str(e))
            raise

    async def _recovery_force_full_sync(self, recovery: RecoveryOperation) -> None:
        """Recovery action: Force full synchronization"""
        try:
            # Trigger full sync for all tenants
            operation_id = await self.status_tracker.start_sync_operation(
                SyncType.FULL_SYNC,
                SyncDirection.BIDIRECTIONAL,
                "health_recovery",
                config={"recovery_operation_id": recovery.operation_id}
            )

            recovery.recovery_data["sync_operation_id"] = operation_id
            logger.info("Full sync triggered", operation_id=recovery.operation_id, sync_id=operation_id)

        except Exception as e:
            logger.error("Full sync trigger failed", operation_id=recovery.operation_id, error=str(e))
            raise

    async def _recovery_resolve_conflicts(self, recovery: RecoveryOperation) -> None:
        """Recovery action: Resolve pending conflicts"""
        try:
            # Get pending conflicts
            pending_conflicts = await self.conflict_manager.get_pending_manual_resolutions()

            resolved_count = 0
            for conflict in pending_conflicts[:10]:  # Limit to 10 conflicts
                try:
                    # Auto-resolve using default strategy
                    await self.conflict_manager.handle_sync_conflict(
                        conflict["resource_type"],
                        conflict["resource_id"],
                        {},  # local_version - would need to fetch
                        {},  # remote_version - would need to fetch
                        conflict["user_id"],
                        conflict.get("tenant_id")
                    )
                    resolved_count += 1

                except Exception as e:
                    logger.warning("Failed to resolve conflict", conflict_id=conflict["conflict_id"], error=str(e))

            recovery.recovery_data["conflicts_resolved"] = resolved_count
            logger.info("Conflicts resolved", operation_id=recovery.operation_id, count=resolved_count)

        except Exception as e:
            logger.error("Conflict resolution failed", operation_id=recovery.operation_id, error=str(e))
            raise

    async def _register_default_health_checks(self) -> None:
        """Register default health checks"""
        default_checks = [
            HealthCheck(
                check_id="sync_performance",
                check_type=HealthCheckType.SYNC_PERFORMANCE,
                name="Sync Performance",
                description="Monitor synchronization performance and success rates",
                interval_seconds=300,  # 5 minutes
                timeout_seconds=30,
                critical=True,
                recovery_actions=[RecoveryAction.FORCE_FULL_SYNC, RecoveryAction.RESOLVE_CONFLICTS]
            ),
            HealthCheck(
                check_id="resource_integrity",
                check_type=HealthCheckType.RESOURCE_INTEGRITY,
                name="Resource Integrity",
                description="Check data integrity and consistency",
                interval_seconds=1800,  # 30 minutes
                timeout_seconds=60,
                recovery_actions=[RecoveryAction.FORCE_FULL_SYNC]
            ),
            HealthCheck(
                check_id="cache_health",
                check_type=HealthCheckType.CACHE_HEALTH,
                name="Cache Health",
                description="Monitor cache system availability and performance",
                interval_seconds=120,  # 2 minutes
                timeout_seconds=10,
                recovery_actions=[RecoveryAction.RESET_CACHE]
            ),
            HealthCheck(
                check_id="database_connection",
                check_type=HealthCheckType.DATABASE_CONNECTION,
                name="Database Connection",
                description="Monitor database connectivity and performance",
                interval_seconds=60,  # 1 minute
                timeout_seconds=15,
                critical=True,
                recovery_actions=[RecoveryAction.NOTIFY_ADMIN]
            ),
            HealthCheck(
                check_id="api_connectivity",
                check_type=HealthCheckType.API_CONNECTIVITY,
                name="API Connectivity",
                description="Monitor Microsoft Graph API connectivity",
                interval_seconds=300,  # 5 minutes
                timeout_seconds=20,
                recovery_actions=[RecoveryAction.NOTIFY_ADMIN]
            ),
            HealthCheck(
                check_id="conflict_resolution",
                check_type=HealthCheckType.CONFLICT_RESOLUTION,
                name="Conflict Resolution",
                description="Monitor conflict resolution system health",
                interval_seconds=600,  # 10 minutes
                timeout_seconds=30,
                recovery_actions=[RecoveryAction.RESOLVE_CONFLICTS]
            )
        ]

        for check in default_checks:
            self.register_health_check(check)

    async def _register_default_recovery_handlers(self) -> None:
        """Register default recovery action handlers"""
        # Default handlers are implemented in _execute_recovery_operation
        pass

    async def _load_active_alerts(self) -> None:
        """Load active alerts from database"""
        try:
            query = """
            SELECT alert_id, level, check_type, title, message, details, tenant_id, user_id,
                   created_at, resolved_at, recovery_actions_taken, auto_resolved
            FROM health_alerts
            WHERE resolved_at IS NULL
            """

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query)

            for row in rows:
                alert = Alert(
                    alert_id=row["alert_id"],
                    level=AlertLevel(row["level"]),
                    check_type=HealthCheckType(row["check_type"]),
                    title=row["title"],
                    message=row["message"],
                    details=json.loads(row["details"]) if row["details"] else {},
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    created_at=row["created_at"],
                    resolved_at=row["resolved_at"],
                    recovery_actions_taken=json.loads(row["recovery_actions_taken"]) if row["recovery_actions_taken"] else [],
                    auto_resolved=row["auto_resolved"]
                )

                self.active_alerts[alert.alert_id] = alert

            logger.info(f"Loaded {len(rows)} active alerts")

        except Exception as e:
            logger.error("Error loading active alerts", error=str(e))

    async def _ensure_monitoring_tables(self) -> None:
        """Ensure health monitoring tables exist"""
        try:
            async with self.database._connection_pool.acquire() as conn:
                # Health check results table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS health_check_results (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        check_id VARCHAR(255) NOT NULL,
                        check_type VARCHAR(50) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        message TEXT,
                        details JSONB DEFAULT '{}',
                        metrics JSONB DEFAULT '{}',
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        response_time_ms FLOAT
                    )
                """)

                # Health alerts table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS health_alerts (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        alert_id VARCHAR(255) UNIQUE NOT NULL,
                        level VARCHAR(20) NOT NULL,
                        check_type VARCHAR(50) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        message TEXT,
                        details JSONB DEFAULT '{}',
                        tenant_id VARCHAR(255),
                        user_id VARCHAR(255),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        resolved_at TIMESTAMP WITH TIME ZONE,
                        recovery_actions_taken JSONB DEFAULT '[]',
                        auto_resolved BOOLEAN DEFAULT false
                    )
                """)

                # Recovery operations table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS recovery_operations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        operation_id VARCHAR(255) UNIQUE NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        trigger_alert_id VARCHAR(255),
                        status VARCHAR(20) NOT NULL,
                        started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        completed_at TIMESTAMP WITH TIME ZONE,
                        error_message TEXT,
                        recovery_data JSONB DEFAULT '{}'
                    )
                """)

                # Create indexes
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_health_check_results_timestamp
                    ON health_check_results(timestamp DESC)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_health_alerts_status
                    ON health_alerts(resolved_at, created_at DESC)
                """)

        except Exception as e:
            logger.error("Failed to create monitoring tables", error=str(e))
            raise

    async def _store_health_result(self, result: HealthResult) -> None:
        """Store health check result in database"""
        try:
            query = """
            INSERT INTO health_check_results (
                check_id, check_type, status, message, details, metrics, timestamp, response_time_ms
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            """

            # Extract check_type from result or use default
            check_type = result.details.get("check_type", "unknown")

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    result.check_id,
                    check_type,
                    result.status,
                    result.message,
                    json.dumps(result.details),
                    json.dumps(result.metrics),
                    result.timestamp,
                    result.response_time_ms
                )

        except Exception as e:
            logger.error("Failed to store health result", check_id=result.check_id, error=str(e))

    async def _store_alert(self, alert: Alert) -> None:
        """Store alert in database"""
        try:
            query = """
            INSERT INTO health_alerts (
                alert_id, level, check_type, title, message, details, tenant_id, user_id,
                created_at, resolved_at, recovery_actions_taken, auto_resolved
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
            )
            ON CONFLICT (alert_id) DO UPDATE SET
                resolved_at = EXCLUDED.resolved_at,
                recovery_actions_taken = EXCLUDED.recovery_actions_taken,
                auto_resolved = EXCLUDED.auto_resolved
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    alert.alert_id,
                    alert.level,
                    alert.check_type,
                    alert.title,
                    alert.message,
                    json.dumps(alert.details),
                    alert.tenant_id,
                    alert.user_id,
                    alert.created_at,
                    alert.resolved_at,
                    json.dumps(alert.recovery_actions_taken),
                    alert.auto_resolved
                )

        except Exception as e:
            logger.error("Failed to store alert", alert_id=alert.alert_id, error=str(e))

    async def _store_recovery_operation(self, recovery: RecoveryOperation) -> None:
        """Store recovery operation in database"""
        try:
            query = """
            INSERT INTO recovery_operations (
                operation_id, action, trigger_alert_id, status, started_at, completed_at,
                error_message, recovery_data
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            ON CONFLICT (operation_id) DO UPDATE SET
                status = EXCLUDED.status,
                completed_at = EXCLUDED.completed_at,
                error_message = EXCLUDED.error_message,
                recovery_data = EXCLUDED.recovery_data
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    recovery.operation_id,
                    recovery.action,
                    recovery.trigger_alert_id,
                    recovery.status,
                    recovery.started_at,
                    recovery.completed_at,
                    recovery.error_message,
                    json.dumps(recovery.recovery_data)
                )

        except Exception as e:
            logger.error("Failed to store recovery operation", operation_id=recovery.operation_id, error=str(e))


# Import required modules at the end to avoid circular imports
import os
from typing import Any
from .status_tracker import SyncDirection