"""
Document Service - Orchestrates Document Management Across Multiple Storage Systems

This service acts as the central coordinator for document operations across:
1. Main application database (maestro.db) - Document records and status
2. AI researcher database (metadata.db) - Extracted metadata for fast queries
3. ChromaDB vector store - Embeddings and chunks for semantic search
4. File system - Original PDFs and processed markdown files

Key responsibilities:
- Coordinating document uploads and processing
- Managing dual-database queries for efficient retrieval
- Handling document deletion across all storage systems
- Providing cached access to frequently accessed metadata
- Supporting pagination, filtering, and search operations

For architecture details, see: docs/DATABASE_ARCHITECTURE.md
"""
import os
import uuid
import asyncio
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from ai_researcher.core_rag.vector_store_manager import VectorStoreManager as VectorStore
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.processor import DocumentProcessor
from ai_researcher.core_rag.database import Database
from database import crud, models
from api.schemas import Document as DocumentSchema, DocumentGroup as DocumentGroupSchema

class DocumentService:
    """
    Service for managing documents using the existing AI researcher infrastructure.
    
    This service coordinates operations across multiple storage systems:
    - Main DB: Basic document records and processing status
    - AI DB: Rich metadata for filtering and search
    - Vector Store: Embeddings for semantic search
    - File System: Original and processed document files
    
    Performance optimizations:
    - 5-minute metadata cache to reduce vector store queries
    - Database-level filtering before pagination
    - Batch operations for efficiency
    """
    
    def __init__(self):
        # Paths to existing document infrastructure - use absolute paths to ensure consistency
        base_path = Path("/app/ai_researcher/data")  # Docker container path
        self.vector_store_path = base_path / "vector_store"
        self.pdf_dir = base_path / "raw_pdfs"
        self.markdown_dir = base_path / "processed" / "markdown"
        self.metadata_dir = base_path / "processed" / "metadata"
        self.db_path = base_path / "processed" / "metadata.db"
        
        # Initialize components lazily
        self._vector_store = None
        self._embedder = None
        self._ai_db = None
        
    def _get_vector_store(self) -> VectorStore:
        """Get or initialize the vector store."""
        if self._vector_store is None:
            self._vector_store = VectorStore(persist_directory=str(self.vector_store_path))
        return self._vector_store
    
    def _get_embedder(self) -> TextEmbedder:
        """Get or initialize the embedder."""
        if self._embedder is None:
            self._embedder = TextEmbedder(model_name="BAAI/bge-m3")
        return self._embedder
    
    def _get_ai_db(self) -> Database:
        """Get or initialize the AI researcher database."""
        if self._ai_db is None:
            self._ai_db = Database(db_path=self.db_path)
        return self._ai_db
    
    # Cache for document metadata to avoid repeated expensive vector store queries
    _document_cache = {}
    _cache_timestamp = None
    _cache_ttl = 300  # 5 minutes cache TTL

    async def _get_cached_documents(self, user_id: int, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """Get cached document metadata or refresh from vector store if needed."""
        current_time = datetime.now()
        
        # Check if cache is valid
        if (not force_refresh and 
            self._cache_timestamp and 
            self._document_cache and
            (current_time - self._cache_timestamp).total_seconds() < self._cache_ttl):
            print(f"DEBUG: Using cached documents ({len(self._document_cache)} documents)")
            return self._document_cache
        
        print(f"DEBUG: Refreshing document cache from vector store")
        
        try:
            vector_store = self._get_vector_store()
            collection = vector_store.dense_collection
            
            # Get all metadata from the vector store
            results = collection.get(include=['metadatas'])
            all_metadatas = results.get('metadatas', [])
            
            print(f"DEBUG: Total metadata entries retrieved: {len(all_metadatas)}")
            
            # Extract unique documents
            unique_docs = {}
            default_timestamp = datetime.now()
            
            for i, meta in enumerate(all_metadatas):
                doc_id = meta.get('doc_id')
                if doc_id and doc_id not in unique_docs:
                    # Handle missing created_at field by providing a default
                    created_at = meta.get('created_at')
                    if not created_at or created_at == '':
                        created_at = default_timestamp
                    elif isinstance(created_at, str):
                        try:
                            # Try to parse if it's a string
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            created_at = default_timestamp
                    
                    # Process authors field properly - keep as string for schema compatibility
                    authors_raw = meta.get('authors', '[]')
                    authors_for_metadata = authors_raw
                    
                    # For the top-level authors field, convert to string if it's a list
                    if isinstance(authors_raw, list):
                        authors_string = json.dumps(authors_raw) if authors_raw else '[]'
                    else:
                        authors_string = authors_raw
                    
                    # For metadata, keep the original format (could be list or string)
                    if isinstance(authors_raw, str):
                        try:
                            # Try to parse JSON string to list for metadata
                            authors_parsed = json.loads(authors_raw)
                            if isinstance(authors_parsed, list):
                                authors_for_metadata = authors_parsed
                        except (json.JSONDecodeError, TypeError):
                            # Keep as string if parsing fails
                            pass
                    
                    doc_data = {
                        'id': doc_id,
                        'original_filename': meta.get('original_filename', 'Unknown'),
                        'title': meta.get('title'),
                        'authors': authors_string,
                        'user_id': user_id,
                        'created_at': created_at,
                        'processing_status': 'completed',
                        'file_size': meta.get('file_size'),
                        'metadata_': {
                            'title': meta.get('title'),
                            'authors': authors_for_metadata,
                            'abstract': meta.get('abstract'),
                            'publication_year': meta.get('publication_year'),
                            'journal_or_source': meta.get('journal_or_source'),
                            'doi': meta.get('doi'),
                            'keywords': meta.get('keywords'),
                            'original_filename': meta.get('original_filename'),
                            **meta
                        }
                    }
                    unique_docs[doc_id] = doc_data
                    
                    # Debug: Print first few documents with key metadata
                    if len(unique_docs) <= 5:
                        print(f"DEBUG: Document {len(unique_docs)}: {doc_id}")
                        print(f"  Title: {meta.get('title', 'N/A')}")
                        print(f"  Authors: {authors_string}")
                        print(f"  Year: {meta.get('publication_year', 'N/A')}")
                        print(f"  Journal: {meta.get('journal_or_source', 'N/A')}")
            
            print(f"DEBUG: Total unique documents found: {len(unique_docs)}")
            
            # Update cache
            self._document_cache = unique_docs
            self._cache_timestamp = current_time
            
            return unique_docs
            
        except Exception as e:
            print(f"Error getting documents: {e}")
            import traceback
            traceback.print_exc()
            return {}

    async def get_all_documents(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all documents from the vector store with rich metadata."""
        unique_docs = await self._get_cached_documents(user_id)
        result_list = list(unique_docs.values())
        print(f"DEBUG: Returning {len(result_list)} documents")
        return result_list

    async def get_paginated_documents(
        self, 
        user_id: int, 
        page: int = 1, 
        limit: int = 20,
        search: Optional[str] = None,
        author: Optional[str] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc"
    ) -> Dict[str, Any]:
        """Get paginated documents with filtering and sorting applied efficiently using database-level filtering."""
        try:
            ai_db = self._get_ai_db()
            
            # Calculate offset for pagination
            offset = (page - 1) * limit
            
            # Map sort_by to database field names
            db_sort_by = "processing_timestamp"  # Default
            if sort_by == "original_filename":
                db_sort_by = "original_filename"
            elif sort_by in ["created_at", "processing_timestamp"]:
                db_sort_by = "processing_timestamp"
            
            print(f"DEBUG: Querying database with filters - search: {search}, author: {author}, year: {year}, journal: {journal}")
            print(f"DEBUG: Pagination - page: {page}, limit: {limit}, offset: {offset}")
            
            # Use the new optimized database method for filtering and pagination
            db_documents, total_count = ai_db.get_filtered_documents(
                search=search,
                author=author,
                year=year,
                journal=journal,
                sort_by=db_sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset
            )
            
            print(f"DEBUG: Database returned {len(db_documents)} documents out of {total_count} total")
            
            # Convert to our expected format
            documents = []
            for db_doc in db_documents:
                metadata = db_doc.get('metadata', {})
                
                # Handle created_at timestamp
                created_at = db_doc.get('processing_timestamp')
                if created_at:
                    try:
                        # Parse ISO format timestamp
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        created_at = datetime.now()
                else:
                    created_at = datetime.now()
                
                # Process authors field properly
                authors_raw = metadata.get('authors', '[]')
                if isinstance(authors_raw, list):
                    authors_string = json.dumps(authors_raw) if authors_raw else '[]'
                    authors_for_metadata = authors_raw
                else:
                    authors_string = authors_raw
                    try:
                        # Try to parse JSON string to list for metadata
                        authors_parsed = json.loads(authors_raw)
                        if isinstance(authors_parsed, list):
                            authors_for_metadata = authors_parsed
                        else:
                            authors_for_metadata = authors_raw
                    except (json.JSONDecodeError, TypeError):
                        authors_for_metadata = authors_raw
                
                doc_data = {
                    'id': db_doc['id'],
                    'original_filename': db_doc['original_filename'],
                    'title': metadata.get('title'),
                    'authors': authors_string,
                    'user_id': user_id,
                    'created_at': created_at,
                    'processing_status': 'completed',
                    'file_size': metadata.get('file_size'),
                    'metadata_': {
                        'title': metadata.get('title'),
                        'authors': authors_for_metadata,
                        'abstract': metadata.get('abstract'),
                        'publication_year': metadata.get('publication_year'),
                        'journal_or_source': metadata.get('journal_or_source'),
                        'doi': metadata.get('doi'),
                        'keywords': metadata.get('keywords'),
                        'original_filename': db_doc['original_filename'],
                        **metadata
                    }
                }
                documents.append(doc_data)
            
            # Apply status filtering if needed (since it's not in the AI researcher database)
            if status:
                documents = [
                    doc for doc in documents
                    if doc.get('processing_status') == status
                ]
                # Recalculate total count if status filtering was applied
                if status:
                    print(f"DEBUG: Status filtering applied, may need to recalculate total count")
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit  # Ceiling division
            
            print(f"DEBUG: Returning {len(documents)} documents, total: {total_count}, pages: {total_pages}")
            
            return {
                'documents': documents,
                'pagination': {
                    'total_count': total_count,
                    'page': page,
                    'limit': limit,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_previous': page > 1
                },
                'filters_applied': {
                    'search': search,
                    'author': author,
                    'year': year,
                    'journal': journal,
                    'status': status,
                    'sort_by': sort_by,
                    'sort_order': sort_order
                }
            }
            
        except Exception as e:
            print(f"Error getting paginated documents: {e}")
            import traceback
            traceback.print_exc()
            return {
                'documents': [],
                'pagination': {
                    'total_count': 0,
                    'page': page,
                    'limit': limit,
                    'total_pages': 0,
                    'has_next': False,
                    'has_previous': False
                },
                'filters_applied': {
                    'search': search,
                    'author': author,
                    'year': year,
                    'journal': journal,
                    'status': status,
                    'sort_by': sort_by,
                    'sort_order': sort_order
                }
            }
    
    async def get_documents_in_group(self, group_id: str, user_id: int, db: Session) -> List[Dict[str, Any]]:
        """Get documents that belong to a specific group with rich metadata from AI researcher database (optimized)."""
        # Get the group from the database
        db_group = crud.get_document_group(db, group_id=group_id, user_id=user_id)
        if not db_group:
            return []
        
        # Get document IDs in this group
        group_doc_ids = {doc.id for doc in db_group.documents}
        # print(f"DEBUG: Group '{db_group.name}' has {len(group_doc_ids)} documents: {list(group_doc_ids)[:10]}{'...' if len(group_doc_ids) > 10 else ''}")
        
        if not group_doc_ids:
            return []
        
        try:
            # Get all documents from AI researcher database (fast)
            ai_db = self._get_ai_db()
            all_db_documents = ai_db.get_all_documents()
            print(f"DEBUG: Retrieved {len(all_db_documents)} total documents from AI researcher database")
            
            # Filter to only documents in this group
            group_documents = []
            for db_doc in all_db_documents:
                if db_doc['id'] in group_doc_ids:
                    metadata = db_doc.get('metadata', {})
                    
                    # Handle created_at timestamp
                    created_at = db_doc.get('processing_timestamp')
                    if created_at:
                        try:
                            # Parse ISO format timestamp
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            created_at = datetime.now()
                    else:
                        created_at = datetime.now()
                    
                    # Process authors field properly
                    authors_raw = metadata.get('authors', '[]')
                    if isinstance(authors_raw, list):
                        authors_string = json.dumps(authors_raw) if authors_raw else '[]'
                        authors_for_metadata = authors_raw
                    else:
                        authors_string = authors_raw
                        try:
                            # Try to parse JSON string to list for metadata
                            authors_parsed = json.loads(authors_raw)
                            if isinstance(authors_parsed, list):
                                authors_for_metadata = authors_parsed
                            else:
                                authors_for_metadata = authors_raw
                        except (json.JSONDecodeError, TypeError):
                            authors_for_metadata = authors_raw
                    
                    doc_data = {
                        'id': db_doc['id'],
                        'original_filename': db_doc['original_filename'],
                        'title': metadata.get('title'),
                        'authors': authors_string,
                        'user_id': user_id,
                        'created_at': created_at,
                        'processing_status': 'completed',
                        'file_size': metadata.get('file_size'),
                        'metadata_': {
                            'title': metadata.get('title'),
                            'authors': authors_for_metadata,
                            'abstract': metadata.get('abstract'),
                            'publication_year': metadata.get('publication_year'),
                            'journal_or_source': metadata.get('journal_or_source'),
                            'doi': metadata.get('doi'),
                            'keywords': metadata.get('keywords'),
                            'original_filename': db_doc['original_filename'],
                            **metadata
                        }
                    }
                    group_documents.append(doc_data)
            
            print(f"DEBUG: Found {len(group_documents)} documents in group '{db_group.name}' from AI researcher database")
            return group_documents
            
        except Exception as e:
            print(f"Error getting group documents from AI researcher database: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback to the old vector store method if AI researcher database fails
            print("DEBUG: Falling back to vector store method")
            return await self._get_documents_in_group_fallback(group_id, user_id, db)

    async def get_paginated_documents_in_group(
        self, 
        group_id: str, 
        user_id: int, 
        db: Session,
        page: int = 1, 
        limit: int = 20,
        search: Optional[str] = None,
        author: Optional[str] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc"
    ) -> Dict[str, Any]:
        """Get paginated documents in a group with filtering and sorting applied efficiently."""
        try:
            # Get the group from the database
            db_group = crud.get_document_group(db, group_id=group_id, user_id=user_id)
            if not db_group:
                return {
                    'documents': [],
                    'pagination': {
                        'total_count': 0,
                        'page': page,
                        'limit': limit,
                        'total_pages': 0,
                        'has_next': False,
                        'has_previous': False
                    },
                    'filters_applied': {
                        'search': search,
                        'author': author,
                        'year': year,
                        'journal': journal,
                        'status': status,
                        'sort_by': sort_by,
                        'sort_order': sort_order
                    }
                }
            
            # Get document IDs in this group
            group_doc_ids = {doc.id for doc in db_group.documents}
            # print(f"DEBUG: Group '{db_group.name}' has {len(group_doc_ids)} documents")
            
            if not group_doc_ids:
                return {
                    'documents': [],
                    'pagination': {
                        'total_count': 0,
                        'page': page,
                        'limit': limit,
                        'total_pages': 0,
                        'has_next': False,
                        'has_previous': False
                    },
                    'filters_applied': {
                        'search': search,
                        'author': author,
                        'year': year,
                        'journal': journal,
                        'status': status,
                        'sort_by': sort_by,
                        'sort_order': sort_order
                    }
                }
            
            ai_db = self._get_ai_db()
            
            # Calculate offset for pagination
            offset = (page - 1) * limit
            
            # Map sort_by to database field names
            db_sort_by = "processing_timestamp"  # Default
            if sort_by == "original_filename":
                db_sort_by = "original_filename"
            elif sort_by in ["created_at", "processing_timestamp"]:
                db_sort_by = "processing_timestamp"
            
            print(f"DEBUG: Querying database for group documents with filters - search: {search}, author: {author}, year: {year}, journal: {journal}")
            print(f"DEBUG: Pagination - page: {page}, limit: {limit}, offset: {offset}")
            
            # Get all filtered documents first (we need to filter by group membership after database filtering)
            all_filtered_docs, _ = ai_db.get_filtered_documents(
                search=search,
                author=author,
                year=year,
                journal=journal,
                sort_by=db_sort_by,
                sort_order=sort_order,
                limit=None,  # Get all matching documents
                offset=None
            )
            
            # Filter to only documents in this group
            group_filtered_docs = [
                doc for doc in all_filtered_docs 
                if doc['id'] in group_doc_ids
            ]
            
            # Apply pagination to the group-filtered results
            total_count = len(group_filtered_docs)
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_docs = group_filtered_docs[start_idx:end_idx]
            
            print(f"DEBUG: After group filtering: {total_count} documents, returning page {page} with {len(paginated_docs)} documents")
            
            # Convert to our expected format
            documents = []
            for db_doc in paginated_docs:
                metadata = db_doc.get('metadata', {})
                
                # Handle created_at timestamp
                created_at = db_doc.get('processing_timestamp')
                if created_at:
                    try:
                        # Parse ISO format timestamp
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        created_at = datetime.now()
                else:
                    created_at = datetime.now()
                
                # Process authors field properly
                authors_raw = metadata.get('authors', '[]')
                if isinstance(authors_raw, list):
                    authors_string = json.dumps(authors_raw) if authors_raw else '[]'
                    authors_for_metadata = authors_raw
                else:
                    authors_string = authors_raw
                    try:
                        # Try to parse JSON string to list for metadata
                        authors_parsed = json.loads(authors_raw)
                        if isinstance(authors_parsed, list):
                            authors_for_metadata = authors_parsed
                        else:
                            authors_for_metadata = authors_raw
                    except (json.JSONDecodeError, TypeError):
                        authors_for_metadata = authors_raw
                
                doc_data = {
                    'id': db_doc['id'],
                    'original_filename': db_doc['original_filename'],
                    'title': metadata.get('title'),
                    'authors': authors_string,
                    'user_id': user_id,
                    'created_at': created_at,
                    'processing_status': 'completed',
                    'file_size': metadata.get('file_size'),
                    'metadata_': {
                        'title': metadata.get('title'),
                        'authors': authors_for_metadata,
                        'abstract': metadata.get('abstract'),
                        'publication_year': metadata.get('publication_year'),
                        'journal_or_source': metadata.get('journal_or_source'),
                        'doi': metadata.get('doi'),
                        'keywords': metadata.get('keywords'),
                        'original_filename': db_doc['original_filename'],
                        **metadata
                    }
                }
                documents.append(doc_data)
            
            # Apply status filtering if needed (since it's not in the AI researcher database)
            if status:
                documents = [
                    doc for doc in documents
                    if doc.get('processing_status') == status
                ]
                # Note: This may affect pagination accuracy, but status filtering is rare
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit  # Ceiling division
            
            print(f"DEBUG: Returning {len(documents)} group documents, total: {total_count}, pages: {total_pages}")
            
            return {
                'documents': documents,
                'pagination': {
                    'total_count': total_count,
                    'page': page,
                    'limit': limit,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_previous': page > 1
                },
                'filters_applied': {
                    'search': search,
                    'author': author,
                    'year': year,
                    'journal': journal,
                    'status': status,
                    'sort_by': sort_by,
                    'sort_order': sort_order
                }
            }
            
        except Exception as e:
            print(f"Error getting paginated group documents: {e}")
            import traceback
            traceback.print_exc()
            return {
                'documents': [],
                'pagination': {
                    'total_count': 0,
                    'page': page,
                    'limit': limit,
                    'total_pages': 0,
                    'has_next': False,
                    'has_previous': False
                },
                'filters_applied': {
                    'search': search,
                    'author': author,
                    'year': year,
                    'journal': journal,
                    'status': status,
                    'sort_by': sort_by,
                    'sort_order': sort_order
                }
            }

    async def _get_documents_in_group_fallback(self, group_id: str, user_id: int, db: Session) -> List[Dict[str, Any]]:
        """Fallback method using vector store (kept for compatibility)."""
        # Get the group from the database
        db_group = crud.get_document_group(db, group_id=group_id, user_id=user_id)
        if not db_group:
            return []
        
        # Get documents associated with this group
        documents = []
        vector_store = self._get_vector_store()
        collection = vector_store.dense_collection
        
        for doc in db_group.documents:
            # Start with database data
            doc_data = {
                'id': doc.id,
                'original_filename': doc.original_filename,
                'user_id': doc.user_id,
                'created_at': doc.created_at.isoformat() if doc.created_at else '',
                'processing_status': doc.processing_status,
                'upload_progress': doc.upload_progress,
                'file_size': doc.file_size,
                'metadata_': doc.metadata_ or {}
            }
            
            # Try to get rich metadata from vector store
            try:
                results = collection.get(
                    where={"doc_id": doc.id},
                    include=['metadatas'],
                    limit=1
                )
                
                if results.get('metadatas') and len(results['metadatas']) > 0:
                    vector_meta = results['metadatas'][0]
                    
                    # Process authors field properly
                    authors_raw = vector_meta.get('authors', '[]')
                    if isinstance(authors_raw, list):
                        authors_string = json.dumps(authors_raw) if authors_raw else '[]'
                    else:
                        authors_string = authors_raw
                    
                    # Merge vector store metadata with database metadata
                    doc_data['title'] = vector_meta.get('title')
                    doc_data['authors'] = authors_string
                    # Update metadata_ with rich information from vector store
                    doc_data['metadata_'] = {
                        'title': vector_meta.get('title'),
                        'authors': vector_meta.get('authors'),
                        'abstract': vector_meta.get('abstract'),
                        'publication_year': vector_meta.get('publication_year'),
                        'journal_or_source': vector_meta.get('journal_or_source'),
                        'doi': vector_meta.get('doi'),
                        'keywords': vector_meta.get('keywords'),
                        'original_filename': vector_meta.get('original_filename'),
                        **vector_meta
                    }
                    
            except Exception as e:
                print(f"Warning: Could not fetch vector store metadata for document {doc.id}: {e}")
                # Continue with database-only data
            
            documents.append(doc_data)
        
        return documents
    
    async def add_document_to_group(self, group_id: str, doc_id: str, user_id: int, db: Session) -> bool:
        """Add an existing document from the vector store to a group."""
        try:
            # Check if document exists in vector store
            vector_store = self._get_vector_store()
            collection = vector_store.dense_collection
            
            # Query for this specific document
            results = collection.get(
                where={"doc_id": doc_id},
                include=['metadatas'],
                limit=1
            )
            
            if not results.get('metadatas'):
                return False
            
            meta = results['metadatas'][0]
            
            # Create document record in our database if it doesn't exist
            existing_doc = crud.get_document(db, doc_id=doc_id, user_id=user_id)
            if not existing_doc:
                # Create new document record
                crud.create_document(
                    db=db,
                    doc_id=doc_id,
                    user_id=user_id,
                    original_filename=meta.get('original_filename', 'Unknown'),
                    metadata=meta
                )
            
            # Add document to group
            db_group = crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=user_id)
            return db_group is not None
            
        except Exception as e:
            print(f"Error adding document to group: {e}")
            return False
    
    async def upload_document(self, file_content: bytes, filename: str, group_id: str, user_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Upload a new document using atomic creation with consistent ID generation."""
        try:
            # Import the improved document creation function
            from database.crud_documents_improved import create_document_atomically
            
            print(f"Starting atomic document creation for: {filename}")
            
            # Create document atomically with rollback capability
            document = await create_document_atomically(
                db=db,
                user_id=user_id,
                original_filename=filename,
                file_content=file_content,
                group_id=group_id,
                metadata={'status': 'uploaded', 'source': 'ui_upload'}
            )
            
            if document:
                # Return document data
                doc_data = {
                    'id': document.id,
                    'original_filename': document.original_filename,
                    'user_id': document.user_id,
                    'created_at': document.created_at.isoformat(),
                    'processing_status': document.processing_status,
                    'upload_progress': document.upload_progress,
                    'file_size': document.file_size,
                    'metadata_': document.metadata_
                }
                
                print(f"Successfully created document {document.id} atomically")
                return doc_data
            else:
                print("Failed to create document atomically")
                return None
            
        except Exception as e:
            print(f"Error uploading document: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def search_documents(self, query: str, user_id: int, n_results: int = 10) -> List[Dict[str, Any]]:
        """Search documents using the existing vector store."""
        try:
            from ai_researcher.core_rag.retriever import Retriever
            from ai_researcher.core_rag.reranker import TextReranker
            
            # Initialize retriever
            embedder = self._get_embedder()
            vector_store = self._get_vector_store()
            reranker = TextReranker(model_name="BAAI/bge-reranker-v2-m3")
            
            retriever = Retriever(embedder=embedder, vector_store=vector_store, reranker=reranker)
            
            # Perform search
            results = await retriever.retrieve(
                query_text=query,
                n_results=n_results,
                use_reranker=True
            )
            
            # Format results
            formatted_results = []
            for result in results:
                metadata = result.get('metadata', {})
                formatted_results.append({
                    'doc_id': metadata.get('doc_id'),
                    'title': metadata.get('title', 'N/A'),
                    'original_filename': metadata.get('original_filename', 'Unknown'),
                    'authors': metadata.get('authors', '[]'),
                    'text_preview': result.get('text', '')[:300],
                    'score': result.get('score', 0.0),
                    'chunk_id': metadata.get('chunk_id')
                })
            
            return formatted_results
            
        except Exception as e:
            print(f"Error searching documents: {e}")
            return []
    
    async def delete_document_from_vector_store(self, doc_id: str, user_id: int) -> bool:
        """Delete a document from the vector store."""
        try:
            vector_store = self._get_vector_store()
            
            # Remove from dense collection
            dense_collection = vector_store.dense_collection
            dense_results = dense_collection.get(where={"doc_id": doc_id})
            if dense_results['ids']:
                dense_collection.delete(ids=dense_results['ids'])
                print(f"Removed {len(dense_results['ids'])} chunks from dense collection for document {doc_id}")
            
            # Remove from sparse collection
            sparse_collection = vector_store.sparse_collection
            sparse_results = sparse_collection.get(where={"doc_id": doc_id})
            if sparse_results['ids']:
                sparse_collection.delete(ids=sparse_results['ids'])
                print(f"Removed {len(sparse_results['ids'])} chunks from sparse collection for document {doc_id}")
            
            # Check if any chunks were actually deleted
            total_deleted = len(dense_results.get('ids', [])) + len(sparse_results.get('ids', []))
            if total_deleted > 0:
                print(f"Successfully deleted document {doc_id} from vector store ({total_deleted} total chunks)")
                return True
            else:
                print(f"No chunks found for document {doc_id} in vector store")
                return False
                
        except Exception as e:
            print(f"Error deleting document {doc_id} from vector store: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_document_from_ai_db(self, doc_id: str) -> bool:
        """Delete a document from the AI researcher database."""
        try:
            ai_db = self._get_ai_db()
            return ai_db.delete_document(doc_id)
        except Exception as e:
            print(f"Error deleting document {doc_id} from AI researcher database: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def delete_document_completely(self, doc_id: str, user_id: int, db: Session) -> bool:
        """
        Delete a document completely and atomically from all storage systems.
        Uses the DocumentConsistencyManager to ensure proper cleanup.
        """
        try:
            # Import the improved deletion function
            from database.crud_documents_improved import delete_document_atomically
            
            print(f"Starting atomic document deletion for: {doc_id}")
            
            # Delete document atomically from all systems
            success = await delete_document_atomically(db, doc_id, user_id)
            
            if success:
                print(f"Successfully deleted document {doc_id} from all systems")
            else:
                print(f"Document {doc_id} deletion completed with some issues")
                
            return success
            
        except Exception as e:
            print(f"Error in atomic document deletion: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def update_document_metadata(self, doc_id: str, user_id: int, metadata_update: Dict[str, Any], db: Session) -> Optional[Dict[str, Any]]:
        """
        Update document metadata across all databases (Main DB, AI DB, Vector Store).
        Ensures atomic updates with rollback capabilities.
        """
        try:
            print(f"Starting metadata update for document {doc_id}")
            
            # Get the document first to ensure it exists and user has access
            document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
            if not document:
                print(f"Document {doc_id} not found for user {user_id}")
                return None
            
            # Prepare updated metadata
            current_metadata = document.metadata_ or {}
            updated_metadata = {**current_metadata, **metadata_update}
            
            # Track update success for rollback
            main_db_updated = False
            ai_db_updated = False
            vector_store_updated = False
            
            try:
                # 1. Update main database
                document.metadata_ = updated_metadata
                document.updated_at = datetime.now()
                
                # Update title and authors at the document level for compatibility
                if 'title' in metadata_update:
                    document.title = metadata_update['title']
                if 'authors' in metadata_update:
                    document.authors = json.dumps(metadata_update['authors']) if isinstance(metadata_update['authors'], list) else metadata_update['authors']
                
                db.commit()
                main_db_updated = True
                print(f"Updated main database for document {doc_id}")
                
                # 2. Update AI researcher database
                try:
                    ai_db = self._get_ai_db()
                    if ai_db.document_exists(doc_id):
                        ai_update_success = ai_db.update_document_metadata(doc_id, updated_metadata)
                        if ai_update_success:
                            ai_db_updated = True
                            print(f"Updated AI database for document {doc_id}")
                        else:
                            print(f"Failed to update AI database for document {doc_id}")
                except Exception as e:
                    print(f"Error updating AI database: {e}")
                
                # 3. Update vector store metadata
                try:
                    vector_store = self._get_vector_store()
                    collection = vector_store.dense_collection
                    
                    # Get all chunks for this document
                    results = collection.get(
                        where={"doc_id": doc_id},
                        include=['metadatas']
                    )
                    
                    if results['metadatas']:
                        # Update metadata for all chunks of this document
                        chunk_ids = results['ids'] if results['ids'] else []
                        updated_metadatas = []
                        
                        for metadata in results['metadatas']:
                            chunk_metadata = {**metadata, **metadata_update}
                            updated_metadatas.append(chunk_metadata)
                        
                        if chunk_ids and updated_metadatas:
                            collection.update(
                                ids=chunk_ids,
                                metadatas=updated_metadatas
                            )
                            vector_store_updated = True
                            print(f"Updated vector store for document {doc_id} ({len(chunk_ids)} chunks)")
                
                    # Also update sparse collection if it exists
                    if hasattr(vector_store, 'sparse_collection') and vector_store.sparse_collection:
                        sparse_results = vector_store.sparse_collection.get(
                            where={"doc_id": doc_id},
                            include=['metadatas']
                        )
                        
                        if sparse_results['metadatas']:
                            sparse_chunk_ids = sparse_results['ids'] if sparse_results['ids'] else []
                            sparse_updated_metadatas = []
                            
                            for metadata in sparse_results['metadatas']:
                                chunk_metadata = {**metadata, **metadata_update}
                                sparse_updated_metadatas.append(chunk_metadata)
                            
                            if sparse_chunk_ids and sparse_updated_metadatas:
                                vector_store.sparse_collection.update(
                                    ids=sparse_chunk_ids,
                                    metadatas=sparse_updated_metadatas
                                )
                                print(f"Updated sparse vector store for document {doc_id} ({len(sparse_chunk_ids)} chunks)")
                
                except Exception as e:
                    print(f"Error updating vector store: {e}")
                
                # Clear cache to ensure fresh data on next request
                self._document_cache = {}
                self._cache_timestamp = None
                
                # Return updated document data
                return {
                    'id': document.id,
                    'original_filename': document.original_filename,
                    'user_id': document.user_id,
                    'created_at': document.created_at.isoformat(),
                    'title': document.title,
                    'authors': document.authors,
                    'processing_status': document.processing_status,
                    'upload_progress': document.upload_progress,
                    'file_size': document.file_size,
                    'processing_error': document.processing_error,
                    'metadata_': updated_metadata
                }
                
            except Exception as e:
                print(f"Error during metadata update, attempting rollback: {e}")
                
                # Rollback main database if it was updated
                if main_db_updated:
                    try:
                        db.rollback()
                        print("Rolled back main database changes")
                    except Exception as rollback_error:
                        print(f"Error rolling back main database: {rollback_error}")
                
                raise e
                
        except Exception as e:
            print(f"Error updating document metadata: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def get_document_content(self, doc_id: str, user_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        Get document content for viewing, including markdown content and metadata.
        """
        try:
            print(f"Retrieving content for document {doc_id}")
            
            # Get the document from main database first
            document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
            if not document:
                print(f"Document {doc_id} not found for user {user_id}")
                return None
            
            # Try to get markdown content from file system
            markdown_content = ""
            markdown_file_path = self.markdown_dir / f"{doc_id}.md"
            
            try:
                if markdown_file_path.exists():
                    with open(markdown_file_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()
                    print(f"Found markdown content for document {doc_id}")
                else:
                    print(f"No markdown file found for document {doc_id} at {markdown_file_path}")
            except Exception as e:
                print(f"Error reading markdown file for document {doc_id}: {e}")
                
                # Fallback: try to get content from vector store chunks
                try:
                    vector_store = self._get_vector_store()
                    collection = vector_store.dense_collection
                    
                    results = collection.get(
                        where={"doc_id": doc_id},
                        include=['documents', 'metadatas']
                    )
                    
                    if results['documents']:
                        # Combine all chunks into content
                        chunks = []
                        for i, (doc_text, metadata) in enumerate(zip(results['documents'], results['metadatas'])):
                            chunk_id = metadata.get('chunk_id', i)
                            chunks.append((chunk_id, doc_text))
                        
                        # Sort by chunk_id and combine
                        chunks.sort(key=lambda x: x[0])
                        markdown_content = "\n\n".join([chunk[1] for chunk in chunks])
                        print(f"Reconstructed content from {len(chunks)} vector store chunks")
                    
                except Exception as vector_error:
                    print(f"Error retrieving content from vector store: {vector_error}")
            
            # Get enhanced metadata from AI database if available
            enhanced_metadata = document.metadata_ or {}
            try:
                ai_db = self._get_ai_db()
                if ai_db.document_exists(doc_id):
                    ai_metadata = ai_db.get_document_metadata(doc_id)
                    if ai_metadata:
                        enhanced_metadata = {**enhanced_metadata, **ai_metadata}
                        print(f"Enhanced metadata from AI database for document {doc_id}")
            except Exception as e:
                print(f"Error getting metadata from AI database: {e}")
            
            return {
                'id': document.id,
                'original_filename': document.original_filename,
                'title': document.title or enhanced_metadata.get('title', document.original_filename),
                'content': markdown_content,
                'metadata_': enhanced_metadata,
                'created_at': document.created_at.isoformat(),
                'file_size': document.file_size
            }
            
        except Exception as e:
            print(f"Error retrieving document content: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def cancel_document_processing(self, doc_id: str, user_id: int, db: Session) -> bool:
        """
        Cancel document processing for a specific document and clean up files.
        """
        try:
            # Try to find the document in the database first
            document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
            
            if document:
                # Clean up physical file if it exists
                if document.file_path and os.path.exists(document.file_path):
                    try:
                        os.remove(document.file_path)
                        print(f"Deleted physical file: {document.file_path}")
                    except Exception as e:
                        print(f"Warning: Could not delete physical file {document.file_path}: {e}")
                
                # Clean up any processed files (markdown, metadata)
                try:
                    # Clean up markdown file
                    markdown_file = self.markdown_dir / f"{doc_id}.md"
                    if markdown_file.exists():
                        markdown_file.unlink()
                        print(f"Deleted markdown file: {markdown_file}")
                    
                    # Clean up metadata file
                    metadata_file = self.metadata_dir / f"{doc_id}.json"
                    if metadata_file.exists():
                        metadata_file.unlink()
                        print(f"Deleted metadata file: {metadata_file}")
                        
                except Exception as e:
                    print(f"Warning: Could not clean up processed files for {doc_id}: {e}")
                
                # Remove from vector store if it exists
                try:
                    await self.delete_document_from_vector_store(doc_id, user_id)
                except Exception as e:
                    print(f"Warning: Could not remove from vector store for {doc_id}: {e}")
                
                # Delete from database completely (instead of just marking as cancelled)
                success = crud.delete_document(db, doc_id=doc_id, user_id=user_id)
                if success:
                    print(f"Successfully cancelled and cleaned up document {doc_id}")
                    return True
                else:
                    print(f"Failed to delete document {doc_id} from database")
                    return False
            
            # If not found in database, try to clean up any orphaned files
            try:
                # Check for orphaned PDF file
                pdf_pattern = self.pdf_dir / f"{doc_id}_*"
                import glob
                pdf_files = glob.glob(str(pdf_pattern))
                for pdf_file in pdf_files:
                    try:
                        os.remove(pdf_file)
                        print(f"Deleted orphaned PDF file: {pdf_file}")
                    except Exception as e:
                        print(f"Warning: Could not delete orphaned PDF file {pdf_file}: {e}")
                
                # Clean up any processed files
                markdown_file = self.markdown_dir / f"{doc_id}.md"
                if markdown_file.exists():
                    markdown_file.unlink()
                    print(f"Deleted orphaned markdown file: {markdown_file}")
                
                metadata_file = self.metadata_dir / f"{doc_id}.json"
                if metadata_file.exists():
                    metadata_file.unlink()
                    print(f"Deleted orphaned metadata file: {metadata_file}")
                
                # Remove from vector store
                await self.delete_document_from_vector_store(doc_id, user_id)
                
            except Exception as e:
                print(f"Warning: Error cleaning up orphaned files for {doc_id}: {e}")
            
            print(f"Document {doc_id} cancellation completed (may have been orphaned)")
            return True
            
        except Exception as e:
            print(f"Error cancelling document processing for {doc_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_document_filename_mapping(self, document_codes: List[str]) -> Dict[str, str]:
        """
        Get a mapping of document codes to actual filenames.
        
        Args:
            document_codes: List of document IDs/codes to look up
            
        Returns:
            Dictionary mapping document_code -> original_filename
        """
        try:
            vector_store = self._get_vector_store()
            collection = vector_store.dense_collection
            
            # Create mapping dictionary
            code_to_filename = {}
            
            for doc_code in document_codes:
                if not doc_code:
                    continue
                    
                try:
                    # Query vector store for this document
                    results = collection.get(
                        where={"doc_id": doc_code},
                        include=['metadatas'],
                        limit=1
                    )
                    
                    if results.get('metadatas') and len(results['metadatas']) > 0:
                        metadata = results['metadatas'][0]
                        original_filename = metadata.get('original_filename', doc_code)
                        code_to_filename[doc_code] = original_filename
                    else:
                        # Fallback to the code itself if not found
                        code_to_filename[doc_code] = doc_code
                        
                except Exception as e:
                    print(f"Warning: Could not fetch filename for document {doc_code}: {e}")
                    code_to_filename[doc_code] = doc_code
            
            return code_to_filename
            
        except Exception as e:
            print(f"Error creating document filename mapping: {e}")
            # Return empty mapping on error
            return {}

    def extract_document_codes_from_text(self, text: str) -> List[str]:
        """
        Extract document codes from text (like file paths or source IDs).
        
        Args:
            text: Text that may contain document codes
            
        Returns:
            List of document codes found in the text
        """
        import re
        
        # Pattern to match document codes in file paths like:
        # /app/ai_researcher/data/processed/markdown/7fafabb4.md
        # or just standalone codes like 7fafabb4
        
        codes = []
        
        # Extract from markdown file paths
        markdown_pattern = r'/app/ai_researcher/data/processed/markdown/([a-f0-9]{8})\.md'
        matches = re.findall(markdown_pattern, text)
        codes.extend(matches)
        
        # Extract from other file paths that might contain document codes
        general_path_pattern = r'/([a-f0-9]{8})(?:\.|\s|$)'
        matches = re.findall(general_path_pattern, text)
        codes.extend(matches)
        
        # Extract standalone 8-character hex codes (common document ID format)
        standalone_pattern = r'\b([a-f0-9]{8})\b'
        matches = re.findall(standalone_pattern, text)
        codes.extend(matches)
        
        # Remove duplicates and return
        return list(set(codes))

    async def replace_document_codes_in_text(self, text: str) -> str:
        """
        Replace document codes in text with actual filenames.
        
        Args:
            text: Text containing document codes or file paths
            
        Returns:
            Text with document codes replaced by actual filenames
        """
        if not text:
            return text
            
        # Extract document codes from the text
        document_codes = self.extract_document_codes_from_text(text)
        
        if not document_codes:
            return text
        
        # Get filename mapping
        code_to_filename = await self.get_document_filename_mapping(document_codes)
        
        # Replace codes in the text
        result_text = text
        for code, filename in code_to_filename.items():
            if code != filename:  # Only replace if we found a different filename
                # Replace in file paths
                result_text = result_text.replace(
                    f'/app/ai_researcher/data/processed/markdown/{code}.md',
                    filename
                )
                # Replace standalone codes (be careful not to replace parts of other words)
                result_text = re.sub(
                    r'\b' + re.escape(code) + r'\b',
                    filename,
                    result_text
                )
        
        return result_text

# Global instance
document_service = DocumentService()
