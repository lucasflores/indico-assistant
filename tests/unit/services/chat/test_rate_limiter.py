"""Unit tests for RateLimiter service.

Feature: 004-chat-api
Task: T019
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from indico_assistant.services.chat.rate_limiter import (
    RateLimitResult,
    RateLimiter,
    get_rate_limiter,
)

# Access RATE_LIMITS from the class
RATE_LIMITS = RateLimiter.RATE_LIMITS


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_result_allowed(self):
        """Test result when allowed."""
        result = RateLimitResult(allowed=True, remaining=59, retry_after=None)
        
        assert result.allowed is True
        assert result.remaining == 59
        assert result.retry_after is None

    def test_result_denied(self):
        """Test result when denied."""
        result = RateLimitResult(allowed=False, remaining=0, retry_after=30)
        
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 30


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_init_creates_memory_backend(self):
        """Test initialization creates memory backend when Redis unavailable."""
        with patch('indico_assistant.services.chat.rate_limiter.redis') as mock_redis:
            mock_redis.StrictRedis.side_effect = Exception("No Redis")
            
            limiter = RateLimiter()
            
            assert limiter._redis is None
            assert limiter._memory_store is not None

    def test_check_rate_first_request_allowed(self):
        """Test first request is always allowed."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            limiter = RateLimiter()
            limiter._redis = None  # Force memory backend
            
            result = limiter.check_rate(user_id=123, endpoint="chat")
            
            assert result.allowed is True
            assert result.remaining == RATE_LIMITS["chat"]["requests"] - 1

    def test_check_rate_under_limit_allowed(self):
        """Test requests under limit are allowed."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            limiter = RateLimiter()
            limiter._redis = None
            
            # Make several requests, all should be allowed
            for i in range(5):
                result = limiter.check_rate(user_id=123, endpoint="chat")
                assert result.allowed is True

    def test_check_rate_over_limit_denied(self):
        """Test requests over limit are denied."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            limiter = RateLimiter()
            limiter._redis = None
            
            # Exhaust the limit
            limit = RATE_LIMITS["chat"]["requests"]
            for i in range(limit):
                limiter.check_rate(user_id=123, endpoint="chat")
            
            # Next request should be denied
            result = limiter.check_rate(user_id=123, endpoint="chat")
            assert result.allowed is False
            assert result.retry_after is not None

    def test_check_rate_different_users_independent(self):
        """Test rate limits are per-user."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            limiter = RateLimiter()
            limiter._redis = None
            
            result1 = limiter.check_rate(user_id=123, endpoint="chat")
            result2 = limiter.check_rate(user_id=456, endpoint="chat")
            
            assert result1.allowed is True
            assert result2.allowed is True
            assert result1.remaining == result2.remaining

    def test_check_rate_different_endpoints_independent(self):
        """Test rate limits are per-endpoint."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            limiter = RateLimiter()
            limiter._redis = None
            
            result_chat = limiter.check_rate(user_id=123, endpoint="chat")
            result_read = limiter.check_rate(user_id=123, endpoint="read")
            
            assert result_chat.allowed is True
            assert result_read.allowed is True

    def test_check_rate_unknown_endpoint_uses_default(self):
        """Test unknown endpoints use default limits."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            limiter = RateLimiter()
            limiter._redis = None
            
            result = limiter.check_rate(user_id=123, endpoint="unknown")
            
            assert result.allowed is True

    def test_rate_limits_configuration(self):
        """Test rate limits are correctly configured."""
        assert "chat" in RATE_LIMITS
        assert "read" in RATE_LIMITS
        
        assert RATE_LIMITS["chat"]["requests"] == 60
        assert RATE_LIMITS["chat"]["window"] == 60
        
        assert RATE_LIMITS["read"]["requests"] == 200
        assert RATE_LIMITS["read"]["window"] == 60


class TestRateLimiterRedisBackend:
    """Tests for RateLimiter with Redis backend."""

    def test_init_with_redis(self):
        """Test initialization with Redis backend."""
        mock_redis_instance = MagicMock()
        
        with patch('indico_assistant.services.chat.rate_limiter.redis') as mock_redis:
            mock_redis.StrictRedis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            
            limiter = RateLimiter()
            
            # Redis should be configured
            assert limiter._redis is not None

    def test_check_rate_with_redis(self):
        """Test rate checking with Redis backend."""
        mock_redis_instance = MagicMock()
        mock_pipe = MagicMock()
        
        with patch('indico_assistant.services.chat.rate_limiter.redis') as mock_redis:
            mock_redis.StrictRedis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.pipeline.return_value = mock_pipe
            mock_pipe.execute.return_value = [1, True]  # INCR result, EXPIRE result
            
            limiter = RateLimiter()
            limiter._redis = mock_redis_instance
            
            result = limiter.check_rate(user_id=123, endpoint="chat")
            
            assert result.allowed is True


class TestGetRateLimiter:
    """Tests for get_rate_limiter factory function."""

    def test_get_rate_limiter_returns_instance(self):
        """Test factory function returns a RateLimiter."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            import indico_assistant.services.chat.rate_limiter as module
            module._rate_limiter = None
            
            limiter = get_rate_limiter()
            
            assert isinstance(limiter, RateLimiter)

    def test_get_rate_limiter_returns_same_instance(self):
        """Test factory function returns same instance (singleton)."""
        with patch('indico_assistant.services.chat.rate_limiter.redis', None):
            import indico_assistant.services.chat.rate_limiter as module
            module._rate_limiter = None
            
            limiter1 = get_rate_limiter()
            limiter2 = get_rate_limiter()
            
            assert limiter1 is limiter2
