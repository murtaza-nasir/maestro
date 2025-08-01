from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "005"
    description = "Enhance document schema for background processing and progress tracking"

    def up(self, connection: Connection):
        # Add new columns to documents table for enhanced document management
        
        # Check existing columns first
        result = connection.execute(text("PRAGMA table_info(documents);"))
        columns = [row[1] for row in result.fetchall()]
        
        # Add processing_status column
        if 'processing_status' not in columns:
            connection.execute(text("""
                ALTER TABLE documents 
                ADD COLUMN processing_status VARCHAR DEFAULT 'pending'
            """))
        
        # Add upload_progress column (0-100)
        if 'upload_progress' not in columns:
            connection.execute(text("""
                ALTER TABLE documents 
                ADD COLUMN upload_progress INTEGER DEFAULT 0
            """))
        
        # Add processing_error column for error messages
        if 'processing_error' not in columns:
            connection.execute(text("""
                ALTER TABLE documents 
                ADD COLUMN processing_error TEXT
            """))
        
        # Add file_size column (in bytes)
        if 'file_size' not in columns:
            connection.execute(text("""
                ALTER TABLE documents 
                ADD COLUMN file_size INTEGER
            """))
        
        # Add file_path column for storing original file location
        if 'file_path' not in columns:
            connection.execute(text("""
                ALTER TABLE documents 
                ADD COLUMN file_path VARCHAR
            """))
        
        # Create document_processing_jobs table for background job tracking
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS document_processing_jobs (
                id VARCHAR PRIMARY KEY,
                document_id VARCHAR NOT NULL,
                user_id INTEGER NOT NULL,
                job_type VARCHAR NOT NULL DEFAULT 'process_document',
                status VARCHAR NOT NULL DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """))
        
        # Create indexes for efficient queries
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_processing_status ON documents (processing_status);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_user_id_status ON documents (user_id, processing_status);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_document_processing_jobs_id ON document_processing_jobs (id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_document_processing_jobs_document_id ON document_processing_jobs (document_id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_document_processing_jobs_user_id ON document_processing_jobs (user_id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_document_processing_jobs_status ON document_processing_jobs (status);"))

    def down(self, connection: Connection):
        # Drop the processing jobs table
        connection.execute(text("DROP TABLE IF EXISTS document_processing_jobs;"))
        
        # Note: SQLite doesn't support dropping columns easily
        # In a production environment, you'd need to recreate the table without these columns
        # For development, we'll leave the columns in place
        pass
