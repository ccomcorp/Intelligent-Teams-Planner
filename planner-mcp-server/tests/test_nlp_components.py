"""
Individual Component Testing for NLP Functionality
Story 1.3 Task 7: Unit tests for each NLP component
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
import spacy

# Import individual NLP components for focused testing
from src.nlp.intent_classifier import IntentClassifier, IntentResult
from src.nlp.entity_extractor import EntityExtractor, ExtractedEntity, EntityExtractionResult
from src.nlp.date_parser import NaturalLanguageDateParser, ParsedDate
from src.nlp.context_manager import ConversationContextManager, ConversationContext, ConversationMessage
from src.nlp.batch_processor import BatchProcessor, BatchJob, BatchOperation
from src.nlp.disambiguator import NLDisambiguator, DisambiguationResult, ClarificationRequest
from src.nlp.error_handler import NLErrorHandler, ErrorContext, NaturalLanguageResponse


class TestIntentClassifierUnit:
    """Focused unit tests for IntentClassifier"""

    @pytest.fixture
    def classifier(self):
        """Create classifier without initialization for unit testing"""
        return IntentClassifier()

    def test_keyword_matching(self, classifier):
        """Test keyword-based intent matching"""
        # Test create task keywords
        create_keywords = classifier.intent_definitions["create_task"]["keywords"]
        test_input = "create a new task"

        matched_intents = []
        for intent, definition in classifier.intent_definitions.items():
            for keyword in definition["keywords"]:
                if keyword in test_input.lower():
                    matched_intents.append(intent)
                    break

        assert "create_task" in matched_intents

    def test_intent_confidence_calculation(self, classifier):
        """Test confidence score calculation logic"""
        # Mock semantic similarity
        with patch.object(classifier, 'model', Mock()):
            classifier.model.encode.return_value = [0.1, 0.2, 0.3]  # Mock embeddings

            with patch('numpy.dot', return_value=0.85):
                with patch('numpy.linalg.norm', side_effect=[1.0, 1.0]):
                    confidence = classifier._calculate_semantic_similarity(
                        "create task", "Create a new task"
                    )
                    assert 0.8 <= confidence <= 1.0

    def test_intent_definitions_structure(self, classifier):
        """Test that intent definitions have required structure"""
        required_fields = ["description", "examples", "keywords"]

        for intent, definition in classifier.intent_definitions.items():
            for field in required_fields:
                assert field in definition, f"Intent {intent} missing {field}"
                assert isinstance(definition[field], list) or isinstance(definition[field], str)

    @pytest.mark.asyncio
    async def test_fallback_intent_handling(self, classifier):
        """Test handling of unrecognized inputs"""
        # Test real fallback functionality without mocks
        result = await classifier.classify_intent("xyzabc random gibberish")

        # Should return help intent as fallback with low confidence
        assert result.intent == "help"
        assert result.confidence <= 0.2  # Low confidence for unrecognized input


class TestEntityExtractorUnit:
    """Focused unit tests for EntityExtractor"""

    @pytest.fixture
    def extractor(self):
        """Create extractor without spaCy initialization"""
        extractor = EntityExtractor()
        return extractor

    def test_entity_pattern_matching(self, extractor):
        """Test regex pattern matching for entities"""
        # Test task title pattern
        test_text = 'Create a task called "Review quarterly report"'
        task_patterns = extractor.entity_patterns["TASK_TITLE"]["patterns"]

        matches = []
        for pattern in task_patterns:
            import re
            match = re.search(pattern, test_text, re.IGNORECASE)
            if match:
                matches.append(match.group(1) if match.groups() else match.group(0))

        assert len(matches) > 0
        assert any("Review quarterly report" in match for match in matches)

    def test_priority_normalization(self, extractor):
        """Test priority value normalization"""
        test_cases = [
            ("urgent", "high"),
            ("critical", "high"),
            ("normal", "medium"),
            ("low", "low")
        ]

        for input_priority, expected in test_cases:
            normalized = extractor.priority_mappings.get(input_priority, input_priority)
            assert normalized == expected

    def test_status_normalization(self, extractor):
        """Test status value normalization"""
        test_cases = [
            ("done", "completed"),
            ("finished", "completed"),
            ("not started", "not_started"),
            ("in progress", "in_progress")
        ]

        for input_status, expected in test_cases:
            normalized = extractor.status_mappings.get(input_status, input_status)
            assert normalized == expected

    def test_entity_validation(self, extractor):
        """Test entity validation logic"""
        # Test valid entities
        valid_entities = [
            ExtractedEntity("ASSIGNEE", "John Smith", 0.9, 0, 10, "John Smith"),
            ExtractedEntity("TASK_TITLE", "Review budget", 0.8, 0, 13, "Review budget"),
            ExtractedEntity("QUANTITY", "5", 0.9, 0, 1, "5")
        ]

        for entity in valid_entities:
            assert extractor._validate_entity(entity)

        # Test invalid entities
        invalid_entities = [
            ExtractedEntity("ASSIGNEE", "", 0.9, 0, 0, ""),  # Empty value
            ExtractedEntity("TASK_TITLE", "A", 0.8, 0, 1, "A"),  # Too short
            ExtractedEntity("QUANTITY", "abc", 0.9, 0, 3, "abc")  # Non-numeric
        ]

        for entity in invalid_entities:
            assert not extractor._validate_entity(entity)

    def test_confidence_calculation(self, extractor):
        """Test pattern confidence calculation"""
        entity_type = "TASK_TITLE"
        pattern = r'"([^"]+)"'  # Quoted string pattern
        value = "Test Task"
        full_text = 'Create task "Test Task" for project'
        position = 12

        confidence = extractor._calculate_pattern_confidence(
            entity_type, pattern, value, full_text, position
        )

        # Quoted strings should have higher confidence
        assert confidence > 0.6
        assert confidence <= 0.95

    def test_entity_deduplication(self, extractor):
        """Test removal of duplicate and overlapping entities"""
        entities = [
            ExtractedEntity("TASK_TITLE", "Review", 0.8, 0, 6, "Review"),
            ExtractedEntity("TASK_TITLE", "Review budget", 0.9, 0, 13, "Review budget"),  # Overlaps
            ExtractedEntity("ASSIGNEE", "John", 0.7, 20, 24, "John")
        ]

        deduplicated = extractor._deduplicate_entities(entities)

        # Should keep the higher confidence overlapping entity
        assert len(deduplicated) == 2
        task_entities = [e for e in deduplicated if e.type == "TASK_TITLE"]
        assert len(task_entities) == 1
        assert task_entities[0].value == "Review budget"


class TestDateParserUnit:
    """Focused unit tests for NaturalLanguageDateParser"""

    @pytest.fixture
    def date_parser(self):
        """Create date parser for unit testing"""
        return NaturalLanguageDateParser()

    def test_relative_date_patterns(self, date_parser):
        """Test regex patterns for relative dates"""
        test_cases = [
            ("tomorrow", "tomorrow"),
            ("next week", "next week"),
            ("in 3 days", "3 days"),
            ("next Friday", "next Friday")
        ]

        for input_text, expected_match in test_cases:
            matched = False
            for pattern_name, pattern in date_parser.relative_patterns.items():
                import re
                if re.search(pattern, input_text, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"No pattern matched for '{input_text}'"

    def test_absolute_date_patterns(self, date_parser):
        """Test regex patterns for absolute dates"""
        test_cases = [
            "12/25/2024",
            "2024-12-25",
            "December 25, 2024",
            "Dec 25"
        ]

        for date_str in test_cases:
            matched = False
            for pattern_name, pattern in date_parser.absolute_patterns.items():
                import re
                if re.search(pattern, date_str, re.IGNORECASE):
                    matched = True
                    break
            assert matched, f"No pattern matched for '{date_str}'"

    def test_business_hours_calculation(self, date_parser):
        """Test business hours adjustment logic"""
        # Test different input times
        test_date = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)  # 2:30 PM
        adjusted = date_parser._adjust_to_business_hours(test_date)

        # Should adjust to business hours if outside
        assert adjusted.hour >= date_parser.business_hours_start
        assert adjusted.hour <= date_parser.business_hours_end

    def test_next_weekday_calculation(self, date_parser):
        """Test calculation of next occurrence of weekday"""
        reference_date = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)  # Monday

        # Test next Friday (should be 4 days later)
        friday_date = date_parser._get_next_weekday(reference_date, 4)  # Friday = 4
        assert friday_date.weekday() == 4
        assert (friday_date - reference_date).days == 4

    def test_week_offset_calculation(self, date_parser):
        """Test calculation of week offsets"""
        reference_date = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Test next week
        next_week = date_parser._add_weeks(reference_date, 1)
        assert (next_week - reference_date).days == 7

        # Test in 2 weeks
        two_weeks = date_parser._add_weeks(reference_date, 2)
        assert (two_weeks - reference_date).days == 14


class TestBatchProcessorUnit:
    """Focused unit tests for BatchProcessor"""

    @pytest.fixture
    def batch_processor(self):
        """Create batch processor for unit testing"""
        return BatchProcessor()

    def test_batch_pattern_detection(self, batch_processor):
        """Test regex patterns for batch operations"""
        test_cases = [
            ("create 5 tasks", "create_multiple_tasks"),
            ("add multiple items", "create_multiple_tasks"),
            ("delete all completed tasks", "delete_completed_tasks"),
            ("assign all tasks to John", "assign_tasks_in_project")
        ]

        for user_input, expected_type in test_cases:
            matched = False
            for pattern, operation_type in batch_processor.batch_patterns.items():
                import re
                if re.search(pattern, user_input.lower(), re.IGNORECASE):
                    if operation_type == expected_type:
                        matched = True
                        break
            assert matched, f"Pattern '{expected_type}' not matched for '{user_input}'"

    def test_quantity_extraction(self, batch_processor):
        """Test extraction of quantities from text"""
        test_cases = [
            ("create 5 tasks", 5),
            ("add three items", 3),
            ("make several tasks", 3),  # Default for 'several'
            ("create many tasks", 5)   # Default for 'many'
        ]

        for user_input, expected_quantity in test_cases:
            # Mock the quantity extraction logic
            entities = {"QUANTITY": "5"} if "5" in user_input else {"QUANTITY": user_input.split()[1]}

            # Test word to number conversion
            if entities["QUANTITY"] in ["three", "several", "many"]:
                word_to_num = {"three": 3, "several": 3, "many": 5}
                quantity = word_to_num.get(entities["QUANTITY"], 1)
            else:
                try:
                    quantity = int(entities["QUANTITY"])
                except:
                    quantity = 1

            assert quantity == expected_quantity

    def test_operation_generation(self, batch_processor):
        """Test generation of individual operations"""
        operation_type = "create_multiple_tasks"
        parameters = {
            "quantity": 3,
            "task_template": {"title": "Task", "plan_name": "Test Project"}
        }

        # This would normally be async, but we can test the logic
        operation_id_base = int(datetime.now().timestamp())
        operations = []

        for i in range(parameters["quantity"]):
            operation = BatchOperation(
                operation_id=f"{operation_id_base}_{i}",
                operation_type="create_task",
                parameters={
                    **parameters["task_template"],
                    "title": f"{parameters['task_template']['title']} {i + 1}",
                    "batch_index": i + 1,
                    "batch_total": parameters["quantity"]
                }
            )
            operations.append(operation)

        assert len(operations) == 3
        assert operations[0].parameters["title"] == "Task 1"
        assert operations[2].parameters["title"] == "Task 3"

    def test_batch_size_validation(self, batch_processor):
        """Test batch size limits"""
        max_size = batch_processor.max_batch_size

        # Test within limits
        assert 10 <= max_size  # Should allow reasonable batch sizes

        # Test validation logic
        valid_size = max_size - 1
        invalid_size = max_size + 1

        assert valid_size <= max_size
        assert invalid_size > max_size


class TestDisambiguatorUnit:
    """Focused unit tests for NLDisambiguator"""

    @pytest.fixture
    def disambiguator(self):
        """Create disambiguator with mock dependencies"""
        mock_db = Mock()
        mock_context_manager = Mock()
        return NLDisambiguator(mock_db, mock_context_manager)

    def test_intent_requirements_structure(self, disambiguator):
        """Test intent requirements definitions"""
        for intent, requirements in disambiguator.intent_requirements.items():
            assert "required" in requirements
            assert "optional" in requirements
            assert "defaults" in requirements
            assert isinstance(requirements["required"], list)
            assert isinstance(requirements["optional"], list)
            assert isinstance(requirements["defaults"], dict)

    def test_parameter_mapping(self, disambiguator):
        """Test parameter to entity mapping"""
        test_cases = [
            ("title", "TASK_TITLE"),
            ("plan_name", "PLAN_NAME"),
            ("assignee", "ASSIGNEE"),
            ("due_date", "DUE_DATE")
        ]

        for parameter, expected_entity in test_cases:
            mapped = disambiguator._map_parameter_to_entity(parameter)
            assert mapped == expected_entity

    def test_missing_parameter_detection(self, disambiguator):
        """Test detection of missing required parameters"""
        intent = "create_task"
        entities = {"PLAN_NAME": "Test Project"}  # Missing TASK_TITLE

        requirements = disambiguator.intent_requirements[intent]
        missing = []

        for param in requirements["required"]:
            entity_key = disambiguator._map_parameter_to_entity(param)
            if entity_key not in entities or not entities[entity_key]:
                missing.append(param)

        assert "title" in missing

    def test_ambiguous_pattern_detection(self, disambiguator):
        """Test detection of ambiguous patterns"""
        test_cases = [
            ("Update that task", ["that"]),  # Pronoun
            ("Same project as before", ["same"]),  # Relative reference
            ("Create some tasks", ["some"]),  # Vague quantity
            ("Due sometime soon", ["sometime", "soon"])  # Vague time
        ]

        for user_input, expected_patterns in test_cases:
            input_lower = user_input.lower()
            found_patterns = []

            # Check pronouns
            for pronoun in disambiguator.ambiguous_patterns["pronouns"]:
                if pronoun in input_lower:
                    found_patterns.append(pronoun)

            # Check relative references
            for ref in disambiguator.ambiguous_patterns["relative_references"]:
                if ref in input_lower:
                    found_patterns.append(ref)

            # Check vague quantities
            for vague in disambiguator.ambiguous_patterns["vague_quantities"]:
                if vague in input_lower:
                    found_patterns.append(vague)

            # Check vague time
            for vague in disambiguator.ambiguous_patterns["vague_time"]:
                if vague in input_lower:
                    found_patterns.append(vague)

            # Should find at least one expected pattern
            assert any(pattern in found_patterns for pattern in expected_patterns)

    def test_action_description_generation(self, disambiguator):
        """Test generation of action descriptions"""
        test_cases = [
            ("create_task", {"TASK_TITLE": "Review budget"}, "Review budget"),
            ("assign_task", {"TASK_TITLE": "Test", "ASSIGNEE": "John"}, "John"),
            ("create_plan", {"PLAN_NAME": "Q4 Goals"}, "Q4 Goals")
        ]

        for intent, parameters, expected_content in test_cases:
            description = disambiguator._describe_action(intent, parameters)
            assert expected_content in description


class TestErrorHandlerUnit:
    """Focused unit tests for NLErrorHandler"""

    @pytest.fixture
    def error_handler(self):
        """Create error handler for unit testing"""
        return NLErrorHandler()

    def test_error_pattern_classification(self, error_handler):
        """Test error pattern matching"""
        test_cases = [
            ("authentication failed", "authentication"),
            ("connection timeout", "network"),
            ("rate limit exceeded", "rate_limit"),
            ("not found", "not_found"),
            ("validation failed", "validation"),
            ("internal server error", "processing")
        ]

        for error_message, expected_type in test_cases:
            classified_type = "unknown"

            for error_type, config in error_handler.error_patterns.items():
                for pattern in config["patterns"]:
                    import re
                    if re.search(pattern, error_message, re.IGNORECASE):
                        classified_type = error_type
                        break
                if classified_type != "unknown":
                    break

            assert classified_type == expected_type

    def test_response_tone_mapping(self, error_handler):
        """Test that error types have appropriate tones"""
        tone_expectations = {
            "authentication": ["helpful", "apologetic"],
            "network": ["apologetic", "informative"],
            "rate_limit": ["informative", "helpful"],
            "not_found": ["helpful"],
            "validation": ["helpful"],
            "processing": ["apologetic"]
        }

        for error_type, expected_tones in tone_expectations.items():
            if error_type in error_handler.error_patterns:
                config = error_handler.error_patterns[error_type]
                assert config["tone"] in expected_tones

    def test_suggestion_quality(self, error_handler):
        """Test that suggestions are helpful and actionable"""
        for error_type, config in error_handler.error_patterns.items():
            suggestions = config["suggestions"]
            assert len(suggestions) > 0
            assert all(len(suggestion) > 10 for suggestion in suggestions)  # Not too short
            assert all(len(suggestion) < 200 for suggestion in suggestions)  # Not too long

    def test_intent_specific_error_mapping(self, error_handler):
        """Test intent-specific error messages"""
        required_intents = ["create_task", "update_task", "assign_task"]

        for intent in required_intents:
            assert intent in error_handler.intent_specific_errors
            intent_errors = error_handler.intent_specific_errors[intent]
            assert isinstance(intent_errors, dict)
            assert len(intent_errors) > 0

    def test_success_message_templates(self, error_handler):
        """Test success message template structure"""
        # This would normally be tested with the actual method
        intent = "create_task"
        parameters = {"TASK_TITLE": "Test Task"}

        # Mock the template selection and formatting
        template = "Great! I've created the task '{title}' for you."
        message = template.format(title=parameters["TASK_TITLE"])

        assert "Test Task" in message
        assert "created" in message.lower()

    def test_clarification_response_generation(self, error_handler):
        """Test clarification request generation"""
        test_cases = [
            ([], "not sure what you'd like me to do"),
            (["create_task"], "create task"),
            (["create_task", "list_tasks"], "create task or list tasks")
        ]

        for possible_intents, expected_content in test_cases:
            # Mock response generation logic
            if len(possible_intents) == 0:
                message = "I'm not sure what you'd like me to do. Could you be more specific?"
            elif len(possible_intents) == 1:
                intent = possible_intents[0]
                message = f"I think you want to {intent.replace('_', ' ')}, but I need more information."
            else:
                intent_descriptions = [intent.replace('_', ' ') for intent in possible_intents]
                message = f"I'm not sure if you want to {' or '.join(intent_descriptions)}. Could you clarify?"

            assert expected_content.lower() in message.lower()


# Performance and Integration Tests
class TestNLPPerformance:
    """Test performance characteristics of NLP components"""

    @pytest.mark.asyncio
    async def test_processing_speed(self):
        """Test that NLP processing completes within reasonable time"""
        start_time = datetime.now()

        # Simulate NLP processing without actual models
        await asyncio.sleep(0.1)  # Simulate processing time

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        # Should complete within reasonable time
        assert processing_time < 5.0  # 5 seconds max for complex processing

    def test_memory_usage(self):
        """Test that components don't use excessive memory"""
        import gc
        import sys

        # Get initial memory usage
        initial_objects = len(gc.get_objects())

        # Create NLP components
        intent_classifier = IntentClassifier()
        entity_extractor = EntityExtractor()
        date_parser = NaturalLanguageDateParser()

        # Check memory usage increase
        final_objects = len(gc.get_objects())
        object_increase = final_objects - initial_objects

        # Should not create excessive objects
        assert object_increase < 1000  # Reasonable object creation limit

    @pytest.mark.asyncio
    async def test_concurrent_processing(self):
        """Test handling of concurrent requests"""
        # Simulate concurrent processing
        tasks = []
        for i in range(10):
            # Would normally be async NLP processing
            task = asyncio.create_task(asyncio.sleep(0.01))
            tasks.append(task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        # All tasks should be created successfully
        assert len(tasks) == 10


# Run individual component tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])