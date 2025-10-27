"""
Required Fields Prompting System
Handles missing required fields with intelligent prompting and context preservation
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog

from .cache import CacheService
from .graph_client import GraphAPIClient

logger = structlog.get_logger(__name__)

class RequiredFieldsHandler:
    """Handles missing required fields with intelligent prompting"""

    def __init__(self, cache_service: CacheService, graph_client: GraphAPIClient):
        self.cache_service = cache_service
        self.graph_client = graph_client

        # Define field-specific prompting strategies
        self.field_prompters = {
            "plan_id": self._prompt_for_plan,
            "group_id": self._prompt_for_group,
            "task_id": self._prompt_for_task,
            "title": self._prompt_for_title,
            "comment": self._prompt_for_comment,
            "query": self._prompt_for_query,
            "user_input": self._prompt_for_user_input,
            "checklist_items": self._prompt_for_checklist_items,
            "document_query": self._prompt_for_document_query,
            "entity_type": self._prompt_for_entity_type,
            "position": self._prompt_for_position,
            "item_index": self._prompt_for_item_index,
            "is_checked": self._prompt_for_is_checked,
            "confirm": self._prompt_for_confirm
        }

        # Cache keys for storing partial requests
        self.PARTIAL_REQUEST_PREFIX = "partial_request:"
        self.PARTIAL_REQUEST_TTL = 3600  # 1 hour

    async def check_required_fields(self, tool_name: str, tool_definition: Dict[str, Any],
                                  provided_args: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if all required fields are provided, return prompting info if not

        Returns:
            (all_fields_present: bool, prompt_response: Optional[Dict])
        """
        required_fields = tool_definition.get("required", [])
        missing_fields = [field for field in required_fields if field not in provided_args or not provided_args[field]]

        if not missing_fields:
            return True, None

        # Generate prompts for missing fields
        user_id = context.get("user_id", "default")
        session_id = context.get("session_id", "default")

        # Store partial request
        partial_request = {
            "tool_name": tool_name,
            "provided_args": provided_args,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
            "missing_fields": missing_fields
        }

        await self.cache_service.set(
            f"{self.PARTIAL_REQUEST_PREFIX}{session_id}:{tool_name}",
            partial_request,
            ttl=self.PARTIAL_REQUEST_TTL
        )

        # Generate contextual prompts
        prompts = []
        suggestions = {}

        for field in missing_fields:
            prompt_info = await self._generate_field_prompt(field, tool_name, provided_args, user_id)
            prompts.append(prompt_info["prompt"])
            if prompt_info.get("suggestions"):
                suggestions[field] = prompt_info["suggestions"]

        prompt_response = {
            "success": False,
            "content": {
                "message": "Missing required information to complete your request.",
                "missing_fields": missing_fields,
                "prompts": prompts,
                "suggestions": suggestions,
                "partial_request_id": f"{session_id}:{tool_name}"
            },
            "error": None,
            "metadata": {
                "operation": "required_fields_prompt",
                "tool_name": tool_name,
                "missing_count": len(missing_fields),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

        return False, prompt_response

    async def complete_partial_request(self, session_id: str, tool_name: str,
                                     provided_values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Complete a partial request with newly provided values"""
        cache_key = f"{self.PARTIAL_REQUEST_PREFIX}{session_id}:{tool_name}"
        partial_request = await self.cache_service.get(cache_key)

        if not partial_request:
            return None

        # Process and resolve special values (like project names to IDs)
        resolved_values = await self._resolve_field_values(provided_values, partial_request["context"]["user_id"])

        # Merge resolved values with original arguments
        complete_args = {**partial_request["provided_args"], **resolved_values}

        # Check if all required fields are now present
        from .tools import ToolRegistry  # Import here to avoid circular imports
        # We'll need to get the tool definition to check requirements

        # Clear the partial request
        await self.cache_service.delete(cache_key)

        return {
            "tool_name": tool_name,
            "arguments": complete_args,
            "context": partial_request["context"]
        }

    async def _resolve_field_values(self, provided_values: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Resolve user-friendly values to system IDs"""
        resolved = {}

        for field, value in provided_values.items():
            if field == "plan_id" and isinstance(value, str):
                # Try to resolve project name/number to plan_id
                resolved_id = await self.resolve_project_identifier(value, user_id)
                if resolved_id:
                    resolved[field] = resolved_id
                    logger.info(f"Resolved project '{value}' to plan_id: {resolved_id}")
                else:
                    # Keep original value if resolution failed
                    resolved[field] = value
                    logger.warning(f"Could not resolve project identifier: {value}")
            else:
                # For other fields, use value as-is
                resolved[field] = value

        return resolved

    async def _generate_field_prompt(self, field: str, tool_name: str,
                                   provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate contextual prompt for a specific field"""
        if field in self.field_prompters:
            return await self.field_prompters[field](tool_name, provided_args, user_id)
        else:
            return {
                "prompt": f"Please provide a value for '{field}':",
                "suggestions": None
            }

    async def _prompt_for_plan(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for plan_id with available plans"""
        try:
            # Get user's accessible plans
            groups = await self.graph_client.get_user_groups(user_id)
            plans = []

            for group in groups[:5]:  # Limit to first 5 groups
                if group.get("@odata.type") == "#microsoft.graph.group":
                    try:
                        group_plans = await self.graph_client.get_group_plans(group["id"], user_id)
                        plans.extend(group_plans[:10])  # Limit plans per group
                    except Exception:
                        continue

            if plans:
                suggestions = []
                for i, plan in enumerate(plans[:10], 1):
                    suggestions.append({
                        "option": str(i),
                        "id": plan["id"],
                        "title": plan["title"],
                        "description": f"Option {i}: {plan['title']}"
                    })

                prompt = f"Which project would you like to work with? I found {len(suggestions)} available projects. Please choose by number or name:"

                # Add the list of projects to the prompt
                project_list = "\n".join([f"  {s['option']}. {s['title']}" for s in suggestions])
                prompt += f"\n\nAvailable Projects:\n{project_list}\n\nYou can respond with either the project number (e.g., '2') or the project name (e.g., 'AI Agentic R&D')."
            else:
                suggestions = []
                prompt = "I couldn't fetch your available projects right now. Please provide the project name you'd like to work with (e.g., 'AI Agentic R&D', 'Company AI Virtual Assistant')."

            return {
                "prompt": prompt,
                "suggestions": suggestions
            }
        except Exception as e:
            logger.warning("Error fetching plans for prompt", error=str(e))
            # Provide fallback with known common project names
            fallback_suggestions = [
                {"option": "1", "title": "AI Agentic R&D", "description": "Option 1: AI Agentic R&D"},
                {"option": "2", "title": "AI PROJECTS", "description": "Option 2: AI PROJECTS"},
                {"option": "3", "title": "Company AI Virtual Assistant", "description": "Option 3: Company AI Virtual Assistant"}
            ]

            prompt = """I couldn't fetch your projects right now, but here are some common projects you might want to use:

Available Projects:
  1. AI Agentic R&D
  2. AI PROJECTS
  3. Company AI Virtual Assistant

You can respond with either the project number (e.g., '1') or the project name (e.g., 'AI Agentic R&D')."""

            return {
                "prompt": prompt,
                "suggestions": fallback_suggestions
            }

    async def resolve_project_identifier(self, user_input: str, user_id: str) -> Optional[str]:
        """
        Resolve project name, number, or partial name to plan_id
        Returns plan_id if found, None otherwise
        """
        # Known project mappings (fallback when API is unavailable)
        known_projects = {
            "1": "G6H5hKp1v06Wd-tzQtduqGQADv35",  # AI Agentic R&D
            "2": "dP7krUD3wEusvytmew0Y0WQAE94a",  # AI PROJECTS
            "3": "8c2tWC6XKEan4fSMdWT09mQAAXKJ",  # Company AI Virtual Assistant
            "ai agentic r&d": "G6H5hKp1v06Wd-tzQtduqGQADv35",
            "ai projects": "dP7krUD3wEusvytmew0Y0WQAE94a",
            "company ai virtual assistant": "8c2tWC6XKEan4fSMdWT09mQAAXKJ",
            "ai": "3JnhPWRXZkqDwsA-uFU2fWQAFNKQ",  # AI
            "ai agentic": "G6H5hKp1v06Wd-tzQtduqGQADv35",  # Partial match
            "virtual assistant": "8c2tWC6XKEan4fSMdWT09mQAAXKJ"  # Partial match
        }

        user_input_lower = user_input.lower().strip()

        # First check exact matches
        if user_input_lower in known_projects:
            return known_projects[user_input_lower]

        # Check if it's already a valid plan ID format
        if len(user_input) > 20 and any(c.isalnum() for c in user_input):
            return user_input

        try:
            # Try to fetch actual plans for dynamic matching
            groups = await self.graph_client.get_user_groups(user_id)
            plans = []

            for group in groups[:5]:
                if group.get("@odata.type") == "#microsoft.graph.group":
                    try:
                        group_plans = await self.graph_client.get_group_plans(group["id"], user_id)
                        plans.extend(group_plans[:20])
                    except Exception:
                        continue

            # Try exact title match
            for plan in plans:
                if plan["title"].lower() == user_input_lower:
                    return plan["id"]

            # Try partial title match
            for plan in plans:
                if user_input_lower in plan["title"].lower():
                    return plan["id"]

        except Exception as e:
            logger.warning("Error resolving project identifier", error=str(e))

        return None

    async def _prompt_for_group(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for group_id with available groups"""
        try:
            groups = await self.graph_client.get_user_groups(user_id)

            if groups:
                suggestions = [
                    {"id": group["id"], "title": group.get("displayName", "Unnamed Group"),
                     "description": f"Group: {group.get('displayName', 'Unnamed Group')}"}
                    for group in groups[:10]
                ]
                prompt = f"Which team/group should this project belong to? I found {len(suggestions)} available groups."
            else:
                suggestions = []
                prompt = "Please provide the team/group ID for this project:"

            return {
                "prompt": prompt,
                "suggestions": suggestions
            }
        except Exception as e:
            logger.warning("Error fetching groups for prompt", error=str(e))
            return {
                "prompt": "Please provide the team/group ID for this project:",
                "suggestions": []
            }

    async def _prompt_for_task(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for task_id with recent tasks"""
        try:
            # If we have a plan_id, get tasks from that plan
            if "plan_id" in provided_args:
                tasks = await self.graph_client.get_plan_tasks(provided_args["plan_id"], user_id)
                context = f"from the '{provided_args.get('plan_title', 'specified')}' project"
            else:
                # Get recent tasks from all plans
                groups = await self.graph_client.get_user_groups(user_id)
                tasks = []
                for group in groups[:3]:  # Limit to first 3 groups
                    if group.get("@odata.type") == "#microsoft.graph.group":
                        try:
                            group_plans = await self.graph_client.get_group_plans(group["id"], user_id)
                            for plan in group_plans[:3]:  # Limit plans per group
                                plan_tasks = await self.graph_client.get_plan_tasks(plan["id"], user_id)
                                tasks.extend(plan_tasks[:5])  # Limit tasks per plan
                        except Exception:
                            continue
                context = "from your recent projects"

            if tasks:
                suggestions = [
                    {"id": task["id"], "title": task["title"],
                     "description": f"Task: {task['title']} ({task.get('percentComplete', 0)}% complete)"}
                    for task in tasks[:10]
                ]
                prompt = f"Which task would you like to work with? I found {len(suggestions)} tasks {context}."
            else:
                suggestions = []
                prompt = "Please provide the task ID you'd like to work with:"

            return {
                "prompt": prompt,
                "suggestions": suggestions
            }
        except Exception as e:
            logger.warning("Error fetching tasks for prompt", error=str(e))
            return {
                "prompt": "Please provide the task ID you'd like to work with:",
                "suggestions": []
            }

    async def _prompt_for_title(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for title field"""
        if tool_name == "create_task":
            return {
                "prompt": "What would you like to name this task?",
                "suggestions": [
                    {"value": "Review document", "description": "Example: Review document"},
                    {"value": "Schedule meeting", "description": "Example: Schedule meeting"},
                    {"value": "Follow up", "description": "Example: Follow up"}
                ]
            }
        elif tool_name == "create_plan":
            return {
                "prompt": "What would you like to name this project?",
                "suggestions": [
                    {"value": "New Project", "description": "Example: New Project"},
                    {"value": "Q4 Planning", "description": "Example: Q4 Planning"},
                    {"value": "Team Initiative", "description": "Example: Team Initiative"}
                ]
            }
        else:
            return {"prompt": "Please provide a title:", "suggestions": []}

    async def _prompt_for_comment(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for comment field"""
        return {
            "prompt": "What comment would you like to add?",
            "suggestions": []
        }

    async def _prompt_for_query(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for query field"""
        if tool_name == "search_tasks":
            return {
                "prompt": "What tasks are you looking for? (e.g., 'urgent tasks', 'meetings', 'overdue')",
                "suggestions": [
                    {"value": "urgent", "description": "Find urgent tasks"},
                    {"value": "overdue", "description": "Find overdue tasks"},
                    {"value": "meeting", "description": "Find meeting-related tasks"}
                ]
            }
        elif tool_name == "search_plans":
            return {
                "prompt": "What projects are you looking for?",
                "suggestions": [
                    {"value": "active", "description": "Find active projects"},
                    {"value": "recent", "description": "Find recent projects"}
                ]
            }
        elif tool_name == "search_documents":
            return {
                "prompt": "What documents are you looking for?",
                "suggestions": []
            }
        else:
            return {"prompt": "What are you searching for?", "suggestions": []}

    async def _prompt_for_user_input(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for user_input field"""
        return {
            "prompt": "What would you like me to help you with?",
            "suggestions": [
                {"value": "Create a task", "description": "I want to create a new task"},
                {"value": "Find my tasks", "description": "Show me my current tasks"},
                {"value": "Update project", "description": "I need to update a project"}
            ]
        }

    async def _prompt_for_checklist_items(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for checklist_items field"""
        return {
            "prompt": "What checklist items would you like to add? (separate multiple items with commas)",
            "suggestions": [
                {"value": "Review requirements, Get approval, Schedule follow-up",
                 "description": "Example: Review requirements, Get approval, Schedule follow-up"}
            ]
        }

    async def _prompt_for_document_query(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for document_query field"""
        return {
            "prompt": "What type of document content should I analyze to create tasks?",
            "suggestions": [
                {"value": "meeting notes", "description": "Extract tasks from meeting notes"},
                {"value": "project requirements", "description": "Extract tasks from requirements"},
                {"value": "action items", "description": "Find action items in documents"}
            ]
        }

    async def _prompt_for_entity_type(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for entity_type field"""
        return {
            "prompt": "What type of relationships would you like to analyze?",
            "suggestions": [
                {"value": "project", "description": "Analyze project relationships"},
                {"value": "task", "description": "Analyze task relationships"},
                {"value": "user", "description": "Analyze user relationships"},
                {"value": "all", "description": "Analyze all relationship types"}
            ]
        }

    async def _prompt_for_position(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for position field"""
        return {
            "prompt": "Which task position are you looking for? (e.g., 1 for first task, 2 for second task)",
            "suggestions": [
                {"value": "1", "description": "First task"},
                {"value": "2", "description": "Second task"},
                {"value": "3", "description": "Third task"}
            ]
        }

    async def _prompt_for_item_index(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for item_index field"""
        return {
            "prompt": "Which checklist item would you like to update? (0 for first item, 1 for second, etc.)",
            "suggestions": []
        }

    async def _prompt_for_is_checked(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for is_checked field"""
        return {
            "prompt": "Should this checklist item be marked as completed?",
            "suggestions": [
                {"value": "true", "description": "Mark as completed"},
                {"value": "false", "description": "Mark as not completed"}
            ]
        }

    async def _prompt_for_confirm(self, tool_name: str, provided_args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Generate prompt for confirm field"""
        task_title = provided_args.get("task_title", "this task")
        return {
            "prompt": f"Are you sure you want to delete '{task_title}'? This action cannot be undone.",
            "suggestions": [
                {"value": "true", "description": "Yes, delete the task"},
                {"value": "false", "description": "No, cancel deletion"}
            ]
        }