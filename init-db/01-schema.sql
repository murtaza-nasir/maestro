-- Complete PostgreSQL Schema for MAESTRO Application
-- This schema EXACTLY matches the SQLAlchemy models in database/models.py
-- Generated from comprehensive analysis of all model definitions

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables if they exist (for clean rebuild)
DROP TABLE IF EXISTS draft_references CASCADE;
DROP TABLE IF EXISTS drafts CASCADE;
DROP TABLE IF EXISTS writing_session_stats CASCADE;
DROP TABLE IF EXISTS writing_sessions CASCADE;
DROP TABLE IF EXISTS document_processing_jobs CASCADE;
DROP TABLE IF EXISTS document_group_association CASCADE;
DROP TABLE IF EXISTS document_group_members CASCADE;
DROP TABLE IF EXISTS document_groups CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS mission_execution_logs CASCADE;
DROP TABLE IF EXISTS missions CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chats CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Users table (Integer ID as per SQLAlchemy model)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    
    -- User Profile Fields
    full_name VARCHAR(255),
    location VARCHAR(255),
    job_title VARCHAR(255),
    
    -- Appearance Settings
    theme VARCHAR(50),
    color_scheme VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Settings stored as JSONB
    settings JSONB,
    
    -- Admin and status fields
    is_admin BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    role VARCHAR(50) DEFAULT 'user' NOT NULL,
    user_type VARCHAR(50) DEFAULT 'individual' NOT NULL
);

-- Document Groups table
CREATE TABLE document_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Documents table
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255),
    metadata_ JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    
    -- Processing status fields
    processing_status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    upload_progress INTEGER DEFAULT 0,
    processing_error TEXT,
    file_size BIGINT,
    file_path VARCHAR(255),
    
    -- Extracted metadata (stored in metadata_ JSONB)
    -- This includes: title, authors, abstract, keywords, year, file_type, content_hash
    
    -- Additional fields from original schema (if needed)
    raw_file_path TEXT,
    markdown_path TEXT,
    chunk_count INTEGER DEFAULT 0,
    dense_collection_name VARCHAR(100) DEFAULT 'documents_dense',
    sparse_collection_name VARCHAR(100) DEFAULT 'documents_sparse'
);

-- Document Group Association (many-to-many)
CREATE TABLE document_group_association (
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    document_group_id UUID NOT NULL REFERENCES document_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, document_group_id)
);

-- Chats table
CREATE TABLE chats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_group_id UUID REFERENCES document_groups(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    chat_type VARCHAR(50) DEFAULT 'research' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    role VARCHAR(20) NOT NULL, -- user, assistant, system
    sources JSONB, -- Store sources as JSONB for assistant messages
    created_at TIMESTAMP WITH TIME ZONE
);

-- Missions table
CREATE TABLE missions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    user_request TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL, -- pending, running, completed, stopped, failed
    mission_context JSONB,
    error_info TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Mission Execution Logs table
CREATE TABLE mission_execution_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id UUID NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    action TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    status VARCHAR(50) DEFAULT 'success' NOT NULL, -- success, failure, warning, running
    error_message TEXT,
    
    -- Detailed logging fields (JSONB)
    full_input JSONB,
    full_output JSONB,
    model_details JSONB,
    tool_calls JSONB,
    file_interactions JSONB,
    
    -- Cost and token tracking
    cost DECIMAL(10, 6),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    native_tokens INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Document Processing Jobs table
CREATE TABLE document_processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_type VARCHAR(50) DEFAULT 'process_document' NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL, -- pending, running, completed, failed
    progress INTEGER DEFAULT 0, -- 0-100
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Writing Sessions table
CREATE TABLE writing_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    document_group_id UUID REFERENCES document_groups(id) ON DELETE SET NULL,
    use_web_search BOOLEAN DEFAULT TRUE,
    current_draft_id UUID,
    settings JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Drafts table
CREATE TABLE drafts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    writing_session_id UUID NOT NULL REFERENCES writing_sessions(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    is_current BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Draft References table
CREATE TABLE draft_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    web_url VARCHAR(255),
    citation_text TEXT NOT NULL,
    context TEXT,
    reference_type VARCHAR(50) NOT NULL, -- document or web
    created_at TIMESTAMP WITH TIME ZONE
);

-- Writing Session Stats table
CREATE TABLE writing_session_stats (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES writing_sessions(id) ON DELETE CASCADE UNIQUE,
    total_cost DECIMAL(10, 6) DEFAULT 0.0,
    total_prompt_tokens INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    total_native_tokens INTEGER DEFAULT 0,
    total_web_searches INTEGER DEFAULT 0,
    total_document_searches INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- System Settings table
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create all necessary indexes for performance
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_processing_status ON documents(processing_status);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);

CREATE INDEX idx_document_groups_user_id ON document_groups(user_id);

CREATE INDEX idx_chats_user_id ON chats(user_id);
CREATE INDEX idx_chats_document_group_id ON chats(document_group_id);
CREATE INDEX idx_chats_chat_type ON chats(chat_type);

CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);

CREATE INDEX idx_missions_chat_id ON missions(chat_id);
CREATE INDEX idx_missions_status ON missions(status);

CREATE INDEX idx_mission_execution_logs_mission_id ON mission_execution_logs(mission_id);
CREATE INDEX idx_mission_execution_logs_agent_name ON mission_execution_logs(agent_name);
CREATE INDEX idx_mission_execution_logs_status ON mission_execution_logs(status);

CREATE INDEX idx_document_processing_jobs_document_id ON document_processing_jobs(document_id);
CREATE INDEX idx_document_processing_jobs_user_id ON document_processing_jobs(user_id);
CREATE INDEX idx_document_processing_jobs_status ON document_processing_jobs(status);

CREATE INDEX idx_writing_sessions_chat_id ON writing_sessions(chat_id);
CREATE INDEX idx_writing_sessions_document_group_id ON writing_sessions(document_group_id);

CREATE INDEX idx_drafts_writing_session_id ON drafts(writing_session_id);
CREATE INDEX idx_drafts_is_current ON drafts(is_current);

CREATE INDEX idx_draft_references_draft_id ON draft_references(draft_id);
CREATE INDEX idx_draft_references_document_id ON draft_references(document_id);

CREATE INDEX idx_writing_session_stats_session_id ON writing_session_stats(session_id);

CREATE INDEX idx_system_settings_key ON system_settings(key);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create update triggers for all tables with updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_document_groups_updated_at BEFORE UPDATE ON document_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chats_updated_at BEFORE UPDATE ON chats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_missions_updated_at BEFORE UPDATE ON missions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_document_processing_jobs_updated_at BEFORE UPDATE ON document_processing_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_writing_sessions_updated_at BEFORE UPDATE ON writing_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_drafts_updated_at BEFORE UPDATE ON drafts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_writing_session_stats_updated_at BEFORE UPDATE ON writing_session_stats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_settings_updated_at BEFORE UPDATE ON system_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default system settings
INSERT INTO system_settings (key, value) VALUES 
    ('app_version', '"1.0.0"'::jsonb),
    ('maintenance_mode', 'false'::jsonb),
    ('max_upload_size_mb', '100'::jsonb),
    ('allowed_file_types', '["pdf", "docx", "doc", "md", "markdown"]'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- Default admin user will be created by Python init script
-- using credentials from environment variables (ADMIN_USERNAME and ADMIN_PASSWORD)

-- Grant permissions to maestro_user (if needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO maestro_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO maestro_user;