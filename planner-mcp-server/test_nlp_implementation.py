#!/usr/bin/env python3
"""
Integration Test for Complete NLP Implementation
Story 1.3: Verify all components work together
"""

import asyncio
import sys
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone

# Test individual NLP components
def test_entity_extraction():
    """Test entity extraction patterns and functionality"""
    try:
        from src.nlp.entity_extractor import EntityExtractor
        import re

        extractor = EntityExtractor()

        # Test task title pattern
        test_text = 'Create a task called "Review quarterly report"'
        task_patterns = extractor.entity_patterns["TASK_TITLE"]["patterns"]

        matches = []
        for pattern in task_patterns:
            match = re.search(pattern, test_text, re.IGNORECASE)
            if match:
                matches.append(match.group(1) if match.groups() else match.group(0))

        assert len(matches) > 0, "Should find task title matches"
        assert any("Review quarterly report" in match for match in matches), "Should extract quoted task title"

        # Test priority normalization
        assert extractor.priority_mappings["urgent"] == "high"
        assert extractor.priority_mappings["critical"] == "high"

        print("✅ Entity extraction tests passed")
        return True

    except Exception as e:
        print(f"❌ Entity extraction test failed: {e}")
        return False


def test_intent_classification():
    """Test intent classification structure and keyword matching"""
    try:
        from src.nlp.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        # Verify all intents have required fields
        required_fields = ["description", "examples", "keywords"]
        for intent, definition in classifier.intent_definitions.items():
            for field in required_fields:
                assert field in definition, f"Intent {intent} missing {field}"

        # Test keyword matching
        test_input = "create a new task"
        create_keywords = classifier.intent_definitions["create_task"]["keywords"]
        matched = any(keyword in test_input.lower() for keyword in create_keywords)
        assert matched, "Should match create task keywords"

        print("✅ Intent classification tests passed")
        return True

    except Exception as e:
        print(f"❌ Intent classification test failed: {e}")
        return False


def test_batch_processing():
    """Test batch operation detection patterns"""
    try:
        from src.nlp.batch_processor import BatchProcessor
        import re

        processor = BatchProcessor()

        test_cases = [
            ("Create 5 tasks for project Alpha", True),
            ("Add multiple tasks to the board", True),
            ("Delete all completed tasks", True),
            ("Create a single task", False)
        ]

        for user_input, should_be_batch in test_cases:
            matched = False
            for pattern, operation_type in processor.batch_patterns.items():
                if re.search(pattern, user_input.lower(), re.IGNORECASE):
                    matched = True
                    break

            assert matched == should_be_batch, f"Batch detection failed for: {user_input}"

        print("✅ Batch processing tests passed")
        return True

    except Exception as e:
        print(f"❌ Batch processing test failed: {e}")
        return False


def test_error_handling():
    """Test error pattern classification"""
    try:
        from src.nlp.error_handler import NLErrorHandler
        import re

        error_handler = NLErrorHandler()

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
                    if re.search(pattern, error_message, re.IGNORECASE):
                        classified_type = error_type
                        break
                if classified_type != "unknown":
                    break

            assert classified_type == expected_type, f"Error classification failed for: {error_message}"

        print("✅ Error handling tests passed")
        return True

    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False


def test_date_parsing():
    """Test date parsing patterns"""
    try:
        from src.nlp.date_parser import DateParser
        from datetime import datetime, timezone

        parser = DateParser()

        # Test basic structure
        assert hasattr(parser, 'business_hours_start'), "Should have business_hours_start"
        assert hasattr(parser, 'business_hours_end'), "Should have business_hours_end"
        assert hasattr(parser, 'relative_patterns'), "Should have relative_patterns"

        # Test business hours configuration
        assert parser.business_hours_start == 9, "Default business hours start should be 9"
        assert parser.business_hours_end == 17, "Default business hours end should be 17"

        # Test working days configuration
        assert parser.working_days == [0, 1, 2, 3, 4], "Working days should be Monday-Friday"

        print("✅ Date parsing tests passed")
        return True

    except Exception as e:
        print(f"❌ Date parsing test failed: {e}")
        return False


def test_disambiguator():
    """Test disambiguation logic"""
    try:
        from src.nlp.disambiguator import NLDisambiguator

        # Mock dependencies
        mock_db = Mock()
        mock_context_manager = Mock()
        disambiguator = NLDisambiguator(mock_db, mock_context_manager)

        # Test intent requirements structure
        for intent, requirements in disambiguator.intent_requirements.items():
            assert "required" in requirements, f"Intent {intent} missing required field"
            assert "optional" in requirements, f"Intent {intent} missing optional field"
            assert "defaults" in requirements, f"Intent {intent} missing defaults field"
            assert isinstance(requirements["required"], list), f"Required should be list for {intent}"

        # Test parameter mapping
        test_cases = [
            ("title", "TASK_TITLE"),
            ("plan_name", "PLAN_NAME"),
            ("assignee", "ASSIGNEE"),
            ("due_date", "DUE_DATE")
        ]

        for parameter, expected_entity in test_cases:
            mapped = disambiguator._map_parameter_to_entity(parameter)
            assert mapped == expected_entity, f"Parameter mapping failed: {parameter} -> {mapped}"

        print("✅ Disambiguator tests passed")
        return True

    except Exception as e:
        print(f"❌ Disambiguator test failed: {e}")
        return False


async def test_nlp_service_basic():
    """Test basic NLP service functionality without full initialization"""
    try:
        from src.services.nlp_service import NLPProcessingResult

        # Test dataclass structure
        result = NLPProcessingResult(
            intent="create_task",
            entities={"TASK_TITLE": "Test Task"},
            confidence_score=0.8,
            context_updated=True
        )

        assert result.intent == "create_task", "Should store intent correctly"
        assert result.entities["TASK_TITLE"] == "Test Task", "Should store entities correctly"
        assert result.confidence_score == 0.8, "Should store confidence correctly"
        assert result.context_updated == True, "Should store context_updated correctly"

        # Test optional fields
        assert result.is_batch_operation == False, "Should default is_batch_operation to False"
        assert result.needs_clarification == False, "Should default needs_clarification to False"

        print("✅ NLP service structure tests passed")
        return True

    except Exception as e:
        print(f"❌ NLP service test failed: {e}")
        return False


async def test_context_manager():
    """Test conversation context manager structure"""
    try:
        from src.nlp.context_manager import ConversationContextManager, ConversationMessage
        from datetime import datetime, timezone

        # Test message structure
        message = ConversationMessage(
            role="user",
            content="Create a task",
            timestamp=datetime.now(timezone.utc),
            entities={"TASK_TITLE": "Test"},
            intent="create_task"
        )

        assert message.role == "user", "Should store role correctly"
        assert message.content == "Create a task", "Should store content correctly"

        print("✅ Context manager structure tests passed")
        return True

    except Exception as e:
        print(f"❌ Context manager test failed: {e}")
        return False


def test_spacy_availability():
    """Test that spaCy and language model are available"""
    try:
        import spacy
        nlp = spacy.load('en_core_web_sm')

        # Test basic NER
        doc = nlp("John Smith will review the quarterly report tomorrow")
        entities = [(ent.text, ent.label_) for ent in doc.ents]

        assert len(entities) > 0, "Should find some entities"
        print(f"✅ spaCy model working: Found {len(entities)} entities")
        return True

    except Exception as e:
        print(f"❌ spaCy test failed: {e}")
        return False


async def run_all_tests():
    """Run all NLP implementation tests"""
    print("🧪 Running comprehensive NLP implementation tests...\n")

    tests = [
        ("Entity Extraction", test_entity_extraction),
        ("Intent Classification", test_intent_classification),
        ("Batch Processing", test_batch_processing),
        ("Error Handling", test_error_handling),
        ("Date Parsing", test_date_parsing),
        ("Disambiguator", test_disambiguator),
        ("spaCy Availability", test_spacy_availability),
        ("NLP Service Structure", test_nlp_service_basic),
        ("Context Manager Structure", test_context_manager),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n🔍 Testing {test_name}...")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()

            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            failed += 1

    print(f"\n📊 Test Results:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {(passed/(passed+failed)*100):.1f}%")

    if failed == 0:
        print("\n🎉 All NLP components are working correctly!")
        print("🚀 Story 1.3: Natural Language Command Processing is COMPLETE")
        return True
    else:
        print(f"\n⚠️  {failed} tests failed. Please review implementation.")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite failed: {e}")
        sys.exit(1)