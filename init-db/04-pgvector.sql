-- PGVector Schema for Document Embeddings
-- This replaces ChromaDB with PostgreSQL native vector storage

-- Create document_chunks table for vector storage
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id VARCHAR(255) UNIQUE NOT NULL,  -- Format: {doc_id}_{chunk_index}
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    dense_embedding vector(1024),  -- BGE-M3 dense embeddings
    sparse_embedding JSONB NOT NULL DEFAULT '{}',  -- BGE-M3 sparse embeddings (30k dimensions as JSONB)
    chunk_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(doc_id, chunk_index)
);

-- Create HNSW index for dense embeddings (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_dense_embedding_hnsw 
    ON document_chunks 
    USING hnsw (dense_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Create GIN index for JSONB metadata searching
CREATE INDEX IF NOT EXISTS idx_chunk_metadata_gin 
    ON document_chunks 
    USING gin (chunk_metadata);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id 
    ON document_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id 
    ON document_chunks(chunk_id);

-- Create index for sparse embeddings (JSONB)
CREATE INDEX IF NOT EXISTS idx_sparse_embedding_gin 
    ON document_chunks 
    USING gin (sparse_embedding);

-- Add comment to table
COMMENT ON TABLE document_chunks IS 'Storage for document chunks with dense and sparse embeddings';
COMMENT ON COLUMN document_chunks.dense_embedding IS 'BGE-M3 dense embeddings (1024 dimensions)';
COMMENT ON COLUMN document_chunks.sparse_embedding IS 'BGE-M3 sparse embeddings stored as JSONB (30k dimensions)';