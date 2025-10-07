"""
Microsoft Graph API client for Planner operations
"""

import os
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

import httpx
import structlog

from .auth import AuthService
from .cache import CacheService

logger = structlog.get_logger(__name__)

class GraphAPIError(Exception):
    """Graph API operation error"""
    pass

class RateLimitExceeded(GraphAPIError):
    """Rate limit exceeded"""
    pass

class GraphAPIClient:
    """Microsoft Graph API client with caching and rate limiting"""

    def __init__(self, auth_service: AuthService, cache_service: CacheService):
        self.auth_service = auth_service
        self.cache_service = cache_service
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
        self.rate_limit_window = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    async def test_connection(self, user_id: str = "default") -> bool:
        """Test Graph API connectivity"""
        try:
            response = await self._make_request("GET", "/me", user_id=user_id)
            return response is not None
        except Exception:
            return False

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        user_id: str,
        data: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
        use_cache: bool = True,
        cache_ttl: int = 300
    ) -> Optional[Dict[str, Any]]:
        """Make authenticated request to Graph API"""
        try:
            # Check rate limiting
            await self._check_rate_limit(user_id)

            # Get access token
            access_token = await self.auth_service.get_access_token(user_id)
            if not access_token:
                raise GraphAPIError("No valid access token available")

            # Check cache for GET requests
            if method == "GET" and use_cache:
                cache_key = f"graph_api:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
                cached_result = await self.cache_service.get(cache_key)
                if cached_result:
                    logger.debug("Returning cached result", endpoint=endpoint)
                    return cached_result

            # Prepare request
            url = f"{self.base_url}{endpoint}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            # Add ETag support for optimistic concurrency
            if method in ["PATCH", "PUT", "DELETE"] and data and "etag" in data:
                headers["If-Match"] = data.pop("etag")

            # Make request with retry logic
            result = await self._make_request_with_retry(
                method, url, headers, data, params
            )

            # Cache successful GET requests
            if method == "GET" and use_cache and result:
                cache_key = f"graph_api:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
                await self.cache_service.set(cache_key, result, ttl=cache_ttl)

            # Update rate limiting counter
            await self._update_rate_limit_counter(user_id)

            return result

        except GraphAPIError:
            raise
        except Exception as e:
            logger.error("Graph API request failed", endpoint=endpoint, error=str(e))
            raise GraphAPIError(f"Request failed: {str(e)}")

    async def _make_request_with_retry(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Dict[str, Any] = None,
        params: Dict[str, Any] = None,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """Make request with exponential backoff retry"""
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=data if data else None,
                        params=params
                    )

                    # Handle rate limiting
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", "60"))
                        logger.warning("Rate limited by Graph API", retry_after=retry_after)

                        if attempt < max_retries:
                            await asyncio.sleep(min(retry_after, 60))  # Cap at 60 seconds
                            continue
                        else:
                            raise RateLimitExceeded("Rate limit exceeded, max retries reached")

                    # Handle authentication errors
                    if response.status_code == 401:
                        raise GraphAPIError("Authentication failed - token may be expired")

                    # Handle not found
                    if response.status_code == 404:
                        logger.info("Resource not found", url=url)
                        return None

                    # Handle client errors
                    if 400 <= response.status_code < 500:
                        error_detail = response.text if response.text else "Unknown client error"
                        raise GraphAPIError(f"Client error {response.status_code}: {error_detail}")

                    # Handle server errors with retry
                    if response.status_code >= 500:
                        if attempt < max_retries:
                            delay = (2 ** attempt) + (attempt * 0.1)  # Exponential backoff
                            logger.warning("Server error, retrying", status_code=response.status_code, delay=delay)
                            await asyncio.sleep(delay)
                            continue
                        else:
                            raise GraphAPIError(f"Server error {response.status_code}: {response.text}")

                    # Success
                    if response.status_code == 204:  # No content
                        return {}

                    return response.json() if response.text else {}

            except httpx.RequestError as e:
                if attempt < max_retries:
                    delay = (2 ** attempt) + (attempt * 0.1)
                    logger.warning("Request error, retrying", error=str(e), delay=delay)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise GraphAPIError(f"Request error: {str(e)}")

        raise GraphAPIError("Max retries exceeded")

    async def _check_rate_limit(self, user_id: str):
        """Check if user has exceeded rate limit"""
        rate_limit_key = f"rate_limit:{user_id}"
        current_count = await self.cache_service.get(rate_limit_key) or 0

        if current_count >= self.rate_limit_requests:
            raise RateLimitExceeded(f"Rate limit exceeded: {current_count}/{self.rate_limit_requests} requests per {self.rate_limit_window}s")

    async def _update_rate_limit_counter(self, user_id: str):
        """Update rate limit counter"""
        rate_limit_key = f"rate_limit:{user_id}"
        current_count = await self.cache_service.get(rate_limit_key) or 0
        await self.cache_service.set(
            rate_limit_key,
            current_count + 1,
            ttl=self.rate_limit_window
        )

    # Planner-specific operations

    async def get_user_groups(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's groups"""
        result = await self._make_request("GET", "/me/memberOf", user_id)
        return result.get("value", []) if result else []

    async def get_group_plans(self, group_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get plans for a group"""
        result = await self._make_request("GET", f"/groups/{group_id}/planner/plans", user_id)
        return result.get("value", []) if result else []

    async def get_plan_details(self, plan_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get plan details"""
        return await self._make_request("GET", f"/planner/plans/{plan_id}", user_id)

    async def create_plan(self, plan_data: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
        """Create a new plan"""
        required_fields = ["title", "owner"]
        if not all(field in plan_data for field in required_fields):
            raise GraphAPIError(f"Missing required fields: {required_fields}")

        return await self._make_request(
            "POST",
            "/planner/plans",
            user_id,
            data=plan_data,
            use_cache=False
        )

    async def update_plan(self, plan_id: str, plan_data: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
        """Update a plan"""
        return await self._make_request(
            "PATCH",
            f"/planner/plans/{plan_id}",
            user_id,
            data=plan_data,
            use_cache=False
        )

    async def delete_plan(self, plan_id: str, etag: str, user_id: str) -> bool:
        """Delete a plan"""
        result = await self._make_request(
            "DELETE",
            f"/planner/plans/{plan_id}",
            user_id,
            data={"etag": etag},
            use_cache=False
        )
        return result is not None

    async def get_plan_tasks(self, plan_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get tasks for a plan"""
        result = await self._make_request("GET", f"/planner/plans/{plan_id}/tasks", user_id)
        return result.get("value", []) if result else []

    async def get_task_details(self, task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get task details"""
        return await self._make_request("GET", f"/planner/tasks/{task_id}", user_id)

    async def create_task(self, task_data: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
        """Create a new task"""
        required_fields = ["title", "planId"]
        if not all(field in task_data for field in required_fields):
            raise GraphAPIError(f"Missing required fields: {required_fields}")

        return await self._make_request(
            "POST",
            "/planner/tasks",
            user_id,
            data=task_data,
            use_cache=False
        )

    async def update_task(self, task_id: str, task_data: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
        """Update a task"""
        return await self._make_request(
            "PATCH",
            f"/planner/tasks/{task_id}",
            user_id,
            data=task_data,
            use_cache=False
        )

    async def delete_task(self, task_id: str, etag: str, user_id: str) -> bool:
        """Delete a task"""
        result = await self._make_request(
            "DELETE",
            f"/planner/tasks/{task_id}",
            user_id,
            data={"etag": etag},
            use_cache=False
        )
        return result is not None

    async def get_plan_buckets(self, plan_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get buckets for a plan"""
        result = await self._make_request("GET", f"/planner/plans/{plan_id}/buckets", user_id)
        return result.get("value", []) if result else []

    async def create_bucket(self, bucket_data: Dict[str, Any], user_id: str) -> Optional[Dict[str, Any]]:
        """Create a new bucket"""
        required_fields = ["name", "planId"]
        if not all(field in bucket_data for field in required_fields):
            raise GraphAPIError(f"Missing required fields: {required_fields}")

        return await self._make_request(
            "POST",
            "/planner/buckets",
            user_id,
            data=bucket_data,
            use_cache=False
        )

    # Batch operations for efficiency
    async def batch_request(self, requests: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """Execute multiple requests in a batch (up to 20)"""
        if len(requests) > 20:
            raise GraphAPIError("Batch requests limited to 20 operations")

        if not requests:
            return []

        # Prepare batch request
        batch_data = {
            "requests": [
                {
                    "id": str(i),
                    "method": req.get("method", "GET"),
                    "url": req["url"],
                    "body": req.get("body"),
                    "headers": req.get("headers", {})
                }
                for i, req in enumerate(requests)
            ]
        }

        result = await self._make_request(
            "POST",
            "/$batch",
            user_id,
            data=batch_data,
            use_cache=False
        )

        if not result or "responses" not in result:
            raise GraphAPIError("Invalid batch response")

        return result["responses"]

    async def get_delta_changes(self, resource_url: str, delta_token: str, user_id: str) -> Dict[str, Any]:
        """Get delta changes for a resource"""
        params = {}
        if delta_token:
            params["$deltatoken"] = delta_token

        url = f"{resource_url}/delta" if not resource_url.endswith("/delta") else resource_url

        return await self._make_request(
            "GET",
            url,
            user_id,
            params=params,
            use_cache=False
        )

    async def search_users(self, query: str, user_id: str) -> List[Dict[str, Any]]:
        """Search for users"""
        params = {
            "$search": f'"displayName:{query}" OR "mail:{query}"',
            "$select": "id,displayName,mail,userPrincipalName"
        }

        result = await self._make_request(
            "GET",
            "/users",
            user_id,
            params=params,
            cache_ttl=60  # Short cache for search
        )

        return result.get("value", []) if result else []

    # Task Comment Operations
    async def get_task_comments(self, task_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get comments for a task"""
        result = await self._make_request("GET", f"/planner/tasks/{task_id}/details", user_id)
        if result and "checklist" in result:
            # Planner stores comments in task details/checklist format
            checklist = result.get("checklist", {})
            comments = []
            for item_id, item in checklist.items():
                if item.get("title"):
                    comments.append({
                        "id": item_id,
                        "text": item["title"],
                        "createdDateTime": item.get("lastModifiedDateTime"),
                        "isChecked": item.get("isChecked", False)
                    })
            return comments
        return []

    async def add_task_comment(self, task_id: str, comment_text: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Add a comment to a task (via task details checklist)"""
        # First get current task details to get ETag
        current_details = await self._make_request("GET", f"/planner/tasks/{task_id}/details", user_id)
        if not current_details:
            raise GraphAPIError("Could not get task details for comment addition")

        # Generate unique ID for the comment
        import uuid
        comment_id = str(uuid.uuid4())

        # Get existing checklist or create new one
        checklist = current_details.get("checklist", {})

        # Add new comment as checklist item
        checklist[comment_id] = {
            "@odata.type": "#microsoft.graph.plannerChecklistItem",
            "title": comment_text,
            "isChecked": False,
            "orderHint": " !"
        }

        # Update task details with new comment
        update_data = {
            "checklist": checklist,
            "etag": current_details.get("@odata.etag")
        }

        result = await self._make_request(
            "PATCH",
            f"/planner/tasks/{task_id}/details",
            user_id,
            data=update_data,
            use_cache=False
        )

        if result:
            return {
                "id": comment_id,
                "text": comment_text,
                "createdDateTime": datetime.utcnow().isoformat() + "Z"
            }
        return None
