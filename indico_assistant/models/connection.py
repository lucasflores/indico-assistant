"""Connection: a user's account on a connected service, with its tokens encrypted (spec 023).

Feature: 023-github-connector

Only ``services.connectors.store`` reads or writes the tokens: they are Fernet ciphertext here, never plain text.
"""

from __future__ import annotations

from datetime import UTC, datetime

from indico.core.db import db
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint


class Connection(db.Model):
    __tablename__ = 'connections'
    __table_args__ = (
        UniqueConstraint('user_id', 'service'),  # one per user and service (FR-008)
        {'schema': 'plugin_assistant'},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    service = Column(String(20), nullable=False)
    account_id = Column(BigInteger, nullable=False)
    account_login = Column(String(100), nullable=False)
    access_token = Column(Text, nullable=False)  # ciphertext
    access_expires_at = Column(DateTime(timezone=True), nullable=True)  # None: GitHub's never-expiring tokens
    refresh_token = Column(Text, nullable=True)  # ciphertext
    refresh_expires_at = Column(DateTime(timezone=True), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    needs_renewal = Column(Boolean, nullable=False, default=False)  # a refused refresh, or a key that changed

    def __repr__(self):
        return f'<Connection {self.id} {self.service} @{self.account_login} user={self.user_id}>'
