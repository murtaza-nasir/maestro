from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "003"
    description = "Create document, document_group, and association tables"

    def up(self, connection: Connection):
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id VARCHAR PRIMARY KEY,
                user_id INTEGER NOT NULL,
                original_filename VARCHAR NOT NULL,
                metadata JSON,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_id ON documents (id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id);"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS document_groups (
                id VARCHAR PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR NOT NULL,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_document_groups_id ON document_groups (id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_document_groups_user_id ON document_groups (user_id);"))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS document_group_association (
                document_id VARCHAR NOT NULL,
                document_group_id VARCHAR NOT NULL,
                PRIMARY KEY (document_id, document_group_id),
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(document_group_id) REFERENCES document_groups(id)
            );
        """))

        # Adding a column with ALTER TABLE is tricky with idempotency.
        # We'll check if the column exists first.
        result = connection.execute(text("PRAGMA table_info(chats);"))
        columns = [row[1] for row in result.fetchall()]
        if 'document_group_id' not in columns:
            connection.execute(text("ALTER TABLE chats ADD COLUMN document_group_id VARCHAR;"))
        
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_chats_document_group_id ON chats (document_group_id);"))

    def down(self, connection: Connection):
        # Note: SQLite makes dropping columns and constraints difficult.
        # This downgrade path is simplified and may require manual intervention in a real scenario.
        connection.execute(text("DROP INDEX ix_chats_document_group_id;"))
        # The following line would be ideal, but ALTER TABLE DROP COLUMN is not supported in all SQLite versions.
        # connection.execute(text("ALTER TABLE chats DROP COLUMN document_group_id;"))
        connection.execute(text("DROP TABLE document_group_association;"))
        connection.execute(text("DROP TABLE document_groups;"))
        connection.execute(text("DROP TABLE documents;"))
