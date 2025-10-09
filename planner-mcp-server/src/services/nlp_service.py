"""
Natural Language Processing Service
Story 1.3: Main NLP orchestration service
"""

import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import structlog

from ..nlp.intent_classifier import IntentClassifier
from ..nlp.entity_extractor import EntityExtractor, EntityExtractionResult
from ..nlp.date_parser import DateParser
from ..nlp.context_manager import ConversationContextManager
from ..nlp.batch_processor import BatchProcessor
from ..nlp.disambiguator import NLDisambiguator
from ..nlp.error_handler import NLErrorHandler, ErrorContext

logger = structlog.get_logger(__name__)


@dataclass
class NLPProcessingResult:
    """Complete result of NLP processing"""
    intent: str
    entities: Dict[str, Any]
    confidence_score: float
    context_updated: bool
    batch_operation: Optional[Dict[str, Any]] = None
    suggested_action: Optional[Dict[str, Any]] = None
    clarification_needed: Optional[str] = None
    processing_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None
    is_batch_operation: bool = False
    batch_info: Optional[Dict[str, Any]] = None
    needs_clarification: bool = False
    clarification_requests: Optional[List[Any]] = None
    natural_language_response: Optional[str] = None

    @property
    def confidence(self) -> float:
        """Backward compatibility property for confidence_score"""
        return self.confidence_score

    def __post_init__(self):
        """Ensure clarification_requests is always a list"""
        if self.clarification_requests is None:
            self.clarification_requests = []


class NLPService:
    """
    Main Natural Language Processing service
    Orchestrates intent classification, entity extraction, date parsing, and context management
    """

    def __init__(self, database, cache_service=None):
        self.database = database
        self.cache_service = cache_service

        # Initialize NLP components
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self.date_parser = DateParser()
        self.context_manager = ConversationContextManager(database)
        self.batch_processor = BatchProcessor()
        self.disambiguator = NLDisambiguator(database, self.context_manager)
        self.error_handler = NLErrorHandler()

        # Confidence thresholds
        self.min_intent_confidence = 0.6
        self.min_entity_confidence = 0.5
        self.min_date_confidence = 0.5

        self.initialized = False

    async def initialize(self):
        """Initialize all NLP components"""
        try:
            logger.info("Initializing NLP service")

            # Initialize all components concurrently
            await asyncio.gather(
                self.intent_classifier.initialize(),
                self.entity_extractor.initialize(),
                self.context_manager.initialize()
            )

            self.initialized = True
            logger.info("NLP service initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize NLP service", error=str(e))
            raise

    async def process_natural_language(self, user_input: str, user_id: str, session_id: str,
                                     context: Optional[Dict[str, Any]] = None) -> NLPProcessingResult:
        """
        Process natural language input through the complete NLP pipeline

        Args:
            user_input: User's natural language input
            user_id: User identifier
            session_id: Session identifier
            context: Additional context information

        Returns:
            NLPProcessingResult with all processing results
        """
        start_time = datetime.now()

        try:
            if not self.initialized:
                raise RuntimeError("NLP service not initialized. Call initialize() first.")

            logger.debug("Processing natural language input",
                        user_id=user_id,
                        session_id=session_id,
                        input_length=len(user_input))

            # Step 1: Intent Classification
            intent_result = await self.intent_classifier.classify_intent(user_input)
            intent = intent_result.intent if hasattr(intent_result, 'intent') else "unknown"
            intent_confidence = intent_result.confidence if hasattr(intent_result, 'confidence') else 0.0

            # Step 2: Entity Extraction
            entity_result = await self.entity_extractor.extract_entities(user_input, context)
            entities = {}
            for entity in entity_result.entities:
                entities[entity.type] = entity.value

            # Step 3: Date Parsing
            date_result = await self.date_parser.parse_date(user_input)

            # Step 4: Context Resolution
            resolved_entities = await self._resolve_context_references(
                user_id, session_id, entity_result, context
            )

            # Step 5: Batch Operation Detection
            batch_operation = await self.batch_processor.detect_batch_operation(
                user_input, resolved_entities
            )

            # Step 6: Generate Suggested Action
            suggested_action = await self._generate_suggested_action(
                intent, resolved_entities, date_result, batch_operation
            )

            # Step 7: Check for Clarification Needs
            clarification_needed = await self._check_clarification_needed(
                intent, resolved_entities, suggested_action
            )

            # Initialize clarification_requests based on clarification_needed
            clarification_requests = []
            if clarification_needed:
                clarification_requests = [{
                    "question": clarification_needed,
                    "question_type": "input_request",
                    "parameter_name": "missing_info"
                }]

            # Step 8: Update Conversation Context
            context_updated = await self._update_conversation_context(
                user_id, session_id, user_input, intent, resolved_entities
            )

            # Calculate overall confidence
            confidence_score = intent_confidence

            # Reduce confidence when clarification is needed
            if clarification_needed:
                confidence_score = min(confidence_score * 0.6, 0.6)  # Max 0.6 when clarification needed

            processing_time = (datetime.now() - start_time).total_seconds()

            result = NLPProcessingResult(
                intent=intent,
                entities=resolved_entities,
                confidence_score=confidence_score,
                context_updated=context_updated,
                batch_operation=batch_operation,
                suggested_action=suggested_action,
                clarification_needed=clarification_needed,
                processing_time=processing_time,
                is_batch_operation=batch_operation is not None and batch_operation.get("is_batch", False),
                batch_info=batch_operation,
                needs_clarification=clarification_needed is not None,
                clarification_requests=clarification_requests,
                metadata={
                    "resolved_entities": resolved_entities,
                    "user_id": user_id,
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "intent_confidence": intent_confidence,
                    "date_result": date_result.success if date_result else False
                }
            )

            logger.info("Completed NLP processing",
                       user_id=user_id,
                       intent=intent,
                       confidence=confidence_score,
                       processing_time=processing_time)

            return result

        except Exception as e:
            logger.error("Error processing natural language",
                        error=str(e),
                        user_id=user_id,
                        session_id=session_id)

            # Return error result
            processing_time = (datetime.now() - start_time).total_seconds()
            return NLPProcessingResult(
                intent="unknown",
                entities={},
                confidence_score=0.0,
                context_updated=False,
                processing_time=processing_time,
                natural_language_response="I encountered an error processing your request. Please try again.",
                metadata={"error": str(e)}
            )

    async def _resolve_context_references(self, user_id: str, session_id: str,
                                        entity_result: EntityExtractionResult,
                                        context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Resolve contextual references in extracted entities"""
        try:
            resolved_entities = {}

            # Convert entities to dictionary
            for entity in entity_result.entities:
                if entity.type not in resolved_entities:
                    resolved_entities[entity.type] = []
                resolved_entities[entity.type].append(entity.value)

            # Flatten single-item lists
            for entity_type, values in resolved_entities.items():
                if len(values) == 1:
                    resolved_entities[entity_type] = values[0]

            # Check for contextual references that need resolution
            contextual_phrases = [
                "same project", "that project", "this project",
                "same person", "that person", "same assignee",
                "that task", "this task", "my tasks"
            ]

            original_text = entity_result.cleaned_text.lower()
            for phrase in contextual_phrases:
                if phrase in original_text:
                    resolved_ref = await self.context_manager.resolve_reference(
                        user_id, session_id, phrase
                    )
                    if resolved_ref:
                        resolved_entities.update(resolved_ref)

            # Add user_id for "my" references
            if "my tasks" in original_text or "my assignments" in original_text:
                resolved_entities["ASSIGNEE"] = user_id

            return resolved_entities

        except Exception as e:
            logger.warning("Error resolving context references", error=str(e))
            # Return entities as-is on error
            resolved = {}
            for entity in entity_result.entities:
                resolved[entity.type] = entity.value
            return resolved

    async def _generate_suggested_action(self, intent: str,
                                       entities: Dict[str, Any],
                                       dates: Any,
                                       batch_operation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate suggested action based on NLP results"""
        try:
            suggested_action = {
                "action": intent,
                "confidence": 0.8,  # Default confidence
                "parameters": {}
            }

            # Map entities to action parameters
            if "TASK_TITLE" in entities:
                suggested_action["parameters"]["title"] = entities["TASK_TITLE"]

            if "ASSIGNEE" in entities:
                suggested_action["parameters"]["assignee"] = entities["ASSIGNEE"]

            if "PLAN_NAME" in entities:
                suggested_action["parameters"]["plan_name"] = entities["PLAN_NAME"]

            if "PRIORITY" in entities:
                suggested_action["parameters"]["priority"] = entities["PRIORITY"]

            if "STATUS" in entities:
                suggested_action["parameters"]["status"] = entities["STATUS"]

            # Add date information
            if dates and hasattr(dates, 'parsed_date') and dates.parsed_date:
                suggested_action["parameters"]["due_date"] = dates.parsed_date.isoformat()

            # Handle batch operations
            if batch_operation and batch_operation.get("is_batch"):
                suggested_action["is_batch"] = True
                suggested_action["batch_type"] = batch_operation.get("operation_type")

                if "quantity" in batch_operation:
                    suggested_action["parameters"]["quantity"] = batch_operation["quantity"]

            # Add tool mapping
            tool_mapping = {
                "create_task": "create_task",
                "read_tasks": "list_tasks",
                "update_task": "update_task",
                "delete_task": "delete_task",
                "assign_task": "assign_task",
                "complete_task": "complete_task",
                "get_task_details": "get_task_details",
                "help": "help"
            }

            suggested_action["tool"] = tool_mapping.get(intent, "help")

            return suggested_action

        except Exception as e:
            logger.warning("Error generating suggested action", error=str(e))
            return {
                "action": "help",
                "confidence": 0.0,
                "parameters": {},
                "error": str(e)
            }

    async def _check_clarification_needed(self, intent: str,
                                        entities: Dict[str, Any],
                                        suggested_action: Dict[str, Any]) -> Optional[str]:
        """Check if clarification is needed for the user's request"""
        try:
            # Missing required entities for certain actions
            if intent == "create_task":
                if "TASK_TITLE" not in entities or not entities["TASK_TITLE"]:
                    return "I'd like to help you create a task. What should the task be called?"

            elif intent == "assign_task":
                if "ASSIGNEE" not in entities:
                    return "Who would you like to assign this task to?"
                if "TASK_TITLE" not in entities and "PLAN_NAME" not in entities:
                    return "Which task or project would you like to assign?"

            elif intent == "delete_task":
                if "TASK_TITLE" not in entities and "PLAN_NAME" not in entities:
                    return "Which task or project would you like to delete? Please be specific to avoid accidental deletions."

            elif intent in ["update_task", "complete_task"]:
                if "TASK_TITLE" not in entities and "PLAN_NAME" not in entities:
                    return "Which task would you like to update?"

            # Ambiguous date references - only check if DUE_DATE is actually a list
            due_date_entity = entities.get("DUE_DATE", [])
            if (suggested_action.get("parameters", {}).get("due_date") and
                isinstance(due_date_entity, list) and len(due_date_entity) > 1):
                return "I found multiple dates in your request. Which date should I use as the due date?"

            # Destructive operations without confirmation
            if intent == "delete_task" and suggested_action.get("is_batch"):
                return "This will delete multiple tasks. Are you sure you want to continue? Please confirm."

            return None

        except Exception as e:
            logger.warning("Error checking clarification needs", error=str(e))
            return None

    async def _update_conversation_context(self, user_id: str, session_id: str,
                                         user_input: str, intent: str,
                                         entities: Dict[str, Any]) -> bool:
        """Update conversation context with current interaction"""
        try:
            # Prepare entities for context storage
            entity_data = {f"{k}_history": v for k, v in entities.items()}

            success = await self.context_manager.add_message(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=user_input,
                entities=entity_data,
                intent=intent,
                metadata={
                    "intent_confidence": 0.8,
                    "intent_alternatives": []
                }
            )

            return success

        except Exception as e:
            logger.warning("Error updating conversation context", error=str(e))
            return False

    def _calculate_overall_confidence(self, intent: str,
                                    entity_result: EntityExtractionResult,
                                    date_result: Any) -> float:
        """Calculate overall confidence score for the NLP processing"""
        try:
            # Intent confidence (weighted 50%)
            intent_score = 0.8 * 0.5  # Default confidence

            # Entity confidence (weighted 30%)
            if entity_result.entities:
                avg_entity_confidence = sum(e.confidence for e in entity_result.entities) / len(entity_result.entities)
                entity_score = avg_entity_confidence * 0.3
            else:
                entity_score = 0.1  # Small penalty for no entities

            # Date confidence (weighted 20%)
            if date_result and hasattr(date_result, 'confidence'):
                date_score = date_result.confidence * 0.2
            else:
                date_score = 0.1  # Small penalty for no dates

            overall_confidence = intent_score + entity_score + date_score

            # Apply bonuses/penalties for rich entity extraction

            if len(entity_result.entities) >= 3:
                overall_confidence += 0.05  # Bonus for rich entity extraction

            return min(overall_confidence, 1.0)  # Cap at 1.0

        except Exception as e:
            logger.warning("Error calculating overall confidence", error=str(e))
            return 0.5  # Default moderate confidence

    async def generate_natural_response(self, nlp_result: NLPProcessingResult,
                                      execution_result: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a natural language response based on NLP processing and execution results

        Args:
            nlp_result: Result from NLP processing
            execution_result: Result from action execution

        Returns:
            Natural language response
        """
        try:
            intent = nlp_result.intent
            confidence = nlp_result.confidence_score

            # Handle clarification requests
            if nlp_result.clarification_needed:
                return nlp_result.clarification_needed

            # Handle low confidence responses
            if confidence < 0.5:
                return "I'm not quite sure what you're asking for. Could you please rephrase your request or ask for help to see what I can do?"

            # Generate response based on intent and execution result
            if execution_result:
                if execution_result.get("success"):
                    return self._generate_success_response(intent, execution_result, nlp_result)
                else:
                    return self._generate_error_response(intent, execution_result, nlp_result)
            else:
                return self._generate_processing_response(intent, nlp_result)

        except Exception as e:
            logger.error("Error generating natural response", error=str(e))
            return "I processed your request, but I'm having trouble generating a response. The action may have been completed successfully."

    def _generate_success_response(self, intent: str, execution_result: Dict[str, Any],
                                 nlp_result: NLPProcessingResult) -> str:
        """Generate success response message"""
        try:
            entities = nlp_result.metadata.get("resolved_entities", {})

            if intent == "create_task":
                task_title = entities.get("TASK_TITLE", "task")
                if nlp_result.batch_operation and nlp_result.batch_operation.get("is_batch"):
                    quantity = nlp_result.suggested_action.get("parameters", {}).get("quantity", "multiple")
                    return f"Successfully created {quantity} tasks for {task_title}."
                else:
                    return f"Successfully created task: {task_title}."

            elif intent == "read_tasks" or intent == "get_task_details":
                count = execution_result.get("count", 0)
                if count == 0:
                    return "I didn't find any tasks matching your criteria."
                elif count == 1:
                    return "I found 1 task matching your criteria."
                else:
                    return f"I found {count} tasks matching your criteria."

            elif intent == "update_task":
                return "Task updated successfully."

            elif intent == "delete_task":
                count = execution_result.get("deleted_count", 1)
                if count == 1:
                    return "Task deleted successfully."
                else:
                    return f"Successfully deleted {count} tasks."

            elif intent == "assign_task":
                assignee = entities.get("ASSIGNEE", "the specified person")
                return f"Task assigned to {assignee} successfully."

            elif intent == "complete_task":
                return "Task marked as completed successfully."

            else:
                return "Request completed successfully."

        except Exception as e:
            logger.warning("Error generating success response", error=str(e))
            return "Your request was completed successfully."

    def _generate_error_response(self, intent: str, execution_result: Dict[str, Any],
                               nlp_result: NLPProcessingResult) -> str:
        """Generate error response message"""
        try:
            error_message = execution_result.get("error", "An unknown error occurred")

            # Convert technical errors to user-friendly messages
            if "404" in error_message or "not found" in error_message.lower():
                if intent in ["update_task", "delete_task", "assign_task", "complete_task"]:
                    return "I couldn't find the task you're referring to. Please check the task name or try listing your tasks first."
                elif intent == "read_tasks":
                    return "I couldn't find any tasks matching your criteria."
                else:
                    return "I couldn't find what you're looking for. Please check your request and try again."

            elif "403" in error_message or "permission" in error_message.lower():
                return "I don't have permission to perform that action. Please check if you have access to the specified plan or task."

            elif "429" in error_message or "rate limit" in error_message.lower():
                return "Microsoft's servers are busy right now. Please try again in a moment."

            elif "validation" in error_message.lower():
                return f"There's an issue with the information provided: {error_message}"

            else:
                return f"I encountered an error while processing your request: {error_message}"

        except Exception as e:
            logger.warning("Error generating error response", error=str(e))
            return "I encountered an error while processing your request. Please try again."

    def _generate_processing_response(self, intent: str, nlp_result: NLPProcessingResult) -> str:
        """Generate response for processing without execution result"""
        if nlp_result.batch_operation and nlp_result.batch_operation.get("is_batch"):
            return "I understand you want to perform a batch operation. Let me process that for you..."

        elif intent == "help":
            return ("I can help you manage tasks and projects. You can ask me to:\n"
                   "• Create tasks: 'Create a task to review the budget'\n"
                   "• List tasks: 'Show me my tasks for this week'\n"
                   "• Update tasks: 'Change the deadline to next Friday'\n"
                   "• Assign tasks: 'Assign the presentation task to John'\n"
                   "• Complete tasks: 'Mark the review task as done'\n"
                   "• Delete tasks: 'Delete the cancelled project tasks'")

        else:
            return "I understand your request. Let me process that for you..."

    async def get_service_status(self) -> Dict[str, Any]:
        """Get status of the NLP service and its components"""
        try:
            return {
                "initialized": self.initialized,
                "components": {
                    "intent_classifier": {
                        "available": self.intent_classifier.model is not None,
                        "supported_intents": list(self.intent_classifier.intent_definitions.keys())
                    },
                    "entity_extractor": {
                        "available": self.entity_extractor.nlp is not None,
                        "supported_entities": list(self.entity_extractor.entity_patterns.keys())
                    },
                    "date_parser": {
                        "available": True,
                        "supported_patterns": len(self.date_parser.relative_patterns)
                    },
                    "context_manager": {
                        "available": True,
                        "database_connected": self.database is not None
                    },
                    "batch_processor": {
                        "available": True,
                        "max_batch_size": self.batch_processor.max_batch_size
                    }
                },
                "configuration": {
                    "min_intent_confidence": self.min_intent_confidence,
                    "min_entity_confidence": self.min_entity_confidence,
                    "min_date_confidence": self.min_date_confidence
                }
            }

        except Exception as e:
            logger.error("Error getting service status", error=str(e))
            return {"initialized": False, "error": str(e)}