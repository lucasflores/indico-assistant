"""Indico Assistant - AI-powered chatbot for Indico."""

from .app_chnlit import *
from .query_tools import (
    query_indico_database_tool,
    create_reference_footnotes,
    fetch_current_user_info
)
from .event_processing import Event, EventQueue, EventProcessor
from .exceptions import (
    IndicoAssistantError,
    DatabaseError,
    SQLValidationError,
    ConfigurationError,
    ModelError,
    EventProcessingError
)

__version__ = '0.1.0'

__all__ = [
    # Core functionality
    'query_indico_database_tool',
    'create_reference_footnotes',
    'fetch_current_user_info',
    
    # Event processing
    'Event',
    'EventQueue',
    'EventProcessor',
    
    # Exceptions
    'IndicoAssistantError',
    'DatabaseError', 
    'SQLValidationError',
    'ConfigurationError',
    'ModelError',
    'EventProcessingError'
]
