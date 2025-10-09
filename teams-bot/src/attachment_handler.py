"""
Teams File Attachment Handler
Phase 4: Teams Integration - File Attachment Processing
"""

import io
from typing import Dict, Any, List, Optional, Tuple
import uuid
import re
from urllib.parse import urlparse

import httpx
import structlog
from botbuilder.core import TurnContext
from botbuilder.schema import Attachment

logger = structlog.get_logger(__name__)

# Security constants
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB limit
ALLOWED_HOSTS = [
    "teams.microsoft.com",
    "graph.microsoft.com",
    "sharepoint.com",
    "onedrive.live.com",
]
DANGEROUS_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".pif",
    ".vbs",
    ".js",
    ".jar",
    ".sh",
    ".ps1",
    ".msi",
    ".dll",
    ".app",
    ".deb",
    ".rpm",
}


class TeamsAttachmentHandler:
    """
    Handles file attachments from Teams messages
    Downloads files and forwards them to RAG service for processing
    """

    def __init__(self, rag_service_url: str = "http://localhost:7120"):
        self.rag_service_url = rag_service_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

        # Supported file types for RAG processing
        self.supported_types = {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/json",
            "application/xml",
        }

    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal and other attacks"""
        if not filename:
            return f"attachment_{uuid.uuid4().hex[:8]}"

        # Remove directory paths
        filename = filename.split("/")[-1].split("\\")[-1]

        # Remove null bytes and control characters
        filename = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", filename)

        # Replace dangerous characters
        filename = re.sub(r'[<>:"|?*]', "_", filename)

        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            filename = name[:250] + ("." + ext if ext else "")

        # Prevent Windows reserved names
        reserved_names = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }
        base_name = filename.split(".")[0].upper()
        if base_name in reserved_names:
            filename = f"safe_{filename}"

        return filename or f"attachment_{uuid.uuid4().hex[:8]}"

    def _validate_file_extension(self, filename: str) -> bool:
        """Validate file extension is not dangerous"""
        if not filename:
            return False

        # Get extension in lowercase
        ext = "." + filename.split(".")[-1].lower() if "." in filename else ""

        return ext not in DANGEROUS_EXTENSIONS

    def _validate_url(self, url: str) -> bool:
        """Validate URL to prevent SSRF attacks"""
        try:
            parsed = urlparse(url)

            # Only allow HTTPS
            if parsed.scheme != "https":
                return False

            # Check allowed hosts
            hostname = parsed.hostname
            if not hostname:
                return False

            # Allow exact matches or subdomains of allowed hosts
            for allowed_host in ALLOWED_HOSTS:
                if hostname == allowed_host or hostname.endswith("." + allowed_host):
                    return True

            return False

        except Exception:
            return False

    def is_supported_file(self, attachment: Attachment) -> bool:
        """Check if file type is supported for RAG processing"""
        if attachment.content_type not in self.supported_types:
            return False

        # Additional security checks
        if not self._validate_file_extension(attachment.name):
            logger.warning(
                "File rejected due to dangerous extension", filename=attachment.name
            )
            return False

        if not self._validate_url(attachment.content_url):
            logger.warning(
                "File rejected due to invalid URL", url=attachment.content_url
            )
            return False

        return True

    async def download_attachment(
        self, attachment: Attachment, turn_context: TurnContext
    ) -> Optional[Tuple[bytes, str]]:
        """
        Download file attachment from Teams

        Returns:
            Tuple of (file_content, filename) or None if download fails
        """
        try:
            if not attachment.content_url:
                logger.warning("Attachment has no content URL", name=attachment.name)
                return None

            logger.info(
                "Downloading attachment",
                name=attachment.name,
                content_type=attachment.content_type,
                url=attachment.content_url[:100],
            )

            # Get authorization header from the bot framework adapter
            # Teams attachments require the bot's access token for download
            auth_header = None
            try:
                # Extract the authorization header from the current context
                if (
                    hasattr(turn_context.adapter, "request")
                    and turn_context.adapter.request
                ):
                    auth_header = turn_context.adapter.request.headers.get(
                        "Authorization"
                    )

                # If no auth header from adapter, try to get it from the activity
                if not auth_header and hasattr(turn_context.activity, "service_url"):
                    # Get the adapter's authentication
                    if hasattr(turn_context.adapter, "authentication"):
                        # This is a more complex approach that would require
                        # proper token management. For now, we'll try without
                        # auth and handle 401 responses
                        pass

            except Exception as e:
                logger.warning("Could not extract auth header", error=str(e))

            # Prepare headers for download
            headers = {}
            if auth_header:
                headers["Authorization"] = auth_header

            # Download the file with size limit
            response = await self.client.get(attachment.content_url, headers=headers)

            if response.status_code == 200:
                content = response.content

                # Check file size limit
                if len(content) > MAX_FILE_SIZE:
                    logger.warning(
                        "File rejected due to size limit",
                        filename=attachment.name,
                        size=len(content),
                        limit=MAX_FILE_SIZE,
                    )
                    return None

                # Sanitize filename
                filename = self._sanitize_filename(attachment.name)

                logger.info(
                    "Successfully downloaded attachment",
                    filename=filename,
                    size=len(content),
                )

                return content, filename

            elif response.status_code == 401:
                logger.error(
                    "Unauthorized to download attachment - authentication issue",
                    status_code=response.status_code,
                )
                return None

            else:
                logger.error(
                    "Failed to download attachment",
                    status_code=response.status_code,
                    response=response.text[:200],
                )
                return None

        except Exception as e:
            logger.error(
                "Error downloading attachment", error=str(e), name=attachment.name
            )
            return None

    async def upload_to_rag_service(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        user_id: str,
        conversation_id: str,
    ) -> Dict[str, Any]:
        """
        Upload downloaded file to RAG service for processing

        Returns:
            Dictionary with upload result
        """
        try:
            # Sanitize inputs to prevent injection
            safe_filename = self._sanitize_filename(filename)
            safe_user_id = re.sub(r"[^\w@.-]", "", user_id)[:100]
            safe_conversation_id = re.sub(r"[^\w-]", "", conversation_id)[:100]

            logger.info(
                "Uploading file to RAG service",
                filename=safe_filename,
                size=len(file_content),
            )

            # Prepare multipart form data
            files = {"file": (safe_filename, io.BytesIO(file_content), content_type)}

            data = {
                "source": "teams",
                "user_id": safe_user_id,
                "conversation_id": safe_conversation_id,
            }

            # Upload to RAG service
            response = await self.client.post(
                f"{self.rag_service_url}/api/upload", files=files, data=data
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Successfully uploaded to RAG service",
                    document_id=result.get("document_id"),
                    chunks_created=result.get("chunks_created"),
                )

                return {
                    "success": True,
                    "document_id": result.get("document_id"),
                    "filename": result.get("filename"),
                    "chunks_created": result.get("chunks_created", 0),
                    "processing_status": result.get("processing_status", "completed"),
                }

            else:
                logger.error(
                    "RAG service upload failed",
                    status_code=response.status_code,
                    response=response.text[:200],
                )

                return {
                    "success": False,
                    "error": f"Upload failed: {response.status_code}",
                }

        except Exception as e:
            logger.error("Error uploading to RAG service", error=str(e))
            return {"success": False, "error": str(e)}

    async def process_attachments(
        self,
        attachments: List[Attachment],
        turn_context: TurnContext,
        user_id: str,
        conversation_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Process all attachments in a Teams message

        Returns:
            List of processing results for each attachment
        """
        results: List[Dict[str, Any]] = []

        if not attachments:
            return results

        logger.info("Processing attachments", count=len(attachments))

        for attachment in attachments:
            try:
                result = {
                    "filename": attachment.name,
                    "content_type": attachment.content_type,
                    "success": False,
                }

                # Check if file type is supported
                if not self.is_supported_file(attachment):
                    result["error"] = (
                        f"File type {attachment.content_type} is not supported"
                    )
                    logger.info(
                        "Unsupported file type",
                        filename=attachment.name,
                        content_type=attachment.content_type,
                    )
                    results.append(result)
                    continue

                # Download the file
                download_result = await self.download_attachment(
                    attachment, turn_context
                )

                if not download_result:
                    result["error"] = "Failed to download file"
                    results.append(result)
                    continue

                file_content, filename = download_result

                # Upload to RAG service
                upload_result = await self.upload_to_rag_service(
                    file_content,
                    filename,
                    attachment.content_type,
                    user_id,
                    conversation_id,
                )

                # Combine results
                result.update(upload_result)
                results.append(result)

            except Exception as e:
                logger.error(
                    "Error processing attachment",
                    error=str(e),
                    filename=attachment.name,
                )

                results.append(
                    {
                        "filename": attachment.name,
                        "content_type": attachment.content_type,
                        "success": False,
                        "error": str(e),
                    }
                )

        return results

    def format_attachment_response(self, results: List[Dict[str, Any]]) -> str:
        """
        Format attachment processing results into a user-friendly message
        """
        if not results:
            return ""

        successful_uploads = [r for r in results if r.get("success")]
        failed_uploads = [r for r in results if not r.get("success")]

        message_parts = []

        if successful_uploads:
            message_parts.append("📎 **Attachments Processed Successfully:**")
            for result in successful_uploads:
                chunks = result.get("chunks_created", 0)
                message_parts.append(
                    f"✅ **{result['filename']}** - {chunks} chunks created, "
                    f"ready for search"
                )

            message_parts.append(
                "\n💡 You can now ask questions about these documents!"
            )

        if failed_uploads:
            message_parts.append("\n⚠️ **Some attachments could not be processed:**")
            for result in failed_uploads:
                error = result.get("error", "Unknown error")
                message_parts.append(f"❌ **{result['filename']}** - {error}")

        return "\n".join(message_parts)
