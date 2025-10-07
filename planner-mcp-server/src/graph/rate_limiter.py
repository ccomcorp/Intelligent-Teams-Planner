"""
Intelligent rate limiting for Microsoft Graph API
Story 2.1 Task 6: Rate Limit Handling with exponential backoff, adaptive retry, and circuit breaker
"""

import os
import time
import asyncio
import random
from typing import Dict, List, Any, Optional, Callable, Union
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..utils.performance_monitor import get_performance_monitor


logger = structlog.get_logger(__name__)


class RateLimitStrategy(str, Enum):
    """Rate limiting strategies"""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    ADAPTIVE = "adaptive"
    FIXED_DELAY = "fixed_delay"


class EndpointTier(str, Enum):
    """Graph API endpoint tiers with different rate limits"""
    HIGH_VOLUME = "high_volume"      # /me, /users, basic queries
    MEDIUM_VOLUME = "medium_volume"  # /groups, /sites, complex queries
    LOW_VOLUME = "low_volume"        # /applications, admin operations
    BATCH = "batch"                  # $batch endpoints
    WEBHOOK = "webhook"              # Webhook subscriptions


@dataclass
class RateLimitWindow:
    """Rate limit tracking window"""
    window_start: datetime
    window_size_seconds: int
    requests_made: int = 0
    requests_allowed: int = 1000
    reset_time: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if rate limit window has expired"""
        return datetime.now(timezone.utc) >= (self.window_start + timedelta(seconds=self.window_size_seconds))

    def time_until_reset(self) -> float:
        """Get seconds until window resets"""
        if self.reset_time:
            return max(0, (self.reset_time - datetime.now(timezone.utc)).total_seconds())
        return max(0, self.window_size_seconds - (datetime.now(timezone.utc) - self.window_start).total_seconds())

    def can_make_request(self) -> bool:
        """Check if request can be made within limits"""
        return self.requests_made < self.requests_allowed


@dataclass
class RetryConfig:
    """Retry configuration for different scenarios"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 300.0
    backoff_multiplier: float = 2.0
    jitter_range: tuple = (0.1, 0.3)
    strategy: RateLimitStrategy = RateLimitStrategy.EXPONENTIAL_BACKOFF


@dataclass
class RateLimitState:
    """Current rate limit state for an endpoint"""
    endpoint: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    current_window: Optional[RateLimitWindow] = None
    retry_after: Optional[float] = None
    consecutive_rate_limits: int = 0
    last_rate_limit: Optional[datetime] = None
    total_requests: int = 0
    total_rate_limits: int = 0
    success_rate: float = 100.0

    def update_success_rate(self) -> None:
        """Update success rate based on rate limits"""
        if self.total_requests > 0:
            self.success_rate = ((self.total_requests - self.total_rate_limits) / self.total_requests) * 100


class IntelligentRateLimiter:
    """
    Intelligent rate limiter for Microsoft Graph API
    Features:
    - Adaptive rate limiting based on response headers
    - Exponential backoff with jitter
    - Circuit breaker for repeated failures
    - Per-endpoint and per-tenant tracking
    - Predictive rate limit avoidance
    """

    def __init__(self):
        # Configuration
        self.config = self._load_config()

        # Rate limit tracking
        self.rate_limit_states: Dict[str, RateLimitState] = {}
        self.endpoint_configs: Dict[str, RetryConfig] = self._initialize_endpoint_configs()

        # Circuit breaker tracking
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}

        # Performance monitoring
        self.performance_monitor = get_performance_monitor()

        # Predictive models
        self.usage_patterns: Dict[str, List[float]] = {}

        logger.info("Intelligent rate limiter initialized",
                   default_strategy=self.config["default_strategy"],
                   circuit_breaker_enabled=self.config["circuit_breaker_enabled"])

    def _load_config(self) -> Dict[str, Any]:
        """Load rate limiter configuration"""
        return {
            "rate_limit_enabled": os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
            "rate_limit_adaptive": os.getenv("RATE_LIMIT_ADAPTIVE", "true").lower() == "true",
            "default_strategy": RateLimitStrategy(os.getenv("RATE_LIMIT_STRATEGY", "exponential_backoff")),
            "exponential_backoff_base": float(os.getenv("EXPONENTIAL_BACKOFF_BASE", "2.0")),
            "exponential_backoff_max": float(os.getenv("EXPONENTIAL_BACKOFF_MAX", "300.0")),
            "circuit_breaker_enabled": os.getenv("CIRCUIT_BREAKER_ENABLED", "true").lower() == "true",
            "circuit_breaker_threshold": int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5")),
            "circuit_breaker_timeout": int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60")),
            "predictive_enabled": os.getenv("RATE_LIMIT_PREDICTIVE", "true").lower() == "true",
            "jitter_enabled": os.getenv("RATE_LIMIT_JITTER", "true").lower() == "true"
        }

    def _initialize_endpoint_configs(self) -> Dict[str, RetryConfig]:
        """Initialize retry configurations for different endpoint patterns"""
        return {
            # High volume endpoints - more aggressive
            r"/me.*": RetryConfig(
                max_retries=5,
                base_delay=0.5,
                max_delay=60.0,
                backoff_multiplier=1.5,
                strategy=RateLimitStrategy.ADAPTIVE
            ),

            # Batch endpoints - conservative
            r"/\$batch": RetryConfig(
                max_retries=3,
                base_delay=2.0,
                max_delay=300.0,
                backoff_multiplier=2.5,
                strategy=RateLimitStrategy.EXPONENTIAL_BACKOFF
            ),

            # Planner endpoints - balanced
            r"/planner/.*": RetryConfig(
                max_retries=4,
                base_delay=1.0,
                max_delay=120.0,
                backoff_multiplier=2.0,
                strategy=RateLimitStrategy.EXPONENTIAL_BACKOFF
            ),

            # Admin endpoints - very conservative
            r"/(applications|servicePrincipals|directoryRoles)/.*": RetryConfig(
                max_retries=2,
                base_delay=5.0,
                max_delay=600.0,
                backoff_multiplier=3.0,
                strategy=RateLimitStrategy.EXPONENTIAL_BACKOFF
            ),

            # Default configuration
            "default": RetryConfig(
                max_retries=3,
                base_delay=1.0,
                max_delay=300.0,
                backoff_multiplier=2.0,
                strategy=RateLimitStrategy.EXPONENTIAL_BACKOFF
            )
        }

    def _get_endpoint_config(self, endpoint: str) -> RetryConfig:
        """Get retry configuration for endpoint"""
        for pattern, config in self.endpoint_configs.items():
            if pattern != "default":
                import re
                if re.match(pattern, endpoint):
                    return config
        return self.endpoint_configs["default"]

    def _get_rate_limit_key(self, endpoint: str, tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> str:
        """Generate unique key for rate limit tracking"""
        components = [endpoint]
        if tenant_id:
            components.append(f"tenant:{tenant_id}")
        if user_id:
            components.append(f"user:{user_id}")
        return "|".join(components)

    async def check_rate_limit(self, endpoint: str,
                              tenant_id: Optional[str] = None,
                              user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if request can be made or if rate limiting is in effect

        Returns:
            Dict with 'allowed', 'delay', 'reason' fields
        """
        if not self.config["rate_limit_enabled"]:
            return {"allowed": True, "delay": 0, "reason": "rate_limiting_disabled"}

        key = self._get_rate_limit_key(endpoint, tenant_id, user_id)

        # Check circuit breaker
        if self._is_circuit_breaker_open(key):
            return {
                "allowed": False,
                "delay": self._get_circuit_breaker_delay(key),
                "reason": "circuit_breaker_open"
            }

        # Get or create rate limit state
        if key not in self.rate_limit_states:
            self.rate_limit_states[key] = RateLimitState(
                endpoint=endpoint,
                tenant_id=tenant_id,
                user_id=user_id
            )

        state = self.rate_limit_states[key]

        # Check if currently rate limited
        if state.retry_after and state.retry_after > time.time():
            delay = state.retry_after - time.time()
            return {
                "allowed": False,
                "delay": delay,
                "reason": "rate_limited",
                "retry_after": delay
            }

        # Predictive rate limiting
        if self.config["predictive_enabled"]:
            prediction_delay = self._predict_rate_limit_delay(endpoint, tenant_id)
            if prediction_delay > 0:
                return {
                    "allowed": False,
                    "delay": prediction_delay,
                    "reason": "predictive_throttling"
                }

        return {"allowed": True, "delay": 0, "reason": "within_limits"}

    async def record_request_result(self, endpoint: str,
                                   success: bool,
                                   response_headers: Optional[Dict[str, str]] = None,
                                   status_code: Optional[int] = None,
                                   tenant_id: Optional[str] = None,
                                   user_id: Optional[str] = None) -> None:
        """Record the result of a request for rate limit tracking"""
        key = self._get_rate_limit_key(endpoint, tenant_id, user_id)

        if key not in self.rate_limit_states:
            self.rate_limit_states[key] = RateLimitState(
                endpoint=endpoint,
                tenant_id=tenant_id,
                user_id=user_id
            )

        state = self.rate_limit_states[key]
        state.total_requests += 1

        if status_code == 429:  # Rate limited
            self._handle_rate_limit_response(state, response_headers)
        elif success:
            self._handle_successful_response(state, response_headers)
        else:
            self._handle_error_response(state, status_code)

        # Update circuit breaker
        self._update_circuit_breaker(key, success, status_code == 429)

        # Update performance metrics
        self.performance_monitor.update_connection_stats(
            error_count=state.total_rate_limits if not success else None
        )

    def _handle_rate_limit_response(self, state: RateLimitState, headers: Optional[Dict[str, str]]) -> None:
        """Handle rate limit response and extract timing information"""
        state.total_rate_limits += 1
        state.consecutive_rate_limits += 1
        state.last_rate_limit = datetime.now(timezone.utc)

        # Extract retry-after header
        retry_after = 60  # Default fallback
        if headers:
            if "retry-after" in headers:
                try:
                    retry_after = int(headers["retry-after"])
                except (ValueError, TypeError):
                    pass
            elif "x-ms-retry-after-ms" in headers:
                try:
                    retry_after = int(headers["x-ms-retry-after-ms"]) / 1000
                except (ValueError, TypeError):
                    pass

        # Apply adaptive backoff for repeated rate limits
        if state.consecutive_rate_limits > 1:
            multiplier = min(2.0 ** (state.consecutive_rate_limits - 1), 8.0)
            retry_after *= multiplier

        state.retry_after = time.time() + retry_after
        state.update_success_rate()

        logger.warning("Rate limit detected",
                      endpoint=state.endpoint,
                      retry_after=retry_after,
                      consecutive_limits=state.consecutive_rate_limits,
                      success_rate=state.success_rate)

    def _handle_successful_response(self, state: RateLimitState, headers: Optional[Dict[str, str]]) -> None:
        """Handle successful response and update rate limit windows"""
        state.consecutive_rate_limits = 0
        state.retry_after = None

        # Parse rate limit headers for proactive management
        if headers and self.config["rate_limit_adaptive"]:
            self._parse_rate_limit_headers(state, headers)

        state.update_success_rate()

    def _handle_error_response(self, state: RateLimitState, status_code: Optional[int]) -> None:
        """Handle error response"""
        # For server errors, apply mild backoff to avoid overwhelming
        if status_code and 500 <= status_code < 600:
            if not state.retry_after or state.retry_after < time.time():
                backoff_delay = min(5.0 * (state.consecutive_rate_limits + 1), 60.0)
                state.retry_after = time.time() + backoff_delay

    def _parse_rate_limit_headers(self, state: RateLimitState, headers: Dict[str, str]) -> None:
        """Parse Graph API rate limit headers for proactive management"""
        # Microsoft Graph rate limit headers
        rate_limit_headers = [
            "x-ms-resource-unit",
            "x-ms-throttle-limit-percentage",
            "x-ms-throttle-scope",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset"
        ]

        rate_limit_info = {}
        for header in rate_limit_headers:
            if header in headers:
                rate_limit_info[header] = headers[header]

        # Create or update rate limit window
        if "x-ratelimit-limit" in rate_limit_info and "x-ratelimit-remaining" in rate_limit_info:
            try:
                limit = int(rate_limit_info["x-ratelimit-limit"])
                remaining = int(rate_limit_info["x-ratelimit-remaining"])

                # Create new window if needed
                if not state.current_window or state.current_window.is_expired():
                    window_size = 3600  # Default 1 hour window
                    state.current_window = RateLimitWindow(
                        window_start=datetime.now(timezone.utc),
                        window_size_seconds=window_size,
                        requests_allowed=limit
                    )

                state.current_window.requests_made = limit - remaining

                # Set reset time if available
                if "x-ratelimit-reset" in rate_limit_info:
                    try:
                        reset_timestamp = int(rate_limit_info["x-ratelimit-reset"])
                        state.current_window.reset_time = datetime.fromtimestamp(reset_timestamp, timezone.utc)
                    except (ValueError, TypeError):
                        pass

            except (ValueError, TypeError):
                pass

    def _predict_rate_limit_delay(self, endpoint: str, tenant_id: Optional[str]) -> float:
        """Predict if rate limiting is likely and return suggested delay"""
        if not self.config["predictive_enabled"]:
            return 0.0

        key = f"{endpoint}:{tenant_id or 'default'}"

        # Track usage patterns
        current_time = time.time()
        if key not in self.usage_patterns:
            self.usage_patterns[key] = []

        self.usage_patterns[key].append(current_time)

        # Keep only last 100 requests for pattern analysis
        self.usage_patterns[key] = self.usage_patterns[key][-100:]

        # Analyze request frequency
        if len(self.usage_patterns[key]) >= 10:
            recent_requests = [t for t in self.usage_patterns[key] if current_time - t < 60]  # Last minute

            if len(recent_requests) >= 8:  # High frequency detected
                # Calculate adaptive delay
                frequency = len(recent_requests) / 60.0  # requests per second
                if frequency > 0.5:  # More than 0.5 requests per second
                    suggested_delay = min(2.0 / frequency, 10.0)  # Adaptive delay
                    logger.debug("Predictive throttling applied",
                               endpoint=endpoint,
                               frequency=frequency,
                               delay=suggested_delay)
                    return suggested_delay

        return 0.0

    def calculate_backoff_delay(self, endpoint: str,
                               retry_count: int,
                               tenant_id: Optional[str] = None,
                               user_id: Optional[str] = None,
                               error_type: Optional[str] = None) -> float:
        """Calculate backoff delay for retry attempts"""
        config = self._get_endpoint_config(endpoint)

        if retry_count >= config.max_retries:
            return -1  # No more retries

        # Base delay calculation
        if config.strategy == RateLimitStrategy.EXPONENTIAL_BACKOFF:
            delay = config.base_delay * (config.backoff_multiplier ** retry_count)
        elif config.strategy == RateLimitStrategy.LINEAR_BACKOFF:
            delay = config.base_delay * (retry_count + 1)
        elif config.strategy == RateLimitStrategy.ADAPTIVE:
            # Adaptive based on recent success rate
            key = self._get_rate_limit_key(endpoint, tenant_id, user_id)
            success_rate = 100.0
            if key in self.rate_limit_states:
                success_rate = self.rate_limit_states[key].success_rate

            # More aggressive backoff for lower success rates
            multiplier = max(1.0, (100.0 - success_rate) / 50.0)
            delay = config.base_delay * (config.backoff_multiplier ** retry_count) * multiplier
        else:  # FIXED_DELAY
            delay = config.base_delay

        # Apply jitter to prevent thundering herd
        if self.config["jitter_enabled"]:
            jitter_min, jitter_max = config.jitter_range
            jitter = random.uniform(jitter_min, jitter_max)
            delay *= (1 + jitter)

        # Cap at maximum delay
        delay = min(delay, config.max_delay)

        logger.debug("Calculated backoff delay",
                    endpoint=endpoint,
                    retry_count=retry_count,
                    strategy=config.strategy,
                    delay=delay)

        return delay

    def _is_circuit_breaker_open(self, key: str) -> bool:
        """Check if circuit breaker is open for the given key"""
        if not self.config["circuit_breaker_enabled"]:
            return False

        if key not in self.circuit_breakers:
            return False

        breaker = self.circuit_breakers[key]

        if breaker["state"] == "open":
            # Check if timeout has passed
            if time.time() >= breaker["next_attempt"]:
                breaker["state"] = "half_open"
                breaker["test_requests"] = 0
                logger.info("Circuit breaker transitioning to half-open", key=key)
                return False
            return True

        return False

    def _get_circuit_breaker_delay(self, key: str) -> float:
        """Get delay until circuit breaker can be retried"""
        if key not in self.circuit_breakers:
            return 0.0

        breaker = self.circuit_breakers[key]
        if breaker["state"] == "open":
            return max(0.0, breaker["next_attempt"] - time.time())

        return 0.0

    def _update_circuit_breaker(self, key: str, success: bool, rate_limited: bool) -> None:
        """Update circuit breaker state based on request result"""
        if not self.config["circuit_breaker_enabled"]:
            return

        if key not in self.circuit_breakers:
            self.circuit_breakers[key] = {
                "state": "closed",
                "failure_count": 0,
                "success_count": 0,
                "last_failure": None,
                "next_attempt": None,
                "test_requests": 0
            }

        breaker = self.circuit_breakers[key]

        if success and not rate_limited:
            breaker["success_count"] += 1

            # Reset failure count on success (unless in half-open state testing)
            if breaker["state"] == "closed":
                breaker["failure_count"] = 0
            elif breaker["state"] == "half_open":
                breaker["test_requests"] += 1
                if breaker["test_requests"] >= 3:  # 3 successful test requests
                    breaker["state"] = "closed"
                    breaker["failure_count"] = 0
                    logger.info("Circuit breaker closed", key=key)

        else:
            breaker["failure_count"] += 1
            breaker["last_failure"] = time.time()

            # Open circuit breaker if threshold exceeded
            threshold = self.config["circuit_breaker_threshold"]
            if breaker["state"] in ["closed", "half_open"] and breaker["failure_count"] >= threshold:
                breaker["state"] = "open"
                timeout = self.config["circuit_breaker_timeout"]
                breaker["next_attempt"] = time.time() + timeout

                logger.warning("Circuit breaker opened",
                             key=key,
                             failure_count=breaker["failure_count"],
                             timeout=timeout)

    async def get_rate_limit_status(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Get current rate limit status"""
        if endpoint:
            key = self._get_rate_limit_key(endpoint)
            state = self.rate_limit_states.get(key)
            if state:
                return {
                    "endpoint": endpoint,
                    "total_requests": state.total_requests,
                    "total_rate_limits": state.total_rate_limits,
                    "success_rate": state.success_rate,
                    "consecutive_rate_limits": state.consecutive_rate_limits,
                    "currently_rate_limited": state.retry_after and state.retry_after > time.time(),
                    "retry_after": max(0, state.retry_after - time.time()) if state.retry_after else 0
                }
            return {"endpoint": endpoint, "no_data": True}

        # Return summary of all endpoints
        summary = {
            "total_endpoints": len(self.rate_limit_states),
            "total_requests": sum(s.total_requests for s in self.rate_limit_states.values()),
            "total_rate_limits": sum(s.total_rate_limits for s in self.rate_limit_states.values()),
            "endpoints": []
        }

        for key, state in self.rate_limit_states.items():
            summary["endpoints"].append({
                "endpoint": state.endpoint,
                "requests": state.total_requests,
                "rate_limits": state.total_rate_limits,
                "success_rate": state.success_rate
            })

        return summary

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get circuit breaker status for all tracked endpoints"""
        status = {}
        for key, breaker in self.circuit_breakers.items():
            status[key] = {
                "state": breaker["state"],
                "failure_count": breaker["failure_count"],
                "success_count": breaker["success_count"],
                "last_failure": breaker["last_failure"],
                "next_attempt": breaker["next_attempt"]
            }
        return status

    async def reset_rate_limits(self, endpoint: Optional[str] = None) -> None:
        """Reset rate limit tracking (for testing/debugging)"""
        if endpoint:
            key = self._get_rate_limit_key(endpoint)
            if key in self.rate_limit_states:
                del self.rate_limit_states[key]
            if key in self.circuit_breakers:
                del self.circuit_breakers[key]
        else:
            self.rate_limit_states.clear()
            self.circuit_breakers.clear()

        logger.info("Rate limits reset", endpoint=endpoint or "all")


# Global rate limiter instance
_rate_limiter: Optional[IntelligentRateLimiter] = None


def get_rate_limiter() -> IntelligentRateLimiter:
    """Get or create global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = IntelligentRateLimiter()
    return _rate_limiter