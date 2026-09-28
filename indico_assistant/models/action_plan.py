"""ActionPlan: a plan of Indico changes the assistant showed to a user (chat actions).

Feature: 019-chat-actions

One row per version of a plan: a revision creates a new row and supersedes the previous one. Nothing in a
plan runs until the user confirms that exact version (see services/actions/executor.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, UTC

from indico.core.db import db
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID


PLAN_TTL = timedelta(minutes=30)  # an unconfirmed plan expires (FR-007)

STATUSES = ('shown', 'confirmed', 'running', 'done', 'failed', 'refused', 'cancelled', 'superseded', 'expired')
TERMINAL = frozenset({'done', 'failed', 'refused', 'cancelled', 'superseded', 'expired'})


def _now():
    return datetime.now(UTC)


class ActionPlan(db.Model):
    __tablename__ = 'action_plans'
    __table_args__ = (
        CheckConstraint(f"status IN ({', '.join(repr(s) for s in STATUSES)})", name='valid_status'),
        Index('ix_action_plans_user_status_finished', 'user_id', 'status', 'finished_at'),
        Index('ix_action_plans_session_created', 'session_id', 'created_at'),
        {'schema': 'plugin_assistant'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, nullable=False)
    # the plan outlives its chat (audit, retention_plan_days): None once the chat is deleted
    session_id = Column(UUID(as_uuid=True), ForeignKey('plugin_assistant.chat_sessions.id', ondelete='SET NULL'),
                        nullable=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey('plugin_assistant.chat_messages.id', ondelete='SET NULL'),
                        nullable=True)
    supersedes_id = Column(UUID(as_uuid=True), ForeignKey('plugin_assistant.action_plans.id', ondelete='SET NULL'),
                           nullable=True)
    undoes_id = Column(UUID(as_uuid=True), ForeignKey('plugin_assistant.action_plans.id', ondelete='SET NULL'),
                       nullable=True)
    status = Column(String(16), nullable=False, default='shown')
    steps = Column(JSONB, nullable=False, default=list)
    questions = Column(JSONB, nullable=False, default=list)
    suggestions = Column(JSONB, nullable=False, default=list)
    summary = Column(Text, nullable=False)
    token_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False, default=lambda: _now() + PLAN_TTL)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    llm_calls = Column(JSONB, nullable=False, default=list)
    draft = Column(JSONB, nullable=True)  # what the user asked for (PlanDraft), to apply answers to it

    @property
    def effective_status(self):
        """The status as the user sees it: an unconfirmed plan past its time is expired."""
        if self.status == 'shown' and self.expires_at <= _now():
            return 'expired'
        return self.status

    @property
    def can_confirm(self):
        return self.effective_status == 'shown' and not self.questions

    def __repr__(self):
        return f'<ActionPlan {self.id} {self.status} user={self.user_id}>'
