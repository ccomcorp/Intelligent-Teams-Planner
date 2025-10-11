"""
Integration tests for Teams Bot enhancements
Tests the integration of adaptive cards, mentions, and activity feed
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime, timezone
from botbuilder.core import TurnContext, MessageFactory
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import TeamsBot, OpenWebUIClient, ConversationContextManager
from mention_handler import MentionHandler
from activity_feed import ActivityFeedManager
from attachment_handler import TeamsAttachmentHandler


class TestTeamsIntegration:
    """Integration tests for enhanced Teams Bot functionality"""

    @pytest.fixture
    def mock_openwebui_client(self):
        """Mock OpenWebUI client"""
        client = AsyncMock(spec=OpenWebUIClient)
        client.send_message = AsyncMock(return_value={
            "success": True,
            "content": "Task created successfully: Review Q4 Budget\n\n**Details:**\n- Priority: High\n- Due: January 15, 2025\n- Assigned to: @alice",
            "conversation_id": "conv123"
        })
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_context_manager(self):
        """Mock conversation context manager"""
        manager = AsyncMock(spec=ConversationContextManager)
        manager.get_context = AsyncMock(return_value=None)
        manager.update_context = AsyncMock()
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def mock_attachment_handler(self):
        """Mock attachment handler"""
        handler = AsyncMock(spec=TeamsAttachmentHandler)
        handler.process_attachments = AsyncMock(return_value=[])
        handler.format_attachment_response = AsyncMock(return_value="")
        handler.close = AsyncMock()
        return handler

    @pytest.fixture
    def mock_mention_handler(self):
        """Mock mention handler"""
        handler = AsyncMock(spec=MentionHandler)
        handler.process_mentions = AsyncMock()
        handler.extract_task_context_from_mentions = AsyncMock(return_value={
            "has_task_assignment": True,
            "mentioned_users": [{"id": "alice@company.com", "name": "Alice"}]
        })
        handler.handle_mention_actions = AsyncMock()
        return handler

    @pytest.fixture
    def mock_activity_feed_manager(self):
        """Mock activity feed manager"""
        manager = AsyncMock(spec=ActivityFeedManager)
        manager.notify_mention_received = AsyncMock(return_value=True)
        manager.create_activity_summary_card = AsyncMock()
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def teams_bot(
        self,
        mock_openwebui_client,
        mock_context_manager,
        mock_attachment_handler,
        mock_mention_handler,
        mock_activity_feed_manager
    ):
        """Create Teams bot instance with mocked dependencies"""
        return TeamsBot(
            openwebui_client=mock_openwebui_client,
            context_manager=mock_context_manager,
            attachment_handler=mock_attachment_handler,
            mention_handler=mock_mention_handler,
            activity_feed_manager=mock_activity_feed_manager
        )

    @pytest.fixture
    def mock_turn_context(self):
        """Create mock turn context with mention"""
        activity = Activity(
            type=ActivityTypes.message,
            text="Please @alice review the budget proposal and set priority to high",
            from_property=ChannelAccount(id="user123", name="Bob"),
            conversation=ChannelAccount(id="conv456"),
            recipient=ChannelAccount(id="bot789", name="Intelligent Planner")
        )

        # Add mention entity
        mention_entity = MagicMock()
        mention_entity.type = "mention"
        mention_entity.text = "<at>Alice Johnson</at>"
        mention_entity.mentioned = MagicMock()
        mention_entity.mentioned.id = "alice@company.com"
        mention_entity.mentioned.name = "Alice Johnson"
        activity.entities = [mention_entity]

        turn_context = MagicMock(spec=TurnContext)
        turn_context.activity = activity
        turn_context.send_activity = AsyncMock()
        return turn_context

    @pytest.mark.asyncio
    async def test_enhanced_message_processing(
        self,
        teams_bot,
        mock_turn_context,
        mock_mention_handler
    ):
        """Test enhanced message processing with mentions"""
        # Setup mention handler mock
        mock_mention_handler.process_mentions.return_value = {
            "text": "Please @alice review the budget proposal",
            "formatted_text": "Please @Alice Johnson review the budget proposal",
            "mentions": [{
                "id": "alice@company.com",
                "name": "Alice Johnson",
                "should_notify": True,
                "mention_type": "user_mention"
            }],
            "mention_count": 1,
            "bot_mentioned": False,
            "mention_summary": "Users: Alice Johnson"
        }

        await teams_bot.on_message_activity(mock_turn_context)

        # Verify mention processing was called
        mock_mention_handler.process_mentions.assert_called_once()

        # Verify OpenWebUI was called with enhanced content
        teams_bot.openwebui_client.send_message.assert_called_once()
        call_args = teams_bot.openwebui_client.send_message.call_args[1]
        message_content = call_args["message_content"]
        assert "formatted_text" in message_content
        assert len(message_content["mentions"]) == 1

    @pytest.mark.asyncio
    async def test_adaptive_card_response(
        self,
        teams_bot,
        mock_turn_context,
        mock_mention_handler
    ):
        """Test adaptive card response for structured content"""
        # Setup mention handler to indicate bot was mentioned
        mock_mention_handler.process_mentions.return_value = {
            "text": "@bot show me my tasks",
            "formatted_text": "@Intelligent Planner show me my tasks",
            "mentions": [{
                "id": "bot789",
                "name": "Intelligent Planner",
                "mention_type": "teams_mention"
            }],
            "mention_count": 1,
            "bot_mentioned": True,
            "mention_summary": "Bot mentioned"
        }

        # Setup OpenWebUI to return structured response
        teams_bot.openwebui_client.send_message.return_value = {
            "success": True,
            "content": "**Your Tasks:**\n\n- Review budget proposal (High priority)\n- Update project timeline (Medium priority)\n- Prepare presentation (Low priority)",
            "conversation_id": "conv123"
        }

        await teams_bot.on_message_activity(mock_turn_context)

        # Verify response was sent
        mock_turn_context.send_activity.assert_called()

        # Check if adaptive card was used (would be attachment in real scenario)
        call_args = mock_turn_context.send_activity.call_args[0]
        response_activity = call_args[0]

        # Verify response contains the content
        assert response_activity.text is not None or response_activity.attachments is not None

    @pytest.mark.asyncio
    async def test_mention_notifications_sent(
        self,
        teams_bot,
        mock_turn_context,
        mock_mention_handler,
        mock_activity_feed_manager
    ):
        """Test mention notifications are sent to activity feed"""
        # Setup mention handler
        mock_mention_handler.process_mentions.return_value = {
            "text": "Please @alice review this task",
            "mentions": [{
                "id": "alice@company.com",
                "name": "Alice Johnson",
                "should_notify": True,
                "mention_type": "user_mention"
            }],
            "mention_count": 1,
            "bot_mentioned": False
        }

        await teams_bot.on_message_activity(mock_turn_context)

        # Verify mention notification was sent
        mock_activity_feed_manager.notify_mention_received.assert_called_once()

        call_args = mock_activity_feed_manager.notify_mention_received.call_args[1]
        assert call_args["mentioned_user_id"] == "alice@company.com"
        assert call_args["mentioner_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_adaptive_card_action_handling(
        self,
        teams_bot,
        mock_mention_handler
    ):
        """Test handling of adaptive card actions"""
        # Create mock invoke activity
        invoke_activity = Activity(
            type=ActivityTypes.invoke,
            value={
                "action": "viewTask",
                "taskId": "task123"
            }
        )

        turn_context = MagicMock()
        turn_context.activity = invoke_activity
        turn_context.send_activity = AsyncMock()

        # Setup mention handler response
        mock_mention_handler.handle_mention_actions.return_value = MessageFactory.text(
            "Viewing task details for task ID: task123"
        )

        await teams_bot.on_message_activity_invoke(turn_context)

        # Verify mention handler was called
        mock_mention_handler.handle_mention_actions.assert_called_once()

        # Verify response was sent
        turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_activity_summary_card_action(
        self,
        teams_bot,
        mock_activity_feed_manager
    ):
        """Test activity summary card generation from action"""
        # Create mock invoke activity for activity summary
        invoke_activity = Activity(
            type=ActivityTypes.invoke,
            value={
                "action": "viewAllActivities",
                "userId": "user123",
                "timePeriod": "today"
            },
            from_property=ChannelAccount(id="user123")
        )

        turn_context = MagicMock()
        turn_context.activity = invoke_activity
        turn_context.send_activity = AsyncMock()

        # Setup activity feed manager response
        mock_activity_feed_manager.create_activity_summary_card.return_value = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Activity Summary - Today"
                }
            ]
        }

        # Mock token extraction
        with patch.object(teams_bot, '_extract_teams_token', return_value="fake_token"):
            await teams_bot.on_message_activity_invoke(turn_context)

        # Verify activity summary was created
        mock_activity_feed_manager.create_activity_summary_card.assert_called_once_with(
            "user123", "today", "fake_token"
        )

        # Verify card was sent
        turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_in_enhanced_processing(
        self,
        teams_bot,
        mock_turn_context,
        mock_mention_handler
    ):
        """Test error handling in enhanced message processing"""
        # Make mention handler raise an exception
        mock_mention_handler.process_mentions.side_effect = Exception("Mention processing error")

        # Should not raise exception, should fall back gracefully
        await teams_bot.on_message_activity(mock_turn_context)

        # Verify some response was sent
        mock_turn_context.send_activity.assert_called()

    @pytest.mark.asyncio
    async def test_special_commands_still_work(
        self,
        teams_bot,
        mock_mention_handler
    ):
        """Test that special commands still work with enhancements"""
        # Create help command activity
        help_activity = Activity(
            type=ActivityTypes.message,
            text="/help",
            from_property=ChannelAccount(id="user123"),
            conversation=ChannelAccount(id="conv456")
        )

        turn_context = MagicMock()
        turn_context.activity = help_activity
        turn_context.send_activity = AsyncMock()

        # Setup mention handler to return minimal processing
        mock_mention_handler.process_mentions.return_value = {
            "text": "/help",
            "mentions": [],
            "mention_count": 0,
            "bot_mentioned": False
        }

        await teams_bot.on_message_activity(turn_context)

        # Verify help message was sent
        turn_context.send_activity.assert_called_once()
        call_args = turn_context.send_activity.call_args[0]
        response_text = call_args[0].text
        assert "Help" in response_text

    @pytest.mark.asyncio
    async def test_card_decision_logic(self, teams_bot):
        """Test adaptive card usage decision logic"""
        # Test bot mentioned - should use card
        message_content = {"bot_mentioned": True}
        response = "Simple response"
        assert teams_bot._should_use_adaptive_card(message_content, response) is True

        # Test task keywords - should use card
        message_content = {"bot_mentioned": False}
        response = "Created new task for you"
        assert teams_bot._should_use_adaptive_card(message_content, response) is True

        # Test structured content - should use card
        message_content = {"bot_mentioned": False}
        response = "**Tasks:**\n- Task 1\n- Task 2"
        assert teams_bot._should_use_adaptive_card(message_content, response) is True

        # Test simple content - should not use card
        message_content = {"bot_mentioned": False}
        response = "Hello there"
        assert teams_bot._should_use_adaptive_card(message_content, response) is False

    def test_card_data_extraction(self, teams_bot):
        """Test extraction of card data from response"""
        response = """**Task Created Successfully**

        Title: Review Budget Proposal
        Priority: High
        Due Date: January 15, 2025

        **Next Steps:**
        - Review document
        - Prepare feedback
        - Schedule meeting"""

        card_data = teams_bot._extract_card_data_from_response(response)

        assert card_data is not None
        assert card_data["type"] == "task_response"
        assert len(card_data["facts"]) > 0
        assert len(card_data["list_items"]) == 3

    def test_response_card_creation(self, teams_bot):
        """Test creation of response cards"""
        card_data = {
            "type": "task_response",
            "content": "Task created successfully",
            "facts": [
                {"title": "Priority", "value": "High"},
                {"title": "Due Date", "value": "January 15"}
            ],
            "list_items": ["Review document", "Prepare feedback"]
        }

        message_content = {"bot_mentioned": True}

        card = teams_bot._create_response_card(card_data, message_content)

        assert card is not None
        assert card["type"] == "AdaptiveCard"
        assert len(card["body"]) > 0
        assert len(card["actions"]) > 0

        # Check for header since bot was mentioned
        header_found = False
        for item in card["body"]:
            if item.get("type") == "TextBlock" and "Intelligent Planner Response" in item.get("text", ""):
                header_found = True
        assert header_found

    @pytest.mark.asyncio
    async def test_full_integration_workflow(
        self,
        teams_bot,
        mock_turn_context,
        mock_mention_handler,
        mock_activity_feed_manager
    ):
        """Test complete integration workflow"""
        # Setup comprehensive mention processing
        mock_mention_handler.process_mentions.return_value = {
            "text": "@bot create task for @alice: Review budget proposal",
            "formatted_text": "@Intelligent Planner create task for @Alice Johnson: Review budget proposal",
            "mentions": [
                {
                    "id": "bot789",
                    "name": "Intelligent Planner",
                    "mention_type": "teams_mention",
                    "should_notify": False
                },
                {
                    "id": "alice@company.com",
                    "name": "Alice Johnson",
                    "mention_type": "user_mention",
                    "should_notify": True
                }
            ],
            "mention_count": 2,
            "bot_mentioned": True,
            "mention_summary": "Bot and Alice mentioned"
        }

        # Setup structured OpenWebUI response
        teams_bot.openwebui_client.send_message.return_value = {
            "success": True,
            "content": "**Task Created Successfully**\n\nTitle: Review Budget Proposal\nAssigned to: @Alice Johnson\nPriority: High\nDue: January 15, 2025",
            "conversation_id": "conv123"
        }

        await teams_bot.on_message_activity(mock_turn_context)

        # Verify all components were called
        mock_mention_handler.process_mentions.assert_called_once()
        teams_bot.openwebui_client.send_message.assert_called_once()
        mock_activity_feed_manager.notify_mention_received.assert_called_once()

        # Verify response was sent (either as text or card)
        mock_turn_context.send_activity.assert_called()

    @pytest.mark.asyncio
    async def test_conversation_context_integration(
        self,
        teams_bot,
        mock_turn_context,
        mock_context_manager
    ):
        """Test conversation context integration with enhancements"""
        # Setup existing context
        mock_context_manager.get_context.return_value = {
            "openwebui_conversation_id": "existing_conv",
            "messages": []
        }

        await teams_bot.on_message_activity(mock_turn_context)

        # Verify context was retrieved and updated
        mock_context_manager.get_context.assert_called_once()
        mock_context_manager.update_context.assert_called_once()

        # Verify OpenWebUI was called with existing conversation ID
        call_args = teams_bot.openwebui_client.send_message.call_args[1]
        assert call_args["conversation_id"] == "existing_conv"