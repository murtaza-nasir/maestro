"""
Create Fresh Database with Unified Architecture

This script creates a new database with the improved unified schema
that merges the AI database into the main database.

Use this for new installations or when you want to start fresh.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Text, Boolean, DateTime, JSON, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base = declarative_base()

# ============= User Models =============

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    
    # Profile fields
    first_name = Column(String(100))
    last_name = Column(String(100))
    bio = Column(Text)
    
    # Role and permissions
    role = Column(String(50), default='user')  # user, admin, super_admin
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    user_type = Column(String(50), default='standard')
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    documents = relationship('Document', back_populates='user', cascade='all, delete-orphan')
    settings = relationship('UserSettings', back_populates='user', uselist=False)

# ============= Document Models (Unified) =============

class Document(Base):
    __tablename__ = 'documents'
    
    # Primary key and relationships
    id = Column(String(8), primary_key=True)  # 8-character UUID
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    
    # Basic document info
    original_filename = Column(String(500), nullable=False)
    file_path = Column(String(1000))
    file_size = Column(Integer)
    
    # Extracted metadata (previously in AI database)
    title = Column(Text)
    authors = Column(Text)  # JSON array as text
    publication_year = Column(Integer)
    journal = Column(Text)
    abstract = Column(Text)
    doi = Column(Text)
    keywords = Column(Text)  # JSON array as text
    extracted_metadata = Column(JSON)  # Full metadata JSON
    
    # Processing tracking (saga pattern)
    processing_status = Column(String(50), default='queued')
    processing_stage = Column(String(50), default='created')
    processing_error = Column(Text)
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    upload_progress = Column(Integer, default=0)
    
    # Component existence flags
    has_ai_metadata = Column(Boolean, default=False)
    has_vector_embeddings = Column(Boolean, default=False)
    has_markdown_file = Column(Boolean, default=False)
    has_pdf_file = Column(Boolean, default=False)
    
    # Chunking and embedding info
    chunk_count = Column(Integer, default=0)
    embedding_model = Column(String(100))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Cached metadata (legacy support)
    metadata_ = Column('metadata', JSON)
    
    # Relationships
    user = relationship('User', back_populates='documents')
    groups = relationship('DocumentGroup', secondary='document_group_association', back_populates='documents')

class DocumentGroup(Base):
    __tablename__ = 'document_groups'
    
    id = Column(String(50), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship('Document', secondary='document_group_association', back_populates='groups')

class DocumentGroupAssociation(Base):
    __tablename__ = 'document_group_association'
    
    document_id = Column(String(8), ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
    group_id = Column(String(50), ForeignKey('document_groups.id', ondelete='CASCADE'), primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)

# ============= Chat Models =============

class Chat(Base):
    __tablename__ = 'chats'
    
    id = Column(String(50), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(500))
    chat_type = Column(String(50), default='research')  # research, writing, general
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship('Message', back_populates='chat', cascade='all, delete-orphan')

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(String(50), primary_key=True)
    chat_id = Column(String(50), ForeignKey('chats.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # Sources for citations
    sources = Column(JSON)
    source_documents = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    token_count = Column(Integer)
    model_used = Column(String(100))
    
    # Relationships
    chat = relationship('Chat', back_populates='messages')

# ============= Settings Models =============

class UserSettings(Base):
    __tablename__ = 'user_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    
    # LLM Settings
    llm_provider = Column(String(50), default='anthropic')
    llm_model = Column(String(100), default='claude-3-5-sonnet-20241022')
    api_key = Column(String(500))
    
    # Research settings
    search_settings = Column(JSON)
    embedding_settings = Column(JSON)
    
    # UI preferences
    theme = Column(String(50), default='light')
    appearance_settings = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship('User', back_populates='settings')

class SystemSettings(Base):
    __tablename__ = 'system_settings'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSON)
    description = Column(Text)
    category = Column(String(50))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey('users.id'))

# ============= Migration Tracking =============

class Migration(Base):
    __tablename__ = 'migrations'
    
    version = Column(Integer, primary_key=True)
    description = Column(String(500))
    applied_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default='applied')

def create_database(db_path: str = "./data/maestro_fresh.db"):
    """Create a fresh database with the unified schema."""
    
    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing database if it exists
    if Path(db_path).exists():
        logger.warning(f"Database already exists at {db_path}")
        response = input("Do you want to delete it and create fresh? (y/n): ")
        if response.lower() != 'y':
            logger.info("Aborted")
            return False
        Path(db_path).unlink()
        logger.info(f"Deleted existing database")
    
    # Create engine and tables
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Add migration record for the unified schema
        migration = Migration(
            version=21,
            description="Unified database schema with merged AI database",
            status="applied"
        )
        session.add(migration)
        
        # Create default admin user
        from werkzeug.security import generate_password_hash
        
        admin = User(
            username="admin",
            email="admin@maestro.ai",
            password_hash=generate_password_hash("admin"),
            role="super_admin",
            is_admin=True,
            first_name="System",
            last_name="Administrator"
        )
        session.add(admin)
        
        # Create default settings for admin
        admin_settings = UserSettings(
            user_id=1,  # Admin will be user 1
            llm_provider="anthropic",
            llm_model="claude-3-5-sonnet-20241022",
            theme="dark"
        )
        session.add(admin_settings)
        
        # Add system settings
        system_settings = [
            SystemSettings(
                key="consistency_check_interval_hours",
                value=12,
                description="Hours between automatic consistency checks",
                category="maintenance"
            ),
            SystemSettings(
                key="document_processing_timeout_minutes",
                value=30,
                description="Maximum time for processing a single document",
                category="processing"
            ),
            SystemSettings(
                key="max_concurrent_processing",
                value=1,
                description="Maximum number of documents to process concurrently",
                category="processing"
            )
        ]
        
        for setting in system_settings:
            session.add(setting)
        
        session.commit()
        logger.info(f"✅ Database created successfully at {db_path}")
        logger.info("✅ Default admin user created (username: admin, password: admin)")
        logger.info("✅ System settings initialized")
        
        # Print summary
        print("\n" + "="*60)
        print("DATABASE CREATED SUCCESSFULLY")
        print("="*60)
        print(f"Location: {db_path}")
        print("\nFeatures:")
        print("✓ Unified schema (AI database merged into main)")
        print("✓ Saga pattern support with processing stages")
        print("✓ Component existence tracking flags")
        print("✓ Full metadata fields in documents table")
        print("✓ Cascade delete constraints")
        print("\nDefault Credentials:")
        print("Username: admin")
        print("Password: admin")
        print("\nNext Steps:")
        print("1. Move the database to ./data/maestro.db to use it")
        print("2. Or update DATABASE_URL to point to the new database")
        print("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "./data/maestro_fresh.db"
    
    success = create_database(db_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()