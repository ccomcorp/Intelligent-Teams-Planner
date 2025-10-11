"""
Enhanced Delta Query Optimization with Batching and Caching
Story 8.1 Task 2.4: Advanced delta query performance optimization

Implements sophisticated optimization strategies for Microsoft Graph delta queries
including intelligent batching, multi-level caching, and adaptive performance tuning.
"""

import asyncio
import json
import hashlib
import time
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..database import Database
from ..cache import CacheService
from ..models.graph_models import DeltaResult, ResourceChange
from .status_tracker import SyncStatusTracker, SyncType, SyncDirection
from ..utils.performance_monitor import get_performance_monitor, track_operation

logger = structlog.get_logger(__name__)


class CacheLevel(str, Enum):
    """Cache hierarchy levels"""

    L1_MEMORY = "l1_memory"        # In-memory cache (fastest)
    L2_REDIS = "l2_redis"          # Redis cache (fast)
    L3_DATABASE = "l3_database"    # Database cache (persistent)


class BatchStrategy(str, Enum):
    """Delta query batching strategies"""

    RESOURCE_TYPE = "resource_type"    # Batch by resource type
    TENANT = "tenant"                  # Batch by tenant
    TIME_WINDOW = "time_window"        # Batch by time window
    ADAPTIVE = "adaptive"              # Adaptive based on performance


@dataclass
class CacheEntry:
    """Multi-level cache entry"""

    key: str
    data: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    cache_level: CacheLevel = CacheLevel.L1_MEMORY
    size_bytes: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchRequest:
    """Delta query batch request"""

    batch_id: str
    resource_type: str
    user_ids: Set[str]
    tenant_ids: Set[str]
    resource_ids: Set[str]
    priority: int = 5  # 1-10 scale
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    estimated_cost: Optional[float] = None
    dependencies: Set[str] = field(default_factory=set)


@dataclass
class OptimizationMetrics:
    """Performance optimization metrics"""

    # Cache performance
    cache_hit_rate_l1: float = 0.0
    cache_hit_rate_l2: float = 0.0
    cache_hit_rate_l3: float = 0.0
    cache_eviction_rate: float = 0.0

    # Batch performance
    avg_batch_size: float = 0.0
    avg_batch_processing_time: float = 0.0
    batch_efficiency_score: float = 0.0

    # Query performance
    avg_query_response_time: float = 0.0
    queries_per_second: float = 0.0
    api_rate_limit_hits: int = 0

    # Resource efficiency
    memory_usage_mb: float = 0.0
    cpu_utilization_percent: float = 0.0
    network_bytes_saved: int = 0

    # Adaptive metrics
    optimization_score: float = 0.0
    last_optimization_time: Optional[datetime] = None


class MultiLevelCache:
    """Advanced multi-level caching system for delta query optimization"""

    def __init__(self, cache_service: CacheService, database: Database):
        self.cache_service = cache_service
        self.database = database

        # L1 Cache - In-memory
        self._l1_cache: Dict[str, CacheEntry] = {}
        self._l1_max_size = int(os.getenv("DELTA_L1_CACHE_SIZE", "1000"))
        self._l1_ttl_seconds = int(os.getenv("DELTA_L1_TTL", "300"))  # 5 minutes

        # L2 Cache - Redis
        self._l2_ttl_seconds = int(os.getenv("DELTA_L2_TTL", "3600"))  # 1 hour

        # L3 Cache - Database
        self._l3_ttl_seconds = int(os.getenv("DELTA_L3_TTL", "86400"))  # 24 hours

        # Cache statistics
        self._stats = {
            "l1_hits": 0, "l1_misses": 0,
            "l2_hits": 0, "l2_misses": 0,
            "l3_hits": 0, "l3_misses": 0,
            "evictions": 0
        }

    async def get(self, key: str) -> Optional[Any]:
        """Get data from multi-level cache with intelligent promotion"""
        cache_key = self._normalize_key(key)

        # Try L1 cache first
        l1_entry = self._l1_cache.get(cache_key)
        if l1_entry and not self._is_expired(l1_entry):
            self._stats["l1_hits"] += 1
            l1_entry.access_count += 1
            l1_entry.last_accessed = datetime.now(timezone.utc)
            return l1_entry.data

        self._stats["l1_misses"] += 1

        # Try L2 cache (Redis)
        try:
            l2_data = await self.cache_service.get(f"delta_l2:{cache_key}")
            if l2_data:
                self._stats["l2_hits"] += 1

                # Promote to L1 if frequently accessed
                await self._promote_to_l1(cache_key, l2_data)
                return l2_data

        except Exception as e:
            logger.warning("L2 cache error", key=cache_key, error=str(e))

        self._stats["l2_misses"] += 1

        # Try L3 cache (Database)
        try:
            l3_data = await self._get_from_l3(cache_key)
            if l3_data:
                self._stats["l3_hits"] += 1

                # Promote to L2 and potentially L1
                await self._promote_to_l2(cache_key, l3_data)
                return l3_data

        except Exception as e:
            logger.warning("L3 cache error", key=cache_key, error=str(e))

        self._stats["l3_misses"] += 1
        return None

    async def set(
        self,
        key: str,
        data: Any,
        ttl_seconds: Optional[int] = None,
        cache_levels: Optional[List[CacheLevel]] = None
    ) -> None:
        """Set data in multi-level cache with intelligent distribution"""
        cache_key = self._normalize_key(key)
        current_time = datetime.now(timezone.utc)

        # Default to all cache levels
        if cache_levels is None:
            cache_levels = [CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS, CacheLevel.L3_DATABASE]

        # Calculate expiration times for each level
        l1_ttl = ttl_seconds or self._l1_ttl_seconds
        l2_ttl = ttl_seconds or self._l2_ttl_seconds
        l3_ttl = ttl_seconds or self._l3_ttl_seconds

        # Store in L1 cache
        if CacheLevel.L1_MEMORY in cache_levels:
            await self._ensure_l1_capacity()

            entry = CacheEntry(
                key=cache_key,
                data=data,
                created_at=current_time,
                expires_at=current_time + timedelta(seconds=l1_ttl),
                cache_level=CacheLevel.L1_MEMORY,
                size_bytes=self._estimate_size(data)
            )

            self._l1_cache[cache_key] = entry

        # Store in L2 cache (Redis)
        if CacheLevel.L2_REDIS in cache_levels:
            try:
                await self.cache_service.set(
                    f"delta_l2:{cache_key}",
                    data,
                    ttl=l2_ttl
                )
            except Exception as e:
                logger.warning("L2 cache set error", key=cache_key, error=str(e))

        # Store in L3 cache (Database)
        if CacheLevel.L3_DATABASE in cache_levels:
            try:
                await self._set_in_l3(cache_key, data, l3_ttl)
            except Exception as e:
                logger.warning("L3 cache set error", key=cache_key, error=str(e))

    async def invalidate(self, key: str) -> None:
        """Invalidate cache entry across all levels"""
        cache_key = self._normalize_key(key)

        # Remove from L1
        self._l1_cache.pop(cache_key, None)

        # Remove from L2
        try:
            await self.cache_service.delete(f"delta_l2:{cache_key}")
        except Exception as e:
            logger.warning("L2 cache invalidation error", key=cache_key, error=str(e))

        # Remove from L3
        try:
            await self._delete_from_l3(cache_key)
        except Exception as e:
            logger.warning("L3 cache invalidation error", key=cache_key, error=str(e))

    async def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching a pattern"""
        # Invalidate L1 cache
        keys_to_remove = [
            key for key in self._l1_cache.keys()
            if self._matches_pattern(key, pattern)
        ]

        for key in keys_to_remove:
            del self._l1_cache[key]

        # Invalidate L2 cache
        try:
            await self.cache_service.delete_pattern(f"delta_l2:{pattern}")
        except Exception as e:
            logger.warning("L2 pattern invalidation error", pattern=pattern, error=str(e))

        # Invalidate L3 cache
        try:
            await self._delete_pattern_from_l3(pattern)
        except Exception as e:
            logger.warning("L3 pattern invalidation error", pattern=pattern, error=str(e))

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        total_requests = sum([
            self._stats["l1_hits"], self._stats["l1_misses"],
            self._stats["l2_hits"], self._stats["l2_misses"],
            self._stats["l3_hits"], self._stats["l3_misses"]
        ])

        if total_requests == 0:
            return {"message": "No cache requests yet"}

        l1_hit_rate = self._stats["l1_hits"] / (self._stats["l1_hits"] + self._stats["l1_misses"]) * 100
        l2_hit_rate = self._stats["l2_hits"] / (self._stats["l2_hits"] + self._stats["l2_misses"]) * 100
        l3_hit_rate = self._stats["l3_hits"] / (self._stats["l3_hits"] + self._stats["l3_misses"]) * 100

        overall_hit_rate = (
            self._stats["l1_hits"] + self._stats["l2_hits"] + self._stats["l3_hits"]
        ) / total_requests * 100

        return {
            "total_requests": total_requests,
            "overall_hit_rate": round(overall_hit_rate, 2),
            "l1_hit_rate": round(l1_hit_rate, 2),
            "l2_hit_rate": round(l2_hit_rate, 2),
            "l3_hit_rate": round(l3_hit_rate, 2),
            "l1_cache_size": len(self._l1_cache),
            "evictions": self._stats["evictions"],
            "memory_usage_estimate": sum(
                entry.size_bytes or 0 for entry in self._l1_cache.values()
            )
        }

    def _normalize_key(self, key: str) -> str:
        """Normalize cache key"""
        return hashlib.md5(key.encode()).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry is expired"""
        if not entry.expires_at:
            return False
        return datetime.now(timezone.utc) > entry.expires_at

    def _estimate_size(self, data: Any) -> int:
        """Estimate memory size of data"""
        try:
            if isinstance(data, str):
                return len(data.encode('utf-8'))
            elif isinstance(data, (dict, list)):
                return len(json.dumps(data).encode('utf-8'))
            else:
                return len(str(data).encode('utf-8'))
        except Exception:
            return 1024  # Default estimate

    async def _ensure_l1_capacity(self) -> None:
        """Ensure L1 cache doesn't exceed capacity"""
        while len(self._l1_cache) >= self._l1_max_size:
            # LRU eviction
            oldest_key = min(
                self._l1_cache.keys(),
                key=lambda k: self._l1_cache[k].last_accessed or self._l1_cache[k].created_at
            )

            del self._l1_cache[oldest_key]
            self._stats["evictions"] += 1

    async def _promote_to_l1(self, key: str, data: Any) -> None:
        """Promote data from L2 to L1 cache"""
        await self.set(key, data, cache_levels=[CacheLevel.L1_MEMORY])

    async def _promote_to_l2(self, key: str, data: Any) -> None:
        """Promote data from L3 to L2 cache"""
        await self.set(key, data, cache_levels=[CacheLevel.L2_REDIS])

    async def _get_from_l3(self, key: str) -> Optional[Any]:
        """Get data from L3 database cache"""
        try:
            query = """
            SELECT data FROM delta_cache
            WHERE cache_key = $1
              AND (expires_at IS NULL OR expires_at > NOW())
            """

            async with self.database._connection_pool.acquire() as conn:
                row = await conn.fetchrow(query, key)

            if row:
                return json.loads(row["data"])

            return None

        except Exception as e:
            logger.error("L3 cache get error", key=key, error=str(e))
            return None

    async def _set_in_l3(self, key: str, data: Any, ttl_seconds: int) -> None:
        """Set data in L3 database cache"""
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

            query = """
            INSERT INTO delta_cache (cache_key, data, created_at, expires_at)
            VALUES ($1, $2, NOW(), $3)
            ON CONFLICT (cache_key) DO UPDATE SET
                data = EXCLUDED.data,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
            """

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(query, key, json.dumps(data), expires_at)

        except Exception as e:
            logger.error("L3 cache set error", key=key, error=str(e))

    async def _delete_from_l3(self, key: str) -> None:
        """Delete data from L3 database cache"""
        try:
            query = "DELETE FROM delta_cache WHERE cache_key = $1"

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(query, key)

        except Exception as e:
            logger.error("L3 cache delete error", key=key, error=str(e))

    async def _delete_pattern_from_l3(self, pattern: str) -> None:
        """Delete data matching pattern from L3 database cache"""
        try:
            # Convert pattern to SQL LIKE pattern
            sql_pattern = pattern.replace("*", "%")
            query = "DELETE FROM delta_cache WHERE cache_key LIKE $1"

            async with self.database._connection_pool.acquire() as conn:
                await conn.execute(query, sql_pattern)

        except Exception as e:
            logger.error("L3 cache pattern delete error", pattern=pattern, error=str(e))

    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches pattern (simple wildcard support)"""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)


class DeltaBatchProcessor:
    """Intelligent batching processor for delta queries"""

    def __init__(
        self,
        cache: MultiLevelCache,
        database: Database,
        graph_client: Any,
        status_tracker: SyncStatusTracker
    ):
        self.cache = cache
        self.database = database
        self.graph_client = graph_client
        self.status_tracker = status_tracker

        # Batching configuration
        self.max_batch_size = int(os.getenv("DELTA_MAX_BATCH_SIZE", "50"))
        self.batch_timeout_seconds = int(os.getenv("DELTA_BATCH_TIMEOUT", "5"))
        self.min_batch_efficiency = float(os.getenv("DELTA_MIN_BATCH_EFFICIENCY", "0.7"))

        # Batch queues
        self._batch_queues: Dict[str, List[BatchRequest]] = {}
        self._processing_batches: Set[str] = set()

        # Performance tracking
        self._batch_metrics: Dict[str, List[float]] = {
            "processing_times": [],
            "batch_sizes": [],
            "efficiency_scores": []
        }

    async def submit_delta_request(
        self,
        resource_type: str,
        user_id: str,
        tenant_id: Optional[str] = None,
        resource_ids: Optional[Set[str]] = None,
        priority: int = 5
    ) -> str:
        """Submit a delta query request for intelligent batching"""
        batch_request = BatchRequest(
            batch_id=str(uuid.uuid4()),
            resource_type=resource_type,
            user_ids={user_id},
            tenant_ids={tenant_id} if tenant_id else set(),
            resource_ids=resource_ids or set(),
            priority=priority
        )

        # Calculate estimated cost
        batch_request.estimated_cost = self._estimate_request_cost(batch_request)

        # Determine batch strategy
        strategy = self._select_batch_strategy(batch_request)
        batch_key = self._get_batch_key(batch_request, strategy)

        # Add to appropriate batch queue
        if batch_key not in self._batch_queues:
            self._batch_queues[batch_key] = []

        self._batch_queues[batch_key].append(batch_request)

        # Trigger batch processing if conditions met
        await self._check_batch_ready(batch_key)

        return batch_request.batch_id

    async def process_batches(self) -> None:
        """Process ready batches"""
        ready_batches = await self._get_ready_batches()

        for batch_key in ready_batches:
            if batch_key in self._processing_batches:
                continue

            self._processing_batches.add(batch_key)

            try:
                await self._process_batch(batch_key)
            finally:
                self._processing_batches.discard(batch_key)

    def _select_batch_strategy(self, request: BatchRequest) -> BatchStrategy:
        """Select optimal batching strategy for request"""
        # High priority requests use tenant-based batching
        if request.priority >= 8:
            return BatchStrategy.TENANT

        # Resource-specific requests use resource type batching
        if request.resource_ids:
            return BatchStrategy.RESOURCE_TYPE

        # Default to adaptive strategy
        return BatchStrategy.ADAPTIVE

    def _get_batch_key(self, request: BatchRequest, strategy: BatchStrategy) -> str:
        """Generate batch key based on strategy"""
        if strategy == BatchStrategy.TENANT:
            tenant = list(request.tenant_ids)[0] if request.tenant_ids else "default"
            return f"tenant:{tenant}:{request.resource_type}"

        elif strategy == BatchStrategy.RESOURCE_TYPE:
            return f"resource:{request.resource_type}"

        elif strategy == BatchStrategy.TIME_WINDOW:
            # Group by 5-minute windows
            window = int(time.time() // 300) * 300
            return f"time:{window}:{request.resource_type}"

        else:  # ADAPTIVE
            # Combine multiple factors
            tenant = list(request.tenant_ids)[0] if request.tenant_ids else "default"
            return f"adaptive:{tenant}:{request.resource_type}:{request.priority}"

    def _estimate_request_cost(self, request: BatchRequest) -> float:
        """Estimate the cost of processing a request"""
        base_cost = 1.0

        # Cost increases with number of resources
        if request.resource_ids:
            base_cost += len(request.resource_ids) * 0.1

        # Cost decreases with higher priority (more urgent)
        priority_factor = (11 - request.priority) / 10
        base_cost *= priority_factor

        # Cost increases with tenant isolation requirements
        if request.tenant_ids:
            base_cost += len(request.tenant_ids) * 0.2

        return base_cost

    async def _check_batch_ready(self, batch_key: str) -> None:
        """Check if batch is ready for processing"""
        if batch_key not in self._batch_queues:
            return

        batch = self._batch_queues[batch_key]

        # Ready conditions
        size_ready = len(batch) >= self.max_batch_size
        time_ready = self._is_batch_timeout(batch)
        efficiency_ready = self._calculate_batch_efficiency(batch) >= self.min_batch_efficiency

        if size_ready or time_ready or efficiency_ready:
            await self._process_batch(batch_key)

    def _is_batch_timeout(self, batch: List[BatchRequest]) -> bool:
        """Check if batch has timed out"""
        if not batch:
            return False

        oldest_request = min(batch, key=lambda r: r.created_at)
        age_seconds = (datetime.now(timezone.utc) - oldest_request.created_at).total_seconds()

        return age_seconds >= self.batch_timeout_seconds

    def _calculate_batch_efficiency(self, batch: List[BatchRequest]) -> float:
        """Calculate batch processing efficiency score"""
        if not batch:
            return 0.0

        # Efficiency factors
        size_efficiency = min(len(batch) / self.max_batch_size, 1.0)
        cost_efficiency = 1.0 / (sum(r.estimated_cost or 1.0 for r in batch) / len(batch))
        priority_efficiency = sum(r.priority for r in batch) / (len(batch) * 10)

        # Weighted average
        return (size_efficiency * 0.4 + cost_efficiency * 0.3 + priority_efficiency * 0.3)

    async def _get_ready_batches(self) -> List[str]:
        """Get list of batches ready for processing"""
        ready_batches = []

        for batch_key, batch in self._batch_queues.items():
            if batch_key in self._processing_batches:
                continue

            if (len(batch) >= self.max_batch_size or
                self._is_batch_timeout(batch) or
                self._calculate_batch_efficiency(batch) >= self.min_batch_efficiency):

                ready_batches.append(batch_key)

        return ready_batches

    async def _process_batch(self, batch_key: str) -> None:
        """Process a batch of delta requests"""
        if batch_key not in self._batch_queues:
            return

        batch = self._batch_queues[batch_key]
        if not batch:
            return

        start_time = time.time()

        try:
            # Start sync operation tracking
            operation_id = await self.status_tracker.start_sync_operation(
                SyncType.DELTA_SYNC,
                SyncDirection.INBOUND,
                "batch_processor",
                tenant_id=self._get_primary_tenant(batch),
                resource_type=batch[0].resource_type,
                config={
                    "batch_size": len(batch),
                    "batch_key": batch_key,
                    "strategy": self._extract_strategy_from_key(batch_key)
                }
            )

            await self.status_tracker.update_operation_status(operation_id, SyncStatus.RUNNING)

            # Merge batch requests efficiently
            merged_request = self._merge_batch_requests(batch)

            # Check cache first
            cache_key = self._generate_cache_key(merged_request)
            cached_result = await self.cache.get(cache_key)

            if cached_result:
                logger.info(
                    "Batch served from cache",
                    batch_key=batch_key,
                    batch_size=len(batch)
                )

                await self._distribute_cached_results(batch, cached_result, operation_id)
            else:
                # Execute batch query
                result = await self._execute_batch_query(merged_request, operation_id)

                # Cache the result
                if result:
                    await self.cache.set(
                        cache_key,
                        result,
                        ttl_seconds=300,  # 5 minutes
                        cache_levels=[CacheLevel.L1_MEMORY, CacheLevel.L2_REDIS]
                    )

                # Distribute results to individual requests
                await self._distribute_query_results(batch, result, operation_id)

            # Record batch metrics
            processing_time = time.time() - start_time
            efficiency_score = self._calculate_batch_efficiency(batch)

            self._batch_metrics["processing_times"].append(processing_time)
            self._batch_metrics["batch_sizes"].append(len(batch))
            self._batch_metrics["efficiency_scores"].append(efficiency_score)

            # Keep only recent metrics
            max_metrics = 100
            for metric_list in self._batch_metrics.values():
                if len(metric_list) > max_metrics:
                    metric_list[:] = metric_list[-max_metrics:]

            await self.status_tracker.complete_sync_operation(operation_id)

            logger.info(
                "Batch processed successfully",
                batch_key=batch_key,
                batch_size=len(batch),
                processing_time=processing_time,
                efficiency_score=efficiency_score
            )

        except Exception as e:
            logger.error(
                "Batch processing failed",
                batch_key=batch_key,
                batch_size=len(batch),
                error=str(e)
            )

            if 'operation_id' in locals():
                await self.status_tracker.update_operation_status(
                    operation_id,
                    SyncStatus.FAILED,
                    str(e)
                )

        finally:
            # Remove processed batch
            self._batch_queues.pop(batch_key, None)

    def _get_primary_tenant(self, batch: List[BatchRequest]) -> Optional[str]:
        """Get primary tenant ID from batch"""
        tenant_ids = set()
        for request in batch:
            tenant_ids.update(request.tenant_ids)

        if len(tenant_ids) == 1:
            return list(tenant_ids)[0]
        elif len(tenant_ids) > 1:
            return "multi_tenant"
        else:
            return None

    def _extract_strategy_from_key(self, batch_key: str) -> str:
        """Extract batching strategy from batch key"""
        return batch_key.split(":")[0]

    def _merge_batch_requests(self, batch: List[BatchRequest]) -> BatchRequest:
        """Merge multiple batch requests into a single optimized request"""
        if not batch:
            raise ValueError("Cannot merge empty batch")

        # Use the highest priority
        max_priority = max(request.priority for request in batch)

        # Merge all user IDs, tenant IDs, and resource IDs
        all_user_ids = set()
        all_tenant_ids = set()
        all_resource_ids = set()

        for request in batch:
            all_user_ids.update(request.user_ids)
            all_tenant_ids.update(request.tenant_ids)
            all_resource_ids.update(request.resource_ids)

        # Create merged request
        merged = BatchRequest(
            batch_id=f"merged_{uuid.uuid4()}",
            resource_type=batch[0].resource_type,  # Assume same resource type
            user_ids=all_user_ids,
            tenant_ids=all_tenant_ids,
            resource_ids=all_resource_ids,
            priority=max_priority
        )

        return merged

    def _generate_cache_key(self, request: BatchRequest) -> str:
        """Generate cache key for batch request"""
        key_parts = [
            request.resource_type,
            ":".join(sorted(request.user_ids)),
            ":".join(sorted(request.tenant_ids)),
            ":".join(sorted(request.resource_ids))
        ]

        key_string = "|".join(key_parts)
        return f"batch_delta:{hashlib.md5(key_string.encode()).hexdigest()}"

    async def _execute_batch_query(
        self,
        request: BatchRequest,
        operation_id: str
    ) -> Optional[DeltaResult]:
        """Execute optimized batch delta query"""
        try:
            # Build optimized Graph API query
            if request.resource_type == "plans":
                if request.resource_ids:
                    # Use $filter for specific plans
                    plan_ids = "','".join(request.resource_ids)
                    url = f"planner/plans/delta?$filter=id in ('{plan_ids}')"
                else:
                    url = "planner/plans/delta"

            elif request.resource_type == "tasks":
                if request.resource_ids:
                    # Use $filter for specific tasks
                    task_ids = "','".join(request.resource_ids)
                    url = f"planner/tasks/delta?$filter=id in ('{task_ids}')"
                else:
                    url = "planner/tasks/delta"

            else:
                raise ValueError(f"Unsupported resource type: {request.resource_type}")

            # Add batching parameters
            query_params = {
                "$top": str(min(self.max_batch_size * 2, 999)),  # Larger batch size
                "$select": self._get_optimized_select_fields(request.resource_type)
            }

            # Execute query with performance tracking
            start_time = time.time()

            response = await self.graph_client.get(url, params=query_params)

            query_time = time.time() - start_time

            # Update operation metrics
            await self.status_tracker.update_operation_metrics(
                operation_id,
                api_calls_made=1,
                processed_resources=len(response.get("value", [])),
                avg_processing_time_ms=query_time * 1000
            )

            # Parse response into DeltaResult
            return self._parse_batch_response(response)

        except Exception as e:
            logger.error("Batch query execution failed", error=str(e))
            await self.status_tracker.update_operation_metrics(
                operation_id,
                other_errors=1
            )
            raise

    def _get_optimized_select_fields(self, resource_type: str) -> str:
        """Get optimized field selection for resource type"""
        if resource_type == "plans":
            return "id,title,description,owner,createdDateTime,lastModifiedDateTime,@odata.etag"
        elif resource_type == "tasks":
            return "id,title,description,planId,bucketId,dueDateTime,percentComplete,assignments,createdDateTime,lastModifiedDateTime,@odata.etag"
        else:
            return "*"

    def _parse_batch_response(self, response: Dict[str, Any]) -> DeltaResult:
        """Parse batch response into DeltaResult"""
        changes = []

        for item in response.get("value", []):
            change = ResourceChange(
                change_type="updated",  # Default for batch
                resource_type=self._determine_resource_type(item),
                resource_id=item.get("id", ""),
                resource_data=item,
                change_time=datetime.now(timezone.utc),
                etag=item.get("@odata.etag")
            )
            changes.append(change)

        # Extract delta token
        next_delta_token = None
        delta_link = response.get("@odata.deltaLink")
        if delta_link and "$deltatoken=" in delta_link:
            next_delta_token = delta_link.split("$deltatoken=")[1].split("&")[0]

        return DeltaResult(
            delta_token="",
            next_delta_token=next_delta_token,
            changes=changes,
            has_more_changes="@odata.nextLink" in response
        )

    def _determine_resource_type(self, item: Dict[str, Any]) -> str:
        """Determine resource type from Graph API item"""
        if "planId" in item:
            return "task"
        elif "owner" in item:
            return "plan"
        else:
            return "unknown"

    async def _distribute_cached_results(
        self,
        batch: List[BatchRequest],
        cached_result: DeltaResult,
        operation_id: str
    ) -> None:
        """Distribute cached results to individual requests"""
        for request in batch:
            # Filter results relevant to this request
            relevant_changes = self._filter_changes_for_request(cached_result.changes, request)

            # Update status tracker
            await self.status_tracker.update_operation_metrics(
                operation_id,
                cache_hits=1,
                successful_resources=len(relevant_changes)
            )

            # Store individual result
            await self._store_request_result(request, relevant_changes)

    async def _distribute_query_results(
        self,
        batch: List[BatchRequest],
        result: DeltaResult,
        operation_id: str
    ) -> None:
        """Distribute query results to individual requests"""
        for request in batch:
            # Filter results relevant to this request
            relevant_changes = self._filter_changes_for_request(result.changes, request)

            # Update status tracker
            await self.status_tracker.update_operation_metrics(
                operation_id,
                successful_resources=len(relevant_changes)
            )

            # Store individual result
            await self._store_request_result(request, relevant_changes)

    def _filter_changes_for_request(
        self,
        changes: List[ResourceChange],
        request: BatchRequest
    ) -> List[ResourceChange]:
        """Filter changes relevant to a specific request"""
        relevant_changes = []

        for change in changes:
            # Check if change is relevant to this request
            if request.resource_ids and change.resource_id not in request.resource_ids:
                continue

            # Add tenant filtering logic here if needed

            relevant_changes.append(change)

        return relevant_changes

    async def _store_request_result(
        self,
        request: BatchRequest,
        changes: List[ResourceChange]
    ) -> None:
        """Store result for individual request"""
        try:
            # Store in cache for request retrieval
            result_key = f"request_result:{request.batch_id}"

            result_data = {
                "batch_id": request.batch_id,
                "changes": [
                    {
                        "change_type": change.change_type,
                        "resource_type": change.resource_type,
                        "resource_id": change.resource_id,
                        "resource_data": change.resource_data,
                        "change_time": change.change_time.isoformat(),
                        "etag": change.etag
                    }
                    for change in changes
                ],
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

            await self.cache.set(
                result_key,
                result_data,
                ttl_seconds=1800,  # 30 minutes
                cache_levels=[CacheLevel.L2_REDIS]
            )

        except Exception as e:
            logger.error("Failed to store request result", batch_id=request.batch_id, error=str(e))

    def get_batch_metrics(self) -> Dict[str, Any]:
        """Get batch processing performance metrics"""
        if not any(self._batch_metrics.values()):
            return {"message": "No batch metrics available yet"}

        processing_times = self._batch_metrics["processing_times"]
        batch_sizes = self._batch_metrics["batch_sizes"]
        efficiency_scores = self._batch_metrics["efficiency_scores"]

        return {
            "total_batches_processed": len(processing_times),
            "avg_processing_time": sum(processing_times) / len(processing_times),
            "max_processing_time": max(processing_times),
            "min_processing_time": min(processing_times),
            "avg_batch_size": sum(batch_sizes) / len(batch_sizes),
            "max_batch_size": max(batch_sizes),
            "avg_efficiency_score": sum(efficiency_scores) / len(efficiency_scores),
            "current_queue_sizes": {
                key: len(batch) for key, batch in self._batch_queues.items()
            },
            "active_batches": len(self._processing_batches)
        }


class DeltaOptimizer:
    """Main delta query optimization coordinator"""

    def __init__(
        self,
        database: Database,
        cache_service: CacheService,
        graph_client: Any,
        status_tracker: SyncStatusTracker
    ):
        self.database = database
        self.cache_service = cache_service
        self.graph_client = graph_client
        self.status_tracker = status_tracker

        # Initialize components
        self.cache = MultiLevelCache(cache_service, database)
        self.batch_processor = DeltaBatchProcessor(
            self.cache, database, graph_client, status_tracker
        )

        # Optimization metrics
        self.metrics = OptimizationMetrics()

        # Background tasks
        self._optimization_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize delta optimizer"""
        await self._ensure_cache_tables()

        # Start background optimization
        self._optimization_task = asyncio.create_task(self._optimization_loop())

        logger.info("Delta optimizer initialized")

    async def shutdown(self) -> None:
        """Shutdown delta optimizer"""
        if self._optimization_task:
            self._optimization_task.cancel()

        await asyncio.gather(self._optimization_task, return_exceptions=True)

        logger.info("Delta optimizer shutdown completed")

    @track_operation("optimized_delta_query")
    async def execute_optimized_delta_query(
        self,
        resource_type: str,
        user_id: str,
        tenant_id: Optional[str] = None,
        resource_ids: Optional[List[str]] = None,
        priority: int = 5
    ) -> Optional[DeltaResult]:
        """Execute optimized delta query with caching and batching"""
        try:
            # Convert resource_ids to set for batch processing
            resource_id_set = set(resource_ids) if resource_ids else set()

            # Submit to batch processor
            batch_id = await self.batch_processor.submit_delta_request(
                resource_type=resource_type,
                user_id=user_id,
                tenant_id=tenant_id,
                resource_ids=resource_id_set,
                priority=priority
            )

            # Process any ready batches
            await self.batch_processor.process_batches()

            # Wait for result with timeout
            max_wait_time = 30  # seconds
            wait_interval = 0.5  # seconds
            waited_time = 0

            while waited_time < max_wait_time:
                # Check if result is available
                result_key = f"request_result:{batch_id}"
                result_data = await self.cache.get(result_key)

                if result_data:
                    # Convert back to DeltaResult
                    changes = []
                    for change_data in result_data["changes"]:
                        change = ResourceChange(
                            change_type=change_data["change_type"],
                            resource_type=change_data["resource_type"],
                            resource_id=change_data["resource_id"],
                            resource_data=change_data["resource_data"],
                            change_time=datetime.fromisoformat(change_data["change_time"]),
                            etag=change_data.get("etag")
                        )
                        changes.append(change)

                    return DeltaResult(
                        delta_token="",
                        next_delta_token=None,
                        changes=changes,
                        has_more_changes=False
                    )

                await asyncio.sleep(wait_interval)
                waited_time += wait_interval

            logger.warning("Delta query result timeout", batch_id=batch_id)
            return None

        except Exception as e:
            logger.error("Optimized delta query failed", error=str(e))
            raise

    async def get_optimization_metrics(self) -> Dict[str, Any]:
        """Get comprehensive optimization metrics"""
        cache_stats = self.cache.get_cache_stats()
        batch_metrics = self.batch_processor.get_batch_metrics()

        return {
            "cache_performance": cache_stats,
            "batch_performance": batch_metrics,
            "optimization_score": self.metrics.optimization_score,
            "last_optimization": self.metrics.last_optimization_time.isoformat() if self.metrics.last_optimization_time else None
        }

    async def _optimization_loop(self) -> None:
        """Background optimization loop"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes

                # Process ready batches
                await self.batch_processor.process_batches()

                # Update optimization metrics
                await self._update_optimization_metrics()

                # Perform adaptive optimizations
                await self._perform_adaptive_optimizations()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in optimization loop", error=str(e))

    async def _update_optimization_metrics(self) -> None:
        """Update optimization performance metrics"""
        try:
            cache_stats = self.cache.get_cache_stats()
            batch_metrics = self.batch_processor.get_batch_metrics()

            # Update cache metrics
            if cache_stats.get("total_requests", 0) > 0:
                self.metrics.cache_hit_rate_l1 = cache_stats.get("l1_hit_rate", 0)
                self.metrics.cache_hit_rate_l2 = cache_stats.get("l2_hit_rate", 0)
                self.metrics.cache_hit_rate_l3 = cache_stats.get("l3_hit_rate", 0)

            # Update batch metrics
            if batch_metrics.get("total_batches_processed", 0) > 0:
                self.metrics.avg_batch_size = batch_metrics.get("avg_batch_size", 0)
                self.metrics.avg_batch_processing_time = batch_metrics.get("avg_processing_time", 0)
                self.metrics.batch_efficiency_score = batch_metrics.get("avg_efficiency_score", 0)

            # Calculate overall optimization score
            self.metrics.optimization_score = self._calculate_optimization_score()
            self.metrics.last_optimization_time = datetime.now(timezone.utc)

        except Exception as e:
            logger.error("Error updating optimization metrics", error=str(e))

    def _calculate_optimization_score(self) -> float:
        """Calculate overall optimization performance score (0-100)"""
        # Weight different factors
        cache_score = (
            self.metrics.cache_hit_rate_l1 * 0.5 +
            self.metrics.cache_hit_rate_l2 * 0.3 +
            self.metrics.cache_hit_rate_l3 * 0.2
        )

        batch_score = self.metrics.batch_efficiency_score * 100

        # Combine scores with weights
        overall_score = (cache_score * 0.6 + batch_score * 0.4)

        return min(overall_score, 100.0)

    async def _perform_adaptive_optimizations(self) -> None:
        """Perform adaptive optimizations based on metrics"""
        try:
            # Optimize cache eviction if hit rate is low
            if self.metrics.cache_hit_rate_l1 < 50:
                await self._optimize_cache_strategy()

            # Adjust batch parameters if efficiency is low
            if self.metrics.batch_efficiency_score < 0.6:
                await self._optimize_batch_strategy()

            # Clean up expired cache entries
            await self._cleanup_expired_cache()

        except Exception as e:
            logger.error("Error in adaptive optimizations", error=str(e))

    async def _optimize_cache_strategy(self) -> None:
        """Optimize caching strategy based on performance"""
        # Implement cache optimization logic
        logger.info("Optimizing cache strategy", hit_rate=self.metrics.cache_hit_rate_l1)

    async def _optimize_batch_strategy(self) -> None:
        """Optimize batching strategy based on performance"""
        # Implement batch optimization logic
        logger.info("Optimizing batch strategy", efficiency=self.metrics.batch_efficiency_score)

    async def _cleanup_expired_cache(self) -> None:
        """Clean up expired cache entries"""
        try:
            query = "DELETE FROM delta_cache WHERE expires_at < NOW()"

            async with self.database._connection_pool.acquire() as conn:
                result = await conn.execute(query)

            logger.debug("Cleaned up expired cache entries", result=result)

        except Exception as e:
            logger.error("Error cleaning up cache", error=str(e))

    async def _ensure_cache_tables(self) -> None:
        """Ensure cache tables exist"""
        try:
            async with self.database._connection_pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS delta_cache (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        cache_key VARCHAR(255) UNIQUE NOT NULL,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        expires_at TIMESTAMP WITH TIME ZONE,
                        access_count INTEGER DEFAULT 0,
                        last_accessed TIMESTAMP WITH TIME ZONE
                    )
                """)

                # Create index for efficient lookups
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_delta_cache_key_expires
                    ON delta_cache(cache_key, expires_at)
                """)

        except Exception as e:
            logger.error("Failed to create cache tables", error=str(e))
            raise


# Import required modules at the end to avoid circular imports
import os
import uuid
from typing import Any
from ..models.graph_models import SyncStatus