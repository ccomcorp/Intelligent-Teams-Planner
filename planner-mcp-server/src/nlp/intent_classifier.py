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


@dataclass
class IntentResult:
    """Result of intent classification - alias for compatibility"""
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
                    "What tasks do I have today?",
                    "What tasks are assigned to angel@ccomgroupinc.com",
                    "What tasks are assigned to john.smith@company.com",
                    "Show tasks assigned to sarah@team.com",
                    "List tasks assigned to admin@domain.com",
                    "Find tasks assigned to user@example.com"
                ],
                "keywords": ["show", "list", "get", "find", "search", "view", "display", "my tasks", "what tasks", "assigned to", "assigned"]
            },
            "update_task": {
                "description": "Update or modify existing tasks",
                "examples": [
                    "Update the task deadline to next week",
                    "Change task priority to high",
                    "Modify the task description",
                    "Edit the presentation task",
                    "Update task status to in progress",
                    "Change the assignee of the budget task",
                    "Update the task 'Review budget' to be due tomorrow",
                    "Change the priority of 'Client meeting' to high",
                    "Modify the task description for project planning",
                    "Update budget review task due date",
                    "Change client meeting task priority level",
                    "Modify project planning task details"
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
                "description": "Assign existing tasks to team members",
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
            "create_and_assign_task": {
                "description": "Create a new task and assign it to someone",
                "examples": [
                    "assign task: configure ssl on servers to angel@company.com",
                    "create task configure website and assign to john@team.com",
                    "assign new task budget review to sarah.smith@company.com",
                    "delegate task: update documentation to dev@team.com",
                    "assign task configure ssl on ais for all commgroupinc.ai sites to angel@ccomgroupinc.com"
                ],
                "keywords": ["assign task:", "create task", "delegate task:", "new task", "assign new"]
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

            # Pre-processing: Check for create+assign patterns FIRST
            create_assign_patterns = [
                r"assign\s+task:?\s+.+\s+to\s+[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                r"assign\s+task:?\s+.+\s+to\s+\w+",
                r"create\s+task\s+.+\s+(?:and\s+)?assign\s+to\s+",
                r"delegate\s+task:?\s+.+\s+to\s+"
            ]

            for pattern in create_assign_patterns:
                if re.search(pattern, normalized_input, re.IGNORECASE):
                    logger.debug("Detected create+assign pattern", pattern=pattern)
                    return IntentMatch(
                        intent="create_and_assign_task",
                        confidence=0.95,
                        alternatives=[("assign_task", 0.8), ("create_task", 0.7)]
                    )

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
                # Adaptive weighting: favor keyword when it's strong, semantic when keyword is weak
                if keyword_match.confidence >= 0.7:
                    # Strong keyword match - favor keywords heavily
                    semantic_weight = 0.3
                    keyword_weight = 0.7
                elif keyword_match.confidence >= 0.5:
                    # Moderate keyword match - balanced weighting
                    semantic_weight = 0.5
                    keyword_weight = 0.5
                else:
                    # Weak keyword match - favor semantic
                    semantic_weight = 0.7
                    keyword_weight = 0.3

                combined_confidence = (semantic_weight * semantic_match.confidence +
                                     keyword_weight * keyword_match.confidence)

                # Use intent with higher individual confidence, but boost keyword when both are close
                confidence_diff = abs(semantic_match.confidence - keyword_match.confidence)
                if confidence_diff < 0.1 and keyword_match.confidence >= 0.5:
                    # Very close confidence - prefer keyword match
                    final_intent = keyword_match.intent
                elif keyword_match.confidence > semantic_match.confidence:
                    final_intent = keyword_match.intent
                else:
                    final_intent = semantic_match.intent

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
            keyword_count = len(definition["keywords"])

            for keyword in definition["keywords"]:
                # Check for exact phrase match or word boundary match
                if keyword in normalized_input:
                    if " " in keyword:  # Multi-word phrase
                        score += 3  # Higher weight for phrase matches
                    else:  # Single word - check word boundaries
                        pattern = r'\b' + re.escape(keyword) + r'\b'
                        if re.search(pattern, normalized_input):
                            score += 2  # Increased weight for exact word matches
                    matched_keywords.append(keyword)

            if score > 0:
                # Enhanced scoring: base score + bonus for multiple matches
                base_score = min(score / keyword_count, 1.0)
                match_ratio = len(matched_keywords) / keyword_count

                # Boost confidence when we have strong keyword matches
                if match_ratio >= 0.5:  # 50% or more keywords matched
                    confidence_boost = 0.3 * match_ratio
                elif match_ratio >= 0.25:  # 25% or more keywords matched
                    confidence_boost = 0.2 * match_ratio
                else:
                    confidence_boost = 0.1 * match_ratio

                # Strong keyword matches get significant boost
                if score >= 3:  # High-value keywords matched
                    confidence_boost += 0.2

                final_score = min(base_score + confidence_boost, 1.0)
                intent_scores[intent] = (final_score, matched_keywords)

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

    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two text strings"""
        try:
            # Simple word-based similarity for testing
            words1 = set(text1.lower().split())
            words2 = set(text2.lower().split())

            if not words1 or not words2:
                return 0.0

            # Calculate intersection and total words
            intersection = len(words1.intersection(words2))

            # Enhanced similarity calculation that favors shared important words
            # Give higher weight when key action words match
            key_words = {'create', 'task', 'new', 'add', 'make', 'update', 'delete', 'list', 'show'}
            key_intersection = len(words1.intersection(words2).intersection(key_words))

            # Base Jaccard similarity
            union = len(words1.union(words2))
            jaccard = intersection / union if union > 0 else 0.0

            # Boost similarity if important words match
            if key_intersection > 0:
                boost = min(0.3, key_intersection * 0.15)
                return min(1.0, jaccard + boost)

            return jaccard

        except Exception as e:
            logger.error("Error calculating semantic similarity", error=str(e))
            return 0.0