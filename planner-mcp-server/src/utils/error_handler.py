"""
Enhanced error handling and classification for Graph API operations
Story 2.1 Task 7: Comprehensive Error Classification
"""

import re
import uuid
import asyncio
from typing import Dict, List, Any, Optional, Callable, Union, Type
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..models.graph_models import ErrorContext


logger = structlog.get_logger(__name__)


class ErrorCategory(str, Enum):
    """Error categories for classification"""
    TRANSIENT = "transient"          # Retry with backoff
    AUTHENTICATION = "authentication" # Token refresh/re-auth
    AUTHORIZATION = "authorization"   # Permission denied
    CLIENT_ERROR = "client_error"     # Request validation
    NOT_FOUND = "not_found"          # Resource not found
    RATE_LIMIT = "rate_limit"        # Rate limiting
    SERVER_ERROR = "server_error"     # Server issues
    NETWORK_ERROR = "network_error"   # Network/connectivity
    TIMEOUT = "timeout"              # Request timeout
    PERMANENT = "permanent"          # Non-recoverable
    UNKNOWN = "unknown"              # Unclassified


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"         # Informational, no action needed
    MEDIUM = "medium"   # Recoverable, retry may help
    HIGH = "high"       # Requires attention, may cause degradation
    CRITICAL = "critical" # System impacting, immediate action required


class RecoveryStrategy(str, Enum):
    """Recovery strategies for different error types"""
    RETRY = "retry"                    # Retry with backoff
    REFRESH_TOKEN = "refresh_token"    # Refresh authentication token
    FALLBACK = "fallback"             # Use fallback mechanism
    DEGRADE = "degrade"               # Graceful degradation
    ALERT = "alert"                   # Alert and manual intervention
    FAIL_FAST = "fail_fast"           # Fail immediately
    IGNORE = "ignore"                 # Log and continue


@dataclass
class ErrorPattern:
    """Error pattern definition for classification"""
    pattern: str                      # Regex pattern or string match
    category: ErrorCategory
    severity: ErrorSeverity
    recovery_strategy: RecoveryStrategy
    description: str
    retry_count: int = 0
    backoff_multiplier: float = 2.0
    max_backoff: float = 300.0
    circuit_breaker_threshold: int = 5
    tags: List[str] = field(default_factory=list)


@dataclass
class ErrorMetrics:
    """Error metrics and statistics"""
    error_code: str
    total_count: int = 0
    recent_count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    success_rate: float = 100.0
    recovery_rate: float = 0.0
    avg_recovery_time: float = 0.0


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for error handling"""
    operation: str
    state: str = "closed"  # closed, open, half_open
    failure_count: int = 0
    success_count: int = 0
    last_failure: Optional[datetime] = None
    next_attempt: Optional[datetime] = None
    threshold: int = 5
    timeout: int = 60  # seconds


class EnhancedErrorHandler:
    """
    Comprehensive error handling and classification system
    Provides intelligent error classification, recovery strategies, and circuit breaker patterns
    """

    def __init__(self):
        self.error_patterns = self._initialize_error_patterns()
        self.error_metrics: Dict[str, ErrorMetrics] = {}
        self.circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self.correlation_tracking: Dict[str, List[str]] = {}

        logger.info("Enhanced error handler initialized",
                   patterns=len(self.error_patterns))

    def _initialize_error_patterns(self) -> List[ErrorPattern]:
        """Initialize error classification patterns"""
        return [
            # Authentication errors
            ErrorPattern(
                pattern=r"401|unauthorized|invalid.*token|token.*expired",
                category=ErrorCategory.AUTHENTICATION,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.REFRESH_TOKEN,
                description="Authentication failure - token expired or invalid",
                retry_count=1,
                tags=["auth", "token"]
            ),

            # Authorization errors
            ErrorPattern(
                pattern=r"403|forbidden|insufficient.*privileges|access.*denied",
                category=ErrorCategory.AUTHORIZATION,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.ALERT,
                description="Authorization failure - insufficient permissions",
                retry_count=0,
                tags=["auth", "permissions"]
            ),

            # Rate limiting
            ErrorPattern(
                pattern=r"429|too.*many.*requests|rate.*limit|quota.*exceeded",
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=RecoveryStrategy.RETRY,
                description="Rate limit exceeded - backoff required",
                retry_count=3,
                backoff_multiplier=2.0,
                tags=["throttling", "rate_limit"]
            ),

            # Not found errors
            ErrorPattern(
                pattern=r"404|not.*found|resource.*not.*found|item.*not.*found",
                category=ErrorCategory.NOT_FOUND,
                severity=ErrorSeverity.LOW,
                recovery_strategy=RecoveryStrategy.FAIL_FAST,
                description="Resource not found",
                retry_count=0,
                tags=["not_found"]
            ),

            # Validation errors
            ErrorPattern(
                pattern=r"400|bad.*request|invalid.*request|validation.*failed|malformed",
                category=ErrorCategory.CLIENT_ERROR,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=RecoveryStrategy.FAIL_FAST,
                description="Client request validation error",
                retry_count=0,
                tags=["validation", "client_error"]
            ),

            # Conflict errors
            ErrorPattern(
                pattern=r"409|conflict|resource.*exists|duplicate",
                category=ErrorCategory.CLIENT_ERROR,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=RecoveryStrategy.FALLBACK,
                description="Resource conflict",
                retry_count=1,
                tags=["conflict"]
            ),

            # Server errors (transient)
            ErrorPattern(
                pattern=r"502|bad.*gateway|503|service.*unavailable|504|gateway.*timeout",
                category=ErrorCategory.TRANSIENT,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.RETRY,
                description="Transient server error",
                retry_count=3,
                backoff_multiplier=2.0,
                circuit_breaker_threshold=5,
                tags=["server_error", "transient"]
            ),

            # Internal server errors
            ErrorPattern(
                pattern=r"500|internal.*server.*error|server.*error",
                category=ErrorCategory.SERVER_ERROR,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.RETRY,
                description="Internal server error",
                retry_count=2,
                backoff_multiplier=1.5,
                circuit_breaker_threshold=3,
                tags=["server_error"]
            ),

            # Network errors
            ErrorPattern(
                pattern=r"connection.*refused|connection.*timeout|dns.*resolution|network.*unreachable",
                category=ErrorCategory.NETWORK_ERROR,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.RETRY,
                description="Network connectivity error",
                retry_count=3,
                backoff_multiplier=2.0,
                circuit_breaker_threshold=5,
                tags=["network"]
            ),

            # Timeout errors
            ErrorPattern(
                pattern=r"timeout|request.*timeout|read.*timeout|connection.*timeout",
                category=ErrorCategory.TIMEOUT,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=RecoveryStrategy.RETRY,
                description="Request timeout",
                retry_count=2,
                backoff_multiplier=1.5,
                tags=["timeout"]
            ),

            # SSL/TLS errors
            ErrorPattern(
                pattern=r"ssl.*error|tls.*error|certificate.*error|handshake.*failed",
                category=ErrorCategory.NETWORK_ERROR,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.ALERT,
                description="SSL/TLS connection error",
                retry_count=1,
                tags=["ssl", "security"]
            ),

            # Graph API specific errors
            ErrorPattern(
                pattern=r"InvalidAuthenticationToken|CompactToken.*parsing.*failed",
                category=ErrorCategory.AUTHENTICATION,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.REFRESH_TOKEN,
                description="Graph API authentication token error",
                retry_count=1,
                tags=["graph_api", "token"]
            ),

            ErrorPattern(
                pattern=r"TooManyRequests|Request_ThrottledTemporarily",
                category=ErrorCategory.RATE_LIMIT,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=RecoveryStrategy.RETRY,
                description="Graph API rate limiting",
                retry_count=3,
                backoff_multiplier=2.0,
                tags=["graph_api", "throttling"]
            ),

            ErrorPattern(
                pattern=r"ErrorAccessDenied|Forbidden|InsufficientPermissions",
                category=ErrorCategory.AUTHORIZATION,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.ALERT,
                description="Graph API permission denied",
                retry_count=0,
                tags=["graph_api", "permissions"]
            ),

            ErrorPattern(
                pattern=r"ItemNotFound|ResourceNotFound|NotFound",
                category=ErrorCategory.NOT_FOUND,
                severity=ErrorSeverity.LOW,
                recovery_strategy=RecoveryStrategy.FAIL_FAST,
                description="Graph API resource not found",
                retry_count=0,
                tags=["graph_api", "not_found"]
            ),

            ErrorPattern(
                pattern=r"BadRequest|InvalidRequest|RequestBodyRead",
                category=ErrorCategory.CLIENT_ERROR,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=RecoveryStrategy.FAIL_FAST,
                description="Graph API request validation error",
                retry_count=0,
                tags=["graph_api", "validation"]
            ),

            # Generic permanent errors
            ErrorPattern(
                pattern=r"405|method.*not.*allowed|410|gone|501|not.*implemented",
                category=ErrorCategory.PERMANENT,
                severity=ErrorSeverity.HIGH,
                recovery_strategy=RecoveryStrategy.FAIL_FAST,
                description="Permanent client error",
                retry_count=0,
                tags=["permanent"]
            )
        ]

    def classify_error(self, error: Union[str, Exception, Dict[str, Any]],
                      context: Optional[Dict[str, Any]] = None) -> ErrorContext:
        """
        Classify error and determine recovery strategy

        Args:
            error: Error message, exception, or error data
            context: Additional context for classification

        Returns:
            ErrorContext with classification and recovery information
        """
        context = context or {}

        # Extract error information
        error_message = self._extract_error_message(error)
        status_code = self._extract_status_code(error, context)
        error_code = self._extract_error_code(error, context)

        # Classify using patterns
        error_pattern = self._match_error_pattern(error_message, status_code)

        # Generate correlation ID
        correlation_id = context.get("correlation_id") or str(uuid.uuid4())

        # Create error context
        error_context = ErrorContext(
            error_code=error_code or "UNKNOWN",
            error_message=error_message,
            status_code=status_code or 0,
            correlation_id=correlation_id,
            request_id=context.get("request_id"),
            operation=context.get("operation"),
            endpoint=context.get("endpoint"),
            user_id=context.get("user_id"),
            tenant_id=context.get("tenant_id"),
            retry_count=context.get("retry_count", 0),
            is_transient=error_pattern.category in [
                ErrorCategory.TRANSIENT,
                ErrorCategory.RATE_LIMIT,
                ErrorCategory.TIMEOUT,
                ErrorCategory.NETWORK_ERROR
            ],
            suggested_action=self._get_suggested_action(error_pattern),
            additional_details={
                "category": error_pattern.category,
                "severity": error_pattern.severity,
                "recovery_strategy": error_pattern.recovery_strategy,
                "pattern_description": error_pattern.description,
                "tags": error_pattern.tags,
                "retry_recommended": error_pattern.retry_count > 0,
                "max_retries": error_pattern.retry_count,
                "backoff_multiplier": error_pattern.backoff_multiplier,
                "circuit_breaker_threshold": error_pattern.circuit_breaker_threshold
            }
        )

        # Update metrics
        self._update_error_metrics(error_context)

        # Log classified error
        logger.error("Error classified",
                    error_code=error_context.error_code,
                    category=error_pattern.category,
                    severity=error_pattern.severity,
                    recovery_strategy=error_pattern.recovery_strategy,
                    correlation_id=correlation_id,
                    operation=error_context.operation)

        return error_context

    def _extract_error_message(self, error: Union[str, Exception, Dict[str, Any]]) -> str:
        """Extract error message from various error types"""
        if isinstance(error, str):
            return error
        elif isinstance(error, Exception):
            return str(error)
        elif isinstance(error, dict):
            # Try common error message fields
            for field in ["message", "error_description", "error", "detail", "description"]:
                if field in error:
                    if isinstance(error[field], dict) and "message" in error[field]:
                        return error[field]["message"]
                    return str(error[field])
            return str(error)
        else:
            return str(error)

    def _extract_status_code(self, error: Union[str, Exception, Dict[str, Any]],
                           context: Dict[str, Any]) -> Optional[int]:
        """Extract HTTP status code from error"""
        # Check context first
        if "status_code" in context:
            return int(context["status_code"])

        # Try to extract from error
        if isinstance(error, dict):
            for field in ["status_code", "statusCode", "code", "status"]:
                if field in error:
                    try:
                        return int(error[field])
                    except (ValueError, TypeError):
                        continue

        # Try to extract from exception
        if hasattr(error, "status_code"):
            try:
                return int(error.status_code)
            except (ValueError, TypeError):
                pass

        # Try to parse from message
        if isinstance(error, (str, Exception)):
            message = str(error)
            status_match = re.search(r'\b(4\d{2}|5\d{2})\b', message)
            if status_match:
                return int(status_match.group(1))

        return None

    def _extract_error_code(self, error: Union[str, Exception, Dict[str, Any]],
                          context: Dict[str, Any]) -> Optional[str]:
        """Extract error code from error"""
        # Check context first
        if "error_code" in context:
            return context["error_code"]

        # Try to extract from error dict
        if isinstance(error, dict):
            for field in ["error_code", "errorCode", "code", "error", "type"]:
                if field in error:
                    if isinstance(error[field], dict) and "code" in error[field]:
                        return error[field]["code"]
                    return str(error[field])

        # Try to extract from exception
        if hasattr(error, "error_code"):
            return str(error.error_code)

        return None

    def _match_error_pattern(self, error_message: str, status_code: Optional[int]) -> ErrorPattern:
        """Match error against classification patterns"""
        search_text = error_message.lower()

        # Add status code to search text if available
        if status_code:
            search_text = f"{status_code} {search_text}"

        # Try to match patterns
        for pattern in self.error_patterns:
            if re.search(pattern.pattern, search_text, re.IGNORECASE):
                return pattern

        # Default unknown pattern
        return ErrorPattern(
            pattern=".*",
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM,
            recovery_strategy=RecoveryStrategy.ALERT,
            description="Unclassified error",
            retry_count=1,
            tags=["unknown"]
        )

    def _get_suggested_action(self, pattern: ErrorPattern) -> str:
        """Get suggested action based on error pattern"""
        action_map = {
            RecoveryStrategy.RETRY: f"Retry operation with exponential backoff (max {pattern.retry_count} attempts)",
            RecoveryStrategy.REFRESH_TOKEN: "Refresh authentication token and retry",
            RecoveryStrategy.FALLBACK: "Use fallback mechanism or alternative approach",
            RecoveryStrategy.DEGRADE: "Continue with graceful degradation",
            RecoveryStrategy.ALERT: "Alert operations team for manual intervention",
            RecoveryStrategy.FAIL_FAST: "Fail immediately - no retry recommended",
            RecoveryStrategy.IGNORE: "Log error and continue operation"
        }
        return action_map.get(pattern.recovery_strategy, "Review error and determine appropriate action")

    def _update_error_metrics(self, error_context: ErrorContext) -> None:
        """Update error metrics and statistics"""
        error_code = error_context.error_code

        if error_code not in self.error_metrics:
            self.error_metrics[error_code] = ErrorMetrics(
                error_code=error_code,
                first_seen=error_context.timestamp
            )

        metrics = self.error_metrics[error_code]
        metrics.total_count += 1
        metrics.recent_count += 1
        metrics.last_seen = error_context.timestamp

        # Update correlation tracking
        if error_context.correlation_id:
            if error_context.correlation_id not in self.correlation_tracking:
                self.correlation_tracking[error_context.correlation_id] = []
            self.correlation_tracking[error_context.correlation_id].append(error_code)

    def get_error_metrics(self, error_code: Optional[str] = None) -> Union[ErrorMetrics, Dict[str, ErrorMetrics]]:
        """Get error metrics for specific error or all errors"""
        if error_code:
            return self.error_metrics.get(error_code, ErrorMetrics(error_code=error_code))
        return self.error_metrics.copy()

    def should_retry(self, error_context: ErrorContext) -> bool:
        """Determine if operation should be retried based on error classification"""
        retry_count = error_context.retry_count
        max_retries = error_context.additional_details.get("max_retries", 0)

        # Check circuit breaker
        if error_context.operation:
            if self._is_circuit_breaker_open(error_context.operation):
                return False

        # Check retry eligibility
        return (error_context.is_transient and
                retry_count < max_retries and
                error_context.additional_details.get("retry_recommended", False))

    def calculate_backoff_delay(self, error_context: ErrorContext) -> float:
        """Calculate backoff delay for retry"""
        base_delay = 1.0
        multiplier = error_context.additional_details.get("backoff_multiplier", 2.0)
        max_delay = error_context.additional_details.get("max_backoff", 300.0)
        retry_count = error_context.retry_count

        # Add jitter to prevent thundering herd
        import random
        jitter = random.uniform(0.1, 0.3)

        delay = base_delay * (multiplier ** retry_count) * (1 + jitter)
        return min(delay, max_delay)

    def _is_circuit_breaker_open(self, operation: str) -> bool:
        """Check if circuit breaker is open for operation"""
        if operation not in self.circuit_breakers:
            return False

        breaker = self.circuit_breakers[operation]

        if breaker.state == "open":
            # Check if timeout has passed
            if breaker.next_attempt and datetime.now(timezone.utc) >= breaker.next_attempt:
                breaker.state = "half_open"
                breaker.success_count = 0
                logger.info("Circuit breaker transitioning to half-open", operation=operation)
                return False
            return True

        return False

    def record_operation_result(self, operation: str, success: bool, error_context: Optional[ErrorContext] = None) -> None:
        """Record operation result for circuit breaker tracking"""
        if operation not in self.circuit_breakers:
            threshold = 5
            if error_context:
                threshold = error_context.additional_details.get("circuit_breaker_threshold", 5)

            self.circuit_breakers[operation] = CircuitBreakerState(
                operation=operation,
                threshold=threshold
            )

        breaker = self.circuit_breakers[operation]

        if success:
            breaker.success_count += 1

            if breaker.state == "half_open" and breaker.success_count >= 3:
                breaker.state = "closed"
                breaker.failure_count = 0
                logger.info("Circuit breaker closed", operation=operation)

        else:
            breaker.failure_count += 1
            breaker.last_failure = datetime.now(timezone.utc)

            if breaker.state in ["closed", "half_open"] and breaker.failure_count >= breaker.threshold:
                breaker.state = "open"
                breaker.next_attempt = datetime.now(timezone.utc) + timedelta(seconds=breaker.timeout)
                logger.warning("Circuit breaker opened",
                             operation=operation,
                             failure_count=breaker.failure_count)

    def get_circuit_breaker_status(self, operation: Optional[str] = None) -> Union[CircuitBreakerState, Dict[str, CircuitBreakerState]]:
        """Get circuit breaker status for operation or all operations"""
        if operation:
            return self.circuit_breakers.get(operation, CircuitBreakerState(operation=operation))
        return self.circuit_breakers.copy()

    def generate_error_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate comprehensive error report"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Filter recent errors
        recent_errors = {
            code: metrics for code, metrics in self.error_metrics.items()
            if metrics.last_seen and metrics.last_seen >= cutoff_time
        }

        # Calculate statistics
        total_errors = sum(metrics.recent_count for metrics in recent_errors.values())
        top_errors = sorted(recent_errors.items(), key=lambda x: x[1].recent_count, reverse=True)[:10]

        # Circuit breaker status
        active_breakers = {
            op: breaker for op, breaker in self.circuit_breakers.items()
            if breaker.state != "closed"
        }

        return {
            "report_period_hours": hours,
            "total_errors": total_errors,
            "unique_error_types": len(recent_errors),
            "top_errors": [
                {
                    "error_code": code,
                    "count": metrics.recent_count,
                    "last_seen": metrics.last_seen.isoformat() if metrics.last_seen else None
                }
                for code, metrics in top_errors
            ],
            "circuit_breaker_status": {
                op: {
                    "state": breaker.state,
                    "failure_count": breaker.failure_count,
                    "last_failure": breaker.last_failure.isoformat() if breaker.last_failure else None
                }
                for op, breaker in active_breakers.items()
            },
            "correlation_tracking": {
                correlation_id: errors for correlation_id, errors in self.correlation_tracking.items()
                if len(errors) > 1  # Only show correlated errors
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


# Global error handler instance
_error_handler: Optional[EnhancedErrorHandler] = None


def get_error_handler() -> EnhancedErrorHandler:
    """Get or create global error handler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = EnhancedErrorHandler()
    return _error_handler


def handle_error(error: Union[str, Exception, Dict[str, Any]],
                context: Optional[Dict[str, Any]] = None) -> ErrorContext:
    """Convenience function to handle and classify errors"""
    handler = get_error_handler()
    return handler.classify_error(error, context)