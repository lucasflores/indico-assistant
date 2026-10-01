"""What the assistant can do for one user, built for each question (spec 022, FR-008 to FR-010).

Never hand-written: the registered actions, the admin's enabled actions, the installed plugins (through each action's
``available``) and the user's rights. With an event page, the changes are the ones possible on that event; without
one, the ones the chat can reach (the meetings it finds by name, the categories it offers).
"""

import re
from dataclasses import dataclass

#: What the chat answers from Indico's data (the NL2SQL route), in the user's words.
ANSWERS = ("events and meetings (dates, places, descriptions, minutes and notes)", "talks and their speakers",
           "sessions and timetables", "registrations and participants", "attached files, and what the slides and "
           "papers the user can see say", "searching a topic across everything the user can see")
#: What it never does itself, for anyone (FR-010): these are handed off with a link to the page.
NEVER = ("register people", "take payments", "send an email of its own (the reminder emails and Teams invitations its "
         "changes cause are shown in the plan)", "change permissions or protection", "delete events (other than "
         "undoing its own changes)", "book rooms", "review abstracts")
OFF = "switched off by the administrator"
ANYWHERE = "any category (they are an Indico administrator)"


@dataclass
class CapabilityList:
    user_name: str
    is_admin: bool
    data_questions: bool
    create_in: list
    propose_in: list
    can: list  # action summaries
    cannot: list  # (action summary, reason)
    event: dict | None  # {id, title, type, manages, locked}
    changes_enabled: bool
    github: str | None = None  # spec 023: None while GitHub is off; else their login, or "" when not connected
    github_renew: bool = False  # their connection needs renewing (GitHub refused it)

    def render(self):
        lines = [f"You are talking to {self.user_name}{' (an Indico administrator)' if self.is_admin else ''}."]
        if self.data_questions:
            lines.append("I answer questions about: " + "; ".join(ANSWERS) + " (only what this user may see).")
        else:
            lines.append("It cannot answer questions about event data on this Indico (switched off).")
        if self.event:
            e = self.event
            lines.append(f"The page they are on: the {e['type']} “{e['title']}” (/event/{e['id']}/). "
                         + ("They manage it." if e["manages"] else "They do NOT manage it: only its managers can "
                            "change it; do not name them.")
                         + (" It is locked: nothing in it can be changed." if e["locked"] else ""))
        if not self.changes_enabled:
            lines.append("It cannot change anything in Indico here: the administrator has switched changes off.")
        else:
            if self.create_in:
                lines.append("They can create meetings in: " + "; ".join(self.create_in) + ".")
            if self.propose_in:
                lines.append("They can propose meetings (for approval) in: " + "; ".join(self.propose_in) + ".")
            lines.append("Changes I can make for them, each shown as a plan they confirm: "
                         + ("; ".join(self.can) or "none") + ".")
            by_reason = {}
            for what, why in self.cannot:
                by_reason.setdefault(why, []).append(what)
            lines += [f"Changes I cannot make for them ({_about_them(why)}): " + "; ".join(whats) + "."
                      for why, whats in by_reason.items()]
        if self.github is None:
            lines.append("Never, for anyone: " + "; ".join(NEVER) + ". It has no access to GitHub, email inboxes or "
                         "calendars outside Indico.")
        else:
            lines.append("It can read their GitHub, read-only (their pull requests, the reviews waiting for them, "
                         "issues assigned to them, their repositories): "
                         + (f"their connection (@{self.github}) needs renewing, which they can do on the Connected "
                            "accounts page of their profile." if self.github and self.github_renew else
                            f"they are connected as @{self.github}." if self.github else "they have not connected it "
                            "yet, which they can do on the Connected accounts page of their profile."))
            lines.append("Never, for anyone: " + "; ".join(NEVER) + ". It never changes anything on GitHub, and has "
                         "no access to email inboxes or calendars outside Indico.")
        return "\n".join(lines)


def _about_them(reason):
    """A reason written to the user ("You cannot manage…") as one about them: the model read "you" as itself."""
    reason = re.sub(r"\b[Yy]ou\b", "they", reason)
    return re.sub(r"\b[Yy]our\b", "their", reason)


def _places(categories):
    """Category paths (titles repeat across an instance), at most MAX_CHOICES, then how many more."""
    from indico_assistant.services.actions.base import category_path
    from indico_assistant.services.actions.resolve import MAX_CHOICES

    paths = [category_path(c) for c in categories[:MAX_CHOICES]]
    return paths + [f"{len(categories) - MAX_CHOICES} more"] if len(categories) > MAX_CHOICES else paths


def capability_list(user, event=None, settings=None):
    """The list for ``user`` (and the event on the page). Runs as ``user`` (``acting_as``), like the planner."""
    from indico_assistant.default_settings import WRITE_ACTIONS
    from indico_assistant.services.actions import ACTIONS, enabled_actions
    from indico_assistant.services.actions.resolve import creatable_categories, proposable_categories

    settings = settings or {}
    enabled = enabled_actions(settings)
    create_in, propose_in, can, cannot = [], [], [], []
    if enabled:
        if "create_event" in enabled:
            create_in = [ANYWHERE] if user.is_admin else _places(creatable_categories(user))
        # (an admin creates everywhere, so proposes nowhere)
        if "propose_event" in enabled and not user.is_admin and ACTIONS["propose_event"].available(user) is None:
            propose_in = _places(proposable_categories(user))
    for name in WRITE_ACTIONS:
        action = ACTIONS.get(name)
        if action is None:
            continue
        if name not in enabled:
            if enabled:  # the master switch off is said once, in render()
                cannot.append((action.summary, OFF))
            continue
        if name == "propose_event" and not propose_in:
            continue  # only worth saying where a category is moderated for them
        scope = {} if name in ("create_event", "propose_event") else {"event": event}
        reason = action.available(user, **scope)
        (cannot.append((action.summary, reason)) if reason else can.append(action.summary))
    event_info = None
    if event is not None:
        event_info = {"id": event.id, "title": event.title, "type": getattr(event.type_, "name", str(event.type_)),
                      "manages": bool(event.can_manage(user)), "locked": bool(event.is_locked)}
    github, github_renew = None, False
    if settings.get("github_enabled"):
        from indico_assistant.services.connectors.store import connection

        row = connection(user.id)
        github = row.account_login if row is not None else ""
        github_renew = bool(row is not None and row.needs_renewal)
    return CapabilityList(user_name=user.full_name, is_admin=bool(user.is_admin),
                          data_questions=bool(settings.get("nl2sql_enabled", True)), create_in=create_in,
                          propose_in=propose_in, can=can, cannot=cannot, event=event_info,
                          changes_enabled=bool(enabled), github=github, github_renew=github_renew)
