"""
OpenAI API compatibility translator for MCP integration
"""

import re
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

import structlog

from .mcp_client import MCPClient
from .cache import ProxyCache

logger = structlog.get_logger(__name__)


class OpenAITranslator:
    """Translates OpenAI chat completions to MCP tool calls"""

    def __init__(self, mcp_client: MCPClient, cache: ProxyCache):
        self.mcp_client = mcp_client
        self.cache = cache
        self.tool_patterns = []

        # Learning system for improving pattern recognition
        self.failed_requests = []
        self.learned_patterns = []
        self.request_history = []
        self.confidence_threshold = 0.2

    async def initialize(self):
        """Initialize translator with semantic dispatcher and fallback patterns"""
        try:
            # Try to get available tools from MCP server (resilient)
            await self._initialize_tools_safely()

            # Test semantic dispatcher availability
            await self._test_semantic_dispatcher()

            # Initialize only critical fallback patterns (reduced set)
            self.tool_patterns = self._get_critical_patterns()

            logger.info("OpenAI translator initialized with semantic dispatcher",
                       fallback_patterns_count=len(self.tool_patterns),
                       semantic_dispatcher_available=hasattr(self, '_semantic_available'))

        except Exception as e:
            logger.warning("Failed to initialize translator - continuing with limited functionality", error=str(e))
            # Fallback to full regex patterns if semantic dispatcher is not available
            self.tool_patterns = self._get_full_regex_patterns()
            logger.info("Falling back to full regex patterns", patterns_count=len(self.tool_patterns))

    async def _test_semantic_dispatcher(self):
        """Test if semantic dispatcher is available"""
        try:
            # Test with a simple message
            test_result = await self._use_semantic_dispatcher("list plans")
            if test_result:
                self._semantic_available = True
                logger.info("Semantic dispatcher is available and working")
            else:
                self._semantic_available = False
                logger.warning("Semantic dispatcher test returned no result")
        except Exception as e:
            self._semantic_available = False
            logger.warning("Semantic dispatcher is not available", error=str(e))

    def _get_full_regex_patterns(self) -> List[Dict[str, Any]]:
        """Get the original full set of regex patterns for complete fallback"""
        # Return the critical patterns expanded for compatibility
        # This is used when semantic dispatcher is completely unavailable
        critical_patterns = self._get_critical_patterns()

        # Add additional patterns for better coverage when semantic dispatcher fails
        additional_patterns = [
            # Plan-contextualized search patterns
            {
                "pattern": r"(?:look for|find|search)\s+(?:it|task|the task)\s+(?:in|from)\s+(?:the\s+)?(?:project|plan)\s+(.+)",
                "tool": "search_plans",
                "extract_args": self._extract_plan_context_search_args
            },
            {
                "pattern": r"(?:search|find)\s+(.+?)\s+(?:in|from)\s+(?:the\s+)?(?:project|plan)\s+(.+)",
                "tool": "search_plans",
                "extract_args": self._extract_task_in_plan_args
            },

            # Enhanced search patterns
            {
                "pattern": r"(?:show|list)\s+(?:me\s+)?tasks?\s+(?:named|called)\s+(\w+)",
                "tool": "search_tasks",
                "extract_args": self._extract_search_tasks_args
            },
            {
                "pattern": r"(?:find|get|locate)\s+(?:the\s+)?task\s+(?:named|called)\s+(\w+)",
                "tool": "search_tasks",
                "extract_args": self._extract_search_tasks_args
            },

            # Assignment patterns (enhanced for email addresses)
            {
                "pattern": r"(?:assign|give)\s+(?:task|this)\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+)",
                "tool": "update_task",
                "extract_args": self._extract_assign_task_args
            },
            {
                "pattern": r"(?:assign|delegate)\s+(.+?)\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+)",
                "tool": "update_task",
                "extract_args": self._extract_assign_new_task_args
            },

            # Status updates
            {
                "pattern": r"(?:mark|set)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:in\s+progress|started|working)",
                "tool": "update_task",
                "extract_args": self._extract_in_progress_task_args
            },
            {
                "pattern": r"(?:update|change)\s+(?:task\s+)?(.+?)\s+(?:to\s+)?(\d+)%",
                "tool": "update_task",
                "extract_args": self._extract_percentage_update_args
            }
        ]

        # Combine critical patterns with additional patterns
        return critical_patterns + additional_patterns

    async def _initialize_tools_safely(self):
        """Safely initialize tools from MCP client"""
        try:
            import asyncio
            # Try to list tools with a short timeout
            await asyncio.wait_for(self.mcp_client.list_tools(), timeout=5.0)
            logger.info("MCP tools initialized successfully")
        except asyncio.TimeoutError:
            logger.warning("MCP client timeout while listing tools during initialization")
        except Exception as e:
            logger.warning("Failed to list tools from MCP client during initialization", error=str(e))

    async def process_chat_completion(self, request) -> Dict[str, Any]:
        """Process OpenAI chat completion request"""
        try:
            user_id = request.user or "default"
            messages = request.messages
            conversation_id = request.conversation_id

            # Get the last user message
            last_message = None
            for msg in reversed(messages):
                if msg.role == "user":
                    last_message = msg.content
                    break

            if not last_message:
                return self._create_error_response("No user message found")

            logger.info("Processing chat completion", user_id=user_id, message=last_message[:100])

            # Check if this is an authentication-related query
            auth_response = await self._handle_auth_queries(last_message, user_id)
            if auth_response:
                return auth_response

            # Detect intent and extract tool calls
            tool_calls = await self._extract_tool_calls(last_message)

            if not tool_calls:
                # Track failed request for learning
                await self._track_failed_request(last_message, user_id)

                # Try intelligent fallbacks before giving up
                tool_calls = await self._intelligent_fallback_matching(last_message)

                if not tool_calls:
                    # No specific tool detected, provide general help
                    return await self._create_help_response(last_message, user_id)

            # Execute tool calls
            results = []
            for tool_call in tool_calls:
                try:
                    result = await self.mcp_client.execute_tool(
                        tool_call["name"],
                        tool_call["arguments"],
                        user_id
                    )
                    results.append(result)
                except Exception as e:
                    logger.error("Tool execution failed", tool=tool_call["name"], error=str(e))

                    # Check if this is an authentication error
                    error_str = str(e).lower()
                    if any(auth_indicator in error_str for auth_indicator in [
                        "403", "unauthorized", "permission", "access", "authenticate"
                    ]):
                        # This looks like an authentication issue - offer reauth
                        return await self._handle_authentication_error(user_id, tool_call["name"], str(e))

                    results.append({
                        "success": False,
                        "error": str(e),
                        "tool_name": tool_call["name"]
                    })

            # Format response
            response_content = await self._format_tool_results(results, tool_calls)

            # Create OpenAI-compatible response
            return self._create_chat_response(
                content=response_content,
                model=request.model,
                conversation_id=conversation_id
            )

        except Exception as e:
            logger.error("Error processing chat completion", error=str(e))
            return self._create_error_response(f"Processing failed: {str(e)}")

    async def _extract_tool_calls(self, message: str) -> List[Dict[str, Any]]:
        """Extract tool calls from natural language message using semantic dispatcher"""
        tool_calls = []
        start_time = datetime.now()

        logger.info("Tool extraction started",
                   message=message[:100],
                   semantic_available=getattr(self, '_semantic_available', False))

        # First try semantic dispatcher (primary method) if available
        if getattr(self, '_semantic_available', False):
            try:
                semantic_result = await self._use_semantic_dispatcher(message)
                if semantic_result:
                    confidence = semantic_result.get("confidence", 0)
                    suggested_actions = semantic_result.get("suggested_actions", [])

                    logger.info("Semantic dispatcher result",
                               confidence=confidence,
                               suggested_actions_count=len(suggested_actions),
                               intent=semantic_result.get("intent", {}).get("intent"))

                    # Remove assignment bypass - we want these to use enhanced semantic processing
                    # with Neo4j knowledge graph and RAG services for better understanding
                    bypass_patterns = [
                        # Only bypass extremely simple patterns that don't benefit from semantic processing
                    ]

                    should_bypass = any(re.search(pattern, message, re.IGNORECASE) for pattern in bypass_patterns)

                    # Use semantic result with lower threshold for better coverage
                    if confidence >= 0.1 and not should_bypass:
                        # Convert semantic dispatcher results to tool calls
                        for action in suggested_actions:
                            action_confidence = action.get("confidence", 0)
                            if action_confidence >= 0.1:
                                tool_calls.append({
                                    "name": action["tool"],
                                    "arguments": action["parameters"],
                                    "confidence": action_confidence,
                                    "source": "semantic"
                                })
                                logger.info("Semantic tool call created",
                                           tool_name=action["tool"],
                                           confidence=action_confidence)

                        # If no suggested actions but we have a valid intent, create tool call from intent
                        if not tool_calls and confidence >= 0.7:
                            intent_info = semantic_result.get("intent", {})
                            detected_intent = intent_info.get("intent") if isinstance(intent_info, dict) else None
                            entities = semantic_result.get("entities", {})

                            tool_call = await self._convert_intent_to_tool_call(detected_intent, entities, message, confidence)
                            if tool_call:
                                tool_calls.append(tool_call)
                                logger.info("Intent-based tool call created",
                                           intent=detected_intent,
                                           tool_name=tool_call["name"],
                                           confidence=confidence)

                        if tool_calls:
                            processing_time = (datetime.now() - start_time).total_seconds()
                            logger.info("Semantic dispatcher success",
                                       tool_calls_count=len(tool_calls),
                                       processing_time_ms=processing_time * 1000)
                            return tool_calls
                    else:
                        logger.info("Semantic confidence too low, falling back to regex",
                                   confidence=confidence)
                else:
                    logger.warning("Semantic dispatcher returned no result")

            except Exception as e:
                logger.warning("Semantic dispatcher failed, falling back to regex",
                              error=str(e),
                              error_type=type(e).__name__)
        else:
            logger.info("Semantic dispatcher not available, using regex patterns")

        # Fallback to regex patterns
        return await self._extract_with_regex_fallback(message, start_time)

    async def _extract_with_regex_fallback(self, message: str, start_time: datetime) -> List[Dict[str, Any]]:
        """Extract tool calls using regex patterns as fallback"""
        tool_calls = []
        message_lower = message.lower()

        logger.info("Using regex fallback for tool detection")

        # Use appropriate pattern set based on semantic dispatcher availability
        if getattr(self, '_semantic_available', False):
            # Use critical patterns only since semantic should handle most cases
            patterns = self._get_critical_patterns()
            pattern_type = "critical"
        else:
            # Use full pattern set if semantic dispatcher is unavailable
            patterns = self.tool_patterns
            pattern_type = "full"

        logger.debug("Regex fallback pattern details",
                    pattern_type=pattern_type,
                    pattern_count=len(patterns))

        for i, pattern_info in enumerate(patterns):
            pattern = pattern_info["pattern"]
            tool_name = pattern_info["tool"]

            try:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    logger.info("Regex pattern matched",
                               pattern_index=i+1,
                               pattern=pattern[:50] + "..." if len(pattern) > 50 else pattern,
                               tool=tool_name)

                    # Extract arguments with error handling
                    try:
                        arguments = pattern_info["extract_args"](message)
                        tool_calls.append({
                            "name": tool_name,
                            "arguments": arguments,
                            "confidence": 0.8,  # Regex patterns get medium confidence
                            "source": "regex"
                        })
                        logger.info("Regex tool call created",
                                   tool_name=tool_name,
                                   arguments_keys=list(arguments.keys()) if arguments else [])
                        break  # Use first matching pattern

                    except Exception as arg_error:
                        logger.error("Error extracting arguments from regex pattern",
                                    pattern=pattern[:50] + "..." if len(pattern) > 50 else pattern,
                                    tool=tool_name,
                                    error=str(arg_error),
                                    error_type=type(arg_error).__name__)
                        continue  # Try next pattern

            except Exception as pattern_error:
                logger.error("Error processing regex pattern",
                            pattern_index=i+1,
                            pattern=pattern[:50] + "..." if len(pattern) > 50 else pattern,
                            error=str(pattern_error),
                            error_type=type(pattern_error).__name__)
                continue  # Try next pattern

        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info("Tool extraction completed",
                   method="regex_fallback",
                   tool_calls_count=len(tool_calls),
                   processing_time_ms=processing_time * 1000,
                   pattern_type=pattern_type)

        return tool_calls

    async def _use_semantic_dispatcher(self, message: str) -> Optional[Dict[str, Any]]:
        """Use semantic dispatcher to process natural language with comprehensive error handling"""
        start_time = datetime.now()

        try:
            # Validate input
            if not message or not message.strip():
                logger.warning("Semantic dispatcher: Empty message provided")
                return None

            # Call the process_natural_language tool via MCP
            logger.debug("Semantic dispatcher: Calling process_natural_language",
                        message_length=len(message),
                        message_preview=message[:50])

            result = await self.mcp_client.execute_tool(
                "process_natural_language",
                {
                    "user_input": message.strip(),
                    "session_id": "openai_translator_session",
                    "user_id": "translator_user"
                },
                "translator_user"
            )

            processing_time = (datetime.now() - start_time).total_seconds()

            # Validate result structure
            if not isinstance(result, dict):
                logger.error("Semantic dispatcher: Invalid result type",
                            result_type=type(result).__name__,
                            processing_time_ms=processing_time * 1000)
                return None

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                logger.warning("Semantic dispatcher: Tool execution failed",
                              error=error_msg,
                              processing_time_ms=processing_time * 1000)
                return None

            content = result.get("content")
            if not content:
                logger.warning("Semantic dispatcher: No content in successful result",
                              result_keys=list(result.keys()),
                              processing_time_ms=processing_time * 1000)
                return None

            # Validate content structure
            if not isinstance(content, dict):
                logger.error("Semantic dispatcher: Invalid content type",
                            content_type=type(content).__name__,
                            processing_time_ms=processing_time * 1000)
                return None

            # Log successful result with details
            intent_info = content.get("intent", {})
            entities = content.get("entities", {})
            suggested_actions = content.get("suggested_actions", [])

            logger.info("Semantic dispatcher: Successful processing",
                       intent=intent_info.get("intent") if isinstance(intent_info, dict) else str(intent_info),
                       confidence=content.get("confidence"),
                       entities_count=len(entities) if isinstance(entities, dict) else 0,
                       actions_count=len(suggested_actions) if isinstance(suggested_actions, list) else 0,
                       processing_time_ms=processing_time * 1000)

            return content

        except asyncio.TimeoutError:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error("Semantic dispatcher: Timeout error",
                        timeout_seconds=processing_time,
                        message_preview=message[:50] if message else "")
            return None

        except ConnectionError as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error("Semantic dispatcher: Connection error",
                        error=str(e),
                        processing_time_ms=processing_time * 1000)
            return None

        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error("Semantic dispatcher: Unexpected error",
                        error=str(e),
                        error_type=type(e).__name__,
                        processing_time_ms=processing_time * 1000,
                        message_preview=message[:50] if message else "")
            return None

    def _get_critical_patterns(self) -> List[Dict[str, Any]]:
        """Get critical regex patterns for fallback scenarios"""
        # Return only the most critical patterns that must work even if semantic dispatcher fails
        critical_patterns = [
            # Authentication patterns (highest priority)
            {
                "pattern": r"(?:login|authenticate|sign in|connect)",
                "tool": "get_login_url",
                "extract_args": lambda msg: {}
            },
            {
                "pattern": r"(?:logout|sign out|disconnect)",
                "tool": "logout",
                "extract_args": lambda msg: {}
            },

            # Basic search patterns (high priority)
            {
                "pattern": r"(?:search|find|look for)\s+(?:task|tasks?)",
                "tool": "search_tasks",
                "extract_args": self._extract_search_tasks_args
            },
            {
                "pattern": r"(?:search|find|look for)\s+plans?",
                "tool": "search_plans",
                "extract_args": self._extract_search_plans_args
            },

            # My tasks pattern (high priority)
            {
                "pattern": r"(?:list|show|get|find)\s+(?:all\s+)?(?:my|mine|assigned to me)\s+(?:task|tasks?)",
                "tool": "get_my_tasks",
                "extract_args": self._extract_get_my_tasks_args
            },
            # Tasks assigned to specific user (email or name)
            {
                "pattern": r"(?:what\s+)?(?:task|tasks?)\s+(?:are\s+)?assigned\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+(?:\s+\w+)?)",
                "tool": "search_tasks",
                "extract_args": self._extract_assigned_to_args
            },
            # General task listing (when no specific context provided, search across all plans)
            {
                "pattern": r"(?:list|show|get|find)\s+(?:all\s+)?tasks?$",
                "tool": "search_tasks",
                "extract_args": self._extract_list_all_tasks_args
            },

            # Basic list operations
            {
                "pattern": r"(?:list|show|get|find)\s+(?:all\s+)?(?:my\s+)?plans?",
                "tool": "list_plans",
                "extract_args": self._extract_list_plans_args
            },
            {
                "pattern": r"(?:list|show|get|find)\s+(?:all\s+)?tasks?\s+(?:in|for|from)\s+plan\s+(\w+)",
                "tool": "list_tasks",
                "extract_args": self._extract_list_tasks_args
            },
            # What tasks are in [plan] pattern - EXPANDED for natural language
            {
                "pattern": r"(?:what|which|show|list|get|find)\s+(?:are\s+)?(?:the\s+)?tasks?\s+(?:are\s+)?(?:in|for|from|of)\s+(?:the\s+)?(?:plan\s+)?(\w+)(?:\s+plan)?",
                "tool": "search_tasks",
                "extract_args": self._extract_what_tasks_in_plan_args
            },
            # Alternative patterns for task requests
            {
                "pattern": r"tasks?\s+(?:in|for|from|of)\s+(\w+)",
                "tool": "search_tasks",
                "extract_args": self._extract_what_tasks_in_plan_args
            },
            {
                "pattern": r"(?<!create\s)(?<!make\s)(?<!add\s)(?<!new\s)(?<!create\sa\s)(?<!make\sa\s)(?<!add\sa\s)(?<!new\sa\s)(\w+)\s+(?:plan\s+)?tasks?",
                "tool": "search_tasks",
                "extract_args": self._extract_what_tasks_in_plan_args
            },

            # Create operations (basic patterns only)
            {
                "pattern": r"(?:create|make|add|new)\s+(?:a\s+)?plan",
                "tool": "create_plan",
                "extract_args": self._extract_create_plan_args
            },
            {
                "pattern": r"(?:create|make|add|new)\s+(?:a\s+)?task",
                "tool": "create_task",
                "extract_args": self._extract_create_task_args
            },
            # Create and assign task in one command (e.g., "assign task: configure ssl to angel@example.com")
            {
                "pattern": r"(?:assign\s+task|create\s+task):\s*(.+?)\s+(?:to|for)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+)",
                "tool": "create_task",
                "extract_args": self._extract_create_and_assign_task_args
            },

            # Update operations (basic patterns only)
            {
                "pattern": r"(?:mark|set)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:complete|completed|done|finished)",
                "tool": "update_task",
                "extract_args": self._extract_complete_task_args
            },

            # MISSING PATTERNS FROM TESTING
            # Percentage-based updates
            {
                "pattern": r"(?:update|set|change)\s+task\s+(.+?)\s+(?:to|as)\s+(\d+)%\s*(?:complete|progress|done)?",
                "tool": "update_task",
                "extract_args": self._extract_percentage_update_args
            },
            {
                "pattern": r"(?:set|make)\s+(.+?)\s+(?:to\s+)?(\d+)%\s*(?:complete|progress|done)?",
                "tool": "update_task",
                "extract_args": self._extract_percentage_update_args
            },

            # Advanced search for plans
            {
                "pattern": r"(?:search|find|look)\s+(?:for\s+)?plans?\s+(?:about|containing|regarding|on)\s+(.+)",
                "tool": "search_plans",
                "extract_args": self._extract_search_plans_args
            },

            # Assignment-based task filtering
            {
                "pattern": r"(?:show|list|find|get)\s+(?:all\s+)?(?:incomplete|pending|active)?\s*tasks?\s+assigned\s+to\s+(.+)",
                "tool": "search_tasks",
                "extract_args": self._extract_assigned_tasks_args
            },
            {
                "pattern": r"(?:show|list|find)\s+(.+?)(?:'s|s)\s+tasks?",
                "tool": "search_tasks",
                "extract_args": self._extract_user_tasks_args
            },

            # Task details patterns
            {
                "pattern": r"(?:show|get|tell me about|describe)\s+(?:details of|info on|information about)\s+task\s+(.+)",
                "tool": "get_task_details",
                "extract_args": self._extract_task_details_args
            },

            # Delete task patterns
            {
                "pattern": r"(?:delete|remove|cancel)\s+(?:the\s+)?task\s+(.+)",
                "tool": "delete_task",
                "extract_args": self._extract_delete_task_args
            },

            # Task position patterns
            {
                "pattern": r"(?:show|get|what\s+is)\s+(?:the\s+)?(?:first|1st|second|2nd|third|3rd|last)\s+task",
                "tool": "get_task_by_position",
                "extract_args": self._extract_task_position_args
            },

            # Next task patterns
            {
                "pattern": r"(?:what\s+should\s+i\s+work\s+on\s+next|what's\s+next|next\s+task)",
                "tool": "get_next_task",
                "extract_args": lambda msg: {}
            }
        ]

        logger.info("Critical patterns loaded", count=len(critical_patterns))
        return critical_patterns

    # Argument extraction methods

    def _extract_list_plans_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for list_plans"""
        args = {}

        # Look for group-specific requests
        group_match = re.search(r"(?:for|in|from)\s+group\s+(\w+)", message, re.IGNORECASE)
        if group_match:
            args["group_id"] = group_match.group(1)

        # Look for archived plans
        if re.search(r"archived|old", message, re.IGNORECASE):
            args["include_archived"] = True

        return args

    def _extract_create_plan_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for create_plan"""
        args = {}

        # Extract title from quotes or after "called"/"named"
        title_patterns = [
            r'"([^"]+)"',
            r"'([^']+)'",
            r"(?:called|named)\s+([^\s,\.!?]+)",
            r"plan\s+([^\s,\.!?]+)"
        ]

        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["title"] = match.group(1)
                break

        # Extract group ID
        group_match = re.search(r"(?:for|in|with)\s+group\s+(\w+)", message, re.IGNORECASE)
        if group_match:
            args["group_id"] = group_match.group(1)

        # Extract description
        desc_match = re.search(r"(?:description|about|for)[\s:]+([^\.!?]+)", message, re.IGNORECASE)
        if desc_match:
            args["description"] = desc_match.group(1).strip()

        return args

    def _extract_list_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for list_tasks"""
        args = {}

        # Extract plan ID
        plan_match = re.search(r"(?:in|for|from)\s+plan\s+(\w+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1)

        # Filter completed tasks
        if re.search(r"(?:not\s+completed|incomplete|pending|active)", message, re.IGNORECASE):
            args["filter_completed"] = True

        # Filter by assignee
        assignee_match = re.search(r"(?:assigned to|for)\s+(\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assigned_to"] = assignee_match.group(1)

        return args

    def _extract_get_my_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for get_my_tasks"""
        args = {}

        # Check for status filters
        if re.search(r"(?:incomplete|pending|active|unfinished)", message, re.IGNORECASE):
            args["status"] = "active"
        elif re.search(r"(?:completed|finished|done)", message, re.IGNORECASE):
            args["status"] = "completed"
        else:
            args["status"] = "all"

        # Check for sorting preferences
        if re.search(r"(?:due|deadline)", message, re.IGNORECASE):
            args["sort_by"] = "due_date"
        elif re.search(r"(?:priority|important)", message, re.IGNORECASE):
            args["sort_by"] = "priority"
        elif re.search(r"(?:recent|newest|latest)", message, re.IGNORECASE):
            args["sort_by"] = "created"

        # Set reasonable limit
        args["limit"] = 50

        return args

    def _extract_assigned_to_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for tasks assigned to specific user"""
        args = {}

        # Extract email address or name from the pattern match
        pattern = r"(?:what\s+)?(?:task|tasks?)\s+(?:are\s+)?assigned\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+(?:\s+\w+)?)"
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            assignee = match.group(1).strip()
            args["assigned_to"] = assignee

            # Set search query to find tasks assigned to this user
            args["query"] = f"assigned to {assignee}"

        # Set a reasonable limit
        args["limit"] = 50

        return args

    def _extract_search_all_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for searching all tasks across all plans"""
        args = {}

        # Use a broad query that should match most tasks - common words/letters
        if re.search(r"(?:incomplete|pending|active|unfinished)", message, re.IGNORECASE):
            args["query"] = "a"  # Single letter should match most tasks with 'a'
            args["status"] = "active"
        elif re.search(r"(?:completed|finished|done)", message, re.IGNORECASE):
            args["query"] = "a"  # Single letter to cast wide net
            args["status"] = "completed"
        else:
            # Search for all tasks - use single letter query to match broadly
            args["query"] = "a"  # Very common letter that appears in most task names
            args["status"] = "all"

        # Set a higher limit since we want to see tasks across all plans
        args["limit"] = 100

        return args

    def _extract_list_all_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for listing all tasks across all plans"""
        args = {}

        # Use a broad search query to find all tasks
        # Using common letters/words that should match most task titles
        args["query"] = "e"  # Most common letter in English, should match most tasks

        # Check for status filters
        if re.search(r"(?:incomplete|pending|active|unfinished)", message, re.IGNORECASE):
            args["status"] = "active"
        elif re.search(r"(?:completed|finished|done)", message, re.IGNORECASE):
            args["status"] = "completed"
        else:
            args["status"] = "all"  # Show all tasks regardless of status

        # Set a higher limit for comprehensive listing
        args["limit"] = 100  # Show more tasks for "list all" command

        return args

    def _extract_what_tasks_in_plan_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for 'what tasks are in [plan]' requests"""
        args = {}

        # Multiple pattern attempts for flexible extraction
        patterns = [
            r"(?:what|which|show|list|get|find)\s+(?:are\s+)?(?:the\s+)?tasks?\s+(?:are\s+)?(?:in|for|from|of)\s+(?:the\s+)?(?:plan\s+)?(\w+)(?:\s+plan)?",
            r"tasks?\s+(?:in|for|from|of)\s+(\w+)",
            r"(\w+)\s+(?:plan\s+)?tasks?",
            r"(?:in|from)\s+(?:plan\s+)?(\w+)",
            r"plan\s+(\w+)\s+tasks?",
        ]

        plan_name = None
        for pattern in patterns:
            plan_match = re.search(pattern, message, re.IGNORECASE)
            if plan_match:
                plan_name = plan_match.group(1)
                break

        # If no regex match, try word-based extraction
        if not plan_name:
            words = message.lower().split()
            # Look for common plan keywords
            if "ai" in words:
                plan_name = "ai"
            elif any(word in words for word in ["plan", "tasks", "task"]):
                # Find the word after "plan" or before "tasks"
                for i, word in enumerate(words):
                    if word == "plan" and i + 1 < len(words):
                        plan_name = words[i + 1]
                        break
                    elif word in ["tasks", "task"] and i > 0:
                        prev_word = words[i - 1]
                        if prev_word not in ["what", "are", "the", "in", "all", "my"]:
                            plan_name = prev_word
                            break

        if plan_name:
            # Use search_tasks with plan name as search query
            args["query"] = plan_name
            args["plan_context"] = plan_name
            args["_search_mode"] = "plan_tasks"
            logger.info("Extracted plan name from request", plan_name=plan_name, message=message[:50])
        else:
            # Fallback: search all tasks
            args["query"] = ""
            logger.warning("Could not extract plan name, searching all tasks", message=message[:50])

        return args

    def _extract_create_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for create_task"""
        args = {}

        # Extract plan ID
        plan_match = re.search(r"(?:in|for|to)\s+plan\s+(\w+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1)

        # Extract title
        title_patterns = [
            r'"([^"]+)"',
            r"'([^']+)'",
            r"task\s+([^\s,\.!?]+)"
        ]

        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["title"] = match.group(1)
                break

        # Extract due date
        date_match = re.search(r"(?:due|by|before)\s+([\w\s\-\/]+?)(?:\s|$|,|\.)", message, re.IGNORECASE)
        if date_match:
            args["due_date"] = date_match.group(1).strip()

        # Extract priority
        if re.search(r"urgent|high priority|important", message, re.IGNORECASE):
            args["priority"] = 1
        elif re.search(r"low priority|later", message, re.IGNORECASE):
            args["priority"] = 9

        # Extract assignee
        assignee_match = re.search(r"(?:assign to|for)\s+(\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assigned_to"] = [assignee_match.group(1)]

        return args

    def _extract_update_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for update_task"""
        args = {}

        # Extract task ID
        task_match = re.search(r"task\s+(\w+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1)

        # Extract new title
        title_match = re.search(r"(?:title|name)\s+(?:to\s+)?[\"']([^\"']+)[\"']", message, re.IGNORECASE)
        if title_match:
            args["title"] = title_match.group(1)

        # Extract completion percentage
        percent_match = re.search(r"(\d+)%", message)
        if percent_match:
            args["percent_complete"] = int(percent_match.group(1))

        # Extract priority
        if re.search(r"urgent|high", message, re.IGNORECASE):
            args["priority"] = 1
        elif re.search(r"low|later", message, re.IGNORECASE):
            args["priority"] = 9

        return args

    def _extract_complete_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for completing a task"""
        args = {"percent_complete": 100}

        # Extract task ID
        task_match = re.search(r"task\s+(\w+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1)

        return args

    async def _convert_intent_to_tool_call(self, intent: str, entities: Dict[str, Any], message: str, confidence: float) -> Optional[Dict[str, Any]]:
        """Convert detected intent and entities to a tool call"""
        if not intent:
            return None

        logger.info("Converting intent to tool call",
                   intent=intent,
                   entities=entities,
                   message_preview=message[:100])

        # Intent to tool mapping
        intent_tool_map = {
            "create_task": "create_task",
            "create_and_assign_task": "create_task",
            "assign_task": "create_task",  # For new tasks with assignment
            "read_tasks": "search_tasks",
            "update_task": "update_task",
            "delete_task": "delete_task",
            "complete_task": "update_task",
            "get_task_details": "get_task",
            "list_assignments": "search_tasks"
        }

        tool_name = intent_tool_map.get(intent)
        if not tool_name:
            logger.warning("No tool mapping for intent", intent=intent)
            return None

        # Extract arguments based on intent and entities
        args = {}

        if intent in ["create_task", "create_and_assign_task", "assign_task"]:
            # Handle task creation with assignment
            if "EMAIL" in entities:
                args["assigned_to"] = [entities["EMAIL"]]
            elif "ASSIGNEE" in entities:
                args["assigned_to"] = [entities["ASSIGNEE"]]

            # Extract task title from message - prefer quoted strings over entities
            title_match = re.search(r'["\']([^"\']+)["\']', message)
            if title_match:
                args["title"] = title_match.group(1)
            elif "TASK_TITLE" in entities:
                args["title"] = entities["TASK_TITLE"]
            else:
                # Fallback: extract after "task" keyword
                task_match = re.search(r'task\s+(.+?)(?:\s+to\s+|\s*$)', message, re.IGNORECASE)
                if task_match:
                    args["title"] = task_match.group(1).strip()

            # Intelligent plan selection - analyze task context to suggest relevant plans
            plan_context = await self._determine_plan_context(message, entities)
            if plan_context["requires_selection"]:
                # Return a special response requesting plan selection
                return {
                    "name": "request_plan_selection",
                    "arguments": {
                        "task_title": args.get("title", "Untitled Task"),
                        "assigned_to": args.get("assigned_to", []),
                        "suggested_plans": plan_context["suggested_plans"],
                        "context_analysis": plan_context["analysis"]
                    },
                    "confidence": confidence,
                    "source": "plan_selection_required"
                }
            else:
                args["plan_id"] = plan_context["selected_plan_id"]

        elif intent in ["read_tasks", "list_assignments"]:
            # Handle task searching/listing - check if this is an assignment query
            assignment_query = False

            # Check for assignment-related phrases and extract assignee
            assignee = None

            # Pattern 1: "tasks assigned to [name/email]"
            assigned_to_match = re.search(r'tasks assigned to\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)', message, re.IGNORECASE)
            if assigned_to_match:
                assignment_query = True
                assignee = assigned_to_match.group(1)

            # Pattern 2: "assigned to [name/email]"
            elif re.search(r'assigned to\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)', message, re.IGNORECASE):
                assignment_query = True
                assignee_match = re.search(r'assigned to\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)', message, re.IGNORECASE)
                assignee = assignee_match.group(1)

            # Pattern 3: "tasks for [name/email]"
            elif re.search(r'tasks for\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)', message, re.IGNORECASE):
                assignment_query = True
                assignee_match = re.search(r'tasks for\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)', message, re.IGNORECASE)
                assignee = assignee_match.group(1)

            # Fallback: Check entities for EMAIL or ASSIGNEE
            elif "EMAIL" in entities:
                assignment_query = True
                assignee = entities["EMAIL"]
            elif "ASSIGNEE" in entities:
                assignment_query = True
                assignee = entities["ASSIGNEE"]

            if assignment_query and assignee:
                # Use search_tasks for assignment queries
                tool_name = "search_tasks"
                args["query"] = assignee
                args["assigned_to"] = assignee
                # Add default plan - we'll search across the default plan
                args["plan_id"] = "G6H5hKp1v06Wd-tzQtduqGQADv35"  # AI Agentic R&D plan
            else:
                # Regular task listing - add default plan
                args["plan_id"] = "G6H5hKp1v06Wd-tzQtduqGQADv35"  # AI Agentic R&D plan
                args["query"] = ""

        # Add default values if needed
        if tool_name == "create_task" and "title" not in args:
            args["title"] = "Untitled Task"

        logger.info("Intent conversion completed",
                   tool_name=tool_name,
                   arguments=args,
                   confidence=confidence)

        return {
            "name": tool_name,
            "arguments": args,
            "confidence": confidence,
            "source": "intent_conversion"
        }

    async def _determine_plan_context(self, message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze task context and determine appropriate plan selection strategy"""
        try:
            # Get available plans
            plans_result = await self.mcp_client.execute_tool(
                "list_plans",
                {},
                "default"
            )

            if not plans_result.get("success") or not plans_result.get("content", {}).get("plans"):
                # Fallback to default plan if we can't get plans
                return {
                    "requires_selection": False,
                    "selected_plan_id": "G6H5hKp1v06Wd-tzQtduqGQADv35",
                    "analysis": "Using default plan (could not retrieve plan list)"
                }

            plans = plans_result["content"]["plans"]

            # Extract task context
            task_title = entities.get("TASK_TITLE", "")
            if not task_title:
                # Try to extract from quoted strings
                title_match = re.search(r'["\']([^"\']+)["\']', message)
                if title_match:
                    task_title = title_match.group(1)

            # Analyze task keywords for plan relevance
            task_keywords = message.lower()

            # Define plan relevance scoring
            plan_scores = []
            for plan in plans:
                plan_title = plan["title"].lower()
                score = 0

                # Keyword matching
                if "ssl" in task_keywords or "security" in task_keywords or "certificate" in task_keywords:
                    if "ai" in plan_title and ("project" in plan_title or "r&d" in plan_title):
                        score += 30
                elif "ai" in task_keywords or "assistant" in task_keywords:
                    if "ai" in plan_title:
                        score += 40
                        if "assistant" in plan_title:
                            score += 20
                elif "policy" in task_keywords:
                    if "policy" in plan_title:
                        score += 50

                # General AI/tech relevance
                if any(word in task_keywords for word in ["configure", "setup", "technical", "system"]):
                    if "ai" in plan_title:
                        score += 15

                plan_scores.append({
                    "plan": plan,
                    "score": score,
                    "title": plan["title"],
                    "id": plan["id"]
                })

            # Sort by relevance score
            plan_scores.sort(key=lambda x: x["score"], reverse=True)

            # Decision logic
            top_score = plan_scores[0]["score"] if plan_scores else 0
            relevant_plans = [p for p in plan_scores if p["score"] >= max(20, top_score * 0.7)]

            if len(relevant_plans) <= 1:
                # Clear choice or no specific relevance - use top plan
                selected_plan = plan_scores[0] if plan_scores else None
                return {
                    "requires_selection": False,
                    "selected_plan_id": selected_plan["id"] if selected_plan else "G6H5hKp1v06Wd-tzQtduqGQADv35",
                    "analysis": f"Auto-selected '{selected_plan['title']}' (score: {selected_plan['score']})" if selected_plan else "Using fallback plan"
                }
            else:
                # Multiple relevant plans - request user selection
                return {
                    "requires_selection": True,
                    "suggested_plans": [
                        {
                            "title": p["title"],
                            "id": p["id"],
                            "relevance_score": p["score"],
                            "reason": self._get_relevance_reason(p["title"], task_keywords)
                        }
                        for p in relevant_plans[:4]  # Limit to top 4
                    ],
                    "analysis": f"Found {len(relevant_plans)} relevant plans for task: {task_title}"
                }

        except Exception as e:
            logger.error("Error in plan context determination", error=str(e))
            return {
                "requires_selection": False,
                "selected_plan_id": "G6H5hKp1v06Wd-tzQtduqGQADv35",
                "analysis": f"Error occurred, using fallback plan: {str(e)}"
            }

    def _get_relevance_reason(self, plan_title: str, task_keywords: str) -> str:
        """Generate human-readable reason for plan relevance"""
        plan_lower = plan_title.lower()

        if "ssl" in task_keywords and "ai" in plan_lower:
            return "AI/Technical project suitable for SSL configuration tasks"
        elif "ai" in task_keywords and "assistant" in plan_lower:
            return "Direct match for AI assistant related tasks"
        elif "ai" in plan_lower and any(word in task_keywords for word in ["configure", "setup", "technical"]):
            return "AI project plan for technical configuration tasks"
        elif "policy" in plan_lower and "policy" in task_keywords:
            return "Policy-related project for compliance tasks"
        else:
            return "General relevance to task context"

    def _extract_percentage_update_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for percentage-based task updates"""
        args = {}

        # Extract task identifier
        task_patterns = [
            r"(?:update|set|change)\s+task\s+(\w+)",
            r"(?:set|make)\s+(\w+)",
            r"task\s+(\w+)"
        ]

        for pattern in task_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["task_id"] = match.group(1)
                break

        # Extract percentage
        percent_match = re.search(r"(\d+)%", message)
        if percent_match:
            args["percent_complete"] = int(percent_match.group(1))

        return args

    def _extract_assigned_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for finding tasks assigned to specific users"""
        args = {}

        # Extract assignee
        assignee_match = re.search(r"assigned\s+to\s+(\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assignee"] = assignee_match.group(1)
            # Use assignee as search query
            args["query"] = assignee_match.group(1)

        # Check for status filters
        if re.search(r"(?:incomplete|pending|active)", message, re.IGNORECASE):
            args["status"] = "active"

        return args

    def _extract_user_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for finding a user's tasks"""
        args = {}

        # Extract user name (before 's or s)
        user_match = re.search(r"(\w+?)(?:'s|s)\s+tasks?", message, re.IGNORECASE)
        if user_match:
            args["assignee"] = user_match.group(1)
            args["query"] = user_match.group(1)

        return args

    def _extract_task_details_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for getting task details"""
        args = {}

        # Extract task identifier
        task_patterns = [
            r"task\s+(\w+)",
            r"(?:details of|info on|information about)\s+(\w+)",
            r"(?:tell me about|describe)\s+(\w+)"
        ]

        for pattern in task_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["task_id"] = match.group(1)
                break

        return args

    def _extract_delete_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for deleting tasks"""
        args = {}

        # Extract task identifier
        task_patterns = [
            r"(?:delete|remove|cancel)\s+(?:the\s+)?task\s+(\w+)",
            r"task\s+(\w+)"
        ]

        for pattern in task_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["task_id"] = match.group(1)
                break

        return args

    def _extract_task_position_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for getting tasks by position"""
        args = {}

        # Extract position
        position_patterns = {
            r"(?:first|1st)": "1",
            r"(?:second|2nd)": "2",
            r"(?:third|3rd)": "3",
            r"(?:last)": "last",
            r"(?:number\s+)?(\d+)": None  # Will use captured group
        }

        for pattern, value in position_patterns.items():
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                if value:
                    args["position"] = value
                else:
                    args["position"] = match.group(1)
                break

        return args

    def _extract_search_plans_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for search_plans"""
        args = {}

        # Extract search query
        query_patterns = [
            r'search\s+(?:for\s+)?["\']([^"\']+)["\']',
            r'find\s+(?:plans?\s+)?["\']([^"\']+)["\']',
            r'look for\s+["\']([^"\']+)["\']',
            r'search\s+(?:for\s+)?(\w+)',
            r'find\s+(\w+)'
        ]

        for pattern in query_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                args["query"] = match.group(1)
                break

        return args

    def _extract_search_tasks_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for search_tasks"""
        args = {}
        logger.info("DEBUG: Extracting search args from message", message=message)

        # Extract search query - look for various patterns (ordered by specificity)
        query_patterns = [
            # Quoted patterns (highest priority)
            r'(?:search|find|look for)\s+(?:task|tasks?)\s+(?:with\s+query\s+)?["\']([^"\']+)["\']',
            r'(?:search|find|look for)\s+["\']([^"\']+)["\']',
            r'(?:show|list)\s+(?:me\s+)?tasks?\s+(?:named|called)\s+["\']([^"\']+)["\']',

            # Named/called patterns (high priority)
            r'(?:show|list)\s+(?:me\s+)?tasks?\s+(?:named|called)\s+(\w+)',
            r'(?:find|get|locate).*(?:named|called)\s+["\']([^"\']+)["\']',
            r'(?:find|get|locate).*(?:named|called)\s+(\w+)',
            r'task.*(?:named|called)\s+(\w+)',

            # Multi-word search patterns
            r'(?:search|find)\s+(?:task|tasks?)\s+(\w+)',
            r'search\s+(?:task|tasks?)\s+(\w+)',

            # General search patterns (lowest priority)
            r'(?:search|find)\s+(?:for\s+)?(\w+)(?!\s+task)',  # Negative lookahead to avoid "search tasks"
            r'(\w+)\s+task'
        ]

        for i, pattern in enumerate(query_patterns):
            match = re.search(pattern, message, re.IGNORECASE)
            if match and match.group(1):
                logger.info(f"DEBUG: Pattern {i+1} matched", pattern=pattern, extracted=match.group(1))
                args["query"] = match.group(1)
                break
            else:
                logger.debug(f"DEBUG: Pattern {i+1} no match", pattern=pattern)

        # Special handling for common keywords
        if "query" not in args:
            logger.info("DEBUG: No pattern matched, checking special keywords")
            # Look for specific words like "designated", "profile"
            if "designated" in message.lower():
                logger.info("DEBUG: Found 'designated' keyword")
                args["query"] = "designated"
            elif "profile" in message.lower():
                logger.info("DEBUG: Found 'profile' keyword")
                args["query"] = "profile"
            elif "teams planner" in message.lower():
                logger.info("DEBUG: Found 'teams planner' keyword")
                args["query"] = "Teams Planner"

        logger.info("DEBUG: Final extracted args", args=args)
        return args

    # Enhanced argument extractors for new patterns

    def _extract_assigned_to_search_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for searching tasks assigned to someone"""
        args = {}

        assignee_match = re.search(r"(?:assigned|given)\s+to\s+(\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assigned_to"] = assignee_match.group(1)

        return args

    def _extract_due_date_search_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for searching tasks by due date"""
        args = {}

        if "today" in message.lower():
            args["due_date_filter"] = "today"
        elif "tomorrow" in message.lower():
            args["due_date_filter"] = "tomorrow"
        elif "this week" in message.lower():
            args["due_date_filter"] = "this_week"
        elif "next week" in message.lower():
            args["due_date_filter"] = "next_week"

        return args

    def _extract_overdue_search_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for searching overdue tasks"""
        return {"status_filter": "overdue"}

    def _extract_incomplete_search_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for searching incomplete tasks"""
        return {"status_filter": "incomplete"}

    def _extract_completed_search_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for searching completed tasks"""
        return {"status_filter": "completed"}

    def _extract_delete_plan_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for deleting/archiving a plan"""
        args = {}

        plan_match = re.search(r"(?:plan\s+)?(\w+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1)

        if "archive" in message.lower():
            args["action"] = "archive"
        else:
            args["action"] = "delete"

        return args

    def _extract_action_to_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments from 'I need to' or 'We need to' patterns"""
        args = {}

        action_match = re.search(r"(?:i\s+need\s+to|we\s+need\s+to|let's|please)\s+(.+?)(?:\s+by\s+|\s+due\s+|\s+before\s+|$)", message, re.IGNORECASE)
        if action_match:
            args["title"] = action_match.group(1).strip()

        # Extract due date if present
        due_match = re.search(r"(?:by|due|before)\s+([\w\s\-\/]+?)(?:\s|$|,|\.)", message, re.IGNORECASE)
        if due_match:
            args["due_date"] = due_match.group(1).strip()

        return args

    def _extract_reminder_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments from reminder patterns"""
        args = {}

        task_match = re.search(r"(?:remind|schedule)\s+(?:me\s+to|us\s+to)\s+(.+)", message, re.IGNORECASE)
        if task_match:
            args["title"] = f"Reminder: {task_match.group(1).strip()}"

        return args

    def _extract_create_and_assign_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for creating and assigning a task in one command"""
        args = {}

        # Match "assign task: configure ssl to angel@example.com" type patterns
        match = re.search(r"(?:assign\s+task|create\s+task):\s*(.+?)\s+(?:to|for)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+)", message, re.IGNORECASE)
        if match:
            task_title = match.group(1).strip()
            assignee = match.group(2).strip()

            args["title"] = task_title
            args["assigned_to"] = [assignee]

            # Set default priority and category for SSL/infrastructure tasks
            if any(word in task_title.lower() for word in ['ssl', 'certificate', 'https', 'security', 'infrastructure']):
                args["priority"] = "High"
                args["category"] = "Infrastructure"

            # Extract any additional context from the message
            if "priority" in message.lower():
                priority_match = re.search(r"priority[:\s]*(\w+)", message, re.IGNORECASE)
                if priority_match:
                    args["priority"] = priority_match.group(1).title()

            if "category" in message.lower():
                category_match = re.search(r"category[:\s]*(\w+)", message, re.IGNORECASE)
                if category_match:
                    args["category"] = category_match.group(1).title()

        return args

    def _extract_assign_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for assigning an existing task"""
        args = {}

        # Enhanced pattern to capture emails and regular usernames
        assignee_match = re.search(r"(?:assign|give)\s+(?:task|this)\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+)", message, re.IGNORECASE)
        if assignee_match:
            args["assigned_to"] = [assignee_match.group(1)]

        # Try to extract task ID if mentioned
        task_match = re.search(r"task\s+(\w+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1)

        return args

    def _extract_assign_new_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for assigning a new task to someone"""
        args = {}

        # Enhanced pattern to capture emails and regular usernames
        match = re.search(r"(?:assign|delegate)\s+(.+?)\s+to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|\w+)", message, re.IGNORECASE)
        if match:
            args["title"] = match.group(1).strip()
            args["assigned_to"] = [match.group(2)]

        return args

    def _extract_person_should_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments from 'Person should do X' patterns"""
        args = {}

        match = re.search(r"(\w+)\s+(?:should|needs to|has to)\s+(.+)", message, re.IGNORECASE)
        if match:
            args["assigned_to"] = [match.group(1)]
            args["title"] = match.group(2).strip()

        return args

    def _extract_can_person_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments from 'Can person do X' patterns"""
        args = {}

        match = re.search(r"(?:can|could)\s+(\w+)\s+(?:please\s+)?(.+)", message, re.IGNORECASE)
        if match:
            args["assigned_to"] = [match.group(1)]
            args["title"] = match.group(2).strip()

        return args

    def _extract_in_progress_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for marking task as in progress"""
        args = {"percent_complete": 50}

        task_match = re.search(r"(?:mark|set)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:in\s+progress|started|working)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_percentage_update_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for updating task percentage"""
        args = {}

        match = re.search(r"(?:update|change)\s+(?:task\s+)?(.+?)\s+(?:to\s+)?(\d+)%", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["percent_complete"] = int(match.group(2))

        return args

    def _extract_blocked_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for marking task as blocked"""
        args = {"status": "blocked"}

        task_match = re.search(r"(?:set|mark)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:blocked|on hold|paused)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_due_date_update_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for updating task due date"""
        args = {}

        match = re.search(r"(?:set|change|update)\s+(?:due date|deadline)\s+(?:for\s+)?(?:task\s+)?(.+?)\s+(?:to\s+)?(.+)", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["due_date"] = match.group(2).strip()

        return args

    def _extract_task_due_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments from 'task X is due Y' patterns"""
        args = {}

        match = re.search(r"(?:task\s+)?(.+?)\s+(?:is\s+)?due\s+(.+)", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["due_date"] = match.group(2).strip()

        return args

    def _extract_extend_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for extending task deadline"""
        args = {}

        match = re.search(r"(?:extend|postpone|delay)\s+(?:task\s+)?(.+?)\s+(?:by\s+|to\s+)?(.+)", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["extend_by"] = match.group(2).strip()

        return args

    def _extract_high_priority_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for setting high priority"""
        args = {"priority": 1}

        task_match = re.search(r"(?:set|mark|make)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:high\s+priority|urgent|critical)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_low_priority_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for setting low priority"""
        args = {"priority": 9}

        task_match = re.search(r"(?:set|mark|make)\s+(?:task\s+)?(.+?)\s+(?:as\s+)?(?:low\s+priority|normal|routine)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_comment_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for adding comments"""
        args = {}

        match = re.search(r"(?:add|post|leave)\s+(?:a\s+)?comment\s+(?:on\s+)?(?:task\s+)?(.+?):\s*(.+)", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["comment"] = match.group(2).strip()

        return args

    def _extract_note_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for adding notes"""
        args = {}

        note_match = re.search(r"(?:note|comment|mention)\s+(?:that\s+)?(.+)", message, re.IGNORECASE)
        if note_match:
            args["comment"] = note_match.group(1).strip()

        return args

    def _extract_bulk_complete_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for bulk completing tasks"""
        args = {"action": "complete", "percent_complete": 100}

        plan_match = re.search(r"(?:complete|finish)\s+(?:all\s+)?(?:task|tasks?)\s+(?:in\s+)?(?:plan\s+)?(.+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1).strip()

        return args

    def _extract_bulk_assign_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for bulk assigning tasks"""
        args = {"action": "assign"}

        match = re.search(r"(?:assign|give)\s+(?:all\s+)?(?:task|tasks?)\s+(?:in\s+)?(?:plan\s+)?(.+?)\s+to\s+(\w+)", message, re.IGNORECASE)
        if match:
            args["plan_id"] = match.group(1).strip()
            args["assigned_to"] = [match.group(2)]

        return args

    def _extract_bulk_delete_completed_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for bulk deleting completed tasks"""
        return {"action": "delete", "filter": "completed"}

    def _extract_task_status_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for getting task status"""
        args = {}

        task_match = re.search(r"(?:what's|what is)\s+(?:the\s+)?(?:status|progress)\s+(?:of\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_task_count_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for counting tasks"""
        args = {"action": "count"}

        if "incomplete" in message.lower() or "remaining" in message.lower() or "left" in message.lower():
            args["status_filter"] = "incomplete"

        return args

    def _extract_plan_summary_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for getting plan summary"""
        args = {}

        plan_match = re.search(r"(?:show|give)\s+me\s+(?:an?\s+)?(?:overview|summary)\s+(?:of\s+)?(?:plan\s+)?(.+)", message, re.IGNORECASE)
        if plan_match:
            args["plan_id"] = plan_match.group(1).strip()

        return args

    def _extract_meeting_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for creating meeting tasks"""
        args = {"task_type": "meeting"}

        topic_match = re.search(r"(?:schedule|plan|set up)\s+(?:a\s+)?meeting\s+(?:about|for)\s+(.+)", message, re.IGNORECASE)
        if topic_match:
            args["title"] = f"Meeting: {topic_match.group(1).strip()}"

        return args

    def _extract_milestone_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for creating milestone tasks"""
        args = {"task_type": "milestone", "priority": 1}

        milestone_match = re.search(r"(?:create|add)\s+(?:a\s+)?milestone\s+(?:for\s+)?(.+)", message, re.IGNORECASE)
        if milestone_match:
            args["title"] = f"Milestone: {milestone_match.group(1).strip()}"

        return args

    def _extract_dependency_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for task dependencies"""
        args = {}

        match = re.search(r"(?:task\s+)?(.+?)\s+(?:depends on|requires|needs)\s+(.+)", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["depends_on"] = match.group(2).strip()

        return args

    def _extract_blocking_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for blocking tasks"""
        args = {}

        match = re.search(r"(?:block|prevent)\s+(?:task\s+)?(.+?)\s+(?:until|before)\s+(.+)", message, re.IGNORECASE)
        if match:
            args["task_id"] = match.group(1).strip()
            args["blocked_until"] = match.group(2).strip()

        return args

    # Plan context search argument extractors

    def _extract_plan_context_search_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for plan context search (e.g., 'look for it in project AI')"""
        args = {}

        # Extract plan name
        plan_match = re.search(r"(?:look for|find|search)\s+(?:it|task|the task)\s+(?:in|from)\s+(?:the\s+)?(?:project|plan)\s+(.+)", message, re.IGNORECASE)
        if plan_match:
            plan_name = plan_match.group(1).strip()
            args["query"] = plan_name
            # Store context for later use
            args["_context"] = "find_plan_for_task_search"
            args["_original_message"] = message

        return args

    def _extract_task_in_plan_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for task in plan search (e.g., 'find designated in project AI')"""
        args = {}

        # Extract task name and plan name
        match = re.search(r"(?:search|find)\s+(.+?)\s+(?:in|from)\s+(?:the\s+)?(?:project|plan)\s+(.+)", message, re.IGNORECASE)
        if match:
            task_name = match.group(1).strip()
            plan_name = match.group(2).strip()
            args["query"] = plan_name
            # Store context for later use
            args["_context"] = "find_plan_for_specific_task"
            args["_task_query"] = task_name
            args["_original_message"] = message

        return args

    # Document and attachment argument extractors

    def _extract_attachment_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for adding attachments"""
        args = {}

        task_match = re.search(r"(?:attach|upload|add)\s+(?:a\s+)?(?:file|document|attachment)\s+(?:to\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_file_to_task_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for attaching a specific file to a task"""
        args = {}

        match = re.search(r"(?:attach|upload)\s+(.+?)\s+(?:to\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if match:
            args["filename"] = match.group(1).strip()
            args["task_id"] = match.group(2).strip()

        return args

    def _extract_download_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for downloading attachments"""
        args = {}

        task_match = re.search(r"(?:download|get|retrieve)\s+(?:the\s+)?(?:file|document|attachment)\s+(?:from\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_list_attachments_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for listing attachments"""
        args = {}

        task_match = re.search(r"(?:show|list)\s+(?:all\s+)?(?:files|documents|attachments)\s+(?:for\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        return args

    def _extract_remove_attachment_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for removing attachments"""
        args = {}

        match = re.search(r"(?:remove|delete)\s+(?:the\s+)?(?:file|document|attachment)\s+(.+?)\s+(?:from\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if match:
            args["filename"] = match.group(1).strip()
            args["task_id"] = match.group(2).strip()

        return args

    def _extract_create_document_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for creating documents"""
        args = {}

        task_match = re.search(r"(?:create|generate)\s+(?:a\s+)?(?:document|file)\s+(?:for\s+)?(?:task\s+)?(.+)", message, re.IGNORECASE)
        if task_match:
            args["task_id"] = task_match.group(1).strip()

        # Extract document type if specified
        if "spreadsheet" in message.lower() or "excel" in message.lower():
            args["document_type"] = "spreadsheet"
        elif "presentation" in message.lower() or "powerpoint" in message.lower():
            args["document_type"] = "presentation"
        elif "document" in message.lower() or "word" in message.lower():
            args["document_type"] = "document"
        else:
            args["document_type"] = "document"

        return args

    def _extract_share_document_args(self, message: str) -> Dict[str, Any]:
        """Extract arguments for sharing documents"""
        args = {}

        match = re.search(r"(?:share|send)\s+(?:the\s+)?(?:file|document)\s+(.+?)\s+(?:with\s+)?(.+)", message, re.IGNORECASE)
        if match:
            args["filename"] = match.group(1).strip()
            args["share_with"] = match.group(2).strip()

        return args

    async def _handle_auth_queries(self, message: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Handle authentication-related queries"""
        message_lower = message.lower()

        if any(word in message_lower for word in ["login", "authenticate", "sign in", "connect"]):
            try:
                auth_status = await self.mcp_client.get_auth_status(user_id)

                if auth_status.get("authenticated"):
                    content = (
                        f"✅ You're already authenticated as {auth_status.get('user_name', 'Unknown User')}. "
                        "You can start managing your Planner tasks!"
                    )
                else:
                    login_url_result = await self.mcp_client.get_login_url(user_id)
                    login_url = login_url_result.get("login_url")

                    if login_url:
                        content = (
                            f"🔐 Please authenticate with Microsoft: [Login Here]({login_url})\n\n"
                            "After logging in, you'll be able to manage your Planner tasks through this chat interface."
                        )
                    else:
                        content = "❌ Unable to generate login URL. Please check the configuration."

                return self._create_chat_response(content=content, model="planner-assistant")

            except Exception as e:
                logger.error("Error handling auth query", error=str(e))
                return self._create_chat_response(
                    content="❌ Authentication service is currently unavailable. Please try again later.",
                    model="planner-assistant"
                )

        if any(word in message_lower for word in ["logout", "sign out", "disconnect"]):
            try:
                await self.mcp_client.logout(user_id)
                return self._create_chat_response(
                    content="✅ You've been logged out successfully.",
                    model="planner-assistant"
                )
            except Exception as e:
                logger.error("Error handling logout", error=str(e))
                return self._create_chat_response(
                    content="❌ Logout failed. Please try again.",
                    model="planner-assistant"
                )

        return None

    async def _handle_authentication_error(self, user_id: str, tool_name: str, error: str) -> Dict[str, Any]:
        """Handle authentication errors by providing login URL in chat"""
        try:
            # First check current auth status
            auth_status = await self.mcp_client.get_auth_status(user_id)

            if auth_status.get("authenticated"):
                # User appears authenticated but getting 403 - might be permissions issue
                content = (
                    f"🔐 **Authentication Issue Detected**\n\n"
                    f"Your session appears to be authenticated as {auth_status.get('user_name', 'Unknown User')}, "
                    f"but you're getting permission errors when trying to access Microsoft Planner.\n\n"
                    f"**Let's refresh your authentication:**\n"
                    f"1. Try logging out: type `logout`\n"
                    f"2. Then log back in: type `login`\n\n"
                    f"This will refresh your Microsoft Graph permissions and should resolve the access issue."
                )
            else:
                # User is not authenticated - get login URL
                login_url_result = await self.mcp_client.get_login_url(user_id)
                login_url = login_url_result.get("login_url")

                if login_url:
                    content = (
                        f"🔐 **Authentication Required**\n\n"
                        f"To access Microsoft Planner, please authenticate first:\n\n"
                        f"**[Click Here to Login with Microsoft]({login_url})**\n\n"
                        f"After completing the login process, you can retry your request. "
                        f"The authentication will allow access to your Microsoft Planner tasks and plans."
                    )
                else:
                    content = (
                        f"🔐 **Authentication Required**\n\n"
                        f"Unable to generate login URL. Please type `login` to get authentication link."
                    )

            return self._create_chat_response(content=content, model="planner-assistant")

        except Exception as e:
            logger.error("Error handling authentication error", error=str(e))
            content = (
                f"🔐 **Authentication Required**\n\n"
                f"There was an authentication error. Please type `login` to authenticate with Microsoft."
            )
            return self._create_chat_response(content=content, model="planner-assistant")

    async def _track_failed_request(self, message: str, user_id: str):
        """Track failed requests for learning and improvement"""
        failed_request = {
            "message": message.lower(),
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "message_length": len(message),
            "words": message.lower().split()
        }

        self.failed_requests.append(failed_request)

        # Keep only last 100 failed requests to avoid memory issues
        if len(self.failed_requests) > 100:
            self.failed_requests = self.failed_requests[-100:]

        # Log for analysis
        logger.warning("Failed pattern recognition",
                      message=message[:50],
                      word_count=len(message.split()),
                      user_id=user_id)

    async def _intelligent_fallback_matching(self, message: str) -> List[Dict[str, Any]]:
        """Intelligent fallback pattern matching using fuzzy logic and learned patterns"""
        message_lower = message.lower()
        tool_calls = []

        # Fuzzy matching for common task operations (removed AI patterns to avoid conflicts)
        fuzzy_patterns = [
            # Task listing variations
            (["task", "show", "list"], "search_tasks", {"query": ""}),
            (["plan", "show", "list"], "list_plans", {}),
            (["my", "task"], "get_my_tasks", {}),
            (["what", "task"], "search_tasks", {"query": ""}),
            (["which", "task"], "search_tasks", {"query": ""}),
        ]

        # Score fuzzy patterns based on word overlap
        best_match = None
        best_score = 0

        for keywords, tool_name, base_args in fuzzy_patterns:
            score = 0
            for keyword in keywords:
                if keyword in message_lower:
                    score += 1

            # Normalize score by pattern length
            normalized_score = score / len(keywords)

            if normalized_score > best_score and normalized_score >= 0.5:  # At least 50% match
                best_match = (tool_name, base_args)
                best_score = normalized_score

        if best_match:
            tool_name, args = best_match

            # Extract additional context for search queries
            if tool_name == "search_tasks" and not args.get("query"):
                # Try to extract search terms
                words = message_lower.split()
                potential_queries = []

                # Look for plan names or descriptive terms
                for word in words:
                    if word not in ["what", "are", "the", "in", "task", "tasks", "show", "list", "get"]:
                        potential_queries.append(word)

                if potential_queries:
                    args["query"] = potential_queries[0]

            tool_calls.append({
                "name": tool_name,
                "arguments": args,
                "confidence": best_score,
                "source": "fuzzy_match"
            })

            logger.info("Fuzzy pattern match found",
                       tool_name=tool_name,
                       confidence=best_score,
                       message=message[:50])

        return tool_calls

    async def _create_help_response(self, message: str, user_id: str) -> Dict[str, Any]:
        """Create a helpful response when no specific tool is detected"""

        # Check authentication first
        try:
            auth_status = await self.mcp_client.get_auth_status(user_id)
            if not auth_status.get("authenticated"):
                login_url_result = await self.mcp_client.get_login_url(user_id)
                login_url = login_url_result.get("login_url", "#")

                content = f"""🔐 **Authentication Required**

To use Microsoft Planner features, you need to authenticate first:
[Authenticate with Microsoft]({login_url})

After authentication, I can help you with:
- Creating and managing plans
- Adding and updating tasks
- Searching through your plans
- Assigning tasks to team members

Just ask me in natural language like "create a plan for Q4 marketing" or "show me all tasks in project alpha"."""

                return self._create_chat_response(content=content, model="planner-assistant")

        except Exception as e:
            logger.error("Error checking auth in help response", error=str(e))

        # Provide general help
        content = """🤖 **Microsoft Planner Assistant**

I can help you manage your Microsoft Planner with natural language! Here are some examples:

📋 **Plan Management:**
- "List all my plans"
- "Create a plan called 'Q4 Marketing Campaign'"
- "Search for plans about 'project alpha'"

✅ **Task Management:**
- "Show tasks in plan ABC123"
- "Create a task 'Review proposal' in plan ABC123"
- "Update task XYZ456 to 50% complete"
- "Mark task XYZ456 as completed"

🔍 **Search & Filter:**
- "Find plans containing 'marketing'"
- "Show incomplete tasks assigned to John"

Just describe what you want to do in natural language, and I'll help you manage your Planner tasks!"""

        return self._create_chat_response(content=content, model="planner-assistant")

    async def _format_tool_results(self, results: List[Dict[str, Any]], tool_calls: List[Dict[str, Any]]) -> str:
        """Format tool execution results into user-friendly content"""
        if not results:
            return "No results available."

        formatted_parts = []

        for i, (result, tool_call) in enumerate(zip(results, tool_calls)):
            tool_name = tool_call["name"]

            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error")

                # Check if this is an authentication error and provide login link
                if any(auth_indicator in error_msg.lower() for auth_indicator in [
                    "authentication required", "authenticate", "login", "unauthorized",
                    "no valid access token", "access token", "token", "401", "403"
                ]):
                    try:
                        # Get a login URL for the user
                        login_url_result = await self.mcp_client.get_login_url("default")
                        login_url = login_url_result.get("login_url")

                        if login_url:
                            auth_message = (
                                f"🔐 **Authentication Required**\n\n"
                                f"To access Microsoft Planner, please authenticate first:\n\n"
                                f"**[Click Here to Login with Microsoft]({login_url})**\n\n"
                                f"After completing the login process, you can retry your request."
                            )
                            formatted_parts.append(auth_message)
                        else:
                            formatted_parts.append(f"❌ **{tool_name}** failed: {error_msg}")
                    except Exception as e:
                        formatted_parts.append(f"❌ **{tool_name}** failed: {error_msg}")
                else:
                    formatted_parts.append(f"❌ **{tool_name}** failed: {error_msg}")
                continue

            content = result.get("content", {})

            if tool_name == "list_plans":
                formatted_parts.append(self._format_plans_list(content))
            elif tool_name == "create_plan":
                formatted_parts.append(self._format_plan_created(content))
            elif tool_name == "list_tasks":
                formatted_parts.append(self._format_tasks_list(content))
            elif tool_name == "get_my_tasks":
                formatted_parts.append(self._format_my_tasks_list(content))
            elif tool_name == "create_task":
                formatted_parts.append(self._format_task_created(content))
            elif tool_name == "update_task":
                formatted_parts.append(self._format_task_updated(content))
            elif tool_name == "search_plans":
                formatted_parts.append(self._format_search_results(content))
            elif tool_name == "search_tasks":
                formatted_parts.append(self._format_search_tasks_results(content))
            elif tool_name == "delete_task":
                formatted_parts.append(self._format_task_deleted(content))
            elif tool_name == "get_task_details":
                formatted_parts.append(self._format_task_details(content))
            elif tool_name == "add_task_comment":
                formatted_parts.append(self._format_comment_added(content))
            elif tool_name == "add_task_checklist":
                formatted_parts.append(self._format_checklist_added(content))
            elif tool_name == "update_task_checklist":
                formatted_parts.append(self._format_checklist_updated(content))
            elif tool_name == "get_task_by_position":
                formatted_parts.append(self._format_task_details(content))
            elif tool_name == "get_next_task":
                formatted_parts.append(self._format_next_task(content))
            elif tool_name == "list_buckets":
                formatted_parts.append(self._format_buckets_list(content))
            elif tool_name == "create_bucket":
                formatted_parts.append(self._format_bucket_created(content))
            elif tool_name == "update_bucket":
                formatted_parts.append(self._format_bucket_updated(content))
            elif tool_name == "delete_bucket":
                formatted_parts.append(self._format_bucket_deleted(content))
            elif tool_name == "create_tasks_from_document":
                formatted_parts.append(self._format_tasks_from_document(content))
            elif tool_name == "search_documents":
                formatted_parts.append(self._format_documents_search(content))
            elif tool_name == "analyze_project_relationships":
                formatted_parts.append(self._format_relationships_analysis(content))
            elif tool_name == "update_knowledge_graph":
                formatted_parts.append(self._format_knowledge_graph_update(content))
            elif tool_name == "process_natural_language":
                formatted_parts.append(self._format_natural_language_response(content))
            else:
                # Generic formatting
                formatted_parts.append(f"✅ **{tool_name}** completed successfully")

        return "\n\n".join(formatted_parts)

    def _format_plans_list(self, content: Dict[str, Any]) -> str:
        """Format plans list"""
        plans = content.get("plans", [])
        total_count = content.get("total_count", len(plans))

        if not plans:
            return "📋 No plans found."

        result = f"📋 **Found {total_count} plan(s):**\n\n"

        for plan in plans[:10]:  # Limit to 10 plans
            title = plan.get("title", "Untitled")
            plan_id = plan.get("id", "Unknown")
            created = plan.get("createdDateTime", "")
            if created:
                try:
                    created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    created_str = created_date.strftime("%Y-%m-%d")
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug("Failed to parse created date", created=created, error=str(e))
                    created_str = created[:10]  # Take first 10 chars
            else:
                created_str = "Unknown"

            result += f"• **{title}** (ID: `{plan_id}`) - Created: {created_str}\n"

        if len(plans) > 10:
            result += f"\n... and {len(plans) - 10} more plans"

        return result

    def _format_plan_created(self, content: Dict[str, Any]) -> str:
        """Format plan creation result"""
        title = content.get("title", "Untitled")
        plan_id = content.get("id", "Unknown")
        return (
            f"✅ **Plan created successfully!**\n\n📋 **{title}** (ID: `{plan_id}`)\n\n"
            "You can now add tasks to this plan!"
        )

    def _format_tasks_list(self, content: Dict[str, Any]) -> str:
        """Format tasks list with enhanced layout"""
        tasks = content.get("tasks", [])
        total_count = content.get("total_count", len(tasks))
        plan_id = content.get("plan_id", "Unknown")
        plan_title = content.get("plan_title", "Unknown Plan")

        if not tasks:
            return f"✅ No tasks found in plan **{plan_title}** (`{plan_id}`)."

        result = f"✅ **Found {total_count} task(s) in plan {plan_title}:**\n\n"

        for i, task in enumerate(tasks[:8]):  # Limit to 8 tasks for readability
            title = task.get("title", "Untitled")
            task_id = task.get("id", "Unknown")
            percent_complete = task.get("percentComplete", 0)
            due_date = task.get("dueDateTime", "")
            priority = task.get("priority", 5)
            assigned_to = task.get("assignments", {})

            # Priority and status indicators
            priority_emoji = self._get_priority_emoji(priority)
            status_emoji = "✅" if percent_complete == 100 else "🔄" if percent_complete > 0 else "⏳"

            # Format assignee
            assignee_text = self._format_assignees(assigned_to)
            if not assignee_text or assignee_text == "👤 Unassigned":
                assignee_text = "Unassigned"
            else:
                assignee_text = assignee_text.replace("👤 ", "").replace("👥 ", "")

            # Format due date
            due_str = self._format_due_date(due_date)
            if due_str == "📅 No due date":
                due_str = "No due date"
            else:
                due_str = due_str.replace("📅 ", "").replace("⚠️ ", "⚠️ ")

            # Modern card format optimized for HTML/OpenWebUI
            result += f"<div style='background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-left: 4px solid {self._get_priority_color(priority)}; border-radius: 8px; padding: 16px; margin: 8px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>\n"
            result += f"  <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>\n"
            result += f"    <span style='font-weight: 600; color: #2c3e50;'>{priority_emoji} {title}</span>\n"
            result += f"    <span style='background: {self._get_status_color(percent_complete)}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;'>{status_emoji} {percent_complete}%</span>\n"
            result += f"  </div>\n"
            result += f"  <div style='display: flex; justify-content: space-between; font-size: 14px; color: #6c757d;'>\n"
            result += f"    <span>👤 {assignee_text}</span>\n"
            result += f"    <span>📅 {due_str}</span>\n"
            result += f"  </div>\n"
            result += f"  <div style='margin-top: 8px; font-size: 12px; color: #868e96; font-family: monospace;'>\n"
            result += f"    🔗 {task_id}\n"
            result += f"  </div>\n"
            result += f"</div>\n"

            if i < len(tasks[:8]) - 1:  # Add spacing between cards except for the last one
                result += "\n"

        if len(tasks) > 8:
            result += f"\n... and {len(tasks) - 8} more tasks. Use 'get task details [ID]' for more information."

        return result

    def _format_my_tasks_list(self, content: Dict[str, Any]) -> str:
        """Format my tasks list"""
        tasks = content.get("tasks", [])
        total_count = content.get("total_count", len(tasks))

        if not tasks:
            return "✅ **No tasks assigned to you** - You're all caught up! 🎉"

        result = f"✅ **You have {total_count} task(s) assigned:**\n\n"

        for task in tasks[:15]:  # Show more tasks for personal view
            title = task.get("title", "Untitled")
            task_id = task.get("id", "Unknown")
            percent_complete = task.get("percentComplete", 0)
            due_date = task.get("dueDateTime", "")
            plan_title = task.get("planTitle", "Unknown Plan")

            status_emoji = "✅" if percent_complete == 100 else "🔄" if percent_complete > 0 else "⏳"

            due_str = ""
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                    due_str = f" - 📅 Due: {due_dt.strftime('%Y-%m-%d')}"
                except (ValueError, TypeError, AttributeError) as e:
                    logger.debug("Failed to parse due date", due_date=due_date, error=str(e))

            result += f"{status_emoji} **{title}** ({percent_complete}%)\n"
            result += f"   📋 Plan: {plan_title} | ID: `{task_id}`{due_str}\n\n"

        if len(tasks) > 15:
            result += f"... and {len(tasks) - 15} more tasks"

        return result

    def _format_task_created(self, content: Dict[str, Any]) -> str:
        """Format task creation result"""
        title = content.get("title", "Untitled")
        task_id = content.get("id", "Unknown")
        plan_id = content.get("planId", "Unknown")
        return f"✅ **Task created successfully!**\n\n📝 **{title}** (ID: `{task_id}`)\nIn plan: `{plan_id}`"

    def _format_task_updated(self, content: Dict[str, Any]) -> str:
        """Format task update result"""
        title = content.get("title", "Task")
        task_id = content.get("id", "Unknown")
        percent_complete = content.get("percentComplete", 0)

        status = "✅ Completed" if percent_complete == 100 else f"🔄 {percent_complete}% complete"

        return f"✅ **Task updated successfully!**\n\n📝 **{title}** (ID: `{task_id}`)\nStatus: {status}"

    def _format_search_results(self, content: Dict[str, Any]) -> str:
        """Format search results"""
        plans = content.get("plans", [])
        query = content.get("query", "")
        total_found = content.get("total_found", len(plans))

        if not plans:
            return f"🔍 No plans found matching '{query}'."

        result = f"🔍 **Found {total_found} plan(s) matching '{query}':**\n\n"

        for plan in plans:
            title = plan.get("title", "Untitled")
            plan_id = plan.get("id", "Unknown")
            result += f"• **{title}** (ID: `{plan_id}`)\n"

        # If there's only one plan and it's an AI-related search, provide next steps
        if len(plans) == 1 and ("ai" in query.lower() or "artificial" in query.lower()):
            plan = plans[0]
            plan_id = plan.get("id", "Unknown")
            result += f"\n💡 **To search for the 'designated' task in this plan, I can run:**\n"
            result += f"```\nSearch for 'designated' in plan {plan_id}\n```\n"
            result += f"Would you like me to search for tasks in **{plan.get('title', 'this plan')}**?"

        return result

    def _format_search_tasks_results(self, content: Dict[str, Any]) -> str:
        """Format search tasks results with clean text layout"""
        tasks = content.get("tasks", [])
        query = content.get("query", "")
        total_found = content.get("total_found", len(tasks))

        if not tasks:
            return f"🔍 No tasks found matching '{query}'."

        result = f"🔍 **Found {total_found} task(s) matching '{query}':**\n\n"

        for i, task in enumerate(tasks[:5]):  # Limit to 5 for readability
            title = task.get("title", "Untitled")
            task_id = task.get("id", "Unknown")
            plan_title = task.get("plan_title", "Unknown Plan")
            due_date = task.get("dueDateTime")
            percent_complete = task.get("percentComplete", 0)
            priority = task.get("priority", 5)
            assigned_to = task.get("assignments", {})
            bucket_name = task.get("bucketName", "Default")

            # Clean text format for task cards
            priority_emoji = self._get_priority_emoji(priority)
            priority_text = self._get_priority_text(priority)
            ai_tag = " [AI]" if "ai" in title.lower() or "designated" in title.lower() else ""

            # Task header
            result += f"**{priority_emoji} {title.upper()}{ai_tag}** ({priority_text} Priority)\n"

            # Task details in clean format
            progress_text = f"📊 {percent_complete}%"
            assignee_text = self._format_assignees(assigned_to) or "👤 Unassigned"
            due_text = self._format_due_date(due_date)
            bucket_text = f"🏷️ {bucket_name}"

            result += f"• Progress: {progress_text}\n"
            result += f"• Assignee: {assignee_text}\n"
            result += f"• Due Date: {due_text}\n"
            result += f"• Bucket: {bucket_text}\n"
            result += f"• Plan: 📋 **{plan_title}**\n"
            result += f"• Task ID: 🔗 `{task_id}`\n"

            if i < len(tasks[:5]) - 1:  # Add spacing between tasks
                result += "\n---\n\n"

        if len(tasks) > 5:
            result += f"\n\n... and {len(tasks) - 5} more tasks. Use task ID to get details on specific tasks."

        return result

    def _create_chat_response(
        self,
        content: str,
        model: str = "planner-assistant",
        conversation_id: str = None
    ) -> Dict[str, Any]:
        """Create OpenAI-compatible chat completion response"""
        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        timestamp = int(datetime.now().timestamp())

        # Handle None content
        if content is None:
            content = "❌ Error: No response content available"

        # Calculate token usage safely
        content_str = str(content)
        token_count = len(content_str.split()) if content_str else 0

        return {
            "id": response_id,
            "object": "chat.completion",
            "created": timestamp,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content_str
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": token_count,
                "total_tokens": token_count
            }
        }

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response"""
        return self._create_chat_response(
            content=f"❌ Error: {error_message}",
            model="planner-assistant"
        )

    # Enhanced UX Formatting Methods

    def _format_task_details(self, content: Dict[str, Any]) -> str:
        """Format detailed task information with enhanced card-based layout"""
        task = content.get("task", {})
        if not task:
            return "❌ **Task not found or no details available**"

        title = task.get("title", "Untitled Task")
        task_id = task.get("id", "Unknown")
        percent_complete = task.get("percentComplete", 0)
        due_date = task.get("dueDateTime")
        assigned_to = task.get("assignments", {})
        priority = task.get("priority", 5)
        bucket_name = task.get("bucketName", "Unassigned")
        plan_title = task.get("planTitle", "Unknown Plan")
        created_date = task.get("createdDateTime")
        checklist = task.get("checklist", {})
        comments = task.get("conversations", [])
        description = task.get("description", "")

        # Modern detailed task card for HTML/OpenWebUI
        result = f"<div style='background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); border: 1px solid #dee2e6; border-radius: 16px; padding: 24px; margin: 16px 0; box-shadow: 0 8px 24px rgba(0,0,0,0.1); max-width: 800px;'>\n"

        # Header with title and priority
        priority_emoji = self._get_priority_emoji(priority)
        ai_tag = " [AI]" if "ai" in title.lower() or "artificial" in title.lower() else ""

        result += f"  <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 2px solid #e9ecef;'>\n"
        result += f"    <h2 style='margin: 0; color: #2c3e50; font-size: 24px; font-weight: 700;'>{priority_emoji} {title.upper()}{ai_tag}</h2>\n"
        result += f"    <span style='background: {self._get_priority_color(priority)}; color: white; padding: 8px 16px; border-radius: 25px; font-size: 14px; font-weight: 600; text-transform: uppercase;'>{self._get_priority_text(priority)}</span>\n"
        result += f"  </div>\n"

        # Key metrics grid with enhanced styling
        result += f"  <div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px;'>\n"

        progress_text = f"📊 {percent_complete}%"
        assignee_text = self._format_assignees(assigned_to) or "👤 Unassigned"
        due_text = self._format_due_date(due_date)
        bucket_text = f"🏷️ {bucket_name}"

        # Progress card
        result += f"    <div style='background: {self._get_status_color(percent_complete)}; color: white; padding: 16px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);'>\n"
        result += f"      <div style='font-size: 24px; font-weight: 700; margin-bottom: 4px;'>{percent_complete}%</div>\n"
        result += f"      <div style='font-size: 12px; opacity: 0.9;'>📊 Progress</div>\n"
        result += f"    </div>\n"

        # Assignee card
        result += f"    <div style='background: #6c757d; color: white; padding: 16px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);'>\n"
        result += f"      <div style='font-size: 16px; font-weight: 600; margin-bottom: 4px;'>{assignee_text}</div>\n"
        result += f"      <div style='font-size: 12px; opacity: 0.9;'>👤 Assignee</div>\n"
        result += f"    </div>\n"

        # Due date card
        result += f"    <div style='background: #17a2b8; color: white; padding: 16px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);'>\n"
        result += f"      <div style='font-size: 16px; font-weight: 600; margin-bottom: 4px;'>{due_text}</div>\n"
        result += f"      <div style='font-size: 12px; opacity: 0.9;'>📅 Due Date</div>\n"
        result += f"    </div>\n"

        # Bucket card
        result += f"    <div style='background: #28a745; color: white; padding: 16px; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1);'>\n"
        result += f"      <div style='font-size: 16px; font-weight: 600; margin-bottom: 4px;'>{bucket_text}</div>\n"
        result += f"      <div style='font-size: 12px; opacity: 0.9;'>🏷️ Bucket</div>\n"
        result += f"    </div>\n"
        result += f"  </div>\n"

        # Description section
        result += f"  <div style='background: #f8f9fa; border-radius: 12px; padding: 20px; margin-bottom: 20px;'>\n"
        result += f"    <h3 style='margin: 0 0 12px 0; color: #495057; font-size: 16px; display: flex; align-items: center;'>\n"
        result += f"      📝 <span style='margin-left: 8px;'>Description</span>\n"
        result += f"    </h3>\n"
        if description:
            result += f"    <p style='margin: 0; color: #6c757d; line-height: 1.6;'>{description}</p>\n"
        else:
            result += f"    <p style='margin: 0; color: #adb5bd; font-style: italic;'>No description provided</p>\n"
        result += f"  </div>\n"

        # Checklist section
        result += f"  <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;'>\n"
        result += f"    <div style='background: #e3f2fd; border-radius: 12px; padding: 20px;'>\n"
        result += f"      <h3 style='margin: 0 0 12px 0; color: #1976d2; font-size: 16px; display: flex; align-items: center;'>\n"
        result += f"        ☑️ <span style='margin-left: 8px;'>Checklist</span>\n"
        result += f"      </h3>\n"
        if checklist:
            checklist_items = checklist.get("items", [])
            completed_items = sum(1 for item in checklist_items if item.get("isChecked", False))
            total_items = len(checklist_items)
            completion_rate = (completed_items / total_items * 100) if total_items > 0 else 0
            result += f"      <div style='display: flex; justify-content: space-between; align-items: center;'>\n"
            result += f"        <span style='color: #1976d2; font-weight: 600;'>{completed_items}/{total_items} items complete</span>\n"
            result += f"        <span style='background: #1976d2; color: white; padding: 4px 8px; border-radius: 8px; font-size: 12px;'>{completion_rate:.0f}%</span>\n"
            result += f"      </div>\n"
        else:
            result += f"      <p style='margin: 0; color: #64b5f6; font-style: italic;'>No checklist items</p>\n"
        result += f"    </div>\n"

        # Comments section
        comment_count = len(comments)
        result += f"    <div style='background: #fff3e0; border-radius: 12px; padding: 20px;'>\n"
        result += f"      <h3 style='margin: 0 0 12px 0; color: #f57c00; font-size: 16px; display: flex; align-items: center;'>\n"
        result += f"        💬 <span style='margin-left: 8px;'>Comments</span>\n"
        result += f"      </h3>\n"
        if comment_count > 0:
            latest_comment = comments[-1] if comments else {}
            comment_preview = latest_comment.get("preview", "No preview")[:30] + "..."
            time_ago = self._format_time_ago(latest_comment.get("lastModifiedDateTime"))
            result += f"      <div style='color: #f57c00; font-weight: 600; margin-bottom: 4px;'>{comment_count} comment{'s' if comment_count != 1 else ''}</div>\n"
            result += f"      <div style='color: #ff9800; font-size: 14px;'>Latest: \"{comment_preview}\"</div>\n"
            result += f"      <div style='color: #ffb74d; font-size: 12px; margin-top: 4px;'>{time_ago}</div>\n"
        else:
            result += f"      <p style='margin: 0; color: #ffb74d; font-style: italic;'>No comments yet</p>\n"
        result += f"    </div>\n"
        result += f"  </div>\n"

        # Additional metadata
        if created_date:
            created_str = self._format_created_date(created_date)
            result += f"│ 📅 **Created:** {created_str:<50} │\n"

        # Task ID (always last)
        result += f"│ 🔗 ID: {task_id:<58} │\n"
        result += "└─" + "─" * 65 + "┘"

        return result

    def _get_priority_emoji(self, priority: int) -> str:
        """Get emoji based on priority level"""
        if priority <= 2:
            return "🔴"  # High priority
        elif priority <= 5:
            return "🟡"  # Medium priority
        else:
            return "🟢"  # Low priority

    def _get_priority_text(self, priority: int) -> str:
        """Get priority text"""
        if priority <= 2:
            return "High"
        elif priority <= 5:
            return "Med"
        else:
            return "Low"

    def _format_assignees(self, assignments: Dict[str, Any]) -> str:
        """Format assignee information"""
        if not assignments:
            return "👤 Unassigned"

        assignee_names = []
        for assignment_id, assignment_info in assignments.items():
            if isinstance(assignment_info, dict):
                user_info = assignment_info.get("assignedBy", {}).get("user", {})
                name = user_info.get("displayName", "Unknown")
                if name and isinstance(name, str):
                    assignee_names.append(name.split()[0])  # First name only
                else:
                    assignee_names.append("Unknown")

        if not assignee_names:
            return "👤 Unassigned"
        elif len(assignee_names) == 1:
            return f"👤 {assignee_names[0]}"
        else:
            return f"👥 {assignee_names[0]}+{len(assignee_names)-1}"

    def _format_due_date(self, due_date: str) -> str:
        """Format due date with appropriate emoji and text"""
        if not due_date:
            return "📅 No due date"

        try:
            due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
            now = datetime.now(due_dt.tzinfo)
            days_diff = (due_dt.date() - now.date()).days

            if days_diff < 0:
                return f"⚠️ Overdue {abs(days_diff)}d"
            elif days_diff == 0:
                return "📅 Due Today"
            elif days_diff == 1:
                return "📅 Due Tomorrow"
            elif days_diff <= 7:
                return f"📅 Due in {days_diff}d"
            else:
                return f"📅 Due {due_dt.strftime('%b %d')}"
        except (ValueError, TypeError):
            return f"📅 Due: {due_date[:10]}"

    def _format_created_date(self, created_date: str) -> str:
        """Format creation date"""
        if not created_date:
            return "Unknown"

        try:
            created_dt = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
            return created_dt.strftime("%B %d, %Y at %I:%M %p")
        except (ValueError, TypeError):
            return created_date[:10]

    def _format_time_ago(self, timestamp: str) -> str:
        """Format time ago from timestamp"""
        if not timestamp:
            return "unknown time"

        try:
            ts_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            now = datetime.now(ts_dt.tzinfo)
            diff = now - ts_dt

            if diff.days > 0:
                return f"{diff.days}d ago"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f"{hours}h ago"
            elif diff.seconds > 60:
                minutes = diff.seconds // 60
                return f"{minutes}m ago"
            else:
                return "just now"
        except (ValueError, TypeError):
            return "unknown"

    def _get_checklist_preview(self, checklist_items: List[Dict[str, Any]]) -> str:
        """Get a preview of checklist items"""
        if not checklist_items:
            return "No items"

        completed = [item for item in checklist_items if item.get("isChecked", False)]
        if len(completed) == len(checklist_items):
            return "All complete ✓"
        elif completed:
            return f"Partial: {completed[0].get('title', 'Item')[:15]}..."
        else:
            return f"Pending: {checklist_items[0].get('title', 'Item')[:15]}..."

    def _get_priority_color(self, priority: int) -> str:
        """Get color based on priority level"""
        if priority <= 2:
            return "#dc3545"  # High priority - red
        elif priority <= 4:
            return "#fd7e14"  # Medium priority - orange
        else:
            return "#28a745"  # Low priority - green

    def _get_status_color(self, percent_complete: int) -> str:
        """Get color based on completion percentage"""
        if percent_complete == 0:
            return "#6c757d"  # Not started - gray
        elif percent_complete < 50:
            return "#fd7e14"  # In progress - orange
        elif percent_complete < 100:
            return "#17a2b8"  # Nearly complete - blue
        else:
            return "#28a745"  # Complete - green

    def _wrap_text(self, text: str, width: int) -> List[str]:
        """Wrap text to fit within specified width"""
        if not text or not isinstance(text, str):
            return [""]

        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if len(current_line + " " + word) <= width:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word if len(word) <= width else word[:width-3] + "..."

        if current_line:
            lines.append(current_line)

        return lines if lines else [""]

    def _format_next_task(self, content: Dict[str, Any]) -> str:
        """Format next task recommendation"""
        task = content.get("task", {})
        if not task:
            return "🎯 **No next task found** - You're all caught up! 🎉"

        title = task.get("title", "Untitled")
        task_id = task.get("id", "Unknown")
        due_date = task.get("dueDateTime")
        priority = task.get("priority", 5)
        plan_title = task.get("planTitle", "Unknown Plan")

        priority_emoji = self._get_priority_emoji(priority)
        due_info = self._format_due_date(due_date)

        result = f"🎯 **Next Recommended Task:**\n\n"
        result += f"{priority_emoji} **{title}**\n"
        result += f"📋 Plan: {plan_title}\n"
        result += f"{due_info}\n"
        result += f"🔗 ID: `{task_id}`\n\n"
        result += "💡 Ready to get started? Just say 'mark this task as in progress' or update its percentage!"

        return result

    def _format_comment_added(self, content: Dict[str, Any]) -> str:
        """Format comment addition confirmation"""
        comment = content.get("comment", {})
        task_title = content.get("task_title", "Task")

        return f"💬 **Comment added successfully!**\n\n📝 Added to: **{task_title}**\n📄 Comment: \"{comment.get('content', 'No content')}\""

    def _format_checklist_added(self, content: Dict[str, Any]) -> str:
        """Format checklist addition confirmation"""
        task_title = content.get("task_title", "Task")
        items_count = content.get("items_added", 0)

        return f"☑️ **Checklist added successfully!**\n\n📝 Added to: **{task_title}**\n📋 Items added: {items_count}"

    def _format_checklist_updated(self, content: Dict[str, Any]) -> str:
        """Format checklist update confirmation"""
        task_title = content.get("task_title", "Task")
        completed_items = content.get("completed_items", 0)
        total_items = content.get("total_items", 0)

        return f"☑️ **Checklist updated successfully!**\n\n📝 Task: **{task_title}**\n📊 Progress: {completed_items}/{total_items} items completed"

    def _format_task_deleted(self, content: Dict[str, Any]) -> str:
        """Format task deletion confirmation"""
        task_title = content.get("title", "Task")
        task_id = content.get("id", "Unknown")

        return f"🗑️ **Task deleted successfully!**\n\n📝 **{task_title}** (ID: `{task_id}`) has been permanently removed."

    def _format_buckets_list(self, content: Dict[str, Any]) -> str:
        """Format buckets list"""
        buckets = content.get("buckets", [])
        plan_title = content.get("plan_title", "Unknown Plan")

        if not buckets:
            return f"🏷️ No buckets found in plan **{plan_title}**."

        result = f"🏷️ **Buckets in {plan_title}:**\n\n"

        for bucket in buckets:
            name = bucket.get("name", "Untitled Bucket")
            bucket_id = bucket.get("id", "Unknown")
            task_count = bucket.get("task_count", 0)

            result += f"📦 **{name}** ({task_count} tasks) - ID: `{bucket_id}`\n"

        return result

    def _format_bucket_created(self, content: Dict[str, Any]) -> str:
        """Format bucket creation confirmation"""
        name = content.get("name", "Untitled")
        bucket_id = content.get("id", "Unknown")
        plan_title = content.get("plan_title", "Unknown Plan")

        return f"📦 **Bucket created successfully!**\n\n🏷️ **{name}** (ID: `{bucket_id}`)\nIn plan: **{plan_title}**"

    def _format_bucket_updated(self, content: Dict[str, Any]) -> str:
        """Format bucket update confirmation"""
        name = content.get("name", "Bucket")
        bucket_id = content.get("id", "Unknown")

        return f"📦 **Bucket updated successfully!**\n\n🏷️ **{name}** (ID: `{bucket_id}`)"

    def _format_bucket_deleted(self, content: Dict[str, Any]) -> str:
        """Format bucket deletion confirmation"""
        name = content.get("name", "Bucket")
        bucket_id = content.get("id", "Unknown")

        return f"🗑️ **Bucket deleted successfully!**\n\n🏷️ **{name}** (ID: `{bucket_id}`) has been permanently removed."

    def _format_tasks_from_document(self, content: Dict[str, Any]) -> str:
        """Format tasks created from document"""
        tasks_created = content.get("tasks_created", 0)
        document_name = content.get("document_name", "document")
        plan_title = content.get("plan_title", "Unknown Plan")

        return f"📄 **Tasks created from document!**\n\n📝 Document: **{document_name}**\n📋 Plan: **{plan_title}**\n✅ Created: {tasks_created} tasks"

    def _format_documents_search(self, content: Dict[str, Any]) -> str:
        """Format document search results"""
        documents = content.get("documents", [])
        query = content.get("query", "")

        if not documents:
            return f"📄 No documents found matching '{query}'."

        result = f"📄 **Found {len(documents)} document(s) matching '{query}':**\n\n"

        for doc in documents:
            title = doc.get("title", "Untitled")
            doc_type = doc.get("type", "Unknown")
            modified = doc.get("lastModified", "")

            result += f"📄 **{title}** ({doc_type})\n"
            if modified:
                result += f"   Last modified: {modified}\n"
            result += "\n"

        return result

    def _format_relationships_analysis(self, content: Dict[str, Any]) -> str:
        """Format project relationships analysis"""
        relationships = content.get("relationships", [])
        analysis = content.get("analysis", "No analysis available")

        result = f"🔗 **Project Relationships Analysis:**\n\n{analysis}\n\n"

        if relationships:
            result += "**Key Relationships:**\n"
            for rel in relationships[:5]:  # Show top 5
                result += f"• {rel.get('description', 'Unknown relationship')}\n"

        return result

    def _format_knowledge_graph_update(self, content: Dict[str, Any]) -> str:
        """Format knowledge graph update confirmation"""
        entities_added = content.get("entities_added", 0)
        relationships_added = content.get("relationships_added", 0)

        return f"🧠 **Knowledge graph updated!**\n\n📊 Entities added: {entities_added}\n🔗 Relationships added: {relationships_added}"

    def _format_natural_language_response(self, content: Dict[str, Any]) -> str:
        """Format natural language processing response"""
        intent = content.get("intent", {})
        confidence = content.get("confidence", 0)
        suggested_actions = content.get("suggested_actions", [])

        result = f"🤖 **Natural Language Analysis:**\n\n"
        result += f"🎯 Intent: {intent.get('intent', 'Unknown')} (Confidence: {confidence:.1%})\n\n"

        if suggested_actions:
            result += "**Suggested Actions:**\n"
            for action in suggested_actions[:3]:  # Show top 3
                tool = action.get("tool", "Unknown")
                confidence = action.get("confidence", 0)
                result += f"• {tool} (Confidence: {confidence:.1%})\n"

        return result
