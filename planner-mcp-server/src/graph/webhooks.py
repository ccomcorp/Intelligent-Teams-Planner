"""
Microsoft Graph API Webhook Subscription Management
Story 2.1 Task 3: Comprehensive webhook subscription system with security validation
"""

import os
import hmac
import hashlib
import json
import uuid
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from urllib.parse import urljoin
import structlog

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import httpx

from ..models.graph_models import (
    WebhookSubscription,
    WebhookNotification,
    TenantContext
)
from ..database import Database
from ..cache import CacheService

logger = structlog.get_logger(__name__)


class CreateSubscriptionRequest(BaseModel):
    """Request model for creating webhook subscriptions"""
    resource: str
    change_types: List[str]
    user_id: str
    tenant_id: Optional[str] = None
    client_state: Optional[str] = None
    include_resource_data: bool = False
    expiration_hours: int = 168


class WebhookValidationError(Exception):
    """Webhook validation error"""
    pass


class WebhookSecurityError(Exception):
    """Webhook security error"""
    pass


class WebhookSubscriptionManager:
    """
    Manages Microsoft Graph webhook subscriptions with comprehensive security,
    multi-tenant isolation, and retry logic
    """

    def __init__(
        self,
        database: Database,
        cache_service: CacheService,
        graph_client: Any = None
    ):
        self.database = database
        self.cache_service = cache_service
        self.graph_client = graph_client

        # Configuration from environment
        self.webhook_base_url = os.getenv("WEBHOOK_BASE_URL", "")
        self.webhook_secret = os.getenv("WEBHOOK_SECRET", "")
        self.validation_token_timeout = int(os.getenv("WEBHOOK_VALIDATION_TOKEN_TIMEOUT", "300"))
        self.renewal_buffer = int(os.getenv("WEBHOOK_SUBSCRIPTION_RENEWAL_BUFFER", "86400"))
        self.retry_attempts = int(os.getenv("WEBHOOK_RETRY_ATTEMPTS", "3"))
        self.retry_delay = int(os.getenv("WEBHOOK_RETRY_DELAY", "60"))
        self.notification_timeout = int(os.getenv("WEBHOOK_NOTIFICATION_TIMEOUT", "30"))
        self.signature_algorithm = os.getenv("WEBHOOK_SIGNATURE_ALGORITHM", "HMAC-SHA256")

        # In-memory storage for validation tokens and subscriptions
        self.validation_tokens: Dict[str, Dict[str, Any]] = {}
        self.subscriptions: Dict[str, WebhookSubscription] = {}
        self.notification_queue: asyncio.Queue = asyncio.Queue()

        # Background task for processing notifications
        self._notification_processor_task = None
        self._subscription_renewal_task = None

    async def initialize(self) -> None:
        """Initialize webhook manager"""
        try:
            # Load existing subscriptions from database
            await self._load_subscriptions_from_database()

            # Start background tasks
            self._notification_processor_task = asyncio.create_task(
                self._process_notifications()
            )
            self._subscription_renewal_task = asyncio.create_task(
                self._renewal_monitor()
            )

            logger.info("Webhook subscription manager initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize webhook manager", error=str(e))
            raise

    async def shutdown(self) -> None:
        """Shutdown webhook manager"""
        try:
            # Cancel background tasks
            if self._notification_processor_task:
                self._notification_processor_task.cancel()

            if self._subscription_renewal_task:
                self._subscription_renewal_task.cancel()

            # Wait for tasks to complete
            await asyncio.gather(
                self._notification_processor_task,
                self._subscription_renewal_task,
                return_exceptions=True
            )

            logger.info("Webhook subscription manager shutdown completed")

        except Exception as e:
            logger.error("Error during webhook manager shutdown", error=str(e))

    async def create_subscription(
        self,
        resource: str,
        change_types: List[str],
        user_id: str,
        tenant_id: Optional[str] = None,
        client_state: Optional[str] = None,
        include_resource_data: bool = False,
        expiration_hours: int = 168  # 7 days default
    ) -> WebhookSubscription:
        """
        Create a new webhook subscription with Microsoft Graph

        Args:
            resource: The resource to monitor (e.g., '/planner/plans/{id}')
            change_types: List of change types to monitor ['created', 'updated', 'deleted']
            user_id: User identifier
            tenant_id: Tenant identifier for multi-tenant isolation
            client_state: Optional client state for validation
            include_resource_data: Whether to include resource data in notifications
            expiration_hours: Subscription expiration time in hours

        Returns:
            WebhookSubscription: Created subscription
        """
        try:
            # Re-read environment variables for dynamic testing, fall back to instance variables only if not set
            current_webhook_base_url = os.getenv("WEBHOOK_BASE_URL")
            if current_webhook_base_url is None:
                current_webhook_base_url = self.webhook_base_url

            current_webhook_secret = os.getenv("WEBHOOK_SECRET")
            if current_webhook_secret is None:
                current_webhook_secret = self.webhook_secret

            if not current_webhook_base_url:
                raise ValueError("WEBHOOK_BASE_URL must be configured")

            if not current_webhook_secret:
                raise ValueError("WEBHOOK_SECRET must be configured")

            # Generate subscription ID
            subscription_id = str(uuid.uuid4())

            # Calculate expiration
            expiration_date = datetime.now(timezone.utc) + timedelta(hours=expiration_hours)

            # Create notification URL with tenant isolation
            notification_url = self._build_notification_url(tenant_id, current_webhook_base_url)

            # Generate client state if not provided
            if not client_state:
                client_state = self._generate_client_state(user_id, tenant_id)

            # Create subscription object
            subscription = WebhookSubscription(
                id=subscription_id,
                resource=resource,
                change_types=change_types,
                notification_url=notification_url,
                client_state=client_state,
                expiration_date_time=expiration_date,
                creator_id=user_id,
                include_resource_data=include_resource_data,
                user_id=user_id,
                tenant_id=tenant_id
            )

            # Create subscription with Microsoft Graph
            if self.graph_client:
                graph_subscription = await self._create_graph_subscription(subscription)

                # Update subscription with Graph response
                subscription.id = graph_subscription.get("id", subscription_id)
                subscription.expiration_date_time = datetime.fromisoformat(
                    graph_subscription.get("expirationDateTime", "").replace("Z", "+00:00")
                )

            # Store subscription
            self.subscriptions[subscription.id] = subscription
            await self._store_subscription_in_database(subscription)

            # Cache subscription for quick lookup
            await self.cache_service.set(
                f"webhook_subscription:{subscription.id}",
                asdict(subscription),
                ttl=3600
            )

            logger.info(
                "Webhook subscription created successfully",
                subscription_id=subscription.id,
                resource=resource,
                tenant_id=tenant_id
            )

            return subscription

        except Exception as e:
            logger.error(
                "Failed to create webhook subscription",
                error=str(e),
                resource=resource,
                user_id=user_id,
                tenant_id=tenant_id
            )
            raise

    async def validate_notification(
        self,
        request: Request,
        signature: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate incoming webhook notification

        Args:
            request: FastAPI request object
            signature: HMAC signature from headers

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, validation_token_response)
        """
        try:
            # Handle validation token challenge
            validation_token = request.query_params.get("validationToken")
            if validation_token:
                # Microsoft Graph sends validation token for initial subscription verification
                return True, validation_token

            # Get request body
            body = await request.body()

            if not body:
                raise WebhookValidationError("Empty request body")

            # Validate HMAC signature if provided
            if signature and self.webhook_secret:
                expected_signature = self._calculate_signature(body)
                if not hmac.compare_digest(signature, expected_signature):
                    raise WebhookSecurityError("Invalid HMAC signature")

            # Parse notification payload
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise WebhookValidationError(f"Invalid JSON payload: {str(e)}")

            # Validate payload structure
            if "value" not in payload:
                raise WebhookValidationError("Missing 'value' field in payload")

            # Validate individual notifications
            for notification_data in payload["value"]:
                await self._validate_notification_data(notification_data)

            return True, None

        except (WebhookValidationError, WebhookSecurityError) as e:
            logger.error("Webhook validation failed", error=str(e))
            return False, None
        except Exception as e:
            logger.error("Unexpected error during webhook validation", error=str(e))
            return False, None

    async def process_notification(
        self,
        request: Request,
        background_tasks: BackgroundTasks
    ) -> Dict[str, Any]:
        """
        Process incoming webhook notification

        Args:
            request: FastAPI request object
            background_tasks: FastAPI background tasks

        Returns:
            Dict[str, Any]: Processing result
        """
        try:
            # Validate notification
            signature = request.headers.get("x-ms-signature") or request.headers.get("signature")
            is_valid, validation_token = await self.validate_notification(request, signature)

            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid webhook notification"
                )

            # Handle validation token response
            if validation_token:
                return PlainTextResponse(validation_token)

            # Parse notification payload
            body = await request.body()
            payload = json.loads(body.decode("utf-8"))

            # Process notifications in background
            for notification_data in payload["value"]:
                notification = self._create_webhook_notification(notification_data)
                await self.notification_queue.put(notification)

            # Schedule background processing
            background_tasks.add_task(self._ensure_notification_processing)

            return {
                "success": True,
                "processed_count": len(payload["value"]),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to process webhook notification", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )

    async def renew_subscription(
        self,
        subscription_id: str,
        extension_hours: int = 168
    ) -> WebhookSubscription:
        """
        Renew webhook subscription

        Args:
            subscription_id: Subscription ID to renew
            extension_hours: Hours to extend subscription

        Returns:
            WebhookSubscription: Renewed subscription
        """
        try:
            subscription = self.subscriptions.get(subscription_id)
            if not subscription:
                # Try to load from database
                subscription = await self._load_subscription_from_database(subscription_id)
                if not subscription:
                    raise ValueError(f"Subscription {subscription_id} not found")

            # Calculate new expiration - extend from current time (Microsoft Graph behavior)
            new_expiration = datetime.now(timezone.utc) + timedelta(hours=extension_hours)

            # Renew with Microsoft Graph
            if self.graph_client:
                await self._renew_graph_subscription(subscription_id, new_expiration)

            # Update subscription
            subscription.expiration_date_time = new_expiration
            self.subscriptions[subscription_id] = subscription

            # Update in database
            await self._store_subscription_in_database(subscription)

            # Update cache
            await self.cache_service.set(
                f"webhook_subscription:{subscription_id}",
                asdict(subscription),
                ttl=3600
            )

            logger.info(
                "Webhook subscription renewed successfully",
                subscription_id=subscription_id,
                new_expiration=new_expiration.isoformat()
            )

            return subscription

        except Exception as e:
            logger.error(
                "Failed to renew webhook subscription",
                error=str(e),
                subscription_id=subscription_id
            )
            raise

    async def delete_subscription(self, subscription_id: str) -> bool:
        """
        Delete webhook subscription

        Args:
            subscription_id: Subscription ID to delete

        Returns:
            bool: True if successfully deleted
        """
        try:
            # Delete from Microsoft Graph
            if self.graph_client:
                await self._delete_graph_subscription(subscription_id)

            # Remove from local storage
            self.subscriptions.pop(subscription_id, None)

            # Remove from database
            await self._delete_subscription_from_database(subscription_id)

            # Remove from cache
            await self.cache_service.delete(f"webhook_subscription:{subscription_id}")

            logger.info(
                "Webhook subscription deleted successfully",
                subscription_id=subscription_id
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to delete webhook subscription",
                error=str(e),
                subscription_id=subscription_id
            )
            return False

    async def get_subscriptions_for_tenant(
        self,
        tenant_id: Optional[str] = None
    ) -> List[WebhookSubscription]:
        """
        Get all subscriptions for a tenant

        Args:
            tenant_id: Tenant ID (None for default tenant)

        Returns:
            List[WebhookSubscription]: List of subscriptions
        """
        try:
            tenant_subscriptions = [
                subscription for subscription in self.subscriptions.values()
                if subscription.tenant_id == tenant_id
            ]

            return tenant_subscriptions

        except Exception as e:
            logger.error(
                "Failed to get subscriptions for tenant",
                error=str(e),
                tenant_id=tenant_id
            )
            return []

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform webhook system health check

        Returns:
            Dict[str, Any]: Health status
        """
        try:
            active_subscriptions = len([
                s for s in self.subscriptions.values()
                if not s.is_expired()
            ])

            expired_subscriptions = len([
                s for s in self.subscriptions.values()
                if s.is_expired()
            ])

            queue_size = self.notification_queue.qsize()

            return {
                "status": "healthy",
                "active_subscriptions": active_subscriptions,
                "expired_subscriptions": expired_subscriptions,
                "notification_queue_size": queue_size,
                "processor_running": self._notification_processor_task and not self._notification_processor_task.done(),
                "renewal_monitor_running": self._subscription_renewal_task and not self._subscription_renewal_task.done(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error("Webhook health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    # Private methods

    def _build_notification_url(self, tenant_id: Optional[str], webhook_base_url: Optional[str] = None) -> str:
        """Build notification URL with tenant isolation"""
        base_url = webhook_base_url or self.webhook_base_url
        if tenant_id:
            return urljoin(base_url, f"/tenant/{tenant_id}")
        return urljoin(base_url, "/default")

    def _generate_client_state(self, user_id: str, tenant_id: Optional[str]) -> str:
        """Generate client state for validation"""
        state_data = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return json.dumps(state_data)

    def _calculate_signature(self, body: bytes) -> str:
        """Calculate HMAC signature for request body"""
        signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    async def _validate_notification_data(self, notification_data: Dict[str, Any]) -> None:
        """Validate individual notification data"""
        required_fields = ["subscriptionId", "changeType", "resource"]

        for field in required_fields:
            if field not in notification_data:
                raise WebhookValidationError(f"Missing required field: {field}")

        # Validate subscription exists
        subscription_id = notification_data["subscriptionId"]
        if subscription_id not in self.subscriptions:
            # Try to load from database
            subscription = await self._load_subscription_from_database(subscription_id)
            if not subscription:
                raise WebhookValidationError(f"Unknown subscription: {subscription_id}")
            self.subscriptions[subscription_id] = subscription

        # Validate client state if present
        client_state = notification_data.get("clientState")
        if client_state:
            subscription = self.subscriptions[subscription_id]
            if subscription.client_state and client_state != subscription.client_state:
                raise WebhookSecurityError("Client state mismatch")

    def _create_webhook_notification(self, notification_data: Dict[str, Any]) -> WebhookNotification:
        """Create WebhookNotification object from notification data"""
        return WebhookNotification(
            subscription_id=notification_data["subscriptionId"],
            client_state=notification_data.get("clientState"),
            change_type=notification_data["changeType"],
            resource=notification_data["resource"],
            resource_data=notification_data.get("resourceData"),
            lifecycle_event=notification_data.get("lifecycleEvent"),
            subscription_expiration_date_time=self._parse_datetime(
                notification_data.get("subscriptionExpirationDateTime")
            ),
            tenant_id=self._extract_tenant_from_notification(notification_data)
        )

    def _extract_tenant_from_notification(self, notification_data: Dict[str, Any]) -> Optional[str]:
        """Extract tenant ID from notification data"""
        subscription_id = notification_data["subscriptionId"]
        subscription = self.subscriptions.get(subscription_id)
        return subscription.tenant_id if subscription else None

    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string to datetime object"""
        if not datetime_str:
            return None
        try:
            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    async def _process_notifications(self) -> None:
        """Background task to process webhook notifications"""
        while True:
            try:
                # Get notification from queue with timeout
                notification = await asyncio.wait_for(
                    self.notification_queue.get(),
                    timeout=10.0
                )

                await self._handle_notification_with_retry(notification)
                self.notification_queue.task_done()

            except asyncio.TimeoutError:
                # Normal timeout, continue processing
                continue
            except asyncio.CancelledError:
                logger.info("Notification processor task cancelled")
                break
            except Exception as e:
                logger.error("Error in notification processor", error=str(e))
                await asyncio.sleep(1)

    async def _handle_notification_with_retry(self, notification: WebhookNotification) -> None:
        """Handle notification with retry logic"""
        for attempt in range(self.retry_attempts):
            try:
                await self._handle_notification(notification)

                # Mark as processed
                notification.processed = True
                await self._store_notification_in_database(notification)

                logger.info(
                    "Webhook notification processed successfully",
                    subscription_id=notification.subscription_id,
                    change_type=notification.change_type,
                    resource=notification.resource
                )
                return

            except Exception as e:
                notification.processing_error = str(e)

                if attempt < self.retry_attempts - 1:
                    # Wait before retry with exponential backoff
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Notification processing failed, retrying in {wait_time}s",
                        error=str(e),
                        attempt=attempt + 1,
                        subscription_id=notification.subscription_id
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        "Notification processing failed after all retries",
                        error=str(e),
                        subscription_id=notification.subscription_id
                    )

                    # Store failed notification for manual review
                    await self._store_notification_in_database(notification)

    async def _handle_notification(self, notification: WebhookNotification) -> None:
        """Handle individual notification"""
        try:
            # Get subscription for tenant isolation
            subscription = self.subscriptions.get(notification.subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {notification.subscription_id} not found")

            # Update subscription statistics
            subscription.update_notification_stats()
            await self._store_subscription_in_database(subscription)

            # Process based on change type and resource
            if "planner/plans" in notification.resource:
                await self._handle_planner_plan_notification(notification, subscription)
            elif "planner/tasks" in notification.resource:
                await self._handle_planner_task_notification(notification, subscription)
            elif "groups" in notification.resource:
                await self._handle_group_notification(notification, subscription)
            else:
                logger.warning(
                    "Unknown resource type in notification",
                    resource=notification.resource,
                    subscription_id=notification.subscription_id
                )

        except Exception as e:
            logger.error(
                "Failed to handle notification",
                error=str(e),
                subscription_id=notification.subscription_id
            )
            raise

    async def _handle_planner_plan_notification(
        self,
        notification: WebhookNotification,
        subscription: WebhookSubscription
    ) -> None:
        """Handle planner plan change notification"""
        logger.info(
            "Processing planner plan notification",
            change_type=notification.change_type,
            resource=notification.resource,
            tenant_id=subscription.tenant_id
        )

        # Store notification for processing by other components
        await self.cache_service.lpush(
            f"plan_notifications:{subscription.tenant_id}",
            asdict(notification)
        )

    async def _handle_planner_task_notification(
        self,
        notification: WebhookNotification,
        subscription: WebhookSubscription
    ) -> None:
        """Handle planner task change notification"""
        logger.info(
            "Processing planner task notification",
            change_type=notification.change_type,
            resource=notification.resource,
            tenant_id=subscription.tenant_id
        )

        # Store notification for processing by other components
        await self.cache_service.lpush(
            f"task_notifications:{subscription.tenant_id}",
            asdict(notification)
        )

    async def _handle_group_notification(
        self,
        notification: WebhookNotification,
        subscription: WebhookSubscription
    ) -> None:
        """Handle group change notification"""
        logger.info(
            "Processing group notification",
            change_type=notification.change_type,
            resource=notification.resource,
            tenant_id=subscription.tenant_id
        )

        # Store notification for processing by other components
        await self.cache_service.lpush(
            f"group_notifications:{subscription.tenant_id}",
            asdict(notification)
        )

    async def _renewal_monitor(self) -> None:
        """Background task to monitor and renew expiring subscriptions"""
        while True:
            try:
                # Check every hour
                await asyncio.sleep(3600)

                # Find subscriptions that need renewal
                buffer_hours = self.renewal_buffer // 3600
                expiring_subscriptions = [
                    subscription for subscription in self.subscriptions.values()
                    if subscription.needs_renewal(buffer_hours)
                ]

                # Renew expiring subscriptions
                for subscription in expiring_subscriptions:
                    try:
                        await self.renew_subscription(subscription.id)
                    except Exception as e:
                        logger.error(
                            "Failed to auto-renew subscription",
                            error=str(e),
                            subscription_id=subscription.id
                        )

            except asyncio.CancelledError:
                logger.info("Subscription renewal monitor cancelled")
                break
            except Exception as e:
                logger.error("Error in subscription renewal monitor", error=str(e))

    async def _ensure_notification_processing(self) -> None:
        """Ensure notification processing task is running"""
        if not self._notification_processor_task or self._notification_processor_task.done():
            self._notification_processor_task = asyncio.create_task(
                self._process_notifications()
            )

    # Microsoft Graph API integration methods

    async def _create_graph_subscription(self, subscription: WebhookSubscription) -> Dict[str, Any]:
        """Create subscription with Microsoft Graph API"""
        if not self.graph_client:
            # Return mock response for testing
            return {
                "id": subscription.id,
                "expirationDateTime": subscription.expiration_date_time.isoformat() + "Z"
            }

        subscription_data = {
            "resource": subscription.resource,
            "changeType": ",".join(subscription.change_types),
            "notificationUrl": subscription.notification_url,
            "expirationDateTime": subscription.expiration_date_time.isoformat() + "Z",
            "clientState": subscription.client_state,
            "includeResourceData": subscription.include_resource_data
        }

        response = await self.graph_client.post("/subscriptions", subscription_data)
        return response

    async def _renew_graph_subscription(
        self,
        subscription_id: str,
        expiration_date: datetime
    ) -> Dict[str, Any]:
        """Renew subscription with Microsoft Graph API"""
        if not self.graph_client:
            # Return mock response for testing
            return {
                "id": subscription_id,
                "expirationDateTime": expiration_date.isoformat() + "Z"
            }

        renewal_data = {
            "expirationDateTime": expiration_date.isoformat() + "Z"
        }

        response = await self.graph_client.patch(f"/subscriptions/{subscription_id}", renewal_data)
        return response

    async def _delete_graph_subscription(self, subscription_id: str) -> None:
        """Delete subscription from Microsoft Graph API"""
        if not self.graph_client:
            return

        await self.graph_client.delete(f"/subscriptions/{subscription_id}")

    # Database methods

    async def _load_subscriptions_from_database(self) -> None:
        """Load existing subscriptions from database"""
        try:
            query = """
            SELECT subscription_data FROM webhook_subscriptions
            WHERE expiration_date_time > CURRENT_TIMESTAMP
            """

            rows = await self.database.fetch_all(query)

            for row in rows:
                subscription_data = row["subscription_data"]
                # Deserialize JSON string to dictionary if needed
                if isinstance(subscription_data, str):
                    subscription_data = json.loads(subscription_data)
                subscription = WebhookSubscription(**subscription_data)
                self.subscriptions[subscription.id] = subscription

            logger.info(f"Loaded {len(rows)} subscriptions from database")

        except Exception as e:
            logger.error("Failed to load subscriptions from database", error=str(e))

    async def _load_subscription_from_database(
        self,
        subscription_id: str
    ) -> Optional[WebhookSubscription]:
        """Load specific subscription from database"""
        try:
            query = """
            SELECT subscription_data FROM webhook_subscriptions
            WHERE subscription_id = :subscription_id
            """

            row = await self.database.fetch_one(query, {"subscription_id": subscription_id})

            if row:
                subscription_data = row["subscription_data"]
                # Deserialize JSON string to dictionary if needed
                if isinstance(subscription_data, str):
                    subscription_data = json.loads(subscription_data)
                return WebhookSubscription(**subscription_data)

            return None

        except Exception as e:
            logger.error(
                "Failed to load subscription from database",
                error=str(e),
                subscription_id=subscription_id
            )
            return None

    async def _store_subscription_in_database(self, subscription: WebhookSubscription) -> None:
        """Store subscription in database"""
        try:
            query = """
            INSERT INTO webhook_subscriptions (
                id, subscription_id, tenant_id, user_id, resource, notification_url,
                change_types, client_state, expiration_date_time, include_resource_data,
                notification_count, subscription_data, created_at, updated_at
            ) VALUES (
                :id, :subscription_id, :tenant_id, :user_id, :resource, :notification_url,
                :change_types, :client_state, :expiration_date_time, :include_resource_data,
                :notification_count, :subscription_data, :created_at, :updated_at
            )
            ON CONFLICT (subscription_id) DO UPDATE SET
                expiration_date_time = EXCLUDED.expiration_date_time,
                subscription_data = EXCLUDED.subscription_data,
                updated_at = EXCLUDED.updated_at,
                notification_count = EXCLUDED.notification_count
            """

            await self.database.execute(query, {
                "id": str(uuid.uuid4()),  # Generate UUID for primary key
                "subscription_id": subscription.id,
                "tenant_id": subscription.tenant_id,
                "user_id": subscription.user_id,
                "resource": subscription.resource,
                "notification_url": subscription.notification_url,
                "change_types": subscription.change_types,
                "client_state": subscription.client_state,
                "expiration_date_time": subscription.expiration_date_time,
                "include_resource_data": subscription.include_resource_data,
                "notification_count": subscription.notification_count,
                "subscription_data": asdict(subscription),
                "created_at": subscription.created_at,
                "updated_at": datetime.now(timezone.utc)
            })

        except Exception as e:
            logger.error(
                "Failed to store subscription in database",
                error=str(e),
                subscription_id=subscription.id
            )
            raise

    async def _delete_subscription_from_database(self, subscription_id: str) -> None:
        """Delete subscription from database"""
        try:
            query = "DELETE FROM webhook_subscriptions WHERE subscription_id = :subscription_id"
            await self.database.execute(query, {"subscription_id": subscription_id})

        except Exception as e:
            logger.error(
                "Failed to delete subscription from database",
                error=str(e),
                subscription_id=subscription_id
            )
            raise

    async def _store_notification_in_database(self, notification: WebhookNotification) -> None:
        """Store webhook notification in database"""
        try:
            query = """
            INSERT INTO webhook_notifications (
                notification_id, subscription_id, tenant_id, change_type,
                resource, notification_data, received_at, processed
            ) VALUES (
                :notification_id, :subscription_id, :tenant_id, :change_type,
                :resource, :notification_data, :received_at, :processed
            )
            """

            await self.database.execute(query, {
                "notification_id": str(uuid.uuid4()),
                "subscription_id": notification.subscription_id,
                "tenant_id": notification.tenant_id,
                "change_type": notification.change_type,
                "resource": notification.resource,
                "notification_data": asdict(notification),
                "received_at": notification.received_at,
                "processed": notification.processed
            })

        except Exception as e:
            logger.error(
                "Failed to store notification in database",
                error=str(e),
                subscription_id=notification.subscription_id
            )


# FastAPI router for webhook endpoints
def create_webhook_router(webhook_manager: WebhookSubscriptionManager) -> Any:
    """Create FastAPI router for webhook endpoints"""
    from fastapi import APIRouter, Request, BackgroundTasks, Header
    from fastapi.responses import PlainTextResponse

    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    @router.post("/default")
    @router.post("/tenant/{tenant_id}")
    async def webhook_endpoint(
        request: Request,
        background_tasks: BackgroundTasks,
        tenant_id: Optional[str] = None,
        signature: Optional[str] = Header(None, alias="x-ms-signature")
    ):
        """Webhook endpoint for Microsoft Graph notifications"""
        try:
            # Handle validation token for subscription verification
            validation_token = request.query_params.get("validationToken")
            if validation_token:
                return PlainTextResponse(validation_token)

            # Process notification
            result = await webhook_manager.process_notification(request, background_tasks)

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Webhook endpoint error", error=str(e), tenant_id=tenant_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )

    @router.get("/health")
    async def webhook_health():
        """Webhook system health check"""
        return await webhook_manager.health_check()

    @router.get("/subscriptions")
    async def list_subscriptions(tenant_id: Optional[str] = None):
        """List webhook subscriptions for tenant"""
        subscriptions = await webhook_manager.get_subscriptions_for_tenant(tenant_id)
        return [asdict(sub) for sub in subscriptions]

    @router.post("/subscriptions")
    async def create_subscription_endpoint(
        request: CreateSubscriptionRequest
    ):
        """Create new webhook subscription"""
        subscription = await webhook_manager.create_subscription(
            resource=request.resource,
            change_types=request.change_types,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            client_state=request.client_state,
            include_resource_data=request.include_resource_data,
            expiration_hours=request.expiration_hours
        )
        return asdict(subscription)

    @router.put("/subscriptions/{subscription_id}/renew")
    async def renew_subscription_endpoint(
        subscription_id: str,
        extension_hours: int = 168
    ):
        """Renew webhook subscription"""
        subscription = await webhook_manager.renew_subscription(
            subscription_id, extension_hours
        )
        return asdict(subscription)

    @router.delete("/subscriptions/{subscription_id}")
    async def delete_subscription_endpoint(subscription_id: str):
        """Delete webhook subscription"""
        success = await webhook_manager.delete_subscription(subscription_id)
        return {"success": success, "subscription_id": subscription_id}

    return router