"""
Comprehensive tests for batch operations system
Story 2.1 Task 1: Tests for batch request building, response parsing, dependencies, and error handling
"""

import pytest
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any
from unittest.mock import Mock, AsyncMock, patch

from src.graph.batch_operations import (
    BatchOperationBuilder, BatchResponseParser, BatchExecutor, BatchOperationsManager,
    BatchRequestConfig, BatchOptimizationStrategy, DependencyResolutionMethod,
    BatchExecutionContext, OperationDependency, get_batch_manager,
    execute_batch_operations, create_and_execute_batch
)
from src.models.graph_models import (
    BatchOperation, BatchRequest, BatchResponse, RequestMethod,
    BatchRequestStatus, OperationStatus
)


class TestBatchOperationBuilder:
    """Test the batch operation builder functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = BatchRequestConfig(
            max_operations_per_batch=20,
            optimization_strategy=BatchOptimizationStrategy.DEPENDENCY_AWARE
        )
        self.builder = BatchOperationBuilder(self.config)

    def test_add_operation_basic(self):
        """Test adding a basic operation"""
        operation_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me",
            operation_id="get_user_profile"
        )

        assert operation_id == "get_user_profile"
        assert len(self.builder.operations) == 1

        operation = self.builder.operations[0]
        assert operation.id == "get_user_profile"
        assert operation.method == RequestMethod.GET
        assert operation.url == "/me"
        assert operation.status == OperationStatus.PENDING

    def test_add_operation_with_body_and_headers(self):
        """Test adding operation with request body and headers"""
        body = {
            "displayName": "Project Alpha",
            "description": "Strategic initiative for market expansion"
        }
        headers = {"Prefer": "return=representation"}

        operation_id = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans",
            body=body,
            headers=headers,
            priority=50
        )

        operation = self.builder.operations[0]
        assert operation.body == body
        assert operation.headers == headers
        assert self.builder.operation_priorities[operation_id] == 50

    def test_add_operation_with_dependencies(self):
        """Test adding operations with dependencies"""
        # Create parent operation
        parent_id = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans",
            operation_id="create_plan"
        )

        # Create dependent operation
        child_id = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans/{plan-id}/buckets",
            depends_on=[parent_id],
            operation_id="create_bucket"
        )

        assert len(self.builder.dependencies) == 1
        dependency = self.builder.dependencies[0]
        assert dependency.operation_id == child_id
        assert dependency.depends_on_id == parent_id

    def test_add_conditional_operation(self):
        """Test adding conditional operations"""
        # Create parent operation
        parent_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me/planner/plans",
            operation_id="get_plans"
        )

        # Create conditional operation
        child_id = self.builder.add_conditional_operation(
            method=RequestMethod.GET,
            url="/planner/plans/{plan-id}/tasks",
            depends_on_success=parent_id,
            operation_id="get_tasks"
        )

        # Should have two dependencies: normal and conditional
        conditional_deps = [d for d in self.builder.dependencies if d.conditional]
        assert len(conditional_deps) == 1
        assert conditional_deps[0].dependency_type == "success"

    def test_batch_size_limit(self):
        """Test batch size limit enforcement"""
        # Add maximum allowed operations
        for i in range(self.config.max_operations_per_batch):
            self.builder.add_operation(
                method=RequestMethod.GET,
                url=f"/users/{i}",
                operation_id=f"get_user_{i}"
            )

        # Adding one more should raise an exception
        with pytest.raises(ValueError, match="Batch size limit exceeded"):
            self.builder.add_operation(
                method=RequestMethod.GET,
                url="/users/overflow"
            )

    def test_invalid_url_validation(self):
        """Test URL validation"""
        invalid_urls = [
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "file:///etc/passwd",
            "../../../sensitive/file"
        ]

        for url in invalid_urls:
            with pytest.raises(ValueError, match="Invalid URL format"):
                self.builder.add_operation(
                    method=RequestMethod.GET,
                    url=url
                )

    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies"""
        # Create operations with circular dependencies
        op1_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/resource1",
            operation_id="op1",
            depends_on=["op3"]  # Depends on op3
        )

        op2_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/resource2",
            operation_id="op2",
            depends_on=["op1"]  # Depends on op1
        )

        op3_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/resource3",
            operation_id="op3",
            depends_on=["op2"]  # Depends on op2, creating a cycle
        )

        with pytest.raises(ValueError, match="Circular dependency detected"):
            self.builder.build("user123", "tenant456")

    def test_topological_sort_optimization(self):
        """Test topological sort for dependency resolution"""
        # Create operations with clear dependency chain
        op1_id = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans",
            operation_id="create_plan"
        )

        op2_id = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans/{plan-id}/buckets",
            depends_on=[op1_id],
            operation_id="create_bucket"
        )

        op3_id = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/buckets/{bucket-id}/tasks",
            depends_on=[op2_id],
            operation_id="create_task"
        )

        # Add independent operation
        op4_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me",
            operation_id="get_profile"
        )

        batch_request = self.builder.build("user123", "tenant456")

        # Verify dependency order is preserved
        operation_ids = [op.id for op in batch_request.operations]

        # op1 should come before op2, op2 before op3
        assert operation_ids.index("create_plan") < operation_ids.index("create_bucket")
        assert operation_ids.index("create_bucket") < operation_ids.index("create_task")

    def test_priority_based_optimization(self):
        """Test priority-based operation ordering"""
        self.builder.config.optimization_strategy = BatchOptimizationStrategy.PRIORITY_BASED

        # Add operations with different priorities
        high_priority_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/critical/resource",
            operation_id="high_priority",
            priority=10  # High priority (lower number)
        )

        low_priority_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/non_critical/resource",
            operation_id="low_priority",
            priority=100  # Low priority
        )

        medium_priority_id = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/medium/resource",
            operation_id="medium_priority",
            priority=50  # Medium priority
        )

        batch_request = self.builder.build("user123", "tenant456")
        operation_ids = [op.id for op in batch_request.operations]

        # High priority should come first
        assert operation_ids.index("high_priority") < operation_ids.index("medium_priority")
        assert operation_ids.index("medium_priority") < operation_ids.index("low_priority")

    def test_performance_optimization_strategy(self):
        """Test performance-based optimization"""
        self.builder.config.optimization_strategy = BatchOptimizationStrategy.PERFORMANCE_OPTIMIZED

        # Add mix of read and write operations
        read_ops = []
        write_ops = []

        for i in range(3):
            read_id = self.builder.add_operation(
                method=RequestMethod.GET,
                url=f"/read/resource{i}",
                operation_id=f"read_{i}"
            )
            read_ops.append(read_id)

            write_id = self.builder.add_operation(
                method=RequestMethod.POST,
                url=f"/write/resource{i}",
                operation_id=f"write_{i}"
            )
            write_ops.append(write_id)

        batch_request = self.builder.build("user123", "tenant456")

        # Performance optimization should interleave reads and writes
        operation_methods = [op.method for op in batch_request.operations]

        # Should have a mix of GET and POST operations
        assert RequestMethod.GET in operation_methods
        assert RequestMethod.POST in operation_methods

    def test_build_empty_batch_fails(self):
        """Test that building empty batch fails"""
        with pytest.raises(ValueError, match="Cannot build empty batch request"):
            self.builder.build("user123", "tenant456")

    def test_build_with_metadata(self):
        """Test batch building includes proper metadata"""
        self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me",
            priority=42
        )

        batch_request = self.builder.build("user123", "tenant456")

        assert batch_request.user_id == "user123"
        assert batch_request.tenant_id == "tenant456"
        assert batch_request.status == BatchRequestStatus.PENDING
        assert "builder_config" in batch_request.metadata
        assert "operation_priorities" in batch_request.metadata

        builder_config = batch_request.metadata["builder_config"]
        assert builder_config["strategy"] == BatchOptimizationStrategy.DEPENDENCY_AWARE


class TestBatchResponseParser:
    """Test batch response parsing functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.parser = BatchResponseParser()
        self.batch_request = self._create_sample_batch_request()

    def _create_sample_batch_request(self) -> BatchRequest:
        """Create a sample batch request for testing"""
        operations = [
            BatchOperation(
                id="op1",
                method=RequestMethod.GET,
                url="/me"
            ),
            BatchOperation(
                id="op2",
                method=RequestMethod.POST,
                url="/planner/plans"
            ),
            BatchOperation(
                id="op3",
                method=RequestMethod.GET,
                url="/invalid/resource"
            )
        ]

        return BatchRequest(
            id="batch123",
            operations=operations,
            user_id="user456"
        )

    def test_parse_successful_response(self):
        """Test parsing successful batch response"""
        raw_response = {
            "responses": [
                {
                    "id": "op1",
                    "status": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "id": "user456",
                        "displayName": "Sarah Connor",
                        "mail": "sarah.connor@contoso.com"
                    }
                },
                {
                    "id": "op2",
                    "status": 201,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "id": "plan789",
                        "title": "Project Phoenix",
                        "createdDateTime": "2024-10-07T10:00:00Z"
                    }
                }
            ]
        }

        batch_response = self.parser.parse_response(raw_response, self.batch_request)

        assert batch_response.batch_id == "batch123"
        assert batch_response.success_count == 2
        assert batch_response.error_count == 0

        # Check operation statuses
        op1 = self.batch_request.get_operation("op1")
        op2 = self.batch_request.get_operation("op2")

        assert op1.status == OperationStatus.SUCCESS
        assert op2.status == OperationStatus.SUCCESS
        assert op1.response["displayName"] == "Sarah Connor"
        assert op2.response["title"] == "Project Phoenix"

    def test_parse_mixed_success_error_response(self):
        """Test parsing response with mix of success and errors"""
        raw_response = {
            "responses": [
                {
                    "id": "op1",
                    "status": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "id": "user456",
                        "displayName": "Sarah Connor"
                    }
                },
                {
                    "id": "op2",
                    "status": 403,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "error": {
                            "code": "Forbidden",
                            "message": "Insufficient privileges to complete the operation."
                        }
                    }
                },
                {
                    "id": "op3",
                    "status": 404,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "error": {
                            "code": "NotFound",
                            "message": "The requested resource does not exist."
                        }
                    }
                }
            ]
        }

        batch_response = self.parser.parse_response(raw_response, self.batch_request)

        assert batch_response.success_count == 1
        assert batch_response.error_count == 2

        # Check individual operation statuses
        op1 = self.batch_request.get_operation("op1")
        op2 = self.batch_request.get_operation("op2")
        op3 = self.batch_request.get_operation("op3")

        assert op1.status == OperationStatus.SUCCESS
        assert op2.status == OperationStatus.ERROR
        assert op3.status == OperationStatus.ERROR

        # Check error classification
        assert op2.error is not None and "privileges" in op2.error
        assert op3.error is not None and "does not exist" in op3.error

        # Check error context
        assert op2.response is not None and "error_context" in op2.response
        assert op2.response["error_context"]["correlation_id"] is not None

    def test_parse_rate_limit_error(self):
        """Test parsing rate limit errors"""
        raw_response = {
            "responses": [
                {
                    "id": "op1",
                    "status": 429,
                    "headers": {
                        "Content-Type": "application/json",
                        "Retry-After": "60"
                    },
                    "body": {
                        "error": {
                            "code": "TooManyRequests",
                            "message": "Rate limit exceeded. Please retry after 60 seconds."
                        }
                    }
                }
            ]
        }

        batch_response = self.parser.parse_response(raw_response, self.batch_request)

        op1 = self.batch_request.get_operation("op1")
        assert op1.status == OperationStatus.ERROR

        # Rate limit should be classified appropriately
        assert op1.response is not None
        error_context = op1.response["error_context"]
        assert error_context["category"] == "rate_limit"
        assert error_context["retry_recommended"] is True

    def test_parse_authentication_error(self):
        """Test parsing authentication errors"""
        raw_response = {
            "responses": [
                {
                    "id": "op1",
                    "status": 401,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "error": {
                            "code": "InvalidAuthenticationToken",
                            "message": "Access token has expired."
                        }
                    }
                }
            ]
        }

        batch_response = self.parser.parse_response(raw_response, self.batch_request)

        op1 = self.batch_request.get_operation("op1")
        assert op1.response is not None
        error_context = op1.response["error_context"]
        assert error_context["category"] == "authentication"

    def test_parse_malformed_response(self):
        """Test handling of malformed responses"""
        malformed_responses = [
            {},  # Empty response
            {"responses": None},  # Invalid responses
            {"responses": "not_a_list"},  # Invalid responses type
        ]

        for malformed_response in malformed_responses:
            with pytest.raises(Exception):
                self.parser.parse_response(malformed_response, self.batch_request)

    def test_parse_response_missing_operation_id(self):
        """Test handling response with missing operation ID"""
        raw_response = {
            "responses": [
                {
                    # Missing "id" field
                    "status": 200,
                    "body": {"value": "test"}
                }
            ]
        }

        # Should not crash but should log warning
        batch_response = self.parser.parse_response(raw_response, self.batch_request)
        # The response is counted in the raw response statistics even if operation is unknown
        assert batch_response.success_count == 1
        assert batch_response.error_count == 0

    def test_error_message_extraction(self):
        """Test extraction of error messages from various formats"""
        test_cases = [
            {
                "error": {
                    "code": "BadRequest",
                    "message": "Invalid request format"
                }
            },
            {
                "error_description": "Token has expired"
            },
            {
                "message": "Simple error message"
            },
            "String error message"
        ]

        for error_body in test_cases:
            message = self.parser._extract_error_message(error_body)
            assert isinstance(message, str)
            assert len(message) > 0


class TestBatchExecutor:
    """Test batch execution functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = BatchRequestConfig(
            max_retries=2,
            timeout_seconds=30
        )
        self.executor = BatchExecutor(self.config)
        self.batch_request = self._create_sample_batch_request()

    def _create_sample_batch_request(self) -> BatchRequest:
        """Create a sample batch request for testing"""
        operations = [
            BatchOperation(
                id="get_user",
                method=RequestMethod.GET,
                url="/me"
            ),
            BatchOperation(
                id="create_plan",
                method=RequestMethod.POST,
                url="/planner/plans",
                body={"title": "Test Plan"}
            )
        ]

        return BatchRequest(
            id="test_batch",
            operations=operations,
            user_id="test_user",
            tenant_id="test_tenant"
        )

    @pytest.mark.asyncio
    async def test_execute_batch_success(self):
        """Test successful batch execution"""
        # Mock successful HTTP response
        mock_response = {
            "responses": [
                {
                    "id": "get_user",
                    "status": 200,
                    "body": {"displayName": "Test User"}
                },
                {
                    "id": "create_plan",
                    "status": 201,
                    "body": {"id": "plan123", "title": "Test Plan"}
                }
            ]
        }

        with patch.object(self.executor, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.return_value = mock_response

            batch_response = await self.executor.execute_batch(
                batch_request=self.batch_request,
                auth_token="test_token"
            )

            assert batch_response.success_count == 2
            assert batch_response.error_count == 0
            assert self.batch_request.status == BatchRequestStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_batch_with_rate_limit(self):
        """Test batch execution with rate limiting"""
        # Mock rate limiter to simulate rate limit
        with patch.object(self.executor.rate_limiter, 'check_rate_limit') as mock_check:
            mock_check.return_value = {
                "allowed": False,
                "delay": 2.0,
                "reason": "rate_limited"
            }

            with patch.object(self.executor, '_make_http_request', new_callable=AsyncMock) as mock_http:
                mock_http.return_value = {"responses": []}

                start_time = asyncio.get_event_loop().time()
                await self.executor.execute_batch(
                    batch_request=self.batch_request,
                    auth_token="test_token"
                )
                end_time = asyncio.get_event_loop().time()

                # Should have waited for rate limit
                assert end_time - start_time >= 2.0

    @pytest.mark.asyncio
    async def test_execute_batch_with_retry(self):
        """Test batch execution with retry on failure"""
        call_count = 0

        async def mock_http_request(request_data, context):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first two attempts
                raise Exception("Connection timeout")
            # Succeed on third attempt
            return {"responses": []}

        with patch.object(self.executor, '_make_http_request', side_effect=mock_http_request):
            await self.executor.execute_batch(
                batch_request=self.batch_request,
                auth_token="test_token"
            )

            assert call_count == 3  # Should have retried twice

    @pytest.mark.asyncio
    async def test_execute_batch_max_retries_exceeded(self):
        """Test batch execution when max retries are exceeded"""
        with patch.object(self.executor, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.side_effect = Exception("Connection timeout")

            with pytest.raises(Exception, match="Connection timeout"):
                await self.executor.execute_batch(
                    batch_request=self.batch_request,
                    auth_token="test_token"
                )

            # Should have called max_retries + 1 times
            assert mock_http.call_count == self.config.max_retries + 1
            assert self.batch_request.status == BatchRequestStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_batch_authentication_error(self):
        """Test batch execution with authentication error"""
        auth_error_response = {
            "error": {
                "code": "InvalidAuthenticationToken",
                "message": "Access token has expired"
            }
        }

        with patch.object(self.executor, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.return_value = auth_error_response

            with pytest.raises(Exception, match="Batch request failed"):
                await self.executor.execute_batch(
                    batch_request=self.batch_request,
                    auth_token="invalid_token"
                )

    def test_prepare_batch_request(self):
        """Test preparation of batch request data"""
        context = BatchExecutionContext(
            batch_request=self.batch_request,
            config=self.config,
            correlation_id="corr123",
            start_time=datetime.now(timezone.utc),
            auth_token="test_token",
            custom_headers={"X-Custom": "value"}
        )

        request_data = self.executor._prepare_batch_request(context)

        assert request_data["method"] == "POST"
        assert "/$batch" in request_data["url"]
        assert "Bearer test_token" in request_data["headers"]["Authorization"]
        assert "X-Custom" in request_data["headers"]

        # Check batch payload structure
        batch_payload = request_data["data"]
        assert "requests" in batch_payload
        assert len(batch_payload["requests"]) == 2

        # Check individual request format
        request1 = batch_payload["requests"][0]
        assert request1["id"] == "get_user"
        assert request1["method"] == "GET"
        assert request1["url"] == "/me"

        request2 = batch_payload["requests"][1]
        assert request2["id"] == "create_plan"
        assert request2["method"] == "POST"
        assert request2["body"] == {"title": "Test Plan"}


class TestBatchOperationsManager:
    """Test high-level batch operations manager"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = BatchRequestConfig(max_operations_per_batch=5)
        self.manager = BatchOperationsManager(self.config)

    def test_create_builder(self):
        """Test builder creation"""
        builder = self.manager.create_builder()
        assert isinstance(builder, BatchOperationBuilder)
        assert builder.config == self.config

    @pytest.mark.asyncio
    async def test_execute_batch_operations(self):
        """Test high-level batch execution"""
        # Create a batch request
        builder = self.manager.create_builder()
        builder.add_operation(RequestMethod.GET, "/me")
        batch_request = builder.build("user123")

        # Mock the executor
        with patch.object(self.manager.executor, 'execute_batch', new_callable=AsyncMock) as mock_execute:
            mock_response = BatchResponse(
                batch_id=batch_request.id,
                responses=[],
                success_count=1,
                error_count=0
            )
            mock_execute.return_value = mock_response

            response = await self.manager.execute_batch_operations(
                batch_request=batch_request,
                auth_token="test_token"
            )

            assert response == mock_response
            assert batch_request.id not in self.manager.active_batches

    @pytest.mark.asyncio
    async def test_execute_operations_in_chunks(self):
        """Test chunked execution for large operation lists"""
        # Create more operations than batch size limit
        operations = []
        for i in range(12):  # More than max_operations_per_batch (5)
            operations.append(BatchOperation(
                id=f"op_{i}",
                method=RequestMethod.GET,
                url=f"/resource/{i}"
            ))

        # Mock the execute_batch_operations method
        with patch.object(self.manager, 'execute_batch_operations', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = BatchResponse(
                batch_id="test",
                responses=[],
                success_count=1,
                error_count=0
            )

            responses = await self.manager.execute_operations_in_chunks(
                operations=operations,
                user_id="user123",
                auth_token="test_token"
            )

            # Should have created 3 chunks (5 + 5 + 2)
            assert len(responses) == 3
            assert mock_execute.call_count == 3

    def test_active_batch_tracking(self):
        """Test tracking of active batches"""
        builder = self.manager.create_builder()
        builder.add_operation(RequestMethod.GET, "/me")
        batch_request = builder.build("user123")

        # Add to active batches manually (simulating execution start)
        self.manager.active_batches[batch_request.id] = batch_request

        active_batches = self.manager.get_active_batches()
        assert len(active_batches) == 1
        assert active_batches[0] == batch_request

        status = self.manager.get_batch_status(batch_request.id)
        assert status == batch_request

    @pytest.mark.asyncio
    async def test_cancel_batch(self):
        """Test batch cancellation"""
        builder = self.manager.create_builder()
        builder.add_operation(RequestMethod.GET, "/me")
        batch_request = builder.build("user123")

        # Add to active batches
        self.manager.active_batches[batch_request.id] = batch_request

        # Cancel the batch
        success = await self.manager.cancel_batch(batch_request.id)

        assert success is True
        assert batch_request.status == BatchRequestStatus.FAILED

        # Test cancelling non-existent batch
        success = await self.manager.cancel_batch("non_existent")
        assert success is False


class TestDependencyHandling:
    """Test dependency handling and conditional execution"""

    def setup_method(self):
        """Set up test fixtures"""
        self.builder = BatchOperationBuilder()

    def test_simple_dependency_chain(self):
        """Test simple dependency chain A -> B -> C"""
        op_a = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans",
            operation_id="create_plan"
        )

        op_b = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans/{plan-id}/buckets",
            depends_on=[op_a],
            operation_id="create_bucket"
        )

        op_c = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/buckets/{bucket-id}/tasks",
            depends_on=[op_b],
            operation_id="create_task"
        )

        batch_request = self.builder.build("user123")
        operation_ids = [op.id for op in batch_request.operations]

        # Verify dependency order
        assert operation_ids.index("create_plan") < operation_ids.index("create_bucket")
        assert operation_ids.index("create_bucket") < operation_ids.index("create_task")

    def test_parallel_dependencies(self):
        """Test operations with parallel dependencies"""
        # Create root operation
        root_op = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me",
            operation_id="get_user"
        )

        # Create parallel operations depending on root
        op_a = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me/planner/plans",
            depends_on=[root_op],
            operation_id="get_plans"
        )

        op_b = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me/calendar/events",
            depends_on=[root_op],
            operation_id="get_events"
        )

        # Create operation depending on both parallel operations
        final_op = self.builder.add_operation(
            method=RequestMethod.POST,
            url="/analytics/summary",
            depends_on=[op_a, op_b],
            operation_id="create_summary"
        )

        batch_request = self.builder.build("user123")
        operation_ids = [op.id for op in batch_request.operations]

        # Root should come first
        assert operation_ids.index("get_user") < operation_ids.index("get_plans")
        assert operation_ids.index("get_user") < operation_ids.index("get_events")

        # Final operation should come last
        assert operation_ids.index("get_plans") < operation_ids.index("create_summary")
        assert operation_ids.index("get_events") < operation_ids.index("create_summary")

    def test_conditional_execution_success(self):
        """Test conditional execution when dependency succeeds"""
        parent_op = self.builder.add_operation(
            method=RequestMethod.GET,
            url="/me/planner/plans",
            operation_id="get_plans"
        )

        child_op = self.builder.add_conditional_operation(
            method=RequestMethod.GET,
            url="/planner/plans/{plan-id}/tasks",
            depends_on_success=parent_op,
            operation_id="get_tasks"
        )

        # Verify conditional dependency is recorded
        conditional_deps = [d for d in self.builder.dependencies if d.conditional]
        assert len(conditional_deps) == 1
        assert conditional_deps[0].dependency_type == "success"
        assert conditional_deps[0].operation_id == child_op


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios"""

    def setup_method(self):
        """Set up test fixtures"""
        self.parser = BatchResponseParser()

    def test_partial_batch_failure_isolation(self):
        """Test that failed operations don't affect successful ones"""
        operations = [
            BatchOperation(id="success_op", method=RequestMethod.GET, url="/me"),
            BatchOperation(id="error_op", method=RequestMethod.GET, url="/invalid"),
            BatchOperation(id="another_success", method=RequestMethod.GET, url="/users")
        ]

        batch_request = BatchRequest(
            id="test_batch",
            operations=operations,
            user_id="test_user"
        )

        raw_response = {
            "responses": [
                {
                    "id": "success_op",
                    "status": 200,
                    "body": {"displayName": "John Smith"}
                },
                {
                    "id": "error_op",
                    "status": 404,
                    "body": {"error": {"message": "Resource not found"}}
                },
                {
                    "id": "another_success",
                    "status": 200,
                    "body": {"value": [{"displayName": "Jane Doe"}]}
                }
            ]
        }

        batch_response = self.parser.parse_response(raw_response, batch_request)

        assert batch_response.success_count == 2
        assert batch_response.error_count == 1

        # Successful operations should have their data
        success_op = batch_request.get_operation("success_op")
        another_success = batch_request.get_operation("another_success")
        error_op = batch_request.get_operation("error_op")

        assert success_op.status == OperationStatus.SUCCESS
        assert another_success.status == OperationStatus.SUCCESS
        assert error_op.status == OperationStatus.ERROR

        assert success_op.response["displayName"] == "John Smith"
        assert len(another_success.response["value"]) == 1

    def test_transient_error_classification(self):
        """Test classification of transient vs permanent errors"""
        operations = [
            BatchOperation(id="timeout_op", method=RequestMethod.GET, url="/slow"),
            BatchOperation(id="not_found_op", method=RequestMethod.GET, url="/missing"),
            BatchOperation(id="server_error_op", method=RequestMethod.GET, url="/broken")
        ]

        batch_request = BatchRequest(
            id="test_batch",
            operations=operations,
            user_id="test_user"
        )

        raw_response = {
            "responses": [
                {
                    "id": "timeout_op",
                    "status": 504,
                    "body": {"error": {"message": "Gateway timeout"}}
                },
                {
                    "id": "not_found_op",
                    "status": 404,
                    "body": {"error": {"message": "Resource not found"}}
                },
                {
                    "id": "server_error_op",
                    "status": 503,
                    "body": {"error": {"message": "Service unavailable"}}
                }
            ]
        }

        batch_response = self.parser.parse_response(raw_response, batch_request)

        # Check error classifications
        timeout_op = batch_request.get_operation("timeout_op")
        not_found_op = batch_request.get_operation("not_found_op")
        server_error_op = batch_request.get_operation("server_error_op")

        # Timeout and server error should be classified as transient
        assert timeout_op.response is not None
        assert server_error_op.response is not None
        assert not_found_op.response is not None

        timeout_context = timeout_op.response["error_context"]
        server_context = server_error_op.response["error_context"]

        assert timeout_context["retry_recommended"] is True
        assert server_context["retry_recommended"] is True

        # Not found should not be retryable
        not_found_context = not_found_op.response["error_context"]
        assert not_found_context["retry_recommended"] is False


class TestPerformanceAndOptimization:
    """Test performance monitoring and optimization features"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = BatchRequestConfig(
            enable_performance_monitoring=True,
            optimization_strategy=BatchOptimizationStrategy.PERFORMANCE_OPTIMIZED
        )
        self.executor = BatchExecutor(self.config)

    @pytest.mark.asyncio
    async def test_performance_tracking(self):
        """Test that performance metrics are tracked"""
        batch_request = BatchRequest(
            id="perf_test",
            operations=[
                BatchOperation(id="op1", method=RequestMethod.GET, url="/me")
            ],
            user_id="test_user"
        )

        with patch.object(self.executor, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.return_value = {
                "responses": [
                    {"id": "op1", "status": 200, "body": {"success": True}}
                ]
            }

            start_time = asyncio.get_event_loop().time()
            response = await self.executor.execute_batch(
                batch_request=batch_request,
                auth_token="test_token"
            )
            end_time = asyncio.get_event_loop().time()

            # Should have tracking data
            assert response.total_duration is not None
            assert response.total_duration > 0

    def test_large_batch_optimization(self):
        """Test optimization for large batches"""
        builder = BatchOperationBuilder(self.config)

        # Create a mix of different operation types
        for i in range(10):
            if i % 2 == 0:
                builder.add_operation(
                    method=RequestMethod.GET,
                    url=f"/read/resource{i}",
                    operation_id=f"read_{i}"
                )
            else:
                builder.add_operation(
                    method=RequestMethod.POST,
                    url=f"/write/resource{i}",
                    operation_id=f"write_{i}",
                    body={"data": f"value_{i}"}
                )

        batch_request = builder.build("user123")

        # Performance optimization should organize operations efficiently
        assert len(batch_request.operations) == 10

        # Should have good interleaving of read/write operations
        methods = [op.method for op in batch_request.operations]
        assert RequestMethod.GET in methods
        assert RequestMethod.POST in methods


class TestIntegrationScenarios:
    """Test complete integration scenarios"""

    @pytest.mark.asyncio
    async def test_complete_project_setup_scenario(self):
        """Test complete scenario: Create project, add members, assign tasks"""
        manager = get_batch_manager()
        builder = manager.create_builder()

        # Step 1: Create plan
        create_plan_id = builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans",
            body={
                "owner": "marketing_group@contoso.com",
                "title": "Product Launch Campaign"
            },
            operation_id="create_plan"
        )

        # Step 2: Create buckets (depends on plan creation)
        create_design_bucket_id = builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans/{plan-id}/buckets",
            body={"name": "Design Phase"},
            depends_on=[create_plan_id],
            operation_id="create_design_bucket"
        )

        create_dev_bucket_id = builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/plans/{plan-id}/buckets",
            body={"name": "Development Phase"},
            depends_on=[create_plan_id],
            operation_id="create_dev_bucket"
        )

        # Step 3: Create tasks (depends on buckets)
        builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/buckets/{bucket-id}/tasks",
            body={
                "title": "Design product mockups",
                "assigneePriority": "priority5"
            },
            depends_on=[create_design_bucket_id],
            operation_id="create_design_task"
        )

        builder.add_operation(
            method=RequestMethod.POST,
            url="/planner/buckets/{bucket-id}/tasks",
            body={
                "title": "Implement core features",
                "assigneePriority": "priority3"
            },
            depends_on=[create_dev_bucket_id],
            operation_id="create_dev_task"
        )

        batch_request = builder.build("project_manager@contoso.com", "contoso_tenant")

        # Verify dependency ordering
        operation_ids = [op.id for op in batch_request.operations]

        # Plan creation should come first
        plan_index = operation_ids.index("create_plan")

        # Bucket creation should come after plan
        design_bucket_index = operation_ids.index("create_design_bucket")
        dev_bucket_index = operation_ids.index("create_dev_bucket")

        assert plan_index < design_bucket_index
        assert plan_index < dev_bucket_index

        # Task creation should come after respective buckets
        design_task_index = operation_ids.index("create_design_task")
        dev_task_index = operation_ids.index("create_dev_task")

        assert design_bucket_index < design_task_index
        assert dev_bucket_index < dev_task_index

    @pytest.mark.asyncio
    async def test_error_recovery_scenario(self):
        """Test error recovery in complex dependency chain"""
        manager = get_batch_manager()

        # Create operations with complex dependencies
        operations = [
            BatchOperation(
                id="get_user",
                method=RequestMethod.GET,
                url="/me"
            ),
            BatchOperation(
                id="get_plans_valid",
                method=RequestMethod.GET,
                url="/me/planner/plans",
                depends_on=["get_user"]
            ),
            BatchOperation(
                id="get_plans_invalid",
                method=RequestMethod.GET,
                url="/invalid/endpoint",
                depends_on=["get_user"]
            ),
            BatchOperation(
                id="process_valid_plans",
                method=RequestMethod.POST,
                url="/analytics/process",
                depends_on=["get_plans_valid"]
            )
        ]

        batch_request = BatchRequest(
            id="error_recovery_test",
            operations=operations,
            user_id="test_user"
        )

        # Mock executor with mixed results
        mock_response = {
            "responses": [
                {
                    "id": "get_user",
                    "status": 200,
                    "body": {"displayName": "Test User"}
                },
                {
                    "id": "get_plans_valid",
                    "status": 200,
                    "body": {"value": [{"id": "plan1", "title": "Valid Plan"}]}
                },
                {
                    "id": "get_plans_invalid",
                    "status": 404,
                    "body": {"error": {"message": "Endpoint not found"}}
                },
                {
                    "id": "process_valid_plans",
                    "status": 201,
                    "body": {"status": "processed"}
                }
            ]
        }

        with patch.object(manager.executor, '_make_http_request', new_callable=AsyncMock) as mock_http:
            mock_http.return_value = mock_response

            response = await manager.execute_batch_operations(
                batch_request=batch_request,
                auth_token="test_token"
            )

            # Should have 3 successes and 1 error
            assert response.success_count == 3
            assert response.error_count == 1

            # Valid operations should succeed despite one failure
            get_user_op = batch_request.get_operation("get_user")
            get_plans_valid_op = batch_request.get_operation("get_plans_valid")
            process_plans_op = batch_request.get_operation("process_valid_plans")
            get_plans_invalid_op = batch_request.get_operation("get_plans_invalid")

            assert get_user_op.status == OperationStatus.SUCCESS
            assert get_plans_valid_op.status == OperationStatus.SUCCESS
            assert process_plans_op.status == OperationStatus.SUCCESS
            assert get_plans_invalid_op.status == OperationStatus.ERROR


# Convenience function tests
class TestConvenienceFunctions:
    """Test convenience functions and global utilities"""

    @pytest.mark.asyncio
    async def test_execute_batch_operations_function(self):
        """Test the convenience execute_batch_operations function"""
        operations = [
            BatchOperation(
                id="test_op",
                method=RequestMethod.GET,
                url="/me"
            )
        ]

        with patch('src.graph.batch_operations.get_batch_manager') as mock_manager:
            mock_batch_manager = Mock()
            mock_builder = Mock()
            mock_batch_request = Mock()
            mock_response = Mock()

            mock_manager.return_value = mock_batch_manager
            mock_batch_manager.create_builder.return_value = mock_builder
            mock_builder.build.return_value = mock_batch_request
            mock_batch_manager.execute_batch_operations = AsyncMock(return_value=mock_response)

            response = await execute_batch_operations(
                operations=operations,
                user_id="test_user",
                auth_token="test_token",
                tenant_id="test_tenant"
            )

            assert response == mock_response
            mock_builder.build.assert_called_once_with("test_user", "test_tenant")

    @pytest.mark.asyncio
    async def test_create_and_execute_batch_function(self):
        """Test the create_and_execute_batch convenience function"""
        builder, execute_func = await create_and_execute_batch(
            user_id="test_user",
            auth_token="test_token"
        )

        assert isinstance(builder, BatchOperationBuilder)
        assert callable(execute_func)

        # Add an operation to test the builder
        builder.add_operation(
            method=RequestMethod.GET,
            url="/me",
            operation_id="test_op"
        )

        # Mock the execution
        with patch.object(builder, 'build') as mock_build:
            mock_batch_request = Mock()
            mock_batch_request.id = "test_batch_id"
            mock_batch_request.operations = []
            mock_build.return_value = mock_batch_request

            with patch('src.graph.batch_operations.get_batch_manager') as mock_get_manager:
                mock_manager = Mock()
                mock_manager.execute_batch_operations = AsyncMock(return_value=Mock())
                mock_get_manager.return_value = mock_manager

                response = await execute_func()
                assert response is not None

    def test_get_batch_manager_singleton(self):
        """Test that get_batch_manager returns singleton instance"""
        manager1 = get_batch_manager()
        manager2 = get_batch_manager()

        assert manager1 is manager2  # Should be the same instance


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])