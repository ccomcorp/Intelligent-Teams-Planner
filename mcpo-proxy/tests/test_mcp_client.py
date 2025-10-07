"""
Tests for MCP Client integration and protocol handling
Task 1: MCP client integration (AC: 1, 5)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import httpx

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_client import MCPClient, MCPError


class TestMCPClientInitialization:
    """Test MCP client initialization and handshake"""

    @pytest.fixture
    def mcp_client(self):
        return MCPClient("http://test-mcp-server:8000")

    @pytest.mark.asyncio
    async def test_initialization_success(self, mcp_client):
        """Test successful MCP client initialization with handshake"""
        with patch.object(mcp_client, '_perform_handshake') as mock_handshake, \
             patch.object(mcp_client, '_discover_capabilities') as mock_discover, \
             patch.object(mcp_client, 'health_check') as mock_health:

            mock_handshake.return_value = None
            mock_discover.return_value = None
            mock_health.return_value = "healthy"

            await mcp_client.initialize()

            mock_handshake.assert_called_once()
            mock_discover.assert_called_once()
            mock_health.assert_called_once()
            assert mcp_client.client is not None

    @pytest.mark.asyncio
    async def test_initialization_health_check_failure(self, mcp_client):
        """Test initialization failure when health check fails"""
        with patch.object(mcp_client, '_perform_handshake'), \
             patch.object(mcp_client, '_discover_capabilities'), \
             patch.object(mcp_client, 'health_check') as mock_health:

            mock_health.return_value = "unhealthy"

            with pytest.raises(MCPError, match="health check failed"):
                await mcp_client.initialize()

    @pytest.mark.asyncio
    async def test_handshake_protocol_version(self, mcp_client):
        """Test MCP protocol handshake with version detection"""
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"protocol_version": "1.0"}
        mock_client.get.return_value = mock_response

        mcp_client.client = mock_client

        await mcp_client._perform_handshake()

        mock_client.get.assert_called_once_with("http://test-mcp-server:8000/")

    @pytest.mark.asyncio
    async def test_capability_discovery(self, mcp_client):
        """Test MCP server capability discovery"""
        with patch.object(mcp_client, 'get_capabilities') as mock_get_caps, \
             patch.object(mcp_client, 'list_tools') as mock_list_tools:

            mock_get_caps.return_value = {"version": "1.0", "features": ["tools"]}
            mock_list_tools.return_value = [
                {"name": "create_task", "description": "Create a new task"},
                {"name": "list_plans", "description": "List all plans"}
            ]

            await mcp_client._discover_capabilities()

            mock_get_caps.assert_called_once()
            mock_list_tools.assert_called_once()


class TestMCPClientReconnection:
    """Test MCP client reconnection and error recovery"""

    @pytest.fixture
    def mcp_client(self):
        client = MCPClient("http://test-mcp-server:8000")
        client.client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_connection_health_check(self, mcp_client):
        """Test connection health check functionality"""
        # Test healthy connection
        mock_response = Mock()
        mock_response.status_code = 200
        mcp_client.client.get.return_value = mock_response

        result = await mcp_client._is_connection_healthy()
        assert result is True

        # Test unhealthy connection
        mcp_client.client.get.side_effect = httpx.RequestError("Connection failed")
        result = await mcp_client._is_connection_healthy()
        assert result is False

    @pytest.mark.asyncio
    async def test_successful_reconnection(self, mcp_client):
        """Test successful reconnection after connection failure"""
        mcp_client._reconnect_attempts = 0

        with patch.object(mcp_client, '_is_connection_healthy') as mock_health:
            mock_health.return_value = True

            await mcp_client._attempt_reconnection()

            assert mcp_client._reconnect_attempts == 0
            assert mcp_client.client is not None

    @pytest.mark.asyncio
    async def test_max_reconnection_attempts(self, mcp_client):
        """Test max reconnection attempts exceeded"""
        mcp_client._reconnect_attempts = mcp_client._max_reconnect_attempts

        with pytest.raises(MCPError, match="Max reconnection attempts"):
            await mcp_client._attempt_reconnection()

    @pytest.mark.asyncio
    async def test_request_with_retry_and_recovery(self, mcp_client):
        """Test request method with automatic retry and recovery"""
        # First call fails, second succeeds after reconnection
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        mock_response.json.return_value = {"success": True}

        with patch.object(mcp_client, '_is_connection_healthy') as mock_health, \
             patch.object(mcp_client, '_attempt_reconnection') as mock_reconnect:

            # First call: unhealthy, trigger reconnection
            # Second call: healthy, proceed with request
            mock_health.side_effect = [False, True, True]
            mock_reconnect.return_value = None
            mcp_client.client.request.return_value = mock_response

            result = await mcp_client._make_request("GET", "/test")

            mock_reconnect.assert_called_once()
            assert result == {"success": True}


class TestMCPToolDiscovery:
    """Test MCP tool discovery and OpenAPI conversion"""

    @pytest.fixture
    def mcp_client(self):
        client = MCPClient("http://test-mcp-server:8000")
        client.client = AsyncMock()
        return client

    @pytest.fixture
    def sample_tools(self):
        return [
            {
                "name": "create_task",
                "description": "Create a new task",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Task title"},
                        "due_date": {"type": "string", "format": "date"}
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "list_plans",
                "description": "List all plans",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "group_id": {"type": "string"}
                    }
                }
            }
        ]

    @pytest.mark.asyncio
    async def test_list_tools_success(self, mcp_client, sample_tools):
        """Test successful tool listing from MCP server"""
        with patch.object(mcp_client, '_make_request') as mock_request:
            mock_request.return_value = sample_tools

            result = await mcp_client.list_tools()

            assert len(result) == 2
            assert result[0]["name"] == "create_task"
            assert result[1]["name"] == "list_plans"

    @pytest.mark.asyncio
    async def test_get_tool_info(self, mcp_client, sample_tools):
        """Test getting specific tool information"""
        with patch.object(mcp_client, 'list_tools') as mock_list_tools:
            mock_list_tools.return_value = sample_tools

            # Test existing tool
            result = await mcp_client.get_tool_info("create_task")
            assert result is not None
            assert result["name"] == "create_task"

            # Test non-existing tool
            result = await mcp_client.get_tool_info("nonexistent_tool")
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_tool_arguments(self, mcp_client, sample_tools):
        """Test tool argument validation against schema"""
        with patch.object(mcp_client, 'get_tool_info') as mock_get_tool:
            mock_get_tool.return_value = sample_tools[0]  # create_task tool

            # Test valid arguments
            result = await mcp_client.validate_tool_arguments(
                "create_task",
                {"title": "Test task", "due_date": "2025-12-31"}
            )
            assert result["valid"] is True

            # Test missing required argument
            result = await mcp_client.validate_tool_arguments(
                "create_task",
                {"due_date": "2025-12-31"}  # Missing required 'title'
            )
            assert result["valid"] is False
            assert "Missing required fields" in result["error"]


class TestMCPClientCapabilities:
    """Test MCP server capabilities and features"""

    @pytest.fixture
    def mcp_client(self):
        client = MCPClient("http://test-mcp-server:8000")
        client.client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_capabilities(self, mcp_client):
        """Test getting MCP server capabilities"""
        expected_capabilities = {
            "version": "1.0",
            "features": ["tools", "auth", "streaming"],
            "supported_protocols": ["http", "websocket"]
        }

        with patch.object(mcp_client, '_make_request') as mock_request:
            mock_request.return_value = expected_capabilities

            result = await mcp_client.get_capabilities()

            assert result == expected_capabilities
            mock_request.assert_called_once_with("GET", "/capabilities")

    @pytest.mark.asyncio
    async def test_get_server_info(self, mcp_client):
        """Test getting complete server information"""
        health_data = {"status": "healthy", "uptime": 12345}
        capabilities_data = {"version": "1.0", "features": ["tools"]}

        with patch.object(mcp_client, '_make_request') as mock_request, \
             patch.object(mcp_client, 'get_capabilities') as mock_capabilities:

            mock_request.return_value = health_data
            mock_capabilities.return_value = capabilities_data

            result = await mcp_client.get_server_info()

            assert result["health"] == health_data
            assert result["capabilities"] == capabilities_data
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_test_connection(self, mcp_client):
        """Test connection testing functionality"""
        with patch.object(mcp_client, 'health_check') as mock_health:
            # Test successful connection
            mock_health.return_value = "healthy"
            result = await mcp_client.test_connection()
            assert result is True

            # Test failed connection
            mock_health.return_value = "unhealthy"
            result = await mcp_client.test_connection()
            assert result is False

            # Test connection exception
            mock_health.side_effect = Exception("Connection error")
            result = await mcp_client.test_connection()
            assert result is False


class TestMCPErrorHandling:
    """Test MCP client error handling and edge cases"""

    @pytest.fixture
    def mcp_client(self):
        client = MCPClient("http://test-mcp-server:8000")
        client.client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_server_error_with_retry(self, mcp_client):
        """Test server error handling with retry logic"""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Internal server error"

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.text = '{"success": true}'
        mock_response_success.json.return_value = {"success": True}

        with patch.object(mcp_client, '_is_connection_healthy') as mock_health:
            mock_health.return_value = True
            # First call fails, second succeeds
            mcp_client.client.request.side_effect = [mock_response_fail, mock_response_success]

            result = await mcp_client._make_request("GET", "/test")
            assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_client_error_no_retry(self, mcp_client):
        """Test client error (4xx) does not trigger retry"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch.object(mcp_client, '_is_connection_healthy') as mock_health:
            mock_health.return_value = True
            mcp_client.client.request.return_value = mock_response

            with pytest.raises(MCPError, match="Client error 400"):
                await mcp_client._make_request("GET", "/test")

    @pytest.mark.asyncio
    async def test_request_timeout_with_retry(self, mcp_client):
        """Test request timeout with retry mechanism"""
        with patch.object(mcp_client, '_is_connection_healthy') as mock_health, \
             patch.object(mcp_client, '_attempt_reconnection') as mock_reconnect:

            mock_health.return_value = True
            # First calls timeout, final call succeeds
            mcp_client.client.request.side_effect = [
                httpx.RequestError("Timeout"),
                httpx.RequestError("Timeout"),
                Mock(status_code=200, text='{"success": true}', json=lambda: {"success": True})
            ]

            result = await mcp_client._make_request("GET", "/test")
            assert result == {"success": True}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])