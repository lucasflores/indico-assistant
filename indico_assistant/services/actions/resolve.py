"""From a draft (what the user said) to a checked plan (what will be done): people, categories, times,
permissions (research R8-R11). Anything ambiguous becomes a question; nothing here writes.
"""

from dataclasses import dataclass, field


@dataclass
class Resolved:
    steps: list = field(default_factory=list)
    summary: str = ''
    questions: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    refusal: str | None = None  # the user cannot do this at all (the reason, as Indico would give it)


def draft_to_plan(draft, user, *, chat_session_id, open_plan=None):
    raise NotImplementedError  # CreateMeeting: T036; ChangeMeeting: T060; Attach: T066; Undo: T076
