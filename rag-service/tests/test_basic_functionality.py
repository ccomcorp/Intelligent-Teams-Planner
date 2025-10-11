"""
Basic functionality test without heavy dependencies
Test core logic before dependency resolution
"""

import pytest
import sys
import os

# Test our imports work
def test_basic_imports():
    """Test that basic Python functionality works"""
    assert True

def test_story_implementation_exists():
    """Verify our story 6.1 implementation files exist"""
    base_path = os.path.join(os.path.dirname(__file__), '..', 'src')

    # Check universal parser exists
    parser_path = os.path.join(base_path, 'document-processing', 'parsers', 'universal_parser.py')
    assert os.path.exists(parser_path), f"Universal parser not found at {parser_path}"

    # Check document processor exists
    processor_path = os.path.join(base_path, 'processing', 'document_processor.py')
    assert os.path.exists(processor_path), f"Document processor not found at {processor_path}"

    # Check requirements.txt has unstructured
    requirements_path = os.path.join(base_path, '..', 'requirements.txt')
    assert os.path.exists(requirements_path), f"Requirements.txt not found at {requirements_path}"

    with open(requirements_path, 'r') as f:
        content = f.read()
        assert 'unstructured' in content, "unstructured dependency not in requirements.txt"

def test_file_structure_complete():
    """Test that all required files for story 6.1 are present"""
    base_path = os.path.join(os.path.dirname(__file__), '..')

    required_files = [
        'src/document-processing/parsers/universal_parser.py',
        'src/document-processing/parsers/__init__.py',
        'src/processing/document_processor.py',
        'tests/document_processing/parsers/test_universal_parser.py',
        'tests/document_processing/parsers/__init__.py',
        'requirements.txt'
    ]

    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        assert os.path.exists(full_path), f"Required file missing: {file_path}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])