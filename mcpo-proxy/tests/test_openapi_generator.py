"""
Tests for OpenAPI Generator - MCP tool to OpenAPI conversion
Task 1: Parse MCP tool definitions and convert to OpenAPI format
"""

import pytest
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from openapi_generator import OpenAPIGenerator


class TestOpenAPIGenerator:
    """Test OpenAPI specification generation from MCP tools"""

    @pytest.fixture
    def generator(self):
        return OpenAPIGenerator()

    @pytest.fixture
    def sample_mcp_tools(self):
        return [
            {
                "name": "create_task",
                "description": "Create a new task in Microsoft Planner",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Task title"
                        },
                        "due_date": {
                            "type": "string",
                            "format": "date",
                            "description": "Task due date"
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Task priority (1-5)",
                            "enum": [1, 2, 3, 4, 5]
                        },
                        "assigned_to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of assigned user IDs"
                        }
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "list_plans",
                "description": "List all available plans",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "group_id": {
                            "type": "string",
                            "description": "Filter by group ID"
                        }
                    }
                }
            },
            {
                "name": "authenticate_user",
                "description": "Authenticate user with Microsoft Graph",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User identifier"
                        }
                    },
                    "required": ["user_id"]
                }
            }
        ]

    def test_base_spec_structure(self, generator):
        """Test base OpenAPI specification structure"""
        base_spec = generator.base_spec

        assert base_spec["openapi"] == "3.0.3"
        assert base_spec["info"]["title"] == "MCP Tools API"
        assert "servers" in base_spec
        assert "paths" in base_spec
        assert "components" in base_spec
        assert "security" in base_spec

    def test_generate_complete_spec(self, generator, sample_mcp_tools):
        """Test generation of complete OpenAPI specification"""
        spec = generator.generate_openapi_spec(sample_mcp_tools)

        # Verify basic structure
        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["x-tool-count"] == 3
        assert "x-generated-at" in spec["info"]

        # Verify tool paths are created
        assert "/tools/create_task" in spec["paths"]
        assert "/tools/list_plans" in spec["paths"]
        assert "/tools/authenticate_user" in spec["paths"]

        # Verify common endpoints
        assert "/tools" in spec["paths"]
        assert "/health" in spec["paths"]

    def test_tool_path_generation(self, generator, sample_mcp_tools):
        """Test individual tool path generation"""
        spec = {"paths": {}, "components": {"schemas": {}}}

        # Test create_task tool
        tool = sample_mcp_tools[0]
        generator._add_tool_to_spec(spec, tool)

        path = "/tools/create_task"
        assert path in spec["paths"]

        post_spec = spec["paths"][path]["post"]
        assert post_spec["summary"] == "Create a new task in Microsoft Planner"
        assert post_spec["operationId"] == "execute_create_task"
        assert "Tasks" in post_spec["tags"]
        assert post_spec["requestBody"]["required"] is True

    def test_schema_conversion(self, generator):
        """Test MCP schema to OpenAPI schema conversion"""
        mcp_schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3, 4, 5]
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["title"]
        }

        result = generator._convert_mcp_schema_to_openapi(mcp_schema, "test_tool")

        # Should return a reference to component schema
        assert "$ref" in result
        assert result["$ref"] == "#/components/schemas/TestToolRequest"

    def test_property_conversion(self, generator):
        """Test individual property conversion"""
        # String property
        string_prop = {
            "type": "string",
            "description": "A string field",
            "format": "email"
        }
        result = generator._convert_property(string_prop)
        assert result["type"] == "string"
        assert result["description"] == "A string field"
        assert result["format"] == "email"

        # Enum property
        enum_prop = {
            "type": "string",
            "enum": ["option1", "option2", "option3"]
        }
        result = generator._convert_property(enum_prop)
        assert result["enum"] == ["option1", "option2", "option3"]

        # Array property
        array_prop = {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
        result = generator._convert_property(array_prop)
        assert result["type"] == "array"
        assert result["items"]["type"] == "string"

    def test_tool_categorization(self, generator):
        """Test tool categorization for OpenAPI tags"""
        assert generator._get_tool_category("create_plan") == "Plans"
        assert generator._get_tool_category("list_plans") == "Plans"
        assert generator._get_tool_category("create_task") == "Tasks"
        assert generator._get_tool_category("update_task") == "Tasks"
        assert generator._get_tool_category("authenticate_user") == "Authentication"
        assert generator._get_tool_category("search_plans") == "Search"
        assert generator._get_tool_category("get_info") == "General"

    def test_common_endpoints_generation(self, generator):
        """Test generation of common API endpoints"""
        spec = {"paths": {}, "components": {"schemas": {}}}
        generator._add_common_endpoints(spec)

        # Verify tool discovery endpoint
        assert "/tools" in spec["paths"]
        tools_spec = spec["paths"]["/tools"]["get"]
        assert tools_spec["operationId"] == "list_tools"
        assert "Discovery" in tools_spec["tags"]

        # Verify health check endpoint
        assert "/health" in spec["paths"]
        health_spec = spec["paths"]["/health"]["get"]
        assert health_spec["operationId"] == "health_check"
        assert "Health" in health_spec["tags"]

    def test_response_schemas(self, generator):
        """Test generation of response schemas"""
        spec = {"paths": {}, "components": {"schemas": {}}}
        generator._add_common_endpoints(spec)

        schemas = spec["components"]["schemas"]

        # Verify ToolResponse schema
        assert "ToolResponse" in schemas
        tool_response = schemas["ToolResponse"]
        assert tool_response["type"] == "object"
        assert "success" in tool_response["required"]

        # Verify ErrorResponse schema
        assert "ErrorResponse" in schemas
        error_response = schemas["ErrorResponse"]
        assert error_response["type"] == "object"
        assert "error" in error_response["required"]

        # Verify ToolDefinition schema
        assert "ToolDefinition" in schemas
        tool_def = schemas["ToolDefinition"]
        assert "name" in tool_def["required"]
        assert "description" in tool_def["required"]

    def test_tool_schemas_generation(self, generator, sample_mcp_tools):
        """Test generation of tool-specific request schemas"""
        schemas = generator.generate_tool_schemas(sample_mcp_tools)

        # Verify create_task schema
        assert "CreateTaskRequest" in schemas
        create_task_schema = schemas["CreateTaskRequest"]
        assert create_task_schema["type"] == "object"
        assert "title" in create_task_schema["properties"]
        assert "due_date" in create_task_schema["properties"]
        assert create_task_schema["required"] == ["title"]

        # Verify list_plans schema
        assert "ListPlansRequest" in schemas
        list_plans_schema = schemas["ListPlansRequest"]
        assert list_plans_schema["type"] == "object"
        assert "group_id" in list_plans_schema["properties"]

    def test_security_configuration(self, generator):
        """Test OpenAPI security configuration"""
        spec = generator.base_spec

        # Verify security schemes
        assert "securitySchemes" in spec["components"]
        assert "bearerAuth" in spec["components"]["securitySchemes"]

        bearer_auth = spec["components"]["securitySchemes"]["bearerAuth"]
        assert bearer_auth["type"] == "http"
        assert bearer_auth["scheme"] == "bearer"

        # Verify global security requirement
        assert spec["security"] == [{"bearerAuth": []}]

    def test_empty_tools_list(self, generator):
        """Test handling of empty tools list"""
        spec = generator.generate_openapi_spec([])

        assert spec["info"]["x-tool-count"] == 0
        assert len([path for path in spec["paths"] if path.startswith("/tools/")]) == 0

        # Common endpoints should still be present
        assert "/tools" in spec["paths"]
        assert "/health" in spec["paths"]

    def test_malformed_tool_handling(self, generator):
        """Test handling of malformed tool definitions"""
        malformed_tools = [
            {
                # Missing name
                "description": "A tool without name",
                "inputSchema": {"type": "object"}
            },
            {
                "name": "valid_tool",
                "description": "A valid tool",
                # Missing inputSchema - should handle gracefully
            },
            {
                "name": "another_valid_tool",
                "description": "Another valid tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param": {"type": "string"}
                    }
                }
            }
        ]

        # Should not raise exception and should generate spec for valid tools
        spec = generator.generate_openapi_spec(malformed_tools)

        # Only valid tools should have paths
        tool_paths = [path for path in spec["paths"] if path.startswith("/tools/")]
        assert "/tools/valid_tool" in spec["paths"]
        assert "/tools/another_valid_tool" in spec["paths"]

    def test_server_configuration(self, generator):
        """Test OpenAPI server configuration"""
        spec = generator.base_spec

        assert len(spec["servers"]) >= 1
        server = spec["servers"][0]
        assert server["url"] == "http://mcpo-proxy:8001/v1"
        assert "description" in server


if __name__ == "__main__":
    pytest.main([__file__, "-v"])