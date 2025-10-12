"""
MCP Tools Registry for Microsoft Planner operations
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from abc import ABC, abstractmethod

import structlog

from .graph_client import GraphAPIClient, GraphAPIError
from .database import Database
from .cache import CacheService
from .nlp import (
    IntentClassifier,
    EntityExtractor,
    DateParser,
    ConversationContextManager,
    BatchProcessor
)

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

    async def _update_task_description(self, task_id: str, description: str, user_id: str) -> None:
        """Update task description via task details API after creation"""
        import httpx

        access_token = await self.graph_client.get_access_token(user_id)
        if not access_token:
            raise Exception("No valid access token available")

        # Get current task details to get ETag
        async with httpx.AsyncClient() as client:
            details_response = await client.get(
                f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if details_response.status_code == 200:
                details_data = details_response.json()
                etag = details_data.get("@odata.etag")

                # Update description
                update_response = await client.patch(
                    f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "If-Match": etag
                    },
                    json={"description": description}
                )

                if update_response.status_code not in [200, 204]:
                    raise Exception(f"Failed to update description: {update_response.status_code}")

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
                    "description": "Task description (set after creation via task details)"
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
            bucket_id = arguments.get("bucket_id")
            assigned_to = arguments.get("assigned_to", [])

            # Prepare task data (only fields supported during creation)
            task_data = {
                "planId": plan_id,
                "title": title
            }

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
                task_id = result["id"]

                # Update description if provided (requires separate API call to task details)
                if description:
                    try:
                        await self._update_task_description(task_id, description, user_id)
                    except Exception as e:
                        logger.warning("Failed to set task description", error=str(e))
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

    async def _update_task_description(self, task_id: str, description: str, user_id: str) -> None:
        """Update task description via task details API"""
        import httpx

        access_token = await self.graph_client.get_access_token(user_id)
        if not access_token:
            raise Exception("No valid access token available")

        # Get current task details to get ETag
        async with httpx.AsyncClient() as client:
            details_response = await client.get(
                f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if details_response.status_code == 200:
                details_data = details_response.json()
                etag = details_data.get("@odata.etag")

                # Update description
                update_response = await client.patch(
                    f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "If-Match": etag
                    },
                    json={"description": description}
                )

                if update_response.status_code not in [200, 204]:
                    raise Exception(f"Failed to update description: {update_response.status_code}")

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
                "description": {
                    "type": "string",
                    "description": "Task description/notes"
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
                "start_date": {
                    "type": "string",
                    "description": "Start date (ISO 8601 format)"
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority (0-1=urgent, 2-4=important, 5-7=medium, 8-10=low)",
                    "minimum": 0,
                    "maximum": 10
                },
                "bucket_id": {
                    "type": "string",
                    "description": "Bucket ID to move task to"
                },
                "assigned_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "User IDs to assign task to (replaces existing assignments)"
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Category labels to apply to task"
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

            if "start_date" in arguments:
                update_data["startDateTime"] = arguments["start_date"]

            if "priority" in arguments:
                update_data["priority"] = arguments["priority"]

            if "bucket_id" in arguments:
                update_data["bucketId"] = arguments["bucket_id"]

            # Handle assignments
            if "assigned_to" in arguments:
                assignments = {}
                for user_id_assignment in arguments["assigned_to"]:
                    assignments[user_id_assignment] = {
                        "@odata.type": "#microsoft.graph.plannerAssignment",
                        "orderHint": " !"
                    }
                update_data["assignments"] = assignments

            # Handle categories
            if "categories" in arguments:
                applied_categories = {}
                for i, category in enumerate(arguments["categories"][:6]):  # Max 6 categories
                    category_key = f"category{i+1}"
                    applied_categories[category_key] = True
                update_data["appliedCategories"] = applied_categories

            # Handle description update (requires separate API call to task details)
            description_updated = False
            if "description" in arguments:
                try:
                    await self._update_task_description(task_id, arguments["description"], user_id)
                    description_updated = True
                except Exception as e:
                    logger.warning("Failed to update task description", error=str(e))

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

                # Collect updated fields for response
                updated_fields = []
                if "title" in arguments:
                    updated_fields.append("title")
                if "percent_complete" in arguments:
                    updated_fields.append("completion_percentage")
                if "due_date" in arguments:
                    updated_fields.append("due_date")
                if "start_date" in arguments:
                    updated_fields.append("start_date")
                if "priority" in arguments:
                    updated_fields.append("priority")
                if "bucket_id" in arguments:
                    updated_fields.append("bucket_assignment")
                if "assigned_to" in arguments:
                    updated_fields.append("assignments")
                if "categories" in arguments:
                    updated_fields.append("categories")
                if description_updated:
                    updated_fields.append("description")

                return ToolResult(
                    success=True,
                    content={
                        "task": result,
                        "updated_fields": updated_fields,
                        "description_updated": description_updated
                    },
                    metadata={
                        "operation": "update_task",
                        "task_id": task_id,
                        "updated_fields": updated_fields,
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

# Enhanced Task Operations

class GetTaskDetails(Tool):
    """Get detailed information about a specific task"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "get_task_details",
            "Get detailed information about a specific task including comments and metadata"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to get details for (required)"
                },
                "include_comments": {
                    "type": "boolean",
                    "description": "Include task comments",
                    "default": True
                }
            },
            "required": ["task_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            task_id = arguments["task_id"]
            include_comments = arguments.get("include_comments", True)

            # Get task details from Graph API
            task = await self.graph_client.get_task_details(task_id, user_id)
            if not task:
                return ToolResult(success=False, error="Task not found")

            # Get task comments if requested
            comments = []
            if include_comments:
                try:
                    comments = await self.graph_client.get_task_comments(task_id, user_id)
                except Exception as e:
                    logger.warning("Failed to get task comments", error=str(e))

            # Enhance task data with readable information
            enhanced_task = {
                **task,
                "completion_status": "Completed" if task.get("percentComplete", 0) == 100 else "In Progress",
                "priority_text": {1: "Urgent", 2: "Important", 3: "Medium", 4: "Low", 5: "Medium"}.get(task.get("priority", 5), "Medium"),
                "assigned_users": list(task.get("assignments", {}).keys()),
                "comments": comments,
                "comment_count": len(comments)
            }

            return ToolResult(
                success=True,
                content=enhanced_task,
                metadata={
                    "operation": "get_task_details",
                    "task_id": task_id,
                    "include_comments": include_comments,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in get_task_details", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error getting task details", error=str(e))
            return ToolResult(success=False, error=f"Failed to get task details: {str(e)}")

class AddTaskComment(Tool):
    """Add a comment to a task"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "add_task_comment",
            "Add a comment to a Microsoft Planner task"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to add comment to (required)"
                },
                "comment": {
                    "type": "string",
                    "description": "Comment text (required)"
                }
            },
            "required": ["task_id", "comment"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            task_id = arguments["task_id"]
            comment_text = arguments["comment"]

            # Add comment via Graph API
            result = await self.graph_client.add_task_comment(task_id, comment_text, user_id)

            if result:
                return ToolResult(
                    success=True,
                    content={
                        "comment_id": result.get("id"),
                        "comment": comment_text,
                        "task_id": task_id,
                        "created_at": result.get("createdDateTime")
                    },
                    metadata={
                        "operation": "add_task_comment",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                return ToolResult(success=False, error="Failed to add comment")

        except GraphAPIError as e:
            logger.error("Graph API error in add_task_comment", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error adding task comment", error=str(e))
            return ToolResult(success=False, error=f"Failed to add comment: {str(e)}")

class SearchTasks(Tool):
    """Search for tasks across all accessible plans"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "search_tasks",
            "Search for tasks by title or description across all accessible plans"
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
                "plan_id": {
                    "type": "string",
                    "description": "Optional plan ID to limit search to specific plan"
                },
                "status": {
                    "type": "string",
                    "enum": ["all", "active", "completed"],
                    "description": "Filter by task status",
                    "default": "all"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 20,
                    "maximum": 100
                }
            },
            "required": ["query"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            query = arguments["query"].lower()
            plan_id = arguments.get("plan_id")
            status_filter = arguments.get("status", "all")
            limit = arguments.get("limit", 20)

            matching_tasks = []

            if plan_id:
                # Search in specific plan
                tasks = await self.graph_client.get_plan_tasks(plan_id, user_id)
                plan_info = await self.graph_client.get_plan_details(plan_id, user_id)

                for task in tasks:
                    if self._task_matches_query(task, query, status_filter):
                        task["plan_title"] = plan_info.get("title", "Unknown Plan")
                        task["plan_id"] = plan_id
                        matching_tasks.append(task)
            else:
                # Search across all accessible plans
                groups = await self.graph_client.get_user_groups(user_id)

                for group in groups:
                    if group.get("@odata.type") == "#microsoft.graph.group":
                        try:
                            plans = await self.graph_client.get_group_plans(group["id"], user_id)

                            for plan in plans:
                                tasks = await self.graph_client.get_plan_tasks(plan["id"], user_id)

                                for task in tasks:
                                    if self._task_matches_query(task, query, status_filter):
                                        task["plan_title"] = plan.get("title", "Unknown Plan")
                                        task["plan_id"] = plan["id"]
                                        matching_tasks.append(task)
                        except Exception as e:
                            logger.warning(f"Failed to search tasks in group {group['id']}", error=str(e))

            # Sort by relevance and limit results
            matching_tasks.sort(key=lambda x: self._calculate_relevance_score(x, query), reverse=True)
            matching_tasks = matching_tasks[:limit]

            return ToolResult(
                success=True,
                content={
                    "tasks": matching_tasks,
                    "query": arguments["query"],
                    "total_found": len(matching_tasks),
                    "status_filter": status_filter
                },
                metadata={
                    "search_query": query,
                    "plan_id": plan_id,
                    "limit": limit,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in search_tasks", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error searching tasks", error=str(e))
            return ToolResult(success=False, error=f"Failed to search tasks: {str(e)}")

    def _task_matches_query(self, task: Dict[str, Any], query: str, status_filter: str) -> bool:
        """Check if task matches search criteria"""
        title = task.get("title", "").lower()

        # Check status filter
        if status_filter == "active" and task.get("percentComplete", 0) == 100:
            return False
        elif status_filter == "completed" and task.get("percentComplete", 0) != 100:
            return False

        # Check query match
        return query in title

    def _calculate_relevance_score(self, task: Dict[str, Any], query: str) -> int:
        """Calculate relevance score for sorting"""
        title = task.get("title", "").lower()
        score = 0

        if title == query:
            score += 10
        elif title.startswith(query):
            score += 5
        elif query in title:
            score += 2

        # Boost recent tasks
        created = task.get("createdDateTime", "")
        if created and "2024" in created:
            score += 1

        return score

class GetMyTasks(Tool):
    """Get all tasks assigned to the current user"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "get_my_tasks",
            "Get all tasks assigned to the current user across all plans"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["all", "active", "completed"],
                    "description": "Filter by task status",
                    "default": "active"
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["due_date", "priority", "created", "title"],
                    "description": "Sort tasks by field",
                    "default": "due_date"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 50,
                    "maximum": 200
                }
            }
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            status_filter = arguments.get("status", "active")
            sort_by = arguments.get("sort_by", "due_date")
            limit = arguments.get("limit", 50)

            my_tasks = []

            # Get user's groups and their plans
            groups = await self.graph_client.get_user_groups(user_id)

            for group in groups:
                if group.get("@odata.type") == "#microsoft.graph.group":
                    try:
                        plans = await self.graph_client.get_group_plans(group["id"], user_id)

                        for plan in plans:
                            tasks = await self.graph_client.get_plan_tasks(plan["id"], user_id)

                            for task in tasks:
                                # Check if task is assigned to user
                                assignments = task.get("assignments", {})
                                if user_id in assignments:
                                    # Apply status filter
                                    percent_complete = task.get("percentComplete", 0)
                                    if status_filter == "active" and percent_complete == 100:
                                        continue
                                    elif status_filter == "completed" and percent_complete != 100:
                                        continue

                                    # Enhance task with plan info
                                    task["plan_title"] = plan.get("title", "Unknown Plan")
                                    task["plan_id"] = plan["id"]
                                    task["completion_status"] = "Completed" if percent_complete == 100 else "In Progress"
                                    my_tasks.append(task)
                    except Exception as e:
                        logger.warning(f"Failed to get tasks from group {group['id']}", error=str(e))

            # Sort tasks
            my_tasks.sort(key=lambda x: self._get_sort_key(x, sort_by))
            my_tasks = my_tasks[:limit]

            return ToolResult(
                success=True,
                content={
                    "tasks": my_tasks,
                    "total_count": len(my_tasks),
                    "status_filter": status_filter,
                    "sort_by": sort_by
                },
                metadata={
                    "user_id": user_id,
                    "status_filter": status_filter,
                    "sort_by": sort_by,
                    "limit": limit,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in get_my_tasks", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error getting user tasks", error=str(e))
            return ToolResult(success=False, error=f"Failed to get user tasks: {str(e)}")

    def _get_sort_key(self, task: Dict[str, Any], sort_by: str):
        """Get sort key for task sorting"""
        if sort_by == "due_date":
            return task.get("dueDateTime") or "9999-12-31"
        elif sort_by == "priority":
            return task.get("priority", 5)
        elif sort_by == "created":
            return task.get("createdDateTime", "")
        elif sort_by == "title":
            return task.get("title", "").lower()
        else:
            return task.get("dueDateTime") or "9999-12-31"

# Smart Querying Tools

class GetTaskByPosition(Tool):
    """Get task by its position/number in a plan"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "get_task_by_position",
            "Get a task by its position number in a plan (e.g., 'task 1', 'first task')"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID to get task from (required)"
                },
                "position": {
                    "type": "integer",
                    "description": "Task position/number (1-based, required)",
                    "minimum": 1
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["created", "priority", "due_date", "title"],
                    "description": "How to order tasks for position calculation",
                    "default": "created"
                }
            },
            "required": ["plan_id", "position"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            plan_id = arguments["plan_id"]
            position = arguments["position"]
            sort_by = arguments.get("sort_by", "created")

            # Get all tasks in plan
            tasks = await self.graph_client.get_plan_tasks(plan_id, user_id)

            if not tasks:
                return ToolResult(success=False, error="No tasks found in plan")

            # Sort tasks based on criteria
            if sort_by == "created":
                tasks.sort(key=lambda x: x.get("createdDateTime", ""))
            elif sort_by == "priority":
                tasks.sort(key=lambda x: x.get("priority", 5))
            elif sort_by == "due_date":
                tasks.sort(key=lambda x: x.get("dueDateTime") or "9999-12-31")
            elif sort_by == "title":
                tasks.sort(key=lambda x: x.get("title", "").lower())

            # Check if position is valid
            if position > len(tasks):
                return ToolResult(
                    success=False,
                    error=f"Position {position} is out of range. Plan has {len(tasks)} tasks."
                )

            # Get task at position (convert to 0-based index)
            selected_task = tasks[position - 1]

            # Get plan info for context
            plan_info = await self.graph_client.get_plan_details(plan_id, user_id)

            # Enhance task with position and plan info
            enhanced_task = {
                **selected_task,
                "position": position,
                "total_tasks": len(tasks),
                "plan_title": plan_info.get("title", "Unknown Plan"),
                "plan_id": plan_id,
                "sort_order": sort_by,
                "completion_status": "Completed" if selected_task.get("percentComplete", 0) == 100 else "In Progress"
            }

            return ToolResult(
                success=True,
                content=enhanced_task,
                metadata={
                    "operation": "get_task_by_position",
                    "plan_id": plan_id,
                    "position": position,
                    "sort_by": sort_by,
                    "total_tasks": len(tasks),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in get_task_by_position", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error getting task by position", error=str(e))
            return ToolResult(success=False, error=f"Failed to get task by position: {str(e)}")

class GetNextTask(Tool):
    """Get the next recommended task for the user"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "get_next_task",
            "Get the next recommended task based on priority, due dates, and user assignments"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Optional plan ID to limit search to specific plan"
                },
                "strategy": {
                    "type": "string",
                    "enum": ["urgent", "due_soon", "high_priority", "oldest"],
                    "description": "Strategy for selecting next task",
                    "default": "urgent"
                }
            }
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            plan_id = arguments.get("plan_id")
            strategy = arguments.get("strategy", "urgent")

            # Get user's active tasks
            if plan_id:
                # Get tasks from specific plan
                tasks = await self.graph_client.get_plan_tasks(plan_id, user_id)
                plan_info = await self.graph_client.get_plan_details(plan_id, user_id)

                # Filter for user's incomplete tasks
                user_tasks = []
                for task in tasks:
                    if (user_id in task.get("assignments", {}) and
                        task.get("percentComplete", 0) < 100):
                        task["plan_title"] = plan_info.get("title", "Unknown Plan")
                        task["plan_id"] = plan_id
                        user_tasks.append(task)
            else:
                # Get tasks from all plans using get_my_tasks logic
                user_tasks = []
                groups = await self.graph_client.get_user_groups(user_id)

                for group in groups:
                    if group.get("@odata.type") == "#microsoft.graph.group":
                        try:
                            plans = await self.graph_client.get_group_plans(group["id"], user_id)

                            for plan in plans:
                                tasks = await self.graph_client.get_plan_tasks(plan["id"], user_id)

                                for task in tasks:
                                    if (user_id in task.get("assignments", {}) and
                                        task.get("percentComplete", 0) < 100):
                                        task["plan_title"] = plan.get("title", "Unknown Plan")
                                        task["plan_id"] = plan["id"]
                                        user_tasks.append(task)
                        except Exception as e:
                            logger.warning(f"Failed to get tasks from group {group['id']}", error=str(e))

            if not user_tasks:
                return ToolResult(
                    success=True,
                    content=None,
                    metadata={
                        "message": "No active tasks found",
                        "strategy": strategy,
                        "plan_id": plan_id
                    }
                )

            # Select next task based on strategy
            next_task = self._select_next_task(user_tasks, strategy)

            if next_task:
                # Enhance with context
                next_task["selection_strategy"] = strategy
                next_task["completion_status"] = "In Progress"
                next_task["total_active_tasks"] = len(user_tasks)

            return ToolResult(
                success=True,
                content=next_task,
                metadata={
                    "operation": "get_next_task",
                    "strategy": strategy,
                    "plan_id": plan_id,
                    "total_active_tasks": len(user_tasks),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in get_next_task", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error getting next task", error=str(e))
            return ToolResult(success=False, error=f"Failed to get next task: {str(e)}")

    def _select_next_task(self, tasks: List[Dict[str, Any]], strategy: str) -> Optional[Dict[str, Any]]:
        """Select next task based on strategy"""
        if not tasks:
            return None

        if strategy == "urgent":
            # Priority: high priority + due soon
            scored_tasks = []
            for task in tasks:
                score = 0
                priority = task.get("priority", 5)
                due_date = task.get("dueDateTime")

                # Higher priority (lower number) = higher score
                score += (10 - priority) * 2

                # Due soon = higher score
                if due_date:
                    from datetime import datetime, timezone
                    try:
                        due = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                        now = datetime.now(timezone.utc)
                        days_until_due = (due - now).days

                        if days_until_due < 0:  # Overdue
                            score += 20
                        elif days_until_due <= 1:  # Due today/tomorrow
                            score += 15
                        elif days_until_due <= 7:  # Due this week
                            score += 10
                    except:
                        pass

                scored_tasks.append((score, task))

            scored_tasks.sort(key=lambda x: x[0], reverse=True)
            return scored_tasks[0][1] if scored_tasks else None

        elif strategy == "due_soon":
            # Sort by due date
            tasks_with_dates = [t for t in tasks if t.get("dueDateTime")]
            if tasks_with_dates:
                tasks_with_dates.sort(key=lambda x: x.get("dueDateTime"))
                return tasks_with_dates[0]
            else:
                return tasks[0] if tasks else None

        elif strategy == "high_priority":
            # Sort by priority (lower number = higher priority)
            tasks.sort(key=lambda x: x.get("priority", 5))
            return tasks[0]

        elif strategy == "oldest":
            # Sort by creation date
            tasks.sort(key=lambda x: x.get("createdDateTime", ""))
            return tasks[0]

        return tasks[0] if tasks else None

class ListBuckets(Tool):
    """List buckets (categories) in a plan"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "list_buckets",
            "List buckets (categories) in a Microsoft Planner plan"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID to list buckets from (required)"
                },
                "include_task_counts": {
                    "type": "boolean",
                    "description": "Include task counts for each bucket",
                    "default": True
                }
            },
            "required": ["plan_id"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            plan_id = arguments["plan_id"]
            include_task_counts = arguments.get("include_task_counts", True)

            # Get buckets from Graph API
            buckets = await self.graph_client.get_plan_buckets(plan_id, user_id)

            if include_task_counts:
                # Get all tasks to count per bucket
                tasks = await self.graph_client.get_plan_tasks(plan_id, user_id)

                # Count tasks per bucket
                bucket_task_counts = {}
                for task in tasks:
                    bucket_id = task.get("bucketId")
                    if bucket_id:
                        bucket_task_counts[bucket_id] = bucket_task_counts.get(bucket_id, 0) + 1

                # Add task counts to buckets
                for bucket in buckets:
                    bucket_id = bucket.get("id")
                    bucket["task_count"] = bucket_task_counts.get(bucket_id, 0)
                    bucket["completed_tasks"] = len([
                        t for t in tasks
                        if t.get("bucketId") == bucket_id and t.get("percentComplete", 0) == 100
                    ])
                    bucket["active_tasks"] = bucket["task_count"] - bucket["completed_tasks"]

            # Get plan info for context
            plan_info = await self.graph_client.get_plan_details(plan_id, user_id)

            return ToolResult(
                success=True,
                content={
                    "buckets": buckets,
                    "total_buckets": len(buckets),
                    "plan_title": plan_info.get("title", "Unknown Plan"),
                    "plan_id": plan_id
                },
                metadata={
                    "operation": "list_buckets",
                    "plan_id": plan_id,
                    "include_task_counts": include_task_counts,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except GraphAPIError as e:
            logger.error("Graph API error in list_buckets", error=str(e))
            return ToolResult(success=False, error=f"Graph API error: {str(e)}")
        except Exception as e:
            logger.error("Error listing buckets", error=str(e))
            return ToolResult(success=False, error=f"Failed to list buckets: {str(e)}")

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


class ProcessNaturalLanguage(Tool):
    """Process natural language commands and route to appropriate tools"""

    def __init__(self, graph_client: GraphAPIClient, database: Database, nlp_components: Dict[str, Any]):
        super().__init__(
            "process_natural_language",
            "Process natural language commands and convert them to structured actions"
        )
        self.graph_client = graph_client
        self.database = database
        self.nlp_components = nlp_components

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_input": {
                    "type": "string",
                    "description": "Natural language input from the user"
                },
                "session_id": {
                    "type": "string",
                    "description": "Session identifier for conversation context",
                    "default": "default"
                },
                "user_id": {
                    "type": "string",
                    "description": "User identifier",
                    "default": "default"
                }
            },
            "required": ["user_input"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Process natural language input and route to appropriate action"""
        try:
            user_input = arguments["user_input"]
            session_id = arguments.get("session_id", "default")
            user_id = context.get("user_id", "default")

            # Extract conversation context
            conversation_context = await self.nlp_components["context_manager"].get_conversation_context(
                user_id, session_id
            )

            # Classify intent
            intent_result = await self.nlp_components["intent_classifier"].classify_intent(
                user_input, conversation_context
            )

            # Extract entities
            entities = await self.nlp_components["entity_extractor"].extract_entities(
                user_input, conversation_context
            )

            # Parse dates if present
            parsed_dates = await self.nlp_components["date_parser"].parse_dates(user_input)
            if parsed_dates:
                entities.update(parsed_dates)

            # Check for batch operations
            batch_operation = await self.nlp_components["batch_processor"].detect_batch_operation(
                user_input, entities
            )

            # Update conversation context
            await self.nlp_components["context_manager"].update_context(
                user_id, session_id, {
                    "last_input": user_input,
                    "last_intent": intent_result,
                    "last_entities": entities,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            result = {
                "intent": intent_result,
                "entities": entities,
                "batch_operation": batch_operation,
                "conversation_context": conversation_context,
                "suggested_actions": self._generate_action_suggestions(intent_result, entities, batch_operation),
                "confidence": intent_result.get("confidence", 0.0)
            }

            logger.info("Natural language processing completed",
                        user_id=user_id,
                        intent=intent_result.get("intent"),
                        entities_count=len(entities),
                        is_batch=batch_operation is not None)

            return ToolResult(
                success=True,
                content=result,
                metadata={
                    "processing_time": datetime.utcnow().isoformat(),
                    "nlp_version": "1.0",
                    "user_id": user_id,
                    "session_id": session_id
                }
            )

        except Exception as e:
            logger.error("Error processing natural language", error=str(e), user_input=user_input[:100])
            return ToolResult(success=False, error=f"Failed to process natural language: {str(e)}")

    def _generate_action_suggestions(self, intent_result: Dict[str, Any], entities: Dict[str, Any],
                                   batch_operation: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate suggested actions based on NLP analysis"""
        suggestions = []

        intent = intent_result.get("intent", "unknown")

        try:
            if intent == "create_plan":
                suggestions.append({
                    "tool": "create_plan",
                    "parameters": {
                        "title": entities.get("PLAN_NAME", "New Plan"),
                        "description": entities.get("DESCRIPTION", ""),
                        "owner": entities.get("PERSON", "")
                    },
                    "confidence": intent_result.get("confidence", 0.0)
                })

            elif intent == "create_task":
                task_params = {
                    "title": entities.get("TASK_NAME", "New Task"),
                    "description": entities.get("DESCRIPTION", ""),
                    "plan_id": entities.get("PLAN_ID", "")
                }

                # Add date information if available
                if "DUE_DATE" in entities:
                    task_params["due_date"] = entities["DUE_DATE"]

                if "PRIORITY" in entities:
                    task_params["priority"] = entities["PRIORITY"]

                if "PERSON" in entities:
                    task_params["assignee"] = entities["PERSON"]

                suggestions.append({
                    "tool": "create_task",
                    "parameters": task_params,
                    "confidence": intent_result.get("confidence", 0.0)
                })

            elif intent == "list_tasks":
                list_params = {}
                if "PLAN_ID" in entities:
                    list_params["plan_id"] = entities["PLAN_ID"]
                if "PERSON" in entities:
                    list_params["assignee"] = entities["PERSON"]

                suggestions.append({
                    "tool": "list_tasks",
                    "parameters": list_params,
                    "confidence": intent_result.get("confidence", 0.0)
                })

            elif intent == "search":
                search_params = {
                    "query": entities.get("SEARCH_TERM", ""),
                    "include_completed": entities.get("INCLUDE_COMPLETED", True)
                }

                suggestions.append({
                    "tool": "search_tasks",
                    "parameters": search_params,
                    "confidence": intent_result.get("confidence", 0.0)
                })

            # Handle batch operations
            if batch_operation and batch_operation.get("is_batch"):
                suggestions.append({
                    "tool": "execute_batch_operation",
                    "parameters": {
                        "operation_type": batch_operation.get("operation_type"),
                        "batch_parameters": batch_operation
                    },
                    "confidence": 0.8,
                    "is_batch": True
                })

            return suggestions

        except Exception as e:
            logger.error("Error generating action suggestions", error=str(e))
            return []


class AddTaskChecklist(Tool):
    """Add checklist items to a task"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "add_task_checklist",
            "Add checklist items to a Microsoft Planner task"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to add checklist to (required)"
                },
                "checklist_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of checklist item titles (required)"
                }
            },
            "required": ["task_id", "checklist_items"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            task_id = arguments["task_id"]
            checklist_items = arguments["checklist_items"]

            # Get current task details to get ETag
            import httpx
            access_token = await self.graph_client.get_access_token(user_id)
            if not access_token:
                return ToolResult(success=False, error="No valid access token available")

            async with httpx.AsyncClient() as client:
                details_response = await client.get(
                    f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if details_response.status_code == 200:
                    details_data = details_response.json()
                    etag = details_data.get("@odata.etag")
                    existing_checklist = details_data.get("checklist", {})

                    # Add new checklist items
                    for item_title in checklist_items:
                        item_id = f"checklist_item_{len(existing_checklist) + 1}"
                        existing_checklist[item_id] = {
                            "@odata.type": "#microsoft.graph.plannerChecklistItem",
                            "title": item_title,
                            "isChecked": False
                        }

                    # Update checklist
                    update_response = await client.patch(
                        f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "If-Match": etag
                        },
                        json={"checklist": existing_checklist}
                    )

                    if update_response.status_code in [200, 204]:
                        return ToolResult(
                            success=True,
                            content={
                                "task_id": task_id,
                                "added_items": checklist_items,
                                "total_items": len(existing_checklist)
                            },
                            metadata={
                                "operation": "add_task_checklist",
                                "task_id": task_id,
                                "items_added": len(checklist_items),
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        )
                    else:
                        return ToolResult(success=False, error=f"Failed to update checklist: {update_response.status_code}")
                else:
                    return ToolResult(success=False, error="Task not found")

        except Exception as e:
            logger.error("Error adding task checklist", error=str(e))
            return ToolResult(success=False, error=f"Failed to add checklist: {str(e)}")


class UpdateTaskChecklist(Tool):
    """Update checklist item completion status"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "update_task_checklist",
            "Update checklist item completion status in a Microsoft Planner task"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID containing the checklist (required)"
                },
                "item_index": {
                    "type": "integer",
                    "description": "Index of checklist item to update (0-based, required)"
                },
                "is_checked": {
                    "type": "boolean",
                    "description": "Whether the item is completed (required)"
                }
            },
            "required": ["task_id", "item_index", "is_checked"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            task_id = arguments["task_id"]
            item_index = arguments["item_index"]
            is_checked = arguments["is_checked"]

            # Get current task details to get ETag and checklist
            import httpx
            access_token = await self.graph_client.get_access_token(user_id)
            if not access_token:
                return ToolResult(success=False, error="No valid access token available")

            async with httpx.AsyncClient() as client:
                details_response = await client.get(
                    f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if details_response.status_code == 200:
                    details_data = details_response.json()
                    etag = details_data.get("@odata.etag")
                    checklist = details_data.get("checklist", {})

                    # Find the item to update by index
                    checklist_items = list(checklist.items())
                    if item_index >= len(checklist_items):
                        return ToolResult(success=False, error=f"Checklist item index {item_index} not found")

                    item_key, item_data = checklist_items[item_index]
                    item_data["isChecked"] = is_checked

                    # Update checklist
                    update_response = await client.patch(
                        f"https://graph.microsoft.com/v1.0/planner/tasks/{task_id}/details",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "If-Match": etag
                        },
                        json={"checklist": checklist}
                    )

                    if update_response.status_code in [200, 204]:
                        return ToolResult(
                            success=True,
                            content={
                                "task_id": task_id,
                                "item_index": item_index,
                                "item_title": item_data.get("title"),
                                "is_checked": is_checked
                            },
                            metadata={
                                "operation": "update_task_checklist",
                                "task_id": task_id,
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        )
                    else:
                        return ToolResult(success=False, error=f"Failed to update checklist: {update_response.status_code}")
                else:
                    return ToolResult(success=False, error="Task not found")

        except Exception as e:
            logger.error("Error updating task checklist", error=str(e))
            return ToolResult(success=False, error=f"Failed to update checklist: {str(e)}")


class DeleteTask(Tool):
    """Delete a task from Microsoft Planner"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "delete_task",
            "Delete a task from Microsoft Planner"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to delete (required)"
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Confirmation that you want to delete the task (required)",
                    "default": False
                }
            },
            "required": ["task_id", "confirm"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            task_id = arguments["task_id"]
            confirm = arguments.get("confirm", False)

            if not confirm:
                return ToolResult(
                    success=False,
                    error="Task deletion requires explicit confirmation. Set 'confirm' parameter to true."
                )

            # Get current task to get ETag and info
            current_task = await self.graph_client.get_task_details(task_id, user_id)
            if not current_task:
                return ToolResult(success=False, error="Task not found")

            task_title = current_task.get("title", "Unknown")
            etag = current_task.get("@odata.etag")

            # Delete task via Graph API
            result = await self.graph_client.delete_task(task_id, etag, user_id)

            if result:
                # Remove from local database
                await self.database.delete_task(task_id)

                return ToolResult(
                    success=True,
                    content={
                        "task_id": task_id,
                        "task_title": task_title,
                        "deleted": True
                    },
                    metadata={
                        "operation": "delete_task",
                        "task_id": task_id,
                        "task_title": task_title,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                return ToolResult(success=False, error="Failed to delete task")

        except Exception as e:
            logger.error("Error deleting task", error=str(e))
            return ToolResult(success=False, error=f"Failed to delete task: {str(e)}")


class CreateTasksFromDocument(Tool):
    """Analyze document and create tasks based on content"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "create_tasks_from_document",
            "Analyze a document and create Planner tasks based on its content"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID to create tasks in (required)"
                },
                "document_query": {
                    "type": "string",
                    "description": "Query to find specific document or content (required)"
                },
                "bucket_id": {
                    "type": "string",
                    "description": "Bucket ID to place tasks in"
                },
                "task_prefix": {
                    "type": "string",
                    "description": "Prefix for generated task titles",
                    "default": "Doc Task"
                },
                "max_tasks": {
                    "type": "integer",
                    "description": "Maximum number of tasks to create",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5
                }
            },
            "required": ["plan_id", "document_query"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            plan_id = arguments["plan_id"]
            document_query = arguments["document_query"]
            bucket_id = arguments.get("bucket_id")
            task_prefix = arguments.get("task_prefix", "Doc Task")
            max_tasks = arguments.get("max_tasks", 5)

            # Query RAG service for relevant document content
            rag_response = await self._query_rag_service(document_query, user_id)

            if not rag_response or not rag_response.get("results"):
                return ToolResult(
                    success=False,
                    error="No relevant documents found for the query"
                )

            # Extract actionable items from document content
            tasks_to_create = await self._extract_tasks_from_content(
                rag_response["results"], task_prefix, max_tasks
            )

            if not tasks_to_create:
                return ToolResult(
                    success=False,
                    error="No actionable tasks could be extracted from the document content"
                )

            # Create tasks in Microsoft Planner
            created_tasks = []
            for task_data in tasks_to_create:
                task_data["planId"] = plan_id
                if bucket_id:
                    task_data["bucketId"] = bucket_id

                result = await self.graph_client.create_task(task_data, user_id)
                if result:
                    created_tasks.append(result)

                    # Save to local database
                    await self.database.save_task({
                        "graph_id": result["id"],
                        "plan_graph_id": plan_id,
                        "title": result["title"],
                        "description": task_data.get("description", ""),
                        "metadata": {
                            "created_via": "document_analysis",
                            "source_query": document_query,
                            "created_by": user_id
                        }
                    })

            return ToolResult(
                success=True,
                content={
                    "created_tasks": created_tasks,
                    "task_count": len(created_tasks),
                    "source_documents": len(rag_response["results"]),
                    "query_used": document_query
                },
                metadata={
                    "operation": "create_tasks_from_document",
                    "plan_id": plan_id,
                    "tasks_created": len(created_tasks),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            logger.error("Error creating tasks from document", error=str(e))
            return ToolResult(success=False, error=f"Failed to create tasks from document: {str(e)}")

    async def _query_rag_service(self, query: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Query the RAG service for document content"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://rag-service:7120/api/query",
                    json={
                        "query": query,
                        "top_k": 5,
                        "user_id": user_id
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"RAG service query failed: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Failed to query RAG service: {str(e)}")
            return None

    async def _extract_tasks_from_content(self, documents: List[Dict], prefix: str, max_tasks: int) -> List[Dict[str, Any]]:
        """Extract actionable tasks from document content using simple NLP"""
        tasks = []

        # Simple task extraction patterns
        task_patterns = [
            r"(?:TODO|To do|Action item|Task|Must|Need to|Should|Action):\s*(.+?)(?:\.|$)",
            r"(?:^|\n)\s*[-•*]\s*(.+?)(?:\n|$)",
            r"(?:Deliverable|Milestone|Objective|Goal):\s*(.+?)(?:\.|$)",
            r"(?:By|Due|Complete|Finish)\s+(.+?)(?:by|on|before)\s+(.+?)(?:\.|$)"
        ]

        import re

        for doc in documents[:3]:  # Limit to top 3 most relevant docs
            content = doc.get("content", "")

            for pattern in task_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)

                for match in matches:
                    if isinstance(match, tuple):
                        task_text = match[0].strip()
                    else:
                        task_text = match.strip()

                    # Clean and validate task text
                    if len(task_text) > 10 and len(task_text) < 200:
                        tasks.append({
                            "title": f"{prefix}: {task_text[:100]}",
                            "description": f"Extracted from document: {doc.get('source', 'Unknown')}\n\nOriginal content: {task_text}",
                            "priority": 5
                        })

                        if len(tasks) >= max_tasks:
                            break

                if len(tasks) >= max_tasks:
                    break

            if len(tasks) >= max_tasks:
                break

        return tasks[:max_tasks]


class SearchDocuments(Tool):
    """Search documents using semantic similarity"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "search_documents",
            "Search project documents using semantic similarity"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for documents (required)"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5
                },
                "source_filter": {
                    "type": "string",
                    "description": "Filter by document source (openwebui, teams, planner)"
                },
                "task_id": {
                    "type": "string",
                    "description": "Filter by specific task ID"
                }
            },
            "required": ["query"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            query = arguments["query"]
            top_k = arguments.get("top_k", 5)
            source_filter = arguments.get("source_filter")
            task_id = arguments.get("task_id")

            # Build filters for RAG service
            filters = {}
            if source_filter:
                filters["source"] = source_filter
            if task_id:
                filters["task_id"] = task_id

            # Query RAG service
            rag_response = await self._query_rag_service(query, top_k, filters, user_id)

            if not rag_response:
                return ToolResult(
                    success=False,
                    error="Failed to query document search service"
                )

            results = rag_response.get("results", [])

            # Format results for user
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "title": result.get("title", "Untitled Document"),
                    "content_preview": result.get("content", "")[:200] + "...",
                    "source": result.get("source", "unknown"),
                    "similarity_score": result.get("score", 0),
                    "metadata": result.get("metadata", {})
                })

            return ToolResult(
                success=True,
                content={
                    "results": formatted_results,
                    "total_found": len(results),
                    "query": query,
                    "search_metadata": {
                        "top_k": top_k,
                        "filters_applied": filters
                    }
                },
                metadata={
                    "operation": "search_documents",
                    "query": query,
                    "results_count": len(results),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            logger.error("Error searching documents", error=str(e))
            return ToolResult(success=False, error=f"Failed to search documents: {str(e)}")

    async def _query_rag_service(self, query: str, top_k: int, filters: Dict, user_id: str) -> Optional[Dict[str, Any]]:
        """Query the RAG service for document search"""
        import httpx

        try:
            request_data = {
                "query": query,
                "top_k": top_k,
                "user_id": user_id
            }

            if filters:
                request_data["filters"] = filters

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://rag-service:7120/api/query",
                    json=request_data,
                    timeout=30.0
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"RAG service search failed: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Failed to search RAG service: {str(e)}")
            return None


class AnalyzeProjectRelationships(Tool):
    """Analyze and visualize relationships between projects, tasks, and team members"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "analyze_project_relationships",
            "Analyze and visualize relationships between projects, tasks, and team members using knowledge graph"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity to analyze relationships for",
                    "enum": ["project", "task", "user", "team", "all"]
                },
                "entity_id": {
                    "type": "string",
                    "description": "Specific entity ID to analyze (optional)"
                },
                "relationship_depth": {
                    "type": "integer",
                    "description": "Depth of relationships to analyze",
                    "minimum": 1,
                    "maximum": 3,
                    "default": 2
                },
                "include_metrics": {
                    "type": "boolean",
                    "description": "Include relationship strength metrics",
                    "default": True
                }
            },
            "required": ["entity_type"]
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            entity_type = arguments["entity_type"]
            entity_id = arguments.get("entity_id")
            depth = arguments.get("relationship_depth", 2)
            include_metrics = arguments.get("include_metrics", True)

            # Connect to Neo4j and analyze relationships
            relationships = await self._analyze_graph_relationships(
                entity_type, entity_id, depth, include_metrics, user_id
            )

            if not relationships:
                return ToolResult(
                    success=False,
                    error="No relationships found or knowledge graph is not populated"
                )

            # Generate insights from relationships
            insights = await self._generate_relationship_insights(relationships, entity_type)

            return ToolResult(
                success=True,
                content={
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "relationships": relationships,
                    "insights": insights,
                    "relationship_count": len(relationships),
                    "analysis_depth": depth
                },
                metadata={
                    "operation": "analyze_project_relationships",
                    "entity_type": entity_type,
                    "relationships_found": len(relationships),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            logger.error("Error analyzing project relationships", error=str(e))
            return ToolResult(success=False, error=f"Failed to analyze relationships: {str(e)}")

    async def _analyze_graph_relationships(self, entity_type: str, entity_id: str, depth: int, include_metrics: bool, user_id: str) -> List[Dict]:
        """Analyze relationships using Neo4j knowledge graph"""
        try:
            from neo4j import GraphDatabase

            # Neo4j connection
            uri = "bolt://neo4j:7687"
            auth = ("neo4j", "neo4j_password_2024")

            with GraphDatabase.driver(uri, auth=auth) as driver:
                with driver.session() as session:
                    # Build Cypher query based on entity type
                    if entity_type == "all":
                        query = """
                        MATCH (n)-[r]-(m)
                        WHERE n <> m
                        RETURN n, r, m, type(r) as relationship_type
                        LIMIT 100
                        """
                        params = {}
                    elif entity_id:
                        query = f"""
                        MATCH (start {{id: $entity_id}})-[r*1..{depth}]-(connected)
                        RETURN start, r, connected
                        LIMIT 50
                        """
                        params = {"entity_id": entity_id}
                    else:
                        query = f"""
                        MATCH (n:{entity_type.capitalize()})-[r*1..{depth}]-(m)
                        RETURN n, r, m, type(r) as relationship_type
                        LIMIT 50
                        """
                        params = {}

                    result = session.run(query, params)
                    relationships = []

                    for record in result:
                        relationships.append({
                            "source": dict(record["n"]) if "n" in record else None,
                            "target": dict(record["m"]) if "m" in record else None,
                            "relationship": record.get("relationship_type", "CONNECTED"),
                            "strength": self._calculate_relationship_strength(record) if include_metrics else 1.0
                        })

                    return relationships

        except Exception as e:
            logger.warning(f"Knowledge graph not available, using fallback analysis: {str(e)}")
            # Fallback to database analysis
            return await self._fallback_relationship_analysis(entity_type, entity_id, user_id)

    async def _fallback_relationship_analysis(self, entity_type: str, entity_id: str, user_id: str) -> List[Dict]:
        """Fallback relationship analysis using database"""
        relationships = []

        try:
            # Analyze task assignments
            if entity_type in ["task", "user", "all"]:
                # Query database for task-user relationships
                tasks = await self.database.get_tasks_by_user(user_id) if user_id else []

                for task in tasks[:10]:  # Limit to prevent overflow
                    relationships.append({
                        "source": {"id": user_id, "type": "user", "name": user_id},
                        "target": {"id": task.graph_id, "type": "task", "name": task.title},
                        "relationship": "ASSIGNED_TO",
                        "strength": 1.0
                    })

            # Analyze plan-task relationships
            if entity_type in ["project", "task", "all"]:
                plans = await self.graph_client.get_user_plans(user_id) if user_id else []

                for plan in plans[:5]:  # Limit plans
                    plan_id = plan.get("id")
                    tasks = await self.graph_client.get_plan_tasks(plan_id, user_id)

                    for task in tasks[:5]:  # Limit tasks per plan
                        relationships.append({
                            "source": {"id": plan_id, "type": "project", "name": plan.get("title", "Unknown Plan")},
                            "target": {"id": task.get("id"), "type": "task", "name": task.get("title", "Unknown Task")},
                            "relationship": "CONTAINS",
                            "strength": 1.0
                        })

        except Exception as e:
            logger.error(f"Fallback analysis failed: {str(e)}")

        return relationships

    def _calculate_relationship_strength(self, record) -> float:
        """Calculate relationship strength based on various factors"""
        # Simple calculation - can be enhanced
        return 1.0

    async def _generate_relationship_insights(self, relationships: List[Dict], entity_type: str) -> List[str]:
        """Generate insights from relationship analysis"""
        insights = []

        if not relationships:
            return ["No relationships found to analyze"]

        # Count relationships by type
        relationship_types = {}
        for rel in relationships:
            rel_type = rel.get("relationship", "UNKNOWN")
            relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1

        # Generate insights
        total_relationships = len(relationships)
        insights.append(f"Found {total_relationships} relationships involving {entity_type} entities")

        # Most common relationship type
        if relationship_types:
            most_common = max(relationship_types.items(), key=lambda x: x[1])
            insights.append(f"Most common relationship type: {most_common[0]} ({most_common[1]} instances)")

        # Identify highly connected entities
        entity_connections = {}
        for rel in relationships:
            source_id = rel.get("source", {}).get("id")
            target_id = rel.get("target", {}).get("id")

            if source_id:
                entity_connections[source_id] = entity_connections.get(source_id, 0) + 1
            if target_id:
                entity_connections[target_id] = entity_connections.get(target_id, 0) + 1

        if entity_connections:
            highly_connected = max(entity_connections.items(), key=lambda x: x[1])
            insights.append(f"Most connected entity: {highly_connected[0]} ({highly_connected[1]} connections)")

        return insights


class UpdateKnowledgeGraph(Tool):
    """Update knowledge graph with new entities and relationships"""

    def __init__(self, graph_client: GraphAPIClient, database: Database):
        super().__init__(
            "update_knowledge_graph",
            "Update knowledge graph with new entities and relationships from Planner data"
        )
        self.graph_client = graph_client
        self.database = database

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sync_type": {
                    "type": "string",
                    "description": "Type of sync to perform",
                    "enum": ["full", "incremental", "plans", "tasks", "users"],
                    "default": "incremental"
                },
                "plan_id": {
                    "type": "string",
                    "description": "Specific plan ID to sync (optional)"
                }
            }
        }

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            user_id = context.get("user_id", "default")
            sync_type = arguments.get("sync_type", "incremental")
            plan_id = arguments.get("plan_id")

            # Update knowledge graph
            update_results = await self._update_graph_entities(sync_type, plan_id, user_id)

            return ToolResult(
                success=True,
                content={
                    "sync_type": sync_type,
                    "entities_created": update_results.get("entities_created", 0),
                    "relationships_created": update_results.get("relationships_created", 0),
                    "entities_updated": update_results.get("entities_updated", 0),
                    "sync_timestamp": datetime.utcnow().isoformat()
                },
                metadata={
                    "operation": "update_knowledge_graph",
                    "sync_type": sync_type,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            logger.error("Error updating knowledge graph", error=str(e))
            return ToolResult(success=False, error=f"Failed to update knowledge graph: {str(e)}")

    async def _update_graph_entities(self, sync_type: str, plan_id: str, user_id: str) -> Dict[str, int]:
        """Update Neo4j knowledge graph with Planner entities"""
        results = {"entities_created": 0, "relationships_created": 0, "entities_updated": 0}

        try:
            from neo4j import GraphDatabase

            uri = "bolt://neo4j:7687"
            auth = ("neo4j", "neo4j_password_2024")

            with GraphDatabase.driver(uri, auth=auth) as driver:
                with driver.session() as session:
                    # Create constraints and indexes
                    await self._create_graph_schema(session)

                    if sync_type in ["full", "plans"] or plan_id:
                        results.update(await self._sync_plans(session, plan_id, user_id))

                    if sync_type in ["full", "tasks"]:
                        results.update(await self._sync_tasks(session, user_id))

                    if sync_type in ["full", "users"]:
                        results.update(await self._sync_users(session, user_id))

        except Exception as e:
            logger.warning(f"Knowledge graph update failed, will retry later: {str(e)}")

        return results

    async def _create_graph_schema(self, session):
        """Create Neo4j schema constraints and indexes"""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (b:Bucket) REQUIRE b.id IS UNIQUE"
        ]

        for constraint in constraints:
            try:
                session.run(constraint)
            except Exception as e:
                logger.debug(f"Constraint already exists or failed: {str(e)}")

    async def _sync_plans(self, session, plan_id: str, user_id: str) -> Dict[str, int]:
        """Sync plans to knowledge graph"""
        results = {"entities_created": 0, "relationships_created": 0, "entities_updated": 0}

        try:
            if plan_id:
                plans = [await self.graph_client.get_plan_details(plan_id, user_id)]
            else:
                plans = await self.graph_client.get_user_plans(user_id)

            for plan in plans:
                if not plan:
                    continue

                # Create/update plan node
                query = """
                MERGE (p:Project {id: $id})
                SET p.title = $title,
                    p.description = $description,
                    p.created_date = $created_date,
                    p.updated_date = datetime()
                RETURN p
                """

                result = session.run(query, {
                    "id": plan.get("id"),
                    "title": plan.get("title", "Unknown Plan"),
                    "description": plan.get("description", ""),
                    "created_date": plan.get("createdDateTime", datetime.utcnow().isoformat())
                })

                if result.single():
                    results["entities_created"] += 1

        except Exception as e:
            logger.error(f"Plan sync failed: {str(e)}")

        return results

    async def _sync_tasks(self, session, user_id: str) -> Dict[str, int]:
        """Sync tasks to knowledge graph"""
        results = {"entities_created": 0, "relationships_created": 0, "entities_updated": 0}

        try:
            # Get tasks from database
            tasks = await self.database.get_tasks_by_user(user_id)

            for task in tasks[:20]:  # Limit to prevent overwhelming
                # Create/update task node
                query = """
                MERGE (t:Task {id: $id})
                SET t.title = $title,
                    t.description = $description,
                    t.priority = $priority,
                    t.completion_percentage = $completion_percentage,
                    t.updated_date = datetime()
                RETURN t
                """

                result = session.run(query, {
                    "id": task.graph_id,
                    "title": task.title or "Unknown Task",
                    "description": task.description or "",
                    "priority": getattr(task, "priority", 5),
                    "completion_percentage": task.completion_percentage or 0
                })

                if result.single():
                    results["entities_created"] += 1

                # Create relationship to plan
                if task.plan_graph_id:
                    rel_query = """
                    MATCH (p:Project {id: $plan_id}), (t:Task {id: $task_id})
                    MERGE (p)-[r:CONTAINS]->(t)
                    RETURN r
                    """

                    rel_result = session.run(rel_query, {
                        "plan_id": task.plan_graph_id,
                        "task_id": task.graph_id
                    })

                    if rel_result.single():
                        results["relationships_created"] += 1

        except Exception as e:
            logger.error(f"Task sync failed: {str(e)}")

        return results

    async def _sync_users(self, session, user_id: str) -> Dict[str, int]:
        """Sync users to knowledge graph"""
        results = {"entities_created": 0, "relationships_created": 0, "entities_updated": 0}

        try:
            # Create/update user node
            query = """
            MERGE (u:User {id: $id})
            SET u.name = $name,
                u.updated_date = datetime()
            RETURN u
            """

            result = session.run(query, {
                "id": user_id,
                "name": user_id  # Can be enhanced with actual user details
            })

            if result.single():
                results["entities_created"] += 1

        except Exception as e:
            logger.error(f"User sync failed: {str(e)}")

        return results


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

        # Initialize NLP components
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self.date_parser = DateParser()
        self.context_manager = ConversationContextManager(database=database)
        self.batch_processor = BatchProcessor()

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
            self.tools["delete_task"] = DeleteTask(self.graph_client, self.database)

            # Register enhanced task operations (Phase 1)
            self.tools["get_task_details"] = GetTaskDetails(self.graph_client, self.database)
            self.tools["add_task_comment"] = AddTaskComment(self.graph_client, self.database)
            self.tools["add_task_checklist"] = AddTaskChecklist(self.graph_client, self.database)
            self.tools["update_task_checklist"] = UpdateTaskChecklist(self.graph_client, self.database)
            self.tools["search_tasks"] = SearchTasks(self.graph_client, self.database)
            self.tools["get_my_tasks"] = GetMyTasks(self.graph_client, self.database)

            # Register smart querying tools (Phase 2)
            self.tools["get_task_by_position"] = GetTaskByPosition(self.graph_client, self.database)
            self.tools["get_next_task"] = GetNextTask(self.graph_client, self.database)
            self.tools["list_buckets"] = ListBuckets(self.graph_client, self.database)

            # Register search tools
            self.tools["search_plans"] = SearchPlans(self.graph_client, self.database)

            # Register RAG integration tools (Epic 3 - Document Management)
            self.tools["create_tasks_from_document"] = CreateTasksFromDocument(self.graph_client, self.database)
            self.tools["search_documents"] = SearchDocuments(self.graph_client, self.database)

            # Register Knowledge Graph tools (Epic 3 - Knowledge Management)
            self.tools["analyze_project_relationships"] = AnalyzeProjectRelationships(self.graph_client, self.database)
            self.tools["update_knowledge_graph"] = UpdateKnowledgeGraph(self.graph_client, self.database)

            # Register NLP processing tool (Story 1.3)
            nlp_components = {
                "intent_classifier": self.intent_classifier,
                "entity_extractor": self.entity_extractor,
                "date_parser": self.date_parser,
                "context_manager": self.context_manager,
                "batch_processor": self.batch_processor
            }
            self.tools["process_natural_language"] = ProcessNaturalLanguage(
                self.graph_client, self.database, nlp_components
            )

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
