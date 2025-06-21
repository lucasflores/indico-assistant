"""SQL parsing and cleaning utilities."""

import re
from typing import Optional

def extract_sql_block_deepseek(text: str) -> Optional[str]:
    """Extract SQL block from Deepseek output."""
    if not text:
        return None
    
    # Remove thinking blocks
    text_no_think = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    
    # Look for SQL queries
    matches = re.findall(r"\(?\s*SELECT\s+.*?\s+FROM\s+.*?(?:;|\Z)", text_no_think, re.IGNORECASE | re.DOTALL)
    return matches[-1].strip() if matches else None

def clean_up_llm_sql(sql_query: str) -> str:
    """
    Clean up SQL query returned from LLM.
    
    Args:
        sql_query: Raw SQL query from LLM
        
    Returns:
        Cleaned SQL query
    """
    if not sql_query:
        return ""
        
    # Extract SQL block if it was returned by DeepSeek
    cleaned = sql_query
    
    if "deepseek" in str(sql_query).lower():
        cleaned = extract_sql_block_deepseek(sql_query) or sql_query
        
    # Extract from code blocks
    match = re.search(r"```sql\n(.*?)```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)
        
    # Final cleanup
    cleaned = cleaned.strip()
    if not cleaned.endswith(';'):
        cleaned += ';'
        
    return cleaned

def is_safe_sql(sql_query: str) -> bool:
    """
    Check if a SQL query appears safe to execute.
    
    This is a basic check and should not be relied upon as the only protection.
    
    Args:
        sql_query: SQL query to check
        
    Returns:
        True if query appears safe, False otherwise
    """
    # Must be select query
    if not re.match(r'^\s*SELECT\s+.*$', sql_query, re.IGNORECASE | re.DOTALL):
        return False
        
    # Check for dangerous keywords
    dangerous = {
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE',
        'GRANT', 'REVOKE', 'MERGE', 'EXECUTE', 'FUNCTION', 'PROCEDURE'
    }
    
    tokens = {word.upper() for word in re.findall(r'\b\w+\b', sql_query)}
    if tokens & dangerous:
        return False
        
    return True
