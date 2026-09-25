"""ibis provider: real instructor + openai client against a fake ibis transport."""

import json

import httpx
import openai
from pydantic import BaseModel

from indico_assistant.services.llm import factory
from indico_assistant.services.llm.service import LLMService


class Answer(BaseModel):
    city: str


class _Settings(dict):
    pass


class _Plugin:
    settings = _Settings(
        llm_provider="ibis",
        llm_model="ibis/Balanced",
        llm_base_url="http://ibis.test",
        llm_api_key="sk-ibis-abcdefghijkl.secret",
        timeout_seconds=5,
        max_tokens=256,
        max_retries=2,
    )


def _ibis_reply(content: str, cost: str) -> dict:
    return {
        "id": "chatcmpl-x", "object": "chat.completion", "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                  "cost_usd": cost},
        "ibis": {"request_id": "r1", "router": "general", "dial": "Balanced",
                 "chosen": "GPT-5.6-Luna", "served": "openai/gpt-oss-120b"},
    }


def test_ibis_generate_records_every_billed_attempt(monkeypatch):
    requests = []
    replies = [
        _ibis_reply("not json at all", "0.00010"),  # fails validation -> instructor retries
        _ibis_reply('```json\n{"city": "Lisbon"}\n```', "0.00020"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=replies[len(requests) - 1])

    real_openai = openai.OpenAI
    monkeypatch.setattr(
        factory, "OpenAI",
        lambda **kw: real_openai(http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kw),
    )

    llm = LLMService(_Plugin())
    response = llm.generate("Capital of Portugal?", Answer)

    assert response.success and response.result.city == "Lisbon"
    # ibis refuses these fields with a 400; MD_JSON must never send them
    for path, body in requests:
        assert path == "/v1/chat/completions"
        assert body["model"] == "ibis/Balanced"
        assert not {"tools", "tool_choice", "response_format"} & body.keys()
    assert [c["cost_usd"] for c in llm.call_log] == ["0.00010", "0.00020"]
    assert llm.call_log[-1] == {
        "stage": "Answer", "requested_model": "ibis/Balanced",
        "served_model": "openai/gpt-oss-120b", "prompt_tokens": 10, "completion_tokens": 5,
        "cost_usd": "0.00020", "ibis_chosen": "GPT-5.6-Luna", "ibis_dial": "Balanced",
        "ibis_request_id": "r1",
    }


def test_ibis_client_disables_sdk_retries():
    client = factory.create_instructor_client("ibis", "ibis/Balanced", api_key="sk-ibis-x")
    assert client.client.max_retries == 0
    assert str(client.client.base_url) == "https://labs.aithoth.com/ibis-api/v1/"
