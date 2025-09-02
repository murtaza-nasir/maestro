-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- This migration is now handled in 03-sparse-embeddings.sql
-- We only ensure the pgvector extension is enabled here
-- The document_chunks table creation and indexes are managed in 03-sparse-embeddings.sql

-- Add a note for documentation
DO $$
BEGIN
    RAISE NOTICE 'PGVector extension enabled. Table document_chunks is managed by 03-sparse-embeddings.sql';
END $$;