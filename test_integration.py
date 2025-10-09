#!/usr/bin/env python3
"""
End-to-end integration test for Intelligent Teams Planner v2.0
Tests the complete flow: Teams Bot → OpenWebUI → MCPO Proxy → MCP Server → Graph API
"""

import asyncio
import httpx
import json
import os
from datetime import datetime

# Test configuration with new port scheme
MCP_SERVER_URL = "http://localhost:7100"
MCPO_PROXY_URL = "http://localhost:7105"
TEAMS_BOT_URL = "http://localhost:7110"
OPENWEBUI_URL = "http://localhost:7115"

class IntegrationTester:
    """End-to-end integration tester"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_results = []

    async def test_database_connectivity(self):
        """Test PostgreSQL and Redis connectivity"""
        print("🔍 Testing database connectivity...")

        try:
            # Test Redis
            import redis
            try:
                # Try with password first
                r = redis.Redis(host='localhost', port=6379, password='redis_password_2024', decode_responses=True)
                r.ping()
            except redis.exceptions.AuthenticationError:
                # Try without password (fallback)
                r = redis.Redis(host='localhost', port=6379, decode_responses=True)
                r.ping()
            print("  ✅ Redis connection: OK")

            # Test PostgreSQL
            import asyncpg
            conn = await asyncpg.connect(
                "postgresql://itp_user:itp_password_2024@localhost:5432/intelligent_teams_planner"
            )
            await conn.execute("SELECT 1")
            await conn.close()
            print("  ✅ PostgreSQL connection: OK")

            return True
        except Exception as e:
            print(f"  ❌ Database connectivity failed: {e}")
            return False

    async def test_mcp_server_health(self):
        """Test MCP Server health and basic functionality"""
        print("🔍 Testing MCP Server...")

        try:
            # Health check
            response = await self.client.get(f"{MCP_SERVER_URL}/health")
            if response.status_code == 200:
                health_data = response.json()
                print(f"  ✅ MCP Server health: {health_data.get('status')}")
            else:
                print(f"  ❌ MCP Server health check failed: {response.status_code}")
                return False

            # Test capabilities endpoint
            response = await self.client.get(f"{MCP_SERVER_URL}/capabilities")
            if response.status_code == 200:
                capabilities = response.json()
                print(f"  ✅ MCP Server capabilities: {len(capabilities.get('tools', {}))} tools available")
            else:
                print(f"  ❌ MCP Server capabilities failed: {response.status_code}")
                return False

            # Test tools listing
            response = await self.client.get(f"{MCP_SERVER_URL}/tools")
            if response.status_code == 200:
                tools_data = response.json()
                tools = tools_data if isinstance(tools_data, list) else []
                print(f"  ✅ MCP Server tools: {len(tools)} tools listed")

                # Show first few tools
                for tool in tools[:3]:
                    print(f"    - {tool.get('name', 'unknown')}: {tool.get('description', 'no description')}")
            else:
                print(f"  ❌ MCP Server tools listing failed: {response.status_code}")
                return False

            return True
        except Exception as e:
            print(f"  ❌ MCP Server test failed: {e}")
            return False

    async def test_mcpo_proxy_health(self):
        """Test MCPO Proxy health and translation capabilities"""
        print("🔍 Testing MCPO Proxy...")

        try:
            # Health check
            response = await self.client.get(f"{MCPO_PROXY_URL}/health")
            if response.status_code == 200:
                health_data = response.json()
                print(f"  ✅ MCPO Proxy health: {health_data.get('status')}")
            else:
                print(f"  ❌ MCPO Proxy health check failed: {response.status_code}")
                return False

            # Test info endpoint
            response = await self.client.get(f"{MCPO_PROXY_URL}/info")
            if response.status_code == 200:
                info_data = response.json()
                print(f"  ✅ MCPO Proxy info: {info_data.get('name')} v{info_data.get('version')}")
            else:
                print(f"  ❌ MCPO Proxy info failed: {response.status_code}")

            # Test tools endpoint
            response = await self.client.get(f"{MCPO_PROXY_URL}/tools")
            if response.status_code == 200:
                tools_data = response.json()
                tool_count = tools_data.get('total_count', 0)
                print(f"  ✅ MCPO Proxy tools: {tool_count} tools available via proxy")
            else:
                print(f"  ❌ MCPO Proxy tools failed: {response.status_code}")

            # Test OpenAI compatibility
            response = await self.client.get(f"{MCPO_PROXY_URL}/v1/models")
            if response.status_code == 200:
                models_data = response.json()
                model_count = len(models_data.get('data', []))
                print(f"  ✅ OpenAI compatibility: {model_count} models available")
            else:
                print(f"  ❌ OpenAI models endpoint failed: {response.status_code}")

            return True
        except Exception as e:
            print(f"  ❌ MCPO Proxy test failed: {e}")
            return False

    async def test_teams_bot_health(self):
        """Test Teams Bot health"""
        print("🔍 Testing Teams Bot...")

        try:
            # Health check
            response = await self.client.get(f"{TEAMS_BOT_URL}/health")
            if response.status_code == 200:
                health_data = response.json()
                print(f"  ✅ Teams Bot health: {health_data.get('status')}")
                print(f"  ✅ OpenWebUI status: {health_data.get('openwebui_status')}")
                return True
            else:
                print(f"  ❌ Teams Bot health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ Teams Bot test failed: {e}")
            return False

    async def test_tool_execution(self):
        """Test direct tool execution via MCP Server"""
        print("🔍 Testing tool execution...")

        try:
            # Test a simple tool execution - list_plans
            test_tool_call = {
                "name": "list_plans",
                "arguments": {
                    "include_archived": False
                }
            }

            response = await self.client.post(
                f"{MCP_SERVER_URL}/tools/call",
                json=test_tool_call,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result = response.json()
                success = result.get('success', False)
                print(f"  ✅ Tool execution: {'success' if success else 'failed'}")

                if success and 'content' in result:
                    content = result['content']
                    if isinstance(content, dict) and 'plans' in content:
                        plan_count = len(content['plans'])
                        print(f"    - Found {plan_count} plans")
                    else:
                        print(f"    - Response: {content}")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"    - Error: {error}")

                return success
            else:
                print(f"  ❌ Tool execution failed: {response.status_code}")
                print(f"    Response: {response.text}")
                return False

        except Exception as e:
            print(f"  ❌ Tool execution test failed: {e}")
            return False

    async def test_proxy_tool_execution(self):
        """Test tool execution via MCPO Proxy"""
        print("🔍 Testing proxy tool execution...")

        try:
            # Test tool execution through the proxy
            test_arguments = {
                "include_archived": False
            }

            response = await self.client.post(
                f"{MCPO_PROXY_URL}/tools/list_plans/execute",
                json=test_arguments,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result = response.json()
                success = result.get('success', False)
                print(f"  ✅ Proxy tool execution: {'success' if success else 'failed'}")

                if success and 'content' in result:
                    content = result['content']
                    if isinstance(content, dict) and 'plans' in content:
                        plan_count = len(content['plans'])
                        print(f"    - Found {plan_count} plans via proxy")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"    - Error: {error}")

                return success
            else:
                print(f"  ❌ Proxy tool execution failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"  ❌ Proxy tool execution test failed: {e}")
            return False

    async def test_openai_compatibility(self):
        """Test OpenAI-compatible chat completion"""
        print("🔍 Testing OpenAI compatibility...")

        try:
            # Test chat completion
            chat_request = {
                "model": "planner-assistant",
                "messages": [
                    {
                        "role": "user",
                        "content": "List my available plans"
                    }
                ],
                "user": "test_user",
                "stream": False
            }

            response = await self.client.post(
                f"{MCPO_PROXY_URL}/v1/chat/completions",
                json=chat_request,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result = response.json()
                print("  ✅ OpenAI chat completion: success")

                choices = result.get('choices', [])
                if choices:
                    message_content = choices[0].get('message', {}).get('content', '')
                    print(f"    - Response length: {len(message_content)} characters")

                return True
            else:
                print(f"  ❌ OpenAI chat completion failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"  ❌ OpenAI compatibility test failed: {e}")
            return False

    async def run_all_tests(self):
        """Run all integration tests"""
        print("🚀 Starting End-to-End Integration Tests")
        print("=" * 50)

        tests = [
            ("Database Connectivity", self.test_database_connectivity),
            ("MCP Server Health", self.test_mcp_server_health),
            ("MCPO Proxy Health", self.test_mcpo_proxy_health),
            ("Teams Bot Health", self.test_teams_bot_health),
            ("Tool Execution", self.test_tool_execution),
            ("Proxy Tool Execution", self.test_proxy_tool_execution),
            ("OpenAI Compatibility", self.test_openai_compatibility),
        ]

        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            print(f"\n📋 {test_name}")
            try:
                result = await test_func()
                if result:
                    passed += 1
                    self.test_results.append((test_name, "PASS"))
                else:
                    self.test_results.append((test_name, "FAIL"))
            except Exception as e:
                print(f"  ❌ Test failed with exception: {e}")
                self.test_results.append((test_name, "ERROR"))

        print("\n" + "=" * 50)
        print("📊 Test Results Summary")
        print("=" * 50)

        for test_name, status in self.test_results:
            emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
            print(f"{emoji} {test_name}: {status}")

        print(f"\n🎯 Overall Result: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 All tests passed! System is ready for deployment.")
            return True
        else:
            print("⚠️ Some tests failed. Please check the implementation.")
            return False

    async def close(self):
        """Clean up resources"""
        await self.client.aclose()

async def main():
    """Main test function"""
    tester = IntegrationTester()
    try:
        success = await tester.run_all_tests()
        exit_code = 0 if success else 1
    finally:
        await tester.close()

    return exit_code

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)