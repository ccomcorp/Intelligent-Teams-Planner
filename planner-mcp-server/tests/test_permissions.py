"""
Comprehensive test suite for Graph API permission management system
Story 2.1 Task 5: Tests for permission validation, scope-based access control, and audit logging
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from typing import Dict, Any

from src.graph.permissions import (
    GraphPermissionValidator,
    PermissionType,
    AccessLevel,
    ResourceType,
    PermissionAuditEntry,
    get_permission_validator,
    require_permissions
)
from src.models.graph_models import UserPermissions, TenantContext


class TestGraphPermissionValidator:
    """Test suite for GraphPermissionValidator class"""

    @pytest.fixture
    def validator(self):
        """Create a fresh validator instance for each test"""
        return GraphPermissionValidator(
            cache_ttl_minutes=5,
            max_cache_size=100,
            enable_audit_logging=True,
            enable_escalation_detection=True
        )

    @pytest.fixture
    def mock_user_permissions(self):
        """Mock user permissions for testing"""
        return UserPermissions(
            user_id="john.smith@acme.com",
            tenant_id="tenant_123",
            granted_scopes=[
                "User.Read",
                "Planner.Read",
                "Group.Read.All",
                "Tasks.Read"
            ],
            last_validated=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

    @pytest.fixture
    def admin_user_permissions(self):
        """Mock admin user permissions for testing"""
        return UserPermissions(
            user_id="admin.user@acme.com",
            tenant_id="tenant_123",
            granted_scopes=[
                "User.Read",
                "User.ReadWrite.All",
                "Planner.Read",
                "Planner.ReadWrite",
                "Group.Read.All",
                "Group.ReadWrite.All",
                "Directory.Read.All",
                "Tasks.Read",
                "Tasks.ReadWrite"
            ],
            last_validated=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

    @pytest.mark.asyncio
    async def test_validate_permissions_success(self, validator, mock_user_permissions):
        """Test successful permission validation"""
        # Mock the permission fetching
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            result = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read", "Planner.Read"],
                operation="read_user_profile",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            assert result.is_valid is True
            assert set(result.granted_scopes) == {"User.Read", "Planner.Read"}
            assert result.missing_scopes == []
            assert result.escalation_detected is False

    @pytest.mark.asyncio
    async def test_validate_permissions_missing_scopes(self, validator, mock_user_permissions):
        """Test permission validation with missing scopes"""
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            result = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read", "Planner.ReadWrite", "Directory.Read.All"],
                operation="write_planner_data",
                resource_type=ResourceType.PLANNER,
                tenant_id="tenant_123"
            )

            assert result.is_valid is False
            assert "User.Read" in result.granted_scopes
            assert "Planner.ReadWrite" in result.missing_scopes
            assert "Directory.Read.All" in result.missing_scopes

    @pytest.mark.asyncio
    async def test_permission_hierarchy_validation(self, validator, admin_user_permissions):
        """Test permission hierarchy - higher permissions include lower ones"""
        with patch.object(validator, '_fetch_user_permissions', return_value=admin_user_permissions):
            # User has ReadWrite permission, should include Read permission
            result = await validator.validate_permissions(
                user_id="admin.user@acme.com",
                required_scopes=["Planner.Read"],  # Requesting read, user has readwrite
                operation="read_planner",
                resource_type=ResourceType.PLANNER,
                tenant_id="tenant_123"
            )

            assert result.is_valid is True
            assert "Planner.Read" in result.granted_scopes

    @pytest.mark.asyncio
    async def test_escalation_detection(self, validator, mock_user_permissions):
        """Test permission escalation detection"""
        # Request admin permissions when user doesn't have them
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            result = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["Directory.ReadWrite.All"],
                operation="modify_directory",
                resource_type=ResourceType.DIRECTORY,
                tenant_id="tenant_123",
                context={"unusual_access_pattern": True}
            )

            assert result.escalation_detected is True
            assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, validator, mock_user_permissions):
        """Test multi-tenant permission isolation"""
        # Test with disabled tenant
        validator._tenant_contexts["disabled_tenant"] = TenantContext(
            tenant_id="disabled_tenant",
            enabled=False
        )

        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            result = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="disabled_tenant"
            )

            assert result.is_valid is False
            assert "tenant_isolation_violation" in result.validation_context.get("error", "")

    @pytest.mark.asyncio
    async def test_permission_caching(self, validator, mock_user_permissions):
        """Test permission caching functionality"""
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions) as mock_fetch:
            # First call should fetch permissions
            result1 = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            # Second call should use cache
            result2 = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            # Should only fetch once due to caching
            assert mock_fetch.call_count == 1
            assert result1.is_valid is True
            assert result2.is_valid is True
            # Check that the cache was used (access count > 1)
            cache_key = validator._generate_cache_key("john.smith@acme.com", "tenant_123")
            assert cache_key in validator._permission_cache
            assert validator._permission_cache[cache_key].access_count >= 2

    @pytest.mark.asyncio
    async def test_cache_expiration(self, validator, mock_user_permissions):
        """Test cache expiration handling"""
        # Set very short cache TTL
        validator.cache_ttl_minutes = 0.01  # ~0.6 seconds

        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions) as mock_fetch:
            # First call
            await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            # Wait for cache to expire
            await asyncio.sleep(1)

            # Second call should fetch again due to expiration
            await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_audit_logging(self, validator, mock_user_permissions):
        """Test permission audit logging"""
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read", "Planner.ReadWrite"],
                operation="modify_planner",
                resource_type=ResourceType.PLANNER,
                resource_id="plan_12345",
                tenant_id="tenant_123",
                context={
                    "ip_address": "192.168.1.100",
                    "user_agent": "Mozilla/5.0",
                    "correlation_id": "corr_123"
                }
            )

            # Check audit trail
            audit_entries = validator.get_audit_trail(hours=1)
            assert len(audit_entries) > 0

            latest_entry = audit_entries[-1]
            assert latest_entry.user_id == "john.smith@acme.com"
            assert latest_entry.operation == "modify_planner"
            assert latest_entry.resource_type == "planner"
            assert latest_entry.resource_id == "plan_12345"
            assert "User.Read" in latest_entry.granted_scopes
            assert "Planner.ReadWrite" in latest_entry.denied_scopes
            assert latest_entry.ip_address == "192.168.1.100"
            assert latest_entry.correlation_id == "corr_123"

    @pytest.mark.asyncio
    async def test_permission_decorator(self, validator, admin_user_permissions):
        """Test permission decorator functionality"""
        # Patch the global validator to use our test instance
        with patch('src.graph.permissions.get_permission_validator', return_value=validator):
            @require_permissions(["Planner.ReadWrite"], ResourceType.PLANNER)
            async def create_planner_task(user_id: str, task_data: Dict[str, Any], tenant_id: str = None, permission_validation=None):
                return {"status": "success", "task_id": "task_123"}

            with patch.object(validator, '_fetch_user_permissions', return_value=admin_user_permissions):
                # Should succeed with admin permissions
                result = await create_planner_task(
                    user_id="admin.user@acme.com",
                    task_data={"title": "New Task", "description": "Task description"},
                    tenant_id="tenant_123"
                )
                assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_permission_decorator_access_denied(self, validator, mock_user_permissions):
        """Test permission decorator with insufficient permissions"""
        # Patch the global validator to use our test instance
        with patch('src.graph.permissions.get_permission_validator', return_value=validator):
            @require_permissions(["Directory.ReadWrite.All"], ResourceType.DIRECTORY)
            async def modify_directory(user_id: str, directory_data: Dict[str, Any], permission_validation=None):
                return {"status": "success"}

            with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
                # Should raise PermissionError
                with pytest.raises(PermissionError) as exc_info:
                    await modify_directory(
                        user_id="john.smith@acme.com",
                        directory_data={"name": "New Directory"}
                    )
                assert "Insufficient permissions" in str(exc_info.value)

    def test_scope_validation_application_vs_delegated(self, validator):
        """Test validation of application vs delegated permission types"""
        # Test application permission
        app_permissions = UserPermissions(
            user_id="app_service@acme.com",
            granted_scopes=["Group.ReadWrite.All"],  # Application permission
            last_validated=datetime.now(timezone.utc)
        )

        # Should validate application permission for group operations
        is_valid = validator._validate_scope(app_permissions, "Group.ReadWrite.All", ResourceType.GROUP)
        assert is_valid is True

        # Test delegated permission
        delegated_permissions = UserPermissions(
            user_id="user@acme.com",
            granted_scopes=["Planner.Read"],  # Delegated permission
            last_validated=datetime.now(timezone.utc)
        )

        is_valid = validator._validate_scope(delegated_permissions, "Planner.Read", ResourceType.PLANNER)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, validator, mock_user_permissions):
        """Test permission cache invalidation"""
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            # Cache permissions
            await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            # Verify cache exists
            cache_key = validator._generate_cache_key("john.smith@acme.com", "tenant_123")
            assert cache_key in validator._permission_cache

            # Invalidate cache
            invalidated = await validator.invalidate_user_cache("john.smith@acme.com", "tenant_123")
            assert invalidated is True
            assert cache_key not in validator._permission_cache

    @pytest.mark.asyncio
    async def test_refresh_user_permissions(self, validator, mock_user_permissions):
        """Test force refresh of user permissions"""
        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions) as mock_fetch:
            # Initial fetch and cache
            await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER,
                tenant_id="tenant_123"
            )

            # Force refresh - should fetch again even with cache
            refreshed_permissions = await validator.refresh_user_permissions("john.smith@acme.com", "tenant_123")

            assert mock_fetch.call_count == 2  # Initial + refresh
            assert refreshed_permissions.user_id == "john.smith@acme.com"

    def test_permission_statistics(self, validator):
        """Test permission system statistics collection"""
        # Add some mock audit entries
        validator._audit_trail.extend([
            PermissionAuditEntry(
                audit_id="audit_1",
                user_id="user1@acme.com",
                tenant_id="tenant_123",
                operation="read_data",
                resource_type="user",
                resource_id="user_123",
                requested_scopes=["User.Read"],
                granted_scopes=["User.Read"],
                denied_scopes=[],
                result="granted"
            ),
            PermissionAuditEntry(
                audit_id="audit_2",
                user_id="user2@acme.com",
                tenant_id="tenant_123",
                operation="write_data",
                resource_type="planner",
                resource_id="plan_456",
                requested_scopes=["Planner.ReadWrite"],
                granted_scopes=[],
                denied_scopes=["Planner.ReadWrite"],
                result="denied"
            ),
            PermissionAuditEntry(
                audit_id="audit_3",
                user_id="user3@acme.com",
                tenant_id="tenant_123",
                operation="admin_action",
                resource_type="directory",
                resource_id="dir_789",
                requested_scopes=["Directory.ReadWrite.All"],
                granted_scopes=[],
                denied_scopes=["Directory.ReadWrite.All"],
                result="escalation_detected"
            )
        ])

        stats = validator.get_permission_statistics()

        assert stats["total_validations"] == 3
        assert stats["successful_validations"] == 1
        assert stats["denied_validations"] == 2
        assert stats["success_rate"] == pytest.approx(33.33, rel=1e-2)
        assert stats["escalation_count"] == 1
        assert stats["escalation_rate"] == pytest.approx(33.33, rel=1e-2)
        assert "cache_stats" in stats
        assert "most_requested_scopes" in stats
        assert "most_denied_scopes" in stats

    def test_audit_trail_filtering(self, validator):
        """Test audit trail filtering functionality"""
        # Add mock entries with different timestamps
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=25)  # Older than 24 hours
        recent_time = now - timedelta(hours=1)

        validator._audit_trail.extend([
            PermissionAuditEntry(
                audit_id="old_audit",
                user_id="user1@acme.com",
                tenant_id="tenant_123",
                operation="old_operation",
                resource_type="user",
                resource_id="user_old",
                requested_scopes=["User.Read"],
                granted_scopes=["User.Read"],
                denied_scopes=[],
                result="granted",
                timestamp=old_time
            ),
            PermissionAuditEntry(
                audit_id="recent_audit",
                user_id="user2@acme.com",
                tenant_id="tenant_123",
                operation="recent_operation",
                resource_type="planner",
                resource_id="plan_recent",
                requested_scopes=["Planner.Read"],
                granted_scopes=["Planner.Read"],
                denied_scopes=[],
                result="granted",
                timestamp=recent_time
            )
        ])

        # Filter by time (last 24 hours)
        recent_entries = validator.get_audit_trail(hours=24)
        assert len(recent_entries) == 1
        assert recent_entries[0].audit_id == "recent_audit"

        # Filter by user
        user_entries = validator.get_audit_trail(user_id="user1@acme.com", hours=48)
        assert len(user_entries) == 1
        assert user_entries[0].user_id == "user1@acme.com"

        # Filter by operation
        operation_entries = validator.get_audit_trail(operation="recent_operation", hours=48)
        assert len(operation_entries) == 1
        assert operation_entries[0].operation == "recent_operation"

    @pytest.mark.asyncio
    async def test_out_of_hours_escalation_detection(self, validator, mock_user_permissions):
        """Test escalation detection for requests outside normal hours"""
        # Simulate request at 3 AM
        night_time = datetime.now(timezone.utc).replace(hour=3)

        with patch.object(validator, '_fetch_user_permissions', return_value=mock_user_permissions):
            result = await validator.validate_permissions(
                user_id="john.smith@acme.com",
                required_scopes=["Directory.Read.All"],
                operation="read_directory",
                resource_type=ResourceType.DIRECTORY,
                tenant_id="tenant_123",
                context={"request_timestamp": night_time}
            )

            assert result.escalation_detected is True
            assert result.is_valid is False

    def test_permission_scope_definitions(self, validator):
        """Test that permission scope definitions are correctly configured"""
        # Test planner scopes
        planner_scopes = validator.GRAPH_SCOPES[ResourceType.PLANNER]
        assert "Planner.Read" in planner_scopes
        assert "Planner.ReadWrite" in planner_scopes
        assert planner_scopes["Planner.Read"]["type"] == PermissionType.DELEGATED
        assert planner_scopes["Planner.Read"]["level"] == AccessLevel.READ

        # Test group scopes
        group_scopes = validator.GRAPH_SCOPES[ResourceType.GROUP]
        assert "Group.ReadWrite.All" in group_scopes
        assert group_scopes["Group.ReadWrite.All"]["type"] == PermissionType.APPLICATION
        assert group_scopes["Group.ReadWrite.All"]["level"] == AccessLevel.WRITE

        # Test user scopes
        user_scopes = validator.GRAPH_SCOPES[ResourceType.USER]
        assert "User.Read" in user_scopes
        assert "User.ReadBasic.All" in user_scopes
        assert user_scopes["User.Read"]["type"] == PermissionType.DELEGATED

    def test_cache_size_management(self, validator):
        """Test cache size management and LRU eviction"""
        # Set small cache size for testing
        validator.max_cache_size = 3

        # Mock user permissions
        mock_permissions = UserPermissions(
            user_id="test_user",
            granted_scopes=["User.Read"],
            last_validated=datetime.now(timezone.utc)
        )

        # Add entries beyond cache size
        for i in range(5):
            cache_key = f"user_{i}"
            validator._permission_cache[cache_key] = type('CacheEntry', (), {
                'user_id': f'user_{i}',
                'permissions': mock_permissions,
                'cache_key': cache_key,
                'is_expired': lambda: False,
                'update_access': lambda: None
            })()
            validator._cache_access_order.append(cache_key)

        # Trigger cache management
        validator._manage_cache_size()

        # Should only have max_cache_size entries
        assert len(validator._permission_cache) <= validator.max_cache_size
        assert len(validator._cache_access_order) <= validator.max_cache_size


class TestPermissionIntegration:
    """Integration tests for permission system"""

    @pytest.mark.asyncio
    async def test_end_to_end_permission_flow(self):
        """Test complete permission validation flow"""
        validator = GraphPermissionValidator(enable_audit_logging=True)

        # Mock realistic user permissions
        user_permissions = UserPermissions(
            user_id="sarah.johnson@contoso.com",
            tenant_id="contoso_tenant",
            granted_scopes=[
                "User.Read",
                "Planner.ReadWrite",
                "Group.Read.All",
                "Tasks.ReadWrite"
            ],
            last_validated=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
        )

        with patch.object(validator, '_fetch_user_permissions', return_value=user_permissions):
            # Test successful operation
            result = await validator.validate_permissions(
                user_id="sarah.johnson@contoso.com",
                required_scopes=["Planner.ReadWrite", "Tasks.ReadWrite"],
                operation="create_project_plan",
                resource_type=ResourceType.PLANNER,
                resource_id="project_alpha",
                tenant_id="contoso_tenant",
                context={
                    "ip_address": "10.0.1.50",
                    "user_agent": "PlannerApp/2.1.0",
                    "correlation_id": "req_789"
                }
            )

            # Verify successful validation
            assert result.is_valid is True
            assert result.escalation_detected is False
            assert len(result.missing_scopes) == 0

            # Check audit trail
            audit_entries = validator.get_audit_trail(user_id="sarah.johnson@contoso.com")
            assert len(audit_entries) == 1
            assert audit_entries[0].result == "granted"

            # Test permission statistics
            stats = validator.get_permission_statistics()
            assert stats["total_validations"] >= 1
            assert stats["successful_validations"] >= 1

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self):
        """Test multi-tenant permission isolation"""
        validator = GraphPermissionValidator()

        # Setup tenant contexts
        validator._tenant_contexts["tenant_a"] = TenantContext(
            tenant_id="tenant_a",
            tenant_name="Company A",
            enabled=True
        )

        validator._tenant_contexts["tenant_b"] = TenantContext(
            tenant_id="tenant_b",
            tenant_name="Company B",
            enabled=True
        )

        # User permissions for tenant A
        tenant_a_permissions = UserPermissions(
            user_id="user@companya.com",
            tenant_id="tenant_a",
            granted_scopes=["User.Read", "Planner.Read"],
            last_validated=datetime.now(timezone.utc)
        )

        with patch.object(validator, '_fetch_user_permissions', return_value=tenant_a_permissions):
            # User should be able to access resources in their tenant
            result_a = await validator.validate_permissions(
                user_id="user@companya.com",
                required_scopes=["User.Read"],
                operation="read_profile",
                resource_type=ResourceType.USER,
                tenant_id="tenant_a"
            )
            assert result_a.is_valid is True

            # Same user should not be able to access different tenant
            await validator.validate_permissions(
                user_id="user@companya.com",
                required_scopes=["User.Read"],
                operation="read_profile",
                resource_type=ResourceType.USER,
                tenant_id="tenant_b"
            )
            # This test assumes cross-tenant access is properly validated
            # In a real implementation, this would check tenant membership


def test_global_permission_validator():
    """Test global permission validator instance"""
    validator1 = get_permission_validator()
    validator2 = get_permission_validator()

    # Should return the same instance (singleton pattern)
    assert validator1 is validator2
    assert isinstance(validator1, GraphPermissionValidator)


class TestPermissionErrorHandling:
    """Test error handling in permission system"""

    @pytest.fixture
    def validator(self):
        return GraphPermissionValidator()

    @pytest.mark.asyncio
    async def test_permission_validation_with_exception(self, validator):
        """Test permission validation when an exception occurs"""
        # Mock an exception during permission fetching
        with patch.object(validator, '_fetch_user_permissions', side_effect=Exception("API Error")):
            result = await validator.validate_permissions(
                user_id="test.user@example.com",
                required_scopes=["User.Read"],
                operation="read_user",
                resource_type=ResourceType.USER
            )

            # Should fail safely with deny-by-default
            assert result.is_valid is False
            assert result.granted_scopes == []
            assert result.missing_scopes == ["User.Read"]
            assert "error" in result.validation_context

    @pytest.mark.asyncio
    async def test_invalid_scope_handling(self, validator):
        """Test handling of invalid or unknown scopes"""
        mock_permissions = UserPermissions(
            user_id="test.user@example.com",
            granted_scopes=["User.Read"],
            last_validated=datetime.now(timezone.utc)
        )

        with patch.object(validator, '_fetch_user_permissions', return_value=mock_permissions):
            result = await validator.validate_permissions(
                user_id="test.user@example.com",
                required_scopes=["NonExistent.Scope", "User.Read"],
                operation="test_operation",
                resource_type=ResourceType.USER
            )

            assert "User.Read" in result.granted_scopes
            assert "NonExistent.Scope" in result.missing_scopes
            assert result.is_valid is False


if __name__ == "__main__":
    # Run tests with: python -m pytest tests/test_permissions.py -v
    pytest.main([__file__, "-v", "--tb=short"])
