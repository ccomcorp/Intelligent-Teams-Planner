"""
Intent Classification for Natural Language Commands
Story 1.3 Task 1: Intent recognition for CRUD operations
"""

import re
import asyncio
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IntentMatch:
    """Result of intent classification"""
    intent: str
    confidence: float
    alternatives: List[Tuple[str, float]]


class IntentClassifier:
    """
    Intent classification using sentence transformers and keyword matching
    Supports CRUD operations for Microsoft Planner tasks
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", confidence_threshold: float = 0.7):
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.model: Optional[SentenceTransformer] = None
        self._intent_embeddings: Optional[np.ndarray] = None

        # Define supported intents with example phrases
        self.intent_definitions = {
            "create_task": {
                "description": "Create a new task or assignment",
                "examples": [
                    "Create a task to review the quarterly report",
                    "Add a new task for budget analysis",
                    "Make a task to prepare presentation",
                    "New task: Update website content",
                    "I need to create a task for the team meeting",
                    "Add task to finalize project proposal"
                ],
                "keywords": ["create", "add", "make", "new", "task", "assignment", "todo"]
            },
            "read_tasks": {
                "description": "Read, search, or list tasks",
                "examples": [
                    "Show me all my tasks",
                    "List tasks for this week",
                    "Find tasks assigned to John",
                    "Get my overdue tasks",
                    "Search for tasks about budget",
                    "What tasks do I have today?"
                ],
                "keywords": ["show", "list", "get", "find", "search", "view", "display", "my tasks", "what tasks"]
            },
            "update_task": {
                "description": "Update or modify existing tasks",
                "examples": [
                    "Update the task deadline to next week",
                    "Change task priority to high",
                    "Modify the task description",
                    "Edit the presentation task",
                    "Update task status to in progress",
                    "Change the assignee of the budget task"
                ],
                "keywords": ["update", "change", "modify", "edit", "alter", "revise", "adjust"]
            },
            "delete_task": {
                "description": "Delete or remove tasks",
                "examples": [
                    "Delete the completed task",
                    "Remove the cancelled project task",
                    "Drop the old meeting task",
                    "Cancel the review task",
                    "Delete all completed tasks",
                    "Remove tasks from last month"
                ],
                "keywords": ["delete", "remove", "drop", "cancel", "eliminate", "clear"]
            },
            "assign_task": {
                "description": "Assign tasks to team members",
                "examples": [
                    "Assign the budget task to Sarah",
                    "Give the presentation task to John",
                    "Delegate the review to the team lead",
                    "Assign this task to me",
                    "Transfer the task to another person",
                    "Set the assignee to Alice"
                ],
                "keywords": ["assign", "give", "delegate", "transfer", "set assignee", "allocate"]
            },
            "complete_task": {
                "description": "Mark tasks as complete or done",
                "examples": [
                    "Mark the presentation task as complete",
                    "Finish the budget review task",
                    "Complete the website update",
                    "Done with the meeting preparation",
                    "Task is finished",
                    "Close the project task"
                ],
                "keywords": ["complete", "finish", "done", "close", "mark complete", "mark done"]
            },
            "get_task_details": {
                "description": "Get detailed information about specific tasks",
                "examples": [
                    "Tell me about the budget task",
                    "Show details of the presentation task",
                    "What's the status of the review task?",
                    "Get information about my assigned tasks",
                    "Task details for the project update",
                    "Show me the task description"
                ],
                "keywords": ["tell me about", "show details", "status", "information", "details", "describe"]
            },
            "help": {
                "description": "Get help or information about available commands",
                "examples": [
                    "Help me with tasks",
                    "What can I do?",
                    "Show available commands",
                    "How do I create a task?",
                    "What operations are supported?",
                    "Need help with task management"
                ],
                "keywords": ["help", "what can", "how do", "commands", "operations", "support"]
            }
        }

    async def initialize(self):
        """Initialize the sentence transformer model and precompute intent embeddings"""
        try:
            logger.info("Initializing intent classifier", model=self.model_name)

            # Initialize the model in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                lambda: SentenceTransformer(self.model_name)
            )

            # Precompute embeddings for all intent examples
            await self._precompute_intent_embeddings()

            logger.info("Intent classifier initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize intent classifier", error=str(e))
            raise

    async def _precompute_intent_embeddings(self):
        """Precompute embeddings for all intent examples"""
        try:
            all_examples = []
            self.example_to_intent = {}

            # Collect all examples and map them to intents
            for intent, definition in self.intent_definitions.items():
                for example in definition["examples"]:
                    all_examples.append(example)
                    self.example_to_intent[example] = intent

            # Compute embeddings for all examples
            loop = asyncio.get_event_loop()
            self._intent_embeddings = await loop.run_in_executor(
                None,
                lambda: self.model.encode(all_examples)
            )

            logger.debug("Precomputed embeddings for intent classification",
                        num_examples=len(all_examples))

        except Exception as e:
            logger.error("Failed to precompute intent embeddings", error=str(e))
            raise

    async def classify_intent(self, user_input: str) -> IntentMatch:
        """
        Classify user input to determine intent

        Args:
            user_input: The user's natural language input

        Returns:
            IntentMatch with the predicted intent and confidence
        """
        try:
            if not self.model or self._intent_embeddings is None:
                raise RuntimeError("Intent classifier not initialized. Call initialize() first.")

            # Normalize input
            normalized_input = user_input.lower().strip()

            # First, try keyword-based matching for high confidence
            keyword_match = self._keyword_based_classification(normalized_input)
            if keyword_match and keyword_match.confidence >= self.confidence_threshold:
                logger.debug("Intent classified using keywords",
                           intent=keyword_match.intent,
                           confidence=keyword_match.confidence)
                return keyword_match

            # Fall back to semantic similarity using sentence transformers
            semantic_match = await self._semantic_classification(user_input)

            # Combine keyword and semantic results if both available
            if keyword_match and semantic_match:
                # Weighted combination: 60% semantic, 40% keyword
                combined_confidence = (0.6 * semantic_match.confidence +
                                     0.4 * keyword_match.confidence)

                # Use semantic intent if confidence is higher, otherwise keyword
                final_intent = (semantic_match.intent if semantic_match.confidence > keyword_match.confidence
                               else keyword_match.intent)

                return IntentMatch(
                    intent=final_intent,
                    confidence=combined_confidence,
                    alternatives=semantic_match.alternatives
                )

            return semantic_match if semantic_match else keyword_match

        except Exception as e:
            logger.error("Error classifying intent", error=str(e), user_input=user_input)
            # Return a low-confidence help intent as fallback
            return IntentMatch(
                intent="help",
                confidence=0.1,
                alternatives=[]
            )

    def _keyword_based_classification(self, normalized_input: str) -> Optional[IntentMatch]:
        """
        Classify intent using keyword matching

        Args:
            normalized_input: Normalized user input

        Returns:
            IntentMatch if keywords found, None otherwise
        """
        intent_scores = {}

        for intent, definition in self.intent_definitions.items():
            score = 0
            matched_keywords = []

            for keyword in definition["keywords"]:
                # Check for exact phrase match or word boundary match
                if keyword in normalized_input:
                    if " " in keyword:  # Multi-word phrase
                        score += 2  # Higher weight for phrase matches
                    else:  # Single word - check word boundaries
                        pattern = r'\b' + re.escape(keyword) + r'\b'
                        if re.search(pattern, normalized_input):
                            score += 1
                    matched_keywords.append(keyword)

            if score > 0:
                # Normalize score by number of keywords for this intent
                normalized_score = min(score / len(definition["keywords"]), 1.0)
                intent_scores[intent] = (normalized_score, matched_keywords)

        if not intent_scores:
            return None

        # Get the intent with the highest score
        best_intent = max(intent_scores.keys(), key=lambda x: intent_scores[x][0])
        best_score, matched_keywords = intent_scores[best_intent]

        # Generate alternatives
        alternatives = [(intent, score) for intent, (score, _) in intent_scores.items()
                       if intent != best_intent]
        alternatives.sort(key=lambda x: x[1], reverse=True)

        logger.debug("Keyword-based classification",
                    intent=best_intent,
                    score=best_score,
                    matched_keywords=matched_keywords)

        return IntentMatch(
            intent=best_intent,
            confidence=best_score,
            alternatives=alternatives[:3]  # Top 3 alternatives
        )

    async def _semantic_classification(self, user_input: str) -> IntentMatch:
        """
        Classify intent using semantic similarity with sentence transformers

        Args:
            user_input: The user's input

        Returns:
            IntentMatch with semantic similarity results
        """
        try:
            # Encode the user input
            loop = asyncio.get_event_loop()
            input_embedding = await loop.run_in_executor(
                None,
                lambda: self.model.encode([user_input])
            )

            # Calculate similarities with all precomputed intent examples
            similarities = cosine_similarity(input_embedding, self._intent_embeddings)[0]

            # Find the best matching example and its intent
            best_example_idx = np.argmax(similarities)
            best_similarity = similarities[best_example_idx]

            # Get all examples with their intents and similarities
            example_list = list(self.example_to_intent.keys())
            best_example = example_list[best_example_idx]
            best_intent = self.example_to_intent[best_example]

            # Calculate average similarity for each intent
            intent_similarities = {}
            for i, example in enumerate(example_list):
                intent = self.example_to_intent[example]
                if intent not in intent_similarities:
                    intent_similarities[intent] = []
                intent_similarities[intent].append(similarities[i])

            # Average similarities for each intent
            for intent in intent_similarities:
                intent_similarities[intent] = np.mean(intent_similarities[intent])

            # Sort intents by average similarity
            sorted_intents = sorted(intent_similarities.items(),
                                  key=lambda x: x[1], reverse=True)

            # The best intent and its confidence
            final_intent = sorted_intents[0][0]
            final_confidence = float(sorted_intents[0][1])

            # Generate alternatives (top 3 excluding the best)
            alternatives = [(intent, float(sim)) for intent, sim in sorted_intents[1:4]]

            logger.debug("Semantic classification",
                        intent=final_intent,
                        confidence=final_confidence,
                        best_example=best_example)

            return IntentMatch(
                intent=final_intent,
                confidence=final_confidence,
                alternatives=alternatives
            )

        except Exception as e:
            logger.error("Error in semantic classification", error=str(e))
            raise

    def get_intent_description(self, intent: str) -> str:
        """Get description for a given intent"""
        return self.intent_definitions.get(intent, {}).get("description", "Unknown intent")

    def list_supported_intents(self) -> Dict[str, str]:
        """Get all supported intents with their descriptions"""
        return {intent: definition["description"]
                for intent, definition in self.intent_definitions.items()}