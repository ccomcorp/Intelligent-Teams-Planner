import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
import structlog
from fastapi import HTTPException
import redis.asyncio as redis
import json
from urllib.parse import quote

from models.planner import (
    TaskCreateRequest, TaskUpdateRequest, TaskQueryRequest, TaskResponse,
    PlanResponse, BucketResponse, PlanCreateRequest, BucketCreateRequest
)

logger = structlog.get_logger(__name__)

class GraphAPIService:
    """Service for interacting with Microsoft Graph API"""

    def __init__(self, redis_client: redis.Redis):
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.redis_client = redis_client
        self.cache_ttl = 300  # 5 minutes default cache

    async def _make_request(
        self,
        access_token: str,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        etag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Graph API with error handling and retry logic"""

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        if etag and method in ["PATCH", "PUT", "DELETE"]:
            headers["If-Match"] = etag

        url = f"{self.base_url}{endpoint}"

        # Exponential backoff for throttling
        max_retries = 3
        base_delay = 1

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        json=data,
                        params=params,
                        headers=headers
                    )

                    # Handle throttling (HTTP 429)
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", base_delay * (2 ** attempt)))
                        if attempt < max_retries:
                            logger.warning(
                                "Request throttled, retrying",
                                attempt=attempt + 1,
                                retry_after=retry_after,
                                endpoint=endpoint
                            )
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            raise HTTPException(status_code=429, detail="API rate limit exceeded")

                    # Handle other HTTP errors
                    if response.status_code >= 400:
                        error_detail = response.text
                        try:
                            error_json = response.json()
                            error_detail = error_json.get("error", {}).get("message", error_detail)
                        except:
                            pass

                        logger.error(
                            "Graph API error",
                            status_code=response.status_code,
                            endpoint=endpoint,
                            error=error_detail
                        )

                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Graph API error: {error_detail}"
                        )

                    # Success
                    if response.status_code == 204:  # No content
                        return {"success": True}

                    return response.json()

            except httpx.TimeoutException:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning("Request timeout, retrying", attempt=attempt + 1, delay=delay)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise HTTPException(status_code=504, detail="Request timeout")

            except httpx.RequestError as e:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning("Request error, retrying", attempt=attempt + 1, error=str(e), delay=delay)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise HTTPException(status_code=502, detail=f"Request failed: {str(e)}")

    async def _cache_get(self, key: str) -> Optional[Dict]:
        """Get data from Redis cache"""
        try:
            cached_data = await self.redis_client.get(f"graph_cache:{key}")
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning("Cache get error", key=key, error=str(e))
        return None

    async def _cache_set(self, key: str, data: Dict, ttl: int = None) -> None:
        """Set data in Redis cache"""
        try:
            cache_ttl = ttl or self.cache_ttl
            await self.redis_client.setex(
                f"graph_cache:{key}",
                cache_ttl,
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.warning("Cache set error", key=key, error=str(e))

    async def _cache_delete(self, pattern: str) -> None:
        """Delete cache entries matching pattern"""
        try:
            keys = await self.redis_client.keys(f"graph_cache:{pattern}")
            if keys:
                await self.redis_client.delete(*keys)
        except Exception as e:
            logger.warning("Cache delete error", pattern=pattern, error=str(e))

    # Plan operations
    async def get_user_plans(self, access_token: str) -> List[PlanResponse]:
        """Get all plans for the current user"""
        cache_key = "user_plans"
        cached_plans = await self._cache_get(cache_key)

        if cached_plans:
            logger.debug("Returning cached user plans")
            return [PlanResponse(**plan) for plan in cached_plans]

        response = await self._make_request(
            access_token=access_token,
            method="GET",
            endpoint="/me/planner/plans"
        )

        plans = []
        for plan_data in response.get("value", []):
            plan = PlanResponse(
                id=plan_data["id"],
                title=plan_data["title"],
                owner=plan_data.get("owner", ""),
                created_date=datetime.fromisoformat(plan_data["createdDateTime"].replace("Z", "+00:00")),
                container_url=plan_data.get("container", {}).get("url")
            )
            plans.append(plan)

        # Cache the results
        await self._cache_set(cache_key, [plan.model_dump() for plan in plans])

        logger.info("Retrieved user plans", count=len(plans))
        return plans

    async def create_plan(self, access_token: str, request: PlanCreateRequest) -> PlanResponse:
        """Create a new plan"""
        # Note: Creating plans requires a Microsoft 365 Group
        # This is a simplified implementation
        data = {
            "title": request.title
        }

        if request.group_id:
            data["container"] = {
                "@odata.type": "microsoft.graph.plannerPlanContainer",
                "containerId": request.group_id,
                "type": "group"
            }

        response = await self._make_request(
            access_token=access_token,
            method="POST",
            endpoint="/planner/plans",
            data=data
        )

        # Clear plans cache
        await self._cache_delete("user_plans")

        plan = PlanResponse(
            id=response["id"],
            title=response["title"],
            owner=response.get("owner", ""),
            created_date=datetime.fromisoformat(response["createdDateTime"].replace("Z", "+00:00"))
        )

        logger.info("Created new plan", plan_id=plan.id, title=plan.title)
        return plan

    async def get_plan_by_name(self, access_token: str, plan_name: str) -> Optional[PlanResponse]:
        """Find plan by name"""
        plans = await self.get_user_plans(access_token)
        for plan in plans:
            if plan.title.lower() == plan_name.lower():
                return plan
        return None

    # Bucket operations
    async def get_plan_buckets(self, access_token: str, plan_id: str) -> List[BucketResponse]:
        """Get all buckets for a plan"""
        cache_key = f"plan_buckets:{plan_id}"
        cached_buckets = await self._cache_get(cache_key)

        if cached_buckets:
            return [BucketResponse(**bucket) for bucket in cached_buckets]

        response = await self._make_request(
            access_token=access_token,
            method="GET",
            endpoint=f"/planner/plans/{plan_id}/buckets"
        )

        buckets = []
        for bucket_data in response.get("value", []):
            bucket = BucketResponse(
                id=bucket_data["id"],
                name=bucket_data["name"],
                plan_id=bucket_data["planId"],
                order_hint=bucket_data.get("orderHint", "")
            )
            buckets.append(bucket)

        await self._cache_set(cache_key, [bucket.model_dump() for bucket in buckets])

        return buckets

    async def create_bucket(self, access_token: str, request: BucketCreateRequest) -> BucketResponse:
        """Create a new bucket in a plan"""
        # First find the plan
        plan = await self.get_plan_by_name(access_token, request.plan_name)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{request.plan_name}' not found")

        data = {
            "name": request.name,
            "planId": plan.id,
            "orderHint": " !"
        }

        response = await self._make_request(
            access_token=access_token,
            method="POST",
            endpoint="/planner/buckets",
            data=data
        )

        # Clear bucket cache
        await self._cache_delete(f"plan_buckets:{plan.id}")

        bucket = BucketResponse(
            id=response["id"],
            name=response["name"],
            plan_id=response["planId"],
            order_hint=response.get("orderHint", "")
        )

        logger.info("Created new bucket", bucket_id=bucket.id, name=bucket.name, plan_id=plan.id)
        return bucket

    async def get_bucket_by_name(self, access_token: str, plan_id: str, bucket_name: str) -> Optional[BucketResponse]:
        """Find bucket by name within a plan"""
        buckets = await self.get_plan_buckets(access_token, plan_id)
        for bucket in buckets:
            if bucket.name.lower() == bucket_name.lower():
                return bucket
        return None

    # Task operations
    async def create_task(self, access_token: str, request: TaskCreateRequest) -> TaskResponse:
        """Create a new task"""
        # Find the plan
        plan = await self.get_plan_by_name(access_token, request.plan_name)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan '{request.plan_name}' not found")

        # Find bucket if specified
        bucket_id = None
        if request.bucket_name:
            bucket = await self.get_bucket_by_name(access_token, plan.id, request.bucket_name)
            if bucket:
                bucket_id = bucket.id

        data = {
            "planId": plan.id,
            "title": request.title
        }

        if bucket_id:
            data["bucketId"] = bucket_id

        if request.due_date:
            data["dueDateTime"] = request.due_date.isoformat() + "Z"

        if request.priority:
            priority_mapping = {
                "low": 1,
                "normal": 3,
                "high": 5,
                "urgent": 9
            }
            data["priority"] = priority_mapping.get(request.priority.value, 3)

        response = await self._make_request(
            access_token=access_token,
            method="POST",
            endpoint="/planner/tasks",
            data=data
        )

        # Clear related caches
        await self._cache_delete(f"plan_tasks:{plan.id}")
        await self._cache_delete("user_tasks:*")

        task = self._parse_task_response(response, plan.title)

        # Handle assignee if specified
        if request.assignee_email and request.assignee_email != "me":
            try:
                await self._assign_task(access_token, task.id, request.assignee_email, task.etag)
            except Exception as e:
                logger.warning("Failed to assign task", task_id=task.id, assignee=request.assignee_email, error=str(e))

        # Add description if specified
        if request.description:
            try:
                await self._update_task_details(access_token, task.id, request.description)
            except Exception as e:
                logger.warning("Failed to add task description", task_id=task.id, error=str(e))

        logger.info("Created new task", task_id=task.id, title=task.title, plan=plan.title)
        return task

    async def get_user_tasks(self, access_token: str, query: TaskQueryRequest) -> List[TaskResponse]:
        """Get tasks for the current user with filtering"""
        cache_key = f"user_tasks:{hash(str(query.model_dump()))}"
        cached_tasks = await self._cache_get(cache_key)

        if cached_tasks:
            return [TaskResponse(**task) for task in cached_tasks]

        endpoint = "/me/planner/tasks"
        params = {}

        # Apply OData filters
        filters = []

        if query.completion_status:
            if query.completion_status == "completed":
                filters.append("percentComplete eq 100")
            elif query.completion_status == "in_progress":
                filters.append("percentComplete gt 0 and percentComplete lt 100")
            elif query.completion_status == "not_started":
                filters.append("percentComplete eq 0")

        if query.due_date_filter:
            now = datetime.utcnow()
            if query.due_date_filter == "overdue":
                filters.append(f"dueDateTime lt {now.isoformat()}Z")
            elif query.due_date_filter == "today":
                today_end = now.replace(hour=23, minute=59, second=59)
                filters.append(f"dueDateTime le {today_end.isoformat()}Z")
            elif query.due_date_filter == "this_week":
                week_end = now + timedelta(days=7-now.weekday())
                filters.append(f"dueDateTime le {week_end.isoformat()}Z")
            elif query.due_date_filter == "this_month":
                if now.month == 12:
                    month_end = now.replace(year=now.year+1, month=1, day=1) - timedelta(days=1)
                else:
                    month_end = now.replace(month=now.month+1, day=1) - timedelta(days=1)
                filters.append(f"dueDateTime le {month_end.isoformat()}Z")

        if filters:
            params["$filter"] = " and ".join(filters)

        params["$top"] = query.limit

        response = await self._make_request(
            access_token=access_token,
            method="GET",
            endpoint=endpoint,
            params=params
        )

        tasks = []
        plan_cache = {}  # Cache plan names

        for task_data in response.get("value", []):
            # Get plan name if not cached
            plan_id = task_data.get("planId")
            plan_name = plan_cache.get(plan_id)
            if not plan_name and plan_id:
                try:
                    plan_response = await self._make_request(
                        access_token=access_token,
                        method="GET",
                        endpoint=f"/planner/plans/{plan_id}"
                    )
                    plan_name = plan_response.get("title", "Unknown")
                    plan_cache[plan_id] = plan_name
                except:
                    plan_name = "Unknown"

            task = self._parse_task_response(task_data, plan_name)

            # Apply client-side filters
            if query.plan_name and plan_name.lower() != query.plan_name.lower():
                continue

            if query.title_contains and query.title_contains.lower() not in task.title.lower():
                continue

            tasks.append(task)

        # Cache results for 5 minutes
        await self._cache_set(cache_key, [task.model_dump() for task in tasks], ttl=300)

        logger.info("Retrieved user tasks", count=len(tasks), filters=query.model_dump())
        return tasks

    async def update_task(self, access_token: str, request: TaskUpdateRequest) -> TaskResponse:
        """Update an existing task"""
        # First get the current task to get ETag
        current_task_response = await self._make_request(
            access_token=access_token,
            method="GET",
            endpoint=f"/planner/tasks/{request.task_id}"
        )

        etag = current_task_response.get("@odata.etag")
        if not etag:
            raise HTTPException(status_code=400, detail="Unable to get task ETag for update")

        # Build update data
        data = {}

        if request.title is not None:
            data["title"] = request.title

        if request.due_date is not None:
            data["dueDateTime"] = request.due_date.isoformat() + "Z"

        if request.percent_complete is not None:
            data["percentComplete"] = request.percent_complete

        if request.priority is not None:
            priority_mapping = {
                "low": 1,
                "normal": 3,
                "high": 5,
                "urgent": 9
            }
            data["priority"] = priority_mapping.get(request.priority.value, 3)

        # Update the task
        response = await self._make_request(
            access_token=access_token,
            method="PATCH",
            endpoint=f"/planner/tasks/{request.task_id}",
            data=data,
            etag=etag
        )

        # Clear caches
        await self._cache_delete("user_tasks:*")
        await self._cache_delete("plan_tasks:*")

        # Get plan name
        plan_id = response.get("planId")
        plan_name = "Unknown"
        if plan_id:
            try:
                plan_response = await self._make_request(
                    access_token=access_token,
                    method="GET",
                    endpoint=f"/planner/plans/{plan_id}"
                )
                plan_name = plan_response.get("title", "Unknown")
            except:
                pass

        task = self._parse_task_response(response, plan_name)

        # Update description if specified
        if request.description is not None:
            try:
                await self._update_task_details(access_token, task.id, request.description)
            except Exception as e:
                logger.warning("Failed to update task description", task_id=task.id, error=str(e))

        # Update assignee if specified
        if request.assignee_email is not None:
            try:
                await self._assign_task(access_token, task.id, request.assignee_email, task.etag)
            except Exception as e:
                logger.warning("Failed to update task assignee", task_id=task.id, error=str(e))

        logger.info("Updated task", task_id=task.id, updates=data.keys())
        return task

    async def delete_task(self, access_token: str, task_id: str) -> bool:
        """Delete a task"""
        # Get current task for ETag
        current_task_response = await self._make_request(
            access_token=access_token,
            method="GET",
            endpoint=f"/planner/tasks/{task_id}"
        )

        etag = current_task_response.get("@odata.etag")
        if not etag:
            raise HTTPException(status_code=400, detail="Unable to get task ETag for deletion")

        await self._make_request(
            access_token=access_token,
            method="DELETE",
            endpoint=f"/planner/tasks/{task_id}",
            etag=etag
        )

        # Clear caches
        await self._cache_delete("user_tasks:*")
        await self._cache_delete("plan_tasks:*")

        logger.info("Deleted task", task_id=task_id)
        return True

    def _parse_task_response(self, task_data: Dict, plan_name: str = None) -> TaskResponse:
        """Parse Graph API task response into TaskResponse model"""
        assignees = []
        assignments = task_data.get("assignments", {})
        for user_id in assignments.keys():
            assignees.append(user_id)

        # Map priority back to enum
        priority_map = {1: "low", 3: "normal", 5: "high", 9: "urgent"}
        priority = priority_map.get(task_data.get("priority", 3), "normal")

        due_date = None
        if task_data.get("dueDateTime"):
            due_date = datetime.fromisoformat(task_data["dueDateTime"].replace("Z", "+00:00"))

        return TaskResponse(
            id=task_data["id"],
            title=task_data["title"],
            plan_id=task_data["planId"],
            plan_name=plan_name,
            bucket_id=task_data.get("bucketId"),
            created_date=datetime.fromisoformat(task_data["createdDateTime"].replace("Z", "+00:00")),
            due_date=due_date,
            percent_complete=task_data.get("percentComplete", 0),
            priority=priority,
            assignees=assignees,
            etag=task_data.get("@odata.etag")
        )

    async def _assign_task(self, access_token: str, task_id: str, assignee_email: str, etag: str):
        """Assign a task to a user"""
        # First get user ID from email
        if assignee_email == "me":
            user_response = await self._make_request(
                access_token=access_token,
                method="GET",
                endpoint="/me"
            )
            user_id = user_response["id"]
        else:
            user_response = await self._make_request(
                access_token=access_token,
                method="GET",
                endpoint=f"/users/{quote(assignee_email)}"
            )
            user_id = user_response["id"]

        # Update task assignments
        data = {
            "assignments": {
                user_id: {
                    "@odata.type": "microsoft.graph.plannerAssignment",
                    "orderHint": " !"
                }
            }
        }

        await self._make_request(
            access_token=access_token,
            method="PATCH",
            endpoint=f"/planner/tasks/{task_id}",
            data=data,
            etag=etag
        )

    async def _update_task_details(self, access_token: str, task_id: str, description: str):
        """Update task details (description)"""
        # Get current task details for ETag
        try:
            details_response = await self._make_request(
                access_token=access_token,
                method="GET",
                endpoint=f"/planner/tasks/{task_id}/details"
            )
            etag = details_response.get("@odata.etag")
        except HTTPException as e:
            if e.status_code == 404:
                # Details don't exist yet, create them
                etag = None
            else:
                raise

        data = {"description": description}

        if etag:
            # Update existing details
            await self._make_request(
                access_token=access_token,
                method="PATCH",
                endpoint=f"/planner/tasks/{task_id}/details",
                data=data,
                etag=etag
            )
        else:
            # Create new details
            await self._make_request(
                access_token=access_token,
                method="PATCH",
                endpoint=f"/planner/tasks/{task_id}/details",
                data=data
            )