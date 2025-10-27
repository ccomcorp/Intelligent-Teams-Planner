#!/usr/bin/env python3
"""
Test the specific query that failed
"""

import asyncio
import sys
import os

# Add the planner-mcp-server src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'planner-mcp-server', 'src'))

from nlp.hybrid_ner import HybridNER
from nlp.semantic_intent_matcher import SemanticIntentMatcher

async def test_angel_query():
    """Test the specific query that failed"""
    print("🔍 Testing: 'tasks assigned to angel'")
    print("=" * 50)

    # Initialize components
    print("Initializing semantic components...")
    ner = HybridNER()
    intent_matcher = SemanticIntentMatcher(use_chromadb=False)

    await ner.initialize()
    await intent_matcher.initialize()
    print("✓ Components initialized\n")

    query = "tasks assigned to angel"

    print(f"Query: '{query}'")
    print("-" * 30)

    # Test intent classification
    intent_match = await intent_matcher.classify_intent(query)
    print(f"Intent: {intent_match.intent} (confidence: {intent_match.confidence:.2f})")
    print(f"Matched example: {intent_match.matched_example}")

    # Test entity extraction
    ner_result = await ner.extract_entities(query)
    print(f"Entities found: {len(ner_result.entities)}")
    for entity in ner_result.entities:
        print(f"  - {entity.type}: '{entity.value}' (conf: {entity.confidence:.2f}, method: {entity.extraction_method})")

    print(f"Cleaned text: {ner_result.cleaned_text}")

    # Test assignment entity extraction specifically
    assignment_info = await ner.extract_assignment_entities(query)
    print(f"\nAssignment extraction:")
    print(f"  - Confidence: {assignment_info.get('confidence', 0):.2f}")
    print(f"  - Assignee: {assignment_info.get('assignee', 'Not found')}")
    print(f"  - Action type: {assignment_info.get('action_type', 'Not found')}")

if __name__ == "__main__":
    asyncio.run(test_angel_query())