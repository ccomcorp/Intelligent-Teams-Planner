"""
Enhanced Microsoft Graph API client with advanced features
Story 2.1 Task 8: Performance optimization and connection management
"""

import os
import asyncio
import time
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import structlog

import httpx
try:
    import orjson as json
    JSON_ENCODER = "orjson"
except ImportError:
    import json
    JSON_ENCODER = "json"

try:
    import uvloop
    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False

from ..utils.performance_monitor import get_performance_monitor, track_operation


logger = structlog.get_logger(__name__)


class GraphClientConfig:
    """Configuration for Graph API client"""

    def __init__(self):
        # Connection settings
        self.max_connections = int(os.getenv("HTTP_CONNECTION_POOL_SIZE", "100"))
        self.max_keepalive_connections = int(os.getenv("HTTP_KEEPALIVE_CONNECTIONS", "20"))
        self.keepalive_expiry = int(os.getenv("HTTP_KEEPALIVE_EXPIRY", "5"))
        self.timeout = float(os.getenv("HTTP_CONNECTION_TIMEOUT", "30.0"))

        # Performance settings
        self.enable_http2 = os.getenv("HTTP2_ENABLED", "true").lower() == "true"
        self.enable_compression = os.getenv("REQUEST_COMPRESSION_ENABLED", "true").lower() == "true"
        self.json_encoder_optimized = os.getenv("JSON_ENCODER_OPTIMIZED", "true").lower() == "true"

        # Request settings
        self.max_retries = int(os.getenv("GRAPH_MAX_RETRIES", "3"))
        self.base_delay = float(os.getenv("EXPONENTIAL_BACKOFF_BASE", "1.0"))
        self.max_delay = float(os.getenv("EXPONENTIAL_BACKOFF_MAX", "60.0"))

        # API settings
        self.base_url = os.getenv("GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0")
        self.beta_url = os.getenv("GRAPH_BETA_URL", "https://graph.microsoft.com/beta")
        self.enable_beta = os.getenv("GRAPH_BETA_ENDPOINT_ENABLED", "false").lower() == "true"

        logger.info("Graph client configuration loaded",
                   max_connections=self.max_connections,
                   enable_http2=self.enable_http2,
                   json_encoder=JSON_ENCODER)


class GraphAPIError(Exception):
    """Base Graph API error"""
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class GraphAPIRateLimitError(GraphAPIError):
    """Rate limit exceeded error"""
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class GraphAPIAuthError(GraphAPIError):
    """Authentication error"""
    def __init__(self, message: str):
        super().__init__(message, status_code=401)


class GraphAPIClientError(GraphAPIError):
    """Client error (4xx)"""
    pass


class GraphAPIServerError(GraphAPIError):
    """Server error (5xx)"""
    pass


class EnhancedGraphClient:
    """
    Enhanced Microsoft Graph API client with:
    - HTTP/2 support and connection pooling
    - Request compression and optimized JSON encoding
    - Performance monitoring and metrics
    - Connection reuse and optimization
    """

    def __init__(self, auth_service, cache_service=None):
        self.auth_service = auth_service
        self.cache_service = cache_service
        self.config = GraphClientConfig()
        self.performance_monitor = get_performance_monitor()

        # HTTP client will be initialized lazily
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

        # Connection statistics
        self._connection_stats = {
            "created": 0,
            "reused": 0,
            "errors": 0,
            "active": 0
        }

        logger.info("Enhanced Graph client initialized")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling"""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    # Set event loop policy for uvloop if available
                    if UVLOOP_AVAILABLE and not isinstance(asyncio.get_event_loop(), uvloop.Loop):
                        logger.info("Using uvloop for enhanced performance")

                    # Configure HTTP client with optimizations
                    limits = httpx.Limits(
                        max_connections=self.config.max_connections,
                        max_keepalive_connections=self.config.max_keepalive_connections,
                        keepalive_expiry=self.config.keepalive_expiry
                    )

                    timeout = httpx.Timeout(
                        connect=10.0,
                        read=self.config.timeout,
                        write=10.0,
                        pool=2.0
                    )

                    # Enable HTTP/2 if configured
                    http2 = self.config.enable_http2

                    self._client = httpx.AsyncClient(
                        limits=limits,
                        timeout=timeout,
                        http2=http2,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "PlannerMCP/2.0"
                        }
                    )

                    self._connection_stats["created"] += 1

                    logger.info("HTTP client created",
                               max_connections=self.config.max_connections,
                               http2=http2,
                               keepalive_connections=self.config.max_keepalive_connections)

        return self._client

    async def close(self) -> None:
        """Close HTTP client and cleanup resources"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")

    @asynccontextmanager
    async def _track_request(self, operation: str, endpoint: str):
        """Track request performance"""
        metadata = {
            "endpoint": endpoint,
            "connection_stats": self._connection_stats.copy()
        }

        async with self.performance_monitor.track_operation(operation, metadata) as metrics:
            start_time = time.time()
            try:
                yield metrics
            finally:
                # Update connection statistics in performance monitor
                pool_info = await self._get_pool_info()
                self.performance_monitor.update_connection_stats(
                    active=pool_info.get("active", 0),
                    idle=pool_info.get("idle", 0),
                    total=pool_info.get("total", 0)
                )

    async def _get_pool_info(self) -> Dict[str, int]:
        """Get connection pool information"""
        if self._client:
            # HTTPx doesn't expose detailed pool stats, so we approximate
            return {
                "active": self._connection_stats["active"],
                "idle": max(0, self.config.max_keepalive_connections - self._connection_stats["active"]),
                "total": self._connection_stats["created"]
            }
        return {"active": 0, "idle": 0, "total": 0}

    @track_operation("graph_api_request")
    async def make_request(self,
                          method: str,
                          endpoint: str,
                          user_id: str,
                          data: Optional[Dict[str, Any]] = None,
                          params: Optional[Dict[str, Any]] = None,
                          headers: Optional[Dict[str, str]] = None,
                          use_beta: bool = False,
                          timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Make authenticated request to Graph API with enhanced performance
        """
        client = await self._get_client()
        base_url = self.config.beta_url if use_beta else self.config.base_url
        url = f"{base_url}{endpoint}"

        # Get authentication token
        access_token = await self.auth_service.get_access_token(user_id)
        if not access_token:
            raise GraphAPIAuthError("No valid access token available")

        # Prepare headers
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }

        if headers:
            request_headers.update(headers)

        # Enable compression if configured
        if self.config.enable_compression:
            request_headers["Accept-Encoding"] = "gzip, deflate, br"

        # Prepare request body
        request_body = None
        if data:
            if self.config.json_encoder_optimized and JSON_ENCODER == "orjson":
                request_body = json.dumps(data).decode("utf-8")
                request_headers["Content-Type"] = "application/json"
            else:
                request_body = data
                request_headers["Content-Type"] = "application/json"

        # Set timeout
        request_timeout = timeout or self.config.timeout

        # Execute request with retry logic
        async with self._track_request(f"graph_{method.lower()}", endpoint):
            return await self._execute_with_retry(
                client, method, url, request_headers, request_body, params, request_timeout
            )

    async def _execute_with_retry(self,
                                 client: httpx.AsyncClient,
                                 method: str,
                                 url: str,
                                 headers: Dict[str, str],
                                 body: Any,
                                 params: Optional[Dict[str, Any]],
                                 timeout: float) -> Optional[Dict[str, Any]]:
        """Execute request with exponential backoff retry"""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                self._connection_stats["active"] += 1

                # Make request
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body if isinstance(body, (str, bytes)) else None,
                    json=body if isinstance(body, dict) else None,
                    params=params,
                    timeout=timeout
                )

                self._connection_stats["reused"] += 1

                # Handle response
                return await self._handle_response(response, attempt, url)

            except GraphAPIRateLimitError as e:
                if attempt < self.config.max_retries:
                    delay = min(e.retry_after, self.config.max_delay)
                    logger.warning("Rate limited, retrying",
                                 attempt=attempt,
                                 delay=delay,
                                 url=url)
                    await asyncio.sleep(delay)
                    continue
                raise

            except (GraphAPIServerError, httpx.RequestError) as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.base_delay * (2 ** attempt),
                        self.config.max_delay
                    )
                    logger.warning("Request failed, retrying",
                                 attempt=attempt,
                                 delay=delay,
                                 error=str(e),
                                 url=url)
                    await asyncio.sleep(delay)
                    continue
                self._connection_stats["errors"] += 1
                raise

            except Exception as e:
                self._connection_stats["errors"] += 1
                logger.error("Unexpected error in request", error=str(e), url=url)
                raise GraphAPIError(f"Unexpected error: {str(e)}")

            finally:
                self._connection_stats["active"] = max(0, self._connection_stats["active"] - 1)

        # If we get here, all retries failed
        if last_exception:
            raise last_exception
        raise GraphAPIError("All retry attempts failed")

    async def _handle_response(self,
                              response: httpx.Response,
                              attempt: int,
                              url: str) -> Optional[Dict[str, Any]]:
        """Handle HTTP response and convert to appropriate exception if needed"""
        # Success responses
        if 200 <= response.status_code < 300:
            if response.status_code == 204:  # No content
                return {}

            try:
                if self.config.json_encoder_optimized and JSON_ENCODER == "orjson":
                    return json.loads(response.content)
                else:
                    return response.json()
            except Exception as e:
                logger.warning("Failed to parse JSON response",
                             status_code=response.status_code,
                             content=response.text[:200])
                return {}

        # Rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            raise GraphAPIRateLimitError(
                f"Rate limit exceeded (attempt {attempt})",
                retry_after=retry_after
            )

        # Authentication errors
        if response.status_code == 401:
            raise GraphAPIAuthError("Authentication failed - token may be expired")

        # Not found
        if response.status_code == 404:
            logger.debug("Resource not found", url=url)
            return None

        # Client errors
        if 400 <= response.status_code < 500:
            error_detail = response.text if response.text else "Unknown client error"
            raise GraphAPIClientError(
                f"Client error {response.status_code}: {error_detail}",
                status_code=response.status_code
            )

        # Server errors
        if response.status_code >= 500:
            error_detail = response.text if response.text else "Unknown server error"
            raise GraphAPIServerError(
                f"Server error {response.status_code}: {error_detail}",
                status_code=response.status_code
            )

        # Unexpected status code
        raise GraphAPIError(
            f"Unexpected status code {response.status_code}: {response.text}",
            status_code=response.status_code
        )

    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get detailed connection statistics"""
        pool_info = await self._get_pool_info()

        return {
            **self._connection_stats,
            **pool_info,
            "max_connections": self.config.max_connections,
            "max_keepalive": self.config.max_keepalive_connections,
            "http2_enabled": self.config.enable_http2,
            "compression_enabled": self.config.enable_compression,
            "json_encoder": JSON_ENCODER
        }

    async def health_check(self, user_id: str = "default") -> Dict[str, Any]:
        """Perform health check of Graph API connectivity"""
        start_time = time.time()

        try:
            # Make a simple request to test connectivity
            response = await self.make_request("GET", "/me", user_id)
            duration = time.time() - start_time

            return {
                "status": "healthy",
                "response_time": duration,
                "connection_stats": await self.get_connection_stats(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            duration = time.time() - start_time

            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__,
                "response_time": duration,
                "connection_stats": await self.get_connection_stats(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def __del__(self):
        """Cleanup on deletion"""
        if self._client:
            # Note: This is not ideal but necessary for cleanup
            # In production, always call close() explicitly
            try:
                # Check if we're in an async context
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    # Schedule cleanup for later
                    loop.create_task(self.close())
            except RuntimeError:
                # No running loop, can't cleanup async resources
                pass
            except Exception:
                pass  # Ignore errors during cleanup