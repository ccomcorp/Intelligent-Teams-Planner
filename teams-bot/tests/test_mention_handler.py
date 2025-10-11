"""
Test suite for mention handler functionality
Tests mention detection, processing, and notifications
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from botbuilder.core import TurnContext, MessageFactory
from botbuilder.schema import Activity, ActivityTypes, Mention, ChannelAccount

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mention_handler import MentionHandler


class TestMentionHandler:
    """Test mention processing functionality"""

    @pytest.fixture
    def mock_openwebui_client(self):
        """Mock OpenWebUI client"""
        client = AsyncMock()
        return client

    @pytest.fixture
    def mock_context_manager(self):
        """Mock conversation context manager"""
        manager = AsyncMock()
        return manager

    @pytest.fixture
    def mention_handler(self, mock_openwebui_client, mock_context_manager):
        """Create mention handler instance"""
        return MentionHandler(mock_openwebui_client, mock_context_manager)

    @pytest.fixture
    def mock_turn_context(self):
        """Create mock turn context"""
        activity = Activity(
            type=ActivityTypes.message,
            text="Hello @john please review this task",
            from_property=ChannelAccount(id="user123", name="Alice"),
            conversation=ChannelAccount(id="conv456"),
            recipient=ChannelAccount(id="bot789", name="Intelligent Planner")
        )

        turn_context = MagicMock()
        turn_context.activity = activity
        return turn_context

    def test_extract_activity_mentions(self, mention_handler, mock_turn_context):
        """Test extraction of mentions from activity entities"""
        # Create mock mention entity
        mention_entity = MagicMock()
        mention_entity.type = "mention"
        mention_entity.text = "<at>John Smith</at>"
        mention_entity.mentioned = MagicMock()
        mention_entity.mentioned.id = "john.smith@company.com"
        mention_entity.mentioned.name = "John Smith"

        mock_turn_context.activity.entities = [mention_entity]

        mentions = mention_handler._extract_activity_mentions(mock_turn_context.activity)

        assert len(mentions) == 1
        assert mentions[0]["id"] == "john.smith@company.com"
        assert mentions[0]["name"] == "John Smith"
        assert mentions[0]["text"] == "John Smith"  # Cleaned up
        assert mentions[0]["source"] == "activity_entity"

    def test_parse_text_mentions(self, mention_handler):
        """Test parsing mentions from text using regex"""
        text = "Please @john and @jane.doe review this. Also notify @everyone"

        mentions = mention_handler._parse_text_mentions(text)

        assert len(mentions) >= 3

        mention_names = [m["name"] for m in mentions]
        assert "john" in mention_names
        assert "jane.doe" in mention_names
        assert "everyone" in mention_names

        # Check source is marked correctly
        for mention in mentions:
            assert mention["source"] == "text_parsing"

    def test_merge_mentions_deduplication(self, mention_handler):
        """Test merging and deduplication of mentions"""
        activity_mentions = [
            {
                "id": "john@company.com",
                "name": "John Smith",
                "text": "John Smith",
                "source": "activity_entity"
            }
        ]

        text_mentions = [
            {
                "id": None,
                "name": "john",
                "text": "@john",
                "source": "text_parsing"
            },
            {
                "id": None,
                "name": "Jane",
                "text": "@Jane",
                "source": "text_parsing"
            }
        ]

        merged = mention_handler._merge_mentions(activity_mentions, text_mentions)

        # Should prioritize activity mention for john, add jane
        # Note: "john" will be considered similar to "John Smith" and deduplicated
        assert len(merged) == 2

        john_mention = next((m for m in merged if "john" in m["name"].lower()), None)
        assert john_mention is not None
        assert john_mention["source"] == "activity_entity"

        jane_mention = next((m for m in merged if m["name"].lower() == "jane"), None)
        assert jane_mention is not None
        assert jane_mention["source"] == "text_parsing"

    @pytest.mark.asyncio
    async def test_process_mentions_full_workflow(self, mention_handler, mock_turn_context):
        """Test full mention processing workflow"""
        # Set up mock activity with mention
        mention_entity = MagicMock()
        mention_entity.type = "mention"
        mention_entity.text = "<at>John Smith</at>"
        mention_entity.mentioned = MagicMock()
        mention_entity.mentioned.id = "john@company.com"
        mention_entity.mentioned.name = "John Smith"

        mock_turn_context.activity.entities = [mention_entity]
        mock_turn_context.activity.text = "Hello <at>John Smith</at> please review this task"

        message_content = {
            "text": "Hello <at>John Smith</at> please review this task",
            "mentions": [],
            "attachments": []
        }

        # Process mentions
        enhanced_content = await mention_handler.process_mentions(
            mock_turn_context, message_content
        )

        assert enhanced_content["mention_count"] == 1
        assert len(enhanced_content["mentions"]) == 1
        assert enhanced_content["mentions"][0]["name"] == "John Smith"
        assert enhanced_content["mentions"][0]["id"] == "john@company.com"
        assert "formatted_text" in enhanced_content
        assert "@John Smith" in enhanced_content["formatted_text"]

    def test_determine_mention_type(self, mention_handler):
        """Test mention type determination"""
        # Test user mention
        user_mention = {
            "id": "user123",
            "name": "John Smith",
            "source": "activity_entity"
        }
        assert mention_handler._determine_mention_type(user_mention) == "teams_mention"

        # Test group mention
        group_mention = {
            "name": "everyone",
            "source": "text_parsing"
        }
        assert mention_handler._determine_mention_type(group_mention) == "group_mention"

        # Test text mention
        text_mention = {
            "name": "someone",
            "source": "text_parsing"
        }
        assert mention_handler._determine_mention_type(text_mention) == "text_mention"

    def test_should_notify_user(self, mention_handler):
        """Test notification decision logic"""
        # Should notify for user mentions
        user_mention = {"mention_type": "user_mention"}
        assert mention_handler._should_notify_user(user_mention) is True

        # Should notify for Teams mentions
        teams_mention = {"mention_type": "teams_mention"}
        assert mention_handler._should_notify_user(teams_mention) is True

        # Should not notify for group mentions
        group_mention = {"mention_type": "group_mention"}
        assert mention_handler._should_notify_user(group_mention) is False

        # Should not notify for text mentions by default
        text_mention = {"mention_type": "text_mention"}
        assert mention_handler._should_notify_user(text_mention) is False

    def test_is_bot_mentioned(self, mention_handler, mock_turn_context):
        """Test bot mention detection"""
        # Test mention by ID
        mentions = [{"id": "bot789", "name": "Someone"}]
        assert mention_handler._is_bot_mentioned(mentions, mock_turn_context) is True

        # Test mention by name (partial match)
        mentions = [{"id": "other", "name": "planner"}]
        assert mention_handler._is_bot_mentioned(mentions, mock_turn_context) is True

        # Test no bot mention
        mentions = [{"id": "user123", "name": "John"}]
        assert mention_handler._is_bot_mentioned(mentions, mock_turn_context) is False

    def test_generate_mention_summary(self, mention_handler):
        """Test mention summary generation"""
        mentions = [
            {"mention_type": "user_mention", "name": "John"},
            {"mention_type": "teams_mention", "name": "Jane"},
            {"mention_type": "group_mention", "name": "everyone"}
        ]

        summary = mention_handler._generate_mention_summary(mentions)

        assert "Users: John, Jane" in summary
        assert "Groups: everyone" in summary

    def test_format_text_with_mentions(self, mention_handler):
        """Test text formatting with mentions"""
        text = "Hello <at>John Smith</at> and @jane please review"
        mentions = [
            {
                "text": "<at>John Smith</at>",
                "name": "John Smith",
                "source": "activity_entity"
            },
            {
                "text": "@jane",
                "name": "jane",
                "source": "text_parsing",
                "start_index": 26,
                "end_index": 31
            }
        ]

        formatted = mention_handler._format_text_with_mentions(text, mentions)

        assert "@John Smith" in formatted
        assert "@jane" in formatted
        assert "<at>" not in formatted

    @pytest.mark.asyncio
    async def test_send_mention_notification(self, mention_handler, mock_turn_context):
        """Test sending mention notifications"""
        with patch.object(mention_handler, 'openwebui_client'):
            result = await mention_handler.send_mention_notification(
                mentioned_user_id="user123",
                mentioned_by="Alice",
                task_title="Review Proposal",
                task_id="task456",
                message="Please review this proposal",
                turn_context=mock_turn_context
            )

            # Should return True for successful notification preparation
            assert result is True

    @pytest.mark.asyncio
    async def test_handle_mention_actions(self, mention_handler, mock_turn_context):
        """Test handling of mention-related actions"""
        # Test view task action
        action_data = {"action": "viewTask", "taskId": "task123"}

        response = await mention_handler.handle_mention_actions(
            action_data, mock_turn_context
        )

        assert response is not None
        assert "task123" in response.text

        # Test reply action
        action_data = {
            "action": "replyToMention",
            "taskId": "task123",
            "mentionedBy": "Alice"
        }

        response = await mention_handler.handle_mention_actions(
            action_data, mock_turn_context
        )

        assert response is not None
        assert "Alice" in response.text

        # Test help action
        action_data = {"action": "getHelp"}

        response = await mention_handler.handle_mention_actions(
            action_data, mock_turn_context
        )

        assert response is not None
        assert "help" in response.text.lower()

    def test_extract_task_context_from_mentions(self, mention_handler):
        """Test task context extraction from mentions"""
        mentions = [
            {
                "mention_type": "user_mention",
                "id": "user123",
                "name": "John",
                "should_notify": True
            }
        ]

        message_text = "Please assign this task to @john and set priority to high"

        context = mention_handler.extract_task_context_from_mentions(mentions, message_text)

        assert context["has_task_reference"] is True
        assert context["has_task_assignment"] is True
        assert len(context["mentioned_users"]) == 1
        assert context["mentioned_users"][0]["name"] == "John"
        assert "task" in context["task_keywords"]
        assert "assign" in context["action_keywords"]

    def test_mention_patterns_coverage(self, mention_handler):
        """Test mention patterns cover various formats"""
        test_cases = [
            "@username",
            "@user.name",
            "@user_name",
            "<at>John Smith</at>",
            "@[Display Name]"
        ]

        for test_text in test_cases:
            mentions = mention_handler._parse_text_mentions(test_text)
            assert len(mentions) >= 1, f"Failed to parse: {test_text}"

    def test_error_handling_in_processing(self, mention_handler, mock_turn_context):
        """Test error handling in mention processing"""
        # Create invalid activity that should cause errors
        mock_turn_context.activity.entities = None
        mock_turn_context.activity.text = None

        message_content = {"text": None, "mentions": [], "attachments": []}

        # Should not raise exception, should return original content
        try:
            # This would be async in real usage
            mentions = mention_handler._extract_activity_mentions(mock_turn_context.activity)
            assert mentions == []
        except Exception:
            pytest.fail("Error handling failed in mention processing")

    def test_mention_deduplication_edge_cases(self, mention_handler):
        """Test edge cases in mention deduplication"""
        # Test case-insensitive deduplication
        activity_mentions = [
            {"name": "John Smith", "id": "john@company.com", "source": "activity_entity"}
        ]

        text_mentions = [
            {"name": "john smith", "source": "text_parsing"},
            {"name": "JOHN SMITH", "source": "text_parsing"}
        ]

        merged = mention_handler._merge_mentions(activity_mentions, text_mentions)

        # Should only have one John Smith mention
        assert len(merged) == 1
        assert merged[0]["source"] == "activity_entity"

    def test_large_mention_list_handling(self, mention_handler):
        """Test handling of large numbers of mentions"""
        # Create many mentions
        large_mention_text = " ".join([f"@user{i}" for i in range(50)])

        mentions = mention_handler._parse_text_mentions(large_mention_text)

        # Should handle all mentions
        assert len(mentions) == 50

        # Test summary generation with many mentions
        processed_mentions = [
            {"mention_type": "user_mention", "name": f"user{i}"}
            for i in range(50)
        ]

        summary = mention_handler._generate_mention_summary(processed_mentions)

        # Should create a reasonable summary
        assert len(summary) > 0
        assert "Users:" in summary