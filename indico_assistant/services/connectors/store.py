"""The connections' tokens, encrypted at rest (spec 023, FR-008 to FR-010).

Nothing else decrypts a token. The key is a Fernet key in an environment variable, as the Teams plugin reads its own
secrets (Indico drops unknown ``indico.conf`` keys); the web server stores the tokens and the worker reads them, so
both need it.
"""

import os

KEY_ENV = "INDICO_ASSISTANT_CONNECTOR_KEY"


def fernet():
    """The tokens' Fernet, or None when the key is missing or not a Fernet key."""
    from cryptography.fernet import Fernet

    key = os.environ.get(KEY_ENV, "").strip()
    try:
        return Fernet(key) if key else None
    except ValueError:
        return None
