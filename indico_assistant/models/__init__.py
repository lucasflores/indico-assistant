"""Models package for indico_assistant.

Provides SQLAlchemy models for the Indico Assistant plugin.
"""

from indico_assistant.models.audit import QueryAuditLog

__all__ = ["QueryAuditLog"]
