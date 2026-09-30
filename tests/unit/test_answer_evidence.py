"""What an answer records about itself when it is made (spec 021 R4, R5): the evidence and the problem flag.

Feature: 021-issue-reports
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from indico_assistant.services.actions.planner import PlanTurn
from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.nl2sql.models import PipelineError, PipelineErrorType, PipelineResult


def answer_metadata(result: PipelineResult) -> dict:
    service = ChatService(session_manager=MagicMock(), context_builder=MagicMock())
    pipeline = MagicMock()
    pipeline.process.return_value = result
    plugin = MagicMock()
    plugin.settings.get.side_effect = lambda k, default=None: False if k == "vector_search_enabled" else default
    with patch("indico_assistant.plugin.AssistantPlugin") as plugin_cls, \
            patch("indico_assistant.services.nl2sql.create_nl2sql_pipeline_from_plugin", return_value=pipeline):
        plugin_cls.instance = plugin
        return service._process_with_nl2sql(message="Q", context=[], event_id=None, user_id=1)[1]


def test_an_answer_records_its_evidence():
    metadata = answer_metadata(PipelineResult(
        success=True, answer="Two.", generated_sql="SELECT 1", confidence=0.9, row_count=2, correction_attempts=1,
        corrected=True, from_cache=False, intent="event_query", intent_confidence=0.8,
        validation_rejection="Attempt 1: forbidden keyword"))
    assert metadata["evidence"] == {"intent": "event_query", "intent_confidence": 0.8, "row_count": 2,
                                    "validation_rejection": "Attempt 1: forbidden keyword",
                                    "correction_attempts": 1, "corrected": True, "cached": False}
    assert metadata["sql_generated"] == "SELECT 1"  # (where it always was)


# --- spec 021 R4: the problem flag the chat offers a report on ------------------------------------------------

def failure(error_type):
    return PipelineResult(success=False, error=PipelineError(error_type=error_type, message='m', user_message='u'))


def test_a_good_answer_has_no_problem():
    assert 'problem' not in answer_metadata(PipelineResult(success=True, answer='Two.'))


def test_an_out_of_scope_question_and_a_failure_are_told_apart():
    assert answer_metadata(failure(PipelineErrorType.OUT_OF_SCOPE))['problem'] == 'out_of_scope'
    assert answer_metadata(failure(PipelineErrorType.VALIDATION_FAILED))['problem'] == 'failed'


def test_the_planners_problem_reaches_the_answer():
    service = ChatService(session_manager=MagicMock(), context_builder=MagicMock())
    with patch("indico_assistant.plugin.AssistantPlugin"), \
            patch("indico_assistant.services.actions.context.acting_as"), \
            patch("indico_assistant.services.actions.planner.plan_turn",
                  return_value=PlanTurn("I could not work out what to change.", problem="not_understood")):
        reply, metadata, plan = service._plan(MagicMock(), "s1", "move it", [], None)
    assert metadata == {"plan_id": None, "cannot_plan": False, "problem": "not_understood"} and plan is None
