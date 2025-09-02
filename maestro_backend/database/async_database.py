"""
Async database configuration using SQLAlchemy with asyncpg driver.
This provides non-blocking database operations for the application.
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Get the base PostgreSQL URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://maestro_user:maestro_password@postgres:5432/maestro_db"
)

# Convert to async PostgreSQL URL for asyncpg driver
# Replace postgresql:// with postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
elif DATABASE_URL.startswith("postgres://"):
    # Handle Heroku-style URLs
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://")
else:
    # Fallback for other formats or SQLite (which won't work with async)
    logger.error(f"Unsupported database URL format for async: {DATABASE_URL}")
    ASYNC_DATABASE_URL = None

# Create async engine
if ASYNC_DATABASE_URL:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        # Use NullPool to avoid connection pool issues in async context
        poolclass=NullPool,
        echo=False,  # Set to True for SQL query debugging
        future=True,  # Use SQLAlchemy 2.0 style
    )
    
    # Alternative: Use proper async pool configuration
    # async_engine = create_async_engine(
    #     ASYNC_DATABASE_URL,
    #     pool_size=50,  # Number of persistent connections
    #     max_overflow=30,  # Maximum overflow connections
    #     pool_pre_ping=True,  # Verify connections before using
    #     pool_recycle=3600,  # Recycle connections after 1 hour
    #     echo=False,
    #     future=True,
    # )
    
    logger.info(f"Created async engine for PostgreSQL database")
else:
    async_engine = None
    logger.error("Async database engine not created - invalid database URL")

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False,
)

@asynccontextmanager
async def get_async_db():
    """
    Async context manager for database sessions.
    Usage:
        async with get_async_db() as session:
            result = await session.execute(query)
    """
    if not async_engine:
        raise RuntimeError("Async database engine not initialized")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def get_async_db_session() -> AsyncSession:
    """
    Get an async database session.
    Caller is responsible for closing the session.
    """
    if not async_engine:
        raise RuntimeError("Async database engine not initialized")
    
    return AsyncSessionLocal()

async def test_async_connection():
    """Test async database connection"""
    if not async_engine:
        logger.error("Cannot test connection - async engine not initialized")
        return False
    
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            await result.fetchone()
        logger.info("Async database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Async database connection test failed: {str(e)}")
        return False

async def init_async_db():
    """
    Initialize async database tables.
    Note: Table creation should typically use sync operations at startup.
    This is here for completeness.
    """
    if not async_engine:
        logger.error("Cannot initialize database - async engine not initialized")
        return
    
    try:
        # Import all models to ensure they're registered
        from . import models
        
        # For async, we'd typically use sync operations for DDL
        # or use Alembic for migrations
        logger.info("Async database initialization would typically use sync DDL or migrations")
    except Exception as e:
        logger.error(f"Failed to initialize async database: {str(e)}")
        raise