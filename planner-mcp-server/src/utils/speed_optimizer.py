"""
Ultra-Aggressive Speed Optimization for 90%+ execution time improvement
Focus on CPU-bound operations and memory access patterns
"""

import asyncio
import time
import concurrent.futures
from typing import Any, Dict, List, Callable, Union
import functools
import threading
import structlog

logger = structlog.get_logger(__name__)

# Thread pool for CPU-intensive operations
_thread_pool = None
_max_workers = None

def initialize_speed_optimizer(max_workers: int = None):
    """Initialize the speed optimizer with optimized thread pool"""
    global _thread_pool, _max_workers

    if max_workers is None:
        import os
        max_workers = min(32, (os.cpu_count() or 1) * 4)  # 4x CPU cores

    _max_workers = max_workers
    _thread_pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="SpeedOpt"
    )

    logger.info("Speed optimizer initialized", max_workers=max_workers)

def get_thread_pool():
    """Get the optimized thread pool"""
    if _thread_pool is None:
        initialize_speed_optimizer()
    return _thread_pool

class UltraFastProcessor:
    """Ultra-high-speed processor with aggressive optimizations"""

    def __init__(self):
        self.cache = {}
        self.stats = {
            "sync_operations": 0,
            "async_operations": 0,
            "parallel_operations": 0,
            "cache_hits": 0,
            "total_time_saved": 0.0
        }

    @functools.lru_cache(maxsize=10000)  # Aggressive function-level caching
    def fast_hash_key(self, data: str) -> str:
        """Ultra-fast hash key generation"""
        return str(hash(data))

    async def parallel_process_list(self, items: List[Any], processor: Callable, chunk_size: int = 100) -> List[Any]:
        """Process list items in parallel with optimal chunking"""
        start_time = time.perf_counter()

        if len(items) <= chunk_size:
            # Small lists - process directly
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(get_thread_pool(), processor, item) for item in items]
            results = await asyncio.gather(*tasks)
        else:
            # Large lists - chunk and process
            chunks = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]

            async def process_chunk(chunk):
                loop = asyncio.get_event_loop()
                tasks = [loop.run_in_executor(get_thread_pool(), processor, item) for item in chunk]
                return await asyncio.gather(*tasks)

            chunk_results = await asyncio.gather(*[process_chunk(chunk) for chunk in chunks])
            results = [item for chunk in chunk_results for item in chunk]

        processing_time = time.perf_counter() - start_time
        self.stats["parallel_operations"] += 1
        self.stats["total_time_saved"] += max(0, len(items) * 0.001 - processing_time)  # Estimate time saved

        logger.debug("Parallel processing completed",
                    items_count=len(items),
                    processing_time_ms=round(processing_time * 1000, 2),
                    items_per_second=round(len(items) / processing_time, 2))

        return results

    async def batch_process_async(self, operations: List[Callable], max_concurrent: int = 50) -> List[Any]:
        """Process async operations in optimized batches"""
        start_time = time.perf_counter()

        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_operation(op):
            async with semaphore:
                return await op()

        results = await asyncio.gather(*[bounded_operation(op) for op in operations])

        processing_time = time.perf_counter() - start_time
        self.stats["async_operations"] += 1

        logger.debug("Batch async processing completed",
                    operations_count=len(operations),
                    processing_time_ms=round(processing_time * 1000, 2),
                    ops_per_second=round(len(operations) / processing_time, 2))

        return results

    def ultra_fast_dict_merge(self, *dicts: Dict[str, Any]) -> Dict[str, Any]:
        """Ultra-fast dictionary merging optimized for performance"""
        if not dicts:
            return {}

        if len(dicts) == 1:
            return dict(dicts[0])  # Copy to avoid mutation

        # Use dict comprehension for speed
        result = {}
        for d in dicts:
            result.update(d)

        return result

    def ultra_fast_list_dedupe(self, items: List[Any]) -> List[Any]:
        """Ultra-fast list deduplication preserving order"""
        seen = set()
        result = []

        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)

        return result

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get detailed performance statistics"""
        return {
            "operations": self.stats.copy(),
            "cache_size": len(self.cache),
            "lru_cache_info": self.fast_hash_key.cache_info()._asdict()
        }

# Global instance
_speed_processor = UltraFastProcessor()

# Decorator for automatic speed optimization
def ultra_fast(cache: bool = True, async_safe: bool = True):
    """Decorator to automatically optimize function execution speed"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            # Generate cache key if caching enabled
            if cache:
                cache_key = _speed_processor.fast_hash_key(str((func.__name__, args, tuple(sorted(kwargs.items())))))

                if cache_key in _speed_processor.cache:
                    _speed_processor.stats["cache_hits"] += 1
                    return _speed_processor.cache[cache_key]

            # Execute function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                if async_safe:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(get_thread_pool(), func, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)

            # Cache result if enabled
            if cache:
                _speed_processor.cache[cache_key] = result

            execution_time = time.perf_counter() - start_time
            if execution_time > 0.01:  # Log slow operations
                logger.debug("Function execution time",
                           function=func.__name__,
                           execution_time_ms=round(execution_time * 1000, 2))

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            # Generate cache key if caching enabled
            if cache:
                cache_key = _speed_processor.fast_hash_key(str((func.__name__, args, tuple(sorted(kwargs.items())))))

                if cache_key in _speed_processor.cache:
                    _speed_processor.stats["cache_hits"] += 1
                    return _speed_processor.cache[cache_key]

            # Execute function
            result = func(*args, **kwargs)

            # Cache result if enabled
            if cache:
                _speed_processor.cache[cache_key] = result

            execution_time = time.perf_counter() - start_time
            _speed_processor.stats["sync_operations"] += 1

            return result

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

# Utility functions for common speed optimizations
async def parallel_map(func: Callable, items: List[Any], chunk_size: int = 100) -> List[Any]:
    """Ultra-fast parallel mapping with optimal chunking"""
    return await _speed_processor.parallel_process_list(items, func, chunk_size)

async def batch_async_ops(operations: List[Callable], max_concurrent: int = 50) -> List[Any]:
    """Ultra-fast batch processing of async operations"""
    return await _speed_processor.batch_process_async(operations, max_concurrent)

def fast_dict_merge(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Ultra-fast dictionary merging"""
    return _speed_processor.ultra_fast_dict_merge(*dicts)

def fast_dedupe(items: List[Any]) -> List[Any]:
    """Ultra-fast list deduplication"""
    return _speed_processor.ultra_fast_list_dedupe(items)

def get_speed_stats() -> Dict[str, Any]:
    """Get global speed optimization statistics"""
    return _speed_processor.get_performance_stats()

# Initialize on import
initialize_speed_optimizer()