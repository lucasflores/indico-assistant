"""Audit log models for NL2SQL pipeline (T047/US5).

Provides QueryAuditLog model for compliance logging of all NL2SQL queries.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.orm import declarative_base

if TYPE_CHECKING:
    pass

Base = declarative_base()


class QueryAuditLog(Base):
    """Audit log for NL2SQL queries.
    
    Records all NL2SQL pipeline executions for compliance and debugging.
    Per FR-031: Query results are NOT stored in audit logs.
    
    Attributes:
        id: Primary key
        created_at: Timestamp of query submission
        user_id: ID of user who submitted the query (optional)
        user_email: Email of user who submitted the query (optional)
        session_id: Session identifier for grouping related queries
        question: Original natural language question
        intent: Classified intent (event_list, speaker_query, etc.)
        intent_confidence: Classification confidence score (0.0-1.0)
        generated_sql: SQL query generated (None if classification failed)
        execution_time_ms: Query execution time in milliseconds
        row_count: Number of rows returned (None if execution failed)
        success: Whether the query completed successfully
        error_message: Error message if query failed
        validation_rejection_reason: Reason code if SQL was rejected
        correction_attempts: Number of error correction attempts
        was_corrected: Whether SQL was corrected after initial failure
        cached: Whether result was served from cache
        ip_address: Client IP address (optional, for security audit)
    """

    __tablename__ = "query_audit_log"
    __table_args__ = {"schema": "plugin_assistant"}

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    created_at: datetime = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    
    # User information
    user_id: Optional[int] = Column(Integer, nullable=True, index=True)
    user_email: Optional[str] = Column(String(255), nullable=True)
    session_id: Optional[str] = Column(String(64), nullable=True, index=True)
    
    # Query information
    question: str = Column(Text, nullable=False)
    intent: Optional[str] = Column(String(64), nullable=True, index=True)
    intent_confidence: Optional[float] = Column(Float, nullable=True)
    
    # Generated SQL (FR-031: results NOT stored)
    generated_sql: Optional[str] = Column(Text, nullable=True)
    
    # Execution metrics
    execution_time_ms: Optional[float] = Column(Float, nullable=True)
    row_count: Optional[int] = Column(Integer, nullable=True)
    
    # Status
    success: bool = Column(Boolean, nullable=False, default=False)
    error_message: Optional[str] = Column(Text, nullable=True)
    
    # Validation tracking
    validation_rejection_reason: Optional[str] = Column(String(128), nullable=True)
    
    # Error correction tracking
    correction_attempts: int = Column(Integer, nullable=False, default=0)
    was_corrected: bool = Column(Boolean, nullable=False, default=False)
    
    # Cache tracking
    cached: bool = Column(Boolean, nullable=False, default=False)
    
    # Security audit
    ip_address: Optional[str] = Column(String(45), nullable=True)  # IPv6 max length

    def __repr__(self) -> str:
        """Return string representation."""
        status = "✓" if self.success else "✗"
        return (
            f"<QueryAuditLog(id={self.id}, {status}, "
            f"intent={self.intent}, time={self.execution_time_ms}ms)>"
        )

    @classmethod
    def create_entry(
        cls,
        question: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> "QueryAuditLog":
        """Create a new audit log entry at pipeline entry.
        
        Args:
            question: The natural language question
            user_id: Optional user ID
            user_email: Optional user email
            session_id: Optional session identifier
            ip_address: Optional client IP address
            
        Returns:
            New QueryAuditLog instance (not yet committed)
        """
        return cls(
            question=question,
            user_id=user_id,
            user_email=user_email,
            session_id=session_id,
            ip_address=ip_address,
            success=False,  # Will be updated on completion
            correction_attempts=0,  # Initialize in-memory defaults
            was_corrected=False,
            cached=False,
        )

    def update_classification(
        self,
        intent: str,
        confidence: float,
    ) -> None:
        """Update with classification results.
        
        Args:
            intent: Classified intent
            confidence: Classification confidence score
        """
        self.intent = intent
        self.intent_confidence = confidence

    def update_generation(self, sql: str) -> None:
        """Update with generated SQL.
        
        Args:
            sql: Generated SQL query
        """
        self.generated_sql = sql

    def update_execution(
        self,
        execution_time_ms: float,
        row_count: int,
        success: bool = True,
    ) -> None:
        """Update with execution results.
        
        Args:
            execution_time_ms: Execution time in milliseconds
            row_count: Number of rows returned
            success: Whether execution was successful
        """
        self.execution_time_ms = execution_time_ms
        self.row_count = row_count
        self.success = success

    def mark_validation_rejected(self, reason: str) -> None:
        """Mark query as rejected by validation.
        
        Args:
            reason: Rejection reason code
        """
        self.validation_rejection_reason = reason
        self.success = False

    def mark_error(self, error_message: str) -> None:
        """Mark query as failed with error.
        
        Args:
            error_message: Error message
        """
        self.error_message = error_message
        self.success = False

    def mark_correction_attempt(self) -> None:
        """Increment correction attempt counter."""
        self.correction_attempts += 1

    def mark_corrected(self) -> None:
        """Mark query as successfully corrected."""
        self.was_corrected = True

    def mark_cached(self) -> None:
        """Mark result as served from cache."""
        self.cached = True
