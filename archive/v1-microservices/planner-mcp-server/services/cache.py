import json
from typing import Optional, Any
import redis.asyncio as redis
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)

class CacheService:
    """Redis-based caching service for Graph API responses"""

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.default_ttl = 300  # 5 minutes

    async def get(self, key: str) -> Optional[Any]:
        """Get cached data by key"""
        try:
            cached_data = await self.redis_client.get(f"cache:{key}")
            if cached_data:
                data = json.loads(cached_data)
                logger.debug("Cache hit", key=key)
                return data
            logger.debug("Cache miss", key=key)
            return None
        except Exception as e:
            logger.warning("Cache get error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set cached data with optional TTL"""
        try:
            cache_ttl = ttl or self.default_ttl
            await self.redis_client.setex(
                f"cache:{key}",
                cache_ttl,
                json.dumps(value, default=str)
            )
            logger.debug("Cache set", key=key, ttl=cache_ttl)
            return True
        except Exception as e:
            logger.warning("Cache set error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete cached data by key"""
        try:
            deleted = await self.redis_client.delete(f"cache:{key}")
            logger.debug("Cache delete", key=key, deleted=bool(deleted))
            return bool(deleted)
        except Exception as e:
            logger.warning("Cache delete error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        try:
            keys = await self.redis_client.keys(f"cache:{pattern}")
            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.debug("Cache pattern delete", pattern=pattern, deleted=deleted)
                return deleted
            return 0
        except Exception as e:
            logger.warning("Cache pattern delete error", pattern=pattern, error=str(e))
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            exists = await self.redis_client.exists(f"cache:{key}")
            return bool(exists)
        except Exception as e:
            logger.warning("Cache exists error", key=key, error=str(e))
            return False

    async def get_stats(self) -> dict:
        """Get cache statistics"""
        try:
            info = await self.redis_client.info("memory")
            keyspace = await self.redis_client.info("keyspace")

            cache_keys = await self.redis_client.keys("cache:*")

            return {
                "total_memory": info.get("used_memory_human", "Unknown"),
                "cache_keys_count": len(cache_keys),
                "redis_version": info.get("redis_version", "Unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "keyspace_hits": keyspace.get("keyspace_hits", 0),
                "keyspace_misses": keyspace.get("keyspace_misses", 0)
            }
        except Exception as e:
            logger.error("Error getting cache stats", error=str(e))
            return {"error": str(e)}

    async def clear_user_cache(self, user_id: str) -> int:
        """Clear all cache entries for a specific user"""
        patterns = [
            f"user_tasks:{user_id}:*",
            f"user_plans:{user_id}",
            f"plan_buckets:*"  # Plan buckets might be shared
        ]

        total_deleted = 0
        for pattern in patterns:
            deleted = await self.delete_pattern(pattern)
            total_deleted += deleted

        logger.info("Cleared user cache", user_id=user_id, entries_deleted=total_deleted)
        return total_deleted

    async def warm_cache(self, access_token: str, user_id: str):
        """Warm up cache with commonly accessed data"""
        try:
            from services.graph_api import GraphAPIService

            graph_service = GraphAPIService(self.redis_client)

            # Pre-load user plans
            plans = await graph_service.get_user_plans(access_token)
            logger.info("Cache warmed with user plans", user_id=user_id, plans_count=len(plans))

            # Pre-load buckets for each plan
            for plan in plans[:5]:  # Limit to first 5 plans
                buckets = await graph_service.get_plan_buckets(access_token, plan.id)
                logger.debug("Cache warmed with plan buckets", plan_id=plan.id, buckets_count=len(buckets))

        except Exception as e:
            logger.warning("Cache warm-up failed", user_id=user_id, error=str(e))

    def create_cache_key(self, *args) -> str:
        """Create a consistent cache key from arguments"""
        key_parts = []
        for arg in args:
            if isinstance(arg, str):
                key_parts.append(arg)
            else:
                key_parts.append(str(hash(str(arg))))
        return ":".join(key_parts)