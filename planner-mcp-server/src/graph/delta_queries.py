"""
Delta Query Support for Microsoft Graph API
Story 2.1 Task 2: Advanced Graph API Integration with Delta Queries

Implements comprehensive delta query functionality for Planner tasks and plans
with token management, incremental sync, error handling, and performance monitoring.
"""

import os
import asyncio
import json
import hashlib
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..models.graph_models import DeltaToken, DeltaResult, ResourceChange, ErrorContext
from ..database import Database
from ..utils.performance_monitor import get_performance_monitor, track_operation
from .client import EnhancedGraphClient

logger = structlog.get_logger(__name__)


class DeltaStorageType(str, Enum):
    """Delta token storage backend types"""

    DATABASE = "database"
    REDIS = "redis"
    FILE = "file"


class DeltaSyncStatus(str, Enum):
    """Delta synchronization status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    FALLBACK_FULL_SYNC = "fallback_full_sync"


@dataclass
class DeltaQueryConfig:
    """Configuration for delta query operations"""

    enabled: bool = True
    storage_type: DeltaStorageType = DeltaStorageType.DATABASE
    token_ttl_seconds: int = 86400  # 24 hours
    sync_interval_seconds: int = 300  # 5 minutes
    fallback_threshold: int = 10  # errors before full sync
    max_page_size: int = 999
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    max_concurrent_syncs: int = 5
    enable_change_tracking: bool = True
    enable_conflict_resolution: bool = True


@dataclass
class DeltaSyncMetrics:
    """Metrics for delta synchronization operations"""

    sync_id: str
    resource_type: str
    user_id: str
    tenant_id: Optional[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    status: DeltaSyncStatus = DeltaSyncStatus.PENDING
    changes_processed: int = 0
    changes_applied: int = 0
    changes_skipped: int = 0
    errors_encountered: int = 0
    full_sync_triggered: bool = False
    performance_stats: Dict[str, Any] = field(default_factory=dict)


class DeltaTokenStorage:
    """Base class for delta token storage backends"""

    async def save_token(self, token: DeltaToken) -> None:
        """Save delta token"""
        raise NotImplementedError

    async def get_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[DeltaToken]:
        """Get delta token"""
        raise NotImplementedError

    async def delete_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Delete delta token"""
        raise NotImplementedError

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired tokens, return count of deleted tokens"""
        raise NotImplementedError


class DatabaseTokenStorage(DeltaTokenStorage):
    """Database-backed delta token storage"""

    def __init__(self, database: Database):
        self.db = database
        self._ensure_table_created = False

    async def _ensure_table(self) -> None:
        """Ensure delta tokens table exists"""
        if self._ensure_table_created:
            return

        async with self.db._connection_pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delta_tokens (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    resource_type VARCHAR(100) NOT NULL,
                    resource_id VARCHAR(255),
                    user_id VARCHAR(255) NOT NULL,
                    tenant_id VARCHAR(255),
                    token TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_used TIMESTAMP WITH TIME ZONE,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    metadata JSONB DEFAULT '{}',
                    UNIQUE(resource_type, resource_id, user_id, tenant_id)
                )
            """
            )

            # Create index for efficient lookups
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_delta_tokens_lookup
                ON delta_tokens(resource_type, user_id, tenant_id, expires_at)
            """
            )

        self._ensure_table_created = True

    async def save_token(self, token: DeltaToken) -> None:
        """Save delta token to database"""
        await self._ensure_table()

        async with self.db._connection_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO delta_tokens
                (resource_type, resource_id, user_id, tenant_id, token,
                 created_at, last_used, expires_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (resource_type, resource_id, user_id, tenant_id)
                DO UPDATE SET
                    token = EXCLUDED.token,
                    last_used = EXCLUDED.last_used,
                    expires_at = EXCLUDED.expires_at,
                    metadata = EXCLUDED.metadata
            """,
                token.resource_type,
                token.resource_id,
                token.user_id,
                token.tenant_id,
                token.token,
                token.created_at,
                token.last_used,
                token.expires_at,
                json.dumps(token.metadata),
            )

    async def get_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[DeltaToken]:
        """Get delta token from database"""
        await self._ensure_table()

        async with self.db._connection_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT resource_type, resource_id, user_id, tenant_id, token,
                       created_at, last_used, expires_at, metadata
                FROM delta_tokens
                WHERE resource_type = $1 AND resource_id = $2
                  AND user_id = $3 AND tenant_id = $4
                  AND (expires_at IS NULL OR expires_at > NOW())
            """,
                resource_type,
                resource_id,
                user_id,
                tenant_id,
            )

            if not row:
                return None

            return DeltaToken(
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                token=row["token"],
                user_id=row["user_id"],
                tenant_id=row["tenant_id"],
                created_at=row["created_at"],
                last_used=row["last_used"],
                expires_at=row["expires_at"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            )

    async def delete_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Delete delta token from database"""
        await self._ensure_table()

        async with self.db._connection_pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM delta_tokens
                WHERE resource_type = $1 AND resource_id = $2
                  AND user_id = $3 AND tenant_id = $4
            """,
                resource_type,
                resource_id,
                user_id,
                tenant_id,
            )

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired tokens"""
        await self._ensure_table()

        async with self.db._connection_pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM delta_tokens
                WHERE expires_at IS NOT NULL AND expires_at <= NOW()
            """
            )
            return int(result.split()[-1])  # Extract count from "DELETE n"


class FileTokenStorage(DeltaTokenStorage):
    """File-based delta token storage for development/testing"""

    def __init__(self, storage_dir: str = "/tmp/delta_tokens"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def _get_token_path(
        self, resource_type: str, resource_id: Optional[str], user_id: str, tenant_id: Optional[str]
    ) -> str:
        """Generate file path for token"""
        key_parts = [resource_type, resource_id or "global", user_id, tenant_id or "default"]
        key = "_".join(key_parts)
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.storage_dir, f"{key_hash}.json")

    async def save_token(self, token: DeltaToken) -> None:
        """Save delta token to file"""
        file_path = self._get_token_path(
            token.resource_type, token.resource_id, token.user_id, token.tenant_id
        )

        token_data = {
            "resource_type": token.resource_type,
            "resource_id": token.resource_id,
            "user_id": token.user_id,
            "tenant_id": token.tenant_id,
            "token": token.token,
            "created_at": token.created_at.isoformat(),
            "last_used": token.last_used.isoformat() if token.last_used else None,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "metadata": token.metadata,
        }

        with open(file_path, "w") as f:
            json.dump(token_data, f, indent=2)

    async def get_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[DeltaToken]:
        """Get delta token from file"""
        file_path = self._get_token_path(resource_type, resource_id, user_id, tenant_id)

        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r") as f:
                token_data = json.load(f)

            # Check if token is expired
            if token_data.get("expires_at"):
                expires_at = datetime.fromisoformat(token_data["expires_at"])
                if datetime.now(timezone.utc) > expires_at:
                    os.remove(file_path)
                    return None

            return DeltaToken(
                resource_type=token_data["resource_type"],
                resource_id=token_data["resource_id"],
                user_id=token_data["user_id"],
                tenant_id=token_data["tenant_id"],
                token=token_data["token"],
                created_at=datetime.fromisoformat(token_data["created_at"]),
                last_used=(
                    datetime.fromisoformat(token_data["last_used"])
                    if token_data.get("last_used")
                    else None
                ),
                expires_at=(
                    datetime.fromisoformat(token_data["expires_at"])
                    if token_data.get("expires_at")
                    else None
                ),
                metadata=token_data.get("metadata", {}),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "Failed to load delta token from file", file_path=file_path, error=str(e)
            )
            return None

    async def delete_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Delete delta token file"""
        file_path = self._get_token_path(resource_type, resource_id, user_id, tenant_id)
        if os.path.exists(file_path):
            os.remove(file_path)

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired token files"""
        count = 0
        for filename in os.listdir(self.storage_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(self.storage_dir, filename)
                try:
                    with open(file_path, "r") as f:
                        token_data = json.load(f)

                    if token_data.get("expires_at"):
                        expires_at = datetime.fromisoformat(token_data["expires_at"])
                        if datetime.now(timezone.utc) > expires_at:
                            os.remove(file_path)
                            count += 1
                except (json.JSONDecodeError, KeyError, ValueError, OSError):
                    # Remove corrupted files
                    os.remove(file_path)
                    count += 1

        return count


class DeltaQueryManager:
    """
    Main delta query manager for Microsoft Graph API
    Handles incremental synchronization with change detection and error recovery
    """

    def __init__(
        self,
        graph_client: EnhancedGraphClient,
        database: Database,
        config: Optional[DeltaQueryConfig] = None,
    ):
        self.graph_client = graph_client
        self.database = database
        self.config = config or self._load_config_from_env()
        self.performance_monitor = get_performance_monitor()

        # Initialize token storage backend
        self.token_storage = self._create_token_storage()

        # Error tracking for fallback logic
        self._error_counts: Dict[str, int] = {}
        self._sync_semaphore = asyncio.Semaphore(self.config.max_concurrent_syncs)

        logger.info(
            "Delta query manager initialized",
            storage_type=self.config.storage_type,
            enabled=self.config.enabled,
        )

    def _load_config_from_env(self) -> DeltaQueryConfig:
        """Load configuration from environment variables"""
        return DeltaQueryConfig(
            enabled=os.getenv("DELTA_QUERY_ENABLED", "true").lower() == "true",
            storage_type=DeltaStorageType(os.getenv("DELTA_TOKEN_STORAGE_TYPE", "database")),
            token_ttl_seconds=int(os.getenv("DELTA_TOKEN_TTL", "86400")),
            sync_interval_seconds=int(os.getenv("DELTA_SYNC_INTERVAL", "300")),
            fallback_threshold=int(os.getenv("DELTA_FALLBACK_THRESHOLD", "10")),
            max_page_size=int(os.getenv("DELTA_MAX_PAGE_SIZE", "999")),
            retry_attempts=int(os.getenv("DELTA_RETRY_ATTEMPTS", "3")),
            retry_delay_seconds=float(os.getenv("DELTA_RETRY_DELAY", "1.0")),
            max_concurrent_syncs=int(os.getenv("DELTA_MAX_CONCURRENT_SYNCS", "5")),
            enable_change_tracking=os.getenv("DELTA_ENABLE_CHANGE_TRACKING", "true").lower()
            == "true",
            enable_conflict_resolution=os.getenv("DELTA_ENABLE_CONFLICT_RESOLUTION", "true").lower()
            == "true",
        )

    def _create_token_storage(self) -> DeltaTokenStorage:
        """Create appropriate token storage backend"""
        if self.config.storage_type == DeltaStorageType.DATABASE:
            return DatabaseTokenStorage(self.database)
        elif self.config.storage_type == DeltaStorageType.FILE:
            storage_dir = os.getenv("DELTA_TOKEN_FILE_DIR", "/tmp/delta_tokens")
            return FileTokenStorage(storage_dir)
        else:
            # Future: implement Redis storage
            raise NotImplementedError(f"Storage type {self.config.storage_type} not implemented")

    @track_operation("delta_query_sync")
    async def sync_resource_changes(
        self,
        resource_type: str,
        user_id: str,
        tenant_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        force_full_sync: bool = False,
    ) -> DeltaSyncMetrics:
        """
        Synchronize changes for a resource using delta queries

        Args:
            resource_type: Type of resource (plans, tasks, etc.)
            user_id: User identifier
            tenant_id: Tenant identifier for multi-tenant support
            resource_id: Specific resource ID (optional, for resource-specific deltas)
            force_full_sync: Force full synchronization instead of delta

        Returns:
            Synchronization metrics and results
        """
        if not self.config.enabled:
            raise ValueError("Delta queries are disabled")

        sync_id = f"{resource_type}_{user_id}_{datetime.now().isoformat()}"
        metrics = DeltaSyncMetrics(
            sync_id=sync_id,
            resource_type=resource_type,
            user_id=user_id,
            tenant_id=tenant_id,
            start_time=datetime.now(timezone.utc),
        )

        async with self._sync_semaphore:
            try:
                metrics.status = DeltaSyncStatus.IN_PROGRESS

                # Check if we should force full sync due to errors
                error_key = f"{resource_type}_{user_id}_{tenant_id}"
                if (
                    self._error_counts.get(error_key, 0) >= self.config.fallback_threshold
                    or force_full_sync
                ):
                    logger.info(
                        "Performing full sync due to error threshold or force flag",
                        error_count=self._error_counts.get(error_key, 0),
                        force_full_sync=force_full_sync,
                    )
                    metrics.full_sync_triggered = True
                    result = await self._perform_full_sync(
                        resource_type, user_id, tenant_id, resource_id
                    )
                else:
                    result = await self._perform_delta_sync(
                        resource_type, user_id, tenant_id, resource_id
                    )

                # Process changes and update metrics
                metrics.changes_processed = len(result.changes)
                changes_applied, changes_skipped = await self._apply_changes(
                    result.changes, metrics
                )
                metrics.changes_applied = changes_applied
                metrics.changes_skipped = changes_skipped

                # Update delta token if sync was successful
                if result.next_delta_token:
                    await self._save_delta_token(
                        resource_type, resource_id, user_id, tenant_id, result.next_delta_token
                    )

                # Reset error count on successful sync
                if error_key in self._error_counts:
                    del self._error_counts[error_key]

                metrics.status = DeltaSyncStatus.COMPLETED

            except Exception as e:
                metrics.status = DeltaSyncStatus.FAILED
                metrics.errors_encountered += 1

                # Track errors for fallback logic
                error_key = f"{resource_type}_{user_id}_{tenant_id}"
                self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1

                logger.error(
                    "Delta sync failed",
                    sync_id=sync_id,
                    error=str(e),
                    error_count=self._error_counts[error_key],
                )
                raise

            finally:
                metrics.end_time = datetime.now(timezone.utc)
                await self._record_sync_metrics(metrics)

        return metrics

    async def _perform_delta_sync(
        self, resource_type: str, user_id: str, tenant_id: Optional[str], resource_id: Optional[str]
    ) -> DeltaResult:
        """Perform incremental delta synchronization"""
        # Get existing delta token
        delta_token = await self.token_storage.get_token(
            resource_type, resource_id, user_id, tenant_id
        )

        # Build delta query URL
        if resource_type == "plans":
            if resource_id:
                # Group-specific plans
                url = f"groups/{resource_id}/planner/plans/delta"
            else:
                # All plans for user
                url = "planner/plans/delta"
        elif resource_type == "tasks":
            if resource_id:
                # Plan-specific tasks
                url = f"planner/plans/{resource_id}/tasks/delta"
            else:
                # All tasks for user
                url = "planner/tasks/delta"
        else:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        # Add delta token to query if available
        query_params = {"$top": str(self.config.max_page_size)}
        if delta_token:
            query_params["$deltatoken"] = delta_token.token
            delta_token.update_last_used()
            await self.token_storage.save_token(delta_token)

        # Execute delta query with retry logic
        for attempt in range(self.config.retry_attempts):
            try:
                response = await self.graph_client.get(url, params=query_params)
                return self._parse_delta_response(
                    response, delta_token.token if delta_token else None
                )

            except Exception as e:
                if attempt == self.config.retry_attempts - 1:
                    raise

                logger.warning(
                    "Delta query attempt failed, retrying", attempt=attempt + 1, error=str(e)
                )
                await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))

    async def _perform_full_sync(
        self, resource_type: str, user_id: str, tenant_id: Optional[str], resource_id: Optional[str]
    ) -> DeltaResult:
        """Perform full synchronization as fallback"""
        logger.info("Performing full synchronization", resource_type=resource_type, user_id=user_id)

        # Clear existing delta token
        await self.token_storage.delete_token(resource_type, resource_id, user_id, tenant_id)

        # Build full query URL (without delta token)
        if resource_type == "plans":
            if resource_id:
                url = f"groups/{resource_id}/planner/plans"
            else:
                url = "planner/plans"
        elif resource_type == "tasks":
            if resource_id:
                url = f"planner/plans/{resource_id}/tasks"
            else:
                url = "planner/tasks"
        else:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        query_params = {"$top": str(self.config.max_page_size)}

        # Execute full query
        response = await self.graph_client.get(url, params=query_params)

        # Convert full response to delta format
        resources = response.get("value", [])
        changes = []

        for resource in resources:
            changes.append(
                ResourceChange(
                    change_type="created",  # Treat all as created in full sync
                    resource_type=resource_type,
                    resource_id=resource.get("id", ""),
                    resource_data=resource,
                    change_time=datetime.now(timezone.utc),
                    etag=resource.get("@odata.etag"),
                )
            )

        # Extract delta token from response
        next_delta_token = None
        delta_link = response.get("@odata.deltaLink")
        if delta_link and "$deltatoken=" in delta_link:
            next_delta_token = delta_link.split("$deltatoken=")[1].split("&")[0]

        return DeltaResult(
            delta_token="",  # No previous token for full sync
            next_delta_token=next_delta_token,
            changes=changes,
            has_more_changes=False,
        )

    def _parse_delta_response(
        self, response: Dict[str, Any], previous_token: Optional[str]
    ) -> DeltaResult:
        """Parse Microsoft Graph delta query response"""
        changes = []

        # Process each item in the response
        for item in response.get("value", []):
            # Determine change type
            change_type = "updated"  # Default
            if item.get("@removed"):
                change_type = "deleted"
            elif not previous_token:
                change_type = "created"

            resource_type = self._extract_resource_type(item, response.get("@odata.context", ""))
            resource_id = item.get("id", "")

            logger.debug(
                "Processing delta item",
                resource_type=resource_type,
                resource_id=resource_id,
                change_type=change_type,
            )

            changes.append(
                ResourceChange(
                    change_type=change_type,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    resource_data=item,
                    change_time=datetime.now(timezone.utc),
                    etag=item.get("@odata.etag"),
                    metadata={
                        "removed": item.get("@removed", {}),
                        "context": item.get("@odata.context", ""),
                    },
                )
            )

        # Extract next delta token
        next_delta_token = None
        delta_link = response.get("@odata.deltaLink")
        if delta_link and "$deltatoken=" in delta_link:
            next_delta_token = delta_link.split("$deltatoken=")[1].split("&")[0]

        # Check if there are more changes (nextLink)
        has_more_changes = "@odata.nextLink" in response

        return DeltaResult(
            delta_token=previous_token or "",
            next_delta_token=next_delta_token,
            changes=changes,
            has_more_changes=has_more_changes,
        )

    def _extract_resource_type(self, item: Dict[str, Any], response_context: str = "") -> str:
        """Extract resource type from Graph API item"""
        # Check item context first, then response context
        context = item.get("@odata.context", response_context)
        if "plans" in context:
            return "plan"
        elif "tasks" in context:
            return "task"
        elif "buckets" in context:
            return "bucket"
        else:
            return "unknown"

    async def _apply_changes(
        self, changes: List[ResourceChange], metrics: DeltaSyncMetrics
    ) -> Tuple[int, int]:
        """Apply resource changes to local storage"""
        applied_count = 0
        skipped_count = 0

        for change in changes:
            try:
                logger.debug(
                    "Applying change",
                    change_type=change.change_type,
                    resource_type=change.resource_type,
                    resource_id=change.resource_id,
                )

                if change.change_type == "deleted":
                    # Handle deletion
                    await self._handle_resource_deletion(change)
                    applied_count += 1

                elif change.change_type in ["created", "updated"]:
                    # Handle creation/update with conflict resolution
                    if await self._handle_resource_upsert(change):
                        applied_count += 1
                    else:
                        skipped_count += 1

            except Exception as e:
                logger.error(
                    "Failed to apply resource change",
                    change_type=change.change_type,
                    resource_id=change.resource_id,
                    error=str(e),
                )
                metrics.errors_encountered += 1
                skipped_count += 1

        return applied_count, skipped_count

    async def _handle_resource_deletion(self, change: ResourceChange) -> None:
        """Handle resource deletion"""
        if change.resource_type == "plan":
            # Delete plan and associated tasks
            await self.database.delete_plan(change.resource_id)
        elif change.resource_type == "task":
            # Delete task
            await self.database.delete_task(change.resource_id)

    async def _handle_resource_upsert(self, change: ResourceChange) -> bool:
        """Handle resource creation/update with conflict resolution"""
        if not self.config.enable_conflict_resolution:
            # Simple upsert without conflict resolution
            return await self._simple_upsert(change)

        # Get existing resource
        existing_resource = await self._get_existing_resource(change)

        if existing_resource and existing_resource.get("@odata.etag"):
            # Check for conflicts using etag
            if (
                change.etag
                and existing_resource["@odata.etag"] != change.etag
                and self._is_newer_change(existing_resource, change)
            ):
                # Local version is newer, skip update
                logger.info(
                    "Skipping update due to newer local version", resource_id=change.resource_id
                )
                return False

        # Apply the change
        return await self._simple_upsert(change)

    async def _simple_upsert(self, change: ResourceChange) -> bool:
        """Perform simple upsert without conflict resolution"""
        try:
            if change.resource_type == "plan":
                plan_data = self._convert_graph_plan_to_db_format(change.resource_data)
                await self.database.save_plan(plan_data)
            elif change.resource_type == "task":
                task_data = self._convert_graph_task_to_db_format(change.resource_data)
                await self.database.save_task(task_data)

            return True

        except Exception as e:
            logger.error(
                "Failed to upsert resource",
                resource_type=change.resource_type,
                resource_id=change.resource_id,
                error=str(e),
            )
            return False

    async def _get_existing_resource(self, change: ResourceChange) -> Optional[Dict[str, Any]]:
        """Get existing resource from local storage"""
        # This would need to be implemented based on your database schema
        # For now, return None to always allow updates
        return None

    def _is_newer_change(self, existing: Dict[str, Any], change: ResourceChange) -> bool:
        """Check if existing resource is newer than the change"""
        # Simple timestamp comparison - would need refinement for production
        existing_time = existing.get("lastModifiedDateTime")
        change_time = change.resource_data.get("lastModifiedDateTime")

        if not existing_time or not change_time:
            return False

        try:
            existing_dt = datetime.fromisoformat(existing_time.replace("Z", "+00:00"))
            change_dt = datetime.fromisoformat(change_time.replace("Z", "+00:00"))
            return existing_dt > change_dt
        except (ValueError, AttributeError):
            return False

    def _convert_graph_plan_to_db_format(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Graph API plan data to database format"""
        return {
            "graph_id": graph_data.get("id"),
            "title": graph_data.get("title", ""),
            "description": graph_data.get("description"),
            "owner_id": graph_data.get("owner", ""),
            "group_id": graph_data.get("container", {}).get("containerId"),
            "is_archived": False,  # Graph API doesn't have archived flag
            "plan_metadata": {
                "etag": graph_data.get("@odata.etag"),
                "created_datetime": graph_data.get("createdDateTime"),
                "last_modified_datetime": graph_data.get("lastModifiedDateTime"),
                "raw_data": graph_data,
            },
        }

    def _convert_graph_task_to_db_format(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Graph API task data to database format"""
        # Parse due date
        due_date = None
        if graph_data.get("dueDateTime"):
            try:
                due_date = datetime.fromisoformat(graph_data["dueDateTime"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Parse start date
        start_date = None
        if graph_data.get("startDateTime"):
            try:
                start_date = datetime.fromisoformat(
                    graph_data["startDateTime"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Parse completion
        completed_at = None
        if graph_data.get("completedDateTime"):
            try:
                completed_at = datetime.fromisoformat(
                    graph_data["completedDateTime"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        return {
            "graph_id": graph_data.get("id"),
            "plan_graph_id": graph_data.get("planId"),
            "title": graph_data.get("title", ""),
            "description": graph_data.get("description"),
            "bucket_id": graph_data.get("bucketId"),
            "assigned_to": (
                graph_data.get("assignments", {}).keys() if graph_data.get("assignments") else []
            ),
            "priority": graph_data.get("priority"),
            "due_date": due_date,
            "start_date": start_date,
            "completion_percentage": graph_data.get("percentComplete", 0),
            "is_completed": graph_data.get("percentComplete", 0) == 100,
            "completed_at": completed_at,
            "task_metadata": {
                "etag": graph_data.get("@odata.etag"),
                "created_datetime": graph_data.get("createdDateTime"),
                "last_modified_datetime": graph_data.get("lastModifiedDateTime"),
                "raw_data": graph_data,
            },
        }

    async def _save_delta_token(
        self,
        resource_type: str,
        resource_id: Optional[str],
        user_id: str,
        tenant_id: Optional[str],
        token: str,
    ) -> None:
        """Save delta token with expiration"""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.config.token_ttl_seconds)

        delta_token = DeltaToken(
            resource_type=resource_type,
            resource_id=resource_id,
            token=token,
            user_id=user_id,
            tenant_id=tenant_id,
            expires_at=expires_at,
        )

        await self.token_storage.save_token(delta_token)

    async def _record_sync_metrics(self, metrics: DeltaSyncMetrics) -> None:
        """Record synchronization metrics for monitoring"""
        duration = None
        if metrics.end_time:
            duration = (metrics.end_time - metrics.start_time).total_seconds()

        # Record in performance monitor
        self.performance_monitor.update_connection_stats()

        logger.info(
            "Delta sync completed",
            sync_id=metrics.sync_id,
            status=metrics.status,
            duration=duration,
            changes_processed=metrics.changes_processed,
            changes_applied=metrics.changes_applied,
            errors=metrics.errors_encountered,
        )

    async def cleanup_expired_tokens(self) -> int:
        """Clean up expired delta tokens"""
        return await self.token_storage.cleanup_expired_tokens()

    async def reset_delta_token(
        self,
        resource_type: str,
        user_id: str,
        tenant_id: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> None:
        """Reset delta token to force full sync on next operation"""
        await self.token_storage.delete_token(resource_type, resource_id, user_id, tenant_id)

        # Reset error count
        error_key = f"{resource_type}_{user_id}_{tenant_id}"
        if error_key in self._error_counts:
            del self._error_counts[error_key]

        logger.info(
            "Delta token reset", resource_type=resource_type, user_id=user_id, tenant_id=tenant_id
        )

    async def get_sync_status(
        self, resource_type: str, user_id: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get current synchronization status for a resource"""
        delta_token = await self.token_storage.get_token(resource_type, None, user_id, tenant_id)

        error_key = f"{resource_type}_{user_id}_{tenant_id}"
        error_count = self._error_counts.get(error_key, 0)

        return {
            "resource_type": resource_type,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "has_delta_token": delta_token is not None,
            "delta_token_created": delta_token.created_at.isoformat() if delta_token else None,
            "delta_token_last_used": (
                delta_token.last_used.isoformat() if delta_token and delta_token.last_used else None
            ),
            "delta_token_expires": (
                delta_token.expires_at.isoformat()
                if delta_token and delta_token.expires_at
                else None
            ),
            "error_count": error_count,
            "will_fallback_to_full_sync": error_count >= self.config.fallback_threshold,
            "config": {
                "enabled": self.config.enabled,
                "fallback_threshold": self.config.fallback_threshold,
                "sync_interval": self.config.sync_interval_seconds,
            },
        }
