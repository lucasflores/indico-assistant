"""Minimal Chainlit app for Indico Assistant widget.

- Auth: validates JWT from Indico plugin using CHAINLIT_AUTH_SECRET.
- Message handler: simple echo placeholder (replace with real LLM logic).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
import asyncio
import chainlit as cl
import httpx
import jwt

CHAINLIT_AUTH_SECRET = os.environ.get("CHAINLIT_AUTH_SECRET", "")

logger = logging.getLogger(__name__)


def _load_env_file() -> dict[str, str]:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return {}
    values: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def _get_indico_api_url() -> str:
    env_url = os.environ.get("INDICO_API_URL")
    if env_url:
        return env_url.rstrip("/")

    env_values = _load_env_file()
    return env_values.get("INDICO_API_URL", "").rstrip("/")


def _get_auth_token() -> str | None:
    user = getattr(cl, "user", None)
    if user is None:
        user = getattr(getattr(cl, "context", None), "current_user", None)

    if user and getattr(user, "metadata", None):
        token = user.metadata.get("auth_token")
        if token:
            cl.user_session.set("auth_token", token)
            return token
        if CHAINLIT_AUTH_SECRET:
            payload = {
                "identifier": getattr(user, "identifier", "unknown"),
                "metadata": {
                    "name": user.metadata.get("name", ""),
                    "email": user.metadata.get("email", ""),
                },
                "exp": datetime.now(timezone.utc) + timedelta(hours=24),
                "iat": datetime.now(timezone.utc),
            }
            token = jwt.encode(payload, CHAINLIT_AUTH_SECRET, algorithm="HS256")
            cl.user_session.set("auth_token", token)
            return token

    token = cl.user_session.get("auth_token")
    if token:
        return token

    try:
        context = getattr(cl, "context", None)
        session = getattr(context, "session", None)
        if session is not None and getattr(session, "token", None):
            token = session.token
            cl.user_session.set("auth_token", token)
            return token
    except Exception:
        logger.debug("Unable to extract auth token from Chainlit session", exc_info=True)

    try:
        context = getattr(cl, "context", None)
        if context is not None:
            cookies = getattr(context, "cookies", None)
            if cookies and isinstance(cookies, dict) and cookies.get("access_token"):
                token = cookies.get("access_token")
                cl.user_session.set("auth_token", token)
                return token

        request = getattr(context, "current_request", None)
        if request and getattr(request, "headers", None):
            auth_header = request.headers.get("Authorization") or request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.removeprefix("Bearer ")
                cl.user_session.set("auth_token", token)
                return token
            cookie_header = request.headers.get("Cookie") or request.headers.get("cookie", "")
            if cookie_header:
                for part in cookie_header.split(";"):
                    name, _, value = part.strip().partition("=")
                    if name == "access_token" and value:
                        cl.user_session.set("auth_token", value)
                        return value
    except Exception:
        logger.debug("Unable to extract auth token from current request", exc_info=True)

    return None


_http_clients: dict[str, httpx.AsyncClient] = {}

# Indico answers in a Celery worker (up to ~2.5 min); we poll for the reply meanwhile.
POLL_INTERVAL = 1.0
ANSWER_TIMEOUT = 180.0


async def _get_http_client(base_url: str) -> httpx.AsyncClient:
    # One pooled client per Indico URL for the whole process (not one per chat session, never closed).
    if base_url not in _http_clients:
        _http_clients[base_url] = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(15.0))
    return _http_clients[base_url]


async def _wait_for_answer(client: httpx.AsyncClient, job_id: str, auth_token: str) -> httpx.Response:
    """Poll the queued answer until it is ready, failed, or ANSWER_TIMEOUT passes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ANSWER_TIMEOUT
    while True:
        response = await client.get(
            f"/api/assistant/chat/jobs/{job_id}", headers={"X-Assistant-Auth": auth_token}
        )
        if response.status_code == 429 and loop.time() < deadline:  # polling too fast: the answer still comes
            await asyncio.sleep(float(response.headers.get("Retry-After", POLL_INTERVAL)))
            continue
        if response.status_code != 202 or loop.time() > deadline:
            return response
        await asyncio.sleep(POLL_INTERVAL)


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("indico_session_id", None)
    
    # Store event_id from user metadata in session for easy access
    # User object is returned by header_auth_callback
    user = cl.user_session.get("user")
    
    if user and isinstance(user, cl.User) and hasattr(user, "metadata"):
        event_id = user.metadata.get("event_id")
        if event_id:
            cl.user_session.set("indico_event_id", event_id)
    
    _get_auth_token()


@cl.header_auth_callback
def header_auth_callback(headers: dict) -> cl.User | None:
    """Authenticate users via JWT passed from the Indico plugin.

    Expects Authorization: Bearer <token> and validates with CHAINLIT_AUTH_SECRET.
    Returns a cl.User so Chainlit associates sessions with the Indico user.
    """

    auth_header = headers.get("Authorization") or headers.get("authorization", "")
    cookie_header = headers.get("Cookie") or headers.get("cookie", "")
    
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
    elif cookie_header:
        for part in cookie_header.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "access_token" and value:
                token = value
                break
    if not token:
        logger.info("Authorization token missing in headers")
        return None

    if not CHAINLIT_AUTH_SECRET:
        # Dev fallback: accept tokens but mark unauthenticated
        cl.user_session.set("auth_token", token)
        return cl.User(
            identifier="anonymous",
            metadata={
                "authenticated": False,
                "source": "indico",
                "auth_token": token,
                "event_id": None,
            },
        )

    try:
        payload = jwt.decode(token, CHAINLIT_AUTH_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    identifier = payload.get("identifier", "unknown")
    meta = payload.get("metadata", {}) or {}

    # Extract event_id from JWT metadata (Feature 013: event context)
    event_id = meta.get("event_id")

    cl.user_session.set("auth_token", token)
    user = cl.User(
        identifier=identifier,
        metadata={
            "name": meta.get("name", ""),
            "email": meta.get("email", ""),
            "authenticated": True,
            "source": "indico",
            "auth_token": token,
            "event_id": event_id,
        },
    )
    return user

@cl.set_starters
async def starters():
    return [
        cl.Starter(
            label="Monday week starter refresh",
            message="Summarize the previous week's meetings and tasks, and provide a list of potential priorities for the week ahead.",
            icon="/public/weather-color-sun-cloud-svgrepo-com.svg",
            ),
        cl.Starter(
            label="Upcoming meetings",
            message="Detail any upcoming meetings from now until the end of the work week, and provide a summary of the agenda for each meeting.",
            icon="/public/crystal-ball-svgrepo-com.svg",
            )
    ]


@cl.on_message
async def on_message(message: cl.Message):
    """Forward message to Indico assistant API and return response."""
    await _ask(message.content, files=[e for e in (message.elements or []) if getattr(e, "path", None)])


async def _upload(client: httpx.AsyncClient, auth_token: str, element) -> str:
    """Hand a file sent in the chat to Indico (Chainlit deletes its own copy when the session ends)."""
    with open(element.path, "rb") as data:
        response = await client.post(
            "/api/assistant/chat/uploads",
            files={"file": (element.name, data, getattr(element, "mime", None) or "application/octet-stream")},
            data={"session_id": cl.user_session.get("indico_session_id") or ""},
            headers={"X-Assistant-Auth": auth_token},
        )
    if response.status_code != 201:
        try:
            reason = response.json().get("message")
        except Exception:
            reason = None
        raise ValueError(f"{element.name} was not accepted: {reason or 'upload failed'}")
    return response.json()["uuid"]


async def _ask(text: str, files=()):
    """Send ``text`` to the Indico assistant as the user's next message and show the answer."""
    indico_api_url = _get_indico_api_url()
    if not indico_api_url:
        await cl.Message(
            content=(
                "Indico API URL is not configured. Set INDICO_API_URL in your "
                "environment or chainlit_app/.env and restart Chainlit."
            )
        ).send()
        return

    auth_token = _get_auth_token()
    token_prefix = f"{auth_token[:8]}..." if auth_token else None
    logger.info("Auth token available for request=%s prefix=%s", bool(auth_token), token_prefix)
    if not auth_token:
        await cl.Message(
            content="Authentication token missing. Please re-authenticate."
        ).send()
        return

    # Feature 017: Create loading message to show processing state
    # Create message but don't set content yet - this should show loading
    loading_msg = cl.Message(content="")
    
    client = await _get_http_client(indico_api_url)
    payload: dict[str, object] = {"message": text}
    if files:
        try:
            payload["uploads"] = [await _upload(client, auth_token, element) for element in files]
        except (ValueError, httpx.RequestError) as exc:
            loading_msg.content = str(exc) if isinstance(exc, ValueError) else "The file could not be uploaded."
            await loading_msg.send()
            return
    session_id = cl.user_session.get("indico_session_id")
    if session_id:
        payload["session_id"] = session_id
    
    # Get event_id from user session (extracted during auth from Referer header)
    # Feature 013: Event context for scoped queries
    event_id = cl.user_session.get("indico_event_id")
    if event_id:
        payload["event_id"] = event_id

    logger.info(
        "Sending request to Indico assistant API",
        extra={"url": f"{indico_api_url}/api/assistant/chat", "has_event_id": bool(event_id)}
    )
    try:
        response = await client.post(
            "/api/assistant/chat",
            json=payload,
            headers={"X-Assistant-Auth": auth_token},
        )
        if response.status_code == 202:
            queued = response.json()
            cl.user_session.set("indico_session_id", queued.get("session_id"))
            response = await _wait_for_answer(client, queued["job_id"], auth_token)
            if response.status_code == 202:
                loading_msg.content = "The assistant is taking too long to answer. Please try again."
                await loading_msg.send()
                return
    except httpx.RequestError:
        logger.exception("Failed to reach Indico assistant API")
        loading_msg.content = "Unable to reach the assistant service. Please try again later."
        await loading_msg.send()
        return

    logger.info(
        "Received response from Indico assistant API",
        extra={"status_code": response.status_code}
    )

    if response.status_code == 401:
        logger.info("Indico auth error response: %s", response.text)
        loading_msg.content = "Authentication failed. Please sign in again."
        await loading_msg.send()
        return
    if response.status_code == 403:
        loading_msg.content = "You do not have permission to access this resource."
        await loading_msg.send()
        return
    if response.status_code in (400, 422):
        logger.info("Indico validation error response: %s", response.text)
        loading_msg.content = "Your request could not be validated. Please rephrase and try again."
        await loading_msg.send()
        return
    if response.status_code >= 500:
        logger.info("Indico server error response: %s", response.text)
        error_message = "The assistant encountered an error. Please try again shortly."
        try:
            error_payload = response.json()
            if isinstance(error_payload, dict):
                detail = error_payload.get("details")
                message = error_payload.get("message")
                if detail or message:
                    detail_text = detail if isinstance(detail, str) else None
                    error_message = " ".join(
                        part for part in [message, detail_text] if part
                    )
        except Exception:
            pass

        loading_msg.content = error_message
        await loading_msg.send()
        return
    if response.status_code >= 400:
        logger.info("Indico error response: %s", response.text)
        loading_msg.content = "The assistant could not process your request. Please try again."
        await loading_msg.send()
        return
    data = response.json()
    new_session_id = data.get("session_id")
    if new_session_id:
        cl.user_session.set("indico_session_id", new_session_id)
    reply = data.get("response") or "No response returned from assistant."
    metadata = data.get("metadata") or {}
    
    # Debug mode: show SQL and metadata
    if os.environ.get("CHAINLIT_DEBUG_SQL") == "1":
        sql_generated = metadata.get("sql_generated")
        confidence = metadata.get("confidence")
        data_sources = metadata.get("data_sources")
        debug_lines = []
        if sql_generated:
            debug_lines.append(f"SQL: {sql_generated}")
        if confidence is not None:
            debug_lines.append(f"Confidence: {confidence}")
        if data_sources:
            # Feature 015: Handle new dict format for citations
            if isinstance(data_sources, list) and len(data_sources) > 0:
                if isinstance(data_sources[0], dict):
                    # New format: list of citation dicts
                    source_descriptions = [s.get('description', s.get('url', 'source')) for s in data_sources]
                    debug_lines.append(f"Sources: {', '.join(source_descriptions)}")
                else:
                    # Old format: list of strings (table names)
                    debug_lines.append(f"Sources: {', '.join(data_sources)}")
        if debug_lines:
            reply = f"{reply}\n\n" + "\n".join(debug_lines)
    
    # Append follow-up suggestions to the main response if available
    suggested_followups = metadata.get("suggested_followups", [])
    if suggested_followups:
        # Format as a natural continuation with active, helpful tone
        followup_text = "\n\n---\n\nI could also help with:\n" + "\n".join(
            f"- {suggestion}" for suggestion in suggested_followups
        )
        followup_text += "\n\nJust say the word!"
        reply += followup_text
    
    plan = data.get("plan")
    if plan:
        card, actions = render_plan(plan)
        loading_msg.content = f"{reply}\n\n{card}" if reply else card
        loading_msg.actions = actions
        await _forget_plan_buttons()  # only the latest plan can be confirmed
        await loading_msg.send()
        cl.user_session.set("plan_message", loading_msg)
        cl.user_session.set("plan_id", plan["id"])
        return

    loading_msg.content = reply
    await loading_msg.send()
    await _drop_stale_plan_buttons(client, auth_token)


# --- Chat actions (Feature 019): the plan card and its buttons ------------------------------------------


def render_plan(plan: dict) -> tuple[str, list[cl.Action]]:
    """The plan as the user confirms it (contracts/api.md), and its buttons."""
    lines = [f"**{plan['summary']}**", ""]
    for step in plan.get("steps", []):
        lines.append(f"{step['n']}. {step['description']}")
        lines.extend(f"    - {effect}" for effect in step.get("side_effects", []))
    actions: list[cl.Action] = []
    for question in plan.get("questions", []):
        lines += ["", f"**{question['text']}**"]
        for choice in question.get("choices", []):
            note = f" ({choice['note']})" if choice.get("note") else ""
            lines.append(f"- {choice['label']}{note}")
            actions.append(cl.Action(name="plan_choice", label=choice["label"], payload={"text": choice["label"]}))
    for suggestion in plan.get("suggestions", []):
        lines += ["", f"Suggestion ({suggestion['source']['label']}): {suggestion['content']}"]
        actions.append(cl.Action(name="plan_choice", label=f"Add: {suggestion['kind']}",
                                 payload={"text": f"add suggestion {suggestion['id']}"}))
    if plan.get("can_confirm"):
        actions.append(cl.Action(name="confirm_plan", label="Confirm", icon="check",
                                 payload={"plan_id": plan["id"], "token": plan.get("token")}))
    actions.append(cl.Action(name="cancel_plan", label="Cancel", icon="x", payload={"plan_id": plan["id"]}))
    return "\n".join(lines), actions


async def _drop_stale_plan_buttons(client: httpx.AsyncClient, auth_token: str):
    """A plan answered in words ("yes", "cancel") keeps no buttons that could only fail now."""
    plan_id = cl.user_session.get("plan_id")
    if not plan_id or cl.user_session.get("plan_message") is None:
        return
    try:
        response = await client.get(f"/api/assistant/plans/{plan_id}", headers={"X-Assistant-Auth": auth_token})
    except httpx.RequestError:
        return
    if response.status_code != 200 or response.json().get("status") != "shown":
        await _forget_plan_buttons()


async def _forget_plan_buttons():
    previous = cl.user_session.get("plan_message")
    if previous is not None:
        await previous.remove_actions()
        cl.user_session.set("plan_message", None)


async def _plan_call(path: str, body: dict | None = None) -> httpx.Response | None:
    indico_api_url, auth_token = _get_indico_api_url(), _get_auth_token()
    if not indico_api_url or not auth_token:
        await cl.Message(content="Authentication token missing. Please re-authenticate.").send()
        return None
    client = await _get_http_client(indico_api_url)
    try:
        response = await client.post(path, json=body or {}, headers={"X-Assistant-Auth": auth_token})
        if response.status_code == 202:  # confirmed: wait for the worker to carry it out
            response = await _wait_for_answer(client, response.json()["job_id"], auth_token)
    except httpx.RequestError:
        logger.exception("Failed to reach Indico assistant API")
        await cl.Message(content="Unable to reach the assistant service. Please try again later.").send()
        return None
    return response


def _plan_outcome(response: httpx.Response) -> str:
    if response.status_code == 200:
        return response.json().get("response") or "Done."
    if response.status_code == 202:
        return "This is taking longer than expected; the result will appear in the event shortly."
    if response.status_code == 409:
        return "This plan changed or expired, so nothing was done. Ask again for a new plan."
    if response.status_code == 403:
        return response.json().get("message") or "You cannot confirm this plan."
    return "The assistant encountered an error. Nothing was changed; please try again."


@cl.action_callback("confirm_plan")
async def on_confirm_plan(action: cl.Action):
    await _forget_plan_buttons()
    response = await _plan_call(f"/api/assistant/plans/{action.payload['plan_id']}/confirm",
                                {"token": action.payload.get("token")})
    if response is not None:
        await cl.Message(content=_plan_outcome(response)).send()


@cl.action_callback("cancel_plan")
async def on_cancel_plan(action: cl.Action):
    await _forget_plan_buttons()
    response = await _plan_call(f"/api/assistant/plans/{action.payload['plan_id']}/cancel")
    if response is not None:
        text = "Cancelled; nothing was changed." if response.status_code == 200 else _plan_outcome(response)
        await cl.Message(content=text).send()


@cl.action_callback("plan_choice")
async def on_plan_choice(action: cl.Action):
    """A choice or suggestion button answers the plan as if the user had typed it."""
    await cl.Message(content=action.payload["text"], type="user_message").send()
    await _ask(action.payload["text"])


if __name__ == "__main__":
    # Allows `python app_chnlit.py` during quick tests
    cl.run()
