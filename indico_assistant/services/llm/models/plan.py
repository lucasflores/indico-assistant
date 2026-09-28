"""The chat-action planner's LLM output (contracts/plan-draft.md).

The model states intent in the user's own terms (names, "today", "it"); code resolves every person, category,
time and permission afterwards, so a draft never carries ids the user or the context did not supply.

Feature: 019-chat-actions
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class PersonRef(BaseModel):
    name: str | None = Field(None, description='As the user said it, e.g. "Makoto"; "me" for the user')
    email: str | None = None


class When(BaseModel):
    date: str | None = Field(None, description='As said: "today", "next Tuesday", "2026-10-02"')
    time: str | None = Field(None, description='"14:00", "2pm"; null when not given (the assistant suggests times)')
    duration_minutes: int | None = None
    timezone: str | None = Field(None, description='Only if the user named one')


class Slot(BaseModel):
    title: str | None = None
    speaker: PersonRef | None = None
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


class SlotChange(BaseModel):
    which: str = Field(..., description='"second", "the Q&A", "Makoto\'s"')
    title: str | None = None
    speaker: PersonRef | None = None
    duration_minutes: int | None = None
    move_to: When | None = None


class ChangeMeeting(BaseModel):
    action: Literal['change_meeting']
    meeting: str = Field('it', description='"it" = the meeting made in this chat; otherwise its name')
    move_to: When | None = None
    title: str | None = None
    description: str | None = None
    add_slots: list[Slot] = Field(default_factory=list)
    change_slots: list[SlotChange] = Field(default_factory=list)


class Attach(BaseModel):
    action: Literal['attach']
    target: str = Field(..., description='"my contribution to the meeting", "the meeting"')
    upload: str | None = Field(None, description='"this" = the file(s) sent with the message')
    url: str | None = None
    title: str | None = None


class Undo(BaseModel):
    action: Literal['undo']
    which: str = 'last'


Step = Annotated[Union[CreateMeeting, ChangeMeeting, Attach, Undo], Field(discriminator='action')]


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
    reply: str = Field(..., description='One or two sentences to the user')
