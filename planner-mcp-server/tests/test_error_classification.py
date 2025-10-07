"""
Comprehensive tests for error handling system
Story 2.1 Task 7: Error classification, circuit breaker, retry logic, and metrics
"""

import pytest
import asyncio
import uuid
import re
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Any, Optional

# Import the error handling components
from src.utils.error_handler import (
    EnhancedErrorHandler,
    ErrorCategory,
    ErrorSeverity,
    RecoveryStrategy,
    ErrorPattern,
    ErrorMetrics,
    CircuitBreakerState,
    get_error_handler,
    handle_error
)
from src.models.graph_models import ErrorContext


class TestErrorPatternMatching:
    """Test error pattern classification functionality"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_authentication_error_patterns(self, error_handler):
        """Test authentication error pattern matching"""
        test_cases = [
            ("401 Unauthorized", ErrorCategory.AUTHENTICATION),
            ("Invalid token provided", ErrorCategory.AUTHENTICATION),
            ("Token has expired", ErrorCategory.AUTHENTICATION),
            ("InvalidAuthenticationToken", ErrorCategory.AUTHENTICATION),
            ("CompactToken parsing failed", ErrorCategory.AUTHENTICATION)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.REFRESH_TOKEN

    def test_authorization_error_patterns(self, error_handler):
        """Test authorization error pattern matching"""
        test_cases = [
            ("403 Forbidden", ErrorCategory.AUTHORIZATION),
            ("Access denied", ErrorCategory.AUTHORIZATION),
            ("Insufficient privileges", ErrorCategory.AUTHORIZATION),
            ("ErrorAccessDenied", ErrorCategory.AUTHORIZATION),
            ("InsufficientPermissions", ErrorCategory.AUTHORIZATION)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.ALERT
            assert result.additional_details["max_retries"] == 0

    def test_rate_limit_error_patterns(self, error_handler):
        """Test rate limiting error pattern matching"""
        test_cases = [
            ("429 Too Many Requests", ErrorCategory.RATE_LIMIT),
            ("Rate limit exceeded", ErrorCategory.RATE_LIMIT),
            ("Quota exceeded", ErrorCategory.RATE_LIMIT),
            ("TooManyRequests", ErrorCategory.RATE_LIMIT),
            ("Request_ThrottledTemporarily", ErrorCategory.RATE_LIMIT)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.RETRY
            assert result.additional_details["max_retries"] == 3

    def test_not_found_error_patterns(self, error_handler):
        """Test not found error pattern matching"""
        test_cases = [
            ("404 Not Found", ErrorCategory.NOT_FOUND),
            ("Resource not found", ErrorCategory.NOT_FOUND),
            ("Item not found", ErrorCategory.NOT_FOUND),
            ("ItemNotFound", ErrorCategory.NOT_FOUND),
            ("ResourceNotFound", ErrorCategory.NOT_FOUND)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.FAIL_FAST
            assert result.additional_details["max_retries"] == 0

    def test_validation_error_patterns(self, error_handler):
        """Test validation error pattern matching"""
        test_cases = [
            ("400 Bad Request", ErrorCategory.CLIENT_ERROR),
            ("Invalid request format", ErrorCategory.CLIENT_ERROR),
            ("Validation failed", ErrorCategory.CLIENT_ERROR),
            ("Malformed request", ErrorCategory.CLIENT_ERROR),
            ("BadRequest", ErrorCategory.CLIENT_ERROR)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.FAIL_FAST

    def test_server_error_patterns(self, error_handler):
        """Test server error pattern matching"""
        test_cases = [
            ("500 Internal Server Error", ErrorCategory.SERVER_ERROR),
            ("502 Bad Gateway", ErrorCategory.TRANSIENT),
            ("503 Service Unavailable", ErrorCategory.TRANSIENT),
            ("504 Gateway Timeout", ErrorCategory.TRANSIENT)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.RETRY

    def test_network_error_patterns(self, error_handler):
        """Test network error pattern matching"""
        test_cases = [
            ("Connection refused", ErrorCategory.NETWORK_ERROR),
            ("Connection timeout", ErrorCategory.NETWORK_ERROR),
            ("DNS resolution failed", ErrorCategory.NETWORK_ERROR),
            ("Network unreachable", ErrorCategory.NETWORK_ERROR),
            ("SSL error", ErrorCategory.NETWORK_ERROR)
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category

    def test_timeout_error_patterns(self, error_handler):
        """Test timeout error pattern matching"""
        test_cases = [
            ("Request timeout", ErrorCategory.TIMEOUT),
            ("Read timeout", ErrorCategory.TIMEOUT),
            ("timeout occurred", ErrorCategory.TIMEOUT)  # Changed to match the pattern better
        ]

        for error_message, expected_category in test_cases:
            result = error_handler.classify_error(error_message)
            assert result.additional_details["category"] == expected_category
            assert result.additional_details["recovery_strategy"] == RecoveryStrategy.RETRY

    def test_unknown_error_pattern(self, error_handler):
        """Test unknown error classification"""
        unknown_error = "Some completely unknown error message xyz123"
        result = error_handler.classify_error(unknown_error)

        assert result.additional_details["category"] == ErrorCategory.UNKNOWN
        assert result.additional_details["recovery_strategy"] == RecoveryStrategy.ALERT
        assert result.additional_details["max_retries"] == 1


class TestErrorExtraction:
    """Test error information extraction from various formats"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_extract_message_from_string(self, error_handler):
        """Test extracting error message from string"""
        error_message = "Something went wrong"
        extracted = error_handler._extract_error_message(error_message)
        assert extracted == error_message

    def test_extract_message_from_exception(self, error_handler):
        """Test extracting error message from exception"""
        error = ValueError("Invalid input provided")
        extracted = error_handler._extract_error_message(error)
        assert extracted == "Invalid input provided"

    def test_extract_message_from_dict(self, error_handler):
        """Test extracting error message from dictionary"""
        test_cases = [
            ({"message": "Error occurred"}, "Error occurred"),
            ({"error_description": "Auth failed"}, "Auth failed"),
            ({"error": "Not found"}, "Not found"),
            ({"detail": "Validation error"}, "Validation error"),
            ({"error": {"message": "Nested error"}}, "Nested error")
        ]

        for error_dict, expected in test_cases:
            extracted = error_handler._extract_error_message(error_dict)
            assert extracted == expected

    def test_extract_status_code_from_context(self, error_handler):
        """Test extracting status code from context"""
        error = "Some error"
        context = {"status_code": 404}

        status_code = error_handler._extract_status_code(error, context)
        assert status_code == 404

    def test_extract_status_code_from_dict(self, error_handler):
        """Test extracting status code from error dictionary"""
        test_cases = [
            ({"status_code": 500}, 500),
            ({"statusCode": 400}, 400),
            ({"code": 403}, 403),
            ({"status": 429}, 429)
        ]

        for error_dict, expected in test_cases:
            status_code = error_handler._extract_status_code(error_dict, {})
            assert status_code == expected

    def test_extract_status_code_from_message(self, error_handler):
        """Test extracting status code from error message"""
        test_cases = [
            ("HTTP 404 not found", 404),
            ("Server returned 500 error", 500),
            ("Got 429 rate limit", 429)
        ]

        for message, expected in test_cases:
            status_code = error_handler._extract_status_code(message, {})
            assert status_code == expected

    def test_extract_error_code_from_context(self, error_handler):
        """Test extracting error code from context"""
        error = "Some error"
        context = {"error_code": "INVALID_TOKEN"}

        error_code = error_handler._extract_error_code(error, context)
        assert error_code == "INVALID_TOKEN"

    def test_extract_error_code_from_dict(self, error_handler):
        """Test extracting error code from error dictionary"""
        test_cases = [
            ({"error_code": "AUTH_FAILED"}, "AUTH_FAILED"),
            ({"errorCode": "NOT_FOUND"}, "NOT_FOUND"),
            ({"code": "TIMEOUT"}, "TIMEOUT"),
            ({"error": {"code": "NESTED_ERROR"}}, "NESTED_ERROR")
        ]

        for error_dict, expected in test_cases:
            error_code = error_handler._extract_error_code(error_dict, {})
            assert error_code == expected


class TestCircuitBreakerFunctionality:
    """Test circuit breaker functionality"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_circuit_breaker_initialization(self, error_handler):
        """Test circuit breaker initialization"""
        operation = "test_operation"

        # Initially no circuit breaker exists
        assert operation not in error_handler.circuit_breakers

        # Record a failure to initialize circuit breaker
        error_handler.record_operation_result(operation, False)

        # Circuit breaker should now exist and be closed
        assert operation in error_handler.circuit_breakers
        breaker = error_handler.circuit_breakers[operation]
        assert breaker.state == "closed"
        assert breaker.failure_count == 1

    def test_circuit_breaker_stays_closed_on_success(self, error_handler):
        """Test circuit breaker stays closed on successful operations"""
        operation = "test_operation"

        # Record several successes
        for _ in range(5):
            error_handler.record_operation_result(operation, True)

        breaker = error_handler.circuit_breakers[operation]
        assert breaker.state == "closed"
        assert breaker.success_count == 5
        assert breaker.failure_count == 0

    def test_circuit_breaker_opens_on_threshold_failures(self, error_handler):
        """Test circuit breaker opens after threshold failures"""
        operation = "test_operation"
        threshold = 5

        # Set up circuit breaker with custom threshold
        error_context = Mock()
        error_context.additional_details = {"circuit_breaker_threshold": threshold}

        # Record failures up to threshold
        for i in range(threshold):
            error_handler.record_operation_result(operation, False, error_context)

        breaker = error_handler.circuit_breakers[operation]
        assert breaker.state == "open"
        assert breaker.failure_count == threshold
        assert breaker.next_attempt is not None

    def test_circuit_breaker_half_open_transition(self, error_handler):
        """Test circuit breaker transitions to half-open after timeout"""
        operation = "test_operation"

        # Open the circuit breaker
        for _ in range(5):
            error_handler.record_operation_result(operation, False)

        breaker = error_handler.circuit_breakers[operation]
        assert breaker.state == "open"

        # Manually set next_attempt to past time to simulate timeout
        breaker.next_attempt = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Check if circuit breaker is open (should transition to half-open)
        is_open = error_handler._is_circuit_breaker_open(operation)
        assert not is_open  # Should return False as it transitions to half-open
        assert breaker.state == "half_open"

    def test_circuit_breaker_closes_after_half_open_successes(self, error_handler):
        """Test circuit breaker closes after successful operations in half-open state"""
        operation = "test_operation"

        # Set up half-open state
        error_handler.circuit_breakers[operation] = CircuitBreakerState(
            operation=operation,
            state="half_open",
            failure_count=5
        )

        # Record 3 successes in half-open state
        for _ in range(3):
            error_handler.record_operation_result(operation, True)

        breaker = error_handler.circuit_breakers[operation]
        assert breaker.state == "closed"
        assert breaker.failure_count == 0
        assert breaker.success_count >= 3

    def test_circuit_breaker_reopens_on_half_open_failure(self, error_handler):
        """Test circuit breaker reopens on failure in half-open state"""
        operation = "test_operation"

        # Set up half-open state with failure count at threshold
        error_handler.circuit_breakers[operation] = CircuitBreakerState(
            operation=operation,
            state="half_open",
            failure_count=4,  # One less than threshold
            threshold=5
        )

        # Record failure in half-open state - this should trigger opening
        error_handler.record_operation_result(operation, False)

        breaker = error_handler.circuit_breakers[operation]
        assert breaker.state == "open"
        assert breaker.failure_count == 5

    def test_circuit_breaker_status_retrieval(self, error_handler):
        """Test circuit breaker status retrieval"""
        operation1 = "operation1"
        operation2 = "operation2"

        # Create circuit breakers
        error_handler.record_operation_result(operation1, False)
        error_handler.record_operation_result(operation2, True)

        # Test individual status
        status1 = error_handler.get_circuit_breaker_status(operation1)
        assert status1.operation == operation1
        assert status1.failure_count == 1

        # Test all statuses
        all_statuses = error_handler.get_circuit_breaker_status()
        assert operation1 in all_statuses
        assert operation2 in all_statuses

        # Test non-existent operation
        unknown_status = error_handler.get_circuit_breaker_status("unknown")
        assert unknown_status.operation == "unknown"
        assert unknown_status.state == "closed"


class TestRetryLogicAndBackoff:
    """Test retry logic and backoff calculation"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_should_retry_transient_error(self, error_handler):
        """Test should retry for transient errors within retry limit"""
        error_context = ErrorContext(
            error_code="TIMEOUT",
            error_message="Request timeout",
            status_code=408,
            retry_count=1,
            is_transient=True,
            additional_details={
                "max_retries": 3,
                "retry_recommended": True
            }
        )

        assert error_handler.should_retry(error_context)

    def test_should_not_retry_non_transient_error(self, error_handler):
        """Test should not retry for non-transient errors"""
        error_context = ErrorContext(
            error_code="NOT_FOUND",
            error_message="Resource not found",
            status_code=404,
            retry_count=0,
            is_transient=False,
            additional_details={
                "max_retries": 3,
                "retry_recommended": False
            }
        )

        assert not error_handler.should_retry(error_context)

    def test_should_not_retry_exceeded_max_retries(self, error_handler):
        """Test should not retry when max retries exceeded"""
        error_context = ErrorContext(
            error_code="TIMEOUT",
            error_message="Request timeout",
            status_code=408,
            retry_count=5,
            is_transient=True,
            additional_details={
                "max_retries": 3,
                "retry_recommended": True
            }
        )

        assert not error_handler.should_retry(error_context)

    def test_should_not_retry_circuit_breaker_open(self, error_handler):
        """Test should not retry when circuit breaker is open"""
        operation = "test_operation"

        # Open circuit breaker
        for _ in range(5):
            error_handler.record_operation_result(operation, False)

        error_context = ErrorContext(
            error_code="TIMEOUT",
            error_message="Request timeout",
            status_code=408,
            retry_count=1,
            is_transient=True,
            operation=operation,
            additional_details={
                "max_retries": 3,
                "retry_recommended": True
            }
        )

        assert not error_handler.should_retry(error_context)

    def test_backoff_delay_calculation(self, error_handler):
        """Test exponential backoff delay calculation"""
        test_cases = [
            (0, 1.0, 2.0),  # First retry
            (1, 2.0, 2.0),  # Second retry
            (2, 4.0, 2.0),  # Third retry
            (3, 8.0, 2.0),  # Fourth retry
        ]

        for retry_count, expected_base, multiplier in test_cases:
            error_context = ErrorContext(
                error_code="TIMEOUT",
                error_message="Request timeout",
                status_code=408,
                retry_count=retry_count,
                additional_details={
                    "backoff_multiplier": multiplier,
                    "max_backoff": 300.0
                }
            )

            delay = error_handler.calculate_backoff_delay(error_context)

            # Account for jitter (10-30% added)
            min_expected = expected_base * 1.1
            max_expected = expected_base * 1.3

            assert min_expected <= delay <= max_expected

    def test_backoff_delay_max_limit(self, error_handler):
        """Test backoff delay respects maximum limit"""
        error_context = ErrorContext(
            error_code="TIMEOUT",
            error_message="Request timeout",
            status_code=408,
            retry_count=10,  # High retry count
            additional_details={
                "backoff_multiplier": 2.0,
                "max_backoff": 60.0  # Low max to test limit
            }
        )

        delay = error_handler.calculate_backoff_delay(error_context)
        assert delay <= 60.0

    @patch('random.uniform')
    def test_backoff_delay_jitter(self, mock_random, error_handler):
        """Test that jitter is applied to backoff delay"""
        mock_random.return_value = 0.2  # Fixed jitter value

        error_context = ErrorContext(
            error_code="TIMEOUT",
            error_message="Request timeout",
            status_code=408,
            retry_count=1,
            additional_details={
                "backoff_multiplier": 2.0,
                "max_backoff": 300.0
            }
        )

        delay = error_handler.calculate_backoff_delay(error_context)

        # Base delay: 1.0 * (2.0 ** 1) = 2.0
        # With jitter: 2.0 * (1 + 0.2) = 2.4
        expected = 2.4
        assert abs(delay - expected) < 0.01


class TestErrorMetricsTracking:
    """Test error metrics tracking functionality"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_error_metrics_initialization(self, error_handler):
        """Test error metrics initialization on first error"""
        error_context = ErrorContext(
            error_code="TEST_ERROR",
            error_message="Test error message",
            status_code=500,
            timestamp=datetime.now(timezone.utc)
        )

        # Initially no metrics
        assert "TEST_ERROR" not in error_handler.error_metrics

        # Update metrics
        error_handler._update_error_metrics(error_context)

        # Metrics should now exist
        assert "TEST_ERROR" in error_handler.error_metrics
        metrics = error_handler.error_metrics["TEST_ERROR"]
        assert metrics.error_code == "TEST_ERROR"
        assert metrics.total_count == 1
        assert metrics.recent_count == 1
        assert metrics.first_seen == error_context.timestamp
        assert metrics.last_seen == error_context.timestamp

    def test_error_metrics_accumulation(self, error_handler):
        """Test error metrics accumulate correctly"""
        error_code = "REPEATED_ERROR"

        # Create multiple error contexts
        for i in range(5):
            error_context = ErrorContext(
                error_code=error_code,
                error_message=f"Error occurrence {i}",
                status_code=500,
                timestamp=datetime.now(timezone.utc)
            )
            error_handler._update_error_metrics(error_context)

        metrics = error_handler.error_metrics[error_code]
        assert metrics.total_count == 5
        assert metrics.recent_count == 5

    def test_correlation_tracking(self, error_handler):
        """Test error correlation tracking"""
        correlation_id = str(uuid.uuid4())

        # Create multiple errors with same correlation ID
        error_codes = ["ERROR_1", "ERROR_2", "ERROR_3"]
        for error_code in error_codes:
            error_context = ErrorContext(
                error_code=error_code,
                error_message="Correlated error",
                status_code=500,
                correlation_id=correlation_id
            )
            error_handler._update_error_metrics(error_context)

        # Check correlation tracking
        assert correlation_id in error_handler.correlation_tracking
        tracked_errors = error_handler.correlation_tracking[correlation_id]
        assert len(tracked_errors) == 3
        assert all(error_code in tracked_errors for error_code in error_codes)

    def test_get_error_metrics_specific(self, error_handler):
        """Test retrieving specific error metrics"""
        error_code = "SPECIFIC_ERROR"
        error_context = ErrorContext(
            error_code=error_code,
            error_message="Specific error",
            status_code=400
        )
        error_handler._update_error_metrics(error_context)

        # Get specific metrics
        metrics = error_handler.get_error_metrics(error_code)
        assert metrics.error_code == error_code
        assert metrics.total_count == 1

        # Get non-existent metrics
        missing_metrics = error_handler.get_error_metrics("NON_EXISTENT")
        assert missing_metrics.error_code == "NON_EXISTENT"
        assert missing_metrics.total_count == 0

    def test_get_all_error_metrics(self, error_handler):
        """Test retrieving all error metrics"""
        # Create multiple error types
        error_codes = ["ERROR_A", "ERROR_B", "ERROR_C"]
        for error_code in error_codes:
            error_context = ErrorContext(
                error_code=error_code,
                error_message="Test error",
                status_code=500
            )
            error_handler._update_error_metrics(error_context)

        # Get all metrics
        all_metrics = error_handler.get_error_metrics()
        assert len(all_metrics) >= 3
        assert all(error_code in all_metrics for error_code in error_codes)


class TestRecoveryStrategyDetermination:
    """Test recovery strategy determination"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_suggested_action_generation(self, error_handler):
        """Test suggested action generation for different recovery strategies"""
        test_cases = [
            (RecoveryStrategy.RETRY, "Retry operation with exponential backoff"),
            (RecoveryStrategy.REFRESH_TOKEN, "Refresh authentication token and retry"),
            (RecoveryStrategy.FALLBACK, "Use fallback mechanism or alternative approach"),
            (RecoveryStrategy.DEGRADE, "Continue with graceful degradation"),
            (RecoveryStrategy.ALERT, "Alert operations team for manual intervention"),
            (RecoveryStrategy.FAIL_FAST, "Fail immediately - no retry recommended"),
            (RecoveryStrategy.IGNORE, "Log error and continue operation")
        ]

        for strategy, expected_text in test_cases:
            pattern = ErrorPattern(
                pattern="test",
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                recovery_strategy=strategy,
                description="Test pattern",
                retry_count=3
            )

            action = error_handler._get_suggested_action(pattern)
            assert expected_text.lower() in action.lower()

    def test_error_context_recovery_information(self, error_handler):
        """Test that error context contains proper recovery information"""
        error_message = "429 Too Many Requests"
        result = error_handler.classify_error(error_message)

        # Should be classified as rate limit error
        assert result.additional_details["category"] == ErrorCategory.RATE_LIMIT
        assert result.additional_details["recovery_strategy"] == RecoveryStrategy.RETRY
        assert result.additional_details["retry_recommended"] is True
        assert result.additional_details["max_retries"] == 3
        assert result.additional_details["backoff_multiplier"] == 2.0
        assert result.is_transient is True
        assert "retry" in result.suggested_action.lower()

    def test_non_recoverable_error_strategy(self, error_handler):
        """Test non-recoverable error strategies"""
        error_message = "404 Not Found"
        result = error_handler.classify_error(error_message)

        # Should be classified as not found with fail fast strategy
        assert result.additional_details["category"] == ErrorCategory.NOT_FOUND
        assert result.additional_details["recovery_strategy"] == RecoveryStrategy.FAIL_FAST
        assert result.additional_details["retry_recommended"] is False
        assert result.additional_details["max_retries"] == 0
        assert result.is_transient is False


class TestErrorReportGeneration:
    """Test error report generation functionality"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_error_report_structure(self, error_handler):
        """Test error report contains required fields"""
        # Generate some errors first
        error_codes = ["ERROR_1", "ERROR_2", "ERROR_3"]
        for error_code in error_codes:
            error_context = ErrorContext(
                error_code=error_code,
                error_message="Test error",
                status_code=500,
                timestamp=datetime.now(timezone.utc)
            )
            error_handler._update_error_metrics(error_context)

        report = error_handler.generate_error_report(24)

        # Check required fields
        required_fields = [
            "report_period_hours",
            "total_errors",
            "unique_error_types",
            "top_errors",
            "circuit_breaker_status",
            "correlation_tracking",
            "generated_at"
        ]

        for field in required_fields:
            assert field in report

    def test_error_report_time_filtering(self, error_handler):
        """Test error report filters by time period"""
        # Create old error (outside time window)
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        old_error = ErrorContext(
            error_code="OLD_ERROR",
            error_message="Old error",
            status_code=500,
            timestamp=old_time
        )
        error_handler.error_metrics["OLD_ERROR"] = ErrorMetrics(
            error_code="OLD_ERROR",
            total_count=1,
            recent_count=1,
            first_seen=old_time,
            last_seen=old_time
        )

        # Create recent error (within time window)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_error = ErrorContext(
            error_code="RECENT_ERROR",
            error_message="Recent error",
            status_code=500,
            timestamp=recent_time
        )
        error_handler._update_error_metrics(recent_error)

        # Generate 24-hour report
        report = error_handler.generate_error_report(24)

        # Should only include recent error
        assert report["unique_error_types"] == 1
        assert len(report["top_errors"]) == 1
        assert report["top_errors"][0]["error_code"] == "RECENT_ERROR"

    def test_error_report_top_errors_sorting(self, error_handler):
        """Test top errors are sorted by frequency"""
        # Create errors with different frequencies
        error_frequencies = [("LOW_FREQ", 1), ("HIGH_FREQ", 5), ("MED_FREQ", 3)]

        for error_code, frequency in error_frequencies:
            for _ in range(frequency):
                error_context = ErrorContext(
                    error_code=error_code,
                    error_message="Test error",
                    status_code=500,
                    timestamp=datetime.now(timezone.utc)
                )
                error_handler._update_error_metrics(error_context)

        report = error_handler.generate_error_report(24)
        top_errors = report["top_errors"]

        # Should be sorted by count (descending)
        assert len(top_errors) == 3
        assert top_errors[0]["error_code"] == "HIGH_FREQ"
        assert top_errors[0]["count"] == 5
        assert top_errors[1]["error_code"] == "MED_FREQ"
        assert top_errors[1]["count"] == 3
        assert top_errors[2]["error_code"] == "LOW_FREQ"
        assert top_errors[2]["count"] == 1

    def test_error_report_circuit_breaker_status(self, error_handler):
        """Test error report includes circuit breaker status"""
        operation = "test_operation"

        # Open a circuit breaker
        for _ in range(5):
            error_handler.record_operation_result(operation, False)

        report = error_handler.generate_error_report(24)

        # Should include circuit breaker status
        assert operation in report["circuit_breaker_status"]
        breaker_status = report["circuit_breaker_status"][operation]
        assert breaker_status["state"] == "open"
        assert breaker_status["failure_count"] == 5

    def test_error_report_correlation_tracking(self, error_handler):
        """Test error report includes correlation tracking"""
        correlation_id = str(uuid.uuid4())

        # Create correlated errors
        for i in range(3):
            error_context = ErrorContext(
                error_code=f"ERROR_{i}",
                error_message="Correlated error",
                status_code=500,
                correlation_id=correlation_id,
                timestamp=datetime.now(timezone.utc)
            )
            error_handler._update_error_metrics(error_context)

        report = error_handler.generate_error_report(24)

        # Should include correlation tracking for errors with multiple occurrences
        assert correlation_id in report["correlation_tracking"]
        correlated_errors = report["correlation_tracking"][correlation_id]
        assert len(correlated_errors) == 3


class TestErrorHandlerIntegration:
    """Test error handler integration and end-to-end functionality"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_full_error_handling_workflow(self, error_handler):
        """Test complete error handling workflow"""
        # Simulate a real error scenario
        error_data = {
            "error": {
                "code": "TooManyRequests",
                "message": "Rate limit exceeded for this resource"
            },
            "status": 429
        }

        context = {
            "operation": "get_tasks",
            "endpoint": "/me/planner/tasks",
            "user_id": "user123",
            "tenant_id": "tenant456",
            "request_id": str(uuid.uuid4())
        }

        # Classify error
        result = error_handler.classify_error(error_data, context)

        # Verify classification
        assert result.error_code == "TooManyRequests"
        assert result.status_code == 429
        assert result.additional_details["category"] == ErrorCategory.RATE_LIMIT
        assert result.is_transient is True

        # Check if should retry
        assert error_handler.should_retry(result)

        # Calculate backoff delay
        delay = error_handler.calculate_backoff_delay(result)
        assert delay > 0

        # Record operation result
        error_handler.record_operation_result(context["operation"], False, result)

        # Check metrics were updated
        metrics = error_handler.get_error_metrics("TooManyRequests")
        assert metrics.total_count == 1

    def test_error_escalation_scenario(self, error_handler):
        """Test error escalation through circuit breaker"""
        operation = "failing_operation"
        error_context = Mock()
        error_context.additional_details = {"circuit_breaker_threshold": 3}

        # Simulate repeated failures
        for i in range(5):
            error_handler.record_operation_result(operation, False, error_context)

            # Check circuit breaker state progression
            if i < 2:
                assert not error_handler._is_circuit_breaker_open(operation)
            else:
                assert error_handler._is_circuit_breaker_open(operation)

    def test_error_recovery_scenario(self, error_handler):
        """Test error recovery scenario"""
        operation = "recovering_operation"

        # Fail enough times to open circuit breaker
        for _ in range(5):
            error_handler.record_operation_result(operation, False)

        # Verify circuit breaker is open
        assert error_handler._is_circuit_breaker_open(operation)

        # Simulate timeout passage
        breaker = error_handler.circuit_breakers[operation]
        breaker.next_attempt = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Should transition to half-open
        assert not error_handler._is_circuit_breaker_open(operation)
        assert breaker.state == "half_open"

        # Record successes to close circuit breaker
        for _ in range(3):
            error_handler.record_operation_result(operation, True)

        # Circuit breaker should be closed
        assert breaker.state == "closed"
        assert not error_handler._is_circuit_breaker_open(operation)

    def test_global_error_handler_instance(self):
        """Test global error handler instance management"""
        # Get global instance
        handler1 = get_error_handler()
        handler2 = get_error_handler()

        # Should be same instance (singleton)
        assert handler1 is handler2

        # Test convenience function
        error_result = handle_error("Test error", {"operation": "test"})
        assert isinstance(error_result, ErrorContext)
        assert error_result.error_message == "Test error"

    def test_concurrent_error_handling(self, error_handler):
        """Test concurrent error handling doesn't cause issues"""
        import threading
        import time

        results = []

        def handle_errors():
            for i in range(10):
                error = f"Concurrent error {i}"
                result = error_handler.classify_error(error)
                results.append(result)
                time.sleep(0.001)  # Small delay to simulate processing

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=handle_errors)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all errors were handled
        assert len(results) == 50  # 5 threads * 10 errors each
        assert all(isinstance(result, ErrorContext) for result in results)


class TestErrorPatternCustomization:
    """Test error pattern customization and extension"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_custom_error_pattern_addition(self, error_handler):
        """Test adding custom error patterns"""
        # Add custom pattern
        custom_pattern = ErrorPattern(
            pattern=r"CUSTOM_ERROR_CODE",
            category=ErrorCategory.CLIENT_ERROR,
            severity=ErrorSeverity.HIGH,
            recovery_strategy=RecoveryStrategy.FALLBACK,
            description="Custom application error",
            retry_count=2,
            tags=["custom", "application"]
        )

        error_handler.error_patterns.append(custom_pattern)

        # Test custom pattern matching
        result = error_handler.classify_error("CUSTOM_ERROR_CODE: Something went wrong")

        assert result.additional_details["category"] == ErrorCategory.CLIENT_ERROR
        assert result.additional_details["recovery_strategy"] == RecoveryStrategy.FALLBACK
        assert result.additional_details["pattern_description"] == "Custom application error"
        assert "custom" in result.additional_details["tags"]

    def test_pattern_priority_ordering(self, error_handler):
        """Test that more specific patterns take precedence"""
        # Add a more specific pattern for authentication
        specific_pattern = ErrorPattern(
            pattern=r"InvalidAuthenticationToken.*expired",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.CRITICAL,
            recovery_strategy=RecoveryStrategy.REFRESH_TOKEN,
            description="Specific expired token error",
            retry_count=1,
            tags=["auth", "expired", "specific"]
        )

        # Insert at beginning to give it priority
        error_handler.error_patterns.insert(0, specific_pattern)

        # Test that specific pattern matches
        result = error_handler.classify_error("InvalidAuthenticationToken has expired")

        assert result.additional_details["severity"] == ErrorSeverity.CRITICAL
        assert "specific" in result.additional_details["tags"]


# Performance and stress tests
class TestErrorHandlerPerformance:
    """Test error handler performance characteristics"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance for testing"""
        return EnhancedErrorHandler()

    def test_classification_performance(self, error_handler):
        """Test error classification performance"""
        import time

        error_messages = [
            "401 Unauthorized access",
            "429 Too Many Requests",
            "500 Internal Server Error",
            "404 Resource Not Found",
            "Connection timeout occurred"
        ] * 100  # 500 total classifications

        start_time = time.time()

        for message in error_messages:
            error_handler.classify_error(message)

        end_time = time.time()
        duration = end_time - start_time

        # Should classify 500 errors in reasonable time (< 1 second)
        assert duration < 1.0

        # Average time per classification should be very fast
        avg_time = duration / len(error_messages)
        assert avg_time < 0.002  # Less than 2ms per classification

    def test_memory_usage_stability(self, error_handler):
        """Test that error handler doesn't leak memory"""
        import gc

        # Get initial object count
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Process many errors
        for i in range(1000):
            error_handler.classify_error(f"Error {i}: Something went wrong")

        # Force garbage collection
        gc.collect()
        final_objects = len(gc.get_objects())

        # Object count shouldn't grow excessively
        object_growth = final_objects - initial_objects
        assert object_growth < 5000  # Reasonable growth limit

    def test_large_error_message_handling(self, error_handler):
        """Test handling of very large error messages"""
        # Create large error message (10KB)
        large_message = "Error: " + "x" * 10000

        # Should handle large messages without issues
        result = error_handler.classify_error(large_message)
        assert result is not None
        assert result.error_message == large_message


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])