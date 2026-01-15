# This file is part of the Indico Assistant Plugin.
# Copyright (C) 2024 - present CERN
#
# Indico Assistant Plugin is free software; you can redistribute it
# and/or modify it under the terms of the MIT License; see the
# LICENSE file for more details.

"""
Query result cache for NL2SQL pipeline.

Implements TTL-based caching for identical SQL queries to improve
performance for repeated questions. Cache key is based on user ID,
SQL text, and parameters (FR-042).
"""

import hashlib
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any

from indico_assistant.services.nl2sql.models import CachedResult, PipelineResult


class QueryCache:
    """TTL-based cache for query results."""

    def __init__(
        self,
        ttl_seconds: int = 600,
        max_entries: int = 1000,
    ) -> None:
        """
        Initialize the query cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 600 = 10 minutes)
            max_entries: Maximum number of entries to store (default: 1000)
        """
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: OrderedDict[str, CachedResult] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def make_key(
        user_id: int, sql: str, params: dict[str, Any] | None = None
    ) -> str:
        """
        Generate a cache key from user ID, SQL, and parameters.

        Args:
            user_id: The user's ID
            sql: The SQL query text
            params: Optional query parameters

        Returns:
            A unique cache key string.
        """
        # Normalize SQL (remove extra whitespace)
        normalized_sql = " ".join(sql.split())

        # Create deterministic string from params
        params_str = ""
        if params:
            # Sort keys for deterministic ordering
            sorted_items = sorted(params.items())
            params_str = str(sorted_items)

        # Combine components
        key_source = f"{user_id}:{normalized_sql}:{params_str}"

        # Hash for fixed-length key
        return hashlib.sha256(key_source.encode()).hexdigest()

    def get(self, cache_key: str) -> CachedResult | None:
        """
        Retrieve a cached result if it exists and hasn't expired.

        Args:
            cache_key: The cache key to look up

        Returns:
            The cached result if found and not expired, None otherwise.
        """
        with self._lock:
            if cache_key not in self._cache:
                return None

            entry = self._cache[cache_key]
            now = datetime.now(timezone.utc)

            # Check expiration
            if now >= entry.expires_at:
                # Entry has expired, remove it
                del self._cache[cache_key]
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(cache_key)
            return entry

    def set(self, cache_key: str, result: PipelineResult) -> None:
        """
        Store a result in the cache.

        Args:
            cache_key: The cache key to store under
            result: The pipeline result to cache
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_seconds)

        entry = CachedResult(
            result=result,
            cached_at=now,
            expires_at=expires_at,
            cache_key=cache_key,
        )

        with self._lock:
            # If key exists, update it
            if cache_key in self._cache:
                self._cache[cache_key] = entry
                self._cache.move_to_end(cache_key)
            else:
                # Add new entry
                self._cache[cache_key] = entry

                # Evict oldest entries if at capacity
                while len(self._cache) > self._max_entries:
                    self._cache.popitem(last=False)

    def invalidate(self, cache_key: str) -> bool:
        """
        Remove a specific entry from the cache.

        Args:
            cache_key: The cache key to invalidate

        Returns:
            True if the entry was found and removed, False otherwise.
        """
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False

    def clear(self) -> int:
        """
        Clear all entries from the cache.

        Returns:
            The number of entries that were cleared.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            The number of entries that were removed.
        """
        now = datetime.now(timezone.utc)
        removed = 0

        with self._lock:
            # Create list of expired keys to avoid modifying dict during iteration
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if now >= entry.expires_at
            ]

            for key in expired_keys:
                del self._cache[key]
                removed += 1

        return removed

    @property
    def size(self) -> int:
        """Get the current number of entries in the cache."""
        with self._lock:
            return len(self._cache)

    @property
    def ttl_seconds(self) -> int:
        """Get the configured TTL in seconds."""
        return self._ttl_seconds

    @property
    def max_entries(self) -> int:
        """Get the configured maximum entries."""
        return self._max_entries
