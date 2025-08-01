"""
Database migration to add created_at and updated_at columns to existing users table.
"""

import logging
import os
from sqlalchemy import text, create_engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_add_timestamps():
    """Add timestamp columns to existing users table."""
    try:
        # Use the same database URL as defined in database.py
        database_url = "sqlite:///./data/maestro.db"
        engine = create_engine(database_url)
        
        logger.info("Starting timestamp migration for users table...")
        
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(users);"))
            columns = [row[1] for row in result.fetchall()]
            logger.info(f"Current users table columns: {columns}")
            
            # Add created_at column if it doesn't exist
            if 'created_at' not in columns:
                logger.info("Adding created_at column to users table...")
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                """))
                conn.commit()
                logger.info("✅ Added created_at column")
            else:
                logger.info("created_at column already exists")
            
            # Add updated_at column if it doesn't exist
            if 'updated_at' not in columns:
                logger.info("Adding updated_at column to users table...")
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                """))
                conn.commit()
                logger.info("✅ Added updated_at column")
            else:
                logger.info("updated_at column already exists")
            
            # Verify the changes
            result = conn.execute(text("PRAGMA table_info(users);"))
            columns = [row[1] for row in result.fetchall()]
            logger.info(f"Updated users table columns: {columns}")
        
        return True
        
    except Exception as e:
        logger.error(f"Timestamp migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate_add_timestamps()
    if success:
        print("✅ Timestamp migration completed successfully!")
        exit(0)
    else:
        print("❌ Timestamp migration failed!")
        exit(1)
