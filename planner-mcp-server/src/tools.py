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

            # Register enhanced task operations (Phase 1)
            self.tools["get_task_details"] = GetTaskDetails(self.graph_client, self.database)
            self.tools["add_task_comment"] = AddTaskComment(self.graph_client, self.database)
            self.tools["search_tasks"] = SearchTasks(self.graph_client, self.database)
            self.tools["get_my_tasks"] = GetMyTasks(self.graph_client, self.database)

            # Register smart querying tools (Phase 2)
            self.tools["get_task_by_position"] = GetTaskByPosition(self.graph_client, self.database)
            self.tools["get_next_task"] = GetNextTask(self.graph_client, self.database)
            self.tools["list_buckets"] = ListBuckets(self.graph_client, self.database)

            # Register search tools
            self.tools["search_plans"] = SearchPlans(self.graph_client, self.database)

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
