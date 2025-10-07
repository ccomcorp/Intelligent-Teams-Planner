"""
Advanced Permission Management for Microsoft Graph API Integration
Story 2.1 Task 5: Comprehensive permission validation, scope-based access control, and audit logging
"""

import re
import uuid
import time
import hashlib
import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from collections import defaultdict
import structlog

from ..models.graph_models import UserPermissions, TenantContext
from ..utils.error_handler import get_error_handler
from ..utils.performance_monitor import get_performance_monitor, track_operation


logger = structlog.get_logger(__name__)


class PermissionType(str, Enum):
    """Microsoft Graph permission types"""
    APPLICATION = "application"
    DELEGATED = "delegated"


class AccessLevel(str, Enum):
    """Access levels for permissions"""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    FULL_ACCESS = "full_access"


class ResourceType(str, Enum):
    """Microsoft Graph resource types"""
    PLANNER = "planner"
    GROUP = "group"
    USER = "user"
    DIRECTORY = "directory"
    TASKS = "tasks"
    CALENDAR = "calendar"
    MAIL = "mail"


@dataclass
class PermissionValidationResult:
    """Result of permission validation"""
    is_valid: bool
    granted_scopes: List[str]
    missing_scopes: List[str]
    escalation_detected: bool = False
    validation_context: Dict[str, Any] = field(default_factory=dict)
    validation_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PermissionAuditEntry:
    """Audit entry for permission operations"""
    audit_id: str
    user_id: str
    tenant_id: Optional[str]
    operation: str
    resource_type: str
    resource_id: Optional[str]
    requested_scopes: List[str]
    granted_scopes: List[str]
    denied_scopes: List[str]
    result: str  # granted, denied, escalation_detected
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    correlation_id: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.audit_id:
            self.audit_id = str(uuid.uuid4())
        # Set resource_id to empty string if not provided
        if not hasattr(self, 'resource_id') or self.resource_id is None:
            self.resource_id = ""


@dataclass
class PermissionCacheEntry:
    """Cached permission entry"""
    user_id: str
    tenant_id: Optional[str]
    permissions: UserPermissions
    cache_key: str
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        if self.expires_at is None:
            return False  # Never expires if no expiration set
        return datetime.now(timezone.utc) > self.expires_at

    def update_access(self) -> None:
        """Update access statistics"""
        self.access_count += 1
        self.last_accessed = datetime.now(timezone.utc)


class GraphPermissionValidator:
    """
    Microsoft Graph API permission validation and management system

    Provides comprehensive permission validation, scope-based access control,
    audit logging, and multi-tenant permission isolation
    """

    # Microsoft Graph scopes by category
    GRAPH_SCOPES = {
        ResourceType.PLANNER: {
            "Planner.Read": {"type": PermissionType.DELEGATED, "level": AccessLevel.READ},
            "Planner.ReadWrite": {"type": PermissionType.DELEGATED, "level": AccessLevel.WRITE},
            "Group.Read.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.READ},
            "Group.ReadWrite.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.WRITE},
        },
        ResourceType.GROUP: {
            "Group.Read.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.READ},
            "Group.ReadWrite.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.WRITE},
            "GroupMember.Read.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.READ},
            "GroupMember.ReadWrite.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.WRITE},
        },
        ResourceType.USER: {
            "User.Read": {"type": PermissionType.DELEGATED, "level": AccessLevel.READ},
            "User.ReadBasic.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.READ},
            "User.Read.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.READ},
            "User.ReadWrite.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.WRITE},
        },
        ResourceType.DIRECTORY: {
            "Directory.Read.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.READ},
            "Directory.ReadWrite.All": {"type": PermissionType.APPLICATION, "level": AccessLevel.ADMIN},
        },
        ResourceType.TASKS: {
            "Tasks.Read": {"type": PermissionType.DELEGATED, "level": AccessLevel.READ},
            "Tasks.ReadWrite": {"type": PermissionType.DELEGATED, "level": AccessLevel.WRITE},
            "Tasks.Read.Shared": {"type": PermissionType.DELEGATED, "level": AccessLevel.READ},
            "Tasks.ReadWrite.Shared": {"type": PermissionType.DELEGATED, "level": AccessLevel.WRITE},
        },
    }

    # Permission hierarchy - higher level permissions include lower ones
    PERMISSION_HIERARCHY = {
        AccessLevel.FULL_ACCESS: [AccessLevel.ADMIN, AccessLevel.WRITE, AccessLevel.READ],
        AccessLevel.ADMIN: [AccessLevel.WRITE, AccessLevel.READ],
        AccessLevel.WRITE: [AccessLevel.READ],
        AccessLevel.READ: [],
    }

    def __init__(self,
                 cache_ttl_minutes: int = 15,
                 max_cache_size: int = 10000,
                 enable_audit_logging: bool = True,
                 enable_escalation_detection: bool = True):
        self.cache_ttl_minutes = cache_ttl_minutes
        self.max_cache_size = max_cache_size
        self.enable_audit_logging = enable_audit_logging
        self.enable_escalation_detection = enable_escalation_detection

        # Permission cache
        self._permission_cache: Dict[str, PermissionCacheEntry] = {}
        self._cache_access_order: List[str] = []

        # Audit trail
        self._audit_trail: List[PermissionAuditEntry] = []
        self._max_audit_entries = 50000

        # Tenant contexts
        self._tenant_contexts: Dict[str, TenantContext] = {}

        # Performance monitoring
        self.error_handler = get_error_handler()
        self.performance_monitor = get_performance_monitor()

        logger.info("Graph permission validator initialized",
                    cache_ttl=cache_ttl_minutes,
                    audit_enabled=enable_audit_logging,
                    escalation_detection=enable_escalation_detection)

    def _generate_cache_key(self, user_id: str, tenant_id: Optional[str] = None) -> str:
        """Generate cache key for user permissions"""
        key_parts = [user_id]
        if tenant_id:
            key_parts.append(tenant_id)

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _manage_cache_size(self) -> None:
        """Manage cache size using LRU eviction"""
        while len(self._permission_cache) >= self.max_cache_size:
            if self._cache_access_order:
                oldest_key = self._cache_access_order.pop(0)
                self._permission_cache.pop(oldest_key, None)

    @track_operation("permission_validation")
    async def validate_permissions(self,
                                   user_id: str,
                                   required_scopes: List[str],
                                   operation: str,
                                   resource_type: ResourceType,
                                   resource_id: Optional[str] = None,
                                   tenant_id: Optional[str] = None,
                                   context: Optional[Dict[str, Any]] = None) -> PermissionValidationResult:
        """
        Validate user permissions for a specific operation

        Args:
            user_id: User identifier
            required_scopes: List of required permission scopes
            operation: Operation being performed
            resource_type: Type of resource being accessed
            resource_id: Specific resource identifier (optional)
            tenant_id: Tenant identifier for multi-tenant scenarios
            context: Additional validation context

        Returns:
            PermissionValidationResult with validation details
        """
        context = context or {}
        validation_start = time.time()

        try:
            # Get user permissions (cached or fresh)
            user_permissions = await self._get_user_permissions(user_id, tenant_id)

            # Validate tenant isolation
            if tenant_id and not self._validate_tenant_isolation(user_id, tenant_id):
                await self._log_audit_entry(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    operation=operation,
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    requested_scopes=required_scopes,
                    granted_scopes=[],
                    denied_scopes=required_scopes,
                    result="tenant_isolation_violation",
                    context=context
                )

                return PermissionValidationResult(
                    is_valid=False,
                    granted_scopes=[],
                    missing_scopes=required_scopes,
                    validation_context={"error": "tenant_isolation_violation"}
                )

            # Check for permission escalation
            escalation_detected = False
            if self.enable_escalation_detection:
                escalation_detected = self._detect_permission_escalation(
                    user_permissions, required_scopes, context
                )

            # Validate individual scopes
            granted_scopes = []
            missing_scopes = []

            for scope in required_scopes:
                if self._validate_scope(user_permissions, scope, resource_type):
                    granted_scopes.append(scope)
                else:
                    missing_scopes.append(scope)

            # Determine validation result
            is_valid = len(missing_scopes) == 0 and not escalation_detected

            # Log audit entry
            if self.enable_audit_logging:
                result = "granted" if is_valid else "denied"
                if escalation_detected:
                    result = "escalation_detected"

                await self._log_audit_entry(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    operation=operation,
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    requested_scopes=required_scopes,
                    granted_scopes=granted_scopes,
                    denied_scopes=missing_scopes,
                    result=result,
                    context=context
                )

            validation_result = PermissionValidationResult(
                is_valid=is_valid,
                granted_scopes=granted_scopes,
                missing_scopes=missing_scopes,
                escalation_detected=escalation_detected,
                validation_context={
                    "validation_duration": time.time() - validation_start,
                    "cache_hit": self._was_cache_hit(user_id, tenant_id),
                    "tenant_id": tenant_id,
                    "resource_type": resource_type.value
                }
            )

            if not is_valid:
                logger.warning("Permission validation failed",
                               user_id=user_id,
                               operation=operation,
                               missing_scopes=missing_scopes,
                               escalation_detected=escalation_detected)

            return validation_result

        except Exception as e:
            self.error_handler.classify_error(e, {
                "operation": "permission_validation",
                "user_id": user_id,
                "tenant_id": tenant_id
            })

            logger.error("Permission validation error",
                         error=str(e),
                         user_id=user_id,
                         operation=operation)

            # Return deny-by-default result
            return PermissionValidationResult(
                is_valid=False,
                granted_scopes=[],
                missing_scopes=required_scopes,
                validation_context={"error": str(e)}
            )

    async def _get_user_permissions(self, user_id: str, tenant_id: Optional[str] = None) -> UserPermissions:
        """Get user permissions from cache or fetch fresh"""
        cache_key = self._generate_cache_key(user_id, tenant_id)

        # Check cache first
        if cache_key in self._permission_cache:
            cache_entry = self._permission_cache[cache_key]

            if not cache_entry.is_expired():
                cache_entry.update_access()
                # Move to end of access order (most recently used)
                if cache_key in self._cache_access_order:
                    self._cache_access_order.remove(cache_key)
                self._cache_access_order.append(cache_key)

                logger.debug("Permission cache hit", user_id=user_id, cache_key=cache_key)
                return cache_entry.permissions
            else:
                # Remove expired entry
                del self._permission_cache[cache_key]
                if cache_key in self._cache_access_order:
                    self._cache_access_order.remove(cache_key)

        # Fetch fresh permissions (would integrate with actual Graph API in production)
        user_permissions = await self._fetch_user_permissions(user_id, tenant_id)

        # Cache the result
        self._manage_cache_size()

        cache_entry = PermissionCacheEntry(
            user_id=user_id,
            tenant_id=tenant_id,
            permissions=user_permissions,
            cache_key=cache_key
        )
        cache_entry.update_access()  # Initialize access count

        self._permission_cache[cache_key] = cache_entry
        self._cache_access_order.append(cache_key)

        logger.debug("Permission cached", user_id=user_id, cache_key=cache_key)
        return user_permissions

    def _was_cache_hit(self, user_id: str, tenant_id: Optional[str] = None) -> bool:
        """Check if the last request was a cache hit"""
        cache_key = self._generate_cache_key(user_id, tenant_id)
        if cache_key in self._permission_cache:
            cache_entry = self._permission_cache[cache_key]
            # Consider it a cache hit if accessed recently and not expired
            if not cache_entry.is_expired() and cache_entry.access_count > 1:
                return True
        return False

    async def _fetch_user_permissions(self, user_id: str, tenant_id: Optional[str] = None) -> UserPermissions:
        """
        Fetch user permissions from Microsoft Graph API
        In production, this would make actual API calls to Graph
        """
        # Simulate API call delay
        await asyncio.sleep(0.1)

        # For demonstration, return mock permissions
        # In production, this would query the actual Graph API
        base_scopes = [
            "User.Read",
            "Planner.Read",
            "Group.Read.All"
        ]

        # Add additional scopes based on user context
        if user_id.endswith("_admin"):
            base_scopes.extend([
                "Planner.ReadWrite",
                "Group.ReadWrite.All",
                "Directory.Read.All"
            ])

        return UserPermissions(
            user_id=user_id,
            tenant_id=tenant_id,
            granted_scopes=base_scopes,
            last_validated=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

    def _validate_scope(self, user_permissions: UserPermissions, scope: str, resource_type: ResourceType) -> bool:
        """Validate if user has specific scope for resource type"""
        # Direct scope match
        if scope in user_permissions.granted_scopes:
            return True

        # Check permission hierarchy
        return self._check_permission_hierarchy(user_permissions, scope, resource_type)

    def _check_permission_hierarchy(self, user_permissions: UserPermissions, scope: str,
                                    resource_type: ResourceType) -> bool:
        """Check if user has higher-level permission that includes the requested scope"""
        # Get scope information
        resource_scopes = self.GRAPH_SCOPES.get(resource_type, {})
        scope_info = resource_scopes.get(scope)

        if not scope_info:
            return False

        required_level = scope_info["level"]

        # Check if user has higher-level permissions
        for user_scope in user_permissions.granted_scopes:
            user_scope_info = resource_scopes.get(user_scope)
            if not user_scope_info:
                continue

            user_level = user_scope_info["level"]

            # Check hierarchy
            if user_level in self.PERMISSION_HIERARCHY:
                included_levels = self.PERMISSION_HIERARCHY[user_level]
                if required_level in included_levels:
                    return True

        return False

    def _validate_tenant_isolation(self, user_id: str, tenant_id: str) -> bool:
        """Validate tenant isolation boundaries"""
        # In production, this would validate against tenant configuration
        # For now, simple validation
        if not tenant_id:
            return True

        # Check if tenant context exists and is enabled
        tenant_context = self._tenant_contexts.get(tenant_id)
        if tenant_context and not tenant_context.enabled:
            return False

        return True

    def _detect_permission_escalation(self,
                                      user_permissions: UserPermissions,
                                      requested_scopes: List[str],
                                      context: Dict[str, Any]) -> bool:
        """Detect potential permission escalation attempts"""
        if not self.enable_escalation_detection:
            return False

        # Check for suspicious patterns
        suspicious_patterns = [
            # Requesting admin permissions without current admin access
            r".*\.Admin.*",
            r".*\.All$",
            r"Directory\..*",
            # Application permissions when user typically has delegated
            r".*\.Application$"
        ]

        current_admin_scopes = [
            scope for scope in user_permissions.granted_scopes
            if any(re.match(pattern, scope, re.IGNORECASE) for pattern in suspicious_patterns)
        ]

        requested_admin_scopes = [
            scope for scope in requested_scopes
            if any(re.match(pattern, scope, re.IGNORECASE) for pattern in suspicious_patterns)
        ]

        # Escalation if requesting admin scopes without having any
        if requested_admin_scopes and not current_admin_scopes:
            return True

        # Check for unusual access patterns in context
        if context.get("unusual_access_pattern"):
            return True

        # Check for requests outside normal hours (if timestamp provided)
        request_time = context.get("request_timestamp")
        if request_time and isinstance(request_time, datetime):
            hour = request_time.hour
            if hour < 6 or hour > 22:  # Outside 6 AM - 10 PM
                return True

        return False

    async def _log_audit_entry(self,
                               user_id: str,
                               operation: str,
                               resource_type: str,
                               requested_scopes: List[str],
                               granted_scopes: List[str],
                               denied_scopes: List[str],
                               result: str,
                               tenant_id: Optional[str] = None,
                               resource_id: Optional[str] = None,
                               context: Optional[Dict[str, Any]] = None) -> None:
        """Log permission audit entry"""
        if not self.enable_audit_logging:
            return

        context = context or {}

        audit_entry = PermissionAuditEntry(
            audit_id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            requested_scopes=requested_scopes,
            granted_scopes=granted_scopes,
            denied_scopes=denied_scopes,
            result=result,
            ip_address=context.get("ip_address"),
            user_agent=context.get("user_agent"),
            correlation_id=context.get("correlation_id"),
            additional_context=context
        )

        # Manage audit trail size
        if len(self._audit_trail) >= self._max_audit_entries:
            # Remove oldest 10% of entries
            remove_count = self._max_audit_entries // 10
            self._audit_trail = self._audit_trail[remove_count:]

        self._audit_trail.append(audit_entry)

        logger.info("Permission audit logged",
                    audit_id=audit_entry.audit_id,
                    user_id=user_id,
                    operation=operation,
                    result=result)

    def require_permissions(self, required_scopes: List[str], resource_type: ResourceType):
        """
        Decorator for enforcing permissions on functions/methods

        Usage:
            @permission_validator.require_permissions(["Planner.ReadWrite"], ResourceType.PLANNER)
            async def create_task(user_id: str, task_data: dict):
                # Function implementation
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user_id and tenant_id from function arguments
                user_id = kwargs.get("user_id") or (args[0] if args else None)
                tenant_id = kwargs.get("tenant_id")
                operation = func.__name__

                if not user_id:
                    raise ValueError("user_id is required for permission validation")

                # Validate permissions
                validation_result = await self.validate_permissions(
                    user_id=user_id,
                    required_scopes=required_scopes,
                    operation=operation,
                    resource_type=resource_type,
                    tenant_id=tenant_id,
                    context=kwargs.get("permission_context", {})
                )

                if not validation_result.is_valid:
                    error_msg = f"Insufficient permissions for {operation}"
                    if validation_result.missing_scopes:
                        error_msg += f". Missing scopes: {validation_result.missing_scopes}"
                    if validation_result.escalation_detected:
                        error_msg += ". Permission escalation detected"

                    raise PermissionError(error_msg)

                # Add validation result to kwargs for function access if function accepts it
                import inspect
                sig = inspect.signature(func)
                if "permission_validation" in sig.parameters:
                    kwargs["permission_validation"] = validation_result

                return await func(*args, **kwargs)

            return wrapper
        return decorator

    def get_audit_trail(self,
                        user_id: Optional[str] = None,
                        operation: Optional[str] = None,
                        result: Optional[str] = None,
                        hours: int = 24) -> List[PermissionAuditEntry]:
        """Get filtered audit trail entries"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        filtered_entries = []
        for entry in self._audit_trail:
            if entry.timestamp < cutoff_time:
                continue

            if user_id and entry.user_id != user_id:
                continue

            if operation and entry.operation != operation:
                continue

            if result and entry.result != result:
                continue

            filtered_entries.append(entry)

        return filtered_entries

    def get_permission_statistics(self) -> Dict[str, Any]:
        """Get permission system statistics"""
        total_validations = len(self._audit_trail)

        if total_validations == 0:
            return {
                "total_validations": 0,
                "success_rate": 0.0,
                "escalation_rate": 0.0,
                "cache_stats": self._get_cache_statistics()
            }

        successful_validations = sum(1 for entry in self._audit_trail if entry.result == "granted")
        escalations = sum(1 for entry in self._audit_trail if entry.result == "escalation_detected")

        return {
            "total_validations": total_validations,
            "successful_validations": successful_validations,
            "denied_validations": total_validations - successful_validations,
            "success_rate": (successful_validations / total_validations) * 100,
            "escalation_count": escalations,
            "escalation_rate": (escalations / total_validations) * 100,
            "cache_stats": self._get_cache_statistics(),
            "most_requested_scopes": self._get_most_requested_scopes(),
            "most_denied_scopes": self._get_most_denied_scopes()
        }

    def _get_cache_statistics(self) -> Dict[str, Any]:
        """Get permission cache statistics"""
        total_entries = len(self._permission_cache)
        expired_entries = sum(1 for entry in self._permission_cache.values() if entry.is_expired())
        total_accesses = sum(entry.access_count for entry in self._permission_cache.values())

        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": total_entries - expired_entries,
            "total_accesses": total_accesses,
            "cache_hit_rate": self._calculate_cache_hit_rate()
        }

    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate from recent operations"""
        # This would be more sophisticated in production
        # For now, estimate based on cache access patterns
        if not self._permission_cache:
            return 0.0

        recent_accesses = sum(
            entry.access_count for entry in self._permission_cache.values()
            if entry.last_accessed and
            entry.last_accessed > datetime.now(timezone.utc) - timedelta(hours=1)
        )

        # Estimate hit rate based on cache usage
        return min(75.0, recent_accesses * 5.0)  # Simplified calculation

    def _get_most_requested_scopes(self) -> List[Dict[str, Any]]:
        """Get most frequently requested permission scopes"""
        scope_counts = defaultdict(int)

        for entry in self._audit_trail:
            for scope in entry.requested_scopes:
                scope_counts[scope] += 1

        return [
            {"scope": scope, "count": count}
            for scope, count in sorted(scope_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

    def _get_most_denied_scopes(self) -> List[Dict[str, Any]]:
        """Get most frequently denied permission scopes"""
        scope_counts = defaultdict(int)

        for entry in self._audit_trail:
            if entry.result == "denied":
                for scope in entry.denied_scopes:
                    scope_counts[scope] += 1

        return [
            {"scope": scope, "count": count}
            for scope, count in sorted(scope_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

    async def invalidate_user_cache(self, user_id: str, tenant_id: Optional[str] = None) -> bool:
        """Invalidate cached permissions for a user"""
        cache_key = self._generate_cache_key(user_id, tenant_id)

        if cache_key in self._permission_cache:
            del self._permission_cache[cache_key]
            if cache_key in self._cache_access_order:
                self._cache_access_order.remove(cache_key)

            logger.info("User permission cache invalidated", user_id=user_id, tenant_id=tenant_id)
            return True

        return False

    async def refresh_user_permissions(self, user_id: str, tenant_id: Optional[str] = None) -> UserPermissions:
        """Force refresh of user permissions"""
        # Invalidate cache first
        await self.invalidate_user_cache(user_id, tenant_id)

        # Fetch fresh permissions
        return await self._get_user_permissions(user_id, tenant_id)


# Global permission validator instance
_permission_validator: Optional[GraphPermissionValidator] = None


def get_permission_validator() -> GraphPermissionValidator:
    """Get or create global permission validator instance"""
    global _permission_validator
    if _permission_validator is None:
        _permission_validator = GraphPermissionValidator()
    return _permission_validator


def require_permissions(required_scopes: List[str], resource_type: ResourceType):
    """Convenience decorator for permission enforcement"""
    validator = get_permission_validator()
    return validator.require_permissions(required_scopes, resource_type)
