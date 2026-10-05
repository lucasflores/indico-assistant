"""A document question through the whole chat, on a real database (spec 025, T037).

POST /chat → the worker's task → the turn (Jev skipped: no key; the agent with a scripted model) → the job's answer
carries validated citations, and the session's history shows the route and what the answer touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from indico.modules.attachments.models.attachments import AttachmentFile

import indico_assistant.controllers.chat as chat_module
import indico_assistant.controllers.sessions as sessions_module
from indico_assistant.controllers.chat import RHChat, RHChatJob
from indico_assistant.controllers.sessions import RHSessionDetail
from indico_assistant.services.chat import jobs
from indico_assistant.services.llm.models import LLMResponse
from indico_assistant.services.turn import loop, tools
from indico_assistant.services.turn.citations import Citation
from indico_assistant.tasks import indexing
from indico_assistant.tasks.chat import answer_chat


class FakeCache(dict):
    def set(self, key, value, timeout=None):
        self[key] = value


class Script:
    """The model: search the documents, then answer citing p.1."""

    def __init__(self, document_id):
        self.document_id, self.n = document_id, 0

    def generate(self, prompt, response_model, **kwargs):
        self.n += 1
        if self.n == 1:
            step = response_model(call=tools.SearchDocumentsArgs(tool="search_documents", query="pile-up kinds"))
        else:
            assert "<tool_data>" in prompt and "in-time and out-of-time" in prompt
            step = response_model(
                answer=loop.Final(
                    reply="Pile-up comes in two kinds, in-time and out-of-time [p.1].",
                    citations=[Citation(document=self.document_id, page=1, quote="in-time and out-of-time")],
                )
            )
        return LLMResponse(success=True, result=step, latency_ms=1, calls=[])


@pytest.fixture
def thesis(db, dummy_user, dummy_event, create_attachment, fake_embedder):
    attachment = create_attachment(dummy_user, dummy_event, title="Thesis")
    attachment.file = AttachmentFile(user=dummy_user, filename="thesis.md", content_type="text/plain")
    attachment.file.save(b"# Thesis\nPile-up comes in two kinds: in-time and out-of-time.")
    db.session.flush()
    with patch.object(indexing, "_vector_search_enabled", return_value=True):
        assert indexing.index_attachment(attachment, embedder=fake_embedder)["status"] == "ready"
    db.session.commit()
    return attachment


def test_a_document_question_is_answered_with_citations(
    db, dummy_user, dummy_event, thesis, fake_embedder, monkeypatch
):
    monkeypatch.setattr(jobs, "_cache", FakeCache())
    request = MagicMock()
    monkeypatch.setattr(chat_module, "request", request)
    monkeypatch.setattr(sessions_module, "request", request)
    queued = []

    def rh(cls):
        controller = cls.__new__(cls)
        controller._user = dummy_user
        return controller

    from indico_assistant.default_settings import DEFAULT_SETTINGS

    plugin = MagicMock(llm_service=Script(thesis.id))  # (the plugin isn't loaded in the test app)
    plugin.settings.get_all.return_value = {**DEFAULT_SETTINGS, "jev_api_key": None}
    plugin.settings.get.side_effect = lambda key, default=None: plugin.settings.get_all.return_value.get(key, default)
    plugin.event_settings.get.return_value = None
    with (
        patch.object(answer_chat, "delay", side_effect=lambda *args: queued.append(args)),
        patch("indico_assistant.plugin.AssistantPlugin", MagicMock(instance=plugin, settings=plugin.settings)),
        patch.object(tools, "_embedder", return_value=fake_embedder),
    ):
        request.get_json.return_value = {
            "message": "What kinds of pile-up does the thesis describe?",
            "event_id": dummy_event.id,
        }
        response, status = rh(RHChat)._process()
        assert status == 202
        body = response.get_json()
        answer_chat.run(*queued[0])  # what the worker does
        request.view_args = {"job_id": body["job_id"]}
        job, status = rh(RHChatJob)._process()
        assert status == 200
        result = job.get_json()
        request.view_args = {"session_id": body["session_id"]}
        request.args = {}
        detail, _ = rh(RHSessionDetail)._process()

    assert result["response"].startswith("Pile-up comes in two kinds")
    [citation] = result["metadata"]["citations"]
    assert (citation["attachment_id"], citation["filename"], citation["page"]) == (thesis.id, "thesis.md", 1)
    assert citation["url"].endswith("#page=1")
    answer = detail.get_json()["messages"][-1]
    assert answer["metadata"]["route"]["route"] == "agent"
    assert answer["metadata"]["route"]["tools"] == ["search_documents"]
    assert answer["metadata"]["touched"] == [
        {"kind": "document", "ref": {"attachment_id": thesis.id}, "title": "thesis.md", "position": 1}
    ]


def test_the_old_search_endpoint_is_gone(app):
    assert not [rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/api/assistant/search")]
