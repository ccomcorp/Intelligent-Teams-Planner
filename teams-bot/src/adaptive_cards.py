"""
Adaptive Cards for Teams App - Task Display Templates
Provides rich card templates for displaying Planner tasks and plans
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json


class AdaptiveCardTemplates:
    """Factory class for creating adaptive card templates"""

    @staticmethod
    def task_card(
        task_id: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium",
        status: str = "notStarted",
        assigned_to: Optional[List[Dict[str, str]]] = None,
        due_date: Optional[str] = None,
        plan_name: Optional[str] = None,
        progress_percent: int = 0,
        created_by: Optional[str] = None,
        created_date: Optional[str] = None,
        checklist_items: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create adaptive card for task display"""

        # Priority color mapping
        priority_colors = {
            "low": "good",
            "medium": "warning",
            "high": "attention",
            "urgent": "destructive"
        }

        # Status icon mapping
        status_icons = {
            "notStarted": "⏳",
            "inProgress": "🔄",
            "completed": "✅",
            "deferred": "⏸️",
            "waiting": "⏰"
        }

        card = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "emphasis",
                    "items": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "stretch",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": f"{status_icons.get(status, '📋')} **{title}**",
                                            "size": "medium",
                                            "weight": "bolder",
                                            "wrap": True
                                        }
                                    ]
                                },
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": priority.upper(),
                                            "size": "small",
                                            "weight": "bolder",
                                            "color": priority_colors.get(priority, "default"),
                                            "horizontalAlignment": "right"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Add plan information if available
        if plan_name:
            card["body"].append({
                "type": "TextBlock",
                "text": f"📁 **Plan:** {plan_name}",
                "size": "small",
                "color": "accent",
                "spacing": "small"
            })

        # Add description if available
        if description:
            card["body"].append({
                "type": "TextBlock",
                "text": description,
                "wrap": True,
                "spacing": "small"
            })

        # Add progress bar if task is in progress
        if status == "inProgress" and progress_percent > 0:
            card["body"].append({
                "type": "TextBlock",
                "text": f"Progress: {progress_percent}%",
                "size": "small",
                "spacing": "small"
            })
            card["body"].append({
                "type": "ProgressBar",
                "value": progress_percent,
                "spacing": "none"
            })

        # Add assignment information
        if assigned_to:
            assignee_text = ", ".join([f"@{user.get('name', user.get('id', 'Unknown'))}"
                                     for user in assigned_to])
            card["body"].append({
                "type": "TextBlock",
                "text": f"👤 **Assigned to:** {assignee_text}",
                "size": "small",
                "spacing": "small"
            })

        # Add due date if available
        if due_date:
            try:
                due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                is_overdue = due_dt < now

                due_text = f"📅 **Due:** {due_dt.strftime('%B %d, %Y at %I:%M %p')}"
                if is_overdue:
                    due_text += " ⚠️ **OVERDUE**"

                card["body"].append({
                    "type": "TextBlock",
                    "text": due_text,
                    "size": "small",
                    "color": "attention" if is_overdue else "default",
                    "spacing": "small"
                })
            except (ValueError, AttributeError):
                card["body"].append({
                    "type": "TextBlock",
                    "text": f"📅 **Due:** {due_date}",
                    "size": "small",
                    "spacing": "small"
                })

        # Add checklist if available
        if checklist_items:
            completed_items = sum(1 for item in checklist_items if item.get("isChecked", False))
            total_items = len(checklist_items)

            card["body"].append({
                "type": "TextBlock",
                "text": f"✅ **Checklist:** {completed_items}/{total_items} completed",
                "size": "small",
                "spacing": "medium"
            })

            # Show first few checklist items
            for i, item in enumerate(checklist_items[:3]):
                icon = "✅" if item.get("isChecked", False) else "⬜"
                card["body"].append({
                    "type": "TextBlock",
                    "text": f"{icon} {item.get('title', 'Checklist item')}",
                    "size": "small",
                    "spacing": "none"
                })

            if len(checklist_items) > 3:
                card["body"].append({
                    "type": "TextBlock",
                    "text": f"... and {len(checklist_items) - 3} more items",
                    "size": "small",
                    "color": "accent",
                    "spacing": "none"
                })

        # Add metadata footer
        footer_items = []
        if created_by:
            footer_items.append(f"Created by {created_by}")
        if created_date:
            try:
                created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                footer_items.append(f"on {created_dt.strftime('%B %d, %Y')}")
            except (ValueError, AttributeError):
                footer_items.append(f"on {created_date}")

        if footer_items:
            card["body"].append({
                "type": "TextBlock",
                "text": " ".join(footer_items),
                "size": "small",
                "color": "accent",
                "spacing": "medium",
                "separator": True
            })

        # Add action buttons
        card["actions"] = [
            {
                "type": "Action.Submit",
                "title": "View Details",
                "data": {
                    "action": "viewTask",
                    "taskId": task_id
                }
            },
            {
                "type": "Action.Submit",
                "title": "Edit Task",
                "data": {
                    "action": "editTask",
                    "taskId": task_id
                }
            }
        ]

        # Add status-specific actions
        if status != "completed":
            card["actions"].append({
                "type": "Action.Submit",
                "title": "Mark Complete",
                "data": {
                    "action": "completeTask",
                    "taskId": task_id
                }
            })

        if assigned_to:
            card["actions"].append({
                "type": "Action.Submit",
                "title": "Reassign",
                "data": {
                    "action": "reassignTask",
                    "taskId": task_id
                }
            })

        return card

    @staticmethod
    def plan_summary_card(
        plan_id: str,
        plan_name: str,
        description: Optional[str] = None,
        owner: Optional[str] = None,
        total_tasks: int = 0,
        completed_tasks: int = 0,
        overdue_tasks: int = 0,
        team_members: Optional[List[Dict[str, str]]] = None,
        created_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create adaptive card for plan summary display"""

        completion_percent = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0

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
                            "text": f"📋 **{plan_name}**",
                            "size": "large",
                            "weight": "bolder",
                            "wrap": True
                        }
                    ]
                }
            ]
        }

        # Add description if available
        if description:
            card["body"].append({
                "type": "TextBlock",
                "text": description,
                "wrap": True,
                "spacing": "small"
            })

        # Add progress statistics
        card["body"].append({
            "type": "FactSet",
            "facts": [
                {
                    "title": "Total Tasks:",
                    "value": str(total_tasks)
                },
                {
                    "title": "Completed:",
                    "value": f"{completed_tasks} ({completion_percent}%)"
                },
                {
                    "title": "In Progress:",
                    "value": str(total_tasks - completed_tasks - overdue_tasks)
                }
            ],
            "spacing": "medium"
        })

        # Add overdue warning if applicable
        if overdue_tasks > 0:
            card["body"].append({
                "type": "TextBlock",
                "text": f"⚠️ **{overdue_tasks} overdue tasks**",
                "color": "attention",
                "weight": "bolder",
                "spacing": "small"
            })

        # Add progress bar
        if total_tasks > 0:
            card["body"].append({
                "type": "TextBlock",
                "text": f"Overall Progress: {completion_percent}%",
                "size": "small",
                "spacing": "medium"
            })
            card["body"].append({
                "type": "ProgressBar",
                "value": completion_percent,
                "spacing": "none"
            })

        # Add team members if available
        if team_members:
            member_text = ", ".join([f"@{member.get('name', member.get('id', 'Unknown'))}"
                                   for member in team_members[:5]])
            if len(team_members) > 5:
                member_text += f" and {len(team_members) - 5} more"

            card["body"].append({
                "type": "TextBlock",
                "text": f"👥 **Team Members:** {member_text}",
                "size": "small",
                "spacing": "medium"
            })

        # Add metadata
        footer_items = []
        if owner:
            footer_items.append(f"Owned by {owner}")
        if created_date:
            try:
                created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                footer_items.append(f"created {created_dt.strftime('%B %d, %Y')}")
            except (ValueError, AttributeError):
                footer_items.append(f"created {created_date}")

        if footer_items:
            card["body"].append({
                "type": "TextBlock",
                "text": " ".join(footer_items),
                "size": "small",
                "color": "accent",
                "spacing": "medium",
                "separator": True
            })

        # Add action buttons
        card["actions"] = [
            {
                "type": "Action.Submit",
                "title": "View All Tasks",
                "data": {
                    "action": "viewPlanTasks",
                    "planId": plan_id
                }
            },
            {
                "type": "Action.Submit",
                "title": "Add Task",
                "data": {
                    "action": "addTask",
                    "planId": plan_id
                }
            },
            {
                "type": "Action.Submit",
                "title": "Plan Settings",
                "data": {
                    "action": "planSettings",
                    "planId": plan_id
                }
            }
        ]

        return card

    @staticmethod
    def task_list_card(
        tasks: List[Dict[str, Any]],
        title: str = "Tasks",
        filter_applied: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create adaptive card for displaying a list of tasks"""

        card = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"📋 **{title}**",
                    "size": "large",
                    "weight": "bolder"
                }
            ]
        }

        # Add filter information if applicable
        if filter_applied:
            card["body"].append({
                "type": "TextBlock",
                "text": f"🔍 Filter: {filter_applied}",
                "size": "small",
                "color": "accent",
                "spacing": "small"
            })

        # Add task count
        card["body"].append({
            "type": "TextBlock",
            "text": f"Found {len(tasks)} task{'s' if len(tasks) != 1 else ''}",
            "size": "small",
            "spacing": "small",
            "separator": True
        })

        # Add tasks (limit to first 10 for readability)
        tasks_to_show = tasks[:10]
        for i, task in enumerate(tasks_to_show):
            status_icon = {
                "notStarted": "⏳",
                "inProgress": "🔄",
                "completed": "✅",
                "deferred": "⏸️",
                "waiting": "⏰"
            }.get(task.get("status", "notStarted"), "📋")

            priority_color = {
                "low": "good",
                "medium": "default",
                "high": "warning",
                "urgent": "attention"
            }.get(task.get("priority", "medium"), "default")

            # Task item container
            task_container = {
                "type": "Container",
                "style": "default",
                "items": [
                    {
                        "type": "ColumnSet",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": f"{status_icon} **{task.get('title', 'Untitled Task')}**",
                                        "size": "medium",
                                        "weight": "bolder",
                                        "wrap": True
                                    }
                                ]
                            },
                            {
                                "type": "Column",
                                "width": "auto",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": task.get("priority", "medium").upper(),
                                        "size": "small",
                                        "weight": "bolder",
                                        "color": priority_color,
                                        "horizontalAlignment": "right"
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "spacing": "medium" if i > 0 else "small",
                "separator": i > 0
            }

            # Add assignment info if available
            if task.get("assignedTo"):
                assignees = task["assignedTo"]
                if isinstance(assignees, list) and assignees:
                    assignee_text = ", ".join([f"@{a.get('name', a.get('id', 'Unknown'))}"
                                             for a in assignees[:2]])
                    if len(assignees) > 2:
                        assignee_text += f" +{len(assignees) - 2}"

                    task_container["items"].append({
                        "type": "TextBlock",
                        "text": f"👤 {assignee_text}",
                        "size": "small",
                        "spacing": "none"
                    })

            # Add due date if available
            if task.get("dueDateTime"):
                due_date = task["dueDateTime"]
                try:
                    due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    is_overdue = due_dt < now

                    due_text = f"📅 Due {due_dt.strftime('%m/%d/%Y')}"
                    if is_overdue:
                        due_text += " ⚠️"

                    task_container["items"].append({
                        "type": "TextBlock",
                        "text": due_text,
                        "size": "small",
                        "color": "attention" if is_overdue else "default",
                        "spacing": "none"
                    })
                except (ValueError, AttributeError):
                    task_container["items"].append({
                        "type": "TextBlock",
                        "text": f"📅 Due {due_date}",
                        "size": "small",
                        "spacing": "none"
                    })

            card["body"].append(task_container)

        # Add "show more" indicator if there are more tasks
        if len(tasks) > 10:
            card["body"].append({
                "type": "TextBlock",
                "text": f"... and {len(tasks) - 10} more tasks",
                "size": "small",
                "color": "accent",
                "spacing": "medium",
                "separator": True
            })

        # Add action buttons
        if tasks:
            card["actions"] = [
                {
                    "type": "Action.Submit",
                    "title": "Refresh",
                    "data": {
                        "action": "refreshTasks"
                    }
                },
                {
                    "type": "Action.Submit",
                    "title": "Add Task",
                    "data": {
                        "action": "addTask"
                    }
                }
            ]

        return card

    @staticmethod
    def mention_notification_card(
        mentioned_by: str,
        task_title: str,
        task_id: str,
        message: str,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create adaptive card for @mention notifications"""

        card = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "attention",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "💬 **You were mentioned in a task**",
                            "size": "medium",
                            "weight": "bolder"
                        }
                    ]
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {
                            "title": "Mentioned by:",
                            "value": f"@{mentioned_by}"
                        },
                        {
                            "title": "Task:",
                            "value": task_title
                        }
                    ],
                    "spacing": "medium"
                },
                {
                    "type": "TextBlock",
                    "text": f"**Message:** {message}",
                    "wrap": True,
                    "spacing": "medium"
                }
            ]
        }

        # Add timestamp if available
        if timestamp:
            try:
                ts_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                card["body"].append({
                    "type": "TextBlock",
                    "text": f"🕒 {ts_dt.strftime('%B %d, %Y at %I:%M %p')}",
                    "size": "small",
                    "color": "accent",
                    "spacing": "small"
                })
            except (ValueError, AttributeError):
                card["body"].append({
                    "type": "TextBlock",
                    "text": f"🕒 {timestamp}",
                    "size": "small",
                    "color": "accent",
                    "spacing": "small"
                })

        # Add action buttons
        card["actions"] = [
            {
                "type": "Action.Submit",
                "title": "View Task",
                "data": {
                    "action": "viewTask",
                    "taskId": task_id
                }
            },
            {
                "type": "Action.Submit",
                "title": "Reply",
                "data": {
                    "action": "replyToMention",
                    "taskId": task_id,
                    "mentionedBy": mentioned_by
                }
            }
        ]

        return card

    @staticmethod
    def error_card(
        error_message: str,
        error_code: Optional[str] = None,
        suggested_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create adaptive card for error display"""

        card = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "attention",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "⚠️ **Error**",
                            "size": "medium",
                            "weight": "bolder",
                            "color": "attention"
                        }
                    ]
                },
                {
                    "type": "TextBlock",
                    "text": error_message,
                    "wrap": True,
                    "spacing": "medium"
                }
            ]
        }

        # Add error code if available
        if error_code:
            card["body"].append({
                "type": "TextBlock",
                "text": f"**Error Code:** {error_code}",
                "size": "small",
                "color": "accent",
                "spacing": "small"
            })

        # Add suggested action if available
        if suggested_action:
            card["body"].append({
                "type": "TextBlock",
                "text": f"**Suggested Action:** {suggested_action}",
                "wrap": True,
                "spacing": "medium"
            })

        # Add action buttons
        card["actions"] = [
            {
                "type": "Action.Submit",
                "title": "Try Again",
                "data": {
                    "action": "retry"
                }
            },
            {
                "type": "Action.Submit",
                "title": "Get Help",
                "data": {
                    "action": "getHelp"
                }
            }
        ]

        return card