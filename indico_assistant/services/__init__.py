"""Indico Assistant services package.

This package contains service classes that encapsulate business logic
for the Indico Assistant plugin.

Services:
    - LLMService: Low-level LLM interaction service (from 002-llm-service-layer)
    - NL2SQLPipeline: Natural language to SQL translation pipeline (from 003-nl2sql-pipeline)
    - Vector Search: Document embedding, search, and RAG (from 006-vector-search-rag)
"""

from indico_assistant.services.llm import LLMService, create_llm_service
from indico_assistant.services.nl2sql import (
    NL2SQLPipeline,
    PipelineError,
    PipelineErrorType,
    PipelineResult,
    create_nl2sql_pipeline,
    create_nl2sql_pipeline_from_plugin,
)

# Vector Search services (006-vector-search-rag)
from indico_assistant.services.vector_search import (
    check_pgvector_available,
    reset_pgvector_cache,
    VectorStore,
    SearchService,
    RAGService,
)
from indico_assistant.services.embedding import EmbeddingService
from indico_assistant.services.document import (
    DocumentExtractor,
    DocumentChunker,
    DocumentProcessor,
)

__all__ = [
    # LLM Service (002)
    "LLMService",
    "create_llm_service",
    # NL2SQL Pipeline (003)
    "NL2SQLPipeline",
    "create_nl2sql_pipeline",
    "create_nl2sql_pipeline_from_plugin",
    "PipelineResult",
    "PipelineError",
    "PipelineErrorType",
    # Vector Search (006)
    "check_pgvector_available",
    "reset_pgvector_cache",
    "VectorStore",
    "SearchService",
    "RAGService",
    "EmbeddingService",
    "DocumentExtractor",
    "DocumentChunker",
    "DocumentProcessor",
]
