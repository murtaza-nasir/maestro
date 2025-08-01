"""
Migration 017: Add role column to users table
"""

from sqlalchemy import text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "017"
    description = "Add role column to users table"

    def up(self, session):
        """Add role column to users table"""
        try:
            session.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user';"))
            print("✓ Added role column to users table")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'role' already exists in 'users'. Skipping.")
            else:
                raise e

    def down(self, session):
        """Remove role column from users table"""
        print("Downgrade for migration 017 is not fully supported in SQLite.")
        pass
