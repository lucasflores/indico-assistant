"""The knowledge gate: Jev, asked whether the latest message is a knowledge question (spec 022, FR-001/004/006)."""

import httpx
import pytest

from indico_assistant.services.knowledge import gate

SETTINGS = {"knowledge_jev_api_key": "sk-or-test", "knowledge_jev_cutoff": 0.2, "knowledge_jev_timeout_seconds": 1.5}
TALK = [{"role": "system", "content": "The user is on the page of event 657."},
        {"role": "user", "content": "Can you add a Teams meeting to this event?"},
        {"role": "assistant", "content": "Yes, I can add a Microsoft Teams meeting to this meeting. Shall I? " + "x" * 500},
        {"role": "user", "content": "how would I do it myself?"}]


def _transport(score=0.5, raises=None, record=None):
    def send(payload, key, timeout):
        if record is not None:
            record.append((payload, key, timeout))
        if raises:
            raise raises
        return {"answers": {"knowledge": {"noul": score}}, "usage": {"cost": 0.0000165}}
    return send


def test_the_input_is_the_web_gate_format():
    instruction, state = gate.gate_input(TALK)
    assert instruction == gate.ASK_CONTEXT
    assert state.startswith("Earlier conversation:\nUSER: Can you add a Teams meeting to this event?\nASSISTANT: Yes")
    assert state.endswith("LATEST MESSAGE: how would I do it myself?")
    assert "x" * 401 not in state  # each earlier reply cut to 400 characters
    assert "event 657" not in state  # only user and assistant turns
    assert gate.gate_input([{"role": "user", "content": "What can you do?"}]) == (gate.ASK_FIRST, "What can you do?")


def test_at_or_above_the_cut_off_is_knowledge():
    sent = []
    result = gate.decide(TALK, SETTINGS, transport=_transport(0.2, record=sent))
    assert gate.is_knowledge(result, SETTINGS) and result.score == 0.2 and not result.skipped
    payload, key, timeout = sent[0]
    assert payload["model"] == gate.JEV_MODEL and payload["questions"]["knowledge"]["type"] == "noul"
    assert (key, timeout) == ("sk-or-test", 1.5)
    assert not gate.is_knowledge(gate.decide(TALK, SETTINGS, transport=_transport(0.19)), SETTINGS)


@pytest.mark.parametrize(("settings", "transport", "reason"), [
    ({**SETTINGS, "knowledge_jev_api_key": None}, _transport(), "no key"),
    (SETTINGS, _transport(raises=httpx.ReadTimeout("slow")), "timeout"),
    (SETTINGS, _transport(raises=RuntimeError("500")), "error"),
    (SETTINGS, _transport(score=1.7), "no score"),
    (SETTINGS, _transport(score=True), "no score"),
    (SETTINGS, _transport(score=float("nan")), "no score"),
    (SETTINGS, _transport(score="0.9"), "no score"),
])
def test_skipped_never_fails(settings, transport, reason):
    result = gate.decide(TALK, settings, transport=transport)
    assert result.skipped and result.reason == reason and not gate.is_knowledge(result, settings)


def test_a_late_decision_is_skipped(monkeypatch):
    clock = iter([0.0, 2.0])
    monkeypatch.setattr(gate.time, "monotonic", lambda: next(clock))
    result = gate.decide(TALK, SETTINGS, transport=_transport(0.9))
    assert result.skipped and result.reason == "timeout" and result.score == 0.9  # kept for the audit


def test_a_conversation_without_a_user_message_is_skipped():
    assert gate.decide([{"role": "assistant", "content": "Hello"}], SETTINGS, transport=_transport()).skipped
