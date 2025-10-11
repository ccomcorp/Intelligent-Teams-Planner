"""
Document processor with multi-format support using Unstructured.io
Story 6.1: Advanced Document Processing Pipeline
Aligned with IMPLEMENTATION-PLAN.md multi-source approach
"""

import asyncio
import hashlib
import uuid
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import tempfile
import os

import structlog
import importlib.util
import sys
import os

logger = structlog.get_logger(__name__)

# Import UniversalDocumentParser with proper path handling for hyphenated directory
document_processing_path = os.path.join(os.path.dirname(__file__), '..', 'document-processing', 'parsers', 'universal_parser.py')
spec = importlib.util.spec_from_file_location("universal_parser", document_processing_path)
universal_parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(universal_parser_module)
UniversalDocumentParser = universal_parser_module.UniversalDocumentParser

# Import TextEmbedder for semantic search capabilities
try:
    from ..embeddings.text_embedder import TextEmbedder
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    logger.warning("TextEmbedder not available - embeddings will be skipped")
    EMBEDDINGS_AVAILABLE = False


class DocumentProcessor:
    """
    Advanced document processor with multi-format support using Unstructured.io
    Supports multi-source ingestion (OpenWebUI, Teams, Planner)
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100, enable_embeddings: bool = True):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.enable_embeddings = enable_embeddings and EMBEDDINGS_AVAILABLE

        # Initialize Universal Document Parser with configuration
        parser_config = {
            'max_chunk_size': chunk_size,
            'chunk_overlap': chunk_overlap,
            'ocr_enabled': True,
            'ocr_languages': ['eng']
        }

        self.parser = UniversalDocumentParser(config=parser_config)

        # Initialize text embedder for semantic search
        self.text_embedder = None
        if self.enable_embeddings:
            try:
                self.text_embedder = TextEmbedder()
            except Exception as e:
                logger.warning("Failed to initialize text embedder", error=str(e))
                self.enable_embeddings = False

        logger.info("DocumentProcessor initialized",
                   supported_formats=self.parser.get_supported_formats(),
                   chunk_size=chunk_size,
                   parser_type='unstructured.io',
                   embeddings_enabled=self.enable_embeddings)

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
        Process document content with multi-source support using Unstructured.io

        Args:
            content: Raw document bytes
            filename: Original filename
            source: Source system (openwebui, teams, planner)
            source_id: ID from source system
            uploaded_by: User identifier
            task_id: Planner task ID (if applicable)
            task_title: Planner task title (if applicable)
            conversation_id: Teams conversation ID (if applicable)
            metadata: Additional metadata

        Returns:
            Processed document with chunks ready for vector storage
        """
        try:
            logger.info("Processing document",
                       filename=filename,
                       source=source,
                       size=len(content),
                       uploaded_by=uploaded_by)

            # Detect MIME type
            mime_type = self._get_content_type(Path(filename).suffix.lower())

            # Prepare additional metadata for parsing
            parsing_metadata = {
                'source': source,
                'source_id': source_id,
                'uploaded_by': uploaded_by,
                'task_id': task_id,
                'task_title': task_title,
                'conversation_id': conversation_id,
                'file_size': len(content)
            }

            if metadata:
                parsing_metadata.update(metadata)

            # Parse document using UniversalDocumentParser
            parsed_result = await self.parser.parse_document(
                content=content,
                filename=filename,
                mime_type=mime_type,
                **parsing_metadata
            )

            if not parsed_result.get('processing_success'):
                raise ValueError(f"Document parsing failed: {parsed_result.get('error')}")

            # Generate embeddings for chunks if enabled
            chunks_with_embeddings = parsed_result["chunks"]
            if self.enable_embeddings and self.text_embedder:
                try:
                    logger.info("Generating embeddings for document chunks",
                               document_id=parsed_result["document_id"],
                               chunks_count=len(chunks_with_embeddings))

                    chunks_with_embeddings = await self.text_embedder.embed_document_chunks(
                        chunks_with_embeddings
                    )

                    logger.info("Embeddings generated successfully",
                               document_id=parsed_result["document_id"],
                               embedded_chunks=len(chunks_with_embeddings))

                except Exception as e:
                    logger.warning("Failed to generate embeddings, proceeding without them",
                                 error=str(e),
                                 document_id=parsed_result["document_id"])

            # Transform to expected format for RAG service
            processed_doc = {
                "document_id": parsed_result["document_id"],
                "filename": filename,
                "source": source,
                "source_id": source_id,
                "uploaded_by": uploaded_by,
                "file_size": len(content),
                "content_type": mime_type,
                "task_id": task_id,
                "task_title": task_title,
                "conversation_id": conversation_id,
                "metadata": parsed_result["metadata"],
                "extracted_content": parsed_result["content"],
                "chunks": chunks_with_embeddings,
                "processing_status": "completed",
                "processing_time_ms": parsed_result.get("processing_time_ms", 0),
                "elements_count": parsed_result.get("elements_count", 0),
                "chunks_count": parsed_result.get("chunks_count", 0),
                "embeddings_generated": self.enable_embeddings and len(chunks_with_embeddings) > 0
            }

            logger.info("Document processed successfully",
                       document_id=parsed_result["document_id"],
                       source=source,
                       chunks_created=len(parsed_result["chunks"]),
                       text_length=len(parsed_result["content"].get("text", "")),
                       processing_time_ms=parsed_result.get("processing_time_ms", 0))

            return processed_doc

        except Exception as e:
            logger.error("Document processing failed",
                        error=str(e),
                        filename=filename,
                        source=source)
            raise

    async def _extract_structured_content(self, doc) -> Dict[str, Any]:
        """Extract structured content from Docling document"""
        try:
            # Get main text content in markdown format
            main_text = doc.export_to_markdown()

            # Extract tables if available
            tables = []
            if hasattr(doc, 'tables') and doc.tables:
                for table in doc.tables:
                    table_data = {
                        "caption": getattr(table, 'caption', ''),
                        "content": table.export_to_markdown() if hasattr(table, 'export_to_markdown') else str(table)
                    }
                    tables.append(table_data)

            # Extract images/figures metadata
            figures = []
            if hasattr(doc, 'pictures') and doc.pictures:
                for i, picture in enumerate(doc.pictures):
                    figure_data = {
                        "index": i,
                        "caption": getattr(picture, 'caption', ''),
                        "description": getattr(picture, 'description', '')
                    }
                    figures.append(figure_data)

            # Extract document structure/outline
            outline = []
            if hasattr(doc, 'headers') and doc.headers:
                for header in doc.headers:
                    outline_item = {
                        "level": getattr(header, 'level', 1),
                        "text": str(header)
                    }
                    outline.append(outline_item)

            return {
                "text": main_text,
                "tables": tables,
                "figures": figures,
                "outline": outline,
                "page_count": getattr(doc, 'page_count', 1) if hasattr(doc, 'page_count') else 1
            }

        except Exception as e:
            logger.error("Content extraction failed", error=str(e))
            # Fallback to basic text extraction
            return {
                "text": str(doc) if doc else "",
                "tables": [],
                "figures": [],
                "outline": [],
                "page_count": 1
            }

    async def _extract_metadata(self, doc, filename: str, content: bytes, source: str) -> Dict[str, Any]:
        """Extract document metadata with source attribution"""
        metadata = {
            "filename": filename,
            "file_extension": Path(filename).suffix.lower(),
            "file_size": len(content),
            "content_hash": hashlib.sha256(content).hexdigest(),
            "processing_timestamp": asyncio.get_event_loop().time(),
            "source": source,
            "processed_with": "docling"
        }

        # Extract document properties if available
        if hasattr(doc, 'meta') and doc.meta:
            doc_meta = doc.meta

            # Standard document properties
            for prop in ['title', 'author', 'subject', 'creator']:
                if hasattr(doc_meta, prop):
                    value = getattr(doc_meta, prop)
                    if value:
                        metadata[prop] = str(value)

            # Date properties
            for date_prop in ['creation_date', 'modification_date']:
                if hasattr(doc_meta, date_prop):
                    value = getattr(doc_meta, date_prop)
                    if value:
                        metadata[date_prop] = str(value)

        # Add document statistics
        if hasattr(doc, 'export_to_markdown'):
            text_content = doc.export_to_markdown()
            metadata.update({
                "character_count": len(text_content),
                "word_count": len(text_content.split()),
                "line_count": text_content.count('\n') + 1
            })

        return metadata

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

        logger.debug("Created text chunks",
                    total_chunks=len(chunks),
                    chunk_size=self.chunk_size,
                    overlap=self.chunk_overlap)
        return chunks

    def _get_content_type(self, file_ext: str) -> str:
        """Get MIME content type for file extension"""
        content_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.html': 'text/html',
            '.md': 'text/markdown',
            '.txt': 'text/plain',
            '.csv': 'text/plain',  # CSV files mapped to text/plain
            '.rtf': 'application/rtf',
            '.odt': 'application/vnd.oasis.opendocument.text',
            '.odp': 'application/vnd.oasis.opendocument.presentation',
            '.ods': 'application/vnd.oasis.opendocument.spreadsheet'
        }
        return content_types.get(file_ext, 'application/octet-stream')

    async def validate_processing_result(self, processed_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Validate processing result quality"""
        validation_result = {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "quality_score": 1.0
        }

        try:
            # Check required fields (aligned with implementation plan schema)
            required_fields = ["document_id", "filename", "source", "uploaded_by", "chunks"]
            for field in required_fields:
                if field not in processed_doc:
                    validation_result["errors"].append(f"Missing required field: {field}")
                    validation_result["is_valid"] = False

            # Validate source
            valid_sources = ["openwebui", "teams", "planner"]
            if processed_doc.get("source") not in valid_sources:
                validation_result["warnings"].append(f"Invalid source: {processed_doc.get('source')}")
                validation_result["quality_score"] *= 0.8

            # Check chunk quality
            chunks = processed_doc.get("chunks", [])
            if not chunks:
                validation_result["warnings"].append("No chunks created from document")
                validation_result["quality_score"] *= 0.5
            else:
                empty_chunks = sum(1 for chunk in chunks if not chunk.get("content", "").strip())
                if empty_chunks > 0:
                    validation_result["warnings"].append(f"{empty_chunks} empty chunks found")
                    validation_result["quality_score"] *= (1 - empty_chunks / len(chunks))

            # Check text extraction quality
            extracted_content = processed_doc.get("extracted_content", {})
            text_content = extracted_content.get("text", "")
            if len(text_content.strip()) < 10:
                validation_result["warnings"].append("Very little text extracted from document")
                validation_result["quality_score"] *= 0.3

            # Source-specific validations
            source = processed_doc.get("source")
            if source == "planner" and not processed_doc.get("task_id"):
                validation_result["warnings"].append("Planner source should have task_id")
                validation_result["quality_score"] *= 0.9

            if source == "teams" and not processed_doc.get("conversation_id"):
                validation_result["warnings"].append("Teams source should have conversation_id")
                validation_result["quality_score"] *= 0.9

        except Exception as e:
            validation_result["errors"].append(f"Validation error: {str(e)}")
            validation_result["is_valid"] = False

        return validation_result

    def get_supported_formats(self) -> List[str]:
        """Get list of supported file formats"""
        return self.parser.get_supported_formats()

    async def process_batch(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process multiple documents in batch"""
        results = []

        for doc_info in documents:
            try:
                result = await self.process_document(**doc_info)
                results.append(result)
            except Exception as e:
                logger.error("Batch processing failed for document",
                           filename=doc_info.get("filename"),
                           error=str(e))
                # Continue with other documents
                results.append({
                    "filename": doc_info.get("filename"),
                    "processing_status": "failed",
                    "error": str(e)
                })

        logger.info("Batch processing completed",
                   total_documents=len(documents),
                   successful=len([r for r in results if r.get("processing_status") == "completed"]),
                   failed=len([r for r in results if r.get("processing_status") == "failed"]))

        return results