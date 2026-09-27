"""Per-user rate limits on Indico's Redis limiter (the test app runs a real Redis).

Feature: 004-chat-api
"""

import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from indico_assistant.services.chat.rate_limiter import RATE_LIMITS, RateLimiter, get_rate_limiter


@pytest.fixture
def user_id():
    return random.randrange(10**9)  # fresh counters per test


def test_limit_is_per_user_and_reports_retry_after(user_id):
    limiter = RateLimiter({'chat': ('2 per minute',)})
    assert [limiter.check_rate(user_id).allowed for _ in range(3)] == [True, True, False]
    refused = limiter.check_rate(user_id)
    assert not refused.allowed and 1 <= refused.retry_after <= 60
    assert limiter.check_rate(user_id + 1).allowed


def test_every_limit_of_an_endpoint_must_pass(user_id):
    limiter = RateLimiter({'chat': ('5 per minute', '2 per day')})
    assert [limiter.check_rate(user_id).allowed for _ in range(3)] == [True, True, False]
    assert limiter.check_rate(user_id).retry_after > 60  # the daily limit is the one that bit


def test_shared_between_limiter_instances(user_id):
    # stands in for two worker processes: the count lives in Redis, not in the object
    first, second = RateLimiter({'chat': ('1 per minute',)}), RateLimiter({'chat': ('1 per minute',)})
    assert first.check_rate(user_id).allowed
    assert not second.check_rate(user_id).allowed


def test_concurrent_requests_cannot_overshoot(user_id):
    limiter = RateLimiter({'chat': ('5 per minute',)})
    with ThreadPoolExecutor(20) as pool:
        allowed = list(pool.map(lambda _: limiter.check_rate(user_id).allowed, range(20)))
    assert allowed.count(True) == 5


def test_endpoint_types_are_independent_and_unknown_means_chat(user_id):
    limiter = RateLimiter({'chat': ('1 per minute',), 'read': ('1 per minute',)})
    assert limiter.check_rate(user_id, 'chat').allowed
    assert limiter.check_rate(user_id, 'read').allowed
    assert not limiter.check_rate(user_id, 'unknown').allowed


def test_defaults():
    assert set(RATE_LIMITS) == {'chat', 'read'}
    assert get_rate_limiter() is get_rate_limiter()
