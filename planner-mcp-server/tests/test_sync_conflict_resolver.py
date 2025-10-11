"""
Comprehensive Tests for Sync Conflict Resolution System
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.sync.conflict_resolver import (
    ConflictDetector,
    ConflictResolver,
    ConflictManager,
    ConflictContext,
    ConflictType,
    ConflictSeverity,
    ResolutionStrategy,
    ResolutionResult
)


@pytest.fixture
def mock_database():
    """Mock database for testing"""
    db = Mock()
    db._connection_pool = Mock()
    db._connection_pool.acquire.return_value.__aenter__ = AsyncMock()
    db._connection_pool.acquire.return_value.__aexit__ = AsyncMock()
    return db


@pytest.fixture
def mock_cache_service():
    """Mock cache service for testing"""
    cache = Mock()
    cache.set = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.delete = AsyncMock()
    cache.lpush = AsyncMock()
    return cache


@pytest.fixture
def conflict_detector(mock_database, mock_cache_service):
    """Create conflict detector instance"""
    return ConflictDetector(mock_database, mock_cache_service)


@pytest.fixture
def conflict_resolver(mock_database, mock_cache_service):
    """Create conflict resolver instance"""
    return ConflictResolver(mock_database, mock_cache_service)


@pytest.fixture
def conflict_manager(mock_database, mock_cache_service):
    """Create conflict manager instance"""
    return ConflictManager(mock_database, mock_cache_service)


@pytest.fixture
def sample_task_local():
    """Sample local task version"""
    return {
        "id": "task-123",
        "title": "Local Task Title",
        "description": "Local description",
        "dueDateTime": "2024-02-15T10:00:00Z",
        "percentComplete": 50,
        "assignments": {"user1": {}, "user2": {}},
        "lastModifiedDateTime": "2024-02-10T15:30:00Z",
        "@odata.etag": "W/\"etag-local-123\""
    }


@pytest.fixture
def sample_task_remote():
    """Sample remote task version"""
    return {
        "id": "task-123",
        "title": "Remote Task Title",
        "description": "Remote description updated",
        "dueDateTime": "2024-02-16T10:00:00Z",
        "percentComplete": 75,
        "assignments": {"user1": {}, "user3": {}},
        "lastModifiedDateTime": "2024-02-10T16:00:00Z",
        "@odata.etag": "W/\"etag-remote-456\""
    }


class TestConflictDetector:
    """Test conflict detection functionality"""

    @pytest.mark.asyncio
    async def test_detect_no_conflict_same_etag(self, conflict_detector, sample_task_local):
        """Test no conflict when etags are the same"""
        # Same etag - no conflict
        remote_version = sample_task_local.copy()

        conflict = await conflict_detector.detect_conflict(
            "task", "task-123", sample_task_local, remote_version, "user1"
        )

        assert conflict is None

    @pytest.mark.asyncio
    async def test_detect_conflict_different_etags(self, conflict_detector, sample_task_local, sample_task_remote):
        """Test conflict detection with different etags"""
        with patch.object(conflict_detector, '_store_conflict', new=AsyncMock()):
            conflict = await conflict_detector.detect_conflict(
                "task", "task-123", sample_task_local, sample_task_remote, "user1"
            )

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.CONCURRENT_EDIT
        assert conflict.resource_type == "task"
        assert conflict.resource_id == "task-123"
        assert len(conflict.conflicting_fields) > 0

    @pytest.mark.asyncio
    async def test_detect_high_severity_conflict(self, conflict_detector):
        """Test detection of high severity conflicts"""
        local_version = {
            "id": "task-123",
            "title": "Original Title",
            "planId": "plan-456",
            "@odata.etag": "W/\"etag-1\""
        }

        remote_version = {
            "id": "task-123",
            "title": "Completely Different Title",
            "planId": "plan-789",  # Critical field changed
            "@odata.etag": "W/\"etag-2\""
        }

        with patch.object(conflict_detector, '_store_conflict', new=AsyncMock()):
            conflict = await conflict_detector.detect_conflict(
                "task", "task-123", local_version, remote_version, "user1"
            )

        assert conflict is not None
        assert conflict.severity == ConflictSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_find_conflicting_fields(self, conflict_detector, sample_task_local, sample_task_remote):
        """Test identification of specific conflicting fields"""
        conflicting_fields = await conflict_detector._find_conflicting_fields(
            "task", sample_task_local, sample_task_remote
        )

        expected_fields = ["title", "description", "dueDateTime", "percentComplete", "assignments"]
        assert all(field in conflicting_fields for field in expected_fields)

    @pytest.mark.asyncio
    async def test_dependency_conflict_detection(self, conflict_detector):
        """Test detection of dependency conflicts"""
        local_version = {"id": "task-123", "planId": "plan-456"}
        remote_version = {"id": "task-123", "planId": "plan-999"}  # Non-existent plan

        # Mock plan existence check
        with patch.object(conflict_detector, '_check_plan_exists', return_value=False):
            with patch.object(conflict_detector, '_store_conflict', new=AsyncMock()):
                conflict = await conflict_detector.detect_conflict(
                    "task", "task-123", local_version, remote_version, "user1"
                )

        assert conflict is not None
        assert conflict.conflict_type == ConflictType.DEPENDENCY_CONFLICT

    def test_values_equal_simple_types(self, conflict_detector):
        """Test value equality for simple types"""
        assert conflict_detector._values_equal("test", "test")
        assert conflict_detector._values_equal(123, 123)
        assert conflict_detector._values_equal(True, True)
        assert not conflict_detector._values_equal("test", "different")
        assert not conflict_detector._values_equal(123, 456)

    def test_values_equal_complex_types(self, conflict_detector):
        """Test value equality for complex types"""
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"a": 1, "b": {"c": 2}}
        dict3 = {"a": 1, "b": {"c": 3}}

        assert conflict_detector._values_equal(dict1, dict2)
        assert not conflict_detector._values_equal(dict1, dict3)

        list1 = [1, 2, 3]
        list2 = [3, 1, 2]  # Different order
        list3 = [1, 2, 4]

        assert conflict_detector._values_equal(list1, list2)  # Order shouldn't matter
        assert not conflict_detector._values_equal(list1, list3)


class TestConflictResolver:
    """Test conflict resolution functionality"""

    @pytest.mark.asyncio
    async def test_last_write_wins_strategy(self, conflict_resolver):
        """Test last write wins resolution strategy"""
        conflict = ConflictContext(
            conflict_id="test-conflict",
            conflict_type=ConflictType.CONCURRENT_EDIT,
            severity=ConflictSeverity.LOW,
            resource_type="task",
            resource_id="task-123",
            tenant_id="tenant-1",
            user_id="user-1",
            local_version={"id": "task-123", "title": "Local Title"},
            remote_version={"id": "task-123", "title": "Remote Title"},
            local_timestamp=datetime(2024, 2, 10, 15, 0, 0, tzinfo=timezone.utc),
            remote_timestamp=datetime(2024, 2, 10, 16, 0, 0, tzinfo=timezone.utc)  # Later
        )

        with patch.object(conflict_resolver, '_update_conflict_resolution', new=AsyncMock()):
            result = await conflict_resolver._resolve_last_write_wins(conflict)

        assert result.success
        assert result.strategy_used == ResolutionStrategy.LAST_WRITE_WINS
        assert result.resolved_version["title"] == "Remote Title"  # Remote was later

    @pytest.mark.asyncio
    async def test_merge_fields_strategy(self, conflict_resolver):
        """Test merge fields resolution strategy"""
        conflict = ConflictContext(
            conflict_id="test-conflict",
            conflict_type=ConflictType.CONCURRENT_EDIT,
            severity=ConflictSeverity.MEDIUM,
            resource_type="task",
            resource_id="task-123",
            tenant_id="tenant-1",
            user_id="user-1",
            local_version={
                "id": "task-123",
                "title": "Local Title",
                "description": "Local description",
                "percentComplete": 50
            },
            remote_version={
                "id": "task-123",
                "title": "Remote Title",
                "description": "Remote description",
                "percentComplete": 75
            },
            conflicting_fields=["title", "description"]
        )

        with patch.object(conflict_resolver, '_update_conflict_resolution', new=AsyncMock()):
            result = await conflict_resolver._resolve_merge_fields(conflict)

        assert result.success
        assert result.strategy_used == ResolutionStrategy.MERGE_FIELDS
        # Should merge non-conflicting fields
        assert result.resolved_version["percentComplete"] == 75  # From remote
        assert "@odata.etag" in result.resolved_version  # Should have new etag

    @pytest.mark.asyncio
    async def test_manual_resolution_preparation(self, conflict_resolver):
        """Test preparation for manual conflict resolution"""
        conflict = ConflictContext(
            conflict_id="test-conflict",
            conflict_type=ConflictType.CONCURRENT_EDIT,
            severity=ConflictSeverity.CRITICAL,
            resource_type="task",
            resource_id="task-123",
            tenant_id="tenant-1",
            user_id="user-1",
            local_version={"id": "task-123", "title": "Local Title"},
            remote_version={"id": "task-123", "title": "Remote Title"}
        )

        with patch.object(conflict_resolver, '_store_manual_resolution_data', new=AsyncMock()):
            with patch.object(conflict_resolver, '_update_conflict_resolution', new=AsyncMock()):
                result = await conflict_resolver._prepare_manual_resolution(conflict)

        assert result.success
        assert result.requires_manual_intervention
        assert result.strategy_used == ResolutionStrategy.MANUAL_RESOLUTION

    @pytest.mark.asyncio
    async def test_merge_conflicting_field_assignments(self, conflict_resolver):
        """Test merging assignment fields"""
        local_assignments = {"user1": {}, "user2": {}}
        remote_assignments = {"user2": {}, "user3": {}}

        merged = await conflict_resolver._merge_conflicting_field(
            "assignments", local_assignments, remote_assignments, "task"
        )

        expected = {"user1": {}, "user2": {}, "user3": {}}
        assert merged == expected

    @pytest.mark.asyncio
    async def test_merge_conflicting_field_percent_complete(self, conflict_resolver):
        """Test merging percent complete fields (use max)"""
        merged = await conflict_resolver._merge_conflicting_field(
            "percentComplete", 50, 75, "task"
        )

        assert merged == 75

    @pytest.mark.asyncio
    async def test_merge_conflicting_field_description(self, conflict_resolver):
        """Test merging description fields"""
        merged = await conflict_resolver._merge_conflicting_field(
            "description", "Local desc", "Remote desc", "task"
        )

        assert "Local desc" in merged
        assert "Remote desc" in merged
        assert "[Merged]" in merged


class TestConflictManager:
    """Test conflict manager integration"""

    @pytest.mark.asyncio
    async def test_handle_sync_conflict_no_conflict(self, conflict_manager):
        """Test handling when no conflict is detected"""
        local_version = {"id": "task-123", "title": "Same Title", "@odata.etag": "W/\"same-etag\""}
        remote_version = {"id": "task-123", "title": "Same Title", "@odata.etag": "W/\"same-etag\""}

        with patch.object(conflict_manager.detector, 'detect_conflict', return_value=None):
            success, resolved_version, conflict_id = await conflict_manager.handle_sync_conflict(
                "task", "task-123", local_version, remote_version, "user1"
            )

        assert success
        assert resolved_version == remote_version
        assert conflict_id is None

    @pytest.mark.asyncio
    async def test_handle_sync_conflict_with_resolution(self, conflict_manager):
        """Test handling conflict with successful resolution"""
        local_version = {"id": "task-123", "title": "Local Title"}
        remote_version = {"id": "task-123", "title": "Remote Title"}

        mock_conflict = ConflictContext(
            conflict_id="test-conflict",
            conflict_type=ConflictType.CONCURRENT_EDIT,
            severity=ConflictSeverity.LOW,
            resource_type="task",
            resource_id="task-123",
            tenant_id=None,
            user_id="user1",
            local_version=local_version,
            remote_version=remote_version
        )

        mock_result = ResolutionResult(
            conflict_id="test-conflict",
            strategy_used=ResolutionStrategy.LAST_WRITE_WINS,
            resolved_version=remote_version,
            success=True
        )

        with patch.object(conflict_manager.detector, 'detect_conflict', return_value=mock_conflict):
            with patch.object(conflict_manager.resolver, 'resolve_conflict', return_value=mock_result):
                success, resolved_version, conflict_id = await conflict_manager.handle_sync_conflict(
                    "task", "task-123", local_version, remote_version, "user1"
                )

        assert success
        assert resolved_version == remote_version
        assert conflict_id == "test-conflict"

    @pytest.mark.asyncio
    async def test_get_pending_manual_resolutions(self, conflict_manager):
        """Test getting pending manual resolutions"""
        mock_rows = [
            {
                "conflict_id": "conflict-1",
                "conflict_type": "concurrent_edit",
                "severity": "high",
                "resource_type": "task",
                "resource_id": "task-123",
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "conflicting_fields": '["title", "description"]',
                "created_at": datetime.now(timezone.utc)
            }
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        conflict_manager.database._connection_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        conflicts = await conflict_manager.get_pending_manual_resolutions()

        assert len(conflicts) == 1
        assert conflicts[0]["conflict_id"] == "conflict-1"
        assert isinstance(conflicts[0]["conflicting_fields"], list)

    @pytest.mark.asyncio
    async def test_get_conflict_statistics(self, conflict_manager):
        """Test getting conflict statistics"""
        mock_rows = [
            {
                "conflict_type": "concurrent_edit",
                "severity": "high",
                "resolution_strategy": "last_write_wins",
                "count": 5,
                "avg_resolution_time": 120.5
            },
            {
                "conflict_type": "dependency_conflict",
                "severity": "critical",
                "resolution_strategy": "rollback",
                "count": 2,
                "avg_resolution_time": 300.0
            }
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        conflict_manager.database._connection_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        stats = await conflict_manager.get_conflict_statistics()

        assert stats["total_conflicts"] == 7
        assert stats["by_type"]["concurrent_edit"] == 5
        assert stats["by_severity"]["high"] == 5
        assert stats["by_resolution"]["last_write_wins"] == 5


class TestConflictResolutionIntegration:
    """Integration tests for conflict resolution system"""

    @pytest.mark.asyncio
    async def test_complete_conflict_resolution_flow(self, conflict_manager):
        """Test complete conflict resolution flow"""
        # Setup test data
        local_version = {
            "id": "task-123",
            "title": "Local Task",
            "description": "Local description",
            "percentComplete": 25,
            "lastModifiedDateTime": "2024-02-10T15:00:00Z",
            "@odata.etag": "W/\"local-etag\""
        }

        remote_version = {
            "id": "task-123",
            "title": "Remote Task",
            "description": "Remote description",
            "percentComplete": 75,
            "lastModifiedDateTime": "2024-02-10T16:00:00Z",
            "@odata.etag": "W/\"remote-etag\""
        }

        # Mock database operations
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)  # No existing plan check
        conflict_manager.database._connection_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        # Test conflict detection and resolution
        success, resolved_version, conflict_id = await conflict_manager.handle_sync_conflict(
            "task", "task-123", local_version, remote_version, "user1", "tenant1"
        )

        # Verify results
        assert success
        assert resolved_version is not None
        assert conflict_id is not None

        # Should prefer remote version (last write wins with later timestamp)
        assert resolved_version["title"] == "Remote Task"
        assert resolved_version["percentComplete"] == 75

    @pytest.mark.asyncio
    async def test_conflict_resolution_with_custom_strategy(self, conflict_manager):
        """Test conflict resolution with custom strategy"""
        local_version = {"id": "task-123", "title": "Local", "percentComplete": 100}
        remote_version = {"id": "task-123", "title": "Remote", "percentComplete": 50}

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        conflict_manager.database._connection_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        # Force merge strategy
        success, resolved_version, conflict_id = await conflict_manager.handle_sync_conflict(
            "task", "task-123", local_version, remote_version, "user1", "tenant1",
            preferred_strategy=ResolutionStrategy.MERGE_FIELDS
        )

        assert success
        assert resolved_version is not None
        # Should have merged non-conflicting fields appropriately

    @pytest.mark.asyncio
    async def test_error_handling_in_conflict_detection(self, conflict_manager):
        """Test error handling during conflict detection"""
        local_version = {"id": "task-123", "title": "Local"}
        remote_version = {"id": "task-123", "title": "Remote"}

        # Mock database error
        conflict_manager.database._connection_pool.acquire.side_effect = Exception("Database error")

        success, resolved_version, conflict_id = await conflict_manager.handle_sync_conflict(
            "task", "task-123", local_version, remote_version, "user1"
        )

        # Should fall back gracefully
        assert not success
        assert resolved_version == local_version  # Falls back to local
        assert conflict_id is None


@pytest.mark.asyncio
async def test_concurrent_conflict_detection():
    """Test concurrent conflict detection scenarios"""
    # This would test multiple simultaneous conflict detections
    # to ensure thread safety and proper isolation
    pass


@pytest.mark.asyncio
async def test_conflict_resolution_performance():
    """Test performance of conflict resolution under load"""
    # This would test performance with many conflicts
    # to ensure the system scales appropriately
    pass


if __name__ == "__main__":
    pytest.main([__file__])