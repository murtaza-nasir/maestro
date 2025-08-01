"""
Migration 018: Add user_type column to users table
"""

from sqlalchemy import text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "018"
    description = "Add user_type column to users table"

    def up(self, session):
        """Add user_type column to users table"""
        try:
            session.execute(text("ALTER TABLE users ADD COLUMN user_type VARCHAR(50) NOT NULL DEFAULT 'individual';"))
            print("✓ Added user_type column to users table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'user_type' already exists in 'users'. Skipping.")
            else:
                raise e

    def down(self, session):
        """Remove user_type column from users table"""
        print("Downgrade for migration 018 is not fully supported in SQLite.")
        pass
