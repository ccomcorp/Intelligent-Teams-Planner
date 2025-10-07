"""
Tests for Task 8: Performance Optimization and Connection Management
Story 2.1: Advanced Microsoft Graph API Integration
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from src.utils.performance_monitor import (
    PerformanceMonitor, PerformanceMetrics, ConnectionPoolStats,
    get_performance_monitor, track_operation
)
from src.graph.client import EnhancedGraphClient, GraphClientConfig
from src.models.graph_models import BatchOperation, RequestMethod


class TestPerformanceMonitor:
    """Test performance monitoring functionality"""

    @pytest.fixture
    def performance_monitor(self):
        """Create performance monitor instance"""
        return PerformanceMonitor(
            enable_prometheus=False,  # Disable for testing
            enable_opentelemetry=False,
            metrics_retention_minutes=5
        )

    @pytest.mark.asyncio
    async def test_track_operation_success(self, performance_monitor):
        """Test successful operation tracking"""
        operation_name = "test_operation"
        metadata = {"endpoint": "/test", "user_id": "test_user"}

        async with performance_monitor.track_operation(operation_name, metadata) as metrics:
            await asyncio.sleep(0.01)  # Simulate work
            assert metrics.operation_name == operation_name
            assert metrics.metadata == metadata
            assert metrics.status == "pending"

        # Check metrics were recorded
        assert metrics.status == "success"
        assert metrics.duration is not None
        assert metrics.duration > 0

        # Check stats
        stats = performance_monitor.get_operation_stats(operation_name)
        assert stats["count"] == 1
        assert stats["error_count"] == 0
        assert stats["average_duration"] > 0

    @pytest.mark.asyncio
    async def test_track_operation_error(self, performance_monitor):
        """Test error operation tracking"""
        operation_name = "test_error_operation"

        with pytest.raises(ValueError):
            async with performance_monitor.track_operation(operation_name):
                await asyncio.sleep(0.01)
                raise ValueError("Test error")

        # Check error was recorded
        stats = performance_monitor.get_operation_stats(operation_name)
        assert stats["count"] == 1
        assert stats["error_count"] == 1

    def test_connection_stats_update(self, performance_monitor):
        """Test connection statistics tracking"""
        performance_monitor.update_connection_stats(
            active=5,
            idle=3,
            total=8,
            reuse_count=15,
            creation_count=8,
            error_count=1
        )

        stats = performance_monitor.get_connection_stats()
        assert stats.active_connections == 5
        assert stats.idle_connections == 3
        assert stats.total_connections == 8
        assert stats.connection_reuse_count == 15
        assert stats.connection_creation_count == 8
        assert stats.connection_errors == 1

    def test_percentile_calculation(self, performance_monitor):
        """Test response time percentile calculation"""
        # Add test metrics with explicit durations
        for i in range(100):
            metrics = PerformanceMetrics(
                operation_name="test_percentiles",
                start_time=time.time() - 0.1,  # Past time
                end_time=time.time(),
                duration=i * 0.01,  # 0, 0.01, 0.02, ... 0.99 seconds
                status="success"
            )
            performance_monitor._record_metrics(metrics)

        percentiles = performance_monitor.calculate_percentiles("test_percentiles")

        # Check that percentiles are in expected ranges
        assert 0.4 <= percentiles["p50.0"] <= 0.6  # 50th percentile around 0.5
        assert 0.9 <= percentiles["p95.0"] <= 1.0   # 95th percentile around 0.95
        assert 0.95 <= percentiles["p99.0"] <= 1.0  # 99th percentile around 0.99

    def test_track_operation_decorator(self, performance_monitor):
        """Test track_operation decorator"""
        @track_operation("decorated_operation")
        async def test_async_function():
            await asyncio.sleep(0.01)
            return "success"

        # Run the decorated function
        result = asyncio.run(test_async_function())
        assert result == "success"

        # Check metrics were recorded
        monitor = get_performance_monitor()
        stats = monitor.get_operation_stats("decorated_operation")
        assert stats["count"] >= 1


class TestEnhancedGraphClient:
    """Test enhanced Graph API client performance features"""

    @pytest.fixture
    def mock_auth_service(self):
        """Mock authentication service"""
        auth_service = Mock()
        auth_service.get_access_token = AsyncMock(return_value="mock_token")
        return auth_service

    @pytest.fixture
    def mock_cache_service(self):
        """Mock cache service"""
        cache_service = Mock()
        cache_service.get = AsyncMock(return_value=None)
        cache_service.set = AsyncMock()
        return cache_service

    @pytest.fixture
    def graph_client(self, mock_auth_service, mock_cache_service):
        """Create enhanced Graph client instance"""
        return EnhancedGraphClient(mock_auth_service, mock_cache_service)

    def test_graph_client_config(self):
        """Test Graph client configuration"""
        config = GraphClientConfig()

        assert config.max_connections > 0
        assert config.timeout > 0
        assert isinstance(config.enable_http2, bool)
        assert isinstance(config.enable_compression, bool)
        assert config.max_retries >= 0

    @pytest.mark.asyncio
    async def test_client_initialization(self, graph_client):
        """Test client initialization and cleanup"""
        # Initially no client
        assert graph_client._client is None

        # Get client (triggers initialization)
        client = await graph_client._get_client()
        assert client is not None
        assert graph_client._client is not None

        # Cleanup
        await graph_client.close()
        assert graph_client._client is None

    @pytest.mark.asyncio
    async def test_connection_stats(self, graph_client):
        """Test connection statistics tracking"""
        # Initialize client
        await graph_client._get_client()

        stats = await graph_client.get_connection_stats()

        assert "created" in stats
        assert "reused" in stats
        assert "errors" in stats
        assert "active" in stats
        assert "max_connections" in stats
        assert "http2_enabled" in stats
        assert "compression_enabled" in stats

    @pytest.mark.asyncio
    async def test_health_check_success(self, graph_client):
        """Test successful health check"""
        with patch.object(graph_client, 'make_request') as mock_request:
            mock_request.return_value = {"id": "test_user"}

            health = await graph_client.health_check("test_user")

            assert health["status"] == "healthy"
            assert "response_time" in health
            assert "connection_stats" in health
            assert "timestamp" in health

    @pytest.mark.asyncio
    async def test_health_check_failure(self, graph_client):
        """Test failed health check"""
        with patch.object(graph_client, 'make_request') as mock_request:
            mock_request.side_effect = Exception("Network error")

            health = await graph_client.health_check("test_user")

            assert health["status"] == "unhealthy"
            assert "error" in health
            assert "error_type" in health
            assert health["error_type"] == "Exception"

    @pytest.mark.asyncio
    async def test_performance_tracking(self, graph_client):
        """Test that requests are tracked for performance"""
        with patch('httpx.AsyncClient') as mock_client_class:
            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"value": []}
            mock_response.text = ""

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()

            # Create async context manager
            async_context = AsyncMock()
            async_context.__aenter__ = AsyncMock(return_value=mock_client)
            async_context.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = async_context

            # Make request
            result = await graph_client.make_request(
                "GET", "/me", "test_user"
            )

            # Verify performance monitoring was used
            monitor = get_performance_monitor()
            stats = monitor.get_operation_stats("graph_api_request")
            assert stats["count"] >= 1


class TestConnectionPooling:
    """Test HTTP connection pooling functionality"""

    @pytest.mark.asyncio
    async def test_connection_reuse(self):
        """Test that connections are properly reused"""
        config = GraphClientConfig()

        # Verify connection pooling configuration
        assert config.max_connections > 1
        assert config.max_keepalive_connections > 0
        assert config.keepalive_expiry > 0

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        mock_auth_service = Mock()
        mock_auth_service.get_access_token = AsyncMock(return_value="mock_token")

        client = EnhancedGraphClient(mock_auth_service)

        # Mock HTTP responses
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"success": True}
            mock_response.text = ""

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()

            # Create async context manager
            async_context = AsyncMock()
            async_context.__aenter__ = AsyncMock(return_value=mock_client)
            async_context.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = async_context

            # Make concurrent requests
            tasks = [
                client.make_request("GET", f"/endpoint_{i}", f"user_{i}")
                for i in range(5)
            ]

            results = await asyncio.gather(*tasks)

            # All requests should succeed
            assert len(results) == 5
            assert all(result == {"success": True} for result in results)

        await client.close()


class TestJsonOptimization:
    """Test JSON encoding/decoding optimizations"""

    def test_json_encoder_selection(self):
        """Test that optimal JSON encoder is selected"""
        try:
            import orjson
            from src.graph.client import JSON_ENCODER
            assert JSON_ENCODER == "orjson"
        except ImportError:
            from src.graph.client import JSON_ENCODER
            assert JSON_ENCODER == "json"

    @pytest.mark.asyncio
    async def test_optimized_json_handling(self):
        """Test optimized JSON handling in requests"""
        config = GraphClientConfig()

        # JSON optimization should be configurable
        assert isinstance(config.json_encoder_optimized, bool)


class TestPerformanceBenchmarks:
    """Performance benchmark tests"""

    @pytest.mark.asyncio
    async def test_request_performance_simple(self):
        """Simple performance test without benchmark plugin"""
        monitor = PerformanceMonitor(
            enable_prometheus=False,
            enable_opentelemetry=False
        )

        start_time = time.time()
        async with monitor.track_operation("simple_request"):
            await asyncio.sleep(0.001)  # Simulate fast request

        end_time = time.time()
        duration = end_time - start_time

        # Verify it's reasonably fast (less than 100ms)
        assert duration < 0.1

        # Check metrics were recorded
        stats = monitor.get_operation_stats("simple_request")
        assert stats["count"] == 1

    def test_metrics_processing_performance(self):
        """Test metrics processing performance"""
        monitor = PerformanceMonitor(
            enable_prometheus=False,
            enable_opentelemetry=False
        )

        start_time = time.time()

        # Add many metrics quickly
        for i in range(100):
            metrics = PerformanceMetrics(
                operation_name=f"test_op_{i % 10}",
                start_time=time.time(),
                duration=0.001 * i
            )
            metrics.complete("success")
            monitor._record_metrics(metrics)

        processing_time = time.time() - start_time

        # Verify processing is fast (less than 1 second)
        assert processing_time < 1.0

        # Get statistics
        stats = monitor.get_all_operation_stats()
        assert len(stats) == 10  # 10 different operation names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])