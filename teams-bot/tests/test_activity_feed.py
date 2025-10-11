"""
Test suite for activity feed integration
Tests activity notifications and feed management
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import asyncio

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from activity_feed import ActivityFeedManager, ActivityType


class TestActivityFeedManager:
    """Test activity feed management functionality"""

    @pytest.fixture
    def activity_manager(self):
        """Create activity feed manager instance"""
        return ActivityFeedManager(
            graph_api_url="https://graph.microsoft.com/v1.0",
            max_retries=2,
            timeout=10.0
        )

    @pytest.mark.asyncio
    async def test_send_activity_notification_success(self, activity_manager):
        """Test successful activity notification sending"""
        with patch.object(activity_manager, '_send_to_graph_api', return_value=True) as mock_send:
            result = await activity_manager.send_activity_notification(
                activity_type=ActivityType.TASK_CREATED,
                recipient_id="user123",
                actor_id="user456",
                activity_data={
                    "taskTitle": "New Task",
                    "actorName": "Alice Johnson"
                },
                auth_token="fake_token"
            )

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_activity_notification_no_token(self, activity_manager):
        """Test activity notification without auth token"""
        result = await activity_manager.send_activity_notification(
            activity_type=ActivityType.TASK_CREATED,
            recipient_id="user123",
            actor_id="user456",
            activity_data={"taskTitle": "New Task"},
            auth_token=None
        )

        assert result is False

    def test_create_activity_payload_task_created(self, activity_manager):
        """Test activity payload creation for task created"""
        payload = activity_manager._create_activity_payload(
            activity_type=ActivityType.TASK_CREATED,
            recipient_id="user123",
            actor_id="user456",
            activity_data={
                "taskTitle": "Review Budget",
                "actorName": "Alice Johnson"
            }
        )

        assert payload["activityType"] == "taskCreated"
        assert payload["recipient"]["userId"] == "user123"
        assert "Review Budget" in payload["previewText"]["content"]

        # Check template parameters
        params = payload["templateParameters"]
        actor_param = next((p for p in params if p["name"] == "actor"), None)
        assert actor_param is not None
        assert actor_param["value"] == "Alice Johnson"

        task_param = next((p for p in params if p["name"] == "taskTitle"), None)
        assert task_param is not None
        assert task_param["value"] == "Review Budget"

    def test_create_activity_payload_with_team(self, activity_manager):
        """Test activity payload creation with team context"""
        payload = activity_manager._create_activity_payload(
            activity_type=ActivityType.TASK_ASSIGNED,
            recipient_id="user123",
            actor_id="user456",
            activity_data={"taskTitle": "Test Task"},
            team_id="team789"
        )

        assert "teams/team789" in payload["topic"]["value"]

    def test_generate_preview_text(self, activity_manager):
        """Test preview text generation for different activity types"""
        test_cases = [
            (ActivityType.TASK_CREATED, {"taskTitle": "New Task"}, "New task created: New Task"),
            (ActivityType.TASK_ASSIGNED, {"taskTitle": "Assigned Task"}, "Task assigned to you: Assigned Task"),
            (ActivityType.TASK_COMPLETED, {"taskTitle": "Done Task"}, "Task completed: Done Task"),
            (ActivityType.PLAN_CREATED, {"planName": "New Plan"}, "New plan created: New Plan"),
        ]

        for activity_type, data, expected in test_cases:
            preview = activity_manager._generate_preview_text(activity_type, data)
            assert expected in preview

    def test_create_template_parameters(self, activity_manager):
        """Test template parameter creation"""
        # Test task-related parameters
        params = activity_manager._create_template_parameters(
            ActivityType.TASK_ASSIGNED,
            {
                "taskTitle": "Review Document",
                "actorName": "Alice",
                "assigneeName": "Bob"
            },
            "user123"
        )

        param_dict = {p["name"]: p["value"] for p in params}
        assert param_dict["actor"] == "Alice"
        assert param_dict["taskTitle"] == "Review Document"
        assert param_dict["assignee"] == "Bob"

        # Test plan-related parameters
        params = activity_manager._create_template_parameters(
            ActivityType.PLAN_CREATED,
            {
                "planName": "Q2 Strategy",
                "actorName": "Charlie"
            },
            "user456"
        )

        param_dict = {p["name"]: p["value"] for p in params}
        assert param_dict["actor"] == "Charlie"
        assert param_dict["planName"] == "Q2 Strategy"

    @pytest.mark.asyncio
    async def test_send_to_graph_api_success(self, activity_manager):
        """Test successful Graph API call"""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(activity_manager.client, 'post', return_value=mock_response) as mock_post:
            payload = {"test": "data"}
            result = await activity_manager._send_to_graph_api(payload, "fake_token")

            assert result is True
            mock_post.assert_called_once()

            # Check headers
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer fake_token"
            assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_send_to_graph_api_rate_limited(self, activity_manager):
        """Test Graph API rate limiting handling"""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}

        with patch.object(activity_manager.client, 'post', return_value=mock_response):
            with patch('asyncio.sleep') as mock_sleep:
                payload = {"test": "data"}
                result = await activity_manager._send_to_graph_api(payload, "fake_token")

                assert result is False  # Should fail after retries
                mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_notify_task_created(self, activity_manager):
        """Test task creation notifications"""
        assigned_users = [
            {"id": "user1", "name": "Alice"},
            {"id": "user2", "name": "Bob"},
            {"id": "creator", "name": "Creator"}  # Should not be notified
        ]

        with patch.object(activity_manager, 'send_activity_notification', return_value=True) as mock_send:
            results = await activity_manager.notify_task_created(
                task_id="task123",
                task_title="New Task",
                plan_name="Test Plan",
                creator_id="creator",
                creator_name="Creator",
                assigned_users=assigned_users,
                auth_token="fake_token"
            )

            # Should notify 2 users (not the creator)
            assert len(results) == 2
            assert all(results)
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_notify_task_assigned(self, activity_manager):
        """Test task assignment notification"""
        with patch.object(activity_manager, 'send_activity_notification', return_value=True) as mock_send:
            result = await activity_manager.notify_task_assigned(
                task_id="task123",
                task_title="Important Task",
                assignee_id="user123",
                assignee_name="Alice",
                assigner_id="user456",
                assigner_name="Bob",
                auth_token="fake_token"
            )

            assert result is True
            mock_send.assert_called_once()

            # Check call arguments (positional arguments)
            call_args = mock_send.call_args[0]
            assert call_args[0] == ActivityType.TASK_ASSIGNED
            assert call_args[1] == "user123"
            assert call_args[2] == "user456"

    @pytest.mark.asyncio
    async def test_notify_task_completed(self, activity_manager):
        """Test task completion notifications"""
        notify_users = ["user1", "user2", "completer"]

        with patch.object(activity_manager, 'send_activity_notification', return_value=True) as mock_send:
            results = await activity_manager.notify_task_completed(
                task_id="task123",
                task_title="Completed Task",
                completer_id="completer",
                completer_name="Alice",
                notify_users=notify_users,
                auth_token="fake_token"
            )

            # Should notify 2 users (not the completer)
            assert len(results) == 2
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_notify_task_overdue(self, activity_manager):
        """Test overdue task notifications"""
        assigned_users = ["user1", "user2"]

        with patch.object(activity_manager, 'send_activity_notification', return_value=True) as mock_send:
            results = await activity_manager.notify_task_overdue(
                task_id="task123",
                task_title="Overdue Task",
                assigned_users=assigned_users,
                due_date="2024-12-01T10:00:00Z",
                auth_token="fake_token"
            )

            assert len(results) == 2
            assert all(results)
            assert mock_send.call_count == 2

            # Check system actor is used (positional arguments)
            call_args = mock_send.call_args[0]
            assert call_args[2] == "system"  # actor_id is the 3rd positional argument

    @pytest.mark.asyncio
    async def test_notify_mention_received(self, activity_manager):
        """Test mention notification"""
        with patch.object(activity_manager, 'send_activity_notification', return_value=True) as mock_send:
            result = await activity_manager.notify_mention_received(
                task_id="task123",
                task_title="Important Task",
                mentioned_user_id="user123",
                mentioner_id="user456",
                mentioner_name="Alice",
                message="Please review this task when you have time",
                auth_token="fake_token",
                channel_id="channel789"
            )

            assert result is True
            mock_send.assert_called_once()

            # Check activity data includes truncated message (positional arguments)
            call_args = mock_send.call_args[0]
            activity_data = call_args[3]  # activity_data is the 4th positional argument
            assert len(activity_data["message"]) <= 103  # 100 chars + "..."

    @pytest.mark.asyncio
    async def test_create_activity_summary_card(self, activity_manager):
        """Test activity summary card creation"""
        with patch.object(activity_manager, '_fetch_user_activities') as mock_fetch:
            mock_fetch.return_value = [
                {"type": "taskCreated", "description": "Created task"},
                {"type": "taskCompleted", "description": "Completed task"}
            ]

            card = await activity_manager.create_activity_summary_card(
                user_id="user123",
                time_period="today",
                auth_token="fake_token"
            )

            assert card["type"] == "AdaptiveCard"
            assert len(card["body"]) > 0
            assert len(card["actions"]) > 0

            # Check for statistics
            facts_found = False
            for item in card["body"]:
                if item.get("type") == "FactSet":
                    facts = item.get("facts", [])
                    fact_titles = [f["title"] for f in facts]
                    if "Tasks Created:" in fact_titles:
                        facts_found = True
            assert facts_found

    def test_calculate_activity_stats(self, activity_manager):
        """Test activity statistics calculation"""
        activities = [
            {"type": "taskCreated"},
            {"type": "taskCompleted"},
            {"type": "taskCreated"},
            {"type": "mentionReceived"},
            {"type": "unknown"}  # Should be ignored
        ]

        stats = activity_manager._calculate_activity_stats(activities)

        assert stats["tasks_created"] == 2
        assert stats["tasks_completed"] == 1
        assert stats["mentions_received"] == 1
        assert stats["tasks_assigned"] == 0

    @pytest.mark.asyncio
    async def test_batch_send_notifications(self, activity_manager):
        """Test batch notification sending"""
        notifications = [
            {
                "activity_type": "taskCreated",
                "recipient_id": "user1",
                "actor_id": "user2",
                "activity_data": {"taskTitle": "Task 1"}
            },
            {
                "activity_type": "taskAssigned",
                "recipient_id": "user3",
                "actor_id": "user4",
                "activity_data": {"taskTitle": "Task 2"}
            }
        ]

        with patch.object(activity_manager, 'send_activity_notification') as mock_send:
            mock_send.side_effect = [True, False]  # First succeeds, second fails

            results = await activity_manager.batch_send_notifications(
                notifications, "fake_token"
            )

            assert results["total"] == 2
            assert results["succeeded"] == 1
            assert results["failed"] == 1
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_send_with_concurrency_limit(self, activity_manager):
        """Test batch sending respects concurrency limits"""
        # Create many notifications to test semaphore
        notifications = [
            {
                "activity_type": "taskCreated",
                "recipient_id": f"user{i}",
                "actor_id": "creator",
                "activity_data": {"taskTitle": f"Task {i}"}
            }
            for i in range(15)  # More than semaphore limit
        ]

        call_count = 0

        async def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate API call time
            return True

        with patch.object(activity_manager, 'send_activity_notification', side_effect=mock_send):
            results = await activity_manager.batch_send_notifications(
                notifications, "fake_token"
            )

            assert results["total"] == 15
            assert results["succeeded"] == 15
            assert call_count == 15

    @pytest.mark.asyncio
    async def test_error_handling_in_notifications(self, activity_manager):
        """Test error handling in notification sending"""
        with patch.object(activity_manager, '_send_to_graph_api', side_effect=Exception("API Error")):
            result = await activity_manager.send_activity_notification(
                activity_type=ActivityType.TASK_CREATED,
                recipient_id="user123",
                actor_id="user456",
                activity_data={"taskTitle": "Test Task"},
                auth_token="fake_token"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_client_cleanup(self, activity_manager):
        """Test HTTP client cleanup"""
        # Mock the client
        activity_manager.client = AsyncMock()

        await activity_manager.close()

        activity_manager.client.aclose.assert_called_once()

    def test_activity_type_enum_coverage(self):
        """Test all activity types are properly defined"""
        expected_types = [
            "taskCreated", "taskAssigned", "taskCompleted", "taskOverdue",
            "taskUpdated", "planCreated", "planUpdated", "mentionReceived",
            "commentAdded"
        ]

        enum_values = [activity_type.value for activity_type in ActivityType]

        for expected in expected_types:
            assert expected in enum_values

    @pytest.mark.asyncio
    async def test_network_timeout_handling(self, activity_manager):
        """Test network timeout handling"""
        with patch.object(activity_manager.client, 'post', side_effect=asyncio.TimeoutError()):
            payload = {"test": "data"}
            result = await activity_manager._send_to_graph_api(payload, "fake_token")

            assert result is False

    def test_preview_text_with_missing_data(self, activity_manager):
        """Test preview text generation with missing data"""
        # Test with minimal data
        preview = activity_manager._generate_preview_text(
            ActivityType.TASK_CREATED, {}
        )

        assert "New task created: a task" in preview

        # Test with partial data
        preview = activity_manager._generate_preview_text(
            ActivityType.TASK_ASSIGNED, {"actorName": "Alice"}
        )

        assert "Task assigned to you: a task" in preview