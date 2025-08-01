"""
Database migration script to add Chat, Message, and Mission tables.
This script will create the new tables while preserving existing User data.
"""

import logging
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Run database migration to add new tables."""
    try:
        # Import here to use the same setup as main.py
        from database.database import engine
        from database.models import Base
        
        logger.info("Starting database migration...")
        
        # Create all tables (this will only create tables that don't exist)
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database migration completed successfully!")
        logger.info("New tables created: chats, messages, missions")
        logger.info("Existing users table preserved")
        
        # Verify tables exist
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
            tables = [row[0] for row in result.fetchall()]
            logger.info(f"Current database tables: {tables}")
            
            # Check if we have any existing users
            result = conn.execute(text("SELECT COUNT(*) FROM users;"))
            user_count = result.fetchone()[0]
            logger.info(f"Existing users in database: {user_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Database migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate_database()
    if success:
        print("✅ Database migration completed successfully!")
        exit(0)
    else:
        print("❌ Database migration failed!")
        exit(1)
