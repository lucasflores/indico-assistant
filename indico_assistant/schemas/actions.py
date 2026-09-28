"""What the client sees of a plan (contracts/api.md). Step arguments stay on the server: the user confirms
the plain-language description, which is what the executor carries out.

Feature: 019-chat-actions
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PlanStepView(BaseModel):
    n: int
    description: str
    side_effects: list[str] = Field(default_factory=list)


class PlanView(BaseModel):
    id: UUID
    status: str
    expires_at: datetime
    token: str | None = None  # only in the answer that shows the plan to its owner
    summary: str
    steps: list[PlanStepView]
    questions: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[dict[str, Any]] = Field(default_factory=list)
    can_confirm: bool
    error: str | None = None

    @classmethod
    def of(cls, plan, token=None):
        return cls(id=plan.id, status=plan.effective_status, expires_at=plan.expires_at, token=token,
                   summary=plan.summary, can_confirm=plan.can_confirm, error=plan.error,
                   steps=[PlanStepView(n=s['n'], description=s.get('description', s['action']),
                                       side_effects=s.get('side_effects', [])) for s in plan.steps],
                   questions=plan.questions, suggestions=plan.suggestions)


class ConfirmRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=128)
