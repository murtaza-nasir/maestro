"""
New Database Configuration for PostgreSQL
Clean implementation without legacy SQLite code
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Database URL from environment or default
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://maestro_user:maestro_password@postgres:5432/maestro_db"
)

# Create engine with proper pooling for PostgreSQL
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # Use NullPool to avoid connection issues in multi-threaded environment
    echo=False,  # Set to True for SQL query logging
    future=True  # Use SQLAlchemy 2.0 style
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency to get database session.
    Usage in FastAPI:
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.
    Note: In production, use Alembic migrations instead.
    """
    from database import models_new
    Base.metadata.create_all(bind=engine)


# Export
__all__ = ['engine', 'SessionLocal', 'Base', 'get_db', 'init_db', 'DATABASE_URL']