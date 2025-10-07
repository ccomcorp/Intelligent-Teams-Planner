"""
Batch Operation Processing for Natural Language Commands
Story 1.3 Task 5: Batch operation support with progress tracking
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BatchOperation:
    """Represents a single operation in a batch"""
    operation_id: str
    operation_type: str  # 'create', 'update', 'delete', etc.
    parameters: Dict[str, Any]
    status: str = 'pending'  # 'pending', 'running', 'completed', 'failed'
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class BatchJob:
    """Represents a complete batch job"""
    job_id: str
    user_id: str
    session_id: str
    operations: List[BatchOperation]
    total_operations: int
    created_at: datetime
    completed_operations: int = 0
    failed_operations: int = 0
    status: str = 'pending'  # 'pending', 'running', 'completed', 'partial', 'failed'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class BatchProcessor:
    """
    Processes batch operations for natural language commands
    Supports operations like "create 5 tasks for project Alpha"
    """

    def __init__(self, max_batch_size: int = 50):
        self.max_batch_size = max_batch_size
        self.active_jobs: Dict[str, BatchJob] = {}

        # Batch command patterns
        self.batch_patterns = {
            # Create multiple tasks
            r'(?:create|add|make)\s+(\d+)\s+(?:tasks?|items?)(?:\s+for\s+(.+?))?(?:\s|$)': 'create_multiple_tasks',
            r'(?:create|add|make)\s+(multiple|several|many)\s+(?:tasks?|items?)(?:\s+for\s+(.+?))?(?:\s|$)': 'create_multiple_tasks',

            # Delete multiple tasks
            r'(?:delete|remove)\s+(?:all\s+)?(?:completed|done|finished)\s+(?:tasks?|items?)': 'delete_completed_tasks',
            r'(?:delete|remove)\s+(?:all\s+)?(?:tasks?|items?)\s+(?:from|for)\s+(.+?)(?:\s|$)': 'delete_tasks_from_project',

            # Update multiple tasks
            r'(?:update|change|modify)\s+(?:all\s+)?(?:tasks?|items?)\s+(?:from|for|in)\s+(.+?)\s+(?:to|as)\s+(.+?)(?:\s|$)': 'update_tasks_in_project',
            r'(?:mark|set)\s+(?:all\s+)?(?:completed|done|finished)\s+(?:tasks?|items?)\s+(?:as|to)\s+(.+?)(?:\s|$)': 'mark_tasks_status',

            # Assign multiple tasks
            r'(?:assign|give|delegate)\s+(?:all\s+)?(?:tasks?|items?)\s+(?:from|for|in)\s+(.+?)\s+(?:to)\s+(.+?)(?:\s|$)': 'assign_tasks_in_project',
        }

    async def detect_batch_operation(self, user_input: str, entities: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Detect if user input represents a batch operation

        Args:
            user_input: User's natural language input
            entities: Extracted entities

        Returns:
            Batch operation details or None
        """
        try:
            normalized_input = user_input.lower().strip()

            for pattern, operation_type in self.batch_patterns.items():
                match = re.search(pattern, normalized_input, re.IGNORECASE)
                if match:
                    return {
                        "is_batch": True,
                        "operation_type": operation_type,
                        "pattern_match": match,
                        "groups": match.groups(),
                        "entities": entities
                    }

            # Check for numeric quantities in entities
            if "QUANTITY" in entities:
                try:
                    quantity = int(entities["QUANTITY"])
                    if quantity > 1:
                        return {
                            "is_batch": True,
                            "operation_type": "create_multiple_tasks",
                            "quantity": quantity,
                            "entities": entities
                        }
                except (ValueError, TypeError):
                    pass

            return None

        except Exception as e:
            logger.error("Error detecting batch operation", error=str(e), user_input=user_input[:100])
            return None

    async def create_batch_job(self, user_id: str, session_id: str, operation_type: str,
                              parameters: Dict[str, Any]) -> BatchJob:
        """
        Create a new batch job

        Args:
            user_id: User identifier
            session_id: Session identifier
            operation_type: Type of batch operation
            parameters: Operation parameters

        Returns:
            Created BatchJob
        """
        try:
            job_id = f"batch_{int(datetime.now().timestamp())}_{user_id[:8]}"

            # Generate individual operations based on type
            operations = await self._generate_operations(operation_type, parameters)

            # Validate batch size
            if len(operations) > self.max_batch_size:
                raise ValueError(f"Batch size {len(operations)} exceeds maximum {self.max_batch_size}")

            batch_job = BatchJob(
                job_id=job_id,
                user_id=user_id,
                session_id=session_id,
                operations=operations,
                total_operations=len(operations),
                status='pending',
                created_at=datetime.now(timezone.utc),
                metadata={
                    "operation_type": operation_type,
                    "parameters": parameters
                }
            )

            self.active_jobs[job_id] = batch_job

            logger.info("Created batch job",
                       job_id=job_id,
                       user_id=user_id,
                       operation_count=len(operations))

            return batch_job

        except Exception as e:
            logger.error("Error creating batch job", error=str(e))
            raise

    async def _generate_operations(self, operation_type: str, parameters: Dict[str, Any]) -> List[BatchOperation]:
        """Generate individual operations for a batch job"""
        operations = []
        operation_id_base = int(datetime.now().timestamp())

        try:
            if operation_type == "create_multiple_tasks":
                quantity = parameters.get("quantity", 1)
                if isinstance(quantity, str):
                    # Convert word numbers to integers
                    word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "several": 3, "multiple": 3, "many": 5}
                    quantity = word_to_num.get(quantity.lower(), 1)

                base_task = parameters.get("task_template", {})

                for i in range(quantity):
                    operation = BatchOperation(
                        operation_id=f"{operation_id_base}_{i}",
                        operation_type="create_task",
                        parameters={
                            **base_task,
                            "title": f"{base_task.get('title', 'Task')} {i + 1}",
                            "batch_index": i + 1,
                            "batch_total": quantity
                        }
                    )
                    operations.append(operation)

            elif operation_type == "delete_completed_tasks":
                # This would be handled by querying existing tasks first
                operation = BatchOperation(
                    operation_id=f"{operation_id_base}_0",
                    operation_type="query_and_delete_tasks",
                    parameters={
                        "filter": {"status": "completed"},
                        **parameters
                    }
                )
                operations.append(operation)

            elif operation_type == "delete_tasks_from_project":
                project_name = parameters.get("project_name")
                operation = BatchOperation(
                    operation_id=f"{operation_id_base}_0",
                    operation_type="query_and_delete_tasks",
                    parameters={
                        "filter": {"plan_name": project_name},
                        **parameters
                    }
                )
                operations.append(operation)

            elif operation_type == "update_tasks_in_project":
                project_name = parameters.get("project_name")
                update_data = parameters.get("update_data", {})
                operation = BatchOperation(
                    operation_id=f"{operation_id_base}_0",
                    operation_type="query_and_update_tasks",
                    parameters={
                        "filter": {"plan_name": project_name},
                        "update_data": update_data,
                        **parameters
                    }
                )
                operations.append(operation)

            elif operation_type == "assign_tasks_in_project":
                project_name = parameters.get("project_name")
                assignee = parameters.get("assignee")
                operation = BatchOperation(
                    operation_id=f"{operation_id_base}_0",
                    operation_type="query_and_update_tasks",
                    parameters={
                        "filter": {"plan_name": project_name},
                        "update_data": {"assignee": assignee},
                        **parameters
                    }
                )
                operations.append(operation)

            else:
                raise ValueError(f"Unknown batch operation type: {operation_type}")

            return operations

        except Exception as e:
            logger.error("Error generating operations", error=str(e), operation_type=operation_type)
            raise

    async def execute_batch_job(self, job_id: str,
                               operation_executor: callable) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute a batch job with progress tracking

        Args:
            job_id: Batch job identifier
            operation_executor: Async function to execute individual operations

        Yields:
            Progress updates
        """
        try:
            if job_id not in self.active_jobs:
                raise ValueError(f"Batch job {job_id} not found")

            batch_job = self.active_jobs[job_id]
            batch_job.status = 'running'
            batch_job.started_at = datetime.now(timezone.utc)

            logger.info("Starting batch job execution",
                       job_id=job_id,
                       total_operations=batch_job.total_operations)

            # Yield initial progress
            yield {
                "job_id": job_id,
                "status": "started",
                "progress": 0,
                "message": f"Starting batch job with {batch_job.total_operations} operations"
            }

            # Execute operations
            for i, operation in enumerate(batch_job.operations):
                try:
                    operation.status = 'running'
                    operation.started_at = datetime.now(timezone.utc)

                    # Execute the operation
                    result = await operation_executor(operation.operation_type, operation.parameters)

                    operation.status = 'completed'
                    operation.result = result
                    operation.completed_at = datetime.now(timezone.utc)
                    batch_job.completed_operations += 1

                    logger.debug("Completed batch operation",
                                job_id=job_id,
                                operation_id=operation.operation_id,
                                operation_type=operation.operation_type)

                except Exception as op_error:
                    operation.status = 'failed'
                    operation.error = str(op_error)
                    operation.completed_at = datetime.now(timezone.utc)
                    batch_job.failed_operations += 1

                    logger.warning("Batch operation failed",
                                  job_id=job_id,
                                  operation_id=operation.operation_id,
                                  error=str(op_error))

                # Yield progress update
                progress = ((i + 1) / batch_job.total_operations) * 100
                yield {
                    "job_id": job_id,
                    "status": "progress",
                    "progress": progress,
                    "completed": batch_job.completed_operations,
                    "failed": batch_job.failed_operations,
                    "total": batch_job.total_operations,
                    "current_operation": operation.operation_type,
                    "message": f"Completed {batch_job.completed_operations}/{batch_job.total_operations} operations"
                }

            # Finalize job status
            batch_job.completed_at = datetime.now(timezone.utc)

            if batch_job.failed_operations == 0:
                batch_job.status = 'completed'
                final_message = f"All {batch_job.total_operations} operations completed successfully"
            elif batch_job.completed_operations == 0:
                batch_job.status = 'failed'
                final_message = f"All {batch_job.total_operations} operations failed"
            else:
                batch_job.status = 'partial'
                final_message = f"Completed {batch_job.completed_operations}/{batch_job.total_operations} operations"

            # Yield final progress
            yield {
                "job_id": job_id,
                "status": batch_job.status,
                "progress": 100,
                "completed": batch_job.completed_operations,
                "failed": batch_job.failed_operations,
                "total": batch_job.total_operations,
                "message": final_message,
                "duration": (batch_job.completed_at - batch_job.started_at).total_seconds()
            }

            logger.info("Completed batch job execution",
                       job_id=job_id,
                       status=batch_job.status,
                       completed=batch_job.completed_operations,
                       failed=batch_job.failed_operations)

        except Exception as e:
            # Mark job as failed
            if job_id in self.active_jobs:
                self.active_jobs[job_id].status = 'failed'
                self.active_jobs[job_id].completed_at = datetime.now(timezone.utc)

            logger.error("Error executing batch job", error=str(e), job_id=job_id)

            yield {
                "job_id": job_id,
                "status": "failed",
                "progress": 0,
                "message": f"Batch job failed: {str(e)}",
                "error": str(e)
            }

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a batch job

        Args:
            job_id: Batch job identifier

        Returns:
            Job status dictionary or None
        """
        try:
            if job_id not in self.active_jobs:
                return None

            batch_job = self.active_jobs[job_id]

            return {
                "job_id": job_id,
                "status": batch_job.status,
                "total_operations": batch_job.total_operations,
                "completed_operations": batch_job.completed_operations,
                "failed_operations": batch_job.failed_operations,
                "progress_percent": (batch_job.completed_operations / batch_job.total_operations) * 100,
                "created_at": batch_job.created_at.isoformat(),
                "started_at": batch_job.started_at.isoformat() if batch_job.started_at else None,
                "completed_at": batch_job.completed_at.isoformat() if batch_job.completed_at else None,
                "metadata": batch_job.metadata
            }

        except Exception as e:
            logger.error("Error getting job status", error=str(e), job_id=job_id)
            return None

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running batch job

        Args:
            job_id: Batch job identifier

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            if job_id not in self.active_jobs:
                return False

            batch_job = self.active_jobs[job_id]

            if batch_job.status in ['completed', 'failed']:
                return False  # Cannot cancel completed jobs

            batch_job.status = 'cancelled'
            batch_job.completed_at = datetime.now(timezone.utc)

            logger.info("Cancelled batch job", job_id=job_id)
            return True

        except Exception as e:
            logger.error("Error cancelling job", error=str(e), job_id=job_id)
            return False

    async def cleanup_completed_jobs(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed batch jobs older than specified age

        Args:
            max_age_hours: Maximum age in hours for completed jobs

        Returns:
            Number of jobs cleaned up
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            jobs_to_remove = []

            for job_id, batch_job in self.active_jobs.items():
                if (batch_job.status in ['completed', 'failed', 'cancelled'] and
                    batch_job.completed_at and batch_job.completed_at < cutoff_time):
                    jobs_to_remove.append(job_id)

            for job_id in jobs_to_remove:
                del self.active_jobs[job_id]

            logger.info("Cleaned up batch jobs", count=len(jobs_to_remove))
            return len(jobs_to_remove)

        except Exception as e:
            logger.error("Error cleaning up jobs", error=str(e))
            return 0

    def get_batch_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get summary of batch jobs for a user

        Args:
            user_id: User identifier

        Returns:
            Summary dictionary
        """
        try:
            user_jobs = [job for job in self.active_jobs.values() if job.user_id == user_id]

            if not user_jobs:
                return {"total_jobs": 0}

            status_counts = {}
            for job in user_jobs:
                status_counts[job.status] = status_counts.get(job.status, 0) + 1

            return {
                "total_jobs": len(user_jobs),
                "status_breakdown": status_counts,
                "active_jobs": [job.job_id for job in user_jobs if job.status == 'running'],
                "recent_jobs": [
                    {
                        "job_id": job.job_id,
                        "status": job.status,
                        "created_at": job.created_at.isoformat(),
                        "total_operations": job.total_operations
                    }
                    for job in sorted(user_jobs, key=lambda x: x.created_at, reverse=True)[:5]
                ]
            }

        except Exception as e:
            logger.error("Error getting batch summary", error=str(e), user_id=user_id)
            return {"total_jobs": 0, "error": str(e)}