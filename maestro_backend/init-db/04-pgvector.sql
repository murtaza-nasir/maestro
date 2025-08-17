-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop the old document_chunks table if it exists
DROP TABLE IF EXISTS document_chunks CASCADE;

-- Create new document_chunks table with pgvector support
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id UUID NOT NULL,
    chunk_id VARCHAR(255) NOT NULL UNIQUE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,  -- Store the actual text content
    
    -- Vector embeddings using pgvector
    dense_embedding vector(1024),  -- BGE-M3 dense embeddings
    sparse_embedding JSONB NOT NULL,  -- Sparse embeddings as JSONB (only non-zero values)
    
    -- Metadata
    chunk_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key to documents table
    CONSTRAINT fk_document
        FOREIGN KEY (doc_id) 
        REFERENCES documents(id) 
        ON DELETE CASCADE
);

-- Create HNSW index for fast dense vector similarity search
-- HNSW is faster than IVFFlat for most use cases
CREATE INDEX IF NOT EXISTS idx_dense_embedding_hnsw 
    ON document_chunks 
    USING hnsw (dense_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Create indexes for other fields
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON document_chunks(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunks_sparse_gin ON document_chunks USING GIN(sparse_embedding);

-- Add comments
COMMENT ON TABLE document_chunks IS 'Stores document chunks with both dense and sparse embeddings using pgvector';
COMMENT ON COLUMN document_chunks.dense_embedding IS 'Dense embedding vector (1024 dimensions) for similarity search';
COMMENT ON COLUMN document_chunks.sparse_embedding IS 'Sparse embedding as JSONB - stores only non-zero token_id:weight pairs';
COMMENT ON COLUMN document_chunks.chunk_text IS 'The actual text content of the chunk';