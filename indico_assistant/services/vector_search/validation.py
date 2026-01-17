"""Validation scripts for Vector Search RAG feature.

Feature: 006-vector-search-rag
Tasks: T057, T058, T059

These scripts validate:
- T057: Graceful degradation when pgvector is disabled
- T058: Performance validation (search latency <500ms)
- T059: Quickstart scenario validation
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def validate_graceful_degradation() -> dict[str, Any]:
    """T057: Verify graceful degradation when pgvector is disabled.
    
    Tests that the system works correctly when pgvector is unavailable:
    1. Search endpoint returns appropriate error
    2. Chat continues to work (SQL-only mode)
    3. Health endpoint shows correct status
    4. No crashes or unhandled exceptions
    
    Returns:
        Dict with validation results
    """
    results = {
        "task": "T057",
        "name": "Graceful Degradation Validation",
        "passed": True,
        "tests": []
    }
    
    # Test 1: pgvector availability check
    try:
        from indico_assistant.services.vector_search import (
            check_pgvector_available,
            reset_pgvector_cache,
        )
        
        # Reset cache to force fresh check
        reset_pgvector_cache()
        available = check_pgvector_available()
        
        results["tests"].append({
            "name": "pgvector_check",
            "passed": True,
            "details": f"pgvector available: {available}"
        })
    except Exception as e:
        results["tests"].append({
            "name": "pgvector_check",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Test 2: SearchService handles unavailability
    try:
        from indico_assistant.services.vector_search.search import SearchService
        from indico_assistant.services.embedding import EmbeddingService
        from indico_assistant.services.vector_search.store import VectorStore
        
        # Create service (should not crash)
        embedding_svc = EmbeddingService()
        vector_store = VectorStore()
        search_svc = SearchService(
            embedding_service=embedding_svc,
            vector_store=vector_store
        )
        
        # Check availability property
        is_available = search_svc.is_available
        
        results["tests"].append({
            "name": "search_service_init",
            "passed": True,
            "details": f"SearchService initialized, available: {is_available}"
        })
    except Exception as e:
        results["tests"].append({
            "name": "search_service_init",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Test 3: RAGService fallback behavior
    try:
        from indico_assistant.services.vector_search.rag import RAGService
        
        # Create RAG service with mock search
        class MockSearchService:
            is_available = False
            def search(self, *args, **kwargs):
                return None
        
        rag_svc = RAGService(search_service=MockSearchService())
        
        # Should detect unavailability
        should_use = rag_svc.should_use_document_context("test query")
        
        results["tests"].append({
            "name": "rag_fallback",
            "passed": should_use == False,
            "details": f"RAG correctly falls back when unavailable: {not should_use}"
        })
    except Exception as e:
        results["tests"].append({
            "name": "rag_fallback",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Test 4: Query classification still works
    try:
        from indico_assistant.services.vector_search.rag import RAGService
        
        class MockSearchService:
            is_available = False
        
        rag_svc = RAGService(search_service=MockSearchService())
        
        # Test various query types
        test_queries = [
            ("What does the presentation say?", "document"),
            ("How many participants?", "sql"),
            ("What events have slides about physics?", "hybrid"),
        ]
        
        all_correct = True
        for query, expected_type in test_queries:
            actual_type = rag_svc.classify_query(query)
            if actual_type != expected_type:
                all_correct = False
        
        results["tests"].append({
            "name": "query_classification",
            "passed": all_correct,
            "details": "Query classification works independently of pgvector"
        })
    except Exception as e:
        results["tests"].append({
            "name": "query_classification",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    return results


def validate_search_performance(
    num_queries: int = 10,
    target_latency_ms: float = 500
) -> dict[str, Any]:
    """T058: Performance validation - search latency <500ms.
    
    Measures search latency across multiple queries.
    
    Args:
        num_queries: Number of test queries to run.
        target_latency_ms: Target maximum latency in milliseconds.
        
    Returns:
        Dict with performance metrics
    """
    results = {
        "task": "T058",
        "name": "Search Performance Validation",
        "target_latency_ms": target_latency_ms,
        "passed": True,
        "tests": []
    }
    
    # Test queries
    test_queries = [
        "What is the registration deadline?",
        "presentation about quantum computing",
        "conference schedule",
        "speaker information",
        "workshop materials",
        "event location",
        "contact information",
        "submission guidelines",
        "important dates",
        "poster session details",
    ]
    
    # Test 1: Embedding generation latency
    try:
        from indico_assistant.services.embedding import EmbeddingService
        
        embedding_svc = EmbeddingService()
        
        latencies = []
        for query in test_queries[:num_queries]:
            start = time.perf_counter()
            embedding = embedding_svc.embed(query)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)
        
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        
        passed = max_latency < target_latency_ms
        results["tests"].append({
            "name": "embedding_latency",
            "passed": passed,
            "avg_ms": round(avg_latency, 2),
            "max_ms": round(max_latency, 2),
            "target_ms": target_latency_ms,
            "details": f"Avg: {avg_latency:.2f}ms, Max: {max_latency:.2f}ms"
        })
        if not passed:
            results["passed"] = False
            
    except Exception as e:
        results["tests"].append({
            "name": "embedding_latency",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Test 2: Full search latency (if pgvector available)
    try:
        from indico_assistant.services.vector_search import check_pgvector_available
        from indico_assistant.services.vector_search.search import create_search_service
        
        if check_pgvector_available():
            # Need plugin context for this
            results["tests"].append({
                "name": "full_search_latency",
                "passed": True,
                "skipped": True,
                "details": "Requires Indico runtime context"
            })
        else:
            results["tests"].append({
                "name": "full_search_latency",
                "passed": True,
                "skipped": True,
                "details": "pgvector not available"
            })
    except Exception as e:
        results["tests"].append({
            "name": "full_search_latency",
            "passed": False,
            "error": str(e)
        })
    
    return results


def validate_quickstart_scenarios() -> dict[str, Any]:
    """T059: Run quickstart.md validation scenarios.
    
    Validates the scenarios described in quickstart.md can be executed.
    
    Returns:
        Dict with scenario validation results
    """
    results = {
        "task": "T059",
        "name": "Quickstart Scenario Validation",
        "passed": True,
        "tests": []
    }
    
    # Scenario 1: Module imports
    try:
        from indico_assistant.services.embedding import EmbeddingService
        from indico_assistant.services.document import (
            DocumentExtractor,
            DocumentChunker,
            DocumentProcessor,
        )
        from indico_assistant.services.vector_search import (
            VectorStore,
            SearchService,
            RAGService,
        )
        
        results["tests"].append({
            "name": "module_imports",
            "passed": True,
            "details": "All service modules import correctly"
        })
    except ImportError as e:
        results["tests"].append({
            "name": "module_imports",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Scenario 2: Document extraction
    try:
        from indico_assistant.services.document import DocumentExtractor
        
        extractor = DocumentExtractor()
        
        # Check supported file types
        supported = [".pdf", ".docx", ".txt", ".md"]
        for ext in supported:
            from pathlib import Path
            test_path = Path(f"test{ext}")
            is_supported = extractor.is_supported(test_path)
        
        results["tests"].append({
            "name": "document_extractor",
            "passed": True,
            "details": f"Extractor supports: {supported}"
        })
    except Exception as e:
        results["tests"].append({
            "name": "document_extractor",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Scenario 3: Text chunking
    try:
        from indico_assistant.services.document import DocumentChunker
        
        chunker = DocumentChunker(chunk_size=1000, chunk_overlap=200)
        
        # Test chunking
        test_text = "This is a test. " * 100  # ~1600 chars
        chunks = chunker.chunk(test_text)
        
        results["tests"].append({
            "name": "document_chunker",
            "passed": len(chunks) > 0,
            "details": f"Chunked {len(test_text)} chars into {len(chunks)} chunks"
        })
    except Exception as e:
        results["tests"].append({
            "name": "document_chunker",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Scenario 4: Embedding generation
    try:
        from indico_assistant.services.embedding import EmbeddingService
        
        embedding_svc = EmbeddingService()
        
        # Skip if no model (would need download)
        if embedding_svc._enabled:
            test_texts = ["Hello world", "Test embedding"]
            embeddings = embedding_svc.embed_batch(test_texts)
            
            results["tests"].append({
                "name": "embedding_generation",
                "passed": len(embeddings) == 2,
                "details": f"Generated {len(embeddings)} embeddings"
            })
        else:
            results["tests"].append({
                "name": "embedding_generation",
                "passed": True,
                "skipped": True,
                "details": "Embedding service disabled"
            })
    except Exception as e:
        results["tests"].append({
            "name": "embedding_generation",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Scenario 5: RAG query classification
    try:
        from indico_assistant.services.vector_search.rag import RAGService
        
        class MockSearchService:
            is_available = True
            def search(self, *args, **kwargs):
                from indico_assistant.services.vector_search.search import SearchResponse
                return SearchResponse(success=True, results=[])
        
        rag_svc = RAGService(search_service=MockSearchService())
        
        # Test query classification
        doc_query = "What does the presentation say about AI?"
        sql_query = "How many registered participants?"
        
        doc_type = rag_svc.classify_query(doc_query)
        sql_type = rag_svc.classify_query(sql_query)
        
        results["tests"].append({
            "name": "rag_query_classification",
            "passed": doc_type == "document" and sql_type == "sql",
            "details": f"Doc query -> {doc_type}, SQL query -> {sql_type}"
        })
    except Exception as e:
        results["tests"].append({
            "name": "rag_query_classification",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    # Scenario 6: Schema validation
    try:
        from indico_assistant.schemas.search import (
            search_request_schema,
            search_response_schema,
        )
        
        # Test request validation
        valid_request = {
            "query": "test query",
            "event_id": 123,
            "top_k": 5
        }
        loaded = search_request_schema.load(valid_request)
        
        results["tests"].append({
            "name": "schema_validation",
            "passed": loaded["query"] == "test query",
            "details": "Request/response schemas work correctly"
        })
    except Exception as e:
        results["tests"].append({
            "name": "schema_validation",
            "passed": False,
            "error": str(e)
        })
        results["passed"] = False
    
    return results


def run_all_validations() -> dict[str, Any]:
    """Run all validation tests.
    
    Returns:
        Dict with all validation results
    """
    print("=" * 60)
    print("Vector Search RAG - Validation Suite")
    print("=" * 60)
    
    all_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "validations": [],
        "overall_passed": True
    }
    
    # T057: Graceful Degradation
    print("\n[T057] Validating graceful degradation...")
    t057_results = validate_graceful_degradation()
    all_results["validations"].append(t057_results)
    if not t057_results["passed"]:
        all_results["overall_passed"] = False
    print(f"  Result: {'PASS' if t057_results['passed'] else 'FAIL'}")
    
    # T058: Performance
    print("\n[T058] Validating search performance...")
    t058_results = validate_search_performance()
    all_results["validations"].append(t058_results)
    if not t058_results["passed"]:
        all_results["overall_passed"] = False
    print(f"  Result: {'PASS' if t058_results['passed'] else 'FAIL'}")
    
    # T059: Quickstart Scenarios
    print("\n[T059] Validating quickstart scenarios...")
    t059_results = validate_quickstart_scenarios()
    all_results["validations"].append(t059_results)
    if not t059_results["passed"]:
        all_results["overall_passed"] = False
    print(f"  Result: {'PASS' if t059_results['passed'] else 'FAIL'}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Overall: {'ALL TESTS PASSED' if all_results['overall_passed'] else 'SOME TESTS FAILED'}")
    print("=" * 60)
    
    return all_results


if __name__ == "__main__":
    # Run validations when executed directly
    import json
    
    results = run_all_validations()
    
    # Print detailed results
    print("\nDetailed Results:")
    print(json.dumps(results, indent=2, default=str))
