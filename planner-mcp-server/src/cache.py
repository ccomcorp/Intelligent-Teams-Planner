"""
Cache service using Redis for session management and performance optimization
with L1 in-memory cache layer
"""

import json
import asyncio
import threading
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
from functools import lru_cache

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)

class CacheError(Exception):
    """Cache operation error"""
    pass

class L1Cache:
    """Ultra-high-performance thread-safe in-memory LRU cache with sub-millisecond access"""

    def __init__(self, max_size: int = 5000, ttl: int = 300):  # Increased size for better hit ratio
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, Dict] = {}
        self._access_order: List[str] = []  # Track access order for ultra-fast LRU
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_access_time": 0.0
        }

    def get(self, key: str) -> Any:
        import time
        start_time = time.perf_counter()

        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                access_time = time.perf_counter() - start_time
                self._stats["total_access_time"] += access_time
                return None

            item = self._cache[key]
            current_time = datetime.utcnow().timestamp()

            # Ultra-fast TTL check
            if current_time > item['expires']:
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                self._stats["misses"] += 1
                access_time = time.perf_counter() - start_time
                self._stats["total_access_time"] += access_time
                return None

            # Ultra-fast LRU update
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            item['accessed'] = current_time
            self._stats["hits"] += 1

            access_time = time.perf_counter() - start_time
            self._stats["total_access_time"] += access_time

            return item['value']

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_oldest()

            expires = datetime.utcnow().timestamp() + (ttl or self.ttl)
            self._cache[key] = {
                'value': value,
                'expires': expires,
                'accessed': datetime.utcnow().timestamp()
            }

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _evict_oldest(self) -> None:
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k]['accessed']
        )
        del self._cache[oldest_key]

    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl
            }

class CacheService:
    """Redis-based cache service with L1 in-memory cache and JSON serialization"""

    def __init__(self, redis_url: str, l1_enabled: bool = True):
        self.redis_url = redis_url
        self.redis_client: redis.Redis = None
        self.l1_enabled = l1_enabled
        self.l1_cache = L1Cache() if l1_enabled else None
        self.l1_hits = 0
        self.l1_misses = 0

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                max_connections=20
            )

            # Test connection
            await self.redis_client.ping()
            logger.info("Cache service initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize cache service", error=str(e))
            raise CacheError(f"Cache initialization failed: {str(e)}")

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Cache service closed")

    async def health_check(self) -> str:
        """Check cache health"""
        try:
            await self.redis_client.ping()
            return "healthy"
        except Exception as e:
            logger.error("Cache health check failed", error=str(e))
            return "unhealthy"

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: str = "itp"
    ) -> bool:
        """Set a value in cache with optional TTL (both L1 and L2)"""
        try:
            full_key = f"{namespace}:{key}"

            # Store in L1 cache first
            if self.l1_enabled and self.l1_cache:
                self.l1_cache.set(full_key, value, ttl)

            # Serialize value to JSON for Redis
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, default=str)
            elif isinstance(value, (datetime,)):
                serialized_value = value.isoformat()
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
        namespace: str = "itp",
        default: Any = None
    ) -> Any:
        """Get a value from cache (L1 then L2)"""
        try:
            full_key = f"{namespace}:{key}"

            # Check L1 cache first
            if self.l1_enabled and self.l1_cache:
                l1_value = self.l1_cache.get(full_key)
                if l1_value is not None:
                    self.l1_hits += 1
                    return l1_value
                self.l1_misses += 1

            # Check Redis (L2)
            value = await self.redis_client.get(full_key)

            if value is None:
                return default

            # Try to deserialize JSON
            try:
                deserialized_value = json.loads(value)
            except json.JSONDecodeError:
                # Return as string if not JSON
                deserialized_value = value

            # Store in L1 cache for next time
            if self.l1_enabled and self.l1_cache:
                self.l1_cache.set(full_key, deserialized_value)

            return deserialized_value

        except Exception as e:
            logger.error("Error getting cache value", key=key, error=str(e))
            return default

    async def delete(self, key: str, namespace: str = "itp") -> bool:
        """Delete a value from cache (both L1 and L2)"""
        try:
            full_key = f"{namespace}:{key}"

            # Delete from L1 cache
            if self.l1_enabled and self.l1_cache:
                self.l1_cache.delete(full_key)

            # Delete from Redis
            result = await self.redis_client.delete(full_key)
            return result > 0

        except Exception as e:
            logger.error("Error deleting cache value", key=key, error=str(e))
            return False

    async def exists(self, key: str, namespace: str = "itp") -> bool:
        """Check if key exists in cache"""
        try:
            full_key = f"{namespace}:{key}"
            result = await self.redis_client.exists(full_key)
            return result > 0

        except Exception as e:
            logger.error("Error checking cache key existence", key=key, error=str(e))
            return False

    async def ttl(self, key: str, namespace: str = "itp") -> int:
        """Get TTL for a key"""
        try:
            full_key = f"{namespace}:{key}"
            return await self.redis_client.ttl(full_key)

        except Exception as e:
            logger.error("Error getting TTL", key=key, error=str(e))
            return -1

    async def expire(self, key: str, ttl: int, namespace: str = "itp") -> bool:
        """Set TTL for existing key"""
        try:
            full_key = f"{namespace}:{key}"
            result = await self.redis_client.expire(full_key, ttl)
            return result

        except Exception as e:
            logger.error("Error setting expiration", key=key, error=str(e))
            return False

    async def increment(
        self,
        key: str,
        amount: int = 1,
        namespace: str = "itp",
        ttl: Optional[int] = None
    ) -> int:
        """Increment a numeric value"""
        try:
            full_key = f"{namespace}:{key}"
            result = await self.redis_client.incrby(full_key, amount)

            # Set TTL if specified and key was just created
            if ttl and result == amount:
                await self.redis_client.expire(full_key, ttl)

            return result

        except Exception as e:
            logger.error("Error incrementing cache value", key=key, error=str(e))
            return 0

    async def get_multiple(
        self,
        keys: List[str],
        namespace: str = "itp"
    ) -> Dict[str, Any]:
        """Get multiple values at once"""
        try:
            full_keys = [f"{namespace}:{key}" for key in keys]
            values = await self.redis_client.mget(full_keys)

            result = {}
            for i, key in enumerate(keys):
                value = values[i]
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value

            return result

        except Exception as e:
            logger.error("Error getting multiple cache values", keys=keys, error=str(e))
            return {}

    async def set_multiple(
        self,
        data: Dict[str, Any],
        namespace: str = "itp",
        ttl: Optional[int] = None
    ) -> bool:
        """Set multiple values at once"""
        try:
            # Prepare data for mset
            serialized_data = {}
            for key, value in data.items():
                full_key = f"{namespace}:{key}"
                if isinstance(value, (dict, list)):
                    serialized_data[full_key] = json.dumps(value, default=str)
                elif isinstance(value, datetime):
                    serialized_data[full_key] = value.isoformat()
                else:
                    serialized_data[full_key] = str(value)

            await self.redis_client.mset(serialized_data)

            # Set TTL for all keys if specified
            if ttl:
                tasks = [
                    self.redis_client.expire(f"{namespace}:{key}", ttl)
                    for key in data.keys()
                ]
                await asyncio.gather(*tasks)

            return True

        except Exception as e:
            logger.error("Error setting multiple cache values", error=str(e))
            return False

    async def get_keys_pattern(
        self,
        pattern: str,
        namespace: str = "itp"
    ) -> List[str]:
        """Get keys matching a pattern"""
        try:
            full_pattern = f"{namespace}:{pattern}"
            keys = await self.redis_client.keys(full_pattern)

            # Remove namespace prefix
            return [key.replace(f"{namespace}:", "") for key in keys]

        except Exception as e:
            logger.error("Error getting keys by pattern", pattern=pattern, error=str(e))
            return []

    async def delete_pattern(
        self,
        pattern: str,
        namespace: str = "itp"
    ) -> int:
        """Delete keys matching a pattern"""
        try:
            full_pattern = f"{namespace}:{pattern}"
            keys = await self.redis_client.keys(full_pattern)

            if keys:
                return await self.redis_client.delete(*keys)
            return 0

        except Exception as e:
            logger.error("Error deleting keys by pattern", pattern=pattern, error=str(e))
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics (L1 and L2)"""
        try:
            info = await self.redis_client.info()

            stats = {
                "redis": {
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "used_memory_human": info.get("used_memory_human", "0B"),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "uptime_in_seconds": info.get("uptime_in_seconds", 0)
                }
            }

            # Add L1 cache stats if enabled
            if self.l1_enabled and self.l1_cache:
                l1_stats = self.l1_cache.stats()
                total_requests = self.l1_hits + self.l1_misses
                hit_rate = (self.l1_hits / total_requests * 100) if total_requests > 0 else 0

                stats["l1_cache"] = {
                    "enabled": True,
                    "hits": self.l1_hits,
                    "misses": self.l1_misses,
                    "hit_rate_percent": round(hit_rate, 2),
                    **l1_stats
                }
            else:
                stats["l1_cache"] = {"enabled": False}

            return stats

        except Exception as e:
            logger.error("Error getting cache stats", error=str(e))
            return {"error": str(e)}

    # Session management helpers
    async def create_session(
        self,
        session_id: str,
        user_id: str,
        session_data: Dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """Create a user session"""
        session_info = {
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            **session_data
        }

        return await self.set(
            f"session:{session_id}",
            session_info,
            ttl=ttl,
            namespace="sessions"
        )

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        return await self.get(
            f"session:{session_id}",
            namespace="sessions"
        )

    async def update_session_activity(self, session_id: str) -> bool:
        """Update session last activity timestamp"""
        session_data = await self.get_session(session_id)
        if session_data:
            session_data["last_activity"] = datetime.utcnow().isoformat()
            return await self.set(
                f"session:{session_id}",
                session_data,
                ttl=3600,  # Reset TTL
                namespace="sessions"
            )
        return False

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        return await self.delete(
            f"session:{session_id}",
            namespace="sessions"
        )

    # Rate limiting helpers
    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window: int,
        namespace: str = "rate_limit"
    ) -> Dict[str, Any]:
        """Check and update rate limit"""
        try:
            key = f"{namespace}:{identifier}"
            current_count = await self.get(key, default=0)

            if isinstance(current_count, str):
                current_count = int(current_count)

            if current_count >= limit:
                ttl = await self.ttl(key, namespace=namespace)
                return {
                    "allowed": False,
                    "current_count": current_count,
                    "limit": limit,
                    "reset_in": ttl
                }

            # Increment counter
            new_count = await self.increment(key, namespace=namespace, ttl=window)

            return {
                "allowed": True,
                "current_count": new_count,
                "limit": limit,
                "reset_in": window
            }

        except Exception as e:
            logger.error("Error checking rate limit", identifier=identifier, error=str(e))
            # Allow request on error
            return {
                "allowed": True,
                "current_count": 0,
                "limit": limit,
                "error": str(e)
            }

    # Redis list operations for notification queues
    async def lpush(self, key: str, value: Any, namespace: str = "itp") -> int:
        """Push value to the left (head) of the list"""
        try:
            full_key = f"{namespace}:{key}"

            # Serialize value to JSON if needed
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, default=str)
            elif isinstance(value, datetime):
                serialized_value = value.isoformat()
            else:
                serialized_value = str(value)

            return await self.redis_client.lpush(full_key, serialized_value)

        except Exception as e:
            logger.error("Error pushing to list", key=key, error=str(e))
            return 0

    async def rpush(self, key: str, value: Any, namespace: str = "itp") -> int:
        """Push value to the right (tail) of the list"""
        try:
            full_key = f"{namespace}:{key}"

            # Serialize value to JSON if needed
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, default=str)
            elif isinstance(value, datetime):
                serialized_value = value.isoformat()
            else:
                serialized_value = str(value)

            return await self.redis_client.rpush(full_key, serialized_value)

        except Exception as e:
            logger.error("Error pushing to list", key=key, error=str(e))
            return 0

    async def lpop(self, key: str, namespace: str = "itp") -> Any:
        """Pop value from the left (head) of the list"""
        try:
            full_key = f"{namespace}:{key}"
            value = await self.redis_client.lpop(full_key)

            if value is None:
                return None

            # Try to deserialize JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        except Exception as e:
            logger.error("Error popping from list", key=key, error=str(e))
            return None

    async def rpop(self, key: str, namespace: str = "itp") -> Any:
        """Pop value from the right (tail) of the list"""
        try:
            full_key = f"{namespace}:{key}"
            value = await self.redis_client.rpop(full_key)

            if value is None:
                return None

            # Try to deserialize JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        except Exception as e:
            logger.error("Error popping from list", key=key, error=str(e))
            return None

    async def llen(self, key: str, namespace: str = "itp") -> int:
        """Get length of the list"""
        try:
            full_key = f"{namespace}:{key}"
            return await self.redis_client.llen(full_key)

        except Exception as e:
            logger.error("Error getting list length", key=key, error=str(e))
            return 0

    async def lrange(self, key: str, start: int = 0, end: int = -1, namespace: str = "itp") -> List[Any]:
        """Get a range of elements from the list"""
        try:
            full_key = f"{namespace}:{key}"
            values = await self.redis_client.lrange(full_key, start, end)

            # Deserialize values
            result = []
            for value in values:
                try:
                    result.append(json.loads(value))
                except json.JSONDecodeError:
                    result.append(value)

            return result

        except Exception as e:
            logger.error("Error getting list range", key=key, error=str(e))
            return []

    async def lrem(self, key: str, count: int, value: Any, namespace: str = "itp") -> int:
        """Remove elements from the list"""
        try:
            full_key = f"{namespace}:{key}"

            # Serialize value to match stored format
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, default=str)
            elif isinstance(value, datetime):
                serialized_value = value.isoformat()
            else:
                serialized_value = str(value)

            return await self.redis_client.lrem(full_key, count, serialized_value)

        except Exception as e:
            logger.error("Error removing from list", key=key, error=str(e))
            return 0

    async def ltrim(self, key: str, start: int, end: int, namespace: str = "itp") -> bool:
        """Trim list to specified range"""
        try:
            full_key = f"{namespace}:{key}"
            await self.redis_client.ltrim(full_key, start, end)
            return True

        except Exception as e:
            logger.error("Error trimming list", key=key, error=str(e))
            return False

    # Cache invalidation helpers
    async def invalidate_tags(self, tags: List[str], namespace: str = "itp") -> int:
        """Invalidate all cache entries with specified tags"""
        if not tags:
            return 0

        try:
            keys_to_delete = []
            for tag in tags:
                tag_keys = await self.get_keys_pattern(f"tag:{tag}:*", namespace)
                keys_to_delete.extend(tag_keys)

            if keys_to_delete:
                # Remove duplicates
                unique_keys = list(set(keys_to_delete))

                # Delete from L1 cache
                if self.l1_enabled and self.l1_cache:
                    for key in unique_keys:
                        self.l1_cache.delete(f"{namespace}:{key}")

                # Delete from Redis
                full_keys = [f"{namespace}:{key}" for key in unique_keys]
                deleted = await self.redis_client.delete(*full_keys)

                logger.info("Invalidated cache entries", tags=tags, count=deleted)
                return deleted

            return 0

        except Exception as e:
            logger.error("Error invalidating cache tags", tags=tags, error=str(e))
            return 0

    async def set_with_tags(
        self,
        key: str,
        value: Any,
        tags: List[str],
        ttl: Optional[int] = None,
        namespace: str = "itp"
    ) -> bool:
        """Set a cache value with associated tags for invalidation"""
        try:
            # Set the main cache entry
            success = await self.set(key, value, ttl, namespace)
            if not success:
                return False

            # Set tag associations
            for tag in tags:
                tag_key = f"tag:{tag}:{key}"
                await self.set(tag_key, True, ttl, namespace)

            return True

        except Exception as e:
            logger.error("Error setting cache with tags", key=key, tags=tags, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str, namespace: str = "itp") -> int:
        """Invalidate cache entries matching a pattern"""
        try:
            keys = await self.get_keys_pattern(pattern, namespace)
            if not keys:
                return 0

            # Delete from L1 cache
            if self.l1_enabled and self.l1_cache:
                for key in keys:
                    self.l1_cache.delete(f"{namespace}:{key}")

            # Delete from Redis
            return await self.delete_pattern(pattern, namespace)

        except Exception as e:
            logger.error("Error invalidating pattern", pattern=pattern, error=str(e))
            return 0

    async def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cache entries for a specific user"""
        return await self.invalidate_pattern(f"user:{user_id}:*")

    async def invalidate_team_cache(self, team_id: str) -> int:
        """Invalidate all cache entries for a specific team"""
        return await self.invalidate_pattern(f"team:{team_id}:*")

    async def invalidate_plan_cache(self, plan_id: str) -> int:
        """Invalidate all cache entries for a specific plan"""
        return await self.invalidate_pattern(f"plan:{plan_id}:*")