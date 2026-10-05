"""What an answer records about itself when it is made (spec 021 R4, R5; spec 025: through the turn's tools).

Feature: 021-issue-reports
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from indico_assistant.services.actions.planner import PlanTurn
from indico_assistant.services.nl2sql.models import PipelineError, PipelineErrorType, PipelineResult
from indico_assistant.services.turn import abilities
from indico_assistant.services.turn.tools import Ctx


def query(result: PipelineResult, allowed_tables=None):
    ctx = Ctx(
        user=MagicMock(id=1, is_admin=False),
        session_id=uuid4(),
        message_id=None,
        page_event_id=7,
        history=[{"role": "user", "content": "earlier"}],
        settings={},
        llm=MagicMock(),
        base_url="x",
        allowed_tables=allowed_tables,
    )
    pipeline = MagicMock()
    pipeline.process.return_value = result
    with (
        patch("indico_assistant.plugin.AssistantPlugin"),
        patch("indico_assistant.services.nl2sql.create_nl2sql_pipeline_from_plugin", return_value=pipeline) as factory,
        patch("indico.modules.events.Event.query"),
    ):
        text = abilities._query_data(ctx, abilities.QueryDataArgs(tool="query_data", question="Q"))
    return text, ctx, pipeline, factory


def test_a_query_records_its_evidence():
    text, ctx, pipeline, factory = query(
        PipelineResult(
            success=True,
            answer="Two.",
            generated_sql="SELECT 1",
            confidence=0.9,
            row_count=2,
            correction_attempts=1,
            intent="event_query",
            intent_confidence=0.8,
        ),
        allowed_tables=["events.events"],
    )
    assert text == "Two."
    assert ctx.data["evidence"] == [{"intent": "event_query", "row_count": 2, "corrections": 1}]
    assert ctx.data["sql"] == ["SELECT 1"]
    kwargs = pipeline.process.call_args.kwargs
    assert kwargs["event_ids"] == [7] and kwargs["user"].id == 1 and kwargs["conversation_history"][0]["content"]
    assert factory.call_args.kwargs["allowed_tables"] == ["events.events"]


def test_a_failed_query_is_text_for_the_agent():
    failure = PipelineResult(
        success=False,
        error=PipelineError(error_type=PipelineErrorType.VALIDATION_FAILED, message="m", user_message="u"),
    )
    assert query(failure)[0] == "The lookup failed: u"


def test_a_question_that_is_not_about_data_is_sent_to_the_right_tool():
    assert "propose_change" in query(PipelineResult(success=True, write_request=True))[0]
    assert "ask_guide" in query(PipelineResult(success=True, knowledge_request=True))[0]


def test_the_planners_problem_reaches_the_answer():
    with (
        patch("indico_assistant.plugin.AssistantPlugin"),
        patch("indico_assistant.services.actions.context.acting_as"),
        patch(
            "indico_assistant.services.actions.planner.plan_turn",
            return_value=PlanTurn("I could not work out what to change.", problem="not_understood"),
        ),
    ):
        reply, metadata, plan = abilities.plan(MagicMock(), "s1", "move it", [], None, None)
    assert metadata == {"plan_id": None, "cannot_plan": False, "problem": "not_understood"} and plan is None
