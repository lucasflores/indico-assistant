"""The knowledge gate: Jev decides whether the latest message is a "how do I" / "can you" question (spec 022).

Jev is a decision model, not a chat model: it returns a probability from OpenRouter's decisions endpoint, so it is
called here, outside the Instructor abstraction (constitution 1.1.0, Principle III): its key and timeout are settings,
its score is validated, the classifier decides whenever it is skipped, and ``transport`` is injectable for tests.
The input is the format ibis's web gate measured (ibis_routing.webgate.gate_input): the last two exchanges, each
earlier reply cut to 400 characters, and the latest message.
"""

import math
import time
from dataclasses import dataclass

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
#: Pinned by version: a new model would move the cut-off without anyone re-measuring it.
JEV_MODEL = "typesafe/jev-1.13"
CONTEXT_EXCHANGES = 2
ASSISTANT_CHARS = 400
# The instructions measured in the research routing test
ASK_FIRST = ("This message, sent to the assistant built into Indico (an event management system), asks how to do "
             "something in Indico, where to find a page or setting, or what the assistant itself can or cannot do. "
             "It does not ask for data about events, people or documents, and it does not tell the assistant to make "
             "a specific change.")
ASK_CONTEXT = ("The LATEST MESSAGE, sent to the assistant built into Indico (an event management system), asks how to "
               "do something in Indico, where to find a page or setting, or what the assistant itself can or cannot "
               "do. It does not ask for data about events, people or documents, and it is not an instruction to make, "
               "or an agreement to, a specific change.")


@dataclass
class GateResult:
    score: float | None
    skipped: bool
    reason: str  # "score", or why it was skipped: "no key", "timeout", "error", "no score"
    ms: int = 0
    cost: float | None = None
    name: str = JEV_MODEL


def gate_input(messages):
    """(instruction, state) for Jev, from chat messages ({role, content}); only user and assistant turns count."""
    turns = [(m.get("role"), m.get("content") or "") for m in messages if m.get("role") in ("user", "assistant")]
    last_user = max((i for i, (role, _) in enumerate(turns) if role == "user"), default=None)
    if last_user is None:
        raise ValueError("a gate decision needs a user message")
    exchanges = []
    for role, text in turns[:last_user]:
        if role == "user":
            exchanges.append([text.strip(), ""])
        elif exchanges and not exchanges[-1][1]:
            exchanges[-1][1] = text[:ASSISTANT_CHARS]
    latest = turns[last_user][1].strip()
    if not exchanges:
        return ASK_FIRST, latest
    convo = "".join(f"USER: {u}\nASSISTANT: {a}\n\n" for u, a in exchanges[-CONTEXT_EXCHANGES:])
    return ASK_CONTEXT, f"Earlier conversation:\n{convo}LATEST MESSAGE: {latest}"


def _http(payload, key, timeout):
    import httpx

    response = httpx.post(JEV_URL, json=payload, timeout=timeout, headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    return response.json()


def _probability(value):
    """A score only if it is a real probability (a bool is an int to Python, NaN is a float: neither counts)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0.0 <= value <= 1.0 else None


def decide(messages, settings, transport=_http):
    """Jev's decision on the latest message. Never raises: anything wrong is a skipped decision."""
    import httpx

    key = settings.get("knowledge_jev_api_key")
    if not key:
        return GateResult(None, True, "no key")
    timeout = float(settings.get("knowledge_jev_timeout_seconds") or 1.5)
    try:
        instruction, state = gate_input(messages)
    except ValueError:
        return GateResult(None, True, "error")
    payload = {"model": JEV_MODEL, "state": state,
               "questions": {"knowledge": {"type": "noul", "instructions": instruction}}}
    started = time.monotonic()
    try:
        body = transport(payload, key, timeout)
    except httpx.TimeoutException:
        return GateResult(None, True, "timeout", int((time.monotonic() - started) * 1000))
    except Exception:  # noqa: BLE001 - the classifier decides instead
        return GateResult(None, True, "error", int((time.monotonic() - started) * 1000))
    ms = int((time.monotonic() - started) * 1000)
    score = _probability((((body or {}).get("answers") or {}).get("knowledge") or {}).get("noul"))
    cost = ((body or {}).get("usage") or {}).get("cost")
    if score is None:
        return GateResult(None, True, "no score", ms, cost)
    if ms > timeout * 1000:  # late: kept for the audit, but it does not decide
        return GateResult(score, True, "timeout", ms, cost)
    return GateResult(score, False, "score", ms, cost)


def is_knowledge(result, settings):
    return (result is not None and not result.skipped
            and result.score >= float(settings.get("knowledge_jev_cutoff", 0.2)))
