"""
Enhanced @mention processing for Teams Bot
Handles mention detection, processing, and notifications
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import json
import re
import asyncio
import structlog
from botbuilder.core import TurnContext, MessageFactory
from botbuilder.schema import Activity, ActivityTypes, Mention, Entity

try:
    from .adaptive_cards import AdaptiveCardTemplates
except ImportError:
    from adaptive_cards import AdaptiveCardTemplates

logger = structlog.get_logger(__name__)


class MentionHandler:
    """Enhanced mention handling for Teams Bot"""

    def __init__(self, openwebui_client, context_manager):
        self.openwebui_client = openwebui_client
        self.context_manager = context_manager
        self.mention_patterns = [
            r'@([a-zA-Z0-9._-]+)',  # Standard @username pattern
            r'<at>([^<]+)</at>',     # Teams mention format
            r'@\[([^\]]+)\]',        # Alternative mention format
        ]

    async def process_mentions(
        self,
        turn_context: TurnContext,
        message_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process mentions in the message and enhance content

        Args:
            turn_context: Bot framework turn context
            message_content: Extracted message content

        Returns:
            Enhanced message content with processed mentions
        """
        try:
            # Extract mentions from activity entities
            extracted_mentions = self._extract_activity_mentions(turn_context.activity)

            # Parse mentions from text content
            text_mentions = self._parse_text_mentions(message_content.get("text", ""))

            # Combine and deduplicate mentions
            all_mentions = self._merge_mentions(extracted_mentions, text_mentions)

            # Process each mention for additional context
            processed_mentions = await self._process_mention_details(all_mentions, turn_context)

            # Update message content with processed mentions
            enhanced_content = message_content.copy()
            enhanced_content["mentions"] = processed_mentions
            enhanced_content["mention_count"] = len(processed_mentions)

            # Check if bot was mentioned
            bot_mentioned = self._is_bot_mentioned(processed_mentions, turn_context)
            enhanced_content["bot_mentioned"] = bot_mentioned

            # Generate mention summary for context
            mention_summary = self._generate_mention_summary(processed_mentions)
            enhanced_content["mention_summary"] = mention_summary

            # Create formatted text with proper mention handling
            enhanced_content["formatted_text"] = self._format_text_with_mentions(
                message_content.get("text", ""), processed_mentions
            )

            logger.info(
                "Processed mentions in message",
                mention_count=len(processed_mentions),
                bot_mentioned=bot_mentioned,
                user_id=turn_context.activity.from_property.id
            )

            return enhanced_content

        except Exception as e:
            logger.error("Error processing mentions", error=str(e))
            # Return original content on error
            return message_content

    def _extract_activity_mentions(self, activity: Activity) -> List[Dict[str, Any]]:
        """Extract mentions from Teams activity entities"""
        mentions = []

        try:
            if hasattr(activity, "entities") and activity.entities:
                for entity in activity.entities:
                    if entity.type == "mention":
                        mention = {
                            "id": getattr(entity.mentioned, "id", None) if hasattr(entity, "mentioned") else None,
                            "name": getattr(entity.mentioned, "name", None) if hasattr(entity, "mentioned") else None,
                            "text": getattr(entity, "text", None),
                            "source": "activity_entity",
                            "raw_entity": entity
                        }

                        # Clean up mention text
                        if mention["text"]:
                            # Remove <at> tags and clean up
                            cleaned_text = mention["text"]
                            if cleaned_text.startswith("<at>") and cleaned_text.endswith("</at>"):
                                cleaned_text = cleaned_text[4:-5]  # Remove <at> and </at>
                            mention["text"] = cleaned_text.strip()

                        mentions.append(mention)

        except Exception as e:
            logger.error("Error extracting activity mentions", error=str(e))

        return mentions

    def _parse_text_mentions(self, text: str) -> List[Dict[str, Any]]:
        """Parse mentions from message text using regex patterns"""
        mentions = []

        try:
            for pattern in self.mention_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    mention_text = match.group(0)
                    mention_name = match.group(1)

                    mention = {
                        "id": None,  # Will be resolved later if possible
                        "name": mention_name.strip(),
                        "text": mention_text,
                        "source": "text_parsing",
                        "start_index": match.start(),
                        "end_index": match.end()
                    }

                    mentions.append(mention)

        except Exception as e:
            logger.error("Error parsing text mentions", error=str(e))

        return mentions

    def _merge_mentions(
        self,
        activity_mentions: List[Dict[str, Any]],
        text_mentions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge and deduplicate mentions from different sources"""
        merged = []
        seen_names = set()
        seen_ids = set()

        # Prioritize activity mentions (more reliable)
        for mention in activity_mentions:
            key = mention.get("name", "").lower()
            mention_id = mention.get("id")

            if key and key not in seen_names:
                merged.append(mention)
                seen_names.add(key)
                if mention_id:
                    seen_ids.add(mention_id)

        # Add text mentions that weren't found in activity
        for mention in text_mentions:
            key = mention.get("name", "").lower()

            # Check if this is similar to an existing mention (case-insensitive partial match)
            is_duplicate = False
            for existing_name in seen_names:
                if key in existing_name or existing_name in key:
                    is_duplicate = True
                    break

            if key and not is_duplicate:
                # Try to match with existing IDs
                mention["priority"] = "text_only"
                merged.append(mention)
                seen_names.add(key)

        return merged

    async def _process_mention_details(
        self,
        mentions: List[Dict[str, Any]],
        turn_context: TurnContext
    ) -> List[Dict[str, Any]]:
        """Process mention details and add additional context"""
        processed = []

        for mention in mentions:
            try:
                # Copy original mention data
                processed_mention = mention.copy()

                # Add timestamp
                processed_mention["mentioned_at"] = datetime.now(timezone.utc).isoformat()

                # Add conversation context
                processed_mention["conversation_id"] = turn_context.activity.conversation.id
                processed_mention["channel_id"] = getattr(turn_context.activity, "channel_id", None)

                # Try to resolve user details if we have an ID
                if mention.get("id"):
                    user_details = await self._resolve_user_details(mention["id"], turn_context)
                    if user_details:
                        processed_mention.update(user_details)

                # Determine mention type
                processed_mention["mention_type"] = self._determine_mention_type(processed_mention)

                # Add notification flag
                processed_mention["should_notify"] = self._should_notify_user(processed_mention)

                processed.append(processed_mention)

            except Exception as e:
                logger.error("Error processing mention details", error=str(e), mention=mention)
                # Still add the mention even if processing fails
                processed.append(mention)

        return processed

    async def _resolve_user_details(self, user_id: str, turn_context: TurnContext) -> Optional[Dict[str, Any]]:
        """Resolve additional user details from Teams API"""
        try:
            # Note: In a full implementation, this would call Teams/Graph API
            # For now, we'll return basic resolved info
            return {
                "resolved": True,
                "user_type": "teams_user",
                "availability": "unknown"
            }
        except Exception as e:
            logger.error("Error resolving user details", error=str(e), user_id=user_id)
            return None

    def _determine_mention_type(self, mention: Dict[str, Any]) -> str:
        """Determine the type of mention"""
        name = mention.get("name", "").lower()

        if name in ["everyone", "channel", "here"]:
            return "group_mention"
        elif mention.get("source") == "activity_entity":
            return "teams_mention"
        elif mention.get("id"):
            return "user_mention"
        else:
            return "text_mention"

    def _should_notify_user(self, mention: Dict[str, Any]) -> bool:
        """Determine if the mentioned user should receive a notification"""
        # Don't notify for group mentions in this basic implementation
        if mention.get("mention_type") == "group_mention":
            return False

        # Notify for direct user mentions
        if mention.get("mention_type") in ["user_mention", "teams_mention"]:
            return True

        # Default to not notifying
        return False

    def _is_bot_mentioned(self, mentions: List[Dict[str, Any]], turn_context: TurnContext) -> bool:
        """Check if the bot was mentioned in the message"""
        bot_id = turn_context.activity.recipient.id
        bot_name = getattr(turn_context.activity.recipient, "name", "").lower()

        for mention in mentions:
            # Check by ID
            if mention.get("id") == bot_id:
                return True

            # Check by name
            mention_name = mention.get("name", "").lower()
            if mention_name and (mention_name == bot_name or "planner" in mention_name):
                return True

        return False

    def _generate_mention_summary(self, mentions: List[Dict[str, Any]]) -> str:
        """Generate a summary of mentions for context"""
        if not mentions:
            return "No mentions"

        user_mentions = [m for m in mentions if m.get("mention_type") in ["user_mention", "teams_mention"]]
        group_mentions = [m for m in mentions if m.get("mention_type") == "group_mention"]

        summary_parts = []

        if user_mentions:
            user_names = [m.get("name", "Unknown") for m in user_mentions]
            summary_parts.append(f"Users: {', '.join(user_names)}")

        if group_mentions:
            group_names = [m.get("name", "Unknown") for m in group_mentions]
            summary_parts.append(f"Groups: {', '.join(group_names)}")

        return "; ".join(summary_parts) if summary_parts else "General mentions"

    def _format_text_with_mentions(self, text: str, mentions: List[Dict[str, Any]]) -> str:
        """Format text with proper mention representation"""
        if not text or not mentions:
            return text

        formatted_text = text

        # Sort mentions by start index (if available) in reverse order to avoid index shifting
        text_mentions = [m for m in mentions if m.get("start_index") is not None]
        text_mentions.sort(key=lambda x: x.get("start_index", 0), reverse=True)

        # Replace mentions with formatted versions
        for mention in text_mentions:
            start = mention.get("start_index")
            end = mention.get("end_index")
            original_text = mention.get("text", "")
            name = mention.get("name", "")

            if start is not None and end is not None and name:
                # Replace with @name format
                replacement = f"@{name}"
                formatted_text = formatted_text[:start] + replacement + formatted_text[end:]

        # Also handle activity-based mentions that might not have indices
        for mention in mentions:
            if mention.get("source") == "activity_entity" and mention.get("text"):
                original = mention["text"]
                name = mention.get("name", "")
                if name and original in formatted_text:
                    formatted_text = formatted_text.replace(original, f"@{name}")

        return formatted_text

    async def send_mention_notification(
        self,
        mentioned_user_id: str,
        mentioned_by: str,
        task_title: str,
        task_id: str,
        message: str,
        turn_context: TurnContext
    ) -> bool:
        """Send notification to mentioned user"""
        try:
            # Create adaptive card for mention notification
            card = AdaptiveCardTemplates.mention_notification_card(
                mentioned_by=mentioned_by,
                task_title=task_title,
                task_id=task_id,
                message=message,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

            # Create activity with the card (simplified for basic notification)
            # In a real implementation, this would create a proper adaptive card attachment
            notification_activity = MessageFactory.text(
                f"You were mentioned by {mentioned_by} in task: {task_title}"
            )

            # Set the recipient to the mentioned user
            notification_activity.conversation = turn_context.activity.conversation
            notification_activity.recipient = turn_context.activity.from_property  # This would be modified in real implementation

            logger.info(
                "Sending mention notification",
                mentioned_user=mentioned_user_id,
                mentioned_by=mentioned_by,
                task_id=task_id
            )

            # In a full implementation, this would use the Graph API to send a proactive message
            # For now, we'll log the notification
            logger.info("Mention notification prepared", card_type="mention_notification")

            return True

        except Exception as e:
            logger.error("Error sending mention notification", error=str(e))
            return False

    async def handle_mention_actions(
        self,
        action_data: Dict[str, Any],
        turn_context: TurnContext
    ) -> Optional[Activity]:
        """Handle actions from mention notification cards"""
        try:
            action = action_data.get("action")

            if action == "viewTask":
                task_id = action_data.get("taskId")
                if task_id:
                    # Create response to view task
                    return MessageFactory.text(f"Viewing task details for task ID: {task_id}")

            elif action == "replyToMention":
                task_id = action_data.get("taskId")
                mentioned_by = action_data.get("mentionedBy")

                if task_id and mentioned_by:
                    # Create response for replying to mention
                    return MessageFactory.text(
                        f"Replying to @{mentioned_by} regarding task {task_id}. "
                        "Please type your response."
                    )

            elif action == "retry":
                return MessageFactory.text("Please try your request again.")

            elif action == "getHelp":
                return MessageFactory.text(
                    "For help with mentions and notifications, type 'help' or contact support."
                )

            return None

        except Exception as e:
            logger.error("Error handling mention action", error=str(e))
            return MessageFactory.text("Sorry, there was an error processing that action.")

    def extract_task_context_from_mentions(self, mentions: List[Dict[str, Any]], message_text: str) -> Dict[str, Any]:
        """Extract task-related context from mentions and message"""
        context = {
            "has_task_assignment": False,
            "has_task_reference": False,
            "mentioned_users": [],
            "task_keywords": [],
            "action_keywords": []
        }

        try:
            # Extract mentioned users
            for mention in mentions:
                if mention.get("mention_type") in ["user_mention", "teams_mention"]:
                    user_info = {
                        "id": mention.get("id"),
                        "name": mention.get("name"),
                        "should_notify": mention.get("should_notify", False)
                    }
                    context["mentioned_users"].append(user_info)

            # Look for task-related keywords
            task_keywords = [
                "task", "todo", "assignment", "assign", "due", "deadline",
                "priority", "complete", "finish", "done", "progress"
            ]

            action_keywords = [
                "create", "add", "update", "edit", "delete", "remove",
                "assign", "reassign", "complete", "start", "review"
            ]

            message_lower = message_text.lower()

            # Check for task keywords
            found_task_keywords = [kw for kw in task_keywords if kw in message_lower]
            context["task_keywords"] = found_task_keywords
            context["has_task_reference"] = len(found_task_keywords) > 0

            # Check for action keywords
            found_action_keywords = [kw for kw in action_keywords if kw in message_lower]
            context["action_keywords"] = found_action_keywords

            # Determine if this is a task assignment
            assignment_patterns = [
                r"assign.*to.*@",
                r"@.*assigned.*to",
                r"@.*responsible.*for",
                r"@.*handle.*this",
                r"@.*take.*care.*of"
            ]

            for pattern in assignment_patterns:
                if re.search(pattern, message_lower):
                    context["has_task_assignment"] = True
                    break

            logger.debug("Extracted task context from mentions", context=context)

        except Exception as e:
            logger.error("Error extracting task context", error=str(e))

        return context