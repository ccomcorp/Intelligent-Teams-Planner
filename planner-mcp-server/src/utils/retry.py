"""
Simple retry utilities with exponential backoff
"""

import asyncio
import random
import time
from typing import Any, Callable, Optional, TypeVar, Union
from functools import wraps
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')

class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        exceptions: tuple = (Exception,)
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.exceptions = exceptions

def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for retry attempt with exponential backoff"""
    delay = config.base_delay * (config.backoff_factor ** (attempt - 1))
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add random jitter (±25%)
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)

def retry_sync(config: Optional[RetryConfig] = None):
    """Decorator for synchronous functions with retry logic"""
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info("Function succeeded after retry",
                                  function=func.__name__,
                                  attempt=attempt)
                    return result

                except config.exceptions as e:
                    last_exception = e
                    if attempt == config.max_attempts:
                        logger.error("Function failed after all retries",
                                   function=func.__name__,
                                   attempts=config.max_attempts,
                                   error=str(e))
                        break

                    delay = calculate_delay(attempt, config)
                    logger.warning("Function failed, retrying",
                                 function=func.__name__,
                                 attempt=attempt,
                                 delay=delay,
                                 error=str(e))
                    time.sleep(delay)

                except Exception as e:
                    # Non-retryable exception
                    logger.error("Function failed with non-retryable error",
                               function=func.__name__,
                               error=str(e))
                    raise

            # Re-raise the last exception if all retries failed
            if last_exception:
                raise last_exception

        return wrapper
    return decorator

def retry_async(config: Optional[RetryConfig] = None):
    """Decorator for asynchronous functions with retry logic"""
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 1:
                        logger.info("Async function succeeded after retry",
                                  function=func.__name__,
                                  attempt=attempt)
                    return result

                except config.exceptions as e:
                    last_exception = e
                    if attempt == config.max_attempts:
                        logger.error("Async function failed after all retries",
                                   function=func.__name__,
                                   attempts=config.max_attempts,
                                   error=str(e))
                        break

                    delay = calculate_delay(attempt, config)
                    logger.warning("Async function failed, retrying",
                                 function=func.__name__,
                                 attempt=attempt,
                                 delay=delay,
                                 error=str(e))
                    await asyncio.sleep(delay)

                except Exception as e:
                    # Non-retryable exception
                    logger.error("Async function failed with non-retryable error",
                               function=func.__name__,
                               error=str(e))
                    raise

            # Re-raise the last exception if all retries failed
            if last_exception:
                raise last_exception

        return wrapper
    return decorator

async def retry_call_async(
    func: Callable[..., Any],
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs
) -> Any:
    """Call an async function with retry logic"""
    if config is None:
        config = RetryConfig()

    decorated_func = retry_async(config)(func)
    return await decorated_func(*args, **kwargs)

def retry_call_sync(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs
) -> T:
    """Call a sync function with retry logic"""
    if config is None:
        config = RetryConfig()

    decorated_func = retry_sync(config)(func)
    return decorated_func(*args, **kwargs)

# Common retry configurations
NETWORK_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    backoff_factor=2.0,
    exceptions=(ConnectionError, TimeoutError)
)

DATABASE_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=10.0,
    backoff_factor=2.0,
    exceptions=(Exception,)  # Database-specific exceptions would go here
)

API_RETRY = RetryConfig(
    max_attempts=5,
    base_delay=1.0,
    max_delay=60.0,
    backoff_factor=1.5,
    exceptions=(ConnectionError, TimeoutError)
)