"""ibis provider: real instructor + openai client against a fake ibis transport."""

import json
import threading
import time
from unittest.mock import MagicMock

import httpx
import openai
import pytest
from pydantic import BaseModel

from indico_assistant.services.llm import factory
from indico_assistant.services.llm.service import LLMService


class Answer(BaseModel):
    city: str


class _Plugin:
    settings = dict(
        llm_provider="ibis",
        llm_model="ibis/Balanced",
        llm_base_url="http://ibis.test",
        llm_api_key="sk-ibis-abcdefghijkl.secret",
        llm_ibis_mode="md_json",  # these tests are about the records; the modes are tested below
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

    _fake_ibis(monkeypatch, handler)

    llm = LLMService(_Plugin())
    response = llm.generate("Capital of Portugal?", Answer)
    assert response.retries == 1 and len(response.calls) == 2  # retries agree with the records

    assert response.success and response.result.city == "Lisbon"
    # MD_JSON asks in the prompt, so it sends none of the structured-output fields
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


def _fake_ibis(monkeypatch, handler):
    real_openai = openai.OpenAI
    monkeypatch.setattr(
        factory, "OpenAI",
        lambda **kw: real_openai(http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kw),
    )


def test_concurrent_calls_on_one_service_keep_their_own_records(monkeypatch):
    """The service (and its client) is shared per process; overlapping calls must not see each other's
    completions (they used to: each call hooked the shared client, so every hook saw every completion)."""
    both_in_flight = threading.Barrier(2, timeout=5)

    def handler(request: httpx.Request) -> httpx.Response:
        city = "Lisbon" if "Portugal" in request.content.decode() else "Madrid"
        both_in_flight.wait()  # both requests are open at the same time
        cost = "0.00011" if city == "Lisbon" else "0.00022"
        return httpx.Response(200, json=_ibis_reply(f'```json\n{{"city": "{city}"}}\n```', cost))

    _fake_ibis(monkeypatch, handler)
    llm = LLMService(_Plugin())
    llm._ensure_client()  # one long-lived client shared by both calls, as in production
    results = {}

    def ask(question):
        results[question] = llm.generate(question, Answer)

    threads = [threading.Thread(target=ask, args=(q,)) for q in ("Capital of Portugal?", "Capital of Spain?")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert [c["cost_usd"] for c in results["Capital of Portugal?"].calls] == ["0.00011"]
    assert [c["cost_usd"] for c in results["Capital of Spain?"].calls] == ["0.00022"]
    assert sorted(c["cost_usd"] for c in llm.call_log) == ["0.00011", "0.00022"]


def test_call_log_is_bounded(monkeypatch):
    from indico_assistant.services.llm import service as service_module

    monkeypatch.setattr(service_module, "CALL_LOG_MAX", 2)
    _fake_ibis(monkeypatch, lambda request: httpx.Response(
        200, json=_ibis_reply('```json\n{"city": "Lisbon"}\n```', "0.00010")))
    llm = LLMService(_Plugin())
    for _ in range(3):
        assert len(llm.generate("Capital of Portugal?", Answer).calls) == 1
    assert len(llm.call_log) == 2  # the service lives as long as the process: only recent records kept


def test_unsupported_provider_message_lists_ibis():
    with pytest.raises(ValueError, match="ollama, huggingface, openai, ibis"):
        factory.create_instructor_client("ibsi", "m")


def test_health_check_completion_is_recorded(monkeypatch):
    _fake_ibis(monkeypatch, lambda request: httpx.Response(
        200, json=_ibis_reply('```json\n{"status": "ok"}\n```', "0.00001")))
    llm = LLMService(_Plugin())
    assert llm.health_check().status == "connected"
    assert [(c["stage"], c["cost_usd"]) for c in llm.call_log] == [("health_check", "0.00001")]


def test_first_calls_from_several_threads_build_one_client(monkeypatch):
    built = []

    def slow_create(self, settings):
        time.sleep(0.05)  # widen the window in which a second thread could also build one
        built.append(1)
        return MagicMock()

    monkeypatch.setattr(LLMService, "_create_client", slow_create)
    llm = LLMService(_Plugin())
    threads = [threading.Thread(target=llm._ensure_client) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1


def test_a_client_whose_hooks_fail_is_not_cached(monkeypatch):
    """Otherwise every later call would run without recording any cost."""
    broken = MagicMock()
    broken.on.side_effect = RuntimeError("no hooks in this instructor")
    good = MagicMock()
    clients = iter([broken, good])
    monkeypatch.setattr(LLMService, "_create_client", lambda self, settings: next(clients))
    llm = LLMService(_Plugin())
    assert llm._ensure_client()[0] is None
    assert llm._ensure_client()[0] is good


def test_switching_provider_rebuilds_the_client(monkeypatch):
    monkeypatch.setattr(LLMService, "_create_client", lambda self, settings: MagicMock())
    plugin = _Plugin()
    plugin.settings = dict(_Plugin.settings)
    llm = LLMService(plugin)
    first = llm._ensure_client()[0]
    assert llm._ensure_client()[0] is first
    plugin.settings.update(llm_provider="openai", llm_base_url="https://openrouter.test/v1")
    assert llm._ensure_client()[0] is not first  # mode and base URL follow the admin's change


def test_attempt_lost_in_transport_is_recorded(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow dial", request=request)

    _fake_ibis(monkeypatch, handler)
    response = LLMService(_Plugin()).generate("Capital of Portugal?", Answer)
    assert not response.success
    assert response.calls and response.calls[0]["cost_usd"] is None
    assert response.calls[0]["error"] in ("APITimeoutError", "APIConnectionError")


def test_collect_calls_gathers_a_request_across_generate_calls(monkeypatch):
    from indico_assistant.services.llm.service import collect_calls

    _fake_ibis(monkeypatch, lambda request: httpx.Response(
        200, json=_ibis_reply('```json\n{"city": "Lisbon"}\n```', "0.00010")))
    llm = LLMService(_Plugin())
    with collect_calls() as calls:
        llm.generate("Capital of Portugal?", Answer)
        llm.generate("Capital of Portugal, again?", Answer)
    assert [c["cost_usd"] for c in calls] == ["0.00010", "0.00010"]


def test_health_check_is_bounded(monkeypatch):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_ibis_reply('```json\n{"status": "ok"}\n```', "0.00001"))

    _fake_ibis(monkeypatch, handler)
    LLMService(_Plugin()).health_check()
    assert bodies[0]["max_tokens"] == 16


def test_collectors_nest_and_the_outer_one_survives_errors(monkeypatch):
    from indico_assistant.services.llm.service import collect_calls

    _fake_ibis(monkeypatch, lambda request: httpx.Response(
        200, json=_ibis_reply('```json\n{"city": "Lisbon"}\n```', "0.00010")))
    llm = LLMService(_Plugin())
    with collect_calls() as outer:
        with pytest.raises(RuntimeError):
            with collect_calls() as inner:  # e.g. the pipeline's own collector
                llm.generate("Capital of Portugal?", Answer)
                raise RuntimeError("pipeline failed after the call")
    assert len(inner) == 1 and len(outer) == 1


# --- the structured-output modes (llm_ibis_mode) ---------------------------------------------

def _plugin(mode):
    plugin = _Plugin()
    plugin.settings = {**_Plugin.settings, "llm_ibis_mode": mode}
    return plugin


def _tool_reply(arguments: str) -> dict:
    reply = _ibis_reply("", "0.00030")
    reply["choices"][0] = {"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": "Answer", "arguments": arguments}}]}}
    return reply


def test_tools_mode_sends_the_schema_as_a_tool_and_reads_the_call(monkeypatch):
    """ibis carries tools since ibis-api #17, so tools is what the ibis provider asks with by default."""
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=_tool_reply('{"city": "Lisbon"}'))

    _fake_ibis(monkeypatch, handler)
    for mode in ("tools", None):                                   # None: the default
        response = LLMService(_plugin(mode)).generate("Capital of Portugal?", Answer)
        assert response.success and response.result.city == "Lisbon"
    for body in requests:
        assert body["tools"][0]["function"]["name"] == "Answer"
        assert body["tool_choice"] == {"type": "function", "function": {"name": "Answer"}}
        assert "response_format" not in body


def test_json_schema_mode_sends_a_response_format_and_reads_the_content(monkeypatch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=_ibis_reply('{"city": "Lisbon"}', "0.00020"))

    _fake_ibis(monkeypatch, handler)
    response = LLMService(_plugin("json_schema")).generate("Capital of Portugal?", Answer)
    assert response.success and response.result.city == "Lisbon"
    (body,) = requests
    assert body["response_format"]["type"] == "json_schema" and "tools" not in body


def test_an_unknown_mode_is_refused_naming_the_choices():
    with pytest.raises(ValueError, match="tools, json_schema, md_json"):
        factory.create_instructor_client("ibis", "ibis/Balanced", api_key="sk-ibis-x", ibis_mode="xml")


def test_changing_the_mode_rebuilds_the_client(monkeypatch):
    _fake_ibis(monkeypatch, lambda request: httpx.Response(200, json=_tool_reply('{"city": "Lisbon"}')))
    plugin = _plugin("tools")
    llm = LLMService(plugin)
    llm.generate("q", Answer)
    first = llm._client
    plugin.settings = {**plugin.settings, "llm_ibis_mode": "md_json"}
    llm._ensure_client()
    assert llm._client is not first
