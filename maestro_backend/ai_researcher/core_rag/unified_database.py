"""
Unified Database Adapter
Provides compatibility layer for code expecting the old AI database interface.
All operations are redirected to the main unified database.
"""

import json
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import or_
import logging

# Import using absolute imports without modifying sys.path
from database.models import Document
from database.database import get_db
from database import crud

logger = logging.getLogger(__name__)


class UnifiedDocumentDatabase:
    """
    Adapter class that provides the old DocumentDatabase interface
    but uses the unified main database instead.
    """
    
    def __init__(self, db_path: str = None, session: Session = None):
        # Ignore db_path - we always use the main database
        self.db_path = "data/maestro.db"
        self.session = session  # Accept optional session
        logger.debug("Using unified database at data/maestro.db")
    
    def _get_session(self) -> Session:
        """Get a database session."""
        if self.session:
            return self.session
        # Fallback for compatibility - creates a new session when none provided
        # This is not ideal but maintains backward compatibility
        return next(get_db())
    
    def add_document(self, doc_id: str, filename: str, metadata_json: str = None, session: Session = None) -> bool:
        """Add a document to the database."""
        db = session if session else self._get_session()
        try:
            # Check if document exists
            existing = db.query(Document).filter(Document.id == doc_id).first()
            if existing:
                logger.info(f"Document {doc_id} already exists, updating metadata")
                if metadata_json:
                    metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                    existing.extracted_metadata = metadata
                    existing.has_extracted_metadata = True
                    db.commit()
                return True
            
            # Parse metadata
            metadata = {}
            if metadata_json:
                metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
            
            # Create new document - note we don't create a full document here
            # as that should be done through the main document service
            # This is just for compatibility with old code
            logger.info(f"Document {doc_id} should be created through main document service")
            return True
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def update_document_status(self, doc_id: str, status: str, session: Session = None) -> bool:
        """Update document processing status."""
        db = session if session else self._get_session()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                # Map old status values to new ones
                status_map = {
                    "completed": "completed",
                    "processing": "processing", 
                    "error": "failed",
                    "error_embedding_storing": "failed",
                    "error_saving_markdown": "failed",
                    "error_conversion": "failed"
                }
                
                doc.processing_status = status_map.get(status, status)
                
                if status == "completed":
                    doc.has_vector_chunks = True
                    doc.has_extracted_metadata = True
                
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating document {doc_id} status: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def update_document_metadata(self, doc_id: str, metadata: Dict[str, Any], session: Session = None) -> bool:
        """Update document metadata."""
        db = session if session else self._get_session()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.extracted_metadata = metadata
                doc.has_extracted_metadata = True
                
                # Update specific fields if they exist
                if 'title' in metadata:
                    doc.extracted_title = metadata['title']
                if 'authors' in metadata:
                    authors = metadata['authors']
                    if isinstance(authors, list):
                        doc.extracted_authors = ', '.join(authors)
                    else:
                        doc.extracted_authors = str(authors)
                if 'year' in metadata:
                    try:
                        doc.extracted_year = int(metadata['year'])
                    except:
                        pass
                if 'journal' in metadata:
                    doc.extracted_journal = metadata['journal']
                
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating document {doc_id} metadata: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def get_document_info_by_filename(self, filename: str, session: Session = None) -> Optional[Dict[str, Any]]:
        """Get document info by filename."""
        db = session if session else self._get_session()
        try:
            doc = db.query(Document).filter(Document.original_filename == filename).first()
            if doc:
                return {
                    'doc_id': doc.id,
                    'filename': doc.original_filename,
                    'metadata_json': json.dumps(doc.extracted_metadata) if doc.extracted_metadata else None,
                    'processing_status': doc.processing_status,
                    'has_extracted_metadata': doc.has_extracted_metadata if hasattr(doc, 'has_extracted_metadata') else False,
                    'has_vector_chunks': doc.has_vector_chunks if hasattr(doc, 'has_vector_chunks') else False
                }
            return None
        except Exception as e:
            logger.error(f"Error getting document by filename {filename}: {e}")
            return None
        finally:
            db.close()
    
    def get_all_documents(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get all documents."""
        db = session if session else self._get_session()
        try:
            query = db.query(Document)
            if limit:
                query = query.limit(limit)
            
            documents = []
            for doc in query.all():
                documents.append({
                    'doc_id': doc.id,
                    'filename': doc.original_filename,
                    'metadata': doc.extracted_metadata if hasattr(doc, 'extracted_metadata') else {},
                    'processing_status': doc.processing_status,
                    'has_extracted_metadata': doc.has_extracted_metadata if hasattr(doc, 'has_extracted_metadata') else False,
                    'has_vector_chunks': doc.has_vector_chunks if hasattr(doc, 'has_vector_chunks') else False
                })
            return documents
        except Exception as e:
            logger.error(f"Error getting all documents: {e}")
            return []
        finally:
            db.close()
    
    def get_filtered_documents(
        self,
        search: Optional[str] = None,
        author: Optional[str] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        sort_by: str = "processing_timestamp",
        sort_order: str = "desc",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        doc_ids: Optional[List[str]] = None,
        session: Session = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get filtered documents with pagination support.
        Returns (documents, total_count)
        """
        db = session if session else self._get_session()
        try:
            query = db.query(Document)
            
            # Apply filters
            if doc_ids:
                query = query.filter(Document.id.in_(doc_ids))
            
            if search:
                # Search in title, filename, and extracted metadata
                search_pattern = f"%{search}%"
                # Try both column naming conventions
                filters = [Document.original_filename.ilike(search_pattern)]
                
                if hasattr(Document, 'title'):
                    filters.append(Document.title.ilike(search_pattern))
                elif hasattr(Document, 'extracted_title'):
                    filters.append(Document.extracted_title.ilike(search_pattern))
                    
                if hasattr(Document, 'authors'):
                    filters.append(Document.authors.ilike(search_pattern))
                elif hasattr(Document, 'extracted_authors'):
                    filters.append(Document.extracted_authors.ilike(search_pattern))
                    
                if hasattr(Document, 'journal'):
                    filters.append(Document.journal.ilike(search_pattern))
                elif hasattr(Document, 'extracted_journal'):
                    filters.append(Document.extracted_journal.ilike(search_pattern))
                
                query = query.filter(or_(*filters))
            
            if author:
                author_pattern = f"%{author}%"
                if hasattr(Document, 'authors'):
                    query = query.filter(Document.authors.ilike(author_pattern))
                elif hasattr(Document, 'extracted_authors'):
                    query = query.filter(Document.extracted_authors.ilike(author_pattern))
            
            if year:
                if hasattr(Document, 'publication_year'):
                    query = query.filter(Document.publication_year == year)
                elif hasattr(Document, 'extracted_year'):
                    query = query.filter(Document.extracted_year == year)
            
            if journal:
                journal_pattern = f"%{journal}%"
                if hasattr(Document, 'journal'):
                    query = query.filter(Document.journal.ilike(journal_pattern))
                elif hasattr(Document, 'extracted_journal'):
                    query = query.filter(Document.extracted_journal.ilike(journal_pattern))
            
            # Apply sorting
            if sort_by == "processing_timestamp" or sort_by == "created_at":
                if sort_order == "desc":
                    query = query.order_by(Document.created_at.desc())
                else:
                    query = query.order_by(Document.created_at.asc())
            elif sort_by == "original_filename" or sort_by == "filename":
                if sort_order == "desc":
                    query = query.order_by(Document.original_filename.desc())
                else:
                    query = query.order_by(Document.original_filename.asc())
            
            # Get total count before pagination
            total_count = query.count()
            
            # Apply pagination
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            # Convert to dictionaries matching expected format
            documents = []
            for doc in query.all():
                # Build metadata dict - support both naming conventions
                metadata = doc.metadata_ if hasattr(doc, 'metadata_') and doc.metadata_ else {}
                
                # Add extracted fields to metadata if they exist and aren't already there
                # Try migration 021 column names first, then old names
                if 'title' not in metadata:
                    if hasattr(doc, 'title') and doc.title:
                        metadata['title'] = doc.title
                    elif hasattr(doc, 'extracted_title') and doc.extracted_title:
                        metadata['title'] = doc.extracted_title
                        
                if 'authors' not in metadata:
                    if hasattr(doc, 'authors') and doc.authors:
                        # Authors might be JSON string
                        try:
                            metadata['authors'] = json.loads(doc.authors) if isinstance(doc.authors, str) else doc.authors
                        except:
                            metadata['authors'] = doc.authors
                    elif hasattr(doc, 'extracted_authors') and doc.extracted_authors:
                        metadata['authors'] = doc.extracted_authors
                        
                if 'year' not in metadata:
                    if hasattr(doc, 'publication_year') and doc.publication_year:
                        metadata['year'] = doc.publication_year
                    elif hasattr(doc, 'extracted_year') and doc.extracted_year:
                        metadata['year'] = doc.extracted_year
                        
                if 'journal' not in metadata:
                    if hasattr(doc, 'journal') and doc.journal:
                        metadata['journal'] = doc.journal
                    elif hasattr(doc, 'extracted_journal') and doc.extracted_journal:
                        metadata['journal'] = doc.extracted_journal
                
                doc_dict = {
                    'doc_id': doc.id,
                    'id': doc.id,  # Some code expects 'id' field
                    'original_filename': doc.original_filename,
                    'filename': doc.original_filename,  # Compatibility
                    'metadata': metadata,
                    'processing_timestamp': doc.created_at.isoformat() if hasattr(doc, 'created_at') and doc.created_at else None,
                    'processing_status': doc.processing_status,
                    'has_extracted_metadata': doc.has_extracted_metadata if hasattr(doc, 'has_extracted_metadata') else bool(metadata),
                    'has_vector_chunks': doc.has_vector_chunks if hasattr(doc, 'has_vector_chunks') else False
                }
                
                documents.append(doc_dict)
            
            return documents, total_count
            
        except Exception as e:
            logger.error(f"Error getting filtered documents: {e}")
            return [], 0
        finally:
            db.close()
    
    def delete_document(self, doc_id: str, session: Session = None) -> bool:
        """Delete a document."""
        db = session if session else self._get_session()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                db.delete(doc)
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def document_exists(self, doc_id: str, session: Session = None) -> bool:
        """Check if document exists."""
        db = session if session else self._get_session()
        try:
            exists = db.query(Document).filter(Document.id == doc_id).count() > 0
            return exists
        except Exception as e:
            logger.error(f"Error checking document {doc_id}: {e}")
            return False
        finally:
            db.close()
    
    def get_document_metadata(self, doc_id: str, session: Session = None) -> Optional[Dict[str, Any]]:
        """Get document metadata."""
        db = session if session else self._get_session()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                # Start with metadata_ field
                metadata = doc.metadata_ if hasattr(doc, 'metadata_') and doc.metadata_ else {}
                
                # Add extracted fields if not in metadata - support both naming conventions
                if 'title' not in metadata:
                    if hasattr(doc, 'title') and doc.title:
                        metadata['title'] = doc.title
                    elif hasattr(doc, 'extracted_title') and doc.extracted_title:
                        metadata['title'] = doc.extracted_title
                        
                if 'authors' not in metadata:
                    if hasattr(doc, 'authors') and doc.authors:
                        try:
                            metadata['authors'] = json.loads(doc.authors) if isinstance(doc.authors, str) else doc.authors
                        except:
                            metadata['authors'] = doc.authors
                    elif hasattr(doc, 'extracted_authors') and doc.extracted_authors:
                        metadata['authors'] = doc.extracted_authors
                        
                if 'year' not in metadata:
                    if hasattr(doc, 'publication_year') and doc.publication_year:
                        metadata['year'] = doc.publication_year
                    elif hasattr(doc, 'extracted_year') and doc.extracted_year:
                        metadata['year'] = doc.extracted_year
                        
                if 'journal' not in metadata:
                    if hasattr(doc, 'journal') and doc.journal:
                        metadata['journal'] = doc.journal
                    elif hasattr(doc, 'extracted_journal') and doc.extracted_journal:
                        metadata['journal'] = doc.extracted_journal
                
                return metadata
            return None
        except Exception as e:
            logger.error(f"Error getting metadata for document {doc_id}: {e}")
            return None
        finally:
            db.close()
    
    def get_all_document_ids(self, session: Session = None) -> List[str]:
        """Get all document IDs from the database."""
        db = session if session else self._get_session()
        try:
            doc_ids = [doc.id for doc in db.query(Document.id).all()]
            return doc_ids
        except Exception as e:
            logger.error(f"Error getting all document IDs: {e}")
            return []
        finally:
            db.close()


# Compatibility alias
DocumentDatabase = UnifiedDocumentDatabase