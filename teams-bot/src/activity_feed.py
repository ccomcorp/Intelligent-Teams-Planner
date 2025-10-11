"""
Teams Activity Feed Integration
Manages activity feed notifications and updates for Microsoft Teams
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import json
import asyncio
import structlog
import httpx
from enum import Enum

try:
    from .adaptive_cards import AdaptiveCardTemplates
except ImportError:
    from adaptive_cards import AdaptiveCardTemplates

logger = structlog.get_logger(__name__)


class ActivityType(Enum):
    """Types of activities that can be posted to Teams feed"""
    TASK_CREATED = "taskCreated"
    TASK_ASSIGNED = "taskAssigned"
    TASK_COMPLETED = "taskCompleted"
    TASK_OVERDUE = "taskOverdue"
    TASK_UPDATED = "taskUpdated"
    PLAN_CREATED = "planCreated"
    PLAN_UPDATED = "planUpdated"
    MENTION_RECEIVED = "mentionReceived"
    COMMENT_ADDED = "commentAdded"


class ActivityFeedManager:
    """Manages Teams activity feed integration"""

    def __init__(
        self,
        graph_api_url: str = "https://graph.microsoft.com/v1.0",
        max_retries: int = 3,
        timeout: float = 30.0
    ):
        self.graph_api_url = graph_api_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()

    async def send_activity_notification(
        self,
        activity_type: ActivityType,
        recipient_id: str,
        actor_id: str,
        activity_data: Dict[str, Any],
        auth_token: Optional[str] = None,
        team_id: Optional[str] = None,
        channel_id: Optional[str] = None
    ) -> bool:
        """
        Send activity notification to Teams activity feed

        Args:
            activity_type: Type of activity
            recipient_id: User ID to notify
            actor_id: User ID who performed the action
            activity_data: Activity-specific data
            auth_token: Authentication token for Graph API
            team_id: Team ID (if applicable)
            channel_id: Channel ID (if applicable)

        Returns:
            Success status
        """
        try:
            if not auth_token:
                logger.warning("No auth token provided for activity notification")
                return False

            # Create activity payload
            activity_payload = self._create_activity_payload(
                activity_type, recipient_id, actor_id, activity_data, team_id, channel_id
            )

            # Send to Graph API
            success = await self._send_to_graph_api(activity_payload, auth_token)

            if success:
                logger.info(
                    "Activity notification sent successfully",
                    activity_type=activity_type.value,
                    recipient_id=recipient_id
                )
            else:
                logger.error(
                    "Failed to send activity notification",
                    activity_type=activity_type.value,
                    recipient_id=recipient_id
                )

            return success

        except Exception as e:
            logger.error("Error sending activity notification", error=str(e))
            return False

    def _create_activity_payload(
        self,
        activity_type: ActivityType,
        recipient_id: str,
        actor_id: str,
        activity_data: Dict[str, Any],
        team_id: Optional[str] = None,
        channel_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create activity payload for Graph API"""

        base_payload = {
            "topic": {
                "source": "entityUrl",
                "value": f"https://graph.microsoft.com/v1.0/users/{recipient_id}"
            },
            "activityType": activity_type.value,
            "previewText": {
                "content": self._generate_preview_text(activity_type, activity_data)
            },
            "recipient": {
                "@odata.type": "microsoft.graph.aadUserNotificationRecipient",
                "userId": recipient_id
            },
            "templateParameters": self._create_template_parameters(activity_type, activity_data, actor_id)
        }

        # Add team/channel context if provided
        if team_id:
            base_payload["topic"]["value"] = f"https://graph.microsoft.com/v1.0/teams/{team_id}"
            if channel_id:
                base_payload["topic"]["value"] += f"/channels/{channel_id}"

        return base_payload

    def _generate_preview_text(self, activity_type: ActivityType, activity_data: Dict[str, Any]) -> str:
        """Generate preview text for activity notification"""

        task_title = activity_data.get("taskTitle", "a task")
        plan_name = activity_data.get("planName", "a plan")
        actor_name = activity_data.get("actorName", "Someone")

        preview_texts = {
            ActivityType.TASK_CREATED: f"New task created: {task_title}",
            ActivityType.TASK_ASSIGNED: f"Task assigned to you: {task_title}",
            ActivityType.TASK_COMPLETED: f"Task completed: {task_title}",
            ActivityType.TASK_OVERDUE: f"Task overdue: {task_title}",
            ActivityType.TASK_UPDATED: f"Task updated: {task_title}",
            ActivityType.PLAN_CREATED: f"New plan created: {plan_name}",
            ActivityType.PLAN_UPDATED: f"Plan updated: {plan_name}",
            ActivityType.MENTION_RECEIVED: f"You were mentioned in: {task_title}",
            ActivityType.COMMENT_ADDED: f"New comment on: {task_title}"
        }

        return preview_texts.get(activity_type, f"{actor_name} performed an action")

    def _create_template_parameters(
        self,
        activity_type: ActivityType,
        activity_data: Dict[str, Any],
        actor_id: str
    ) -> List[Dict[str, str]]:
        """Create template parameters for activity notification"""

        parameters = [
            {
                "name": "actor",
                "value": activity_data.get("actorName", actor_id)
            }
        ]

        # Add activity-specific parameters
        if activity_type in [
            ActivityType.TASK_CREATED,
            ActivityType.TASK_ASSIGNED,
            ActivityType.TASK_COMPLETED,
            ActivityType.TASK_OVERDUE,
            ActivityType.TASK_UPDATED,
            ActivityType.MENTION_RECEIVED,
            ActivityType.COMMENT_ADDED
        ]:
            if "taskTitle" in activity_data:
                parameters.append({
                    "name": "taskTitle",
                    "value": activity_data["taskTitle"]
                })

        elif activity_type in [ActivityType.PLAN_CREATED, ActivityType.PLAN_UPDATED]:
            if "planName" in activity_data:
                parameters.append({
                    "name": "planName",
                    "value": activity_data["planName"]
                })

        # Add assignee for task assignment
        if activity_type == ActivityType.TASK_ASSIGNED and "assigneeName" in activity_data:
            parameters.append({
                "name": "assignee",
                "value": activity_data["assigneeName"]
            })

        return parameters

    async def _send_to_graph_api(self, payload: Dict[str, Any], auth_token: str) -> bool:
        """Send activity notification to Microsoft Graph API"""

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }

        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(
                    f"{self.graph_api_url}/me/teamwork/sendActivityNotification",
                    json=payload,
                    headers=headers
                )

                if response.status_code in [200, 201, 202]:
                    return True
                elif response.status_code == 429:  # Rate limited
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited, retrying after {retry_after} seconds")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    logger.error(
                        "Graph API error",
                        status_code=response.status_code,
                        response=response.text,
                        attempt=attempt + 1
                    )

            except Exception as e:
                logger.error(f"Error sending to Graph API (attempt {attempt + 1})", error=str(e))

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return False

    async def notify_task_created(
        self,
        task_id: str,
        task_title: str,
        plan_name: str,
        creator_id: str,
        creator_name: str,
        assigned_users: List[Dict[str, str]],
        auth_token: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> List[bool]:
        """Send task created notifications to assigned users"""

        results = []
        activity_data = {
            "taskId": task_id,
            "taskTitle": task_title,
            "planName": plan_name,
            "actorName": creator_name,
            "createdAt": datetime.now(timezone.utc).isoformat()
        }

        for user in assigned_users:
            user_id = user.get("id")
            if user_id and user_id != creator_id:  # Don't notify creator
                success = await self.send_activity_notification(
                    ActivityType.TASK_CREATED,
                    user_id,
                    creator_id,
                    activity_data,
                    auth_token,
                    team_id
                )
                results.append(success)

        return results

    async def notify_task_assigned(
        self,
        task_id: str,
        task_title: str,
        assignee_id: str,
        assignee_name: str,
        assigner_id: str,
        assigner_name: str,
        auth_token: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> bool:
        """Send task assignment notification"""

        activity_data = {
            "taskId": task_id,
            "taskTitle": task_title,
            "assigneeName": assignee_name,
            "actorName": assigner_name,
            "assignedAt": datetime.now(timezone.utc).isoformat()
        }

        return await self.send_activity_notification(
            ActivityType.TASK_ASSIGNED,
            assignee_id,
            assigner_id,
            activity_data,
            auth_token,
            team_id
        )

    async def notify_task_completed(
        self,
        task_id: str,
        task_title: str,
        completer_id: str,
        completer_name: str,
        notify_users: List[str],
        auth_token: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> List[bool]:
        """Send task completion notifications"""

        results = []
        activity_data = {
            "taskId": task_id,
            "taskTitle": task_title,
            "actorName": completer_name,
            "completedAt": datetime.now(timezone.utc).isoformat()
        }

        for user_id in notify_users:
            if user_id != completer_id:  # Don't notify completer
                success = await self.send_activity_notification(
                    ActivityType.TASK_COMPLETED,
                    user_id,
                    completer_id,
                    activity_data,
                    auth_token,
                    team_id
                )
                results.append(success)

        return results

    async def notify_task_overdue(
        self,
        task_id: str,
        task_title: str,
        assigned_users: List[str],
        due_date: str,
        auth_token: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> List[bool]:
        """Send overdue task notifications"""

        results = []
        activity_data = {
            "taskId": task_id,
            "taskTitle": task_title,
            "dueDate": due_date,
            "overdueAt": datetime.now(timezone.utc).isoformat()
        }

        # Use system as actor for overdue notifications
        system_actor_id = "system"

        for user_id in assigned_users:
            success = await self.send_activity_notification(
                ActivityType.TASK_OVERDUE,
                user_id,
                system_actor_id,
                activity_data,
                auth_token,
                team_id
            )
            results.append(success)

        return results

    async def notify_mention_received(
        self,
        task_id: str,
        task_title: str,
        mentioned_user_id: str,
        mentioner_id: str,
        mentioner_name: str,
        message: str,
        auth_token: Optional[str] = None,
        team_id: Optional[str] = None,
        channel_id: Optional[str] = None
    ) -> bool:
        """Send mention notification to activity feed"""

        activity_data = {
            "taskId": task_id,
            "taskTitle": task_title,
            "actorName": mentioner_name,
            "message": message[:100] + "..." if len(message) > 100 else message,
            "mentionedAt": datetime.now(timezone.utc).isoformat()
        }

        return await self.send_activity_notification(
            ActivityType.MENTION_RECEIVED,
            mentioned_user_id,
            mentioner_id,
            activity_data,
            auth_token,
            team_id,
            channel_id
        )

    async def create_activity_summary_card(
        self,
        user_id: str,
        time_period: str = "today",
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create activity summary card for user"""

        try:
            # In a full implementation, this would fetch actual activity data
            # For now, we'll create a mock summary
            activities = await self._fetch_user_activities(user_id, time_period, auth_token)

            # Create summary statistics
            stats = self._calculate_activity_stats(activities)

            # Create adaptive card
            card = {
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {
                        "type": "Container",
                        "style": "emphasis",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"📊 **Activity Summary - {time_period.title()}**",
                                "size": "large",
                                "weight": "bolder"
                            }
                        ]
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {
                                "title": "Tasks Created:",
                                "value": str(stats.get("tasks_created", 0))
                            },
                            {
                                "title": "Tasks Completed:",
                                "value": str(stats.get("tasks_completed", 0))
                            },
                            {
                                "title": "Tasks Assigned:",
                                "value": str(stats.get("tasks_assigned", 0))
                            },
                            {
                                "title": "Mentions Received:",
                                "value": str(stats.get("mentions_received", 0))
                            }
                        ],
                        "spacing": "medium"
                    }
                ]
            }

            # Add recent activities
            if activities:
                card["body"].append({
                    "type": "TextBlock",
                    "text": "**Recent Activities:**",
                    "weight": "bolder",
                    "spacing": "medium",
                    "separator": True
                })

                for activity in activities[:5]:  # Show last 5 activities
                    card["body"].append({
                        "type": "TextBlock",
                        "text": f"• {activity.get('description', 'Activity')}",
                        "size": "small",
                        "spacing": "small"
                    })

            # Add action buttons
            card["actions"] = [
                {
                    "type": "Action.Submit",
                    "title": "View All Activities",
                    "data": {
                        "action": "viewAllActivities",
                        "userId": user_id,
                        "timePeriod": time_period
                    }
                },
                {
                    "type": "Action.Submit",
                    "title": "Refresh",
                    "data": {
                        "action": "refreshActivitySummary",
                        "userId": user_id,
                        "timePeriod": time_period
                    }
                }
            ]

            return card

        except Exception as e:
            logger.error("Error creating activity summary card", error=str(e))
            return AdaptiveCardTemplates.error_card(
                "Failed to load activity summary",
                suggested_action="Try refreshing the page or contact support"
            )

    async def _fetch_user_activities(
        self,
        user_id: str,
        time_period: str,
        auth_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch user activities from Graph API"""

        # Mock implementation - in reality this would call Graph API
        mock_activities = [
            {
                "type": "taskCreated",
                "description": "Created task 'Review proposal'",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            {
                "type": "taskCompleted",
                "description": "Completed task 'Design mockups'",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]

        return mock_activities

    def _calculate_activity_stats(self, activities: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate activity statistics"""

        stats = {
            "tasks_created": 0,
            "tasks_completed": 0,
            "tasks_assigned": 0,
            "mentions_received": 0,
            "plans_created": 0
        }

        for activity in activities:
            activity_type = activity.get("type", "")
            if activity_type == "taskCreated":
                stats["tasks_created"] += 1
            elif activity_type == "taskCompleted":
                stats["tasks_completed"] += 1
            elif activity_type == "taskAssigned":
                stats["tasks_assigned"] += 1
            elif activity_type == "mentionReceived":
                stats["mentions_received"] += 1
            elif activity_type == "planCreated":
                stats["plans_created"] += 1

        return stats

    async def batch_send_notifications(
        self,
        notifications: List[Dict[str, Any]],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send multiple notifications in batch"""

        results = {
            "total": len(notifications),
            "succeeded": 0,
            "failed": 0,
            "errors": []
        }

        # Process notifications in parallel (with reasonable concurrency)
        semaphore = asyncio.Semaphore(10)  # Limit to 10 concurrent requests

        async def send_single_notification(notification: Dict[str, Any]) -> bool:
            async with semaphore:
                try:
                    return await self.send_activity_notification(
                        ActivityType(notification["activity_type"]),
                        notification["recipient_id"],
                        notification["actor_id"],
                        notification["activity_data"],
                        auth_token,
                        notification.get("team_id"),
                        notification.get("channel_id")
                    )
                except Exception as e:
                    results["errors"].append(str(e))
                    return False

        # Execute all notifications
        tasks = [send_single_notification(notif) for notif in notifications]
        notification_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        for result in notification_results:
            if isinstance(result, bool):
                if result:
                    results["succeeded"] += 1
                else:
                    results["failed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(str(result))

        logger.info(
            "Batch notification results",
            total=results["total"],
            succeeded=results["succeeded"],
            failed=results["failed"]
        )

        return results