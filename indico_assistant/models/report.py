"""IssueReport: a report a user sent from the chat, and the team's status on it (spec 021).

Feature: 021-issue-reports

A report may carry a frozen copy of the conversation (``copy``), taken when it was sent: the team reads that
copy, never the live chat (FR-018). Retention deletes closed reports ``retention_report_days`` after
``closed_at``; a report that is not closed has no ``closed_at`` and is never purged (FR-020).
"""

from __future__ import annotations

from datetime import UTC, datetime

from indico.core.db import db
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

CATEGORIES = ('bug', 'feature', 'wrong_answer')
STATUSES = ('open', 'under_review', 'closed')
TEXT_MAX = 5000
NOTE_MAX = 2000


def _in(column, values):
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class IssueReport(db.Model):
    __tablename__ = 'issue_reports'
    __table_args__ = (
        CheckConstraint(_in('category', CATEGORIES), name='valid_category'),
        CheckConstraint(_in('status', STATUSES), name='valid_status'),
        UniqueConstraint('user_id', 'form_key'),  # one report per form, however often Send is pressed (R8)
        Index('ix_issue_reports_status_created', 'status', 'created_at'),
        {'schema': 'plugin_assistant'},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    form_key = Column(UUID(as_uuid=True), nullable=False)
    category = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    copy = Column(JSONB(none_as_null=True), nullable=True)  # SQL NULL when not attached (FR-004), not JSON null
    status = Column(String(20), nullable=False, default='open')
    note = Column(Text, nullable=True)
    updated_by_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)  # the team's last save; the stale-save check (R11)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    def __repr__(self):
        return f'<IssueReport {self.id} {self.category} {self.status} user={self.user_id}>'
