from sqlalchemy import create_engine, pool, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging

logger = logging.getLogger(__name__)

# PostgreSQL connection URL from environment
# Format: postgresql://user:password@host:port/database
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://maestro_user:maestro_password@postgres:5432/maestro_db"
)

# Check if we're using SQLite (for backward compatibility in development)
if DATABASE_URL.startswith("sqlite"):
    # SQLite specific settings
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False},
        echo=False
    )
    logger.warning("Using SQLite database - consider migrating to PostgreSQL for production")
else:
    # PostgreSQL specific settings
    # Use QueuePool for proper connection pooling
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,  # Number of persistent connections
        max_overflow=10,  # Maximum overflow connections
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
        echo=False,  # Set to True for SQL query debugging
        future=True,  # Use SQLAlchemy 2.0 style
        connect_args={
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000"  # 30 second statement timeout
        }
    )
    logger.info(f"Connected to PostgreSQL database: {DATABASE_URL.split('@')[1].split('/')[0]}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    try:
        # Import all models to ensure they're registered with Base
        from . import models
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        return False
