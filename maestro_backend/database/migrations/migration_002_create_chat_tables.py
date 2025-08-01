"""
Migration 002: Create chats, messages, and missions tables.
"""

from sqlalchemy import Connection, text
from .base_migration import BaseMigration
import logging

logger = logging.getLogger(__name__)

class Migration002CreateChatTables(BaseMigration):
    """Create chats, messages, and missions tables."""
    
    version = "002"
    description = "Create chats, messages, and missions tables"
    
    def up(self, connection: Connection) -> None:
        """Create the new tables."""
        logger.info("Creating chats, messages, and missions tables...")
        
        # Create chats table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """))
        logger.info("✅ Created chats table")
        
        # Create messages table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                content TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        """))
        logger.info("✅ Created messages table")
        
        # Create missions table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                user_request TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                mission_context TEXT,
                error_info TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        """))
        logger.info("✅ Created missions table")
        
        # Create indexes for better performance
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats (user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_missions_chat_id ON missions (chat_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_missions_status ON missions (status)"))
        logger.info("✅ Created indexes")
        
        logger.info("✅ Migration 002 completed successfully")
    
    def validate(self, connection: Connection) -> bool:
        """Validate that the tables were created correctly."""
        try:
            # Check that all tables exist
            result = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
            tables = [row[0] for row in result.fetchall()]
            
            required_tables = ['chats', 'messages', 'missions']
            for table in required_tables:
                if table not in tables:
                    logger.error(f"Validation failed: {table} table not found")
                    return False
            
            # Check table structures
            for table in required_tables:
                result = connection.execute(text(f"PRAGMA table_info({table});"))
                columns = [row[1] for row in result.fetchall()]
                logger.info(f"{table} table columns: {columns}")
            
            # Check that we can insert and query (basic functionality test)
            # This is a minimal test - in production you might want more thorough validation
            
            logger.info("✅ Migration 002 validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def down(self, connection: Connection) -> None:
        """Drop the created tables."""
        logger.info("Dropping chats, messages, and missions tables...")
        
        # Drop in reverse order due to foreign key constraints
        connection.execute(text("DROP TABLE IF EXISTS missions"))
        connection.execute(text("DROP TABLE IF EXISTS messages"))
        connection.execute(text("DROP TABLE IF EXISTS chats"))
        
        logger.info("✅ Tables dropped successfully")
