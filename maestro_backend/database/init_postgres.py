#!/usr/bin/env python3
"""
PostgreSQL Database Initialization Script
Ensures the database is properly set up with all required extensions and tables
"""

import os
import sys
import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import DATABASE_URL, Base, engine, init_db, test_connection
from database import models  # Import all models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def wait_for_database(max_retries=30, retry_interval=2):
    """Wait for database to be available"""
    for attempt in range(max_retries):
        try:
            if test_connection():
                logger.info("Database is ready!")
                return True
        except Exception as e:
            logger.warning(f"Database not ready yet (attempt {attempt + 1}/{max_retries}): {str(e)}")
            time.sleep(retry_interval)
    
    logger.error("Database did not become available in time")
    return False

def ensure_extensions():
    """Ensure required PostgreSQL extensions are installed"""
    try:
        with engine.connect() as conn:
            # Ensure UUID extension
            result = conn.execute(text(
                "SELECT * FROM pg_extension WHERE extname = 'uuid-ossp'"
            ))
            if not result.fetchone():
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"))
                conn.commit()
                logger.info("UUID extension installed")
            else:
                logger.info("UUID extension already exists")
            
            # Ensure pgvector extension
            result = conn.execute(text(
                "SELECT * FROM pg_extension WHERE extname = 'vector'"
            ))
            if not result.fetchone():
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
                logger.info("PGVector extension installed")
            else:
                logger.info("PGVector extension already exists")
    except Exception as e:
        logger.error(f"Failed to ensure extensions: {str(e)}")
        raise

def create_tables():
    """Create all database tables"""
    try:
        # Create all tables defined in models
        Base.metadata.create_all(bind=engine)
        logger.info("All database tables created successfully")
        
        # List created tables
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))
            tables = [row[0] for row in result]
            logger.info(f"Created tables: {', '.join(tables)}")
            
    except Exception as e:
        logger.error(f"Failed to create tables: {str(e)}")
        raise

def create_default_admin():
    """Create a default admin user if none exists"""
    from sqlalchemy.orm import Session
    from libpass.context import CryptContext
    from datetime import datetime, timezone
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    try:
        with Session(engine) as session:
            # Check if any admin exists
            admin_exists = session.query(models.User).filter_by(is_admin=True).first()
            if not admin_exists:
                # Get admin credentials from environment or use defaults
                admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
                admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
                
                # Create default admin
                admin = models.User(
                    username=admin_username,
                    email="admin@maestro.local",  # Added email field
                    hashed_password=pwd_context.hash(admin_password),
                    full_name="System Administrator",
                    is_admin=True,
                    is_active=True,
                    role="admin",
                    user_type="admin",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(admin)
                session.commit()
                logger.info(f"Default admin user created (username: {admin_username})")
                if admin_password == 'admin123':
                    logger.warning("⚠️  IMPORTANT: Using default password - change immediately!")
                else:
                    logger.info("Admin user created with custom password from environment")
            else:
                logger.info("Admin user already exists")
    except Exception as e:
        logger.error(f"Failed to create default admin: {str(e)}")

def verify_database_setup():
    """Verify that the database is properly set up"""
    try:
        with engine.connect() as conn:
            # Check UUID extension
            result = conn.execute(text(
                "SELECT * FROM pg_extension WHERE extname = 'uuid-ossp'"
            ))
            if not result.fetchone():
                logger.error("UUID extension not found!")
                return False
            
            # Check pgvector extension
            result = conn.execute(text(
                "SELECT * FROM pg_extension WHERE extname = 'vector'"
            ))
            if not result.fetchone():
                logger.error("PGVector extension not found!")
                return False
            
            # Check critical tables
            critical_tables = [
                'users', 'documents', 'document_groups', 
                'chats', 'messages', 'writing_sessions'
            ]
            
            for table in critical_tables:
                result = conn.execute(text(
                    f"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '{table}')"
                ))
                if not result.scalar():
                    logger.error(f"Table '{table}' not found!")
                    return False
            
            logger.info("Database setup verified successfully")
            return True
            
    except Exception as e:
        logger.error(f"Database verification failed: {str(e)}")
        return False

def run_sql_migrations():
    """Run SQL migration files for existing databases"""
    try:
        import glob
        import os
        
        # Get the init-db directory path
        init_db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'init-db')
        
        if os.path.exists(init_db_dir):
            # Get all SQL files sorted by name
            sql_files = sorted(glob.glob(os.path.join(init_db_dir, '*.sql')))
            
            for sql_file in sql_files:
                filename = os.path.basename(sql_file)
                # Skip the main schema files, only run migration files
                # Run migration files that start with 03- or higher numbers
                if any(filename.startswith(f'{num:02d}-') for num in range(3, 100)):
                    logger.info(f"Running migration: {filename}")
                    try:
                        with open(sql_file, 'r') as f:
                            sql_content = f.read()
                        
                        with engine.connect() as conn:
                            # Execute the migration SQL
                            conn.execute(text(sql_content))
                            conn.commit()
                            logger.info(f"✅ Migration {filename} completed")
                    except Exception as e:
                        # Log but don't fail - migration might already be applied
                        logger.warning(f"Migration {filename} skipped or already applied: {str(e)}")
        
        logger.info("SQL migrations check completed")
        
    except Exception as e:
        logger.error(f"Error running SQL migrations: {str(e)}")

def main():
    """Main initialization function"""
    logger.info("Starting PostgreSQL database initialization...")
    
    # Skip if using SQLite
    if DATABASE_URL.startswith("sqlite"):
        logger.info("Using SQLite database, skipping PostgreSQL initialization")
        init_db()
        return
    
    # Wait for database to be available
    if not wait_for_database():
        sys.exit(1)
    
    # Ensure required extensions
    ensure_extensions()
    
    # Create tables
    create_tables()
    
    # Run SQL migrations for existing databases
    run_sql_migrations()
    
    # Create default admin
    create_default_admin()
    
    # Verify setup
    if verify_database_setup():
        logger.info("✅ PostgreSQL database initialization completed successfully!")
    else:
        logger.error("❌ Database setup verification failed")
        sys.exit(1)

if __name__ == "__main__":
    main()