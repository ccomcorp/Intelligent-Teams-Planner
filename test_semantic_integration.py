#!/usr/bin/env python3
"""
Test semantic integration with real assignment queries
"""

import asyncio
import sys
import os

# Add the planner-mcp-server src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'planner-mcp-server', 'src'))

from nlp.hybrid_ner import HybridNER
from nlp.semantic_intent_matcher import SemanticIntentMatcher

async def test_assignment_queries():
    """Test semantic processing with assignment queries"""
    print("🧠 Testing Semantic Assignment Processing")
    print("=" * 50)

    # Initialize components
    print("Initializing semantic components...")
    ner = HybridNER()
    intent_matcher = SemanticIntentMatcher(use_chromadb=False)

    await ner.initialize()
    await intent_matcher.initialize()
    print("✓ Components initialized\n")

    # Test queries
    test_queries = [
        "assign task configure ssl on ais for all sites to angel@ccomgroupinc.com",
        "create task: update website content and assign to john@company.com",
        "delegate task: review quarterly budget to sarah.smith@team.com",
        "what tasks are assigned to angel@ccomgroupinc.com",
        "make a task to setup monitoring and give it to admin@domain.com"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: '{query}'")
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
        print()

    print("🎉 All tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_assignment_queries())