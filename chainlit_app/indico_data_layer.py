"""Chainlit's data layer, backed by Indico (spec 020 R4).

Conversations live only in Indico (``chat_sessions`` / ``chat_messages``). The Past Chats sidebar and
resuming read them from Indico's API; the messages Chainlit would store are already stored by the chat API,
so those writes are no-ops. Every call is made as the requesting user, so Indico checks ownership each time.

Chainlit calls the data layer without saying who asks, so the token comes from:
- HTTP routes (the sidebar): the request's Chainlit cookie, put in ``CURRENT_TOKEN`` by our middleware;
- the websocket (resume): the session's token.
The cookie holds Chainlit's session JWT, which Chainlit mints from the Indico token (same secret, same
claims) and Indico accepts (R3).
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from datetime import datetime, UTC
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
from chainlit.data.base import BaseDataLayer
from chainlit.types import Feedback, PageInfo, PaginatedResponse, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User

logger = logging.getLogger(__name__)

CURRENT_TOKEN: ContextVar[str | None] = ContextVar("indico_assistant_token", default=None)
TITLE_CHARS = 200  # chat_sessions.title
API = "/api/assistant"


def _websocket_token() -> str | None:
    try:
        from chainlit.context import context
        return context.session.token
    except Exception:  # no websocket context (e.g. an HTTP route, or during the handshake)
        return None


def _token() -> str | None:
    return CURRENT_TOKEN.get() or _websocket_token()


def _identifier(token: str) -> str:
    """Who the token belongs to (it was signed by Indico or Chainlit with the shared secret)."""
    claims = jwt.decode(token, os.environ.get("CHAINLIT_AUTH_SECRET", ""), algorithms=["HS256"])
    return str(claims.get("identifier", ""))


def indico_origin(indico_url: str = "") -> str:
    """The origin of the Indico pages that frame the panel: INDICO_ORIGIN, else that of the Indico URL the app
    calls (they differ when Chainlit reaches Indico at an internal address)."""
    parts = urlsplit(os.environ.get("INDICO_ORIGIN") or indico_url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def install_token_middleware(app, indico_url: str = "") -> None:
    """Make each HTTP request's Chainlit cookie the token the data layer calls Indico with, and let only
    Indico frame the app (the panel; anything else framing it could steer the sign-in page)."""
    from chainlit.auth.cookie import get_token_from_cookies

    ancestors = " ".join(filter(None, ["'self'", indico_origin(indico_url)]))

    @app.middleware("http")
    async def _indico_token(request, call_next):
        reset = CURRENT_TOKEN.set(get_token_from_cookies(request.cookies))
        try:
            response = await call_next(request)
        finally:
            CURRENT_TOKEN.reset(reset)
        response.headers["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
        return response


def _assistant_name() -> str:
    try:
        from chainlit.config import config
        return config.ui.name
    except Exception:
        return "Assistant"


class IndicoDataLayer(BaseDataLayer):
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), transport=transport,
                                         timeout=httpx.Timeout(10.0))

    async def _call(self, method: str, path: str, **kwargs) -> httpx.Response | None:
        """``None`` without a token (nothing is read for nobody) or when Indico is unreachable."""
        token = _token()
        if not token:
            return None
        try:
            return await self._client.request(method, API + path, headers={"X-Assistant-Auth": token}, **kwargs)
        except httpx.HTTPError:
            logger.warning("Indico unreachable for %s %s", method, path, exc_info=True)
            return None

    # --- reads ---------------------------------------------------------------------------------------

    async def get_thread(self, thread_id: str) -> ThreadDict | None:
        response = await self._call("GET", f"/sessions/{thread_id}")
        if response is None or response.status_code != 200:
            return None
        return self._thread(response.json(), _identifier(_token()), with_steps=True)

    async def get_thread_author(self, thread_id: str) -> str:
        # Indico answers 200 only to the owner, so the author is whoever asked; "" makes Chainlit refuse
        response = await self._call("GET", f"/sessions/{thread_id}")
        return _identifier(_token()) if response is not None and response.status_code == 200 else ""

    async def list_threads(self, pagination: Pagination, filters: ThreadFilter) -> PaginatedResponse[ThreadDict]:
        # filters.userId is ignored: Indico lists the caller's own sessions only
        params = {"limit": str(pagination.first)}
        if pagination.cursor:
            params["cursor"] = pagination.cursor
        if filters.search:
            params["search"] = filters.search
        response = await self._call("GET", "/sessions", params=params)
        if response is None or response.status_code != 200:
            return PaginatedResponse(pageInfo=PageInfo(hasNextPage=False, startCursor=None, endCursor=None), data=[])
        body = response.json()
        owner = _identifier(_token())
        threads = [self._thread(item, owner, with_steps=False) for item in body.get("sessions", [])]
        return PaginatedResponse(
            pageInfo=PageInfo(hasNextPage=bool(body.get("next_cursor")), startCursor=pagination.cursor,
                              endCursor=body.get("next_cursor")),
            data=threads,
        )

    @staticmethod
    def _thread(session: dict[str, Any], owner: str, with_steps: bool) -> ThreadDict:
        thread_id = str(session["session_id"])
        return {
            "id": thread_id,
            "createdAt": session.get("updated_at") or session.get("created_at"),  # grouped by last activity
            "name": session.get("title") or None,
            "userId": owner,
            "userIdentifier": owner,
            "tags": [],
            "metadata": {"started_on_event_id": session.get("event_id")},
            "steps": [IndicoDataLayer._step(m, thread_id) for m in session.get("messages", [])] if with_steps else [],
            "elements": [],
        }

    @staticmethod
    def _step(message: dict[str, Any], thread_id: str) -> dict[str, Any]:
        metadata = message.get("metadata") or {}
        output = message["content"]
        if uploads := metadata.get("uploads"):
            output += "\n\n" + "\n".join(f"📎 {u['filename']}" for u in uploads)
        user = message["role"] == "user"
        step = {
            "id": str(message["message_id"]),
            "threadId": thread_id,
            "parentId": None,
            "name": "User" if user else _assistant_name(),
            "type": "user_message" if user else "assistant_message",
            "output": output,
            "input": "",
            "createdAt": message["created_at"],
            "start": message["created_at"],
            "end": message["created_at"],
            "metadata": {},
            "streaming": False,
            "isError": False,
            "waitForAnswer": False,
        }
        if feedback := message.get("feedback"):
            step["feedback"] = {"forId": step["id"], "id": feedback["id"], "value": feedback["value"],
                                "comment": feedback.get("comment")}
        return step

    # --- writes Chainlit makes -------------------------------------------------------------------------

    async def update_thread(self, thread_id: str, name: str | None = None, user_id: str | None = None,
                            metadata: dict | None = None, tags: list[str] | None = None):
        if name is None:
            return  # metadata (Chainlit's session state) and tags are not kept
        response = await self._call("PATCH", f"/sessions/{thread_id}", json={"title": name.strip()[:TITLE_CHARS]})
        if response is not None and response.status_code == 404:
            # Chainlit names a new thread on its first message, then lists Past Chats and opens /thread/<id>,
            # all before the chat API has the session: create it now (named as its first question would name it)
            response = await self._call("PUT", f"/sessions/{thread_id}", json={"first_message": name})
        if response is not None and response.status_code not in (200, 201):
            logger.warning("Naming %s failed: %s", thread_id, response.status_code)

    async def delete_thread(self, thread_id: str):
        await self._call("DELETE", f"/sessions/{thread_id}")

    async def upsert_feedback(self, feedback: Feedback) -> str:
        return ""  # T047

    async def delete_feedback(self, feedback_id: str) -> bool:
        return False  # T047

    # --- users: built from the identifier, never stored ---------------------------------------------------

    async def get_user(self, identifier: str) -> PersistedUser | None:
        # None: users are never stored. Chainlit then calls create_user with the signed-in user, which keeps its
        # metadata (the page's event, R3); a user built here from the identifier alone would replace it.
        return None

    async def create_user(self, user: User) -> PersistedUser | None:
        return PersistedUser(id=user.identifier, identifier=user.identifier, metadata=user.metadata,
                             createdAt=datetime.now(UTC).isoformat())

    # --- no-ops: Indico already stores every message; uploads go through spec 019's endpoint -------------

    async def create_step(self, step_dict):
        pass

    async def update_step(self, step_dict):
        pass

    async def delete_step(self, step_id: str):
        pass

    async def create_element(self, element):
        pass

    async def get_element(self, thread_id: str, element_id: str):
        return None

    async def delete_element(self, element_id: str, thread_id: str | None = None):
        pass

    async def get_favorite_steps(self, user_id: str) -> list[dict]:
        return []

    async def build_debug_url(self) -> str:
        return ""

    async def close(self) -> None:
        await self._client.aclose()
