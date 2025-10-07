"""
Conversation Context Management
Story 1.3 Task 3: Context management with PostgreSQL storage
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ConversationMessage:
    """Single message in conversation history"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime
    entities: Optional[Dict[str, Any]] = None
    intent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ConversationContext:
    """Complete conversation context for a user session"""
    user_id: str
    session_id: str
    messages: List[ConversationMessage]
    extracted_entities: Dict[str, Any]
    user_preferences: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class ConversationContextManager:
    """
    Manages conversation context with PostgreSQL storage
    Maintains conversation history and entity context
    """

    def __init__(self, database, max_context_messages: int = 10, context_ttl_hours: int = 1):
        self.database = database
        self.max_context_messages = max_context_messages
        self.context_ttl_hours = context_ttl_hours

    async def initialize(self):
        """Initialize database schema for conversation context"""
        try:
            logger.info("Initializing conversation context manager")

            # Create conversation context table if it doesn't exist
            await self._create_context_table()

            logger.info("Conversation context manager initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize conversation context manager", error=str(e))
            raise

    async def _create_context_table(self):
        """Create conversation context table"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS conversation_context (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            session_id VARCHAR(255) NOT NULL,
            message_history JSONB NOT NULL DEFAULT '[]',
            extracted_entities JSONB NOT NULL DEFAULT '{}',
            user_preferences JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            UNIQUE(user_id, session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_conversation_user_session
        ON conversation_context(user_id, session_id);

        CREATE INDEX IF NOT EXISTS idx_conversation_expires
        ON conversation_context(expires_at);
        """

        await self.database.execute(create_table_sql)

    async def get_context(self, user_id: str, session_id: str) -> Optional[ConversationContext]:
        """
        Retrieve conversation context for a user session

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            ConversationContext if found, None otherwise
        """
        try:
            query = """
            SELECT user_id, session_id, message_history, extracted_entities,
                   user_preferences, created_at, updated_at, expires_at
            FROM conversation_context
            WHERE user_id = $1 AND session_id = $2 AND expires_at > CURRENT_TIMESTAMP
            """

            row = await self.database.fetch_one(query, user_id, session_id)

            if not row:
                logger.debug("No context found for user session",
                           user_id=user_id, session_id=session_id)
                return None

            # Parse message history
            messages = []
            for msg_data in row['message_history']:
                messages.append(ConversationMessage(
                    role=msg_data['role'],
                    content=msg_data['content'],
                    timestamp=datetime.fromisoformat(msg_data['timestamp']),
                    entities=msg_data.get('entities'),
                    intent=msg_data.get('intent'),
                    metadata=msg_data.get('metadata')
                ))

            context = ConversationContext(
                user_id=row['user_id'],
                session_id=row['session_id'],
                messages=messages,
                extracted_entities=row['extracted_entities'],
                user_preferences=row['user_preferences'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                expires_at=row['expires_at']
            )

            logger.debug("Retrieved conversation context",
                        user_id=user_id,
                        session_id=session_id,
                        message_count=len(messages))

            return context

        except Exception as e:
            logger.error("Error retrieving conversation context",
                        error=str(e), user_id=user_id, session_id=session_id)
            return None

    async def update_context(self, context: ConversationContext) -> bool:
        """
        Update conversation context in storage

        Args:
            context: ConversationContext to update

        Returns:
            True if successful, False otherwise
        """
        try:
            # Trim messages to max limit
            if len(context.messages) > self.max_context_messages:
                context.messages = context.messages[-self.max_context_messages:]

            # Serialize messages
            message_history = []
            for msg in context.messages:
                message_history.append({
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.timestamp.isoformat(),
                    'entities': msg.entities,
                    'intent': msg.intent,
                    'metadata': msg.metadata
                })

            # Update timestamps
            context.updated_at = datetime.now(timezone.utc)
            context.expires_at = context.updated_at + timedelta(hours=self.context_ttl_hours)

            # Upsert context
            upsert_query = """
            INSERT INTO conversation_context
            (user_id, session_id, message_history, extracted_entities, user_preferences,
             created_at, updated_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id, session_id)
            DO UPDATE SET
                message_history = EXCLUDED.message_history,
                extracted_entities = EXCLUDED.extracted_entities,
                user_preferences = EXCLUDED.user_preferences,
                updated_at = EXCLUDED.updated_at,
                expires_at = EXCLUDED.expires_at
            """

            await self.database.execute(
                upsert_query,
                context.user_id,
                context.session_id,
                json.dumps(message_history),
                json.dumps(context.extracted_entities),
                json.dumps(context.user_preferences),
                context.created_at,
                context.updated_at,
                context.expires_at
            )

            logger.debug("Updated conversation context",
                        user_id=context.user_id,
                        session_id=context.session_id,
                        message_count=len(context.messages))

            return True

        except Exception as e:
            logger.error("Error updating conversation context",
                        error=str(e),
                        user_id=context.user_id,
                        session_id=context.session_id)
            return False

    async def add_message(self, user_id: str, session_id: str, role: str, content: str,
                         entities: Optional[Dict[str, Any]] = None,
                         intent: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a message to conversation context

        Args:
            user_id: User identifier
            session_id: Session identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            entities: Extracted entities
            intent: Detected intent
            metadata: Additional metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing context or create new one
            context = await self.get_context(user_id, session_id)

            if not context:
                context = ConversationContext(
                    user_id=user_id,
                    session_id=session_id,
                    messages=[],
                    extracted_entities={},
                    user_preferences={},
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=self.context_ttl_hours)
                )

            # Create new message
            message = ConversationMessage(
                role=role,
                content=content,
                timestamp=datetime.now(timezone.utc),
                entities=entities,
                intent=intent,
                metadata=metadata
            )

            # Add message to context
            context.messages.append(message)

            # Update extracted entities if provided
            if entities:
                context.extracted_entities.update(entities)

            # Update context in storage
            return await self.update_context(context)

        except Exception as e:
            logger.error("Error adding message to context",
                        error=str(e), user_id=user_id, session_id=session_id)
            return False

    async def get_recent_entities(self, user_id: str, session_id: str,
                                entity_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get recently extracted entities from conversation

        Args:
            user_id: User identifier
            session_id: Session identifier
            entity_type: Specific entity type to retrieve (optional)

        Returns:
            Dictionary of entities
        """
        try:
            context = await self.get_context(user_id, session_id)

            if not context:
                return {}

            if entity_type:
                return {entity_type: context.extracted_entities.get(entity_type)}

            return context.extracted_entities

        except Exception as e:
            logger.error("Error getting recent entities",
                        error=str(e), user_id=user_id, session_id=session_id)
            return {}

    async def get_last_entity(self, user_id: str, session_id: str, entity_type: str) -> Optional[Any]:
        """
        Get the last occurrence of a specific entity type

        Args:
            user_id: User identifier
            session_id: Session identifier
            entity_type: Entity type to find

        Returns:
            Last entity value or None
        """
        try:
            context = await self.get_context(user_id, session_id)

            if not context:
                return None

            # Search messages in reverse order for the entity
            for message in reversed(context.messages):
                if message.entities and entity_type in message.entities:
                    return message.entities[entity_type]

            # Check extracted entities as fallback
            return context.extracted_entities.get(entity_type)

        except Exception as e:
            logger.error("Error getting last entity",
                        error=str(e), user_id=user_id, session_id=session_id)
            return None

    async def resolve_reference(self, user_id: str, session_id: str,
                              reference: str) -> Optional[Dict[str, Any]]:
        """
        Resolve contextual references like "that task", "same project", etc.

        Args:
            user_id: User identifier
            session_id: Session identifier
            reference: Reference text to resolve

        Returns:
            Resolved entity data or None
        """
        try:
            reference_lower = reference.lower()

            # Common reference patterns
            if "same project" in reference_lower or "that project" in reference_lower:
                project = await self.get_last_entity(user_id, session_id, "PLAN_NAME")
                return {"PLAN_NAME": project} if project else None

            elif "that task" in reference_lower or "the task" in reference_lower:
                task = await self.get_last_entity(user_id, session_id, "TASK_TITLE")
                return {"TASK_TITLE": task} if task else None

            elif "same person" in reference_lower or "that person" in reference_lower:
                assignee = await self.get_last_entity(user_id, session_id, "ASSIGNEE")
                return {"ASSIGNEE": assignee} if assignee else None

            elif "my tasks" in reference_lower:
                return {"ASSIGNEE": user_id}

            return None

        except Exception as e:
            logger.error("Error resolving reference",
                        error=str(e), user_id=user_id, session_id=session_id)
            return None

    async def update_user_preferences(self, user_id: str, session_id: str,
                                    preferences: Dict[str, Any]) -> bool:
        """
        Update user preferences in context

        Args:
            user_id: User identifier
            session_id: Session identifier
            preferences: Preferences to update

        Returns:
            True if successful, False otherwise
        """
        try:
            context = await self.get_context(user_id, session_id)

            if not context:
                context = ConversationContext(
                    user_id=user_id,
                    session_id=session_id,
                    messages=[],
                    extracted_entities={},
                    user_preferences=preferences,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=self.context_ttl_hours)
                )
            else:
                context.user_preferences.update(preferences)

            return await self.update_context(context)

        except Exception as e:
            logger.error("Error updating user preferences",
                        error=str(e), user_id=user_id, session_id=session_id)
            return False

    async def clear_context(self, user_id: str, session_id: str) -> bool:
        """
        Clear conversation context for a user session

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            delete_query = """
            DELETE FROM conversation_context
            WHERE user_id = $1 AND session_id = $2
            """

            await self.database.execute(delete_query, user_id, session_id)

            logger.debug("Cleared conversation context",
                        user_id=user_id, session_id=session_id)

            return True

        except Exception as e:
            logger.error("Error clearing conversation context",
                        error=str(e), user_id=user_id, session_id=session_id)
            return False

    async def cleanup_expired_contexts(self) -> int:
        """
        Clean up expired conversation contexts

        Returns:
            Number of contexts cleaned up
        """
        try:
            delete_query = """
            DELETE FROM conversation_context
            WHERE expires_at < CURRENT_TIMESTAMP
            """

            result = await self.database.execute(delete_query)
            cleaned_count = result.rowcount if hasattr(result, 'rowcount') else 0

            logger.info("Cleaned up expired conversation contexts", count=cleaned_count)

            return cleaned_count

        except Exception as e:
            logger.error("Error cleaning up expired contexts", error=str(e))
            return 0

    async def get_conversation_summary(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """
        Get a summary of the conversation context

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            Summary dictionary
        """
        try:
            context = await self.get_context(user_id, session_id)

            if not context:
                return {"exists": False}

            # Count message types
            user_messages = sum(1 for msg in context.messages if msg.role == 'user')
            assistant_messages = sum(1 for msg in context.messages if msg.role == 'assistant')

            # Get unique intents
            intents = list(set(msg.intent for msg in context.messages if msg.intent))

            # Get entity types
            entity_types = list(context.extracted_entities.keys())

            return {
                "exists": True,
                "message_count": len(context.messages),
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "unique_intents": intents,
                "entity_types": entity_types,
                "created_at": context.created_at.isoformat(),
                "expires_at": context.expires_at.isoformat(),
                "has_preferences": bool(context.user_preferences)
            }

        except Exception as e:
            logger.error("Error getting conversation summary",
                        error=str(e), user_id=user_id, session_id=session_id)
            return {"exists": False, "error": str(e)}