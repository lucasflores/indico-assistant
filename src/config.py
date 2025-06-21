"""Configuration settings for the Indico Assistant."""

import os
import warnings
from pathlib import Path
from typing import Optional

# Base paths
PKG_DIR = Path(__file__).parent
PROMPTS_DIR = PKG_DIR / "prompts"
CONFIG_DIR = PKG_DIR / "config"

# Database configuration defaults
DEFAULT_DB_URL = "postgresql+psycopg2://lucasflores:@localhost:5432/indico"
DEFAULT_POOL_SIZE = 5
DEFAULT_MAX_OVERFLOW = 10
DEFAULT_POOL_TIMEOUT = 30

class Config:
    """Configuration for Indico Assistant.
    
    Attributes:
        db_url: Database connection URL
        pool_size: Database connection pool size
        max_overflow: Maximum number of connections that can be created beyond pool_size
        pool_timeout: Number of seconds to wait before timing out on getting a connection
        hf_token: HuggingFace API token for embeddings
        schema_path: Path to database schema YAML file
        prompts_path: Directory containing prompt template files
        invariant_api_key: API key for Invariant guardrails service
    """
    
    def __init__(self):
        # Database settings
        self.db_url: str = os.getenv("INDICO_DB_URL", DEFAULT_DB_URL)
        self.pool_size: int = int(os.getenv("INDICO_DB_POOL_SIZE", str(DEFAULT_POOL_SIZE)))
        self.max_overflow: int = int(os.getenv("INDICO_DB_MAX_OVERFLOW", str(DEFAULT_MAX_OVERFLOW)))
        self.pool_timeout: int = int(os.getenv("INDICO_DB_POOL_TIMEOUT", str(DEFAULT_POOL_TIMEOUT)))
        
        # Model settings
        self.hf_token: Optional[str] = os.getenv("HF_TOKEN")
        if not self.hf_token:
            warnings.warn("HF_TOKEN not set. Some features may not work.")
        
        # Path settings
        self.schema_path: Path = CONFIG_DIR / "all_tables.yaml"
        self.prompts_path: Path = PROMPTS_DIR
        
        # Prompt file requirements
        self.required_prompts = [
            "classify_prompt.txt",
            "sql_prompt.txt", 
            "summarize_prompt.txt",
            "sql_error_prompt.txt"
        ]
        
        # Guardrails settings
        self.invariant_api_key: str = os.getenv("INVARIANT_API_KEY", "")
        
        # Validate configuration
        self._validate()

    def _validate(self) -> None:
        """Validate configuration settings.
        
        Raises:
            ValueError: If required files are missing or settings are invalid
        """
        if not self.schema_path.exists():
            raise ValueError(f"Schema file not found: {self.schema_path}")
        
        if not self.prompts_path.exists():
            raise ValueError(f"Prompts directory not found: {self.prompts_path}")
        
        for prompt in self.required_prompts:
            if not (self.prompts_path / prompt).exists():
                raise ValueError(f"Required prompt file not found: {prompt}")
        
        if not self.db_url:
            raise ValueError("Database URL must be provided")
            
        if self.pool_size < 1:
            raise ValueError("Pool size must be at least 1")
            
        if self.pool_timeout < 1:
            raise ValueError("Pool timeout must be at least 1 second")

    @property
    def prompt_files(self) -> dict[str, Path]:
        """Get paths to all prompt files.
        
        Returns:
            Dictionary mapping prompt names to file paths
        """
        return {
            prompt: self.prompts_path / prompt 
            for prompt in self.required_prompts
        }

# Global config instance 
config = Config()
