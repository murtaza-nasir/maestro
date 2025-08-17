-- Enable required PostgreSQL extensions
-- This script runs first (00-) to ensure extensions are available for other scripts

-- Enable UUID support
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Show installed extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('uuid-ossp', 'vector');