"""Rate limiter service with Redis backend and in-memory fallback.

Feature: 004-chat-api
Task: T010
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Optional

try:
    import redis
except ImportError:
    redis = None


@dataclass
class RateLimitResult:
    """Result of a rate limit check.
    
    Attributes:
        allowed: Whether the request is allowed
        remaining: Requests remaining in current window
        retry_after: Seconds to wait before retrying (if not allowed)
    """
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter:
    """Per-user rate limiter with Redis backend and in-memory fallback.
    
    Implements a sliding window rate limiting algorithm. Uses Redis
    when available for distributed rate limiting across workers,
    with automatic fallback to in-memory storage.
    
    Rate limits are configured per endpoint type:
    - 'chat': 60 requests per minute (default)
    - 'read': 200 requests per minute (default)
    
    Attributes:
        RATE_LIMITS: Default rate limits by endpoint type
    """
    
    # Default rate limits: (max_requests, window_seconds)
    RATE_LIMITS = {
        'chat': (60, 60),   # 60 requests per minute
        'read': (200, 60),  # 200 requests per minute
    }
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        rate_limits: Optional[dict[str, tuple[int, int]]] = None
    ):
        """Initialize the rate limiter.
        
        Args:
            redis_url: Redis connection URL (optional)
            rate_limits: Custom rate limits by type (optional)
        """
        self._redis: Optional["redis.Redis"] = None
        self._memory_store: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        
        # Merge custom rate limits with defaults
        self._rate_limits = {**self.RATE_LIMITS}
        if rate_limits:
            self._rate_limits.update(rate_limits)
        
        # Try to connect to Redis
        if redis_url and redis is not None:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()  # Verify connection
            except Exception:
                self._redis = None  # Fall back to memory
    
    def check_rate(
        self,
        user_id: int,
        endpoint_type: str = 'chat'
    ) -> RateLimitResult:
        """Check if a user is within their rate limit.
        
        Args:
            user_id: Indico user ID
            endpoint_type: Type of endpoint ('chat' or 'read')
            
        Returns:
            RateLimitResult with allowed status and metadata
        """
        max_requests, window_seconds = self._rate_limits.get(
            endpoint_type,
            self.RATE_LIMITS['chat']
        )
        
        key = f"rate_limit:{user_id}:{endpoint_type}"
        now = time.time()
        window_start = now - window_seconds
        
        if self._redis:
            return self._check_redis(key, now, window_start, max_requests, window_seconds)
        return self._check_memory(key, now, window_start, max_requests, window_seconds)
    
    def _check_redis(
        self,
        key: str,
        now: float,
        window_start: float,
        max_requests: int,
        window_seconds: int
    ) -> RateLimitResult:
        """Check rate limit using Redis sorted set.
        
        Uses a sorted set where scores are timestamps. Old entries
        outside the window are automatically removed.
        """
        pipe = self._redis.pipeline()
        
        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current entries in window
        pipe.zcard(key)
        
        # Execute pipeline
        _, current_count = pipe.execute()
        
        if current_count >= max_requests:
            # Get oldest entry to calculate retry_after
            oldest = self._redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(oldest[0][1] + window_seconds - now) + 1
            else:
                retry_after = window_seconds
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after=max(1, retry_after)
            )
        
        # Add current request and set expiry
        self._redis.zadd(key, {str(now): now})
        self._redis.expire(key, window_seconds * 2)  # 2x window for safety
        
        return RateLimitResult(
            allowed=True,
            remaining=max_requests - current_count - 1,
            retry_after=0
        )
    
    def _check_memory(
        self,
        key: str,
        now: float,
        window_start: float,
        max_requests: int,
        window_seconds: int
    ) -> RateLimitResult:
        """Check rate limit using in-memory storage.
        
        Thread-safe implementation for single-process rate limiting.
        """
        with self._lock:
            # Remove old entries outside the window
            self._memory_store[key] = [
                ts for ts in self._memory_store[key]
                if ts > window_start
            ]
            
            current_count = len(self._memory_store[key])
            
            if current_count >= max_requests:
                # Calculate retry_after from oldest entry
                if self._memory_store[key]:
                    oldest = min(self._memory_store[key])
                    retry_after = int(oldest + window_seconds - now) + 1
                else:
                    retry_after = window_seconds
                
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=max(1, retry_after)
                )
            
            # Add current request
            self._memory_store[key].append(now)
            
            return RateLimitResult(
                allowed=True,
                remaining=max_requests - current_count - 1,
                retry_after=0
            )
    
    def reset(self, user_id: int, endpoint_type: Optional[str] = None) -> None:
        """Reset rate limit for a user (for testing).
        
        Args:
            user_id: Indico user ID
            endpoint_type: Specific type to reset, or None for all
        """
        types_to_reset = [endpoint_type] if endpoint_type else list(self._rate_limits.keys())
        
        for et in types_to_reset:
            key = f"rate_limit:{user_id}:{et}"
            
            if self._redis:
                self._redis.delete(key)
            else:
                with self._lock:
                    self._memory_store.pop(key, None)


# Global rate limiter instance (initialized lazily)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter instance.
    
    Returns:
        Configured RateLimiter instance
    """
    global _rate_limiter
    
    if _rate_limiter is None:
        # Try to get Redis URL from plugin settings
        redis_url = None
        try:
            from indico.core.plugins import plugin_engine
            plugin = plugin_engine.get_plugin("assistant")
            if plugin:
                redis_url = plugin.settings.get("redis_url")
        except Exception:
            pass
        
        _rate_limiter = RateLimiter(redis_url=redis_url)
    
    return _rate_limiter
