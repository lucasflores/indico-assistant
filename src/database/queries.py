"""Database query utilities for Indico Assistant."""

import traceback
from typing import Any, Dict, List, Optional, cast
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Connection

from database.base import engine, get_db
from config import config
from utils.sql import clean_up_llm_sql, is_safe_sql
from exceptions import DatabaseError, SQLValidationError

@contextmanager
def transaction_context(read_only: bool = True):
    """Create a database transaction context.
    
    Args:
        read_only: Whether the transaction should be read-only. Defaults to True.
        
    Yields:
        Active database connection
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            if read_only:
                conn.execute(text("SET TRANSACTION READ ONLY"))
            yield conn
            trans.commit()
        except Exception as e:
            trans.rollback()
            raise DatabaseError("Database transaction failed") from e

def execute_query(conn: Connection, 
                 sql: str, 
                 params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a SQL query and return results.
    
    Args:
        conn: Database connection
        sql: SQL query string
        params: Query parameters
        
    Returns:
        List of result rows as dictionaries
        
    Raises:
        SQLValidationError: If query validation fails
        DatabaseError: If query execution fails
    """
    if not is_safe_sql(sql):
        raise SQLValidationError("Query validation failed - only SELECT statements allowed")
        
    try:
        result = conn.execute(text(sql), params or {})
        return list(result.mappings().all())
    except SQLAlchemyError as e:
        raise DatabaseError(f"Query execution failed: {str(e)}") from e

def query_indico_database(sql_query: str, 
                         params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a query against the Indico database.
    
    This is the main entry point for database queries. It:
    1. Cleans and validates the SQL
    2. Executes in a read-only transaction
    3. Handles errors and retries if needed
    
    Args:
        sql_query: Raw SQL query string
        params: Optional query parameters
        
    Returns:
        Query results as a list of dictionaries
        
    Raises: 
        DatabaseError: If the query fails and cannot be corrected
    """
    clean_sql = clean_up_llm_sql(sql_query)
    
    with transaction_context(read_only=True) as conn:
        try:
            return execute_query(conn, clean_sql, params)
        except DatabaseError as e:
            # Add error correction logic here if needed
            raise
