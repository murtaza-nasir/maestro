from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "006"
    description = "Add settings column to users table for user-configurable settings"

    def up(self, connection: Connection):
        # Add settings column to users table
        # Check if column already exists
        result = connection.execute(text("PRAGMA table_info(users);"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'settings' not in columns:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN settings JSON
            """))
        
        connection.commit()

    def down(self, connection: Connection):
        # Note: SQLite doesn't support dropping columns easily
        # In a production environment, you'd need to recreate the table without this column
        # For development, we'll leave the column in place
        pass
