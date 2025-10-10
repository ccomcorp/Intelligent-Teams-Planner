"""
Enhanced Graph API data models
Story 2.1: Advanced Graph API models for batch operations, delta queries, etc.
"""

from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import uuid


class RequestMethod(str, Enum):
    """HTTP request methods"""
    GET = "GET"
    POST = "POST"
    PATCH = "PATCH"
    PUT = "PUT"
    DELETE = "DELETE"


class BatchRequestStatus(str, Enum):
    """Batch request status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationStatus(str, Enum):
    """Individual operation status"""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class BatchOperation:
    """Individual operation in a batch request"""
    id: str
    method: RequestMethod
    url: str
    body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    depends_on: Optional[List[str]] = None  # IDs of operations this depends on
    status: OperationStatus = OperationStatus.PENDING
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration: Optional[float] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class BatchRequest:
    """Batch request containing multiple operations"""
    id: str
    operations: List[BatchOperation]
    user_id: str
    tenant_id: Optional[str] = None
    status: BatchRequestStatus = BatchRequestStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    total_operations: int = field(init=False)
    successful_operations: int = 0
    failed_operations: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        self.total_operations = len(self.operations)

    def add_operation(self, operation: BatchOperation) -> None:
        """Add operation to batch"""
        self.operations.append(operation)
        self.total_operations = len(self.operations)

    def get_operation(self, operation_id: str) -> Optional[BatchOperation]:
        """Get operation by ID"""
        return next((op for op in self.operations if op.id == operation_id), None)

    def get_pending_operations(self) -> List[BatchOperation]:
        """Get operations that are still pending"""
        return [op for op in self.operations if op.status == OperationStatus.PENDING]

    def get_completed_operations(self) -> List[BatchOperation]:
        """Get completed operations (success or error)"""
        return [op for op in self.operations if op.status in [OperationStatus.SUCCESS, OperationStatus.ERROR]]

    def is_complete(self) -> bool:
        """Check if all operations are complete"""
        return all(op.status != OperationStatus.PENDING for op in self.operations)

    def update_statistics(self) -> None:
        """Update success/failure statistics"""
        self.successful_operations = sum(1 for op in self.operations if op.status == OperationStatus.SUCCESS)
        self.failed_operations = sum(1 for op in self.operations if op.status == OperationStatus.ERROR)

        if self.is_complete():
            self.status = BatchRequestStatus.COMPLETED
            if not self.completed_at:
                self.completed_at = datetime.now(timezone.utc)


@dataclass
class BatchResponse:
    """Response from a batch request"""
    batch_id: str
    responses: List[Dict[str, Any]]
    success_count: int = 0
    error_count: int = 0
    total_duration: Optional[float] = None

    def __post_init__(self):
        # Calculate statistics from responses
        for response in self.responses:
            if response.get("status", 0) < 400:
                self.success_count += 1
            else:
                self.error_count += 1


@dataclass
class DeltaToken:
    """Delta query token for tracking changes"""
    resource_type: str
    resource_id: Optional[str]
    token: str
    user_id: str
    tenant_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if token is expired"""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def update_last_used(self) -> None:
        """Update last used timestamp"""
        self.last_used = datetime.now(timezone.utc)


@dataclass
class ResourceChange:
    """Represents a change to a resource from delta query"""
    change_type: str  # created, updated, deleted
    resource_type: str  # task, plan, bucket, etc.
    resource_id: str
    resource_data: Dict[str, Any]
    change_time: datetime
    etag: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeltaResult:
    """Result from a delta query"""
    delta_token: str
    next_delta_token: Optional[str]
    changes: List[ResourceChange]
    has_more_changes: bool = False
    total_changes: int = field(init=False)

    def __post_init__(self):
        self.total_changes = len(self.changes)


@dataclass
class WebhookSubscription:
    """Webhook subscription data"""
    id: str
    resource: str
    change_types: List[str]
    notification_url: str
    client_state: Optional[str] = None
    lifecycle_notification_url: Optional[str] = None
    expiration_date_time: Optional[datetime] = None
    creator_id: Optional[str] = None
    latest_supported_tls_version: Optional[str] = None
    encryption_certificate: Optional[str] = None
    encryption_certificate_id: Optional[str] = None
    include_resource_data: bool = False
    application_id: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_notification: Optional[datetime] = None
    notification_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if subscription is expired"""
        if not self.expiration_date_time:
            return False
        return datetime.now(timezone.utc) > self.expiration_date_time

    def needs_renewal(self, buffer_hours: int = 24) -> bool:
        """Check if subscription needs renewal within buffer time"""
        if not self.expiration_date_time:
            return False
        buffer_time = datetime.now(timezone.utc).timestamp() + (buffer_hours * 3600)
        return self.expiration_date_time.timestamp() < buffer_time

    def update_notification_stats(self) -> None:
        """Update notification statistics"""
        self.notification_count += 1
        self.last_notification = datetime.now(timezone.utc)


@dataclass
class WebhookNotification:
    """Webhook notification data"""
    subscription_id: str
    client_state: Optional[str]
    change_type: str
    resource: str
    resource_data: Optional[Dict[str, Any]] = None
    lifecycle_event: Optional[str] = None
    subscription_expiration_date_time: Optional[datetime] = None
    tenant_id: Optional[str] = None
    received_at: datetime = field(default_factory=datetime.utcnow)
    processed: bool = False
    processing_error: Optional[str] = None


@dataclass
class TenantContext:
    """Multi-tenant context information"""
    tenant_id: str
    tenant_name: Optional[str] = None
    client_id: str = ""
    client_secret: str = ""
    authority: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = None
    usage_count: int = 0
    rate_limit_config: Dict[str, Any] = field(default_factory=dict)

    def update_usage(self) -> None:
        """Update usage statistics"""
        self.usage_count += 1
        self.last_used = datetime.now(timezone.utc)


@dataclass
class PermissionScope:
    """Permission scope definition"""
    scope: str
    permission_type: str  # application, delegated
    description: str
    required: bool = False
    admin_consent_required: bool = False


@dataclass
class UserPermissions:
    """User permissions context"""
    user_id: str
    tenant_id: Optional[str] = None
    granted_scopes: List[str] = field(default_factory=list)
    effective_permissions: Dict[str, bool] = field(default_factory=dict)
    last_validated: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    def has_permission(self, scope: str) -> bool:
        """Check if user has specific permission"""
        return scope in self.granted_scopes

    def add_permission(self, scope: str) -> None:
        """Add permission to user"""
        if scope not in self.granted_scopes:
            self.granted_scopes.append(scope)
            self.effective_permissions[scope] = True


@dataclass
class RateLimitInfo:
    """Rate limit information"""
    endpoint: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    requests_remaining: int = 0
    reset_time: Optional[datetime] = None
    window_start: Optional[datetime] = None
    window_size_seconds: int = 60
    total_requests: int = 0
    requests_used: int = 0

    def is_exhausted(self) -> bool:
        """Check if rate limit is exhausted"""
        return self.requests_remaining <= 0

    def time_until_reset(self) -> Optional[float]:
        """Get seconds until rate limit resets"""
        if not self.reset_time:
            return None
        return max(0, (self.reset_time - datetime.now(timezone.utc)).total_seconds())


@dataclass
class ErrorContext:
    """Error context for detailed error handling"""
    error_code: str
    error_message: str
    status_code: int
    correlation_id: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    operation: Optional[str] = None
    endpoint: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    retry_count: int = 0
    is_transient: bool = False
    suggested_action: Optional[str] = None
    additional_details: Dict[str, Any] = field(default_factory=dict)


# Type aliases for better readability
BatchOperationList = List[BatchOperation]
WebhookSubscriptionList = List[WebhookSubscription]
ResourceChangeList = List[ResourceChange]
PermissionScopeList = List[PermissionScope]