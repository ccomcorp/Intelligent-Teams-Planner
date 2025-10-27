"""
Universal Pattern Matcher for Microsoft Planner Operations
Comprehensive natural language to tool mapping for ALL 24 Planner tools
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)


class UniversalPlannerPatterns:
    """
    Comprehensive pattern matching for ALL Microsoft Planner operations
    Supports: Plans, Tasks, Comments, Checklists, Buckets, Documents, Assignments, Dates
    """

    def __init__(self):
        # Email pattern for user assignments
        self.email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        self.user_pattern = rf"({self.email_pattern}|\w+(?:\s+\w+)?)"

        # Date patterns
        self.date_patterns = [
            r"tomorrow|today|yesterday",
            r"(?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)",
            r"\d{1,2}\/\d{1,2}\/\d{4}",
            r"\d{4}-\d{2}-\d{2}",
            r"(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}",
        ]

        # Priority patterns
        self.priority_patterns = {
            "urgent": "High",
            "high": "High",
            "critical": "High",
            "important": "High",
            "medium": "Medium",
            "normal": "Medium",
            "low": "Low",
            "minor": "Low"
        }

        # Progress patterns
        self.progress_patterns = r"(\d{1,3})%|(\d{1,3})\s*percent"

        # Initialize all patterns
        self.patterns = self._initialize_all_patterns()

    def _initialize_all_patterns(self) -> List[Dict[str, Any]]:
        """Initialize comprehensive pattern library for all 24 tools"""
        patterns = []

        # ============================================================================
        # PLAN MANAGEMENT PATTERNS (3 tools)
        # ============================================================================

        # LIST PLANS
        patterns.extend([
            {
                "pattern": r"(?:show|list|get|display)\s+(?:all\s+)?(?:my\s+)?plans?",
                "tool": "list_plans",
                "confidence": 0.95,
                "extract_func": self._extract_list_plans_args
            },
            {
                "pattern": r"what\s+plans?\s+(?:do\s+i\s+have|are\s+available)",
                "tool": "list_plans",
                "confidence": 0.90,
                "extract_func": self._extract_list_plans_args
            }
        ])

        # CREATE PLAN
        patterns.extend([
            {
                "pattern": rf"(?:create|make|start|new)\s+(?:a\s+)?plan\s+(?:called|named|titled)?\s*[\"']?([^\"']+)[\"']?",
                "tool": "create_plan",
                "confidence": 0.95,
                "extract_func": self._extract_create_plan_args
            },
            {
                "pattern": rf"create\s+plan:\s*([^,\n]+)",
                "tool": "create_plan",
                "confidence": 0.95,
                "extract_func": self._extract_create_plan_args
            }
        ])

        # SEARCH PLANS
        patterns.extend([
            {
                "pattern": rf"(?:search|find|locate)\s+(?:for\s+)?plans?\s+(?:about|containing|with|regarding)\s+(.+)",
                "tool": "search_plans",
                "confidence": 0.90,
                "extract_func": self._extract_search_plans_args
            }
        ])

        # ============================================================================
        # TASK MANAGEMENT PATTERNS (9 tools)
        # ============================================================================

        # LIST TASKS
        patterns.extend([
            {
                "pattern": rf"(?:show|list|get|display)\s+(?:all\s+)?tasks?\s+(?:in|from)\s+(?:plan\s+)?(.+)",
                "tool": "list_tasks",
                "confidence": 0.95,
                "extract_func": self._extract_list_tasks_args
            },
            {
                "pattern": r"(?:show|list|get|display)\s+(?:all\s+)?(?:my\s+)?tasks?",
                "tool": "list_tasks",
                "confidence": 0.85,
                "extract_func": self._extract_list_tasks_args
            }
        ])

        # CREATE TASK (including assignment)
        patterns.extend([
            {
                "pattern": rf"(?:assign|create|make|add|new)\s+task:?\s*(.+?)\s+(?:to|for|assign(?:ed)?\s+to)\s+{self.user_pattern}",
                "tool": "create_task",
                "confidence": 0.95,
                "extract_func": self._extract_create_and_assign_task_args
            },
            {
                "pattern": rf"(?:create|make|add|new)\s+(?:a\s+)?task\s+(?:called|named|titled)?\s*[\"']?([^\"']+)[\"']?",
                "tool": "create_task",
                "confidence": 0.90,
                "extract_func": self._extract_create_task_args
            },
            {
                "pattern": rf"create\s+task:\s*([^,\n]+)",
                "tool": "create_task",
                "confidence": 0.95,
                "extract_func": self._extract_create_task_args
            }
        ])

        # UPDATE TASK (comprehensive updates)
        patterns.extend([
            {
                "pattern": rf"(?:update|change|modify|set)\s+task\s+(.+?)\s+(?:to|as)\s+({self.progress_patterns})",
                "tool": "update_task",
                "confidence": 0.95,
                "extract_func": self._extract_update_task_progress_args
            },
            {
                "pattern": rf"(?:assign|give|delegate)\s+task\s+(.+?)\s+(?:to|for)\s+{self.user_pattern}",
                "tool": "update_task",
                "confidence": 0.95,
                "extract_func": self._extract_assign_existing_task_args
            },
            {
                "pattern": rf"(?:set|change|update)\s+(?:task\s+)?(.+?)\s+(?:priority|importance)\s+(?:to\s+)?(\w+)",
                "tool": "update_task",
                "confidence": 0.95,
                "extract_func": self._extract_update_task_priority_args
            },
            {
                "pattern": rf"(?:set|change|update)\s+(?:task\s+)?(.+?)\s+due\s+(?:date\s+)?(?:to\s+)?(.+)",
                "tool": "update_task",
                "confidence": 0.95,
                "extract_func": self._extract_update_task_due_date_args
            },
            {
                "pattern": rf"(?:set|change|update)\s+(?:task\s+)?(.+?)\s+start\s+(?:date\s+)?(?:to\s+)?(.+)",
                "tool": "update_task",
                "confidence": 0.95,
                "extract_func": self._extract_update_task_start_date_args
            },
            {
                "pattern": rf"(?:mark|set)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:complete|completed|done|finished)",
                "tool": "update_task",
                "confidence": 0.95,
                "extract_func": self._extract_complete_task_args
            }
        ])

        # DELETE TASK
        patterns.extend([
            {
                "pattern": rf"(?:delete|remove|drop|cancel)\s+(?:task\s+)?(.+)",
                "tool": "delete_task",
                "confidence": 0.95,
                "extract_func": self._extract_delete_task_args
            }
        ])

        # GET TASK DETAILS
        patterns.extend([
            {
                "pattern": rf"(?:show|get|tell\s+me\s+about|describe|details?)\s+(?:for\s+)?(?:task\s+)?(.+)",
                "tool": "get_task_details",
                "confidence": 0.85,
                "extract_func": self._extract_task_details_args
            },
            {
                "pattern": rf"what(?:'s|\s+is)\s+(?:the\s+)?status\s+(?:of\s+)?(?:task\s+)?(.+)",
                "tool": "get_task_details",
                "confidence": 0.90,
                "extract_func": self._extract_task_details_args
            }
        ])

        # SEARCH TASKS
        patterns.extend([
            {
                "pattern": rf"(?:search|find|locate)\s+(?:for\s+)?tasks?\s+(?:about|containing|with|regarding|assigned\s+to)\s+(.+)",
                "tool": "search_tasks",
                "confidence": 0.90,
                "extract_func": self._extract_search_tasks_args
            }
        ])

        # GET MY TASKS
        patterns.extend([
            {
                "pattern": r"(?:show|get|list)\s+(?:all\s+)?(?:my|mine)\s+tasks?",
                "tool": "get_my_tasks",
                "confidence": 0.95,
                "extract_func": self._extract_my_tasks_args
            },
            {
                "pattern": r"what\s+(?:am\s+i\s+working\s+on|tasks?\s+do\s+i\s+have|are\s+my\s+assignments)",
                "tool": "get_my_tasks",
                "confidence": 0.90,
                "extract_func": self._extract_my_tasks_args
            }
        ])

        # GET TASK BY POSITION
        patterns.extend([
            {
                "pattern": rf"(?:show|get)\s+task\s+(?:number\s+)?(\d+)",
                "tool": "get_task_by_position",
                "confidence": 0.95,
                "extract_func": self._extract_task_by_position_args
            }
        ])

        # GET NEXT TASK
        patterns.extend([
            {
                "pattern": r"(?:what(?:'s|\s+is)\s+)?(?:my\s+)?(?:next|upcoming)\s+task",
                "tool": "get_next_task",
                "confidence": 0.95,
                "extract_func": self._extract_next_task_args
            }
        ])

        # ============================================================================
        # TASK ENHANCEMENT PATTERNS (3 tools)
        # ============================================================================

        # ADD TASK COMMENT
        patterns.extend([
            {
                "pattern": rf"(?:add|post|leave)\s+(?:a\s+)?comment\s+(?:to|on|for)\s+(?:task\s+)?(.+?):\s*(.+)",
                "tool": "add_task_comment",
                "confidence": 0.95,
                "extract_func": self._extract_add_comment_args
            },
            {
                "pattern": rf"comment\s+(?:on\s+)?(?:task\s+)?(.+?):\s*(.+)",
                "tool": "add_task_comment",
                "confidence": 0.95,
                "extract_func": self._extract_add_comment_args
            }
        ])

        # ADD TASK CHECKLIST
        patterns.extend([
            {
                "pattern": rf"(?:add|create)\s+(?:a\s+)?checklist\s+(?:to|for)\s+(?:task\s+)?(.+)",
                "tool": "add_task_checklist",
                "confidence": 0.95,
                "extract_func": self._extract_add_checklist_args
            }
        ])

        # UPDATE TASK CHECKLIST
        patterns.extend([
            {
                "pattern": rf"(?:mark|check|complete)\s+(?:checklist\s+)?item\s+(\d+)\s+(?:in\s+)?(?:task\s+)?(.+)",
                "tool": "update_task_checklist",
                "confidence": 0.95,
                "extract_func": self._extract_update_checklist_args
            }
        ])

        # ============================================================================
        # BUCKET MANAGEMENT PATTERNS (4 tools)
        # ============================================================================

        # LIST BUCKETS
        patterns.extend([
            {
                "pattern": rf"(?:show|list|get)\s+(?:all\s+)?(?:buckets|categories)\s+(?:in|from)\s+(?:plan\s+)?(.+)",
                "tool": "list_buckets",
                "confidence": 0.95,
                "extract_func": self._extract_list_buckets_args
            }
        ])

        # CREATE BUCKET
        patterns.extend([
            {
                "pattern": rf"(?:create|make|add)\s+(?:a\s+)?(?:bucket|category)\s+(?:called|named)?\s*(.+)",
                "tool": "create_bucket",
                "confidence": 0.95,
                "extract_func": self._extract_create_bucket_args
            }
        ])

        # UPDATE BUCKET
        patterns.extend([
            {
                "pattern": rf"(?:rename|update|change)\s+(?:bucket|category)\s+(.+?)\s+(?:to|as)\s+(.+)",
                "tool": "update_bucket",
                "confidence": 0.95,
                "extract_func": self._extract_update_bucket_args
            }
        ])

        # DELETE BUCKET
        patterns.extend([
            {
                "pattern": rf"(?:delete|remove)\s+(?:bucket|category)\s+(.+)",
                "tool": "delete_bucket",
                "confidence": 0.95,
                "extract_func": self._extract_delete_bucket_args
            }
        ])

        # ============================================================================
        # DOCUMENT & KNOWLEDGE PATTERNS (4 tools)
        # ============================================================================

        # CREATE TASKS FROM DOCUMENT
        patterns.extend([
            {
                "pattern": rf"(?:create|extract|generate)\s+tasks?\s+from\s+(?:document|file)\s+(.+)",
                "tool": "create_tasks_from_document",
                "confidence": 0.95,
                "extract_func": self._extract_document_tasks_args
            }
        ])

        # SEARCH DOCUMENTS
        patterns.extend([
            {
                "pattern": rf"(?:search|find)\s+(?:for\s+)?documents?\s+(?:about|containing)\s+(.+)",
                "tool": "search_documents",
                "confidence": 0.90,
                "extract_func": self._extract_search_documents_args
            }
        ])

        # ANALYZE PROJECT RELATIONSHIPS
        patterns.extend([
            {
                "pattern": rf"(?:analyze|show)\s+(?:project\s+)?(?:relationships|connections)\s+(?:for|in)\s+(.+)",
                "tool": "analyze_project_relationships",
                "confidence": 0.90,
                "extract_func": self._extract_analyze_relationships_args
            }
        ])

        return patterns

    def match_pattern(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Match user message against all patterns and return best match
        """
        best_match = None
        highest_confidence = 0.0

        normalized_message = message.lower().strip()

        for pattern_config in self.patterns:
            pattern = pattern_config["pattern"]
            confidence = pattern_config["confidence"]

            match = re.search(pattern, normalized_message, re.IGNORECASE)
            if match:
                # Apply confidence boost for exact matches
                final_confidence = confidence
                if len(match.groups()) > 0 and match.group(1):
                    final_confidence = min(1.0, confidence + 0.05)

                if final_confidence > highest_confidence:
                    highest_confidence = final_confidence
                    best_match = {
                        "tool": pattern_config["tool"],
                        "confidence": final_confidence,
                        "match": match,
                        "extract_func": pattern_config["extract_func"],
                        "source": "universal_pattern"
                    }

        return best_match

    # ============================================================================
    # ARGUMENT EXTRACTION FUNCTIONS
    # ============================================================================

    def _extract_create_and_assign_task_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for create+assign task operations"""
        task_title = match.group(1).strip()
        assignee = match.group(2).strip()

        args = {
            "title": task_title,
            "assigned_to": [assignee],
            "description": f"Task: {task_title}",
        }

        # Smart categorization and priority
        if any(kw in task_title.lower() for kw in ["ssl", "certificate", "security", "urgent", "critical"]):
            args["priority"] = "High"
            args["category"] = "Infrastructure" if "ssl" in task_title.lower() else "High Priority"

        # Extract due date if mentioned
        due_date = self._extract_date_from_message(message)
        if due_date:
            args["due_date"] = due_date

        return args

    def _extract_create_task_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for create task operations"""
        task_title = match.group(1).strip()

        args = {
            "title": task_title,
            "description": f"Task: {task_title}",
        }

        # Extract additional context
        priority = self._extract_priority_from_message(message)
        if priority:
            args["priority"] = priority

        due_date = self._extract_date_from_message(message)
        if due_date:
            args["due_date"] = due_date

        return args

    def _extract_update_task_progress_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for updating task progress"""
        task_identifier = match.group(1).strip()

        # Extract percentage
        progress_match = re.search(self.progress_patterns, message)
        if progress_match:
            percentage = progress_match.group(1) or progress_match.group(2)
        else:
            percentage = "50"  # Default

        return {
            "task_id": task_identifier,
            "progress": int(percentage)
        }

    def _extract_assign_existing_task_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for assigning existing task"""
        task_identifier = match.group(1).strip()
        assignee = match.group(2).strip()

        return {
            "task_id": task_identifier,
            "assigned_to": [assignee]
        }

    def _extract_update_task_priority_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for updating task priority"""
        task_identifier = match.group(1).strip()
        priority_raw = match.group(2).strip().lower()

        priority = self.priority_patterns.get(priority_raw, "Medium")

        return {
            "task_id": task_identifier,
            "priority": priority
        }

    def _extract_update_task_due_date_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for updating task due date"""
        task_identifier = match.group(1).strip()
        date_text = match.group(2).strip()

        return {
            "task_id": task_identifier,
            "due_date": self._parse_date_text(date_text)
        }

    def _extract_update_task_start_date_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for updating task start date"""
        task_identifier = match.group(1).strip()
        date_text = match.group(2).strip()

        return {
            "task_id": task_identifier,
            "start_date": self._parse_date_text(date_text)
        }

    def _extract_complete_task_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for completing task"""
        task_identifier = match.group(1).strip()

        return {
            "task_id": task_identifier,
            "progress": 100,
            "status": "completed"
        }

    def _extract_add_comment_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        """Extract arguments for adding task comment"""
        task_identifier = match.group(1).strip()
        comment_text = match.group(2).strip()

        return {
            "task_id": task_identifier,
            "comment": comment_text
        }

    # Add more extraction methods for other tools...
    def _extract_list_plans_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        return {}

    def _extract_create_plan_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        plan_name = match.group(1).strip() if match.groups() else "New Plan"
        return {"title": plan_name}

    def _extract_search_plans_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        query = match.group(1).strip()
        return {"query": query}

    def _extract_list_tasks_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        if match.groups() and match.group(1):
            return {"plan_id": match.group(1).strip()}
        return {}

    def _extract_delete_task_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        task_identifier = match.group(1).strip()
        return {"task_id": task_identifier}

    def _extract_task_details_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        task_identifier = match.group(1).strip()
        return {"task_id": task_identifier}

    def _extract_search_tasks_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        query = match.group(1).strip()
        return {"query": query}

    def _extract_my_tasks_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        return {}

    def _extract_task_by_position_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        position = int(match.group(1))
        return {"position": position}

    def _extract_next_task_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        return {}

    def _extract_add_checklist_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        task_identifier = match.group(1).strip()
        return {"task_id": task_identifier}

    def _extract_update_checklist_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        item_index = int(match.group(1))
        task_identifier = match.group(2).strip()
        return {"task_id": task_identifier, "item_index": item_index, "is_checked": True}

    def _extract_list_buckets_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        plan_id = match.group(1).strip()
        return {"plan_id": plan_id}

    def _extract_create_bucket_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        bucket_name = match.group(1).strip()
        return {"name": bucket_name}

    def _extract_update_bucket_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        old_name = match.group(1).strip()
        new_name = match.group(2).strip()
        return {"bucket_id": old_name, "name": new_name}

    def _extract_delete_bucket_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        bucket_name = match.group(1).strip()
        return {"bucket_id": bucket_name}

    def _extract_document_tasks_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        document_path = match.group(1).strip()
        return {"document_path": document_path}

    def _extract_search_documents_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        query = match.group(1).strip()
        return {"query": query}

    def _extract_analyze_relationships_args(self, message: str, match: re.Match) -> Dict[str, Any]:
        project_id = match.group(1).strip()
        return {"project_id": project_id}

    # ============================================================================
    # UTILITY FUNCTIONS
    # ============================================================================

    def _extract_date_from_message(self, message: str) -> Optional[str]:
        """Extract date from message using various patterns"""
        for pattern in self.date_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return self._parse_date_text(match.group(0))
        return None

    def _extract_priority_from_message(self, message: str) -> Optional[str]:
        """Extract priority from message"""
        for priority_word, priority_value in self.priority_patterns.items():
            if re.search(rf"\b{priority_word}\b", message, re.IGNORECASE):
                return priority_value
        return None

    def _parse_date_text(self, date_text: str) -> str:
        """Parse date text to ISO format"""
        date_text = date_text.lower().strip()

        if date_text == "today":
            return datetime.now().isoformat()
        elif date_text == "tomorrow":
            return (datetime.now() + timedelta(days=1)).isoformat()
        elif date_text == "yesterday":
            return (datetime.now() - timedelta(days=1)).isoformat()
        elif "next week" in date_text:
            return (datetime.now() + timedelta(weeks=1)).isoformat()
        else:
            # Return as-is for more complex parsing by the server
            return date_text