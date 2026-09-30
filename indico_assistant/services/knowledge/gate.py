"""The router: one Jev decision gives the route of a message and, for a data question, its kind (spec 022).

Jev is a decision model, not a chat model: it answers typed questions at OpenRouter's decisions endpoint, so it is
called here, outside the Instructor abstraction (constitution 1.1.0, Principle III). Its key and timeout are settings,
its answers are validated, the classifier routes instead whenever it is skipped, and ``transport`` is injectable.

One call carries two ``choice`` questions: ``route`` (knowledge, change, data, chat, out_of_scope) and ``intent`` (the
classifier's 11 data intents, used only for data). The state is the format ibis's web gate measured
(ibis_routing.webgate.gate_input): the last two exchanges, each earlier reply cut to 400 characters, then the latest
message. The criteria are the ones the router probe measured (thread E study, jev_router_probe.py), with two changes
Lucas made on 2026-09-30: a "can you ...?" naming a concrete change is a change (the plan card is the offer, as the
classifier has it), and chat answers from the conversation, informed by general knowledge.
"""

import math
import time
from dataclasses import dataclass, field

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
#: Pinned by version: a new model could change the routes without anyone re-measuring them.
JEV_MODEL = "typesafe/jev-1.13"
CONTEXT_EXCHANGES = 2
ASSISTANT_CHARS = 400
PLAN_WAITING = "(A plan made in this chat is waiting for the user to confirm it.)"

ROUTES = {
    "knowledge": "How to do something in Indico, where a page or setting is, or what the assistant itself can or "
                 "cannot do in general (\"what can you do?\", \"can you create meetings?\", \"are you able to "
                 "send emails?\").",
    "change": "A request to make a change in Indico now (create, change, move, add, attach, cancel or undo "
              "something), including a polite one naming a concrete change (\"can you move it to 3pm?\", "
              "\"could you add a Teams meeting to this event?\"), or an agreement to a change the assistant just "
              "offered or planned. Asking how to make a change, or what the assistant can do in general, is not a "
              "change.",
    "data": "A question about information stored in Indico: events, meetings, talks, speakers, sessions, schedules, "
            "registrations, participants, minutes and notes, attached files and what they say. Unfamiliar project, "
            "topic or meeting names are usually things stored in Indico.",
    "chat": "Something the assistant can answer from the conversation so far, using general knowledge to explain "
            "it, without looking anything up in Indico or changing it: a follow-up about its last answer or about "
            "something the conversation mentions (a term, a result, a process), a request to rephrase, summarise, "
            "translate or reformat, drafting a text about the user's meetings, thanks or a greeting.",
    "out_of_scope": "Clearly unrelated to Indico, its content or this conversation: weather, sports, coding help, "
                    "general trivia.",
}
#: The classifier's data intents, in its own words (services/nl2sql/classifier.py; a test keeps them equal).
INTENTS = {
    "topic_search": "A broad search for a topic, keyword or project name across all content (events, notes, "
                    "contributions, documents).",
    "event_query": "Events, conferences, meetings: count, list, search, basic info, meeting minutes, notes.",
    "registration_query": "Event registrations, participants, check-ins.",
    "contribution_query": "Talks, presentations, contributions, papers.",
    "speaker_query": "Speakers, presenters, authors of contributions.",
    "session_query": "Conference sessions, tracks, time blocks.",
    "attendee_query": "Who attended events, or registrations with personal details.",
    "schedule_query": "Event schedules, timetables, the timing of contributions.",
    "attachment_query": "File metadata: filenames, types, storage locations.",
    "document_content_query": "The content within files: what slides say, paper contents.",
    "general_info": "General questions about the system, or unclear queries.",
}
QUESTIONS = {
    "route": {"type": "choice", "criteria": ROUTES,
              "instructions": "What kind of message is the latest message, sent to the chat assistant built into "
                              "Indico (an event management system)? It can look things up in Indico, make changes "
                              "in Indico after the user confirms, and explain how Indico works."},
    "intent": {"type": "choice", "criteria": INTENTS,
               "instructions": "If the latest message asks for information stored in Indico, which kind of "
                               "question is it?"},
}


@dataclass
class Decision:
    route: str | None
    intent: str | None
    skipped: bool
    reason: str  # "score", or why it was skipped: "no key", "timeout", "error", "invalid"
    confidence: float | None = None
    probabilities: dict = field(default_factory=dict)
    ms: int = 0
    cost: float | None = None
    name: str = JEV_MODEL


def _skipped(reason, ms=0, cost=None):
    return Decision(None, None, True, reason, ms=ms, cost=cost)


def state_of(messages, plan_waiting=False):
    """What Jev reads: user and assistant turns only, the last two exchanges and the latest message."""
    turns = [(m.get("role"), m.get("content") or "") for m in messages if m.get("role") in ("user", "assistant")]
    last_user = max((i for i, (role, _) in enumerate(turns) if role == "user"), default=None)
    if last_user is None:
        raise ValueError("a decision needs a user message")
    exchanges = []
    for role, text in turns[:last_user]:
        if role == "user":
            exchanges.append([text.strip(), ""])
        elif exchanges and not exchanges[-1][1]:
            exchanges[-1][1] = text[:ASSISTANT_CHARS]
    latest = turns[last_user][1].strip()
    note = f"{PLAN_WAITING}\n" if plan_waiting else ""
    if not exchanges and not note:
        return latest
    convo = "".join(f"USER: {u}\nASSISTANT: {a}\n\n" for u, a in exchanges[-CONTEXT_EXCHANGES:])
    return f"Earlier conversation:\n{convo}{note}LATEST MESSAGE: {latest}"


def _http(payload, key, timeout):
    import httpx

    response = httpx.post(JEV_URL, json=payload, timeout=timeout, headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    return response.json()


def _number(value):
    """A real probability (a bool is an int to Python, NaN is a float: neither counts)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0.0 <= value <= 1.0 else None


def decide(messages, settings, *, plan_waiting=False, transport=_http):
    """Jev's route (and intent) for the latest message. Never raises: anything wrong is a skipped decision."""
    import httpx

    key = settings.get("jev_api_key")
    if not key:
        return _skipped("no key")
    timeout = float(settings.get("jev_timeout_seconds") or 1.5)
    try:
        payload = {"model": JEV_MODEL, "state": state_of(messages, plan_waiting), "questions": QUESTIONS}
    except ValueError:
        return _skipped("error")
    started = time.monotonic()
    try:
        body = transport(payload, key, timeout)
    except httpx.TimeoutException:
        return _skipped("timeout", int((time.monotonic() - started) * 1000))
    except Exception:  # noqa: BLE001 - the classifier routes instead
        return _skipped("error", int((time.monotonic() - started) * 1000))
    ms = int((time.monotonic() - started) * 1000)
    answers = (body or {}).get("answers") or {}
    cost = ((body or {}).get("usage") or {}).get("cost")
    route, intent = answers.get("route") or {}, answers.get("intent") or {}
    probabilities = route.get("probabilities") or {}
    if (route.get("choice") not in ROUTES or not probabilities
            or any(k not in ROUTES or _number(v) is None for k, v in probabilities.items())):
        return _skipped("invalid", ms, cost)
    if ms > timeout * 1000:  # late: it does not decide
        return _skipped("timeout", ms, cost)
    return Decision(route["choice"], intent.get("choice") if intent.get("choice") in INTENTS else None, False,
                    "score", confidence=_number(route.get("confidence")), probabilities=probabilities, ms=ms,
                    cost=cost)
