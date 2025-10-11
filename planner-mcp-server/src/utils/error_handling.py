"""
Graceful error handling utilities
"""

import asyncio
import traceback
from typing import Any, Callable, Dict, Optional, Type, Union, TypeVar
from functools import wraps
from contextlib import contextmanager, asynccontextmanager
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')

class ErrorContext:
    """Context for error handling with additional metadata"""

    def __init__(self, operation: str, **metadata):
        self.operation = operation
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            **self.metadata
        }

class GracefulError(Exception):
    """Base exception for graceful error handling"""

    def __init__(self, message: str, context: Optional[ErrorContext] = None, recoverable: bool = True):
        super().__init__(message)
        self.context = context
        self.recoverable = recoverable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self),
            "type": self.__class__.__name__,
            "recoverable": self.recoverable,
            "context": self.context.to_dict() if self.context else None
        }

def safe_execute(
    func: Callable[..., T],
    *args,
    default_value: Any = None,
    log_errors: bool = True,
    context: Optional[ErrorContext] = None,
    **kwargs
) -> Union[T, Any]:
    """Safely execute a function with error handling"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            error_info = {
                "function": func.__name__,
                "error": str(e),
                "error_type": type(e).__name__
            }
            if context:
                error_info.update(context.to_dict())

            logger.error("Function execution failed", **error_info)

        return default_value

async def safe_execute_async(
    func: Callable[..., Any],
    *args,
    default_value: Any = None,
    log_errors: bool = True,
    context: Optional[ErrorContext] = None,
    **kwargs
) -> Any:
    """Safely execute an async function with error handling"""
    try:
        return await func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            error_info = {
                "function": func.__name__,
                "error": str(e),
                "error_type": type(e).__name__
            }
            if context:
                error_info.update(context.to_dict())

            logger.error("Async function execution failed", **error_info)

        return default_value

def graceful_exception_handler(
    default_value: Any = None,
    log_errors: bool = True,
    reraise: bool = False,
    context: Optional[ErrorContext] = None
):
    """Decorator for graceful exception handling"""

    def decorator(func: Callable[..., T]) -> Callable[..., Union[T, Any]]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Union[T, Any]:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if log_errors:
                        error_info = {
                            "function": func.__name__,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "traceback": traceback.format_exc()
                        }
                        if context:
                            error_info.update(context.to_dict())

                        logger.error("Decorated async function failed", **error_info)

                    if reraise:
                        raise
                    return default_value

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Union[T, Any]:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if log_errors:
                        error_info = {
                            "function": func.__name__,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "traceback": traceback.format_exc()
                        }
                        if context:
                            error_info.update(context.to_dict())

                        logger.error("Decorated function failed", **error_info)

                    if reraise:
                        raise
                    return default_value

            return sync_wrapper

    return decorator

@contextmanager
def error_boundary(
    operation: str,
    default_value: Any = None,
    log_errors: bool = True,
    reraise: bool = False,
    **metadata
):
    """Context manager for error boundaries"""
    context = ErrorContext(operation, **metadata)

    try:
        yield context
    except Exception as e:
        if log_errors:
            error_info = {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
            error_info.update(context.to_dict())

            logger.error("Error boundary triggered", **error_info)

        if reraise:
            raise
        return default_value

@asynccontextmanager
async def async_error_boundary(
    operation: str,
    default_value: Any = None,
    log_errors: bool = True,
    reraise: bool = False,
    **metadata
):
    """Async context manager for error boundaries"""
    context = ErrorContext(operation, **metadata)

    try:
        yield context
    except Exception as e:
        if log_errors:
            error_info = {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
            error_info.update(context.to_dict())

            logger.error("Async error boundary triggered", **error_info)

        if reraise:
            raise

def validate_and_handle(
    value: Any,
    validation_func: Callable[[Any], bool],
    error_message: str = "Validation failed",
    default_value: Any = None,
    context: Optional[ErrorContext] = None
) -> Any:
    """Validate a value and handle validation errors gracefully"""
    try:
        if validation_func(value):
            return value
        else:
            error_info = {
                "validation_error": error_message,
                "value": str(value)[:100]  # Limit value logging
            }
            if context:
                error_info.update(context.to_dict())

            logger.warning("Validation failed", **error_info)
            return default_value

    except Exception as e:
        error_info = {
            "validation_error": "Validation function failed",
            "error": str(e),
            "error_type": type(e).__name__
        }
        if context:
            error_info.update(context.to_dict())

        logger.error("Validation function error", **error_info)
        return default_value

def create_error_handler(
    exception_types: Union[Type[Exception], tuple] = Exception,
    default_value: Any = None,
    log_level: str = "error"
) -> Callable:
    """Create a custom error handler for specific exception types"""

    def handler(func: Callable[..., T]) -> Callable[..., Union[T, Any]]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Union[T, Any]:
                try:
                    return await func(*args, **kwargs)
                except exception_types as e:
                    log_method = getattr(logger, log_level, logger.error)
                    log_method("Custom error handler triggered",
                             function=func.__name__,
                             error=str(e),
                             error_type=type(e).__name__)
                    return default_value

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Union[T, Any]:
                try:
                    return func(*args, **kwargs)
                except exception_types as e:
                    log_method = getattr(logger, log_level, logger.error)
                    log_method("Custom error handler triggered",
                             function=func.__name__,
                             error=str(e),
                             error_type=type(e).__name__)
                    return default_value

            return sync_wrapper

    return handler

def log_and_suppress(*exception_types: Type[Exception]):
    """Decorator to log and suppress specific exception types"""
    if not exception_types:
        exception_types = (Exception,)

    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Optional[T]:
                try:
                    return await func(*args, **kwargs)
                except exception_types as e:
                    logger.warning("Exception suppressed",
                                 function=func.__name__,
                                 error=str(e),
                                 error_type=type(e).__name__)
                    return None

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Optional[T]:
                try:
                    return func(*args, **kwargs)
                except exception_types as e:
                    logger.warning("Exception suppressed",
                                 function=func.__name__,
                                 error=str(e),
                                 error_type=type(e).__name__)
                    return None

            return sync_wrapper

    return decorator

# Common error handling patterns
handle_connection_errors = create_error_handler(
    (ConnectionError, TimeoutError),
    default_value=None,
    log_level="warning"
)

handle_validation_errors = create_error_handler(
    (ValueError, TypeError),
    default_value=None,
    log_level="info"
)

# Utility functions for common error patterns
def is_recoverable_error(error: Exception) -> bool:
    """Check if an error is recoverable"""
    recoverable_types = (
        ConnectionError,
        TimeoutError,
        OSError
    )
    return isinstance(error, recoverable_types)

def format_error_response(error: Exception, context: Optional[ErrorContext] = None) -> Dict[str, Any]:
    """Format an error for API responses"""
    return {
        "error": {
            "message": str(error),
            "type": type(error).__name__,
            "recoverable": is_recoverable_error(error),
            "context": context.to_dict() if context else None
        }
    }