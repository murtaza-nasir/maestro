"""
Database Models for Maestro Application

This module defines the SQLAlchemy ORM models for the PostgreSQL database.
The application uses a unified architecture:
1. PostgreSQL database - All application data, users, chats, documents with metadata
2. Vector store (ChromaDB) - Document embeddings and chunks for semantic search
3. File storage - Original documents and converted markdown

For detailed architecture documentation, see: docs/DATABASE_ARCHITECTURE.md
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Table, Boolean, Numeric, BigInteger
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
import sqlalchemy
import uuid
from database.database import Base
from database.uuid_type import StringUUID

# Association Table for Document and DocumentGroup
# Enables many-to-many relationship between documents and groups
# A document can belong to multiple groups, and a group can contain multiple documents
document_group_association = Table('document_group_association', Base.metadata,
    Column('document_id', StringUUID, ForeignKey('documents.id'), primary_key=True),
    Column('document_group_id', StringUUID, ForeignKey('document_groups.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)  # Added to match PostgreSQL schema
    hashed_password = Column(String)
    
    # User Profile Fields
    full_name = Column(String, nullable=True)
    location = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    
    # Appearance Settings
    theme = Column(String, nullable=True)
    color_scheme = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    settings = Column(JSONB, nullable=True)  # Store user settings as JSONB for PostgreSQL
    
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String, default="user", nullable=False)
    user_type = Column(String, default="individual", nullable=False)
    
    # Relationships
    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")

class Chat(Base):
    __tablename__ = "chats"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_group_id = Column(StringUUID, ForeignKey("document_groups.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    chat_type = Column(String, nullable=False, default="research", index=True)  # 'research' or 'writing'
    settings = Column(JSONB, nullable=True)  # Store chat-specific settings (web search, doc group, etc.)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="chats")
    document_group = relationship("DocumentGroup", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at")
    missions = relationship("Mission", back_populates="chat", cascade="all, delete-orphan", order_by="Mission.created_at")

class Message(Base):
    __tablename__ = "messages"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    chat_id = Column(StringUUID, ForeignKey("chats.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    sources = Column(JSONB, nullable=True)  # Store sources as JSONB for assistant messages
    created_at = Column(DateTime(timezone=True))
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")

class Mission(Base):
    __tablename__ = "missions"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    chat_id = Column(StringUUID, ForeignKey("chats.id"), nullable=False, index=True)
    user_request = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)  # pending, running, completed, stopped, failed
    mission_context = Column(JSONB, nullable=True)  # Store the full mission context as JSONB
    error_info = Column(Text, nullable=True)
    generated_document_group_id = Column(StringUUID, ForeignKey("document_groups.id"), nullable=True, index=True)  # Document group created from this mission
    current_report_version = Column(Integer, default=1)  # Track current version of the research report
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    
    # Relationships
    chat = relationship("Chat", back_populates="missions")
    execution_logs = relationship("MissionExecutionLog", back_populates="mission", cascade="all, delete-orphan", order_by="MissionExecutionLog.created_at")
    generated_document_group = relationship("DocumentGroup", foreign_keys=[generated_document_group_id], backref="source_missions")

class MissionExecutionLog(Base):
    __tablename__ = "mission_execution_logs"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    mission_id = Column(StringUUID, ForeignKey("missions.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    agent_name = Column(String, nullable=False, index=True)
    action = Column(Text, nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="success", index=True)  # success, failure, warning, running
    error_message = Column(Text, nullable=True)
    
    # Detailed logging fields
    full_input = Column(JSONB, nullable=True)
    full_output = Column(JSONB, nullable=True)
    model_details = Column(JSONB, nullable=True)
    tool_calls = Column(JSONB, nullable=True)
    file_interactions = Column(JSONB, nullable=True)
    
    # Cost and token tracking
    cost = Column(Numeric(10, 6), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    native_tokens = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False)
    
    # Relationships
    mission = relationship("Mission", back_populates="execution_logs")

class Document(Base):
    """
    Document model represents uploaded documents in the system.
    
    This table stores basic document records and processing status.
    The actual document content is processed and stored in:
    - AI researcher database (metadata.db) for extracted metadata
    - ChromaDB vector store for embeddings and chunks
    - File system for original PDFs and converted markdown
    
    Processing workflow:
    1. Document uploaded → status='pending'
    2. Processing starts → status='processing'
    3. Successfully processed → status='completed'
    4. Processing failed → status='failed' with error in processing_error
    """
    __tablename__ = "documents"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)  # Primary field matching PostgreSQL schema
    original_filename = Column(String, nullable=True)  # For backward compatibility
    metadata_ = Column(JSONB, nullable=True)  # Document metadata stored as JSONB
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    
    # Enhanced document management fields
    processing_status = Column(String, nullable=False, default="pending", index=True)  # pending, uploading, processing, completed, failed
    upload_progress = Column(Integer, default=0)  # 0-100
    processing_error = Column(Text, nullable=True)  # Error messages during processing
    file_size = Column(BigInteger, nullable=True)  # File size in bytes
    
    # Additional fields from database schema
    file_path = Column(String(255), nullable=True)  # Path to the original PDF file
    raw_file_path = Column(Text, nullable=True)
    markdown_path = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    dense_collection_name = Column(String(100), default='documents_dense')
    sparse_collection_name = Column(String(100), default='documents_sparse')

    # Relationships
    user = relationship("User")
    groups = relationship("DocumentGroup", secondary=document_group_association, back_populates="documents")
    processing_jobs = relationship("DocumentProcessingJob", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        # If original_filename is provided but not filename, copy it
        if 'original_filename' in kwargs and 'filename' not in kwargs:
            kwargs['filename'] = kwargs['original_filename']
        # If filename is provided but not original_filename, copy it
        elif 'filename' in kwargs and 'original_filename' not in kwargs:
            kwargs['original_filename'] = kwargs['filename']
        super().__init__(**kwargs)

class DocumentGroup(Base):
    __tablename__ = "document_groups"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    source_mission_id = Column(StringUUID, ForeignKey("missions.id"), nullable=True, index=True)  # Mission this group was generated from
    auto_generated = Column(Boolean, default=False)  # Whether this group was auto-generated
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User")
    documents = relationship("Document", secondary=document_group_association, back_populates="groups")
    chats = relationship("Chat", back_populates="document_group")

class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(StringUUID, ForeignKey("documents.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_type = Column(String, nullable=False, default="process_document")  # process_document, upload, etc.
    status = Column(String, nullable=False, default="pending", index=True)  # pending, running, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    document = relationship("Document", back_populates="processing_jobs")
    user = relationship("User")

class WritingSession(Base):
    __tablename__ = "writing_sessions"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    chat_id = Column(StringUUID, ForeignKey("chats.id"), nullable=False, index=True)
    document_group_id = Column(StringUUID, ForeignKey("document_groups.id"), nullable=True, index=True)
    use_web_search = Column(Boolean, default=True)
    current_draft_id = Column(StringUUID, nullable=True)  # References the active draft
    settings = Column(JSONB, nullable=True)  # Writing-specific settings
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    chat = relationship("Chat")
    document_group = relationship("DocumentGroup")
    drafts = relationship("Draft", back_populates="writing_session", cascade="all, delete-orphan")

class Draft(Base):
    __tablename__ = "drafts"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    writing_session_id = Column(StringUUID, ForeignKey("writing_sessions.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)  # Store content as a single Markdown text block
    version = Column(Integer, default=1)  # Version number for draft history
    is_current = Column(Boolean, default=True)  # Whether this is the current active draft
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    writing_session = relationship("WritingSession", back_populates="drafts")
    references = relationship("Reference", back_populates="draft", cascade="all, delete-orphan")

class Reference(Base):
    __tablename__ = "draft_references"

    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    draft_id = Column(StringUUID, ForeignKey("drafts.id"), nullable=False, index=True)
    document_id = Column(StringUUID, ForeignKey("documents.id"), nullable=True, index=True)  # For RAG document references
    web_url = Column(String, nullable=True)  # For web search references
    citation_text = Column(Text, nullable=False)  # The actual citation text
    context = Column(Text, nullable=True)  # Context where this reference is used
    reference_type = Column(String, nullable=False)  # 'document' or 'web'
    created_at = Column(DateTime(timezone=True))

    # Relationships
    draft = relationship("Draft", back_populates="references")
    document = relationship("Document")

class WritingSessionStats(Base):
    __tablename__ = "writing_session_stats"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(StringUUID, ForeignKey("writing_sessions.id"), nullable=False, index=True, unique=True)
    total_cost = Column(Numeric(10, 6), default=0.0)
    total_prompt_tokens = Column(Integer, default=0)
    total_completion_tokens = Column(Integer, default=0)
    total_native_tokens = Column(Integer, default=0)
    total_web_searches = Column(Integer, default=0)
    total_document_searches = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    writing_session = relationship("WritingSession")

class DocumentChunk(Base):
    """
    Stores dense and sparse embeddings for document chunks.
    Uses pgvector for dense embeddings and JSONB for sparse embeddings.
    """
    __tablename__ = "document_chunks"
    
    id = Column(StringUUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_id = Column(StringUUID, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    chunk_id = Column(String(255), unique=True, nullable=False, index=True)  # Format: {doc_id}_{chunk_index}
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    dense_embedding = Column(Text, nullable=True)  # Will be handled as vector type by pgvector
    sparse_embedding = Column(JSONB, nullable=False, default={})  # Stores {token_id: weight} pairs
    chunk_metadata = Column(JSONB, nullable=False, default={})  # Renamed from metadata to avoid SQLAlchemy reserved word
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship to Document
    document = relationship("Document", back_populates="chunks")

class ResearchReport(Base):
    """
    Stores versioned research reports for missions.
    Each mission can have multiple report versions.
    """
    __tablename__ = "research_reports"
    
    id = Column(StringUUID, primary_key=True, default=uuid.uuid4, index=True)
    mission_id = Column(StringUUID, ForeignKey("missions.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    is_current = Column(Boolean, default=True, index=True)
    revision_notes = Column(Text, nullable=True)  # Notes about what was revised
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    mission = relationship("Mission", backref=backref("research_reports", cascade="all, delete-orphan"))
    
    __table_args__ = (
        # Ensure unique version numbers per mission
        sqlalchemy.UniqueConstraint('mission_id', 'version', name='uq_mission_version'),
        # Index for finding current report quickly
        sqlalchemy.Index('idx_mission_current', 'mission_id', 'is_current'),
    )

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
