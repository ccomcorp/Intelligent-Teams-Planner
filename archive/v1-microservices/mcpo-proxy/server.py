import os
from datetime import datetime
from typing import Dict, Any
import asyncio

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from translators.mcp_to_openapi import MCPToOpenAPITranslator
from translators.openapi_spec import OpenAPISpecGenerator

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

app = FastAPI(
    title="MCPO - MCP to OpenAPI Proxy",
    description="Proxy service that translates Model Context Protocol (MCP) to OpenAPI for OpenWebUI integration",
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
translator: MCPToOpenAPITranslator = None
spec_generator: OpenAPISpecGenerator = None
cached_spec: Dict[str, Any] = None
last_spec_update: datetime = None

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global translator, spec_generator

    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

    translator = MCPToOpenAPITranslator(mcp_server_url)
    spec_generator = OpenAPISpecGenerator("Planner Tools API", "1.0.0")

    # Pre-load the OpenAPI spec
    await refresh_openapi_spec()

    logger.info("MCPO Proxy started successfully", mcp_server_url=mcp_server_url)

async def refresh_openapi_spec():
    """Refresh the cached OpenAPI specification"""
    global cached_spec, last_spec_update

    try:
        tools = await translator.discover_tools()
        cached_spec = spec_generator.generate_spec_from_tools(tools)
        last_spec_update = datetime.utcnow()

        logger.info("OpenAPI specification refreshed", tools_count=len(tools))

    except Exception as e:
        logger.error("Failed to refresh OpenAPI spec", error=str(e))
        # Keep the old spec if refresh fails
        if cached_spec is None:
            # Create a minimal spec if we have no cached spec
            cached_spec = {
                "openapi": "3.0.3",
                "info": {
                    "title": "Planner Tools API",
                    "description": "Error loading tools from MCP server",
                    "version": "1.0.0"
                },
                "paths": {}
            }

def get_authorization_header(request: Request) -> str:
    """Extract authorization header from request"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header required")
    return auth_header

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        mcp_health = await translator.health_check()

        return {
            "status": "healthy" if mcp_health["mcp_server_status"] == "healthy" else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "proxy_version": "1.0.0",
            **mcp_health
        }

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }

@app.get("/openapi.json")
async def get_openapi_spec():
    """Get the dynamically generated OpenAPI specification"""
    global cached_spec, last_spec_update

    # Refresh spec if it's older than 5 minutes or doesn't exist
    if (cached_spec is None or
        last_spec_update is None or
        (datetime.utcnow() - last_spec_update).total_seconds() > 300):
        await refresh_openapi_spec()

    return cached_spec

@app.get("/")
async def root():
    """Root endpoint with service information"""
    server_info = await translator.get_server_info()

    return {
        "service": "MCPO - MCP to OpenAPI Proxy",
        "version": "1.0.0",
        "description": "Proxy service for Model Context Protocol integration with OpenWebUI",
        "endpoints": {
            "health": "/health",
            "openapi_spec": "/openapi.json",
            "tools": "/tools/*",
            "server_info": "/info"
        },
        "mcp_server": server_info
    }

@app.get("/info")
async def get_server_info():
    """Get detailed information about the proxy and MCP server"""
    return await translator.get_server_info()

@app.get("/tools")
async def list_tools():
    """List all available tools from MCP server"""
    try:
        tools = await translator.discover_tools()
        return {
            "tools": tools,
            "count": len(tools),
            "last_updated": last_spec_update.isoformat() if last_spec_update else None
        }
    except Exception as e:
        logger.error("Error listing tools", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list tools")

@app.post("/tools/{tool_name}")
async def execute_tool(
    tool_name: str,
    request: Request,
    authorization: str = Depends(get_authorization_header)
):
    """Execute a tool via MCP protocol"""
    try:
        # Get request body
        request_body = await request.json()

        logger.info("Executing tool via proxy", tool_name=tool_name)

        # Validate parameters (optional)
        is_valid = await translator.validate_parameters(tool_name, request_body)
        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid parameters")

        # Execute the tool on MCP server
        result = await translator.execute_tool(
            tool_name=tool_name,
            parameters=request_body,
            authorization_header=authorization
        )

        # Format response for OpenAPI consumers
        formatted_result = translator.format_openapi_response(result)

        logger.info("Tool executed successfully via proxy", tool_name=tool_name)
        return formatted_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error executing tool", tool_name=tool_name, error=str(e))
        error_response = translator.format_error_response(
            error_message=str(e),
            error_code="TOOL_EXECUTION_ERROR"
        )
        raise HTTPException(status_code=500, detail=error_response)

@app.get("/tools/{tool_name}/schema")
async def get_tool_schema(tool_name: str):
    """Get the parameter schema for a specific tool"""
    try:
        tools = await translator.discover_tools()
        tool_def = next((tool for tool in tools if tool.get("name") == tool_name), None)

        if not tool_def:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

        return {
            "tool_name": tool_name,
            "description": tool_def.get("description"),
            "parameters": tool_def.get("parameters", {}),
            "required": tool_def.get("parameters", {}).get("required", [])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting tool schema", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get tool schema")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": "Request failed",
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=request.url.path,
        exc_info=True
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "error": "An unexpected error occurred",
            "status_code": 500
        }
    )

# Background task to refresh spec periodically
async def periodic_spec_refresh():
    """Periodically refresh the OpenAPI specification"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            await refresh_openapi_spec()
        except Exception as e:
            logger.error("Error in periodic spec refresh", error=str(e))

@app.on_event("startup")
async def start_background_tasks():
    """Start background tasks"""
    asyncio.create_task(periodic_spec_refresh())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)