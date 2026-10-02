"""Each generate() is one analytics step (spec 024, T009/T014): real instructor and openai clients over a fake
transport, inside a turn held in memory (the recorder's database writes are tested in tests/integration/analytics)."""

import json
import time
from decimal import Decimal

import httpx
import openai
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from pydantic import BaseModel

from indico_assistant.services.analytics import recorder
from indico_assistant.services.llm import factory
from indico_assistant.services.llm.service import LLMService


class Answer(BaseModel):
    city: str


class Plugin:
    def __init__(self, **settings):
        self.settings = {'llm_provider': 'ibis', 'llm_model': 'ibis/Balanced', 'llm_base_url': 'http://ibis.test',
                         'llm_api_key': 'sk-ibis-abcdefghijkl.secret', 'llm_ibis_mode': 'md_json',
                         'timeout_seconds': 5, 'max_tokens': 256, 'max_retries': 2, **settings}


def reply(content, **usage):
    return {'id': 'x', 'object': 'chat.completion', 'created': 0, 'model': 'openai/gpt-oss-120b',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15, **usage},
            'ibis': {'request_id': 'r1', 'dial': 'Balanced', 'chosen': 'GPT-5.6-Luna'}}


def tool_reply(arguments, **usage):
    """The openai provider's tools mode: the answer comes as a call of the response model's function."""
    body = reply(None, **usage)
    body['choices'][0]['message'] = {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'c1', 'type': 'function', 'function': {'name': 'Answer', 'arguments': json.dumps(arguments)}}]}
    return body


LISBON = '```json\n{"city": "Lisbon"}\n```'


def fake(monkeypatch, handler):
    real = openai.OpenAI
    monkeypatch.setattr(factory, 'OpenAI', lambda http_client=None, **kw: real(http_client=httpx.Client(
        transport=httpx.MockTransport(handler), event_hooks=http_client.event_hooks), **kw))


@pytest.fixture
def turn():
    current = recorder._Turn(1, text_on=True)
    token = recorder._current.set(current)
    yield current
    recorder._current.reset(token)


def test_a_call_is_one_step_with_its_attempts_tokens_cost_and_text(monkeypatch, turn):
    replies = iter([reply('not json', cost_usd='0.00010'), reply(LISBON, cost_usd='0.00020')])
    fake(monkeypatch, lambda request: httpx.Response(200, json=next(replies)))
    response = LLMService(Plugin()).generate('Capital of Portugal?', Answer, system_prompt='Be brief.')
    assert response.success
    [step] = turn.steps
    assert (step.kind, step.stage, step.ok, step.attempts) == ('llm', 'Answer', True, 2)  # a validation retry
    assert (step.prompt_tokens, step.completion_tokens, step.cost_usd) == (20, 10, Decimal('0.00030'))
    assert (step.requested_model, step.served_model, step.ibis_chosen, step.ibis_dial) == (
        'ibis/Balanced', 'openai/gpt-oss-120b', 'GPT-5.6-Luna', 'Balanced')
    prompt, answer = turn.texts[(1, 'prompt')][0], turn.texts[(1, 'response')][0]
    assert json.loads(prompt)[0] == {'role': 'system', 'content': 'Be brief.'} and 'Portugal' in prompt
    assert json.loads(answer) == {'city': 'Lisbon'}


def test_an_error_returned_not_raised_marks_the_step_failed(monkeypatch, turn):
    fake(monkeypatch, lambda request: httpx.Response(500, json={'error': {'message': 'down'}}))
    response = LLMService(Plugin()).generate('Capital of Portugal?', Answer)
    assert not response.success
    [step] = turn.steps
    assert step.ok is False and step.error_code == response.error.error_type.value
    assert step.cost_usd is None and step.http_errors == [500]


def test_retries_inside_the_sdk_are_counted(monkeypatch, turn):
    """OpenRouter through the openai provider: the SDK retries a 429 on its own, unseen by instructor."""
    replies = iter([httpx.Response(429, headers={'retry-after-ms': '1'}, json={'error': {'message': 'slow down'}}),
                    httpx.Response(200, json=tool_reply({'city': 'Lisbon'}, cost=0.0003))])
    fake(monkeypatch, lambda request: next(replies))
    plugin = Plugin(llm_provider='openai', llm_model='openai/gpt-4o-mini', llm_base_url='https://openrouter.test/v1')
    response = LLMService(plugin).generate('Capital of Portugal?', Answer)
    assert response.success
    [step] = turn.steps
    assert step.attempts == 2 and step.http_errors == [429]
    assert step.cost_usd == Decimal('0.0003')  # OpenRouter's usage.cost (FR-005)


def test_the_soft_time_limit_is_raised_even_when_the_sdk_wrapped_it(monkeypatch, turn):
    def handler(request):
        raise SoftTimeLimitExceeded()  # (the worker's signal, inside the HTTP read)

    fake(monkeypatch, handler)
    with pytest.raises(SoftTimeLimitExceeded):
        LLMService(Plugin()).generate('Capital of Portugal?', Answer)
    assert turn.steps[0].ok is False and turn.steps[0].error_code == 'SoftTimeLimitExceeded'


def test_no_call_starts_past_the_turns_deadline(monkeypatch, turn):
    fake(monkeypatch, lambda request: pytest.fail('no request may be sent'))
    turn.deadline = turn.t0 - 1
    with pytest.raises(SoftTimeLimitExceeded):
        LLMService(Plugin()).generate('Capital of Portugal?', Answer)
    assert turn.steps == []


def test_a_call_gets_no_longer_than_the_time_left(monkeypatch, turn):
    seen = []

    def handler(request):
        seen.append(request.extensions['timeout'])
        return httpx.Response(200, json=reply(LISBON, cost_usd='0.0001'))

    fake(monkeypatch, handler)
    turn.deadline = time.monotonic() + 2  # (2 s left, against a 5 s setting)
    LLMService(Plugin()).generate('Capital of Portugal?', Answer)
    assert all(value <= 2 for value in seen[0].values() if value is not None)


def test_outside_a_turn_nothing_is_recorded(monkeypatch):
    fake(monkeypatch, lambda request: httpx.Response(200, json=reply(LISBON)))
    assert LLMService(Plugin()).generate('Capital of Portugal?', Answer).success
    assert recorder.current_step() is None


def test_no_sdk_retry_starts_past_the_deadline(monkeypatch, turn):
    """Review of #21: the SDK swallows the worker's signal and retries; the request hook refuses each retry."""
    calls = []

    def handler(request):
        calls.append(request)
        turn.deadline = time.monotonic() - 1  # (the soft limit fires during this read)
        raise SoftTimeLimitExceeded()

    fake(monkeypatch, handler)
    plugin = Plugin(llm_provider='openai', llm_model='openai/gpt-4o-mini', llm_base_url='https://openrouter.test/v1')
    with pytest.raises(SoftTimeLimitExceeded):
        LLMService(plugin).generate('Capital of Portugal?', Answer)
    assert len(calls) == 1  # (the SDK's two retries never reached the network)


def test_a_cost_that_is_not_an_amount_is_unknown_and_never_fails_the_answer(monkeypatch, turn):
    fake(monkeypatch, lambda request: httpx.Response(200, json=tool_reply({'city': 'Lisbon'}, cost='n/a')))
    plugin = Plugin(llm_provider='openai', llm_model='openai/gpt-4o-mini', llm_base_url='https://openrouter.test/v1')
    assert LLMService(plugin).generate('Capital of Portugal?', Answer).success
    assert turn.steps[0].cost_usd is None
