"""
MCPO Proxy - OpenWebUI to MCP Translation Layer v2.0
Translates OpenWebUI's OpenAPI format to Model Context Protocol
"""

import os
import sys
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from .mcp_client import MCPClient
from .openai_translator import OpenAITranslator
from .cache import ProxyCache
from .openapi_generator import OpenAPIGenerator
from .dynamic_routes import DynamicRouteGenerator
from .protocol_translator import ProtocolTranslator
from .websocket_handler import WebSocketMCPBridge
from .security_middleware import SecurityMiddleware, AuthenticationHandler, SecurityValidator
from .monitoring import HealthChecker, metrics_collector, alert_manager
from .rate_limiter import initialize_performance_optimizer, get_performance_optimizer

# Configure structured logging
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

# Global services
mcp_client: MCPClient = None
openai_translator: OpenAITranslator = None
proxy_cache: ProxyCache = None
openapi_generator: OpenAPIGenerator = None
dynamic_routes: DynamicRouteGenerator = None
protocol_translator: ProtocolTranslator = None
websocket_bridge: WebSocketMCPBridge = None
security_middleware: SecurityMiddleware = None
auth_handler: AuthenticationHandler = None
security_validator: SecurityValidator = None
health_checker: HealthChecker = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global mcp_client, openai_translator, proxy_cache, openapi_generator
    global dynamic_routes, protocol_translator, websocket_bridge
    global security_middleware, auth_handler, security_validator, health_checker

    try:
        # Initialize cache
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        proxy_cache = ProxyCache(redis_url)
        await proxy_cache.initialize()

        # Initialize MCP client
        mcp_server_url = os.getenv("MCP_SERVER_URL", "http://planner-mcp-server:8000")
        mcp_client = MCPClient(mcp_server_url)
        await mcp_client.initialize()

        # Initialize security components
        security_middleware = SecurityMiddleware()
        auth_handler = AuthenticationHandler(security_middleware)
        security_validator = SecurityValidator()

        # Initialize performance optimizer
        initialize_performance_optimizer(proxy_cache)

        # Initialize health checker
        health_checker = HealthChecker(mcp_client, proxy_cache)

        # Initialize OpenAPI generator
        openapi_generator = OpenAPIGenerator()

        # Initialize protocol translator
        protocol_translator = ProtocolTranslator(mcp_client)

        # Initialize WebSocket bridge
        websocket_bridge = WebSocketMCPBridge(mcp_client, protocol_translator)

        # Initialize dynamic routes
        dynamic_routes = DynamicRouteGenerator(mcp_client, openapi_generator)
        await dynamic_routes.initialize()

        # Initialize OpenAI translator
        openai_translator = OpenAITranslator(mcp_client, proxy_cache)
        await openai_translator.initialize()

        # Add dynamic routes to app
        app.include_router(dynamic_routes.get_router())

        logger.info("MCPO Proxy initialized successfully with all components")

        yield

    except Exception as e:
        logger.error("Failed to initialize MCPO Proxy", error=str(e))
        raise
    finally:
        # Cleanup
        if proxy_cache:
            await proxy_cache.close()
        if mcp_client:
            await mcp_client.close()

# Create FastAPI app
app = FastAPI(
    title="MCPO Proxy",
    description="OpenWebUI to Model Context Protocol translation layer",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI-compatible API models


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    name: Optional[str] = Field(None, description="Message author name")


class ChatCompletionRequest(BaseModel):
    """Chat completion request model"""
    model: str = Field(default="planner-assistant", description="Model name")
    messages: List[ChatMessage] = Field(..., description="Conversation messages")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    temperature: Optional[float] = Field(0.7, description="Sampling temperature")
    stream: bool = Field(False, description="Stream response")
    user: Optional[str] = Field(None, description="User identifier")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")


class ChatCompletionChoice(BaseModel):
    """Chat completion choice"""
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    """Token usage information"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Chat completion response"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ModelInfo(BaseModel):
    """Model information"""
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    """Models list response"""
    object: str = "list"
    data: List[ModelInfo]

# Dependency injection


async def get_mcp_client() -> MCPClient:
    """Get MCP client instance"""
    return mcp_client


async def get_translator() -> OpenAITranslator:
    """Get translator instance"""
    return openai_translator


async def get_cache() -> ProxyCache:
    """Get cache instance"""
    return proxy_cache


async def get_openapi_generator() -> OpenAPIGenerator:
    """Get OpenAPI generator instance"""
    return openapi_generator


async def get_dynamic_routes() -> DynamicRouteGenerator:
    """Get dynamic routes instance"""
    return dynamic_routes


async def get_protocol_translator() -> ProtocolTranslator:
    """Get protocol translator instance"""
    return protocol_translator

# Health check


@app.get("/health")
async def health_check():
    """Enhanced health check endpoint with comprehensive system status"""
    try:
        if health_checker:
            return await health_checker.check_system_health()
        else:
            # Fallback to basic health check
            mcp_status = await mcp_client.health_check()
            cache_status = await proxy_cache.health_check()

            overall_status = "healthy" if all([
                mcp_status == "healthy",
                cache_status == "healthy"
            ]) else "degraded"

            return {
                "status": overall_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "services": {
                    "mcp_server": mcp_status,
                    "cache": cache_status
                },
                "version": "2.0.0"
            }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

# OpenAI-compatible endpoints


@app.get("/v1/models", response_model=ModelsResponse)
async def list_models():
    """List available models (OpenAI compatibility)"""
    return ModelsResponse(
        data=[
            ModelInfo(
                id="planner-assistant",
                created=int(datetime.now(timezone.utc).timestamp()),
                owned_by="intelligent-teams-planner"
            )
        ]
    )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    translator: OpenAITranslator = Depends(get_translator)
):
    """Create chat completion (OpenAI compatibility)"""
    try:
        logger.info("Processing chat completion", user=request.user, model=request.model)

        # Translate OpenAI request to MCP tool calls
        response = await translator.process_chat_completion(request)

        return response

    except Exception as e:
        logger.error("Error processing chat completion", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# MCP tool discovery endpoints


@app.get("/tools")
async def list_tools(
    dynamic_routes: DynamicRouteGenerator = Depends(get_dynamic_routes)
):
    """List available MCP tools with their API schemas"""
    try:
        tools = await dynamic_routes.get_available_tools()
        return {
            "tools": tools,
            "total_count": len(tools),
            "base_url": "/v1/tools"
        }
    except Exception as e:
        logger.error("Error listing tools", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/tools")
async def list_tools_v1(
    dynamic_routes: DynamicRouteGenerator = Depends(get_dynamic_routes)
):
    """List available tools (v1 endpoint for OpenWebUI compatibility)"""
    try:
        tools = await dynamic_routes.get_available_tools()
        return {
            "tools": tools,
            "total_count": len(tools),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("Error listing tools v1", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/capabilities")
async def get_capabilities(
    mcp_client: MCPClient = Depends(get_mcp_client)
):
    """Get MCP server capabilities"""
    try:
        capabilities = await mcp_client.get_capabilities()
        return capabilities
    except Exception as e:
        logger.error("Error getting capabilities", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Direct MCP tool execution endpoint


@app.post("/tools/{tool_name}/execute")
async def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: str = "default",
    mcp_client: MCPClient = Depends(get_mcp_client)
):
    """Execute MCP tool directly"""
    try:
        logger.info("Executing tool directly", tool=tool_name, user_id=user_id)

        result = await mcp_client.execute_tool(tool_name, arguments, user_id)

        return {
            "success": result.get("success", False),
            "content": result.get("content"),
            "error": result.get("error"),
            "metadata": result.get("metadata", {})
        }

    except Exception as e:
        logger.error("Error executing tool", tool=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Authentication proxy endpoints


@app.get("/auth/status")
async def get_auth_status(
    user_id: str = "default",
    mcp_client: MCPClient = Depends(get_mcp_client)
):
    """Get authentication status from MCP server"""
    try:
        auth_status = await mcp_client.get_auth_status(user_id)
        return auth_status
    except Exception as e:
        logger.error("Error getting auth status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/login-url")
async def get_login_url(
    user_id: str = "default",
    mcp_client: MCPClient = Depends(get_mcp_client)
):
    """Get OAuth login URL from MCP server"""
    try:
        result = await mcp_client.get_login_url(user_id)
        return result
    except Exception as e:
        logger.error("Error getting login URL", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/callback")
async def auth_callback(
    code: str,
    state: str,
    user_id: str = "default",
    mcp_client: MCPClient = Depends(get_mcp_client)
):
    """Handle OAuth callback via MCP server"""
    try:
        result = await mcp_client.handle_auth_callback(code, state, user_id)
        return result
    except Exception as e:
        logger.error("Error handling auth callback", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# OpenAPI specification endpoints


@app.get("/openapi.json")
async def get_openapi_spec():
    """Get OpenAPI specification"""
    return app.openapi()


@app.get("/v1/openapi.json")
async def get_dynamic_openapi_spec(
    mcp_client: MCPClient = Depends(get_mcp_client),
    openapi_generator: OpenAPIGenerator = Depends(get_openapi_generator)
):
    """Get dynamically generated OpenAPI specification from MCP tools"""
    try:
        # Get current tools from MCP server
        tools = await mcp_client.list_tools()

        # Generate OpenAPI specification
        spec = openapi_generator.generate_openapi_spec(tools)

        return spec
    except Exception as e:
        logger.error("Error generating dynamic OpenAPI spec", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time communication


@app.websocket("/v1/ws")
async def websocket_endpoint(websocket: WebSocket, user_id: str = "default"):
    """WebSocket endpoint for real-time MCP tool execution"""
    if websocket_bridge:
        await websocket_bridge.handle_websocket_connection(websocket, user_id)
    else:
        await websocket.close(code=1011, reason="WebSocket bridge not available")

# Monitoring and metrics endpoints


@app.get("/metrics")
async def get_metrics():
    """Get comprehensive system metrics"""
    try:
        metrics = metrics_collector.get_metrics_summary()

        # Add performance metrics if available
        performance_optimizer = get_performance_optimizer()
        if performance_optimizer:
            metrics["performance"] = performance_optimizer.get_performance_metrics()

        return metrics
    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts")
async def get_alerts():
    """Get active system alerts"""
    try:
        return {
            "active_alerts": alert_manager.get_active_alerts(),
            "alert_history": alert_manager.alert_history,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("Error getting alerts", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an active alert"""
    try:
        success = alert_manager.acknowledge_alert(alert_id)
        if success:
            return {"message": "Alert acknowledged", "alert_id": alert_id}
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
    except Exception as e:
        logger.error("Error acknowledging alert", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Info endpoint for debugging


@app.get("/info")
async def get_proxy_info(
    protocol_translator: ProtocolTranslator = Depends(get_protocol_translator)
):
    """Get proxy information"""
    try:
        translation_stats = protocol_translator.get_translation_statistics()

        return {
            "name": "MCPO Proxy",
            "version": "2.0.0",
            "description": "OpenWebUI to Model Context Protocol translation layer with dynamic routes",
            "mcp_server_url": os.getenv("MCP_SERVER_URL", "http://planner-mcp-server:8000"),
            "supported_endpoints": [
                "/v1/chat/completions",
                "/v1/models",
                "/v1/tools",
                "/v1/tools/{tool_name}",
                "/v1/openapi.json",
                "/tools",
                "/capabilities",
                "/auth/status",
                "/auth/login-url"
            ],
            "features": [
                "Dynamic route generation",
                "Protocol translation",
                "OpenAPI specification generation",
                "MCP tool discovery",
                "Connection pooling",
                "Error recovery"
            ],
            "translation_stats": translation_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("Error getting proxy info", error=str(e))
        return {
            "name": "MCPO Proxy",
            "version": "2.0.0",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


def main():
    """Main entry point"""
    try:
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8001"))

        logger.info("Starting MCPO Proxy", host=host, port=port)

        import uvicorn
        uvicorn.run(
            "src.main:app",
            host=host,
            port=port,
            reload=os.getenv("ENVIRONMENT") == "development",
            log_level="info"
        )

    except Exception as e:
        logger.error("Failed to start MCPO Proxy", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
