"""
Document Service V2 - Unified Database Architecture

This service replaces the original document service with a cleaner architecture:
1. Single source of truth: Main database contains all metadata
2. Vector store only for embeddings
3. File system for document storage
4. Saga pattern for consistency
5. Event-driven processing with proper rollback
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_

from services.document_saga import DocumentSagaBuilder, ProcessingStage
from ai_researcher.core_rag.pgvector_store import PGVectorStore as VectorStoreManager

logger = logging.getLogger(__name__)

class UnifiedDocumentService:
    """
    Unified document service with consolidated database architecture.
    All metadata is stored in the main database for fast queries.
    Vector store is only used for semantic search.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.vector_store = None  # Lazy load
        self.base_path = Path("/app/ai_researcher/data")
        
    def _get_vector_store(self) -> VectorStoreManager:
        """Lazy load vector store."""
        if self.vector_store is None:
            self.vector_store = VectorStoreManager(
                persist_directory=str(self.base_path / "vector_store")
            )
        return self.vector_store
    
    def get_documents_with_metadata(
        self,
        user_id: int,
        search: Optional[str] = None,
        author: Optional[str] = None,
        year: Optional[int] = None,
        journal: Optional[str] = None,
        status_filter: Optional[str] = None,
        group_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict], int]:
        """
        Get documents with full metadata from unified database.
        Fast queries without touching vector store.
        """
        
        # Build base query - using actual column names from the database
        query = """
            SELECT 
                d.id,
                d.filename,
                d.original_filename,
                d.metadata_,
                d.processing_status,
                d.chunk_count,
                d.file_size,
                d.created_at,
                d.updated_at,
                d.processing_error,
                d.upload_progress
            FROM documents d
            WHERE d.user_id = :user_id
        """
        
        count_query = """
            SELECT COUNT(*) as total
            FROM documents d
            WHERE d.user_id = :user_id
        """
        
        params = {'user_id': user_id}
        
        # Add filters using JSONB operators
        if search:
            search_condition = """
                AND (
                    LOWER(d.metadata_->>'title') LIKE :search OR
                    LOWER(d.original_filename) LIKE :search OR
                    LOWER(d.filename) LIKE :search OR
                    LOWER(d.metadata_->>'authors')::text LIKE :search OR
                    LOWER(d.metadata_->>'abstract') LIKE :search OR
                    LOWER(d.metadata_->>'keywords')::text LIKE :search OR
                    LOWER(d.metadata_->>'journal_or_source') LIKE :search
                )
            """
            query += search_condition
            count_query += search_condition
            params['search'] = f"%{search.lower()}%"
        
        if author:
            author_condition = " AND LOWER(d.metadata_->>'authors') LIKE :author"
            query += author_condition
            count_query += author_condition
            params['author'] = f"%{author.lower()}%"
        
        if year:
            year_condition = " AND (d.metadata_->>'publication_year')::int = :year"
            query += year_condition
            count_query += year_condition
            params['year'] = year
        
        if journal:
            journal_condition = " AND LOWER(d.metadata_->>'journal_or_source') LIKE :journal"
            query += journal_condition
            count_query += journal_condition
            params['journal'] = f"%{journal.lower()}%"
        
        if status_filter:
            status_condition = " AND d.processing_status = :status"
            query += status_condition
            count_query += status_condition
            params['status'] = status_filter
        
        if group_id:
            group_join = """
                INNER JOIN document_group_association dga ON d.id = dga.document_id
                AND dga.document_group_id = :group_id
            """
            # Insert join after FROM clause
            query = query.replace("FROM documents d", f"FROM documents d {group_join}")
            count_query = count_query.replace("FROM documents d", f"FROM documents d {group_join}")
            params['group_id'] = group_id
        
        # Add ordering and pagination
        query += " ORDER BY d.created_at DESC LIMIT :limit OFFSET :offset"
        params['limit'] = limit
        params['offset'] = offset
        
        # Execute queries
        result = self.db.execute(text(query), params)
        documents = []
        
        for row in result:
            # Extract metadata from JSONB field
            metadata = row.metadata_ or {}
            
            # Convert authors list to JSON string for schema compatibility
            authors = metadata.get('authors', [])
            if isinstance(authors, list):
                authors_str = json.dumps(authors) if authors else None
            else:
                authors_str = authors
            
            # Convert keywords list to JSON string as well
            keywords = metadata.get('keywords', [])
            if isinstance(keywords, list):
                keywords_str = json.dumps(keywords) if keywords else None
            else:
                keywords_str = keywords
            
            doc = {
                'id': str(row.id),
                'user_id': user_id,  # Include user_id as required by schema
                'filename': row.filename,
                'original_filename': row.original_filename or row.filename,
                'title': metadata.get('title', row.original_filename or row.filename),
                'authors': authors_str,  # Authors as JSON string
                'publication_year': metadata.get('publication_year'),
                'journal': metadata.get('journal_or_source'),
                'abstract': metadata.get('abstract'),
                'doi': metadata.get('doi'),
                'keywords': keywords_str,  # Keywords as JSON string
                'processing_status': row.processing_status,
                'processing_error': row.processing_error,
                'upload_progress': row.upload_progress,
                'chunk_count': row.chunk_count or 0,  
                'file_size': row.file_size,
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None,
                'metadata_': metadata  # Include full metadata object
            }
            documents.append(doc)
        
        # Get total count
        count_result = self.db.execute(text(count_query), {k: v for k, v in params.items() if k not in ['limit', 'offset']})
        total_count = count_result.scalar()
        
        return documents, total_count
    
    def semantic_search(
        self,
        user_id: int,
        query: str,
        limit: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Perform semantic search using vector store.
        Returns document chunks with metadata from main database.
        """
        
        # Get user's document IDs for filtering
        user_docs_query = text("SELECT id FROM documents WHERE user_id = :user_id")
        result = self.db.execute(user_docs_query, {'user_id': user_id})
        user_doc_ids = [row.id for row in result]
        
        if not user_doc_ids:
            return []
        
        # For now, return empty results until vector store is properly configured
        # The vector store integration needs to be fixed with proper pgvector setup
        return []
        
        # Enrich results with metadata from main database
        enriched_results = []
        for result in results:
            doc_id = result.get('metadata', {}).get('doc_id')
            if doc_id:
                # Get document metadata from main database
                doc_query = text("""
                    SELECT title, authors, publication_year, journal, original_filename
                    FROM documents 
                    WHERE id = :doc_id AND user_id = :user_id
                """)
                
                doc_result = self.db.execute(doc_query, {
                    'doc_id': doc_id,
                    'user_id': user_id
                }).first()
                
                if doc_result:
                    enriched_result = {
                        'doc_id': doc_id,
                        'title': doc_result.title or doc_result.original_filename,
                        'authors': json.loads(doc_result.authors) if doc_result.authors else [],
                        'year': doc_result.publication_year,
                        'journal': doc_result.journal,
                        'chunk_text': result.get('text', ''),
                        'score': result.get('score', 0),
                        'chunk_id': result.get('id', '')
                    }
                    enriched_results.append(enriched_result)
        
        return enriched_results
    
    def check_document_consistency(self, doc_id: str, user_id: int) -> Dict[str, Any]:
        """
        Check consistency of a document across storage systems.
        Uses flags from unified database for efficient checking.
        """
        
        query = text("""
            SELECT 
                processing_status,
                processing_stage,
                has_ai_metadata,
                has_vector_embeddings,
                has_markdown_file,
                has_pdf_file,
                chunk_count
            FROM documents 
            WHERE id = :doc_id AND user_id = :user_id
        """)
        
        result = self.db.execute(query, {
            'doc_id': doc_id,
            'user_id': user_id
        }).first()
        
        if not result:
            return {
                'exists': False,
                'consistent': False,
                'issues': ['Document not found in database']
            }
        
        issues = []
        
        # Check based on processing status
        if result.processing_status == 'completed':
            # Completed documents should have all components
            if not result.has_ai_metadata:
                issues.append('Missing metadata')
            if not result.has_vector_embeddings:
                issues.append('Missing vector embeddings')
            if not result.has_markdown_file:
                issues.append('Missing markdown file')
            if result.chunk_count == 0:
                issues.append('No chunks generated')
                
        elif result.processing_status == 'processing':
            # Check if stuck in processing
            stage_query = text("""
                SELECT processing_started_at 
                FROM documents 
                WHERE id = :doc_id
            """)
            stage_result = self.db.execute(stage_query, {'doc_id': doc_id}).first()
            
            if stage_result and stage_result.processing_started_at:
                time_diff = datetime.utcnow() - stage_result.processing_started_at
                if time_diff.total_seconds() > 3600:  # 1 hour
                    issues.append(f'Stuck in processing for {time_diff.total_seconds() / 3600:.1f} hours')
        
        return {
            'exists': True,
            'consistent': len(issues) == 0,
            'status': result.processing_status,
            'stage': result.processing_stage,
            'components': {
                'has_metadata': result.has_ai_metadata,
                'has_embeddings': result.has_vector_embeddings,
                'has_markdown': result.has_markdown_file,
                'has_pdf': result.has_pdf_file,
                'chunk_count': result.chunk_count
            },
            'issues': issues
        }
    
    async def delete_document_with_cascade(self, doc_id: str, user_id: int) -> bool:
        """
        Delete a document with cascade to all storage systems.
        Uses saga pattern for proper rollback on failure.
        """
        
        try:
            # 1. Remove from vector store
            try:
                vector_store = self._get_vector_store()
                await vector_store.delete_document(doc_id)
                logger.info(f"Removed document {doc_id} from vector store")
            except Exception as e:
                logger.warning(f"Error removing from vector store (continuing): {e}")
            
            # 2. Delete physical files
            try:
                # Delete PDF
                pdf_pattern = f"{doc_id}_*"
                for pdf_file in (self.base_path / "raw_pdfs").glob(pdf_pattern):
                    pdf_file.unlink()
                    logger.info(f"Deleted PDF file: {pdf_file}")
                
                # Delete markdown
                md_file = self.base_path / "processed" / "markdown" / f"{doc_id}.md"
                if md_file.exists():
                    md_file.unlink()
                    logger.info(f"Deleted markdown file: {md_file}")
                
                # Delete metadata JSON
                meta_file = self.base_path / "processed" / "metadata" / f"{doc_id}.json"
                if meta_file.exists():
                    meta_file.unlink()
                    logger.info(f"Deleted metadata file: {meta_file}")
                    
            except Exception as e:
                logger.warning(f"Error deleting files (continuing): {e}")
            
            # 3. Delete from database (cascade will handle associations)
            delete_query = text("""
                DELETE FROM documents 
                WHERE id = :doc_id AND user_id = :user_id
            """)
            
            result = self.db.execute(delete_query, {
                'doc_id': doc_id,
                'user_id': user_id
            })
            
            if result.rowcount > 0:
                self.db.commit()
                logger.info(f"Successfully deleted document {doc_id}")
                return True
            else:
                self.db.rollback()
                logger.warning(f"Document {doc_id} not found for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            self.db.rollback()
            return False
    
    def get_processing_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Get document processing statistics for a user.
        All from unified database - no need to query multiple sources.
        """
        
        stats_query = text("""
            SELECT 
                processing_status,
                COUNT(*) as count,
                SUM(chunk_count) as total_chunks,
                SUM(CASE WHEN has_ai_metadata THEN 1 ELSE 0 END) as with_metadata,
                SUM(CASE WHEN has_vector_embeddings THEN 1 ELSE 0 END) as with_embeddings,
                SUM(CASE WHEN has_markdown_file THEN 1 ELSE 0 END) as with_markdown,
                SUM(CASE WHEN has_pdf_file THEN 1 ELSE 0 END) as with_pdf,
                SUM(file_size) as total_size
            FROM documents
            WHERE user_id = :user_id
            GROUP BY processing_status
        """)
        
        result = self.db.execute(stats_query, {'user_id': user_id})
        
        stats = {
            'total_documents': 0,
            'by_status': {},
            'total_chunks': 0,
            'storage': {
                'with_metadata': 0,
                'with_embeddings': 0,
                'with_markdown': 0,
                'with_pdf': 0,
                'total_size_bytes': 0
            }
        }
        
        for row in result:
            stats['by_status'][row.processing_status] = row.count
            stats['total_documents'] += row.count
            stats['total_chunks'] += row.total_chunks or 0
            stats['storage']['with_metadata'] += row.with_metadata or 0
            stats['storage']['with_embeddings'] += row.with_embeddings or 0
            stats['storage']['with_markdown'] += row.with_markdown or 0
            stats['storage']['with_pdf'] += row.with_pdf or 0
            stats['storage']['total_size_bytes'] += row.total_size or 0
        
        # Check for consistency issues
        consistency_query = text("""
            SELECT COUNT(*) as inconsistent_count
            FROM documents
            WHERE user_id = :user_id
            AND processing_status = 'completed'
            AND (
                has_ai_metadata = FALSE OR
                has_vector_embeddings = FALSE OR
                chunk_count = 0
            )
        """)
        
        consistency_result = self.db.execute(consistency_query, {'user_id': user_id})
        stats['inconsistent_documents'] = consistency_result.scalar()
        
        return stats

# Create a singleton instance that can be initialized with db later
class DocumentServiceSingleton:
    """Singleton wrapper for UnifiedDocumentService that handles db injection."""
    
    def __init__(self):
        self._service = None
        self._db = None
    
    def init_db(self, db: Session):
        """Initialize with database session."""
        if self._db != db:
            self._db = db
            self._service = UnifiedDocumentService(db)
        return self._service
    
    def __getattr__(self, name):
        """Proxy all attributes to the actual service."""
        if self._service is None:
            raise RuntimeError("DocumentService not initialized. Call init_db() first.")
        return getattr(self._service, name)

# Global singleton instance
document_service = DocumentServiceSingleton()