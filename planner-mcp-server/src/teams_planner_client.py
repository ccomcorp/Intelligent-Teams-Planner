"""
Simple Microsoft Teams and Planner client for MVP testing
Focus on basic connectivity and task creation
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import httpx
import structlog

from .auth import AuthService, AuthenticationError

logger = structlog.get_logger(__name__)


class TeamsPlannierError(Exception):
    """Teams and Planner client errors"""
    pass


class SimpleTeamsPlannerClient:
    """Simple client for Microsoft Teams and Planner operations"""

    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service
        self.base_url = "https://graph.microsoft.com/v1.0"

    async def get_user_teams(self, user_id: str) -> List[Dict[str, Any]]:
        """Get teams that the user is a member of"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/me/joinedTeams",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    teams_data = response.json()
                    logger.info("Retrieved user teams", count=len(teams_data.get('value', [])))
                    return teams_data.get('value', [])
                else:
                    logger.error("Failed to get teams", status_code=response.status_code)
                    raise TeamsPlannierError(f"Failed to get teams: {response.status_code}")

        except httpx.HTTPError as e:
            logger.error("HTTP error getting teams", error=str(e))
            raise TeamsPlannierError(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error("Error getting teams", error=str(e))
            raise TeamsPlannierError(f"Error getting teams: {str(e)}")

    async def get_team_planner_plans(self, user_id: str, team_id: str) -> List[Dict[str, Any]]:
        """Get Planner plans for a specific team with enhanced error handling"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                # Get plans for the group (team_id is actually the group_id in Microsoft Graph)
                response = await client.get(
                    f"{self.base_url}/groups/{team_id}/planner/plans",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    plans_data = response.json()
                    logger.info("Retrieved team plans", team_id=team_id, count=len(plans_data.get('value', [])))
                    return plans_data.get('value', [])
                elif response.status_code == 403:
                    logger.error("Insufficient permissions for plans", team_id=team_id)
                    raise TeamsPlannierError(f"Insufficient permissions to access plans for team {team_id}")
                elif response.status_code == 404:
                    logger.info("No plans found for team", team_id=team_id)
                    return []  # Return empty list instead of error
                else:
                    error_text = response.text
                    logger.error("Failed to get plans", team_id=team_id, status_code=response.status_code, error=error_text)
                    raise TeamsPlannierError(f"Failed to get plans: {response.status_code} - {error_text}")

        except httpx.HTTPError as e:
            logger.error("HTTP error getting plans", error=str(e))
            raise TeamsPlannierError(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error("Error getting plans", error=str(e))
            raise TeamsPlannierError(f"Error getting plans: {str(e)}")

    async def get_plan_buckets(self, user_id: str, plan_id: str) -> List[Dict[str, Any]]:
        """Get buckets (columns) for a specific Planner plan"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/planner/plans/{plan_id}/buckets",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    buckets_data = response.json()
                    logger.info("Retrieved plan buckets", plan_id=plan_id, count=len(buckets_data.get('value', [])))
                    return buckets_data.get('value', [])
                else:
                    logger.error("Failed to get buckets", plan_id=plan_id, status_code=response.status_code)
                    raise TeamsPlannierError(f"Failed to get buckets: {response.status_code}")

        except Exception as e:
            logger.error("Error getting buckets", error=str(e))
            raise TeamsPlannierError(f"Error getting buckets: {str(e)}")

    async def get_plan_tasks(self, user_id: str, plan_id: str) -> List[Dict[str, Any]]:
        """Get all tasks for a specific Planner plan"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/planner/plans/{plan_id}/tasks",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    tasks_data = response.json()
                    logger.info("Retrieved plan tasks", plan_id=plan_id, count=len(tasks_data.get('value', [])))
                    return tasks_data.get('value', [])
                else:
                    logger.error("Failed to get tasks", plan_id=plan_id, status_code=response.status_code)
                    raise TeamsPlannierError(f"Failed to get tasks: {response.status_code}")

        except Exception as e:
            logger.error("Error getting tasks", error=str(e))
            raise TeamsPlannierError(f"Error getting tasks: {str(e)}")

    async def create_planner_task(
        self,
        user_id: str,
        plan_id: str,
        title: str,
        description: str = None,
        bucket_id: str = None,
        assignments: Dict[str, Any] = None,
        due_date: datetime = None,
        start_date: datetime = None,
        priority: int = 5,
        progress: str = "notStarted",
        categories: List[str] = None
    ) -> Dict[str, Any]:
        """Create a new task in a Planner plan with full functionality"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            # Comprehensive task payload
            task_data = {
                "planId": plan_id,
                "title": title,
                "assignments": assignments or {},
                "priority": priority,
                "percentComplete": 0 if progress == "notStarted" else 50 if progress == "inProgress" else 100
            }

            # Add optional fields
            if bucket_id:
                task_data["bucketId"] = bucket_id

            if due_date:
                task_data["dueDateTime"] = due_date.isoformat() + "Z"

            if start_date:
                task_data["startDateTime"] = start_date.isoformat() + "Z"

            if categories:
                # Categories are boolean flags (category1, category2, etc.)
                for i, category in enumerate(categories[:6]):  # Max 6 categories
                    task_data[f"appliedCategories"] = task_data.get("appliedCategories", {})
                    task_data["appliedCategories"][f"category{i+1}"] = True

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/planner/tasks",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=task_data
                )

                if response.status_code == 201:
                    task_result = response.json()

                    # If description provided, update task details separately
                    if description:
                        await self._update_task_details(user_id, task_result["id"], description)

                    logger.info("Task created successfully",
                              task_id=task_result.get('id'),
                              title=title,
                              plan_id=plan_id)
                    return task_result
                else:
                    error_text = response.text
                    logger.error("Failed to create task",
                               status_code=response.status_code,
                               error=error_text)
                    raise TeamsPlannierError(f"Failed to create task: {response.status_code} - {error_text}")

        except httpx.HTTPError as e:
            logger.error("HTTP error creating task", error=str(e))
            raise TeamsPlannierError(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error("Error creating task", error=str(e))
            raise TeamsPlannierError(f"Error creating task: {str(e)}")

    async def _update_task_details(self, user_id: str, task_id: str, description: str) -> None:
        """Update task details (description, checklist, etc.)"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            # Get current task details first to get the @odata.etag
            async with httpx.AsyncClient() as client:
                get_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if get_response.status_code == 200:
                    current_details = get_response.json()
                    etag = get_response.headers.get("ETag", "")

                    # Update with new description
                    update_data = {
                        "description": description
                    }

                    patch_response = await client.patch(
                        f"{self.base_url}/planner/tasks/{task_id}/details",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "If-Match": etag
                        },
                        json=update_data
                    )

                    if patch_response.status_code != 200:
                        logger.warning("Failed to update task description",
                                     task_id=task_id,
                                     status_code=patch_response.status_code)

        except Exception as e:
            logger.warning("Error updating task details", task_id=task_id, error=str(e))

    async def add_task_checklist(
        self,
        user_id: str,
        task_id: str,
        checklist_items: List[Dict[str, Any]]
    ) -> bool:
        """Add checklist items to a task

        Args:
            user_id: User ID
            task_id: Task ID
            checklist_items: List of checklist items, each containing:
                - title: str - Item title
                - isChecked: bool - Whether item is checked (optional, default False)
        """
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            # Get current task details to get ETag
            async with httpx.AsyncClient() as client:
                get_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if get_response.status_code == 200:
                    current_details = get_response.json()
                    etag = get_response.headers.get("ETag", "")

                    # Build checklist items object
                    checklist_object = {}
                    for i, item in enumerate(checklist_items):
                        checklist_id = f"checklist-{i+1}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        checklist_object[checklist_id] = {
                            "@odata.type": "microsoft.graph.plannerChecklistItem",
                            "title": item.get("title", ""),
                            "isChecked": item.get("isChecked", False)
                        }

                    # Update task details with checklist
                    update_data = {
                        "checklist": checklist_object
                    }

                    patch_response = await client.patch(
                        f"{self.base_url}/planner/tasks/{task_id}/details",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "If-Match": etag
                        },
                        json=update_data
                    )

                    if patch_response.status_code in [200, 204]:  # 204 is also success for PATCH
                        logger.info("Checklist added successfully", task_id=task_id, items=len(checklist_items))
                        return True
                    else:
                        error_text = patch_response.text
                        logger.error("Failed to add checklist",
                                   task_id=task_id,
                                   status_code=patch_response.status_code,
                                   error=error_text)
                        return False
                else:
                    logger.error("Failed to get task details for checklist",
                               task_id=task_id,
                               status_code=get_response.status_code)
                    return False

        except Exception as e:
            logger.error("Error adding checklist", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error adding checklist: {str(e)}")

    async def update_checklist_item(
        self,
        user_id: str,
        task_id: str,
        checklist_item_id: str,
        is_checked: bool
    ) -> bool:
        """Update a specific checklist item's checked status"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                get_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if get_response.status_code == 200:
                    current_details = get_response.json()
                    etag = get_response.headers.get("ETag", "")

                    # Update specific checklist item
                    checklist = current_details.get("checklist", {})
                    if checklist_item_id in checklist:
                        checklist[checklist_item_id]["isChecked"] = is_checked

                        update_data = {"checklist": checklist}

                        patch_response = await client.patch(
                            f"{self.base_url}/planner/tasks/{task_id}/details",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/json",
                                "If-Match": etag
                            },
                            json=update_data
                        )

                        if patch_response.status_code in [200, 204]:
                            logger.info("Checklist item updated",
                                      task_id=task_id,
                                      item_id=checklist_item_id,
                                      checked=is_checked)
                            return True

                    logger.warning("Checklist item not found", item_id=checklist_item_id)
                    return False

        except Exception as e:
            logger.error("Error updating checklist item", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error updating checklist item: {str(e)}")

    async def get_task_checklist(self, user_id: str, task_id: str) -> List[Dict[str, Any]]:
        """Get checklist items for a task"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    details = response.json()
                    checklist = details.get("checklist", {})

                    # Convert checklist object to list
                    checklist_items = []
                    for item_id, item_data in checklist.items():
                        checklist_items.append({
                            "id": item_id,
                            "title": item_data.get("title", ""),
                            "isChecked": item_data.get("isChecked", False)
                        })

                    logger.info("Retrieved task checklist", task_id=task_id, items=len(checklist_items))
                    return checklist_items
                else:
                    logger.error("Failed to get task checklist", task_id=task_id, status_code=response.status_code)
                    return []

        except Exception as e:
            logger.error("Error getting task checklist", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error getting task checklist: {str(e)}")

    async def add_task_comment(
        self,
        user_id: str,
        task_id: str,
        comment: str
    ) -> bool:
        """Add a comment/reference to a task"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                # Get current task details to get ETag
                get_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if get_response.status_code == 200:
                    current_details = get_response.json()
                    etag = get_response.headers.get("ETag", "")

                    # Add comment to description (references API has URI validation issues)
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    current_description = current_details.get("description", "")
                    new_description = f"{current_description}\n\n--- Comment ({timestamp}) ---\n{comment}" if current_description else f"--- Comment ({timestamp}) ---\n{comment}"

                    update_data = {
                        "description": new_description
                    }

                    patch_response = await client.patch(
                        f"{self.base_url}/planner/tasks/{task_id}/details",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                            "If-Match": etag
                        },
                        json=update_data
                    )

                    if patch_response.status_code in [200, 204]:
                        logger.info("Comment added successfully", task_id=task_id)
                        return True
                    else:
                        error_text = patch_response.text
                        logger.error("Failed to add comment",
                                   task_id=task_id,
                                   status_code=patch_response.status_code,
                                   error=error_text)
                        return False
                else:
                    logger.error("Failed to get task details for comment",
                               task_id=task_id,
                               status_code=get_response.status_code)
                    return False

        except Exception as e:
            logger.error("Error adding comment", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error adding comment: {str(e)}")

    async def get_task_comments(self, user_id: str, task_id: str) -> List[Dict[str, Any]]:
        """Get comments/references for a task"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    details = response.json()
                    references = details.get("references", {})

                    # Extract comments from references
                    comments = []
                    for ref_id, ref_data in references.items():
                        if ref_id.startswith("comment-"):
                            comments.append({
                                "id": ref_id,
                                "alias": ref_data.get("alias", ""),
                                "type": ref_data.get("type", "Other"),
                                "lastModifiedBy": ref_data.get("lastModifiedBy", {})
                            })

                    # Also extract from description
                    description = details.get("description", "")
                    if "--- Comment (" in description:
                        # Parse comments from description
                        comment_sections = description.split("--- Comment (")
                        for section in comment_sections[1:]:  # Skip first part (original description)
                            if ") ---\n" in section:
                                timestamp_end = section.find(") ---\n")
                                timestamp = section[:timestamp_end]
                                comment_text = section[timestamp_end + 6:]
                                comments.append({
                                    "timestamp": timestamp,
                                    "text": comment_text.strip()
                                })

                    logger.info("Retrieved task comments", task_id=task_id, comments=len(comments))
                    return comments
                else:
                    logger.error("Failed to get task comments", task_id=task_id, status_code=response.status_code)
                    return []

        except Exception as e:
            logger.error("Error getting task comments", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error getting task comments: {str(e)}")

    async def get_task_details(self, user_id: str, task_id: str) -> Dict[str, Any]:
        """Get complete task details including description, checklist, and comments"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                # Get basic task info
                task_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                # Get detailed task info
                details_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}/details",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if task_response.status_code == 200 and details_response.status_code == 200:
                    task_data = task_response.json()
                    details_data = details_response.json()

                    # Combine basic task data with details
                    complete_task = {
                        **task_data,
                        "description": details_data.get("description", ""),
                        "checklist": details_data.get("checklist", {}),
                        "references": details_data.get("references", {}),
                        "details": details_data
                    }

                    logger.info("Retrieved complete task details", task_id=task_id)
                    return complete_task
                else:
                    logger.error("Failed to get complete task details",
                               task_id=task_id,
                               task_status=task_response.status_code,
                               details_status=details_response.status_code)
                    raise TeamsPlannierError(f"Failed to get task details: task={task_response.status_code}, details={details_response.status_code}")

        except Exception as e:
            logger.error("Error getting complete task details", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error getting complete task details: {str(e)}")

    async def update_planner_task(
        self,
        user_id: str,
        task_id: str,
        title: str = None,
        bucket_id: str = None,
        progress: str = None,
        assignments: Dict[str, Any] = None,
        due_date: datetime = None,
        start_date: datetime = None,
        priority: int = None
    ) -> Dict[str, Any]:
        """Update an existing Planner task"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            # Get current task to obtain ETag
            async with httpx.AsyncClient() as client:
                get_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if get_response.status_code != 200:
                    raise TeamsPlannierError(f"Failed to get task: {get_response.status_code}")

                current_task = get_response.json()
                etag = get_response.headers.get("ETag", "")

                # Build update payload
                update_data = {}
                if title is not None:
                    update_data["title"] = title
                if bucket_id is not None:
                    update_data["bucketId"] = bucket_id
                if progress is not None:
                    update_data["percentComplete"] = 0 if progress == "notStarted" else 50 if progress == "inProgress" else 100
                if assignments is not None:
                    update_data["assignments"] = assignments
                if due_date is not None:
                    update_data["dueDateTime"] = due_date.isoformat() + "Z"
                if start_date is not None:
                    update_data["startDateTime"] = start_date.isoformat() + "Z"
                if priority is not None:
                    update_data["priority"] = priority

                # Update task
                patch_response = await client.patch(
                    f"{self.base_url}/planner/tasks/{task_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "If-Match": etag
                    },
                    json=update_data
                )

                if patch_response.status_code == 200:
                    logger.info("Task updated successfully", task_id=task_id)
                    return patch_response.json()
                else:
                    error_text = patch_response.text
                    logger.error("Failed to update task",
                               task_id=task_id,
                               status_code=patch_response.status_code,
                               error=error_text)
                    raise TeamsPlannierError(f"Failed to update task: {patch_response.status_code} - {error_text}")

        except Exception as e:
            logger.error("Error updating task", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error updating task: {str(e)}")

    async def delete_planner_task(self, user_id: str, task_id: str) -> bool:
        """Delete a Planner task"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            # Get current task to obtain ETag
            async with httpx.AsyncClient() as client:
                get_response = await client.get(
                    f"{self.base_url}/planner/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if get_response.status_code != 200:
                    raise TeamsPlannierError(f"Failed to get task: {get_response.status_code}")

                etag = get_response.headers.get("ETag", "")

                # Delete task
                delete_response = await client.delete(
                    f"{self.base_url}/planner/tasks/{task_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "If-Match": etag
                    }
                )

                if delete_response.status_code == 204:
                    logger.info("Task deleted successfully", task_id=task_id)
                    return True
                else:
                    error_text = delete_response.text
                    logger.error("Failed to delete task",
                               task_id=task_id,
                               status_code=delete_response.status_code,
                               error=error_text)
                    return False

        except Exception as e:
            logger.error("Error deleting task", task_id=task_id, error=str(e))
            raise TeamsPlannierError(f"Error deleting task: {str(e)}")

    async def create_planner_bucket(
        self,
        user_id: str,
        plan_id: str,
        name: str,
        order_hint: str = None
    ) -> Dict[str, Any]:
        """Create a new bucket (column) in a Planner plan"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            bucket_data = {
                "name": name,
                "planId": plan_id
            }

            if order_hint:
                bucket_data["orderHint"] = order_hint

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/planner/buckets",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=bucket_data
                )

                if response.status_code == 201:
                    bucket_result = response.json()
                    logger.info("Bucket created successfully",
                              bucket_id=bucket_result.get('id'),
                              name=name,
                              plan_id=plan_id)
                    return bucket_result
                else:
                    error_text = response.text
                    logger.error("Failed to create bucket",
                               status_code=response.status_code,
                               error=error_text)
                    raise TeamsPlannierError(f"Failed to create bucket: {response.status_code} - {error_text}")

        except Exception as e:
            logger.error("Error creating bucket", error=str(e))
            raise TeamsPlannierError(f"Error creating bucket: {str(e)}")

    async def get_team_channels(self, user_id: str, team_id: str) -> List[Dict[str, Any]]:
        """Get channels for a specific team"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/teams/{team_id}/channels",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    channels_data = response.json()
                    logger.info("Retrieved team channels", team_id=team_id, count=len(channels_data.get('value', [])))
                    return channels_data.get('value', [])
                else:
                    logger.error("Failed to get channels", team_id=team_id, status_code=response.status_code)
                    raise TeamsPlannierError(f"Failed to get channels: {response.status_code}")

        except Exception as e:
            logger.error("Error getting channels", error=str(e))
            raise TeamsPlannierError(f"Error getting channels: {str(e)}")

    async def get_team_members(self, user_id: str, team_id: str) -> List[Dict[str, Any]]:
        """Get members of a specific team"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/teams/{team_id}/members",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    members_data = response.json()
                    logger.info("Retrieved team members", team_id=team_id, count=len(members_data.get('value', [])))
                    return members_data.get('value', [])
                else:
                    logger.error("Failed to get team members", team_id=team_id, status_code=response.status_code)
                    raise TeamsPlannierError(f"Failed to get team members: {response.status_code}")

        except Exception as e:
            logger.error("Error getting team members", error=str(e))
            raise TeamsPlannierError(f"Error getting team members: {str(e)}")

    async def send_channel_message(
        self,
        user_id: str,
        team_id: str,
        channel_id: str,
        message: str,
        content_type: str = "text"
    ) -> Dict[str, Any]:
        """Send a message to a Teams channel"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            message_data = {
                "body": {
                    "contentType": content_type,
                    "content": message
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/teams/{team_id}/channels/{channel_id}/messages",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=message_data
                )

                if response.status_code == 201:
                    message_result = response.json()
                    logger.info("Message sent successfully",
                              message_id=message_result.get('id'),
                              team_id=team_id,
                              channel_id=channel_id)
                    return message_result
                else:
                    error_text = response.text
                    logger.error("Failed to send message",
                               status_code=response.status_code,
                               error=error_text)
                    raise TeamsPlannierError(f"Failed to send message: {response.status_code} - {error_text}")

        except Exception as e:
            logger.error("Error sending message", error=str(e))
            raise TeamsPlannierError(f"Error sending message: {str(e)}")

    async def create_planner_plan(
        self,
        user_id: str,
        group_id: str,
        title: str,
        description: str = None
    ) -> Dict[str, Any]:
        """Create a new Planner plan for a group/team"""
        try:
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise TeamsPlannierError("No valid access token available")

            plan_data = {
                "container": {
                    "containerId": group_id,
                    "type": "group"
                },
                "title": title
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/planner/plans",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=plan_data
                )

                if response.status_code == 201:
                    plan_result = response.json()
                    logger.info("Plan created successfully",
                              plan_id=plan_result.get('id'),
                              title=title,
                              group_id=group_id)
                    return plan_result
                else:
                    error_text = response.text
                    logger.error("Failed to create plan",
                               status_code=response.status_code,
                               error=error_text)
                    raise TeamsPlannierError(f"Failed to create plan: {response.status_code} - {error_text}")

        except Exception as e:
            logger.error("Error creating plan", error=str(e))
            raise TeamsPlannierError(f"Error creating plan: {str(e)}")

    async def test_connectivity(self, user_id: str) -> Dict[str, Any]:
        """Test basic connectivity to Microsoft Graph for Teams and Planner"""
        results = {
            "user_info": None,
            "teams": None,
            "connectivity_test": False,
            "errors": []
        }

        try:
            # Test 1: Get user info
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                results["errors"].append("No valid access token available")
                return results

            async with httpx.AsyncClient() as client:
                # Test user info
                response = await client.get(
                    f"{self.base_url}/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    results["user_info"] = response.json()
                    logger.info("User info retrieved successfully")
                else:
                    results["errors"].append(f"Failed to get user info: {response.status_code}")

                # Test teams access
                response = await client.get(
                    f"{self.base_url}/me/joinedTeams",
                    headers={"Authorization": f"Bearer {access_token}"}
                )

                if response.status_code == 200:
                    teams_data = response.json()
                    results["teams"] = teams_data.get('value', [])
                    results["connectivity_test"] = True
                    logger.info("Teams connectivity test successful",
                              teams_count=len(results["teams"]))
                else:
                    results["errors"].append(f"Failed to get teams: {response.status_code}")

        except Exception as e:
            error_msg = f"Connectivity test failed: {str(e)}"
            results["errors"].append(error_msg)
            logger.error("Connectivity test error", error=str(e))

        return results


async def run_mvp_test():
    """Run a simple MVP test to verify Teams and Planner connectivity"""
    from .cache import CacheService
    import os

    # Initialize services
    cache_service = CacheService("redis://localhost:6379/0")
    await cache_service.initialize()

    auth_service = AuthService(
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_secret=os.getenv("AZURE_CLIENT_SECRET"),
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        cache_service=cache_service
    )

    client = SimpleTeamsPlannerClient(auth_service)

    # Test connectivity
    print("Testing Microsoft Teams and Planner connectivity...")
    test_user_id = "test_user"  # This would be a real user in practice

    try:
        results = await client.test_connectivity(test_user_id)
        print(f"Connectivity test results: {results}")

        if results["connectivity_test"]:
            print("✅ Successfully connected to Microsoft Teams and Planner!")

            # If we have teams, try to get plans for the first team
            if results["teams"]:
                first_team = results["teams"][0]
                team_id = first_team["id"]
                print(f"Testing plan access for team: {first_team.get('displayName', 'Unknown')}")

                plans = await client.get_team_planner_plans(test_user_id, team_id)
                print(f"Found {len(plans)} plans in the team")

                # If we have plans, test creating a task
                if plans:
                    first_plan = plans[0]
                    plan_id = first_plan["id"]
                    print(f"Testing task creation in plan: {first_plan.get('title', 'Unknown')}")

                    task = await client.create_planner_task(
                        test_user_id,
                        plan_id,
                        "MVP Test Task",
                        "This is a test task created by the MVP implementation"
                    )
                    print(f"✅ Task created successfully: {task['id']}")

        else:
            print("❌ Connectivity test failed")
            for error in results["errors"]:
                print(f"Error: {error}")

    except Exception as e:
        print(f"❌ MVP test failed: {str(e)}")

    finally:
        await cache_service.close()


if __name__ == "__main__":
    asyncio.run(run_mvp_test())
