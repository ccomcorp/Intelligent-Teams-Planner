"""
Test suite for adaptive card templates
Tests all card creation functionality
"""

import pytest
import sys
import os
from datetime import datetime, timezone

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from adaptive_cards import AdaptiveCardTemplates


class TestAdaptiveCardTemplates:
    """Test adaptive card template generation"""

    def test_task_card_basic(self):
        """Test basic task card creation"""
        card = AdaptiveCardTemplates.task_card(
            task_id="test-task-1",
            title="Review Project Proposal",
            description="Review the Q4 project proposal document",
            priority="high",
            status="inProgress"
        )

        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"
        assert len(card["body"]) > 0
        assert len(card["actions"]) > 0

        # Check title is present
        title_found = False
        for item in card["body"]:
            if item.get("type") == "Container":
                for subitem in item.get("items", []):
                    if subitem.get("type") == "ColumnSet":
                        for column in subitem.get("columns", []):
                            for column_item in column.get("items", []):
                                if "Review Project Proposal" in column_item.get("text", ""):
                                    title_found = True
        assert title_found

    def test_task_card_with_assignments(self):
        """Test task card with assigned users"""
        assigned_users = [
            {"id": "user1", "name": "John Smith"},
            {"id": "user2", "name": "Jane Doe"}
        ]

        card = AdaptiveCardTemplates.task_card(
            task_id="test-task-2",
            title="Development Task",
            assigned_to=assigned_users,
            due_date="2025-01-15T10:00:00Z"
        )

        # Check assignment text is present
        assignment_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                if "Assigned to" in text and "John Smith" in text:
                    assignment_found = True
        assert assignment_found

    def test_task_card_with_checklist(self):
        """Test task card with checklist items"""
        checklist_items = [
            {"title": "Complete research", "isChecked": True},
            {"title": "Write report", "isChecked": False},
            {"title": "Present findings", "isChecked": False}
        ]

        card = AdaptiveCardTemplates.task_card(
            task_id="test-task-3",
            title="Research Project",
            checklist_items=checklist_items
        )

        # Check checklist is present
        checklist_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                if "Checklist" in text and "1/3" in text:
                    checklist_found = True
        assert checklist_found

    def test_task_card_overdue(self):
        """Test task card with overdue date"""
        past_date = "2024-12-01T10:00:00Z"

        card = AdaptiveCardTemplates.task_card(
            task_id="test-task-4",
            title="Overdue Task",
            due_date=past_date,
            status="inProgress"
        )

        # Check overdue warning is present
        overdue_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                if "OVERDUE" in text:
                    overdue_found = True
        assert overdue_found

    def test_plan_summary_card(self):
        """Test plan summary card creation"""
        team_members = [
            {"id": "user1", "name": "Alice Johnson"},
            {"id": "user2", "name": "Bob Wilson"}
        ]

        card = AdaptiveCardTemplates.plan_summary_card(
            plan_id="plan-1",
            plan_name="Q1 Marketing Campaign",
            description="Marketing campaign for Q1 product launch",
            owner="Alice Johnson",
            total_tasks=10,
            completed_tasks=6,
            overdue_tasks=1,
            team_members=team_members
        )

        assert card["type"] == "AdaptiveCard"
        assert len(card["body"]) > 0

        # Check plan name is present
        plan_name_found = False
        for item in card["body"]:
            if item.get("type") == "Container":
                for subitem in item.get("items", []):
                    if "Q1 Marketing Campaign" in subitem.get("text", ""):
                        plan_name_found = True
        assert plan_name_found

        # Check facts are present
        facts_found = False
        for item in card["body"]:
            if item.get("type") == "FactSet":
                facts = item.get("facts", [])
                if any(fact.get("title") == "Total Tasks:" for fact in facts):
                    facts_found = True
        assert facts_found

    def test_task_list_card(self):
        """Test task list card creation"""
        tasks = [
            {
                "title": "Task 1",
                "status": "completed",
                "priority": "high",
                "assignedTo": [{"name": "John"}]
            },
            {
                "title": "Task 2",
                "status": "inProgress",
                "priority": "medium",
                "dueDateTime": "2025-02-01T10:00:00Z"
            }
        ]

        card = AdaptiveCardTemplates.task_list_card(
            tasks=tasks,
            title="My Tasks",
            filter_applied="Status: In Progress"
        )

        assert card["type"] == "AdaptiveCard"
        assert len(card["body"]) > 0

        # Check task count
        count_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                if "Found 2 tasks" in text:
                    count_found = True
        assert count_found

    def test_mention_notification_card(self):
        """Test mention notification card creation"""
        card = AdaptiveCardTemplates.mention_notification_card(
            mentioned_by="Alice Johnson",
            task_title="Review Budget Proposal",
            task_id="task-123",
            message="Please review the budget proposal for Q2",
            timestamp="2025-01-10T14:30:00Z"
        )

        assert card["type"] == "AdaptiveCard"
        assert len(card["actions"]) >= 2

        # Check mention indicator
        mention_found = False
        for item in card["body"]:
            if item.get("type") == "Container":
                for subitem in item.get("items", []):
                    if "You were mentioned" in subitem.get("text", ""):
                        mention_found = True
        assert mention_found

        # Check actions include view and reply
        action_titles = [action.get("title") for action in card["actions"]]
        assert "View Task" in action_titles
        assert "Reply" in action_titles

    def test_error_card(self):
        """Test error card creation"""
        card = AdaptiveCardTemplates.error_card(
            error_message="Failed to connect to Microsoft Planner",
            error_code="PLANNER_API_ERROR",
            suggested_action="Check your network connection and try again"
        )

        assert card["type"] == "AdaptiveCard"

        # Check error message is present
        error_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                if "Failed to connect" in text:
                    error_found = True
        assert error_found

        # Check suggested action is present
        suggestion_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                if "Check your network" in text:
                    suggestion_found = True
        assert suggestion_found

    def test_task_card_actions(self):
        """Test task card action buttons"""
        card = AdaptiveCardTemplates.task_card(
            task_id="action-test",
            title="Test Task",
            status="notStarted"
        )

        actions = card.get("actions", [])
        assert len(actions) >= 3

        action_data = [action.get("data", {}) for action in actions]
        action_types = [data.get("action") for data in action_data]

        assert "viewTask" in action_types
        assert "editTask" in action_types
        assert "completeTask" in action_types

    def test_progress_bar_in_card(self):
        """Test progress bar inclusion in task cards"""
        card = AdaptiveCardTemplates.task_card(
            task_id="progress-test",
            title="Task with Progress",
            status="inProgress",
            progress_percent=75
        )

        # Check for progress bar
        progress_found = False
        for item in card["body"]:
            if item.get("type") == "ProgressBar":
                assert item.get("value") == 75
                progress_found = True
        assert progress_found

    def test_card_version_compatibility(self):
        """Test all cards use compatible version"""
        cards = [
            AdaptiveCardTemplates.task_card("test", "Test Task"),
            AdaptiveCardTemplates.plan_summary_card("plan", "Test Plan"),
            AdaptiveCardTemplates.task_list_card([]),
            AdaptiveCardTemplates.mention_notification_card("user", "task", "id", "msg"),
            AdaptiveCardTemplates.error_card("error")
        ]

        for card in cards:
            assert card.get("version") == "1.5"
            assert card.get("type") == "AdaptiveCard"

    def test_large_checklist_truncation(self):
        """Test checklist items are properly truncated"""
        large_checklist = [
            {"title": f"Item {i}", "isChecked": False}
            for i in range(10)
        ]

        card = AdaptiveCardTemplates.task_card(
            task_id="truncate-test",
            title="Large Checklist Task",
            checklist_items=large_checklist
        )

        # Count checklist items shown (should be max 3 + "more" indicator)
        checklist_items_shown = 0
        more_indicator_found = False

        for item in card["body"]:
            if item.get("type") == "TextBlock":
                text = item.get("text", "")
                # Count individual checklist items, not the header
                if text.startswith(("✅ Item", "⬜ Item")):
                    checklist_items_shown += 1
                elif "more items" in text:
                    more_indicator_found = True

        assert checklist_items_shown <= 3
        assert more_indicator_found

    def test_empty_data_handling(self):
        """Test cards handle empty or missing data gracefully"""
        # Test with minimal data
        card = AdaptiveCardTemplates.task_card(
            task_id="",
            title=""
        )

        assert card["type"] == "AdaptiveCard"
        assert len(card["body"]) > 0

        # Test plan card with minimal data
        plan_card = AdaptiveCardTemplates.plan_summary_card(
            plan_id="",
            plan_name=""
        )

        assert plan_card["type"] == "AdaptiveCard"
        assert len(plan_card["body"]) > 0

    def test_special_characters_handling(self):
        """Test cards handle special characters properly"""
        special_title = "Task with Special Chars: @#$%^&*()_+-=[]{}|;':\",./<>?"

        card = AdaptiveCardTemplates.task_card(
            task_id="special-test",
            title=special_title,
            description="Description with unicode: 🚀 📋 ✅ ⚠️"
        )

        assert card["type"] == "AdaptiveCard"

        # Check title is preserved
        title_found = False
        for item in card["body"]:
            if item.get("type") == "Container":
                for subitem in item.get("items", []):
                    if subitem.get("type") == "ColumnSet":
                        for column in subitem.get("columns", []):
                            for column_item in column.get("items", []):
                                if special_title in column_item.get("text", ""):
                                    title_found = True
        assert title_found