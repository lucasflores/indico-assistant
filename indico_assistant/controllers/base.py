"""Base controller classes for Chat API endpoints.

Feature: 004-chat-api
Feature: 006-vector-search-rag
Task: T011
"""

from __future__ import annotations

from flask import jsonify, request, session
from indico.web.rh import RH
from werkzeug.exceptions import Forbidden, NotFound, Unauthorized

from indico_assistant.schemas.errors import ErrorCode, create_error_response


class RHAssistantBase(RH):
    """Base class for all Assistant plugin API endpoints.
    
    Provides common functionality for authenticated endpoints.
    Subclasses should override _process() to implement endpoint logic.
    """
    
    DENY_FRAMES = True  # Prevent clickjacking
    ADMIN_ONLY = False  # Override to True for admin-only endpoints

    def _check_access(self):
        """Enforce authentication for all Assistant API endpoints.
        
        Raises:
            Unauthorized: If user is not authenticated
            Forbidden: If ADMIN_ONLY and user is not admin
        """
        if session.user is None:
            raise Unauthorized("Authentication required")
        
        if self.ADMIN_ONLY and not session.user.is_admin:
            raise Forbidden("Admin access required")
    
    @property
    def user(self):
        """Get the current authenticated user."""
        return session.user
    
    @property
    def plugin(self):
        """Get the plugin instance."""
        from indico.core.plugins import plugin_engine
        return plugin_engine.get_plugin("assistant")


class RHChatBase(RHAssistantBase):
    """Base class for authenticated Chat API endpoints.
    
    All Chat API endpoints require Indico authentication. This base class
    enforces authentication and provides common error handling utilities.
    
    Subclasses should override _process() to implement endpoint logic.
    """

    def _get_current_user_id(self) -> int:
        """Get the current authenticated user's ID.
        
        Returns:
            User ID from Indico session
            
        Raises:
            Unauthorized: If user is not authenticated
        """
        if session.user is None:
            raise Unauthorized("Authentication required")
        return session.user.id

    def _error_response(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        status: int = 400
    ):
        """Create a standardized JSON error response.
        
        Args:
            code: Error code from ErrorCode constants
            message: Human-readable error message
            details: Optional additional context
            status: HTTP status code
            
        Returns:
            Flask response tuple (jsonified data, status code)
        """
        return jsonify(create_error_response(code, message, details)), status

    def _validation_error(self, message: str, field: str | None = None):
        """Create a validation error response.
        
        Args:
            message: Error message
            field: Optional field name that failed validation
            
        Returns:
            Flask response tuple with 400 status
        """
        details = {"field": field} if field else None
        return self._error_response(
            ErrorCode.VALIDATION_ERROR,
            message,
            details,
            400
        )

    def _not_found_error(self, resource: str, resource_id: str | None = None):
        """Create a not found error response.
        
        Args:
            resource: Resource type (e.g., "Session", "Message")
            resource_id: Optional resource identifier
            
        Returns:
            Flask response tuple with 404 status
        """
        details = {"id": resource_id} if resource_id else None
        return self._error_response(
            ErrorCode.NOT_FOUND,
            f"{resource} not found",
            details,
            404
        )

    def _forbidden_error(self, message: str, details: dict | None = None):
        """Create a forbidden error response.
        
        Args:
            message: Error message
            details: Optional additional context
            
        Returns:
            Flask response tuple with 403 status
        """
        return self._error_response(
            ErrorCode.FORBIDDEN,
            message,
            details,
            403
        )

    def _rate_limit_error(self, retry_after: int):
        """Create a rate limit exceeded error response.
        
        Args:
            retry_after: Seconds until rate limit resets
            
        Returns:
            Flask response tuple with 429 status and Retry-After header
        """
        response = jsonify(create_error_response(
            ErrorCode.RATE_LIMITED,
            "Too many requests, please wait before retrying",
            {"retry_after": retry_after}
        ))
        response.headers['Retry-After'] = str(retry_after)
        return response, 429

    def _internal_error(self, message: str = "An internal error occurred"):
        """Create an internal server error response.
        
        Args:
            message: Error message (defaults to generic message)
            
        Returns:
            Flask response tuple with 500 status
        """
        return self._error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
            None,
            500
        )
