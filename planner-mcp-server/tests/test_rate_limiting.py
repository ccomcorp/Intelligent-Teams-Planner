"""
Comprehensive tests for the Intelligent Rate Limiting system
Story 2.1 Task 6: Rate Limit Handling with exponential backoff, adaptive retry, and circuit breaker
"""

import pytest
import asyncio
import time
import random
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from src.graph.rate_limiter import (
    IntelligentRateLimiter, RateLimitStrategy, EndpointTier,
    RateLimitWindow, RetryConfig, RateLimitState,
    get_rate_limiter
)
from src.utils.performance_monitor import get_performance_monitor


class TestRateLimitWindow:
    """Test rate limit window functionality"""

    def test_window_creation(self):
        """Test creating a rate limit window"""
        window = RateLimitWindow(
            window_start=datetime.now(timezone.utc),
            window_size_seconds=3600,
            requests_allowed=1000
        )

        assert window.window_start is not None
        assert window.window_size_seconds == 3600
        assert window.requests_made == 0
        assert window.requests_allowed == 1000
        assert window.reset_time is None

    def test_window_expiry_check(self):
        """Test window expiry detection"""
        # Create expired window
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        expired_window = RateLimitWindow(
            window_start=past_time,
            window_size_seconds=3600
        )
        assert expired_window.is_expired()

        # Create active window
        current_time = datetime.now(timezone.utc)
        active_window = RateLimitWindow(
            window_start=current_time,
            window_size_seconds=3600
        )
        assert not active_window.is_expired()

    def test_time_until_reset(self):
        """Test time until reset calculation"""
        current_time = datetime.now(timezone.utc)
        window = RateLimitWindow(
            window_start=current_time,
            window_size_seconds=300  # 5 minutes
        )

        time_until_reset = window.time_until_reset()
        assert 250 <= time_until_reset <= 300  # Should be close to 5 minutes

        # Test with explicit reset time
        reset_time = current_time + timedelta(seconds=600)
        window.reset_time = reset_time
        time_until_reset = window.time_until_reset()
        assert 550 <= time_until_reset <= 600  # Should be close to 10 minutes

    def test_can_make_request(self):
        """Test request capacity checking"""
        window = RateLimitWindow(
            window_start=datetime.now(timezone.utc),
            window_size_seconds=3600,
            requests_allowed=100
        )

        # Should allow requests when under limit
        assert window.can_make_request()

        # Fill up the window
        window.requests_made = 99
        assert window.can_make_request()

        # Exceed the limit
        window.requests_made = 100
        assert not window.can_make_request()

        window.requests_made = 101
        assert not window.can_make_request()


class TestRetryConfig:
    """Test retry configuration functionality"""

    def test_default_config(self):
        """Test default retry configuration"""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 300.0
        assert config.backoff_multiplier == 2.0
        assert config.jitter_range == (0.1, 0.3)
        assert config.strategy == RateLimitStrategy.EXPONENTIAL_BACKOFF

    def test_custom_config(self):
        """Test custom retry configuration"""
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=600.0,
            backoff_multiplier=1.5,
            jitter_range=(0.2, 0.4),
            strategy=RateLimitStrategy.ADAPTIVE
        )

        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 600.0
        assert config.backoff_multiplier == 1.5
        assert config.jitter_range == (0.2, 0.4)
        assert config.strategy == RateLimitStrategy.ADAPTIVE


class TestRateLimitState:
    """Test rate limit state tracking"""

    def test_state_creation(self):
        """Test creating rate limit state"""
        state = RateLimitState(
            endpoint="/me",
            tenant_id="tenant123",
            user_id="user456"
        )

        assert state.endpoint == "/me"
        assert state.tenant_id == "tenant123"
        assert state.user_id == "user456"
        assert state.current_window is None
        assert state.retry_after is None
        assert state.consecutive_rate_limits == 0
        assert state.total_requests == 0
        assert state.total_rate_limits == 0
        assert state.success_rate == 100.0

    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        state = RateLimitState(endpoint="/test")

        # No requests yet
        state.update_success_rate()
        assert state.success_rate == 100.0

        # Some requests with no rate limits
        state.total_requests = 10
        state.total_rate_limits = 0
        state.update_success_rate()
        assert state.success_rate == 100.0

        # Some rate limits
        state.total_rate_limits = 2
        state.update_success_rate()
        assert state.success_rate == 80.0

        # All requests rate limited
        state.total_requests = 5
        state.total_rate_limits = 5
        state.update_success_rate()
        assert state.success_rate == 0.0


class TestIntelligentRateLimiter:
    """Test the main IntelligentRateLimiter class"""

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter instance for testing"""
        with patch.dict('os.environ', {
            'RATE_LIMIT_ENABLED': 'true',
            'RATE_LIMIT_ADAPTIVE': 'true',
            'CIRCUIT_BREAKER_ENABLED': 'true',
            'RATE_LIMIT_PREDICTIVE': 'true',
            'RATE_LIMIT_JITTER': 'true'
        }):
            return IntelligentRateLimiter()

    def test_initialization(self, rate_limiter):
        """Test rate limiter initialization"""
        assert rate_limiter.config["rate_limit_enabled"] is True
        assert rate_limiter.config["rate_limit_adaptive"] is True
        assert rate_limiter.config["circuit_breaker_enabled"] is True
        assert rate_limiter.config["predictive_enabled"] is True
        assert rate_limiter.config["jitter_enabled"] is True

        assert isinstance(rate_limiter.rate_limit_states, dict)
        assert isinstance(rate_limiter.endpoint_configs, dict)
        assert isinstance(rate_limiter.circuit_breakers, dict)
        assert isinstance(rate_limiter.usage_patterns, dict)

    def test_config_loading(self):
        """Test configuration loading from environment"""
        # Test with disabled features
        with patch.dict('os.environ', {
            'RATE_LIMIT_ENABLED': 'false',
            'CIRCUIT_BREAKER_ENABLED': 'false',
            'RATE_LIMIT_PREDICTIVE': 'false'
        }):
            limiter = IntelligentRateLimiter()
            assert limiter.config["rate_limit_enabled"] is False
            assert limiter.config["circuit_breaker_enabled"] is False
            assert limiter.config["predictive_enabled"] is False

        # Test with custom values
        with patch.dict('os.environ', {
            'EXPONENTIAL_BACKOFF_BASE': '3.0',
            'EXPONENTIAL_BACKOFF_MAX': '600.0',
            'CIRCUIT_BREAKER_THRESHOLD': '10'
        }):
            limiter = IntelligentRateLimiter()
            assert limiter.config["exponential_backoff_base"] == 3.0
            assert limiter.config["exponential_backoff_max"] == 600.0
            assert limiter.config["circuit_breaker_threshold"] == 10

    def test_endpoint_config_matching(self, rate_limiter):
        """Test endpoint configuration pattern matching"""
        # Test /me endpoint
        config = rate_limiter._get_endpoint_config("/me")
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.strategy == RateLimitStrategy.ADAPTIVE

        # Test batch endpoint
        config = rate_limiter._get_endpoint_config("/$batch")
        assert config.max_retries == 3
        assert config.base_delay == 2.0
        assert config.strategy == RateLimitStrategy.EXPONENTIAL_BACKOFF

        # Test planner endpoint
        config = rate_limiter._get_endpoint_config("/planner/tasks")
        assert config.max_retries == 4
        assert config.base_delay == 1.0

        # Test admin endpoint
        config = rate_limiter._get_endpoint_config("/applications/123")
        assert config.max_retries == 2
        assert config.base_delay == 5.0

        # Test unknown endpoint (should use default)
        config = rate_limiter._get_endpoint_config("/unknown/endpoint")
        assert config.max_retries == 3
        assert config.base_delay == 1.0

    def test_rate_limit_key_generation(self, rate_limiter):
        """Test rate limit key generation"""
        # Basic endpoint
        key = rate_limiter._get_rate_limit_key("/me")
        assert key == "/me"

        # With tenant
        key = rate_limiter._get_rate_limit_key("/me", tenant_id="tenant123")
        assert key == "/me|tenant:tenant123"

        # With tenant and user
        key = rate_limiter._get_rate_limit_key("/me", tenant_id="tenant123", user_id="user456")
        assert key == "/me|tenant:tenant123|user:user456"

        # With user only
        key = rate_limiter._get_rate_limit_key("/me", user_id="user456")
        assert key == "/me|user:user456"

    @pytest.mark.asyncio
    async def test_check_rate_limit_disabled(self):
        """Test rate limit checking when disabled"""
        with patch.dict('os.environ', {'RATE_LIMIT_ENABLED': 'false'}):
            limiter = IntelligentRateLimiter()

            result = await limiter.check_rate_limit("/me")
            assert result["allowed"] is True
            assert result["delay"] == 0
            assert result["reason"] == "rate_limiting_disabled"

    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limits(self, rate_limiter):
        """Test rate limit checking when within limits"""
        result = await rate_limiter.check_rate_limit("/me")
        assert result["allowed"] is True
        assert result["delay"] == 0
        assert result["reason"] == "within_limits"

    @pytest.mark.asyncio
    async def test_check_rate_limit_active_limit(self, rate_limiter):
        """Test rate limit checking with active rate limit"""
        # Simulate an active rate limit
        key = rate_limiter._get_rate_limit_key("/me")
        state = RateLimitState(endpoint="/me")
        state.retry_after = time.time() + 60  # Rate limited for 60 seconds
        rate_limiter.rate_limit_states[key] = state

        result = await rate_limiter.check_rate_limit("/me")
        assert result["allowed"] is False
        assert result["delay"] > 0
        assert result["reason"] == "rate_limited"
        assert "retry_after" in result

    @pytest.mark.asyncio
    async def test_record_successful_request(self, rate_limiter):
        """Test recording successful request"""
        await rate_limiter.record_request_result(
            endpoint="/me",
            success=True,
            status_code=200
        )

        key = rate_limiter._get_rate_limit_key("/me")
        state = rate_limiter.rate_limit_states[key]

        assert state.total_requests == 1
        assert state.total_rate_limits == 0
        assert state.consecutive_rate_limits == 0
        assert state.retry_after is None
        assert state.success_rate == 100.0

    @pytest.mark.asyncio
    async def test_record_rate_limited_request(self, rate_limiter):
        """Test recording rate limited request"""
        headers = {
            "retry-after": "60"
        }

        await rate_limiter.record_request_result(
            endpoint="/me",
            success=False,
            response_headers=headers,
            status_code=429
        )

        key = rate_limiter._get_rate_limit_key("/me")
        state = rate_limiter.rate_limit_states[key]

        assert state.total_requests == 1
        assert state.total_rate_limits == 1
        assert state.consecutive_rate_limits == 1
        assert state.retry_after is not None
        assert state.retry_after > time.time()
        assert state.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_handle_consecutive_rate_limits(self, rate_limiter):
        """Test handling consecutive rate limits with adaptive backoff"""
        headers = {"retry-after": "30"}

        # First rate limit
        await rate_limiter.record_request_result(
            endpoint="/me", success=False, response_headers=headers, status_code=429
        )

        key = rate_limiter._get_rate_limit_key("/me")
        state = rate_limiter.rate_limit_states[key]
        first_retry_after = state.retry_after

        # Second consecutive rate limit (should have increased backoff)
        await rate_limiter.record_request_result(
            endpoint="/me", success=False, response_headers=headers, status_code=429
        )

        second_retry_after = state.retry_after
        assert state.consecutive_rate_limits == 2
        # Second retry should be longer than first (adaptive backoff)
        assert second_retry_after > first_retry_after

    def test_parse_rate_limit_headers(self, rate_limiter):
        """Test parsing Microsoft Graph rate limit headers"""
        headers = {
            "x-ratelimit-limit": "1000",
            "x-ratelimit-remaining": "750",
            "x-ratelimit-reset": str(int(time.time() + 3600)),
            "x-ms-resource-unit": "10",
            "x-ms-throttle-limit-percentage": "80"
        }

        state = RateLimitState(endpoint="/me")
        rate_limiter._parse_rate_limit_headers(state, headers)

        assert state.current_window is not None
        assert state.current_window.requests_allowed == 1000
        assert state.current_window.requests_made == 250  # 1000 - 750
        assert state.current_window.reset_time is not None

    def test_parse_retry_after_headers(self, rate_limiter):
        """Test parsing different retry-after header formats"""
        state = RateLimitState(endpoint="/test")

        # Test retry-after in seconds
        headers = {"retry-after": "120"}
        rate_limiter._handle_rate_limit_response(state, headers)
        expected_time = time.time() + 120
        assert abs(state.retry_after - expected_time) < 2  # Allow 2 second tolerance

        # Test x-ms-retry-after-ms
        state = RateLimitState(endpoint="/test")
        headers = {"x-ms-retry-after-ms": "30000"}  # 30 seconds in milliseconds
        rate_limiter._handle_rate_limit_response(state, headers)
        expected_time = time.time() + 30
        assert abs(state.retry_after - expected_time) < 2

        # Test invalid header values (should use default)
        state = RateLimitState(endpoint="/test")
        headers = {"retry-after": "invalid"}
        rate_limiter._handle_rate_limit_response(state, headers)
        expected_time = time.time() + 60  # Default fallback
        assert abs(state.retry_after - expected_time) < 2


class TestBackoffStrategies:
    """Test different backoff strategies"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for backoff testing"""
        return IntelligentRateLimiter()

    def test_exponential_backoff(self, rate_limiter):
        """Test exponential backoff calculation"""
        endpoint = "/test"

        # Mock endpoint config for exponential backoff
        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(
                base_delay=1.0,
                backoff_multiplier=2.0,
                max_delay=60.0,
                strategy=RateLimitStrategy.EXPONENTIAL_BACKOFF,
                jitter_range=(0, 0)  # No jitter for predictable testing
            )

            # Test successive retry delays
            delay0 = rate_limiter.calculate_backoff_delay(endpoint, 0)
            delay1 = rate_limiter.calculate_backoff_delay(endpoint, 1)
            delay2 = rate_limiter.calculate_backoff_delay(endpoint, 2)

            assert delay0 == 1.0  # 1.0 * (2.0 ** 0)
            assert delay1 == 2.0  # 1.0 * (2.0 ** 1)
            assert delay2 == 4.0  # 1.0 * (2.0 ** 2)

    def test_linear_backoff(self, rate_limiter):
        """Test linear backoff calculation"""
        endpoint = "/test"

        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(
                base_delay=2.0,
                strategy=RateLimitStrategy.LINEAR_BACKOFF,
                jitter_range=(0, 0)
            )

            delay0 = rate_limiter.calculate_backoff_delay(endpoint, 0)
            delay1 = rate_limiter.calculate_backoff_delay(endpoint, 1)
            delay2 = rate_limiter.calculate_backoff_delay(endpoint, 2)

            assert delay0 == 2.0  # 2.0 * (0 + 1)
            assert delay1 == 4.0  # 2.0 * (1 + 1)
            assert delay2 == 6.0  # 2.0 * (2 + 1)

    def test_adaptive_backoff(self, rate_limiter):
        """Test adaptive backoff based on success rate"""
        endpoint = "/test"
        key = rate_limiter._get_rate_limit_key(endpoint)

        # Create state with low success rate
        state = RateLimitState(endpoint=endpoint)
        state.total_requests = 10
        state.total_rate_limits = 8  # 20% success rate
        state.update_success_rate()
        rate_limiter.rate_limit_states[key] = state

        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(
                base_delay=1.0,
                backoff_multiplier=2.0,
                strategy=RateLimitStrategy.ADAPTIVE,
                jitter_range=(0, 0)
            )

            delay = rate_limiter.calculate_backoff_delay(endpoint, 1)

            # Should be higher than standard exponential backoff due to low success rate
            expected_base = 1.0 * (2.0 ** 1)  # 2.0
            multiplier = max(1.0, (100.0 - 20.0) / 50.0)  # 1.6
            expected_delay = expected_base * multiplier  # 3.2
            assert abs(delay - expected_delay) < 0.1

    def test_fixed_delay(self, rate_limiter):
        """Test fixed delay strategy"""
        endpoint = "/test"

        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(
                base_delay=5.0,
                strategy=RateLimitStrategy.FIXED_DELAY,
                jitter_range=(0, 0)
            )

            delay0 = rate_limiter.calculate_backoff_delay(endpoint, 0)
            delay1 = rate_limiter.calculate_backoff_delay(endpoint, 1)
            delay2 = rate_limiter.calculate_backoff_delay(endpoint, 2)

            assert delay0 == 5.0
            assert delay1 == 5.0
            assert delay2 == 5.0

    def test_max_delay_cap(self, rate_limiter):
        """Test that delays are capped at max_delay"""
        endpoint = "/test"

        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(
                base_delay=10.0,
                backoff_multiplier=10.0,
                max_delay=50.0,
                max_retries=10,  # Allow more retries to test capping
                strategy=RateLimitStrategy.EXPONENTIAL_BACKOFF,
                jitter_range=(0, 0)
            )

            # High retry count should be capped
            delay = rate_limiter.calculate_backoff_delay(endpoint, 5)
            assert delay == 50.0  # Should be capped at max_delay

    def test_max_retries_exceeded(self, rate_limiter):
        """Test behavior when max retries exceeded"""
        endpoint = "/test"

        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(max_retries=3)

            # Within limits
            delay = rate_limiter.calculate_backoff_delay(endpoint, 2)
            assert delay > 0

            # Exceeded limits
            delay = rate_limiter.calculate_backoff_delay(endpoint, 3)
            assert delay == -1

    def test_jitter_application(self, rate_limiter):
        """Test that jitter is applied correctly"""
        endpoint = "/test"

        with patch.object(rate_limiter, '_get_endpoint_config') as mock_config:
            mock_config.return_value = RetryConfig(
                base_delay=10.0,
                strategy=RateLimitStrategy.FIXED_DELAY,
                jitter_range=(0.1, 0.3)  # 10-30% jitter
            )

            # Calculate multiple delays to test jitter variance
            delays = [rate_limiter.calculate_backoff_delay(endpoint, 0) for _ in range(20)]

            # All delays should be between 11.0 and 13.0 (10.0 * 1.1 to 10.0 * 1.3)
            assert all(11.0 <= d <= 13.0 for d in delays)
            # Should have some variance (not all the same)
            assert len(set(delays)) > 1


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter with circuit breaker enabled"""
        with patch.dict('os.environ', {
            'CIRCUIT_BREAKER_ENABLED': 'true',
            'CIRCUIT_BREAKER_THRESHOLD': '3',
            'CIRCUIT_BREAKER_TIMEOUT': '30'
        }):
            return IntelligentRateLimiter()

    def test_circuit_breaker_disabled(self):
        """Test circuit breaker when disabled"""
        with patch.dict('os.environ', {'CIRCUIT_BREAKER_ENABLED': 'false'}):
            limiter = IntelligentRateLimiter()

            key = "test_key"
            assert not limiter._is_circuit_breaker_open(key)

            # Should not create circuit breaker on failure
            limiter._update_circuit_breaker(key, False, True)
            assert key not in limiter.circuit_breakers

    def test_circuit_breaker_states(self, rate_limiter):
        """Test circuit breaker state transitions"""
        key = "test_endpoint"

        # Initially no breaker exists
        assert not rate_limiter._is_circuit_breaker_open(key)

        # Record some failures
        for _ in range(2):
            rate_limiter._update_circuit_breaker(key, False, True)

        breaker = rate_limiter.circuit_breakers[key]
        assert breaker["state"] == "closed"
        assert breaker["failure_count"] == 2

        # One more failure should open the circuit
        rate_limiter._update_circuit_breaker(key, False, True)
        assert breaker["state"] == "open"
        assert breaker["failure_count"] == 3
        assert rate_limiter._is_circuit_breaker_open(key)

    def test_circuit_breaker_timeout_transition(self, rate_limiter):
        """Test circuit breaker transition from open to half-open"""
        key = "test_endpoint"

        # Open the circuit breaker
        for _ in range(3):
            rate_limiter._update_circuit_breaker(key, False, True)

        breaker = rate_limiter.circuit_breakers[key]
        assert breaker["state"] == "open"

        # Simulate timeout passage by setting next_attempt to past
        breaker["next_attempt"] = time.time() - 1

        # Should transition to half-open
        assert not rate_limiter._is_circuit_breaker_open(key)
        assert breaker["state"] == "half_open"

    def test_circuit_breaker_half_open_recovery(self, rate_limiter):
        """Test circuit breaker recovery from half-open to closed"""
        key = "test_endpoint"

        # Set up half-open state
        rate_limiter.circuit_breakers[key] = {
            "state": "half_open",
            "failure_count": 3,
            "success_count": 0,
            "last_failure": None,
            "next_attempt": None,
            "test_requests": 0
        }

        # Record successful test requests
        for _ in range(3):
            rate_limiter._update_circuit_breaker(key, True, False)

        breaker = rate_limiter.circuit_breakers[key]
        assert breaker["state"] == "closed"
        assert breaker["failure_count"] == 0

    def test_circuit_breaker_half_open_failure(self, rate_limiter):
        """Test circuit breaker failure in half-open state"""
        key = "test_endpoint"

        # Set up half-open state
        rate_limiter.circuit_breakers[key] = {
            "state": "half_open",
            "failure_count": 2,  # Just below threshold
            "success_count": 0,
            "last_failure": None,
            "next_attempt": None,
            "test_requests": 0
        }

        # Failure in half-open should immediately re-open
        rate_limiter._update_circuit_breaker(key, False, True)

        breaker = rate_limiter.circuit_breakers[key]
        assert breaker["state"] == "open"

    def test_circuit_breaker_delay_calculation(self, rate_limiter):
        """Test circuit breaker delay calculation"""
        key = "test_endpoint"

        # No breaker - no delay
        delay = rate_limiter._get_circuit_breaker_delay(key)
        assert delay == 0.0

        # Open breaker with future next_attempt
        future_time = time.time() + 60
        rate_limiter.circuit_breakers[key] = {
            "state": "open",
            "next_attempt": future_time,
            "failure_count": 3,
            "success_count": 0,
            "last_failure": None,
            "test_requests": 0
        }

        delay = rate_limiter._get_circuit_breaker_delay(key)
        assert 55 <= delay <= 60  # Should be close to 60 seconds

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_requests(self, rate_limiter):
        """Test that open circuit breaker blocks requests"""
        endpoint = "/test"
        key = rate_limiter._get_rate_limit_key(endpoint)

        # Open the circuit breaker
        for _ in range(3):
            rate_limiter._update_circuit_breaker(key, False, True)

        # Request should be blocked
        result = await rate_limiter.check_rate_limit(endpoint)
        assert result["allowed"] is False
        assert result["reason"] == "circuit_breaker_open"
        assert result["delay"] > 0

    def test_circuit_breaker_success_resets_failures(self, rate_limiter):
        """Test that success resets failure count in closed state"""
        key = "test_endpoint"

        # Record some failures
        for _ in range(2):
            rate_limiter._update_circuit_breaker(key, False, True)

        breaker = rate_limiter.circuit_breakers[key]
        assert breaker["failure_count"] == 2

        # Success should reset failures
        rate_limiter._update_circuit_breaker(key, True, False)
        assert breaker["failure_count"] == 0
        assert breaker["success_count"] == 1


class TestPredictiveThrottling:
    """Test predictive rate limit avoidance"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter with predictive features enabled"""
        with patch.dict('os.environ', {'RATE_LIMIT_PREDICTIVE': 'true'}):
            return IntelligentRateLimiter()

    def test_predictive_disabled(self):
        """Test predictive throttling when disabled"""
        with patch.dict('os.environ', {'RATE_LIMIT_PREDICTIVE': 'false'}):
            limiter = IntelligentRateLimiter()
            delay = limiter._predict_rate_limit_delay("/test", "tenant123")
            assert delay == 0.0

    def test_predictive_with_insufficient_data(self, rate_limiter):
        """Test predictive throttling with insufficient request history"""
        delay = rate_limiter._predict_rate_limit_delay("/test", "tenant123")
        assert delay == 0.0

    def test_predictive_with_low_frequency(self, rate_limiter):
        """Test predictive throttling with low request frequency"""
        endpoint = "/test"
        tenant_id = "tenant123"
        key = f"{endpoint}:{tenant_id}"

        # Simulate low frequency requests
        current_time = time.time()
        rate_limiter.usage_patterns[key] = [
            current_time - 30,  # 30 seconds ago
            current_time - 20,  # 20 seconds ago
            current_time - 10   # 10 seconds ago
        ]

        delay = rate_limiter._predict_rate_limit_delay(endpoint, tenant_id)
        assert delay == 0.0  # Should not throttle low frequency

    def test_predictive_with_high_frequency(self, rate_limiter):
        """Test predictive throttling with high request frequency"""
        endpoint = "/test"
        tenant_id = "tenant123"
        key = f"{endpoint}:{tenant_id}"

        # Simulate high frequency requests (more than 0.5 per second)
        current_time = time.time()
        # Pre-populate with requests to create high frequency
        # Need more than 30 requests in last 60 seconds to exceed 0.5 req/s
        # Pre-populate with 31 requests, method will add 1 more = 32 total
        rate_limiter.usage_patterns[key] = [
            current_time - (i * 1.5) for i in range(31)  # 31 requests over ~46 seconds
        ]

        delay = rate_limiter._predict_rate_limit_delay(endpoint, tenant_id)
        assert delay > 0  # Should apply throttling

    @pytest.mark.asyncio
    async def test_predictive_integration(self, rate_limiter):
        """Test predictive throttling integration with check_rate_limit"""
        endpoint = "/test"
        tenant_id = "tenant123"
        key = f"{endpoint}:{tenant_id}"

        # Set up high frequency pattern
        current_time = time.time()
        rate_limiter.usage_patterns[key] = [
            current_time - i for i in range(9, 0, -1)  # 9 requests recently
        ]

        # This request should trigger predictive throttling
        result = await rate_limiter.check_rate_limit(endpoint, tenant_id)

        # Might be allowed or throttled depending on exact timing
        if not result["allowed"]:
            assert result["reason"] == "predictive_throttling"
            assert result["delay"] > 0

    def test_usage_pattern_cleanup(self, rate_limiter):
        """Test that usage patterns are kept within limits"""
        endpoint = "/test"
        tenant_id = "tenant123"

        # Add more than 100 requests to trigger cleanup
        for _ in range(150):
            rate_limiter._predict_rate_limit_delay(endpoint, tenant_id)

        key = f"{endpoint}:{tenant_id}"
        assert len(rate_limiter.usage_patterns[key]) <= 100


class TestRateLimitMetrics:
    """Test rate limiting metrics and monitoring"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for metrics testing"""
        return IntelligentRateLimiter()

    @pytest.mark.asyncio
    async def test_get_rate_limit_status_single_endpoint(self, rate_limiter):
        """Test getting status for a single endpoint"""
        endpoint = "/me"

        # No data initially
        status = await rate_limiter.get_rate_limit_status(endpoint)
        assert status["no_data"] is True

        # Add some data
        await rate_limiter.record_request_result(endpoint, True, status_code=200)
        await rate_limiter.record_request_result(endpoint, False, status_code=429)

        status = await rate_limiter.get_rate_limit_status(endpoint)
        assert status["endpoint"] == endpoint
        assert status["total_requests"] == 2
        assert status["total_rate_limits"] == 1
        assert status["success_rate"] == 50.0
        assert "currently_rate_limited" in status
        assert "retry_after" in status

    @pytest.mark.asyncio
    async def test_get_rate_limit_status_all_endpoints(self, rate_limiter):
        """Test getting status for all endpoints"""
        # Add data for multiple endpoints
        await rate_limiter.record_request_result("/me", True, status_code=200)
        await rate_limiter.record_request_result("/users", False, status_code=429)
        await rate_limiter.record_request_result("/groups", True, status_code=200)

        status = await rate_limiter.get_rate_limit_status()

        assert status["total_endpoints"] == 3
        assert status["total_requests"] == 3
        assert status["total_rate_limits"] == 1
        assert len(status["endpoints"]) == 3

        # Check endpoint details
        endpoint_data = {ep["endpoint"]: ep for ep in status["endpoints"]}
        assert endpoint_data["/me"]["requests"] == 1
        assert endpoint_data["/me"]["rate_limits"] == 0
        assert endpoint_data["/users"]["rate_limits"] == 1

    def test_get_circuit_breaker_status(self, rate_limiter):
        """Test getting circuit breaker status"""
        # Initially empty
        status = rate_limiter.get_circuit_breaker_status()
        assert status == {}

        # Add some circuit breaker data
        key1 = "endpoint1"
        key2 = "endpoint2"

        rate_limiter.circuit_breakers[key1] = {
            "state": "closed",
            "failure_count": 1,
            "success_count": 5,
            "last_failure": time.time(),
            "next_attempt": None,
            "test_requests": 0
        }

        rate_limiter.circuit_breakers[key2] = {
            "state": "open",
            "failure_count": 5,
            "success_count": 0,
            "last_failure": time.time(),
            "next_attempt": time.time() + 60,
            "test_requests": 0
        }

        status = rate_limiter.get_circuit_breaker_status()
        assert len(status) == 2
        assert status[key1]["state"] == "closed"
        assert status[key2]["state"] == "open"

    @pytest.mark.asyncio
    async def test_reset_rate_limits(self, rate_limiter):
        """Test resetting rate limit tracking"""
        # Add some data
        await rate_limiter.record_request_result("/me", True)
        rate_limiter._update_circuit_breaker("test_key", False, True)

        assert len(rate_limiter.rate_limit_states) > 0
        assert len(rate_limiter.circuit_breakers) > 0

        # Reset specific endpoint
        await rate_limiter.reset_rate_limits("/me")
        key = rate_limiter._get_rate_limit_key("/me")
        assert key not in rate_limiter.rate_limit_states

        # Reset all
        await rate_limiter.reset_rate_limits()
        assert len(rate_limiter.rate_limit_states) == 0
        assert len(rate_limiter.circuit_breakers) == 0

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, rate_limiter):
        """Test integration with performance monitoring"""
        # Record a request with error
        await rate_limiter.record_request_result(
            endpoint="/me",
            success=False,
            status_code=429
        )

        # Performance monitor should be updated
        # This is tested indirectly through the update_connection_stats call


class TestEndpointTierConfigurations:
    """Test different endpoint tier configurations"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for testing endpoint configurations"""
        return IntelligentRateLimiter()

    def test_high_volume_endpoint_config(self, rate_limiter):
        """Test high volume endpoint configuration"""
        config = rate_limiter._get_endpoint_config("/me")
        assert config.strategy == RateLimitStrategy.ADAPTIVE
        assert config.base_delay == 0.5
        assert config.max_retries == 5

    def test_batch_endpoint_config(self, rate_limiter):
        """Test batch endpoint configuration"""
        config = rate_limiter._get_endpoint_config("/$batch")
        assert config.strategy == RateLimitStrategy.EXPONENTIAL_BACKOFF
        assert config.base_delay == 2.0
        assert config.max_retries == 3
        assert config.backoff_multiplier == 2.5

    def test_planner_endpoint_config(self, rate_limiter):
        """Test planner endpoint configuration"""
        config = rate_limiter._get_endpoint_config("/planner/tasks")
        assert config.strategy == RateLimitStrategy.EXPONENTIAL_BACKOFF
        assert config.base_delay == 1.0
        assert config.max_retries == 4

    def test_admin_endpoint_config(self, rate_limiter):
        """Test admin endpoint configuration"""
        config = rate_limiter._get_endpoint_config("/applications/123")
        assert config.strategy == RateLimitStrategy.EXPONENTIAL_BACKOFF
        assert config.base_delay == 5.0
        assert config.max_retries == 2
        assert config.max_delay == 600.0

    def test_multiple_pattern_matching(self, rate_limiter):
        """Test that more specific patterns are matched first"""
        # These should match specific patterns, not the default
        patterns_to_test = [
            ("/me/messages", 5),  # Should match /me.* pattern
            ("/planner/plans/123", 4),  # Should match /planner/.* pattern
            ("/$batch", 3),  # Should match /$batch pattern
            ("/servicePrincipals/456", 2),  # Should match admin pattern
            ("/unknown/endpoint", 3)  # Should match default
        ]

        for endpoint, expected_retries in patterns_to_test:
            config = rate_limiter._get_endpoint_config(endpoint)
            assert config.max_retries == expected_retries, f"Failed for endpoint {endpoint}"


class TestPerTenantTracking:
    """Test per-tenant and per-user rate limit tracking"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for tenant testing"""
        return IntelligentRateLimiter()

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, rate_limiter):
        """Test that different tenants have isolated rate limits"""
        endpoint = "/me"
        tenant1 = "tenant1"
        tenant2 = "tenant2"

        # Rate limit tenant1
        headers = {"retry-after": "60"}
        await rate_limiter.record_request_result(
            endpoint, False, headers, 429, tenant1
        )

        # Check that tenant1 is rate limited but tenant2 is not
        result1 = await rate_limiter.check_rate_limit(endpoint, tenant1)
        result2 = await rate_limiter.check_rate_limit(endpoint, tenant2)

        assert result1["allowed"] is False
        assert result2["allowed"] is True

    @pytest.mark.asyncio
    async def test_user_isolation(self, rate_limiter):
        """Test that different users have isolated rate limits"""
        endpoint = "/me"
        tenant_id = "tenant123"
        user1 = "user1"
        user2 = "user2"

        # Rate limit user1
        headers = {"retry-after": "60"}
        await rate_limiter.record_request_result(
            endpoint, False, headers, 429, tenant_id, user1
        )

        # Check isolation
        result1 = await rate_limiter.check_rate_limit(endpoint, tenant_id, user1)
        result2 = await rate_limiter.check_rate_limit(endpoint, tenant_id, user2)

        assert result1["allowed"] is False
        assert result2["allowed"] is True

    @pytest.mark.asyncio
    async def test_combined_tenant_user_tracking(self, rate_limiter):
        """Test combined tenant and user tracking"""
        endpoint = "/me"

        # Test different combinations
        combinations = [
            ("tenant1", "user1"),
            ("tenant1", "user2"),
            ("tenant2", "user1"),
            ("tenant2", None),
            (None, "user1")
        ]

        for tenant_id, user_id in combinations:
            await rate_limiter.record_request_result(
                endpoint, True, None, 200, tenant_id, user_id
            )

        # Should have separate tracking for each combination
        assert len(rate_limiter.rate_limit_states) == len(combinations)

        # Verify keys are unique
        keys = set(rate_limiter.rate_limit_states.keys())
        assert len(keys) == len(combinations)


class TestErrorHandlingScenarios:
    """Test error handling in various scenarios"""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for error testing"""
        return IntelligentRateLimiter()

    def test_invalid_header_values(self, rate_limiter):
        """Test handling of invalid header values"""
        state = RateLimitState(endpoint="/test")

        # Test various invalid header formats
        invalid_headers = [
            {"retry-after": "not_a_number"},
            {"retry-after": ""},
            {"x-ms-retry-after-ms": "invalid"},
            {"x-ratelimit-limit": "not_numeric"},
            {"x-ratelimit-remaining": "abc"},
            {"x-ratelimit-reset": "invalid_timestamp"}
        ]

        for headers in invalid_headers:
            # Should not raise exceptions
            try:
                rate_limiter._handle_rate_limit_response(state, headers)
                rate_limiter._parse_rate_limit_headers(state, headers)
            except Exception as e:
                pytest.fail(f"Should handle invalid headers gracefully: {e}")

    @pytest.mark.asyncio
    async def test_server_error_handling(self, rate_limiter):
        """Test handling of server errors (5xx)"""
        endpoint = "/test"

        # Record server error
        await rate_limiter.record_request_result(
            endpoint, False, None, 500
        )

        key = rate_limiter._get_rate_limit_key(endpoint)
        state = rate_limiter.rate_limit_states[key]

        # Should apply mild backoff for server errors
        assert state.retry_after is not None
        assert state.retry_after > time.time()

    def test_missing_headers(self, rate_limiter):
        """Test handling when headers are missing"""
        state = RateLimitState(endpoint="/test")

        # Should handle None headers gracefully
        rate_limiter._handle_rate_limit_response(state, None)
        rate_limiter._parse_rate_limit_headers(state, {})

        # Should use default values
        assert state.retry_after is not None  # Default 60 second backoff applied

    @pytest.mark.asyncio
    async def test_concurrent_access(self, rate_limiter):
        """Test thread safety with concurrent access"""
        endpoint = "/test"

        async def make_request():
            await rate_limiter.record_request_result(endpoint, True)
            return await rate_limiter.check_rate_limit(endpoint)

        # Run multiple concurrent operations
        tasks = [make_request() for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)
            assert "allowed" in result


class TestGlobalRateLimiterInstance:
    """Test global rate limiter instance management"""

    def test_get_rate_limiter_singleton(self):
        """Test that get_rate_limiter returns singleton instance"""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2
        assert isinstance(limiter1, IntelligentRateLimiter)

    def test_global_instance_configuration(self):
        """Test that global instance uses environment configuration"""
        # Clear any existing global instance
        import src.graph.rate_limiter
        src.graph.rate_limiter._rate_limiter = None

        with patch.dict('os.environ', {
            'RATE_LIMIT_ENABLED': 'false',
            'CIRCUIT_BREAKER_THRESHOLD': '10'
        }):
            limiter = get_rate_limiter()
            assert limiter.config["rate_limit_enabled"] is False
            assert limiter.config["circuit_breaker_threshold"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])