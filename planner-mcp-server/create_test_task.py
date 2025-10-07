#!/usr/bin/env python3
"""
Create a test task in the AI PROJECTS plan
"""

import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
import structlog

from src.cache import CacheService
from src.auth import AuthService
from src.teams_planner_client import SimpleTeamsPlannerClient

# Load environment variables
load_dotenv()

logger = structlog.get_logger(__name__)

async def create_task_in_ai_projects():
    """Create a test task in the AI PROJECTS plan"""

    # Initialize services
    cache_service = CacheService(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    await cache_service.initialize()

    auth_service = AuthService(
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_secret=os.getenv("AZURE_CLIENT_SECRET"),
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        cache_service=cache_service,
        redirect_uri="http://localhost:8888/auth/callback"
    )

    teams_client = SimpleTeamsPlannerClient(auth_service)

    try:
        user_id = "oauth_test_user"  # Same user ID from OAuth flow

        print("🔍 Finding AI PROJECTS plan...")

        # Get all teams
        teams = await teams_client.get_user_teams(user_id)
        print(f"Found {len(teams)} teams")

        # Find plans in all teams
        all_plans = []
        for team in teams:
            team_name = team.get('displayName', 'Unknown')
            print(f"Checking plans in team: {team_name}")
            try:
                plans = await teams_client.get_team_planner_plans(user_id, team['id'])
                for plan in plans:
                    plan['team_name'] = team_name
                    plan['team_id'] = team['id']
                    all_plans.append(plan)
                    print(f"  - Plan: {plan.get('title', 'Unknown')}")
            except Exception as e:
                print(f"  Could not access plans for {team_name}: {str(e)}")

        # Find the AI PROJECTS plan
        ai_projects_plan = None
        for plan in all_plans:
            if plan.get('title') == 'AI PROJECTS':
                ai_projects_plan = plan
                break

        if not ai_projects_plan:
            print("❌ AI PROJECTS plan not found!")
            print("Available plans:")
            for plan in all_plans:
                print(f"  - {plan.get('title', 'Unknown')} (Team: {plan.get('team_name', 'Unknown')})")
            return

        print(f"✅ Found AI PROJECTS plan: {ai_projects_plan['id']}")
        print(f"   Team: {ai_projects_plan.get('team_name', 'Unknown')}")

        # Create a test task in AI PROJECTS
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        task_title = f"Test Task for AI PROJECTS - {timestamp}"
        task_description = "This is a test task created specifically in the AI PROJECTS plan to verify Microsoft Graph API connectivity and task creation functionality."

        print(f"🚀 Creating test task: {task_title}")

        task = await teams_client.create_planner_task(
            user_id=user_id,
            plan_id=ai_projects_plan['id'],
            title=task_title,
            description=task_description,
            priority=3  # Medium priority
        )

        print("✅ SUCCESS! Test task created in AI PROJECTS:")
        print(f"   Task ID: {task.get('id')}")
        print(f"   Title: {task.get('title')}")
        print(f"   Plan: AI PROJECTS ({ai_projects_plan['id']})")
        print(f"   Team: {ai_projects_plan.get('team_name')}")

        # Get updated task list to confirm
        print("\n📋 Current tasks in AI PROJECTS plan:")
        tasks = await teams_client.get_plan_tasks(user_id, ai_projects_plan['id'])
        for i, task_item in enumerate(tasks, 1):
            print(f"   {i}. {task_item.get('title', 'Untitled')}")

        print(f"\n🎉 Task successfully created in AI PROJECTS plan!")

    except Exception as e:
        print(f"❌ Error creating task: {str(e)}")
        logger.error("Error creating test task", error=str(e))

    finally:
        await cache_service.close()

if __name__ == "__main__":
    asyncio.run(create_task_in_ai_projects())