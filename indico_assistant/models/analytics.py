"""Turns, their steps and their text: what the analytics page and each answer's trace read (spec 024).

Feature: 024-assistant-analytics

A turn is stamped when it happens and never recomputed. It has no foreign key to chats, messages, users or events,
so a deleted chat doesn't take its numbers with it (its text does go, FR-011). Nothing measured stays NULL, never 0.
Only ``services.analytics.recorder`` writes them, on its own connection.
"""

from __future__ import annotations

from datetime import UTC, datetime

from indico.core.db import db
from sqlalchemy import (BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, Numeric,
                        SmallInteger, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID


class Turn(db.Model):
    """One chat answer attempt (plan, Design 2)."""

    __tablename__ = 'turns'
    __table_args__ = (
        Index('ix_turns_user_started', 'user_id', 'started_at'),
        # the running ones (finished_at NULL): the "no end record" count reads only these
        Index('ix_turns_unfinished', 'started_at', postgresql_where=db.text('finished_at IS NULL')),
        {'schema': 'plugin_assistant'},
    )

    id = Column(BigInteger, primary_key=True)
    job_id = Column(String(32), nullable=False, unique=True)
    # who and where, stamped by the start row (FR-002)
    user_id = Column(Integer, nullable=True)  # NULL once the user is deleted or anonymised (FR-012)
    is_admin = Column(Boolean, nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    message_id = Column(UUID(as_uuid=True), nullable=False)  # the question
    answer_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # the answer message, once saved
    event_id = Column(Integer, nullable=True)
    category_id = Column(Integer, nullable=True)
    private = Column(Boolean, nullable=False, default=False)  # no text kept (FR-009)
    # when
    queued_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    # what happened
    outcome = Column(String(24), nullable=True)  # answered | failed | timeout | access_denied | refusal | cannot_plan
    error_code = Column(String(48), nullable=True)
    route = Column(String(16), nullable=True)
    decided_by = Column(String(16), nullable=True)  # jev | classifier | shortcut | planner
    jev_confidence = Column(Float, nullable=True)
    fallback = Column(String(48), nullable=True)
    # totals: sums over the steps
    llm_calls = Column(SmallInteger, nullable=True)  # steps of kind llm or jev
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(12, 6), nullable=True)  # the known sum
    unpriced_calls = Column(SmallInteger, nullable=True)
    # the data route
    intent = Column(String(48), nullable=True)
    corrections = Column(SmallInteger, nullable=True)
    row_count = Column(Integer, nullable=True)
    truncated = Column(Boolean, nullable=True)
    sql_ms = Column(Integer, nullable=True)
    # the other routes
    plan_id = Column(UUID(as_uuid=True), nullable=True)
    tool_calls = Column(SmallInteger, nullable=True)
    rating = Column(SmallInteger, nullable=True)  # 1, -1, or NULL (FR-007)
    record = Column(JSONB, nullable=True)  # the route record and its extras

    def __repr__(self):
        return f'<Turn {self.id} {self.route} {self.outcome}>'


class TurnStep(db.Model):
    """One model call, query, Jev call or tool call inside a turn."""

    __tablename__ = 'turn_steps'
    __table_args__ = (
        UniqueConstraint('turn_id', 'seq'),
        {'schema': 'plugin_assistant'},
    )

    id = Column(BigInteger, primary_key=True)
    turn_id = Column(BigInteger, ForeignKey('plugin_assistant.turns.id', ondelete='CASCADE'), nullable=False)
    seq = Column(SmallInteger, nullable=False)
    parent_seq = Column(SmallInteger, nullable=True)
    kind = Column(String(8), nullable=False)  # llm | sql | jev | tool
    stage = Column(String(48), nullable=True)  # for llm, the response model's name (QueryClassification, ...)
    name = Column(String(64), nullable=True)  # the tool, or the query's intent
    offset_ms = Column(Integer, nullable=True)  # from the turn's start
    duration_ms = Column(Integer, nullable=True)
    ok = Column(Boolean, nullable=False, default=True)
    error_code = Column(String(48), nullable=True)
    requested_model = Column(String(128), nullable=True)
    served_model = Column(String(128), nullable=True)
    ibis_chosen = Column(String(128), nullable=True)
    ibis_dial = Column(String(32), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(12, 6), nullable=True)
    attempts = Column(SmallInteger, nullable=True)  # every HTTP request, SDK retries included
    row_count = Column(Integer, nullable=True)


class TurnText(db.Model):
    """The prompt, response, SQL or row preview of one step, deleted on its own schedule (FR-013)."""

    __tablename__ = 'turn_texts'
    __table_args__ = (
        UniqueConstraint('turn_id', 'seq', 'kind'),
        {'schema': 'plugin_assistant'},
    )

    id = Column(BigInteger, primary_key=True)  # (the retention purge deletes by id)
    turn_id = Column(BigInteger, ForeignKey('plugin_assistant.turns.id', ondelete='CASCADE'), nullable=False)
    seq = Column(SmallInteger, nullable=False)
    kind = Column(String(16), nullable=False)  # prompt | response | sql | rows
    text = Column(Text, nullable=False)
    cut = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)
