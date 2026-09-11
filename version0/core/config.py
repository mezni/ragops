from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Global Application Settings loaded from process environment or .env file."""
    
    # Environment & Logging
    ENV: Environment = Field(default=Environment.DEVELOPMENT, description="Application environment")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    JSON_LOGS: bool = Field(default=True, description="Output logs in JSON format if True")
    
    # PostgreSQL Relational Database
    DATABASE_URL: str = Field(
        default="postgresql://rag_user:rag_password@localhost:5432/rag_db",
        description="Async/Sync SQLAlchemy PostgreSQL connection string"
    )
    
    # Vector Database Configuration
    VECTOR_STORE_PROVIDER: str = Field(default="qdrant", description="Vector database provider (qdrant, pinecone, sqlite)")
    QDRANT_HOST: str = Field(default="localhost", description="Qdrant server host")
    QDRANT_PORT: int = Field(default=6333, description="Qdrant server HTTP port")
    QDRANT_API_KEY: Optional[str] = Field(default=None, description="Qdrant API Key for cloud deployments")
    
    # LLM & Embedding Settings
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="Model used for chunk vectorization")
    GENERATION_MODEL: str = Field(default="gpt-4o-mini", description="Model used for RAG response synthesis")
    
    # Ingestion & Chunking Defaults
    CHUNK_SIZE: int = Field(default=500, description="Target chunk size in tokens/characters")
    CHUNK_OVERLAP: int = Field(default=50, description="Overlap between consecutive chunks")

    @model_validator(mode="after")
    def validate_chunking(self) -> "Settings":
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self
    
    # Pydantic Settings Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore unexpected environment variables
    )


# Instantiated single global configuration object
settings = Settings()