"""Integration smoke test for the chat wiring: POST /chat → Celery task → GET /chat/jobs/<id>.

Feature: 010-chat-pipeline-integration (queued since the scalability audit, Phase 1)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import indico_assistant.controllers.chat as chat_module
from indico_assistant.controllers.chat import RHChat, RHChatJob
from indico_assistant.services.chat import jobs
from indico_assistant.services.chat.service import ChatService
from indico_assistant.services.turn.answer import Outcome
from indico_assistant.tasks.chat import answer_chat


class FakeCache(dict):
    def set(self, key, value, timeout=None):
        self[key] = value


def test_chat_round_trip(monkeypatch):
    user = MagicMock(id=321, is_admin=False)
    session = MagicMock(id=uuid4(), event_id=None)
    manager = MagicMock()
    manager.create_session.return_value = manager.get_session.return_value = session
    manager.add_assistant_message.return_value = MagicMock(id=uuid4())
    manager.page_event_of.side_effect = lambda message_id, fallback: fallback  # (spec 020: the question's page)
    manager.offer_before.return_value = None  # (spec 022: no answer offered a change)
    service = ChatService(session_manager=manager, context_builder=MagicMock())
    monkeypatch.setattr(jobs, '_cache', FakeCache())
    request = MagicMock()
    monkeypatch.setattr(chat_module, 'request', request)

    def rh(cls):
        controller = cls.__new__(cls)
        controller._user = user
        return controller

    queued = []
    with patch('indico_assistant.controllers.chat.get_chat_service', return_value=service), \
            patch('indico_assistant.services.chat.get_chat_service', return_value=service), \
            patch.object(answer_chat, 'delay', side_effect=lambda *args: queued.append(args)), \
            patch.object(service, '_load_user', return_value=user), \
            patch('indico_assistant.services.turn.answer.answer',
                  return_value=Outcome("Hello from pipeline", {}, "agent")), \
            patch('indico_assistant.services.turn.answer.disabled_for', return_value=False), \
            patch('indico_assistant.services.actions.executor.open_plan', return_value=None), \
            patch('indico_assistant.services.chat.service.db'):
        request.get_json.return_value = {"message": "Hello"}
        response, status = rh(RHChat)._process()
        assert status == 202
        job_id = response.get_json()['job_id']

        request.view_args = {'job_id': job_id}
        assert rh(RHChatJob)._process()[1] == 202  # not answered yet

        answer_chat.run(*queued[0])  # what the worker does
        response, status = rh(RHChatJob)._process()

    assert status == 200
    assert response.get_json()['response'] == "Hello from pipeline"
