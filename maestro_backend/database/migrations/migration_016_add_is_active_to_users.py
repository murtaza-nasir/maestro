"""
Migration 016: Add is_active column to users table
"""

from sqlalchemy import text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "016"
    description = "Add is_active column to users table"

    def up(self, session):
        """Add is_active column to users table"""
        try:
            session.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;"))
            print("✓ Added is_active column to users table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'is_active' already exists in 'users'. Skipping.")
            else:
                raise e

    def down(self, session):
        """Remove is_active column from users table"""
        print("Downgrade for migration 016 is not fully supported in SQLite.")
        pass
