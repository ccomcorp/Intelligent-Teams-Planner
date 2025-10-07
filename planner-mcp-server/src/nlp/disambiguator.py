"""
Disambiguation and Clarification Logic for Natural Language Commands
Story 1.3 Task 4: Clarify ambiguous commands and missing parameters
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AmbiguityContext:
    """Context information about detected ambiguity"""
    ambiguity_type: str  # 'missing_parameter', 'multiple_options', 'unclear_intent'
    parameter_name: str
    possible_values: List[str]
    confidence: float
    user_input: str
    extracted_entities: Dict[str, Any]


@dataclass
class ClarificationRequest:
    """Request for user clarification"""
    question: str
    question_type: str  # 'selection', 'confirmation', 'input_request'
    options: Optional[List[str]] = None
    parameter_name: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class DisambiguationResult:
    """Result of disambiguation processing"""
    needs_clarification: bool
    clarification_requests: List[ClarificationRequest]
    confidence_score: float
    suggested_action: Optional[Dict[str, Any]]
    resolved_parameters: Dict[str, Any]


class NLDisambiguator:
    """
    Handles disambiguation and clarification of natural language commands
    Identifies missing parameters, ambiguous references, and unclear intents
    """

    def __init__(self, database, context_manager):
        self.database = database
        self.context_manager = context_manager

        # Define required parameters for each intent
        self.intent_requirements = {
            "create_task": {
                "required": ["title"],
                "optional": ["plan_name", "assignee", "due_date", "priority", "description"],
                "defaults": {
                    "priority": "medium",
                    "plan_name": "My Planner"
                }
            },
            "update_task": {
                "required": ["task_identifier"],
                "optional": ["title", "assignee", "due_date", "priority", "status", "description"],
                "defaults": {}
            },
            "delete_task": {
                "required": ["task_identifier"],
                "optional": [],
                "defaults": {}
            },
            "list_tasks": {
                "required": [],
                "optional": ["plan_name", "assignee", "status", "due_date"],
                "defaults": {}
            },
            "assign_task": {
                "required": ["task_identifier", "assignee"],
                "optional": [],
                "defaults": {}
            },
            "create_plan": {
                "required": ["plan_name"],
                "optional": ["description"],
                "defaults": {}
            },
            "get_help": {
                "required": [],
                "optional": [],
                "defaults": {}
            }
        }

        # Common ambiguous patterns
        self.ambiguous_patterns = {
            "pronouns": ["it", "this", "that", "these", "those"],
            "relative_references": ["same", "previous", "last", "current"],
            "vague_quantities": ["some", "several", "many", "few"],
            "vague_time": ["soon", "later", "sometime", "eventually"]
        }

    async def disambiguate_command(self, intent: str, entities: Dict[str, Any],
                                 user_input: str, user_id: str, session_id: str) -> DisambiguationResult:
        """
        Analyze command for ambiguities and generate clarification requests

        Args:
            intent: Detected intent
            entities: Extracted entities
            user_input: Original user input
            user_id: User identifier
            session_id: Session identifier

        Returns:
            DisambiguationResult with clarification needs
        """
        try:
            clarification_requests = []
            resolved_parameters = {}
            confidence_score = 1.0

            # Check for missing required parameters
            missing_params = await self._check_missing_parameters(intent, entities)
            for param in missing_params:
                clarification = await self._generate_parameter_request(param, intent, entities, user_id, session_id)
                if clarification:
                    clarification_requests.append(clarification)
                    confidence_score -= 0.2

            # Check for ambiguous references
            ambiguous_refs = await self._detect_ambiguous_references(user_input, entities, user_id, session_id)
            for ref in ambiguous_refs:
                clarification = await self._generate_reference_clarification(ref, user_id, session_id)
                if clarification:
                    clarification_requests.append(clarification)
                    confidence_score -= 0.15

            # Check for vague parameters
            vague_params = await self._detect_vague_parameters(entities, user_input)
            for param in vague_params:
                clarification = await self._generate_vague_parameter_clarification(param, entities)
                if clarification:
                    clarification_requests.append(clarification)
                    confidence_score -= 0.1

            # Try to resolve parameters using context
            resolved_parameters = await self._resolve_with_context(entities, user_id, session_id)

            # Check if we have enough to proceed
            needs_clarification = len(clarification_requests) > 0

            # Generate suggested action if confidence is high enough
            suggested_action = None
            if confidence_score >= 0.7 and not needs_clarification:
                suggested_action = await self._generate_suggested_action(intent, resolved_parameters)

            logger.debug("Disambiguation completed",
                        intent=intent,
                        needs_clarification=needs_clarification,
                        confidence=confidence_score,
                        clarification_count=len(clarification_requests))

            return DisambiguationResult(
                needs_clarification=needs_clarification,
                clarification_requests=clarification_requests,
                confidence_score=max(confidence_score, 0.0),
                suggested_action=suggested_action,
                resolved_parameters=resolved_parameters
            )

        except Exception as e:
            logger.error("Error in disambiguation", error=str(e), intent=intent)
            return DisambiguationResult(
                needs_clarification=False,
                clarification_requests=[],
                confidence_score=0.0,
                suggested_action=None,
                resolved_parameters=entities
            )

    async def _check_missing_parameters(self, intent: str, entities: Dict[str, Any]) -> List[str]:
        """Check for missing required parameters"""
        try:
            if intent not in self.intent_requirements:
                return []

            requirements = self.intent_requirements[intent]
            missing = []

            for param in requirements["required"]:
                # Map parameter names to entity types
                entity_key = self._map_parameter_to_entity(param)
                if entity_key not in entities or not entities[entity_key]:
                    missing.append(param)

            return missing

        except Exception as e:
            logger.warning("Error checking missing parameters", error=str(e), intent=intent)
            return []

    def _map_parameter_to_entity(self, parameter: str) -> str:
        """Map parameter names to entity types"""
        mapping = {
            "title": "TASK_TITLE",
            "plan_name": "PLAN_NAME",
            "assignee": "ASSIGNEE",
            "due_date": "DUE_DATE",
            "priority": "PRIORITY",
            "status": "STATUS",
            "task_identifier": "TASK_TITLE",  # Could be title or ID
            "description": "DESCRIPTION"
        }
        return mapping.get(parameter, parameter.upper())

    async def _generate_parameter_request(self, parameter: str, intent: str,
                                        entities: Dict[str, Any], user_id: str, session_id: str) -> Optional[ClarificationRequest]:
        """Generate clarification request for missing parameter"""
        try:
            questions = {
                "title": "What would you like to name this task?",
                "plan_name": "Which plan should this task be added to?",
                "assignee": "Who should be assigned to this task?",
                "due_date": "When is this task due?",
                "priority": "What priority should this task have?",
                "task_identifier": "Which task are you referring to? Please provide the task name or describe it.",
                "description": "Would you like to add a description to this task?"
            }

            question = questions.get(parameter, f"Please provide the {parameter}")

            # Add context-specific options
            options = None
            if parameter == "priority":
                options = ["high", "medium", "low"]
            elif parameter == "status":
                options = ["not_started", "in_progress", "completed"]
            elif parameter == "plan_name":
                # Could fetch available plans from database
                options = await self._get_available_plans(user_id)

            return ClarificationRequest(
                question=question,
                question_type="input_request" if not options else "selection",
                options=options,
                parameter_name=parameter,
                context={"intent": intent, "entities": entities}
            )

        except Exception as e:
            logger.warning("Error generating parameter request", error=str(e), parameter=parameter)
            return None

    async def _detect_ambiguous_references(self, user_input: str, entities: Dict[str, Any],
                                         user_id: str, session_id: str) -> List[AmbiguityContext]:
        """Detect ambiguous references in user input"""
        ambiguities = []
        input_lower = user_input.lower()

        try:
            # Check for pronouns
            for pronoun in self.ambiguous_patterns["pronouns"]:
                if pronoun in input_lower:
                    ambiguities.append(AmbiguityContext(
                        ambiguity_type="unclear_reference",
                        parameter_name="reference",
                        possible_values=[],
                        confidence=0.8,
                        user_input=user_input,
                        extracted_entities=entities
                    ))

            # Check for relative references
            for ref in self.ambiguous_patterns["relative_references"]:
                if ref in input_lower:
                    # Try to resolve using context
                    resolved = await self.context_manager.resolve_reference(user_id, session_id, ref)
                    if not resolved:
                        ambiguities.append(AmbiguityContext(
                            ambiguity_type="relative_reference",
                            parameter_name="reference",
                            possible_values=[],
                            confidence=0.7,
                            user_input=user_input,
                            extracted_entities=entities
                        ))

            return ambiguities

        except Exception as e:
            logger.warning("Error detecting ambiguous references", error=str(e))
            return []

    async def _generate_reference_clarification(self, ambiguity: AmbiguityContext,
                                              user_id: str, session_id: str) -> Optional[ClarificationRequest]:
        """Generate clarification for ambiguous reference"""
        try:
            if ambiguity.ambiguity_type == "unclear_reference":
                # Get recent entities for context
                recent_entities = await self.context_manager.get_recent_entities(user_id, session_id)

                options = []
                if "TASK_TITLE" in recent_entities:
                    options.append(f"Task: {recent_entities['TASK_TITLE']}")
                if "PLAN_NAME" in recent_entities:
                    options.append(f"Plan: {recent_entities['PLAN_NAME']}")

                question = "What are you referring to?"
                if options:
                    question = "What are you referring to? Here are some recent items:"

                return ClarificationRequest(
                    question=question,
                    question_type="selection" if options else "input_request",
                    options=options if options else None,
                    parameter_name="reference",
                    context={"ambiguity": ambiguity}
                )

            elif ambiguity.ambiguity_type == "relative_reference":
                return ClarificationRequest(
                    question="Could you be more specific about which item you're referring to?",
                    question_type="input_request",
                    parameter_name="reference",
                    context={"ambiguity": ambiguity}
                )

            return None

        except Exception as e:
            logger.warning("Error generating reference clarification", error=str(e))
            return None

    async def _detect_vague_parameters(self, entities: Dict[str, Any], user_input: str) -> List[AmbiguityContext]:
        """Detect vague or imprecise parameters"""
        vague_params = []
        input_lower = user_input.lower()

        try:
            # Check for vague quantities
            if "QUANTITY" in entities:
                quantity = entities["QUANTITY"].lower()
                if quantity in self.ambiguous_patterns["vague_quantities"]:
                    vague_params.append(AmbiguityContext(
                        ambiguity_type="vague_quantity",
                        parameter_name="quantity",
                        possible_values=["1", "2", "3", "5", "10"],
                        confidence=0.6,
                        user_input=user_input,
                        extracted_entities=entities
                    ))

            # Check for vague time references
            if "DUE_DATE" in entities:
                due_date = entities["DUE_DATE"].lower()
                if any(vague in due_date for vague in self.ambiguous_patterns["vague_time"]):
                    vague_params.append(AmbiguityContext(
                        ambiguity_type="vague_time",
                        parameter_name="due_date",
                        possible_values=["today", "tomorrow", "next week", "next month"],
                        confidence=0.7,
                        user_input=user_input,
                        extracted_entities=entities
                    ))

            return vague_params

        except Exception as e:
            logger.warning("Error detecting vague parameters", error=str(e))
            return []

    async def _generate_vague_parameter_clarification(self, ambiguity: AmbiguityContext,
                                                    entities: Dict[str, Any]) -> Optional[ClarificationRequest]:
        """Generate clarification for vague parameters"""
        try:
            if ambiguity.ambiguity_type == "vague_quantity":
                return ClarificationRequest(
                    question="How many tasks would you like to create?",
                    question_type="selection",
                    options=ambiguity.possible_values,
                    parameter_name="quantity",
                    context={"ambiguity": ambiguity}
                )

            elif ambiguity.ambiguity_type == "vague_time":
                return ClarificationRequest(
                    question="When would you like this to be due?",
                    question_type="selection",
                    options=ambiguity.possible_values,
                    parameter_name="due_date",
                    context={"ambiguity": ambiguity}
                )

            return None

        except Exception as e:
            logger.warning("Error generating vague parameter clarification", error=str(e))
            return None

    async def _resolve_with_context(self, entities: Dict[str, Any], user_id: str, session_id: str) -> Dict[str, Any]:
        """Resolve parameters using conversation context"""
        resolved = entities.copy()

        try:
            # If no plan name specified, use the last mentioned plan
            if "PLAN_NAME" not in resolved or not resolved["PLAN_NAME"]:
                last_plan = await self.context_manager.get_last_entity(user_id, session_id, "PLAN_NAME")
                if last_plan:
                    resolved["PLAN_NAME"] = last_plan

            # If no assignee specified for update/assign operations, check context
            if "ASSIGNEE" not in resolved or not resolved["ASSIGNEE"]:
                last_assignee = await self.context_manager.get_last_entity(user_id, session_id, "ASSIGNEE")
                if last_assignee:
                    resolved["ASSIGNEE"] = last_assignee

            return resolved

        except Exception as e:
            logger.warning("Error resolving with context", error=str(e))
            return entities

    async def _get_available_plans(self, user_id: str) -> List[str]:
        """Get available plans for the user"""
        try:
            # This would query the database for user's plans
            # For now, return common default plans
            return ["My Planner", "Work Tasks", "Personal Projects", "Team Goals"]

        except Exception as e:
            logger.warning("Error getting available plans", error=str(e))
            return ["My Planner"]

    async def _generate_suggested_action(self, intent: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Generate suggested action when confidence is high"""
        try:
            action = {
                "intent": intent,
                "parameters": parameters,
                "confidence": "high",
                "description": self._describe_action(intent, parameters)
            }

            return action

        except Exception as e:
            logger.warning("Error generating suggested action", error=str(e))
            return {}

    def _describe_action(self, intent: str, parameters: Dict[str, Any]) -> str:
        """Generate human-readable description of the action"""
        try:
            descriptions = {
                "create_task": f"Create task '{parameters.get('TASK_TITLE', 'New Task')}'",
                "update_task": f"Update task '{parameters.get('TASK_TITLE', 'Unknown Task')}'",
                "delete_task": f"Delete task '{parameters.get('TASK_TITLE', 'Unknown Task')}'",
                "list_tasks": "List tasks",
                "assign_task": f"Assign task to {parameters.get('ASSIGNEE', 'someone')}",
                "create_plan": f"Create plan '{parameters.get('PLAN_NAME', 'New Plan')}'",
            }

            base_description = descriptions.get(intent, f"Execute {intent}")

            # Add additional details
            details = []
            if parameters.get("PLAN_NAME"):
                details.append(f"in plan '{parameters['PLAN_NAME']}'")
            if parameters.get("DUE_DATE"):
                details.append(f"due {parameters['DUE_DATE']}")
            if parameters.get("ASSIGNEE") and intent != "assign_task":
                details.append(f"assigned to {parameters['ASSIGNEE']}")

            if details:
                base_description += " " + ", ".join(details)

            return base_description

        except Exception as e:
            logger.warning("Error describing action", error=str(e))
            return f"Execute {intent}"

    async def process_clarification_response(self, response: str, clarification_request: ClarificationRequest,
                                           original_entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process user's response to clarification request

        Args:
            response: User's clarification response
            clarification_request: Original clarification request
            original_entities: Original extracted entities

        Returns:
            Updated entities dictionary
        """
        try:
            updated_entities = original_entities.copy()
            param_name = clarification_request.parameter_name

            if clarification_request.question_type == "selection" and clarification_request.options:
                # Handle selection from options
                response_lower = response.lower().strip()

                # Find matching option
                for option in clarification_request.options:
                    if response_lower in option.lower() or option.lower() in response_lower:
                        entity_key = self._map_parameter_to_entity(param_name)
                        updated_entities[entity_key] = option
                        break
                else:
                    # If no exact match, use the response as-is
                    entity_key = self._map_parameter_to_entity(param_name)
                    updated_entities[entity_key] = response.strip()

            else:
                # Handle free-form input
                entity_key = self._map_parameter_to_entity(param_name)
                updated_entities[entity_key] = response.strip()

            logger.debug("Processed clarification response",
                        parameter=param_name,
                        response=response[:50],
                        updated_key=entity_key)

            return updated_entities

        except Exception as e:
            logger.error("Error processing clarification response", error=str(e))
            return original_entities