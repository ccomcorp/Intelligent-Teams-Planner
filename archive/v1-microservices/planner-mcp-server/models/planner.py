from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

class TaskPriority(str, Enum):
    """Task priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class TaskCreateRequest(BaseModel):
    """Request model for creating a new task"""
    title: str = Field(..., description="Task title")
    plan_name: str = Field(..., description="Name of the plan to create task in")
    bucket_name: Optional[str] = Field(None, description="Name of the bucket within the plan")
    assignee_email: Optional[str] = Field(None, description="Email of user to assign task to")
    due_date: Optional[datetime] = Field(None, description="Due date for the task")
    priority: Optional[TaskPriority] = Field(TaskPriority.NORMAL, description="Task priority level")
    description: Optional[str] = Field(None, description="Task description")

class TaskUpdateRequest(BaseModel):
    """Request model for updating an existing task"""
    task_id: str = Field(..., description="ID of the task to update")
    title: Optional[str] = Field(None, description="New task title")
    due_date: Optional[datetime] = Field(None, description="New due date")
    percent_complete: Optional[int] = Field(None, ge=0, le=100, description="Completion percentage")
    priority: Optional[TaskPriority] = Field(None, description="New priority level")
    description: Optional[str] = Field(None, description="New task description")
    assignee_email: Optional[str] = Field(None, description="Email of user to assign/reassign task to")

class TaskQueryRequest(BaseModel):
    """Request model for querying tasks"""
    plan_name: Optional[str] = Field(None, description="Filter by plan name")
    assignee_email: Optional[str] = Field(None, description="Filter by assignee email ('me' for current user)")
    completion_status: Optional[str] = Field(None, description="Filter by completion status: 'completed', 'in_progress', 'not_started'")
    due_date_filter: Optional[str] = Field(None, description="Filter by due date: 'overdue', 'today', 'this_week', 'this_month'")
    title_contains: Optional[str] = Field(None, description="Filter by title containing text")
    limit: Optional[int] = Field(10, ge=1, le=100, description="Maximum number of tasks to return")

class PlanCreateRequest(BaseModel):
    """Request model for creating a new plan"""
    title: str = Field(..., description="Plan title")
    group_id: Optional[str] = Field(None, description="Microsoft 365 Group ID (if not provided, user must be in a group)")

class BucketCreateRequest(BaseModel):
    """Request model for creating a new bucket"""
    name: str = Field(..., description="Bucket name")
    plan_name: str = Field(..., description="Name of the plan to create bucket in")

class DocumentGenerationRequest(BaseModel):
    """Request model for document generation"""
    plan_name: str = Field(..., description="Name of the plan to generate report for")
    document_type: str = Field(..., description="Type of document: 'pdf', 'word', 'powerpoint'")
    include_completed: bool = Field(True, description="Include completed tasks in report")
    include_in_progress: bool = Field(True, description="Include in-progress tasks in report")
    include_not_started: bool = Field(True, description="Include not started tasks in report")

class TaskResponse(BaseModel):
    """Response model for task data"""
    id: str
    title: str
    plan_id: str
    plan_name: Optional[str] = None
    bucket_id: Optional[str] = None
    bucket_name: Optional[str] = None
    created_date: datetime
    due_date: Optional[datetime] = None
    percent_complete: int = 0
    priority: TaskPriority = TaskPriority.NORMAL
    assignees: List[str] = []
    description: Optional[str] = None
    etag: Optional[str] = None

class PlanResponse(BaseModel):
    """Response model for plan data"""
    id: str
    title: str
    owner: str
    created_date: datetime
    container_url: Optional[str] = None
    bucket_count: int = 0
    task_count: int = 0

class BucketResponse(BaseModel):
    """Response model for bucket data"""
    id: str
    name: str
    plan_id: str
    order_hint: str
    task_count: int = 0

class APIResponse(BaseModel):
    """Standard API response wrapper"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class MCPToolDefinition(BaseModel):
    """MCP tool definition for function calling"""
    name: str
    description: str
    parameters: Dict[str, Any]

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime
    services: Dict[str, str]
    version: str = "1.0.0"