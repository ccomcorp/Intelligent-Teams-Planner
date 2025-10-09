"""
Comprehensive Tests for Story 1.1: Teams Bot Message Forwarding
Validates all 8 acceptance criteria with real test scenarios
Following @CLAUDE.md testing standards
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from botbuilder.core import TurnContext, MessageFactory
from botbuilder.schema import Activity, ActivityTypes, ChannelAccount, Entity, Mention

# Import classes under test
from src.main import TeamsBot, OpenWebUIClient, ConversationContextManager


class TestAcceptanceCriteria:
    """Test all 8 acceptance criteria from Story 1.1"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for testing"""
        redis_mock = Mock()
        redis_mock.ping = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.close = AsyncMock()
        return redis_mock

    @pytest.fixture
    def context_manager(self, mock_redis):
        """ConversationContextManager with mocked Redis"""
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            manager = ConversationContextManager("redis://test:6379", ttl=3600)
            manager.redis_client = mock_redis
            return manager

    @pytest.fixture
    def mock_openwebui_client(self):
        """Mock OpenWebUI client"""
        client = Mock(spec=OpenWebUIClient)
        client.send_message = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_attachment_handler(self):
        """Mock attachment handler"""
        from src.attachment_handler import TeamsAttachmentHandler
        handler = Mock(spec=TeamsAttachmentHandler)
        handler.process_attachments = AsyncMock()
        handler.format_attachment_response = Mock(return_value="")
        handler.close = AsyncMock()
        return handler

    @pytest.fixture
    def teams_bot(self, mock_openwebui_client, context_manager, mock_attachment_handler):
        """TeamsBot instance with mocked dependencies"""
        return TeamsBot(mock_openwebui_client, context_manager, mock_attachment_handler)

    @pytest.fixture
    def mock_turn_context_basic(self):
        """Basic mock TurnContext for Teams messages"""
        activity = Activity(
            type=ActivityTypes.message,
            text="Create a new project plan for Q4 marketing",
            from_property=ChannelAccount(id="user@contoso.com", name="John Smith"),
            conversation=Mock(id="19:meeting_abc123"),
            channel_data={"authToken": "mock-teams-token-12345"}
        )
        context = Mock(spec=TurnContext)
        context.activity = activity
        context.send_activity = AsyncMock()
        context.adapter = Mock()
        context.adapter.request = Mock()
        context.adapter.request.headers = {"Authorization": "Bearer mock-teams-token-12345"}
        return context

    @pytest.fixture
    def mock_turn_context_with_mentions(self):
        """TurnContext with mentions and attachments"""
        # Create mention entity with proper Bot Framework structure
        mention_entity = Mock()
        mention_entity.type = "mention"
        mention_entity.mentioned = Mock()
        mention_entity.mentioned.id = "user2@contoso.com"
        mention_entity.mentioned.name = "Sarah Johnson"
        mention_entity.text = "@Sarah Johnson"

        # Create attachment with proper Bot Framework structure
        attachment = Mock()
        attachment.name = "project_proposal.pdf"
        attachment.content_type = "application/pdf"
        attachment.content_url = "https://teams.microsoft.com/attachments/abc123"
        attachment.thumbnail_url = None

        activity = Activity(
            type=ActivityTypes.message,
            text="@Sarah Johnson can you review this task proposal?",
            from_property=ChannelAccount(id="user@contoso.com", name="John Smith"),
            conversation=Mock(id="19:meeting_abc123"),
            entities=[mention_entity],
            attachments=[attachment]
        )

        context = Mock(spec=TurnContext)
        context.activity = activity
        context.send_activity = AsyncMock()
        context.adapter = Mock()
        context.adapter.request = Mock()
        context.adapter.request.headers = {"Authorization": "Bearer mock-teams-token-12345"}
        return context

    # AC1: Teams Bot receives messages from Teams client through Bot Framework
    @pytest.mark.asyncio
    async def test_ac1_teams_bot_receives_messages(self, teams_bot, mock_turn_context_basic, mock_openwebui_client):
        """AC1: Teams Bot receives messages through Bot Framework"""
        # Arrange
        mock_openwebui_client.send_message.return_value = {
            "success": True,
            "content": "I'll help you create a Q4 marketing project plan.",
            "conversation_id": "conv-123"
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_basic)

        # Assert
        mock_openwebui_client.send_message.assert_called_once()
        call_args = mock_openwebui_client.send_message.call_args
        assert call_args[1]["user_id"] == "user@contoso.com"
        assert "Create a new project plan for Q4 marketing" in str(call_args)

    # AC2: Messages are forwarded to OpenWebUI API endpoint
    @pytest.mark.asyncio
    async def test_ac2_messages_forwarded_to_openwebui(self, teams_bot, mock_turn_context_basic, mock_openwebui_client):
        """AC2: Messages forwarded to OpenWebUI API endpoint"""
        # Arrange
        mock_openwebui_client.send_message.return_value = {
            "success": True,
            "content": "Response from OpenWebUI",
            "conversation_id": "conv-456"
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_basic)

        # Assert - Verify OpenWebUI client called with correct parameters
        mock_openwebui_client.send_message.assert_called_once()
        call_kwargs = mock_openwebui_client.send_message.call_args[1]

        # Check message content structure
        assert "message_content" in call_kwargs
        message_content = call_kwargs["message_content"]
        assert message_content["text"] == "Create a new project plan for Q4 marketing"
        assert "user_id" in call_kwargs
        assert "auth_token" in call_kwargs

    # AC3: OpenWebUI responses are returned to Teams user with proper formatting
    @pytest.mark.asyncio
    async def test_ac3_openwebui_responses_returned_properly(self, teams_bot, mock_turn_context_basic, mock_openwebui_client):
        """AC3: OpenWebUI responses returned with proper formatting"""
        # Arrange
        expected_response = "I've created a Q4 marketing project plan with the following tasks:\n1. Market research\n2. Campaign design\n3. Launch strategy"
        mock_openwebui_client.send_message.return_value = {
            "success": True,
            "content": expected_response,
            "conversation_id": "conv-789"
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_basic)

        # Assert - Verify response sent to Teams
        assert mock_turn_context_basic.send_activity.call_count >= 2  # typing indicator + response

        # Find the actual response message (not typing indicator)
        response_calls = [call for call in mock_turn_context_basic.send_activity.call_args_list
                         if call[0][0].text == expected_response]
        assert len(response_calls) == 1

    # AC4: Message formatting preserved during forwarding (mentions, attachments)
    @pytest.mark.asyncio
    async def test_ac4_message_formatting_preserved(self, teams_bot, mock_turn_context_with_mentions, mock_openwebui_client):
        """AC4: Message formatting preserved (mentions, attachments)"""
        # Arrange
        mock_openwebui_client.send_message.return_value = {
            "success": True,
            "content": "I'll notify Sarah about this task.",
            "conversation_id": "conv-mentions-123"
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_with_mentions)

        # Assert - Verify mentions and attachments preserved
        call_kwargs = mock_openwebui_client.send_message.call_args[1]
        message_content = call_kwargs["message_content"]

        # Check mentions preserved
        assert len(message_content["mentions"]) == 1
        assert message_content["mentions"][0]["name"] == "Sarah Johnson"
        assert message_content["mentions"][0]["id"] == "user2@contoso.com"

        # Check attachments preserved
        assert len(message_content["attachments"]) == 1
        assert message_content["attachments"][0]["name"] == "project_proposal.pdf"
        assert message_content["attachments"][0]["content_type"] == "application/pdf"

    # AC5: Error handling when OpenWebUI is unavailable with fallback message
    @pytest.mark.asyncio
    async def test_ac5_error_handling_fallback(self, teams_bot, mock_turn_context_basic, mock_openwebui_client):
        """AC5: Error handling with fallback message"""
        # Arrange
        mock_openwebui_client.send_message.return_value = {
            "success": False,
            "content": "Sorry, I'm having trouble connecting to the Planner service. Please try again later."
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_basic)

        # Assert - Verify fallback message sent
        response_calls = [call for call in mock_turn_context_basic.send_activity.call_args_list
                         if "trouble connecting" in str(call[0][0].text)]
        assert len(response_calls) == 1

    # AC6: Authentication context passed through forwarding chain
    @pytest.mark.asyncio
    async def test_ac6_authentication_context_forwarded(self, teams_bot, mock_turn_context_basic, mock_openwebui_client):
        """AC6: Authentication context passed through forwarding chain"""
        # Arrange
        mock_openwebui_client.send_message.return_value = {
            "success": True,
            "content": "Authenticated response",
            "conversation_id": "conv-auth-123"
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_basic)

        # Assert - Verify authentication token forwarded
        call_kwargs = mock_openwebui_client.send_message.call_args[1]
        assert "auth_token" in call_kwargs
        assert call_kwargs["auth_token"] == "mock-teams-token-12345"

    # AC7: Conversation context maintained across multiple message exchanges
    @pytest.mark.asyncio
    async def test_ac7_conversation_context_maintained(self, teams_bot, mock_turn_context_basic, mock_openwebui_client, context_manager, mock_redis):
        """AC7: Conversation context maintained across multiple exchanges"""
        # Arrange - Mock Redis to return existing conversation
        existing_context = {
            "openwebui_conversation_id": "existing-conv-456",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
            "messages": [{"user": "Previous message", "assistant": "Previous response"}]
        }
        mock_redis.get.return_value = json.dumps(existing_context)

        mock_openwebui_client.send_message.return_value = {
            "success": True,
            "content": "Continuing our conversation",
            "conversation_id": "existing-conv-456"
        }

        # Act
        await teams_bot.on_message_activity(mock_turn_context_basic)

        # Assert - Verify existing conversation ID used
        call_kwargs = mock_openwebui_client.send_message.call_args[1]
        assert call_kwargs["conversation_id"] == "existing-conv-456"

        # Verify Redis was queried for context
        mock_redis.get.assert_called_with("teams:conversation:19:meeting_abc123:user@contoso.com")

    # AC8: Teams bot compliance requirements preserved (activity handling, adaptive cards)
    @pytest.mark.asyncio
    async def test_ac8_teams_compliance_preserved(self, teams_bot, mock_openwebui_client):
        """AC8: Teams bot compliance requirements preserved"""
        # Test welcome message functionality
        context = Mock(spec=TurnContext)
        context.activity = Mock()
        context.activity.recipient = Mock(id="bot-id")
        context.send_activity = AsyncMock()

        members = [Mock(id="new-user@contoso.com", name="New User")]

        # Act
        await teams_bot.on_members_added_activity(members, context)

        # Assert - Verify welcome message sent (Teams compliance requirement)
        context.send_activity.assert_called_once()
        sent_message = context.send_activity.call_args[0][0]
        assert "Welcome" in sent_message.text
        assert "Intelligent Teams Planner" in sent_message.text

    @pytest.mark.asyncio
    async def test_help_command_compliance(self, teams_bot, mock_openwebui_client):
        """Test help command handling (Teams compliance)"""
        # Arrange
        activity = Activity(
            type=ActivityTypes.message,
            text="/help",
            from_property=ChannelAccount(id="user@contoso.com"),
            conversation=Mock(id="19:meeting_help123")
        )
        context = Mock(spec=TurnContext)
        context.activity = activity
        context.send_activity = AsyncMock()

        # Act
        await teams_bot.on_message_activity(context)

        # Assert - Verify help message sent without calling OpenWebUI
        context.send_activity.assert_called_once()
        sent_message = context.send_activity.call_args[0][0]
        assert "Commands:" in sent_message.text or "help" in sent_message.text.lower()
        mock_openwebui_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_command_compliance(self, teams_bot, mock_openwebui_client, context_manager):
        """Test reset command handling (Teams compliance)"""
        # Arrange
        activity = Activity(
            type=ActivityTypes.message,
            text="/reset",
            from_property=ChannelAccount(id="user@contoso.com"),
            conversation=Mock(id="19:meeting_reset123")
        )
        context = Mock(spec=TurnContext)
        context.activity = activity
        context.send_activity = AsyncMock()

        # Act
        await teams_bot.on_message_activity(context)

        # Assert - Verify reset confirmation sent
        context.send_activity.assert_called_once()
        sent_message = context.send_activity.call_args[0][0]
        assert "reset" in sent_message.text.lower()
        mock_openwebui_client.send_message.assert_not_called()


class TestConversationContextManager:
    """Test Redis conversation context functionality"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis_mock = Mock()
        redis_mock.ping = AsyncMock()
        redis_mock.get = AsyncMock()
        redis_mock.setex = AsyncMock()
        redis_mock.close = AsyncMock()
        return redis_mock

    @pytest.fixture
    def context_manager(self, mock_redis):
        """ConversationContextManager with mocked Redis"""
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            manager = ConversationContextManager("redis://test:6379", ttl=3600)
            manager.redis_client = mock_redis
            return manager

    @pytest.mark.asyncio
    async def test_redis_key_generation(self, context_manager):
        """Test Redis key generation follows expected pattern"""
        # Act
        key = context_manager._get_key("19:meeting_abc123", "user@contoso.com")

        # Assert
        assert key == "teams:conversation:19:meeting_abc123:user@contoso.com"

    @pytest.mark.asyncio
    async def test_context_storage_and_retrieval(self, context_manager, mock_redis):
        """Test storing and retrieving conversation context"""
        # Arrange
        test_context = {
            "openwebui_conversation_id": "conv-test-123",
            "created_at": "2025-10-07T10:00:00",
            "messages": [{"user": "Hello", "assistant": "Hi there!"}]
        }
        mock_redis.get.return_value = json.dumps(test_context)

        # Act
        result = await context_manager.get_context("19:meeting_abc123", "user@contoso.com")

        # Assert
        assert result["openwebui_conversation_id"] == "conv-test-123"
        assert len(result["messages"]) == 1
        mock_redis.get.assert_called_with("teams:conversation:19:meeting_abc123:user@contoso.com")

    @pytest.mark.asyncio
    async def test_context_update_with_ttl(self, context_manager, mock_redis):
        """Test context updates with proper TTL"""
        # Arrange - Mock get to return None (no existing context)
        mock_redis.get.return_value = None

        # Act
        await context_manager.update_context(
            "19:meeting_abc123",
            "user@contoso.com",
            "conv-new-456",
            "Create a task",
            "Task created successfully"
        )

        # Assert
        mock_redis.setex.assert_called()
        call_args = mock_redis.setex.call_args
        key, ttl, data = call_args[0]

        assert key == "teams:conversation:19:meeting_abc123:user@contoso.com"
        assert ttl == 3600  # 1 hour TTL

        context_data = json.loads(data)
        assert context_data["openwebui_conversation_id"] == "conv-new-456"
        assert len(context_data["messages"]) == 1


class TestOpenWebUIClient:
    """Test OpenWebUI client with enhanced message formatting"""

    @pytest.fixture
    def client(self):
        """OpenWebUI client instance"""
        return OpenWebUIClient("http://test-openwebui:8080", "test-api-key")

    @pytest.mark.asyncio
    async def test_rich_message_content_formatting(self, client):
        """Test rich message content with mentions and attachments"""
        with patch.object(client.client, 'post') as mock_post:
            # Arrange
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Processed rich content"}}],
                "conversation_id": "conv-rich-123"
            }
            mock_post.return_value = mock_response

            message_content = {
                "text": "Review this document @Sarah",
                "mentions": [{"id": "user2@contoso.com", "name": "Sarah"}],
                "attachments": [{"name": "doc.pdf", "content_type": "application/pdf"}],
                "formatted_text": "Review this document @Sarah\n\n**Attachments:**\n- doc.pdf (application/pdf)\n\n**Mentioned users:**\n- @Sarah\n"
            }

            # Act
            result = await client.send_message(
                message_content=message_content,
                user_id="user@contoso.com",
                auth_token="test-token"
            )

            # Assert
            assert result["success"] is True
            assert result["content"] == "Processed rich content"

            # Verify payload structure
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert "metadata" in payload
            assert "teams_mentions" in payload["metadata"]
            assert "teams_attachments" in payload["metadata"]

    @pytest.mark.asyncio
    async def test_authentication_token_forwarding(self, client):
        """Test Teams authentication token forwarding"""
        with patch.object(client.client, 'post') as mock_post:
            # Arrange
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Authenticated response"}}]
            }
            mock_post.return_value = mock_response

            # Act
            await client.send_message(
                message_content={"text": "Test with auth"},
                user_id="user@contoso.com",
                auth_token="teams-token-12345"
            )

            # Assert
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert "X-Teams-Auth-Token" in headers
            assert headers["X-Teams-Auth-Token"] == "teams-token-12345"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])