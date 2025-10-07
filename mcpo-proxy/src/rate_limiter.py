"""
Rate limiting and performance optimization for MCPO Proxy
Task 7: Rate limiting and performance optimization
"""

import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from collections import defaultdict, deque
from dataclasses import dataclass

import structlog

try:
    from .cache import ProxyCache
except ImportError:
    # For testing
    from cache import ProxyCache

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration"""
    requests: int
    window_seconds: int
    burst_allowance: int = 0
    description: str = ""


class TokenBucket:
    """Token bucket algorithm implementation for rate limiting"""

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens, return True if allowed"""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate)
        )
        self.last_refill = now

    def get_status(self) -> Dict[str, Any]:
        """Get current bucket status"""
        self._refill()
        return {
            "tokens_available": int(self.tokens),
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "utilization_percent": round((1 - self.tokens / self.capacity) * 100, 2)
        }


class AdvancedRateLimiter:
    """Advanced rate limiter with multiple strategies"""

    def __init__(self, cache: Optional[ProxyCache] = None):
        self.cache = cache
        self.token_buckets: Dict[str, TokenBucket] = {}
        self.sliding_windows: Dict[str, deque] = {}
        self.rate_limit_rules = {
            "default": RateLimitRule(100, 60, 10, "Default rate limit"),
            "authenticated": RateLimitRule(1000, 60, 50, "Authenticated users"),
            "premium": RateLimitRule(5000, 60, 100, "Premium users"),
            "system": RateLimitRule(10000, 60, 200, "System/admin users"),
            "per_tool": RateLimitRule(50, 60, 5, "Per tool rate limit")
        }

    async def check_rate_limit(
        self,
        client_id: str,
        rule_name: str = "default",
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Check if request is within rate limits"""
        try:
            rule = self.rate_limit_rules.get(rule_name, self.rate_limit_rules["default"])

            # Use token bucket for primary rate limiting
            bucket_key = f"{client_id}:{rule_name}"
            if bucket_key not in self.token_buckets:
                self.token_buckets[bucket_key] = TokenBucket(
                    capacity=rule.requests + rule.burst_allowance,
                    refill_rate=rule.requests / rule.window_seconds
                )

            bucket = self.token_buckets[bucket_key]
            allowed = bucket.consume(1)

            # Additional sliding window check for precision
            window_key = f"window:{bucket_key}"
            current_time = time.time()

            if window_key not in self.sliding_windows:
                self.sliding_windows[window_key] = deque()

            # Clean old requests from sliding window
            window = self.sliding_windows[window_key]
            while window and window[0] < current_time - rule.window_seconds:
                window.popleft()

            # Check sliding window limit
            if len(window) >= rule.requests and allowed:
                # Token bucket allowed but sliding window is full
                allowed = False

            if allowed:
                window.append(current_time)

            # Calculate reset time
            if window:
                reset_time = window[0] + rule.window_seconds
            else:
                reset_time = current_time + rule.window_seconds

            result = {
                "allowed": allowed,
                "rule_name": rule_name,
                "limit": rule.requests,
                "remaining": max(0, rule.requests - len(window)),
                "reset_time": reset_time,
                "retry_after": max(0, int(reset_time - current_time)) if not allowed else 0,
                "bucket_status": bucket.get_status(),
                "window_count": len(window)
            }

            # Store in cache for distributed rate limiting
            if self.cache and not allowed:
                await self._store_rate_limit_violation(client_id, rule_name, result)

            logger.debug(
                "Rate limit check",
                client_id=client_id,
                rule_name=rule_name,
                allowed=allowed,
                remaining=result["remaining"]
            )

            return result

        except Exception as e:
            logger.error("Rate limit check error", client_id=client_id, error=str(e))
            # Allow request on error to prevent DoS
            return {
                "allowed": True,
                "error": str(e),
                "rule_name": rule_name,
                "limit": 0,
                "remaining": 0
            }

    async def check_tool_rate_limit(
        self,
        client_id: str,
        tool_name: str,
        user_type: str = "default"
    ) -> Dict[str, Any]:
        """Check rate limits specific to tool usage"""
        try:
            # Combine client and tool for specific limiting
            tool_client_key = f"{client_id}:tool:{tool_name}"

            # Check per-tool rate limit
            tool_result = await self.check_rate_limit(
                tool_client_key,
                "per_tool",
                {"tool_name": tool_name}
            )

            # Check user-type rate limit
            user_result = await self.check_rate_limit(client_id, user_type)

            # Most restrictive limit wins
            if not tool_result["allowed"]:
                tool_result["limit_type"] = "per_tool"
                return tool_result
            elif not user_result["allowed"]:
                user_result["limit_type"] = "user_type"
                return user_result
            else:
                # Both allowed, return combined info
                return {
                    "allowed": True,
                    "limit_type": "both",
                    "tool_limit": tool_result,
                    "user_limit": user_result
                }

        except Exception as e:
            logger.error("Tool rate limit check error", tool_name=tool_name, error=str(e))
            return {"allowed": True, "error": str(e)}

    async def _store_rate_limit_violation(
        self,
        client_id: str,
        rule_name: str,
        result: Dict[str, Any]
    ):
        """Store rate limit violation for analysis"""
        try:
            if self.cache:
                violation_data = {
                    "client_id": client_id,
                    "rule_name": rule_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "limit": result["limit"],
                    "window_count": result["window_count"]
                }
                await self.cache.set(
                    f"rate_limit_violation:{client_id}:{int(time.time())}",
                    violation_data,
                    ttl=3600  # Keep for 1 hour
                )
        except Exception as e:
            logger.error("Error storing rate limit violation", error=str(e))

    def get_rate_limit_stats(self) -> Dict[str, Any]:
        """Get comprehensive rate limiting statistics"""
        try:
            stats = {
                "active_buckets": len(self.token_buckets),
                "active_windows": len(self.sliding_windows),
                "rules": {
                    name: {
                        "requests": rule.requests,
                        "window_seconds": rule.window_seconds,
                        "burst_allowance": rule.burst_allowance,
                        "description": rule.description
                    }
                    for name, rule in self.rate_limit_rules.items()
                },
                "bucket_utilization": {}
            }

            # Calculate bucket utilization
            for bucket_key, bucket in self.token_buckets.items():
                bucket_status = bucket.get_status()
                stats["bucket_utilization"][bucket_key] = bucket_status["utilization_percent"]

            return stats

        except Exception as e:
            logger.error("Error getting rate limit stats", error=str(e))
            return {"error": str(e)}


class ConnectionPoolManager:
    """Manage connection pooling for optimal performance"""

    def __init__(self):
        self.pool_configs = {
            "mcp_server": {
                "max_connections": 100,
                "max_keepalive": 50,
                "keepalive_timeout": 30,
                "connection_timeout": 10
            },
            "redis": {
                "max_connections": 20,
                "max_keepalive": 10,
                "keepalive_timeout": 60,
                "connection_timeout": 5
            }
        }
        self.connection_stats = defaultdict(lambda: {
            "active": 0,
            "total_created": 0,
            "total_closed": 0,
            "errors": 0
        })

    def get_optimal_pool_size(self, service_name: str, current_load: float) -> Dict[str, int]:
        """Calculate optimal pool size based on current load"""
        base_config = self.pool_configs.get(service_name, self.pool_configs["mcp_server"])

        # Adjust based on load (0.0 to 1.0)
        load_factor = max(0.1, min(1.0, current_load))

        optimal_config = {
            "max_connections": int(base_config["max_connections"] * load_factor),
            "max_keepalive": int(base_config["max_keepalive"] * load_factor),
            "keepalive_timeout": base_config["keepalive_timeout"],
            "connection_timeout": base_config["connection_timeout"]
        }

        return optimal_config

    def record_connection_event(self, service_name: str, event_type: str):
        """Record connection events for monitoring"""
        if event_type == "created":
            self.connection_stats[service_name]["total_created"] += 1
            self.connection_stats[service_name]["active"] += 1
        elif event_type == "closed":
            self.connection_stats[service_name]["total_closed"] += 1
            self.connection_stats[service_name]["active"] = max(
                0, self.connection_stats[service_name]["active"] - 1
            )
        elif event_type == "error":
            self.connection_stats[service_name]["errors"] += 1

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return dict(self.connection_stats)


class CacheOptimizer:
    """Optimize caching strategies for performance"""

    def __init__(self, cache: ProxyCache):
        self.cache = cache
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_requests": 0
        }
        self.cache_strategies = {
            "tool_discovery": {"ttl": 300, "priority": "high"},    # 5 minutes
            "user_auth": {"ttl": 1800, "priority": "medium"},      # 30 minutes
            "mcp_responses": {"ttl": 60, "priority": "low"},       # 1 minute for frequently changing data
            "rate_limits": {"ttl": 3600, "priority": "medium"}     # 1 hour
        }

    async def get_cached_or_compute(
        self,
        cache_key: str,
        compute_func: callable,
        category: str = "default",
        force_refresh: bool = False
    ) -> Tuple[Any, bool]:
        """Get from cache or compute with optimized strategy"""
        try:
            self.cache_stats["total_requests"] += 1

            # Try cache first (unless force refresh)
            if not force_refresh:
                cached_value = await self.cache.get(cache_key)
                if cached_value is not None:
                    self.cache_stats["hits"] += 1
                    logger.debug("Cache hit", cache_key=cache_key[:50])
                    return cached_value, True

            # Cache miss - compute value
            self.cache_stats["misses"] += 1
            logger.debug("Cache miss, computing", cache_key=cache_key[:50])

            computed_value = await compute_func()

            # Store in cache with appropriate strategy
            strategy = self.cache_strategies.get(category, {"ttl": 300, "priority": "medium"})
            await self.cache.set(cache_key, computed_value, ttl=strategy["ttl"])

            return computed_value, False

        except Exception as e:
            logger.error("Cache optimization error", cache_key=cache_key[:50], error=str(e))
            # Fall back to computing without cache
            try:
                return await compute_func(), False
            except Exception as compute_error:
                logger.error("Compute function failed", error=str(compute_error))
                raise

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        if self.cache_stats["total_requests"] == 0:
            return 0.0
        return (self.cache_stats["hits"] / self.cache_stats["total_requests"]) * 100

    async def optimize_cache_cleanup(self):
        """Perform cache cleanup and optimization"""
        try:
            # This would implement cache eviction policies
            # For now, just log current stats
            hit_rate = self.get_cache_hit_rate()
            logger.info(
                "Cache optimization check",
                hit_rate=round(hit_rate, 2),
                total_requests=self.cache_stats["total_requests"],
                hits=self.cache_stats["hits"],
                misses=self.cache_stats["misses"]
            )

            # Reset stats periodically to prevent overflow
            if self.cache_stats["total_requests"] > 10000:
                self.cache_stats = {
                    "hits": 0,
                    "misses": 0,
                    "evictions": 0,
                    "total_requests": 0
                }

        except Exception as e:
            logger.error("Cache cleanup error", error=str(e))


class PerformanceOptimizer:
    """Main performance optimization coordinator"""

    def __init__(self, cache: ProxyCache):
        self.rate_limiter = AdvancedRateLimiter(cache)
        self.connection_manager = ConnectionPoolManager()
        self.cache_optimizer = CacheOptimizer(cache)
        self.optimization_history = deque(maxlen=100)

    async def optimize_request_handling(
        self,
        request_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimize handling of individual requests"""
        try:
            optimizations = []

            # Rate limiting optimization
            client_id = request_context.get("client_id", "unknown")
            user_type = request_context.get("user_type", "default")

            rate_limit_result = await self.rate_limiter.check_rate_limit(client_id, user_type)
            if not rate_limit_result["allowed"]:
                return {
                    "optimized": False,
                    "rate_limited": True,
                    "rate_limit_info": rate_limit_result
                }

            optimizations.append("rate_limit_passed")

            # Connection pool optimization
            current_load = request_context.get("current_load", 0.5)
            optimal_pool = self.connection_manager.get_optimal_pool_size("mcp_server", current_load)
            optimizations.append(f"pool_optimized_for_load_{current_load}")

            # Cache strategy optimization
            tool_name = request_context.get("tool_name")
            if tool_name:
                # Use tool-specific caching strategy
                optimizations.append("tool_cache_strategy")

            optimization_result = {
                "optimized": True,
                "optimizations_applied": optimizations,
                "rate_limit_info": rate_limit_result,
                "optimal_pool_config": optimal_pool,
                "cache_hit_rate": self.cache_optimizer.get_cache_hit_rate(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            self.optimization_history.append(optimization_result)

            return optimization_result

        except Exception as e:
            logger.error("Performance optimization error", error=str(e))
            return {
                "optimized": False,
                "error": str(e)
            }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        try:
            return {
                "rate_limiting": self.rate_limiter.get_rate_limit_stats(),
                "connection_pooling": self.connection_manager.get_connection_stats(),
                "cache_performance": {
                    "hit_rate_percent": round(self.cache_optimizer.get_cache_hit_rate(), 2),
                    "stats": self.cache_optimizer.cache_stats
                },
                "optimization_history": list(self.optimization_history)[-10:],  # Last 10
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error("Error getting performance metrics", error=str(e))
            return {"error": str(e)}


# Global performance optimizer instance
performance_optimizer: Optional[PerformanceOptimizer] = None


def initialize_performance_optimizer(cache: ProxyCache):
    """Initialize global performance optimizer"""
    global performance_optimizer
    performance_optimizer = PerformanceOptimizer(cache)
    logger.info("Performance optimizer initialized")


def get_performance_optimizer() -> Optional[PerformanceOptimizer]:
    """Get global performance optimizer instance"""
    return performance_optimizer
