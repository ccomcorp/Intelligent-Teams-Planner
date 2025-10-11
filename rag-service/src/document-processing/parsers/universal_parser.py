"""
Universal Document Parser using Unstructured.io
Story 6.1: Advanced Document Processing Pipeline

This module provides intelligent document processing with multi-format support,
content extraction, and automated classification capabilities using Unstructured.io.
"""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, BinaryIO
import asyncio
import logging
from datetime import datetime, timezone

import structlog
from unstructured.partition.auto import partition
from unstructured.chunking.title import chunk_by_title
# Note: elements_to_json import removed as it's not used and causes NumPy 2.x compatibility issues

logger = structlog.get_logger(__name__)


class UniversalDocumentParser:
    """
    Universal document parser using Unstructured.io for multi-format document processing.

    Supports:
    - PDF documents with layout preservation
    - Microsoft Office formats (Word, Excel, PowerPoint)
    - Images with OCR (JPEG, PNG, TIFF)
    - Plain text and CSV files
    - Advanced chunking and content extraction
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the universal document parser"""
        self.config = config or {}

        # Document format mappings
        self.supported_formats = {
            'application/pdf': 'pdf',
            'application/msword': 'doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.ms-excel': 'xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            'application/vnd.ms-powerpoint': 'ppt',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
            'text/plain': 'txt',
            'text/csv': 'csv',
            'text/html': 'html',
            'image/jpeg': 'jpg',
            'image/png': 'png',
            'image/tiff': 'tiff',
            'image/bmp': 'bmp'
        }

        # Chunking configuration
        self.chunk_config = {
            'max_characters': self.config.get('max_chunk_size', 1000),
            'new_after_n_chars': self.config.get('new_after_n_chars', 800),
            'combine_text_under_n_chars': self.config.get('combine_text_under_n_chars', 200),
            'overlap': self.config.get('chunk_overlap', 100)
        }

        # OCR configuration
        self.ocr_enabled = self.config.get('ocr_enabled', True)
        self.ocr_languages = self.config.get('ocr_languages', ['eng'])

        logger.info("UniversalDocumentParser initialized",
                   supported_formats=len(self.supported_formats),
                   ocr_enabled=self.ocr_enabled)

    async def parse_document(
        self,
        content: Union[bytes, BinaryIO],
        filename: str,
        mime_type: Optional[str] = None,
        **metadata
    ) -> Dict[str, Any]:
        """
        Parse document using Unstructured.io

        Args:
            content: Document content as bytes or file-like object
            filename: Original filename
            mime_type: MIME type of the document
            **metadata: Additional metadata to include

        Returns:
            Dictionary containing parsed document data with chunks
        """
        try:
            document_id = str(uuid.uuid4())
            start_time = datetime.now(timezone.utc)

            logger.info("Starting document parsing",
                       document_id=document_id,
                       filename=filename,
                       mime_type=mime_type)

            # Determine file format
            file_format = self._detect_format(filename, mime_type)

            if file_format == 'unknown':
                raise ValueError(f"Unsupported file format: {mime_type} for file {filename}")

            # Write content to temporary file for Unstructured.io
            with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as temp_file:
                if isinstance(content, bytes):
                    temp_file.write(content)
                else:
                    temp_file.write(content.read())
                temp_file_path = temp_file.name

            try:
                # Parse document with Unstructured.io
                elements = await self._partition_document(temp_file_path, file_format)

                # Extract structured content
                structured_content = await self._extract_structured_content(elements)

                # Generate intelligent chunks
                chunks = await self._generate_chunks(elements, structured_content)

                # Extract metadata
                extracted_metadata = await self._extract_metadata(elements, filename, file_format)

                # Combine metadata
                final_metadata = {
                    **extracted_metadata,
                    **metadata,
                    'document_id': document_id,
                    'filename': filename,
                    'file_format': file_format,
                    'mime_type': mime_type,
                    'parsed_at': start_time.isoformat(),
                    'parser_version': 'unstructured-0.11+',
                    'processing_success': True
                }

                result = {
                    'document_id': document_id,
                    'filename': filename,
                    'file_format': file_format,
                    'mime_type': mime_type,
                    'content': structured_content,
                    'chunks': chunks,
                    'metadata': final_metadata,
                    'elements_count': len(elements),
                    'chunks_count': len(chunks),
                    'processing_time_ms': (datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
                    'processing_success': True,
                    'error': None
                }

                logger.info("Document parsing completed successfully",
                           document_id=document_id,
                           elements_count=len(elements),
                           chunks_count=len(chunks),
                           processing_time_ms=result['processing_time_ms'])

                return result

            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass

        except Exception as e:
            logger.error("Document parsing failed",
                        filename=filename,
                        error=str(e),
                        exc_info=True)

            return {
                'document_id': document_id if 'document_id' in locals() else str(uuid.uuid4()),
                'filename': filename,
                'processing_success': False,
                'error': str(e),
                'content': None,
                'chunks': [],
                'metadata': {'filename': filename, 'error': str(e)}
            }

    async def _partition_document(self, file_path: str, file_format: str) -> List:
        """Partition document using Unstructured.io"""
        try:
            # Configure partitioning strategy based on file format
            partition_kwargs = {
                'filename': file_path,
                'strategy': 'auto',  # Let Unstructured.io choose the best strategy
                'include_page_breaks': True,
            }

            # Add OCR configuration for image formats
            if file_format in ['jpg', 'png', 'tiff', 'bmp']:
                partition_kwargs.update({
                    'strategy': 'ocr_only' if self.ocr_enabled else 'fast',
                    'languages': self.ocr_languages
                })

            # Add hi-res strategy for PDFs
            elif file_format == 'pdf':
                partition_kwargs.update({
                    'strategy': 'hi_res',  # Better layout detection
                    'infer_table_structure': True,
                    'extract_images_in_pdf': True
                })

            # Run partitioning in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            elements = await loop.run_in_executor(
                None,
                lambda: partition(**partition_kwargs)
            )

            logger.debug("Document partitioned successfully",
                        elements_count=len(elements),
                        file_format=file_format)

            return elements

        except Exception as e:
            logger.error("Document partitioning failed",
                        file_path=file_path,
                        file_format=file_format,
                        error=str(e))
            raise

    async def _extract_structured_content(self, elements: List) -> Dict[str, Any]:
        """Extract structured content from document elements"""
        content = {
            'text': '',
            'title': '',
            'tables': [],
            'images': [],
            'lists': [],
            'headers': [],
            'metadata_elements': []
        }

        for element in elements:
            element_type = str(type(element).__name__)
            element_text = str(element)

            # Add to full text
            content['text'] += element_text + '\n'

            # Categorize by element type
            if 'Title' in element_type:
                if not content['title']:  # Use first title as document title
                    content['title'] = element_text
                content['headers'].append({
                    'level': 1,
                    'text': element_text,
                    'type': element_type
                })

            elif 'Header' in element_type:
                content['headers'].append({
                    'level': 2,
                    'text': element_text,
                    'type': element_type
                })

            elif 'Table' in element_type:
                content['tables'].append({
                    'text': element_text,
                    'type': element_type,
                    'metadata': getattr(element, 'metadata', {})
                })

            elif 'List' in element_type:
                content['lists'].append({
                    'text': element_text,
                    'type': element_type
                })

            elif 'Image' in element_type:
                content['images'].append({
                    'text': element_text,
                    'type': element_type,
                    'metadata': getattr(element, 'metadata', {})
                })

            # Store element metadata
            if hasattr(element, 'metadata'):
                content['metadata_elements'].append({
                    'type': element_type,
                    'text': element_text[:200],  # Truncate for storage
                    'metadata': element.metadata
                })

        # Clean up text
        content['text'] = content['text'].strip()

        # Generate summary statistics
        content['stats'] = {
            'total_elements': len(elements),
            'text_length': len(content['text']),
            'tables_count': len(content['tables']),
            'images_count': len(content['images']),
            'lists_count': len(content['lists']),
            'headers_count': len(content['headers'])
        }

        logger.debug("Structured content extracted",
                    text_length=content['stats']['text_length'],
                    elements_count=content['stats']['total_elements'])

        return content

    async def _generate_chunks(self, elements: List, structured_content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate intelligent chunks using Unstructured.io chunking"""
        try:
            # Use Unstructured.io's title-based chunking
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                None,
                lambda: chunk_by_title(
                    elements,
                    max_characters=self.chunk_config['max_characters'],
                    new_after_n_chars=self.chunk_config['new_after_n_chars'],
                    combine_text_under_n_chars=self.chunk_config['combine_text_under_n_chars']
                )
            )

            # Convert chunks to our format
            formatted_chunks = []
            for i, chunk in enumerate(chunks):
                chunk_text = str(chunk)

                # Extract chunk metadata
                chunk_metadata = {
                    'chunk_index': i,
                    'chunk_type': str(type(chunk).__name__),
                    'char_count': len(chunk_text),
                    'word_count': len(chunk_text.split()),
                    'source_elements': []
                }

                # Add element metadata if available
                if hasattr(chunk, 'metadata') and chunk.metadata:
                    try:
                        # Handle ElementMetadata objects from unstructured
                        if hasattr(chunk.metadata, '__dict__'):
                            # Safely extract metadata attributes
                            for attr_name in dir(chunk.metadata):
                                if not attr_name.startswith('_') and not callable(getattr(chunk.metadata, attr_name, None)):
                                    try:
                                        attr_value = getattr(chunk.metadata, attr_name)
                                        # Only add serializable values
                                        if attr_value is not None and isinstance(attr_value, (str, int, float, bool, list, dict)):
                                            chunk_metadata[attr_name] = attr_value
                                    except (AttributeError, TypeError):
                                        continue
                        elif isinstance(chunk.metadata, dict):
                            # Direct dictionary update for regular dict metadata
                            chunk_metadata.update(chunk.metadata)
                    except (TypeError, AttributeError) as e:
                        # Log the error for debugging but don't fail the operation
                        logger.debug("Failed to extract chunk metadata",
                                   error=str(e),
                                   metadata_type=type(chunk.metadata).__name__)

                formatted_chunks.append({
                    'chunk_id': f"chunk_{i}",
                    'content': chunk_text,
                    'chunk_index': i,
                    'metadata': chunk_metadata,
                    'char_count': len(chunk_text),
                    'word_count': len(chunk_text.split())
                })

            logger.debug("Chunks generated",
                        chunks_count=len(formatted_chunks),
                        avg_chunk_size=sum(c['char_count'] for c in formatted_chunks) / len(formatted_chunks) if formatted_chunks else 0)

            return formatted_chunks

        except Exception as e:
            logger.error("Chunk generation failed", error=str(e))

            # Fallback: simple text splitting
            text = structured_content.get('text', '')
            if not text:
                return []

            chunk_size = self.chunk_config['max_characters']
            overlap = self.chunk_config['overlap']

            chunks = []
            for i in range(0, len(text), chunk_size - overlap):
                chunk_text = text[i:i + chunk_size]
                if chunk_text.strip():
                    chunks.append({
                        'chunk_id': f"chunk_{len(chunks)}",
                        'content': chunk_text,
                        'chunk_index': len(chunks),
                        'metadata': {
                            'chunk_index': len(chunks),
                            'chunk_type': 'text_fallback',
                            'char_count': len(chunk_text),
                            'word_count': len(chunk_text.split())
                        },
                        'char_count': len(chunk_text),
                        'word_count': len(chunk_text.split())
                    })

            return chunks

    async def _extract_metadata(self, elements: List, filename: str, file_format: str) -> Dict[str, Any]:
        """Extract metadata from document elements"""
        metadata = {
            'filename': filename,
            'file_format': file_format,
            'language': 'en',  # Default, could be detected
            'page_count': 0,
            'has_tables': False,
            'has_images': False,
            'has_lists': False,
            'element_types': [],
            'creation_date': None,
            'author': None,
            'title': None
        }

        element_types = set()

        for element in elements:
            element_type = str(type(element).__name__)
            element_types.add(element_type)

            # Check for specific content types
            if 'Table' in element_type:
                metadata['has_tables'] = True
            elif 'Image' in element_type:
                metadata['has_images'] = True
            elif 'List' in element_type:
                metadata['has_lists'] = True
            elif 'Title' in element_type and not metadata['title']:
                metadata['title'] = str(element)[:200]  # First title as document title

            # Extract page information
            if hasattr(element, 'metadata') and element.metadata:
                # Handle ElementMetadata objects properly
                try:
                    page_num = getattr(element.metadata, 'page_number', None)
                    if page_num:
                        metadata['page_count'] = max(metadata['page_count'], page_num)
                except (AttributeError, TypeError):
                    pass

                # Extract document metadata - handle ElementMetadata attributes
                for key in ['author', 'creation_date', 'subject', 'keywords']:
                    try:
                        value = getattr(element.metadata, key, None)
                        if value and not metadata.get(key):
                            metadata[key] = str(value)
                    except (AttributeError, TypeError):
                        pass

        metadata['element_types'] = list(element_types)
        metadata['complexity_score'] = self._calculate_complexity_score(metadata, len(elements))

        return metadata

    def _calculate_complexity_score(self, metadata: Dict[str, Any], element_count: int) -> float:
        """Calculate document complexity score (0-1)"""
        score = 0.0

        # Base score from element count
        score += min(element_count / 100, 0.3)

        # Add complexity for special content
        if metadata['has_tables']:
            score += 0.2
        if metadata['has_images']:
            score += 0.2
        if metadata['has_lists']:
            score += 0.1

        # Add complexity for multiple element types
        score += min(len(metadata['element_types']) / 10, 0.2)

        # Page count factor
        if metadata['page_count'] > 10:
            score += 0.1

        return min(score, 1.0)

    def _detect_format(self, filename: str, mime_type: Optional[str] = None) -> str:
        """Detect document format from filename and MIME type"""
        # Try MIME type first
        if mime_type and mime_type in self.supported_formats:
            return self.supported_formats[mime_type]

        # Fall back to file extension
        extension = Path(filename).suffix.lower()
        extension_map = {
            '.pdf': 'pdf',
            '.doc': 'doc',
            '.docx': 'docx',
            '.xls': 'xls',
            '.xlsx': 'xlsx',
            '.ppt': 'ppt',
            '.pptx': 'pptx',
            '.txt': 'txt',
            '.csv': 'csv',
            '.jpg': 'jpg',
            '.jpeg': 'jpg',
            '.png': 'png',
            '.tiff': 'tiff',
            '.tif': 'tiff',
            '.bmp': 'bmp'
        }

        return extension_map.get(extension, 'unknown')

    def get_supported_formats(self) -> List[str]:
        """Get list of supported document formats"""
        return list(set(self.supported_formats.values()))

    def get_format_info(self) -> Dict[str, Any]:
        """Get detailed information about supported formats"""
        return {
            'formats': self.get_supported_formats(),
            'mime_types': list(self.supported_formats.keys()),
            'ocr_enabled': self.ocr_enabled,
            'chunking_config': self.chunk_config,
            'parser_type': 'unstructured.io'
        }