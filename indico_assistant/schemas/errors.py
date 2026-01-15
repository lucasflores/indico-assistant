"""Common error response schemas for the Chat API.

Feature: 004-chat-api
Task: T005
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response format for all API endpoints.
    
    All error responses follow this consistent JSON format:
    {"error": "CODE", "message": "Human readable message", "details": {...}}
    
    Attributes:
        error: Error code for programmatic handling
        message: Human-readable error message
        details: Additional context (optional)
    """
    
    error: str = Field(
        ...,
        description="Error code (VALIDATION_ERROR, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED, UNPROCESSABLE_QUERY, INTERNAL_ERROR)"
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error context"
    )


# Error codes as constants for consistency
class ErrorCode:
    """Standard error codes for the Chat API."""
    
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    UNPROCESSABLE_QUERY = "UNPROCESSABLE_QUERY"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def create_error_response(
    code: str,
    message: str,
    details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a standardized error response dict.
    
    Args:
        code: Error code from ErrorCode constants
        message: Human-readable error message
        details: Optional additional context
        
    Returns:
        Dictionary suitable for jsonify()
    """
    response = {"error": code, "message": message}
    if details is not None:
        response["details"] = details
    return response
