"""
Migration 001: Add created_at and updated_at columns to users table.
"""

from sqlalchemy import Connection, text
from .base_migration import BaseMigration
import logging

logger = logging.getLogger(__name__)

class Migration001AddUserTimestamps(BaseMigration):
    """Add timestamp columns to existing users table."""
    
    version = "001"
    description = "Add created_at and updated_at columns to users table"
    
    def up(self, connection: Connection) -> None:
        """Add timestamp columns to users table."""
        logger.info("Adding timestamp columns to users table...")
        
        # Check if columns already exist
        result = connection.execute(text("PRAGMA table_info(users);"))
        columns = [row[1] for row in result.fetchall()]
        logger.info(f"Current users table columns: {columns}")
        
        # Add created_at column if it doesn't exist
        if 'created_at' not in columns:
            logger.info("Adding created_at column...")
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN created_at DATETIME
            """))
            logger.info("✅ Added created_at column")
        else:
            logger.info("created_at column already exists")
        
        # Add updated_at column if it doesn't exist
        if 'updated_at' not in columns:
            logger.info("Adding updated_at column...")
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN updated_at DATETIME
            """))
            logger.info("✅ Added updated_at column")
        else:
            logger.info("updated_at column already exists")
        
        # Update existing records to have timestamps
        connection.execute(text("""
            UPDATE users 
            SET created_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP 
            WHERE created_at IS NULL OR updated_at IS NULL
        """))
        
        logger.info("✅ Migration 001 completed successfully")
    
    def validate(self, connection: Connection) -> bool:
        """Validate that the timestamp columns were added correctly."""
        try:
            # Check that columns exist
            result = connection.execute(text("PRAGMA table_info(users);"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'created_at' not in columns:
                logger.error("Validation failed: created_at column not found")
                return False
            
            if 'updated_at' not in columns:
                logger.error("Validation failed: updated_at column not found")
                return False
            
            # Check that existing users have timestamps
            result = connection.execute(text("""
                SELECT COUNT(*) FROM users 
                WHERE created_at IS NULL OR updated_at IS NULL
            """))
            null_count = result.fetchone()[0]
            
            if null_count > 0:
                logger.error(f"Validation failed: {null_count} users have null timestamps")
                return False
            
            logger.info("✅ Migration 001 validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def down(self, connection: Connection) -> None:
        """Remove timestamp columns (SQLite doesn't support DROP COLUMN easily)."""
        logger.warning("SQLite doesn't support DROP COLUMN easily. Manual intervention required for rollback.")
        # In a real scenario, we'd need to recreate the table without these columns
        # For now, we'll just log a warning
