"""
OpenAI API compatibility translator for MCP integration
"""

import re
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

import structlog

from .mcp_client import MCPClient
from .cache import ProxyCache

logger = structlog.get_logger(__name__)


class OpenAITranslator:
    """Translates OpenAI chat completions to MCP tool calls"""

    def __init__(self, mcp_client: MCPClient, cache: ProxyCache):
        self.mcp_client = mcp_client
        self.cache = cache
        self.tool_patterns = []

    async def initialize(self):
        """Initialize translator with tool patterns"""
        try:
            # Get available tools from MCP server
            await self.mcp_client.list_tools()

            # Create patterns for intent recognition
            self.tool_patterns = [
                # Plan management patterns
                {
                    "pattern": r"(?:list|show|get|find)\s+(?:all\s+)?plans?",
                    "tool": "list_plans",
                    "extract_args": self._extract_list_plans_args
                },
                {
                    "pattern": r"(?:create|make|add|new)\s+(?:a\s+)?plan",
                    "tool": "create_plan",
                    "extract_args": self._extract_create_plan_args
                },
                # Task management patterns
                {
                    "pattern": r"(?:list|show|get|find)\s+(?:all\s+)?tasks?",
                    "tool": "list_tasks",
                    "extract_args": self._extract_list_tasks_args
                },
                {
                    "pattern": r"(?:create|make|add|new)\s+(?:a\s+)?task",
                    "tool": "create_task",
                    "extract_args": self._extract_create_task_args
                },
                {
                    "pattern": r"(?:update|modify|change|edit)\s+task",
                    "tool": "update_task",
                    "extract_args": self._extract_update_task_args
                },
                {
                    "pattern": r"(?:complete|finish|done)\s+task",
                    "tool": "update_task",
                    "extract_args": self._extract_complete_task_args
                },
                # Search patterns
                {
                    "pattern": r"(?:search|find|look for)\s+plans?",
                    "tool": "search_plans",
                    "extract_args": self._extract_search_plans_args
                }
            ]

            logger.info("OpenAI translator initialized", patterns_count=len(self.tool_patterns))

        except Exception as e:
            logger.error("Failed to initialize translator", error=str(e))
            raise

    async def process_chat_completion(self, request) -> Dict[str, Any]:
        """Process OpenAI chat completion request"""
        try:
            user_id = request.user or "default"
            messages = request.messages
            conversation_id = request.conversation_id

            # Get the last user message
            last_message = None
            for msg in reversed(messages):
                if msg.role == "user":
                    last_message = msg.content
                    break

            if not last_message:
                return self._create_error_response("No user message found")

            logger.info("Processing chat completion", user_id=user_id, message=last_message[:100])

            # Check if this is an authentication-related query
            auth_response = await self._handle_auth_queries(last_message, user_id)
            if auth_response:
                return auth_response

            # Detect intent and extract tool calls
            tool_calls = await self._extract_tool_calls(last_message)

            if not tool_calls:
                # No specific tool detected, provide general help
                return await self._create_help_response(last_message, user_id)

            # Execute tool calls
            results = []
            for tool_call in tool_calls:
                try:
                    result = await self.mcp_client.execute_tool(
                        tool_call["name"],
                        tool_call["arguments"],
                        user_id
                    )
                    results.append(result)
                except Exception as e:
                    logger.error("Tool execution failed", tool=tool_call["name"], error=str(e))
                    results.append({
                        "success": False,
                        "error": str(e),
                        "tool_name": tool_call["name"]
                    })

            # Format response
            response_content = await self._format_tool_results(results, tool_calls)

            # Create OpenAI-compatible response
            return self._create_chat_response(
                content=response_content,
                model=request.model,
                conversation_id=conversation_id
            )

        except Exception as e:
            logger.error("Error processing chat completion", error=str(e))
            return self._create_error_response(f"Processing failed: {str(e)}")

    async def _extract_tool_calls(self, message: str) -> List[Dict[str, Any]]:
        """Extract tool calls from natural language message"""
        tool_calls = []
        message_lower = message.lower()

        for pattern_info in self.tool_patterns:
            pattern = pattern_info["pattern"]
            if re.search(pattern, message_lower, re.IGNORECASE):
                try:
                    arguments = pattern_info["extract_args"](message)
                    tool_calls.append({
                        "name": pattern_info["tool"],
                        "arguments": arguments
                    })
                    break  # Use first matching pattern
                except Exception as e:
                    logger.error("Error extracting arguments", pattern=pattern, error=str(e))

        return tool_calls

    # Argument extraction methods

    def _extract_list_plans_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for list_plans"""
        args = {}

        # Look for group-specific requests
        group_match = re.search(r"(?:for|in|from)\s+group\s+(\w+)", message, re.IGNORECASE)
        if group_match:
            args["group_id"] = group_match.group(1)

        # Look for archived plans
        if re.search(r"archived|old", message, re.IGNORECASE):
            args["include_archived"] = True

        return args

    def _extract_create_plan_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for create_plan"""
        args = {}

        # Extract title from quotes or after "called"/"named"
        title_patterns = [
            r'"([^"]+)"',
            r"'([^']+)'",
            r"(?:called|named)\s+([^\s,\.!?]+)",
            r"plan\s+([^\s,\.!?]+)"
        ]

        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["title"] = match.group(1)
                break

        # Extract group ID
        group_match = re.search(r"(?:for|in|with)\s+group\s+(\w+)", message, re.IGNORECASE)
        if group_match:
            args["group_id"] = group_match.group(1)

        # Extract description
        desc_match = re.search(r"(?:description|about|for)[\s:]+([^\.!?]+)", message, re.IGNORECASE)
        if desc_match:
            args["description"] = desc_match.group(1).strip()

        return args

    def _extract_list_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for list_tasks"""
        args = {}

        # Extract plan ID
        plan_match = re.search(r"(?:in|for|from)\s+plan\s+(\w+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1)

        # Filter completed tasks
        if re.search(r"(?:not\s+completed|incomplete|pending|active)", message, re.IGNORECASE):
            args["filter_completed"] = True

        # Filter by assignee
        assignee_match = re.search(r"(?:assigned to|for)\s+(\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assigned_to"] = assignee_match.group(1)

        return args

    def _extract_create_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for create_task"""
        args = {}

        # Extract plan ID
        plan_match = re.search(r"(?:in|for|to)\s+plan\s+(\w+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1)

        # Extract title
        title_patterns = [
            r'"([^"]+)"',
            r"'([^']+)'",
            r"task\s+([^\s,\.!?]+)"
        ]

        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["title"] = match.group(1)
                break

        # Extract due date
        date_match = re.search(r"(?:due|by|before)\s+([\w\s\-\/]+?)(?:\s|$|,|\.)", message, re.IGNORECASE)
        if date_match:
            args["due_date"] = date_match.group(1).strip()

        # Extract priority
        if re.search(r"urgent|high priority|important", message, re.IGNORECASE):
            args["priority"] = 1
        elif re.search(r"low priority|later", message, re.IGNORECASE):
            args["priority"] = 9

        # Extract assignee
        assignee_match = re.search(r"(?:assign to|for)\s+(\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assigned_to"] = [assignee_match.group(1)]

        return args

    def _extract_update_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for update_task"""
        args = {}

        # Extract task ID
        task_match = re.search(r"task\s+(\w+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1)

        # Extract new title
        title_match = re.search(r"(?:title|name)\s+(?:to\s+)?[\"']([^\"']+)[\"']", message, re.IGNORECASE)
        if title_match:
            args["title"] = title_match.group(1)

        # Extract completion percentage
        percent_match = re.search(r"(\d+)%", message)
        if percent_match:
            args["percent_complete"] = int(percent_match.group(1))

        # Extract priority
        if re.search(r"urgent|high", message, re.IGNORECASE):
            args["priority"] = 1
        elif re.search(r"low|later", message, re.IGNORECASE):
            args["priority"] = 9

        return args

    def _extract_complete_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for completing a task"""
        args = {"percent_complete": 100}

        # Extract task ID
        task_match = re.search(r"task\s+(\w+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1)

        return args

    def _extract_search_plans_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for search_plans"""
        args = {}

        # Extract search query
        query_patterns = [
            r'search\s+(?:for\s+)?["\']([^"\']+)["\']',
            r'find\s+(?:plans?\s+)?["\']([^"\']+)["\']',
            r'look for\s+["\']([^"\']+)["\']',
            r'search\s+(?:for\s+)?(\w+)',
            r'find\s+(\w+)'
        ]

        for pattern in query_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["query"] = match.group(1)
                break

        return args

    async def _handle_auth_queries(self, message: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Handle authentication-related queries"""
        message_lower = message.lower()

        if any(word in message_lower for word in ["login", "authenticate", "sign in", "connect"]):
            try:
                auth_status = await self.mcp_client.get_auth_status(user_id)

                if auth_status.get("authenticated"):
                    content = (
                        f"✅ You're already authenticated as {auth_status.get('user_name', 'Unknown User')}. "
                        "You can start managing your Planner tasks!"
                    )
                else:
                    login_url_result = await self.mcp_client.get_login_url(user_id)
                    login_url = login_url_result.get("login_url")

                    if login_url:
                        content = (
                            f"🔐 Please authenticate with Microsoft: [Login Here]({login_url})\n\n"
                            "After logging in, you'll be able to manage your Planner tasks through this chat interface."
                        )
                    else:
                        content = "❌ Unable to generate login URL. Please check the configuration."

                return self._create_chat_response(content=content, model="planner-assistant")

            except Exception as e:
                logger.error("Error handling auth query", error=str(e))
                return self._create_chat_response(
                    content="❌ Authentication service is currently unavailable. Please try again later.",
                    model="planner-assistant"
                )

        if any(word in message_lower for word in ["logout", "sign out", "disconnect"]):
            try:
                await self.mcp_client.logout(user_id)
                return self._create_chat_response(
                    content="✅ You've been logged out successfully.",
                    model="planner-assistant"
                )
            except Exception as e:
                logger.error("Error handling logout", error=str(e))
                return self._create_chat_response(
                    content="❌ Logout failed. Please try again.",
                    model="planner-assistant"
                )

        return None

    async def _create_help_response(self, message: str, user_id: str) -> Dict[str, Any]:
        """Create a helpful response when no specific tool is detected"""

        # Check authentication first
        try:
            auth_status = await self.mcp_client.get_auth_status(user_id)
            if not auth_status.get("authenticated"):
                login_url_result = await self.mcp_client.get_login_url(user_id)
                login_url = login_url_result.get("login_url", "#")

                content = f"""🔐 **Authentication Required**

To use Microsoft Planner features, you need to authenticate first:
[Authenticate with Microsoft]({login_url})

After authentication, I can help you with:
- Creating and managing plans
- Adding and updating tasks
- Searching through your plans
- Assigning tasks to team members

Just ask me in natural language like "create a plan for Q4 marketing" or "show me all tasks in project alpha"."""

                return self._create_chat_response(content=content, model="planner-assistant")

        except Exception as e:
            logger.error("Error checking auth in help response", error=str(e))

        # Provide general help
        content = """🤖 **Microsoft Planner Assistant**

I can help you manage your Microsoft Planner with natural language! Here are some examples:

📋 **Plan Management:**
- "List all my plans"
- "Create a plan called 'Q4 Marketing Campaign'"
- "Search for plans about 'project alpha'"

✅ **Task Management:**
- "Show tasks in plan ABC123"
- "Create a task 'Review proposal' in plan ABC123"
- "Update task XYZ456 to 50% complete"
- "Mark task XYZ456 as completed"

🔍 **Search & Filter:**
- "Find plans containing 'marketing'"
- "Show incomplete tasks assigned to John"

Just describe what you want to do in natural language, and I'll help you manage your Planner tasks!"""

        return self._create_chat_response(content=content, model="planner-assistant")

    async def _format_tool_results(self, results: List[Dict[str, Any]], tool_calls: List[Dict[str, Any]]) -> str:
        """Format tool execution results into user-friendly content"""
        if not results:
            return "No results available."

        formatted_parts = []

        for i, (result, tool_call) in enumerate(zip(results, tool_calls)):
            tool_name = tool_call["name"]

            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error")
                formatted_parts.append(f"❌ **{tool_name}** failed: {error_msg}")
                continue

            content = result.get("content", {})

            if tool_name == "list_plans":
                formatted_parts.append(self._format_plans_list(content))
            elif tool_name == "create_plan":
                formatted_parts.append(self._format_plan_created(content))
            elif tool_name == "list_tasks":
                formatted_parts.append(self._format_tasks_list(content))
            elif tool_name == "create_task":
                formatted_parts.append(self._format_task_created(content))
            elif tool_name == "update_task":
                formatted_parts.append(self._format_task_updated(content))
            elif tool_name == "search_plans":
                formatted_parts.append(self._format_search_results(content))
            else:
                # Generic formatting
                formatted_parts.append(f"✅ **{tool_name}** completed successfully")

        return "\n\n".join(formatted_parts)

    def _format_plans_list(self, content: Dict[str, Any]) -> str:
        """Format plans list"""
        plans = content.get("plans", [])
        total_count = content.get("total_count", len(plans))

        if not plans:
            return "📋 No plans found."

        result = f"📋 **Found {total_count} plan(s):**\n\n"

        for plan in plans[:10]:  # Limit to 10 plans
            title = plan.get("title", "Untitled")
            plan_id = plan.get("id", "Unknown")
            created = plan.get("createdDateTime", "")
            if created:
                try:
                    created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created_str = created_date.strftime("%Y-%m-%d")
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug("Failed to parse created date", created=created, error=str(e))
                    created_str = created[:10]  # Take first 10 chars
            else:
                created_str = "Unknown"

            result += f"• **{title}** (ID: `{plan_id}`) - Created: {created_str}\n"

        if len(plans) > 10:
            result += f"\n... and {len(plans) - 10} more plans"

        return result

    def _format_plan_created(self, content: Dict[str, Any]) -> str:
        """Format plan creation result"""
        title = content.get("title", "Untitled")
        plan_id = content.get("id", "Unknown")
        return (
            f"✅ **Plan created successfully!**\n\n📋 **{title}** (ID: `{plan_id}`)\n\n"
            "You can now add tasks to this plan!"
        )

    def _format_tasks_list(self, content: Dict[str, Any]) -> str:
        """Format tasks list"""
        tasks = content.get("tasks", [])
        total_count = content.get("total_count", len(tasks))
        plan_id = content.get("plan_id", "Unknown")

        if not tasks:
            return f"✅ No tasks found in plan `{plan_id}`."

        result = f"✅ **Found {total_count} task(s) in plan `{plan_id}`:**\n\n"

        for task in tasks[:10]:  # Limit to 10 tasks
            title = task.get("title", "Untitled")
            task_id = task.get("id", "Unknown")
            percent_complete = task.get("percentComplete", 0)
            due_date = task.get("dueDateTime", "")

            status_emoji = "✅" if percent_complete == 100 else "🔄" if percent_complete > 0 else "⏳"

            due_str = ""
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    due_str = f" - Due: {due_dt.strftime('%Y-%m-%d')}"
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug("Failed to parse due date", due_date=due_date, error=str(e))
                    pass

            result += f"{status_emoji} **{title}** ({percent_complete}%) (ID: `{task_id}`){due_str}\n"

        if len(tasks) > 10:
            result += f"\n... and {len(tasks) - 10} more tasks"

        return result

    def _format_task_created(self, content: Dict[str, Any]) -> str:
        """Format task creation result"""
        title = content.get("title", "Untitled")
        task_id = content.get("id", "Unknown")
        plan_id = content.get("planId", "Unknown")
        return f"✅ **Task created successfully!**\n\n📝 **{title}** (ID: `{task_id}`)\nIn plan: `{plan_id}`"

    def _format_task_updated(self, content: Dict[str, Any]) -> str:
        """Format task update result"""
        title = content.get("title", "Task")
        task_id = content.get("id", "Unknown")
        percent_complete = content.get("percentComplete", 0)

        status = "✅ Completed" if percent_complete == 100 else f"🔄 {percent_complete}% complete"

        return f"✅ **Task updated successfully!**\n\n📝 **{title}** (ID: `{task_id}`)\nStatus: {status}"

    def _format_search_results(self, content: Dict[str, Any]) -> str:
        """Format search results"""
        plans = content.get("plans", [])
        query = content.get("query", "")
        total_found = content.get("total_found", len(plans))

        if not plans:
            return f"🔍 No plans found matching '{query}'."

        result = f"🔍 **Found {total_found} plan(s) matching '{query}':**\n\n"

        for plan in plans:
            title = plan.get("title", "Untitled")
            plan_id = plan.get("id", "Unknown")
            result += f"• **{title}** (ID: `{plan_id}`)\n"

        return result

    def _create_chat_response(
        self,
        content: str,
        model: str = "planner-assistant",
        conversation_id: str = None
    ) -> Dict[str, Any]:
        """Create OpenAI-compatible chat completion response"""
        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        timestamp = int(datetime.now().timestamp())

        return {
            "id": response_id,
            "object": "chat.completion",
            "created": timestamp,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": len(content.split()),
                "total_tokens": len(content.split())
            }
        }

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response"""
        return self._create_chat_response(
            content=f"❌ Error: {error_message}",
            model="planner-assistant"
        )
