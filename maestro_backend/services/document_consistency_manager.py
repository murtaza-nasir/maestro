"""
Document Consistency Manager

This module ensures atomic operations across all document storage systems:
1. Main Database (maestro.db) - Document records and processing status
2. AI Database (metadata.db) - Extracted document metadata  
3. ChromaDB Vector Store - Document embeddings and chunks
4. File System - Original PDFs and processed files

Key features:
- Atomic operations with rollback capability
- Consistent document ID generation
- Comprehensive cleanup on failures
- Transaction-like behavior across multiple systems
"""

import os
import shutil
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from sqlalchemy.orm import Session
import logging

# Use direct vector store access to avoid locking issues
from ai_researcher.core_rag.pgvector_store import PGVectorStore as VectorStore
from database import crud, models

logger = logging.getLogger(__name__)

class DocumentTransaction:
    """Manages a document operation transaction across all storage systems."""
    
    def __init__(self, doc_id: str, operation: str):
        self.doc_id = doc_id
        self.operation = operation  # 'create', 'update', 'delete'
        self.rollback_actions: List[callable] = []
        self.completed_steps: List[str] = []
        self.failed_at_step: Optional[str] = None
        
    def add_rollback_action(self, action: callable, description: str):
        """Add an action to be performed if rollback is needed."""
        self.rollback_actions.append((action, description))
        
    def mark_step_completed(self, step_name: str):
        """Mark a step as completed."""
        self.completed_steps.append(step_name)
        logger.debug(f"[{self.doc_id}] Completed step: {step_name}")
        
    def rollback(self):
        """Execute rollback actions in reverse order."""
        logger.warning(f"[{self.doc_id}] Rolling back transaction. Failed at: {self.failed_at_step}")
        
        for action, description in reversed(self.rollback_actions):
            try:
                action()
                logger.info(f"[{self.doc_id}] Rollback: {description}")
            except Exception as e:
                logger.error(f"[{self.doc_id}] Rollback failed for '{description}': {e}")

class DocumentConsistencyManager:
    """Manages consistent document operations across all storage systems."""
    
    def __init__(self, base_path: str = "/app/ai_researcher/data"):
        self.base_path = Path(base_path)
        self.pdf_dir = self.base_path / "raw_pdfs"
        self.markdown_dir = self.base_path / "processed" / "markdown"  
        self.metadata_dir = self.base_path / "processed" / "metadata"
        self.db_path = "data/maestro.db"  # Use unified database
        
        # Ensure directories exist
        for dir_path in [self.pdf_dir, self.markdown_dir, self.metadata_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
            
        # Initialize storage components (lazy loaded)
        self._vector_store = None
        
    def _get_vector_store(self) -> VectorStore:
        """Get or initialize vector store."""
        if self._vector_store is None:
            self._vector_store = VectorStore()
        return self._vector_store
    
    def generate_consistent_doc_id(self) -> str:
        """Generate a consistent UUID document ID."""
        return str(uuid.uuid4())
        
    def validate_doc_id_format(self, doc_id: str) -> bool:
        """Validate document ID format (UUID format)."""
        try:
            uuid.UUID(doc_id)
            return True
        except (ValueError, AttributeError):
            return False
    
    def check_document_exists(self, doc_id: str, user_id: int, db: Session) -> Dict[str, bool]:
        """Check where a document exists across all storage systems."""
        exists = {
            'main_db': False,
            'ai_db': False, 
            'vector_store': False,
            'pdf_file': False,
            'markdown_file': False,
            'metadata_file': False
        }
        
        try:
            # Check main database
            main_doc = crud.get_document(db, doc_id, user_id)
            exists['main_db'] = main_doc is not None
            
            # AI database no longer exists - metadata is in main database
            exists['ai_db'] = exists['main_db']  # For backwards compatibility
                
            # Check vector store
            try:
                vector_store = self._get_vector_store()
                exists['vector_store'] = vector_store.check_document_exists(doc_id)
            except Exception:
                exists['vector_store'] = False
                
            # Check files
            exists['pdf_file'] = any((self.pdf_dir).glob(f"{doc_id}_*"))
            exists['markdown_file'] = (self.markdown_dir / f"{doc_id}.md").exists()
            exists['metadata_file'] = (self.metadata_dir / f"{doc_id}.json").exists()
            
        except Exception as e:
            logger.error(f"Error checking document existence for {doc_id}: {e}")
            
        return exists
    
    def find_orphaned_documents(self, user_id: int, db: Session) -> Dict[str, List[str]]:
        """Find orphaned documents across all storage systems."""
        orphans = {
            'main_db_only': [],      # In main DB but nowhere else
            'ai_db_only': [],        # In AI DB but not main DB  
            'vector_store_only': [], # In vector store but not main DB
            'files_only': [],        # Files exist but no DB records
            'partial_processing': [] # In main DB but missing from other systems
        }
        
        try:
            # Get all documents from main database for this user
            main_docs = crud.get_user_documents(db, user_id, limit=1000)
            main_doc_ids = {doc.id for doc in main_docs}
            
            # AI database no longer exists - all documents are in main database
            ai_doc_ids = main_doc_ids  # For backwards compatibility
                
            # Get documents from vector store - filter to only this user's documents
            try:
                vector_store = self._get_vector_store()
                all_vector_doc_ids = vector_store.get_all_document_ids()
                
                # Only consider vector documents that belong to this user or no user
                vector_doc_ids = set()
                for doc_id in all_vector_doc_ids:
                    if doc_id in main_doc_ids:
                        vector_doc_ids.add(doc_id)
                    else:
                        # Check if this document belongs to another user
                        other_user_doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
                        if not other_user_doc:
                            # This document doesn't belong to any user - it's a true orphan
                            vector_doc_ids.add(doc_id)
            except Exception as e:
                logger.error(f"Error getting vector store documents: {e}")
                vector_doc_ids = set()
                
            # Find orphans - now these are only documents that don't belong to ANY user
            orphans['ai_db_only'] = list(ai_doc_ids - main_doc_ids)
            orphans['vector_store_only'] = list(vector_doc_ids - main_doc_ids)
            
            # Check main DB documents for completeness
            for doc in main_docs:
                doc_id = doc.id
                if doc.processing_status == 'completed':
                    # Should exist in all systems
                    if doc_id not in ai_doc_ids:
                        orphans['partial_processing'].append(f"{doc_id} (missing from AI DB)")
                    if doc_id not in vector_doc_ids:
                        orphans['partial_processing'].append(f"{doc_id} (missing from vector store)")
                elif doc.processing_status == 'failed':
                    # Should be cleaned up
                    exists = self.check_document_exists(doc_id, user_id, db)
                    if any([exists['ai_db'], exists['vector_store'], exists['pdf_file'], 
                           exists['markdown_file'], exists['metadata_file']]):
                        orphans['partial_processing'].append(f"{doc_id} (failed but not cleaned up)")
                        
        except Exception as e:
            logger.error(f"Error finding orphaned documents: {e}")
            
        return orphans
    
    async def delete_document_atomically(self, doc_id: str, user_id: int, db: Session) -> bool:
        """
        Delete a document atomically from all storage systems.
        
        Ensures document is removed from:
        1. ChromaDB vector store (dense and sparse collections)
        2. Physical files (PDF, markdown, metadata JSON)
        3. Main application database with all metadata (last step)
        """
        transaction = DocumentTransaction(doc_id, 'delete')
        logger.info(f"Starting atomic deletion for document {doc_id}")
        
        try:
            # Step 1: Verify document exists and user has permission
            document = crud.get_document(db, doc_id, user_id)
            if not document:
                logger.warning(f"Document {doc_id} not found in main database or user lacks permission")
                # Check if document exists but user doesn't have permission
                from database.models import Document
                any_doc = db.query(Document).filter(Document.id == doc_id).first()
                if any_doc:
                    logger.warning(f"Document {doc_id} exists but user {user_id} lacks permission")
                    return False
                else:
                    # Document doesn't exist at all - might already be deleted
                    logger.info(f"Document {doc_id} does not exist - may already be deleted")
                    return True
                
            transaction.mark_step_completed('document_verified')
            
            # Step 2: Delete from ChromaDB vector store
            try:
                vector_store = self._get_vector_store()
                dense_deleted, sparse_deleted = vector_store.delete_document(doc_id)
                
                if dense_deleted > 0 or sparse_deleted > 0:
                    transaction.add_rollback_action(
                        lambda: logger.warning(f"Cannot rollback vector store deletion for {doc_id}"),
                        f"Vector store deletion (not reversible)"
                    )
                    transaction.mark_step_completed('vector_store_deleted')
                    logger.info(f"Deleted {dense_deleted + sparse_deleted} chunks from vector store")
                else:
                    logger.info(f"No chunks found in vector store for {doc_id}")
                    transaction.mark_step_completed('vector_store_deleted')
                    
            except Exception as e:
                transaction.failed_at_step = 'vector_store_deletion'
                logger.error(f"Failed to delete from vector store: {e}")
                # Continue with other deletions even if vector store fails
                
            # Step 3: Note about unified database
            # Metadata is now stored in the main database (documents table)
            # It will be deleted in the final step along with the document record
            logger.info(f"Document metadata is in main database - will be deleted with document record")
                
            # Step 4: Delete physical files
            files_deleted = []
            
            # Delete PDF files
            for pdf_file in self.pdf_dir.glob(f"{doc_id}_*"):
                try:
                    backup_path = pdf_file.with_suffix(f'.backup_{int(datetime.now().timestamp())}')
                    shutil.move(str(pdf_file), str(backup_path))
                    files_deleted.append(str(pdf_file))
                    transaction.add_rollback_action(
                        lambda: shutil.move(str(backup_path), str(pdf_file)),
                        f"Restore PDF file {pdf_file.name}"
                    )
                except Exception as e:
                    logger.error(f"Failed to delete PDF file {pdf_file}: {e}")
                    
            # Delete markdown file
            markdown_file = self.markdown_dir / f"{doc_id}.md"
            if markdown_file.exists():
                try:
                    backup_path = markdown_file.with_suffix(f'.backup_{int(datetime.now().timestamp())}')
                    shutil.move(str(markdown_file), str(backup_path))
                    files_deleted.append(str(markdown_file))
                    transaction.add_rollback_action(
                        lambda: shutil.move(str(backup_path), str(markdown_file)),
                        f"Restore markdown file"
                    )
                except Exception as e:
                    logger.error(f"Failed to delete markdown file: {e}")
                    
            # Delete metadata file
            metadata_file = self.metadata_dir / f"{doc_id}.json"
            if metadata_file.exists():
                try:
                    backup_path = metadata_file.with_suffix(f'.backup_{int(datetime.now().timestamp())}')
                    shutil.move(str(metadata_file), str(backup_path))
                    files_deleted.append(str(metadata_file))
                    transaction.add_rollback_action(
                        lambda: shutil.move(str(backup_path), str(metadata_file)),
                        f"Restore metadata file"
                    )
                except Exception as e:
                    logger.error(f"Failed to delete metadata file: {e}")
                    
            if files_deleted:
                transaction.mark_step_completed('files_deleted')
                logger.info(f"Deleted {len(files_deleted)} physical files")
                
            # Step 5: Delete from main database (last step - point of no return)
            try:
                # Re-fetch the document to ensure it still exists before deletion
                document = crud.get_document(db, doc_id, user_id)
                if not document:
                    logger.warning(f"Document {doc_id} already deleted or not found")
                    # If already gone, consider it successfully deleted
                    transaction.mark_step_completed('main_db_deleted')
                    return True
                    
                db.delete(document)
                db.commit()
                transaction.mark_step_completed('main_db_deleted')
                logger.info(f"Document {doc_id} successfully deleted from all systems")
                return True
                
            except Exception as e:
                transaction.failed_at_step = 'main_db_deletion'
                logger.error(f"Failed to delete from main database: {e}")
                db.rollback()
                transaction.rollback()
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error during document deletion: {e}")
            transaction.rollback()
            return False
    
    async def cleanup_failed_document(self, doc_id: str, user_id: int, db: Session) -> bool:
        """Clean up a failed document processing attempt."""
        transaction = DocumentTransaction(doc_id, 'cleanup')
        
        try:
            # Check current state
            exists = self.check_document_exists(doc_id, user_id, db)
            
            # AI database no longer exists - skip this step
            transaction.mark_step_completed('ai_db_cleaned')
            logger.info(f"AI database no longer exists - skipping cleanup")
                    
            # Clean up vector store entries
            if exists['vector_store']:
                try:
                    vector_store = self._get_vector_store()
                    dense_deleted, sparse_deleted = vector_store.delete_document(doc_id)
                    
                    if dense_deleted > 0 or sparse_deleted > 0:
                        transaction.mark_step_completed('vector_store_cleaned')
                        logger.info(f"Cleaned up {dense_deleted + sparse_deleted} chunks from vector store")
                    
                except Exception as e:
                    logger.error(f"Failed to clean up vector store: {e}")
                    
            # Clean up files
            files_cleaned = []
            
            # Clean up PDF files
            for pdf_file in self.pdf_dir.glob(f"{doc_id}_*"):
                try:
                    pdf_file.unlink()
                    files_cleaned.append(str(pdf_file))
                except Exception as e:
                    logger.error(f"Failed to delete PDF file {pdf_file}: {e}")
                    
            # Clean up markdown file
            if exists['markdown_file']:
                try:
                    (self.markdown_dir / f"{doc_id}.md").unlink()
                    files_cleaned.append("markdown")
                except Exception as e:
                    logger.error(f"Failed to delete markdown file: {e}")
                    
            # Clean up metadata file
            if exists['metadata_file']:
                try:
                    (self.metadata_dir / f"{doc_id}.json").unlink()
                    files_cleaned.append("metadata")
                except Exception as e:
                    logger.error(f"Failed to delete metadata file: {e}")
                    
            if files_cleaned:
                transaction.mark_step_completed('files_cleaned')
                
            # Update main database status
            document = crud.get_document(db, doc_id, user_id)
            if document:
                try:
                    # Update status and error message
                    document.processing_status = 'failed'
                    document.processing_error = 'Cleaned up after failed processing'
                    metadata = document.metadata_ or {}
                    metadata['cleaned_up_at'] = datetime.utcnow().isoformat()
                    document.metadata_ = metadata
                    db.commit()
                    transaction.mark_step_completed('main_db_updated')
                except Exception as e:
                    logger.error(f"Failed to update main database status: {e}")
                    db.rollback()
                    
            logger.info(f"Successfully cleaned up failed document {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False
    
    async def cleanup_all_orphans(self, user_id: int, db: Session) -> Dict[str, int]:
        """Clean up all orphaned documents for a user."""
        orphans = self.find_orphaned_documents(user_id, db)
        cleanup_stats = {
            'ai_db_cleaned': 0,
            'vector_store_cleaned': 0, 
            'files_cleaned': 0,
            'main_db_updated': 0
        }
        
        try:
            # Clean up AI DB only orphans
            ai_db = self._get_ai_db()
            for doc_id in orphans['ai_db_only']:
                try:
                    if ai_db.delete_document(doc_id):
                        cleanup_stats['ai_db_cleaned'] += 1
                        logger.info(f"Cleaned up AI DB orphan: {doc_id}")
                except Exception as e:
                    logger.error(f"Failed to clean up AI DB orphan {doc_id}: {e}")
                    
            # Clean up vector store only orphans
            vector_store = self._get_vector_store()
            for doc_id in orphans['vector_store_only']:
                try:
                    dense_deleted, sparse_deleted = vector_store.delete_document(doc_id)
                    
                    if dense_deleted > 0 or sparse_deleted > 0:
                        cleanup_stats['vector_store_cleaned'] += 1
                        logger.info(f"Cleaned up vector store orphan: {doc_id} ({dense_deleted + sparse_deleted} chunks)")
                        
                except Exception as e:
                    logger.error(f"Failed to clean up vector store orphan {doc_id}: {e}")
                    
            # Handle partial processing issues
            for partial_info in orphans['partial_processing']:
                doc_id = partial_info.split(' ')[0]  # Extract doc_id from description
                try:
                    await self.cleanup_failed_document(doc_id, user_id, db)
                    cleanup_stats['main_db_updated'] += 1
                except Exception as e:
                    logger.error(f"Failed to clean up partial processing for {doc_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error during orphan cleanup: {e}")
            
        return cleanup_stats