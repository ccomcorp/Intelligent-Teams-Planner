"""
Database module for PostgreSQL with pgvector support
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Text, JSON, Boolean, Integer, func, text
from sqlalchemy.dialects.postgresql import UUID
import structlog
import uuid

logger = structlog.get_logger(__name__)

class Base(DeclarativeBase):
    """SQLAlchemy declarative base"""
    pass

class User(Base):
    """User model"""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    tenant_id: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class Plan(Base):
    """Planner plan model"""
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    group_id: Mapped[Optional[str]] = mapped_column(String(255))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class Task(Base):
    """Planner task model"""
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    plan_graph_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    bucket_id: Mapped[Optional[str]] = mapped_column(String(255))
    assigned_to: Mapped[Optional[List[str]]] = mapped_column(JSON)
    priority: Mapped[Optional[int]] = mapped_column(Integer)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completion_percentage: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    task_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class TokenStorage(Base):
    """OAuth token storage"""
    __tablename__ = "token_storage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    encrypted_tokens: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class ConversationContext(Base):
    """Conversation context for continuity"""
    __tablename__ = "conversation_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    context_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

class WebhookSubscriptionModel(Base):
    """Webhook subscription database model"""
    __tablename__ = "webhook_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    resource: Mapped[str] = mapped_column(String(500))
    notification_url: Mapped[str] = mapped_column(String(500))
    change_types: Mapped[List[str]] = mapped_column(JSON)
    client_state: Mapped[Optional[str]] = mapped_column(String(255))
    expiration_date_time: Mapped[datetime] = mapped_column(DateTime)
    include_resource_data: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_count: Mapped[int] = mapped_column(Integer, default=0)
    last_notification: Mapped[Optional[datetime]] = mapped_column(DateTime)
    subscription_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class WebhookNotificationModel(Base):
    """Webhook notification database model"""
    __tablename__ = "webhook_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    subscription_id: Mapped[str] = mapped_column(String(255), index=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    change_type: Mapped[str] = mapped_column(String(50))
    resource: Mapped[str] = mapped_column(String(500))
    client_state: Mapped[Optional[str]] = mapped_column(String(255))
    lifecycle_event: Mapped[Optional[str]] = mapped_column(String(50))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)
    notification_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class DatabaseError(Exception):
    """Database operation error"""
    pass

class Database:
    """Database manager with PostgreSQL and pgvector support"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.session_factory = None
        self._connection_pool = None

    async def initialize(self):
        """Initialize database connection and create tables"""
        try:
            # Validate PostgreSQL driver configuration
            if "postgresql" in self.database_url:
                if "+asyncpg" not in self.database_url:
                    logger.warning("Database URL missing +asyncpg driver specification, adding it")
                    self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")

                # Ensure asyncpg is available
                try:
                    import asyncpg
                    logger.info("✅ asyncpg driver available")
                except ImportError:
                    raise DatabaseError("asyncpg driver not available - required for async PostgreSQL connections")

            # Create async engine with database-specific parameters
            engine_kwargs = {
                "echo": os.getenv("DB_ECHO", "false").lower() == "true",
            }

            # Add pool parameters only for non-SQLite databases
            if not self.database_url.startswith("sqlite"):
                engine_kwargs.update({
                    "pool_size": 10,
                    "max_overflow": 20,
                    "pool_pre_ping": True,
                    "pool_recycle": 3600
                })

            logger.info(f"Creating async engine with URL: {self.database_url.split('@')[0]}@***")
            self.engine = create_async_engine(self.database_url, **engine_kwargs)

            # Create session factory
            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Create direct connection pool for raw queries (PostgreSQL only)
            if not self.database_url.startswith("sqlite"):
                self._connection_pool = await asyncpg.create_pool(
                    self.database_url.replace("postgresql+asyncpg://", "postgresql://"),
                    min_size=1,
                    max_size=10
                )

                # Initialize pgvector extension
                await self._initialize_pgvector()

            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize database", error=str(e))
            raise DatabaseError(f"Database initialization failed: {str(e)}")

    async def _initialize_pgvector(self):
        """Initialize pgvector extension"""
        try:
            if self._connection_pool:
                async with self._connection_pool.acquire() as conn:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    logger.info("pgvector extension initialized")
            else:
                logger.info("Skipping pgvector initialization for SQLite database")
        except Exception as e:
            logger.warning("Failed to initialize pgvector extension", error=str(e))

    async def close(self):
        """Close database connections"""
        try:
            if self._connection_pool:
                await self._connection_pool.close()
            if self.engine:
                await self.engine.dispose()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error("Error closing database connections", error=str(e))

    async def health_check(self) -> str:
        """Check database health"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
                return "healthy"
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return "unhealthy"

    # User operations
    async def get_or_create_user(self, user_id: str, display_name: str = None, email: str = None, tenant_id: str = None) -> User:
        """Get existing user or create new one"""
        try:
            async with self.session_factory() as session:
                # Try to get existing user
                result = await session.execute(
                    func.select(User).where(User.user_id == user_id)
                )
                user = result.scalar_one_or_none()

                if user:
                    # Update user info if provided
                    if display_name:
                        user.display_name = display_name
                    if email:
                        user.email = email
                    if tenant_id:
                        user.tenant_id = tenant_id
                    user.updated_at = func.now()
                    await session.commit()
                    return user

                # Create new user
                user = User(
                    user_id=user_id,
                    display_name=display_name,
                    email=email,
                    tenant_id=tenant_id
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user

        except Exception as e:
            logger.error("Error in get_or_create_user", error=str(e))
            raise DatabaseError(f"User operation failed: {str(e)}")

    # Plan operations
    async def save_plan(self, plan_data: Dict[str, Any]) -> Plan:
        """Save or update plan"""
        try:
            async with self.session_factory() as session:
                # Check if plan exists
                result = await session.execute(
                    func.select(Plan).where(Plan.graph_id == plan_data["graph_id"])
                )
                plan = result.scalar_one_or_none()

                if plan:
                    # Update existing plan
                    for key, value in plan_data.items():
                        if hasattr(plan, key) and key != "id":
                            setattr(plan, key, value)
                    plan.updated_at = func.now()
                else:
                    # Create new plan
                    plan = Plan(**plan_data)
                    session.add(plan)

                await session.commit()
                await session.refresh(plan)
                return plan

        except Exception as e:
            logger.error("Error saving plan", error=str(e))
            raise DatabaseError(f"Plan save failed: {str(e)}")

    async def get_plans_by_owner(self, owner_id: str) -> List[Plan]:
        """Get plans by owner"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(Plan).where(
                        Plan.owner_id == owner_id,
                        Plan.is_archived == False
                    ).order_by(Plan.updated_at.desc())
                )
                return result.scalars().all()

        except Exception as e:
            logger.error("Error getting plans by owner", error=str(e))
            raise DatabaseError(f"Plans retrieval failed: {str(e)}")

    # Task operations
    async def save_task(self, task_data: Dict[str, Any]) -> Task:
        """Save or update task"""
        try:
            async with self.session_factory() as session:
                # Check if task exists
                result = await session.execute(
                    func.select(Task).where(Task.graph_id == task_data["graph_id"])
                )
                task = result.scalar_one_or_none()

                if task:
                    # Update existing task
                    for key, value in task_data.items():
                        if hasattr(task, key) and key != "id":
                            setattr(task, key, value)
                    task.updated_at = func.now()
                else:
                    # Create new task
                    task = Task(**task_data)
                    session.add(task)

                await session.commit()
                await session.refresh(task)
                return task

        except Exception as e:
            logger.error("Error saving task", error=str(e))
            raise DatabaseError(f"Task save failed: {str(e)}")

    async def get_tasks_by_plan(self, plan_graph_id: str) -> List[Task]:
        """Get tasks by plan"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(Task).where(Task.plan_graph_id == plan_graph_id)
                    .order_by(Task.created_at.desc())
                )
                return result.scalars().all()

        except Exception as e:
            logger.error("Error getting tasks by plan", error=str(e))
            raise DatabaseError(f"Tasks retrieval failed: {str(e)}")

    # Token storage operations
    async def save_encrypted_tokens(self, user_id: str, encrypted_tokens: str, expires_at: datetime):
        """Save encrypted OAuth tokens"""
        try:
            async with self.session_factory() as session:
                # Check if tokens exist
                result = await session.execute(
                    func.select(TokenStorage).where(TokenStorage.user_id == user_id)
                )
                token_storage = result.scalar_one_or_none()

                if token_storage:
                    # Update existing tokens
                    token_storage.encrypted_tokens = encrypted_tokens
                    token_storage.expires_at = expires_at
                    token_storage.updated_at = func.now()
                else:
                    # Create new token storage
                    token_storage = TokenStorage(
                        user_id=user_id,
                        encrypted_tokens=encrypted_tokens,
                        expires_at=expires_at
                    )
                    session.add(token_storage)

                await session.commit()

        except Exception as e:
            logger.error("Error saving encrypted tokens", error=str(e))
            raise DatabaseError(f"Token save failed: {str(e)}")

    async def get_encrypted_tokens(self, user_id: str) -> Optional[TokenStorage]:
        """Get encrypted tokens for user"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(TokenStorage).where(
                        TokenStorage.user_id == user_id,
                        TokenStorage.expires_at > func.now()
                    )
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error("Error getting encrypted tokens", error=str(e))
            raise DatabaseError(f"Token retrieval failed: {str(e)}")

    async def delete_tokens(self, user_id: str):
        """Delete tokens for user"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(TokenStorage).where(TokenStorage.user_id == user_id)
                )
                token_storage = result.scalar_one_or_none()

                if token_storage:
                    await session.delete(token_storage)
                    await session.commit()

        except Exception as e:
            logger.error("Error deleting tokens", error=str(e))
            raise DatabaseError(f"Token deletion failed: {str(e)}")

    # Conversation context operations
    async def save_conversation_context(self, conversation_id: str, user_id: str, context_data: Dict[str, Any]):
        """Save conversation context"""
        try:
            async with self.session_factory() as session:
                # Check if context exists
                result = await session.execute(
                    func.select(ConversationContext).where(
                        ConversationContext.conversation_id == conversation_id
                    )
                )
                context = result.scalar_one_or_none()

                if context:
                    # Update existing context
                    context.context_data = context_data
                    context.last_activity = func.now()
                else:
                    # Create new context
                    context = ConversationContext(
                        conversation_id=conversation_id,
                        user_id=user_id,
                        context_data=context_data
                    )
                    session.add(context)

                await session.commit()

        except Exception as e:
            logger.error("Error saving conversation context", error=str(e))
            raise DatabaseError(f"Context save failed: {str(e)}")

    async def get_conversation_context(self, conversation_id: str) -> Optional[ConversationContext]:
        """Get conversation context"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(ConversationContext).where(
                        ConversationContext.conversation_id == conversation_id
                    )
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error("Error getting conversation context", error=str(e))
            raise DatabaseError(f"Context retrieval failed: {str(e)}")

    # Plan and Task deletion operations for delta sync
    async def delete_plan(self, graph_id: str) -> bool:
        """Delete plan by graph ID"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(Plan).where(Plan.graph_id == graph_id)
                )
                plan = result.scalar_one_or_none()

                if plan:
                    await session.delete(plan)
                    await session.commit()
                    return True
                return False

        except Exception as e:
            logger.error("Error deleting plan", graph_id=graph_id, error=str(e))
            raise DatabaseError(f"Plan deletion failed: {str(e)}")

    async def delete_task(self, graph_id: str) -> bool:
        """Delete task by graph ID"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(Task).where(Task.graph_id == graph_id)
                )
                task = result.scalar_one_or_none()

                if task:
                    await session.delete(task)
                    await session.commit()
                    return True
                return False

        except Exception as e:
            logger.error("Error deleting task", graph_id=graph_id, error=str(e))
            raise DatabaseError(f"Task deletion failed: {str(e)}")

    async def get_plan_by_graph_id(self, graph_id: str) -> Optional[Plan]:
        """Get plan by graph ID"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(Plan).where(Plan.graph_id == graph_id)
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error("Error getting plan by graph ID", graph_id=graph_id, error=str(e))
            raise DatabaseError(f"Plan retrieval failed: {str(e)}")

    async def get_task_by_graph_id(self, graph_id: str) -> Optional[Task]:
        """Get task by graph ID"""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    func.select(Task).where(Task.graph_id == graph_id)
                )
                return result.scalar_one_or_none()

        except Exception as e:
            logger.error("Error getting task by graph ID", graph_id=graph_id, error=str(e))
            raise DatabaseError(f"Task retrieval failed: {str(e)}")

    async def execute(self, query: str, parameters: dict = None) -> None:
        """Execute raw SQL with parameters (for webhook operations)"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text
                import json

                # Serialize dict/list parameters to JSON for SQLite compatibility
                if parameters:
                    serialized_params = {}
                    for key, value in parameters.items():
                        if isinstance(value, (dict, list)):
                            serialized_params[key] = json.dumps(value, default=str)
                        else:
                            serialized_params[key] = value
                else:
                    serialized_params = {}

                sql = text(query)
                await session.execute(sql, serialized_params)
                await session.commit()
        except Exception as e:
            logger.error("Raw SQL execution failed", error=str(e), query=query[:100])
            raise DatabaseError(f"SQL execution failed: {str(e)}")

    async def fetch_all(self, query: str, parameters: dict = None) -> List[dict]:
        """Fetch all rows from raw SQL query (for webhook operations)"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text
                import json

                sql = text(query)
                result = await session.execute(sql, parameters or {})
                rows = result.fetchall()

                # Convert to list of dictionaries
                if rows:
                    # Get column names from the result
                    columns = result.keys()
                    raw_rows = [dict(zip(columns, row)) for row in rows]

                    # Deserialize JSON fields (for fields that might contain JSON)
                    processed_rows = []
                    for row in raw_rows:
                        processed_row = {}
                        for key, value in row.items():
                            if isinstance(value, str) and key in ['subscription_data', 'metadata']:
                                try:
                                    processed_row[key] = json.loads(value)
                                except (json.JSONDecodeError, TypeError):
                                    processed_row[key] = value
                            else:
                                processed_row[key] = value
                        processed_rows.append(processed_row)
                    return processed_rows
                return []
        except Exception as e:
            logger.error("Raw SQL fetch failed", error=str(e), query=query[:100])
            raise DatabaseError(f"SQL fetch failed: {str(e)}")

    async def fetch_one(self, query: str, parameters: dict = None) -> Optional[dict]:
        """Fetch one row from raw SQL query (for webhook operations)"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text
                sql = text(query)
                result = await session.execute(sql, parameters or {})
                row = result.fetchone()

                if row:
                    columns = result.keys()
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error("Raw SQL fetch one failed", error=str(e), query=query[:100])
            raise DatabaseError(f"SQL fetch one failed: {str(e)}")