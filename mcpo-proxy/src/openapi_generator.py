"""
OpenAPI specification generator from MCP tool definitions
Converts MCP tool schemas to OpenAPI 3.0 format for OpenWebUI compatibility
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


class OpenAPIGenerator:
    """Generates OpenAPI specifications from MCP tool definitions"""

    def __init__(self):
        self.base_spec = {
            "openapi": "3.0.3",
            "info": {
                "title": "MCP Tools API",
                "description": "Auto-generated API from MCP Server tool definitions",
                "version": "1.0.0",
                "contact": {
                    "name": "MCPO Proxy",
                    "url": "http://mcpo-proxy:8001"
                }
            },
            "servers": [
                {
                    "url": "http://mcpo-proxy:8001/v1",
                    "description": "MCPO Proxy Server"
                }
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT"
                    }
                }
            },
            "security": [
                {"bearerAuth": []}
            ]
        }

    def generate_openapi_spec(self, mcp_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate complete OpenAPI specification from MCP tools"""
        try:
            spec = self.base_spec.copy()
            spec["info"]["x-generated-at"] = datetime.now(timezone.utc).isoformat()
            spec["info"]["x-tool-count"] = len(mcp_tools)

            # Generate paths and schemas for each tool
            for tool in mcp_tools:
                self._add_tool_to_spec(spec, tool)

            # Add common endpoints
            self._add_common_endpoints(spec)

            logger.info("Generated OpenAPI spec", tool_count=len(mcp_tools))
            return spec

        except Exception as e:
            logger.error("Failed to generate OpenAPI spec", error=str(e))
            raise

    def _add_tool_to_spec(self, spec: Dict[str, Any], tool: Dict[str, Any]):
        """Add a single MCP tool to the OpenAPI specification"""
        try:
            tool_name = tool.get("name")
            if not tool_name:
                logger.warning("Skipping tool without name", tool=tool)
                return

            tool_description = tool.get("description", f"Execute {tool_name} tool")
            # Extract the input schema from parameters field (MCP tools structure)
            input_schema = tool.get("inputSchema", tool.get("parameters", {}))

            # Create path for tool execution
            path = f"/tools/{tool_name}"
            spec["paths"][path] = {
                "post": {
                    "summary": tool_description,
                    "description": tool_description,
                    "operationId": f"execute_{tool_name}",
                    "tags": [self._get_tool_category(tool_name)],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": self._convert_mcp_schema_to_openapi(input_schema, tool_name)
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Tool execution successful",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ToolResponse"
                                    }
                                }
                            }
                        },
                        "400": {
                            "description": "Invalid request parameters",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ErrorResponse"
                                    }
                                }
                            }
                        },
                        "401": {
                            "description": "Authentication required"
                        },
                        "429": {
                            "description": "Rate limit exceeded"
                        },
                        "500": {
                            "description": "Internal server error"
                        }
                    },
                    "security": [
                        {"bearerAuth": []}
                    ]
                }
            }

            logger.debug("Added tool to OpenAPI spec", tool_name=tool_name)

        except Exception as e:
            logger.error("Failed to add tool to spec", tool_name=tool.get("name"), error=str(e))

    def _convert_mcp_schema_to_openapi(self, mcp_schema: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """Convert MCP input schema to OpenAPI schema"""
        try:
            if not mcp_schema:
                return {
                    "type": "object",
                    "properties": {},
                    "required": []
                }

            # Basic schema conversion
            openapi_schema = {
                "type": mcp_schema.get("type", "object"),
                "properties": {},
                "required": mcp_schema.get("required", [])
            }

            # Convert properties
            properties = mcp_schema.get("properties", {})
            for prop_name, prop_def in properties.items():
                openapi_schema["properties"][prop_name] = self._convert_property(prop_def)

            # Add schema to components for reuse
            schema_name = f"{''.join(word.title() for word in tool_name.split('_'))}Request"
            return {"$ref": f"#/components/schemas/{schema_name}"}

        except Exception as e:
            logger.error("Failed to convert MCP schema", tool_name=tool_name, error=str(e))
            return {"type": "object"}

    def _convert_property(self, prop_def: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single property definition"""
        converted = {
            "type": prop_def.get("type", "string"),
            "description": prop_def.get("description", "")
        }

        # Handle specific types
        if "enum" in prop_def:
            converted["enum"] = prop_def["enum"]

        if "format" in prop_def:
            converted["format"] = prop_def["format"]

        if "items" in prop_def:
            converted["items"] = self._convert_property(prop_def["items"])

        return converted

    def _get_tool_category(self, tool_name: str) -> str:
        """Categorize tool for OpenAPI tags"""
        tool_lower = tool_name.lower()
        if "search" in tool_lower:
            return "Search"
        elif "plan" in tool_lower:
            return "Plans"
        elif "task" in tool_lower:
            return "Tasks"
        elif "auth" in tool_lower:
            return "Authentication"
        else:
            return "General"

    def _add_common_endpoints(self, spec: Dict[str, Any]):
        """Add common API endpoints to the specification"""
        # Tool discovery endpoint
        spec["paths"]["/tools"] = {
            "get": {
                "summary": "List available tools",
                "description": "Get list of all available MCP tools",
                "operationId": "list_tools",
                "tags": ["Discovery"],
                "responses": {
                    "200": {
                        "description": "List of available tools",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "$ref": "#/components/schemas/ToolDefinition"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        # Health check endpoint
        spec["paths"]["/health"] = {
            "get": {
                "summary": "Health check",
                "description": "Check service health and dependencies",
                "operationId": "health_check",
                "tags": ["Health"],
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/HealthResponse"
                                }
                            }
                        }
                    }
                }
            }
        }

        # Add common schemas
        spec["components"]["schemas"].update({
            "ToolResponse": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "data": {"type": "object"},
                    "message": {"type": "string"},
                    "correlation_id": {"type": "string"}
                },
                "required": ["success"]
            },
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "message": {"type": "string"},
                            "details": {"type": "object"},
                            "correlation_id": {"type": "string"}
                        },
                        "required": ["type", "message"]
                    }
                },
                "required": ["error"]
            },
            "ToolDefinition": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "inputSchema": {"type": "object"},
                    "category": {"type": "string"}
                },
                "required": ["name", "description"]
            },
            "HealthResponse": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "dependencies": {
                        "type": "object",
                        "properties": {
                            "mcp_server": {"type": "string"},
                            "redis": {"type": "string"}
                        }
                    }
                },
                "required": ["status", "timestamp"]
            }
        })

    def generate_tool_schemas(self, mcp_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate schemas for tool request bodies"""
        schemas = {}

        for tool in mcp_tools:
            tool_name = tool.get("name")
            if not tool_name:
                continue

            input_schema = tool.get("inputSchema", {})
            schema_name = f"{''.join(word.title() for word in tool_name.split('_'))}Request"

            schemas[schema_name] = {
                "type": input_schema.get("type", "object"),
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", [])
            }

        return schemas
