"""Database connection and engine configuration for Indico Assistant."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from config import config

def create_db_engine() -> Engine:
    """Create SQLAlchemy engine with proper configuration."""
    return create_engine(
        config.db_url,
        pool_size=config.pool_size,
        max_overflow=config.max_overflow,
        pool_timeout=config.pool_timeout
    )

# Global engine instance
engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_db() -> Iterator[Session]:
    """Get a database session within a context manager."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# Listen for application shutdown
def cleanup_db() -> None:
    """Clean up database resources."""
    if engine:
        engine.dispose()
