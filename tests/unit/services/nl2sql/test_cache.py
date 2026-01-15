# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Unit tests for QueryCache class.

Tests the TTL-based query cache for NL2SQL pipeline results.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from indico_assistant.services.nl2sql.cache import QueryCache
from indico_assistant.services.nl2sql.models import (
    PipelineResult,
)


class TestQueryCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_make_key_returns_hash(self):
        """make_key should return a SHA256 hash string."""
        key = QueryCache.make_key(1, "SELECT * FROM events", None)
        
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex digest length

    def test_make_key_same_inputs_same_key(self):
        """Same inputs should produce the same cache key."""
        key1 = QueryCache.make_key(1, "SELECT * FROM events", None)
        key2 = QueryCache.make_key(1, "SELECT * FROM events", None)
        
        assert key1 == key2

    def test_make_key_different_user_different_key(self):
        """Different user IDs should produce different keys."""
        key1 = QueryCache.make_key(1, "SELECT * FROM events", None)
        key2 = QueryCache.make_key(2, "SELECT * FROM events", None)
        
        assert key1 != key2

    def test_make_key_different_sql_different_key(self):
        """Different SQL should produce different keys."""
        key1 = QueryCache.make_key(1, "SELECT * FROM events", None)
        key2 = QueryCache.make_key(1, "SELECT * FROM registrations", None)
        
        assert key1 != key2

    def test_make_key_different_params_different_key(self):
        """Different params should produce different keys."""
        key1 = QueryCache.make_key(1, "SELECT * FROM events WHERE id = :id", {"id": 1})
        key2 = QueryCache.make_key(1, "SELECT * FROM events WHERE id = :id", {"id": 2})
        
        assert key1 != key2

    def test_make_key_normalizes_whitespace(self):
        """SQL whitespace should be normalized."""
        key1 = QueryCache.make_key(1, "SELECT * FROM events", None)
        key2 = QueryCache.make_key(1, "SELECT  *  FROM   events", None)
        key3 = QueryCache.make_key(1, "SELECT\n*\nFROM\nevents", None)
        
        assert key1 == key2 == key3

    def test_make_key_params_order_independent(self):
        """Param key order should not affect cache key."""
        key1 = QueryCache.make_key(1, "SELECT *", {"a": 1, "b": 2})
        key2 = QueryCache.make_key(1, "SELECT *", {"b": 2, "a": 1})
        
        assert key1 == key2


class TestQueryCacheBasicOperations:
    """Tests for basic cache get/set operations."""

    def test_get_returns_none_for_missing_key(self):
        """get should return None for missing keys."""
        cache = QueryCache()
        
        result = cache.get("nonexistent_key")
        
        assert result is None

    def test_set_and_get_returns_result(self):
        """set followed by get should return the cached result."""
        cache = QueryCache(ttl_seconds=60)
        result = PipelineResult(success=True, answer="Test answer")
        key = "test_key"
        
        cache.set(key, result)
        cached = cache.get(key)
        
        assert cached is not None
        assert cached.result.success is True
        assert cached.result.answer == "Test answer"

    def test_set_updates_existing_entry(self):
        """set should update existing cache entries."""
        cache = QueryCache(ttl_seconds=60)
        key = "test_key"
        
        cache.set(key, PipelineResult(success=True, answer="First"))
        cache.set(key, PipelineResult(success=True, answer="Second"))
        
        cached = cache.get(key)
        assert cached.result.answer == "Second"

    def test_cached_result_has_correct_metadata(self):
        """Cached result should have correct timestamps."""
        cache = QueryCache(ttl_seconds=60)
        result = PipelineResult(success=True)
        key = "test_key"
        
        before = datetime.now(timezone.utc)
        cache.set(key, result)
        after = datetime.now(timezone.utc)
        
        cached = cache.get(key)
        
        assert before <= cached.cached_at <= after
        assert cached.expires_at == cached.cached_at + timedelta(seconds=60)
        assert cached.cache_key == key


class TestQueryCacheTTL:
    """Tests for TTL expiration logic."""

    def test_expired_entry_returns_none(self):
        """get should return None for expired entries."""
        cache = QueryCache(ttl_seconds=1)
        result = PipelineResult(success=True)
        key = "test_key"
        
        cache.set(key, result)
        
        # Wait for expiration
        time.sleep(1.1)
        
        cached = cache.get(key)
        assert cached is None

    def test_non_expired_entry_returns_result(self):
        """get should return result for non-expired entries."""
        cache = QueryCache(ttl_seconds=60)
        result = PipelineResult(success=True)
        key = "test_key"
        
        cache.set(key, result)
        
        cached = cache.get(key)
        assert cached is not None

    def test_expired_entry_is_removed_on_get(self):
        """Expired entries should be removed when accessed."""
        cache = QueryCache(ttl_seconds=1)
        result = PipelineResult(success=True)
        key = "test_key"
        
        cache.set(key, result)
        assert cache.size == 1
        
        time.sleep(1.1)
        cache.get(key)  # Should remove expired entry
        
        assert cache.size == 0


class TestQueryCacheCapacity:
    """Tests for cache capacity management."""

    def test_max_entries_enforced(self):
        """Cache should not exceed max_entries."""
        cache = QueryCache(ttl_seconds=60, max_entries=3)
        
        for i in range(5):
            cache.set(f"key_{i}", PipelineResult(success=True, answer=f"Result {i}"))
        
        assert cache.size == 3

    def test_oldest_entries_evicted_first(self):
        """Oldest entries should be evicted when at capacity."""
        cache = QueryCache(ttl_seconds=60, max_entries=3)
        
        cache.set("key_0", PipelineResult(success=True, answer="Result 0"))
        cache.set("key_1", PipelineResult(success=True, answer="Result 1"))
        cache.set("key_2", PipelineResult(success=True, answer="Result 2"))
        cache.set("key_3", PipelineResult(success=True, answer="Result 3"))
        
        # key_0 should be evicted
        assert cache.get("key_0") is None
        assert cache.get("key_1") is not None
        assert cache.get("key_2") is not None
        assert cache.get("key_3") is not None

    def test_get_updates_lru_order(self):
        """get should update entry to most recently used."""
        cache = QueryCache(ttl_seconds=60, max_entries=3)
        
        cache.set("key_0", PipelineResult(success=True, answer="Result 0"))
        cache.set("key_1", PipelineResult(success=True, answer="Result 1"))
        cache.set("key_2", PipelineResult(success=True, answer="Result 2"))
        
        # Access key_0 to make it most recent
        cache.get("key_0")
        
        # Add new entry - key_1 should be evicted (now oldest)
        cache.set("key_3", PipelineResult(success=True, answer="Result 3"))
        
        assert cache.get("key_0") is not None
        assert cache.get("key_1") is None
        assert cache.get("key_2") is not None
        assert cache.get("key_3") is not None


class TestQueryCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_removes_entry(self):
        """invalidate should remove specific entry."""
        cache = QueryCache(ttl_seconds=60)
        key = "test_key"
        
        cache.set(key, PipelineResult(success=True))
        assert cache.get(key) is not None
        
        result = cache.invalidate(key)
        
        assert result is True
        assert cache.get(key) is None

    def test_invalidate_nonexistent_returns_false(self):
        """invalidate should return False for missing keys."""
        cache = QueryCache()
        
        result = cache.invalidate("nonexistent")
        
        assert result is False

    def test_clear_removes_all_entries(self):
        """clear should remove all cache entries."""
        cache = QueryCache(ttl_seconds=60)
        
        for i in range(5):
            cache.set(f"key_{i}", PipelineResult(success=True))
        
        assert cache.size == 5
        
        count = cache.clear()
        
        assert count == 5
        assert cache.size == 0


class TestQueryCacheCleanup:
    """Tests for expired entry cleanup."""

    def test_cleanup_expired_removes_only_expired(self):
        """cleanup_expired should remove only expired entries."""
        cache = QueryCache(ttl_seconds=1)
        
        # Add entry that will expire
        cache.set("expiring", PipelineResult(success=True, answer="Expiring"))
        
        # Wait for it to expire
        time.sleep(1.1)
        
        # Add fresh entry
        cache.set("fresh", PipelineResult(success=True, answer="Fresh"))
        
        removed = cache.cleanup_expired()
        
        assert removed == 1
        assert cache.get("expiring") is None
        assert cache.get("fresh") is not None

    def test_cleanup_expired_returns_count(self):
        """cleanup_expired should return count of removed entries."""
        cache = QueryCache(ttl_seconds=1)
        
        for i in range(3):
            cache.set(f"key_{i}", PipelineResult(success=True))
        
        time.sleep(1.1)
        
        removed = cache.cleanup_expired()
        
        assert removed == 3


class TestQueryCacheProperties:
    """Tests for cache property accessors."""

    def test_size_property(self):
        """size property should return current entry count."""
        cache = QueryCache()
        
        assert cache.size == 0
        
        cache.set("key_1", PipelineResult(success=True))
        assert cache.size == 1
        
        cache.set("key_2", PipelineResult(success=True))
        assert cache.size == 2

    def test_ttl_seconds_property(self):
        """ttl_seconds property should return configured TTL."""
        cache = QueryCache(ttl_seconds=300)
        
        assert cache.ttl_seconds == 300

    def test_max_entries_property(self):
        """max_entries property should return configured max."""
        cache = QueryCache(max_entries=500)
        
        assert cache.max_entries == 500


class TestQueryCacheDefaults:
    """Tests for default configuration values."""

    def test_default_ttl_is_600_seconds(self):
        """Default TTL should be 600 seconds (10 minutes)."""
        cache = QueryCache()
        
        assert cache.ttl_seconds == 600

    def test_default_max_entries_is_1000(self):
        """Default max entries should be 1000."""
        cache = QueryCache()
        
        assert cache.max_entries == 1000


class TestQueryCacheThreadSafety:
    """Tests for thread safety (basic smoke tests)."""

    def test_concurrent_set_get(self):
        """Cache should handle concurrent set/get operations."""
        import threading
        
        cache = QueryCache(ttl_seconds=60, max_entries=100)
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(10):
                    key = f"worker_{worker_id}_key_{i}"
                    cache.set(key, PipelineResult(success=True, answer=f"Answer {i}"))
                    result = cache.get(key)
                    if result and result.result.answer != f"Answer {i}":
                        errors.append(f"Mismatch for {key}")
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread safety errors: {errors}"
