"""
Base Document Handler - Abstract class for all document ingestion sources
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, BinaryIO
from enum import Enum
from datetime import datetime
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class DocumentSource(str, Enum):
    """Supported document sources"""
    OPENWEBUI = "openwebui"
    TEAMS = "teams"
    PLANNER = "planner"
    SHAREPOINT = "sharepoint"
    MANUAL = "manual"


class DocumentMetadata(BaseModel):
    """Metadata for ingested documents"""
    filename: str
    source: DocumentSource
    source_id: Optional[str] = None  # task_id, message_id, etc.
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    content_type: str
    file_size: int
    task_id: Optional[str] = None  # For Planner attachments
    task_title: Optional[str] = None
    conversation_id: Optional[str] = None  # For Teams messages
    additional_metadata: Dict[str, Any] = {}


class ProcessedDocument(BaseModel):
    """Result of document processing"""
    document_id: str
    metadata: DocumentMetadata
    chunks: list[Dict[str, Any]]
    total_chunks: int
    processing_time: float
    success: bool
    error: Optional[str] = None


class BaseDocumentHandler(ABC):
    """
    Abstract base class for document ingestion handlers
    All source-specific handlers must inherit from this
    """

    def __init__(self, source: DocumentSource):
        self.source = source
        self.logger = logger.bind(handler=self.__class__.__name__, source=source.value)

    @abstractmethod
    async def validate_file(self, file_data: BinaryIO, metadata: Dict[str, Any]) -> bool:
        """
        Validate file before processing

        Args:
            file_data: Binary file data
            metadata: File metadata

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    async def extract_metadata(self, file_data: BinaryIO, source_metadata: Dict[str, Any]) -> DocumentMetadata:
        """
        Extract and enrich metadata from file and source

        Args:
            file_data: Binary file data
            source_metadata: Metadata from the source (Teams, Planner, etc.)

        Returns:
            DocumentMetadata object
        """
        pass

    @abstractmethod
    async def handle_upload(self, file_data: BinaryIO, metadata: Dict[str, Any]) -> ProcessedDocument:
        """
        Handle document upload from specific source

        Args:
            file_data: Binary file data
            metadata: Source-specific metadata

        Returns:
            ProcessedDocument with results
        """
        pass

    async def log_ingestion(self, document_id: str, metadata: DocumentMetadata, success: bool):
        """
        Log document ingestion event

        Args:
            document_id: Unique document identifier
            metadata: Document metadata
            success: Whether ingestion was successful
        """
        self.logger.info(
            "document_ingestion",
            document_id=document_id,
            source=metadata.source,
            filename=metadata.filename,
            success=success
        )

    def get_source_attribution(self, metadata: DocumentMetadata) -> str:
        """
        Generate human-readable source attribution

        Args:
            metadata: Document metadata

        Returns:
            Attribution string
        """
        if metadata.source == DocumentSource.TEAMS:
            return f"Teams chat (uploaded by {metadata.uploaded_by})"
        elif metadata.source == DocumentSource.PLANNER:
            return f"Planner task: {metadata.task_title} (ID: {metadata.task_id})"
        elif metadata.source == DocumentSource.OPENWEBUI:
            return f"OpenWebUI workspace (uploaded by {metadata.uploaded_by})"
        elif metadata.source == DocumentSource.SHAREPOINT:
            return f"SharePoint (uploaded by {metadata.uploaded_by})"
        else:
            return f"Manual upload (uploaded by {metadata.uploaded_by})"
