"""
Natural Language Error Handling and User-Friendly Messages
Story 1.3 Task 6: Convert technical errors into conversational responses
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ErrorContext:
    """Context information about an error"""
    error_type: str
    error_code: Optional[str]
    original_message: str
    user_input: str
    intent: Optional[str]
    entities: Dict[str, Any]
    user_id: str
    session_id: str


@dataclass
class NaturalLanguageResponse:
    """Natural language response to an error"""
    message: str
    tone: str  # 'helpful', 'apologetic', 'informative', 'encouraging'
    suggestions: List[str]
    retry_possible: bool
    escalation_needed: bool


class NLErrorHandler:
    """
    Converts technical errors into natural, user-friendly language
    Provides helpful suggestions and maintains conversational tone
    """

    def __init__(self):
        # Error pattern mappings to natural language
        self.error_patterns = {
            # Authentication and Authorization
            "authentication": {
                "patterns": [
                    r"authentication.*failed",
                    r"invalid.*token",
                    r"unauthorized",
                    r"access.*denied",
                    r"401",
                    r"403"
                ],
                "responses": [
                    "I'm having trouble accessing your Microsoft Planner account. Let's get you reconnected.",
                    "It looks like your authentication has expired. You'll need to sign in again.",
                    "I don't have permission to access your planner. Please check your account permissions."
                ],
                "suggestions": [
                    "Try signing out and signing back in",
                    "Check that you've granted the necessary permissions",
                    "Contact your IT administrator if you're using a work account"
                ],
                "tone": "helpful"
            },

            # Network and Connectivity
            "network": {
                "patterns": [
                    r"connection.*timeout",
                    r"network.*error",
                    r"request.*failed",
                    r"timeout",
                    r"503",
                    r"502",
                    r"504"
                ],
                "responses": [
                    "I'm having trouble connecting to Microsoft Planner right now.",
                    "There seems to be a network issue. The service might be temporarily unavailable.",
                    "I couldn't reach the Planner service. This might be a temporary connectivity issue."
                ],
                "suggestions": [
                    "Please try again in a few moments",
                    "Check your internet connection",
                    "If the problem persists, Microsoft's services might be experiencing issues"
                ],
                "tone": "apologetic"
            },

            # Rate Limiting
            "rate_limit": {
                "patterns": [
                    r"rate.*limit.*exceeded",
                    r"too.*many.*requests",
                    r"throttle",
                    r"429"
                ],
                "responses": [
                    "I'm being asked to slow down a bit. We've made quite a few requests recently.",
                    "We've hit the rate limit for API calls. I need to take a short break.",
                    "Microsoft's API is asking us to wait a moment before making more requests."
                ],
                "suggestions": [
                    "Let's wait about a minute and try again",
                    "You can continue with other tasks while we wait",
                    "This helps ensure the service stays fast for everyone"
                ],
                "tone": "informative"
            },

            # Resource Not Found
            "not_found": {
                "patterns": [
                    r"not.*found",
                    r"does.*not.*exist",
                    r"404",
                    r"invalid.*id",
                    r"resource.*not.*found"
                ],
                "responses": [
                    "I couldn't find what you're looking for.",
                    "That item doesn't seem to exist anymore, or I might have the wrong information.",
                    "The task or plan you mentioned isn't available. It might have been moved or deleted."
                ],
                "suggestions": [
                    "Double-check the name or try searching for it",
                    "It might have been moved to a different plan",
                    "Try listing all tasks to see what's available"
                ],
                "tone": "helpful"
            },

            # Validation Errors
            "validation": {
                "patterns": [
                    r"validation.*failed",
                    r"invalid.*format",
                    r"required.*field",
                    r"bad.*request",
                    r"400"
                ],
                "responses": [
                    "There's something about your request that needs to be fixed.",
                    "I understand what you want to do, but there's a formatting issue with the information provided.",
                    "Some required information is missing or in the wrong format."
                ],
                "suggestions": [
                    "Let me help you fix the format",
                    "Please check the information you provided",
                    "I can guide you through the correct format"
                ],
                "tone": "helpful"
            },

            # Processing Errors
            "processing": {
                "patterns": [
                    r"internal.*error",
                    r"processing.*failed",
                    r"unexpected.*error",
                    r"500",
                    r"server.*error"
                ],
                "responses": [
                    "Something unexpected happened while I was processing your request.",
                    "I ran into an internal error. This wasn't your fault!",
                    "There was a hiccup in the system while handling your request."
                ],
                "suggestions": [
                    "Let's try that again",
                    "If it happens again, there might be a temporary system issue",
                    "I've logged this error so it can be investigated"
                ],
                "tone": "apologetic"
            },

            # NLP-Specific Errors
            "understanding": {
                "patterns": [
                    r"intent.*not.*recognized",
                    r"could.*not.*understand",
                    r"ambiguous.*command",
                    r"unclear.*request"
                ],
                "responses": [
                    "I'm not quite sure what you'd like me to do.",
                    "Your request is a bit unclear to me. Could you rephrase it?",
                    "I understand some of what you said, but I need a bit more clarity."
                ],
                "suggestions": [
                    "Try using simpler language",
                    "Be more specific about what you want to accomplish",
                    "You can say things like 'create a task' or 'list my tasks'"
                ],
                "tone": "encouraging"
            },

            # Date/Time Parsing Errors
            "date_parsing": {
                "patterns": [
                    r"invalid.*date",
                    r"date.*format.*error",
                    r"could.*not.*parse.*date",
                    r"unrecognized.*date"
                ],
                "responses": [
                    "I had trouble understanding the date you mentioned.",
                    "The date format you used isn't clear to me.",
                    "I couldn't figure out what date you meant."
                ],
                "suggestions": [
                    "Try formats like 'tomorrow', 'next Friday', or '12/25/2024'",
                    "You can say 'due next week' or 'deadline Monday'",
                    "Relative dates like 'in 3 days' work well too"
                ],
                "tone": "helpful"
            },

            # Permission/Access Errors
            "permissions": {
                "patterns": [
                    r"insufficient.*permissions",
                    r"access.*denied",
                    r"not.*authorized",
                    r"permission.*denied"
                ],
                "responses": [
                    "I don't have permission to do that action.",
                    "Your account doesn't have the necessary permissions for this operation.",
                    "This action requires higher privileges than what's currently available."
                ],
                "suggestions": [
                    "Check with your team administrator",
                    "You might need additional permissions for this plan",
                    "Try a different action that requires fewer permissions"
                ],
                "tone": "informative"
            }
        }

        # Intent-specific error messages
        self.intent_specific_errors = {
            "create_task": {
                "missing_title": "Every task needs a name. What would you like to call this task?",
                "invalid_plan": "I couldn't find that plan. Which plan should I add the task to?",
                "date_error": "I couldn't understand the due date. When should this task be completed?"
            },
            "update_task": {
                "task_not_found": "I couldn't find that task. Could you be more specific about which task you want to update?",
                "no_changes": "I couldn't tell what you want to change about the task. What would you like to update?"
            },
            "assign_task": {
                "invalid_assignee": "I couldn't identify who you want to assign the task to. Please specify a person or email address.",
                "task_not_found": "I couldn't find the task you want to assign. Which task are you referring to?"
            }
        }

        # Conversation repair strategies
        self.repair_strategies = {
            "clarification": "Let me ask you some questions to better understand what you need.",
            "simplification": "Let's break this down into simpler steps.",
            "alternative": "Here's another way we could approach this.",
            "restart": "Let's start over with a fresh approach."
        }

    async def handle_error(self, error: Exception, context: ErrorContext) -> NaturalLanguageResponse:
        """
        Convert an error into a natural language response

        Args:
            error: The exception that occurred
            context: Context about the error and user request

        Returns:
            NaturalLanguageResponse with user-friendly message
        """
        try:
            error_message = str(error).lower()
            error_type = self._classify_error(error_message, error)

            logger.debug("Handling error",
                        error_type=error_type,
                        original_error=str(error)[:100],
                        user_input=context.user_input[:50])

            # Generate appropriate response based on error type
            response = await self._generate_natural_response(error_type, error_message, context)

            # Add intent-specific guidance if available
            if context.intent and context.intent in self.intent_specific_errors:
                response = await self._add_intent_specific_guidance(response, context)

            # Enhance with contextual suggestions
            response = await self._add_contextual_suggestions(response, context)

            logger.info("Generated natural language error response",
                       error_type=error_type,
                       tone=response.tone,
                       suggestions_count=len(response.suggestions))

            return response

        except Exception as e:
            logger.error("Error in error handling", error=str(e))
            # Fallback response
            return NaturalLanguageResponse(
                message="I encountered an unexpected issue while processing your request. Let's try again.",
                tone="apologetic",
                suggestions=["Please try rephrasing your request", "Check if all required information was provided"],
                retry_possible=True,
                escalation_needed=False
            )

    def _classify_error(self, error_message: str, error: Exception) -> str:
        """Classify the error type based on message and exception"""
        try:
            # Check for specific error types first
            if hasattr(error, 'status_code'):
                status_code = str(error.status_code)
                if status_code in ["401", "403"]:
                    return "authentication"
                elif status_code in ["404"]:
                    return "not_found"
                elif status_code in ["429"]:
                    return "rate_limit"
                elif status_code in ["400"]:
                    return "validation"
                elif status_code.startswith("5"):
                    return "processing"

            # Pattern matching
            for error_type, config in self.error_patterns.items():
                for pattern in config["patterns"]:
                    if re.search(pattern, error_message, re.IGNORECASE):
                        return error_type

            # Exception type classification
            if isinstance(error, ConnectionError) or isinstance(error, TimeoutError):
                return "network"
            elif isinstance(error, ValueError):
                return "validation"
            elif isinstance(error, KeyError) or isinstance(error, AttributeError):
                return "not_found"

            # Default classification
            return "processing"

        except Exception as e:
            logger.warning("Error classifying error type", error=str(e))
            return "processing"

    async def _generate_natural_response(self, error_type: str, error_message: str,
                                       context: ErrorContext) -> NaturalLanguageResponse:
        """Generate natural language response for error type"""
        try:
            if error_type not in self.error_patterns:
                error_type = "processing"

            config = self.error_patterns[error_type]

            # Select appropriate response message
            import random
            message = random.choice(config["responses"])

            # Get suggestions
            suggestions = config["suggestions"].copy()

            # Determine retry possibility
            retry_possible = error_type not in ["authentication", "permissions", "not_found"]

            # Determine if escalation is needed
            escalation_needed = error_type in ["authentication", "permissions", "processing"]

            return NaturalLanguageResponse(
                message=message,
                tone=config["tone"],
                suggestions=suggestions,
                retry_possible=retry_possible,
                escalation_needed=escalation_needed
            )

        except Exception as e:
            logger.warning("Error generating natural response", error=str(e))
            return NaturalLanguageResponse(
                message="I encountered an issue processing your request.",
                tone="apologetic",
                suggestions=["Please try again"],
                retry_possible=True,
                escalation_needed=False
            )

    async def _add_intent_specific_guidance(self, response: NaturalLanguageResponse,
                                          context: ErrorContext) -> NaturalLanguageResponse:
        """Add intent-specific guidance to the response"""
        try:
            if context.intent not in self.intent_specific_errors:
                return response

            intent_errors = self.intent_specific_errors[context.intent]

            # Check for specific issues based on entities
            additional_guidance = []

            if context.intent == "create_task":
                if not context.entities.get("TASK_TITLE"):
                    additional_guidance.append(intent_errors["missing_title"])
                if context.entities.get("PLAN_NAME") and "not found" in response.message.lower():
                    additional_guidance.append(intent_errors["invalid_plan"])

            elif context.intent == "update_task":
                if not context.entities.get("TASK_TITLE"):
                    additional_guidance.append(intent_errors["task_not_found"])

            elif context.intent == "assign_task":
                if not context.entities.get("ASSIGNEE"):
                    additional_guidance.append(intent_errors["invalid_assignee"])

            # Add guidance to response
            if additional_guidance:
                response.suggestions.extend(additional_guidance)

            return response

        except Exception as e:
            logger.warning("Error adding intent-specific guidance", error=str(e))
            return response

    async def _add_contextual_suggestions(self, response: NaturalLanguageResponse,
                                        context: ErrorContext) -> NaturalLanguageResponse:
        """Add contextual suggestions based on user input and intent"""
        try:
            contextual_suggestions = []

            # Suggest alternatives based on what the user was trying to do
            if context.intent:
                if context.intent == "create_task":
                    contextual_suggestions.append("Try: 'Create a task called [task name]'")
                elif context.intent == "list_tasks":
                    contextual_suggestions.append("Try: 'Show me my tasks' or 'List tasks in [plan name]'")
                elif context.intent == "update_task":
                    contextual_suggestions.append("Try: 'Update [task name] to be due [date]'")

            # Suggest using help
            if not any("help" in s.lower() for s in response.suggestions):
                contextual_suggestions.append("Say 'help' to see what I can do")

            # Add contextual suggestions to response
            response.suggestions.extend(contextual_suggestions)

            # Limit total suggestions to avoid overwhelming
            response.suggestions = response.suggestions[:5]

            return response

        except Exception as e:
            logger.warning("Error adding contextual suggestions", error=str(e))
            return response

    async def generate_clarification_request(self, ambiguous_input: str,
                                           possible_intents: List[str]) -> NaturalLanguageResponse:
        """
        Generate a clarification request for ambiguous input

        Args:
            ambiguous_input: The unclear user input
            possible_intents: List of possible intents detected

        Returns:
            NaturalLanguageResponse asking for clarification
        """
        try:
            if len(possible_intents) == 0:
                message = "I'm not sure what you'd like me to do. Could you be more specific?"
                suggestions = [
                    "Try saying 'create a task', 'list my tasks', or 'help'",
                    "Use clear action words like 'add', 'update', 'delete', or 'show'"
                ]

            elif len(possible_intents) == 1:
                intent = possible_intents[0]
                message = f"I think you want to {intent.replace('_', ' ')}, but I need more information."
                suggestions = [
                    "Please provide more details about what you want to do",
                    "Be more specific about the task or plan you're referring to"
                ]

            else:
                intent_descriptions = [intent.replace('_', ' ') for intent in possible_intents]
                message = f"I'm not sure if you want to {' or '.join(intent_descriptions)}. Could you clarify?"
                suggestions = [f"Say '{intent.replace('_', ' ')}' if that's what you meant"
                             for intent in possible_intents]

            return NaturalLanguageResponse(
                message=message,
                tone="encouraging",
                suggestions=suggestions,
                retry_possible=True,
                escalation_needed=False
            )

        except Exception as e:
            logger.error("Error generating clarification request", error=str(e))
            return NaturalLanguageResponse(
                message="I need more information to help you. Could you rephrase your request?",
                tone="helpful",
                suggestions=["Try being more specific about what you want to do"],
                retry_possible=True,
                escalation_needed=False
            )

    async def generate_success_response(self, intent: str, parameters: Dict[str, Any],
                                      result: Dict[str, Any]) -> str:
        """
        Generate a natural language success response

        Args:
            intent: The successfully executed intent
            parameters: Parameters used in the operation
            result: Result of the operation

        Returns:
            Natural language success message
        """
        try:
            success_templates = {
                "create_task": [
                    "Great! I've created the task '{title}' for you.",
                    "Perfect! Your new task '{title}' has been added.",
                    "Done! I've added '{title}' to your tasks."
                ],
                "update_task": [
                    "I've updated the task '{title}' as requested.",
                    "The task '{title}' has been successfully updated.",
                    "All set! Your changes to '{title}' have been saved."
                ],
                "delete_task": [
                    "I've removed the task '{title}' for you.",
                    "The task '{title}' has been deleted.",
                    "Done! '{title}' is no longer in your task list."
                ],
                "list_tasks": [
                    "Here are your tasks:",
                    "I found these tasks for you:",
                    "Your current tasks:"
                ],
                "assign_task": [
                    "I've assigned '{title}' to {assignee}.",
                    "The task '{title}' is now assigned to {assignee}.",
                    "Perfect! {assignee} now has the task '{title}'."
                ],
                "create_plan": [
                    "I've created the plan '{plan_name}' for you.",
                    "Your new plan '{plan_name}' is ready!",
                    "Great! The plan '{plan_name}' has been set up."
                ]
            }

            if intent not in success_templates:
                return "I've completed your request successfully!"

            import random
            template = random.choice(success_templates[intent])

            # Format with parameters
            format_params = {}
            if parameters.get("TASK_TITLE"):
                format_params["title"] = parameters["TASK_TITLE"]
            if parameters.get("ASSIGNEE"):
                format_params["assignee"] = parameters["ASSIGNEE"]
            if parameters.get("PLAN_NAME"):
                format_params["plan_name"] = parameters["PLAN_NAME"]

            try:
                message = template.format(**format_params)
            except KeyError:
                # If formatting fails, use a generic success message
                message = success_templates[intent][0].replace("{title}", "the task").replace("{assignee}", "someone").replace("{plan_name}", "the plan")

            # Add additional context if available
            if parameters.get("DUE_DATE"):
                message += f" It's due {parameters['DUE_DATE']}."
            if parameters.get("PRIORITY") and parameters["PRIORITY"] != "medium":
                message += f" Priority is set to {parameters['PRIORITY']}."

            return message

        except Exception as e:
            logger.warning("Error generating success response", error=str(e))
            return "I've completed your request successfully!"

    async def format_error_for_user(self, response: NaturalLanguageResponse) -> str:
        """
        Format the natural language response for display to user

        Args:
            response: NaturalLanguageResponse to format

        Returns:
            Formatted string ready for user display
        """
        try:
            message_parts = [response.message]

            if response.suggestions:
                if len(response.suggestions) == 1:
                    message_parts.append(f"\n💡 Suggestion: {response.suggestions[0]}")
                else:
                    message_parts.append("\n💡 Here are some suggestions:")
                    for i, suggestion in enumerate(response.suggestions, 1):
                        message_parts.append(f"   {i}. {suggestion}")

            if response.retry_possible:
                message_parts.append("\nFeel free to try again!")

            return "\n".join(message_parts)

        except Exception as e:
            logger.warning("Error formatting error for user", error=str(e))
            return response.message