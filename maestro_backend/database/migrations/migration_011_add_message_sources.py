"""
Migration 011: Add sources column to messages table
"""

from sqlalchemy import text
from database.migrations.base_migration import BaseMigration

class Migration011AddMessageSources(BaseMigration):
    version = "011"
    description = "Add sources column to messages table"
    
    def up(self, connection):
        """Add sources column to messages table"""
        try:
            # Add sources column as JSON
            connection.execute(text("""
                ALTER TABLE messages 
                ADD COLUMN sources JSON
            """))
            
            print("✓ Added sources column to messages table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'sources' already exists in 'messages'. Skipping.")
            else:
                raise e
    
    def down(self, connection):
        """Remove sources column from messages table"""
        connection.execute(text("""
            ALTER TABLE messages 
            DROP COLUMN sources
        """))
        
        print("✓ Removed sources column from messages table")
