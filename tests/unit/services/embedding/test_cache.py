"""Unit tests for EmbeddingCache.

Feature: 007-tdd-gap-analysis
GAP: GAP-002 (Critical - LLM Integration)
Tasks: T014-T019

Tests the embedding cache including:
- Cache hits and misses
- Cache invalidation
- Hash collision handling
- Database loading
"""

import pytest
from unittest.mock import MagicMock, patch

from indico_assistant.services.embedding.cache import (
    EmbeddingCache,
    compute_content_hash,
)


class TestEmbeddingCache:
    """Tests for EmbeddingCache."""

    @pytest.fixture
    def cache(self):
        """Create fresh EmbeddingCache instance."""
        return EmbeddingCache()

    # =========================================================================
    # T015: test_cache_hit
    # =========================================================================

    def test_cache_hit_returns_true(self, cache):
        """Test is_cached returns True for cached content."""
        content = "test content"
        content_hash = cache.compute_hash(content)
        
        # Mark as cached
        cache.mark_cached(content_hash)
        
        # Assert cache hit
        assert cache.is_cached(content_hash) is True

    def test_cache_hit_after_multiple_adds(self, cache):
        """Test cache hit works with multiple cached items."""
        hashes = [cache.compute_hash(f"content_{i}") for i in range(10)]
        
        for h in hashes:
            cache.mark_cached(h)
        
        # All should be cache hits
        for h in hashes:
            assert cache.is_cached(h) is True

    def test_cache_hit_same_content_same_hash(self, cache):
        """Test identical content produces same hash (deterministic)."""
        content = "identical content"
        
        hash1 = cache.compute_hash(content)
        hash2 = cache.compute_hash(content)
        
        assert hash1 == hash2
        
        cache.mark_cached(hash1)
        assert cache.is_cached(hash2) is True

    # =========================================================================
    # T016: test_cache_miss
    # =========================================================================

    def test_cache_miss_returns_false(self, cache):
        """Test is_cached returns False for uncached content."""
        content_hash = cache.compute_hash("uncached content")
        
        assert cache.is_cached(content_hash) is False

    def test_cache_miss_empty_cache(self, cache):
        """Test cache miss on empty cache."""
        assert cache.is_cached("any_hash") is False
        assert cache.size == 0

    def test_cache_miss_after_clear(self, cache):
        """Test cache miss after clearing cache."""
        content_hash = cache.compute_hash("content")
        cache.mark_cached(content_hash)
        
        assert cache.is_cached(content_hash) is True
        
        cache.clear()
        
        assert cache.is_cached(content_hash) is False

    # =========================================================================
    # T017: test_cache_invalidation
    # =========================================================================

    def test_cache_invalidation_removes_hash(self, cache):
        """Test invalidate removes specific hash from cache."""
        content_hash = cache.compute_hash("content to invalidate")
        cache.mark_cached(content_hash)
        
        assert cache.is_cached(content_hash) is True
        
        cache.invalidate(content_hash)
        
        assert cache.is_cached(content_hash) is False

    def test_cache_invalidation_only_affects_target(self, cache):
        """Test invalidate only removes target hash, not others."""
        hash1 = cache.compute_hash("content1")
        hash2 = cache.compute_hash("content2")
        
        cache.mark_cached(hash1)
        cache.mark_cached(hash2)
        
        cache.invalidate(hash1)
        
        assert cache.is_cached(hash1) is False
        assert cache.is_cached(hash2) is True

    def test_cache_invalidation_nonexistent_hash(self, cache):
        """Test invalidate on non-existent hash doesn't raise error."""
        # Should not raise
        cache.invalidate("nonexistent_hash")
        
        assert cache.size == 0

    def test_cache_clear_removes_all(self, cache):
        """Test clear removes all cached hashes."""
        for i in range(5):
            cache.mark_cached(cache.compute_hash(f"content_{i}"))
        
        assert cache.size == 5
        
        cache.clear()
        
        assert cache.size == 0

    # =========================================================================
    # T018: test_cache_key_collision
    # =========================================================================

    def test_different_content_different_hash(self, cache):
        """Test different content produces different hashes."""
        hash1 = cache.compute_hash("content A")
        hash2 = cache.compute_hash("content B")
        
        assert hash1 != hash2

    def test_hash_is_deterministic(self, cache):
        """Test same content always produces same hash."""
        content = "deterministic content"
        
        hashes = [cache.compute_hash(content) for _ in range(10)]
        
        assert all(h == hashes[0] for h in hashes)

    def test_hash_format(self, cache):
        """Test hash is 64-character hex string (SHA-256)."""
        content_hash = cache.compute_hash("test content")
        
        assert len(content_hash) == 64
        assert all(c in '0123456789abcdef' for c in content_hash)

    def test_similar_content_different_hash(self, cache):
        """Test similar but not identical content produces different hashes."""
        hash1 = cache.compute_hash("Hello World")
        hash2 = cache.compute_hash("Hello World!")  # One character different
        hash3 = cache.compute_hash("hello world")  # Case different
        
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3

    def test_unicode_content_hashing(self, cache):
        """Test cache handles unicode content correctly."""
        hash1 = cache.compute_hash("日本語テスト")
        hash2 = cache.compute_hash("Ñoño")
        hash3 = cache.compute_hash("emoji: 🎉")
        
        # All should produce valid hashes
        assert len(hash1) == 64
        assert len(hash2) == 64
        assert len(hash3) == 64
        
        # All different
        assert hash1 != hash2 != hash3


class TestEmbeddingCacheLoad:
    """Tests for EmbeddingCache.load_from_database()."""

    @pytest.fixture
    def cache(self):
        """Create fresh EmbeddingCache instance."""
        return EmbeddingCache()

    def test_load_from_database_populates_cache(self, cache):
        """Test loading hashes from database populates cache."""
        existing_hashes = ["hash1", "hash2", "hash3"]
        
        cache.load_from_database(existing_hashes)
        
        assert cache.size == 3
        for h in existing_hashes:
            assert cache.is_cached(h) is True

    def test_load_from_database_empty_list(self, cache):
        """Test loading empty list doesn't affect cache."""
        cache.load_from_database([])
        
        assert cache.size == 0

    def test_load_from_database_duplicates(self, cache):
        """Test loading duplicate hashes is handled."""
        cache.load_from_database(["hash1", "hash1", "hash2"])
        
        assert cache.size == 2  # Set deduplicates

    def test_load_from_database_preserves_existing(self, cache):
        """Test loading doesn't remove existing cache entries."""
        cache.mark_cached("existing_hash")
        
        cache.load_from_database(["new_hash1", "new_hash2"])
        
        assert cache.size == 3
        assert cache.is_cached("existing_hash") is True


class TestComputeContentHashFunction:
    """Tests for compute_content_hash convenience function."""

    def test_compute_content_hash_matches_class_method(self):
        """Test convenience function matches class method."""
        content = "test content"
        
        result1 = compute_content_hash(content)
        result2 = EmbeddingCache.compute_hash(content)
        
        assert result1 == result2

    def test_compute_content_hash_empty_string(self):
        """Test hashing empty string."""
        result = compute_content_hash("")
        
        assert len(result) == 64
        assert isinstance(result, str)

    def test_compute_content_hash_whitespace(self):
        """Test whitespace-only content produces valid hash."""
        result = compute_content_hash("   \n\t  ")
        
        assert len(result) == 64


class TestEmbeddingCacheSize:
    """Tests for EmbeddingCache.size property."""

    def test_size_starts_at_zero(self):
        """Test new cache has size 0."""
        cache = EmbeddingCache()
        
        assert cache.size == 0

    def test_size_increments_on_add(self):
        """Test size increases when adding hashes."""
        cache = EmbeddingCache()
        
        cache.mark_cached("hash1")
        assert cache.size == 1
        
        cache.mark_cached("hash2")
        assert cache.size == 2

    def test_size_decrements_on_invalidate(self):
        """Test size decreases when invalidating."""
        cache = EmbeddingCache()
        cache.mark_cached("hash1")
        cache.mark_cached("hash2")
        
        cache.invalidate("hash1")
        
        assert cache.size == 1

    def test_size_no_change_duplicate_add(self):
        """Test size doesn't change for duplicate adds."""
        cache = EmbeddingCache()
        
        cache.mark_cached("hash1")
        cache.mark_cached("hash1")  # Duplicate
        
        assert cache.size == 1
