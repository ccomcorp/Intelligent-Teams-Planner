import asyncio
from typing import Dict, Any, Optional
import httpx
import structlog
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

class MCPToOpenAPITranslator:
    """Translate between MCP protocol and OpenAPI requests/responses"""

    def __init__(self, mcp_server_url: str):
        self.mcp_server_url = mcp_server_url.rstrip("/")
        self.timeout = httpx.Timeout(30.0)

    async def discover_tools(self) -> list[Dict[str, Any]]:
        """Discover available tools from MCP server"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.mcp_server_url}/tools")
                response.raise_for_status()
                tools = response.json()

                logger.info("Discovered MCP tools", count=len(tools))
                return tools

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error discovering tools", status_code=e.response.status_code, error=str(e))
            raise HTTPException(status_code=502, detail=f"MCP server error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error("Request error discovering tools", error=str(e))
            raise HTTPException(status_code=503, detail="MCP server unavailable")
        except Exception as e:
            logger.error("Unexpected error discovering tools", error=str(e))
            raise HTTPException(status_code=500, detail="Tool discovery failed")

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        authorization_header: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a tool on the MCP server"""
        try:
            headers = {"Content-Type": "application/json"}
            if authorization_header:
                headers["Authorization"] = authorization_header

            # Construct the MCP tool endpoint
            endpoint = f"{self.mcp_server_url}/tools/{tool_name}"

            logger.debug("Executing MCP tool", tool_name=tool_name, endpoint=endpoint)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=parameters,
                    headers=headers
                )

                # Handle different response codes
                if response.status_code == 401:
                    raise HTTPException(status_code=401, detail="Unauthorized - invalid or expired token")
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
                elif response.status_code >= 400:
                    try:
                        error_detail = response.json().get("detail", response.text)
                    except:
                        error_detail = response.text

                    logger.error(
                        "MCP tool execution failed",
                        tool_name=tool_name,
                        status_code=response.status_code,
                        error=error_detail
                    )
                    raise HTTPException(status_code=response.status_code, detail=error_detail)

                result = response.json()
                logger.info("MCP tool executed successfully", tool_name=tool_name)
                return result

        except HTTPException:
            raise
        except httpx.TimeoutException:
            logger.error("Timeout executing MCP tool", tool_name=tool_name)
            raise HTTPException(status_code=504, detail="Tool execution timeout")
        except httpx.RequestError as e:
            logger.error("Request error executing MCP tool", tool_name=tool_name, error=str(e))
            raise HTTPException(status_code=503, detail="MCP server unavailable")
        except Exception as e:
            logger.error("Unexpected error executing MCP tool", tool_name=tool_name, error=str(e))
            raise HTTPException(status_code=500, detail="Tool execution failed")

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters against tool schema (basic validation)"""
        try:
            # Get tool definition from cache or fetch from server
            tools = await self.discover_tools()
            tool_def = next((tool for tool in tools if tool.get("name") == tool_name), None)

            if not tool_def:
                logger.warning("Tool definition not found for validation", tool_name=tool_name)
                return True  # Allow execution to proceed

            tool_params = tool_def.get("parameters", {})
            required_params = tool_params.get("required", [])

            # Check required parameters
            for param in required_params:
                if param not in parameters:
                    logger.error("Missing required parameter", tool_name=tool_name, param=param)
                    return False

            # Basic type checking could be added here
            logger.debug("Parameter validation passed", tool_name=tool_name)
            return True

        except Exception as e:
            logger.warning("Error validating parameters", tool_name=tool_name, error=str(e))
            return True  # Allow execution to proceed on validation errors

    async def health_check(self) -> Dict[str, Any]:
        """Check health of MCP server"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(f"{self.mcp_server_url}/health")
                response.raise_for_status()

                health_data = response.json()
                logger.debug("MCP server health check successful")
                return {
                    "mcp_server_status": "healthy",
                    "mcp_server_health": health_data
                }

        except httpx.HTTPStatusError as e:
            logger.warning("MCP server health check failed", status_code=e.response.status_code)
            return {
                "mcp_server_status": f"unhealthy (HTTP {e.response.status_code})",
                "mcp_server_health": None
            }
        except httpx.RequestError as e:
            logger.warning("MCP server unreachable", error=str(e))
            return {
                "mcp_server_status": "unreachable",
                "mcp_server_health": None
            }
        except Exception as e:
            logger.error("Unexpected error in health check", error=str(e))
            return {
                "mcp_server_status": f"error: {str(e)}",
                "mcp_server_health": None
            }

    def format_openapi_response(self, mcp_response: Dict[str, Any]) -> Dict[str, Any]:
        """Format MCP response for OpenAPI consumers"""
        # MCP responses should already be in the correct format
        # but we can add any additional formatting here

        if not isinstance(mcp_response, dict):
            return {
                "success": False,
                "message": "Invalid response format from MCP server",
                "error": "Response is not a valid JSON object"
            }

        # Ensure required fields are present
        if "success" not in mcp_response:
            mcp_response["success"] = True  # Assume success if not specified

        if "message" not in mcp_response:
            mcp_response["message"] = "Operation completed"

        return mcp_response

    def format_error_response(self, error_message: str, error_code: Optional[str] = None) -> Dict[str, Any]:
        """Format error response for OpenAPI consumers"""
        return {
            "success": False,
            "message": "Operation failed",
            "error": error_message,
            "error_code": error_code
        }

    async def get_server_info(self) -> Dict[str, Any]:
        """Get information about the MCP server"""
        try:
            health_info = await self.health_check()
            tools = await self.discover_tools()

            return {
                "mcp_server_url": self.mcp_server_url,
                "health": health_info,
                "tools_count": len(tools),
                "available_tools": [tool.get("name") for tool in tools]
            }

        except Exception as e:
            logger.error("Error getting server info", error=str(e))
            return {
                "mcp_server_url": self.mcp_server_url,
                "error": str(e)
            }