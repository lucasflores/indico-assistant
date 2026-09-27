"""Per-user rate limits for the assistant API, shared by every process and node.

Built on Indico's limiter (Redis, ``RATELIMIT_STORAGE_URI``), keyed on the user id rather than the IP
address: Chainlit forwards every user from one address.

Feature: 004-chat-api
"""

from __future__ import annotations

from dataclasses import dataclass

from indico.core.limiter import make_rate_limiter


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed
        remaining: Kept for callers; not tracked (-1)
        retry_after: Seconds to wait before retrying (if not allowed)
    """
    allowed: bool
    remaining: int
    retry_after: int


# Every limit of an endpoint type must pass. 'chat' covers anything that spends LLM money.
RATE_LIMITS = {
    'chat': ('10 per minute', '200 per day'),
    'read': ('200 per minute',),
}


class RateLimiter:
    def __init__(self, rate_limits: dict[str, tuple[str, ...]] | None = None):
        self._limiters = {
            endpoint: [make_rate_limiter(f'assistant-{endpoint}-{i}', definition, by_ip=False)
                       for i, definition in enumerate(definitions)]
            for endpoint, definitions in (rate_limits or RATE_LIMITS).items()
        }

    def check_rate(self, user_id: int, endpoint_type: str = 'chat') -> RateLimitResult:
        """Count a request by ``user_id``; refused if any limit of ``endpoint_type`` is used up."""
        for limiter in self._limiters.get(endpoint_type, self._limiters['chat']):
            # hit() checks and counts in one atomic Redis step, and counts nothing when it refuses
            # ponytail: a refusal by a later limit leaves the earlier ones counted (shortest window first)
            if not limiter.hit(user_id):
                retry_after = int(limiter.get_reset_delay(user_id).total_seconds())
                return RateLimitResult(allowed=False, remaining=0, retry_after=max(1, retry_after))
        return RateLimitResult(allowed=True, remaining=-1, retry_after=0)

_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
