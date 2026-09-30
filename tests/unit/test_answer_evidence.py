"""What an answer records about itself when it is made (spec 021 R4, R5): the evidence and the problem flag.

Feature: 021-issue-reports
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.nl2sql.models import PipelineResult


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
