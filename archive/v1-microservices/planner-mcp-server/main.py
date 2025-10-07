import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List
import uuid

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
import redis.asyncio as redis
import structlog
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response

from models.planner import (
    TaskCreateRequest, TaskUpdateRequest, TaskQueryRequest, TaskResponse,
    PlanCreateRequest, BucketCreateRequest, PlanResponse, BucketResponse,
    DocumentGenerationRequest, APIResponse, MCPToolDefinition, HealthResponse
)
from services.oauth import GraphAuthService
from services.graph_api import GraphAPIService
from services.cache import CacheService

# Configure structured logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status_code'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')

app = FastAPI(
    title="Planner MCP Server",
    description="Microsoft Graph API integration server for Planner management",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
redis_client: redis.Redis = None
auth_service: GraphAuthService = None
graph_service: GraphAPIService = None
cache_service: CacheService = None

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global redis_client, auth_service, graph_service, cache_service

    try:
        # Initialize Redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established", redis_url=redis_url)

        # Initialize services
        auth_service = GraphAuthService(redis_client)
        graph_service = GraphAPIService(redis_client)
        cache_service = CacheService(redis_client)

        logger.info("Planner MCP Server started successfully")

    except Exception as e:
        logger.error("Failed to initialize services", error=str(e))
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global redis_client

    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")

# Middleware for metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Collect metrics for all requests"""
    start_time = datetime.utcnow()

    response = await call_next(request)

    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code
    ).inc()

    duration = (datetime.utcnow() - start_time).total_seconds()
    REQUEST_DURATION.observe(duration)

    return response

# Dependency for getting user access token
async def get_access_token(request: Request) -> str:
    """Extract and validate user access token"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split(" ")[1]

    # Validate token
    if not await auth_service.validate_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    return token

async def get_user_id_from_token(access_token: str) -> str:
    """Extract user ID from access token"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            user_data = response.json()
            return user_data.get("id")
    except Exception as e:
        logger.error("Error getting user ID", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid access token")

# Health and metrics endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    services_status = {}

    # Check Redis
    try:
        await redis_client.ping()
        services_status["redis"] = "healthy"
    except Exception as e:
        services_status["redis"] = f"unhealthy: {str(e)}"

    # Check if all required env vars are present
    required_vars = ["MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_TENANT_ID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        services_status["config"] = f"missing: {', '.join(missing_vars)}"
    else:
        services_status["config"] = "healthy"

    overall_status = "healthy" if all("healthy" in status for status in services_status.values()) else "unhealthy"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        services=services_status
    )

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")

# Authentication endpoints
@app.get("/auth/login")
async def login():
    """Initiate OAuth login flow"""
    state = str(uuid.uuid4())
    auth_url = auth_service.get_auth_url(state)

    # Store state in Redis for validation (optional)
    await redis_client.setex(f"auth_state:{state}", 600, "pending")  # 10 minute expiry

    return {"auth_url": auth_url, "state": state}

@app.get("/auth/callback")
async def auth_callback(code: str, state: str):
    """Handle OAuth callback"""
    try:
        # Validate state (optional)
        stored_state = await redis_client.get(f"auth_state:{state}")
        if not stored_state:
            raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

        # Exchange code for tokens
        token_data = await auth_service.exchange_code_for_tokens(code, state)

        # Clean up state
        await redis_client.delete(f"auth_state:{state}")

        # Warm up cache for the user
        try:
            await cache_service.warm_cache(token_data["access_token"], token_data["user_id"])
        except Exception as e:
            logger.warning("Cache warm-up failed", error=str(e))

        return {
            "success": True,
            "message": "Authentication successful",
            "user_id": token_data["user_id"],
            "expires_at": token_data["expires_at"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication callback error", error=str(e))
        raise HTTPException(status_code=500, detail="Authentication failed")

@app.post("/auth/logout")
async def logout(request: Request):
    """Logout user and revoke tokens"""
    try:
        # Get user ID from token
        access_token = await get_access_token(request)
        user_id = await get_user_id_from_token(access_token)

        # Revoke tokens
        success = await auth_service.revoke_tokens(user_id)

        # Clear user cache
        await cache_service.clear_user_cache(user_id)

        return {"success": success, "message": "Logged out successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Logout error", error=str(e))
        raise HTTPException(status_code=500, detail="Logout failed")

# MCP Tool Discovery
@app.get("/tools", response_model=List[MCPToolDefinition])
async def get_available_tools():
    """Get list of available MCP tools"""
    tools = [
        MCPToolDefinition(
            name="planner.create_task",
            description="Create a new task in Microsoft Planner",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "plan_name": {"type": "string", "description": "Name of the plan"},
                    "bucket_name": {"type": "string", "description": "Name of the bucket (optional)"},
                    "assignee_email": {"type": "string", "description": "Email of assignee (optional)"},
                    "due_date": {"type": "string", "format": "date-time", "description": "Due date (optional)"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "description": "Priority level"},
                    "description": {"type": "string", "description": "Task description (optional)"}
                },
                "required": ["title", "plan_name"]
            }
        ),
        MCPToolDefinition(
            name="planner.get_user_tasks",
            description="Get tasks for the current user with optional filtering",
            parameters={
                "type": "object",
                "properties": {
                    "plan_name": {"type": "string", "description": "Filter by plan name"},
                    "assignee_email": {"type": "string", "description": "Filter by assignee ('me' for current user)"},
                    "completion_status": {"type": "string", "enum": ["completed", "in_progress", "not_started"]},
                    "due_date_filter": {"type": "string", "enum": ["overdue", "today", "this_week", "this_month"]},
                    "title_contains": {"type": "string", "description": "Filter by title containing text"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Max results"}
                }
            }
        ),
        MCPToolDefinition(
            name="planner.update_task",
            description="Update an existing task",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to update"},
                    "title": {"type": "string", "description": "New title"},
                    "due_date": {"type": "string", "format": "date-time", "description": "New due date"},
                    "percent_complete": {"type": "integer", "minimum": 0, "maximum": 100},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                    "description": {"type": "string", "description": "New description"},
                    "assignee_email": {"type": "string", "description": "New assignee email"}
                },
                "required": ["task_id"]
            }
        ),
        MCPToolDefinition(
            name="planner.delete_task",
            description="Delete a task",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to delete"}
                },
                "required": ["task_id"]
            }
        ),
        MCPToolDefinition(
            name="planner.get_user_plans",
            description="Get all plans for the current user",
            parameters={"type": "object", "properties": {}}
        ),
        MCPToolDefinition(
            name="planner.create_plan",
            description="Create a new plan",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Plan title"},
                    "group_id": {"type": "string", "description": "Microsoft 365 Group ID (optional)"}
                },
                "required": ["title"]
            }
        ),
        MCPToolDefinition(
            name="planner.create_bucket",
            description="Create a new bucket in a plan",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Bucket name"},
                    "plan_name": {"type": "string", "description": "Plan name"}
                },
                "required": ["name", "plan_name"]
            }
        ),
        MCPToolDefinition(
            name="planner.generate_document",
            description="Generate a document report from Planner data",
            parameters={
                "type": "object",
                "properties": {
                    "plan_name": {"type": "string", "description": "Plan name for report"},
                    "document_type": {"type": "string", "enum": ["pdf", "word", "powerpoint"]},
                    "include_completed": {"type": "boolean", "description": "Include completed tasks"},
                    "include_in_progress": {"type": "boolean", "description": "Include in-progress tasks"},
                    "include_not_started": {"type": "boolean", "description": "Include not started tasks"}
                },
                "required": ["plan_name", "document_type"]
            }
        )
    ]

    return tools

# MCP Tool Endpoints
@app.post("/tools/planner.create_task", response_model=APIResponse)
async def create_task_tool(request: TaskCreateRequest, access_token: str = Depends(get_access_token)):
    """MCP tool: Create a new task"""
    try:
        task = await graph_service.create_task(access_token, request)
        return APIResponse(
            success=True,
            message=f"Task '{task.title}' created successfully",
            data=task.model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")

@app.post("/tools/planner.get_user_tasks", response_model=APIResponse)
async def get_user_tasks_tool(request: TaskQueryRequest, access_token: str = Depends(get_access_token)):
    """MCP tool: Get user tasks with filtering"""
    try:
        tasks = await graph_service.get_user_tasks(access_token, request)
        return APIResponse(
            success=True,
            message=f"Found {len(tasks)} tasks",
            data={"tasks": [task.model_dump() for task in tasks]}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user tasks", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get tasks: {str(e)}")

@app.post("/tools/planner.update_task", response_model=APIResponse)
async def update_task_tool(request: TaskUpdateRequest, access_token: str = Depends(get_access_token)):
    """MCP tool: Update an existing task"""
    try:
        task = await graph_service.update_task(access_token, request)
        return APIResponse(
            success=True,
            message=f"Task '{task.title}' updated successfully",
            data=task.model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update task: {str(e)}")

@app.post("/tools/planner.delete_task", response_model=APIResponse)
async def delete_task_tool(task_id: str, access_token: str = Depends(get_access_token)):
    """MCP tool: Delete a task"""
    try:
        success = await graph_service.delete_task(access_token, task_id)
        return APIResponse(
            success=success,
            message="Task deleted successfully" if success else "Failed to delete task"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting task", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")

@app.post("/tools/planner.get_user_plans", response_model=APIResponse)
async def get_user_plans_tool(access_token: str = Depends(get_access_token)):
    """MCP tool: Get all user plans"""
    try:
        plans = await graph_service.get_user_plans(access_token)
        return APIResponse(
            success=True,
            message=f"Found {len(plans)} plans",
            data={"plans": [plan.model_dump() for plan in plans]}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user plans", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get plans: {str(e)}")

@app.post("/tools/planner.create_plan", response_model=APIResponse)
async def create_plan_tool(request: PlanCreateRequest, access_token: str = Depends(get_access_token)):
    """MCP tool: Create a new plan"""
    try:
        plan = await graph_service.create_plan(access_token, request)
        return APIResponse(
            success=True,
            message=f"Plan '{plan.title}' created successfully",
            data=plan.model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating plan", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create plan: {str(e)}")

@app.post("/tools/planner.create_bucket", response_model=APIResponse)
async def create_bucket_tool(request: BucketCreateRequest, access_token: str = Depends(get_access_token)):
    """MCP tool: Create a new bucket"""
    try:
        bucket = await graph_service.create_bucket(access_token, request)
        return APIResponse(
            success=True,
            message=f"Bucket '{bucket.name}' created successfully",
            data=bucket.model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating bucket", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create bucket: {str(e)}")

@app.post("/tools/planner.generate_document", response_model=APIResponse)
async def generate_document_tool(request: DocumentGenerationRequest, access_token: str = Depends(get_access_token)):
    """MCP tool: Generate document report"""
    try:
        # This would call the document generation service
        # For now, return a placeholder response
        return APIResponse(
            success=True,
            message=f"Document generation requested for plan '{request.plan_name}'",
            data={
                "plan_name": request.plan_name,
                "document_type": request.document_type,
                "status": "Document generation service integration pending"
            }
        )
    except Exception as e:
        logger.error("Error generating document", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate document: {str(e)}")

# Cache management endpoints
@app.get("/cache/stats")
async def get_cache_stats(access_token: str = Depends(get_access_token)):
    """Get cache statistics"""
    stats = await cache_service.get_stats()
    return {"cache_stats": stats}

@app.delete("/cache/clear")
async def clear_user_cache(request: Request, access_token: str = Depends(get_access_token)):
    """Clear cache for current user"""
    user_id = await get_user_id_from_token(access_token)
    deleted_count = await cache_service.clear_user_cache(user_id)
    return {"deleted_entries": deleted_count, "message": "User cache cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)