"""Minimal Chainlit app for Indico Assistant widget.

- Auth: validates JWT from Indico plugin using CHAINLIT_AUTH_SECRET.
- Message handler: simple echo placeholder (replace with real LLM logic).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
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


async def _get_http_client(base_url: str) -> httpx.AsyncClient:
    client = cl.user_session.get("indico_http_client")
    current_base_url = cl.user_session.get("indico_api_base_url")
    if client is None or current_base_url != base_url:
        client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0)
        )
        cl.user_session.set("indico_http_client", client)
        cl.user_session.set("indico_api_base_url", base_url)
    return client


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("indico_session_id", None)
    _get_auth_token()


@cl.header_auth_callback
def header_auth_callback(headers: dict) -> cl.User | None:
    """Authenticate users via JWT passed from the Indico plugin.

    Expects Authorization: Bearer <token> and validates with CHAINLIT_AUTH_SECRET.
    Returns a cl.User so Chainlit associates sessions with the Indico user.
    """

    auth_header = headers.get("Authorization") or headers.get("authorization", "")
    cookie_header = headers.get("Cookie") or headers.get("cookie", "")
    logger.info(
        "Auth callback headers received (has_authorization=%s, has_cookie=%s, header_keys=%s)",
        bool(auth_header),
        bool(cookie_header),
        list(headers.keys()),
    )
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

    cl.user_session.set("auth_token", token)
    user = cl.User(
        identifier=identifier,
        metadata={
            "name": meta.get("name", ""),
            "email": meta.get("email", ""),
            "authenticated": True,
            "source": "indico",
            "auth_token": token,
        },
    )
    return user


@cl.on_message
async def on_message(message: cl.Message):
    """Forward message to Indico assistant API and return response."""
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

    client = await _get_http_client(indico_api_url)
    payload: dict[str, object] = {"message": message.content}
    session_id = cl.user_session.get("indico_session_id")
    if session_id:
        payload["session_id"] = session_id

    logger.info(
        "Sending request to Indico assistant API",
        extra={"url": f"{indico_api_url}/api/assistant/chat"}
    )
    try:
        response = await client.post(
            "/api/assistant/chat",
            json=payload,
            headers={"X-Assistant-Auth": auth_token},
        )
    except httpx.RequestError:
        logger.exception("Failed to reach Indico assistant API")
        await cl.Message(
            content="Unable to reach the assistant service. Please try again later."
        ).send()
        return

    logger.info(
        "Received response from Indico assistant API",
        extra={"status_code": response.status_code}
    )

    if response.status_code == 401:
        logger.info("Indico auth error response: %s", response.text)
        await cl.Message(
            content="Authentication failed. Please sign in again."
        ).send()
        return
    if response.status_code == 403:
        await cl.Message(
            content="You do not have permission to access this resource."
        ).send()
        return
    if response.status_code in (400, 422):
        logger.info("Indico validation error response: %s", response.text)
        await cl.Message(
            content="Your request could not be validated. Please rephrase and try again."
        ).send()
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

        await cl.Message(content=error_message).send()
        return
    if response.status_code >= 400:
        logger.info("Indico error response: %s", response.text)
        await cl.Message(
            content="The assistant could not process your request. Please try again."
        ).send()
        return
    data = response.json()
    new_session_id = data.get("session_id")
    if new_session_id:
        cl.user_session.set("indico_session_id", new_session_id)
    reply = data.get("response") or "No response returned from assistant."
    if os.environ.get("CHAINLIT_DEBUG_SQL"):
        metadata = data.get("metadata") or {}
        sql_generated = metadata.get("sql_generated")
        confidence = metadata.get("confidence")
        data_sources = metadata.get("data_sources")
        debug_lines = []
        if sql_generated:
            debug_lines.append(f"SQL: {sql_generated}")
        if confidence is not None:
            debug_lines.append(f"Confidence: {confidence}")
        if data_sources:
            debug_lines.append(f"Sources: {', '.join(data_sources)}")
        if debug_lines:
            reply = f"{reply}\n\n" + "\n".join(debug_lines)
    await cl.Message(content=reply).send()


if __name__ == "__main__":
    # Allows `python app_chnlit.py` during quick tests
    cl.run()
