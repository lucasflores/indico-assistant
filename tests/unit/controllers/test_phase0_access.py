"""Phase 0 security: every assistant endpoint needs a user; /health never spends LLM money for the public."""

from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Unauthorized

from indico_assistant.controllers.base import RHAssistantBase
from indico_assistant.controllers.health import RHHealth


def _rh(cls):
    rh = cls.__new__(cls)
    rh._user = None
    return rh


def test_anonymous_request_is_refused():
    rh = _rh(RHAssistantBase)
    with patch("indico_assistant.controllers.base.session", MagicMock(user=None)), \
            patch.object(RHAssistantBase, "_get_user_from_bearer_token", return_value=None), \
            patch("indico_assistant.controllers.base.request", MagicMock(headers={})):
        with pytest.raises(Unauthorized):
            rh._check_access()


def test_token_user_is_accepted():
    rh = _rh(RHAssistantBase)
    user = MagicMock(is_admin=False)
    with patch("indico_assistant.controllers.base.session", MagicMock(user=None)), \
            patch.object(RHAssistantBase, "_get_user_from_bearer_token", return_value=user), \
            patch("indico_assistant.controllers.base.request", MagicMock(headers={})):
        rh._check_access()
    assert rh._user is user


@pytest.mark.parametrize("user", [None, MagicMock(is_admin=False)])
def test_health_is_free_for_non_admins(user):
    plugin = MagicMock()
    plugin.settings.get.side_effect = {"llm_provider": "openai", "llm_model": "m", "enabled": True}.get
    with patch("flask.session", MagicMock(user=user)):
        info = RHHealth.__new__(RHHealth)._check_llm_status(plugin)
    assert info == {"status": "configured", "provider": "openai", "model": "m"}
    plugin.llm_service.health_check.assert_not_called()


def test_health_live_check_for_admins():
    plugin = MagicMock()
    plugin.settings.get.side_effect = {"llm_provider": "openai", "llm_model": "m"}.get
    plugin.llm_service.health_check.return_value = MagicMock(status="connected", latency_ms=5, error=None,
                                                             provider="openai", model="m")
    with patch("flask.session", MagicMock(user=MagicMock(is_admin=True))):
        RHHealth.__new__(RHHealth)._check_llm_status(plugin)
    plugin.llm_service.health_check.assert_called_once()


def test_every_response_is_private_and_uncached():
    from flask import Response
    from indico.web.rh import RH
    from indico_assistant.controllers.base import RHAssistantBase
    with patch.object(RH, 'process', return_value=Response('{}')):
        response = RHAssistantBase.process(RHAssistantBase.__new__(RHAssistantBase))
    assert response.headers['Cache-Control'] == 'private, no-store'
