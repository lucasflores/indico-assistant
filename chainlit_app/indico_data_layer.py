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
_RENAME = object()  # update_thread without user_id: the sidebar's rename
API = "/api/assistant"


def _websocket_token() -> str | None:
    try:
        from chainlit.context import context
        return context.session.token
    except Exception:  # no websocket context (e.g. an HTTP route, or during the handshake)
        return None


def _token() -> str | None:
    return CURRENT_TOKEN.get() or _websocket_token()


def _chainlit_session():
    try:
        from chainlit.context import context
        return context.session
    except Exception:
        return None


# Chainlit also starts a thread on a new chat's first *action*, named after it (server.py call_action). The report
# form's Send and Cancel can be that first action (spec 021): they are no conversation, so none is created or named.
NOT_CONVERSATIONS = frozenset({"report_submit", "report_cancel"})


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
        # Indico answers 200 only to the owner, so the author is whoever asked; "" makes Chainlit refuse. (Without
        # its messages: get_thread reads them next. Review, PR #5: a page load read the conversation 4 times.)
        response = await self._call("GET", f"/sessions/{thread_id}", params={"messages": "0"})
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
            # the job of a question still unanswered when this was read: resume shows its answer even if it lands
            # before the resume's own look (Copilot review, PR #5)
            "metadata": {"started_on_event_id": session.get("event_id"),
                         "pending_job_id": session.get("pending_job_id"),
                         "waiting_plan_id": session.get("waiting_plan_id")},
            "steps": IndicoDataLayer._steps(session.get("messages", []), thread_id) if with_steps else [],
            "elements": [],
        }

    @staticmethod
    def _steps(messages: list[dict[str, Any]], thread_id: str) -> list[dict[str, Any]]:
        """Each answer in a run, as Chainlit draws a live one: the thumbs belong to the run, so its id is the
        answer's Indico id (a live answer is stored under its run's id, sent as answer_id)."""
        steps, question = [], None
        for message in messages:
            step = IndicoDataLayer._step(message, thread_id)
            if step["type"] == "user_message":
                question = step
                steps.append(step)
                continue
            run = {**step, "type": "run", "name": "on_message", "parentId": question and question["id"],
                   "input": question["output"] if question else "", "output": ""}
            step.pop("feedback", None)
            steps += [run, {**step, "id": f"{step['id']}:answer", "parentId": run["id"]}]
        return steps

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

    async def update_thread(self, thread_id: str, name: str | None = None, user_id: object = _RENAME,
                            metadata: dict | None = None, tags: list[str] | None = None):
        if name is None:
            return  # metadata (Chainlit's session state) and tags are not kept
        if user_id is not _RENAME and name in NOT_CONVERSATIONS:
            if session := _chainlit_session():
                session.has_first_interaction = False  # the chat's first real message still starts the conversation
            return
        if user_id is not _RENAME:
            # Chainlit's own naming of a new thread by its first message (emitter.flush_thread_queues passes
            # user_id; the sidebar's rename does not). Not a rename: the title stays the question's start. It
            # comes before the chat API has the session, and Chainlit then lists Past Chats and opens
            # /thread/<id>: make sure Indico has it.
            response = await self._call("PUT", f"/sessions/{thread_id}", json={"first_message": name})
        else:
            response = await self._call("PATCH", f"/sessions/{thread_id}", json={"title": name.strip()[:TITLE_CHARS]})
        if response is None or response.status_code not in (200, 201):
            # raised: the sidebar then says the rename failed instead of showing one a reload undoes (Chainlit's
            # own naming catches it)
            raise RuntimeError(f"Naming {thread_id} not saved: {getattr(response, 'status_code', None)}")

    async def delete_thread(self, thread_id: str):
        response = await self._call("DELETE", f"/sessions/{thread_id}")
        if response is None or response.status_code >= 300:
            raise RuntimeError(f"Deleting {thread_id} failed: {getattr(response, 'status_code', None)}")

    async def upsert_feedback(self, feedback: Feedback) -> str:
        # the thumb is the vote (its id is what Chainlit deletes later); its comment goes with it in the same
        # request, so Indico keeps both or neither (review, PR #5)
        body = {"message_id": feedback.forId, "feedback_type": "thumbs_up" if feedback.value else "thumbs_down",
                "value": True}
        if feedback.comment and feedback.comment.strip():
            body["comment"] = feedback.comment.strip()
        response = await self._call("POST", "/feedback", json=body)
        if response is None or response.status_code != 201:
            # raised, so Chainlit tells the user it failed instead of showing a vote that was not kept
            raise RuntimeError(f"Feedback on {feedback.forId} not saved: {getattr(response, 'status_code', None)}")
        return response.json()["feedback_id"]

    async def delete_feedback(self, feedback_id: str) -> bool:
        response = await self._call("DELETE", f"/feedback/{feedback_id}")
        return response is not None and response.status_code == 204

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
