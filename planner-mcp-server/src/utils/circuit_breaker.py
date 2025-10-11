"""
Simple circuit breaker pattern for preventing cascading failures
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, TypeVar
from functools import wraps
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, calls fail fast
    HALF_OPEN = "half_open"  # Testing if service is back

class CircuitBreakerConfig:
    """Configuration for circuit breaker"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: tuple = (Exception,),
        name: str = "default"
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name

class CircuitBreaker:
    """Simple circuit breaker implementation"""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Call function with circuit breaker protection"""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time < self.config.recovery_timeout:
                    logger.warning("Circuit breaker is OPEN",
                                 name=self.config.name,
                                 failure_count=self.failure_count)
                    raise CircuitBreakerError(f"Circuit breaker {self.config.name} is OPEN")
                else:
                    # Move to half-open state
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker moving to HALF_OPEN",
                              name=self.config.name)

        try:
            # Execute the function
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

            # Success - reset failure count and close circuit
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    logger.info("Circuit breaker moving to CLOSED after success",
                              name=self.config.name)
                self.failure_count = 0
                self.state = CircuitState.CLOSED

            return result

        except self.config.expected_exception as e:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.error("Circuit breaker opened due to failures",
                               name=self.config.name,
                               failure_count=self.failure_count,
                               threshold=self.config.failure_threshold)
                else:
                    logger.warning("Circuit breaker failure recorded",
                                 name=self.config.name,
                                 failure_count=self.failure_count,
                                 threshold=self.config.failure_threshold)

            raise

    def get_state(self) -> dict:
        """Get current circuit breaker state"""
        return {
            "name": self.config.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.config.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.config.recovery_timeout
        }

    def reset(self):
        """Reset circuit breaker to initial state"""
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED
        logger.info("Circuit breaker reset", name=self.config.name)

class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass

class CircuitBreakerManager:
    """Manages multiple circuit breakers"""

    def __init__(self):
        self._breakers = {}

    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker"""
        if name not in self._breakers:
            if config is None:
                config = CircuitBreakerConfig(name=name)
            self._breakers[name] = CircuitBreaker(config)
        return self._breakers[name]

    def get_all_states(self) -> dict:
        """Get states of all circuit breakers"""
        return {name: breaker.get_state() for name, breaker in self._breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()

# Global circuit breaker manager
_circuit_manager = CircuitBreakerManager()

def circuit_breaker(config: Optional[CircuitBreakerConfig] = None):
    """Decorator for functions with circuit breaker protection"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        breaker_name = config.name if config else func.__name__
        breaker = _circuit_manager.get_breaker(breaker_name, config)

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                return await breaker.call(func, *args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                return asyncio.run(breaker.call(func, *args, **kwargs))
            return sync_wrapper

    return decorator

def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get a circuit breaker instance"""
    return _circuit_manager.get_breaker(name, config)

def get_all_circuit_states() -> dict:
    """Get states of all circuit breakers"""
    return _circuit_manager.get_all_states()

def reset_all_circuits():
    """Reset all circuit breakers"""
    _circuit_manager.reset_all()

# Common circuit breaker configurations
DATABASE_CIRCUIT = CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout=30.0,
    name="database"
)

API_CIRCUIT = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=60.0,
    name="api"
)

EXTERNAL_SERVICE_CIRCUIT = CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout=45.0,
    name="external_service"
)