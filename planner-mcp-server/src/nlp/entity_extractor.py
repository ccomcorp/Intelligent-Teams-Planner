"""
Named Entity Recognition for Task Management
Story 1.3 Task 1: Entity extraction for task parameters
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timezone
import spacy
from spacy.lang.en import English
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedEntity:
    """Represents an extracted entity"""
    type: str
    value: str
    confidence: float
    start_pos: int
    end_pos: int
    raw_text: str


@dataclass
class EntityExtractionResult:
    """Result of entity extraction"""
    entities: List[ExtractedEntity]
    cleaned_text: str  # Text with entities removed/replaced
    metadata: Dict[str, Any]


class EntityExtractor:
    """
    Named Entity Recognition for Microsoft Planner task parameters
    Extracts task titles, dates, assignees, plan names, priorities, etc.
    """

    def __init__(self, model_name: str = "en_core_web_sm"):
        self.model_name = model_name
        self.nlp: Optional[spacy.Language] = None

        # Define entity patterns and rules
        self.entity_patterns = {
            "TASK_TITLE": {
                "patterns": [
                    r'"([^"]+)"',  # Quoted strings
                    r"'([^']+)'",  # Single quoted strings
                    r"(?:task|assignment|todo)(?:\s+(?:to|for|about))?\s+([^,\.]+)",  # task to...
                    r"(?:create|add|make)\s+(?:a\s+)?(?:task\s+)?(?:to\s+)?([^,\.]+)",  # create task to...
                ],
                "context_words": ["task", "assignment", "todo", "work", "item"]
            },
            "DUE_DATE": {
                "patterns": [
                    r"(?:due|deadline|by|until|before)\s+(.+?)(?:\s|$|,|\.|;)",
                    r"(?:next|this|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                    r"(?:in\s+)?(\d+)\s+(day|days|week|weeks|month|months)",
                    r"(today|tomorrow|yesterday)",
                    r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",  # Date formats
                    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}",
                ],
                "context_words": ["due", "deadline", "by", "until", "before", "schedule"]
            },
            "ASSIGNEE": {
                "patterns": [
                    r"(?:assign|give|delegate|transfer)(?:\s+(?:to|it\s+to))?\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
                    r"(?:for|by)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
                    r"@([A-Za-z0-9\._-]+)",  # @mentions
                    r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",  # Email addresses
                ],
                "context_words": ["assign", "assignee", "for", "by", "delegate", "give"]
            },
            "PLAN_NAME": {
                "patterns": [
                    r"(?:plan|project|board)\s+([^,\.]+)",
                    r"(?:in|to|for)\s+(?:the\s+)?([A-Z][^,\.]*?)(?:\s+(?:plan|project|board))",
                    r"([A-Z][a-zA-Z\s]+)\s+(?:plan|project|board)",
                ],
                "context_words": ["plan", "project", "board", "workspace"]
            },
            "PRIORITY": {
                "patterns": [
                    r"(?:priority|importance|urgency)\s+(high|medium|low|urgent|normal|critical)",
                    r"(high|medium|low|urgent|normal|critical)\s+priority",
                    r"mark\s+(?:as\s+)?(high|medium|low|urgent|normal|critical)",
                ],
                "context_words": ["priority", "urgent", "important", "critical"]
            },
            "STATUS": {
                "patterns": [
                    r"(?:status|state)\s+(not\s+started|in\s+progress|completed|done|cancelled)",
                    r"mark\s+(?:as\s+)?(not\s+started|in\s+progress|completed|done|cancelled)",
                    r"set\s+(?:to\s+)?(not\s+started|in\s+progress|completed|done|cancelled)",
                ],
                "context_words": ["status", "state", "complete", "done", "progress"]
            },
            "QUANTITY": {
                "patterns": [
                    r"(\d+)\s+(?:tasks|items|assignments)",
                    r"(one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:tasks|items)",
                    r"(?:create|add|make)\s+(\d+)",
                ],
                "context_words": ["tasks", "items", "multiple", "batch"]
            }
        }

        # Priority mappings
        self.priority_mappings = {
            "urgent": "high",
            "critical": "high",
            "important": "high",
            "normal": "medium",
            "low": "low"
        }

        # Status mappings
        self.status_mappings = {
            "done": "completed",
            "finished": "completed",
            "cancelled": "cancelled",
            "canceled": "cancelled",
            "not started": "not_started",
            "in progress": "in_progress",
            "ongoing": "in_progress"
        }

    async def initialize(self):
        """Initialize the spaCy model"""
        try:
            logger.info("Initializing entity extractor", model=self.model_name)

            # Load spaCy model in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            self.nlp = await loop.run_in_executor(
                None,
                lambda: spacy.load(self.model_name)
            )

            # Add custom pipeline components if needed
            await self._setup_custom_components()

            logger.info("Entity extractor initialized successfully")

        except OSError as e:
            logger.error(f"spaCy model '{self.model_name}' not found. "
                        f"Please install it using: python -m spacy download {self.model_name}")
            raise
        except Exception as e:
            logger.error("Failed to initialize entity extractor", error=str(e))
            raise

    async def _setup_custom_components(self):
        """Set up custom spaCy pipeline components for task-specific entities"""
        try:
            # Add custom entity patterns to the matcher
            from spacy.matcher import Matcher
            from spacy.util import filter_spans

            if not hasattr(self.nlp, 'custom_matcher'):
                self.nlp.custom_matcher = Matcher(self.nlp.vocab)

            # Add patterns for task-specific entities
            # (This could be expanded with more sophisticated patterns)

            logger.debug("Custom spaCy components set up successfully")

        except Exception as e:
            logger.warning("Failed to set up custom spaCy components", error=str(e))

    async def extract_entities(self, text: str, context: Optional[Dict[str, Any]] = None) -> EntityExtractionResult:
        """
        Extract entities from natural language text

        Args:
            text: Input text to process
            context: Optional context information for better extraction

        Returns:
            EntityExtractionResult with extracted entities
        """
        try:
            if not self.nlp:
                raise RuntimeError("Entity extractor not initialized. Call initialize() first.")

            entities = []
            cleaned_text = text
            metadata = {"original_length": len(text)}

            # First, extract using spaCy NER
            spacy_entities = await self._extract_with_spacy(text)
            entities.extend(spacy_entities)

            # Then, extract using custom patterns
            pattern_entities = await self._extract_with_patterns(text)
            entities.extend(pattern_entities)

            # Remove duplicates and overlapping entities
            entities = self._deduplicate_entities(entities)

            # Post-process and validate entities
            entities = self._post_process_entities(entities, context)

            # Create cleaned text with entities removed/replaced
            cleaned_text = self._create_cleaned_text(text, entities)

            metadata.update({
                "entities_found": len(entities),
                "extraction_methods": ["spacy", "patterns"],
                "processed_length": len(cleaned_text)
            })

            logger.debug("Entity extraction completed",
                        num_entities=len(entities),
                        entity_types=[e.type for e in entities])

            return EntityExtractionResult(
                entities=entities,
                cleaned_text=cleaned_text,
                metadata=metadata
            )

        except Exception as e:
            logger.error("Error extracting entities", error=str(e), text=text[:100])
            # Return empty result on error
            return EntityExtractionResult(
                entities=[],
                cleaned_text=text,
                metadata={"error": str(e)}
            )

    async def _extract_with_spacy(self, text: str) -> List[ExtractedEntity]:
        """Extract entities using spaCy NER"""
        try:
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(None, lambda: self.nlp(text))

            entities = []
            for ent in doc.ents:
                # Map spaCy entity types to our entity types
                entity_type = self._map_spacy_entity_type(ent.label_)
                if entity_type:
                    entities.append(ExtractedEntity(
                        type=entity_type,
                        value=ent.text.strip(),
                        confidence=0.8,  # Default confidence for spaCy entities
                        start_pos=ent.start_char,
                        end_pos=ent.end_char,
                        raw_text=ent.text
                    ))

            return entities

        except Exception as e:
            logger.warning("Error in spaCy entity extraction", error=str(e))
            return []

    def _map_spacy_entity_type(self, spacy_label: str) -> Optional[str]:
        """Map spaCy entity labels to our entity types"""
        mapping = {
            "PERSON": "ASSIGNEE",
            "ORG": "PLAN_NAME",
            "DATE": "DUE_DATE",
            "TIME": "DUE_DATE",
            "CARDINAL": "QUANTITY",
            "ORDINAL": "QUANTITY"
        }
        return mapping.get(spacy_label)

    async def _extract_with_patterns(self, text: str) -> List[ExtractedEntity]:
        """Extract entities using regex patterns"""
        entities = []

        for entity_type, config in self.entity_patterns.items():
            for pattern in config["patterns"]:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # Determine which group contains the entity value
                    value = match.group(1) if match.groups() else match.group(0)
                    value = value.strip()

                    if value and len(value) > 1:  # Basic validation
                        # Calculate confidence based on pattern specificity and context
                        confidence = self._calculate_pattern_confidence(
                            entity_type, pattern, value, text, match.start()
                        )

                        entities.append(ExtractedEntity(
                            type=entity_type,
                            value=value,
                            confidence=confidence,
                            start_pos=match.start(),
                            end_pos=match.end(),
                            raw_text=match.group(0)
                        ))

        return entities

    def _calculate_pattern_confidence(self, entity_type: str, pattern: str, value: str,
                                    full_text: str, position: int) -> float:
        """Calculate confidence score for pattern-based extraction"""
        base_confidence = 0.6

        # Increase confidence for quoted strings
        if pattern.startswith(r'"') or pattern.startswith(r"'"):
            base_confidence += 0.2

        # Check for context words nearby
        context_words = self.entity_patterns[entity_type]["context_words"]
        text_before = full_text[max(0, position - 20):position].lower()
        text_after = full_text[position:position + 20].lower()

        context_found = any(word in text_before or word in text_after
                          for word in context_words)
        if context_found:
            base_confidence += 0.1

        # Validate entity value
        if entity_type == "ASSIGNEE" and "@" in value:
            base_confidence += 0.1  # Email addresses are more reliable

        if entity_type == "DUE_DATE" and any(word in value.lower()
                                           for word in ["today", "tomorrow", "next", "this"]):
            base_confidence += 0.1  # Relative dates are clear

        return min(base_confidence, 0.95)  # Cap at 95%

    def _deduplicate_entities(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        """Remove duplicate and overlapping entities, keeping the highest confidence ones"""
        if not entities:
            return entities

        # Sort by start position
        entities.sort(key=lambda e: e.start_pos)

        deduplicated = []
        for entity in entities:
            # Check for overlaps with already selected entities
            overlaps = any(
                not (entity.end_pos <= existing.start_pos or entity.start_pos >= existing.end_pos)
                for existing in deduplicated
            )

            if not overlaps:
                deduplicated.append(entity)
            else:
                # If there's an overlap, keep the one with higher confidence
                # Find overlapping entities and compare
                overlapping = [e for e in deduplicated
                             if not (entity.end_pos <= e.start_pos or entity.start_pos >= e.end_pos)]

                if overlapping:
                    max_existing_confidence = max(e.confidence for e in overlapping)
                    if entity.confidence > max_existing_confidence:
                        # Remove overlapping entities and add this one
                        deduplicated = [e for e in deduplicated if e not in overlapping]
                        deduplicated.append(entity)

        return deduplicated

    def _post_process_entities(self, entities: List[ExtractedEntity],
                             context: Optional[Dict[str, Any]] = None) -> List[ExtractedEntity]:
        """Post-process and validate extracted entities"""
        processed = []

        for entity in entities:
            # Normalize entity values
            if entity.type == "PRIORITY":
                entity.value = self.priority_mappings.get(entity.value.lower(), entity.value.lower())

            elif entity.type == "STATUS":
                entity.value = self.status_mappings.get(entity.value.lower(), entity.value.lower())

            elif entity.type == "ASSIGNEE":
                # Clean up assignee names
                entity.value = self._clean_assignee_name(entity.value)

            elif entity.type == "TASK_TITLE":
                # Clean up task titles
                entity.value = self._clean_task_title(entity.value)

            elif entity.type == "QUANTITY":
                # Convert word numbers to digits
                entity.value = self._normalize_quantity(entity.value)

            # Validate entity value
            if self._validate_entity(entity):
                processed.append(entity)

        return processed

    def _clean_assignee_name(self, name: str) -> str:
        """Clean up assignee names"""
        # Remove common prefixes/suffixes
        name = re.sub(r'^(to|for|by)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+(please|pls)$', '', name, flags=re.IGNORECASE)
        return name.strip()

    def _clean_task_title(self, title: str) -> str:
        """Clean up task titles"""
        # Remove common prefixes
        title = re.sub(r'^(task\s+to\s+|create\s+|add\s+|make\s+)', '', title, flags=re.IGNORECASE)
        return title.strip()

    def _normalize_quantity(self, quantity: str) -> str:
        """Convert word numbers to digits"""
        word_to_num = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"
        }
        return word_to_num.get(quantity.lower(), quantity)

    def _validate_entity(self, entity: ExtractedEntity) -> bool:
        """Validate if an entity value is reasonable"""
        if not entity.value or len(entity.value.strip()) == 0:
            return False

        if entity.type == "ASSIGNEE":
            # Assignee should be a reasonable name or email
            return len(entity.value) >= 2 and not entity.value.isdigit()

        elif entity.type == "TASK_TITLE":
            # Task title should be meaningful
            return len(entity.value) >= 3 and not entity.value.isdigit()

        elif entity.type == "QUANTITY":
            # Quantity should be a number
            return entity.value.isdigit() or entity.value in ["one", "two", "three", "four", "five"]

        return True

    def _create_cleaned_text(self, original_text: str, entities: List[ExtractedEntity]) -> str:
        """Create cleaned text with entities removed or replaced with placeholders"""
        if not entities:
            return original_text

        # Sort entities by position (reverse order to maintain positions)
        sorted_entities = sorted(entities, key=lambda e: e.start_pos, reverse=True)

        cleaned = original_text
        for entity in sorted_entities:
            # Replace entity with a placeholder or remove it
            placeholder = f"[{entity.type}]"
            cleaned = cleaned[:entity.start_pos] + placeholder + cleaned[entity.end_pos:]

        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned

    def get_entities_by_type(self, entities: List[ExtractedEntity], entity_type: str) -> List[ExtractedEntity]:
        """Get all entities of a specific type"""
        return [e for e in entities if e.type == entity_type]

    def get_entity_values_by_type(self, entities: List[ExtractedEntity], entity_type: str) -> List[str]:
        """Get all entity values of a specific type"""
        return [e.value for e in entities if e.type == entity_type]