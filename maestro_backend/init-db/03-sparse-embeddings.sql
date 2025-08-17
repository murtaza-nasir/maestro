-- Create table for storing sparse embeddings efficiently
-- This uses JSONB to store only non-zero values instead of full 30,000-dimension vectors

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id UUID NOT NULL,
    chunk_id VARCHAR(255) NOT NULL UNIQUE,  -- Format: {doc_id}_{chunk_index}
    chunk_index INTEGER NOT NULL,
    sparse_embedding JSONB NOT NULL,  -- Stores {token_id: weight} pairs
    chunk_metadata JSONB,  -- Additional chunk metadata if needed (renamed to avoid SQLAlchemy reserved word)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key to documents table
    CONSTRAINT fk_document
        FOREIGN KEY (doc_id) 
        REFERENCES documents(id) 
        ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON document_chunks(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunks_sparse_gin ON document_chunks USING GIN(sparse_embedding);  -- GIN index for JSONB queries

-- Add comment explaining the table
COMMENT ON TABLE document_chunks IS 'Stores sparse embeddings for document chunks using JSONB for efficient sparse data storage';
COMMENT ON COLUMN document_chunks.sparse_embedding IS 'Sparse embedding as JSONB - stores only non-zero token_id:weight pairs instead of full 30k vector';