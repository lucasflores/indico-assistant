"""The turn's tool loop (spec 025, research R1), generalised from the connector's (``services/connectors/loop.py``).

Each step is one ``LLMService.generate`` returning a validated ``Step``: one tool call, or the answer (constitution
III: any provider can run it, through Instructor). One tool per step, in sequence, which the recorder's step stack
needs anyway. The limits are settings (data-model "Settings"): model requests, tool calls, measured cost and time.
Hitting one, the turn answers from what it found and says it stopped (FR-025). A repeated identical call ends the
lookups too. What a tool returns goes back marked as untrusted data (FR-024). With ``turn_pin_model``, the first
step's ibis pick is sent as the model for the rest of the turn.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Union

from celery.exceptions import SoftTimeLimitExceeded
from pydantic import BaseModel, Field, create_model, model_validator

from indico_assistant.services.analytics import recorder
from indico_assistant.services.connectors import Tool
from indico_assistant.services.turn.citations import Citation
from indico_assistant.services.turn.tools import Ctx

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 8_000
STEP_SECONDS = 30.0
MIN_STEP_SECONDS = 5.0  # with less left, the turn answers instead of looking up more
FINAL_SECONDS = 10.0  # the answer always gets at least this
MARK = "tool_data"
#: The mark's tags, in any case and spacing: "<" becomes "‹", so a tool's text can't open or close one
_TAG = re.compile(rf"<(\s*/?\s*{MARK})", re.I)

UNAVAILABLE = (
    "The assistant's language model couldn't be reached just now, so nothing was looked up or changed. "
    "Please try again in a moment."
)
NOT_ANSWERED = "I could not answer that just now. Please try again in a moment."
STOPPED = {
    "requests": "I stopped after the most steps an answer may take",
    "tools": "I stopped after the most lookups an answer may make",
    "cost": "I stopped at the cost limit for one answer",
    "budget": "I stopped at the time limit for one answer",
}
#: Provider errors: nothing can be answered, and nothing was changed (FR-028)
_DOWN = {"connection_error", "timeout", "rate_limit", "authentication_error", "model_not_found", "not_configured"}


class Final(BaseModel):
    reply: str = Field(..., description="The answer to the user, in markdown, citing document pages as [p.N]")
    citations: list[Citation] = Field(default_factory=list, description="One per cited document page")


class _Step(BaseModel):
    @model_validator(mode="after")
    def _one(self) -> _Step:
        call, answer = getattr(self, "call", None), getattr(self, "answer", None)
        if (call is None) == (answer is None or not answer.reply.strip()):
            raise ValueError("give either one tool call or the answer")
        return self


@cache
def step_model(tools: tuple[Tool, ...]) -> type[BaseModel]:
    """``Step``: one of ``tools``' calls (told apart by ``tool``), or the answer."""
    calls = tuple(t.args for t in tools)
    # a plain union (anyOf), not a discriminated one: some providers behind ibis take a subset of JSON Schema
    call = Union[calls] if len(calls) > 1 else calls[0]  # noqa: UP007
    return create_model(
        "Step",
        __base__=_Step,
        call=(call | None, Field(None, description="The one tool to call next; null once you can answer")),
        answer=(Final | None, Field(None, description="The answer, when no more lookups are needed; else null")),
    )


def mark(text: str) -> str:
    """A tool's text inside the mark, cut to size, unable to close the mark early."""
    body = _TAG.sub("‹\\1", text[:MAX_RESULT_CHARS])
    cut = "\n(cut short)" if len(text) > MAX_RESULT_CHARS else ""
    return f"<{MARK}>\n{body}{cut}\n</{MARK}>"


def _prompt(ctx: Ctx, message: str, tools: Sequence[Tool], done: list[tuple[Any, str]], final: str | None) -> str:
    page = (
        f'The user is on the page of event {ctx.page_event_id}: "this event" and "this meeting" mean it.'
        if ctx.page_event_id
        else "The user is not on an event page."
    )
    lines = [
        "## The page",
        page,
        "",
        "## Remembered from earlier answers",
        ctx.memory.render(),
        "",
        "## Tools",
        *(f"- {t.name}: {t.description}" for t in tools),
        "",
        "## Looked up so far",
    ]
    if not done:
        lines.append("(nothing yet)")
    for n, (call, text) in enumerate(done, 1):
        arguments = _TAG.sub("‹\\1", call.model_dump_json(exclude={"tool"}))  # (the model wrote them)
        lines += [f"{n}. {call.tool} {arguments}", mark(text)]
    if final:
        lines += ["", f"No more lookups ({final}): answer now from what was found."]
    return "\n".join([*lines, "", "## The latest message", message])


@dataclass
class TurnResult:
    text: str = NOT_ANSWERED
    citations: list[Citation] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)  # {name, ms, ok} per call
    stop: str = "answered"  # answered | requests | tools | cost | budget | repeated | failed_step | plan | unavailable
    failed: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)


def _cost(calls: list[dict[str, Any]]) -> float:
    return float(sum(c for call in calls if (c := recorder.cost(call.get("cost_usd"))) is not None))


def run(
    ctx: Ctx, message: str, tools: Sequence[Tool], *, system_prompt: str, now: Callable[[], float] = time.monotonic
) -> TurnResult:
    """Answer ``message`` with ``tools``; the conversation before it is ``ctx.history``."""
    from indico_assistant.services.llm.service import collect_calls

    tools = tuple(tools)
    by_name, step = {t.name: t for t in tools}, step_model(tools)
    settings = ctx.settings
    max_requests = int(settings.get("turn_max_requests") or 8)
    max_tools = int(settings.get("turn_max_tool_calls") or 12)
    max_cost = float(settings.get("turn_max_cost_usd") or 0.10)
    deadline = float(settings.get("turn_deadline_seconds") or 75)
    pin = bool(settings.get("turn_pin_model", True))
    started = now() if ctx.started is None else ctx.started
    result, seen = TurnResult(stop="requests"), set()
    done: list[tuple[Any, str]] = []
    model: str | None = None
    answered, spent = False, 0.0
    with collect_calls() as calls:
        for _ in range(max_requests - 1):  # (the last request is kept for the answer)
            left = deadline - (now() - started)
            if left < MIN_STEP_SECONDS:
                result.stop = "budget"
                break
            if spent >= max_cost:
                result.stop = "cost"
                break
            if len(result.tools) >= max_tools:
                result.stop = "tools"
                break
            response = ctx.llm.generate(
                _prompt(ctx, message, tools, done, None),
                step,
                system_prompt=system_prompt,
                messages=ctx.history,
                timeout=min(STEP_SECONDS, left),
                model=model,
            )
            spent += _cost(response.calls)  # (measured, never estimated: spec 024)
            if pin and model is None:
                model = next((c.get("ibis_chosen") for c in reversed(response.calls) if c.get("ibis_chosen")), None)
            if not response.success:
                error_type = getattr(getattr(response.error, "error_type", None), "value", None)
                if error_type in _DOWN:
                    result.text, result.stop, result.failed = UNAVAILABLE, "unavailable", True
                    result.calls = calls
                    return result
                logger.warning("A turn step failed (%s)", error_type)
                result.stop = "failed_step"
                break
            if response.result.call is None:
                result.text, result.citations = response.result.answer.reply, response.result.answer.citations
                result.stop, answered = "answered", True
                break
            call = response.result.call
            if (key := call.model_dump_json()) in seen:
                result.stop = "repeated"
                break
            seen.add(key)
            done.append((call, _call(ctx, by_name[call.tool], call, result, now)))
            if ctx.plan is not None:  # a plan to confirm: its card and the planner's words are the answer
                result.text, result.stop, answered = ctx.plan[0], "plan", True
                break
        if not answered:
            reason = STOPPED.get(result.stop)
            left = max(FINAL_SECONDS, deadline - (now() - started))
            response = ctx.llm.generate(
                _prompt(ctx, message, tools, done, reason or "answer"),
                Final,
                system_prompt=system_prompt,
                messages=ctx.history,
                timeout=min(STEP_SECONDS, left),
                model=model,
            )
            if response.success:
                result.text, result.citations = response.result.reply, response.result.citations
                if reason:  # FR-025: the user is told the answer may be incomplete
                    result.text += f"\n\n_({reason}: ask me to go on if something is missing.)_"
            else:
                error_type = getattr(getattr(response.error, "error_type", None), "value", None)
                result.text = UNAVAILABLE if error_type in _DOWN else NOT_ANSWERED
                result.failed = True
    result.calls = calls
    return result


def _call(ctx: Ctx, tool: Tool, call: Any, result: TurnResult, now: Callable[[], float]) -> str:
    """Run one tool as an analytics step (its name, time and outcome). Its failure is text for the model."""
    began, ok = now(), True
    with recorder.step("tool", "turn", tool.name) as tool_step:
        try:
            text = tool.run(ctx, call)
        except SoftTimeLimitExceeded:  # (the worker's limit: the task reports the timeout)
            raise
        except Exception:  # noqa: BLE001 - one tool failing must not fail the answer
            logger.exception("The %s tool failed", tool.name)
            from indico.core.db import db

            db.session.rollback()
            text, ok = "The lookup failed.", False
            tool_step.error_code = "failed"
        tool_step.ok = ok
    result.tools.append({"name": tool.name, "ms": int((now() - began) * 1000), "ok": ok})
    from indico_assistant.services.knowledge import links

    paths, guide = links.found_in([text], ctx.base_url)  # (this Indico's pages and the guide's: the answer may link)
    ctx.link_paths.update(paths)
    ctx.guide_urls.update(guide)
    return text
