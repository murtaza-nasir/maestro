"""
Migration 013: Add writing_session_stats table for tracking usage statistics
"""

from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration013AddWritingSessionStats(BaseMigration):
    version = "013"
    description = "Add writing_session_stats table for tracking usage statistics"
    
    def __init__(self):
        super().__init__()
    
    def up(self, connection: Connection) -> None:
        """Apply the migration"""
        
        # First check if table already exists
        result = connection.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='writing_session_stats'
        """)).fetchone()
        
        if result:
            print("✓ writing_session_stats table already exists")
            return
        
        # Create writing_session_stats table
        connection.execute(text("""
            CREATE TABLE writing_session_stats (
                id TEXT PRIMARY KEY,
                writing_session_id TEXT NOT NULL,
                total_cost DECIMAL(10, 6) DEFAULT 0.0,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                native_tokens INTEGER DEFAULT 0,
                web_searches INTEGER DEFAULT 0,
                document_searches INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (writing_session_id) REFERENCES writing_sessions (id) ON DELETE CASCADE,
                UNIQUE(writing_session_id)
            )
        """))
        
        # Create index for faster lookups
        connection.execute(text("""
            CREATE INDEX idx_writing_session_stats_session_id 
            ON writing_session_stats(writing_session_id)
        """))
        
        # Create trigger to update updated_at timestamp
        connection.execute(text("""
            CREATE TRIGGER update_writing_session_stats_updated_at
            AFTER UPDATE ON writing_session_stats
            FOR EACH ROW
            BEGIN
                UPDATE writing_session_stats 
                SET updated_at = CURRENT_TIMESTAMP 
                WHERE id = NEW.id;
            END
        """))
        
        connection.commit()
        print("✓ Created writing_session_stats table with indexes and triggers")
    
    def down(self, connection: Connection) -> None:
        """Rollback the migration"""
        
        # Drop trigger
        connection.execute(text("DROP TRIGGER IF EXISTS update_writing_session_stats_updated_at"))
        
        # Drop index
        connection.execute(text("DROP INDEX IF EXISTS idx_writing_session_stats_session_id"))
        
        # Drop table
        connection.execute(text("DROP TABLE IF EXISTS writing_session_stats"))
        
        connection.commit()
        print("✓ Dropped writing_session_stats table, indexes, and triggers")
