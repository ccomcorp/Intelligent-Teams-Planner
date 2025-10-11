"""
Sync Configuration Management System
Story 8.1 Task 2.5: Advanced synchronization configuration management

Implements comprehensive configuration management for Microsoft Planner synchronization
with dynamic updates, validation, and tenant-specific settings.
"""

import os
import json
import asyncio
from typing import Dict, List, Any, Optional, Set, Union, Callable
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
import structlog

from ..database import Database
from ..cache import CacheService

logger = structlog.get_logger(__name__)


class ConfigScope(str, Enum):
    """Configuration scope levels"""

    GLOBAL = "global"
    TENANT = "tenant"
    USER = "user"
    RESOURCE = "resource"


class ConfigType(str, Enum):
    """Configuration value types"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    LIST = "list"


class ConfigValidationLevel(str, Enum):
    """Configuration validation levels"""

    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"
    CUSTOM = "custom"


@dataclass
class ConfigDefinition:
    """Configuration parameter definition"""

    key: str
    name: str
    description: str
    config_type: ConfigType
    default_value: Any
    scope: ConfigScope
    validation_level: ConfigValidationLevel = ConfigValidationLevel.BASIC

    # Validation constraints
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    allowed_values: Optional[List[Any]] = None
    regex_pattern: Optional[str] = None

    # Metadata
    category: str = "general"
    requires_restart: bool = False
    sensitive: bool = False
    deprecated: bool = False

    # Custom validation
    custom_validator: Optional[Callable] = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConfigValue:
    """Configuration value instance"""

    key: str
    value: Any
    scope: ConfigScope
    scope_id: Optional[str] = None  # tenant_id, user_id, resource_id

    # Metadata
    set_by: Optional[str] = None
    set_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    # Validation
    validated: bool = False
    validation_error: Optional[str] = None

    # Change tracking
    previous_value: Optional[Any] = None
    change_reason: Optional[str] = None


@dataclass
class ConfigTemplate:
    """Configuration template for quick setup"""

    template_id: str
    name: str
    description: str
    category: str
    configurations: Dict[str, Any]
    scope: ConfigScope
    tags: List[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None


class ConfigValidator:
    """Configuration value validator"""

    def __init__(self):
        self.validators = {
            ConfigType.STRING: self._validate_string,
            ConfigType.INTEGER: self._validate_integer,
            ConfigType.FLOAT: self._validate_float,
            ConfigType.BOOLEAN: self._validate_boolean,
            ConfigType.JSON: self._validate_json,
            ConfigType.LIST: self._validate_list
        }

    def validate(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate configuration value against definition

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Skip validation if disabled
            if definition.validation_level == ConfigValidationLevel.NONE:
                return True, None

            # Type validation
            if definition.config_type in self.validators:
                is_valid, error = self.validators[definition.config_type](definition, value)
                if not is_valid:
                    return False, error

            # Custom validation
            if definition.custom_validator:
                try:
                    result = definition.custom_validator(value)
                    if isinstance(result, bool):
                        return result, None if result else "Custom validation failed"
                    elif isinstance(result, tuple):
                        return result
                    else:
                        return bool(result), None if result else "Custom validation failed"
                except Exception as e:
                    return False, f"Custom validation error: {str(e)}"

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _validate_string(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """Validate string value"""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"

        if definition.min_value is not None and len(value) < definition.min_value:
            return False, f"String too short (min: {definition.min_value})"

        if definition.max_value is not None and len(value) > definition.max_value:
            return False, f"String too long (max: {definition.max_value})"

        if definition.allowed_values and value not in definition.allowed_values:
            return False, f"Value not in allowed list: {definition.allowed_values}"

        if definition.regex_pattern:
            import re
            if not re.match(definition.regex_pattern, value):
                return False, f"Value does not match pattern: {definition.regex_pattern}"

        return True, None

    def _validate_integer(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """Validate integer value"""
        if not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError):
                return False, f"Expected integer, got {type(value).__name__}"

        if definition.min_value is not None and value < definition.min_value:
            return False, f"Value too small (min: {definition.min_value})"

        if definition.max_value is not None and value > definition.max_value:
            return False, f"Value too large (max: {definition.max_value})"

        if definition.allowed_values and value not in definition.allowed_values:
            return False, f"Value not in allowed list: {definition.allowed_values}"

        return True, None

    def _validate_float(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """Validate float value"""
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (ValueError, TypeError):
                return False, f"Expected number, got {type(value).__name__}"

        if definition.min_value is not None and value < definition.min_value:
            return False, f"Value too small (min: {definition.min_value})"

        if definition.max_value is not None and value > definition.max_value:
            return False, f"Value too large (max: {definition.max_value})"

        return True, None

    def _validate_boolean(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """Validate boolean value"""
        if not isinstance(value, bool):
            if isinstance(value, str):
                value_lower = value.lower()
                if value_lower in ["true", "1", "yes", "on"]:
                    return True, None
                elif value_lower in ["false", "0", "no", "off"]:
                    return True, None
                else:
                    return False, f"Invalid boolean string: {value}"
            else:
                return False, f"Expected boolean, got {type(value).__name__}"

        return True, None

    def _validate_json(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """Validate JSON value"""
        if isinstance(value, str):
            try:
                json.loads(value)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON: {str(e)}"
        elif not isinstance(value, (dict, list)):
            return False, f"Expected JSON object/array, got {type(value).__name__}"

        return True, None

    def _validate_list(self, definition: ConfigDefinition, value: Any) -> tuple[bool, Optional[str]]:
        """Validate list value"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                # Try comma-separated values
                value = [item.strip() for item in value.split(",")]

        if not isinstance(value, list):
            return False, f"Expected list, got {type(value).__name__}"

        if definition.min_value is not None and len(value) < definition.min_value:
            return False, f"List too short (min: {definition.min_value})"

        if definition.max_value is not None and len(value) > definition.max_value:
            return False, f"List too long (max: {definition.max_value})"

        return True, None


class ConfigManager:
    """Main configuration management system"""

    def __init__(self, database: Database, cache_service: CacheService):
        self.database = database
        self.cache_service = cache_service
        self.validator = ConfigValidator()

        # Configuration registry
        self.definitions: Dict[str, ConfigDefinition] = {}
        self.templates: Dict[str, ConfigTemplate] = {}

        # Change listeners
        self.change_listeners: Dict[str, List[Callable]] = {}

        # Configuration cache
        self._config_cache: Dict[str, ConfigValue] = {}
        self._cache_ttl = int(os.getenv("CONFIG_CACHE_TTL", "300"))  # 5 minutes

        # Background tasks
        self._refresh_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize configuration management system"""
        await self._ensure_config_tables()
        await self._register_default_configurations()
        await self._register_default_templates()
        await self._load_definitions()
        await self._preload_cache()

        # Start background tasks
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info("Configuration management system initialized")

    async def shutdown(self) -> None:
        """Shutdown configuration management system"""
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        await asyncio.gather(
            self._refresh_task,
            self._cleanup_task,
            return_exceptions=True
        )

        logger.info("Configuration management system shutdown completed")

    def register_definition(self, definition: ConfigDefinition) -> None:
        """Register a configuration definition"""
        self.definitions[definition.key] = definition
        logger.info("Configuration definition registered", key=definition.key)

    def register_template(self, template: ConfigTemplate) -> None:
        """Register a configuration template"""
        self.templates[template.template_id] = template
        logger.info("Configuration template registered", template_id=template.template_id)

    def add_change_listener(self, config_key: str, listener: Callable) -> None:
        """Add listener for configuration changes"""
        if config_key not in self.change_listeners:
            self.change_listeners[config_key] = []
        self.change_listeners[config_key].append(listener)

    async def get(
        self,
        key: str,
        scope: ConfigScope = ConfigScope.GLOBAL,
        scope_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """
        Get configuration value with scope resolution

        Args:
            key: Configuration key
            scope: Configuration scope
            scope_id: Scope identifier (tenant_id, user_id, etc.)
            default: Default value if not found

        Returns:
            Configuration value
        """
        try:
            # Build cache key
            cache_key = self._build_cache_key(key, scope, scope_id)

            # Check cache first
            if cache_key in self._config_cache:
                cached_value = self._config_cache[cache_key]
                if not self._is_cache_expired(cached_value):
                    return cached_value.value

            # Load from database with scope resolution
            value = await self._load_config_with_resolution(key, scope, scope_id)

            if value is not None:
                # Cache the result
                config_value = ConfigValue(
                    key=key,
                    value=value,
                    scope=scope,
                    scope_id=scope_id,
                    validated=True
                )
                self._config_cache[cache_key] = config_value
                return value

            # Fall back to default from definition
            if key in self.definitions:
                default_value = self.definitions[key].default_value
                return default_value if default_value is not None else default

            return default

        except Exception as e:
            logger.error("Error getting configuration", key=key, error=str(e))
            return default

    async def set(
        self,
        key: str,
        value: Any,
        scope: ConfigScope = ConfigScope.GLOBAL,
        scope_id: Optional[str] = None,
        set_by: Optional[str] = None,
        change_reason: Optional[str] = None,
        validate: bool = True
    ) -> bool:
        """
        Set configuration value

        Args:
            key: Configuration key
            value: Configuration value
            scope: Configuration scope
            scope_id: Scope identifier
            set_by: User who set the value
            change_reason: Reason for change
            validate: Whether to validate the value

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current value for change tracking
            current_value = await self.get(key, scope, scope_id)

            # Validate if enabled
            if validate and key in self.definitions:
                definition = self.definitions[key]
                is_valid, error_message = self.validator.validate(definition, value)

                if not is_valid:
                    logger.warning(
                        "Configuration validation failed",
                        key=key,
                        value=value,
                        error=error_message
                    )
                    return False

            # Create config value
            config_value = ConfigValue(
                key=key,
                value=value,
                scope=scope,
                scope_id=scope_id,
                set_by=set_by,
                validated=validate,
                previous_value=current_value,
                change_reason=change_reason
            )

            # Store in database
            await self._store_config_value(config_value)

            # Update cache
            cache_key = self._build_cache_key(key, scope, scope_id)
            self._config_cache[cache_key] = config_value

            # Invalidate cache for this key across all scopes
            await self._invalidate_cache_pattern(f"config:{key}:*")

            # Notify change listeners
            await self._notify_change_listeners(key, current_value, value, scope, scope_id)

            logger.info(
                "Configuration updated",
                key=key,
                scope=scope,
                scope_id=scope_id,
                previous_value=current_value,
                new_value=value
            )

            return True

        except Exception as e:
            logger.error("Error setting configuration", key=key, error=str(e))
            return False

    async def delete(
        self,
        key: str,
        scope: ConfigScope = ConfigScope.GLOBAL,
        scope_id: Optional[str] = None
    ) -> bool:
        """Delete configuration value"""
        try:
            # Get current value for change tracking
            current_value = await self.get(key, scope, scope_id)

            # Delete from database
            await self._delete_config_value(key, scope, scope_id)

            # Remove from cache
            cache_key = self._build_cache_key(key, scope, scope_id)
            self._config_cache.pop(cache_key, None)

            # Notify change listeners
            await self._notify_change_listeners(key, current_value, None, scope, scope_id)

            logger.info("Configuration deleted", key=key, scope=scope, scope_id=scope_id)
            return True

        except Exception as e:
            logger.error("Error deleting configuration", key=key, error=str(e))
            return False

    async def get_all(
        self,
        scope: Optional[ConfigScope] = None,
        scope_id: Optional[str] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all configuration values for a scope"""
        try:
            query = "SELECT key, value, scope, scope_id FROM config_values WHERE 1=1"
            params = []
            param_count = 0

            if scope:
                param_count += 1
                query += f" AND scope = ${param_count}"
                params.append(scope)

            if scope_id:
                param_count += 1
                query += f" AND scope_id = ${param_count}"
                params.append(scope_id)

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            result = {}
            for row in rows:
                key = row["key"]
                value = json.loads(row["value"]) if row["value"] else None

                # Filter by category if specified
                if category and key in self.definitions:
                    if self.definitions[key].category != category:
                        continue

                result[key] = value

            return result

        except Exception as e:
            logger.error("Error getting all configurations", error=str(e))
            return {}

    async def apply_template(
        self,
        template_id: str,
        scope: ConfigScope,
        scope_id: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
        set_by: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Apply configuration template

        Returns:
            Dictionary of key -> success status
        """
        try:
            if template_id not in self.templates:
                raise ValueError(f"Unknown template: {template_id}")

            template = self.templates[template_id]
            results = {}

            # Merge template configurations with overrides
            configs = template.configurations.copy()
            if overrides:
                configs.update(overrides)

            # Apply each configuration
            for key, value in configs.items():
                success = await self.set(
                    key=key,
                    value=value,
                    scope=scope,
                    scope_id=scope_id,
                    set_by=set_by,
                    change_reason=f"Applied template: {template_id}"
                )
                results[key] = success

            logger.info(
                "Template applied",
                template_id=template_id,
                scope=scope,
                scope_id=scope_id,
                success_count=sum(results.values()),
                total_count=len(results)
            )

            return results

        except Exception as e:
            logger.error("Error applying template", template_id=template_id, error=str(e))
            return {}

    async def export_config(
        self,
        scope: Optional[ConfigScope] = None,
        scope_id: Optional[str] = None,
        include_sensitive: bool = False
    ) -> Dict[str, Any]:
        """Export configuration as JSON"""
        try:
            configs = await self.get_all(scope, scope_id)

            # Filter sensitive configurations if requested
            if not include_sensitive:
                filtered_configs = {}
                for key, value in configs.items():
                    if key in self.definitions and self.definitions[key].sensitive:
                        filtered_configs[key] = "***REDACTED***"
                    else:
                        filtered_configs[key] = value
                configs = filtered_configs

            export_data = {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "scope": scope,
                "scope_id": scope_id,
                "configurations": configs
            }

            return export_data

        except Exception as e:
            logger.error("Error exporting configuration", error=str(e))
            return {}

    async def import_config(
        self,
        config_data: Dict[str, Any],
        scope: ConfigScope,
        scope_id: Optional[str] = None,
        set_by: Optional[str] = None,
        validate: bool = True
    ) -> Dict[str, bool]:
        """Import configuration from JSON"""
        try:
            if "configurations" not in config_data:
                raise ValueError("Invalid config data format")

            configurations = config_data["configurations"]
            results = {}

            for key, value in configurations.items():
                # Skip redacted values
                if value == "***REDACTED***":
                    continue

                success = await self.set(
                    key=key,
                    value=value,
                    scope=scope,
                    scope_id=scope_id,
                    set_by=set_by,
                    change_reason="Configuration import",
                    validate=validate
                )
                results[key] = success

            logger.info(
                "Configuration imported",
                scope=scope,
                scope_id=scope_id,
                success_count=sum(results.values()),
                total_count=len(results)
            )

            return results

        except Exception as e:
            logger.error("Error importing configuration", error=str(e))
            return {}

    async def get_change_history(
        self,
        key: Optional[str] = None,
        scope: Optional[ConfigScope] = None,
        scope_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get configuration change history"""
        try:
            query = """
            SELECT key, value, previous_value, scope, scope_id, set_by, set_at, change_reason
            FROM config_history
            WHERE 1=1
            """
            params = []
            param_count = 0

            if key:
                param_count += 1
                query += f" AND key = ${param_count}"
                params.append(key)

            if scope:
                param_count += 1
                query += f" AND scope = ${param_count}"
                params.append(scope)

            if scope_id:
                param_count += 1
                query += f" AND scope_id = ${param_count}"
                params.append(scope_id)

            query += " ORDER BY set_at DESC"

            if limit:
                param_count += 1
                query += f" LIMIT ${param_count}"
                params.append(limit)

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)

            history = []
            for row in rows:
                change = {
                    "key": row["key"],
                    "value": json.loads(row["value"]) if row["value"] else None,
                    "previous_value": json.loads(row["previous_value"]) if row["previous_value"] else None,
                    "scope": row["scope"],
                    "scope_id": row["scope_id"],
                    "set_by": row["set_by"],
                    "set_at": row["set_at"].isoformat(),
                    "change_reason": row["change_reason"]
                }
                history.append(change)

            return history

        except Exception as e:
            logger.error("Error getting change history", error=str(e))
            return []

    async def validate_all(
        self,
        scope: Optional[ConfigScope] = None,
        scope_id: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Validate all configurations in scope"""
        try:
            configs = await self.get_all(scope, scope_id)
            results = {}

            for key, value in configs.items():
                if key in self.definitions:
                    definition = self.definitions[key]
                    is_valid, error_message = self.validator.validate(definition, value)

                    results[key] = {
                        "valid": is_valid,
                        "error": error_message,
                        "value": value,
                        "definition": asdict(definition)
                    }

            return results

        except Exception as e:
            logger.error("Error validating configurations", error=str(e))
            return {}

    def _build_cache_key(self, key: str, scope: ConfigScope, scope_id: Optional[str]) -> str:
        """Build cache key for configuration"""
        return f"config:{key}:{scope}:{scope_id or 'none'}"

    def _is_cache_expired(self, config_value: ConfigValue) -> bool:
        """Check if cached value is expired"""
        if config_value.expires_at:
            return datetime.now(timezone.utc) > config_value.expires_at

        # Use default TTL
        age = (datetime.now(timezone.utc) - config_value.set_at).total_seconds()
        return age > self._cache_ttl

    async def _load_config_with_resolution(
        self,
        key: str,
        scope: ConfigScope,
        scope_id: Optional[str]
    ) -> Optional[Any]:
        """Load configuration with scope resolution (specific -> general)"""
        try:
            # Try specific scope first
            value = await self._load_config_direct(key, scope, scope_id)
            if value is not None:
                return value

            # If not found and scope is specific, try broader scopes
            if scope == ConfigScope.RESOURCE and scope_id:
                # Try user scope (extract user from resource if possible)
                # This would need resource -> user mapping logic
                pass
            elif scope == ConfigScope.USER:
                # Try tenant scope
                # This would need user -> tenant mapping logic
                pass
            elif scope in [ConfigScope.TENANT, ConfigScope.USER]:
                # Try global scope
                value = await self._load_config_direct(key, ConfigScope.GLOBAL, None)
                if value is not None:
                    return value

            return None

        except Exception as e:
            logger.error("Error loading config with resolution", key=key, error=str(e))
            return None

    async def _load_config_direct(
        self,
        key: str,
        scope: ConfigScope,
        scope_id: Optional[str]
    ) -> Optional[Any]:
        """Load configuration directly from database"""
        try:
            query = """
            SELECT value FROM config_values
            WHERE key = $1 AND scope = $2 AND scope_id = $3
            """

            async with self.database._connection_pool.acquire() as conn:
                row = await conn.fetchrow(query, key, scope, scope_id)

            if row:
                return json.loads(row["value"]) if row["value"] else None

            return None

        except Exception as e:
            logger.error("Error loading config direct", key=key, error=str(e))
            return None

    async def _store_config_value(self, config_value: ConfigValue) -> None:
        """Store configuration value in database"""
        try:
            # Store current value
            query = """
            INSERT INTO config_values (key, value, scope, scope_id, set_by, set_at, expires_at, validated, validation_error, change_reason)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (key, scope, scope_id) DO UPDATE SET
                value = EXCLUDED.value,
                set_by = EXCLUDED.set_by,
                set_at = EXCLUDED.set_at,
                expires_at = EXCLUDED.expires_at,
                validated = EXCLUDED.validated,
                validation_error = EXCLUDED.validation_error,
                change_reason = EXCLUDED.change_reason
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    config_value.key,
                    json.dumps(config_value.value),
                    config_value.scope,
                    config_value.scope_id,
                    config_value.set_by,
                    config_value.set_at,
                    config_value.expires_at,
                    config_value.validated,
                    config_value.validation_error,
                    config_value.change_reason
                )

            # Store in history
            await self._store_config_history(config_value)

        except Exception as e:
            logger.error("Error storing config value", key=config_value.key, error=str(e))
            raise

    async def _store_config_history(self, config_value: ConfigValue) -> None:
        """Store configuration change in history"""
        try:
            query = """
            INSERT INTO config_history (key, value, previous_value, scope, scope_id, set_by, set_at, change_reason)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    config_value.key,
                    json.dumps(config_value.value),
                    json.dumps(config_value.previous_value) if config_value.previous_value is not None else None,
                    config_value.scope,
                    config_value.scope_id,
                    config_value.set_by,
                    config_value.set_at,
                    config_value.change_reason
                )

        except Exception as e:
            logger.error("Error storing config history", key=config_value.key, error=str(e))

    async def _delete_config_value(
        self,
        key: str,
        scope: ConfigScope,
        scope_id: Optional[str]
    ) -> None:
        """Delete configuration value from database"""
        try:
            query = "DELETE FROM config_values WHERE key = $1 AND scope = $2 AND scope_id = $3"

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(query, key, scope, scope_id)

        except Exception as e:
            logger.error("Error deleting config value", key=key, error=str(e))
            raise

    async def _invalidate_cache_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern"""
        try:
            keys_to_remove = [
                key for key in self._config_cache.keys()
                if self._matches_pattern(key, pattern)
            ]

            for key in keys_to_remove:
                del self._config_cache[key]

            # Also invalidate Redis cache if available
            await self.cache_service.delete_pattern(pattern)

        except Exception as e:
            logger.error("Error invalidating cache pattern", pattern=pattern, error=str(e))

    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches pattern"""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)

    async def _notify_change_listeners(
        self,
        key: str,
        old_value: Any,
        new_value: Any,
        scope: ConfigScope,
        scope_id: Optional[str]
    ) -> None:
        """Notify registered change listeners"""
        try:
            if key in self.change_listeners:
                for listener in self.change_listeners[key]:
                    try:
                        if asyncio.iscoroutinefunction(listener):
                            await listener(key, old_value, new_value, scope, scope_id)
                        else:
                            listener(key, old_value, new_value, scope, scope_id)
                    except Exception as e:
                        logger.error("Change listener failed", key=key, listener=str(listener), error=str(e))

        except Exception as e:
            logger.error("Error notifying change listeners", key=key, error=str(e))

    async def _preload_cache(self) -> None:
        """Preload frequently used configurations into cache"""
        try:
            # Load global configurations
            query = """
            SELECT key, value, scope, scope_id, set_at
            FROM config_values
            WHERE scope = 'global'
            """

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query)

            for row in rows:
                cache_key = self._build_cache_key(row["key"], row["scope"], row["scope_id"])
                config_value = ConfigValue(
                    key=row["key"],
                    value=json.loads(row["value"]) if row["value"] else None,
                    scope=ConfigScope(row["scope"]),
                    scope_id=row["scope_id"],
                    set_at=row["set_at"],
                    validated=True
                )
                self._config_cache[cache_key] = config_value

            logger.info(f"Preloaded {len(rows)} configurations into cache")

        except Exception as e:
            logger.error("Error preloading cache", error=str(e))

    async def _load_definitions(self) -> None:
        """Load configuration definitions from database"""
        try:
            query = "SELECT definition_data FROM config_definitions"

            async with self.database._connection_pool.acquire() as conn:
                rows = await conn.fetch(query)

            for row in rows:
                definition_data = json.loads(row["definition_data"])
                definition = ConfigDefinition(**definition_data)
                self.definitions[definition.key] = definition

            logger.info(f"Loaded {len(rows)} configuration definitions")

        except Exception as e:
            logger.error("Error loading definitions", error=str(e))

    async def _refresh_loop(self) -> None:
        """Background task to refresh cache"""
        while True:
            try:
                await asyncio.sleep(self._cache_ttl // 2)  # Refresh at half TTL

                # Refresh expired cache entries
                current_time = datetime.now(timezone.utc)
                expired_keys = []

                for cache_key, config_value in self._config_cache.items():
                    if self._is_cache_expired(config_value):
                        expired_keys.append(cache_key)

                # Remove expired entries
                for key in expired_keys:
                    del self._config_cache[key]

                if expired_keys:
                    logger.debug(f"Refreshed {len(expired_keys)} expired cache entries")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in refresh loop", error=str(e))

    async def _cleanup_loop(self) -> None:
        """Background task to cleanup old data"""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily

                # Clean up old history entries (keep 90 days)
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)

                async with self.database._connection_pool.acquire() as conn:
                    result = await conn.execute(
                        "DELETE FROM config_history WHERE set_at < $1",
                        cutoff_date
                    )

                logger.info("Cleaned up old configuration history")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup loop", error=str(e))

    async def _register_default_configurations(self) -> None:
        """Register default configuration definitions"""
        default_configs = [
            # Sync performance configurations
            ConfigDefinition(
                key="sync.interval_seconds",
                name="Sync Interval",
                description="Default synchronization interval in seconds",
                config_type=ConfigType.INTEGER,
                default_value=300,
                scope=ConfigScope.GLOBAL,
                min_value=60,
                max_value=3600,
                category="sync"
            ),
            ConfigDefinition(
                key="sync.batch_size",
                name="Sync Batch Size",
                description="Number of items to process in each sync batch",
                config_type=ConfigType.INTEGER,
                default_value=50,
                scope=ConfigScope.GLOBAL,
                min_value=1,
                max_value=1000,
                category="sync"
            ),
            ConfigDefinition(
                key="sync.timeout_seconds",
                name="Sync Timeout",
                description="Timeout for sync operations in seconds",
                config_type=ConfigType.INTEGER,
                default_value=300,
                scope=ConfigScope.GLOBAL,
                min_value=30,
                max_value=1800,
                category="sync"
            ),
            ConfigDefinition(
                key="sync.retry_attempts",
                name="Sync Retry Attempts",
                description="Maximum number of retry attempts for failed syncs",
                config_type=ConfigType.INTEGER,
                default_value=3,
                scope=ConfigScope.GLOBAL,
                min_value=0,
                max_value=10,
                category="sync"
            ),

            # Cache configurations
            ConfigDefinition(
                key="cache.ttl_seconds",
                name="Cache TTL",
                description="Default cache time-to-live in seconds",
                config_type=ConfigType.INTEGER,
                default_value=3600,
                scope=ConfigScope.GLOBAL,
                min_value=60,
                max_value=86400,
                category="cache"
            ),
            ConfigDefinition(
                key="cache.max_size_mb",
                name="Cache Max Size",
                description="Maximum cache size in megabytes",
                config_type=ConfigType.INTEGER,
                default_value=100,
                scope=ConfigScope.GLOBAL,
                min_value=10,
                max_value=1000,
                category="cache"
            ),

            # Conflict resolution configurations
            ConfigDefinition(
                key="conflict.auto_resolve",
                name="Auto Resolve Conflicts",
                description="Enable automatic conflict resolution",
                config_type=ConfigType.BOOLEAN,
                default_value=True,
                scope=ConfigScope.TENANT,
                category="conflict"
            ),
            ConfigDefinition(
                key="conflict.resolution_strategy",
                name="Default Resolution Strategy",
                description="Default strategy for resolving conflicts",
                config_type=ConfigType.STRING,
                default_value="last_write_wins",
                scope=ConfigScope.TENANT,
                allowed_values=["last_write_wins", "first_write_wins", "merge_fields", "manual_resolution"],
                category="conflict"
            ),

            # Health monitoring configurations
            ConfigDefinition(
                key="health.check_interval_seconds",
                name="Health Check Interval",
                description="Interval between health checks in seconds",
                config_type=ConfigType.INTEGER,
                default_value=300,
                scope=ConfigScope.GLOBAL,
                min_value=60,
                max_value=3600,
                category="health"
            ),
            ConfigDefinition(
                key="health.auto_recovery",
                name="Auto Recovery",
                description="Enable automatic recovery actions",
                config_type=ConfigType.BOOLEAN,
                default_value=True,
                scope=ConfigScope.GLOBAL,
                category="health"
            ),

            # API configurations
            ConfigDefinition(
                key="api.rate_limit_per_minute",
                name="API Rate Limit",
                description="Maximum API calls per minute",
                config_type=ConfigType.INTEGER,
                default_value=1000,
                scope=ConfigScope.GLOBAL,
                min_value=100,
                max_value=10000,
                category="api"
            ),
            ConfigDefinition(
                key="api.timeout_seconds",
                name="API Timeout",
                description="API request timeout in seconds",
                config_type=ConfigType.INTEGER,
                default_value=30,
                scope=ConfigScope.GLOBAL,
                min_value=5,
                max_value=300,
                category="api"
            )
        ]

        for config in default_configs:
            self.register_definition(config)
            # Store in database
            await self._store_config_definition(config)

    async def _register_default_templates(self) -> None:
        """Register default configuration templates"""
        default_templates = [
            ConfigTemplate(
                template_id="high_performance",
                name="High Performance Sync",
                description="Optimized for high-performance synchronization",
                category="performance",
                configurations={
                    "sync.interval_seconds": 60,
                    "sync.batch_size": 100,
                    "cache.ttl_seconds": 1800,
                    "conflict.auto_resolve": True,
                    "api.rate_limit_per_minute": 2000
                },
                scope=ConfigScope.TENANT,
                tags=["performance", "fast"]
            ),
            ConfigTemplate(
                template_id="conservative",
                name="Conservative Sync",
                description="Conservative settings for stability",
                category="stability",
                configurations={
                    "sync.interval_seconds": 600,
                    "sync.batch_size": 25,
                    "sync.retry_attempts": 5,
                    "cache.ttl_seconds": 7200,
                    "conflict.auto_resolve": False
                },
                scope=ConfigScope.TENANT,
                tags=["stable", "conservative"]
            ),
            ConfigTemplate(
                template_id="development",
                name="Development Mode",
                description="Settings optimized for development",
                category="development",
                configurations={
                    "sync.interval_seconds": 120,
                    "sync.batch_size": 10,
                    "cache.ttl_seconds": 300,
                    "health.check_interval_seconds": 60,
                    "health.auto_recovery": False
                },
                scope=ConfigScope.TENANT,
                tags=["development", "debug"]
            )
        ]

        for template in default_templates:
            self.register_template(template)
            # Store in database
            await self._store_config_template(template)

    async def _store_config_definition(self, definition: ConfigDefinition) -> None:
        """Store configuration definition in database"""
        try:
            query = """
            INSERT INTO config_definitions (key, definition_data, created_at, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO UPDATE SET
                definition_data = EXCLUDED.definition_data,
                updated_at = EXCLUDED.updated_at
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    definition.key,
                    json.dumps(asdict(definition)),
                    definition.created_at,
                    definition.updated_at
                )

        except Exception as e:
            logger.error("Error storing config definition", key=definition.key, error=str(e))

    async def _store_config_template(self, template: ConfigTemplate) -> None:
        """Store configuration template in database"""
        try:
            query = """
            INSERT INTO config_templates (template_id, template_data, created_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (template_id) DO UPDATE SET
                template_data = EXCLUDED.template_data
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(
                    query,
                    template.template_id,
                    json.dumps(asdict(template)),
                    template.created_at
                )

        except Exception as e:
            logger.error("Error storing config template", template_id=template.template_id, error=str(e))

    async def _ensure_config_tables(self) -> None:
        """Ensure configuration management tables exist"""
        try:
            async with self.database._connection_pool.acquire() as conn:
                # Configuration definitions table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS config_definitions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        key VARCHAR(255) UNIQUE NOT NULL,
                        definition_data JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Configuration values table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS config_values (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        key VARCHAR(255) NOT NULL,
                        value JSONB,
                        scope VARCHAR(50) NOT NULL,
                        scope_id VARCHAR(255),
                        set_by VARCHAR(255),
                        set_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        expires_at TIMESTAMP WITH TIME ZONE,
                        validated BOOLEAN DEFAULT false,
                        validation_error TEXT,
                        change_reason TEXT,
                        UNIQUE(key, scope, scope_id)
                    )
                """)

                # Configuration history table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS config_history (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        key VARCHAR(255) NOT NULL,
                        value JSONB,
                        previous_value JSONB,
                        scope VARCHAR(50) NOT NULL,
                        scope_id VARCHAR(255),
                        set_by VARCHAR(255),
                        set_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        change_reason TEXT
                    )
                """)

                # Configuration templates table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS config_templates (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        template_id VARCHAR(255) UNIQUE NOT NULL,
                        template_data JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)

                # Create indexes
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_config_values_scope
                    ON config_values(scope, scope_id, key)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_config_history_key_time
                    ON config_history(key, set_at DESC)
                """)

        except Exception as e:
            logger.error("Failed to create configuration tables", error=str(e))
            raise