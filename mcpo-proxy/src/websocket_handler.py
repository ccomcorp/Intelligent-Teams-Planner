"""
WebSocket handler for real-time communication between OpenWebUI and MCP
Task 4: Add WebSocket support for real-time communication
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Set
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
import structlog

try:
    from .mcp_client import MCPClient
    from .protocol_translator import ProtocolTranslator
except ImportError:
    # For testing
    from mcp_client import MCPClient
    from protocol_translator import ProtocolTranslator

logger = structlog.get_logger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections and message routing"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        self.user_connections: Dict[str, Set[str]] = {}  # user_id -> connection_ids

    async def connect(self, websocket: WebSocket, connection_id: str, user_id: str = "default") -> bool:
        """Accept and register a new WebSocket connection"""
        try:
            await websocket.accept()

            self.active_connections[connection_id] = websocket
            self.connection_metadata[connection_id] = {
                "user_id": user_id,
                "connected_at": datetime.now(timezone.utc),
                "message_count": 0,
                "last_activity": datetime.now(timezone.utc)
            }

            # Track user connections
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)

            logger.info("WebSocket connection established", connection_id=connection_id, user_id=user_id)
            return True

        except Exception as e:
            logger.error("Failed to establish WebSocket connection", error=str(e))
            return False

    async def disconnect(self, connection_id: str):
        """Disconnect and cleanup a WebSocket connection"""
        try:
            if connection_id in self.active_connections:
                metadata = self.connection_metadata.get(connection_id, {})
                user_id = metadata.get("user_id", "default")

                # Remove from tracking
                del self.active_connections[connection_id]
                del self.connection_metadata[connection_id]

                # Remove from user connections
                if user_id in self.user_connections:
                    self.user_connections[user_id].discard(connection_id)
                    if not self.user_connections[user_id]:
                        del self.user_connections[user_id]

                logger.info("WebSocket connection closed", connection_id=connection_id, user_id=user_id)

        except Exception as e:
            logger.error("Error during WebSocket disconnect", connection_id=connection_id, error=str(e))

    async def send_personal_message(self, message: Dict[str, Any], connection_id: str):
        """Send message to specific connection"""
        try:
            if connection_id in self.active_connections:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(json.dumps(message))

                # Update metadata
                if connection_id in self.connection_metadata:
                    self.connection_metadata[connection_id]["message_count"] += 1
                    self.connection_metadata[connection_id]["last_activity"] = datetime.now(timezone.utc)

        except WebSocketDisconnect:
            await self.disconnect(connection_id)
        except Exception as e:
            logger.error("Error sending WebSocket message", connection_id=connection_id, error=str(e))

    async def send_to_user(self, message: Dict[str, Any], user_id: str):
        """Send message to all connections for a specific user"""
        if user_id in self.user_connections:
            connection_ids = list(self.user_connections[user_id])
            for connection_id in connection_ids:
                await self.send_personal_message(message, connection_id)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all active connections"""
        connection_ids = list(self.active_connections.keys())
        for connection_id in connection_ids:
            await self.send_personal_message(message, connection_id)

    def get_connection_info(self) -> Dict[str, Any]:
        """Get information about active connections"""
        return {
            "total_connections": len(self.active_connections),
            "unique_users": len(self.user_connections),
            "connections_by_user": {
                user_id: len(conn_ids)
                for user_id, conn_ids in self.user_connections.items()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


class WebSocketMCPBridge:
    """Bridges WebSocket messages to MCP protocol"""

    def __init__(self, mcp_client: MCPClient, protocol_translator: ProtocolTranslator):
        self.mcp_client = mcp_client
        self.protocol_translator = protocol_translator
        self.connection_manager = WebSocketConnectionManager()

    async def handle_websocket_connection(self, websocket: WebSocket, user_id: str = "default"):
        """Handle a new WebSocket connection with full lifecycle management"""
        connection_id = f"ws_{uuid.uuid4().hex[:8]}"

        try:
            # Establish connection
            connected = await self.connection_manager.connect(websocket, connection_id, user_id)
            if not connected:
                return

            # Send welcome message
            welcome_message = {
                "type": "connection_established",
                "connection_id": connection_id,
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "capabilities": ["tool_execution", "streaming", "real_time_updates"],
                "supported_message_types": ["tool_call", "ping", "status_request"]
            }
            await self.connection_manager.send_personal_message(welcome_message, connection_id)

            # Main message loop
            while True:
                try:
                    # Receive message from WebSocket
                    data = await websocket.receive_text()
                    message = json.loads(data)

                    logger.debug(
                        "WebSocket message received",
                        connection_id=connection_id,
                        message_type=message.get("type")
                    )

                    # Process message
                    await self._process_websocket_message(message, connection_id, user_id)

                except WebSocketDisconnect:
                    logger.info("WebSocket client disconnected", connection_id=connection_id)
                    break
                except json.JSONDecodeError:
                    await self._send_error(connection_id, "invalid_json", "Invalid JSON in message")
                except Exception as e:
                    logger.error("Error processing WebSocket message", connection_id=connection_id, error=str(e))
                    await self._send_error(connection_id, "message_processing_error", str(e))

        except Exception as e:
            logger.error("WebSocket connection error", connection_id=connection_id, error=str(e))
        finally:
            await self.connection_manager.disconnect(connection_id)

    async def _process_websocket_message(self, message: Dict[str, Any], connection_id: str, user_id: str):
        """Process incoming WebSocket message"""
        message_type = message.get("type")
        correlation_id = message.get("correlation_id", f"ws_{uuid.uuid4().hex[:8]}")

        if message_type == "tool_call":
            await self._handle_tool_call(message, connection_id, user_id, correlation_id)
        elif message_type == "ping":
            await self._handle_ping(connection_id, correlation_id)
        elif message_type == "status_request":
            await self._handle_status_request(connection_id, correlation_id)
        elif message_type == "streaming_tool_call":
            await self._handle_streaming_tool_call(message, connection_id, user_id, correlation_id)
        else:
            await self._send_error(connection_id, "unknown_message_type", f"Unknown message type: {message_type}")

    async def _handle_tool_call(self, message: Dict[str, Any], connection_id: str, user_id: str, correlation_id: str):
        """Handle tool execution request via WebSocket"""
        try:
            tool_data = message.get("data", {})
            tool_name = tool_data.get("name")
            arguments = tool_data.get("arguments", {})

            if not tool_name:
                await self._send_error(connection_id, "missing_tool_name", "Tool name is required")
                return

            # Translate to MCP format
            mcp_request = await self.protocol_translator.translate_openwebui_to_mcp(
                tool_name, arguments, user_id
            )

            # Send acknowledgment
            ack_message = {
                "type": "tool_call_acknowledged",
                "correlation_id": correlation_id,
                "mcp_request_id": mcp_request["id"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.connection_manager.send_personal_message(ack_message, connection_id)

            # Execute tool via MCP client
            result = await self.mcp_client.execute_tool(tool_name, arguments, user_id)

            # Translate response back to OpenWebUI format
            openwebui_response = self.protocol_translator.translate_mcp_to_openwebui({
                "jsonrpc": "2.0",
                "result": result,
                "id": mcp_request["id"]
            })

            # Send result
            response_message = {
                "type": "tool_call_result",
                "correlation_id": correlation_id,
                "data": openwebui_response,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.connection_manager.send_personal_message(response_message, connection_id)

        except Exception as e:
            logger.error("Error handling tool call", connection_id=connection_id, error=str(e))
            await self._send_error(connection_id, "tool_execution_error", str(e), correlation_id)

    async def _handle_streaming_tool_call(
        self, message: Dict[str, Any], connection_id: str, user_id: str, correlation_id: str
    ):
        """Handle streaming tool execution request"""
        try:
            tool_data = message.get("data", {})
            tool_name = tool_data.get("name")
            arguments = tool_data.get("arguments", {})

            if not tool_name:
                await self._send_error(connection_id, "missing_tool_name", "Tool name is required")
                return

            # Send stream start acknowledgment
            start_message = {
                "type": "streaming_started",
                "correlation_id": correlation_id,
                "tool_name": tool_name,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.connection_manager.send_personal_message(start_message, connection_id)

            # Execute tool and stream results
            # Note: This would require the MCP client to support streaming
            # For now, we'll simulate streaming by chunking the response
            result = await self.mcp_client.execute_tool(tool_name, arguments, user_id)

            # Simulate streaming chunks (in production, this would be real streaming)
            chunks = self._simulate_streaming_chunks(result)

            for i, chunk in enumerate(chunks):
                chunk_message = {
                    "type": "streaming_chunk",
                    "correlation_id": correlation_id,
                    "chunk_index": i,
                    "data": chunk,
                    "is_final": i == len(chunks) - 1,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await self.connection_manager.send_personal_message(chunk_message, connection_id)
                await asyncio.sleep(0.1)  # Small delay between chunks

            # Send stream end
            end_message = {
                "type": "streaming_ended",
                "correlation_id": correlation_id,
                "total_chunks": len(chunks),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.connection_manager.send_personal_message(end_message, connection_id)

        except Exception as e:
            logger.error("Error handling streaming tool call", connection_id=connection_id, error=str(e))
            await self._send_error(connection_id, "streaming_error", str(e), correlation_id)

    def _simulate_streaming_chunks(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Simulate streaming by breaking result into chunks"""
        if not result.get("success"):
            return [result]

        content = result.get("content", {})
        if isinstance(content, dict) and len(content) > 1:
            # Split dictionary into chunks
            items = list(content.items())
            chunk_size = max(1, len(items) // 3)  # Create ~3 chunks
            chunks = []
            for i in range(0, len(items), chunk_size):
                chunk_items = items[i:i + chunk_size]
                chunks.append(dict(chunk_items))
            return chunks
        else:
            return [content]

    async def _handle_ping(self, connection_id: str, correlation_id: str):
        """Handle ping message"""
        pong_message = {
            "type": "pong",
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.connection_manager.send_personal_message(pong_message, connection_id)

    async def _handle_status_request(self, connection_id: str, correlation_id: str):
        """Handle status request"""
        try:
            mcp_health = await self.mcp_client.health_check()
            connection_info = self.connection_manager.get_connection_info()

            status_message = {
                "type": "status_response",
                "correlation_id": correlation_id,
                "data": {
                    "mcp_server_health": mcp_health,
                    "websocket_connections": connection_info,
                    "proxy_status": "healthy"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await self.connection_manager.send_personal_message(status_message, connection_id)

        except Exception as e:
            await self._send_error(connection_id, "status_error", str(e), correlation_id)

    async def _send_error(self, connection_id: str, error_type: str, message: str, correlation_id: str = None):
        """Send error message to WebSocket client"""
        error_message = {
            "type": "error",
            "correlation_id": correlation_id or f"err_{uuid.uuid4().hex[:8]}",
            "error": {
                "type": error_type,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        await self.connection_manager.send_personal_message(error_message, connection_id)

    async def broadcast_to_users(self, message: Dict[str, Any], user_ids: List[str] = None):
        """Broadcast message to specific users or all users"""
        if user_ids:
            for user_id in user_ids:
                await self.connection_manager.send_to_user(message, user_id)
        else:
            await self.connection_manager.broadcast(message)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection statistics"""
        return self.connection_manager.get_connection_info()


# WebSocket message format examples:

# Tool Call Message:
# {
#   "type": "tool_call",
#   "correlation_id": "req_12345",
#   "data": {
#     "name": "create_task",
#     "arguments": {
#       "title": "Test Task",
#       "due_date": "2025-12-31"
#     }
#   }
# }

# Streaming Tool Call Message:
# {
#   "type": "streaming_tool_call",
#   "correlation_id": "stream_12345",
#   "data": {
#     "name": "generate_report",
#     "arguments": {
#       "report_type": "quarterly"
#     }
#   }
# }

# Ping Message:
# {
#   "type": "ping",
#   "correlation_id": "ping_12345"
# }

# Status Request Message:
# {
#   "type": "status_request",
#   "correlation_id": "status_12345"
# }
