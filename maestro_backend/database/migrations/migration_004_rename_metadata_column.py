from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "004"
    description = "Ensure metadata column in documents table is named metadata_"

    def up(self, connection: Connection):
        result = connection.execute(text("PRAGMA table_info(documents);"))
        columns = [row[1] for row in result.fetchall()]
        if 'metadata_' not in columns:
            if 'metadata' in columns:
                connection.execute(text("ALTER TABLE documents RENAME COLUMN metadata TO metadata_"))
            else:
                connection.execute(text("ALTER TABLE documents ADD COLUMN metadata_ JSON"))

    def down(self, connection: Connection):
        result = connection.execute(text("PRAGMA table_info(documents);"))
        columns = [row[1] for row in result.fetchall()]
        if 'metadata' not in columns and 'metadata_' in columns:
            connection.execute(text("ALTER TABLE documents RENAME COLUMN metadata_ TO metadata"))
