"""
Database Models for Maestro Application

This module defines the SQLAlchemy ORM models for the main application database.
The application uses a dual-database architecture:
1. This main database (maestro.db) - Application data, users, chats, document records
2. AI researcher database (metadata.db) - Extracted document metadata for fast queries
3. Vector store (ChromaDB) - Document embeddings and chunks for semantic search

For detailed architecture documentation, see: docs/DATABASE_ARCHITECTURE.md
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Table, Boolean, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from database.database import Base

# Association Table for Document and DocumentGroup
# Enables many-to-many relationship between documents and groups
# A document can belong to multiple groups, and a group can contain multiple documents
document_group_association = Table('document_group_association', Base.metadata,
    Column('document_id', String, ForeignKey('documents.id'), primary_key=True),
    Column('document_group_id', String, ForeignKey('document_groups.id'), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
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
    settings = Column(JSON, nullable=True)  # Store user settings as JSON
    
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String, default="user", nullable=False)
    user_type = Column(String, default="individual", nullable=False)
    
    # Relationships
    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")

class Chat(Base):
    __tablename__ = "chats"

    id = Column(String, primary_key=True, index=True)  # UUID string
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_group_id = Column(String, ForeignKey("document_groups.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    chat_type = Column(String, nullable=False, default="research", index=True)  # 'research' or 'writing'
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="chats")
    document_group = relationship("DocumentGroup", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at")
    missions = relationship("Mission", back_populates="chat", cascade="all, delete-orphan", order_by="Mission.created_at")

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, index=True)  # UUID string
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    sources = Column(JSON, nullable=True)  # Store sources as JSON for assistant messages
    created_at = Column(DateTime(timezone=True))
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")

class Mission(Base):
    __tablename__ = "missions"

    id = Column(String, primary_key=True, index=True)  # UUID string
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False, index=True)
    user_request = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)  # pending, running, completed, stopped, failed
    mission_context = Column(JSON, nullable=True)  # Store the full mission context as JSON
    error_info = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    
    # Relationships
    chat = relationship("Chat", back_populates="missions")
    execution_logs = relationship("MissionExecutionLog", back_populates="mission", cascade="all, delete-orphan", order_by="MissionExecutionLog.created_at")

class MissionExecutionLog(Base):
    __tablename__ = "mission_execution_logs"

    id = Column(String, primary_key=True, index=True)  # UUID string
    mission_id = Column(String, ForeignKey("missions.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    agent_name = Column(String, nullable=False, index=True)
    action = Column(Text, nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="success", index=True)  # success, failure, warning, running
    error_message = Column(Text, nullable=True)
    
    # Detailed logging fields
    full_input = Column(JSON, nullable=True)
    full_output = Column(JSON, nullable=True)
    model_details = Column(JSON, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    file_interactions = Column(JSON, nullable=True)
    
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

    id = Column(String, primary_key=True, index=True)  # 8-character UUID from the RAG pipeline (e.g., "7fafabb4")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    metadata_ = Column(JSON, nullable=True)  # Cached metadata from AI researcher database
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    
    # Enhanced document management fields
    processing_status = Column(String, nullable=False, default="pending", index=True)  # pending, uploading, processing, completed, failed
    upload_progress = Column(Integer, default=0)  # 0-100
    processing_error = Column(Text, nullable=True)  # Error messages during processing
    file_size = Column(Integer, nullable=True)  # File size in bytes
    file_path = Column(String, nullable=True)  # Path to the original PDF file

    # Relationships
    user = relationship("User")
    groups = relationship("DocumentGroup", secondary=document_group_association, back_populates="documents")
    processing_jobs = relationship("DocumentProcessingJob", back_populates="document", cascade="all, delete-orphan")

class DocumentGroup(Base):
    __tablename__ = "document_groups"

    id = Column(String, primary_key=True, index=True)  # UUID string
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User")
    documents = relationship("Document", secondary=document_group_association, back_populates="groups")
    chats = relationship("Chat", back_populates="document_group")

class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"

    id = Column(String, primary_key=True, index=True)  # UUID string
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
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

    id = Column(String, primary_key=True, index=True)  # UUID string
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False, index=True)
    document_group_id = Column(String, ForeignKey("document_groups.id"), nullable=True, index=True)
    use_web_search = Column(Boolean, default=True)
    current_draft_id = Column(String, nullable=True)  # References the active draft
    settings = Column(JSON, nullable=True)  # Writing-specific settings
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationships
    chat = relationship("Chat")
    document_group = relationship("DocumentGroup")
    drafts = relationship("Draft", back_populates="writing_session", cascade="all, delete-orphan")

class Draft(Base):
    __tablename__ = "drafts"

    id = Column(String, primary_key=True, index=True)  # UUID string
    writing_session_id = Column(String, ForeignKey("writing_sessions.id"), nullable=False, index=True)
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

    id = Column(String, primary_key=True, index=True)  # UUID string
    draft_id = Column(String, ForeignKey("drafts.id"), nullable=False, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)  # For RAG document references
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
    session_id = Column(String, ForeignKey("writing_sessions.id"), nullable=False, index=True, unique=True)
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

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
