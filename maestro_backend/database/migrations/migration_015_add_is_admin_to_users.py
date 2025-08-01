"""
Migration 015: Add is_admin column to users table
"""

from sqlalchemy import text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "015"
    description = "Add is_admin column to users table"

    def up(self, session):
        """Add is_admin column to users table"""
        try:
            session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;"))
            print("✓ Added is_admin column to users table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'is_admin' already exists in 'users'. Skipping.")
            else:
                raise e

    def down(self, session):
        """Remove is_admin column from users table"""
        # This is not safely reversible in SQLite without data loss.
        # A proper downgrade would involve creating a new table and copying data.
        # For now, we'll just print a warning.
        print("Downgrade for migration 015 is not fully supported in SQLite.")
        pass
