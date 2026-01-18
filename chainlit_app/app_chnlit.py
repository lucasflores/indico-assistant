"""Minimal Chainlit app for Indico Assistant widget.

- Auth: validates JWT from Indico plugin using CHAINLIT_AUTH_SECRET.
- Message handler: simple echo placeholder (replace with real LLM logic).
"""

from __future__ import annotations

import os
import chainlit as cl
import jwt

CHAINLIT_AUTH_SECRET = os.environ.get("CHAINLIT_AUTH_SECRET", "")


@cl.header_auth_callback
def header_auth_callback(headers: dict) -> cl.User | None:
    """Authenticate users via JWT passed from the Indico plugin.

    Expects Authorization: Bearer <token> and validates with CHAINLIT_AUTH_SECRET.
    Returns a cl.User so Chainlit associates sessions with the Indico user.
    """

    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ")

    if not CHAINLIT_AUTH_SECRET:
        # Dev fallback: accept tokens but mark unauthenticated
        return cl.User(identifier="anonymous", metadata={"authenticated": False})

    try:
        payload = jwt.decode(token, CHAINLIT_AUTH_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    identifier = payload.get("identifier", "unknown")
    meta = payload.get("metadata", {}) or {}

    user = cl.User(
        identifier=identifier,
        metadata={
            "name": meta.get("name", ""),
            "email": meta.get("email", ""),
            "authenticated": True,
            "source": "indico",
        },
    )
    return user


@cl.on_message
async def on_message(message: cl.Message):
    """Placeholder chat handler; replace with real assistant logic."""
    reply = f"Echo: {message.content}"
    await cl.Message(content=reply).send()


if __name__ == "__main__":
    # Allows `python app_chnlit.py` during quick tests
    cl.run()
