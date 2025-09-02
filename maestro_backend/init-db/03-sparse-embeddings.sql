-- Migration for document_chunks table with dense and sparse embeddings support
-- This migration is idempotent and works for both new and existing installations
-- It ensures pgvector extension is available and creates/updates the document_chunks table

-- First ensure pgvector extension is enabled (in case 04-pgvector.sql hasn't run yet)
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    -- First, check if the table exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'document_chunks'
    ) THEN
        -- Create the table for new installations
        CREATE TABLE document_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            doc_id UUID NOT NULL,
            chunk_id VARCHAR(255) NOT NULL UNIQUE,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            dense_embedding vector(1024),
            sparse_embedding JSONB NOT NULL DEFAULT '{}',
            chunk_metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT fk_document
                FOREIGN KEY (doc_id) 
                REFERENCES documents(id) 
                ON DELETE CASCADE
        );
        
        -- Add unique constraint (checking if it doesn't already exist)
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE table_name = 'document_chunks' 
            AND constraint_type = 'UNIQUE'
        ) THEN
            ALTER TABLE document_chunks ADD CONSTRAINT unique_doc_chunk UNIQUE (doc_id, chunk_index);
        END IF;
        
        RAISE NOTICE 'Table document_chunks created successfully';
    ELSE
        RAISE NOTICE 'Table document_chunks already exists - ensuring all required columns are present';
        
        -- For existing tables, add any missing columns
        
        -- Check and add chunk_text column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'chunk_text'
        ) THEN
            ALTER TABLE document_chunks ADD COLUMN chunk_text TEXT NOT NULL DEFAULT '';
            RAISE NOTICE 'Added chunk_text column to document_chunks';
        END IF;
        
        -- Check and add dense_embedding column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'dense_embedding'
        ) THEN
            ALTER TABLE document_chunks ADD COLUMN dense_embedding vector(1024);
            RAISE NOTICE 'Added dense_embedding column to document_chunks';
        END IF;
        
        -- Check and add sparse_embedding column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'sparse_embedding'
        ) THEN
            ALTER TABLE document_chunks ADD COLUMN sparse_embedding JSONB NOT NULL DEFAULT '{}';
            RAISE NOTICE 'Added sparse_embedding column to document_chunks';
        END IF;
        
        -- Check and add chunk_metadata column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'chunk_metadata'
        ) THEN
            ALTER TABLE document_chunks ADD COLUMN chunk_metadata JSONB NOT NULL DEFAULT '{}';
            RAISE NOTICE 'Added chunk_metadata column to document_chunks';
        END IF;
        
        -- Check and add created_at column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'document_chunks' 
            AND column_name = 'created_at'
        ) THEN
            ALTER TABLE document_chunks ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
            RAISE NOTICE 'Added created_at column to document_chunks';
        END IF;
        
        -- Check and add unique constraint if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE table_name = 'document_chunks' 
            AND constraint_name = 'unique_doc_chunk'
        ) THEN
            -- First check if there's already a unique constraint on (doc_id, chunk_index)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu 
                ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = 'document_chunks' 
                AND tc.constraint_type = 'UNIQUE'
                AND ccu.column_name IN ('doc_id', 'chunk_index')
                GROUP BY tc.constraint_name
                HAVING COUNT(*) = 2
            ) THEN
                ALTER TABLE document_chunks ADD CONSTRAINT unique_doc_chunk UNIQUE (doc_id, chunk_index);
                RAISE NOTICE 'Added unique constraint on (doc_id, chunk_index)';
            END IF;
        END IF;
    END IF;
    
    -- Create indexes (these are idempotent with IF NOT EXISTS)
    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(doc_id);
    CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON document_chunks(chunk_id);
    CREATE INDEX IF NOT EXISTS idx_sparse_embedding_gin ON document_chunks USING GIN(sparse_embedding);
    CREATE INDEX IF NOT EXISTS idx_chunk_metadata_gin ON document_chunks USING GIN(chunk_metadata);
    
    -- Create HNSW index for dense embeddings if the vector extension is available
    IF EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'vector'
    ) THEN
        -- Check if HNSW index exists
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = 'document_chunks' 
            AND indexname = 'idx_dense_embedding_hnsw'
        ) THEN
            BEGIN
                CREATE INDEX idx_dense_embedding_hnsw ON document_chunks 
                USING hnsw (dense_embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64);
                RAISE NOTICE 'Created HNSW index for dense embeddings';
            EXCEPTION 
                WHEN OTHERS THEN
                    RAISE NOTICE 'Could not create HNSW index: %', SQLERRM;
            END;
        END IF;
    END IF;
    
    RAISE NOTICE 'Document chunks table migration completed successfully';
    
EXCEPTION
    WHEN OTHERS THEN
        -- If we get here, something unexpected happened
        -- Log it but don't fail the entire migration
        RAISE WARNING 'Unexpected error in document_chunks migration: %', SQLERRM;
        RAISE WARNING 'The application may still work but please check the document_chunks table structure';
END $$;