"""
Semantic Intent Matching using ChromaDB and Modern Sentence Transformers
Replaces hard-coded regex patterns with vector similarity search
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from sentence_transformers import SentenceTransformer
import structlog

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None

logger = structlog.get_logger(__name__)


@dataclass
class SemanticMatch:
    """Result of semantic intent matching"""
    intent: str
    confidence: float
    alternatives: List[Tuple[str, float]]
    semantic_similarity: float
    matched_example: str


class SemanticIntentMatcher:
    """
    Modern semantic intent matching using vector similarity search
    Replaces regex patterns with semantic understanding
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-mpnet-base-v2",
                 use_chromadb: bool = True):
        self.model_name = model_name
        self.use_chromadb = use_chromadb and CHROMADB_AVAILABLE
        self.model: Optional[SentenceTransformer] = None
        self.chroma_client = None
        self.intent_collection = None
        self.fallback_embeddings = {}  # Fallback when ChromaDB not available

        # Enhanced intent definitions with more examples
        self.intent_definitions = self._get_enhanced_intent_definitions()

    def _get_enhanced_intent_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Enhanced intent definitions with comprehensive examples"""
        return {
            "create_task": {
                "description": "Create a new task",
                "examples": [
                    "Create a task to review the quarterly report",
                    "Add a new task for budget analysis",
                    "Make a task to prepare presentation",
                    "New task: Update website content",
                    "I need to create a task for the team meeting",
                    "Add task to finalize project proposal",
                    "Create task: Configure SSL certificates",
                    "Make a new task for code review",
                    "Add task to update documentation"
                ]
            },
            "assign_task": {
                "description": "Assign an existing task to someone",
                "examples": [
                    "Assign the budget task to Sarah",
                    "Give the presentation task to John",
                    "Delegate the review to the team lead",
                    "Assign this task to me",
                    "Transfer the task to another person",
                    "Set the assignee to Alice",
                    "Assign angel@ccomgroupinc.com to task configure SSL",
                    "Give task CONFIGURE SSL to angel@company.com",
                    "Delegate configure SSL task to angel@ccomgroupinc.com"
                ]
            },
            "create_and_assign_task": {
                "description": "Create a new task and assign it to someone",
                "examples": [
                    "assign task: configure ssl on servers to angel@company.com",
                    "create task configure website and assign to john@team.com",
                    "assign new task budget review to sarah.smith@company.com",
                    "delegate task: update documentation to dev@team.com",
                    "assign task configure ssl on ais for all commgroupinc.ai sites to angel@ccomgroupinc.com",
                    "create and assign SSL configuration to angel@ccomgroupinc.com",
                    "make task update server and give to admin@company.com"
                ]
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
                    "Show tasks assigned to john.smith@company.com",
                    "List tasks assigned to sarah@team.com",
                    "Find tasks assigned to admin@domain.com",
                    "tasks assigned to angel@ccomgroupinc.com"
                ]
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
                    "Mark task as complete",
                    "Set task progress to 50%"
                ]
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
                ]
            },
            "help": {
                "description": "Get help or information",
                "examples": [
                    "Help me with tasks",
                    "What can I do?",
                    "Show available commands",
                    "How do I create a task?",
                    "What operations are supported?",
                    "Need help with task management"
                ]
            }
        }

    async def initialize(self):
        """Initialize the semantic intent matcher"""
        try:
            logger.info("Initializing semantic intent matcher",
                       model=self.model_name, use_chromadb=self.use_chromadb)

            # Initialize sentence transformer model
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None, lambda: SentenceTransformer(self.model_name)
            )

            if self.use_chromadb:
                await self._initialize_chromadb()
            else:
                await self._initialize_fallback_embeddings()

            logger.info("Semantic intent matcher initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize semantic intent matcher", error=str(e))
            if self.use_chromadb:
                logger.info("Falling back to non-ChromaDB implementation")
                self.use_chromadb = False
                await self._initialize_fallback_embeddings()
            else:
                raise

    async def _initialize_chromadb(self):
        """Initialize ChromaDB for vector storage"""
        try:
            # Create ChromaDB client
            self.chroma_client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory="./chroma_db"
            ))

            # Create or get collection
            try:
                self.intent_collection = self.chroma_client.get_collection(
                    name="intent_examples"
                )
                logger.info("Loaded existing ChromaDB collection")
            except:
                self.intent_collection = self.chroma_client.create_collection(
                    name="intent_examples",
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info("Created new ChromaDB collection")

                # Populate collection with intent examples
                await self._populate_chromadb()

        except Exception as e:
            logger.error("ChromaDB initialization failed", error=str(e))
            raise

    async def _populate_chromadb(self):
        """Populate ChromaDB with intent examples"""
        try:
            all_examples = []
            all_metadatas = []
            all_ids = []

            # Collect all examples
            for intent, definition in self.intent_definitions.items():
                examples = definition["examples"]
                for i, example in enumerate(examples):
                    all_examples.append(example)
                    all_metadatas.append({"intent": intent})
                    all_ids.append(f"{intent}_{i}")

            # Generate embeddings
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: self.model.encode(all_examples)
            )

            # Add to ChromaDB
            self.intent_collection.add(
                embeddings=embeddings.tolist(),
                documents=all_examples,
                metadatas=all_metadatas,
                ids=all_ids
            )

            logger.info("Populated ChromaDB with intent examples",
                       total_examples=len(all_examples))

        except Exception as e:
            logger.error("Failed to populate ChromaDB", error=str(e))
            raise

    async def _initialize_fallback_embeddings(self):
        """Initialize fallback embeddings when ChromaDB is not available"""
        try:
            logger.info("Initializing fallback embeddings")

            loop = asyncio.get_event_loop()

            for intent, definition in self.intent_definitions.items():
                examples = definition["examples"]
                embeddings = await loop.run_in_executor(
                    None, lambda ex=examples: self.model.encode(ex)
                )
                self.fallback_embeddings[intent] = {
                    "examples": examples,
                    "embeddings": embeddings
                }

            logger.info("Fallback embeddings initialized")

        except Exception as e:
            logger.error("Failed to initialize fallback embeddings", error=str(e))
            raise

    async def classify_intent(self, user_input: str, n_results: int = 5) -> SemanticMatch:
        """
        Classify user intent using semantic similarity

        Args:
            user_input: The user's input text
            n_results: Number of similar examples to consider

        Returns:
            SemanticMatch with intent and confidence
        """
        try:
            if not self.model:
                raise RuntimeError("Semantic intent matcher not initialized")

            if self.use_chromadb and self.intent_collection:
                return await self._classify_with_chromadb(user_input, n_results)
            else:
                return await self._classify_with_fallback(user_input)

        except Exception as e:
            logger.error("Error in semantic intent classification", error=str(e))
            return SemanticMatch(
                intent="help",
                confidence=0.1,
                alternatives=[],
                semantic_similarity=0.0,
                matched_example=""
            )

    async def _classify_with_chromadb(self, user_input: str, n_results: int) -> SemanticMatch:
        """Classify intent using ChromaDB vector search"""
        try:
            # Generate embedding for user input
            loop = asyncio.get_event_loop()
            query_embedding = await loop.run_in_executor(
                None, lambda: self.model.encode([user_input])
            )

            # Query ChromaDB for similar examples
            results = self.intent_collection.query(
                query_embeddings=query_embedding.tolist(),
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )

            if not results["metadatas"] or not results["metadatas"][0]:
                return SemanticMatch(
                    intent="help",
                    confidence=0.1,
                    alternatives=[],
                    semantic_similarity=0.0,
                    matched_example=""
                )

            # Aggregate results by intent
            intent_scores = {}
            best_match_example = ""
            best_similarity = 0.0

            for metadata, document, distance in zip(
                results["metadatas"][0],
                results["documents"][0],
                results["distances"][0]
            ):
                intent = metadata["intent"]
                similarity = 1 - distance  # Convert distance to similarity

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_example = document

                if intent not in intent_scores:
                    intent_scores[intent] = []
                intent_scores[intent].append(similarity)

            # Calculate average confidence per intent
            final_scores = {}
            for intent, scores in intent_scores.items():
                # Use weighted average favoring higher scores
                weights = np.exp(np.array(scores))  # Exponential weighting
                final_scores[intent] = np.average(scores, weights=weights)

            # Get best intent and alternatives
            sorted_intents = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
            best_intent, best_confidence = sorted_intents[0]
            alternatives = sorted_intents[1:4]  # Top 3 alternatives

            return SemanticMatch(
                intent=best_intent,
                confidence=float(best_confidence),
                alternatives=[(intent, float(conf)) for intent, conf in alternatives],
                semantic_similarity=float(best_similarity),
                matched_example=best_match_example
            )

        except Exception as e:
            logger.error("ChromaDB classification failed", error=str(e))
            raise

    async def _classify_with_fallback(self, user_input: str) -> SemanticMatch:
        """Classify intent using fallback embeddings"""
        try:
            loop = asyncio.get_event_loop()
            user_embedding = await loop.run_in_executor(
                None, lambda: self.model.encode([user_input])
            )

            intent_scores = {}
            best_match_example = ""
            best_similarity = 0.0

            for intent, data in self.fallback_embeddings.items():
                examples = data["examples"]
                embeddings = data["embeddings"]

                # Calculate similarities
                from sklearn.metrics.pairwise import cosine_similarity
                similarities = cosine_similarity(user_embedding, embeddings)[0]

                # Find best match for this intent
                max_idx = similarities.argmax()
                max_similarity = similarities[max_idx]

                if max_similarity > best_similarity:
                    best_similarity = max_similarity
                    best_match_example = examples[max_idx]

                # Calculate intent score (average of top similarities)
                top_similarities = np.sort(similarities)[-3:]  # Top 3
                intent_scores[intent] = np.mean(top_similarities)

            # Get best intent and alternatives
            sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
            best_intent, best_confidence = sorted_intents[0]
            alternatives = sorted_intents[1:4]

            return SemanticMatch(
                intent=best_intent,
                confidence=float(best_confidence),
                alternatives=[(intent, float(conf)) for intent, conf in alternatives],
                semantic_similarity=float(best_similarity),
                matched_example=best_match_example
            )

        except Exception as e:
            logger.error("Fallback classification failed", error=str(e))
            raise

    async def add_training_example(self, user_input: str, correct_intent: str):
        """Add a new training example for continuous learning"""
        try:
            if self.use_chromadb and self.intent_collection:
                # Generate embedding
                loop = asyncio.get_event_loop()
                embedding = await loop.run_in_executor(
                    None, lambda: self.model.encode([user_input])
                )

                # Add to ChromaDB
                example_id = f"{correct_intent}_user_{len(self.intent_definitions[correct_intent]['examples'])}"
                self.intent_collection.add(
                    embeddings=embedding.tolist(),
                    documents=[user_input],
                    metadatas=[{"intent": correct_intent}],
                    ids=[example_id]
                )

                logger.info("Added training example",
                           input=user_input, intent=correct_intent)
            else:
                # Add to fallback embeddings
                if correct_intent in self.fallback_embeddings:
                    self.fallback_embeddings[correct_intent]["examples"].append(user_input)
                    # Re-compute embeddings (expensive, but ensures consistency)
                    await self._recompute_fallback_embeddings(correct_intent)

        except Exception as e:
            logger.error("Failed to add training example", error=str(e))

    async def _recompute_fallback_embeddings(self, intent: str):
        """Recompute fallback embeddings for a specific intent"""
        try:
            examples = self.fallback_embeddings[intent]["examples"]
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: self.model.encode(examples)
            )
            self.fallback_embeddings[intent]["embeddings"] = embeddings

        except Exception as e:
            logger.error("Failed to recompute fallback embeddings", error=str(e))

    def get_supported_intents(self) -> List[str]:
        """Get list of supported intents"""
        return list(self.intent_definitions.keys())

    def get_intent_description(self, intent: str) -> str:
        """Get description for a specific intent"""
        return self.intent_definitions.get(intent, {}).get("description", "Unknown intent")