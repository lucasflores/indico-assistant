"""The chat-action planner's LLM output (contracts/plan-draft.md).

The model states intent in the user's own terms (names, "today", "it"); code resolves every person, category,
time and permission afterwards, so a draft never carries ids the user or the context did not supply.

Feature: 019-chat-actions
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class PersonRef(BaseModel):
    name: str | None = Field(None, description='As the user said it, e.g. "Makoto"; "me" for the user')
    email: str | None = None

    @model_validator(mode='before')
    @classmethod
    def _from_name(cls, value):
        if isinstance(value, str):
            return {'name': value}  # models often send just the name
        if isinstance(value, dict) and '@' not in str(value.get('email') or ''):
            value = {**value, 'email': None}  # seen live: "null" as a string, which turned a user into a guest
        return value


class When(BaseModel):
    date: str | None = Field(None, description='As said: "today", "next Tuesday", "2026-10-02"; null when the user '
                                               'named no day (a move to "3pm" keeps the day)')
    time: str | None = Field(None, description='"14:00", "2pm"; null when not given (the assistant suggests times)')
    duration_minutes: int | None = Field(None, description='Only if the user said how long the meeting is')
    timezone: str | None = Field(None, description='Only if the user named one')
    keep_past: bool = Field(False, description='True only if the user confirmed a time that has already passed')


class Slot(BaseModel):
    title: str | None = None
    speaker: PersonRef | None = Field(None, description='Who gives this talk; "me" for the user')
    duration_minutes: int | None = None


class CreateMeeting(BaseModel):
    action: Literal['create_meeting']
    title: str | None = None
    category: str | None = Field(None, description='The category name as said, or null to ask the user')
    when: When
    people: list[PersonRef] = Field(default_factory=list, description='Everyone invited, besides the user')
    slots: list[Slot] = Field(default_factory=list, description='Contributions (talks) with their speakers')
    teams: bool = Field(False, description='A Microsoft Teams meeting was asked for')
    description: str | None = None
    links: list[str] = Field(default_factory=list, description='Links to attach as material (accepted suggestions)')


class SlotChange(BaseModel):
    which: str = Field(..., description='"second", "the Q&A", "Makoto\'s"')
    title: str | None = None
    speaker: PersonRef | None = None
    duration_minutes: int | None = None
    move_to: When | None = None


class ReminderDraft(BaseModel):
    minutes_before: int | None = Field(None, description='How long before the start, in minutes, as the user said '
                                                          'it ("1 day before" = 1440); null if not said')
    at: When | None = Field(None, description='Only when the user gave the reminder its own time ("tomorrow 9am")')
    participants: bool = Field(False, description='To the registered participants ("all participants")')
    speakers: bool = Field(False, description='To the speakers')
    people: list[PersonRef] = Field(default_factory=list, description='Other people to email, as the user named them')


class ChangeMeeting(BaseModel):
    action: Literal['change_meeting']
    meeting: str = Field('it', description='"it" = the meeting made in this chat; otherwise its name')
    move_to: When | None = None
    title: str | None = None
    description: str | None = None
    add_slots: list[Slot] = Field(default_factory=list)
    change_slots: list[SlotChange] = Field(default_factory=list)
    teams: bool = Field(False, description='Add a Microsoft Teams meeting to it')
    reminder: ReminderDraft | None = Field(None, description='Add an email reminder before it')


class Attach(BaseModel):
    action: Literal['attach']
    target: str = Field(..., description='"my contribution to the meeting", "the meeting"')
    upload: str | None = Field(None, description='"this" = the file(s) sent with the message')
    url: str | None = None
    title: str | None = None


class Undo(BaseModel):
    action: Literal['undo']
    which: str = 'last'


Step = Annotated[CreateMeeting | ChangeMeeting | Attach | Undo, Field(discriminator='action')]


class SuggestionDraft(BaseModel):
    kind: Literal['title', 'description', 'agenda_item', 'person', 'material', 'duration']
    content: str
    source_ref: str = Field(..., description='An id from the context block: "chat", "event:431", "attachment:88"')


class PlanDraft(BaseModel):
    decision: Literal['new_request', 'revise', 'confirm', 'cancel', 'unrelated'] = Field(
        ..., description='revise/confirm/cancel refer to the open plan; unrelated = a question, not a change')
    steps: list[Step] = Field(default_factory=list, max_length=10)
    questions: list[str] = Field(default_factory=list, description='Only what context cannot answer')
    suggestions: list[SuggestionDraft] = Field(default_factory=list)
    reply: str = Field('', description='One or two sentences to the user')
