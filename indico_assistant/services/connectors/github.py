"""GitHub, read with the user's own token (spec 023): the client, its OAuth calls, and the read tools."""

#: The one fixed callback of the instance's GitHub App (registered there; outside the profile's per-user URLs).
CALLBACK_PATH = "/assistant/github/callback"


def callback_url():
    from indico.core.config import config

    return config.BASE_URL.rstrip("/") + CALLBACK_PATH
