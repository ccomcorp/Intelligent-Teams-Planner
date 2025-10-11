"""
Comprehensive Sync Status Tracking and Reporting System
Story 8.1 Task 2.3: Advanced synchronization status tracking

Implements detailed tracking of synchronization operations, performance metrics,
and comprehensive reporting for Microsoft Planner integration.
"""

import uuid
import json
import asyncio
from typing import Dict, List, Any, Optional, Set, Union
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
import structlog

from ..database import Database
from ..cache import CacheService
from ..models.graph_models import TenantContext

logger = structlog.get_logger(__name__)


class SyncType(str, Enum):
    """Types of synchronization operations"""

    FULL_SYNC = "full_sync"
    DELTA_SYNC = "delta_sync"
    MANUAL_SYNC = "manual_sync"
    WEBHOOK_SYNC = "webhook_sync"
    CONFLICT_RESOLUTION = "conflict_resolution"


class SyncDirection(str, Enum):
    """Synchronization direction"""

    INBOUND = "inbound"      # From Graph to local
    OUTBOUND = "outbound"    # From local to Graph
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(str, Enum):
    """Synchronization operation status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ResourceStatus(str, Enum):
    """Status of individual resource synchronization"""

    SYNCED = "synced"
    PENDING = "pending"
    FAILED = "failed"
    CONFLICT = "conflict"
    SKIPPED = "skipped"


@dataclass
class SyncMetrics:
    """Performance and operation metrics for sync operations"""

    # Timing metrics
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Resource counts
    total_resources: int = 0
    processed_resources: int = 0
    successful_resources: int = 0
    failed_resources: int = 0
    skipped_resources: int = 0
    conflict_resources: int = 0

    # Data transfer metrics
    bytes_transferred: int = 0
    api_calls_made: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    # Performance metrics
    avg_processing_time_ms: Optional[float] = None
    max_processing_time_ms: Optional[float] = None
    min_processing_time_ms: Optional[float] = None
    throughput_resources_per_second: Optional[float] = None

    # Error metrics
    rate_limit_errors: int = 0
    network_errors: int = 0
    permission_errors: int = 0
    validation_errors: int = 0
    other_errors: int = 0

    def calculate_derived_metrics(self) -> None:
        """Calculate derived metrics from basic counts"""
        if self.end_time and self.start_time:
            self.duration_seconds = (self.end_time - self.start_time).total_seconds()

            if self.duration_seconds > 0:
                self.throughput_resources_per_second = self.processed_resources / self.duration_seconds


@dataclass
class ResourceSyncStatus:
    """Status of individual resource synchronization"""

    resource_id: str
    resource_type: str
    status: ResourceStatus
    last_sync_time: Optional[datetime] = None
    sync_operation_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    local_etag: Optional[str] = None
    remote_etag: Optional[str] = None
    conflict_id: Optional[str] = None


@dataclass
class SyncOperation:
    """Complete synchronization operation record"""

    # Basic identification
    operation_id: str
    sync_type: SyncType
    sync_direction: SyncDirection
    status: SyncStatus

    # Context
    user_id: str
    tenant_id: Optional[str] = None
    resource_type: Optional[str] = None  # None for full sync
    resource_ids: List[str] = field(default_factory=list)

    # Timing and progress
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None

    # Results
    metrics: Optional[SyncMetrics] = None
    error_message: Optional[str] = None
    warning_messages: List[str] = field(default_factory=list)

    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Related operations
    parent_operation_id: Optional[str] = None
    child_operation_ids: List[str] = field(default_factory=list)

    # Resource tracking
    resource_statuses: Dict[str, ResourceSyncStatus] = field(default_factory=dict)


@dataclass
class SyncHealth:
    """Overall synchronization health metrics"""

    tenant_id: Optional[str]
    last_successful_sync: Optional[datetime] = None
    last_failed_sync: Optional[datetime] = None
    consecutive_failures: int = 0
    total_operations_24h: int = 0
    failed_operations_24h: int = 0
    avg_sync_duration_24h: Optional[float] = None
    success_rate_24h: Optional[float] = None

    # Resource health
    resources_in_sync: int = 0
    resources_with_conflicts: int = 0
    resources_with_errors: int = 0
    resources_pending_sync: int = 0

    # System health indicators
    is_healthy: bool = True
    health_issues: List[str] = field(default_factory=list)
    last_health_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SyncStatusTracker:
    """Tracks and manages synchronization status and metrics"""

    def __init__(self, database: Database, cache_service: CacheService):
        self.database = database
        self.cache_service = cache_service

        # Active operation tracking
        self._active_operations: Dict[str, SyncOperation] = {}
        self._operation_locks: Dict[str, asyncio.Lock] = {}

        # Configuration
        self.max_operation_history = int(os.getenv("MAX_SYNC_OPERATION_HISTORY", "1000"))
        self.cleanup_interval_hours = int(os.getenv("SYNC_CLEANUP_INTERVAL_HOURS", "24"))
        self.heartbeat_interval_seconds = int(os.getenv("SYNC_HEARTBEAT_INTERVAL", "30"))

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize sync status tracking"""
        await self._ensure_sync_tables()
        await self._load_active_operations()

        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._heartbeat_task = asyncio.create_task(self._periodic_heartbeat())

        logger.info("Sync status tracker initialized")

    async def shutdown(self) -> None:
        """Shutdown sync status tracker"""
        # Cancel background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(
            self._cleanup_task,
            self._heartbeat_task,
            return_exceptions=True
        )

        logger.info("Sync status tracker shutdown completed")

    async def start_sync_operation(
        self,
        sync_type: SyncType,
        sync_direction: SyncDirection,
        user_id: str,
        tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_ids: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        parent_operation_id: Optional[str] = None
    ) -> str:
        """
        Start tracking a new synchronization operation

        Args:
            sync_type: Type of synchronization
            sync_direction: Direction of sync
            user_id: User identifier
            tenant_id: Tenant context
            resource_type: Type of resources being synced
            resource_ids: Specific resource IDs (if applicable)
            config: Operation configuration
            parent_operation_id: Parent operation for nested syncs

        Returns:
            Operation ID for tracking
        """
        operation_id = str(uuid.uuid4())

        operation = SyncOperation(
            operation_id=operation_id,
            sync_type=sync_type,
            sync_direction=sync_direction,
            status=SyncStatus.PENDING,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_ids=resource_ids or [],
            config=config or {},
            parent_operation_id=parent_operation_id
        )

        # Store in active operations
        self._active_operations[operation_id] = operation
        self._operation_locks[operation_id] = asyncio.Lock()

        # Persist to database
        await self._store_sync_operation(operation)

        # Update parent operation if applicable
        if parent_operation_id and parent_operation_id in self._active_operations:
            self._active_operations[parent_operation_id].child_operation_ids.append(operation_id)

        logger.info(
            "Sync operation started",
            operation_id=operation_id,
            sync_type=sync_type,
            resource_type=resource_type,
            user_id=user_id
        )

        return operation_id

    async def update_operation_status(
        self,
        operation_id: str,
        status: SyncStatus,
        error_message: Optional[str] = None,
        warning_message: Optional[str] = None
    ) -> None:
        """Update the status of a sync operation"""
        if operation_id not in self._active_operations:
            logger.warning("Attempted to update unknown operation", operation_id=operation_id)
            return

        async with self._operation_locks[operation_id]:
            operation = self._active_operations[operation_id]
            operation.status = status
            operation.last_heartbeat = datetime.now(timezone.utc)

            if status == SyncStatus.RUNNING and not operation.started_at:
                operation.started_at = datetime.now(timezone.utc)

            if status in [SyncStatus.COMPLETED, SyncStatus.FAILED, SyncStatus.CANCELLED]:
                operation.completed_at = datetime.now(timezone.utc)

            if error_message:
                operation.error_message = error_message

            if warning_message:
                operation.warning_messages.append(warning_message)

            # Update in database
            await self._update_sync_operation(operation)

            # Cache recent status for quick access
            await self.cache_service.set(
                f"sync_status:{operation_id}",
                {
                    "status": status,
                    "last_update": operation.last_heartbeat.isoformat(),
                    "progress": self._calculate_progress(operation)
                },
                ttl=3600
            )

        logger.debug(
            "Operation status updated",
            operation_id=operation_id,
            status=status,
            error_message=error_message
        )

    async def start_operation_metrics(self, operation_id: str) -> None:
        """Initialize metrics tracking for an operation"""
        if operation_id not in self._active_operations:
            return

        async with self._operation_locks[operation_id]:
            operation = self._active_operations[operation_id]
            operation.metrics = SyncMetrics(
                start_time=datetime.now(timezone.utc)
            )

    async def update_operation_metrics(
        self,
        operation_id: str,
        **metrics_updates: Any
    ) -> None:
        """Update metrics for a sync operation"""
        if operation_id not in self._active_operations:
            return

        async with self._operation_locks[operation_id]:
            operation = self._active_operations[operation_id]
            if not operation.metrics:
                operation.metrics = SyncMetrics(start_time=datetime.now(timezone.utc))

            # Update metrics fields
            for field, value in metrics_updates.items():
                if hasattr(operation.metrics, field):
                    current_value = getattr(operation.metrics, field)

                    # Handle cumulative fields
                    if field in ["api_calls_made", "cache_hits", "cache_misses", "bytes_transferred",
                                "processed_resources", "successful_resources", "failed_resources",
                                "skipped_resources", "conflict_resources", "rate_limit_errors",
                                "network_errors", "permission_errors", "validation_errors", "other_errors"]:
                        setattr(operation.metrics, field, current_value + value)
                    else:
                        setattr(operation.metrics, field, value)

            # Update performance metrics
            if operation.metrics.end_time:
                operation.metrics.calculate_derived_metrics()

    async def update_resource_status(
        self,
        operation_id: str,
        resource_id: str,
        resource_type: str,
        status: ResourceStatus,
        error_message: Optional[str] = None,
        local_etag: Optional[str] = None,
        remote_etag: Optional[str] = None,
        conflict_id: Optional[str] = None
    ) -> None:
        """Update the status of a specific resource within an operation"""
        if operation_id not in self._active_operations:
            return

        async with self._operation_locks[operation_id]:
            operation = self._active_operations[operation_id]

            resource_status = ResourceSyncStatus(
                resource_id=resource_id,
                resource_type=resource_type,
                status=status,
                last_sync_time=datetime.now(timezone.utc),
                sync_operation_id=operation_id,
                error_message=error_message,
                local_etag=local_etag,
                remote_etag=remote_etag,
                conflict_id=conflict_id
            )

            # Update retry count if this is a retry
            if resource_id in operation.resource_statuses:
                old_status = operation.resource_statuses[resource_id]
                if old_status.status == ResourceStatus.FAILED and status == ResourceStatus.PENDING:
                    resource_status.retry_count = old_status.retry_count + 1

            operation.resource_statuses[resource_id] = resource_status

            # Update operation metrics
            if operation.metrics:
                self._update_metrics_from_resource_status(operation.metrics, status)

            # Store resource status
            await self._store_resource_status(resource_status)

    def _update_metrics_from_resource_status(self, metrics: SyncMetrics, status: ResourceStatus) -> None:
        """Update operation metrics based on resource status"""
        if status == ResourceStatus.SYNCED:
            metrics.successful_resources += 1
        elif status == ResourceStatus.FAILED:
            metrics.failed_resources += 1
        elif status == ResourceStatus.CONFLICT:
            metrics.conflict_resources += 1
        elif status == ResourceStatus.SKIPPED:
            metrics.skipped_resources += 1

    async def complete_sync_operation(
        self,
        operation_id: str,
        final_status: SyncStatus = SyncStatus.COMPLETED,
        error_message: Optional[str] = None
    ) -> None:
        """Complete a sync operation and finalize metrics"""
        if operation_id not in self._active_operations:
            return

        async with self._operation_locks[operation_id]:
            operation = self._active_operations[operation_id]
            operation.status = final_status
            operation.completed_at = datetime.now(timezone.utc)

            if error_message:
                operation.error_message = error_message

            # Finalize metrics
            if operation.metrics:
                operation.metrics.end_time = operation.completed_at
                operation.metrics.calculate_derived_metrics()

                # Calculate total resources
                operation.metrics.total_resources = len(operation.resource_statuses)

            # Final database update
            await self._update_sync_operation(operation)

            # Update sync health
            await self._update_sync_health(operation)

            # Remove from active operations
            del self._active_operations[operation_id]
            del self._operation_locks[operation_id]

        logger.info(
            "Sync operation completed",
            operation_id=operation_id,
            final_status=final_status,
            duration=operation.metrics.duration_seconds if operation.metrics else None
        )

    async def get_operation_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a sync operation"""
        # Check active operations first
        if operation_id in self._active_operations:
            operation = self._active_operations[operation_id]
            return {
                "operation_id": operation_id,
                "status": operation.status,
                "sync_type": operation.sync_type,
                "sync_direction": operation.sync_direction,
                "progress": self._calculate_progress(operation),
                "started_at": operation.started_at.isoformat() if operation.started_at else None,
                "last_heartbeat": operation.last_heartbeat.isoformat() if operation.last_heartbeat else None,
                "metrics": asdict(operation.metrics) if operation.metrics else None,
                "error_message": operation.error_message,
                "warning_count": len(operation.warning_messages)
            }

        # Check cache
        cached_status = await self.cache_service.get(f"sync_status:{operation_id}")
        if cached_status:
            return cached_status

        # Check database
        return await self._get_operation_from_database(operation_id)

    def _calculate_progress(self, operation: SyncOperation) -> Dict[str, Any]:
        """Calculate progress metrics for an operation"""
        total_resources = len(operation.resource_statuses)
        if total_resources == 0:
            return {"percentage": 0, "completed": 0, "total": 0}

        completed = sum(
            1 for status in operation.resource_statuses.values()
            if status.status in [ResourceStatus.SYNCED, ResourceStatus.FAILED, ResourceStatus.SKIPPED]
        )

        percentage = (completed / total_resources) * 100 if total_resources > 0 else 0

        return {
            "percentage": round(percentage, 2),
            "completed": completed,
            "total": total_resources,
            "synced": sum(1 for s in operation.resource_statuses.values() if s.status == ResourceStatus.SYNCED),
            "failed": sum(1 for s in operation.resource_statuses.values() if s.status == ResourceStatus.FAILED),
            "conflicts": sum(1 for s in operation.resource_statuses.values() if s.status == ResourceStatus.CONFLICT),
            "pending": sum(1 for s in operation.resource_statuses.values() if s.status == ResourceStatus.PENDING)
        }

    async def get_sync_health(self, tenant_id: Optional[str] = None) -> SyncHealth:
        """Get overall synchronization health for a tenant"""
        try:
            # Get recent operations
            cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)

            query = """
            SELECT operation_id, status, sync_type, started_at, completed_at, metrics
            FROM sync_operations
            WHERE created_at >= $1
            """
            params = [cutoff_24h]

            if tenant_id:
                query += " AND tenant_id = $2"
                params.append(tenant_id)

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            # Calculate health metrics
            total_ops = len(rows)
            failed_ops = sum(1 for row in rows if row["status"] == SyncStatus.FAILED)

            # Find last successful and failed syncs
            last_successful = None
            last_failed = None
            consecutive_failures = 0
            total_duration = 0
            duration_count = 0

            sorted_ops = sorted(rows, key=lambda x: x["started_at"] or x["created_at"], reverse=True)

            for row in sorted_ops:
                status = row["status"]
                completed_at = row["completed_at"]
                started_at = row["started_at"]

                # Track last successful/failed
                if status == SyncStatus.COMPLETED and not last_successful:
                    last_successful = completed_at
                elif status == SyncStatus.FAILED and not last_failed:
                    last_failed = completed_at

                # Count consecutive failures from most recent
                if consecutive_failures == len([r for r in sorted_ops[:rows.index(row)]]):
                    if status == SyncStatus.FAILED:
                        consecutive_failures += 1
                    else:
                        break

                # Calculate average duration
                if started_at and completed_at:
                    duration = (completed_at - started_at).total_seconds()
                    total_duration += duration
                    duration_count += 1

            # Calculate success rate
            success_rate = ((total_ops - failed_ops) / total_ops * 100) if total_ops > 0 else 100
            avg_duration = total_duration / duration_count if duration_count > 0 else None

            # Get resource health
            resource_health = await self._get_resource_health(tenant_id)

            # Determine overall health
            health_issues = []
            is_healthy = True

            if consecutive_failures >= 3:
                health_issues.append(f"Consecutive sync failures: {consecutive_failures}")
                is_healthy = False

            if success_rate < 90:
                health_issues.append(f"Low success rate: {success_rate:.1f}%")
                is_healthy = False

            if resource_health["conflicts"] > 10:
                health_issues.append(f"High conflict count: {resource_health['conflicts']}")
                is_healthy = False

            return SyncHealth(
                tenant_id=tenant_id,
                last_successful_sync=last_successful,
                last_failed_sync=last_failed,
                consecutive_failures=consecutive_failures,
                total_operations_24h=total_ops,
                failed_operations_24h=failed_ops,
                avg_sync_duration_24h=avg_duration,
                success_rate_24h=success_rate,
                resources_in_sync=resource_health["synced"],
                resources_with_conflicts=resource_health["conflicts"],
                resources_with_errors=resource_health["errors"],
                resources_pending_sync=resource_health["pending"],
                is_healthy=is_healthy,
                health_issues=health_issues
            )

        except Exception as e:
            logger.error("Error calculating sync health", tenant_id=tenant_id, error=str(e))
            return SyncHealth(
                tenant_id=tenant_id,
                is_healthy=False,
                health_issues=[f"Health check failed: {str(e)}"]
            )

    async def _get_resource_health(self, tenant_id: Optional[str]) -> Dict[str, int]:
        """Get resource-level health metrics"""
        try:
            # Get latest resource statuses
            query = """
            SELECT DISTINCT ON (resource_id, resource_type)
                   resource_id, resource_type, status
            FROM resource_sync_status r
            JOIN sync_operations o ON r.sync_operation_id = o.operation_id
            WHERE 1=1
            """
            params = []

            if tenant_id:
                query += " AND o.tenant_id = $1"
                params.append(tenant_id)

            query += " ORDER BY resource_id, resource_type, r.last_sync_time DESC"

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            # Count by status
            status_counts = {
                "synced": 0,
                "conflicts": 0,
                "errors": 0,
                "pending": 0
            }

            for row in rows:
                status = row["status"]
                if status == ResourceStatus.SYNCED:
                    status_counts["synced"] += 1
                elif status == ResourceStatus.CONFLICT:
                    status_counts["conflicts"] += 1
                elif status == ResourceStatus.FAILED:
                    status_counts["errors"] += 1
                elif status == ResourceStatus.PENDING:
                    status_counts["pending"] += 1

            return status_counts

        except Exception as e:
            logger.error("Error getting resource health", error=str(e))
            return {"synced": 0, "conflicts": 0, "errors": 0, "pending": 0}

    async def get_sync_history(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        sync_type: Optional[SyncType] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get synchronization operation history"""
        try:
            query = """
            SELECT operation_id, sync_type, sync_direction, status, user_id, tenant_id,
                   resource_type, created_at, started_at, completed_at, error_message,
                   metrics
            FROM sync_operations
            WHERE 1=1
            """
            params = []
            param_count = 0

            if user_id:
                param_count += 1
                query += f" AND user_id = ${param_count}"
                params.append(user_id)

            if tenant_id:
                param_count += 1
                query += f" AND tenant_id = ${param_count}"
                params.append(tenant_id)

            if sync_type:
                param_count += 1
                query += f" AND sync_type = ${param_count}"
                params.append(sync_type)

            query += " ORDER BY created_at DESC"

            if limit:
                param_count += 1
                query += f" LIMIT ${param_count}"
                params.append(limit)

            if offset:
                param_count += 1
                query += f" OFFSET ${param_count}"
                params.append(offset)

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            operations = []
            for row in rows:
                operation = dict(row)

                # Parse metrics if available
                if operation["metrics"]:
                    operation["metrics"] = json.loads(operation["metrics"])

                # Calculate duration if possible
                if operation["started_at"] and operation["completed_at"]:
                    duration = (operation["completed_at"] - operation["started_at"]).total_seconds()
                    operation["duration_seconds"] = duration

                operations.append(operation)

            return operations

        except Exception as e:
            logger.error("Error getting sync history", error=str(e))
            return []

    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup of old sync records"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_hours * 3600)

                # Clean up old operations
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

                async with self.database._connection_pool.acquire() as conn:
                    # Keep only the most recent operations per user/tenant
                    await conn.execute("""
                        DELETE FROM sync_operations
                        WHERE created_at < $1
                        AND operation_id NOT IN (
                            SELECT operation_id FROM (
                                SELECT operation_id,
                                       ROW_NUMBER() OVER (
                                           PARTITION BY user_id, tenant_id
                                           ORDER BY created_at DESC
                                       ) as rn
                                FROM sync_operations
                            ) ranked
                            WHERE rn <= $2
                        )
                    """, cutoff_date, self.max_operation_history)

                logger.info("Completed sync operation cleanup")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in sync cleanup", error=str(e))

    async def _periodic_heartbeat(self) -> None:
        """Periodic heartbeat for active operations"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval_seconds)

                current_time = datetime.now(timezone.utc)
                stale_operations = []

                # Check for stale operations
                for operation_id, operation in self._active_operations.items():
                    if operation.last_heartbeat:
                        time_since_heartbeat = (current_time - operation.last_heartbeat).total_seconds()
                        if time_since_heartbeat > 300:  # 5 minutes
                            stale_operations.append(operation_id)

                # Mark stale operations as failed
                for operation_id in stale_operations:
                    await self.update_operation_status(
                        operation_id,
                        SyncStatus.FAILED,
                        "Operation timeout - no heartbeat received"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in heartbeat monitor", error=str(e))

    async def _ensure_sync_tables(self) -> None:
        """Ensure synchronization tracking tables exist"""
        try:
            async with self.database._connection_pool.acquire() as conn:
                # Sync operations table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS sync_operations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        operation_id VARCHAR(255) UNIQUE NOT NULL,
                        sync_type VARCHAR(50) NOT NULL,
                        sync_direction VARCHAR(20) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        tenant_id VARCHAR(255),
                        resource_type VARCHAR(50),
                        resource_ids JSONB DEFAULT '[]',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        started_at TIMESTAMP WITH TIME ZONE,
                        completed_at TIMESTAMP WITH TIME ZONE,
                        last_heartbeat TIMESTAMP WITH TIME ZONE,
                        metrics JSONB,
                        error_message TEXT,
                        warning_messages JSONB DEFAULT '[]',
                        config JSONB DEFAULT '{}',
                        parent_operation_id VARCHAR(255),
                        child_operation_ids JSONB DEFAULT '[]'
                    )
                """)

                # Resource sync status table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS resource_sync_status (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        resource_id VARCHAR(255) NOT NULL,
                        resource_type VARCHAR(50) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        last_sync_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        sync_operation_id VARCHAR(255) NOT NULL,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0,
                        local_etag VARCHAR(255),
                        remote_etag VARCHAR(255),
                        conflict_id VARCHAR(255),
                        FOREIGN KEY (sync_operation_id) REFERENCES sync_operations(operation_id)
                    )
                """)

                # Create indexes for performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sync_operations_user_tenant
                    ON sync_operations(user_id, tenant_id, created_at DESC)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sync_operations_status
                    ON sync_operations(status, created_at DESC)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_resource_sync_status_resource
                    ON resource_sync_status(resource_id, resource_type, last_sync_time DESC)
                """)

        except Exception as e:
            logger.error("Failed to create sync tracking tables", error=str(e))
            raise

    async def _load_active_operations(self) -> None:
        """Load active operations from database on startup"""
        try:
            query = """
            SELECT operation_id, sync_type, sync_direction, status, user_id, tenant_id,
                   resource_type, resource_ids, created_at, started_at, last_heartbeat,
                   config, parent_operation_id, child_operation_ids
            FROM sync_operations
            WHERE status IN ('pending', 'running', 'retrying')
            """

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query)

            for row in rows:
                operation = SyncOperation(
                    operation_id=row["operation_id"],
                    sync_type=SyncType(row["sync_type"]),
                    sync_direction=SyncDirection(row["sync_direction"]),
                    status=SyncStatus(row["status"]),
                    user_id=row["user_id"],
                    tenant_id=row["tenant_id"],
                    resource_type=row["resource_type"],
                    resource_ids=json.loads(row["resource_ids"]) if row["resource_ids"] else [],
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    last_heartbeat=row["last_heartbeat"],
                    config=json.loads(row["config"]) if row["config"] else {},
                    parent_operation_id=row["parent_operation_id"],
                    child_operation_ids=json.loads(row["child_operation_ids"]) if row["child_operation_ids"] else []
                )

                self._active_operations[operation.operation_id] = operation
                self._operation_locks[operation.operation_id] = asyncio.Lock()

            logger.info(f"Loaded {len(rows)} active sync operations")

        except Exception as e:
            logger.error("Error loading active operations", error=str(e))

    async def _store_sync_operation(self, operation: SyncOperation) -> None:
        """Store sync operation in database"""
        try:
            query = """
            INSERT INTO sync_operations (
                operation_id, sync_type, sync_direction, status, user_id, tenant_id,
                resource_type, resource_ids, created_at, started_at, completed_at,
                last_heartbeat, metrics, error_message, warning_messages, config,
                parent_operation_id, child_operation_ids
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
            )
            ON CONFLICT (operation_id) DO UPDATE SET
                status = EXCLUDED.status,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                last_heartbeat = EXCLUDED.last_heartbeat,
                metrics = EXCLUDED.metrics,
                error_message = EXCLUDED.error_message,
                warning_messages = EXCLUDED.warning_messages,
                child_operation_ids = EXCLUDED.child_operation_ids
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    operation.operation_id,
                    operation.sync_type,
                    operation.sync_direction,
                    operation.status,
                    operation.user_id,
                    operation.tenant_id,
                    operation.resource_type,
                    json.dumps(operation.resource_ids),
                    operation.created_at,
                    operation.started_at,
                    operation.completed_at,
                    operation.last_heartbeat,
                    json.dumps(asdict(operation.metrics)) if operation.metrics else None,
                    operation.error_message,
                    json.dumps(operation.warning_messages),
                    json.dumps(operation.config),
                    operation.parent_operation_id,
                    json.dumps(operation.child_operation_ids)
                )

        except Exception as e:
            logger.error("Failed to store sync operation", operation_id=operation.operation_id, error=str(e))

    async def _update_sync_operation(self, operation: SyncOperation) -> None:
        """Update existing sync operation in database"""
        await self._store_sync_operation(operation)

    async def _store_resource_status(self, resource_status: ResourceSyncStatus) -> None:
        """Store resource sync status in database"""
        try:
            query = """
            INSERT INTO resource_sync_status (
                resource_id, resource_type, status, last_sync_time, sync_operation_id,
                error_message, retry_count, local_etag, remote_etag, conflict_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
            )
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    resource_status.resource_id,
                    resource_status.resource_type,
                    resource_status.status,
                    resource_status.last_sync_time,
                    resource_status.sync_operation_id,
                    resource_status.error_message,
                    resource_status.retry_count,
                    resource_status.local_etag,
                    resource_status.remote_etag,
                    resource_status.conflict_id
                )

        except Exception as e:
            logger.error("Failed to store resource status", resource_id=resource_status.resource_id, error=str(e))

    async def _get_operation_from_database(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get operation details from database"""
        try:
            query = """
            SELECT operation_id, sync_type, sync_direction, status, user_id, tenant_id,
                   resource_type, created_at, started_at, completed_at, metrics,
                   error_message, warning_messages
            FROM sync_operations
            WHERE operation_id = $1
            """

            async with self.database._connection_pool.acquire() as conn:
                row = await conn.fetchrow(query, operation_id)

            if not row:
                return None

            result = dict(row)

            # Parse JSON fields
            if result["metrics"]:
                result["metrics"] = json.loads(result["metrics"])
            if result["warning_messages"]:
                result["warning_messages"] = json.loads(result["warning_messages"])

            # Calculate duration
            if result["started_at"] and result["completed_at"]:
                duration = (result["completed_at"] - result["started_at"]).total_seconds()
                result["duration_seconds"] = duration

            return result

        except Exception as e:
            logger.error("Error getting operation from database", operation_id=operation_id, error=str(e))
            return None

    async def _update_sync_health(self, operation: SyncOperation) -> None:
        """Update overall sync health metrics after operation completion"""
        try:
            # Cache health metrics for quick access
            health = await self.get_sync_health(operation.tenant_id)

            await self.cache_service.set(
                f"sync_health:{operation.tenant_id or 'default'}",
                asdict(health),
                ttl=1800  # 30 minutes
            )

        except Exception as e:
            logger.error("Error updating sync health", operation_id=operation.operation_id, error=str(e))


# Import at module level to avoid circular imports
import os
from datetime import timedelta