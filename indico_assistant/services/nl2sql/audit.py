"""Audit logging helper functions for NL2SQL pipeline (T049/US5).

Provides utilities for creating and managing audit log entries.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator, Optional

from indico_assistant.models.audit import QueryAuditLog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AuditLogger:
    """Helper class for audit logging.
    
    Provides a clean interface for creating and managing audit log entries
    throughout the NL2SQL pipeline execution.
    
    Attributes:
        db_session: SQLAlchemy database session
        enabled: Whether audit logging is enabled
    """

    def __init__(
        self,
        db_session: "Session",
        enabled: bool = True,
    ) -> None:
        """Initialize audit logger.
        
        Args:
            db_session: SQLAlchemy database session
            enabled: Whether audit logging is enabled
        """
        self.db_session = db_session
        self.enabled = enabled

    @contextmanager
    def log_query(
        self,
        question: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Generator[Optional[QueryAuditLog], None, None]:
        """Context manager for logging a query execution.
        
        Creates an audit log entry at pipeline entry and commits it
        on context exit (whether successful or not).
        
        Args:
            question: The natural language question
            user_id: Optional user ID
            user_email: Optional user email
            session_id: Optional session identifier
            ip_address: Optional client IP address
            
        Yields:
            QueryAuditLog instance (or None if disabled)
            
        Example:
            with audit_logger.log_query("Show events", user_id=123) as log:
                if log:
                    log.update_classification("event_list", 0.95)
                    log.update_generation("SELECT * FROM events")
                    log.update_execution(150.0, 10, success=True)
        """
        if not self.enabled:
            yield None
            return

        log_entry = QueryAuditLog.create_entry(
            question=question,
            user_id=user_id,
            user_email=user_email,
            session_id=session_id,
            ip_address=ip_address,
        )
        
        try:
            self.db_session.add(log_entry)
            yield log_entry
        finally:
            # Always commit the log entry (successful or failed)
            try:
                self.db_session.commit()
            except Exception:
                # If commit fails, try to rollback and log anyway
                self.db_session.rollback()
                # Re-add the log entry after rollback
                try:
                    self.db_session.add(log_entry)
                    self.db_session.commit()
                except Exception:
                    # Give up if we can't log at all
                    pass

    def create_log_entry(
        self,
        question: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[QueryAuditLog]:
        """Create and persist a new audit log entry.
        
        Use this for manual control over the log entry lifecycle.
        Prefer log_query() context manager for automatic management.
        
        Args:
            question: The natural language question
            user_id: Optional user ID
            user_email: Optional user email
            session_id: Optional session identifier
            ip_address: Optional client IP address
            
        Returns:
            QueryAuditLog instance (or None if disabled)
        """
        if not self.enabled:
            return None

        log_entry = QueryAuditLog.create_entry(
            question=question,
            user_id=user_id,
            user_email=user_email,
            session_id=session_id,
            ip_address=ip_address,
        )
        self.db_session.add(log_entry)
        return log_entry

    def commit(self) -> None:
        """Commit pending changes to database."""
        self.db_session.commit()


def log_classification(
    log_entry: Optional[QueryAuditLog],
    intent: str,
    confidence: float,
) -> None:
    """Log classification result to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
        intent: Classified intent
        confidence: Classification confidence
    """
    if log_entry is not None:
        log_entry.update_classification(intent, confidence)


def log_generation(
    log_entry: Optional[QueryAuditLog],
    sql: str,
) -> None:
    """Log SQL generation to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
        sql: Generated SQL
    """
    if log_entry is not None:
        log_entry.update_generation(sql)


def log_execution(
    log_entry: Optional[QueryAuditLog],
    execution_time_ms: float,
    row_count: int,
    success: bool = True,
) -> None:
    """Log execution result to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
        execution_time_ms: Execution time in milliseconds
        row_count: Number of rows returned
        success: Whether execution was successful
    """
    if log_entry is not None:
        log_entry.update_execution(execution_time_ms, row_count, success)


def log_validation_rejection(
    log_entry: Optional[QueryAuditLog],
    reason: str,
) -> None:
    """Log validation rejection to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
        reason: Rejection reason code
    """
    if log_entry is not None:
        log_entry.mark_validation_rejected(reason)


def _stringify_error(error_message: object | None) -> str:
    if error_message is None:
        return "Unknown error"
    if isinstance(error_message, str):
        return error_message
    if hasattr(error_message, "model_dump"):
        try:
            return json.dumps(error_message.model_dump(), default=str)
        except Exception:
            return str(error_message)
    if hasattr(error_message, "dict"):
        try:
            return json.dumps(error_message.dict(), default=str)
        except Exception:
            return str(error_message)
    return str(error_message)


def log_error(
    log_entry: Optional[QueryAuditLog],
    error_message: object,
) -> None:
    """Log error to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
        error_message: Error message
    """
    if log_entry is not None:
        log_entry.mark_error(_stringify_error(error_message))


def log_correction_attempt(
    log_entry: Optional[QueryAuditLog],
) -> None:
    """Log correction attempt to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
    """
    if log_entry is not None:
        log_entry.mark_correction_attempt()


def log_correction_success(
    log_entry: Optional[QueryAuditLog],
) -> None:
    """Log successful correction to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
    """
    if log_entry is not None:
        log_entry.mark_corrected()


def log_cache_hit(
    log_entry: Optional[QueryAuditLog],
) -> None:
    """Log cache hit to audit entry.
    
    Safe to call with None log_entry (no-op).
    
    Args:
        log_entry: Audit log entry (or None)
    """
    if log_entry is not None:
        log_entry.mark_cached()
