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
from .session_auth import SessionAuthManager
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
session_auth_manager: SessionAuthManager = None
graph_client: GraphAPIClient = None
cache_service: CacheService = None
tool_registry: ToolRegistry = None
webhook_manager: WebhookSubscriptionManager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global database, auth_service, session_auth_manager, graph_client, cache_service, tool_registry, webhook_manager

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
            redirect_uri=os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:7100/auth/callback"),
            testing_mode=testing_mode
        )

        # Initialize Graph API client
        graph_client = GraphAPIClient(auth_service, cache_service)

        # Initialize session authentication manager
        session_auth_manager = SessionAuthManager(cache_service, auth_service)

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
    session_id: Optional[str] = Field(default="default", description="Session ID for tracking partial requests")
    user_id: Optional[str] = Field(default="default", description="User ID for authentication context")

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

async def get_session_auth_manager() -> SessionAuthManager:
    """Get session auth manager instance"""
    return session_auth_manager

# Root endpoint for MCP handshake
@app.get("/")
async def root():
    """Root endpoint for MCP protocol handshake"""
    return {
        "name": "Intelligent Teams Planner MCP Server",
        "version": "2.0.0",
        "protocol_version": "1.0",
        "description": "Model Context Protocol server for Microsoft Graph API integration",
        "capabilities": {
            "tools": True,
            "authentication": True,
            "webhooks": True
        }
    }

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
    tool_registry: ToolRegistry = Depends(get_tool_registry),
    session_auth: SessionAuthManager = Depends(get_session_auth_manager),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Execute a tool call with session-based authentication and required field checking"""
    try:
        session_id = tool_call.session_id or "default"
        provided_user_id = tool_call.user_id

        # Validate session and get authenticated user
        if session_id != "default":
            session_data = await session_auth.validate_session(session_id)
            if not session_data:
                # Generate login URL for re-authentication
                try:
                    user_id_for_auth = provided_user_id or "default"
                    login_url = await auth_service.get_login_url(user_id_for_auth)

                    return MCPToolResponse(
                        success=False,
                        error="Session expired. Please re-authenticate to continue.",
                        metadata={
                            "requires_authentication": True,
                            "session_id": session_id,
                            "login_url": login_url,
                            "user_id": user_id_for_auth,
                            "action_required": "Please visit the login_url to re-authenticate"
                        }
                    )
                except Exception as login_error:
                    logger.error("Error generating login URL for expired session", error=str(login_error))
                    return MCPToolResponse(
                        success=False,
                        error="Session expired and unable to generate login URL. Please check authentication service.",
                        metadata={"requires_authentication": True, "session_id": session_id}
                    )
            authenticated_user_id = session_data["user_id"]
        else:
            # For backward compatibility, try to use provided user_id or default
            authenticated_user_id = provided_user_id or "default"

        logger.info("Executing tool", tool=tool_call.name, arguments=tool_call.arguments,
                   session_id=session_id, authenticated_user=authenticated_user_id)

        result = await tool_registry.execute_tool(
            tool_call.name,
            tool_call.arguments,
            authenticated_user_id,
            session_id
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

# Required Fields Completion Model
class MCPFieldCompletion(BaseModel):
    """MCP field completion request"""
    session_id: str = Field(description="Session ID from the partial request")
    tool_name: str = Field(description="Tool name from the partial request")
    provided_values: Dict[str, Any] = Field(default_factory=dict, description="Missing field values")
    user_id: Optional[str] = Field(default="default", description="User ID for authentication context")

@app.post("/tools/complete", response_model=MCPToolResponse)
async def complete_partial_request(
    completion: MCPFieldCompletion,
    tool_registry: ToolRegistry = Depends(get_tool_registry)
):
    """Complete a partial request by providing missing field values"""
    try:
        logger.info("Completing partial request", session_id=completion.session_id,
                   tool=completion.tool_name, provided_values=completion.provided_values)

        result = await tool_registry.complete_partial_request(
            completion.session_id,
            completion.tool_name,
            completion.provided_values,
            completion.user_id or "default"
        )

        return MCPToolResponse(
            success=result.success,
            content=result.content,
            error=result.error,
            metadata=result.metadata
        )

    except Exception as e:
        logger.error("Error completing partial request", session_id=completion.session_id,
                    tool=completion.tool_name, error=str(e))
        return MCPToolResponse(
            success=False,
            error=str(e)
        )

# Session Management Endpoints

class SessionRequest(BaseModel):
    """Session management request"""
    user_id: str = Field(description="User ID to create session for")
    session_timeout: Optional[int] = Field(default=None, description="Session timeout in seconds (optional)")

class SessionResponse(BaseModel):
    """Session management response"""
    success: bool
    session_id: Optional[str] = None
    message: Optional[str] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@app.post("/session/create", response_model=SessionResponse)
async def create_session(
    request: SessionRequest,
    session_auth: SessionAuthManager = Depends(get_session_auth_manager)
):
    """Create a new authenticated session for a user"""
    try:
        session_id = await session_auth.create_authenticated_session(
            request.user_id,
            request.session_timeout
        )

        if session_id:
            session_info = await session_auth.get_session_info(session_id)
            return SessionResponse(
                success=True,
                session_id=session_id,
                message="Session created successfully",
                expires_at=session_info.get("expires_at") if session_info else None
            )
        else:
            return SessionResponse(
                success=False,
                error="Failed to create session. User may not be authenticated."
            )

    except Exception as e:
        logger.error("Error creating session", user_id=request.user_id, error=str(e))
        return SessionResponse(
            success=False,
            error=str(e)
        )

@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session_info(
    session_id: str,
    session_auth: SessionAuthManager = Depends(get_session_auth_manager)
):
    """Get information about a session"""
    try:
        session_info = await session_auth.get_session_info(session_id)

        if session_info:
            return SessionResponse(
                success=True,
                session_id=session_id,
                message="Session is valid",
                expires_at=session_info.get("expires_at")
            )
        else:
            return SessionResponse(
                success=False,
                error="Session not found or expired"
            )

    except Exception as e:
        logger.error("Error getting session info", session_id=session_id[:8], error=str(e))
        return SessionResponse(
            success=False,
            error=str(e)
        )

@app.delete("/session/{session_id}", response_model=SessionResponse)
async def invalidate_session(
    session_id: str,
    session_auth: SessionAuthManager = Depends(get_session_auth_manager)
):
    """Invalidate a session (logout)"""
    try:
        success = await session_auth.invalidate_session(session_id)

        if success:
            return SessionResponse(
                success=True,
                message="Session invalidated successfully"
            )
        else:
            return SessionResponse(
                success=False,
                error="Session not found"
            )

    except Exception as e:
        logger.error("Error invalidating session", session_id=session_id[:8], error=str(e))
        return SessionResponse(
            success=False,
            error=str(e)
        )

@app.post("/session/{session_id}/close", response_model=SessionResponse)
async def close_session_on_browser_exit(
    session_id: str,
    session_auth: SessionAuthManager = Depends(get_session_auth_manager)
):
    """
    Optimized endpoint for browser window close events
    This endpoint is designed to work with navigator.sendBeacon for reliable cleanup
    """
    try:
        success = await session_auth.invalidate_session(session_id)

        # Always return success for browser close events to avoid blocking page unload
        # Log the actual result but don't fail the request
        if success:
            logger.info("Session closed on browser exit", session_id=session_id[:8])
        else:
            logger.warning("Session already expired/invalid on browser exit", session_id=session_id[:8])

        return SessionResponse(
            success=True,
            message="Session close request processed"
        )

    except Exception as e:
        # Always return success for browser close to avoid blocking page unload
        logger.error("Error processing browser session close", session_id=session_id[:8], error=str(e))
        return SessionResponse(
            success=True,
            message="Session close request processed with error"
        )

@app.post("/session/{session_id}/activity", response_model=SessionResponse)
async def update_session_activity(
    session_id: str,
    session_auth: SessionAuthManager = Depends(get_session_auth_manager)
):
    """
    Update browser activity for session management
    This endpoint can be called periodically by the client to maintain session
    """
    try:
        success = await session_auth.update_browser_activity(session_id)

        if success:
            return SessionResponse(
                success=True,
                message="Session activity updated successfully"
            )
        else:
            return SessionResponse(
                success=False,
                error="Session not found or expired"
            )

    except Exception as e:
        logger.error("Error updating session activity", session_id=session_id[:8], error=str(e))
        return SessionResponse(
            success=False,
            error=str(e)
        )

@app.get("/session/{session_id}/check", response_model=SessionResponse)
async def check_session_with_reauth(
    session_id: str,
    user_id: str = "default",
    session_auth: SessionAuthManager = Depends(get_session_auth_manager),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Check session status and provide re-authentication information if needed
    This endpoint helps clients handle session expiration gracefully
    """
    try:
        session_info = await session_auth.get_session_info(session_id)

        if session_info:
            return SessionResponse(
                success=True,
                session_id=session_id,
                message="Session is valid and active",
                expires_at=session_info.get("expires_at")
            )
        else:
            # Session is expired or invalid, provide re-authentication info
            try:
                login_url = await auth_service.get_login_url(user_id)

                return SessionResponse(
                    success=False,
                    error="Session expired or invalid. Re-authentication required.",
                    metadata={
                        "requires_authentication": True,
                        "login_url": login_url,
                        "user_id": user_id,
                        "action_required": "Please visit the login_url to re-authenticate and create a new session"
                    }
                )
            except Exception as auth_error:
                logger.error("Error generating login URL for session check", error=str(auth_error))
                return SessionResponse(
                    success=False,
                    error="Session expired and authentication service unavailable. Please try again later."
                )

    except Exception as e:
        logger.error("Error checking session with reauth", session_id=session_id[:8], error=str(e))
        return SessionResponse(
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

@app.get("/auth/callback")
@app.post("/auth/callback")
async def auth_callback(
    code: str,
    state: str,
    user_id: str = "default",
    create_session: bool = True,
    auth_service: AuthService = Depends(get_auth_service),
    session_auth: SessionAuthManager = Depends(get_session_auth_manager)
):
    """Handle OAuth callback and optionally create session"""
    try:
        success = await auth_service.handle_callback(code, state, user_id)

        if success:
            response_data = {"success": True, "message": "Authentication successful"}

            # Automatically create a session for the authenticated user
            if create_session:
                session_id = await session_auth.create_authenticated_session(user_id)
                if session_id:
                    session_info = await session_auth.get_session_info(session_id)
                    response_data.update({
                        "session_created": True,
                        "session_id": session_id,
                        "expires_at": session_info.get("expires_at") if session_info else None
                    })
                    logger.info("Auto-created session after authentication", user_id=user_id, session_id=session_id[:8])
                else:
                    response_data["session_created"] = False
                    logger.warning("Failed to auto-create session after authentication", user_id=user_id)

            return response_data
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