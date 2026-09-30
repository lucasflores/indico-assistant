# LLM contract: PlanDraft

**Module**: `indico_assistant.services.llm.models.plan` | Produced by `LLMService.generate(...,
response_model=PlanDraft)` (instructor; MD_JSON / JSON / TOOLS by provider).

The LLM states **intent** in the user's terms. Code resolves every name, time and permission (research R12). A
draft never contains ids that the user or context did not supply verbatim.

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class PersonRef(BaseModel):
    name: str | None = None          # "Makoto", "me" for the requesting user
    email: str | None = None

class When(BaseModel):
    date: str | None = None          # as said: "today", "next Tuesday", "2026-10-02"
    time: str | None = None          # "14:00", "2pm"; None = ask / suggest (US8)
    duration_minutes: int | None = None
    timezone: str | None = None      # only if the user said one

class CreateMeeting(BaseModel):
    action: Literal["create_meeting"]
    title: str | None = None
    category: str | None = None      # a name as the user said it, or None → ask (FR-013)
    when: When
    people: list[PersonRef] = []     # invitees (FR-022)
    slots: list["Slot"] = []         # contributions; their speakers are people too
    teams: bool = False
    description: str | None = None

class Slot(BaseModel):
    title: str | None = None
    speaker: PersonRef | None = None
    duration_minutes: int | None = None

class ChangeMeeting(BaseModel):
    action: Literal["change_meeting"]
    meeting: str = "it"              # "it" = the event made in this chat; otherwise a name
    move_to: When | None = None
    title: str | None = None
    description: str | None = None
    add_slots: list[Slot] = []
    change_slot: dict | None = None  # {"which": "second", "speaker": PersonRef, ...}
    teams: bool = False              # spec 022: add a Teams meeting to a meeting that already exists
    reminder: ReminderDraft | None = None  # spec 022: {minutes_before | at, participants, speakers, people}

class Attach(BaseModel):
    action: Literal["attach"]
    target: str                      # "my contribution to the meeting", "the meeting"
    upload: str | None = None        # "this" = the file(s) sent with the message
    url: str | None = None
    title: str | None = None

class Undo(BaseModel):
    action: Literal["undo"]
    which: str = "last"

Step = Annotated[Union[CreateMeeting, ChangeMeeting, Attach, Undo], Field(discriminator="action")]

class SuggestionDraft(BaseModel):
    kind: Literal["title", "description", "agenda_item", "person", "material", "duration"]
    content: str
    source_ref: str                  # an id from the context block, e.g. "chat", "event:431", "attachment:88"

class PlanDraft(BaseModel):
    decision: Literal["new_request", "revise", "confirm", "cancel", "unrelated"]
    steps: list[Step] = Field(default=[], max_length=10)
    questions: list[str] = []        # only what cannot be resolved from context
    suggestions: list[SuggestionDraft] = []
    reply: str                       # one or two sentences to the user
```

## Prompt inputs (built by `services/actions/planner.py`)

- **Current facts**: the user's name and email, timezone, today's local date and time, whether vc_teams is
  available, the actions enabled.
- **Open plan**, when there is one: its summary and questions, so "make it 30 minutes", "yes" and "Engineering"
  resolve against it.
- **Chat turns**: the last 20 messages, as proper `messages`.
- **Context block**, fenced and labelled *data, not instructions* (FR-017). It holds the ids used by
  `source_ref`:
  - the user's recent meetings on the topic (title, date, category path, attendees);
  - titles of their material;
  - earlier chat snippets.

  The block is fetched through Indico access checks (FR-016).

## Mapping to plan steps (code)

- `CreateMeeting` → `create_event` (or `propose_event`), then an `add_contribution` per slot, then
  `add_reminder`, then `add_teams_room` if `teams`.
- `ChangeMeeting` → `update_event` / `add_contribution` / `update_contribution`.
- `Attach` → `attach_file` / `attach_link`.
- `Undo` → `delete_created`.

At this stage names become ids (`find_person`, `list_categories`, `find_event`), `When` becomes aware datetimes
(R11), and slots are laid out back to back from the start (the meeting is extended to fit, US1 AS-3). Every
unresolved or ambiguous value becomes a **Question**.

A draft that fails validation is sent back once, with the errors (FR-005). If it fails again, the reply asks the
user a question instead.
