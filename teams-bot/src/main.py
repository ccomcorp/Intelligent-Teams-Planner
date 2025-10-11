"""
Intelligent Teams Planner - Teams Bot v2.0
Thin client that forwards conversations to OpenWebUI
"""

import os
import sys
import asyncio
import json
from typing import Dict, Any, Optional
from aiohttp import web
from aiohttp.web import Request, Response, json_response
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp import (
    CloudAdapter,
    ConfigurationBotFrameworkAuthentication,
)
from botbuilder.schema import Activity, ActivityTypes
import structlog
import httpx
import redis.asyncio as redis
from datetime import datetime, timezone

try:
    from .attachment_handler import TeamsAttachmentHandler
    from .mention_handler import MentionHandler
    from .activity_feed import ActivityFeedManager, ActivityType
    from .adaptive_cards import AdaptiveCardTemplates
except ImportError:
    from attachment_handler import TeamsAttachmentHandler
    from mention_handler import MentionHandler
    from activity_feed import ActivityFeedManager, ActivityType
    from adaptive_cards import AdaptiveCardTemplates

# Configure structured logging
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class ConversationContextManager:
    """Redis-based conversation context management"""

    def __init__(self, redis_url: str, ttl: int = 3600):
        self.redis_url = redis_url
        self.ttl = ttl
        self.redis_client: Optional[redis.Redis] = None

    async def connect(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("Connected to Redis for conversation context")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            self.redis_client = None

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.aclose()

    def _get_key(self, channel_id: str, user_id: str) -> str:
        """Generate Redis key for conversation context"""
        return f"teams:conversation:{channel_id}:{user_id}"

    async def get_context(
        self, channel_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve conversation context from Redis"""
        if not self.redis_client:
            return None

        try:
            key = self._get_key(channel_id, user_id)
            data = await self.redis_client.get(key)
            if data:
                context = json.loads(data)
                # Update last activity timestamp
                context["last_activity"] = datetime.now(timezone.utc).isoformat()
                await self.redis_client.setex(key, self.ttl, json.dumps(context))
                return context
        except Exception as e:
            logger.error(
                "Error retrieving conversation context",
                error=str(e),
                channel_id=channel_id,
                user_id=user_id,
            )

        return None

    async def update_context(
        self,
        channel_id: str,
        user_id: str,
        openwebui_conversation_id: str,
        message: str,
        response: str,
    ) -> None:
        """Update conversation context in Redis"""
        if not self.redis_client:
            return

        try:
            key = self._get_key(channel_id, user_id)

            # Get existing context or create new
            existing_data = await self.redis_client.get(key)
            if existing_data:
                context = json.loads(existing_data)
            else:
                context = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "messages": [],
                }

            # Update context
            context["openwebui_conversation_id"] = openwebui_conversation_id
            context["last_activity"] = datetime.now(timezone.utc).isoformat()

            # Add message to history (keep last 10 messages as per story spec)
            context["messages"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "user_message": message,
                    "bot_response": response,
                }
            )

            # Keep only last 10 messages
            max_messages = int(os.getenv("MAX_CONTEXT_MESSAGES", "10"))
            if len(context["messages"]) > max_messages:
                context["messages"] = context["messages"][-max_messages:]

            # Store in Redis with TTL
            await self.redis_client.setex(key, self.ttl, json.dumps(context))

        except Exception as e:
            logger.error(
                "Error updating conversation context",
                error=str(e),
                channel_id=channel_id,
                user_id=user_id,
            )

    async def clear_context(self, channel_id: str, user_id: str) -> None:
        """Clear conversation context for user"""
        if not self.redis_client:
            return

        try:
            key = self._get_key(channel_id, user_id)
            await self.redis_client.delete(key)
            logger.info(
                "Cleared conversation context", channel_id=channel_id, user_id=user_id
            )
        except Exception as e:
            logger.error(
                "Error clearing conversation context",
                error=str(e),
                channel_id=channel_id,
                user_id=user_id,
            )


class OpenWebUIClient:
    """Client for communicating with OpenWebUI"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_message(
        self,
        message_content: Dict[str, Any],
        user_id: str,
        conversation_id: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send message to OpenWebUI and get response"""
        try:
            # Use formatted text that preserves mentions and attachments
            message_text = message_content.get(
                "formatted_text", message_content.get("text", "")
            )

            # Create rich message content for OpenWebUI
            content = message_text

            # Add attachment information if present
            if message_content.get("attachments"):
                attachment_info = "\n\n**Attachments:**\n"
                for att in message_content["attachments"]:
                    attachment_info += f"- {att['name']} ({att['content_type']})\n"
                content += attachment_info

            # Add mention context if present
            if message_content.get("mentions"):
                mention_info = "\n\n**Mentioned users:**\n"
                for mention in message_content["mentions"]:
                    if mention["name"]:
                        mention_info += f"- @{mention['name']}\n"
                content += mention_info

            # Format message for OpenWebUI chat completion
            payload = {
                "model": "planner-assistant",
                "messages": [{"role": "user", "content": content}],
                "user": user_id,
                "conversation_id": conversation_id,
                "stream": False,
                "metadata": {
                    "teams_mentions": message_content.get("mentions", []),
                    "teams_attachments": message_content.get("attachments", []),
                },
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Forward Teams authentication token if available
            if auth_token:
                headers["X-Teams-Auth-Token"] = auth_token
                logger.debug("Forwarding Teams authentication token to OpenWebUI")

            response = await self.client.post(
                f"{self.base_url}/api/chat/completions", json=payload, headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "content": data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "Sorry, I couldn't process that request."),
                    "conversation_id": data.get("conversation_id"),
                }
            else:
                logger.error(
                    "OpenWebUI API error",
                    status_code=response.status_code,
                    response=response.text,
                )
                return {
                    "success": False,
                    "content": "Sorry, I'm having trouble connecting to the Planner service. Please try again later.",
                }

        except Exception as e:
            logger.error("Error communicating with OpenWebUI", error=str(e))
            return {
                "success": False,
                "content": "Sorry, there was an error processing your request. Please try again.",
            }

    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()


class TeamsBot(ActivityHandler):
    """
    Lightweight Teams bot that forwards conversations to OpenWebUI
    Enhanced with mentions, adaptive cards, and activity feed integration
    """

    def __init__(
        self,
        openwebui_client: OpenWebUIClient,
        context_manager: ConversationContextManager,
        attachment_handler: TeamsAttachmentHandler,
        mention_handler: MentionHandler,
        activity_feed_manager: ActivityFeedManager,
    ):
        super().__init__()
        self.openwebui_client = openwebui_client
        self.context_manager = context_manager
        self.attachment_handler = attachment_handler
        self.mention_handler = mention_handler
        self.activity_feed_manager = activity_feed_manager
        # Keep in-memory fallback for when Redis is unavailable
        self.conversations: Dict[str, str] = {}  # conversation_id mapping

    async def _format_message_content(
        self, turn_context: TurnContext
    ) -> Dict[str, Any]:
        """Extract and format message content including mentions and attachments"""
        try:
            activity = turn_context.activity
            message_content = {
                "text": activity.text.strip() if activity.text else "",
                "mentions": [],
                "attachments": [],
            }

            # Use enhanced mention processing
            enhanced_content = await self.mention_handler.process_mentions(
                turn_context, message_content
            )

            # Extract attachments (ensure attachments key exists)
            if "attachments" not in enhanced_content:
                enhanced_content["attachments"] = []

            if hasattr(activity, "attachments") and activity.attachments:
                for attachment in activity.attachments:
                    att = {
                        "content_type": getattr(attachment, "content_type", ""),
                        "content_url": getattr(attachment, "content_url", ""),
                        "name": getattr(attachment, "name", ""),
                        "thumbnail_url": getattr(attachment, "thumbnail_url", None),
                    }
                    enhanced_content["attachments"].append(att)
                    logger.debug("Extracted attachment", attachment=att)

            logger.debug(
                "Formatted message content with enhanced mentions",
                has_mentions=len(enhanced_content["mentions"]) > 0,
                has_attachments=len(enhanced_content["attachments"]) > 0,
                bot_mentioned=enhanced_content.get("bot_mentioned", False)
            )

            return enhanced_content

        except Exception as e:
            logger.error("Error formatting message content", error=str(e))
            # Fallback to simple text
            return {
                "text": (
                    turn_context.activity.text.strip()
                    if turn_context.activity.text
                    else ""
                ),
                "formatted_text": (
                    turn_context.activity.text.strip()
                    if turn_context.activity.text
                    else ""
                ),
                "mentions": [],
                "attachments": [],
            }

    async def _extract_teams_token(self, turn_context: TurnContext) -> Optional[str]:
        """Extract Teams authentication token from activity context"""
        try:
            # Try to get token from activity properties
            activity = turn_context.activity

            # Look for token in activity channel data
            if hasattr(activity, "channel_data") and activity.channel_data:
                # Teams may include auth info in channel_data
                if "authToken" in activity.channel_data:
                    return activity.channel_data["authToken"]

            # Look for token in additional properties
            if (
                hasattr(activity, "additional_properties")
                and activity.additional_properties
            ):
                for key in ["authToken", "access_token", "token"]:
                    if key in activity.additional_properties:
                        return activity.additional_properties[key]

            # Try to get from Bot Framework authorization header
            # This would typically be set by the Teams client during authentication
            if hasattr(turn_context, 'adapter') and hasattr(turn_context.adapter, 'request'):
                auth_header = turn_context.adapter.request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    # Extract just the token part
                    token = auth_header[7:]  # Remove 'Bearer ' prefix
                    logger.debug("Extracted token from Authorization header")
                    return token

            logger.debug("No Teams authentication token found in activity context")
            return None

        except Exception as e:
            logger.error("Error extracting Teams authentication token", error=str(e))
            return None

    async def on_message_activity(self, turn_context: TurnContext):
        """Handle incoming message from Teams"""
        try:
            # Extract and format message content including mentions and attachments
            message_content = await self._format_message_content(turn_context)
            user_message = message_content["text"]
            user_id = turn_context.activity.from_property.id
            conversation_id = turn_context.activity.conversation.id

            # Extract Teams authentication token for forwarding
            teams_auth_token = await self._extract_teams_token(turn_context)

            logger.info(
                "Received message from Teams",
                user_id=user_id,
                message=user_message[:100],
                has_auth_token=bool(teams_auth_token),
                has_mentions=len(message_content["mentions"]) > 0,
                has_attachments=len(message_content["attachments"]) > 0,
            )

            # Handle special commands
            if user_message.lower() in ["/help", "help"]:
                await self._send_help_message(turn_context)
                return

            if user_message.lower() in ["/reset", "reset"]:
                # Clear both Redis and in-memory context
                await self.context_manager.clear_context(conversation_id, user_id)
                if conversation_id in self.conversations:
                    del self.conversations[conversation_id]
                await turn_context.send_activity(
                    MessageFactory.text(
                        "✅ Conversation reset. How can I help you with Microsoft Planner?"
                    )
                )
                return

            # Show typing indicator
            await turn_context.send_activity(Activity(type=ActivityTypes.typing))

            # Process file attachments if present
            attachment_response = ""
            if message_content["attachments"]:
                logger.info(
                    "Processing file attachments",
                    count=len(message_content["attachments"]),
                )

                # Process attachments with RAG service
                attachment_results = await self.attachment_handler.process_attachments(
                    turn_context.activity.attachments,
                    turn_context,
                    user_id,
                    conversation_id,
                )

                # Format response for user
                attachment_response = (
                    self.attachment_handler.format_attachment_response(
                        attachment_results
                    )
                )

                # If we have attachments and no text message, send attachment response immediately
                if not user_message.strip() and attachment_response:
                    await turn_context.send_activity(
                        MessageFactory.text(attachment_response)
                    )
                    return

            # Get existing conversation context from Redis
            context = await self.context_manager.get_context(conversation_id, user_id)
            openwebui_conversation_id = None

            if context:
                openwebui_conversation_id = context.get("openwebui_conversation_id")
            else:
                # Fallback to in-memory conversation mapping
                openwebui_conversation_id = self.conversations.get(conversation_id)

            # Send formatted message content to OpenWebUI with authentication token
            response = await self.openwebui_client.send_message(
                message_content=message_content,
                user_id=user_id,
                conversation_id=openwebui_conversation_id,
                auth_token=teams_auth_token,
            )

            if response["success"]:
                response_content = response["content"]

                # Combine OpenWebUI response with attachment processing results
                final_response = response_content
                if attachment_response:
                    final_response = f"{attachment_response}\n\n{response_content}"

                # Store conversation ID for continuity in both Redis and memory
                if response.get("conversation_id"):
                    self.conversations[conversation_id] = response["conversation_id"]
                    # Update Redis context with the conversation
                    await self.context_manager.update_context(
                        conversation_id,
                        user_id,
                        response["conversation_id"],
                        user_message,
                        final_response,
                    )

                # Check if we should send as adaptive card or text
                should_use_card = self._should_use_adaptive_card(message_content, response_content)

                if should_use_card:
                    # Try to parse response for structured data
                    card_data = self._extract_card_data_from_response(response_content)
                    if card_data:
                        card = self._create_response_card(card_data, message_content)
                        if card:
                            # Create adaptive card attachment (simplified for this implementation)
                            card_attachment = MessageFactory.text(f"[Adaptive Card: {card.get('type', 'Card')}]")
                            await turn_context.send_activity(card_attachment)
                        else:
                            await turn_context.send_activity(MessageFactory.text(final_response))
                    else:
                        await turn_context.send_activity(MessageFactory.text(final_response))
                else:
                    # Send response back to Teams as text
                    await turn_context.send_activity(MessageFactory.text(final_response))

                # Send activity feed notifications for mentions
                await self._handle_mention_notifications(
                    message_content, turn_context, teams_auth_token
                )

            else:
                # Store error response in context too
                await self.context_manager.update_context(
                    conversation_id,
                    user_id,
                    openwebui_conversation_id or "error",
                    user_message,
                    response["content"],
                )
                await turn_context.send_activity(
                    MessageFactory.text(response["content"])
                )

        except Exception as e:
            logger.error("Error processing message", error=str(e))
            await turn_context.send_activity(
                MessageFactory.text(
                    "Sorry, I encountered an error. Please try again or contact support."
                )
            )

    async def on_members_added_activity(
        self, members_added: list, turn_context: TurnContext
    ) -> None:
        """Welcome new members"""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await self._send_welcome_message(turn_context)

    async def _send_welcome_message(self, turn_context: TurnContext) -> None:
        """Send welcome message"""
        welcome_text = """
🎉 **Welcome to Intelligent Teams Planner!**

I'm your AI assistant for managing Microsoft Planner with natural language. Here's what I can help you with:

📋 **Planner Management:**
- Create and manage plans
- Add, update, and organize tasks
- Set due dates and priorities
- Assign tasks to team members

💬 **Natural Language Interface:**
- "Create a new plan for Q4 marketing campaign"
- "Add a task to review budget proposal due Friday"
- "Show me all overdue tasks"
- "Assign the presentation task to John"

🔧 **Commands:**
- Type `help` for more information
- Type `reset` to start a new conversation

Just start typing your request in natural language, and I'll help you manage your Planner tasks!
        """
        await turn_context.send_activity(MessageFactory.text(welcome_text))

    async def _send_help_message(self, turn_context: TurnContext) -> None:
        """Send help message"""
        help_text = """
🔧 **Intelligent Teams Planner Help**

**What I can do:**
✅ Create and manage Planner plans
✅ Add, edit, and delete tasks
✅ Set priorities and due dates
✅ Assign tasks to team members
✅ Show task status and progress
✅ Generate reports and summaries

**Example requests:**
- "Create a new plan called 'Project Alpha'"
- "Add a task to finalize the proposal, due next Friday"
- "Show me all tasks assigned to Sarah"
- "Mark the design review task as completed"
- "What tasks are overdue?"

**Commands:**
- `help` - Show this help message
- `reset` - Reset conversation context

**Tips:**
- Use natural language - no special syntax needed
- Be specific with names and dates
- I'll ask for clarification if needed

Ready to help manage your Planner tasks! 🚀
        """
        await turn_context.send_activity(MessageFactory.text(help_text))

    def _should_use_adaptive_card(self, message_content: Dict[str, Any], response: str) -> bool:
        """Determine if response should be sent as adaptive card"""
        try:
            # Use adaptive cards for:
            # 1. Responses to mentions
            # 2. Task-related responses
            # 3. Structured data responses

            if message_content.get("bot_mentioned", False):
                return True

            # Check for task-related keywords in response
            task_keywords = ["task", "plan", "assigned", "due", "priority", "completed"]
            response_lower = response.lower()

            if any(keyword in response_lower for keyword in task_keywords):
                return True

            # Check for structured data indicators
            if "**" in response or "###" in response or any(
                line.strip().startswith(("- ", "* ", "1. ", "2. "))
                for line in response.split("\n")
            ):
                return True

            return False

        except Exception as e:
            logger.error("Error determining card usage", error=str(e))
            return False

    def _extract_card_data_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract structured data from response for card creation"""
        try:
            # Simple parsing for common response patterns
            card_data = {"type": "general", "content": response}

            # Look for task information
            if "task" in response.lower():
                card_data["type"] = "task_response"

            # Look for list items
            lines = response.split("\n")
            list_items = [
                line.strip()[2:].strip()
                for line in lines
                if line.strip().startswith(("- ", "* "))
            ]

            if list_items:
                card_data["list_items"] = list_items

            # Look for key-value pairs (basic parsing)
            facts = []
            for line in lines:
                if ":" in line and not line.strip().startswith("#"):
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        facts.append({
                            "title": parts[0].strip(),
                            "value": parts[1].strip()
                        })

            if facts:
                card_data["facts"] = facts

            return card_data

        except Exception as e:
            logger.error("Error extracting card data", error=str(e))
            return None

    def _create_response_card(
        self,
        card_data: Dict[str, Any],
        message_content: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create adaptive card from response data"""
        try:
            card = {
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": []
            }

            # Add header
            if message_content.get("bot_mentioned"):
                card["body"].append({
                    "type": "TextBlock",
                    "text": "🤖 **Intelligent Planner Response**",
                    "size": "medium",
                    "weight": "bolder",
                    "color": "accent"
                })

            # Add main content
            content = card_data.get("content", "")
            if content:
                # Split content into paragraphs
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

                for paragraph in paragraphs:
                    if paragraph:
                        card["body"].append({
                            "type": "TextBlock",
                            "text": paragraph,
                            "wrap": True,
                            "spacing": "medium"
                        })

            # Add facts if available
            facts = card_data.get("facts")
            if facts:
                card["body"].append({
                    "type": "FactSet",
                    "facts": facts[:5],  # Limit to 5 facts
                    "spacing": "medium"
                })

            # Add list items if available
            list_items = card_data.get("list_items")
            if list_items:
                for item in list_items[:5]:  # Limit to 5 items
                    card["body"].append({
                        "type": "TextBlock",
                        "text": f"• {item}",
                        "spacing": "small"
                    })

            # Add action button
            card["actions"] = [
                {
                    "type": "Action.Submit",
                    "title": "Ask Follow-up",
                    "data": {
                        "action": "followUp"
                    }
                }
            ]

            return card

        except Exception as e:
            logger.error("Error creating response card", error=str(e))
            return None

    async def _handle_mention_notifications(
        self,
        message_content: Dict[str, Any],
        turn_context: TurnContext,
        auth_token: Optional[str] = None
    ) -> None:
        """Handle notifications for mentioned users"""
        try:
            mentions = message_content.get("mentions", [])
            if not mentions:
                return

            # Extract task context from mentions
            task_context = self.mention_handler.extract_task_context_from_mentions(
                mentions, message_content.get("text", "")
            )

            # Get conversation details
            conversation_id = turn_context.activity.conversation.id
            user_id = turn_context.activity.from_property.id
            user_name = getattr(turn_context.activity.from_property, "name", "Someone")

            # Send notifications for users who should be notified
            for mention in mentions:
                if mention.get("should_notify", False) and mention.get("id"):
                    try:
                        # Send activity feed notification
                        await self.activity_feed_manager.notify_mention_received(
                            task_id="conversation_mention",  # Use conversation as task context
                            task_title=f"Conversation in {conversation_id}",
                            mentioned_user_id=mention["id"],
                            mentioner_id=user_id,
                            mentioner_name=user_name,
                            message=message_content.get("text", "")[:200],  # Truncate message
                            auth_token=auth_token,
                            channel_id=conversation_id
                        )

                        logger.info(
                            "Sent mention notification",
                            mentioned_user=mention["id"],
                            mentioner=user_name
                        )

                    except Exception as e:
                        logger.error(
                            "Error sending mention notification",
                            error=str(e),
                            mentioned_user=mention.get("id")
                        )

        except Exception as e:
            logger.error("Error handling mention notifications", error=str(e))

    async def on_message_activity_invoke(self, turn_context: TurnContext) -> None:
        """Handle invoke activities (adaptive card actions)"""
        try:
            activity = turn_context.activity
            if hasattr(activity, "value") and activity.value:
                action_data = activity.value
                action = action_data.get("action")

                # Handle mention-related actions
                if action in ["viewTask", "replyToMention", "retry", "getHelp"]:
                    response = await self.mention_handler.handle_mention_actions(
                        action_data, turn_context
                    )
                    if response:
                        await turn_context.send_activity(response)

                # Handle other adaptive card actions
                elif action == "followUp":
                    await turn_context.send_activity(
                        MessageFactory.text("What would you like to know more about?")
                    )

                elif action in ["viewAllActivities", "refreshActivitySummary"]:
                    user_id = action_data.get("userId", turn_context.activity.from_property.id)
                    time_period = action_data.get("timePeriod", "today")

                    # Get authentication token
                    auth_token = await self._extract_teams_token(turn_context)

                    # Create activity summary card
                    summary_card = await self.activity_feed_manager.create_activity_summary_card(
                        user_id, time_period, auth_token
                    )

                    if summary_card:
                        # Create adaptive card attachment (simplified for this implementation)
                        card_attachment = MessageFactory.text(f"[Activity Summary Card: {summary_card.get('type', 'Card')}]")
                        await turn_context.send_activity(card_attachment)

                else:
                    await turn_context.send_activity(
                        MessageFactory.text("Action processed. How can I help you further?")
                    )

        except Exception as e:
            logger.error("Error handling invoke activity", error=str(e))
            await turn_context.send_activity(
                MessageFactory.text("Sorry, there was an error processing that action.")
            )


def create_app() -> web.Application:
    """Create the web application"""

    # Load configuration
    bot_app_id = os.getenv("BOT_ID")
    bot_app_password = os.getenv("BOT_PASSWORD")
    openwebui_url = os.getenv("OPENWEBUI_URL", "http://openwebui:8080")
    openwebui_api_key = os.getenv("OPENWEBUI_API_KEY", "dummy-key")

    if not bot_app_id or not bot_app_password:
        raise ValueError("BOT_ID and BOT_PASSWORD must be set")

    # Create configuration object for bot framework authentication
    class DefaultConfig:
        """Simple configuration for bot framework authentication"""

        def __init__(self, app_id: str, app_password: str):
            self.app_id = app_id
            self.app_password = app_password

        @property
        def APP_ID(self) -> str:
            return self.app_id

        @property
        def APP_PASSWORD(self) -> str:
            return self.app_password

    # Create configuration and authentication settings
    config = DefaultConfig(bot_app_id, bot_app_password)
    settings = ConfigurationBotFrameworkAuthentication(config)

    # Create OpenWebUI client
    openwebui_client = OpenWebUIClient(openwebui_url, openwebui_api_key)

    # Create conversation context manager
    redis_url = os.getenv("REDIS_URL", "redis://:redis_password_2024@redis:6379")
    conversation_ttl = int(os.getenv("CONVERSATION_TTL", "3600"))
    context_manager = ConversationContextManager(redis_url, conversation_ttl)

    # Create attachment handler for RAG service integration
    rag_service_url = os.getenv("RAG_SERVICE_URL", "http://localhost:7120")
    attachment_handler = TeamsAttachmentHandler(rag_service_url)

    # Create mention handler
    mention_handler = MentionHandler(openwebui_client, context_manager)

    # Create activity feed manager
    activity_feed_manager = ActivityFeedManager()

    # Create bot adapter and bot
    adapter = CloudAdapter(settings)
    bot = TeamsBot(
        openwebui_client,
        context_manager,
        attachment_handler,
        mention_handler,
        activity_feed_manager
    )

    async def messages(req: Request) -> Response:
        """Handle bot messages"""
        if "application/json" in req.headers.get("Content-Type", ""):
            body = await req.json()
        else:
            return Response(status=415, text="Unsupported Media Type")

        activity = Activity().deserialize(body)
        auth_header = req.headers.get("Authorization", "")

        try:
            invoke_response = await adapter.process_activity(
                activity, auth_header, bot.on_turn
            )
            if invoke_response:
                return json_response(
                    data=invoke_response.body, status=invoke_response.status
                )
            return Response(status=200)
        except Exception as e:
            logger.error("Error processing activity", error=str(e))
            return Response(status=500, text=str(e))

    async def health(req: Request) -> Response:
        """Health check endpoint"""
        try:
            # Test OpenWebUI connectivity
            health_check = await openwebui_client.client.get(
                f"{openwebui_url}/health", timeout=5.0
            )
            openwebui_status = (
                "healthy" if health_check.status_code == 200 else "unhealthy"
            )
        except Exception:
            openwebui_status = "unhealthy"

        return json_response(
            {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "openwebui_status": openwebui_status,
                "version": "2.0.0",
            }
        )

    async def startup(app) -> None:
        """Initialize connections on startup"""
        await context_manager.connect()

    async def cleanup(app) -> None:
        """Cleanup on shutdown"""
        await openwebui_client.close()
        await context_manager.close()
        await attachment_handler.close()
        await activity_feed_manager.close()

    # Create application
    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)

    return app


def main():
    """Main entry point"""
    try:
        # Set up event loop
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Create application
        app = create_app()

        # Start server
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "3978"))

        logger.info("Starting Intelligent Teams Planner Bot", host=host, port=port)

        web.run_app(app, host=host, port=port)

    except Exception as e:
        logger.error("Failed to start Teams bot", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
