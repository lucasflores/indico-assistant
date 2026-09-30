"""Issue reports: the JSON API (spec 021, contracts/api.md).

Feature: 021-issue-reports

Someone else's report, and one that does not exist, get the same 404, so the API never says which ids exist
(FR-014). The profile and admin pages (``report_pages.py``) call the same ``services.reports``.
"""

from __future__ import annotations

from flask import session

from indico_assistant.controllers.base import RHChatBase


class RHReportsAPI(RHChatBase):
    """Base of the report endpoints: Indico's CSRF check for requests made with the Indico session (R10).

    The assistant's API turns CSRF off because the chat panel's server calls it with a token
    (``X-Assistant-Auth``), which a malicious page cannot send. But it also accepts Indico's session cookie,
    which a same-site page could ride on: a report write carried by that cookie must bring the CSRF token.
    """

    CSRF_ENABLED = True

    def _check_csrf(self):
        if session.user is not None:  # the Indico cookie came with it (a token call carries none)
            super()._check_csrf()
