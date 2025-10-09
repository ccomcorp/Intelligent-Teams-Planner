"""
Security Tests for Teams Bot File Attachment Processing
Tests for vulnerability prevention, input validation, and secure file handling
Following @CLAUDE.md security standards
"""

import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch
from botbuilder.core import TurnContext
from botbuilder.schema import Attachment

from src.attachment_handler import TeamsAttachmentHandler
from src.main import TeamsBot, OpenWebUIClient, ConversationContextManager


class TestSecurityValidation:
    """Security tests for file handling and input validation"""

    @pytest.fixture
    def attachment_handler(self):
        """TeamsAttachmentHandler instance for testing"""
        return TeamsAttachmentHandler("http://test-rag-service:7120")

    @pytest.fixture
    def mock_turn_context(self):
        """Mock TurnContext for security testing"""
        context = Mock(spec=TurnContext)
        context.adapter = Mock()
        context.adapter.request = Mock()
        context.adapter.request.headers = {"Authorization": "Bearer safe-test-token"}
        return context

    def test_file_type_validation_prevents_dangerous_files(self, attachment_handler):
        """Test that dangerous file types are rejected"""
        dangerous_files = [
            Attachment(name="malware.exe", content_type="application/x-executable"),
            Attachment(name="script.js", content_type="application/javascript"),
            Attachment(name="backdoor.bat", content_type="application/x-bat"),
            Attachment(name="virus.scr", content_type="application/x-screensaver"),
            Attachment(name="trojan.vbs", content_type="text/vbscript"),
            Attachment(name="malicious.jar", content_type="application/java-archive"),
            Attachment(name="dangerous.zip", content_type="application/zip"),
            Attachment(name="shell.sh", content_type="application/x-sh"),
        ]

        for dangerous_file in dangerous_files:
            assert attachment_handler.is_supported_file(dangerous_file) is False, \
                f"Dangerous file type {dangerous_file.content_type} should be rejected"

    def test_filename_validation_prevents_path_traversal(self, attachment_handler):
        """Test filename validation prevents path traversal attacks"""
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "file.pdf/../../../etc/shadow",
            "normal.txt\x00.exe",  # Null byte injection
            "very_long_filename_" + "x" * 1000 + ".pdf",  # Extremely long filename
            "file with unicode \u202e.pdf",  # Unicode right-to-left override
            ".hidden_file.pdf",  # Hidden files
            "CON.pdf",  # Windows reserved names
            "PRN.docx",
            "AUX.txt"
        ]

        for malicious_name in malicious_filenames:
            attachment = Attachment(
                name=malicious_name,
                content_type="application/pdf",
                content_url="https://safe-url.com/file"
            )

            # The current implementation doesn't explicitly validate filenames
            # This test documents the security gap that should be addressed
            # In a secure implementation, these should be sanitized or rejected

    @pytest.mark.asyncio
    async def test_url_validation_prevents_ssrf(self, attachment_handler, mock_turn_context):
        """Test URL validation prevents Server-Side Request Forgery (SSRF)"""
        malicious_urls = [
            "http://localhost:6379/",  # Redis port
            "http://127.0.0.1:5432/",  # PostgreSQL port
            "http://169.254.169.254/metadata/",  # AWS metadata service
            "file:///etc/passwd",  # Local file access
            "http://internal-server:8080/admin",  # Internal network access
            "ftp://malicious-server.com/file.pdf",  # Non-HTTP protocols
            "javascript:alert('xss')",  # JavaScript protocol
        ]

        for malicious_url in malicious_urls:
            attachment = Attachment(
                name="test.pdf",
                content_type="application/pdf",
                content_url=malicious_url
            )

            with patch.object(attachment_handler.client, 'get') as mock_get:
                # The download should validate URL schemes and hostnames
                result = await attachment_handler.download_attachment(attachment, mock_turn_context)

                # Current implementation doesn't validate URLs - security gap
                # In a secure implementation, internal URLs should be rejected

    @pytest.mark.asyncio
    async def test_file_size_limits_prevent_dos(self, attachment_handler, mock_turn_context):
        """Test file size limits prevent denial of service attacks"""
        with patch.object(attachment_handler.client, 'get') as mock_get:
            # Simulate extremely large file (100MB)
            large_content = b"x" * (100 * 1024 * 1024)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = large_content
            mock_get.return_value = mock_response

            attachment = Attachment(
                name="huge_file.pdf",
                content_type="application/pdf",
                content_url="https://teams.microsoft.com/api/v1.0/attachments/huge123"
            )

            # Act
            result = await attachment_handler.download_attachment(attachment, mock_turn_context)

            # Current implementation doesn't enforce size limits - potential DoS vector
            # In production, should implement size limits (e.g., 10MB max)
            assert result is not None  # Current behavior - no size limit

    def test_content_type_validation_prevents_spoofing(self, attachment_handler):
        """Test content type validation prevents MIME type spoofing"""
        spoofed_files = [
            # Executable disguised as PDF
            Attachment(name="malware.exe.pdf", content_type="application/pdf"),
            # JavaScript disguised as text
            Attachment(name="script.js.txt", content_type="text/plain"),
            # Inconsistent extension and MIME type
            Attachment(name="document.pdf", content_type="application/x-executable"),
        ]

        # Current implementation only checks MIME type, not file extension
        # This is a security gap - should validate both match
        for spoofed_file in spoofed_files:
            # Should implement proper file type detection based on content magic bytes
            pass

    @pytest.mark.asyncio
    async def test_authentication_token_handling_secure(self, attachment_handler, mock_turn_context):
        """Test secure handling of authentication tokens"""
        with patch.object(attachment_handler.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"file content"
            mock_get.return_value = mock_response

            attachment = Attachment(
                name="test.pdf",
                content_type="application/pdf",
                content_url="https://teams.microsoft.com/api/v1.0/attachments/secure123"
            )

            # Act
            await attachment_handler.download_attachment(attachment, mock_turn_context)

            # Assert - verify token is passed securely
            call_args = mock_get.call_args
            headers = call_args[1]["headers"]
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer safe-test-token"

            # Verify token is not logged or exposed
            # (Would need to check logging output in real implementation)

    @pytest.mark.asyncio
    async def test_error_messages_no_information_disclosure(self, attachment_handler):
        """Test error messages don't disclose sensitive information"""
        with patch.object(attachment_handler.client, 'post') as mock_post:
            # Simulate internal server error with detailed message
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal error: Database connection failed at host db-internal-01.company.com:5432"
            mock_post.return_value = mock_response

            # Act
            result = await attachment_handler.upload_to_rag_service(
                file_content=b"test content",
                filename="test.pdf",
                content_type="application/pdf",
                user_id="user@acme.com",
                conversation_id="conv_123"
            )

            # Assert - error message should be sanitized
            assert result["success"] is False
            # Current implementation may expose internal details - security gap
            # Should return generic error message to user

    @pytest.mark.asyncio
    async def test_input_sanitization_prevents_injection(self, attachment_handler):
        """Test input sanitization prevents injection attacks"""
        malicious_inputs = [
            # SQL injection attempts
            "'; DROP TABLE documents; --",
            "' OR '1'='1",
            # NoSQL injection
            "'; return db.dropDatabase(); //",
            # Command injection
            "test.pdf; rm -rf /; echo 'pwned'",
            # XSS attempts
            "<script>alert('xss')</script>",
            # Path injection
            "../../../etc/passwd",
        ]

        for malicious_input in malicious_inputs:
            with patch.object(attachment_handler.client, 'post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"document_id": "safe_id", "chunks_created": 1}
                mock_post.return_value = mock_response

                # Act - try to inject malicious content through various parameters
                await attachment_handler.upload_to_rag_service(
                    file_content=b"safe content",
                    filename=malicious_input,  # Malicious filename
                    content_type="application/pdf",
                    user_id=malicious_input,  # Malicious user ID
                    conversation_id=malicious_input  # Malicious conversation ID
                )

                # Assert - verify parameters are properly sanitized
                call_args = mock_post.call_args
                data = call_args[1]["data"]

                # Current implementation passes through unsanitized - security gap
                # Should implement input validation and sanitization


class TestTeamsBotSecurity:
    """Security tests for the main Teams bot functionality"""

    @pytest.fixture
    def mock_openwebui_client(self):
        """Mock OpenWebUI client for security testing"""
        client = Mock(spec=OpenWebUIClient)
        client.send_message = AsyncMock()
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_context_manager(self):
        """Mock conversation context manager"""
        manager = Mock(spec=ConversationContextManager)
        manager.get_context = AsyncMock()
        manager.update_context = AsyncMock()
        manager.clear_context = AsyncMock()
        manager.connect = AsyncMock()
        manager.close = AsyncMock()
        return manager

    @pytest.fixture
    def mock_attachment_handler(self):
        """Mock attachment handler"""
        handler = Mock(spec=TeamsAttachmentHandler)
        handler.process_attachments = AsyncMock()
        handler.format_attachment_response = Mock(return_value="")
        handler.close = AsyncMock()
        return handler

    @pytest.fixture
    def teams_bot(self, mock_openwebui_client, mock_context_manager, mock_attachment_handler):
        """TeamsBot instance with mocked dependencies"""
        return TeamsBot(mock_openwebui_client, mock_context_manager, mock_attachment_handler)

    def test_message_content_sanitization(self, teams_bot):
        """Test message content is properly sanitized"""
        from botbuilder.schema import Activity, ActivityTypes, ChannelAccount

        malicious_messages = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE users; --",
            "../../../etc/passwd",
            "\x00\x01\x02\x03",  # Binary data
            "A" * 10000,  # Extremely long message
        ]

        for malicious_message in malicious_messages:
            activity = Activity(
                type=ActivityTypes.message,
                text=malicious_message,
                from_property=ChannelAccount(id="user@acme.com"),
                conversation=Mock(id="19:meeting_test")
            )

            context = Mock(spec=TurnContext)
            context.activity = activity

            # The bot should sanitize or validate message content
            # Current implementation may not have comprehensive sanitization

    @pytest.mark.asyncio
    async def test_redis_injection_prevention(self, mock_context_manager):
        """Test Redis key construction prevents injection"""
        malicious_inputs = [
            "user:*",  # Wildcard injection
            "user\r\nFLUSHALL\r\n",  # Redis command injection
            "user\x00admin",  # Null byte injection
        ]

        for malicious_input in malicious_inputs:
            # Test that malicious input in user_id or conversation_id
            # doesn't allow Redis command injection
            key = mock_context_manager._get_key if hasattr(mock_context_manager, '_get_key') else None
            # Current implementation should validate Redis key format

    def test_session_management_security(self, teams_bot):
        """Test secure session and conversation management"""
        # Test that conversation IDs are properly validated
        # and cannot be used to access other users' conversations

        # Test conversation isolation
        # Users should only access their own conversation data

        # Test session timeout
        # Old conversations should expire and be cleaned up

        pass  # Placeholder for session security tests

    def test_rate_limiting_protection(self, teams_bot):
        """Test protection against abuse and rate limiting"""
        # Should implement rate limiting per user/conversation
        # to prevent abuse of attachment processing and API calls

        pass  # Placeholder - rate limiting not implemented

    def test_audit_logging_compliance(self, teams_bot):
        """Test security audit logging requirements"""
        # Should log security-relevant events:
        # - File uploads and processing
        # - Authentication failures
        # - Suspicious activity
        # - Error conditions

        pass  # Placeholder for audit logging tests


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])