from typing import Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)

class OpenAPISpecGenerator:
    """Generate OpenAPI specification from MCP tools"""

    def __init__(self, service_title: str = "Planner MCP Proxy", version: str = "1.0.0"):
        self.service_title = service_title
        self.version = version

    def generate_spec_from_tools(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate OpenAPI 3.0 specification from MCP tools"""

        spec = {
            "openapi": "3.0.3",
            "info": {
                "title": self.service_title,
                "description": "OpenAPI proxy for Model Context Protocol (MCP) tools",
                "version": self.version
            },
            "servers": [
                {
                    "url": "/",
                    "description": "MCP Proxy Server"
                }
            ],
            "security": [
                {
                    "bearerAuth": []
                }
            ],
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "description": "Microsoft Graph API Bearer token"
                    }
                },
                "schemas": {
                    "APIResponse": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean"},
                            "message": {"type": "string"},
                            "data": {"type": "object"},
                            "error": {"type": "string"}
                        },
                        "required": ["success", "message"]
                    },
                    "Error": {
                        "type": "object",
                        "properties": {
                            "detail": {"type": "string"}
                        },
                        "required": ["detail"]
                    }
                }
            },
            "paths": {}
        }

        # Add health endpoint
        spec["paths"]["/health"] = {
            "get": {
                "summary": "Health check",
                "description": "Check if the proxy service is healthy",
                "operationId": "health_check",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string"},
                                        "timestamp": {"type": "string", "format": "date-time"},
                                        "mcp_server_status": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        # Convert each MCP tool to OpenAPI path
        for tool in tools:
            path = self._convert_tool_to_path(tool)
            if path:
                tool_name = tool.get("name", "unknown")
                endpoint_path = f"/tools/{tool_name}"
                spec["paths"][endpoint_path] = path

        logger.info("Generated OpenAPI spec", tools_count=len(tools), paths_count=len(spec["paths"]))
        return spec

    def _convert_tool_to_path(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single MCP tool to OpenAPI path definition"""
        try:
            name = tool.get("name", "unknown")
            description = tool.get("description", "No description available")
            parameters = tool.get("parameters", {})

            # Create operation ID from tool name
            operation_id = name.replace(".", "_").replace("-", "_")

            path_def = {
                "post": {
                    "summary": description,
                    "description": f"Execute {name} tool via MCP protocol",
                    "operationId": operation_id,
                    "security": [{"bearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": self._convert_parameters_to_schema(parameters)
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Tool executed successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/APIResponse"}
                                }
                            }
                        },
                        "400": {
                            "description": "Bad request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        },
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        },
                        "500": {
                            "description": "Internal server error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            }
                        }
                    },
                    "tags": [self._get_tag_from_tool_name(name)]
                }
            }

            return path_def

        except Exception as e:
            logger.error("Error converting tool to path", tool_name=tool.get("name"), error=str(e))
            return None

    def _convert_parameters_to_schema(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MCP parameters to OpenAPI schema"""
        # MCP parameters should already be in JSON Schema format
        if not parameters:
            return {"type": "object", "properties": {}}

        # Ensure it's a valid schema
        schema = parameters.copy()
        if "type" not in schema:
            schema["type"] = "object"
        if "properties" not in schema and schema["type"] == "object":
            schema["properties"] = {}

        return schema

    def _get_tag_from_tool_name(self, tool_name: str) -> str:
        """Extract tag/category from tool name"""
        if "." in tool_name:
            return tool_name.split(".")[0].title()
        return "Tools"

    def add_custom_schemas(self, spec: Dict[str, Any], custom_schemas: Dict[str, Any]) -> Dict[str, Any]:
        """Add custom schemas to the OpenAPI specification"""
        if "components" not in spec:
            spec["components"] = {}
        if "schemas" not in spec["components"]:
            spec["components"]["schemas"] = {}

        spec["components"]["schemas"].update(custom_schemas)
        return spec

    def validate_spec(self, spec: Dict[str, Any]) -> bool:
        """Basic validation of generated OpenAPI spec"""
        try:
            required_keys = ["openapi", "info", "paths"]
            for key in required_keys:
                if key not in spec:
                    logger.error("Missing required key in spec", key=key)
                    return False

            if not isinstance(spec["paths"], dict):
                logger.error("Paths must be a dictionary")
                return False

            return True

        except Exception as e:
            logger.error("Error validating spec", error=str(e))
            return False