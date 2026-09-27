"""A refused request is a real 429 with Retry-After (it used to raise a tuple, i.e. a 500)."""

from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import TooManyRequests

from indico_assistant.controllers.chat import RHChat
from indico_assistant.services.chat.rate_limiter import RateLimitResult


def test_chat_over_limit_raises_429():
    rh = RHChat.__new__(RHChat)
    rh._user = MagicMock(id=5)
    with patch('indico_assistant.controllers.base.RHAssistantBase._check_access'), \
            patch('indico_assistant.controllers.chat.get_rate_limiter') as limiter:
        limiter.return_value.check_rate.return_value = RateLimitResult(allowed=False, remaining=0, retry_after=42)
        with pytest.raises(TooManyRequests) as exc:
            rh._check_access()
    assert exc.value.response.status_code == 429
    assert exc.value.response.headers['Retry-After'] == '42'
    assert exc.value.response.get_json()['error'] == 'RATE_LIMITED'
