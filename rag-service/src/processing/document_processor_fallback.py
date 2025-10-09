"""
Fallback document processor for testing without Docling dependencies
Story 6.1 Task 1: Basic document processing for testing
"""

import asyncio
import hashlib
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
import tempfile
import os

import structlog

logger = structlog.get_logger(__name__)


class DocumentProcessor:
    """
    Fallback document processor for testing without heavy dependencies
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Supported file formats (limited for fallback)
        self.supported_formats = {
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.json': 'application/json'
        }

        logger.info("DocumentProcessor (fallback) initialized",
                   supported_formats=list(self.supported_formats.keys()),
                   chunk_size=chunk_size)

    async def process_document(
        self,
        content: bytes,
        filename: str,
        source: str = "openwebui",
        source_id: Optional[str] = None,
        uploaded_by: str = "default",
        task_id: Optional[str] = None,
        task_title: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process document content (fallback implementation)
        """
        try:
            logger.info("Processing document (fallback)",
                       filename=filename,
                       source=source,
                       size=len(content),
                       uploaded_by=uploaded_by)

            # Generate document ID
            document_id = str(uuid.uuid4())

            # Validate file format
            file_ext = Path(filename).suffix.lower()
            if file_ext not in self.supported_formats:
                raise ValueError(f"Unsupported file format: {file_ext}. Supported: {list(self.supported_formats.keys())}")

            # Extract text content
            try:
                text_content = content.decode('utf-8')
            except UnicodeDecodeError:
                text_content = content.decode('utf-8', errors='ignore')

            # Extract structured content
            extracted_content = {
                "text": text_content,
                "tables": [],
                "figures": [],
                "outline": [],
                "page_count": 1
            }

            # Extract metadata
            doc_metadata = {
                "filename": filename,
                "file_extension": file_ext,
                "file_size": len(content),
                "content_hash": hashlib.sha256(content).hexdigest(),
                "processing_timestamp": asyncio.get_event_loop().time(),
                "source": source,
                "processed_with": "fallback_processor",
                "character_count": len(text_content),
                "word_count": len(text_content.split()),
                "line_count": text_content.count('\n') + 1
            }

            if metadata:
                doc_metadata.update(metadata)

            # Create text chunks
            chunks = await self._create_chunks(text_content)

            # Compile final document structure
            processed_doc = {
                "document_id": document_id,
                "filename": filename,
                "source": source,
                "source_id": source_id,
                "uploaded_by": uploaded_by,
                "file_size": len(content),
                "content_type": self.supported_formats[file_ext],
                "task_id": task_id,
                "task_title": task_title,
                "conversation_id": conversation_id,
                "metadata": doc_metadata,
                "extracted_content": extracted_content,
                "chunks": chunks,
                "processing_status": "completed"
            }

            logger.info("Document processed successfully (fallback)",
                       document_id=document_id,
                       source=source,
                       chunks_created=len(chunks),
                       text_length=len(text_content))

            return processed_doc

        except Exception as e:
            logger.error("Document processing failed (fallback)",
                        error=str(e),
                        filename=filename,
                        source=source)
            raise

    async def _create_chunks(self, text: str) -> List[Dict[str, Any]]:
        """Create overlapping text chunks for vector storage"""
        if not text or not text.strip():
            return []

        chunks = []
        words = text.split()

        if len(words) <= self.chunk_size:
            # Document is smaller than chunk size
            chunks.append({
                "content": text.strip(),
                "metadata": {
                    "chunk_index": 0,
                    "word_count": len(words),
                    "is_complete_document": True
                }
            })
        else:
            # Create overlapping chunks
            for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
                chunk_words = words[i:i + self.chunk_size]
                chunk_text = ' '.join(chunk_words).strip()

                if chunk_text:  # Only add non-empty chunks
                    chunks.append({
                        "content": chunk_text,
                        "metadata": {
                            "chunk_index": len(chunks),
                            "start_word": i,
                            "end_word": i + len(chunk_words),
                            "word_count": len(chunk_words),
                            "is_complete_document": False
                        }
                    })

        logger.debug("Created text chunks (fallback)",
                    total_chunks=len(chunks),
                    chunk_size=self.chunk_size,
                    overlap=self.chunk_overlap)
        return chunks

    def get_supported_formats(self) -> List[str]:
        """Get list of supported file formats"""
        return list(self.supported_formats.keys())

    async def validate_processing_result(self, processed_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Validate processing result quality"""
        validation_result = {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "quality_score": 1.0
        }

        # Basic validation
        required_fields = ["document_id", "filename", "source", "uploaded_by", "chunks"]
        for field in required_fields:
            if field not in processed_doc:
                validation_result["errors"].append(f"Missing required field: {field}")
                validation_result["is_valid"] = False

        return validation_result