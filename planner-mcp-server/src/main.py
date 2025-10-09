"""
Intelligent Teams Planner - MCP Server v2.0
Model Context Protocol server for Microsoft Graph API integration
"""

import os
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog
import asyncio

from .database import Database
from .auth import AuthService
from .graph_client import GraphAPIClient
from .tools import ToolRegistry, Tool, ToolResult
from .cache import CacheService
from .graph.webhooks import WebhookSubscriptionManager, create_webhook_router

# Configure structured logging with DEBUG level
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(10),  # DEBUG level
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

# Global services
database: Database = None
auth_service: AuthService = None
graph_client: GraphAPIClient = None
cache_service: CacheService = None
tool_registry: ToolRegistry = None
webhook_manager: WebhookSubscriptionManager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global database, auth_service, graph_client, cache_service, tool_registry, webhook_manager

    try:
        # Initialize database
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL must be set")

        database = Database(database_url)
        await database.initialize()

        # Initialize cache service
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        cache_service = CacheService(redis_url)
        await cache_service.initialize()

        # Initialize auth service
        testing_mode = os.getenv("TESTING_MODE", "false").lower() == "true"
        auth_service = AuthService(
            client_id=os.getenv("MICROSOFT_CLIENT_ID", "test-client-id"),
            client_secret=os.getenv("MICROSOFT_CLIENT_SECRET", "test-client-secret"),
            tenant_id=os.getenv("MICROSOFT_TENANT_ID", "test-tenant-id"),
            cache_service=cache_service,
            testing_mode=testing_mode
        )

        # Initialize Graph API client
        graph_client = GraphAPIClient(auth_service, cache_service)

        # Initialize tool registry
        tool_registry = ToolRegistry(graph_client, database, cache_service)
        await tool_registry.initialize()

        # Initialize webhook subscription manager
        webhook_manager = WebhookSubscriptionManager(database, cache_service, graph_client)
        await webhook_manager.initialize()

        # Add webhook router to app
        if os.getenv("WEBHOOKS_ENABLED", "true").lower() == "true":
            webhook_router = create_webhook_router(webhook_manager)
            app.include_router(webhook_router)

        logger.info("MCP Server initialized successfully")

        yield

    except Exception as e:
        logger.error("Failed to initialize MCP Server", error=str(e))
        raise
    finally:
        # Cleanup
        if webhook_manager:
            await webhook_manager.shutdown()
        if cache_service:
            await cache_service.close()
        if database:
            await database.close()

# Create FastAPI app
app = FastAPI(
    title="Intelligent Teams Planner MCP Server",
    description="Model Context Protocol server for Microsoft Graph API integration",
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

# Include webhook router - will be added after app startup
# when webhook_manager is initialized

# MCP Protocol Models
class MCPCapabilities(BaseModel):
    """MCP server capabilities"""
    tools: Dict[str, Any] = Field(default_factory=dict)
    prompts: Dict[str, Any] = Field(default_factory=dict)
    resources: Dict[str, Any] = Field(default_factory=dict)

class MCPTool(BaseModel):
    """MCP tool definition"""
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class MCPToolCall(BaseModel):
    """MCP tool call request"""
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

class MCPToolResponse(BaseModel):
    """MCP tool response"""
    success: bool
    content: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AuthStatus(BaseModel):
    """Authentication status"""
    authenticated: bool
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    tenant_id: Optional[str] = None
    expires_at: Optional[str] = None

# Dependency injection
async def get_database() -> Database:
    """Get database instance"""
    return database

async def get_auth_service() -> AuthService:
    """Get auth service instance"""
    return auth_service

async def get_graph_client() -> GraphAPIClient:
    """Get graph client instance"""
    return graph_client

async def get_tool_registry() -> ToolRegistry:
    """Get tool registry instance"""
    return tool_registry

async def get_webhook_manager() -> WebhookSubscriptionManager:
    """Get webhook manager instance"""
    return webhook_manager

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connectivity
        db_status = await database.health_check()

        # Check cache connectivity
        cache_status = await cache_service.health_check()

        # Check Graph API connectivity (if authenticated)
        graph_status = "not_authenticated"
        try:
            if await auth_service.has_valid_token("system"):
                test_result = await graph_client.test_connection()
                graph_status = "healthy" if test_result else "unhealthy"
        except Exception:
            graph_status = "unhealthy"

        overall_status = "healthy" if all([
            db_status == "healthy",
            cache_status == "healthy"
        ]) else "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": db_status,
                "cache": cache_status,
                "graph_api": graph_status
            },
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }

# MCP Protocol Endpoints

@app.get("/capabilities", response_model=MCPCapabilities)
async def get_capabilities(
    tool_registry: ToolRegistry = Depends(get_tool_registry)
):
    """Get MCP server capabilities"""
    try:
        tools = await tool_registry.get_tool_definitions()

        return MCPCapabilities(
            tools={
                "listTools": {"description": "List all available tools"},
                **{tool.name: {
                    "description": tool.description,
                    "parameters": tool.parameters
                } for tool in tools}
            }
        )
    except Exception as e:
        logger.error("Error getting capabilities", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tools", response_model=List[MCPTool])
async def list_tools(
    tool_registry: ToolRegistry = Depends(get_tool_registry)
):
    """List all available tools"""
    try:
        tools = await tool_registry.get_tool_definitions()

        return [
            MCPTool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters
            )
            for tool in tools
        ]
    except Exception as e:
        logger.error("Error listing tools", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/call", response_model=MCPToolResponse)
async def call_tool(
    tool_call: MCPToolCall,
    tool_registry: ToolRegistry = Depends(get_tool_registry)
):
    """Execute a tool call"""
    try:
        logger.info("Executing tool", tool=tool_call.name, arguments=tool_call.arguments)

        result = await tool_registry.execute_tool(
            tool_call.name,
            tool_call.arguments
        )

        return MCPToolResponse(
            success=result.success,
            content=result.content,
            error=result.error,
            metadata=result.metadata
        )

    except Exception as e:
        logger.error("Error executing tool", tool=tool_call.name, error=str(e))
        return MCPToolResponse(
            success=False,
            error=str(e)
        )

# Authentication Endpoints

@app.get("/auth/status", response_model=AuthStatus)
async def get_auth_status(
    user_id: str = "default",
    auth_service: AuthService = Depends(get_auth_service)
):
    """Get authentication status"""
    try:
        is_authenticated = await auth_service.has_valid_token(user_id)

        if is_authenticated:
            token_info = await auth_service.get_token_info(user_id)
            return AuthStatus(
                authenticated=True,
                user_id=token_info.get("user_id"),
                user_name=token_info.get("user_name"),
                tenant_id=token_info.get("tenant_id"),
                expires_at=token_info.get("expires_at")
            )
        else:
            return AuthStatus(authenticated=False)

    except Exception as e:
        logger.error("Error checking auth status", error=str(e))
        return AuthStatus(authenticated=False)

@app.get("/auth/login-url")
async def get_login_url(
    user_id: str = "default",
    auth_service: AuthService = Depends(get_auth_service)
):
    """Get OAuth login URL"""
    try:
        login_url = await auth_service.get_login_url(user_id)
        return {"login_url": login_url}
    except Exception as e:
        logger.error("Error generating login URL", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/callback")
async def auth_callback(
    code: str,
    state: str,
    user_id: str = "default",
    auth_service: AuthService = Depends(get_auth_service)
):
    """Handle OAuth callback"""
    try:
        success = await auth_service.handle_callback(code, state, user_id)

        if success:
            return {"success": True, "message": "Authentication successful"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Authentication failed"
            )

    except Exception as e:
        logger.error("Error handling auth callback", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/logout")
async def logout(
    user_id: str = "default",
    auth_service: AuthService = Depends(get_auth_service)
):
    """Logout user"""
    try:
        await auth_service.clear_tokens(user_id)
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        logger.error("Error during logout", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Development endpoints
if os.getenv("ENVIRONMENT") == "development":
    @app.get("/debug/cache")
    async def debug_cache():
        """Debug cache contents"""
        try:
            stats = await cache_service.get_stats()
            return stats
        except Exception as e:
            return {"error": str(e)}

def main():
    """Main entry point"""
    try:
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "7100"))

        logger.info("Starting Intelligent Teams Planner MCP Server", host=host, port=port)

        import uvicorn
        uvicorn.run(
            "src.main:app",
            host=host,
            port=port,
            reload=os.getenv("ENVIRONMENT") == "development",
            log_level="info"
        )

    except Exception as e:
        logger.error("Failed to start MCP server", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()