"""Document processor orchestrating extraction, chunking, and embedding.

Feature: 006-vector-search-rag
Tasks: T022, T023, T026

Orchestrates the full document processing pipeline:
1. Extract text from document
2. Chunk into segments
3. Generate embeddings
4. Store in vector database
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from indico_assistant.services.document.chunker import DocumentChunker, DocumentChunk
from indico_assistant.services.document.extractor import (
    DocumentExtractor,
    ExtractionError,
    UnsupportedFileTypeError,
)
from indico_assistant.services.embedding.cache import compute_content_hash

if TYPE_CHECKING:
    from indico_assistant.services.embedding import EmbeddingService
    from indico_assistant.services.vector_search.store import VectorStore
    from indico.modules.attachments.models.attachments import Attachment

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of document processing.
    
    Attributes:
        success: Whether processing completed successfully.
        attachment_id: Indico attachment ID.
        chunks_created: Number of chunks created.
        error: Error message if processing failed.
        skipped: Whether document was skipped (unchanged or unsupported).
    """
    success: bool
    attachment_id: int
    chunks_created: int = 0
    error: Optional[str] = None
    skipped: bool = False


class DocumentProcessor:
    """Orchestrates document extraction, chunking, embedding, and storage.
    
    This is the main entry point for processing documents for vector search.
    It coordinates the extractor, chunker, embedding service, and vector store.
    
    Attributes:
        _extractor: Document text extractor.
        _chunker: Text chunker for splitting documents.
        _embedding_service: Service for generating embeddings.
        _vector_store: Storage for document chunks and embeddings.
    
    Example:
        >>> processor = DocumentProcessor(
        ...     embedding_service=embedding_svc,
        ...     vector_store=store,
        ...     chunk_size=1000,
        ...     chunk_overlap=200
        ... )
        >>> result = processor.process_file(
        ...     file_path="/path/to/doc.pdf",
        ...     event_id=123,
        ...     attachment_id=456
        ... )
    """
    
    def __init__(
        self,
        embedding_service: "EmbeddingService",
        vector_store: "VectorStore",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        supported_extensions: Optional[list[str]] = None
    ) -> None:
        """Initialize the document processor.
        
        Args:
            embedding_service: Service for generating embeddings.
            vector_store: Storage for document chunks and embeddings.
            chunk_size: Target chunk size in characters.
            chunk_overlap: Overlap between chunks.
            supported_extensions: Optional list of supported file extensions.
        """
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._extractor = DocumentExtractor(supported_extensions)
        self._chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
    
    def process_file(
        self,
        file_path: Union[str, Path],
        event_id: int,
        attachment_id: int,
        force: bool = False
    ) -> ProcessingResult:
        """Process a document file for vector search.
        
        Args:
            file_path: Path to the document file.
            event_id: Indico event ID.
            attachment_id: Indico attachment ID.
            force: Force reprocessing even if content unchanged.
            
        Returns:
            ProcessingResult with status and details.
        """
        path = Path(file_path)
        
        # Check if file type is supported
        if not self._extractor.is_supported(path):
            logger.info(f"Skipping unsupported file type: {path.suffix}")
            return ProcessingResult(
                success=True,
                attachment_id=attachment_id,
                skipped=True,
                error=f"Unsupported file type: {path.suffix}"
            )
        
        try:
            # Extract text
            logger.debug(f"Extracting text from: {path}")
            text, metadata = self._extractor.extract_with_metadata(path)
            
            if not text or not text.strip():
                logger.info(f"No text content in: {path}")
                return ProcessingResult(
                    success=True,
                    attachment_id=attachment_id,
                    skipped=True,
                    error="No text content extracted"
                )
            
            # Compute content hash
            content_hash = compute_content_hash(text)
            
            # Check if content changed (unless force reprocessing)
            if not force:
                existing_hash = self._vector_store.get_content_hash(attachment_id)
                if existing_hash == content_hash:
                    logger.debug(f"Content unchanged for attachment {attachment_id}")
                    return ProcessingResult(
                        success=True,
                        attachment_id=attachment_id,
                        skipped=True,
                        error="Content unchanged"
                    )
            
            # Delete existing chunks for this attachment
            self._vector_store.delete_attachment_chunks(attachment_id)
            
            # Chunk text
            logger.debug(f"Chunking text ({len(text)} chars)")
            chunks = self._chunker.chunk(text, base_metadata=metadata)
            
            if not chunks:
                logger.info(f"No chunks generated for: {path}")
                return ProcessingResult(
                    success=True,
                    attachment_id=attachment_id,
                    skipped=True,
                    error="No chunks generated"
                )
            
            # Generate embeddings in batch
            logger.debug(f"Generating embeddings for {len(chunks)} chunks")
            texts = [chunk.text for chunk in chunks]
            embeddings = self._embedding_service.embed_batch(texts)
            
            # Prepare chunk data for storage
            chunk_data = []
            for chunk, embedding in zip(chunks, embeddings):
                chunk_metadata = dict(metadata)
                chunk_metadata.update({
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": len(chunks),
                })
                
                chunk_data.append({
                    "event_id": event_id,
                    "attachment_id": attachment_id,
                    "chunk_index": chunk.chunk_index,
                    "content_text": chunk.text,
                    "content_hash": content_hash,
                    "embedding": embedding,
                    "metadata": chunk_metadata,
                })
            
            # Store chunks with embeddings
            logger.debug(f"Storing {len(chunk_data)} chunks")
            self._vector_store.insert_chunks(chunk_data)
            
            logger.info(
                f"Processed {path.name}: {len(chunks)} chunks, "
                f"{len(text)} chars"
            )
            
            return ProcessingResult(
                success=True,
                attachment_id=attachment_id,
                chunks_created=len(chunks)
            )
            
        except UnsupportedFileTypeError as e:
            logger.info(f"Unsupported file: {e}")
            return ProcessingResult(
                success=True,
                attachment_id=attachment_id,
                skipped=True,
                error=str(e)
            )
        except ExtractionError as e:
            logger.error(f"Extraction failed: {e}")
            return ProcessingResult(
                success=False,
                attachment_id=attachment_id,
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Processing failed for {path}: {e}", exc_info=True)
            return ProcessingResult(
                success=False,
                attachment_id=attachment_id,
                error=str(e)
            )
    
    def process_content(
        self,
        content: bytes,
        filename: str,
        event_id: int,
        attachment_id: int,
        force: bool = False
    ) -> ProcessingResult:
        """Process document content from memory.
        
        Args:
            content: Document content as bytes.
            filename: Original filename (for type detection).
            event_id: Indico event ID.
            attachment_id: Indico attachment ID.
            force: Force reprocessing even if content unchanged.
            
        Returns:
            ProcessingResult with status and details.
        """
        import tempfile
        import os
        
        ext = Path(filename).suffix.lower()
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(
            suffix=ext, 
            delete=False,
            prefix=f"doc_{attachment_id}_"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            return self.process_file(
                file_path=tmp_path,
                event_id=event_id,
                attachment_id=attachment_id,
                force=force
            )
        finally:
            os.unlink(tmp_path)
    
    def process_attachment(
        self,
        attachment: "Attachment",
        event_id: int,
        force: bool = False
    ) -> dict:
        """Process an Indico attachment for vector search.
        
        Args:
            attachment: Indico Attachment model instance.
            event_id: Indico event ID.
            force: Force reprocessing even if content unchanged.
            
        Returns:
            Dict with success status and details.
        """
        from indico.modules.attachments.models.attachments import Attachment as AttachmentModel
        
        if not attachment.file:
            return {
                "success": True,
                "skipped": True,
                "error": "No file attached"
            }
        
        # Get file content
        try:
            content = attachment.file.open().read()
            filename = attachment.file.filename
        except Exception as e:
            logger.error(f"Failed to read attachment {attachment.id}: {e}")
            return {
                "success": False,
                "error": f"Failed to read file: {str(e)}"
            }
        
        # Process the content
        result = self.process_content(
            content=content,
            filename=filename,
            event_id=event_id,
            attachment_id=attachment.id,
            force=force
        )
        
        return {
            "success": result.success,
            "skipped": result.skipped,
            "chunks_created": result.chunks_created,
            "error": result.error
        }


if TYPE_CHECKING:
    from indico.modules.attachments.models.attachments import Attachment
