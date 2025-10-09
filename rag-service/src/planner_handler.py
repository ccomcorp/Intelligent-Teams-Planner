"""
Planner Attachment Handler for RAG Service
Phase 5: Planner Integration - Automatic Task Attachment Processing
"""

import io
import uuid
import re
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Security constants (aligned with Teams handler)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB limit
ALLOWED_HOSTS = [
    "teams.microsoft.com",
    "graph.microsoft.com",
    "sharepoint.com",
    "onedrive.live.com",
    "officeapps.live.com",
    "1drv.ms",
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


class PlannerAttachmentHandler:
    """
    Handles file attachments from Microsoft Planner tasks
    Monitors task attachments and forwards them to RAG service for processing
    """

    def __init__(
        self, graph_client_factory, rag_service_url: str = "http://localhost:7120"
    ):
        self.graph_client_factory = graph_client_factory
        self.rag_service_url = rag_service_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

        # Tracking processed attachments to avoid duplicates
        self.processed_attachments = set()

        # Supported file types for RAG processing (aligned with Teams handler)
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
            return f"planner_attachment_{uuid.uuid4().hex[:8]}"

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

        return filename or f"planner_attachment_{uuid.uuid4().hex[:8]}"

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

    def is_supported_file(self, attachment_info: Dict[str, Any]) -> bool:
        """Check if file type is supported for RAG processing"""
        content_type = attachment_info.get("contentType", "")
        filename = attachment_info.get("name", "")
        download_url = attachment_info.get("@microsoft.graph.downloadUrl", "")

        if content_type not in self.supported_types:
            return False

        # Additional security checks
        if not self._validate_file_extension(filename):
            logger.warning(
                "Planner file rejected due to dangerous extension", filename=filename
            )
            return False

        if not self._validate_url(download_url):
            logger.warning(
                "Planner file rejected due to invalid URL", url=download_url[:100]
            )
            return False

        return True

    async def get_task_attachments(
        self, task_id: str, user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Get attachments for a specific Planner task

        Returns:
            List of attachment information dictionaries
        """
        try:
            graph_client = await self.graph_client_factory(user_id)

            # Get task attachments via Graph API
            # Note: Planner task attachments are actually references
            # to files stored elsewhere
            endpoint = f"/planner/tasks/{task_id}/details"

            response = await graph_client._make_request("GET", endpoint, user_id)

            if not response:
                return []

            # Extract attachment references from task details
            attachments = []
            references = response.get("references", {})

            for ref_key, ref_data in references.items():
                if (
                    ref_data.get("type") == "PowerPoint"
                    or ref_data.get("type") == "Word"
                    or ref_data.get("type") == "Excel"
                ):
                    attachment_info = {
                        "id": ref_key,
                        "name": ref_data.get("alias", "Unknown"),
                        "url": ref_data.get("href", ""),
                        "type": ref_data.get("type", ""),
                        "contentType": self._guess_content_type(
                            ref_data.get("alias", "")
                        ),
                        "@microsoft.graph.downloadUrl": ref_data.get("href", ""),
                    }
                    attachments.append(attachment_info)

            logger.info(
                "Retrieved task attachments",
                task_id=task_id,
                attachment_count=len(attachments),
            )

            return attachments

        except Exception as e:
            logger.error(
                "Error retrieving task attachments", error=str(e), task_id=task_id
            )
            return []

    def _guess_content_type(self, filename: str) -> str:
        """Guess content type from filename extension"""
        if not filename:
            return "application/octet-stream"

        ext = filename.split(".")[-1].lower() if "." in filename else ""

        content_type_map = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            "xls": "application/vnd.ms-excel",
            "xlsx": (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            "ppt": "application/vnd.ms-powerpoint",
            "pptx": (
                "application/vnd.openxmlformats-officedocument"
                ".presentationml.presentation"
            ),
            "txt": "text/plain",
            "md": "text/markdown",
            "csv": "text/csv",
            "json": "application/json",
            "xml": "application/xml",
        }

        return content_type_map.get(ext, "application/octet-stream")

    async def download_attachment(
        self, attachment_info: Dict[str, Any], user_id: str = "default"
    ) -> Optional[Tuple[bytes, str]]:
        """
        Download file attachment from Planner task

        Returns:
            Tuple of (file_content, filename) or None if download fails
        """
        try:
            download_url = attachment_info.get("@microsoft.graph.downloadUrl", "")
            filename = attachment_info.get("name", "")

            if not download_url:
                logger.warning("Attachment has no download URL", name=filename)
                return None

            logger.info(
                "Downloading Planner attachment", name=filename, url=download_url[:100]
            )

            # For Planner attachments, we may need to get a fresh download URL
            # via Graph API
            graph_client = await self.graph_client_factory(user_id)
            access_token = await graph_client.auth_service.get_access_token(user_id)

            # Prepare headers for download
            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

            # Download the file with size limit
            response = await self.client.get(
                download_url, headers=headers, follow_redirects=True
            )

            if response.status_code == 200:
                content = response.content

                # Check file size limit
                if len(content) > MAX_FILE_SIZE:
                    logger.warning(
                        "Planner file rejected due to size limit",
                        filename=filename,
                        size=len(content),
                        limit=MAX_FILE_SIZE,
                    )
                    return None

                # Sanitize filename
                safe_filename = self._sanitize_filename(filename)

                logger.info(
                    "Successfully downloaded Planner attachment",
                    filename=safe_filename,
                    size=len(content),
                )

                return content, safe_filename

            else:
                logger.error(
                    "Failed to download Planner attachment",
                    status_code=response.status_code,
                    response=response.text[:200],
                )
                return None

        except Exception as e:
            logger.error(
                "Error downloading Planner attachment",
                error=str(e),
                name=attachment_info.get("name", ""),
            )
            return None

    async def upload_to_rag_service(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        task_id: str,
        task_title: str = "",
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        Upload downloaded file to RAG service for processing

        Returns:
            Dictionary with upload result
        """
        try:
            # Sanitize inputs to prevent injection
            safe_filename = self._sanitize_filename(filename)
            safe_task_id = re.sub(r"[^\w-]", "", task_id)[:100]
            safe_task_title = re.sub(r"[^\w\s.-]", "", task_title)[:500]
            safe_user_id = re.sub(r"[^\w@.-]", "", user_id)[:100]

            logger.info(
                "Uploading Planner file to RAG service",
                filename=safe_filename,
                task_id=safe_task_id,
                size=len(file_content),
            )

            # Prepare multipart form data
            files = {"file": (safe_filename, io.BytesIO(file_content), content_type)}

            data = {
                "source": "planner",
                "source_id": safe_task_id,
                "user_id": safe_user_id,
                "task_id": safe_task_id,
                "task_title": safe_task_title,
            }

            # Upload to RAG service
            response = await self.client.post(
                f"{self.rag_service_url}/api/upload", files=files, data=data
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "Successfully uploaded Planner file to RAG service",
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
                    "RAG service upload failed for Planner file",
                    status_code=response.status_code,
                    response=response.text[:200],
                )

                return {
                    "success": False,
                    "error": f"Upload failed: {response.status_code}",
                }

        except Exception as e:
            logger.error("Error uploading Planner file to RAG service", error=str(e))
            return {"success": False, "error": str(e)}

    async def process_task_attachments(
        self, task_id: str, task_title: str = "", user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """
        Process all attachments for a specific Planner task

        Returns:
            List of processing results for each attachment
        """
        results: List[Dict[str, Any]] = []

        try:
            # Get task attachments
            attachments = await self.get_task_attachments(task_id, user_id)

            if not attachments:
                logger.info("No attachments found for task", task_id=task_id)
                return results

            logger.info(
                "Processing Planner task attachments",
                task_id=task_id,
                count=len(attachments),
            )

            for attachment in attachments:
                try:
                    attachment_id = attachment.get("id", "")
                    filename = attachment.get("name", "")

                    # Skip if already processed
                    if attachment_id in self.processed_attachments:
                        logger.debug(
                            "Skipping already processed attachment",
                            attachment_id=attachment_id,
                        )
                        continue

                    result = {
                        "attachment_id": attachment_id,
                        "filename": filename,
                        "task_id": task_id,
                        "success": False,
                    }

                    # Check if file type is supported
                    if not self.is_supported_file(attachment):
                        result["error"] = "File type not supported or invalid"
                        logger.info(
                            "Unsupported Planner file type",
                            filename=filename,
                            content_type=attachment.get("contentType"),
                        )
                        results.append(result)
                        continue

                    # Download the file
                    download_result = await self.download_attachment(
                        attachment, user_id
                    )

                    if not download_result:
                        result["error"] = "Failed to download file"
                        results.append(result)
                        continue

                    file_content, safe_filename = download_result

                    # Upload to RAG service
                    upload_result = await self.upload_to_rag_service(
                        file_content,
                        safe_filename,
                        attachment.get("contentType", "application/octet-stream"),
                        task_id,
                        task_title,
                        user_id,
                    )

                    # Combine results
                    result.update(upload_result)
                    results.append(result)

                    # Mark as processed if successful
                    if upload_result.get("success"):
                        self.processed_attachments.add(attachment_id)

                except Exception as e:
                    logger.error(
                        "Error processing Planner attachment",
                        error=str(e),
                        attachment_id=attachment.get("id", ""),
                        filename=attachment.get("name", ""),
                    )

                    results.append(
                        {
                            "attachment_id": attachment.get("id", ""),
                            "filename": attachment.get("name", ""),
                            "task_id": task_id,
                            "success": False,
                            "error": str(e),
                        }
                    )

        except Exception as e:
            logger.error(
                "Error processing task attachments", error=str(e), task_id=task_id
            )

        return results

    def format_processing_results(self, results: List[Dict[str, Any]]) -> str:
        """
        Format attachment processing results into a user-friendly message
        """
        if not results:
            return "No attachments found for processing."

        successful_uploads = [r for r in results if r.get("success")]
        failed_uploads = [r for r in results if not r.get("success")]

        message_parts = []

        if successful_uploads:
            message_parts.append("📋 **Planner Attachments Processed Successfully:**")
            for result in successful_uploads:
                chunks = result.get("chunks_created", 0)
                message_parts.append(
                    f"✅ **{result['filename']}** - {chunks} chunks created, "
                    f"ready for search (Task: {result.get('task_id', '')})"
                )

            message_parts.append(
                "\n💡 You can now ask questions about these documents "
                "using task filters!"
            )

        if failed_uploads:
            message_parts.append(
                "\n⚠️ **Some Planner attachments could not be processed:**"
            )
            for result in failed_uploads:
                error = result.get("error", "Unknown error")
                message_parts.append(f"❌ **{result['filename']}** - {error}")

        return "\n".join(message_parts)
