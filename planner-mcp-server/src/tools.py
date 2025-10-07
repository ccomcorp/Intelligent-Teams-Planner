"""
MCP Tools Registry for Microsoft Planner operations
"""

import os
from typing import List, Dict, Any, Optional, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

import structlog

from .graph_client import GraphAPIClient, GraphAPIError
from .database import Database
from .cache import CacheService

logger = structlog.get_logger(__name__)

@dataclass
class ToolResult:
    """Result of tool execution"""
    success: bool
    content: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class Tool(ABC):
    """Abstract base class for MCP tools"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.parameters = self._define_parameters()

    @abstractmethod
    def _define_parameters(self) -> Dict[str, Any]:
        """Define tool parameters schema"""
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Execute the tool"""
        pass

# Plan Management Tools

class ListPlans(Tool):
    """List Microsoft Planner plans"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "list_plans",
            "List Microsoft Planner plans accessible to the user"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "group_id": {
                    "type": "string",
                    "description": "Optional group ID to filter plans"
                },
                "include_archived": {
                    "type": "boolean",
                    "description": "Include archived plans",
                    "default": False
                }
            }
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            group_id = arguments.get("group_id")
            include_archived = arguments.get("include_archived", False)

            if group_id:
                # Get plans for specific group
                plans = await self.graph_client.get_group_plans(group_id, user_id)
            else:
                # Get user's groups and their plans
                groups = await self.graph_client.get_user_groups(user_id)
                plans = []

                for group in groups:
                    if group.get("@odata.type") == "#microsoft.graph.group":
                        group_plans = await self.graph_client.get_group_plans(group["id"], user_id)
                        plans.extend(group_plans)

            # Filter archived plans if not requested
            if not include_archived:
                plans = [plan for plan in plans if not plan.get("isArchived", False)]

            # Sort by creation date
            plans.sort(key=lambda x: x.get("createdDateTime", ""), reverse=True)

            return ToolResult(
                success=True,
                content={
                    "plans": plans,
                    "total_count": len(plans)
                },
                metadata={
                    "group_id": group_id,
                    "include_archived": include_archived,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in list_plans", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error listing plans", error=str(e))
            return ToolResult(success=False, error=f"Failed to list plans: {str(e)}")

class CreatePlan(Tool):
    """Create a new Microsoft Planner plan"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "create_plan",
            "Create a new Microsoft Planner plan"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Plan title (required)"
                },
                "description": {
                    "type": "string",
                    "description": "Plan description"
                },
                "group_id": {
                    "type": "string",
                    "description": "Group ID to associate the plan with (required)"
                }
            },
            "required": ["title", "group_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            title = arguments["title"]
            group_id = arguments["group_id"]
            description = arguments.get("description", "")

            # Prepare plan data
            plan_data = {
                "title": title,
                "owner": group_id
            }

            # Create plan via Graph API
            result = await self.graph_client.create_plan(plan_data, user_id)

            if result:
                # Save to local database
                await self.database.save_plan({
                    "graph_id": result["id"],
                    "title": result["title"],
                    "description": description,
                    "owner_id": result["owner"],
                    "group_id": group_id,
                    "metadata": {
                        "created_via": "mcp_server",
                        "created_by": user_id
                    }
                })

                return ToolResult(
                    success=True,
                    content=result,
                    metadata={
                        "operation": "create_plan",
                        "plan_id": result["id"],
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                return ToolResult(success=False, error="Failed to create plan")

        except GraphAPIError as e:
            logger.error("Graph API error in create_plan", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error creating plan", error=str(e))
            return ToolResult(success=False, error=f"Failed to create plan: {str(e)}")

# Task Management Tools

class ListTasks(Tool):
    """List tasks in a Microsoft Planner plan"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "list_tasks",
            "List tasks in a Microsoft Planner plan"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID to list tasks from (required)"
                },
                "filter_completed": {
                    "type": "boolean",
                    "description": "Filter out completed tasks",
                    "default": False
                },
                "assigned_to": {
                    "type": "string",
                    "description": "Filter tasks assigned to specific user"
                }
            },
            "required": ["plan_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            plan_id = arguments["plan_id"]
            filter_completed = arguments.get("filter_completed", False)
            assigned_to = arguments.get("assigned_to")

            # Get tasks from Graph API
            tasks = await self.graph_client.get_plan_tasks(plan_id, user_id)

            # Apply filters
            if filter_completed:
                tasks = [task for task in tasks if task.get("percentComplete", 0) < 100]

            if assigned_to:
                tasks = [
                    task for task in tasks
                    if assigned_to in task.get("assignments", {}).keys()
                ]

            # Sort by priority and due date
            def sort_key(task):
                priority = task.get("priority", 5)
                due_date = task.get("dueDateTime") or "9999-12-31"
                return (priority, due_date)

            tasks.sort(key=sort_key)

            return ToolResult(
                success=True,
                content={
                    "tasks": tasks,
                    "total_count": len(tasks),
                    "plan_id": plan_id
                },
                metadata={
                    "filter_completed": filter_completed,
                    "assigned_to": assigned_to,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in list_tasks", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error listing tasks", error=str(e))
            return ToolResult(success=False, error=f"Failed to list tasks: {str(e)}")

class CreateTask(Tool):
    """Create a new task in a Microsoft Planner plan"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "create_task",
            "Create a new task in a Microsoft Planner plan"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID to create task in (required)"
                },
                "title": {
                    "type": "string",
                    "description": "Task title (required)"
                },
                "description": {
                    "type": "string",
                    "description": "Task description"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date (ISO 8601 format)"
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority (1=urgent, 5=medium, 9=low)",
                    "minimum": 1,
                    "maximum": 10
                },
                "bucket_id": {
                    "type": "string",
                    "description": "Bucket ID to place task in"
                },
                "assigned_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "User IDs to assign task to"
                }
            },
            "required": ["plan_id", "title"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            plan_id = arguments["plan_id"]
            title = arguments["title"]
            description = arguments.get("description", "")
            due_date = arguments.get("due_date")
            priority = arguments.get("priority", 5)
            bucket_id = arguments.get("bucket_id")
            assigned_to = arguments.get("assigned_to", [])

            # Prepare task data
            task_data = {
                "planId": plan_id,
                "title": title,
                "priority": priority
            }

            if due_date:
                task_data["dueDateTime"] = due_date

            if bucket_id:
                task_data["bucketId"] = bucket_id

            # Prepare assignments
            if assigned_to:
                assignments = {}
                for user_id_assignment in assigned_to:
                    assignments[user_id_assignment] = {
                        "@odata.type": "#microsoft.graph.plannerAssignment",
                        "orderHint": " !"
                    }
                task_data["assignments"] = assignments

            # Create task via Graph API
            result = await self.graph_client.create_task(task_data, user_id)

            if result:
                # Save to local database
                await self.database.save_task({
                    "graph_id": result["id"],
                    "plan_graph_id": plan_id,
                    "title": result["title"],
                    "description": description,
                    "bucket_id": result.get("bucketId"),
                    "assigned_to": assigned_to,
                    "priority": result.get("priority", 5),
                    "due_date": datetime.fromisoformat(due_date.replace("Z", "+00:00")) if due_date else None,
                    "completion_percentage": result.get("percentComplete", 0),
                    "metadata": {
                        "created_via": "mcp_server",
                        "created_by": user_id
                    }
                })

                return ToolResult(
                    success=True,
                    content=result,
                    metadata={
                        "operation": "create_task",
                        "task_id": result["id"],
                        "plan_id": plan_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                return ToolResult(success=False, error="Failed to create task")

        except GraphAPIError as e:
            logger.error("Graph API error in create_task", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error creating task", error=str(e))
            return ToolResult(success=False, error=f"Failed to create task: {str(e)}")

class UpdateTask(Tool):
    """Update an existing task in Microsoft Planner"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "update_task",
            "Update an existing task in Microsoft Planner"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to update (required)"
                },
                "title": {
                    "type": "string",
                    "description": "New task title"
                },
                "percent_complete": {
                    "type": "integer",
                    "description": "Completion percentage (0-100)",
                    "minimum": 0,
                    "maximum": 100
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date (ISO 8601 format)"
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority (1=urgent, 5=medium, 9=low)",
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["task_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            task_id = arguments["task_id"]

            # Get current task to get ETag
            current_task = await self.graph_client.get_task_details(task_id, user_id)
            if not current_task:
                return ToolResult(success=False, error="Task not found")

            # Prepare update data
            update_data = {"etag": current_task.get("@odata.etag")}

            if "title" in arguments:
                update_data["title"] = arguments["title"]

            if "percent_complete" in arguments:
                update_data["percentComplete"] = arguments["percent_complete"]

            if "due_date" in arguments:
                update_data["dueDateTime"] = arguments["due_date"]

            if "priority" in arguments:
                update_data["priority"] = arguments["priority"]

            # Update task via Graph API
            result = await self.graph_client.update_task(task_id, update_data, user_id)

            if result:
                # Update local database
                await self.database.save_task({
                    "graph_id": task_id,
                    "plan_graph_id": result.get("planId"),
                    "title": result.get("title"),
                    "priority": result.get("priority"),
                    "completion_percentage": result.get("percentComplete", 0),
                    "is_completed": result.get("percentComplete", 0) == 100,
                    "metadata": {
                        "updated_via": "mcp_server",
                        "updated_by": user_id
                    }
                })

                return ToolResult(
                    success=True,
                    content=result,
                    metadata={
                        "operation": "update_task",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                return ToolResult(success=False, error="Failed to update task")

        except GraphAPIError as e:
            logger.error("Graph API error in update_task", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error updating task", error=str(e))
            return ToolResult(success=False, error=f"Failed to update task: {str(e)}")

# Search and Query Tools

class SearchPlans(Tool):
    """Search for plans by title or description"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "search_plans",
            "Search for Microsoft Planner plans by title or description"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (required)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                    "maximum": 50
                }
            },
            "required": ["query"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            query = arguments["query"].lower()
            limit = arguments.get("limit", 10)

            # Get all accessible plans
            groups = await self.graph_client.get_user_groups(user_id)
            all_plans = []

            for group in groups:
                if group.get("@odata.type") == "#microsoft.graph.group":
                    group_plans = await self.graph_client.get_group_plans(group["id"], user_id)
                    all_plans.extend(group_plans)

            # Filter plans by query
            matching_plans = []
            for plan in all_plans:
                title = plan.get("title", "").lower()
                if query in title:
                    plan["match_score"] = 2 if query == title else 1
                    matching_plans.append(plan)

            # Sort by match score and limit results
            matching_plans.sort(key=lambda x: x.get("match_score", 0), reverse=True)
            matching_plans = matching_plans[:limit]

            return ToolResult(
                success=True,
                content={
                    "plans": matching_plans,
                    "query": arguments["query"],
                    "total_found": len(matching_plans)
                },
                metadata={
                    "search_query": query,
                    "limit": limit,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in search_plans", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error searching plans", error=str(e))
            return ToolResult(success=False, error=f"Failed to search plans: {str(e)}")

class ToolRegistry:
    """Registry and manager for MCP tools"""

    def __init__(
        self,
        graph_client: GraphAPIClient,
        database: Database,
        cache_service: CacheService
    ):
        self.graph_client = graph_client
        self.database = database
        self.cache_service = cache_service
        self.tools: Dict[str, Tool] = {}

    async def initialize(self):
        """Initialize all tools"""
        try:
            # Register plan management tools
            self.tools["list_plans"] = ListPlans(self.graph_client, self.database)
            self.tools["create_plan"] = CreatePlan(self.graph_client, self.database)

            # Register task management tools
            self.tools["list_tasks"] = ListTasks(self.graph_client, self.database)
            self.tools["create_task"] = CreateTask(self.graph_client, self.database)
            self.tools["update_task"] = UpdateTask(self.graph_client, self.database)

            # Register search tools
            self.tools["search_plans"] = SearchPlans(self.graph_client, self.database)

            logger.info("Tool registry initialized", tool_count=len(self.tools))

        except Exception as e:
            logger.error("Failed to initialize tool registry", error=str(e))
            raise

    async def get_tool_definitions(self) -> List[Tool]:
        """Get all tool definitions"""
        return list(self.tools.values())

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: str = "default"
    ) -> ToolResult:
        """Execute a tool by name"""
        try:
            if tool_name not in self.tools:
                return ToolResult(
                    success=False,
                    error=f"Tool '{tool_name}' not found"
                )

            tool = self.tools[tool_name]
            context = {
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }

            logger.info("Executing tool", tool=tool_name, arguments=arguments, user_id=user_id)

            result = await tool.execute(arguments, context)

            # Log execution result
            if result.success:
                logger.info("Tool executed successfully", tool=tool_name, user_id=user_id)
            else:
                logger.warning("Tool execution failed", tool=tool_name, error=result.error, user_id=user_id)

            return result

        except Exception as e:
            logger.error("Error executing tool", tool=tool_name, error=str(e))
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}"
            )