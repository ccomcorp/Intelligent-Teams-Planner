"""
Dynamic route generator for MCP tools
Creates FastAPI routes dynamically based on discovered MCP tool definitions
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, create_model
import structlog

try:
    from .mcp_client import MCPClient
    from .openapi_generator import OpenAPIGenerator
except ImportError:
    # For testing
    from mcp_client import MCPClient
    from openapi_generator import OpenAPIGenerator

logger = structlog.get_logger(__name__)


class DynamicRouteGenerator:
    """Generates FastAPI routes dynamically from MCP tool definitions"""

    def __init__(self, mcp_client: MCPClient, openapi_generator: OpenAPIGenerator):
        self.mcp_client = mcp_client
        self.openapi_generator = openapi_generator
        self.router = APIRouter(prefix="/v1/tools", tags=["MCP Tools"])
        self.tool_models: Dict[str, Any] = {}

    async def initialize(self):
        """Initialize dynamic routes based on discovered MCP tools"""
        try:
            # Get available tools from MCP server with resilient handling
            tools = await self._get_tools_safely()

            if not tools:
                logger.warning("No MCP tools discovered for route generation - starting with empty routes")
                return

            # Generate routes for each tool
            for tool in tools:
                await self._create_tool_route(tool)

            logger.info("Dynamic routes initialized", tool_count=len(tools))

        except Exception as e:
            logger.warning("Failed to initialize dynamic routes - continuing with degraded functionality", error=str(e))
            # Don't raise - allow startup to continue

    async def _get_tools_safely(self) -> List[Dict[str, Any]]:
        """Safely get tools from MCP client with timeout and error handling"""
        try:
            import asyncio
            # Try to get tools with a short timeout
            tools = await asyncio.wait_for(self.mcp_client.list_tools(), timeout=5.0)
            return tools if tools else []
        except asyncio.TimeoutError:
            logger.warning("MCP client timeout while fetching tools")
            return []
        except Exception as e:
            logger.warning("Failed to fetch tools from MCP client", error=str(e))
            return []

    async def _create_tool_route(self, tool: Dict[str, Any]):
        """Create a FastAPI route for a specific MCP tool"""
        try:
            tool_name = tool.get("name")
            if not tool_name:
                logger.warning("Skipping tool without name", tool=tool)
                return

            tool_description = tool.get("description", f"Execute {tool_name} tool")
            input_schema = tool.get("inputSchema", {})

            # Create Pydantic model for request validation
            request_model = self._create_request_model(tool_name, input_schema)
            self.tool_models[tool_name] = request_model

            # Create the route handler
            async def tool_handler(
                request: request_model,
                user_id: str = "default",
                mcp_client: MCPClient = Depends(lambda: self.mcp_client)
            ) -> Dict[str, Any]:
                """Dynamic tool execution handler"""
                try:
                    # Convert Pydantic model to dictionary
                    arguments = request.model_dump()

                    # Execute tool via MCP client
                    result = await mcp_client.execute_tool(tool_name, arguments, user_id)

                    # Format response
                    return {
                        "success": result.get("success", False),
                        "data": result.get("content"),
                        "message": result.get(
                            "message",
                            "Tool executed successfully" if result.get("success") else "Tool execution failed"
                        ),
                        "correlation_id": result.get("correlation_id"),
                        "tool_name": tool_name,
                        "metadata": result.get("metadata", {})
                    }

                except Exception as e:
                    logger.error("Error executing tool", tool=tool_name, error=str(e))
                    raise HTTPException(
                        status_code=500,
                        detail=f"Tool execution failed: {str(e)}"
                    )

            # Add route to router
            self.router.add_api_route(
                path=f"/{tool_name}",
                endpoint=tool_handler,
                methods=["POST"],
                summary=tool_description,
                description=f"Execute the {tool_name} MCP tool",
                response_model=dict,
                operation_id=f"execute_{tool_name}"
            )

            logger.debug("Created dynamic route", tool=tool_name, path=f"/v1/tools/{tool_name}")

        except Exception as e:
            logger.error("Failed to create tool route", tool=tool.get("name"), error=str(e))

    def _create_request_model(self, tool_name: str, input_schema: Dict[str, Any]) -> BaseModel:
        """Create a Pydantic model from MCP tool input schema"""
        try:
            model_name = f"{''.join(word.title() for word in tool_name.split('_'))}Request"

            # Extract properties and required fields
            properties = input_schema.get("properties", {})
            required_fields = set(input_schema.get("required", []))

            # Convert to Pydantic field definitions
            field_definitions = {}

            for field_name, field_def in properties.items():
                field_type = self._convert_json_type_to_python(field_def)
                default_value = ... if field_name in required_fields else None

                field_definitions[field_name] = (
                    field_type,
                    Field(
                        default=default_value,
                        description=field_def.get("description", ""),
                        **self._extract_field_constraints(field_def)
                    )
                )

            # Create dynamic Pydantic model
            return create_model(model_name, **field_definitions)

        except Exception as e:
            logger.error("Failed to create request model", tool=tool_name, error=str(e))
            # Return a generic model if creation fails
            return create_model(f"{tool_name.title()}Request")

    def _convert_json_type_to_python(self, field_def: Dict[str, Any]) -> type:
        """Convert JSON schema type to Python type"""
        json_type = field_def.get("type", "string")

        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": List[str],  # Default to List[str], could be more sophisticated
            "object": Dict[str, Any]
        }

        python_type = type_mapping.get(json_type, str)

        # Handle array item types
        if json_type == "array" and "items" in field_def:
            item_type = self._convert_json_type_to_python(field_def["items"])
            python_type = List[item_type]

        # Handle optional fields
        if field_def.get("nullable", False):
            python_type = Optional[python_type]

        return python_type

    def _extract_field_constraints(self, field_def: Dict[str, Any]) -> Dict[str, Any]:
        """Extract field constraints from JSON schema"""
        constraints = {}

        # String constraints
        if "minLength" in field_def:
            constraints["min_length"] = field_def["minLength"]
        if "maxLength" in field_def:
            constraints["max_length"] = field_def["maxLength"]
        if "pattern" in field_def:
            constraints["regex"] = field_def["pattern"]

        # Numeric constraints
        if "minimum" in field_def:
            constraints["ge"] = field_def["minimum"]
        if "maximum" in field_def:
            constraints["le"] = field_def["maximum"]
        if "exclusiveMinimum" in field_def:
            constraints["gt"] = field_def["exclusiveMinimum"]
        if "exclusiveMaximum" in field_def:
            constraints["lt"] = field_def["exclusiveMaximum"]

        # Enum constraints
        if "enum" in field_def:
            constraints["choices"] = field_def["enum"]

        return constraints

    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get OpenAPI schema for a specific tool"""
        try:
            if tool_name not in self.tool_models:
                return None

            model = self.tool_models[tool_name]
            return model.model_json_schema()

        except Exception as e:
            logger.error("Error getting tool schema", tool=tool_name, error=str(e))
            return None

    async def refresh_routes(self):
        """Refresh dynamic routes based on current MCP tools"""
        try:
            # Clear existing routes
            self.router.routes.clear()
            self.tool_models.clear()

            # Reinitialize routes
            await self.initialize()

            logger.info("Dynamic routes refreshed")

        except Exception as e:
            logger.error("Failed to refresh routes", error=str(e))
            raise

    def get_router(self) -> APIRouter:
        """Get the FastAPI router with dynamic routes"""
        return self.router

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools with their schemas"""
        try:
            tools = []

            for tool_name, model in self.tool_models.items():
                tools.append({
                    "name": tool_name,
                    "endpoint": f"/v1/tools/{tool_name}",
                    "method": "POST",
                    "schema": model.model_json_schema(),
                    "description": model.model_json_schema().get("description", f"Execute {tool_name} tool")
                })

            return tools

        except Exception as e:
            logger.error("Error getting available tools", error=str(e))
            return []


class ToolExecutionRequest(BaseModel):
    """Generic tool execution request"""
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")
    user_id: str = Field("default", description="User identifier")


class ToolExecutionResponse(BaseModel):
    """Tool execution response"""
    success: bool = Field(..., description="Execution success status")
    data: Optional[Any] = Field(None, description="Tool execution result data")
    message: str = Field(..., description="Execution status message")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID")
    tool_name: str = Field(..., description="Executed tool name")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ToolListResponse(BaseModel):
    """Available tools list response"""
    tools: List[Dict[str, Any]] = Field(..., description="List of available tools")
    total_count: int = Field(..., description="Total number of tools")
    generated_at: str = Field(..., description="Timestamp when list was generated")
