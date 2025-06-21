"""Custom exceptions for Indico Assistant."""

class IndicoAssistantError(Exception):
    """Base exception for Indico Assistant errors."""
    pass

class DatabaseError(IndicoAssistantError):
    """Raised when a database operation fails."""
    pass

class SQLValidationError(DatabaseError):
    """Raised when SQL validation fails."""
    pass

class ConfigurationError(IndicoAssistantError):
    """Raised when there is a configuration error."""
    pass

class ModelError(IndicoAssistantError):
    """Raised when there is an error with ML model operations."""
    pass

class EventProcessingError(IndicoAssistantError):
    """Raised when event processing fails."""
    pass
