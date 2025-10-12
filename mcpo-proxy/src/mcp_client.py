"""
MCP Client for communicating with Model Context Protocol server
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import time

import httpx
import structlog

logger = structlog.get_logger(__name__)


class MCPError(Exception):
    """MCP client error"""
    pass


class MCPClient:
    """Client for communicating with MCP server"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client: httpx.AsyncClient = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 1.0  # Initial delay in seconds
        self._last_successful_request = time.time()

    async def initialize(self):
        """Initialize HTTP client with MCP protocol handshake"""
        try:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
            )

            # Try to perform MCP protocol handshake with retries and graceful degradation
            handshake_success = await self._perform_handshake_with_retries()

            if handshake_success:
                # Discover server capabilities
                await self._discover_capabilities()
                logger.info("MCP client initialized successfully with protocol handshake")
            else:
                # Initialize in degraded mode - client is available but MCP features may be limited
                logger.warning("MCP client initialized in degraded mode - MCP server not immediately available")

        except Exception as e:
            logger.error("Failed to initialize MCP client", error=str(e))
            # Don't fail completely - allow startup with limited functionality
            logger.warning("MCP client starting in offline mode - will retry connections automatically")

    async def _perform_handshake_with_retries(self, max_attempts: int = 3) -> bool:
        """Perform MCP protocol handshake with retries and timeout handling"""
        for attempt in range(max_attempts):
            try:
                logger.info("Attempting MCP handshake",
                           attempt=attempt + 1,
                           max_attempts=max_attempts,
                           server_url=self.base_url)

                # Try handshake with shorter timeout for startup
                await asyncio.wait_for(self._perform_handshake(), timeout=10.0)

                # Test connectivity with shorter timeout
                health_status = await asyncio.wait_for(self.health_check(), timeout=5.0)
                if health_status == "healthy":
                    logger.info("MCP handshake successful",
                               attempt=attempt + 1,
                               server_url=self.base_url)
                    return True
                else:
                    logger.warning("MCP handshake completed but health check failed",
                                 attempt=attempt + 1,
                                 status=health_status,
                                 server_url=self.base_url)

            except asyncio.TimeoutError:
                logger.warning("MCP handshake timeout",
                              attempt=attempt + 1,
                              server_url=self.base_url)
            except Exception as e:
                logger.warning("MCP handshake failed",
                              attempt=attempt + 1,
                              error=str(e),
                              server_url=self.base_url)

            if attempt < max_attempts - 1:
                await asyncio.sleep(2.0)  # Wait before retry

        logger.warning("All MCP handshake attempts failed - continuing with degraded functionality",
                      server_url=self.base_url)
        return False

    async def _perform_handshake(self):
        """Perform MCP protocol handshake"""
        try:
            # Check if server supports MCP protocol
            response = await self.client.get(f"{self.base_url}/")
            if response.status_code == 200:
                server_info = response.json()
                protocol_version = server_info.get("protocol_version", "unknown")
                logger.info("MCP handshake successful", protocol_version=protocol_version)
            else:
                logger.warning("MCP handshake returned non-200 status", status=response.status_code)
        except Exception as e:
            logger.warning("MCP handshake failed, continuing with basic connectivity", error=str(e))

    async def _discover_capabilities(self):
        """Discover and cache MCP server capabilities"""
        try:
            capabilities = await self.get_capabilities()
            if capabilities:
                logger.info("MCP capabilities discovered", capabilities=capabilities)

            # Get available tools
            tools = await self.list_tools()
            logger.info("MCP tools discovered", tool_count=len(tools) if tools else 0)

        except Exception as e:
            logger.warning("MCP capability discovery failed", error=str(e))

    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()
            logger.info("MCP client closed")

    async def health_check(self) -> str:
        """Check MCP server health"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return "healthy"
            else:
                logger.warning("MCP server health check failed", status_code=response.status_code)
                return "unhealthy"
        except Exception as e:
            logger.error("MCP server health check error", error=str(e))
            return "unhealthy"

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
        retry_on_failure: bool = True
    ) -> Dict[str, Any]:
        """Make request to MCP server with automatic retry and reconnection"""
        for attempt in range(3):  # Retry up to 3 times
            try:
                # Check if we need to reconnect
                if not self.client or not await self._is_connection_healthy():
                    await self._attempt_reconnection()

                url = f"{self.base_url}{endpoint}"

                response = await self.client.request(
                    method=method,
                    url=url,
                    json=data if data else None,
                    params=params
                )

                # Update last successful request time
                self._last_successful_request = time.time()
                self._reconnect_attempts = 0  # Reset reconnection counter on success

                if response.status_code == 404:
                    logger.warning("MCP endpoint not found", endpoint=endpoint)
                    return None

                if 400 <= response.status_code < 500:
                    error_detail = response.text if response.text else "Client error"
                    raise MCPError(f"Client error {response.status_code}: {error_detail}")

                if response.status_code >= 500:
                    if retry_on_failure and attempt < 2:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise MCPError(f"Server error {response.status_code}: {response.text}")

                if response.status_code == 204:  # No content
                    return {}

                return response.json() if response.text else {}

            except httpx.RequestError as e:
                logger.error("MCP request error", endpoint=endpoint, error=str(e), attempt=attempt + 1)
                if retry_on_failure and attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise MCPError(f"Request error after {attempt + 1} attempts: {str(e)}")
            except MCPError as e:
                if retry_on_failure and attempt < 2 and "Server error" in str(e):
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                logger.error("Unexpected MCP error", endpoint=endpoint, error=str(e))
                if retry_on_failure and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise MCPError(f"Unexpected error: {str(e)}")

        raise MCPError("Max retry attempts exceeded")

    async def _is_connection_healthy(self) -> bool:
        """Check if the connection to MCP server is healthy"""
        try:
            if not self.client:
                return False

            # Simple connectivity test
            response = await self.client.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200
        except (httpx.RequestError, httpx.TimeoutException, Exception) as e:
            logger.debug("Connection health check failed", error=str(e))
            return False

    async def _attempt_reconnection(self):
        """Attempt to reconnect to MCP server with exponential backoff"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            raise MCPError(f"Max reconnection attempts ({self._max_reconnect_attempts}) exceeded")

        try:
            logger.info("Attempting MCP server reconnection", attempt=self._reconnect_attempts + 1)

            # Close existing client if it exists
            if self.client:
                await self.client.aclose()

            # Create new client
            self.client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
            )

            # Test connectivity with health check
            if not await self._is_connection_healthy():
                raise Exception("Health check failed after reconnection")

            self._reconnect_attempts = 0
            logger.info("MCP server reconnection successful")

        except Exception as e:
            self._reconnect_attempts += 1
            delay = self._reconnect_delay * (2 ** (self._reconnect_attempts - 1))  # Exponential backoff

            logger.error(
                "MCP reconnection failed",
                attempt=self._reconnect_attempts,
                next_delay=delay,
                error=str(e)
            )

            await asyncio.sleep(delay)
            raise MCPError(f"Reconnection attempt {self._reconnect_attempts} failed: {str(e)}")

    # Tool management methods

    async def get_capabilities(self) -> Dict[str, Any]:
        """Get MCP server capabilities"""
        return await self._make_request("GET", "/capabilities")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        result = await self._make_request("GET", "/tools")
        return result or []

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """Execute a tool"""
        data = {
            "name": tool_name,
            "arguments": arguments
        }

        params = {"user_id": user_id} if user_id != "default" else None

        result = await self._make_request("POST", "/tools/call", data=data, params=params)
        return result or {"success": False, "error": "No response from server"}

    # Authentication methods

    async def get_auth_status(self, user_id: str = "default") -> Dict[str, Any]:
        """Get authentication status"""
        params = {"user_id": user_id} if user_id != "default" else None
        return await self._make_request("GET", "/auth/status", params=params)

    async def get_login_url(self, user_id: str = "default") -> Dict[str, Any]:
        """Get OAuth login URL"""
        params = {"user_id": user_id} if user_id != "default" else None
        return await self._make_request("GET", "/auth/login-url", params=params)

    async def handle_auth_callback(
        self,
        code: str,
        state: str,
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """Handle OAuth callback"""
        data = {
            "code": code,
            "state": state,
            "user_id": user_id
        }
        return await self._make_request("POST", "/auth/callback", data=data)

    async def logout(self, user_id: str = "default") -> Dict[str, Any]:
        """Logout user"""
        data = {"user_id": user_id}
        return await self._make_request("POST", "/auth/logout", data=data)

    # Batch operations

    async def execute_multiple_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """Execute multiple tools concurrently"""
        try:
            # Create tasks for concurrent execution
            tasks = []
            for tool_call in tool_calls:
                task = asyncio.create_task(
                    self.execute_tool(
                        tool_call["name"],
                        tool_call.get("arguments", {}),
                        user_id
                    )
                )
                tasks.append(task)

            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        "success": False,
                        "error": str(result),
                        "tool_name": tool_calls[i]["name"]
                    })
                else:
                    processed_results.append(result)

            return processed_results

        except Exception as e:
            logger.error("Error executing multiple tools", error=str(e))
            return [{"success": False, "error": str(e)} for _ in tool_calls]

    # Convenience methods for common operations

    async def list_plans(self, user_id: str = "default", group_id: str = None) -> Dict[str, Any]:
        """List plans"""
        arguments = {}
        if group_id:
            arguments["group_id"] = group_id

        return await self.execute_tool("list_plans", arguments, user_id)

    async def create_plan(
        self,
        title: str,
        group_id: str,
        description: str = "",
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """Create a new plan"""
        arguments = {
            "title": title,
            "group_id": group_id,
            "description": description
        }
        return await self.execute_tool("create_plan", arguments, user_id)

    async def list_tasks(
        self,
        plan_id: str,
        user_id: str = "default",
        filter_completed: bool = False
    ) -> Dict[str, Any]:
        """List tasks in a plan"""
        arguments = {
            "plan_id": plan_id,
            "filter_completed": filter_completed
        }
        return await self.execute_tool("list_tasks", arguments, user_id)

    async def create_task(
        self,
        plan_id: str,
        title: str,
        user_id: str = "default",
        description: str = "",
        due_date: str = None,
        priority: int = 5,
        assigned_to: List[str] = None
    ) -> Dict[str, Any]:
        """Create a new task"""
        arguments = {
            "plan_id": plan_id,
            "title": title,
            "description": description,
            "priority": priority
        }

        if due_date:
            arguments["due_date"] = due_date

        if assigned_to:
            arguments["assigned_to"] = assigned_to

        return await self.execute_tool("create_task", arguments, user_id)

    async def update_task(
        self,
        task_id: str,
        user_id: str = "default",
        **updates
    ) -> Dict[str, Any]:
        """Update a task"""
        arguments = {"task_id": task_id, **updates}
        return await self.execute_tool("update_task", arguments, user_id)

    async def search_plans(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search plans"""
        arguments = {
            "query": query,
            "limit": limit
        }
        return await self.execute_tool("search_plans", arguments, user_id)

    # Tool introspection

    async def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool"""
        try:
            tools = await self.list_tools()
            for tool in tools:
                if tool.get("name") == tool_name:
                    return tool
            return None
        except Exception as e:
            logger.error("Error getting tool info", tool=tool_name, error=str(e))
            return None

    async def validate_tool_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate tool arguments against schema"""
        try:
            tool_info = await self.get_tool_info(tool_name)
            if not tool_info:
                return {"valid": False, "error": f"Tool '{tool_name}' not found"}

            # Basic validation - in production, use jsonschema
            input_schema = tool_info.get("inputSchema", {})
            required = input_schema.get("required", [])

            # Check required fields
            missing_fields = [field for field in required if field not in arguments]
            if missing_fields:
                return {
                    "valid": False,
                    "error": f"Missing required fields: {missing_fields}"
                }

            return {"valid": True}

        except Exception as e:
            logger.error("Error validating arguments", tool=tool_name, error=str(e))
            return {"valid": False, "error": str(e)}

    # Connection management

    async def test_connection(self) -> bool:
        """Test connection to MCP server"""
        try:
            result = await self.health_check()
            return result == "healthy"
        except Exception:
            return False

    async def get_server_info(self) -> Dict[str, Any]:
        """Get server information"""
        try:
            health = await self._make_request("GET", "/health")
            capabilities = await self.get_capabilities()

            return {
                "health": health,
                "capabilities": capabilities,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error("Error getting server info", error=str(e))
            return {"error": str(e)}
