"""
Protocol translation layer for OpenWebUI to MCP conversion
Handles the translation between OpenWebUI tool calls and MCP method invocations
"""

import uuid
import json
from typing import Dict, Any, List, AsyncGenerator
from datetime import datetime, timezone
import structlog

try:
    from .mcp_client import MCPClient
except ImportError:
    # For testing
    from mcp_client import MCPClient

logger = structlog.get_logger(__name__)


class ProtocolTranslator:
    """Translates between OpenWebUI and MCP protocol formats"""

    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client
        self.request_counter = 0

    def generate_request_id(self) -> str:
        """Generate unique request ID for MCP protocol"""
        self.request_counter += 1
        return f"req_{uuid.uuid4().hex[:8]}_{self.request_counter}"

    async def translate_openwebui_to_mcp(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Translate OpenWebUI tool call to MCP method invocation format

        OpenWebUI Format:
        {
            "name": "create_task",
            "arguments": {
                "title": "Review quarterly reports",
                "due_date": "2025-10-15",
                "plan_id": "abc123"
            }
        }

        MCP Format:
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "create_task",
                "arguments": {
                    "title": "Review quarterly reports",
                    "due_date": "2025-10-15",
                    "plan_id": "abc123"
                }
            },
            "id": "req_12345"
        }
        """
        try:
            request_id = self.generate_request_id()

            # Validate tool exists
            tool_info = await self.mcp_client.get_tool_info(tool_name)
            if not tool_info:
                raise ValueError(f"Tool '{tool_name}' not found in MCP server")

            # Validate arguments against tool schema
            validation_result = await self.mcp_client.validate_tool_arguments(tool_name, arguments)
            if not validation_result.get("valid", False):
                raise ValueError(f"Invalid arguments: {validation_result.get('error', 'Unknown validation error')}")

            # Create MCP method invocation
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": request_id
            }

            logger.info(
                "Translated OpenWebUI to MCP",
                tool_name=tool_name,
                user_id=user_id,
                request_id=request_id
            )

            return mcp_request

        except Exception as e:
            logger.error(
                "Failed to translate OpenWebUI to MCP",
                tool_name=tool_name,
                error=str(e)
            )
            raise

    def translate_mcp_to_openwebui(
        self,
        mcp_response: Dict[str, Any],
        original_request: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Translate MCP response to OpenWebUI-compatible format

        MCP Success Response:
        {
            "jsonrpc": "2.0",
            "result": {
                "success": true,
                "content": {
                    "id": "task_123",
                    "title": "Review quarterly reports",
                    "status": "created"
                }
            },
            "id": "req_12345"
        }

        MCP Error Response:
        {
            "jsonrpc": "2.0",
            "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": {"field": "title", "issue": "required"}
            },
            "id": "req_12345"
        }

        OpenWebUI Response:
        {
            "success": true,
            "data": {...},
            "message": "Tool executed successfully",
            "correlation_id": "req_12345",
            "metadata": {...}
        }
        """
        try:
            request_id = mcp_response.get("id", "unknown")

            # Handle MCP error response
            if "error" in mcp_response:
                error = mcp_response["error"]
                error_code = error.get("code", -1)
                error_message = error.get("message", "Unknown error")
                error_data = error.get("data", {})

                # Map MCP error codes to HTTP-like status
                status_mapping = {
                    -32700: "parse_error",      # Parse error
                    -32600: "invalid_request",  # Invalid Request
                    -32601: "method_not_found",  # Method not found
                    -32602: "invalid_params",   # Invalid params
                    -32603: "internal_error",   # Internal error
                }

                error_type = status_mapping.get(error_code, "unknown_error")

                openwebui_response = {
                    "success": False,
                    "error": {
                        "type": error_type,
                        "message": error_message,
                        "details": error_data,
                        "correlation_id": request_id
                    },
                    "correlation_id": request_id,
                    "metadata": {
                        "mcp_error_code": error_code,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }

                logger.warning(
                    "Translated MCP error response",
                    error_type=error_type,
                    error_message=error_message,
                    request_id=request_id
                )

                return openwebui_response

            # Handle MCP success response
            elif "result" in mcp_response:
                result = mcp_response["result"]

                # Extract success status
                success = result.get("success", True)
                content = result.get("content", {})
                message = result.get("message", "Tool executed successfully" if success else "Tool execution failed")

                openwebui_response = {
                    "success": success,
                    "data": content,
                    "message": message,
                    "correlation_id": request_id,
                    "metadata": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "mcp_version": "2.0"
                    }
                }

                # Add additional metadata if present
                if "metadata" in result:
                    openwebui_response["metadata"].update(result["metadata"])

                logger.info(
                    "Translated MCP success response",
                    success=success,
                    request_id=request_id
                )

                return openwebui_response

            else:
                # Invalid MCP response format
                raise ValueError("Invalid MCP response format: missing 'result' or 'error'")

        except Exception as e:
            logger.error("Failed to translate MCP to OpenWebUI", error=str(e))

            # Return error response if translation fails
            return {
                "success": False,
                "error": {
                    "type": "translation_error",
                    "message": f"Failed to translate MCP response: {str(e)}",
                    "details": {},
                    "correlation_id": mcp_response.get("id", "unknown")
                },
                "correlation_id": mcp_response.get("id", "unknown"),
                "metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "translation_error": True
                }
            }

    def convert_openapi_params_to_mcp_args(
        self,
        openapi_params: Dict[str, Any],
        tool_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert OpenAPI parameters to MCP arguments format
        Handles parameter validation and type conversion
        """
        try:
            mcp_args = {}
            schema_properties = tool_schema.get("inputSchema", {}).get("properties", {})

            for param_name, param_value in openapi_params.items():
                if param_name in schema_properties:
                    param_schema = schema_properties[param_name]

                    # Convert parameter based on schema type
                    converted_value = self._convert_parameter_value(
                        param_value,
                        param_schema
                    )

                    mcp_args[param_name] = converted_value
                else:
                    # Pass through unknown parameters (with warning)
                    logger.warning(
                        "Unknown parameter passed through",
                        param=param_name,
                        value=param_value
                    )
                    mcp_args[param_name] = param_value

            return mcp_args

        except Exception as e:
            logger.error("Failed to convert OpenAPI params to MCP args", error=str(e))
            raise

    def _convert_parameter_value(self, value: Any, param_schema: Dict[str, Any]) -> Any:
        """Convert parameter value based on schema type"""
        try:
            param_type = param_schema.get("type", "string")

            # Type conversion based on schema
            if param_type == "integer":
                return int(value) if value is not None else None
            elif param_type == "number":
                return float(value) if value is not None else None
            elif param_type == "boolean":
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on")
                return bool(value) if value is not None else None
            elif param_type == "array":
                if isinstance(value, str):
                    # Try to parse JSON array string
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        # Split comma-separated string
                        return [item.strip() for item in value.split(",")]
                return list(value) if value is not None else []
            elif param_type == "object":
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse object parameter", value=value)
                        return {}
                return dict(value) if value is not None else {}
            else:  # string or unknown type
                return str(value) if value is not None else None

        except Exception as e:
            logger.warning(
                "Failed to convert parameter value",
                value=value,
                schema=param_schema,
                error=str(e)
            )
            # Return original value if conversion fails
            return value

    async def batch_translate_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Translate multiple OpenWebUI tool calls to MCP format
        Useful for batch operations
        """
        try:
            mcp_requests = []

            for tool_call in tool_calls:
                tool_name = tool_call.get("name")
                arguments = tool_call.get("arguments", {})

                if not tool_name:
                    logger.warning("Skipping tool call without name", tool_call=tool_call)
                    continue

                mcp_request = await self.translate_openwebui_to_mcp(
                    tool_name, arguments, user_id
                )
                mcp_requests.append(mcp_request)

            logger.info(
                "Batch translated tool calls",
                count=len(mcp_requests),
                user_id=user_id
            )

            return mcp_requests

        except Exception as e:
            logger.error("Failed to batch translate tools", error=str(e))
            raise

    async def translate_streaming_mcp_to_openwebui(
        self,
        mcp_stream: AsyncGenerator[Dict[str, Any], None],
        original_request: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Translate streaming MCP responses to OpenWebUI format
        Handles real-time streaming for long-running operations
        """
        try:
            async for mcp_chunk in mcp_stream:
                try:
                    # Translate each chunk
                    openwebui_chunk = self.translate_mcp_to_openwebui(mcp_chunk, original_request)

                    # Add streaming metadata
                    openwebui_chunk["streaming"] = True
                    openwebui_chunk["chunk_id"] = uuid.uuid4().hex[:8]

                    yield openwebui_chunk

                except Exception as e:
                    logger.error("Error translating streaming chunk", error=str(e))
                    # Yield error chunk
                    yield {
                        "success": False,
                        "streaming": True,
                        "error": {
                            "type": "stream_translation_error",
                            "message": f"Failed to translate stream chunk: {str(e)}",
                            "details": {},
                            "correlation_id": mcp_chunk.get("id", "unknown")
                        },
                        "correlation_id": mcp_chunk.get("id", "unknown"),
                        "metadata": {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "streaming_error": True
                        }
                    }

        except Exception as e:
            logger.error("Error in streaming translation", error=str(e))
            # Yield final error
            yield {
                "success": False,
                "streaming": True,
                "stream_end": True,
                "error": {
                    "type": "stream_error",
                    "message": f"Streaming translation failed: {str(e)}",
                    "details": {},
                    "correlation_id": "unknown"
                },
                "metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "stream_error": True
                }
            }

    def format_success_response_with_structure(
        self,
        data: Any,
        message: str = "Operation completed successfully",
        correlation_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Format success response with proper JSON structure for OpenWebUI
        Ensures consistent response format across all successful operations
        """
        response = {
            "success": True,
            "data": data,
            "message": message,
            "correlation_id": correlation_id or f"resp_{uuid.uuid4().hex[:8]}",
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_type": "success",
                "translator_version": "1.0.0"
            }
        }

        # Merge additional metadata
        if metadata:
            response["metadata"].update(metadata)

        return response

    def format_error_response_with_context(
        self,
        error_type: str,
        message: str,
        details: Dict[str, Any] = None,
        correlation_id: str = None,
        http_status: int = 500,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Format error response with comprehensive context preservation
        Maintains error context and status codes across translation layers
        """
        response = {
            "success": False,
            "error": {
                "type": error_type,
                "message": message,
                "details": details or {},
                "correlation_id": correlation_id or f"err_{uuid.uuid4().hex[:8]}",
                "http_status": http_status
            },
            "correlation_id": correlation_id or f"err_{uuid.uuid4().hex[:8]}",
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_type": "error",
                "error_context": context or {},
                "translator_version": "1.0.0"
            }
        }

        return response

    def enhance_mcp_response_translation(
        self,
        mcp_response: Dict[str, Any],
        original_request: Dict[str, Any] = None,
        preserve_raw: bool = False
    ) -> Dict[str, Any]:
        """
        Enhanced MCP response translation with better context preservation
        """
        try:
            # Get basic translation
            base_response = self.translate_mcp_to_openwebui(mcp_response, original_request)

            # Enhance with additional context
            if preserve_raw:
                base_response["metadata"]["raw_mcp_response"] = mcp_response

            # Add request correlation if available
            if original_request:
                base_response["metadata"]["original_request_id"] = original_request.get("id")
                base_response["metadata"]["request_method"] = original_request.get("method")

            # Enhanced error context for error responses
            if not base_response.get("success", False) and "error" in mcp_response:
                mcp_error = mcp_response["error"]

                # Add more detailed error mapping
                error_context = {
                    "mcp_error_code": mcp_error.get("code"),
                    "mcp_error_data": mcp_error.get("data", {}),
                    "error_category": self._categorize_error(mcp_error.get("code", -1)),
                    "retry_recommended": self._should_retry_error(mcp_error.get("code", -1))
                }

                base_response["metadata"]["error_context"] = error_context

            return base_response

        except Exception as e:
            logger.error("Error in enhanced MCP response translation", error=str(e))
            return self.format_error_response_with_context(
                "translation_enhancement_error",
                f"Failed to enhance response translation: {str(e)}",
                context={"original_mcp_response": mcp_response}
            )

    def _categorize_error(self, error_code: int) -> str:
        """Categorize MCP error codes for better error handling"""
        if error_code == -32700:
            return "parse_error"
        elif error_code == -32600:
            return "invalid_request"
        elif error_code == -32601:
            return "method_not_found"
        elif error_code == -32602:
            return "invalid_params"
        elif error_code == -32603:
            return "internal_error"
        elif -32099 <= error_code <= -32000:
            return "server_error"
        else:
            return "application_error"

    def _should_retry_error(self, error_code: int) -> bool:
        """Determine if an error should be retried"""
        # Retry on server errors but not on client errors
        return error_code == -32603 or (-32099 <= error_code <= -32000)

    def get_translation_statistics(self) -> Dict[str, Any]:
        """Get translation performance statistics"""
        return {
            "total_requests": self.request_counter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "translator_version": "1.0.0"
        }
