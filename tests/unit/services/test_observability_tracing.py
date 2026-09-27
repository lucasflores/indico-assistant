"""Tracing never changes what the traced code raises, and falls back to a no-op if Langfuse fails."""

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from indico_assistant.services.observability.client import LangfuseClient, NoOpSpan, get_langfuse_client, reset_client


def _client(observation):
    client = LangfuseClient.__new__(LangfuseClient)
    client._client = MagicMock(start_as_current_observation=MagicMock(side_effect=observation))
    client._enabled = True
    return client


@pytest.mark.parametrize('method', ['trace', 'generation', 'span'])
def test_errors_in_the_traced_block_propagate_unchanged(method):
    client = _client(lambda **kw: nullcontext('obs'))
    with pytest.raises(KeyError):
        with getattr(client, method)('x'):
            raise KeyError('real error')  # used to surface as RuntimeError("generator didn't stop")


@pytest.mark.parametrize('method', ['trace', 'generation', 'span'])
def test_langfuse_failure_falls_back_to_noop(method):
    def broken(**kw):
        raise ConnectionError('langfuse down')
    with getattr(_client(broken), method)('x') as observation:
        assert isinstance(observation, NoOpSpan)


def test_client_is_shared_until_its_settings_change():
    reset_client()
    settings = {'langfuse_enabled': False, 'langfuse_host': 'https://a'}
    first = get_langfuse_client(settings)
    assert get_langfuse_client(dict(settings)) is first
    assert get_langfuse_client({**settings, 'langfuse_host': 'https://b'}) is not first
    reset_client()
