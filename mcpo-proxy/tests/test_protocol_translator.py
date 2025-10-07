"""
Tests for Protocol Translator - OpenWebUI to MCP translation
Task 2: Translate OpenWebUI tool calls to MCP method invocations
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from protocol_translator import ProtocolTranslator


class TestProtocolTranslator:
    """Test protocol translation between OpenWebUI and MCP formats"""

    @pytest.fixture
    def mock_mcp_client(self):
        client = AsyncMock()
        client.get_tool_info.return_value = {
            "name": "create_task",
            "description": "Create a new task",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "due_date": {"type": "string", "format": "date"},
                    "priority": {"type": "integer", "minimum": 1, "maximum": 5}
                },
                "required": ["title"]
            }
        }
        client.validate_tool_arguments.return_value = {"valid": True}
        return client

    @pytest.fixture
    def translator(self, mock_mcp_client):
        return ProtocolTranslator(mock_mcp_client)

    @pytest.mark.asyncio
    async def test_openwebui_to_mcp_translation(self, translator, mock_mcp_client):
        """Test successful OpenWebUI to MCP translation"""
        tool_name = "create_task"
        arguments = {
            "title": "Review quarterly reports",
            "due_date": "2025-10-15",
            "priority": 3
        }

        result = await translator.translate_openwebui_to_mcp(tool_name, arguments)

        # Verify MCP format
        assert result["jsonrpc"] == "2.0"
        assert result["method"] == "tools/call"
        assert result["params"]["name"] == tool_name
        assert result["params"]["arguments"] == arguments
        assert "id" in result
        assert result["id"].startswith("req_")

        # Verify MCP client calls
        mock_mcp_client.get_tool_info.assert_called_once_with(tool_name)
        mock_mcp_client.validate_tool_arguments.assert_called_once_with(tool_name, arguments)

    @pytest.mark.asyncio
    async def test_openwebui_to_mcp_invalid_tool(self, translator, mock_mcp_client):
        """Test translation with invalid tool name"""
        mock_mcp_client.get_tool_info.return_value = None

        with pytest.raises(ValueError, match="Tool 'invalid_tool' not found"):
            await translator.translate_openwebui_to_mcp("invalid_tool", {})

    @pytest.mark.asyncio
    async def test_openwebui_to_mcp_invalid_arguments(self, translator, mock_mcp_client):
        """Test translation with invalid arguments"""
        mock_mcp_client.validate_tool_arguments.return_value = {
            "valid": False,
            "error": "Missing required field: title"
        }

        with pytest.raises(ValueError, match="Invalid arguments"):
            await translator.translate_openwebui_to_mcp("create_task", {"priority": 1})

    def test_mcp_success_response_translation(self, translator):
        """Test MCP success response to OpenWebUI translation"""
        mcp_response = {
            "jsonrpc": "2.0",
            "result": {
                "success": True,
                "content": {
                    "id": "task_123",
                    "title": "Review quarterly reports",
                    "status": "created"
                },
                "message": "Task created successfully"
            },
            "id": "req_12345"
        }

        result = translator.translate_mcp_to_openwebui(mcp_response)

        assert result["success"] is True
        assert result["data"]["id"] == "task_123"
        assert result["message"] == "Task created successfully"
        assert result["correlation_id"] == "req_12345"
        assert "timestamp" in result["metadata"]
        assert result["metadata"]["mcp_version"] == "2.0"

    def test_mcp_error_response_translation(self, translator):
        """Test MCP error response to OpenWebUI translation"""
        mcp_response = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": {"field": "title", "issue": "required"}
            },
            "id": "req_12345"
        }

        result = translator.translate_mcp_to_openwebui(mcp_response)

        assert result["success"] is False
        assert result["error"]["type"] == "invalid_params"
        assert result["error"]["message"] == "Invalid params"
        assert result["error"]["details"] == {"field": "title", "issue": "required"}
        assert result["correlation_id"] == "req_12345"
        assert result["metadata"]["mcp_error_code"] == -32602

    def test_mcp_error_code_mapping(self, translator):
        """Test mapping of MCP error codes to OpenWebUI error types"""
        error_mappings = [
            (-32700, "parse_error"),
            (-32600, "invalid_request"),
            (-32601, "method_not_found"),
            (-32602, "invalid_params"),
            (-32603, "internal_error"),
            (-99999, "unknown_error")  # Unknown code
        ]

        for error_code, expected_type in error_mappings:
            mcp_response = {
                "jsonrpc": "2.0",
                "error": {"code": error_code, "message": "Test error"},
                "id": "test_id"
            }

            result = translator.translate_mcp_to_openwebui(mcp_response)
            assert result["error"]["type"] == expected_type

    def test_invalid_mcp_response_translation(self, translator):
        """Test handling of invalid MCP response format"""
        invalid_response = {
            "jsonrpc": "2.0",
            "id": "req_12345"
            # Missing both 'result' and 'error'
        }

        result = translator.translate_mcp_to_openwebui(invalid_response)

        assert result["success"] is False
        assert result["error"]["type"] == "translation_error"
        assert "Failed to translate MCP response" in result["error"]["message"]
        assert result["metadata"]["translation_error"] is True

    def test_convert_openapi_params_to_mcp_args(self, translator):
        """Test OpenAPI parameter conversion to MCP arguments"""
        openapi_params = {
            "title": "Test Task",
            "priority": "3",  # String that should be converted to int
            "due_date": "2025-10-15",
            "tags": "urgent,important",  # Comma-separated string to array
            "metadata": '{"key": "value"}'  # JSON string to object
        }

        tool_schema = {
            "inputSchema": {
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "integer"},
                    "due_date": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"}
                }
            }
        }

        result = translator.convert_openapi_params_to_mcp_args(openapi_params, tool_schema)

        assert result["title"] == "Test Task"
        assert result["priority"] == 3
        assert result["due_date"] == "2025-10-15"
        assert result["tags"] == ["urgent", "important"]
        assert result["metadata"] == {"key": "value"}

    def test_parameter_value_conversion(self, translator):
        """Test individual parameter value conversion"""
        # Integer conversion
        result = translator._convert_parameter_value("42", {"type": "integer"})
        assert result == 42

        # Float conversion
        result = translator._convert_parameter_value("3.14", {"type": "number"})
        assert result == 3.14

        # Boolean conversion
        result = translator._convert_parameter_value("true", {"type": "boolean"})
        assert result is True

        result = translator._convert_parameter_value("false", {"type": "boolean"})
        assert result is False

        # Array conversion from JSON
        result = translator._convert_parameter_value('["a", "b", "c"]', {"type": "array"})
        assert result == ["a", "b", "c"]

        # Array conversion from comma-separated
        result = translator._convert_parameter_value("a,b,c", {"type": "array"})
        assert result == ["a", "b", "c"]

        # Object conversion
        result = translator._convert_parameter_value('{"key": "value"}', {"type": "object"})
        assert result == {"key": "value"}

        # String (default)
        result = translator._convert_parameter_value(123, {"type": "string"})
        assert result == "123"

    @pytest.mark.asyncio
    async def test_batch_translate_tools(self, translator, mock_mcp_client):
        """Test batch translation of multiple tool calls"""
        tool_calls = [
            {"name": "create_task", "arguments": {"title": "Task 1"}},
            {"name": "create_task", "arguments": {"title": "Task 2"}},
            {"name": "list_plans", "arguments": {}}
        ]

        # Mock different tool info for list_plans
        async def mock_get_tool_info(tool_name):
            if tool_name == "list_plans":
                return {"name": "list_plans", "inputSchema": {"type": "object"}}
            return mock_mcp_client.get_tool_info.return_value

        mock_mcp_client.get_tool_info.side_effect = mock_get_tool_info

        results = await translator.batch_translate_tools(tool_calls)

        assert len(results) == 3
        for result in results:
            assert result["jsonrpc"] == "2.0"
            assert result["method"] == "tools/call"
            assert "id" in result

        # First two should be create_task
        assert results[0]["params"]["name"] == "create_task"
        assert results[1]["params"]["name"] == "create_task"
        assert results[2]["params"]["name"] == "list_plans"

    @pytest.mark.asyncio
    async def test_batch_translate_invalid_tool_call(self, translator, mock_mcp_client):
        """Test batch translation with invalid tool call"""
        tool_calls = [
            {"arguments": {"title": "Task without name"}},  # Missing name
            {"name": "valid_tool", "arguments": {"title": "Valid task"}}
        ]

        results = await translator.batch_translate_tools(tool_calls)

        # Should only return result for valid tool call
        assert len(results) == 1
        assert results[0]["params"]["name"] == "valid_tool"

    def test_request_id_generation(self, translator):
        """Test unique request ID generation"""
        id1 = translator.generate_request_id()
        id2 = translator.generate_request_id()

        assert id1 != id2
        assert id1.startswith("req_")
        assert id2.startswith("req_")

        # Should increment counter
        assert translator.request_counter == 2

    def test_translation_statistics(self, translator):
        """Test translation statistics"""
        # Generate some request IDs to increment counter
        translator.generate_request_id()
        translator.generate_request_id()

        stats = translator.get_translation_statistics()

        assert stats["total_requests"] == 2
        assert "timestamp" in stats
        assert stats["translator_version"] == "1.0.0"

    def test_parameter_conversion_edge_cases(self, translator):
        """Test parameter conversion edge cases"""
        # None values
        result = translator._convert_parameter_value(None, {"type": "string"})
        assert result is None

        # Invalid JSON for object
        result = translator._convert_parameter_value("invalid json", {"type": "object"})
        assert result == {}

        # Conversion failure fallback
        result = translator._convert_parameter_value("not_a_number", {"type": "integer"})
        # Should return original value if conversion fails
        assert result == "not_a_number"

    def test_translation_with_metadata(self, translator):
        """Test translation preserving metadata"""
        mcp_response = {
            "jsonrpc": "2.0",
            "result": {
                "success": True,
                "content": {"id": "123"},
                "metadata": {
                    "execution_time": 150,
                    "cache_hit": True
                }
            },
            "id": "req_123"
        }

        result = translator.translate_mcp_to_openwebui(mcp_response)

        assert result["success"] is True
        assert result["metadata"]["execution_time"] == 150
        assert result["metadata"]["cache_hit"] is True
        assert "timestamp" in result["metadata"]
        assert "mcp_version" in result["metadata"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])