"""RAG (Retrieval-Augmented Generation) service.

Feature: 006-vector-search-rag
Tasks: T035, T036, T037, T038, T041, T042

Provides context retrieval and integration for chat responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from indico_assistant.services.vector_search.search import SearchService, SearchResult

if TYPE_CHECKING:
    from indico_assistant.plugin import AssistantPlugin

logger = logging.getLogger(__name__)


@dataclass
class DocumentContext:
    """Context retrieved from documents for RAG.
    
    Attributes:
        text: Formatted context text for LLM prompt.
        sources: List of source references.
        chunks: Original search results.
    """
    text: str
    sources: list[dict[str, Any]]
    chunks: list[SearchResult] = field(default_factory=list)
    
    @property
    def has_context(self) -> bool:
        """Check if any context was retrieved."""
        return bool(self.text and self.chunks)


@dataclass 
class RAGResult:
    """Result of RAG processing.
    
    Attributes:
        should_use_rag: Whether RAG context should be used.
        context: Document context if available.
        query_type: Detected query type (document, sql, hybrid).
        search_results: Original search results for citation extraction (Feature 015: T022).
    """
    should_use_rag: bool
    context: Optional[DocumentContext]
    query_type: str
    search_results: list[Any] = field(default_factory=list)  # Feature 015: T022


class RAGService:
    """Service for Retrieval-Augmented Generation.
    
    Determines when to use document context and retrieves relevant
    information to augment LLM responses.
    
    Example:
        >>> rag = RAGService(search_service)
        >>> result = rag.get_context("What does the presentation say?", event_id=123)
        >>> if result.should_use_rag and result.context:
        ...     prompt = build_prompt(question, result.context.text)
    """
    
    # Keywords suggesting document-based queries
    DOCUMENT_KEYWORDS = {
        "presentation", "slide", "slides", "document", "paper", "pdf",
        "attachment", "file", "material", "says", "mentions", "according",
        "agenda", "schedule", "abstract", "summary", "content", "describe",
        "written", "stated", "talks about", "discusses", "explains"
    }
    
    # Keywords suggesting SQL-based queries  
    SQL_KEYWORDS = {
        "how many", "count", "list", "who", "registered", "participants",
        "events", "registrations", "number of", "total", "average",
        "earliest", "latest", "sessions", "contributions", "categories"
    }
    
    def __init__(
        self,
        search_service: SearchService,
        context_max_chunks: int = 3,
        context_max_chars: int = 2000,
        min_similarity: float = 0.7
    ) -> None:
        """Initialize the RAG service.
        
        Args:
            search_service: Service for semantic search.
            context_max_chunks: Maximum chunks to include in context.
            context_max_chars: Maximum total characters for context.
            min_similarity: Minimum similarity for chunk inclusion.
        """
        self._search_service = search_service
        self._context_max_chunks = context_max_chunks
        self._context_max_chars = context_max_chars
        self._min_similarity = min_similarity
    
    def classify_query(self, query: str) -> str:
        """Classify query as document, sql, or hybrid.
        
        Args:
            query: User's question.
            
        Returns:
            One of: "document", "sql", "hybrid"
        """
        query_lower = query.lower()
        
        has_document_keywords = any(
            kw in query_lower for kw in self.DOCUMENT_KEYWORDS
        )
        has_sql_keywords = any(
            kw in query_lower for kw in self.SQL_KEYWORDS
        )
        
        if has_document_keywords and has_sql_keywords:
            return "hybrid"
        elif has_document_keywords:
            return "document"
        else:
            return "sql"
    
    def should_use_document_context(
        self,
        query: str,
        event_id: Optional[int] = None
    ) -> bool:
        """Determine if document context would benefit this query.
        
        Args:
            query: User's question.
            event_id: Optional event context.
            
        Returns:
            True if document retrieval is recommended.
        """
        # Check if vector search is available
        if not self._search_service.is_available:
            return False
        
        # Classify the query
        query_type = self.classify_query(query)
        
        # Document or hybrid queries benefit from RAG
        return query_type in ("document", "hybrid")
    
    def get_context(
        self,
        query: str,
        event_id: Optional[int] = None,
        event_ids: Optional[list[int]] = None,
        user_id: Optional[int] = None,
        force: bool = False
    ) -> RAGResult:
        """Get document context for a query.
        
        Args:
            query: User's question.
            event_id: Optional single event to search.
            event_ids: Optional list of events to search.
            user_id: Optional user for permission filtering.
            force: Force retrieval even if query doesn't seem document-related.
            
        Returns:
            RAGResult with context and metadata.
        """
        query_type = self.classify_query(query)
        
        # Check if we should use RAG
        should_use = force or query_type in ("document", "hybrid")
        
        if not should_use:
            return RAGResult(
                should_use_rag=False,
                context=None,
                query_type=query_type
            )
        
        # Check availability
        if not self._search_service.is_available:
            logger.debug("RAG unavailable: search service not available")
            return RAGResult(
                should_use_rag=False,
                context=None,
                query_type=query_type
            )
        
        # Perform search
        search_response = self._search_service.search(
            query=query,
            event_id=event_id,
            event_ids=event_ids,
            user_id=user_id,
            top_k=self._context_max_chunks,
            threshold=self._min_similarity
        )
        
        if not search_response.success or not search_response.results:
            logger.debug(f"RAG search returned no results: {search_response.error}")
            return RAGResult(
                should_use_rag=query_type == "document",  # Still suggest for doc queries
                context=None,
                query_type=query_type
            )
        
        # Build context from results
        context = self._build_context(search_response.results)
        
        return RAGResult(
            should_use_rag=True,
            context=context,
            query_type=query_type,
            search_results=search_response.results  # Feature 015: T022
        )
    
    def _build_context(self, chunks: list[SearchResult]) -> DocumentContext:
        """Build context text from search results.
        
        Args:
            chunks: List of search results.
            
        Returns:
            DocumentContext with formatted text and sources.
        """
        context_parts = []
        sources = []
        total_chars = 0
        included_chunks = []
        
        for chunk in chunks:
            # Check character limit
            if total_chars + len(chunk.content) > self._context_max_chars:
                # Truncate if needed
                remaining = self._context_max_chars - total_chars
                if remaining > 100:  # Only include if meaningful
                    truncated = chunk.content[:remaining] + "..."
                    context_parts.append(self._format_chunk(chunk, truncated))
                    included_chunks.append(chunk)
                break
            
            context_parts.append(self._format_chunk(chunk, chunk.content))
            included_chunks.append(chunk)
            total_chars += len(chunk.content)
            
            # Build source reference
            source = {
                "filename": chunk.metadata.get("filename", "document"),
                "event_id": chunk.event_id,
                "attachment_id": chunk.attachment_id,
                "similarity": round(chunk.similarity, 3),
                "type": "document"
            }
            if chunk.metadata.get("page_number"):
                source["page"] = chunk.metadata["page_number"]
            sources.append(source)
        
        context_text = "\n\n---\n\n".join(context_parts)
        
        return DocumentContext(
            text=context_text,
            sources=sources,
            chunks=included_chunks
        )
    
    def _format_chunk(self, chunk: SearchResult, text: str) -> str:
        """Format a chunk for inclusion in context.
        
        Args:
            chunk: The search result.
            text: Text content (possibly truncated).
            
        Returns:
            Formatted context string.
        """
        filename = chunk.metadata.get("filename", "document")
        page_info = ""
        if chunk.metadata.get("page_number"):
            page_info = f", page {chunk.metadata['page_number']}"
        
        return f"From {filename}{page_info}:\n{text}"
    
    def build_rag_prompt(
        self,
        question: str,
        context: DocumentContext,
        base_prompt: Optional[str] = None
    ) -> str:
        """Build a prompt with RAG context.
        
        Args:
            question: User's question.
            context: Document context.
            base_prompt: Optional base system prompt.
            
        Returns:
            Prompt string with context incorporated.
        """
        context_section = f"""
The following context has been retrieved from event documents that may be relevant to the question:

<document_context>
{context.text}
</document_context>

Use this context to inform your response when relevant. If the context doesn't contain the answer, say so and answer based on other available information. When citing information from the context, reference the source document.
"""
        
        if base_prompt:
            return f"{base_prompt}\n\n{context_section}"
        return context_section
    
    def format_citations(self, sources: list[dict]) -> str:
        """Format source citations for a response.
        
        Args:
            sources: List of source dictionaries.
            
        Returns:
            Formatted citation string.
        """
        return self._format_citations_static(sources)
    
    @staticmethod
    def _format_citations_static(sources: list[dict]) -> str:
        """Format source citations for a response (static method).
        
        Args:
            sources: List of source dictionaries.
            
        Returns:
            Formatted citation string.
        """
        if not sources:
            return ""
        
        citations = []
        seen = set()
        
        for source in sources:
            filename = source.get("filename", "document")
            page = source.get("page")
            
            key = (filename, page)
            if key in seen:
                continue
            seen.add(key)
            
            if page:
                citations.append(f"- {filename} (page {page})")
            else:
                citations.append(f"- {filename}")
        
        if citations:
            return "Sources:\n" + "\n".join(citations)
        return ""


def create_rag_service(plugin: "AssistantPlugin") -> RAGService:
    """Factory function to create a RAGService.
    
    Args:
        plugin: The AssistantPlugin instance.
        
    Returns:
        Configured RAGService instance.
    """
    from indico_assistant.services.vector_search.search import create_search_service
    
    search_service = create_search_service(plugin)
    
    return RAGService(
        search_service=search_service,
        context_max_chunks=plugin.settings.get("max_search_results", 3),
        context_max_chars=2000,
        min_similarity=plugin.settings.get("similarity_threshold", 0.7)
    )
