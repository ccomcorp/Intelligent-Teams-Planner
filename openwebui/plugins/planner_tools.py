"""
OpenWebUI Plugin for Microsoft Planner Integration
Connects OpenWebUI to MCPO Proxy for seamless Planner operations
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

import httpx
import structlog

logger = structlog.get_logger(__name__)

class PlannerToolsPlugin:
    """
    OpenWebUI plugin for Microsoft Planner integration via MCPO Proxy
    """

    def __init__(self):
        self.name = "planner-tools"
        self.version = "2.0.0"
        self.description = "Microsoft Planner integration for task and plan management"
        self.proxy_url = "http://mcpo-proxy:8001"
        self.client = None

    async def initialize(self, config: Dict[str, Any]):
        """Initialize the plugin"""
        try:
            self.proxy_url = config.get("proxy_url", "http://mcpo-proxy:8001")
            self.client = httpx.AsyncClient(timeout=30.0)

            # Test connection to MCPO proxy
            response = await self.client.get(f"{self.proxy_url}/health")
            if response.status_code == 200:
                logger.info("Planner tools plugin initialized successfully")
                return True
            else:
                logger.error("Failed to connect to MCPO proxy", status_code=response.status_code)
                return False

        except Exception as e:
            logger.error("Failed to initialize planner tools plugin", error=str(e))
            return False

    async def cleanup(self):
        """Cleanup plugin resources"""
        if self.client:
            await self.client.aclose()

    def get_manifest(self) -> Dict[str, Any]:
        """Get plugin manifest for OpenWebUI"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": "Intelligent Teams Planner Team",
            "license": "MIT",
            "capabilities": [
                "chat_completion_hook",
                "tool_integration",
                "authentication_helper"
            ],
            "configuration": {
                "proxy_url": {
                    "type": "string",
                    "default": "http://mcpo-proxy:8001",
                    "description": "MCPO Proxy URL"
                },
                "auto_authenticate": {
                    "type": "boolean",
                    "default": True,
                    "description": "Automatically prompt for authentication"
                },
                "show_tool_outputs": {
                    "type": "boolean",
                    "default": True,
                    "description": "Show tool execution outputs"
                }
            }
        }

    async def pre_chat_completion_hook(
        self,
        messages: List[Dict[str, Any]],
        user_id: str,
        model: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Hook that runs before chat completion
        Used to enhance messages with Planner context
        """
        try:
            # Check if this is a Planner-related request
            last_message = messages[-1].get("content", "").lower()

            planner_keywords = [
                "plan", "task", "planner", "assign", "due", "complete",
                "create", "list", "show", "update", "delete", "search"
            ]

            if any(keyword in last_message for keyword in planner_keywords):
                # Check authentication status
                auth_status = await self._check_auth_status(user_id)

                if not auth_status.get("authenticated", False):
                    # Add authentication prompt to system message
                    auth_message = {
                        "role": "system",
                        "content": f"""
The user is requesting Planner operations but is not authenticated.
Please prompt them to authenticate with Microsoft Graph API first.
Authentication URL: {self.proxy_url}/auth/login-url?user_id={user_id}
                        """
                    }
                    messages.insert(-1, auth_message)

                else:
                    # Add user context to system message
                    user_info = auth_status.get("user_name", "User")
                    context_message = {
                        "role": "system",
                        "content": f"""
User {user_info} is authenticated and can perform Planner operations.
Available tools through MCPO proxy: list_plans, create_plan, list_tasks,
create_task, update_task, search_plans.
Use natural language to execute these operations.
                        """
                    }
                    messages.insert(-1, context_message)

            return {"messages": messages}

        except Exception as e:
            logger.error("Error in pre_chat_completion_hook", error=str(e))
            return {"messages": messages}

    async def post_chat_completion_hook(
        self,
        response: Dict[str, Any],
        messages: List[Dict[str, Any]],
        user_id: str,
        model: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Hook that runs after chat completion
        Used to add tool execution results
        """
        try:
            # Check if response contains tool calls
            assistant_message = response.get("choices", [{}])[0].get("message", {})
            content = assistant_message.get("content", "")

            # Look for tool execution patterns in the response
            if "plan" in content.lower() or "task" in content.lower():
                # Add helpful suggestions for next actions
                suggestions = await self._get_contextual_suggestions(user_id, content)
                if suggestions:
                    enhanced_content = f"{content}\n\n💡 **Quick Actions:**\n{suggestions}"
                    response["choices"][0]["message"]["content"] = enhanced_content

            return response

        except Exception as e:
            logger.error("Error in post_chat_completion_hook", error=str(e))
            return response

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Handle direct tool calls from OpenWebUI
        """
        try:
            logger.info("Handling tool call", tool=tool_name, user_id=user_id)

            # Forward tool call to MCPO proxy
            response = await self.client.post(
                f"{self.proxy_url}/tools/{tool_name}/execute",
                json=tool_args,
                params={"user_id": user_id}
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "result": result,
                    "formatted_output": await self._format_tool_output(tool_name, result)
                }
            else:
                return {
                    "success": False,
                    "error": f"Tool execution failed: {response.status_code}",
                    "formatted_output": f"❌ Tool '{tool_name}' failed to execute"
                }

        except Exception as e:
            logger.error("Error handling tool call", tool=tool_name, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "formatted_output": f"❌ Error executing tool '{tool_name}': {str(e)}"
            }

    async def get_available_tools(self, user_id: str) -> List[Dict[str, Any]]:
        """Get available tools from MCPO proxy"""
        try:
            response = await self.client.get(f"{self.proxy_url}/tools")
            if response.status_code == 200:
                data = response.json()
                return data.get("tools", [])
            return []

        except Exception as e:
            logger.error("Error getting available tools", error=str(e))
            return []

    async def _check_auth_status(self, user_id: str) -> Dict[str, Any]:
        """Check authentication status via MCPO proxy"""
        try:
            response = await self.client.get(
                f"{self.proxy_url}/auth/status",
                params={"user_id": user_id}
            )

            if response.status_code == 200:
                return response.json()
            return {"authenticated": False}

        except Exception as e:
            logger.error("Error checking auth status", error=str(e))
            return {"authenticated": False}

    async def _get_contextual_suggestions(self, user_id: str, content: str) -> Optional[str]:
        """Get contextual suggestions based on conversation content"""
        try:
            suggestions = []

            content_lower = content.lower()

            if "plan" in content_lower and "created" in content_lower:
                suggestions.append("• Add tasks to your new plan")
                suggestions.append("• Invite team members to collaborate")

            elif "task" in content_lower and "created" in content_lower:
                suggestions.append("• Set a due date for the task")
                suggestions.append("• Assign the task to a team member")

            elif "list" in content_lower and "plan" in content_lower:
                suggestions.append("• Create a new plan")
                suggestions.append("• Search for specific plans")

            elif "list" in content_lower and "task" in content_lower:
                suggestions.append("• Create a new task")
                suggestions.append("• Update task progress")

            return "\n".join(suggestions) if suggestions else None

        except Exception as e:
            logger.error("Error getting contextual suggestions", error=str(e))
            return None

    async def _format_tool_output(self, tool_name: str, result: Dict[str, Any]) -> str:
        """Format tool output for display"""
        try:
            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error")
                return f"❌ **{tool_name}** failed: {error_msg}"

            content = result.get("content", {})

            if tool_name == "list_plans":
                plans = content.get("plans", [])
                if not plans:
                    return "📋 No plans found."

                output = f"📋 **Found {len(plans)} plan(s):**\n\n"
                for plan in plans[:5]:  # Show first 5
                    title = plan.get("title", "Untitled")
                    plan_id = plan.get("id", "Unknown")
                    output += f"• **{title}** (ID: `{plan_id}`)\n"

                if len(plans) > 5:
                    output += f"\n... and {len(plans) - 5} more plans"

                return output

            elif tool_name == "create_plan":
                title = content.get("title", "Untitled")
                plan_id = content.get("id", "Unknown")
                return f"✅ **Plan created:** {title} (ID: `{plan_id}`)"

            elif tool_name == "list_tasks":
                tasks = content.get("tasks", [])
                plan_id = content.get("plan_id", "Unknown")

                if not tasks:
                    return f"✅ No tasks found in plan `{plan_id}`."

                output = f"✅ **Found {len(tasks)} task(s):**\n\n"
                for task in tasks[:5]:  # Show first 5
                    title = task.get("title", "Untitled")
                    percent = task.get("percentComplete", 0)
                    status_emoji = "✅" if percent == 100 else "🔄" if percent > 0 else "⏳"
                    output += f"{status_emoji} **{title}** ({percent}%)\n"

                if len(tasks) > 5:
                    output += f"\n... and {len(tasks) - 5} more tasks"

                return output

            else:
                # Generic success message
                return f"✅ **{tool_name}** completed successfully"

        except Exception as e:
            logger.error("Error formatting tool output", tool=tool_name, error=str(e))
            return f"✅ **{tool_name}** completed"

    def get_plugin_info(self) -> Dict[str, Any]:
        """Get plugin information for OpenWebUI"""
        return {
            "id": self.name,
            "name": "Microsoft Planner Tools",
            "version": self.version,
            "description": self.description,
            "icon": "📋",
            "status": "active",
            "features": [
                "Plan Management",
                "Task Operations",
                "Search Functionality",
                "Authentication Integration"
            ]
        }

# Plugin factory function for OpenWebUI
def create_plugin() -> PlannerToolsPlugin:
    """Create plugin instance"""
    return PlannerToolsPlugin()

# Plugin registration
PLUGIN_MANIFEST = {
    "name": "planner-tools",
    "version": "2.0.0",
    "description": "Microsoft Planner integration plugin",
    "main": "planner_tools.py",
    "class": "PlannerToolsPlugin",
    "factory": "create_plugin"
}