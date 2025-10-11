"""
Simple cursor-based pagination helpers
"""

import base64
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class PaginationCursor:
    """Simple cursor for pagination"""

    def __init__(self, value: Any, field: str = "id"):
        self.value = value
        self.field = field

    def encode(self) -> str:
        """Encode cursor to base64 string"""
        try:
            cursor_data = {
                "value": self.value,
                "field": self.field,
                "timestamp": datetime.utcnow().isoformat()
            }
            json_str = json.dumps(cursor_data, default=str)
            return base64.b64encode(json_str.encode()).decode()
        except Exception as e:
            logger.error("Error encoding cursor", error=str(e))
            return ""

    @classmethod
    def decode(cls, cursor_string: str) -> Optional['PaginationCursor']:
        """Decode cursor from base64 string"""
        try:
            json_str = base64.b64decode(cursor_string.encode()).decode()
            cursor_data = json.loads(json_str)
            return cls(cursor_data["value"], cursor_data["field"])
        except Exception as e:
            logger.error("Error decoding cursor", error=str(e))
            return None

def paginate_list(
    items: List[Any],
    cursor: Optional[str] = None,
    limit: int = 20,
    cursor_field: str = "id"
) -> Dict[str, Any]:
    """Paginate a list with cursor-based pagination"""
    try:
        # Decode cursor if provided
        start_cursor = None
        if cursor:
            start_cursor = PaginationCursor.decode(cursor)

        # Find starting position
        start_index = 0
        if start_cursor:
            for i, item in enumerate(items):
                item_value = item.get(cursor_field) if isinstance(item, dict) else getattr(item, cursor_field, None)
                if item_value == start_cursor.value:
                    start_index = i + 1  # Start after the cursor item
                    break

        # Get page items
        end_index = start_index + limit
        page_items = items[start_index:end_index]

        # Create cursors
        next_cursor = None
        prev_cursor = None

        if page_items:
            # Next cursor (last item of current page)
            last_item = page_items[-1]
            last_value = last_item.get(cursor_field) if isinstance(last_item, dict) else getattr(last_item, cursor_field, None)
            if end_index < len(items):  # Has more items
                next_cursor = PaginationCursor(last_value, cursor_field).encode()

            # Previous cursor (first item of current page)
            if start_index > 0:
                first_item = page_items[0]
                first_value = first_item.get(cursor_field) if isinstance(first_item, dict) else getattr(first_item, cursor_field, None)

                # Find previous item
                for i in range(start_index - 1, -1, -1):
                    if i < len(items):
                        prev_item = items[i]
                        prev_value = prev_item.get(cursor_field) if isinstance(prev_item, dict) else getattr(prev_item, cursor_field, None)
                        prev_cursor = PaginationCursor(prev_value, cursor_field).encode()
                        break

        return {
            "items": page_items,
            "pagination": {
                "next_cursor": next_cursor,
                "prev_cursor": prev_cursor,
                "has_next": next_cursor is not None,
                "has_previous": prev_cursor is not None,
                "page_size": len(page_items),
                "total_count": len(items)
            }
        }

    except Exception as e:
        logger.error("Error paginating list", error=str(e))
        return {
            "items": items[:limit],
            "pagination": {
                "next_cursor": None,
                "prev_cursor": None,
                "has_next": False,
                "has_previous": False,
                "page_size": min(len(items), limit),
                "total_count": len(items)
            }
        }

def create_page_info(
    items: List[Any],
    cursor: Optional[str],
    limit: int,
    total_count: Optional[int] = None
) -> Dict[str, Any]:
    """Create pagination info for API responses"""
    has_next = len(items) > limit
    if has_next:
        items = items[:limit]  # Remove extra item used for has_next check

    next_cursor = None
    if has_next and items:
        last_item = items[-1]
        # Assume items have an 'id' field for cursor
        last_id = last_item.get('id') if isinstance(last_item, dict) else getattr(last_item, 'id', None)
        if last_id:
            next_cursor = PaginationCursor(last_id).encode()

    return {
        "items": items,
        "page_info": {
            "has_next_page": has_next,
            "next_cursor": next_cursor,
            "page_size": len(items),
            "total_count": total_count
        }
    }

def get_offset_from_cursor(cursor: Optional[str], items: List[Any], cursor_field: str = "id") -> int:
    """Get offset position from cursor for database queries"""
    if not cursor:
        return 0

    start_cursor = PaginationCursor.decode(cursor)
    if not start_cursor:
        return 0

    # Find position in items
    for i, item in enumerate(items):
        item_value = item.get(cursor_field) if isinstance(item, dict) else getattr(item, cursor_field, None)
        if item_value == start_cursor.value:
            return i + 1

    return 0

def validate_pagination_params(cursor: Optional[str], limit: Optional[int]) -> Tuple[Optional[str], int]:
    """Validate and normalize pagination parameters"""
    # Validate limit
    if limit is None:
        limit = 20
    else:
        limit = max(1, min(limit, 100))  # Between 1 and 100

    # Validate cursor
    if cursor:
        decoded = PaginationCursor.decode(cursor)
        if decoded is None:
            cursor = None

    return cursor, limit