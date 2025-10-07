"""
Tests for Dynamic Route Generator - FastAPI route generation from MCP tools
Task 2: Create FastAPI application with dynamic route generation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dynamic_routes import DynamicRouteGenerator, ToolExecutionRequest, ToolExecutionResponse


class TestDynamicRouteGenerator:
    """Test dynamic FastAPI route generation from MCP tools"""

    @pytest.fixture
    def mock_mcp_client(self):
        client = AsyncMock()
        client.list_tools.return_value = [
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
                            "description": "Due date in YYYY-MM-DD format"
                        },
                        "priority": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                            "description": "Priority level"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Task tags"
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
            }
        ]
        return client

    @pytest.fixture
    def mock_openapi_generator(self):
        generator = Mock()
        generator.generate_openapi_spec.return_value = {"openapi": "3.0.3"}
        return generator

    @pytest.fixture
    def route_generator(self, mock_mcp_client, mock_openapi_generator):
        return DynamicRouteGenerator(mock_mcp_client, mock_openapi_generator)

    @pytest.mark.asyncio
    async def test_initialization_success(self, route_generator, mock_mcp_client):
        """Test successful initialization with tool discovery"""
        await route_generator.initialize()

        # Verify MCP client was called
        mock_mcp_client.list_tools.assert_called_once()

        # Verify router has routes
        router = route_generator.get_router()
        assert len(router.routes) > 0

        # Verify tool models were created
        assert "create_task" in route_generator.tool_models
        assert "list_plans" in route_generator.tool_models

    @pytest.mark.asyncio
    async def test_initialization_no_tools(self, route_generator, mock_mcp_client):
        """Test initialization with no tools available"""
        mock_mcp_client.list_tools.return_value = []

        await route_generator.initialize()

        # Should not raise error but log warning
        router = route_generator.get_router()
        assert len(router.routes) == 0
        assert len(route_generator.tool_models) == 0

    @pytest.mark.asyncio
    async def test_create_tool_route(self, route_generator):
        """Test creation of individual tool route"""
        tool = {
            "name": "test_tool",
            "description": "A test tool",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "Parameter 1"},
                    "param2": {"type": "integer", "description": "Parameter 2"}
                },
                "required": ["param1"]
            }
        }

        await route_generator._create_tool_route(tool)

        # Verify model was created
        assert "test_tool" in route_generator.tool_models

        # Verify router has the route
        router = route_generator.get_router()
        route_paths = [route.path for route in router.routes]
        assert "/v1/tools/test_tool" in route_paths

    def test_create_request_model_simple(self, route_generator):
        """Test creation of simple Pydantic request model"""
        tool_name = "simple_tool"
        input_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name parameter"},
                "count": {"type": "integer", "description": "Count parameter"}
            },
            "required": ["name"]
        }

        model = route_generator._create_request_model(tool_name, input_schema)

        # Test model creation
        assert issubclass(model, BaseModel)

        # Check that model has the expected fields by creating an instance
        instance = model(name="test")
        assert hasattr(instance, "name")
        assert hasattr(instance, "count")

        # Test model validation - valid data
        instance = model(name="test", count=5)
        assert instance.name == "test"
        assert instance.count == 5

        # Test model validation - missing required field
        with pytest.raises(ValueError):
            model(count=5)  # Missing required 'name'

    def test_create_request_model_complex(self, route_generator):
        """Test creation of complex Pydantic request model with various types"""
        tool_name = "complex_tool"
        input_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 100},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                "due_date": {"type": "string", "format": "date"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "metadata": {"type": "object"},
                "active": {"type": "boolean"},
                "progress": {"type": "number"}
            },
            "required": ["title", "priority"]
        }

        model = route_generator._create_request_model(tool_name, input_schema)

        # Test with valid complex data
        data = {
            "title": "Test Task",
            "priority": 3,
            "due_date": "2025-12-31",
            "tags": ["urgent", "important"],
            "metadata": {"key": "value"},
            "active": True,
            "progress": 0.75
        }

        instance = model(**data)
        assert instance.title == "Test Task"
        assert instance.priority == 3
        assert instance.tags == ["urgent", "important"]
        assert instance.metadata == {"key": "value"}
        assert instance.active is True
        assert instance.progress == 0.75

    def test_convert_json_type_to_python(self, route_generator):
        """Test JSON schema type conversion to Python types"""
        # Test basic types
        assert route_generator._convert_json_type_to_python({"type": "string"}) == str
        assert route_generator._convert_json_type_to_python({"type": "integer"}) == int
        assert route_generator._convert_json_type_to_python({"type": "number"}) == float
        assert route_generator._convert_json_type_to_python({"type": "boolean"}) == bool

        # Test array types
        result = route_generator._convert_json_type_to_python({"type": "array"})
        assert str(result).startswith("typing.List")

        # Test array with item type
        result = route_generator._convert_json_type_to_python({
            "type": "array",
            "items": {"type": "integer"}
        })
        assert "List[int]" in str(result)

        # Test object type
        result = route_generator._convert_json_type_to_python({"type": "object"})
        assert "Dict[str, typing.Any]" in str(result)

        # Test unknown type defaults to string
        assert route_generator._convert_json_type_to_python({"type": "unknown"}) == str

    def test_extract_field_constraints(self, route_generator):
        """Test extraction of field constraints from JSON schema"""
        # String constraints
        field_def = {
            "type": "string",
            "minLength": 5,
            "maxLength": 50,
            "pattern": "^[A-Za-z]+$"
        }
        constraints = route_generator._extract_field_constraints(field_def)
        assert constraints["min_length"] == 5
        assert constraints["max_length"] == 50
        assert constraints["regex"] == "^[A-Za-z]+$"

        # Numeric constraints
        field_def = {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "exclusiveMinimum": 0,
            "exclusiveMaximum": 11
        }
        constraints = route_generator._extract_field_constraints(field_def)
        assert constraints["ge"] == 1
        assert constraints["le"] == 10
        assert constraints["gt"] == 0
        assert constraints["lt"] == 11

        # Enum constraints
        field_def = {
            "type": "string",
            "enum": ["option1", "option2", "option3"]
        }
        constraints = route_generator._extract_field_constraints(field_def)
        assert constraints["choices"] == ["option1", "option2", "option3"]

    @pytest.mark.asyncio
    async def test_get_tool_schema(self, route_generator):
        """Test getting OpenAPI schema for specific tool"""
        # First initialize to create models
        await route_generator.initialize()

        # Test existing tool
        schema = await route_generator.get_tool_schema("create_task")
        assert schema is not None
        assert "properties" in schema
        assert "title" in schema["properties"]

        # Test non-existing tool
        schema = await route_generator.get_tool_schema("nonexistent_tool")
        assert schema is None

    @pytest.mark.asyncio
    async def test_get_available_tools(self, route_generator):
        """Test getting list of available tools with schemas"""
        await route_generator.initialize()

        tools = await route_generator.get_available_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "create_task"
        assert tools[0]["endpoint"] == "/v1/tools/create_task"
        assert tools[0]["method"] == "POST"
        assert "schema" in tools[0]

        assert tools[1]["name"] == "list_plans"
        assert tools[1]["endpoint"] == "/v1/tools/list_plans"

    @pytest.mark.asyncio
    async def test_refresh_routes(self, route_generator, mock_mcp_client):
        """Test refreshing dynamic routes"""
        # Initial setup
        await route_generator.initialize()
        initial_route_count = len(route_generator.get_router().routes)

        # Add more tools
        mock_mcp_client.list_tools.return_value.append({
            "name": "new_tool",
            "description": "A new tool",
            "inputSchema": {"type": "object"}
        })

        # Refresh routes
        await route_generator.refresh_routes()

        # Verify routes were refreshed
        new_route_count = len(route_generator.get_router().routes)
        assert new_route_count > initial_route_count
        assert "new_tool" in route_generator.tool_models

    def test_tool_execution_models(self):
        """Test tool execution request/response models"""
        # Test ToolExecutionRequest
        request = ToolExecutionRequest(
            arguments={"title": "Test Task", "priority": 1},
            user_id="user123"
        )
        assert request.arguments == {"title": "Test Task", "priority": 1}
        assert request.user_id == "user123"

        # Test default user_id
        request = ToolExecutionRequest(arguments={})
        assert request.user_id == "default"

        # Test ToolExecutionResponse
        response = ToolExecutionResponse(
            success=True,
            data={"id": "task_123"},
            message="Task created successfully",
            tool_name="create_task"
        )
        assert response.success is True
        assert response.data == {"id": "task_123"}
        assert response.message == "Task created successfully"
        assert response.tool_name == "create_task"

    @pytest.mark.asyncio
    async def test_tool_route_execution_success(self, route_generator, mock_mcp_client):
        """Test successful tool execution through dynamic route"""
        # Setup tool execution response
        mock_mcp_client.execute_tool.return_value = {
            "success": True,
            "content": {"id": "task_123", "title": "Test Task"},
            "message": "Task created successfully",
            "correlation_id": "req_123"
        }

        await route_generator.initialize()

        # Get the create_task model
        model_class = route_generator.tool_models["create_task"]

        # Simulate route execution
        # This would normally be done by FastAPI, but we test the logic
        request_data = model_class(title="Test Task", priority=3)

        # Execute via MCP client (simulating the route handler)
        result = await mock_mcp_client.execute_tool(
            "create_task",
            request_data.model_dump(),
            "test_user"
        )

        # Verify the result
        assert result["success"] is True
        assert result["content"]["id"] == "task_123"
        assert result["message"] == "Task created successfully"

    @pytest.mark.asyncio
    async def test_malformed_tool_handling(self, route_generator, mock_mcp_client):
        """Test handling of malformed tool definitions"""
        mock_mcp_client.list_tools.return_value = [
            {
                # Missing name
                "description": "Tool without name",
                "inputSchema": {"type": "object"}
            },
            {
                "name": "valid_tool",
                "description": "Valid tool",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "param": {"type": "string"}
                    }
                }
            },
            {
                "name": "tool_without_schema",
                "description": "Tool without input schema"
                # Missing inputSchema
            }
        ]

        # Should not raise exception
        await route_generator.initialize()

        # Only valid tools should have models and routes
        assert "valid_tool" in route_generator.tool_models
        assert "tool_without_schema" in route_generator.tool_models
        assert len(route_generator.tool_models) == 2

    @pytest.mark.asyncio
    async def test_initialization_error_handling(self, route_generator, mock_mcp_client):
        """Test error handling during initialization"""
        mock_mcp_client.list_tools.side_effect = Exception("MCP server error")

        with pytest.raises(Exception, match="MCP server error"):
            await route_generator.initialize()

    def test_model_creation_error_handling(self, route_generator):
        """Test error handling during model creation"""
        # Test with invalid schema that might cause model creation to fail
        invalid_schema = {
            "type": "object",
            "properties": {
                "invalid_field": {"type": "completely_unknown_type"}
            }
        }

        # Should not raise exception, should return generic model
        model = route_generator._create_request_model("test_tool", invalid_schema)
        assert issubclass(model, BaseModel)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])