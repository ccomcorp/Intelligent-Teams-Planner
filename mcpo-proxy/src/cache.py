"""
Simple cache service for MCPO Proxy
"""

import json
from typing import Any, Optional

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)


class ProxyCacheError(Exception):
    """Proxy cache error"""
    pass


class ProxyCache:
    """Simple Redis cache for MCPO Proxy"""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: redis.Redis = None

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )

            # Test connection
            await self.redis_client.ping()
            logger.info("Proxy cache initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize proxy cache", error=str(e))
            raise ProxyCacheError(f"Cache initialization failed: {str(e)}")

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Proxy cache closed")

    async def health_check(self) -> str:
        """Check cache health"""
        try:
            await self.redis_client.ping()
            return "healthy"
        except Exception as e:
            logger.error("Proxy cache health check failed", error=str(e))
            return "unhealthy"

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: str = "mcpo"
    ) -> bool:
        """Set a value in cache"""
        try:
            full_key = f"{namespace}:{key}"

            # Serialize value
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, default=str)
            else:
                serialized_value = str(value)

            if ttl:
                await self.redis_client.setex(full_key, ttl, serialized_value)
            else:
                await self.redis_client.set(full_key, serialized_value)

            return True

        except Exception as e:
            logger.error("Error setting cache value", key=key, error=str(e))
            return False

    async def get(
        self,
        key: str,
        namespace: str = "mcpo",
        default: Any = None
    ) -> Any:
        """Get a value from cache"""
        try:
            full_key = f"{namespace}:{key}"
            value = await self.redis_client.get(full_key)

            if value is None:
                return default

            # Try to deserialize JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        except Exception as e:
            logger.error("Error getting cache value", key=key, error=str(e))
            return default

    async def delete(self, key: str, namespace: str = "mcpo") -> bool:
        """Delete a value from cache"""
        try:
            full_key = f"{namespace}:{key}"
            result = await self.redis_client.delete(full_key)
            return result > 0

        except Exception as e:
            logger.error("Error deleting cache value", key=key, error=str(e))
            return False

    async def exists(self, key: str, namespace: str = "mcpo") -> bool:
        """Check if key exists"""
        try:
            full_key = f"{namespace}:{key}"
            result = await self.redis_client.exists(full_key)
            return result > 0

        except Exception as e:
            logger.error("Error checking cache key existence", key=key, error=str(e))
            return False
