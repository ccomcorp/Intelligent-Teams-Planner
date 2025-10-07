"""
Multi-tenant support for Microsoft Graph API integration
Story 2.1 Task 4: Advanced multi-tenant management with comprehensive tenant isolation
"""

import os
import re
import time
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
import structlog

from ..models.graph_models import TenantContext
from ..auth import AuthService
from ..cache import CacheService
from .rate_limiter import IntelligentRateLimiter


logger = structlog.get_logger(__name__)


class TenantStatus(str, Enum):
    """Tenant status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    MAINTENANCE = "maintenance"


class TenantIsolationLevel(str, Enum):
    """Tenant data isolation levels"""
    STRICT = "strict"          # Complete isolation
    MODERATE = "moderate"      # Shared resources with tenant filtering
    BASIC = "basic"           # Basic tenant identification only


@dataclass
class TenantConfiguration:
    """Complete tenant configuration"""
    tenant_id: str
    tenant_name: str
    client_id: str
    client_secret: str
    authority: str
    status: TenantStatus = TenantStatus.ACTIVE
    isolation_level: TenantIsolationLevel = TenantIsolationLevel.STRICT

    # Rate limiting configuration
    rate_limit_config: Dict[str, int] = field(default_factory=dict)

    # Security configuration
    allowed_scopes: List[str] = field(default_factory=list)
    security_policies: Dict[str, Any] = field(default_factory=dict)

    # Resource quotas
    max_requests_per_hour: int = 1000
    max_batch_size: int = 20
    max_concurrent_requests: int = 10
    storage_quota_mb: int = 1000

    # Operational metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = None
    usage_statistics: Dict[str, Any] = field(default_factory=dict)

    # Configuration metadata
    configuration_version: str = "1.0"
    environment: str = "production"

    def update_usage(self) -> None:
        """Update tenant usage statistics"""
        self.last_used = datetime.now(timezone.utc)
        self.usage_statistics.setdefault("total_requests", 0)
        self.usage_statistics["total_requests"] += 1

    def is_active(self) -> bool:
        """Check if tenant is active and operational"""
        return self.status == TenantStatus.ACTIVE

    def has_scope(self, scope: str) -> bool:
        """Check if tenant has permission for specific scope"""
        return scope in self.allowed_scopes or not self.allowed_scopes


@dataclass
class TenantQuota:
    """Tenant resource quota tracking"""
    tenant_id: str
    requests_made_today: int = 0
    requests_made_hour: int = 0
    storage_used_mb: float = 0.0
    concurrent_requests: int = 0
    batch_operations_today: int = 0
    last_reset_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc).date())
    last_hour_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0))

    def reset_daily_counters(self) -> None:
        """Reset daily usage counters"""
        today = datetime.now(timezone.utc).date()
        if self.last_reset_date < today:
            self.requests_made_today = 0
            self.batch_operations_today = 0
            self.last_reset_date = today

    def reset_hourly_counters(self) -> None:
        """Reset hourly usage counters"""
        current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if self.last_hour_reset < current_hour:
            self.requests_made_hour = 0
            self.last_hour_reset = current_hour


class TenantSecurityError(Exception):
    """Tenant security violation errors"""
    pass


class TenantQuotaExceededError(Exception):
    """Tenant quota exceeded errors"""
    pass


class TenantNotFoundError(Exception):
    """Tenant not found errors"""
    pass


class TenantManager:
    """
    Advanced multi-tenant management for Microsoft Graph API

    Features:
    - Comprehensive tenant isolation and security boundaries
    - Dynamic tenant configuration loading from environment
    - Tenant-specific rate limiting and resource quotas
    - Cross-tenant security policy enforcement
    - Tenant discovery and validation
    - Audit logging for multi-tenant operations
    - Performance monitoring per tenant
    """

    def __init__(self, cache_service: CacheService, rate_limiter: IntelligentRateLimiter):
        """Initialize tenant manager"""
        self.cache_service = cache_service
        self.rate_limiter = rate_limiter

        # Tenant configurations
        self.tenant_configs: Dict[str, TenantConfiguration] = {}
        self.tenant_quotas: Dict[str, TenantQuota] = {}
        self.auth_services: Dict[str, AuthService] = {}

        # Security and isolation settings
        self.default_tenant_id = os.getenv("DEFAULT_TENANT_ID", "")
        self.multi_tenant_enabled = os.getenv("MULTI_TENANT_ENABLED", "false").lower() == "true"
        self.tenant_isolation_enabled = os.getenv("TENANT_ISOLATION_ENABLED", "true").lower() == "true"

        # Performance tracking
        self.tenant_metrics: Dict[str, Dict[str, Any]] = {}

        # Security policies
        self.global_security_policies = self._load_global_security_policies()

        # Load tenant configurations from environment
        self._load_tenant_configurations()

        logger.info("Tenant manager initialized",
                   multi_tenant_enabled=self.multi_tenant_enabled,
                   tenant_count=len(self.tenant_configs),
                   isolation_enabled=self.tenant_isolation_enabled)

    def _load_global_security_policies(self) -> Dict[str, Any]:
        """Load global security policies from environment"""
        return {
            "require_tenant_validation": os.getenv(
                "REQUIRE_TENANT_VALIDATION", "true"
            ).lower() == "true",
            "allow_cross_tenant_access": os.getenv(
                "ALLOW_CROSS_TENANT_ACCESS", "false"
            ).lower() == "true",
            "enforce_scope_restrictions": os.getenv(
                "ENFORCE_SCOPE_RESTRICTIONS", "true"
            ).lower() == "true",
            "audit_all_operations": os.getenv(
                "AUDIT_ALL_OPERATIONS", "true"
            ).lower() == "true",
            "max_tenant_idle_days": int(os.getenv("MAX_TENANT_IDLE_DAYS", "90")),
            "require_encryption": os.getenv(
                "REQUIRE_ENCRYPTION", "true"
            ).lower() == "true"
        }

    def _load_tenant_configurations(self) -> None:
        """Load tenant configurations from environment variables"""
        # Load default tenant if specified
        if self.default_tenant_id:
            default_config = self._create_tenant_config_from_env(self.default_tenant_id, is_default=True)
            if default_config:
                self.tenant_configs[self.default_tenant_id] = default_config
                self.tenant_quotas[self.default_tenant_id] = TenantQuota(tenant_id=self.default_tenant_id)

        # Discover additional tenant configurations
        tenant_pattern = re.compile(r"TENANT_(\d+)_ID")
        discovered_tenants = set()

        for env_var in os.environ:
            match = tenant_pattern.match(env_var)
            if match:
                tenant_number = match.group(1)
                tenant_id = os.getenv(f"TENANT_{tenant_number}_ID")
                if tenant_id and tenant_id not in discovered_tenants:
                    discovered_tenants.add(tenant_id)
                    config = self._create_tenant_config_from_env(tenant_id, tenant_number=tenant_number)
                    if config:
                        self.tenant_configs[tenant_id] = config
                        self.tenant_quotas[tenant_id] = TenantQuota(tenant_id=tenant_id)

        logger.info("Loaded tenant configurations",
                    total_tenants=len(self.tenant_configs),
                    tenant_ids=list(self.tenant_configs.keys()))

    def _create_tenant_config_from_env(
        self,
        tenant_id: str,
        tenant_number: Optional[str] = None,
        is_default: bool = False
    ) -> Optional[TenantConfiguration]:
        """Create tenant configuration from environment variables"""
        try:
            if is_default:
                # Use default Azure configuration
                client_id = os.getenv("AZURE_CLIENT_ID", "")
                client_secret = os.getenv("AZURE_CLIENT_SECRET", "")
                authority = os.getenv("AZURE_AUTHORITY", f"https://login.microsoftonline.com/{tenant_id}")
                tenant_name = os.getenv("DEFAULT_TENANT_NAME", "Default Tenant")
                rate_limit = int(os.getenv("DEFAULT_RATE_LIMIT", "1000"))
            else:
                # Use tenant-specific configuration
                prefix = f"TENANT_{tenant_number}_"
                client_id = os.getenv(f"{prefix}CLIENT_ID", "")
                client_secret = os.getenv(f"{prefix}CLIENT_SECRET", "")
                authority = os.getenv(f"{prefix}AUTHORITY", f"https://login.microsoftonline.com/{tenant_id}")
                tenant_name = os.getenv(f"{prefix}NAME", f"Tenant {tenant_number}")
                rate_limit = int(os.getenv(f"{prefix}RATE_LIMIT", "1000"))

            if not all([client_id, client_secret]):
                logger.warning("Incomplete tenant configuration", tenant_id=tenant_id)
                return None

            # Build allowed scopes
            allowed_scopes = []
            scope_env = os.getenv(f"TENANT_{tenant_number}_SCOPES" if tenant_number else "DEFAULT_TENANT_SCOPES", "")
            if scope_env:
                allowed_scopes = [scope.strip() for scope in scope_env.split(",")]

            # Build rate limit configuration
            rate_limit_config = {
                "requests_per_hour": rate_limit,
                "burst_limit": int(rate_limit * 0.1),  # 10% burst
                "cooldown_period": 300  # 5 minutes
            }

            # Build security policies
            mfa_key = f"TENANT_{tenant_number}_REQUIRE_MFA" if tenant_number else "DEFAULT_REQUIRE_MFA"
            ip_key = f"TENANT_{tenant_number}_ALLOWED_IPS" if tenant_number else "DEFAULT_ALLOWED_IPS"
            timeout_key = f"TENANT_{tenant_number}_SESSION_TIMEOUT" if tenant_number else "DEFAULT_SESSION_TIMEOUT"

            allowed_ips = os.getenv(ip_key, "")
            security_policies = {
                "require_mfa": os.getenv(mfa_key, "false").lower() == "true",
                "allowed_ip_ranges": allowed_ips.split(",") if allowed_ips else [],
                "session_timeout": int(os.getenv(timeout_key, "3600"))
            }

            # Resource quotas
            req_key = f"TENANT_{tenant_number}_MAX_REQUESTS" if tenant_number else "DEFAULT_MAX_REQUESTS"
            batch_key = f"TENANT_{tenant_number}_MAX_BATCH_SIZE" if tenant_number else "DEFAULT_MAX_BATCH_SIZE"
            conc_key = f"TENANT_{tenant_number}_MAX_CONCURRENT" if tenant_number else "DEFAULT_MAX_CONCURRENT"
            storage_key = f"TENANT_{tenant_number}_STORAGE_QUOTA_MB" if tenant_number else "DEFAULT_STORAGE_QUOTA_MB"

            max_requests = int(os.getenv(req_key, "1000"))
            max_batch_size = int(os.getenv(batch_key, "20"))
            max_concurrent = int(os.getenv(conc_key, "10"))
            storage_quota = int(os.getenv(storage_key, "1000"))

            return TenantConfiguration(
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                client_id=client_id,
                client_secret=client_secret,
                authority=authority,
                rate_limit_config=rate_limit_config,
                allowed_scopes=allowed_scopes,
                security_policies=security_policies,
                max_requests_per_hour=max_requests,
                max_batch_size=max_batch_size,
                max_concurrent_requests=max_concurrent,
                storage_quota_mb=storage_quota,
                environment=os.getenv("ENVIRONMENT", "production")
            )

        except Exception as e:
            logger.error("Error creating tenant configuration",
                        tenant_id=tenant_id,
                        error=str(e))
            return None

    async def get_tenant_config(self, tenant_id: str) -> TenantConfiguration:
        """Get tenant configuration with validation"""
        if not tenant_id:
            raise ValueError("Tenant ID is required")

        if tenant_id not in self.tenant_configs:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        config = self.tenant_configs[tenant_id]

        # Validate tenant status
        if not config.is_active():
            raise TenantSecurityError(f"Tenant {tenant_id} is not active (status: {config.status})")

        # Update usage
        config.update_usage()

        return config

    async def validate_tenant_access(self, tenant_id: str, user_id: str, operation: str, scope: Optional[str] = None) -> bool:
        """Validate tenant access with comprehensive security checks"""
        try:
            # Basic tenant validation
            config = await self.get_tenant_config(tenant_id)

            # Check scope permissions
            if scope and not config.has_scope(scope):
                logger.warning("Scope access denied",
                             tenant_id=tenant_id,
                             user_id=user_id,
                             scope=scope)
                return False

            # Check quotas
            await self._check_tenant_quotas(tenant_id, operation)

            # Security policy validation
            if not await self._validate_security_policies(config, user_id, operation):
                return False

            # Audit logging
            if self.global_security_policies["audit_all_operations"]:
                await self._audit_tenant_access(tenant_id, user_id, operation, scope, success=True)

            return True

        except (TenantNotFoundError, TenantSecurityError, TenantQuotaExceededError) as e:
            logger.error("Tenant access validation failed",
                        tenant_id=tenant_id,
                        user_id=user_id,
                        operation=operation,
                        error=str(e))

            # Audit failed access
            if self.global_security_policies["audit_all_operations"]:
                await self._audit_tenant_access(tenant_id, user_id, operation, scope, success=False, error=str(e))

            return False

    async def _check_tenant_quotas(self, tenant_id: str, operation: str) -> None:
        """Check and enforce tenant resource quotas"""
        if tenant_id not in self.tenant_quotas:
            self.tenant_quotas[tenant_id] = TenantQuota(tenant_id=tenant_id)

        quota = self.tenant_quotas[tenant_id]
        config = self.tenant_configs[tenant_id]

        # Reset counters if needed
        quota.reset_daily_counters()
        quota.reset_hourly_counters()

        # Check hourly request limit
        if quota.requests_made_hour >= config.max_requests_per_hour:
            raise TenantQuotaExceededError(f"Hourly request limit exceeded for tenant {tenant_id}")

        # Check concurrent request limit
        if quota.concurrent_requests >= config.max_concurrent_requests:
            raise TenantQuotaExceededError(f"Concurrent request limit exceeded for tenant {tenant_id}")

        # Check storage quota
        if quota.storage_used_mb >= config.storage_quota_mb:
            raise TenantQuotaExceededError(f"Storage quota exceeded for tenant {tenant_id}")

        # Update usage counters
        quota.requests_made_today += 1
        quota.requests_made_hour += 1

        if operation == "batch":
            quota.batch_operations_today += 1

    async def _validate_security_policies(self, config: TenantConfiguration, user_id: str, operation: str) -> bool:
        """Validate tenant-specific security policies"""
        policies = config.security_policies

        # Check if MFA is required (placeholder - would integrate with actual MFA system)
        if policies.get("require_mfa", False):
            # In real implementation, check if user has valid MFA token
            logger.debug("MFA validation required", tenant_id=config.tenant_id, user_id=user_id)

        # Check IP restrictions (placeholder - would check actual request IP)
        allowed_ips = policies.get("allowed_ip_ranges", [])
        if allowed_ips:
            logger.debug("IP validation required", tenant_id=config.tenant_id, allowed_ips=allowed_ips)

        # Check session timeout
        # In real implementation, validate session age against timeout
        # session_timeout = policies.get("session_timeout", 3600)

        return True

    async def _audit_tenant_access(
        self,
        tenant_id: str,
        user_id: str,
        operation: str,
        scope: Optional[str],
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """Audit tenant access attempts"""
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "operation": operation,
            "scope": scope,
            "success": success,
            "error": error,
            "ip_address": "unknown",  # Would be populated from request context
            "user_agent": "unknown"   # Would be populated from request context
        }

        # Store audit entry (in production, this would go to a secure audit log)
        await self.cache_service.set(
            f"audit:{tenant_id}:{int(time.time() * 1000)}",
            audit_entry,
            ttl=86400 * 30  # 30 days
        )

        logger.info("Tenant access audited", **audit_entry)

    @asynccontextmanager
    async def tenant_context(self, tenant_id: str, user_id: str):
        """Create isolated tenant context for operations"""
        if not self.tenant_isolation_enabled:
            yield TenantContext(tenant_id=tenant_id)
            return

        try:
            # Validate tenant access
            config = await self.get_tenant_config(tenant_id)

            # Create tenant context
            context = TenantContext(
                tenant_id=tenant_id,
                tenant_name=config.tenant_name,
                client_id=config.client_id,
                client_secret=config.client_secret,
                authority=config.authority,
                scopes=config.allowed_scopes,
                configuration=config.rate_limit_config,
                rate_limit_config=config.rate_limit_config
            )

            # Track concurrent operations
            if tenant_id in self.tenant_quotas:
                self.tenant_quotas[tenant_id].concurrent_requests += 1

            # Setup tenant-specific monitoring
            start_time = time.time()

            try:
                yield context
            finally:
                # Clean up resources
                if tenant_id in self.tenant_quotas:
                    self.tenant_quotas[tenant_id].concurrent_requests = max(0, self.tenant_quotas[tenant_id].concurrent_requests - 1)

                # Record performance metrics
                duration = time.time() - start_time
                await self._record_tenant_metrics(tenant_id, "operation_duration", duration)

        except Exception as e:
            logger.error("Error in tenant context", tenant_id=tenant_id, error=str(e))
            raise

    async def get_auth_service(self, tenant_id: str) -> AuthService:
        """Get tenant-specific authentication service"""
        if tenant_id not in self.auth_services:
            config = await self.get_tenant_config(tenant_id)

            self.auth_services[tenant_id] = AuthService(
                client_id=config.client_id,
                client_secret=config.client_secret,
                tenant_id=tenant_id,
                cache_service=self.cache_service
            )

        return self.auth_services[tenant_id]

    async def discover_tenant_from_user(self, user_id: str) -> Optional[str]:
        """Discover tenant ID from user information"""
        # Check cached tenant mapping
        cached_tenant = await self.cache_service.get(f"user_tenant:{user_id}")
        if cached_tenant:
            return cached_tenant

        # Try default tenant first
        if self.default_tenant_id:
            try:
                auth_service = await self.get_auth_service(self.default_tenant_id)
                token_info = await auth_service.get_token_info(user_id)
                if token_info:
                    tenant_id = token_info.get("tenant_id", self.default_tenant_id)

                    # Cache the mapping
                    await self.cache_service.set(f"user_tenant:{user_id}", tenant_id, ttl=3600)

                    return tenant_id
            except Exception as e:
                logger.debug("Default tenant check failed", user_id=user_id, error=str(e))

        # Check all configured tenants
        for tenant_id in self.tenant_configs:
            try:
                auth_service = await self.get_auth_service(tenant_id)
                if await auth_service.has_valid_token(user_id):
                    # Cache the mapping
                    await self.cache_service.set(
                        f"user_tenant:{user_id}", tenant_id, ttl=3600
                    )
                    return tenant_id
            except Exception as e:
                logger.debug(
                    "Tenant discovery failed",
                    tenant_id=tenant_id,
                    user_id=user_id,
                    error=str(e)
                )

        return None

    async def _record_tenant_metrics(
        self, tenant_id: str, metric_name: str, value: Union[int, float]
    ) -> None:
        """Record performance metrics for tenant"""
        if tenant_id not in self.tenant_metrics:
            self.tenant_metrics[tenant_id] = {}

        metrics = self.tenant_metrics[tenant_id]
        if metric_name not in metrics:
            metrics[metric_name] = []

        metrics[metric_name].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "value": value
        })

        # Keep only last 100 measurements
        if len(metrics[metric_name]) > 100:
            metrics[metric_name] = metrics[metric_name][-100:]

    async def get_tenant_rate_limit_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant-specific rate limit configuration"""
        config = await self.get_tenant_config(tenant_id)
        return config.rate_limit_config

    async def check_cross_tenant_access(self, source_tenant_id: str, target_tenant_id: str, operation: str) -> bool:
        """Check if cross-tenant access is allowed"""
        if source_tenant_id == target_tenant_id:
            return True

        if not self.global_security_policies["allow_cross_tenant_access"]:
            logger.warning("Cross-tenant access denied by policy",
                          source_tenant=source_tenant_id,
                          target_tenant=target_tenant_id,
                          operation=operation)
            return False

        # Additional cross-tenant validation could be implemented here
        return True

    async def get_tenant_status(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get comprehensive tenant status information"""
        if tenant_id:
            if tenant_id not in self.tenant_configs:
                return {"error": "Tenant not found"}

            config = self.tenant_configs[tenant_id]
            quota = self.tenant_quotas.get(tenant_id, TenantQuota(tenant_id=tenant_id))
            metrics = self.tenant_metrics.get(tenant_id, {})

            return {
                "tenant_id": tenant_id,
                "tenant_name": config.tenant_name,
                "status": config.status,
                "isolation_level": config.isolation_level,
                "last_used": config.last_used.isoformat() if config.last_used else None,
                "usage_statistics": config.usage_statistics,
                "quotas": {
                    "requests_today": quota.requests_made_today,
                    "requests_hour": quota.requests_made_hour,
                    "concurrent_requests": quota.concurrent_requests,
                    "storage_used_mb": quota.storage_used_mb,
                    "batch_operations_today": quota.batch_operations_today
                },
                "limits": {
                    "max_requests_per_hour": config.max_requests_per_hour,
                    "max_batch_size": config.max_batch_size,
                    "max_concurrent_requests": config.max_concurrent_requests,
                    "storage_quota_mb": config.storage_quota_mb
                },
                "metrics": metrics
            }

        # Return summary for all tenants
        summary = {
            "total_tenants": len(self.tenant_configs),
            "multi_tenant_enabled": self.multi_tenant_enabled,
            "isolation_enabled": self.tenant_isolation_enabled,
            "tenants": []
        }

        for tid in self.tenant_configs:
            tenant_status = await self.get_tenant_status(tid)
            summary["tenants"].append(tenant_status)

        return summary

    async def reload_tenant_configurations(self) -> None:
        """Reload tenant configurations from environment"""
        logger.info("Reloading tenant configurations")

        # Clear existing auth services (they will be recreated with new configs)
        self.auth_services.clear()

        # Reload configurations
        self._load_tenant_configurations()

        logger.info("Tenant configurations reloaded", tenant_count=len(self.tenant_configs))


# Global tenant manager instance
_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager(cache_service: CacheService = None, rate_limiter: IntelligentRateLimiter = None) -> TenantManager:
    """Get or create global tenant manager instance"""
    global _tenant_manager
    if _tenant_manager is None:
        if not cache_service:
            # Create a basic cache service for fallback
            cache_service = CacheService("redis://localhost:6379/0")
        if not rate_limiter:
            from .rate_limiter import get_rate_limiter
            rate_limiter = get_rate_limiter()

        _tenant_manager = TenantManager(cache_service, rate_limiter)
    return _tenant_manager
