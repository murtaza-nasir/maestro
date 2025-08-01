"""
Migration 012: Add user profile fields to the users table
"""

from sqlalchemy import text
from database.migrations.base_migration import BaseMigration

class Migration012AddUserProfileFields(BaseMigration):
    version = "012"
    description = "Add full_name, location, and job_title to users table"

    def up(self, connection):
        """Add full_name, location, and job_title columns to users table"""
        try:
            connection.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR;"))
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'full_name' already exists in 'users'. Skipping.")
            else:
                raise e
        try:
            connection.execute(text("ALTER TABLE users ADD COLUMN location VARCHAR;"))
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'location' already exists in 'users'. Skipping.")
            else:
                raise e
        try:
            connection.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR;"))
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'job_title' already exists in 'users'. Skipping.")
            else:
                raise e
        print("✓ Added full_name, location, and job_title to users table")

    def down(self, connection):
        """Remove full_name, location, and job_title columns from users table"""
        # SQLite does not support dropping multiple columns in one statement
        connection.execute(text("ALTER TABLE users DROP COLUMN job_title;"))
        connection.execute(text("ALTER TABLE users DROP COLUMN location;"))
        connection.execute(text("ALTER TABLE users DROP COLUMN full_name;"))
        print("✓ Removed full_name, location, and job_title from users table")
