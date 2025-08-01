from sqlalchemy import text, Column, DateTime
from .base_migration import BaseMigration
from sqlalchemy.schema import MetaData
from sqlalchemy.engine import Connection

class Migration(BaseMigration):
    version = "008"
    description = "Adds the updated_at column to the documents table."

    def up(self, session: Connection):
        """
        Applies the migration.
        - Adds the `updated_at` column to the `documents` table if it doesn't exist.
        - Backfills the new column with the value from `created_at` for existing rows.
        """
        # Use raw SQL for altering the table. This is a safe way to add a column in SQLite.
        try:
            session.execute(text("ALTER TABLE documents ADD COLUMN updated_at DATETIME"))
            print("Added `updated_at` column to the documents table.")
        except Exception as e:
            # This will likely fail if the column already exists, which is fine.
            # We can safely ignore this error and proceed.
            if "duplicate column name" in str(e).lower():
                print("Column `updated_at` already exists in `documents` table. Skipping add.")
                pass
            else:
                # If it's a different error, we should raise it.
                raise e

        # Backfill the `updated_at` column for existing documents to avoid null values,
        # using the `created_at` value as a sensible default.
        session.execute(text("UPDATE documents SET updated_at = created_at WHERE updated_at IS NULL"))
        
        print("Migration '008_add_updated_at_to_documents' is running.")
        print("Backfilled existing rows for `updated_at`.")

    def downgrade(self, session: Connection):
        """
        Reverts the migration. This is complex in SQLite and often involves recreating the table.
        For now, we will log that this is a placeholder.
        """
        print("Downgrade for '008_add_updated_at_to_documents' is not implemented.")
        pass
