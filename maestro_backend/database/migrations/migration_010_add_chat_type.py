"""
Migration 010: Add chat_type column to chats table
"""

from sqlalchemy import text
from database.migrations.base_migration import BaseMigration
import logging

logger = logging.getLogger(__name__)

class Migration010AddChatType(BaseMigration):
    version = "010"
    description = "Add chat_type column to chats table to distinguish between research and writing chats"
    
    def up(self, connection):
        """Add chat_type column to chats table and set default values."""
        try:
            # Add the chat_type column with default value 'research'
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN chat_type VARCHAR DEFAULT 'research' NOT NULL
            """))
            logger.info("Successfully added chat_type column to chats table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.warning("Column 'chat_type' already exists in 'chats'. Skipping.")
            else:
                logger.error(f"Error adding chat_type column: {e}")
                raise
        
        # Create index on chat_type for better query performance
        connection.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_chats_chat_type ON chats (chat_type)
        """))

    def down(self, connection):
        """Remove chat_type column from chats table."""
        try:
            # Drop the index first
            connection.execute(text("""
                DROP INDEX IF EXISTS ix_chats_chat_type
            """))
            
            # Drop the column
            connection.execute(text("""
                ALTER TABLE chats 
                DROP COLUMN chat_type
            """))
            
            logger.info("Successfully removed chat_type column from chats table")
            
        except Exception as e:
            logger.error(f"Error removing chat_type column: {e}")
            raise

    def validate(self, connection):
        """Validate that the migration was applied correctly."""
        try:
            # Check if the column exists
            result = connection.execute(text("""
                SELECT COUNT(*) 
                FROM pragma_table_info('chats') 
                WHERE name = 'chat_type'
            """))
            
            count = result.scalar()
            return count == 1
            
        except Exception as e:
            logger.error(f"Error validating migration: {e}")
            return False
