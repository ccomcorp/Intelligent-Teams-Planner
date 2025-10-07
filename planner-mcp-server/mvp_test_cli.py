#!/usr/bin/env python3
"""
MVP Test CLI for Microsoft Teams and Planner connectivity
Simple command-line tool to test authentication and basic operations
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.auth import AuthService
from src.cache import CacheService
from src.teams_planner_client import SimpleTeamsPlannerClient


async def main():
    """Main MVP test function"""
    print("🚀 MVP Test: Microsoft Teams and Planner Connectivity")
    print("=" * 60)

    # Check environment variables
    required_env_vars = ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set these in your .env file:")
        for var in missing_vars:
            print(f"  {var}=your_value_here")
        return

    try:
        # Initialize services
        print("🔧 Initializing services...")
        cache_service = CacheService("redis://localhost:6379/0")
        await cache_service.initialize()
        print("✅ Cache service initialized")

        auth_service = AuthService(
            client_id=os.getenv("AZURE_CLIENT_ID"),
            client_secret=os.getenv("AZURE_CLIENT_SECRET"),
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            cache_service=cache_service
        )
        print("✅ Auth service initialized")

        client = SimpleTeamsPlannerClient(auth_service)
        print("✅ Teams/Planner client initialized")

        # Test user ID (in a real scenario, this would come from authentication)
        test_user_id = "mvp_test_user"

        print(f"\n🔍 Testing connectivity for user: {test_user_id}")

        # Check if user has a stored token
        has_token = await auth_service.has_valid_token(test_user_id)
        if not has_token:
            print("❌ No valid authentication token found")
            print("\n📋 To test with real authentication:")
            print("1. Implement OAuth flow in your application")
            print("2. Store valid tokens for test user")
            print("3. Re-run this test")
            print("\n🔗 OAuth Authorization URL generation:")
            login_url = await auth_service.get_login_url(test_user_id)
            print(f"   {login_url}")
            print("\n   Visit this URL to authenticate and complete the OAuth flow")
            return

        print("✅ Valid authentication token found")

        # Test connectivity
        print("\n🌐 Testing Microsoft Graph API connectivity...")
        results = await client.test_connectivity(test_user_id)

        if results["connectivity_test"]:
            print("✅ Successfully connected to Microsoft Graph API!")

            if results["user_info"]:
                user = results["user_info"]
                print(f"👤 User: {user.get('displayName', 'Unknown')} ({user.get('mail', user.get('userPrincipalName', 'No email'))})")

            if results["teams"]:
                print(f"🏢 Found {len(results['teams'])} team(s):")
                for i, team in enumerate(results["teams"][:3]):  # Show first 3 teams
                    print(f"   {i+1}. {team.get('displayName', 'Unknown Team')} (ID: {team['id'][:8]}...)")

                # Test Planner plans for first team
                first_team = results["teams"][0]
                team_id = first_team["id"]
                print(f"\n📋 Testing Planner plans for team: {first_team.get('displayName', 'Unknown')}")

                try:
                    plans = await client.get_team_planner_plans(test_user_id, team_id)
                    if plans:
                        print(f"✅ Found {len(plans)} Planner plan(s):")
                        for i, plan in enumerate(plans):
                            print(f"   {i+1}. {plan.get('title', 'Unknown Plan')} (ID: {plan['id'][:8]}...)")

                        # Test task creation in first plan
                        first_plan = plans[0]
                        plan_id = first_plan["id"]
                        print(f"\n✨ Testing task creation in plan: {first_plan.get('title', 'Unknown')}")

                        task = await client.create_planner_task(
                            test_user_id,
                            plan_id,
                            "MVP Test Task - Created by CLI",
                            f"This task was created on {asyncio.get_event_loop().time()} to test MVP connectivity"
                        )

                        print(f"🎉 SUCCESS! Task created:")
                        print(f"   📝 Title: {task.get('title', 'Unknown')}")
                        print(f"   🆔 Task ID: {task['id']}")
                        print(f"   📋 Plan ID: {task.get('planId', 'Unknown')}")

                    else:
                        print("⚠️  No Planner plans found for this team")
                        print("   💡 Tip: Create a plan in Microsoft Planner and try again")

                except Exception as e:
                    print(f"❌ Error testing Planner: {str(e)}")

            else:
                print("⚠️  No teams found for this user")
                print("   💡 Tip: Join a Microsoft Team and try again")

        else:
            print("❌ Connectivity test failed")
            for error in results["errors"]:
                print(f"   💥 {error}")

    except Exception as e:
        print(f"💥 MVP test failed: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        if 'cache_service' in locals():
            await cache_service.close()
            print("\n🔧 Services cleaned up")

    print("\n" + "=" * 60)
    print("🏁 MVP Test Complete")


if __name__ == "__main__":
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("💡 Tip: Install python-dotenv for automatic .env loading")
        print("   pip install python-dotenv")

    asyncio.run(main())