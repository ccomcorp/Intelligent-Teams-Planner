"""
Integration tests for UniversalDocumentParser using real data
Story 6.1: Advanced Document Processing Pipeline
"""

import asyncio
import pytest
import os
import tempfile
from typing import Dict, Any, List
import uuid
from io import BytesIO

# Import the module being tested
import sys
import importlib.util

# Import UniversalDocumentParser with proper path handling for hyphenated directory
rag_service_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
universal_parser_path = os.path.join(rag_service_root, 'src', 'document-processing', 'parsers', 'universal_parser.py')
spec = importlib.util.spec_from_file_location("universal_parser", universal_parser_path)
universal_parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(universal_parser_module)
UniversalDocumentParser = universal_parser_module.UniversalDocumentParser


class TestUniversalDocumentParserIntegration:
    """Integration test suite for UniversalDocumentParser with real document processing"""

    @pytest.fixture
    def parser_config(self) -> Dict[str, Any]:
        """Configuration for parser testing"""
        return {
            'max_chunk_size': 500,
            'chunk_overlap': 50,
            'ocr_enabled': False,  # Disable OCR for faster testing
            'ocr_languages': ['eng']
        }

    @pytest.fixture
    def parser(self, parser_config: Dict[str, Any]) -> UniversalDocumentParser:
        """Create parser instance for testing"""
        return UniversalDocumentParser(config=parser_config)

    @pytest.fixture
    def real_text_content(self) -> bytes:
        """Real text content for testing"""
        content = """
        Microsoft Teams Integration Project Requirements
        ===============================================

        Executive Summary
        -----------------
        This document outlines the comprehensive requirements for implementing
        an advanced Microsoft Teams integration with intelligent document
        processing capabilities.

        Project Scope
        -------------
        The Intelligent Teams Planner project encompasses the following key components:

        1. Document Processing Pipeline
           • Multi-format document support (PDF, DOCX, PPTX, XLSX)
           • OCR capabilities for scanned documents and images
           • Intelligent content extraction and structuring
           • Real-time processing for Teams attachments

        2. RAG Service Implementation
           • Vector embeddings using sentence-transformers
           • PostgreSQL with pgvector for semantic search
           • Context-aware document retrieval
           • Multi-source ingestion (Teams, Planner, OpenWebUI)

        3. Teams Bot Integration
           • Real-time conversation processing
           • Automated task management workflows
           • Intelligent notification systems
           • Microsoft Graph API integration

        Technical Architecture
        ----------------------
        Backend Framework: FastAPI with Python 3.10+
        Database: PostgreSQL 15+ with pgvector extension
        Caching: Redis for session management and performance
        Message Queue: Optional Redis for async processing
        Authentication: Microsoft Azure AD integration

        Performance Requirements
        ------------------------
        • Document processing: < 5 seconds for files up to 10MB
        • Search response time: < 500ms for typical queries
        • Concurrent users: Support for 500+ simultaneous connections
        • Uptime: 99.9% availability requirement

        Security Considerations
        -----------------------
        • All API endpoints require authentication
        • Data encryption in transit and at rest
        • Compliance with enterprise security policies
        • Regular security audits and vulnerability assessments

        Implementation Timeline
        -----------------------
        Phase 1 (Weeks 1-4): Core document processing pipeline
        Phase 2 (Weeks 5-8): RAG service and vector search
        Phase 3 (Weeks 9-12): Teams bot integration
        Phase 4 (Weeks 13-16): Testing, optimization, and deployment

        Success Metrics
        ---------------
        • 95% accuracy in document content extraction
        • 90% user satisfaction with search relevance
        • 50% reduction in manual document management tasks
        • Zero security incidents during first year of operation

        Conclusion
        ----------
        The Intelligent Teams Planner represents a significant advancement
        in enterprise collaboration tools, combining cutting-edge AI
        capabilities with robust Microsoft Teams integration.
        """
        return content.encode('utf-8')

    @pytest.fixture
    def real_csv_content(self) -> bytes:
        """Real CSV content for testing"""
        content = """Employee ID,Name,Department,Role,Start Date,Salary,Manager ID
        10847,John Smith,Engineering,Senior Developer,2023-01-15,95000,10532
        10848,Sarah Johnson,Marketing,Product Manager,2023-02-01,87000,10533
        10849,Michael Chen,Engineering,DevOps Engineer,2023-02-15,92000,10532
        10850,Lisa Anderson,Sales,Account Executive,2023-03-01,78000,10534
        10851,David Wilson,Engineering,Technical Lead,2022-12-01,105000,10532
        10852,Emily Rodriguez,HR,Recruiter,2023-01-30,65000,10535
        10853,Robert Kim,Finance,Financial Analyst,2023-02-20,72000,10536
        10854,Maria Garcia,Engineering,QA Engineer,2023-03-15,84000,10532
        10855,James Thompson,Marketing,Content Specialist,2023-04-01,68000,10533
        10856,Jennifer Lee,Sales,Sales Manager,2022-11-15,95000,10534
        """
        return content.encode('utf-8')

    @pytest.fixture
    def real_html_content(self) -> bytes:
        """Real HTML content for testing"""
        content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Project Status Dashboard</title>
        </head>
        <body>
            <header>
                <h1>Intelligent Teams Planner - Project Status</h1>
                <nav>
                    <ul>
                        <li><a href="#overview">Overview</a></li>
                        <li><a href="#milestones">Milestones</a></li>
                        <li><a href="#team">Team</a></li>
                    </ul>
                </nav>
            </header>

            <main>
                <section id="overview">
                    <h2>Project Overview</h2>
                    <p>The Intelligent Teams Planner project is currently in Phase 2 of development,
                    focusing on RAG service implementation and vector search capabilities.</p>

                    <div class="progress-bar">
                        <div class="progress" style="width: 65%;">65% Complete</div>
                    </div>
                </section>

                <section id="milestones">
                    <h2>Key Milestones</h2>
                    <ul>
                        <li class="completed">✅ Document Processing Pipeline (Completed)</li>
                        <li class="in-progress">🔄 RAG Service Implementation (In Progress)</li>
                        <li class="pending">⏳ Teams Bot Integration (Pending)</li>
                        <li class="pending">⏳ Testing and Deployment (Pending)</li>
                    </ul>
                </section>

                <section id="team">
                    <h2>Team Members</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Role</th>
                                <th>Responsibility</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>Alice Cooper</td>
                                <td>Project Manager</td>
                                <td>Overall project coordination and planning</td>
                            </tr>
                            <tr>
                                <td>Bob Johnson</td>
                                <td>Lead Developer</td>
                                <td>Backend API development and architecture</td>
                            </tr>
                            <tr>
                                <td>Carol Smith</td>
                                <td>AI Engineer</td>
                                <td>RAG implementation and vector search</td>
                            </tr>
                        </tbody>
                    </table>
                </section>
            </main>

            <footer>
                <p>&copy; 2024 Company Name. All rights reserved.</p>
            </footer>
        </body>
        </html>
        """
        return content.encode('utf-8')

    def test_parser_initialization(self, parser_config: Dict[str, Any]) -> None:
        """Test parser initialization with configuration"""
        parser = UniversalDocumentParser(config=parser_config)

        assert parser.config == parser_config
        assert parser.chunk_config['max_characters'] == 500
        assert parser.chunk_config['overlap'] == 50
        assert parser.ocr_enabled is False
        assert parser.ocr_languages == ['eng']
        assert len(parser.supported_formats) > 10

    def test_get_supported_formats(self, parser: UniversalDocumentParser) -> None:
        """Test supported format retrieval"""
        formats = parser.get_supported_formats()

        expected_formats = ['pdf', 'docx', 'txt', 'jpg', 'png', 'xlsx', 'pptx', 'csv']
        for format_type in expected_formats:
            assert format_type in formats

    def test_detect_format_comprehensive(self, parser: UniversalDocumentParser) -> None:
        """Test format detection with real file names"""
        test_cases = [
            ('Annual Report 2024.pdf', 'application/pdf', 'pdf'),
            ('Meeting Minutes March 2024.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'docx'),
            ('Q1 Financial Data.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'),
            ('Team Presentation.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'pptx'),
            ('Employee Database Export.csv', 'text/csv', 'csv'),
            ('Project Notes.txt', 'text/plain', 'txt'),
            ('Screenshot 2024-03-15.png', 'image/png', 'png'),
            ('Scanned Document.jpg', 'image/jpeg', 'jpg')
        ]

        for filename, mime_type, expected_format in test_cases:
            result = parser._detect_format(filename, mime_type)
            assert result == expected_format, f"Failed for {filename}"

    @pytest.mark.asyncio
    async def test_parse_real_text_document(
        self,
        parser: UniversalDocumentParser,
        real_text_content: bytes
    ) -> None:
        """Test parsing real text document with comprehensive content"""

        result = await parser.parse_document(
            content=real_text_content,
            filename="requirements_document.txt",
            mime_type="text/plain",
            source="teams",
            uploaded_by="alice.cooper@company.com",
            conversation_id="conv_real_test_123"
        )

        # Verify successful parsing
        assert result['processing_success'] is True
        assert result['filename'] == "requirements_document.txt"
        assert result['file_format'] == 'txt'
        assert 'document_id' in result
        assert result['elements_count'] > 0
        assert result['chunks_count'] > 0

        # Verify content extraction
        content = result['content']
        assert len(content['text']) > 100
        assert 'Microsoft Teams Integration' in content['text']
        assert len(content['headers']) > 0
        assert content['stats']['text_length'] > 100

        # Verify chunks are meaningful
        chunks = result['chunks']
        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk['content'].strip()) > 0
            assert 'chunk_id' in chunk
            assert chunk['char_count'] > 0

        # Verify metadata
        metadata = result['metadata']
        assert metadata['source'] == 'teams'
        assert metadata['uploaded_by'] == 'alice.cooper@company.com'
        assert metadata['conversation_id'] == 'conv_real_test_123'

    @pytest.mark.asyncio
    async def test_parse_real_csv_document(
        self,
        parser: UniversalDocumentParser,
        real_csv_content: bytes
    ) -> None:
        """Test parsing real CSV document with employee data"""

        result = await parser.parse_document(
            content=real_csv_content,
            filename="employee_database.csv",
            mime_type="text/csv",
            source="planner",
            task_id="task_csv_import_456",
            uploaded_by="bob.johnson@company.com"
        )

        # Verify successful parsing
        assert result['processing_success'] is True
        assert result['filename'] == "employee_database.csv"
        assert result['file_format'] == 'csv'

        # Verify CSV content extraction
        content = result['content']
        assert 'John Smith' in content['text']
        assert 'Engineering' in content['text']
        assert 'Senior Developer' in content['text']  # Check for actual CSV content

        # Verify chunks contain structured data
        chunks = result['chunks']
        assert len(chunks) > 0
        assert any('Employee ID' in chunk['content'] for chunk in chunks)

    @pytest.mark.asyncio
    async def test_parse_real_html_document(
        self,
        parser: UniversalDocumentParser,
        real_html_content: bytes
    ) -> None:
        """Test parsing real HTML document with project dashboard"""

        result = await parser.parse_document(
            content=real_html_content,
            filename="project_dashboard.html",
            mime_type="text/html",
            source="openwebui",
            uploaded_by="carol.smith@company.com"
        )

        # Verify successful parsing
        assert result['processing_success'] is True
        assert result['filename'] == "project_dashboard.html"

        # Verify HTML content extraction
        content = result['content']
        assert 'Project Overview' in content['text']  # Check actual extracted content
        assert 'Intelligent Teams Planner' in content['text']
        assert 'Alice Cooper' in content['text']

        # Verify structured elements are detected
        assert len(content['headers']) > 0

        # HTML tables should be detected
        if len(content['tables']) > 0:
            assert any('Name' in table['text'] for table in content['tables'])

    @pytest.mark.asyncio
    async def test_parse_document_with_metadata_preservation(
        self,
        parser: UniversalDocumentParser,
        real_text_content: bytes
    ) -> None:
        """Test that custom metadata is preserved during parsing"""

        custom_metadata = {
            'project_id': 'proj_789',
            'department': 'Engineering',
            'priority': 'high',
            'deadline': '2024-04-30',
            'stakeholders': ['alice.cooper@company.com', 'bob.johnson@company.com']
        }

        result = await parser.parse_document(
            content=real_text_content,
            filename="project_spec.txt",
            mime_type="text/plain",
            source="planner",
            task_id="task_spec_review",
            uploaded_by="carol.smith@company.com",
            **custom_metadata
        )

        # Verify custom metadata is preserved
        metadata = result['metadata']
        assert metadata['project_id'] == 'proj_789'
        assert metadata['department'] == 'Engineering'
        assert metadata['priority'] == 'high'
        assert metadata['deadline'] == '2024-04-30'
        assert metadata['stakeholders'] == ['alice.cooper@company.com', 'bob.johnson@company.com']

    @pytest.mark.asyncio
    async def test_parse_empty_document(self, parser: UniversalDocumentParser) -> None:
        """Test handling of empty documents"""

        result = await parser.parse_document(
            content=b"",
            filename="empty_file.txt",
            mime_type="text/plain",
            source="openwebui",
            uploaded_by="test.user@company.com"
        )

        # Should handle empty content gracefully
        assert result['processing_success'] is True
        assert result['elements_count'] == 0
        assert result['chunks_count'] == 0

    @pytest.mark.asyncio
    async def test_parse_large_text_document(self, parser: UniversalDocumentParser) -> None:
        """Test parsing large text documents"""

        # Create large content by repeating text
        large_content = """
        This is a section of a large document that contains substantial content.
        It includes multiple paragraphs with detailed technical information.
        The document covers various aspects of software development, project management,
        and technical implementation details that are commonly found in enterprise documentation.
        """ * 100  # Repeat to create large document

        result = await parser.parse_document(
            content=large_content.encode('utf-8'),
            filename="large_technical_document.txt",
            mime_type="text/plain",
            source="teams",
            uploaded_by="technical.writer@company.com"
        )

        # Verify large document processing
        assert result['processing_success'] is True
        assert result['elements_count'] > 0
        assert result['chunks_count'] > 5  # Should create multiple chunks

        # Verify content length
        assert len(result['content']['text']) > 10000

    @pytest.mark.asyncio
    async def test_parse_document_with_special_characters(self, parser: UniversalDocumentParser) -> None:
        """Test parsing documents with Unicode and special characters"""

        unicode_content = """
        International Project Documentation
        ==================================

        Team Members:
        • José María González (Spain) - Lead Developer
        • François Dubois (France) - UI/UX Designer
        • 张伟 (China) - Data Scientist
        • محمد علي (UAE) - Project Manager
        • Анна Петрова (Russia) - QA Engineer

        Technical Specifications:
        - Framework: Next.js with TypeScript
        - Database: PostgreSQL with UTF-8 encoding
        - API Rate Limits: 1,000 requests/minute
        - Response Time: < 200ms (99th percentile)

        Budget Allocation:
        💰 Development: $250,000
        💰 Infrastructure: $50,000
        💰 Testing: $25,000
        💰 Total: $325,000

        Status Indicators:
        ✅ Requirements Complete
        🔄 Development In Progress
        ⏳ Testing Pending
        ❌ Deployment Not Started
        """

        result = await parser.parse_document(
            content=unicode_content.encode('utf-8'),
            filename="international_project_doc.txt",
            mime_type="text/plain",
            source="teams",
            uploaded_by="global.coordinator@company.com"
        )

        # Verify Unicode content is handled correctly
        assert result['processing_success'] is True
        content_text = result['content']['text']
        assert 'José María González' in content_text
        assert '张伟' in content_text
        assert 'محمد علي' in content_text
        assert '💰' in content_text or 'Development' in content_text

    def test_complexity_score_calculation_real_data(self, parser: UniversalDocumentParser) -> None:
        """Test complexity score calculation with realistic metadata"""

        # Simple document metadata
        simple_doc = {
            'has_tables': False,
            'has_images': False,
            'has_lists': True,
            'element_types': ['Title', 'NarrativeText'],
            'page_count': 2
        }
        simple_score = parser._calculate_complexity_score(simple_doc, 15)

        # Complex document metadata
        complex_doc = {
            'has_tables': True,
            'has_images': True,
            'has_lists': True,
            'element_types': ['Title', 'Header', 'Table', 'Image', 'ListItem', 'NarrativeText', 'Address'],
            'page_count': 45
        }
        complex_score = parser._calculate_complexity_score(complex_doc, 200)

        # Verify complexity scoring
        assert 0.0 <= simple_score <= 1.0
        assert 0.0 <= complex_score <= 1.0
        assert complex_score > simple_score

    @pytest.mark.asyncio
    async def test_concurrent_document_parsing(self, parser: UniversalDocumentParser) -> None:
        """Test concurrent parsing of multiple documents"""

        documents = [
            (b"Document 1: Project requirements and specifications", "doc1.txt"),
            (b"Document 2: Technical architecture and design patterns", "doc2.txt"),
            (b"Document 3: Implementation timeline and resource allocation", "doc3.txt"),
            (b"Document 4: Testing strategy and quality assurance plan", "doc4.txt"),
            (b"Document 5: Deployment procedures and operational guidelines", "doc5.txt")
        ]

        # Parse documents concurrently
        tasks = []
        for content, filename in documents:
            task = parser.parse_document(
                content=content,
                filename=filename,
                mime_type="text/plain",
                source="openwebui",
                uploaded_by=f"user_{filename.split('.')[0]}@company.com"
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify all documents processed successfully
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result['processing_success'] is True
            assert result['filename'] == f"doc{i+1}.txt"

    def test_parser_configuration_variations(self) -> None:
        """Test parser with different configuration options"""

        configs = [
            {'max_chunk_size': 200, 'chunk_overlap': 20},
            {'max_chunk_size': 1000, 'chunk_overlap': 100},
            {'max_chunk_size': 2000, 'chunk_overlap': 200, 'ocr_enabled': True}
        ]

        for config in configs:
            parser = UniversalDocumentParser(config=config)
            assert parser.chunk_config['max_characters'] == config['max_chunk_size']
            assert parser.chunk_config['overlap'] == config['chunk_overlap']
            if 'ocr_enabled' in config:
                assert parser.ocr_enabled == config['ocr_enabled']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])