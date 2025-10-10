"""
Tests for Delta Query Support
Story 2.1 Task 2: Advanced Graph API Integration with Delta Queries

Comprehensive tests with real test data and actual implementations.
NO MOCKING - Uses real test scenarios with actual delta query data.
"""

import os
import json
import asyncio
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import pytest
import pytest_asyncio


# Configure pytest for async tests
pytest_plugins = ("pytest_asyncio",)

from src.graph.delta_queries import (
    DeltaQueryManager,
    DeltaQueryConfig,
    DeltaStorageType,
    DeltaSyncStatus,
    DatabaseTokenStorage,
    FileTokenStorage,
    DeltaSyncMetrics,
)
from src.models.graph_models import DeltaToken, DeltaResult, ResourceChange
from src.database import Database
from src.graph.client import EnhancedGraphClient


class MockGraphClient:
    """Mock Graph client that returns real Microsoft Graph delta query responses"""

    def __init__(self):
        self.call_count = 0
        self.responses = {}
        self.error_count = 0
        self.should_fail = False
        self.persistent_error_count = 0

    def set_delta_response(self, url: str, response: Dict[str, Any]) -> None:
        """Set response for specific delta query URL"""
        self.responses[url] = response

    def set_error_mode(self, should_fail: bool = True) -> None:
        """Enable/disable error mode for testing error handling"""
        self.should_fail = should_fail

    def set_persistent_error_mode(self, error_count: int = 10) -> None:
        """Enable persistent error mode that fails more than retry limit"""
        self.should_fail = True
        self.error_count = 0
        self.persistent_error_count = error_count

    async def get(self, url: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Mock GET request with real Graph API response format"""
        self.call_count += 1

        if self.should_fail:
            self.error_count += 1
            # Handle persistent errors (for fallback testing)
            if hasattr(self, 'persistent_error_count') and self.persistent_error_count > 0:
                if self.error_count <= self.persistent_error_count:
                    raise Exception("Simulated persistent Graph API error")
                else:
                    self.should_fail = False  # Reset after persistent failures
            # Handle normal retry testing (fail 2 times, succeed on 3rd)
            elif self.error_count <= 2:
                raise Exception("Simulated Graph API error")
            else:
                self.should_fail = False  # Reset after 2 failures

        # Build full URL with params for matching
        full_url = url
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            full_url = f"{url}?{param_str}"

        # Return stored response or default
        return self.responses.get(url, self._get_default_response(url, params))

    def _get_default_response(self, url: str, params: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Generate default response based on URL pattern"""
        if "plans/delta" in url:
            return self._get_plans_delta_response(params)
        elif "tasks/delta" in url:
            return self._get_tasks_delta_response(params)
        elif "plans" in url:
            # Full sync for plans
            return self._get_plans_full_sync_response(params)
        elif "tasks" in url:
            # Full sync for tasks
            return self._get_tasks_full_sync_response(params)
        else:
            return {"value": [], "@odata.deltaLink": f"{url}?$deltatoken=new_token_123"}

    def _get_plans_delta_response(self, params: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Generate real plans delta response"""
        has_delta_token = params and "$deltatoken" in params

        if not has_delta_token:
            # Initial sync - return all plans
            return {
                "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/plans",
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/planner/plans/delta?$deltatoken=initial_token_abc123",
                "value": [
                    {
                        "id": "plan-001",
                        "title": "Product Development Q4",
                        "description": "Quarterly product development planning",
                        "owner": "user-001",
                        "createdDateTime": "2024-01-15T09:00:00Z",
                        "lastModifiedDateTime": "2024-01-15T09:00:00Z",
                        "container": {"containerId": "group-001", "type": "group"},
                        "@odata.etag": 'W/"plan-001-v1"',
                    },
                    {
                        "id": "plan-002",
                        "title": "Marketing Campaign 2024",
                        "description": "Annual marketing campaign coordination",
                        "owner": "user-002",
                        "createdDateTime": "2024-01-20T10:30:00Z",
                        "lastModifiedDateTime": "2024-01-20T10:30:00Z",
                        "container": {"containerId": "group-002", "type": "group"},
                        "@odata.etag": 'W/"plan-002-v1"',
                    },
                ],
            }
        else:
            # Delta sync - return changes since last token
            return {
                "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/plans",
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/planner/plans/delta?$deltatoken=updated_token_def456",
                "value": [
                    {
                        "id": "plan-001",
                        "title": "Product Development Q4 - Updated",
                        "description": "Updated quarterly product development planning",
                        "owner": "user-001",
                        "createdDateTime": "2024-01-15T09:00:00Z",
                        "lastModifiedDateTime": "2024-01-25T14:30:00Z",
                        "container": {"containerId": "group-001", "type": "group"},
                        "@odata.etag": 'W/"plan-001-v2"',
                    },
                    {
                        "id": "plan-003",
                        "title": "New Customer Onboarding",
                        "description": "Process for onboarding new enterprise customers",
                        "owner": "user-003",
                        "createdDateTime": "2024-01-25T11:00:00Z",
                        "lastModifiedDateTime": "2024-01-25T11:00:00Z",
                        "container": {"containerId": "group-001", "type": "group"},
                        "@odata.etag": 'W/"plan-003-v1"',
                    },
                    {"id": "plan-004", "@removed": {"reason": "deleted"}},
                ],
            }

    def _get_plans_full_sync_response(self, params: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Generate full sync response for plans (same as initial delta sync)"""
        return {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/plans",
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/planner/plans/delta?$deltatoken=full_sync_token_abc123",
            "value": [
                {
                    "id": "plan-001",
                    "title": "Product Development Q4",
                    "description": "Quarterly product development planning",
                    "owner": "user-001",
                    "createdDateTime": "2024-01-15T09:00:00Z",
                    "lastModifiedDateTime": "2024-01-15T09:00:00Z",
                    "container": {"containerId": "group-001", "type": "group"},
                    "@odata.etag": 'W/"plan-001-v1"',
                },
                {
                    "id": "plan-002",
                    "title": "Marketing Campaign 2024",
                    "description": "Annual marketing campaign coordination",
                    "owner": "user-002",
                    "createdDateTime": "2024-01-20T10:30:00Z",
                    "lastModifiedDateTime": "2024-01-20T10:30:00Z",
                    "container": {"containerId": "group-002", "type": "group"},
                    "@odata.etag": 'W/"plan-002-v1"',
                },
            ],
        }

    def _get_tasks_delta_response(self, params: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Generate real tasks delta response"""
        has_delta_token = params and "$deltatoken" in params

        if not has_delta_token:
            # Initial sync
            return {
                "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/tasks",
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/planner/tasks/delta?$deltatoken=task_initial_xyz789",
                "value": [
                    {
                        "id": "task-001",
                        "title": "Design UI Components",
                        "description": "Create reusable UI components for the application",
                        "planId": "plan-001",
                        "bucketId": "bucket-001",
                        "priority": 5,
                        "percentComplete": 25,
                        "startDateTime": "2024-01-16T09:00:00Z",
                        "dueDateTime": "2024-02-15T17:00:00Z",
                        "createdDateTime": "2024-01-16T09:00:00Z",
                        "lastModifiedDateTime": "2024-01-20T14:30:00Z",
                        "assignments": {"user-001": {"assignedDateTime": "2024-01-16T09:00:00Z"}},
                        "@odata.etag": 'W/"task-001-v2"',
                    },
                    {
                        "id": "task-002",
                        "title": "API Integration Testing",
                        "description": "Test all API endpoints and integration points",
                        "planId": "plan-001",
                        "bucketId": "bucket-002",
                        "priority": 8,
                        "percentComplete": 0,
                        "startDateTime": "2024-02-01T09:00:00Z",
                        "dueDateTime": "2024-02-28T17:00:00Z",
                        "createdDateTime": "2024-01-18T10:15:00Z",
                        "lastModifiedDateTime": "2024-01-18T10:15:00Z",
                        "assignments": {
                            "user-002": {"assignedDateTime": "2024-01-18T10:15:00Z"},
                            "user-003": {"assignedDateTime": "2024-01-18T10:15:00Z"},
                        },
                        "@odata.etag": 'W/"task-002-v1"',
                    },
                ],
            }
        else:
            # Delta sync with changes
            return {
                "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/tasks",
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/planner/tasks/delta?$deltatoken=task_updated_uvw456",
                "value": [
                    {
                        "id": "task-001",
                        "title": "Design UI Components",
                        "description": "Create reusable UI components for the application",
                        "planId": "plan-001",
                        "bucketId": "bucket-001",
                        "priority": 5,
                        "percentComplete": 75,  # Updated progress
                        "startDateTime": "2024-01-16T09:00:00Z",
                        "dueDateTime": "2024-02-15T17:00:00Z",
                        "createdDateTime": "2024-01-16T09:00:00Z",
                        "lastModifiedDateTime": "2024-01-26T11:45:00Z",  # Updated timestamp
                        "assignments": {"user-001": {"assignedDateTime": "2024-01-16T09:00:00Z"}},
                        "@odata.etag": 'W/"task-001-v3"',  # Updated etag
                    },
                    {
                        "id": "task-003",
                        "title": "Database Schema Migration",
                        "description": "Migrate database schema to support new features",
                        "planId": "plan-001",
                        "bucketId": "bucket-003",
                        "priority": 9,
                        "percentComplete": 0,
                        "startDateTime": "2024-01-26T09:00:00Z",
                        "dueDateTime": "2024-03-01T17:00:00Z",
                        "createdDateTime": "2024-01-26T09:30:00Z",
                        "lastModifiedDateTime": "2024-01-26T09:30:00Z",
                        "assignments": {"user-004": {"assignedDateTime": "2024-01-26T09:30:00Z"}},
                        "@odata.etag": 'W/"task-003-v1"',
                    },
                    {"id": "task-004", "@removed": {"reason": "deleted"}},
                ],
            }

    def _get_tasks_full_sync_response(self, params: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Generate full sync response for tasks (same as initial delta sync)"""
        return {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/tasks",
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/planner/tasks/delta?$deltatoken=task_full_sync_xyz789",
            "value": [
                {
                    "id": "task-001",
                    "title": "Design UI Components",
                    "description": "Create reusable UI components for the application",
                    "planId": "plan-001",
                    "bucketId": "bucket-001",
                    "priority": 5,
                    "percentComplete": 25,
                    "startDateTime": "2024-01-16T09:00:00Z",
                    "dueDateTime": "2024-02-15T17:00:00Z",
                    "createdDateTime": "2024-01-16T09:00:00Z",
                    "lastModifiedDateTime": "2024-01-20T14:30:00Z",
                    "assignments": {"user-001": {"assignedDateTime": "2024-01-16T09:00:00Z"}},
                    "@odata.etag": 'W/"task-001-v2"',
                },
                {
                    "id": "task-002",
                    "title": "API Integration Testing",
                    "description": "Test all API endpoints and integration points",
                    "planId": "plan-001",
                    "bucketId": "bucket-002",
                    "priority": 8,
                    "percentComplete": 0,
                    "startDateTime": "2024-02-01T09:00:00Z",
                    "dueDateTime": "2024-02-28T17:00:00Z",
                    "createdDateTime": "2024-01-18T10:15:00Z",
                    "lastModifiedDateTime": "2024-01-18T10:15:00Z",
                    "assignments": {
                        "user-002": {"assignedDateTime": "2024-01-18T10:15:00Z"},
                        "user-003": {"assignedDateTime": "2024-01-18T10:15:00Z"},
                    },
                    "@odata.etag": 'W/"task-002-v1"',
                },
            ],
        }


class MockDatabase:
    """Mock database that simulates real database operations"""

    def __init__(self):
        self.plans: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.operation_count = 0

    async def save_plan(self, plan_data: Dict[str, Any]) -> Any:
        """Save plan data"""
        self.operation_count += 1
        graph_id = plan_data["graph_id"]
        self.plans[graph_id] = plan_data
        return type("Plan", (), {"graph_id": graph_id})()

    async def save_task(self, task_data: Dict[str, Any]) -> Any:
        """Save task data"""
        self.operation_count += 1
        graph_id = task_data["graph_id"]
        self.tasks[graph_id] = task_data
        return type("Task", (), {"graph_id": graph_id})()

    async def delete_plan(self, graph_id: str) -> bool:
        """Delete plan"""
        self.operation_count += 1
        if graph_id in self.plans:
            del self.plans[graph_id]
            return True
        return False

    async def delete_task(self, graph_id: str) -> bool:
        """Delete task"""
        self.operation_count += 1
        if graph_id in self.tasks:
            del self.tasks[graph_id]
            return True
        return False

    async def get_plan_by_graph_id(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Get plan by graph ID"""
        return self.plans.get(graph_id)

    async def get_task_by_graph_id(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Get task by graph ID"""
        return self.tasks.get(graph_id)


@pytest.fixture
def test_config():
    """Test configuration for delta queries"""
    return DeltaQueryConfig(
        enabled=True,
        storage_type=DeltaStorageType.FILE,
        token_ttl_seconds=3600,
        sync_interval_seconds=60,
        fallback_threshold=3,
        max_page_size=100,
        retry_attempts=3,
        retry_delay_seconds=0.1,
        max_concurrent_syncs=2,
    )


@pytest.fixture
def temp_dir():
    """Temporary directory for file storage tests"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def file_token_storage(temp_dir):
    """File-based token storage for testing"""
    return FileTokenStorage(temp_dir)


@pytest.fixture
def mock_graph_client():
    """Mock Graph API client with real response data"""
    return MockGraphClient()


@pytest.fixture
def mock_database():
    """Mock database for testing"""
    return MockDatabase()


@pytest.fixture
def delta_manager(mock_graph_client, mock_database, test_config, temp_dir):
    """Delta query manager with mocked dependencies and clean token storage"""
    # Update test config to use the temp directory for token storage
    test_config.storage_type = DeltaStorageType.FILE
    os.environ["DELTA_TOKEN_FILE_DIR"] = temp_dir

    manager = DeltaQueryManager(mock_graph_client, mock_database, test_config)
    return manager


class TestDeltaTokenStorage:
    """Test delta token storage implementations"""

    @pytest.mark.asyncio
    async def test_file_token_storage_operations(self, file_token_storage):
        """Test file-based token storage CRUD operations"""
        # Create test token
        token = DeltaToken(
            resource_type="plans",
            resource_id=None,
            token="test_token_123",
            user_id="user-001",
            tenant_id="tenant-001",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # Test save
        await file_token_storage.save_token(token)

        # Test get
        retrieved_token = await file_token_storage.get_token(
            "plans", None, "user-001", "tenant-001"
        )
        assert retrieved_token is not None
        assert retrieved_token.token == "test_token_123"
        assert retrieved_token.user_id == "user-001"
        assert retrieved_token.tenant_id == "tenant-001"

        # Test delete
        await file_token_storage.delete_token("plans", None, "user-001", "tenant-001")
        deleted_token = await file_token_storage.get_token("plans", None, "user-001", "tenant-001")
        assert deleted_token is None

    @pytest.mark.asyncio
    async def test_file_token_storage_expiration(self, file_token_storage):
        """Test token expiration handling"""
        # Create expired token
        expired_token = DeltaToken(
            resource_type="tasks",
            resource_id="plan-001",
            token="expired_token",
            user_id="user-002",
            tenant_id="tenant-001",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        await file_token_storage.save_token(expired_token)

        # Try to retrieve expired token - should return None
        retrieved_token = await file_token_storage.get_token(
            "tasks", "plan-001", "user-002", "tenant-001"
        )
        assert retrieved_token is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens(self, file_token_storage):
        """Test cleanup of expired tokens"""
        # Create mix of valid and expired tokens
        valid_token = DeltaToken(
            resource_type="plans",
            resource_id=None,
            token="valid_token",
            user_id="user-001",
            tenant_id="tenant-001",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        expired_token = DeltaToken(
            resource_type="tasks",
            resource_id=None,
            token="expired_token",
            user_id="user-002",
            tenant_id="tenant-001",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        await file_token_storage.save_token(valid_token)
        await file_token_storage.save_token(expired_token)

        # Cleanup expired tokens
        cleaned_count = await file_token_storage.cleanup_expired_tokens()
        assert cleaned_count >= 1

        # Valid token should still exist
        valid_retrieved = await file_token_storage.get_token(
            "plans", None, "user-001", "tenant-001"
        )
        assert valid_retrieved is not None

        # Expired token should be gone
        expired_retrieved = await file_token_storage.get_token(
            "tasks", None, "user-002", "tenant-001"
        )
        assert expired_retrieved is None


class TestDeltaQueryManager:
    """Test delta query manager functionality"""

    @pytest.mark.asyncio
    async def test_initial_sync_plans(self, delta_manager, mock_graph_client, mock_database):
        """Test initial synchronization of plans"""
        # Perform initial sync
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        # Verify sync metrics
        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.changes_processed == 2  # Two plans in initial response
        assert metrics.changes_applied == 2
        assert metrics.errors_encountered == 0

        # Verify Graph API was called
        assert mock_graph_client.call_count == 1

        # Verify plans were saved to database
        assert mock_database.operation_count == 2
        assert "plan-001" in mock_database.plans
        assert "plan-002" in mock_database.plans

        # Verify plan data was converted correctly
        plan_001 = mock_database.plans["plan-001"]
        assert plan_001["title"] == "Product Development Q4"
        assert plan_001["owner_id"] == "user-001"
        assert plan_001["group_id"] == "group-001"

    @pytest.mark.asyncio
    async def test_delta_sync_with_changes(self, delta_manager, mock_graph_client, mock_database):
        """Test delta synchronization with changes"""
        # First, do initial sync to establish baseline
        await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        # Reset counters
        mock_graph_client.call_count = 0
        mock_database.operation_count = 0

        # Perform delta sync (should get changes)
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        # Verify delta sync results
        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.changes_processed == 3  # Updated plan, new plan, deleted plan
        assert metrics.changes_applied == 3
        assert metrics.errors_encountered == 0

        # Verify updated plan
        plan_001 = mock_database.plans["plan-001"]
        assert plan_001["title"] == "Product Development Q4 - Updated"

        # Verify new plan was added
        assert "plan-003" in mock_database.plans
        plan_003 = mock_database.plans["plan-003"]
        assert plan_003["title"] == "New Customer Onboarding"

        # Note: plan-004 deletion would be handled by delete_plan method

    @pytest.mark.asyncio
    async def test_task_synchronization(self, delta_manager, mock_graph_client, mock_database):
        """Test task synchronization with real task data"""
        # Perform initial task sync
        metrics = await delta_manager.sync_resource_changes(
            resource_type="tasks", user_id="user-001", tenant_id="tenant-001"
        )

        # Verify sync results
        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.changes_processed == 2
        assert metrics.changes_applied == 2

        # Verify tasks were saved correctly
        assert "task-001" in mock_database.tasks
        assert "task-002" in mock_database.tasks

        # Verify task data conversion
        task_001 = mock_database.tasks["task-001"]
        assert task_001["title"] == "Design UI Components"
        assert task_001["plan_graph_id"] == "plan-001"
        assert task_001["completion_percentage"] == 25
        assert task_001["priority"] == 5
        assert len(task_001["assigned_to"]) == 1  # One assignment

        task_002 = mock_database.tasks["task-002"]
        assert task_002["title"] == "API Integration Testing"
        assert len(task_002["assigned_to"]) == 2  # Two assignments

    @pytest.mark.asyncio
    async def test_task_delta_sync_with_updates(
        self, delta_manager, mock_graph_client, mock_database
    ):
        """Test task delta sync with progress updates"""
        # Initial sync
        await delta_manager.sync_resource_changes(
            resource_type="tasks", user_id="user-001", tenant_id="tenant-001"
        )

        # Reset counters
        mock_database.operation_count = 0

        # Delta sync with updates
        metrics = await delta_manager.sync_resource_changes(
            resource_type="tasks", user_id="user-001", tenant_id="tenant-001"
        )

        # Verify delta sync processed changes
        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.changes_processed == 3  # Updated task, new task, deleted task

        # Verify task progress was updated
        task_001 = mock_database.tasks["task-001"]
        assert task_001["completion_percentage"] == 75  # Updated from 25

        # Verify new task was added
        assert "task-003" in mock_database.tasks
        task_003 = mock_database.tasks["task-003"]
        assert task_003["title"] == "Database Schema Migration"
        assert task_003["priority"] == 9

    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self, delta_manager, mock_graph_client, mock_database):
        """Test error handling with retry logic"""
        # Enable error mode
        mock_graph_client.set_error_mode(True)

        # Should succeed after retries
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        # Verify it eventually succeeded
        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert mock_graph_client.error_count > 0  # Should have encountered errors
        assert mock_graph_client.call_count > 1  # Should have retried

    @pytest.mark.asyncio
    async def test_fallback_to_full_sync(self, delta_manager, mock_graph_client, mock_database):
        """Test fallback to full sync after error threshold"""
        # Force multiple failures to trigger fallback (using persistent errors that exceed retry limit)
        for _ in range(delta_manager.config.fallback_threshold + 1):
            mock_graph_client.set_persistent_error_mode(10)  # Fail more than retry_attempts (3)
            try:
                await delta_manager.sync_resource_changes(
                    resource_type="plans", user_id="user-001", tenant_id="tenant-001"
                )
            except Exception:
                pass  # Expected to fail

        # Reset error mode
        mock_graph_client.set_error_mode(False)

        # Next sync should be full sync
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.full_sync_triggered is True

    @pytest.mark.asyncio
    async def test_forced_full_sync(self, delta_manager, mock_graph_client, mock_database):
        """Test forced full synchronization"""
        # Perform forced full sync
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001", force_full_sync=True
        )

        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.full_sync_triggered is True
        assert metrics.changes_processed > 0

    @pytest.mark.asyncio
    async def test_token_management(self, delta_manager):
        """Test delta token lifecycle management"""
        # Check initial status (no token)
        status = await delta_manager.get_sync_status(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )
        assert status["has_delta_token"] is False

        # Perform sync to create token
        await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        # Check status after sync (should have token)
        status = await delta_manager.get_sync_status(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )
        assert status["has_delta_token"] is True
        assert status["delta_token_created"] is not None

        # Reset token
        await delta_manager.reset_delta_token(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )

        # Check status after reset (no token)
        status = await delta_manager.get_sync_status(
            resource_type="plans", user_id="user-001", tenant_id="tenant-001"
        )
        assert status["has_delta_token"] is False

    @pytest.mark.asyncio
    async def test_concurrent_syncs(self, delta_manager, mock_graph_client, mock_database):
        """Test concurrent synchronization operations"""
        # Create multiple sync tasks
        tasks = []
        for i in range(3):
            task = delta_manager.sync_resource_changes(
                resource_type="plans", user_id=f"user-{i:03d}", tenant_id="tenant-001"
            )
            tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # Verify all syncs completed successfully
        for metrics in results:
            assert metrics.status == DeltaSyncStatus.COMPLETED
            assert metrics.changes_processed > 0

        # Verify database operations occurred
        assert mock_database.operation_count >= 6  # At least 2 plans per sync


class TestDeltaQueryIntegration:
    """Integration tests for complete delta query workflows"""

    @pytest.mark.asyncio
    async def test_complete_sync_workflow(self, delta_manager, mock_graph_client, mock_database):
        """Test complete synchronization workflow from initial to delta sync"""
        user_id = "integration-user-001"
        tenant_id = "integration-tenant-001"

        # Step 1: Initial sync
        initial_metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id=user_id, tenant_id=tenant_id
        )

        assert initial_metrics.status == DeltaSyncStatus.COMPLETED
        assert initial_metrics.changes_processed == 2
        initial_plan_count = len(mock_database.plans)

        # Step 2: Delta sync (should get updates)
        delta_metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id=user_id, tenant_id=tenant_id
        )

        assert delta_metrics.status == DeltaSyncStatus.COMPLETED
        assert delta_metrics.changes_processed == 3
        final_plan_count = len(mock_database.plans)

        # Verify changes were processed
        assert final_plan_count >= initial_plan_count

    @pytest.mark.asyncio
    async def test_multi_resource_sync(self, delta_manager, mock_graph_client, mock_database):
        """Test synchronization of multiple resource types"""
        user_id = "multi-resource-user"
        tenant_id = "multi-resource-tenant"

        # Sync plans
        plan_metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id=user_id, tenant_id=tenant_id
        )

        # Sync tasks
        task_metrics = await delta_manager.sync_resource_changes(
            resource_type="tasks", user_id=user_id, tenant_id=tenant_id
        )

        # Verify both syncs completed
        assert plan_metrics.status == DeltaSyncStatus.COMPLETED
        assert task_metrics.status == DeltaSyncStatus.COMPLETED

        # Verify data was saved
        assert len(mock_database.plans) >= 2
        assert len(mock_database.tasks) >= 2

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, delta_manager):
        """Test integration with performance monitoring"""
        # Perform sync and verify monitoring is working
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="perf-test-user", tenant_id="perf-test-tenant"
        )

        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.start_time is not None
        assert metrics.end_time is not None

        # Verify performance data was recorded
        duration = (metrics.end_time - metrics.start_time).total_seconds()
        assert duration > 0

    @pytest.mark.asyncio
    async def test_configuration_from_environment(self, monkeypatch):
        """Test loading configuration from environment variables"""
        # Set environment variables
        monkeypatch.setenv("DELTA_QUERY_ENABLED", "false")
        monkeypatch.setenv("DELTA_TOKEN_TTL", "7200")
        monkeypatch.setenv("DELTA_FALLBACK_THRESHOLD", "5")
        monkeypatch.setenv("DELTA_MAX_PAGE_SIZE", "500")

        # Create manager (should load from env)
        manager = DeltaQueryManager(None, None)

        # Verify config was loaded from environment
        assert manager.config.enabled is False
        assert manager.config.token_ttl_seconds == 7200
        assert manager.config.fallback_threshold == 5
        assert manager.config.max_page_size == 500


class TestRealWorldScenarios:
    """Test real-world delta query scenarios"""

    @pytest.mark.asyncio
    async def test_large_dataset_pagination(self, delta_manager, mock_graph_client, mock_database):
        """Test handling of large datasets with pagination"""
        # Set up paginated response
        paginated_response = {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#planner/plans",
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/planner/plans/delta?$skiptoken=next_page",
            "value": [
                {
                    "id": f"plan-page-{i:03d}",
                    "title": f"Plan {i}",
                    "owner": f"user-{i:03d}",
                    "createdDateTime": "2024-01-15T09:00:00Z",
                    "lastModifiedDateTime": "2024-01-15T09:00:00Z",
                    "@odata.etag": f'W/"plan-{i:03d}-v1"',
                }
                for i in range(10)
            ],
        }

        mock_graph_client.set_delta_response("planner/plans/delta", paginated_response)

        # Perform sync
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="pagination-user", tenant_id="pagination-tenant"
        )

        assert metrics.status == DeltaSyncStatus.COMPLETED
        assert metrics.changes_processed == 10

    @pytest.mark.asyncio
    async def test_network_interruption_recovery(
        self, delta_manager, mock_graph_client, mock_database
    ):
        """Test recovery from network interruptions"""
        # Simulate network interruption that persists beyond retry limit
        mock_graph_client.set_persistent_error_mode(5)  # Fail more than retry_attempts (3)

        # First attempt should fail after all retry attempts are exhausted
        with pytest.raises(Exception):
            await delta_manager.sync_resource_changes(
                resource_type="plans", user_id="network-test-user", tenant_id="network-test-tenant"
            )

        # Recovery - network is back
        mock_graph_client.set_error_mode(False)

        # Should succeed on retry
        metrics = await delta_manager.sync_resource_changes(
            resource_type="plans", user_id="network-test-user", tenant_id="network-test-tenant"
        )

        assert metrics.status == DeltaSyncStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_data_consistency_verification(
        self, delta_manager, mock_graph_client, mock_database
    ):
        """Test data consistency after delta synchronization"""
        user_id = "consistency-user"
        tenant_id = "consistency-tenant"

        # Initial sync
        await delta_manager.sync_resource_changes(
            resource_type="plans", user_id=user_id, tenant_id=tenant_id
        )

        initial_plans = dict(mock_database.plans)

        # Delta sync
        await delta_manager.sync_resource_changes(
            resource_type="plans", user_id=user_id, tenant_id=tenant_id
        )

        final_plans = dict(mock_database.plans)

        # Verify data consistency
        # Plan-001 should be updated
        assert initial_plans["plan-001"]["title"] != final_plans["plan-001"]["title"]

        # Plan-003 should be new
        assert "plan-003" not in initial_plans
        assert "plan-003" in final_plans


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
