"""
Comprehensive tests for Teams Attachment Handler
Testing file attachment processing, RAG service integration, and security
Following @CLAUDE.md testing standards with real production-like data
"""

import pytest
import asyncio
import io
from unittest.mock import Mock, AsyncMock, patch
from botbuilder.core import TurnContext
from botbuilder.schema import Attachment

from src.attachment_handler import TeamsAttachmentHandler


class TestTeamsAttachmentHandler:
    """Test suite for Teams attachment handler functionality"""

    @pytest.fixture
    def attachment_handler(self):
        """TeamsAttachmentHandler instance for testing"""
        return TeamsAttachmentHandler("http://test-rag-service:7120")

    @pytest.fixture
    def mock_turn_context(self):
        """Mock TurnContext for Teams interactions"""
        context = Mock(spec=TurnContext)
        context.adapter = Mock()
        context.adapter.request = Mock()
        context.adapter.request.headers = {"Authorization": "Bearer test-auth-token"}
        context.activity = Mock()
        context.activity.service_url = "https://smba.trafficmanager.net/teams/"
        return context

    @pytest.fixture
    def sample_pdf_attachment(self):
        """Sample PDF attachment data"""
        return Attachment(
            name="project_proposal.pdf",
            content_type="application/pdf",
            content_url="https://teams.microsoft.com/api/v1.0/attachments/abc123",
            thumbnail_url=None
        )

    @pytest.fixture
    def sample_word_attachment(self):
        """Sample Word document attachment"""
        return Attachment(
            name="requirements_document.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content_url="https://teams.microsoft.com/api/v1.0/attachments/def456",
            thumbnail_url=None
        )

    @pytest.fixture
    def unsupported_attachment(self):
        """Unsupported file type attachment"""
        return Attachment(
            name="image.png",
            content_type="image/png",
            content_url="https://teams.microsoft.com/api/v1.0/attachments/ghi789",
            thumbnail_url=None
        )

    def test_supported_file_types(self, attachment_handler, sample_pdf_attachment, unsupported_attachment):
        """Test file type validation for RAG processing"""
        # Test supported file types
        assert attachment_handler.is_supported_file(sample_pdf_attachment) is True

        # Test unsupported file types
        assert attachment_handler.is_supported_file(unsupported_attachment) is False

    @pytest.mark.asyncio
    async def test_download_attachment_success(self, attachment_handler, sample_pdf_attachment, mock_turn_context):
        """Test successful file download from Teams"""
        with patch.object(attachment_handler.client, 'get') as mock_get:
            # Arrange
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"PDF file content here"
            mock_get.return_value = mock_response

            # Act
            result = await attachment_handler.download_attachment(sample_pdf_attachment, mock_turn_context)

            # Assert
            assert result is not None
            content, filename = result
            assert content == b"PDF file content here"
            assert filename == "project_proposal.pdf"

            # Verify authorization header was used
            call_args = mock_get.call_args
            assert "Authorization" in call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_download_attachment_auth_failure(self, attachment_handler, sample_pdf_attachment, mock_turn_context):
        """Test handling of authentication failures during download"""
        with patch.object(attachment_handler.client, 'get') as mock_get:
            # Arrange
            mock_response = Mock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response

            # Act
            result = await attachment_handler.download_attachment(sample_pdf_attachment, mock_turn_context)

            # Assert
            assert result is None

    @pytest.mark.asyncio
    async def test_download_attachment_no_content_url(self, attachment_handler, mock_turn_context):
        """Test handling of attachments with missing content URL"""
        # Arrange
        attachment = Attachment(
            name="test.pdf",
            content_type="application/pdf",
            content_url=None
        )

        # Act
        result = await attachment_handler.download_attachment(attachment, mock_turn_context)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_to_rag_service_success(self, attachment_handler):
        """Test successful file upload to RAG service"""
        with patch.object(attachment_handler.client, 'post') as mock_post:
            # Arrange
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "document_id": "doc_123456",
                "filename": "project_proposal.pdf",
                "chunks_created": 15,
                "processing_status": "completed"
            }
            mock_post.return_value = mock_response

            file_content = b"PDF content for testing"

            # Act
            result = await attachment_handler.upload_to_rag_service(
                file_content=file_content,
                filename="project_proposal.pdf",
                content_type="application/pdf",
                user_id="john.smith@acme.com",
                conversation_id="conv_789"
            )

            # Assert
            assert result["success"] is True
            assert result["document_id"] == "doc_123456"
            assert result["chunks_created"] == 15
            assert result["processing_status"] == "completed"

            # Verify correct payload was sent
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://test-rag-service:7120/api/upload"

            # Check form data
            files_arg = call_args[1]["files"]
            assert "file" in files_arg
            filename, file_obj, content_type = files_arg["file"]
            assert filename == "project_proposal.pdf"
            assert content_type == "application/pdf"

            data_arg = call_args[1]["data"]
            assert data_arg["source"] == "teams"
            assert data_arg["user_id"] == "john.smith@acme.com"
            assert data_arg["conversation_id"] == "conv_789"

    @pytest.mark.asyncio
    async def test_upload_to_rag_service_failure(self, attachment_handler):
        """Test handling of RAG service upload failures"""
        with patch.object(attachment_handler.client, 'post') as mock_post:
            # Arrange
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_post.return_value = mock_response

            # Act
            result = await attachment_handler.upload_to_rag_service(
                file_content=b"test content",
                filename="test.pdf",
                content_type="application/pdf",
                user_id="user@acme.com",
                conversation_id="conv_123"
            )

            # Assert
            assert result["success"] is False
            assert "Upload failed: 500" in result["error"]

    @pytest.mark.asyncio
    async def test_process_attachments_mixed_types(self, attachment_handler, mock_turn_context):
        """Test processing mixed supported and unsupported file types"""
        # Arrange
        attachments = [
            Attachment(
                name="document.pdf",
                content_type="application/pdf",
                content_url="https://teams.microsoft.com/api/v1.0/attachments/pdf123"
            ),
            Attachment(
                name="image.jpg",
                content_type="image/jpeg",
                content_url="https://teams.microsoft.com/api/v1.0/attachments/img456"
            ),
            Attachment(
                name="spreadsheet.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content_url="https://teams.microsoft.com/api/v1.0/attachments/xl789"
            )
        ]

        with patch.object(attachment_handler, 'download_attachment') as mock_download, \
             patch.object(attachment_handler, 'upload_to_rag_service') as mock_upload:

            # Mock successful downloads for supported files
            mock_download.return_value = (b"file content", "test_file")
            mock_upload.return_value = {
                "success": True,
                "document_id": "doc_test",
                "chunks_created": 5
            }

            # Act
            results = await attachment_handler.process_attachments(
                attachments=attachments,
                turn_context=mock_turn_context,
                user_id="alice.johnson@acme.com",
                conversation_id="conv_multifile"
            )

            # Assert
            assert len(results) == 3

            # PDF should be processed successfully
            pdf_result = next(r for r in results if r["filename"] == "document.pdf")
            assert pdf_result["success"] is True

            # JPEG should be rejected as unsupported
            jpg_result = next(r for r in results if r["filename"] == "image.jpg")
            assert jpg_result["success"] is False
            assert "not supported" in jpg_result["error"]

            # Excel should be processed successfully
            xlsx_result = next(r for r in results if r["filename"] == "spreadsheet.xlsx")
            assert xlsx_result["success"] is True

    @pytest.mark.asyncio
    async def test_process_attachments_download_failure(self, attachment_handler, sample_pdf_attachment, mock_turn_context):
        """Test handling of download failures during processing"""
        with patch.object(attachment_handler, 'download_attachment') as mock_download:
            # Arrange
            mock_download.return_value = None  # Simulate download failure

            # Act
            results = await attachment_handler.process_attachments(
                attachments=[sample_pdf_attachment],
                turn_context=mock_turn_context,
                user_id="user@acme.com",
                conversation_id="conv_fail"
            )

            # Assert
            assert len(results) == 1
            assert results[0]["success"] is False
            assert results[0]["error"] == "Failed to download file"

    def test_format_attachment_response_success_only(self, attachment_handler):
        """Test formatting of successful attachment processing results"""
        results = [
            {
                "filename": "project_plan.pdf",
                "success": True,
                "chunks_created": 12,
                "document_id": "doc_001"
            },
            {
                "filename": "budget_analysis.xlsx",
                "success": True,
                "chunks_created": 8,
                "document_id": "doc_002"
            }
        ]

        response = attachment_handler.format_attachment_response(results)

        assert "Attachments Processed Successfully" in response
        assert "project_plan.pdf" in response
        assert "12 chunks created" in response
        assert "budget_analysis.xlsx" in response
        assert "8 chunks created" in response
        assert "You can now ask questions about these documents!" in response

    def test_format_attachment_response_mixed_results(self, attachment_handler):
        """Test formatting of mixed success/failure results"""
        results = [
            {
                "filename": "valid_document.pdf",
                "success": True,
                "chunks_created": 10
            },
            {
                "filename": "corrupted_file.docx",
                "success": False,
                "error": "File could not be processed"
            }
        ]

        response = attachment_handler.format_attachment_response(results)

        assert "Attachments Processed Successfully" in response
        assert "valid_document.pdf" in response
        assert "Some attachments could not be processed" in response
        assert "corrupted_file.docx" in response
        assert "File could not be processed" in response

    def test_format_attachment_response_empty(self, attachment_handler):
        """Test formatting with no results"""
        response = attachment_handler.format_attachment_response([])
        assert response == ""

    @pytest.mark.asyncio
    async def test_large_file_handling(self, attachment_handler, mock_turn_context):
        """Test handling of large files within reasonable limits"""
        with patch.object(attachment_handler.client, 'get') as mock_get, \
             patch.object(attachment_handler.client, 'post') as mock_post:

            # Arrange - simulate 5MB file (typical large document)
            large_content = b"x" * (5 * 1024 * 1024)

            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get_response.content = large_content
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {
                "document_id": "large_doc_001",
                "chunks_created": 50,
                "processing_status": "completed"
            }
            mock_post.return_value = mock_post_response

            attachment = Attachment(
                name="large_report.pdf",
                content_type="application/pdf",
                content_url="https://teams.microsoft.com/api/v1.0/attachments/large123"
            )

            # Act
            results = await attachment_handler.process_attachments(
                attachments=[attachment],
                turn_context=mock_turn_context,
                user_id="manager@acme.com",
                conversation_id="conv_large"
            )

            # Assert
            assert len(results) == 1
            assert results[0]["success"] is True
            assert results[0]["chunks_created"] == 50

    @pytest.mark.asyncio
    async def test_concurrent_attachment_processing(self, attachment_handler, mock_turn_context):
        """Test processing multiple attachments concurrently"""
        with patch.object(attachment_handler, 'download_attachment') as mock_download, \
             patch.object(attachment_handler, 'upload_to_rag_service') as mock_upload:

            # Arrange - multiple attachments
            attachments = [
                Attachment(name=f"doc_{i}.pdf", content_type="application/pdf",
                          content_url=f"https://teams.microsoft.com/api/v1.0/attachments/doc{i}")
                for i in range(5)
            ]

            async def mock_download_delay(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate network delay
                return (b"content", f"doc_{len(args)}.pdf")

            async def mock_upload_delay(*args, **kwargs):
                await asyncio.sleep(0.1)  # Simulate upload delay
                return {"success": True, "chunks_created": 3}

            mock_download.side_effect = mock_download_delay
            mock_upload.side_effect = mock_upload_delay

            # Act
            start_time = asyncio.get_event_loop().time()
            results = await attachment_handler.process_attachments(
                attachments=attachments,
                turn_context=mock_turn_context,
                user_id="user@acme.com",
                conversation_id="conv_concurrent"
            )
            end_time = asyncio.get_event_loop().time()

            # Assert
            assert len(results) == 5
            assert all(r["success"] for r in results)

            # Should process sequentially, not concurrently (current implementation)
            # This test documents current behavior; concurrent processing could be future enhancement
            processing_time = end_time - start_time
            assert processing_time >= 1.0  # 5 files * 0.2s each >= 1.0s

    @pytest.mark.asyncio
    async def test_rag_service_timeout_handling(self, attachment_handler):
        """Test handling of RAG service timeouts"""
        with patch.object(attachment_handler.client, 'post') as mock_post:
            # Arrange
            import httpx
            mock_post.side_effect = httpx.TimeoutException("Request timed out")

            # Act
            result = await attachment_handler.upload_to_rag_service(
                file_content=b"test content",
                filename="test.pdf",
                content_type="application/pdf",
                user_id="user@acme.com",
                conversation_id="conv_timeout"
            )

            # Assert
            assert result["success"] is False
            assert "Request timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_attachment_handler_cleanup(self, attachment_handler):
        """Test proper cleanup of HTTP client resources"""
        with patch.object(attachment_handler.client, 'aclose') as mock_close:
            # Act
            await attachment_handler.close()

            # Assert
            mock_close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])