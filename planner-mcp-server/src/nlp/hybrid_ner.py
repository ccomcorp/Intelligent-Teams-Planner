"""
Hybrid Named Entity Recognition System
Combines semantic similarity, spaCy NER, and high-precision regex patterns
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass
import spacy
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HybridEntity:
    """Enhanced entity with confidence and extraction method"""
    type: str
    value: str
    confidence: float
    start_pos: int
    end_pos: int
    raw_text: str
    extraction_method: str  # 'semantic', 'spacy', 'regex'
    context: Optional[str] = None


@dataclass
class HybridEntityResult:
    """Result of hybrid entity extraction"""
    entities: List[HybridEntity]
    cleaned_text: str
    metadata: Dict[str, Any]


class HybridNER:
    """
    Modern hybrid NER system combining multiple approaches:
    1. Semantic similarity for task titles and descriptions
    2. spaCy transformer models for general entities
    3. High-precision regex for structured data (emails, dates)
    """

    def __init__(self,
                 sentence_model_name: str = "paraphrase-multilingual-mpnet-base-v2",
                 spacy_model_name: str = "en_core_web_sm"):
        self.sentence_model_name = sentence_model_name
        self.spacy_model_name = spacy_model_name
        self.sentence_model: Optional[SentenceTransformer] = None
        self.nlp: Optional[spacy.Language] = None

        # High-precision regex patterns for structured data
        self.structured_patterns = {
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "URL": r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?',
            "PHONE": r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',
            "DATE_ISO": r'\b\d{4}-\d{2}-\d{2}\b',
            "TIME": r'\b(?:[01]?[0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?\b',
            "ASSIGNEE_NAME": r'(?:assigned?\s+to\s+|tasks?\s+for\s+|delegate\s+to\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        }

        # Semantic examples for domain-specific entities
        self.semantic_examples = {
            "TASK_TITLE": [
                "configure ssl certificates",
                "update website content",
                "review quarterly budget",
                "prepare client presentation",
                "setup development environment",
                "configure ssl on ais for all sites",
                "update database schema",
                "implement authentication system",
                "deploy to production server",
                "fix login bug",
                "create user documentation",
                "setup monitoring dashboard",
                "backup database",
                "optimize performance",
                "security audit"
            ],
            "PROJECT_NAME": [
                "website redesign project",
                "mobile app development",
                "database migration",
                "security upgrade",
                "performance optimization",
                "user interface update",
                "api integration",
                "cloud migration",
                "backup system",
                "monitoring setup"
            ],
            "SKILL": [
                "python programming",
                "javascript development",
                "database administration",
                "system administration",
                "project management",
                "ui/ux design",
                "security analysis",
                "devops engineering"
            ],
            "ASSIGNEE": [
                "angel",
                "john",
                "sarah",
                "mike",
                "lisa",
                "david",
                "emily",
                "alex",
                "jordan",
                "chris",
                "admin",
                "manager",
                "developer",
                "analyst"
            ]
        }

    async def initialize(self):
        """Initialize all NER components"""
        try:
            logger.info("Initializing hybrid NER system")

            # Initialize models in parallel
            await asyncio.gather(
                self._initialize_sentence_model(),
                self._initialize_spacy_model()
            )

            logger.info("Hybrid NER system initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize hybrid NER", error=str(e))
            raise

    async def _initialize_sentence_model(self):
        """Initialize sentence transformer model"""
        try:
            loop = asyncio.get_event_loop()
            self.sentence_model = await loop.run_in_executor(
                None, lambda: SentenceTransformer(self.sentence_model_name)
            )
            logger.info("Sentence transformer model loaded", model=self.sentence_model_name)
        except Exception as e:
            logger.error("Failed to load sentence transformer", error=str(e))
            raise

    async def _initialize_spacy_model(self):
        """Initialize spaCy model"""
        try:
            loop = asyncio.get_event_loop()
            self.nlp = await loop.run_in_executor(
                None, lambda: spacy.load(self.spacy_model_name)
            )
            logger.info("spaCy model loaded", model=self.spacy_model_name)
        except Exception as e:
            logger.warning("Failed to load spaCy model, using fallback", error=str(e))
            # Try fallback to basic English model
            try:
                self.nlp = await loop.run_in_executor(
                    None, lambda: spacy.load("en_core_web_sm")
                )
                logger.info("Loaded fallback spaCy model")
            except:
                logger.error("All spaCy models failed to load")
                self.nlp = None

    async def extract_entities(self, text: str, context: Optional[Dict[str, Any]] = None) -> HybridEntityResult:
        """
        Extract entities using hybrid approach

        Args:
            text: Input text to analyze
            context: Additional context for entity extraction

        Returns:
            HybridEntityResult with extracted entities
        """
        try:
            if not self.sentence_model:
                raise RuntimeError("Hybrid NER not initialized")

            start_time = asyncio.get_event_loop().time()

            # Run all extraction methods in parallel
            extraction_tasks = [
                self._extract_structured_entities(text),
                self._extract_semantic_entities(text),
            ]

            if self.nlp:
                extraction_tasks.append(self._extract_spacy_entities(text))

            entity_lists = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Combine and deduplicate entities
            all_entities = []
            for entity_list in entity_lists:
                if isinstance(entity_list, list):
                    all_entities.extend(entity_list)
                else:
                    logger.warning("Entity extraction method failed", error=str(entity_list))

            # Deduplicate and rank entities
            final_entities = self._deduplicate_and_rank_entities(all_entities)

            # Create cleaned text
            cleaned_text = self._create_cleaned_text(text, final_entities)

            processing_time = asyncio.get_event_loop().time() - start_time

            return HybridEntityResult(
                entities=final_entities,
                cleaned_text=cleaned_text,
                metadata={
                    "processing_time": processing_time,
                    "extraction_methods": ["structured", "semantic", "spacy"] if self.nlp else ["structured", "semantic"],
                    "total_entities": len(final_entities),
                    "entity_types": list(set(e.type for e in final_entities))
                }
            )

        except Exception as e:
            logger.error("Error in hybrid entity extraction", error=str(e))
            return HybridEntityResult(
                entities=[],
                cleaned_text=text,
                metadata={"error": str(e)}
            )

    async def _extract_structured_entities(self, text: str) -> List[HybridEntity]:
        """Extract structured entities using high-precision regex"""
        entities = []

        for entity_type, pattern in self.structured_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if entity_type == "ASSIGNEE_NAME":
                    # Extract just the name part (group 1) and make it an ASSIGNEE
                    assignee_name = match.group(1) if match.groups() else match.group(0)
                    entities.append(HybridEntity(
                        type="ASSIGNEE",
                        value=assignee_name,
                        confidence=0.95,
                        start_pos=match.start(1) if match.groups() else match.start(),
                        end_pos=match.end(1) if match.groups() else match.end(),
                        raw_text=assignee_name,
                        extraction_method="regex"
                    ))
                else:
                    entities.append(HybridEntity(
                        type=entity_type,
                        value=match.group(0),
                        confidence=0.95,  # High confidence for structured patterns
                        start_pos=match.start(),
                        end_pos=match.end(),
                        raw_text=match.group(0),
                        extraction_method="regex"
                    ))

        return entities

    async def _extract_semantic_entities(self, text: str) -> List[HybridEntity]:
        """Extract entities using semantic similarity"""
        entities = []

        try:
            # Extract potential entity candidates
            candidates = self._extract_entity_candidates(text)

            if not candidates:
                return entities

            # Encode candidates
            loop = asyncio.get_event_loop()
            candidate_embeddings = await loop.run_in_executor(
                None, lambda: self.sentence_model.encode(candidates)
            )

            # Check similarity against semantic examples
            for entity_type, examples in self.semantic_examples.items():
                example_embeddings = await loop.run_in_executor(
                    None, lambda ex=examples: self.sentence_model.encode(ex)
                )

                # Calculate similarities
                similarities = cosine_similarity(candidate_embeddings, example_embeddings)

                for i, candidate in enumerate(candidates):
                    max_similarity = similarities[i].max()

                    if max_similarity > 0.7:  # Similarity threshold
                        start_pos = text.lower().find(candidate.lower())
                        if start_pos != -1:
                            entities.append(HybridEntity(
                                type=entity_type,
                                value=candidate,
                                confidence=float(max_similarity),
                                start_pos=start_pos,
                                end_pos=start_pos + len(candidate),
                                raw_text=candidate,
                                extraction_method="semantic"
                            ))

        except Exception as e:
            logger.error("Semantic entity extraction failed", error=str(e))

        return entities

    async def _extract_spacy_entities(self, text: str) -> List[HybridEntity]:
        """Extract entities using spaCy NER"""
        entities = []

        if not self.nlp:
            return entities

        try:
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, lambda: self.nlp(text))

            for ent in doc.ents:
                # Map spaCy entity types to our types
                entity_type = self._map_spacy_entity_type(ent.label_)
                if entity_type:
                    entities.append(HybridEntity(
                        type=entity_type,
                        value=ent.text,
                        confidence=0.8,  # Default confidence for spaCy
                        start_pos=ent.start_char,
                        end_pos=ent.end_char,
                        raw_text=ent.text,
                        extraction_method="spacy",
                        context=ent.sent.text if ent.sent else None
                    ))

        except Exception as e:
            logger.error("spaCy entity extraction failed", error=str(e))

        return entities

    def _extract_entity_candidates(self, text: str) -> List[str]:
        """Extract potential entity candidates from text"""
        candidates = []

        # Extract quoted strings
        quoted_patterns = [
            r'"([^"]+)"',  # Double quotes
            r"'([^']+)'",  # Single quotes
        ]

        for pattern in quoted_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                candidates.append(match.group(1))

        # Extract phrases between common prepositions
        phrase_patterns = [
            r'(?:configure|setup|install|update|create|build|deploy)\s+([^,\.;]+)',
            r'(?:task|project|assignment):\s*([^,\.;]+)',
            r'(?:work on|complete|finish)\s+([^,\.;]+)',
        ]

        for pattern in phrase_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                candidate = match.group(1).strip()
                if len(candidate) > 3 and len(candidate) < 100:  # Reasonable length
                    candidates.append(candidate)

        # Extract capitalized phrases (potential proper nouns)
        caps_pattern = r'\b[A-Z][A-Za-z\s]{2,30}\b'
        caps_matches = re.finditer(caps_pattern, text)
        for match in caps_matches:
            candidate = match.group(0).strip()
            if len(candidate.split()) <= 6:  # Not too long
                candidates.append(candidate)

        return list(set(candidates))  # Remove duplicates

    def _map_spacy_entity_type(self, spacy_label: str) -> Optional[str]:
        """Map spaCy entity labels to our entity types"""
        mapping = {
            "PERSON": "ASSIGNEE",
            "ORG": "ORGANIZATION",
            "GPE": "LOCATION",
            "DATE": "DATE",
            "TIME": "TIME",
            "MONEY": "MONEY",
            "PERCENT": "PERCENTAGE",
            "CARDINAL": "NUMBER",
            "ORDINAL": "NUMBER"
        }
        return mapping.get(spacy_label)

    def _deduplicate_and_rank_entities(self, entities: List[HybridEntity]) -> List[HybridEntity]:
        """Deduplicate overlapping entities and rank by confidence"""
        if not entities:
            return []

        # Sort by confidence (descending)
        entities.sort(key=lambda e: e.confidence, reverse=True)

        final_entities = []
        used_positions = set()

        for entity in entities:
            # Check for overlap with existing entities
            entity_positions = set(range(entity.start_pos, entity.end_pos))

            if not entity_positions.intersection(used_positions):
                final_entities.append(entity)
                used_positions.update(entity_positions)

        # Sort final entities by position
        final_entities.sort(key=lambda e: e.start_pos)

        return final_entities

    def _create_cleaned_text(self, text: str, entities: List[HybridEntity]) -> str:
        """Create cleaned text with entity placeholders"""
        cleaned = text

        # Sort entities by position (reverse order to maintain positions)
        entities_sorted = sorted(entities, key=lambda e: e.start_pos, reverse=True)

        for entity in entities_sorted:
            placeholder = f"[{entity.type}]"
            cleaned = (cleaned[:entity.start_pos] +
                      placeholder +
                      cleaned[entity.end_pos:])

        return cleaned

    async def extract_assignment_entities(self, text: str) -> Dict[str, Any]:
        """
        Specialized extraction for assignment operations

        Args:
            text: Input text containing assignment information

        Returns:
            Dictionary with extracted assignment entities
        """
        try:
            # Extract all entities
            result = await self.extract_entities(text)

            assignment_info = {}

            # Find assignees (emails or names)
            emails = [e.value for e in result.entities if e.type == "EMAIL"]
            assignees = [e.value for e in result.entities if e.type == "ASSIGNEE"]

            if emails:
                assignment_info["assignee"] = emails[0]  # Take first email
            elif assignees:
                assignment_info["assignee"] = assignees[0]  # Take first assignee name

            # Find task titles
            task_titles = [e.value for e in result.entities if e.type == "TASK_TITLE"]
            if task_titles:
                assignment_info["task_title"] = task_titles[0]

            # If no semantic task title found, look for quoted strings
            if "task_title" not in assignment_info:
                quoted_strings = re.findall(r'["\']([^"\']+)["\']', text)
                if quoted_strings:
                    assignment_info["task_title"] = quoted_strings[0]

            # Extract action type from text
            assignment_patterns = [
                (r'\bassign\b.*\bto\b', "assign_existing"),
                (r'\bcreate\b.*\band\b.*\bassign\b', "create_and_assign"),
                (r'\bmake\b.*\bfor\b', "create_and_assign"),
                (r'\bdelegate\b', "assign_existing")
            ]

            for pattern, action_type in assignment_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    assignment_info["action_type"] = action_type
                    break

            # Calculate confidence based on extracted entities
            confidence = 0.0
            if "assignee" in assignment_info:
                confidence += 0.4
            if "task_title" in assignment_info:
                confidence += 0.4
            if "action_type" in assignment_info:
                confidence += 0.2

            assignment_info["confidence"] = confidence
            assignment_info["entities"] = result.entities

            return assignment_info

        except Exception as e:
            logger.error("Assignment entity extraction failed", error=str(e))
            return {"confidence": 0.0, "entities": []}

    def get_entity_types(self) -> List[str]:
        """Get all supported entity types"""
        structured_types = list(self.structured_patterns.keys())
        semantic_types = list(self.semantic_examples.keys())
        spacy_types = ["ASSIGNEE", "ORGANIZATION", "LOCATION", "DATE", "TIME", "MONEY", "PERCENTAGE", "NUMBER"]

        return list(set(structured_types + semantic_types + spacy_types))