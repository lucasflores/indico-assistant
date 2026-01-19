"""Base controller classes for Chat API endpoints.

Feature: 004-chat-api
Feature: 006-vector-search-rag
Task: T011
"""

from __future__ import annotations

import os

import logging
from flask import current_app, jsonify, request, session
from indico.web.rh import RH
from werkzeug.exceptions import Forbidden, NotFound, Unauthorized

from indico_assistant.schemas.errors import ErrorCode, create_error_response
from indico_assistant.services.jwt_service import validate_chainlit_token

logger = logging.getLogger(__name__)


class RHAssistantBase(RH):
    """Base class for all Assistant plugin API endpoints.
    
    Provides common functionality for authenticated endpoints.
    Subclasses should override _process() to implement endpoint logic.
    """
    
    DENY_FRAMES = True  # Prevent clickjacking
    ADMIN_ONLY = False  # Override to True for admin-only endpoints
    CSRF_ENABLED = False  # API auth is handled via JWT header

    def _check_access(self):
        """Enforce authentication for all Assistant API endpoints.
        
        Raises:
            Unauthorized: If user is not authenticated
            Forbidden: If ADMIN_ONLY and user is not admin
        """
        auth_header = request.headers.get("Authorization", "")
        print(
            f"[assistant auth] _check_access called auth_header_present={bool(auth_header)}",
            flush=True,
        )

        user = session.user
        if user is None:
            user = self._get_user_from_bearer_token()
            if user is not None:
                self._user = user
        if user is None:
            print("[assistant auth] session user missing", flush=True)
            raise Unauthorized("Authentication required")
        
        if self.ADMIN_ONLY and not user.is_admin:
            raise Forbidden("Admin access required")

    def _get_user_from_bearer_token(self):
        """Get authenticated user from Authorization header if present."""
        auth_header = request.headers.get("Authorization", "")
        assistant_header = request.headers.get("X-Assistant-Auth", "")
        current_app.logger.warning(
            "Assistant API auth header present=%s assistant_header_present=%s",
            bool(auth_header),
            bool(assistant_header),
        )
        print(
            f"[assistant auth] Authorization header present={bool(auth_header)} "
            f"assistant_header_present={bool(assistant_header)}",
            flush=True,
        )

        token = assistant_header.strip()
        if not token:
            if not auth_header.startswith("Bearer "):
                if auth_header:
                    current_app.logger.warning("Assistant auth header not Bearer")
                    print("[assistant auth] Authorization header not Bearer")
                return None
            token = auth_header.removeprefix("Bearer ").strip()
            if not token:
                return None

        secret = None
        plugin = self.plugin
        if plugin:
            secret = plugin.settings.get("chainlit_auth_secret")
        if not secret:
            secret = os.environ.get("CHAINLIT_AUTH_SECRET", "")
        if not secret:
            current_app.logger.warning("Assistant JWT secret not configured")
            print("[assistant auth] JWT secret not configured")
            return None

        payload = validate_chainlit_token(token, secret)
        if not payload:
            current_app.logger.warning("Assistant JWT validation failed")
            print("[assistant auth] JWT validation failed")
            return None

        user_id = payload.get("identifier") or payload.get("id")
        if not user_id:
            current_app.logger.warning("Assistant JWT missing identifier")
            print("[assistant auth] JWT missing identifier")
            return None

        try:
            from indico.modules.users import User
            user = User.get(int(user_id))
            if user is None:
                current_app.logger.warning(
                    "Assistant JWT user not found for id=%s", user_id
                )
                print(f"[assistant auth] JWT user not found id={user_id}")
            return user
        except Exception:
            current_app.logger.exception("Assistant JWT user lookup failed")
            print("[assistant auth] JWT user lookup failed")
            return None
    
    @property
    def user(self):
        """Get the current authenticated user.
        
        Allows test injection via _user attribute.
        """
        if hasattr(self, '_user') and self._user is not None:
            return self._user
        return session.user
    
    @user.setter
    def user(self, value):
        """Set user for testing purposes."""
        self._user = value
    
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
            Flask response tuple with 422 status
        """
        details = {"field": field} if field else None
        return self._error_response(
            ErrorCode.VALIDATION_ERROR,
            message,
            details,
            status=422
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
