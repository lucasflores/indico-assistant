"""Database query tools and utilities for Indico Assistant.

This module provides tools for:
- Executing SQL queries against the Indico database
- SQL error correction using LLM feedback  
- User context and permission management
- Query result formatting and footnote generation
"""

import os
from typing import Dict, Any, Optional, List

from automaton_core import Automaton, MODEL, HF_TOKEN
from automaton_core.utils import embed_text_huggingface

from config import config

# === Load Schema Context ===
with open(config.schema_path, "r") as file:
    schema_context_v1 = file.read()

# === Load Prompts ===
with open(config.prompts_path / "sql_error_prompt.txt", "r") as f:
    sql_error_prompt = f.read()
    
# === Initialize Error Correction ===
sql_error_correction_automaton = Automaton(
    role_prompt=sql_error_prompt + '\n' + schema_context_v1
)

def query_indico_database_tool(sql_query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Tool for querying the Indico database with SQL.
    
    This is a wrapper around the database query functionality specifically
    designed for use by the language model and chainlit interface.
    
    Args:
        sql_query: The SQL query to execute
        params: Optional query parameters
        
    Returns:
        List of dictionaries containing query results
        
    Raises:
        DatabaseError: If the query fails
    """
    from database.queries import query_indico_database
    return query_indico_database(sql_query, params)

async def correct_sql_error(sql_query: str, error_trace: str) -> str:
    """Attempt to correct a SQL query that produced an error.
    
    Args:
        sql_query: The SQL query that failed
        error_trace: The error trace from the failed query
        
    Returns:
        str: Corrected SQL query
    """
    correction_input = f"Broken SQL:\n{sql_query}\n\nError:\n{error_trace}"
    return await sql_error_correction_automaton.run(user_input=correction_input)

def fetch_current_user_info() -> str:
    """Get information about the currently logged in database user.
    
    This is used to provide context to the language model about user permissions.
    
    Returns:
        str: Information about the current database user
    """
    from database.queries import query_indico_database
    
    result = query_indico_database("""
        SELECT current_user, session_user, current_database(), 
               current_setting('application_name') as app_name;
    """)
    if not result:
        return "No user information available"
        
    info = result[0]
    return (
        f"You are connected as database user '{info['current_user']}' "
        f"to database '{info['current_database']}' "
        f"from application '{info['app_name']}'"
    )

def create_reference_footnotes(results: Dict[str, Any]) -> set:
    """Create formatted reference footnotes from query results.
    
    Args:
        results: Query results containing event information
        
    Returns:
        set: Unique formatted footnotes for events
    """
    footnotes = set()
    
    for row in results:
        if all(k in row for k in ['event_id', 'event_title', 'event_start_dt', 'event_timezone']):
            footnotes.add(
                f"**Event Title**: *{row['event_title']}*, "
                f"**Date/Time**: {row['event_start_dt']} {row['event_timezone']}, "
                f"**Event**: [/event/{row['event_id']}/](/event/{row['event_id']}/)"
            )
            
    return footnotes

