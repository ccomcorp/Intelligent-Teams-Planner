"""
Comprehensive batch operations system for Microsoft Graph API
Story 2.1 Task 1: Advanced batch operations with intelligent optimization and error handling
"""

import uuid
import time
import asyncio
from typing import Dict, List, Any, Optional, Callable, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
import structlog

from ..models.graph_models import (
    BatchOperation, BatchRequest, BatchResponse, RequestMethod,
    BatchRequestStatus, OperationStatus
)
from ..utils.error_handler import get_error_handler
from .rate_limiter import get_rate_limiter
from ..utils.performance_monitor import get_performance_monitor, track_operation


logger = structlog.get_logger(__name__)


class BatchOptimizationStrategy(str, Enum):
    """Batch optimization strategies"""
    FIFO = "fifo"  # First In, First Out
    DEPENDENCY_AWARE = "dependency_aware"  # Resolve dependencies first
    PRIORITY_BASED = "priority_based"  # Priority-based ordering
    PERFORMANCE_OPTIMIZED = "performance_optimized"  # Optimize for performance


class DependencyResolutionMethod(str, Enum):
    """Methods for resolving operation dependencies"""
    TOPOLOGICAL_SORT = "topological_sort"
    SEQUENTIAL = "sequential"
    PARALLEL_WHERE_POSSIBLE = "parallel_where_possible"


@dataclass
class BatchRequestConfig:
    """Configuration for batch request processing"""
    max_operations_per_batch: int = 20
    max_concurrent_batches: int = 5
    timeout_seconds: int = 300
    retry_on_failure: bool = True
    max_retries: int = 3
    optimization_strategy: BatchOptimizationStrategy = (
        BatchOptimizationStrategy.DEPENDENCY_AWARE
    )
    dependency_resolution: DependencyResolutionMethod = (
        DependencyResolutionMethod.TOPOLOGICAL_SORT
    )
    enable_correlation_tracking: bool = True
    enable_performance_monitoring: bool = True


@dataclass
class BatchExecutionContext:
    """Context for batch execution"""
    batch_request: BatchRequest
    config: BatchRequestConfig
    correlation_id: str
    start_time: datetime
    auth_token: Optional[str] = None
    base_url: str = "https://graph.microsoft.com/v1.0"
    custom_headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationDependency:
    """Represents a dependency between operations"""
    operation_id: str
    depends_on_id: str
    dependency_type: str = "completion"  # completion, success, data
    conditional: bool = False  # If true, operation is skipped if dependency fails


class BatchOperationBuilder:
    """Builder for creating batch operations with validation and optimization"""

    def __init__(self, config: Optional[BatchRequestConfig] = None):
        self.config = config or BatchRequestConfig()
        self.operations: List[BatchOperation] = []
        self.dependencies: List[OperationDependency] = []
        self.operation_priorities: Dict[str, int] = {}
        self.error_handler = get_error_handler()

    def add_operation(self,
                      method: RequestMethod,
                      url: str,
                      body: Optional[Dict[str, Any]] = None,
                      headers: Optional[Dict[str, str]] = None,
                      operation_id: Optional[str] = None,
                      depends_on: Optional[List[str]] = None,
                      priority: int = 100) -> str:
        """
        Add an operation to the batch

        Args:
            method: HTTP method
            url: Request URL (relative to Graph API base)
            body: Request body
            headers: Additional headers
            operation_id: Optional custom operation ID
            depends_on: List of operation IDs this depends on
            priority: Operation priority (lower = higher priority)

        Returns:
            Operation ID
        """
        if len(self.operations) >= self.config.max_operations_per_batch:
            raise ValueError(
                f"Batch size limit exceeded: {self.config.max_operations_per_batch}"
            )

        # Generate operation ID if not provided
        if not operation_id:
            operation_id = str(uuid.uuid4())

        # Validate URL format
        if not self._validate_url(url):
            raise ValueError(f"Invalid URL format: {url}")

        # Create operation
        operation = BatchOperation(
            id=operation_id,
            method=method,
            url=url,
            body=body,
            headers=headers or {},
            depends_on=depends_on
        )

        self.operations.append(operation)
        self.operation_priorities[operation_id] = priority

        # Track dependencies
        if depends_on:
            for dep_id in depends_on:
                self.dependencies.append(OperationDependency(
                    operation_id=operation_id,
                    depends_on_id=dep_id
                ))

        logger.debug("Operation added to batch",
                     operation_id=operation_id,
                     method=method,
                     url=url,
                     depends_on=depends_on,
                     priority=priority)

        return operation_id

    def add_conditional_operation(self,
                                  method: RequestMethod,
                                  url: str,
                                  depends_on_success: str,
                                  body: Optional[Dict[str, Any]] = None,
                                  headers: Optional[Dict[str, str]] = None,
                                  operation_id: Optional[str] = None) -> str:
        """
        Add an operation that only executes if dependency succeeds

        Args:
            method: HTTP method
            url: Request URL
            depends_on_success: Operation ID that must succeed
            body: Request body
            headers: Additional headers
            operation_id: Optional custom operation ID

        Returns:
            Operation ID
        """
        operation_id = self.add_operation(
            method=method,
            url=url,
            body=body,
            headers=headers,
            operation_id=operation_id,
            depends_on=[depends_on_success]
        )

        # Mark as conditional
        self.dependencies.append(OperationDependency(
            operation_id=operation_id,
            depends_on_id=depends_on_success,
            dependency_type="success",
            conditional=True
        ))

        return operation_id

    def build(self, user_id: str, tenant_id: Optional[str] = None) -> BatchRequest:
        """
        Build and optimize the batch request

        Args:
            user_id: User ID for the request
            tenant_id: Optional tenant ID

        Returns:
            Optimized BatchRequest
        """
        if not self.operations:
            raise ValueError("Cannot build empty batch request")

        # Validate dependencies
        self._validate_dependencies()

        # Optimize operation order
        optimized_operations = self._optimize_operations()

        # Create batch request
        batch_request = BatchRequest(
            id=str(uuid.uuid4()),
            operations=optimized_operations,
            user_id=user_id,
            tenant_id=tenant_id,
            metadata={
                "builder_config": {
                    "strategy": self.config.optimization_strategy,
                    "dependency_resolution": self.config.dependency_resolution,
                    "total_dependencies": len(self.dependencies)
                },
                "operation_priorities": self.operation_priorities.copy()
            }
        )

        logger.info("Batch request built",
                    batch_id=batch_request.id,
                    operation_count=len(optimized_operations),
                    dependency_count=len(self.dependencies),
                    strategy=self.config.optimization_strategy)

        return batch_request

    def _validate_url(self, url: str) -> bool:
        """Validate URL format for Graph API"""
        # Remove leading slash if present
        url = url.lstrip('/')

        # Basic validation patterns
        invalid_patterns = [
            'javascript:',
            'data:',
            'file:',
            'ftp:',
            '..'
        ]

        url_lower = url.lower()
        for pattern in invalid_patterns:
            if pattern in url_lower:
                return False

        return True

    def _validate_dependencies(self) -> None:
        """Validate that all dependencies reference valid operations"""
        operation_ids = {op.id for op in self.operations}

        for dependency in self.dependencies:
            if dependency.operation_id not in operation_ids:
                raise ValueError(
                    f"Invalid dependency: operation {dependency.operation_id} not found"
                )
            if dependency.depends_on_id not in operation_ids:
                raise ValueError(
                    f"Invalid dependency: operation {dependency.depends_on_id} not found"
                )

        # Check for circular dependencies
        self._check_circular_dependencies()

    def _check_circular_dependencies(self) -> None:
        """Check for circular dependencies using depth-first search"""
        dependency_graph = {}
        for op in self.operations:
            dependency_graph[op.id] = op.depends_on or []

        visited = set()
        rec_stack = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependency_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in dependency_graph:
            if node not in visited:
                if has_cycle(node):
                    raise ValueError(
                        "Circular dependency detected in batch operations"
                    )

    def _optimize_operations(self) -> List[BatchOperation]:
        """Optimize operation order based on strategy"""
        if self.config.optimization_strategy == BatchOptimizationStrategy.FIFO:
            return self.operations.copy()

        elif self.config.optimization_strategy == BatchOptimizationStrategy.DEPENDENCY_AWARE:
            return self._topological_sort()

        elif self.config.optimization_strategy == BatchOptimizationStrategy.PRIORITY_BASED:
            return self._priority_sort()

        elif self.config.optimization_strategy == BatchOptimizationStrategy.PERFORMANCE_OPTIMIZED:
            return self._performance_optimize()

        return self.operations.copy()

    def _topological_sort(self) -> List[BatchOperation]:
        """Sort operations using topological sort to respect dependencies"""
        # Build adjacency list
        graph: Dict[str, List[str]] = {op.id: [] for op in self.operations}
        in_degree = {op.id: 0 for op in self.operations}

        for op in self.operations:
            if op.depends_on:
                for dep_id in op.depends_on:
                    graph[dep_id].append(op.id)
                    in_degree[op.id] += 1

        # Kahn's algorithm
        queue = [op_id for op_id in in_degree if in_degree[op_id] == 0]
        sorted_ops = []

        while queue:
            op_id = queue.pop(0)
            sorted_ops.append(op_id)

            for neighbor in graph[op_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Convert back to BatchOperation objects
        op_map = {op.id: op for op in self.operations}
        return [op_map[op_id] for op_id in sorted_ops]

    def _priority_sort(self) -> List[BatchOperation]:
        """Sort operations by priority, then by dependencies"""
        # First do topological sort to respect dependencies
        topo_sorted = self._topological_sort()

        # Then sort by priority within dependency levels
        return sorted(topo_sorted, key=lambda op: self.operation_priorities.get(op.id, 100))

    def _performance_optimize(self) -> List[BatchOperation]:
        """Optimize for performance based on operation types and sizes"""
        # Start with dependency-aware sorting
        sorted_ops = self._topological_sort()

        # Group operations by type for better batching
        read_ops = []
        write_ops = []
        other_ops = []

        for op in sorted_ops:
            if op.method == RequestMethod.GET:
                read_ops.append(op)
            elif op.method in [RequestMethod.POST, RequestMethod.PUT, RequestMethod.PATCH]:
                write_ops.append(op)
            else:
                other_ops.append(op)

        # Interleave for better performance (reads can often be parallelized)
        optimized = []
        max_len = max(len(read_ops), len(write_ops), len(other_ops))

        for i in range(max_len):
            if i < len(read_ops):
                optimized.append(read_ops[i])
            if i < len(write_ops):
                optimized.append(write_ops[i])
            if i < len(other_ops):
                optimized.append(other_ops[i])

        return optimized


class BatchResponseParser:
    """Parser for batch response with comprehensive error handling"""

    def __init__(self):
        self.error_handler = get_error_handler()

    def parse_response(self, raw_response: Dict[str, Any], batch_request: BatchRequest) -> BatchResponse:
        """
        Parse raw batch response and update operation statuses

        Args:
            raw_response: Raw response from Graph API
            batch_request: Original batch request

        Returns:
            Parsed BatchResponse with operation results
        """
        start_time = time.time()

        try:
            # Extract responses array
            if "responses" not in raw_response:
                raise ValueError("Invalid batch response: missing 'responses' field")

            responses = raw_response["responses"]
            if not isinstance(responses, list):
                raise ValueError("Invalid batch response: 'responses' must be a list")

            # Create operation lookup
            operation_map = {op.id: op for op in batch_request.operations}

            # Process each response
            for response_data in responses:
                self._process_individual_response(response_data, operation_map, batch_request.id)

            # Update batch statistics
            batch_request.update_statistics()

            # Create batch response
            batch_response = BatchResponse(
                batch_id=batch_request.id,
                responses=responses,
                total_duration=time.time() - start_time
            )

            logger.info("Batch response parsed successfully",
                        batch_id=batch_request.id,
                        success_count=batch_response.success_count,
                        error_count=batch_response.error_count,
                        total_duration=batch_response.total_duration)

            return batch_response

        except Exception as e:
            error_context = self.error_handler.classify_error(e, {
                "operation": "batch_response_parsing",
                "batch_id": batch_request.id
            })

            logger.error("Failed to parse batch response",
                         batch_id=batch_request.id,
                         error=str(e),
                         correlation_id=error_context.correlation_id)

            raise

    def _process_individual_response(self,
                                     response_data: Dict[str, Any],
                                     operation_map: Dict[str, BatchOperation],
                                     batch_id: str) -> None:
        """Process an individual operation response"""
        operation_id = response_data.get("id")
        status_code = response_data.get("status", 0)
        response_body = response_data.get("body", {})

        if not operation_id or operation_id not in operation_map:
            logger.warning("Response for unknown operation",
                           operation_id=operation_id,
                           batch_id=batch_id)
            return

        operation = operation_map[operation_id]

        # Update operation based on status code
        if 200 <= status_code < 300:
            operation.status = OperationStatus.SUCCESS
            operation.response = response_body
        else:
            operation.status = OperationStatus.ERROR
            operation.error = self._extract_error_message(response_body)

            # Classify the error for better handling
            error_context = self.error_handler.classify_error(
                response_body,
                {
                    "operation": f"batch_operation_{operation_id}",
                    "status_code": status_code,
                    "batch_id": batch_id,
                    "endpoint": operation.url
                }
            )

            operation.response = {
                "error": response_body,
                "error_context": {
                    "category": error_context.additional_details.get("category"),
                    "severity": error_context.additional_details.get("severity"),
                    "retry_recommended": error_context.additional_details.get("retry_recommended"),
                    "correlation_id": error_context.correlation_id
                }
            }

        logger.debug("Operation response processed",
                     operation_id=operation_id,
                     status_code=status_code,
                     operation_status=operation.status,
                     batch_id=batch_id)

    def _extract_error_message(self, response_body: Dict[str, Any]) -> str:
        """Extract error message from response body"""
        if isinstance(response_body, dict):
            # Try common error message fields
            for error_field in ["message", "error_description", "error"]:
                if error_field in response_body:
                    if isinstance(response_body[error_field], dict):
                        return response_body[error_field].get("message", str(response_body[error_field]))
                    return str(response_body[error_field])

            # Try nested error object
            if "error" in response_body and isinstance(response_body["error"], dict):
                error_obj = response_body["error"]
                if "message" in error_obj:
                    return error_obj["message"]

        return str(response_body)


class BatchExecutor:
    """Executes batch operations with intelligent retry and error handling"""

    def __init__(self, config: Optional[BatchRequestConfig] = None):
        self.config = config or BatchRequestConfig()
        self.rate_limiter = get_rate_limiter()
        self.performance_monitor = get_performance_monitor()
        self.error_handler = get_error_handler()
        self.response_parser = BatchResponseParser()

    @track_operation("batch_execution")
    async def execute_batch(self,
                            batch_request: BatchRequest,
                            auth_token: str,
                            base_url: str = "https://graph.microsoft.com/v1.0",
                            custom_headers: Optional[Dict[str, str]] = None) -> BatchResponse:
        """
        Execute a batch request with comprehensive error handling and monitoring

        Args:
            batch_request: The batch request to execute
            auth_token: Authentication token
            base_url: Graph API base URL
            custom_headers: Additional headers

        Returns:
            BatchResponse with results
        """
        correlation_id = str(uuid.uuid4())

        execution_context = BatchExecutionContext(
            batch_request=batch_request,
            config=self.config,
            correlation_id=correlation_id,
            start_time=datetime.now(timezone.utc),
            auth_token=auth_token,
            base_url=base_url,
            custom_headers=custom_headers or {}
        )

        logger.info("Starting batch execution",
                    batch_id=batch_request.id,
                    operation_count=len(batch_request.operations),
                    correlation_id=correlation_id)

        try:
            batch_request.status = BatchRequestStatus.PROCESSING

            # Check rate limits before execution
            await self._check_rate_limits(execution_context)

            # Execute with retry logic
            response = await self._execute_with_retry(execution_context)

            # Parse response
            batch_response = self.response_parser.parse_response(response, batch_request)

            # Record successful execution
            await self.rate_limiter.record_request_result(
                endpoint="/$batch",
                success=True,
                tenant_id=batch_request.tenant_id,
                user_id=batch_request.user_id
            )

            batch_request.status = BatchRequestStatus.COMPLETED
            batch_request.completed_at = datetime.now(timezone.utc)

            logger.info("Batch execution completed successfully",
                        batch_id=batch_request.id,
                        success_count=batch_response.success_count,
                        error_count=batch_response.error_count,
                        correlation_id=correlation_id)

            return batch_response

        except Exception as e:
            # Record failed execution
            await self.rate_limiter.record_request_result(
                endpoint="/$batch",
                success=False,
                tenant_id=batch_request.tenant_id,
                user_id=batch_request.user_id
            )

            batch_request.status = BatchRequestStatus.FAILED

            error_context = self.error_handler.classify_error(e, {
                "operation": "batch_execution",
                "batch_id": batch_request.id,
                "correlation_id": correlation_id,
                "user_id": batch_request.user_id,
                "tenant_id": batch_request.tenant_id
            })

            logger.error("Batch execution failed",
                         batch_id=batch_request.id,
                         error=str(e),
                         correlation_id=correlation_id,
                         error_category=error_context.additional_details.get("category"))

            raise

    async def _check_rate_limits(self, context: BatchExecutionContext) -> None:
        """Check rate limits before batch execution"""
        rate_limit_check = await self.rate_limiter.check_rate_limit(
            endpoint="/$batch",
            tenant_id=context.batch_request.tenant_id,
            user_id=context.batch_request.user_id
        )

        if not rate_limit_check["allowed"]:
            delay = rate_limit_check["delay"]
            reason = rate_limit_check["reason"]

            logger.warning("Rate limit detected, waiting before batch execution",
                           batch_id=context.batch_request.id,
                           delay=delay,
                           reason=reason)

            if delay > 0:
                await asyncio.sleep(delay)

    async def _execute_with_retry(self, context: BatchExecutionContext) -> Dict[str, Any]:
        """Execute batch request with retry logic"""
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # Prepare request
                request_data = self._prepare_batch_request(context)

                # Execute HTTP request
                response = await self._make_http_request(request_data, context)

                # Check for batch-level errors
                if self._is_batch_success(response):
                    return response

                # Handle batch-level errors
                error_msg = self._extract_batch_error(response)
                raise Exception(f"Batch request failed: {error_msg}")

            except Exception as e:
                last_exception = e

                # Classify error to determine if retry is appropriate
                error_context = self.error_handler.classify_error(e, {
                    "operation": "batch_http_request",
                    "batch_id": context.batch_request.id,
                    "attempt": attempt + 1,
                    "correlation_id": context.correlation_id
                })

                should_retry = (
                    attempt < self.config.max_retries and
                    self.config.retry_on_failure and
                    self.error_handler.should_retry(error_context)
                )

                if should_retry:
                    delay = self.error_handler.calculate_backoff_delay(error_context)

                    logger.warning("Batch request failed, retrying",
                                   batch_id=context.batch_request.id,
                                   attempt=attempt + 1,
                                   delay=delay,
                                   error=str(e))

                    if delay > 0:
                        await asyncio.sleep(delay)
                else:
                    logger.error("Batch request failed, no more retries",
                                 batch_id=context.batch_request.id,
                                 attempt=attempt + 1,
                                 error=str(e))
                    break

        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise Exception("Batch execution failed after all retries")

    def _prepare_batch_request(self, context: BatchExecutionContext) -> Dict[str, Any]:
        """Prepare the HTTP request data for batch execution"""
        # Build requests array
        requests = []
        for operation in context.batch_request.operations:
            request_data = {
                "id": operation.id,
                "method": operation.method.value,
                "url": operation.url
            }

            if operation.body:
                request_data["body"] = operation.body

            if operation.headers:
                request_data["headers"] = operation.headers

            requests.append(request_data)

        batch_payload = {
            "requests": requests
        }

        return {
            "url": f"{context.base_url}/$batch",
            "method": "POST",
            "headers": {
                "Authorization": f"Bearer {context.auth_token}",
                "Content-Type": "application/json",
                **context.custom_headers
            },
            "data": batch_payload
        }

    async def _make_http_request(self, request_data: Dict[str, Any], context: BatchExecutionContext) -> Dict[str, Any]:
        """Make the actual HTTP request (placeholder for actual HTTP client)"""
        # This is a placeholder for the actual HTTP request implementation
        # In a real implementation, this would use aiohttp, httpx, or similar

        # For now, simulate a successful batch response
        # This should be replaced with actual HTTP client logic

        # Simulate processing time
        await asyncio.sleep(0.1)

        # Build mock response based on operations
        responses = []
        for operation in context.batch_request.operations:
            # Simulate successful responses
            response = {
                "id": operation.id,
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {"@odata.context": "mock", "value": "success"}
            }
            responses.append(response)

        return {"responses": responses}

    def _is_batch_success(self, response: Dict[str, Any]) -> bool:
        """Check if batch request was successful at the batch level"""
        return "responses" in response and isinstance(response["responses"], list)

    def _extract_batch_error(self, response: Dict[str, Any]) -> str:
        """Extract error message from failed batch response"""
        if "error" in response:
            error = response["error"]
            if isinstance(error, dict) and "message" in error:
                return error["message"]
            return str(error)
        return "Unknown batch error"


class BatchOperationsManager:
    """High-level manager for batch operations with advanced features"""

    def __init__(self, config: Optional[BatchRequestConfig] = None):
        self.config = config or BatchRequestConfig()
        self.executor = BatchExecutor(self.config)
        self.performance_monitor = get_performance_monitor()
        self.active_batches: Dict[str, BatchRequest] = {}

    def create_builder(self) -> BatchOperationBuilder:
        """Create a new batch operation builder"""
        return BatchOperationBuilder(self.config)

    @track_operation("batch_operations_execute")
    async def execute_batch_operations(self,
                                       batch_request: BatchRequest,
                                       auth_token: str,
                                       base_url: str = "https://graph.microsoft.com/v1.0") -> BatchResponse:
        """
        Execute batch operations with full monitoring and error handling

        Args:
            batch_request: The batch request to execute
            auth_token: Authentication token
            base_url: Graph API base URL

        Returns:
            BatchResponse with results
        """
        # Track active batch
        self.active_batches[batch_request.id] = batch_request

        try:
            # Execute the batch
            response = await self.executor.execute_batch(
                batch_request=batch_request,
                auth_token=auth_token,
                base_url=base_url
            )

            return response

        finally:
            # Remove from active batches
            self.active_batches.pop(batch_request.id, None)

    async def execute_operations_in_chunks(self,
                                           operations: List[BatchOperation],
                                           user_id: str,
                                           auth_token: str,
                                           tenant_id: Optional[str] = None,
                                           chunk_size: Optional[int] = None) -> List[BatchResponse]:
        """
        Execute a large list of operations by chunking into multiple batches

        Args:
            operations: List of operations to execute
            user_id: User ID
            auth_token: Authentication token
            tenant_id: Optional tenant ID
            chunk_size: Override default chunk size

        Returns:
            List of BatchResponse objects
        """
        chunk_size = chunk_size or self.config.max_operations_per_batch

        if len(operations) <= chunk_size:
            # Single batch
            builder = self.create_builder()
            for op in operations:
                builder.operations.append(op)

            batch_request = builder.build(user_id, tenant_id)
            response = await self.execute_batch_operations(batch_request, auth_token)
            return [response]

        # Multiple batches
        responses = []
        for i in range(0, len(operations), chunk_size):
            chunk = operations[i:i + chunk_size]

            builder = self.create_builder()
            for op in chunk:
                builder.operations.append(op)

            batch_request = builder.build(user_id, tenant_id)
            response = await self.execute_batch_operations(batch_request, auth_token)
            responses.append(response)

        logger.info("Chunked batch execution completed",
                    total_operations=len(operations),
                    chunk_count=len(responses),
                    chunk_size=chunk_size)

        return responses

    def get_active_batches(self) -> List[BatchRequest]:
        """Get list of currently active batch requests"""
        return list(self.active_batches.values())

    def get_batch_status(self, batch_id: str) -> Optional[BatchRequest]:
        """Get status of a specific batch request"""
        return self.active_batches.get(batch_id)

    async def cancel_batch(self, batch_id: str) -> bool:
        """
        Cancel an active batch request (if possible)

        Note: This is a placeholder for cancellation logic
        Actual implementation would depend on HTTP client capabilities
        """
        if batch_id in self.active_batches:
            batch_request = self.active_batches[batch_id]
            batch_request.status = BatchRequestStatus.FAILED

            logger.info("Batch request cancelled", batch_id=batch_id)
            return True

        return False


# Global batch operations manager
_batch_manager: Optional[BatchOperationsManager] = None


def get_batch_manager(config: Optional[BatchRequestConfig] = None) -> BatchOperationsManager:
    """Get or create global batch operations manager"""
    global _batch_manager
    if _batch_manager is None:
        _batch_manager = BatchOperationsManager(config or BatchRequestConfig())
    return _batch_manager


# Convenience functions
async def execute_batch_operations(operations: List[BatchOperation],
                                   user_id: str,
                                   auth_token: str,
                                   tenant_id: Optional[str] = None,
                                   config: Optional[BatchRequestConfig] = None) -> BatchResponse:
    """
    Convenience function to execute batch operations

    Args:
        operations: List of operations to execute
        user_id: User ID
        auth_token: Authentication token
        tenant_id: Optional tenant ID
        config: Optional batch configuration

    Returns:
        BatchResponse with results
    """
    manager = get_batch_manager(config)

    # Build batch request
    builder = manager.create_builder()
    for op in operations:
        builder.operations.append(op)

    batch_request = builder.build(user_id, tenant_id)

    # Execute
    return await manager.execute_batch_operations(batch_request, auth_token)


async def create_and_execute_batch(user_id: str,
                                   auth_token: str,
                                   tenant_id: Optional[str] = None,
                                   config: Optional[BatchRequestConfig] = None
                                   ) -> Tuple[BatchOperationBuilder, Callable]:
    """
    Create a batch builder and return execution function

    Args:
        user_id: User ID
        auth_token: Authentication token
        tenant_id: Optional tenant ID
        config: Optional batch configuration

    Returns:
        Tuple of (builder, execute_function)
    """
    manager = get_batch_manager(config)
    builder = manager.create_builder()

    async def execute() -> BatchResponse:
        batch_request = builder.build(user_id, tenant_id)
        return await manager.execute_batch_operations(batch_request, auth_token)

    return builder, execute
