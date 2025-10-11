"""
Microsoft Graph Conflict Resolution System
Story 8.1 Task 2.2: Conflict resolution for concurrent planner edits
"""

import os
import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import structlog

from ..database import Database
from ..cache import CacheService
from .client import GraphAPIClient

logger = structlog.get_logger(__name__)


class ConflictType(Enum):
    """Types of conflicts that can occur"""
    TASK_UPDATE = "task_update"
    PLAN_UPDATE = "plan_update"
    ASSIGNMENT_CONFLICT = "assignment_conflict"
    STATUS_CONFLICT = "status_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"


class ConflictResolutionStrategy(Enum):
    """Conflict resolution strategies"""
    LAST_WRITE_WINS = "last_write_wins"
    MERGE_FIELDS = "merge_fields"
    USER_CHOICE = "user_choice"
    VERSION_BASED = "version_based"
    PRIORITY_BASED = "priority_based"


@dataclass
class ConflictData:
    """Data structure for conflict information"""
    conflict_id: str
    conflict_type: ConflictType
    resource_id: str
    resource_type: str
    tenant_id: Optional[str]
    user_a_id: str
    user_b_id: str
    user_a_changes: Dict[str, Any]
    user_b_changes: Dict[str, Any]
    base_version: Dict[str, Any]
    current_version: Dict[str, Any]
    resolution_strategy: ConflictResolutionStrategy
    resolution_data: Optional[Dict[str, Any]]
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class ConflictResolver:
    """
    Handles conflict resolution for concurrent Microsoft Planner edits
    """

    def __init__(
        self,
        database: Database,
        cache_service: CacheService,
        graph_client: GraphAPIClient
    ):
        self.database = database
        self.cache_service = cache_service
        self.graph_client = graph_client

        # Configuration
        self.conflict_timeout = int(os.getenv("CONFLICT_TIMEOUT_MINUTES", "30")) * 60
        self.auto_resolve_enabled = os.getenv("AUTO_RESOLVE_CONFLICTS", "true").lower() == "true"
        self.max_resolution_attempts = int(os.getenv("MAX_RESOLUTION_ATTEMPTS", "3"))

        # In-memory conflict tracking
        self.active_conflicts: Dict[str, ConflictData] = {}
        self.resolution_queue: asyncio.Queue = asyncio.Queue()

        # Background task for conflict resolution
        self._resolver_task = None

    async def initialize(self) -> None:
        """Initialize conflict resolver"""
        try:
            # Load active conflicts from database
            await self._load_active_conflicts()

            # Start background conflict resolution task
            self._resolver_task = asyncio.create_task(self._process_conflicts())

            logger.info("Conflict resolver initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize conflict resolver", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown conflict resolver"""
        try:
            if self._resolver_task:
                self._resolver_task.cancel()
                await self._resolver_task

            logger.info("Conflict resolver shutdown completed")

        except Exception as e:
            logger.error("Error during conflict resolver shutdown", error=str(e))

    async def detect_and_resolve_conflict(
        self,
        resource_id: str,
        resource_type: str,
        user_id: str,
        proposed_changes: Dict[str, Any],
        current_etag: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Tuple[bool, Optional[ConflictData], Optional[Dict[str, Any]]]:
        """
        Detect conflicts and attempt resolution

        Args:
            resource_id: ID of the resource being modified
            resource_type: Type of resource (task, plan, etc.)
            user_id: ID of user making changes
            proposed_changes: Changes being proposed
            current_etag: Current ETag for optimistic concurrency
            tenant_id: Tenant ID for multi-tenant support

        Returns:
            Tuple[bool, Optional[ConflictData], Optional[Dict[str, Any]]]:
            (conflict_detected, conflict_data, resolved_changes)
        """
        try:
            # Get current version from Graph API
            current_version = await self._get_current_version(resource_id, resource_type, user_id)

            if not current_version:
                # Resource doesn't exist or user doesn't have access
                return False, None, proposed_changes

            # Check for ETag mismatch (optimistic concurrency conflict)
            if current_etag and current_version.get("@odata.etag") != current_etag:
                logger.info(
                    "ETag conflict detected",
                    resource_id=resource_id,
                    expected_etag=current_etag,
                    actual_etag=current_version.get("@odata.etag")
                )

                # Check if there's an active conflict for this resource
                existing_conflict = await self._find_active_conflict(resource_id, user_id)

                if existing_conflict:
                    # Update existing conflict with new changes
                    return await self._update_existing_conflict(
                        existing_conflict, user_id, proposed_changes
                    )
                else:
                    # Create new conflict
                    return await self._create_new_conflict(
                        resource_id, resource_type, user_id, proposed_changes,
                        current_version, tenant_id
                    )

            # No conflict detected
            return False, None, proposed_changes

        except Exception as e:
            logger.error(
                "Error in conflict detection",
                error=str(e),
                resource_id=resource_id,
                user_id=user_id
            )
            # In case of error, allow the operation to proceed
            return False, None, proposed_changes

    async def resolve_conflict(
        self,
        conflict_id: str,
        resolution_strategy: ConflictResolutionStrategy,
        resolution_data: Optional[Dict[str, Any]] = None,
        resolved_by: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a specific conflict

        Args:
            conflict_id: ID of conflict to resolve
            resolution_strategy: Strategy to use for resolution
            resolution_data: Additional data for resolution
            resolved_by: User ID who resolved the conflict

        Returns:
            Optional[Dict[str, Any]]: Resolved changes to apply
        """
        try:
            conflict = self.active_conflicts.get(conflict_id)
            if not conflict:
                # Try to load from database
                conflict = await self._load_conflict_from_database(conflict_id)
                if not conflict:
                    logger.warning("Conflict not found", conflict_id=conflict_id)
                    return None

            # Apply resolution strategy
            resolved_changes = await self._apply_resolution_strategy(
                conflict, resolution_strategy, resolution_data
            )

            if resolved_changes is not None:
                # Mark conflict as resolved
                conflict.resolved = True
                conflict.resolved_at = datetime.now(timezone.utc)
                conflict.resolved_by = resolved_by
                conflict.resolution_strategy = resolution_strategy
                conflict.resolution_data = resolution_data

                # Update database
                await self._store_conflict_in_database(conflict)

                # Remove from active conflicts
                self.active_conflicts.pop(conflict_id, None)

                logger.info(
                    "Conflict resolved successfully",
                    conflict_id=conflict_id,
                    strategy=resolution_strategy.value,
                    resolved_by=resolved_by
                )

                return resolved_changes

            return None

        except Exception as e:
            logger.error(
                "Error resolving conflict",
                error=str(e),
                conflict_id=conflict_id
            )
            return None

    async def get_conflicts_for_user(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        include_resolved: bool = False
    ) -> List[ConflictData]:
        """
        Get conflicts for a specific user

        Args:
            user_id: User ID
            tenant_id: Tenant ID for filtering
            include_resolved: Whether to include resolved conflicts

        Returns:
            List[ConflictData]: List of conflicts
        """
        try:
            conflicts = []

            # Check active conflicts
            for conflict in self.active_conflicts.values():
                if (conflict.user_a_id == user_id or conflict.user_b_id == user_id):
                    if tenant_id is None or conflict.tenant_id == tenant_id:
                        conflicts.append(conflict)

            # Load from database if including resolved conflicts
            if include_resolved:
                db_conflicts = await self._get_user_conflicts_from_database(
                    user_id, tenant_id, include_resolved
                )
                conflicts.extend(db_conflicts)

            return conflicts

        except Exception as e:
            logger.error(
                "Error getting conflicts for user",
                error=str(e),
                user_id=user_id
            )
            return []

    async def get_conflict_statistics(
        self,
        tenant_id: Optional[str] = None,
        time_period_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get conflict statistics for monitoring

        Args:
            tenant_id: Tenant ID for filtering
            time_period_hours: Time period for statistics

        Returns:
            Dict[str, Any]: Conflict statistics
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=time_period_hours)

            stats = {
                "active_conflicts": len([
                    c for c in self.active_conflicts.values()
                    if (tenant_id is None or c.tenant_id == tenant_id)
                ]),
                "resolved_conflicts": 0,
                "auto_resolved": 0,
                "manual_resolved": 0,
                "conflict_types": {},
                "resolution_strategies": {},
                "average_resolution_time_minutes": 0
            }

            # Get statistics from database
            db_stats = await self._get_conflict_statistics_from_database(
                tenant_id, since
            )
            stats.update(db_stats)

            return stats

        except Exception as e:
            logger.error(
                "Error getting conflict statistics",
                error=str(e),
                tenant_id=tenant_id
            )
            return {}

    # Private methods

    async def _get_current_version(
        self,
        resource_id: str,
        resource_type: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get current version of resource from Graph API"""
        try:
            if resource_type == "task":
                endpoint = f"/planner/tasks/{resource_id}"
            elif resource_type == "plan":
                endpoint = f"/planner/plans/{resource_id}"
            else:
                logger.warning("Unknown resource type", resource_type=resource_type)
                return None

            return await self.graph_client._make_request("GET", endpoint, user_id)

        except Exception as e:
            logger.error(
                "Error getting current version",
                error=str(e),
                resource_id=resource_id,
                resource_type=resource_type
            )
            return None

    async def _find_active_conflict(
        self,
        resource_id: str,
        user_id: str
    ) -> Optional[ConflictData]:
        """Find active conflict for resource and user"""
        for conflict in self.active_conflicts.values():
            if (conflict.resource_id == resource_id and
                (conflict.user_a_id == user_id or conflict.user_b_id == user_id)):
                return conflict
        return None

    async def _create_new_conflict(
        self,
        resource_id: str,
        resource_type: str,
        user_id: str,
        proposed_changes: Dict[str, Any],
        current_version: Dict[str, Any],
        tenant_id: Optional[str]
    ) -> Tuple[bool, ConflictData, None]:
        """Create new conflict record"""
        try:
            # Determine conflict type
            conflict_type = self._determine_conflict_type(proposed_changes, current_version)

            # Get base version from cache or assume current is base
            base_version = await self.cache_service.get(
                f"resource_version:{resource_id}:base"
            ) or current_version

            # Create conflict data
            conflict = ConflictData(
                conflict_id=str(uuid.uuid4()),
                conflict_type=conflict_type,
                resource_id=resource_id,
                resource_type=resource_type,
                tenant_id=tenant_id,
                user_a_id=user_id,
                user_b_id="system",  # Will be updated when second user conflicts
                user_a_changes=proposed_changes,
                user_b_changes={},
                base_version=base_version,
                current_version=current_version,
                resolution_strategy=ConflictResolutionStrategy.LAST_WRITE_WINS
            )

            # Store conflict
            self.active_conflicts[conflict.conflict_id] = conflict
            await self._store_conflict_in_database(conflict)

            # Add to resolution queue if auto-resolve is enabled
            if self.auto_resolve_enabled:
                await self.resolution_queue.put(conflict.conflict_id)

            logger.info(
                "New conflict created",
                conflict_id=conflict.conflict_id,
                resource_id=resource_id,
                conflict_type=conflict_type.value
            )

            return True, conflict, None

        except Exception as e:
            logger.error(
                "Error creating new conflict",
                error=str(e),
                resource_id=resource_id,
                user_id=user_id
            )
            return False, None, None

    async def _update_existing_conflict(
        self,
        conflict: ConflictData,
        user_id: str,
        proposed_changes: Dict[str, Any]
    ) -> Tuple[bool, ConflictData, None]:
        """Update existing conflict with new changes"""
        try:
            if conflict.user_a_id == user_id:
                conflict.user_a_changes = proposed_changes
            elif conflict.user_b_id == user_id or conflict.user_b_id == "system":
                conflict.user_b_id = user_id
                conflict.user_b_changes = proposed_changes

            # Update database
            await self._store_conflict_in_database(conflict)

            logger.info(
                "Conflict updated with new changes",
                conflict_id=conflict.conflict_id,
                user_id=user_id
            )

            return True, conflict, None

        except Exception as e:
            logger.error(
                "Error updating existing conflict",
                error=str(e),
                conflict_id=conflict.conflict_id,
                user_id=user_id
            )
            return False, conflict, None

    def _determine_conflict_type(
        self,
        proposed_changes: Dict[str, Any],
        current_version: Dict[str, Any]
    ) -> ConflictType:
        """Determine the type of conflict based on changes"""
        # Check for assignment conflicts
        if "assignments" in proposed_changes:
            return ConflictType.ASSIGNMENT_CONFLICT

        # Check for status conflicts
        if any(field in proposed_changes for field in ["percentComplete", "completedBy"]):
            return ConflictType.STATUS_CONFLICT

        # Check for dependency conflicts
        if any(field in proposed_changes for field in ["orderHint", "dependencies"]):
            return ConflictType.DEPENDENCY_CONFLICT

        # Default to task/plan update based on resource type
        if "planId" in current_version:
            return ConflictType.TASK_UPDATE
        else:
            return ConflictType.PLAN_UPDATE

    async def _apply_resolution_strategy(
        self,
        conflict: ConflictData,
        strategy: ConflictResolutionStrategy,
        resolution_data: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Apply conflict resolution strategy"""
        try:
            if strategy == ConflictResolutionStrategy.LAST_WRITE_WINS:
                return await self._resolve_last_write_wins(conflict)

            elif strategy == ConflictResolutionStrategy.MERGE_FIELDS:
                return await self._resolve_merge_fields(conflict)

            elif strategy == ConflictResolutionStrategy.USER_CHOICE:
                return await self._resolve_user_choice(conflict, resolution_data)

            elif strategy == ConflictResolutionStrategy.VERSION_BASED:
                return await self._resolve_version_based(conflict)

            elif strategy == ConflictResolutionStrategy.PRIORITY_BASED:
                return await self._resolve_priority_based(conflict)

            else:
                logger.warning("Unknown resolution strategy", strategy=strategy.value)
                return None

        except Exception as e:
            logger.error(
                "Error applying resolution strategy",
                error=str(e),
                strategy=strategy.value
            )
            return None

    async def _resolve_last_write_wins(self, conflict: ConflictData) -> Dict[str, Any]:
        """Resolve using last write wins strategy"""
        # Use the changes from the user who made the most recent modification
        if conflict.user_b_changes:
            return conflict.user_b_changes
        else:
            return conflict.user_a_changes

    async def _resolve_merge_fields(self, conflict: ConflictData) -> Dict[str, Any]:
        """Resolve by merging non-conflicting fields"""
        merged_changes = conflict.user_a_changes.copy()

        # Merge user B changes that don't conflict
        for field, value in conflict.user_b_changes.items():
            if field not in conflict.user_a_changes:
                merged_changes[field] = value
            elif field in ["assignments"] and isinstance(value, dict):
                # Special handling for assignments - merge user assignments
                if field not in merged_changes:
                    merged_changes[field] = {}
                merged_changes[field].update(value)

        return merged_changes

    async def _resolve_user_choice(
        self,
        conflict: ConflictData,
        resolution_data: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Resolve using user's choice"""
        if not resolution_data or "chosen_changes" not in resolution_data:
            logger.warning("No user choice provided for resolution")
            return None

        return resolution_data["chosen_changes"]

    async def _resolve_version_based(self, conflict: ConflictData) -> Dict[str, Any]:
        """Resolve based on version numbers or timestamps"""
        # Simple timestamp-based resolution
        if conflict.created_at:
            # Use newer changes
            return conflict.user_b_changes if conflict.user_b_changes else conflict.user_a_changes
        else:
            return conflict.user_a_changes

    async def _resolve_priority_based(self, conflict: ConflictData) -> Dict[str, Any]:
        """Resolve based on user priority or roles"""
        # Simple implementation - could be enhanced with user role checking
        # For now, prefer user A (original modifier)
        return conflict.user_a_changes

    async def _process_conflicts(self) -> None:
        """Background task to process conflict resolution queue"""
        while True:
            try:
                # Get conflict from queue with timeout
                conflict_id = await asyncio.wait_for(
                    self.resolution_queue.get(),
                    timeout=10.0
                )

                # Attempt auto-resolution
                await self._attempt_auto_resolution(conflict_id)

            except asyncio.TimeoutError:
                # Normal timeout, continue processing
                continue
            except asyncio.CancelledError:
                logger.info("Conflict processor task cancelled")
                break
            except Exception as e:
                logger.error("Error in conflict processor", error=str(e))
                await asyncio.sleep(1)

    async def _attempt_auto_resolution(self, conflict_id: str) -> None:
        """Attempt automatic conflict resolution"""
        try:
            conflict = self.active_conflicts.get(conflict_id)
            if not conflict:
                return

            # Check if conflict has timed out
            if (datetime.now(timezone.utc) - conflict.created_at).total_seconds() > self.conflict_timeout:
                logger.info("Conflict timed out, auto-resolving", conflict_id=conflict_id)
                await self.resolve_conflict(
                    conflict_id,
                    ConflictResolutionStrategy.LAST_WRITE_WINS,
                    resolved_by="system_timeout"
                )

        except Exception as e:
            logger.error(
                "Error in auto-resolution",
                error=str(e),
                conflict_id=conflict_id
            )

    # Database methods

    async def _load_active_conflicts(self) -> None:
        """Load active conflicts from database"""
        try:
            query = """
            SELECT conflict_data FROM conflicts
            WHERE resolved = false
            AND created_at > NOW() - INTERVAL '24 hours'
            """

            rows = await self.database.fetch_all(query)

            for row in rows:
                conflict_data = row["conflict_data"]
                if isinstance(conflict_data, str):
                    conflict_data = json.loads(conflict_data)

                conflict = ConflictData(**conflict_data)
                self.active_conflicts[conflict.conflict_id] = conflict

            logger.info(f"Loaded {len(rows)} active conflicts from database")

        except Exception as e:
            logger.error("Failed to load active conflicts", error=str(e))

    async def _load_conflict_from_database(self, conflict_id: str) -> Optional[ConflictData]:
        """Load specific conflict from database"""
        try:
            query = "SELECT conflict_data FROM conflicts WHERE conflict_id = :conflict_id"
            row = await self.database.fetch_one(query, {"conflict_id": conflict_id})

            if row:
                conflict_data = row["conflict_data"]
                if isinstance(conflict_data, str):
                    conflict_data = json.loads(conflict_data)
                return ConflictData(**conflict_data)

            return None

        except Exception as e:
            logger.error(
                "Failed to load conflict from database",
                error=str(e),
                conflict_id=conflict_id
            )
            return None

    async def _store_conflict_in_database(self, conflict: ConflictData) -> None:
        """Store conflict in database"""
        try:
            query = """
            INSERT INTO conflicts (
                id, conflict_id, resource_id, resource_type, tenant_id,
                user_a_id, user_b_id, conflict_type, resolved,
                conflict_data, created_at, updated_at
            ) VALUES (
                :id, :conflict_id, :resource_id, :resource_type, :tenant_id,
                :user_a_id, :user_b_id, :conflict_type, :resolved,
                :conflict_data, :created_at, :updated_at
            )
            ON CONFLICT (conflict_id) DO UPDATE SET
                conflict_data = EXCLUDED.conflict_data,
                resolved = EXCLUDED.resolved,
                updated_at = EXCLUDED.updated_at
            """

            await self.database.execute(query, {
                "id": str(uuid.uuid4()),
                "conflict_id": conflict.conflict_id,
                "resource_id": conflict.resource_id,
                "resource_type": conflict.resource_type,
                "tenant_id": conflict.tenant_id,
                "user_a_id": conflict.user_a_id,
                "user_b_id": conflict.user_b_id,
                "conflict_type": conflict.conflict_type.value,
                "resolved": conflict.resolved,
                "conflict_data": asdict(conflict),
                "created_at": conflict.created_at,
                "updated_at": datetime.now(timezone.utc)
            })

        except Exception as e:
            logger.error(
                "Failed to store conflict in database",
                error=str(e),
                conflict_id=conflict.conflict_id
            )
            raise

    async def _get_user_conflicts_from_database(
        self,
        user_id: str,
        tenant_id: Optional[str],
        include_resolved: bool
    ) -> List[ConflictData]:
        """Get user conflicts from database"""
        try:
            conditions = ["(user_a_id = :user_id OR user_b_id = :user_id)"]
            params = {"user_id": user_id}

            if tenant_id:
                conditions.append("tenant_id = :tenant_id")
                params["tenant_id"] = tenant_id

            if not include_resolved:
                conditions.append("resolved = false")

            query = f"""
            SELECT conflict_data FROM conflicts
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT 100
            """

            rows = await self.database.fetch_all(query, params)

            conflicts = []
            for row in rows:
                conflict_data = row["conflict_data"]
                if isinstance(conflict_data, str):
                    conflict_data = json.loads(conflict_data)
                conflicts.append(ConflictData(**conflict_data))

            return conflicts

        except Exception as e:
            logger.error(
                "Failed to get user conflicts from database",
                error=str(e),
                user_id=user_id
            )
            return []

    async def _get_conflict_statistics_from_database(
        self,
        tenant_id: Optional[str],
        since: datetime
    ) -> Dict[str, Any]:
        """Get conflict statistics from database"""
        try:
            conditions = ["created_at >= :since"]
            params = {"since": since}

            if tenant_id:
                conditions.append("tenant_id = :tenant_id")
                params["tenant_id"] = tenant_id

            where_clause = " AND ".join(conditions)

            # Get basic statistics
            query = f"""
            SELECT
                COUNT(*) as total_conflicts,
                COUNT(CASE WHEN resolved = true THEN 1 END) as resolved_conflicts,
                COUNT(CASE WHEN resolved = true AND resolved_by = 'system_timeout' THEN 1 END) as auto_resolved,
                COUNT(CASE WHEN resolved = true AND resolved_by != 'system_timeout' THEN 1 END) as manual_resolved,
                AVG(CASE WHEN resolved = true THEN EXTRACT(EPOCH FROM (resolved_at - created_at))/60 END) as avg_resolution_time_minutes
            FROM conflicts
            WHERE {where_clause}
            """

            row = await self.database.fetch_one(query, params)

            stats = {
                "total_conflicts": row["total_conflicts"] or 0,
                "resolved_conflicts": row["resolved_conflicts"] or 0,
                "auto_resolved": row["auto_resolved"] or 0,
                "manual_resolved": row["manual_resolved"] or 0,
                "average_resolution_time_minutes": float(row["avg_resolution_time_minutes"] or 0)
            }

            # Get conflict type distribution
            type_query = f"""
            SELECT conflict_type, COUNT(*) as count
            FROM conflicts
            WHERE {where_clause}
            GROUP BY conflict_type
            """

            type_rows = await self.database.fetch_all(type_query, params)
            stats["conflict_types"] = {row["conflict_type"]: row["count"] for row in type_rows}

            return stats

        except Exception as e:
            logger.error(
                "Failed to get conflict statistics from database",
                error=str(e),
                tenant_id=tenant_id
            )
            return {}