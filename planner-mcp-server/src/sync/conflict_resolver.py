"""
Conflict Resolution System for Bidirectional Planner Synchronization
Story 8.1 Task 2.2: Advanced conflict resolution for concurrent edits

Implements comprehensive conflict detection and resolution strategies
for Microsoft Planner task and plan synchronization.
"""

import uuid
import json
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..models.graph_models import ResourceChange
from ..database import Database
from ..cache import CacheService

logger = structlog.get_logger(__name__)


class ConflictType(str, Enum):
    """Types of synchronization conflicts"""

    CONCURRENT_EDIT = "concurrent_edit"
    FIELD_CONFLICT = "field_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    PERMISSION_CONFLICT = "permission_conflict"
    SCHEMA_CONFLICT = "schema_conflict"


class ResolutionStrategy(str, Enum):
    """Conflict resolution strategies"""

    LAST_WRITE_WINS = "last_write_wins"
    FIRST_WRITE_WINS = "first_write_wins"
    MERGE_FIELDS = "merge_fields"
    MANUAL_RESOLUTION = "manual_resolution"
    ROLLBACK = "rollback"
    BRANCH_VERSION = "branch_version"


class ConflictSeverity(str, Enum):
    """Severity levels for conflicts"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ConflictContext:
    """Context information for a conflict"""

    conflict_id: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    resource_type: str
    resource_id: str
    tenant_id: Optional[str]
    user_id: str

    # Conflicting versions
    local_version: Dict[str, Any]
    remote_version: Dict[str, Any]

    # Metadata
    local_etag: Optional[str] = None
    remote_etag: Optional[str] = None
    local_timestamp: Optional[datetime] = None
    remote_timestamp: Optional[datetime] = None

    # Conflict details
    conflicting_fields: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Resolution tracking
    resolution_strategy: Optional[ResolutionStrategy] = None
    resolution_timestamp: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ResolutionResult:
    """Result of conflict resolution"""

    conflict_id: str
    strategy_used: ResolutionStrategy
    resolved_version: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    requires_manual_intervention: bool = False
    backup_versions: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class ConflictDetector:
    """Detects conflicts between local and remote resource versions"""

    def __init__(self, database: Database, cache_service: CacheService):
        self.database = database
        self.cache_service = cache_service

        # Fields that are commonly conflicted
        self.sensitive_fields = {
            "plan": ["title", "description", "assignments"],
            "task": ["title", "description", "dueDateTime", "percentComplete", "assignments"]
        }

        # Fields that should never be merged
        self.exclusive_fields = {
            "plan": ["id", "createdDateTime", "etag"],
            "task": ["id", "createdDateTime", "etag", "planId"]
        }

    async def detect_conflict(
        self,
        resource_type: str,
        resource_id: str,
        local_version: Dict[str, Any],
        remote_version: Dict[str, Any],
        user_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[ConflictContext]:
        """
        Detect conflicts between local and remote versions

        Args:
            resource_type: Type of resource (plan/task)
            resource_id: Resource identifier
            local_version: Current local version
            remote_version: Incoming remote version
            user_id: User making the change
            tenant_id: Tenant context

        Returns:
            ConflictContext if conflict detected, None otherwise
        """
        try:
            # Extract etags and timestamps
            local_etag = local_version.get("@odata.etag")
            remote_etag = remote_version.get("@odata.etag")

            local_timestamp = self._parse_timestamp(
                local_version.get("lastModifiedDateTime")
            )
            remote_timestamp = self._parse_timestamp(
                remote_version.get("lastModifiedDateTime")
            )

            # Check for concurrent edits using etags
            if local_etag and remote_etag and local_etag != remote_etag:
                # Potential conflict - analyze deeper
                conflicting_fields = await self._find_conflicting_fields(
                    resource_type, local_version, remote_version
                )

                if conflicting_fields:
                    severity = self._assess_conflict_severity(
                        resource_type, conflicting_fields, local_version, remote_version
                    )

                    conflict_id = str(uuid.uuid4())

                    conflict = ConflictContext(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.CONCURRENT_EDIT,
                        severity=severity,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        local_version=local_version,
                        remote_version=remote_version,
                        local_etag=local_etag,
                        remote_etag=remote_etag,
                        local_timestamp=local_timestamp,
                        remote_timestamp=remote_timestamp,
                        conflicting_fields=conflicting_fields,
                        metadata={
                            "detection_method": "etag_comparison",
                            "field_count": len(conflicting_fields)
                        }
                    )

                    # Store conflict for tracking
                    await self._store_conflict(conflict)

                    logger.warning(
                        "Conflict detected",
                        conflict_id=conflict_id,
                        resource_id=resource_id,
                        conflicting_fields=conflicting_fields,
                        severity=severity
                    )

                    return conflict

            # Check for dependency conflicts
            dependency_conflict = await self._check_dependency_conflicts(
                resource_type, resource_id, local_version, remote_version, user_id, tenant_id
            )

            if dependency_conflict:
                return dependency_conflict

            return None

        except Exception as e:
            logger.error(
                "Error detecting conflict",
                resource_id=resource_id,
                error=str(e)
            )
            return None

    async def _find_conflicting_fields(
        self,
        resource_type: str,
        local_version: Dict[str, Any],
        remote_version: Dict[str, Any]
    ) -> List[str]:
        """Find specific fields that conflict between versions"""
        conflicting_fields = []

        # Get sensitive fields for this resource type
        sensitive = self.sensitive_fields.get(resource_type, [])

        # Compare each sensitive field
        for field in sensitive:
            local_value = local_version.get(field)
            remote_value = remote_version.get(field)

            # Deep comparison for complex values
            if not self._values_equal(local_value, remote_value):
                conflicting_fields.append(field)

        # Check for unexpected field additions/removals
        local_keys = set(local_version.keys())
        remote_keys = set(remote_version.keys())

        # Fields present in one but not the other
        asymmetric_fields = (local_keys - remote_keys) | (remote_keys - local_keys)

        for field in asymmetric_fields:
            if field not in self.exclusive_fields.get(resource_type, []):
                conflicting_fields.append(field)

        return conflicting_fields

    def _values_equal(self, value1: Any, value2: Any) -> bool:
        """Deep equality comparison for field values"""
        if value1 is None and value2 is None:
            return True

        if value1 is None or value2 is None:
            return False

        # Handle different types
        if type(value1) != type(value2):
            # Try string comparison for type mismatches
            return str(value1) == str(value2)

        # Handle complex objects
        if isinstance(value1, dict):
            return self._dict_equal(value1, value2)
        elif isinstance(value1, list):
            return self._list_equal(value1, value2)
        else:
            return value1 == value2

    def _dict_equal(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> bool:
        """Deep dictionary comparison"""
        if set(dict1.keys()) != set(dict2.keys()):
            return False

        for key in dict1:
            if not self._values_equal(dict1[key], dict2[key]):
                return False

        return True

    def _list_equal(self, list1: List[Any], list2: List[Any]) -> bool:
        """Deep list comparison"""
        if len(list1) != len(list2):
            return False

        # Sort lists if they contain simple comparable values
        try:
            sorted1 = sorted(list1)
            sorted2 = sorted(list2)
            return all(self._values_equal(a, b) for a, b in zip(sorted1, sorted2))
        except TypeError:
            # Fall back to order-dependent comparison
            return all(self._values_equal(a, b) for a, b in zip(list1, list2))

    def _assess_conflict_severity(
        self,
        resource_type: str,
        conflicting_fields: List[str],
        local_version: Dict[str, Any],
        remote_version: Dict[str, Any]
    ) -> ConflictSeverity:
        """Assess the severity of a conflict"""
        # Critical fields that indicate high severity
        critical_fields = {
            "plan": ["title", "owner"],
            "task": ["title", "planId", "bucketId"]
        }

        # High impact fields
        high_impact_fields = {
            "plan": ["description", "container"],
            "task": ["description", "dueDateTime", "percentComplete"]
        }

        # Check for critical conflicts
        for field in conflicting_fields:
            if field in critical_fields.get(resource_type, []):
                return ConflictSeverity.CRITICAL

        # Check for high impact conflicts
        high_impact_count = sum(
            1 for field in conflicting_fields
            if field in high_impact_fields.get(resource_type, [])
        )

        if high_impact_count >= 2:
            return ConflictSeverity.HIGH
        elif high_impact_count == 1:
            return ConflictSeverity.MEDIUM
        else:
            return ConflictSeverity.LOW

    async def _check_dependency_conflicts(
        self,
        resource_type: str,
        resource_id: str,
        local_version: Dict[str, Any],
        remote_version: Dict[str, Any],
        user_id: str,
        tenant_id: Optional[str]
    ) -> Optional[ConflictContext]:
        """Check for dependency-related conflicts"""
        if resource_type == "task":
            # Check if plan still exists
            plan_id = remote_version.get("planId")
            if plan_id:
                plan_exists = await self._check_plan_exists(plan_id, tenant_id)
                if not plan_exists:
                    conflict_id = str(uuid.uuid4())

                    return ConflictContext(
                        conflict_id=conflict_id,
                        conflict_type=ConflictType.DEPENDENCY_CONFLICT,
                        severity=ConflictSeverity.HIGH,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        local_version=local_version,
                        remote_version=remote_version,
                        metadata={
                            "missing_dependency": "plan",
                            "missing_plan_id": plan_id
                        }
                    )

        return None

    async def _check_plan_exists(self, plan_id: str, tenant_id: Optional[str]) -> bool:
        """Check if a plan exists in the database"""
        try:
            query = "SELECT 1 FROM plans WHERE graph_id = $1"
            params = [plan_id]

            if tenant_id:
                # Add tenant filtering if available
                pass

            async with self.database._connection_pool.acquire() as conn:
                result = await conn.fetchrow(query, *params)
                return result is not None

        except Exception as e:
            logger.error("Error checking plan existence", plan_id=plan_id, error=str(e))
            return False

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp string"""
        if not timestamp_str:
            return None

        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    async def _store_conflict(self, conflict: ConflictContext) -> None:
        """Store conflict in database for tracking and analysis"""
        try:
            query = """
            INSERT INTO conflict_resolutions (
                conflict_id, conflict_type, severity, resource_type, resource_id,
                tenant_id, user_id, conflicting_fields, local_version, remote_version,
                local_etag, remote_etag, local_timestamp, remote_timestamp,
                metadata, created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
            )
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    conflict.conflict_id,
                    conflict.conflict_type,
                    conflict.severity,
                    conflict.resource_type,
                    conflict.resource_id,
                    conflict.tenant_id,
                    conflict.user_id,
                    json.dumps(conflict.conflicting_fields),
                    json.dumps(conflict.local_version),
                    json.dumps(conflict.remote_version),
                    conflict.local_etag,
                    conflict.remote_etag,
                    conflict.local_timestamp,
                    conflict.remote_timestamp,
                    json.dumps(conflict.metadata),
                    conflict.created_at
                )

        except Exception as e:
            logger.error("Failed to store conflict", conflict_id=conflict.conflict_id, error=str(e))


class ConflictResolver:
    """Resolves detected conflicts using various strategies"""

    def __init__(self, database: Database, cache_service: CacheService):
        self.database = database
        self.cache_service = cache_service

        # Default resolution strategies by conflict type and severity
        self.strategy_matrix = {
            (ConflictType.CONCURRENT_EDIT, ConflictSeverity.LOW): ResolutionStrategy.LAST_WRITE_WINS,
            (ConflictType.CONCURRENT_EDIT, ConflictSeverity.MEDIUM): ResolutionStrategy.MERGE_FIELDS,
            (ConflictType.CONCURRENT_EDIT, ConflictSeverity.HIGH): ResolutionStrategy.MANUAL_RESOLUTION,
            (ConflictType.CONCURRENT_EDIT, ConflictSeverity.CRITICAL): ResolutionStrategy.MANUAL_RESOLUTION,
            (ConflictType.DEPENDENCY_CONFLICT, ConflictSeverity.HIGH): ResolutionStrategy.ROLLBACK,
            (ConflictType.PERMISSION_CONFLICT, ConflictSeverity.MEDIUM): ResolutionStrategy.MANUAL_RESOLUTION,
        }

    async def resolve_conflict(
        self,
        conflict: ConflictContext,
        preferred_strategy: Optional[ResolutionStrategy] = None
    ) -> ResolutionResult:
        """
        Resolve a conflict using appropriate strategy

        Args:
            conflict: The conflict to resolve
            preferred_strategy: Override automatic strategy selection

        Returns:
            ResolutionResult with resolved version and metadata
        """
        try:
            # Determine resolution strategy
            strategy = preferred_strategy or self._select_strategy(conflict)

            # Apply resolution strategy
            if strategy == ResolutionStrategy.LAST_WRITE_WINS:
                result = await self._resolve_last_write_wins(conflict)
            elif strategy == ResolutionStrategy.FIRST_WRITE_WINS:
                result = await self._resolve_first_write_wins(conflict)
            elif strategy == ResolutionStrategy.MERGE_FIELDS:
                result = await self._resolve_merge_fields(conflict)
            elif strategy == ResolutionStrategy.MANUAL_RESOLUTION:
                result = await self._prepare_manual_resolution(conflict)
            elif strategy == ResolutionStrategy.ROLLBACK:
                result = await self._resolve_rollback(conflict)
            elif strategy == ResolutionStrategy.BRANCH_VERSION:
                result = await self._resolve_branch_version(conflict)
            else:
                raise ValueError(f"Unknown resolution strategy: {strategy}")

            # Update conflict record with resolution
            if result.success:
                await self._update_conflict_resolution(conflict, result)

            logger.info(
                "Conflict resolved",
                conflict_id=conflict.conflict_id,
                strategy=strategy,
                success=result.success,
                manual_required=result.requires_manual_intervention
            )

            return result

        except Exception as e:
            logger.error(
                "Error resolving conflict",
                conflict_id=conflict.conflict_id,
                error=str(e)
            )

            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                strategy_used=strategy or ResolutionStrategy.MANUAL_RESOLUTION,
                resolved_version={},
                success=False,
                error_message=str(e),
                requires_manual_intervention=True
            )

    def _select_strategy(self, conflict: ConflictContext) -> ResolutionStrategy:
        """Select appropriate resolution strategy based on conflict characteristics"""
        key = (conflict.conflict_type, conflict.severity)
        return self.strategy_matrix.get(key, ResolutionStrategy.MANUAL_RESOLUTION)

    async def _resolve_last_write_wins(self, conflict: ConflictContext) -> ResolutionResult:
        """Resolve using last-write-wins strategy"""
        # Compare timestamps to determine winner
        if conflict.remote_timestamp and conflict.local_timestamp:
            if conflict.remote_timestamp > conflict.local_timestamp:
                winner = conflict.remote_version
            else:
                winner = conflict.local_version
        else:
            # Fall back to remote version if timestamps unavailable
            winner = conflict.remote_version

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.LAST_WRITE_WINS,
            resolved_version=winner,
            success=True,
            backup_versions={
                "local": conflict.local_version,
                "remote": conflict.remote_version
            }
        )

    async def _resolve_first_write_wins(self, conflict: ConflictContext) -> ResolutionResult:
        """Resolve using first-write-wins strategy"""
        # Compare timestamps to determine first writer
        if conflict.remote_timestamp and conflict.local_timestamp:
            if conflict.local_timestamp < conflict.remote_timestamp:
                winner = conflict.local_version
            else:
                winner = conflict.remote_version
        else:
            # Fall back to local version if timestamps unavailable
            winner = conflict.local_version

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.FIRST_WRITE_WINS,
            resolved_version=winner,
            success=True,
            backup_versions={
                "local": conflict.local_version,
                "remote": conflict.remote_version
            }
        )

    async def _resolve_merge_fields(self, conflict: ConflictContext) -> ResolutionResult:
        """Resolve by merging non-conflicting fields"""
        try:
            merged_version = conflict.local_version.copy()

            # Merge fields intelligently
            for field in conflict.remote_version:
                if field not in conflict.conflicting_fields:
                    # Use remote value for non-conflicting fields
                    merged_version[field] = conflict.remote_version[field]
                else:
                    # Handle conflicting fields based on field type
                    merged_value = await self._merge_conflicting_field(
                        field,
                        conflict.local_version.get(field),
                        conflict.remote_version.get(field),
                        conflict.resource_type
                    )

                    if merged_value is not None:
                        merged_version[field] = merged_value
                    # else keep local value

            # Update etag to indicate this is a merged version
            merged_version["@odata.etag"] = self._generate_merge_etag(
                conflict.local_etag, conflict.remote_etag
            )
            merged_version["lastModifiedDateTime"] = datetime.now(timezone.utc).isoformat() + "Z"

            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                strategy_used=ResolutionStrategy.MERGE_FIELDS,
                resolved_version=merged_version,
                success=True,
                backup_versions={
                    "local": conflict.local_version,
                    "remote": conflict.remote_version
                }
            )

        except Exception as e:
            logger.error("Field merge failed", conflict_id=conflict.conflict_id, error=str(e))

            return ResolutionResult(
                conflict_id=conflict.conflict_id,
                strategy_used=ResolutionStrategy.MERGE_FIELDS,
                resolved_version={},
                success=False,
                error_message=f"Merge failed: {str(e)}",
                requires_manual_intervention=True
            )

    async def _merge_conflicting_field(
        self,
        field_name: str,
        local_value: Any,
        remote_value: Any,
        resource_type: str
    ) -> Any:
        """Merge a specific conflicting field intelligently"""

        # Handle assignments (merge user lists)
        if field_name == "assignments" and isinstance(local_value, dict) and isinstance(remote_value, dict):
            merged_assignments = local_value.copy()
            merged_assignments.update(remote_value)
            return merged_assignments

        # Handle description fields (append if both exist)
        if field_name == "description" and local_value and remote_value:
            if local_value != remote_value:
                return f"{local_value}\n\n[Merged] {remote_value}"

        # Handle numeric fields (use max for progress)
        if field_name == "percentComplete":
            if isinstance(local_value, (int, float)) and isinstance(remote_value, (int, float)):
                return max(local_value, remote_value)

        # Handle dates (use later date for due dates)
        if field_name in ["dueDateTime", "startDateTime"]:
            if local_value and remote_value:
                try:
                    local_dt = datetime.fromisoformat(local_value.replace("Z", "+00:00"))
                    remote_dt = datetime.fromisoformat(remote_value.replace("Z", "+00:00"))
                    return max(local_dt, remote_dt).isoformat() + "Z"
                except ValueError:
                    pass

        # Default: return None to keep local value
        return None

    def _generate_merge_etag(self, local_etag: Optional[str], remote_etag: Optional[str]) -> str:
        """Generate a new etag for merged version"""
        merge_source = f"merge:{local_etag}:{remote_etag}:{datetime.now().isoformat()}"
        return f"W/\"{hashlib.md5(merge_source.encode()).hexdigest()}\""

    async def _prepare_manual_resolution(self, conflict: ConflictContext) -> ResolutionResult:
        """Prepare conflict for manual resolution"""
        # Store detailed conflict information for manual review
        await self._store_manual_resolution_data(conflict)

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.MANUAL_RESOLUTION,
            resolved_version=conflict.local_version,  # Keep local until manual resolution
            success=True,
            requires_manual_intervention=True,
            backup_versions={
                "local": conflict.local_version,
                "remote": conflict.remote_version
            }
        )

    async def _resolve_rollback(self, conflict: ConflictContext) -> ResolutionResult:
        """Resolve by rolling back to previous known good state"""
        # For dependency conflicts, keep local version and reject remote
        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.ROLLBACK,
            resolved_version=conflict.local_version,
            success=True,
            backup_versions={
                "rejected_remote": conflict.remote_version
            }
        )

    async def _resolve_branch_version(self, conflict: ConflictContext) -> ResolutionResult:
        """Create branched versions for later reconciliation"""
        # Create versioned copies
        branch_id = str(uuid.uuid4())

        # Store both versions with branch metadata
        local_branch = conflict.local_version.copy()
        local_branch["_branch_metadata"] = {
            "branch_id": branch_id,
            "branch_type": "local",
            "original_conflict_id": conflict.conflict_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        remote_branch = conflict.remote_version.copy()
        remote_branch["_branch_metadata"] = {
            "branch_id": branch_id,
            "branch_type": "remote",
            "original_conflict_id": conflict.conflict_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        await self._store_branched_versions(conflict, local_branch, remote_branch)

        return ResolutionResult(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.BRANCH_VERSION,
            resolved_version=local_branch,  # Use local as primary
            success=True,
            requires_manual_intervention=True,
            backup_versions={
                "local_branch": local_branch,
                "remote_branch": remote_branch
            }
        )

    async def _store_manual_resolution_data(self, conflict: ConflictContext) -> None:
        """Store detailed data for manual conflict resolution"""
        try:
            # Store in cache for quick access by resolution UI
            resolution_data = {
                "conflict": {
                    "id": conflict.conflict_id,
                    "type": conflict.conflict_type,
                    "severity": conflict.severity,
                    "resource_type": conflict.resource_type,
                    "resource_id": conflict.resource_id,
                    "conflicting_fields": conflict.conflicting_fields
                },
                "versions": {
                    "local": conflict.local_version,
                    "remote": conflict.remote_version
                },
                "metadata": {
                    "local_etag": conflict.local_etag,
                    "remote_etag": conflict.remote_etag,
                    "local_timestamp": conflict.local_timestamp.isoformat() if conflict.local_timestamp else None,
                    "remote_timestamp": conflict.remote_timestamp.isoformat() if conflict.remote_timestamp else None
                },
                "created_at": conflict.created_at.isoformat()
            }

            await self.cache_service.set(
                f"manual_resolution:{conflict.conflict_id}",
                resolution_data,
                ttl=86400  # 24 hours
            )

        except Exception as e:
            logger.error("Failed to store manual resolution data", conflict_id=conflict.conflict_id, error=str(e))

    async def _store_branched_versions(
        self,
        conflict: ConflictContext,
        local_branch: Dict[str, Any],
        remote_branch: Dict[str, Any]
    ) -> None:
        """Store branched versions for later reconciliation"""
        try:
            query = """
            INSERT INTO conflict_branches (
                conflict_id, branch_type, version_data, created_at
            ) VALUES ($1, $2, $3, $4)
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(query, conflict.conflict_id, "local", json.dumps(local_branch), datetime.now(timezone.utc))
                await conn.execute(query, conflict.conflict_id, "remote", json.dumps(remote_branch), datetime.now(timezone.utc))

        except Exception as e:
            logger.error("Failed to store branched versions", conflict_id=conflict.conflict_id, error=str(e))

    async def _update_conflict_resolution(
        self,
        conflict: ConflictContext,
        result: ResolutionResult
    ) -> None:
        """Update conflict record with resolution details"""
        try:
            query = """
            UPDATE conflict_resolutions SET
                resolution_strategy = $1,
                resolution_timestamp = $2,
                resolved_by = $3,
                resolution_success = $4,
                resolution_notes = $5,
                requires_manual_intervention = $6
            WHERE conflict_id = $7
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    result.strategy_used,
                    datetime.now(timezone.utc),
                    conflict.user_id,
                    result.success,
                    result.error_message or "Automatically resolved",
                    result.requires_manual_intervention,
                    conflict.conflict_id
                )

        except Exception as e:
            logger.error("Failed to update conflict resolution", conflict_id=conflict.conflict_id, error=str(e))


class ConflictManager:
    """Main manager for conflict detection and resolution"""

    def __init__(self, database: Database, cache_service: CacheService):
        self.database = database
        self.cache_service = cache_service
        self.detector = ConflictDetector(database, cache_service)
        self.resolver = ConflictResolver(database, cache_service)

    async def initialize(self) -> None:
        """Initialize conflict management tables"""
        await self._ensure_conflict_tables()

    async def handle_sync_conflict(
        self,
        resource_type: str,
        resource_id: str,
        local_version: Dict[str, Any],
        remote_version: Dict[str, Any],
        user_id: str,
        tenant_id: Optional[str] = None,
        preferred_strategy: Optional[ResolutionStrategy] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Handle synchronization conflict

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier
            local_version: Local version data
            remote_version: Remote version data
            user_id: User identifier
            tenant_id: Tenant context
            preferred_strategy: Override automatic strategy

        Returns:
            Tuple of (success, resolved_version, conflict_id)
        """
        try:
            # Detect conflict
            conflict = await self.detector.detect_conflict(
                resource_type, resource_id, local_version, remote_version, user_id, tenant_id
            )

            if not conflict:
                # No conflict detected, use remote version
                return True, remote_version, None

            # Resolve conflict
            result = await self.resolver.resolve_conflict(conflict, preferred_strategy)

            return result.success, result.resolved_version, conflict.conflict_id

        except Exception as e:
            logger.error(
                "Error handling sync conflict",
                resource_id=resource_id,
                error=str(e)
            )

            # Fall back to local version on error
            return False, local_version, None

    async def get_pending_manual_resolutions(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get conflicts requiring manual resolution"""
        try:
            query = """
            SELECT conflict_id, conflict_type, severity, resource_type, resource_id,
                   tenant_id, user_id, conflicting_fields, created_at
            FROM conflict_resolutions
            WHERE requires_manual_intervention = true
              AND resolution_timestamp IS NULL
            """
            params = []

            if user_id:
                query += " AND user_id = $1"
                params.append(user_id)

            if tenant_id:
                if params:
                    query += f" AND tenant_id = ${len(params) + 1}"
                else:
                    query += " AND tenant_id = $1"
                params.append(tenant_id)

            query += " ORDER BY created_at DESC"

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            conflicts = []
            for row in rows:
                conflict_data = dict(row)
                conflict_data["conflicting_fields"] = json.loads(conflict_data["conflicting_fields"])
                conflicts.append(conflict_data)

            return conflicts

        except Exception as e:
            logger.error("Error getting pending manual resolutions", error=str(e))
            return []

    async def get_conflict_statistics(
        self,
        tenant_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get conflict resolution statistics"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            query = """
            SELECT
                conflict_type,
                severity,
                resolution_strategy,
                COUNT(*) as count,
                AVG(EXTRACT(EPOCH FROM (resolution_timestamp - created_at))) as avg_resolution_time
            FROM conflict_resolutions
            WHERE created_at >= $1
            """
            params = [cutoff_date]

            if tenant_id:
                query += " AND tenant_id = $2"
                params.append(tenant_id)

            query += " GROUP BY conflict_type, severity, resolution_strategy"

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            stats = {
                "period_days": days,
                "total_conflicts": sum(row["count"] for row in rows),
                "by_type": {},
                "by_severity": {},
                "by_resolution": {},
                "avg_resolution_times": {}
            }

            for row in rows:
                conflict_type = row["conflict_type"]
                severity = row["severity"]
                strategy = row["resolution_strategy"]
                count = row["count"]
                avg_time = row["avg_resolution_time"]

                stats["by_type"][conflict_type] = stats["by_type"].get(conflict_type, 0) + count
                stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + count
                if strategy:
                    stats["by_resolution"][strategy] = stats["by_resolution"].get(strategy, 0) + count

                if avg_time:
                    key = f"{conflict_type}_{severity}"
                    stats["avg_resolution_times"][key] = avg_time

            return stats

        except Exception as e:
            logger.error("Error getting conflict statistics", error=str(e))
            return {}

    async def _ensure_conflict_tables(self) -> None:
        """Ensure conflict management tables exist"""
        try:
            async with self.database._connection_pool.acquire() as conn:
                # Conflict resolutions table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS conflict_resolutions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        conflict_id VARCHAR(255) UNIQUE NOT NULL,
                        conflict_type VARCHAR(50) NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        resource_type VARCHAR(50) NOT NULL,
                        resource_id VARCHAR(255) NOT NULL,
                        tenant_id VARCHAR(255),
                        user_id VARCHAR(255) NOT NULL,
                        conflicting_fields JSONB,
                        local_version JSONB,
                        remote_version JSONB,
                        local_etag VARCHAR(255),
                        remote_etag VARCHAR(255),
                        local_timestamp TIMESTAMP WITH TIME ZONE,
                        remote_timestamp TIMESTAMP WITH TIME ZONE,
                        metadata JSONB DEFAULT '{}',
                        resolution_strategy VARCHAR(50),
                        resolution_timestamp TIMESTAMP WITH TIME ZONE,
                        resolved_by VARCHAR(255),
                        resolution_success BOOLEAN,
                        resolution_notes TEXT,
                        requires_manual_intervention BOOLEAN DEFAULT false,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Conflict branches table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS conflict_branches (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        conflict_id VARCHAR(255) NOT NULL,
                        branch_type VARCHAR(20) NOT NULL,
                        version_data JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        FOREIGN KEY (conflict_id) REFERENCES conflict_resolutions(conflict_id)
                    )
                """)

                # Indexes for performance
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conflict_resolutions_resource
                    ON conflict_resolutions(resource_type, resource_id, tenant_id)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conflict_resolutions_user
                    ON conflict_resolutions(user_id, tenant_id, created_at)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conflict_resolutions_manual
                    ON conflict_resolutions(requires_manual_intervention, resolution_timestamp)
                """)

        except Exception as e:
            logger.error("Failed to create conflict management tables", error=str(e))
            raise