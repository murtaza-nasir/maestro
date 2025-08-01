from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "009"
    description = "Create writing_sessions, drafts, and references tables for Writing View"

    def up(self, connection: Connection):
        # Create writing_sessions table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS writing_sessions (
                id VARCHAR PRIMARY KEY,
                chat_id VARCHAR NOT NULL,
                document_group_id VARCHAR,
                use_web_search BOOLEAN DEFAULT TRUE,
                current_draft_id VARCHAR,
                settings JSON,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(chat_id) REFERENCES chats(id),
                FOREIGN KEY(document_group_id) REFERENCES document_groups(id)
            );
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_writing_sessions_id ON writing_sessions (id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_writing_sessions_chat_id ON writing_sessions (chat_id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_writing_sessions_document_group_id ON writing_sessions (document_group_id);"))

        # Create drafts table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS drafts (
                id VARCHAR PRIMARY KEY,
                writing_session_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                content JSON NOT NULL,
                version INTEGER DEFAULT 1,
                is_current BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(writing_session_id) REFERENCES writing_sessions(id)
            );
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_drafts_id ON drafts (id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_drafts_writing_session_id ON drafts (writing_session_id);"))

        # Create draft_references table (avoiding 'references' reserved keyword)
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS draft_references (
                id VARCHAR PRIMARY KEY,
                draft_id VARCHAR NOT NULL,
                document_id VARCHAR,
                web_url VARCHAR,
                citation_text TEXT NOT NULL,
                context TEXT,
                reference_type VARCHAR NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(draft_id) REFERENCES drafts(id),
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );
        """))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_draft_references_id ON draft_references (id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_draft_references_draft_id ON draft_references (draft_id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_draft_references_document_id ON draft_references (document_id);"))

    def down(self, connection: Connection):
        # Drop tables in reverse order due to foreign key constraints
        connection.execute(text("DROP INDEX IF EXISTS ix_draft_references_document_id;"))
        connection.execute(text("DROP INDEX IF EXISTS ix_draft_references_draft_id;"))
        connection.execute(text("DROP INDEX IF EXISTS ix_draft_references_id;"))
        connection.execute(text("DROP TABLE IF EXISTS draft_references;"))
        
        connection.execute(text("DROP INDEX IF EXISTS ix_drafts_writing_session_id;"))
        connection.execute(text("DROP INDEX IF EXISTS ix_drafts_id;"))
        connection.execute(text("DROP TABLE IF EXISTS drafts;"))
        
        connection.execute(text("DROP INDEX IF EXISTS ix_writing_sessions_document_group_id;"))
        connection.execute(text("DROP INDEX IF EXISTS ix_writing_sessions_chat_id;"))
        connection.execute(text("DROP INDEX IF EXISTS ix_writing_sessions_id;"))
        connection.execute(text("DROP TABLE IF EXISTS writing_sessions;"))

    def validate(self, connection: Connection) -> bool:
        """Validate that the migration was applied correctly."""
        try:
            # Check if all tables exist
            tables = ['writing_sessions', 'drafts', 'draft_references']
            for table in tables:
                result = connection.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';"))
                if not result.fetchone():
                    return False
            
            # Check if indexes exist
            indexes = [
                'ix_writing_sessions_id', 'ix_writing_sessions_chat_id', 'ix_writing_sessions_document_group_id',
                'ix_drafts_id', 'ix_drafts_writing_session_id',
                'ix_draft_references_id', 'ix_draft_references_draft_id', 'ix_draft_references_document_id'
            ]
            for index in indexes:
                result = connection.execute(text(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index}';"))
                if not result.fetchone():
                    return False
            
            return True
        except Exception:
            return False
