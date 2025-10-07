#!/usr/bin/env python3
"""
OAuth Callback Server for Microsoft Teams and Planner Authentication
Simple web server to handle OAuth callbacks and test real API connectivity
"""

import asyncio
import os
from urllib.parse import urlparse, parse_qs
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import structlog

from src.cache import CacheService
from src.auth import AuthService, AuthenticationError
from src.teams_planner_client import SimpleTeamsPlannerClient, TeamsPlannierError

# Load environment variables
load_dotenv()

logger = structlog.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Teams Planner OAuth Handler", version="1.0.0")

# Global services
cache_service = None
auth_service = None
teams_client = None

@app.on_event("startup")
async def startup():
    """Initialize services on startup"""
    global cache_service, auth_service, teams_client

    try:
        # Initialize cache service
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        cache_service = CacheService(redis_url)
        await cache_service.initialize()
        logger.info("Cache service initialized")

        # Initialize auth service
        auth_service = AuthService(
            client_id=os.getenv("AZURE_CLIENT_ID"),
            client_secret=os.getenv("AZURE_CLIENT_SECRET"),
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            cache_service=cache_service,
            redirect_uri="http://localhost:8888/auth/callback"
        )
        logger.info("Auth service initialized")

        # Initialize Teams/Planner client
        teams_client = SimpleTeamsPlannerClient(auth_service)
        logger.info("Teams/Planner client initialized")

    except Exception as e:
        logger.error("Failed to initialize services", error=str(e))
        raise

@app.on_event("shutdown")
async def shutdown():
    """Cleanup services on shutdown"""
    global cache_service
    if cache_service:
        await cache_service.close()
        logger.info("Services cleaned up")

@app.get("/")
async def root():
    """Root endpoint with instructions"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Teams Planner OAuth Handler</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .success { color: green; }
            .error { color: red; }
            .info { color: blue; }
            pre { background: #f4f4f4; padding: 15px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Microsoft Teams & Planner OAuth Handler</h1>
            <p class="info">This server is running and ready to handle OAuth callbacks!</p>

            <h2>Next Steps:</h2>
            <ol>
                <li>Run the MVP test CLI: <code>python mvp_test_cli.py</code></li>
                <li>Copy the generated OAuth URL</li>
                <li>Visit the URL in your browser to authenticate</li>
                <li>You'll be redirected back here after authentication</li>
            </ol>

            <p><strong>Server Status:</strong> ✅ Ready for OAuth callbacks</p>
            <p><strong>Callback URL:</strong> http://localhost:8888/auth/callback</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    """Handle OAuth callback from Microsoft"""
    global auth_service, teams_client

    try:
        # Extract query parameters
        query_params = dict(request.query_params)
        code = query_params.get("code")
        state = query_params.get("state")
        error = query_params.get("error")

        if error:
            logger.error("OAuth error received", error=error, description=query_params.get("error_description"))
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html>
                <head><title>OAuth Error</title></head>
                <body>
                    <h1>❌ OAuth Authentication Error</h1>
                    <p><strong>Error:</strong> {error}</p>
                    <p><strong>Description:</strong> {query_params.get("error_description", "No description provided")}</p>
                    <p><a href="/">← Back to Home</a></p>
                </body>
                </html>
                """,
                status_code=400
            )

        if not code or not state:
            logger.error("Missing required parameters", code=bool(code), state=bool(state))
            raise HTTPException(status_code=400, detail="Missing code or state parameter")

        logger.info("Received OAuth callback", state=state[:10], has_code=bool(code))

        # Handle the OAuth callback
        success = await auth_service.handle_callback(code, state, user_id="oauth_test_user")

        if not success:
            raise AuthenticationError("Failed to handle OAuth callback")

        logger.info("OAuth authentication successful")

        # Test Microsoft Graph API connectivity
        test_results = await test_real_connectivity("oauth_test_user")

        # Generate success page
        html_content = generate_success_page(test_results)
        return HTMLResponse(content=html_content, status_code=200)

    except AuthenticationError as e:
        logger.error("Authentication error", error=str(e))
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Authentication Error</title></head>
            <body>
                <h1>❌ Authentication Failed</h1>
                <p><strong>Error:</strong> {str(e)}</p>
                <p><a href="/">← Back to Home</a></p>
            </body>
            </html>
            """,
            status_code=400
        )
    except Exception as e:
        logger.error("Unexpected error in OAuth callback", error=str(e))
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Server Error</title></head>
            <body>
                <h1>❌ Server Error</h1>
                <p><strong>Error:</strong> {str(e)}</p>
                <p><a href="/">← Back to Home</a></p>
            </body>
            </html>
            """,
            status_code=500
        )

async def test_real_connectivity(user_id: str) -> dict:
    """Test real Microsoft Graph API connectivity"""
    global teams_client

    results = {
        "user_info": None,
        "teams": [],
        "plans": [],
        "tasks": [],
        "test_task": None,
        "errors": []
    }

    try:
        logger.info("Testing real Microsoft Graph API connectivity")

        # Test 1: Get user info
        try:
            user_info = await auth_service.get_user_info(user_id)
            if user_info:
                results["user_info"] = user_info
                logger.info("✅ User info retrieved", display_name=user_info.get("displayName"))
            else:
                results["errors"].append("Failed to get user info")
        except Exception as e:
            results["errors"].append(f"User info error: {str(e)}")

        # Test 2: Get user teams
        try:
            teams = await teams_client.get_user_teams(user_id)
            results["teams"] = teams
            logger.info("✅ Teams retrieved", count=len(teams))
        except Exception as e:
            results["errors"].append(f"Teams error: {str(e)}")

        # Test 3: Get plans for first team (if available)
        if results["teams"]:
            try:
                first_team = results["teams"][0]
                plans = await teams_client.get_team_planner_plans(user_id, first_team["id"])
                results["plans"] = plans
                logger.info("✅ Plans retrieved", count=len(plans), team=first_team.get("displayName"))
            except Exception as e:
                results["errors"].append(f"Plans error: {str(e)}")

        # Test 4: Get tasks for first plan (if available)
        if results["plans"]:
            try:
                first_plan = results["plans"][0]
                tasks = await teams_client.get_plan_tasks(user_id, first_plan["id"])
                results["tasks"] = tasks
                logger.info("✅ Tasks retrieved", count=len(tasks), plan=first_plan.get("title"))
            except Exception as e:
                results["errors"].append(f"Tasks error: {str(e)}")

        # Test 5: Create a test task (if we have a plan)
        if results["plans"]:
            try:
                first_plan = results["plans"][0]
                test_task = await teams_client.create_planner_task(
                    user_id,
                    first_plan["id"],
                    f"OAuth Test Task - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    "This task was created via OAuth authentication test to verify Microsoft Graph API connectivity."
                )
                results["test_task"] = test_task
                logger.info("✅ Test task created", task_id=test_task.get("id"))
            except Exception as e:
                results["errors"].append(f"Task creation error: {str(e)}")

        logger.info("Microsoft Graph API connectivity test completed",
                   errors=len(results["errors"]),
                   teams=len(results["teams"]),
                   plans=len(results["plans"]))

    except Exception as e:
        logger.error("Connectivity test failed", error=str(e))
        results["errors"].append(f"General connectivity error: {str(e)}")

    return results

def generate_success_page(test_results: dict) -> str:
    """Generate HTML success page with test results"""
    user_info = test_results.get("user_info", {})
    teams = test_results.get("teams", [])
    plans = test_results.get("plans", [])
    tasks = test_results.get("tasks", [])
    test_task = test_results.get("test_task")
    errors = test_results.get("errors", [])

    # Build results HTML
    results_html = ""

    if user_info:
        results_html += f"""
        <div class="success">
            <h3>✅ User Authentication</h3>
            <p><strong>Name:</strong> {user_info.get('displayName', 'N/A')}</p>
            <p><strong>Email:</strong> {user_info.get('mail', user_info.get('userPrincipalName', 'N/A'))}</p>
            <p><strong>ID:</strong> {user_info.get('id', 'N/A')}</p>
        </div>
        """

    if teams:
        results_html += f"""
        <div class="success">
            <h3>✅ Microsoft Teams Access</h3>
            <p><strong>Teams Found:</strong> {len(teams)}</p>
            <ul>
        """
        for team in teams[:5]:  # Show first 5 teams
            results_html += f"<li>{team.get('displayName', 'Unknown Team')}</li>"
        if len(teams) > 5:
            results_html += f"<li>... and {len(teams) - 5} more teams</li>"
        results_html += "</ul></div>"

    if plans:
        results_html += f"""
        <div class="success">
            <h3>✅ Microsoft Planner Access</h3>
            <p><strong>Plans Found:</strong> {len(plans)}</p>
            <ul>
        """
        for plan in plans[:5]:  # Show first 5 plans
            results_html += f"<li>{plan.get('title', 'Unknown Plan')}</li>"
        if len(plans) > 5:
            results_html += f"<li>... and {len(plans) - 5} more plans</li>"
        results_html += "</ul></div>"

    if tasks:
        results_html += f"""
        <div class="info">
            <h3>📋 Existing Tasks</h3>
            <p><strong>Tasks Found in First Plan:</strong> {len(tasks)}</p>
        </div>
        """

    if test_task:
        results_html += f"""
        <div class="success">
            <h3>✅ Task Creation Test</h3>
            <p><strong>Test Task Created:</strong> {test_task.get('title', 'Unknown')}</p>
            <p><strong>Task ID:</strong> {test_task.get('id', 'N/A')}</p>
            <p><strong>Plan:</strong> {test_task.get('planId', 'N/A')}</p>
        </div>
        """

    if errors:
        results_html += """
        <div class="error">
            <h3>⚠️ Errors Encountered</h3>
            <ul>
        """
        for error in errors:
            results_html += f"<li>{error}</li>"
        results_html += "</ul></div>"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Success - Teams & Planner Connected!</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .success {{ color: green; background: #f0f8f0; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .error {{ color: red; background: #f8f0f0; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .info {{ color: blue; background: #f0f0f8; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; }}
            ul {{ margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎉 OAuth Authentication Successful!</h1>
            <p>Your Microsoft Teams and Planner integration is now working!</p>

            {results_html}

            <div class="info">
                <h3>🚀 What's Next?</h3>
                <ul>
                    <li>Your application can now access Microsoft Teams and Planner</li>
                    <li>Use the Teams client methods to manage teams, channels, and members</li>
                    <li>Use the Planner client methods to create plans, buckets, and tasks</li>
                    <li>All API calls are authenticated with your user context</li>
                </ul>
            </div>

            <p><a href="/">← Back to Home</a></p>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    print("🚀 Starting OAuth Callback Server...")
    print("📍 Server will be available at: http://localhost:8888")
    print("🔗 OAuth callback URL: http://localhost:8888/auth/callback")
    print("📋 Visit http://localhost:8888 for instructions")
    print()

    uvicorn.run(
        "oauth_callback_server:app",
        host="0.0.0.0",
        port=8888,
        log_level="info",
        reload=False
    )