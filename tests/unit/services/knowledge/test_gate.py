"""The router: one Jev decision gives the route and, for data, the kind of question (spec 022, Lucas 2026-09-30)."""

import re
import time

import httpx
import pytest

from indico_assistant.services.knowledge import gate

SETTINGS = {"jev_api_key": "sk-or-test", "jev_timeout_seconds": 1.5}
TALK = [{"role": "system", "content": "The user is on the page of event 657."},
        {"role": "user", "content": "Can you add a Teams meeting to this event?"},
        {"role": "assistant", "content": "Yes, I can add a Microsoft Teams meeting to this meeting. Shall I? " + "x" * 500},
        {"role": "user", "content": "yes please"}]


def _answer(route="change", intent="event_query", probabilities=None):
    return {"answers": {
        "route": {"type": "choice", "choice": route, "confidence": 0.9,
                  "probabilities": probabilities or {route: 0.9, "knowledge": 0.1}},
        "intent": {"type": "choice", "choice": intent, "confidence": 0.8, "probabilities": {intent: 0.8}}},
        "usage": {"cost": 0.00004}}


def _transport(body=None, raises=None, record=None):
    def send(payload, key, timeout):
        if record is not None:
            record.append((payload, key, timeout))
        if raises:
            raise raises
        return body if body is not None else _answer()
    return send


def test_the_state_is_the_web_gate_format():
    state = gate.state_of(TALK)
    assert state.startswith("Earlier conversation:\nUSER: Can you add a Teams meeting to this event?\nASSISTANT: Yes")
    assert state.endswith("LATEST MESSAGE: yes please")
    assert "x" * 401 not in state and "event 657" not in state  # replies cut to 400; only user/assistant turns
    assert gate.state_of([{"role": "user", "content": "What can you do?"}]) == "What can you do?"
    assert gate.state_of(TALK, plan_waiting=True).endswith(
        "(A plan made in this chat is waiting for the user to confirm it.)\nLATEST MESSAGE: yes please")


def test_one_call_asks_both_questions():
    sent = []
    decision = gate.decide(TALK, SETTINGS, transport=_transport(record=sent))
    payload, key, timeout = sent[0]
    assert set(payload["questions"]) == {"route", "intent"} and payload["model"] == gate.JEV_MODEL
    assert payload["questions"]["route"]["type"] == "choice"
    assert set(payload["questions"]["route"]["criteria"]) == set(gate.ROUTES)
    assert set(payload["questions"]["intent"]["criteria"]) == set(gate.INTENTS)
    assert (key, timeout) == ("sk-or-test", 1.5)
    assert (decision.route, decision.intent, decision.skipped, decision.reason) == ("change", "event_query", False, "score")
    assert decision.confidence == 0.9 and decision.cost == 0.00004
    assert decision.intent_confidence == 0.8  # (fresh review, PR #15) the intent's own, not the route's


def test_the_intents_are_the_classifiers_data_intents():
    from indico_assistant.services.nl2sql.classifier import CLASSIFICATION_PROMPT

    section = CLASSIFICATION_PROMPT.split("## INTENTS")[1].split("## CLASSIFICATION HINTS")[0]
    listed = re.findall(r"^- \*\*(\w+)\*\*:", section, re.M)
    routes = {"write_request", "knowledge", "chat", "out_of_scope"}
    assert set(gate.INTENTS) == set(listed) - routes and len(gate.INTENTS) == 11


def test_a_concrete_can_you_is_a_change_as_the_classifier_has_it():
    from indico_assistant.services.nl2sql.classifier import CLASSIFICATION_PROMPT

    assert "Can you move it to 3pm?" in CLASSIFICATION_PROMPT and "can you move it to 3pm?" in gate.ROUTES["change"]
    assert "can you create meetings?" in CLASSIFICATION_PROMPT and "can you create meetings?" in gate.ROUTES["knowledge"]


@pytest.mark.parametrize(("settings", "transport", "reason"), [
    ({**SETTINGS, "jev_api_key": None}, _transport(), "no key"),
    (SETTINGS, _transport(raises=httpx.ReadTimeout("slow")), "timeout"),
    (SETTINGS, _transport(raises=RuntimeError("500")), "error"),
    (SETTINGS, _transport(body=_answer(route="gossip")), "invalid"),
    (SETTINGS, _transport(body={"answers": {}}), "invalid"),
    (SETTINGS, _transport(body=_answer(probabilities={"change": float("nan")})), "invalid"),
    (SETTINGS, _transport(body=[]), "invalid"),  # (shapes an alpha endpoint could send: none may raise)
    (SETTINGS, _transport(body={"answers": {"route": "knowledge"}}), "invalid"),
    (SETTINGS, _transport(body={"answers": {"route": {"choice": ["knowledge"], "probabilities": {}}}}), "invalid"),
    (SETTINGS, _transport(body={"answers": [], "usage": "free"}), "invalid"),
])
def test_skipped_never_fails(settings, transport, reason):
    decision = gate.decide(TALK, settings, transport=transport)
    assert decision.skipped and decision.reason == reason and decision.route is None


def test_a_malformed_intent_is_dropped_too():
    body = _answer(route="data")
    body["answers"]["intent"] = {"choice": ["event_query"]}
    decision = gate.decide(TALK, SETTINGS, transport=_transport(body=body))
    assert decision.route == "data" and decision.intent is None
    body["answers"]["intent"] = "event_query"
    assert gate.decide(TALK, SETTINGS, transport=_transport(body=body)).intent is None


def test_an_offer_is_noted_for_jev():
    """The offer usually ends a reply, past the 400 characters Jev sees of it."""
    state = gate.state_of(TALK, offer="add a Teams meeting to Sync")
    assert state.endswith("(The assistant's last answer offered to make this change: add a Teams meeting to Sync)\n"
                          "LATEST MESSAGE: yes please")
    sent = []
    gate.decide(TALK, SETTINGS, offer="add a Teams meeting to Sync", transport=_transport(record=sent))
    assert "add a Teams meeting to Sync" in sent[0][0]["state"]


def test_an_unknown_intent_is_dropped_not_fatal():
    decision = gate.decide(TALK, SETTINGS, transport=_transport(body=_answer(route="data", intent="weather_query")))
    assert decision.route == "data" and decision.intent is None and not decision.skipped


def test_a_late_decision_is_skipped(monkeypatch):
    clock = iter([0.0, 2.0])
    monkeypatch.setattr(gate.time, "monotonic", lambda: next(clock))
    decision = gate.decide(TALK, SETTINGS, transport=_transport())
    assert decision.skipped and decision.reason == "timeout" and decision.route is None


def test_one_deadline_for_the_whole_call():
    """(review, PR #15) httpx's timeout is per phase: the user never waits past the setting for a decision"""
    def slow(payload, key, timeout):
        time.sleep(1.0)
        return _answer()
    started = time.monotonic()
    decision = gate.decide(TALK, {**SETTINGS, "jev_timeout_seconds": 0.2}, transport=slow)
    assert decision.skipped and decision.reason == "timeout" and time.monotonic() - started < 0.6


def test_a_conversation_without_a_user_message_is_skipped():
    assert gate.decide([{"role": "assistant", "content": "Hello"}], SETTINGS, transport=_transport()).skipped
