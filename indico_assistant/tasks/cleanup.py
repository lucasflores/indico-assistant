"""Session cleanup tasks for expired chat sessions.

Feature: 004-chat-api
Task: T039

This task runs daily to remove chat sessions that have been
inactive for more than 90 days.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from celery.schedules import crontab

from indico.core.celery import celery
from indico.core.db import db

from indico_assistant.models.session import ChatSession

logger = logging.getLogger(__name__)

# Default retention period in days
SESSION_RETENTION_DAYS = 90


@celery.task(name="indico_assistant_cleanup_expired_sessions")
def cleanup_expired_sessions(retention_days: int = SESSION_RETENTION_DAYS) -> dict:
    """Delete chat sessions inactive for longer than retention period.
    
    This task is scheduled to run daily via Celery beat.
    
    Args:
        retention_days: Number of days after which inactive sessions are deleted
        
    Returns:
        dict with deletion statistics
    """
    logger.info(
        "Starting chat session cleanup (retention=%d days)",
        retention_days
    )
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    try:
        # Find sessions that haven't been updated since cutoff
        expired_sessions = ChatSession.query.filter(
            ChatSession.updated_at < cutoff_date
        ).all()
        
        session_count = len(expired_sessions)
        message_count = 0
        feedback_count = 0
        
        for session in expired_sessions:
            # Count messages and feedback before deletion
            message_count += len(session.messages)
            for msg in session.messages:
                feedback_count += len(msg.feedback_entries) if hasattr(msg, 'feedback_entries') else 0
            
            # Delete session (cascade deletes messages and feedback)
            db.session.delete(session)
        
        db.session.commit()
        
        logger.info(
            "Cleanup complete: deleted %d sessions, %d messages, %d feedback entries",
            session_count,
            message_count,
            feedback_count
        )
        
        return {
            "status": "success",
            "deleted_sessions": session_count,
            "deleted_messages": message_count,
            "deleted_feedback": feedback_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as e:
        db.session.rollback()
        logger.exception("Error during session cleanup")
        return {
            "status": "error",
            "error": str(e)
        }


def schedule_cleanup_task() -> dict:
    """Get the schedule configuration for the cleanup task.
    
    Returns:
        Celery beat schedule entry for the cleanup task
    """
    return {
        "indico_assistant_cleanup_expired_sessions": {
            "task": "indico_assistant_cleanup_expired_sessions",
            "schedule": crontab(hour=2, minute=0),  # Run daily at 2 AM
            "kwargs": {"retention_days": SESSION_RETENTION_DAYS}
        }
    }
