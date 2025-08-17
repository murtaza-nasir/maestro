"""
Improved Document CRUD Operations with Consistency Management

This module provides document CRUD operations that maintain consistency
across all storage systems using the DocumentConsistencyManager.
"""

import asyncio
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from database import crud
from database.models import Document
from ai_researcher.config import SERVER_TIMEZONE

logger = logging.getLogger(__name__)

# Lazy-loaded consistency manager instance
_consistency_manager = None

def get_consistency_manager():
    """Get or create the consistency manager instance (lazy initialization)."""
    global _consistency_manager
    if _consistency_manager is None:
        from services.document_consistency_manager import DocumentConsistencyManager
        _consistency_manager = DocumentConsistencyManager()
    return _consistency_manager

def get_current_time() -> datetime:
    """Returns the current time in the server's timezone."""
    return datetime.now(SERVER_TIMEZONE)

async def create_document_atomically(
    db: Session, 
    user_id: int, 
    original_filename: str, 
    file_content: bytes,
    group_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Document]:
    """
    Create a document atomically with consistent ID generation.
    
    This function:
    1. Generates a consistent 8-character document ID
    2. Creates the document record in main database
    3. Saves the physical file with the correct naming convention
    4. Adds to document group if specified
    5. Rolls back everything if any step fails
    """
    doc_id = get_consistency_manager().generate_consistent_doc_id()
    logger.info(f"Creating document {doc_id} with filename: {original_filename}")
    
    try:
        # Step 1: Save physical file first
        # Create appropriate directory based on file type
        filename_lower = original_filename.lower()
        
        if filename_lower.endswith('.pdf'):
            file_dir = get_consistency_manager().pdf_dir
        elif filename_lower.endswith(('.docx', '.doc')):
            file_dir = get_consistency_manager().pdf_dir / 'word_documents'  # Store Word docs in subdirectory
        elif filename_lower.endswith(('.md', '.markdown')):
            file_dir = get_consistency_manager().pdf_dir / 'markdown_files'  # Store Markdown files in subdirectory
        else:
            raise ValueError(f"Unsupported file format: {original_filename}")
            
        file_dir.mkdir(parents=True, exist_ok=True)
        file_path = file_dir / f"{doc_id}_{original_filename}"
        
        with open(file_path, 'wb') as f:
            f.write(file_content)
        logger.debug(f"Saved file: {file_path}")
        
        # Step 2: Create document record
        document_metadata = metadata or {}
        document_metadata.update({
            'status': 'uploaded',
            'file_path': str(file_path),
            'uploaded_at': get_current_time().isoformat()
        })
        
        try:
            document = crud.create_document(
                db=db,
                doc_id=doc_id,
                user_id=user_id,
                original_filename=original_filename,
                metadata=document_metadata,
                processing_status='queued',
                upload_progress=100,
                file_size=len(file_content),
                file_path=str(file_path)
            )
            logger.debug(f"Created document record in main database")
            
        except Exception as e:
            # Rollback: delete the file
            try:
                file_path.unlink()
                logger.info(f"Rolled back: deleted file {file_path}")
            except Exception as cleanup_error:
                logger.error(f"Failed to rollback file deletion: {cleanup_error}")
            raise e
            
        # Step 3: Add to group if specified
        if group_id:
            try:
                crud.add_document_to_group(db, group_id, doc_id, user_id)
                logger.debug(f"Added document to group {group_id}")
            except Exception as e:
                # Rollback: delete document record and file
                try:
                    db.delete(document)
                    db.commit()
                    file_path.unlink()
                    logger.info(f"Rolled back: deleted document record and file")
                except Exception as cleanup_error:
                    logger.error(f"Failed to rollback document creation: {cleanup_error}")
                raise e
                
        logger.info(f"Successfully created document {doc_id}")
        return document
        
    except Exception as e:
        logger.error(f"Failed to create document atomically: {e}")
        return None

def delete_document_atomically_sync(
    db: Session, 
    doc_id: str, 
    user_id: int
) -> bool:
    """
    Delete a document atomically from all storage systems.
    
    Directly handles deletion without using DocumentConsistencyManager to avoid async/sync issues.
    Ensures document is removed from:
    1. ChromaDB vector store (dense and sparse collections)
    2. Physical files (PDF, markdown, metadata JSON)
    3. Main application database with all metadata (last step)
    """
    logger.info(f"Deleting document {doc_id} atomically")
    
    try:
        # Step 1: Verify document exists and user has permission
        document = crud.get_document(db, doc_id, user_id)
        if not document:
            logger.warning(f"Document {doc_id} not found or user {user_id} lacks permission")
            # Check if document exists but belongs to another user
            from database.models import Document
            any_doc = db.query(Document).filter(Document.id == doc_id).first()
            if any_doc:
                logger.warning(f"Document {doc_id} exists but belongs to another user")
                return False
            else:
                logger.info(f"Document {doc_id} does not exist - may already be deleted")
                return True
        
        # Step 2: Delete from ChromaDB vector store
        try:
            from ai_researcher.core_rag.vector_store_singleton import get_vector_store
            vector_store = get_vector_store()
            dense_deleted, sparse_deleted = vector_store.delete_document(doc_id)
            
            if dense_deleted > 0 or sparse_deleted > 0:
                logger.info(f"Deleted {dense_deleted + sparse_deleted} chunks from vector store")
            else:
                logger.info(f"No chunks found in vector store for {doc_id}")
        except Exception as e:
            logger.error(f"Failed to delete from vector store: {e}")
            # Continue with other deletions even if vector store fails
        
        # Step 3: Delete physical files
        import shutil
        from pathlib import Path
        
        base_path = Path("/app/ai_researcher/data")
        pdf_dir = base_path / "raw_pdfs"
        markdown_dir = base_path / "processed" / "markdown"
        metadata_dir = base_path / "processed" / "metadata"
        
        files_deleted = []
        
        # Delete PDF files
        for pdf_file in pdf_dir.glob(f"{doc_id}_*"):
            try:
                pdf_file.unlink()
                files_deleted.append(str(pdf_file))
                logger.info(f"Deleted PDF file: {pdf_file}")
            except Exception as e:
                logger.error(f"Failed to delete PDF file {pdf_file}: {e}")
        
        # Delete markdown file
        markdown_file = markdown_dir / f"{doc_id}.md"
        if markdown_file.exists():
            try:
                markdown_file.unlink()
                files_deleted.append(str(markdown_file))
                logger.info(f"Deleted markdown file: {markdown_file}")
            except Exception as e:
                logger.error(f"Failed to delete markdown file: {e}")
        
        # Delete metadata file
        metadata_file = metadata_dir / f"{doc_id}.json"
        if metadata_file.exists():
            try:
                metadata_file.unlink()
                files_deleted.append(str(metadata_file))
                logger.info(f"Deleted metadata file: {metadata_file}")
            except Exception as e:
                logger.error(f"Failed to delete metadata file: {e}")
        
        if files_deleted:
            logger.info(f"Deleted {len(files_deleted)} physical files")
        
        # Step 4: Delete from main database (last step - point of no return)
        try:
            db.delete(document)
            db.commit()
            logger.info(f"Document {doc_id} successfully deleted from all systems")
            return True
        except Exception as e:
            logger.error(f"Failed to delete from main database: {e}")
            db.rollback()
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error during document deletion: {e}")
        import traceback
        traceback.print_exc()
        return False

async def delete_document_atomically(
    db: Session, 
    doc_id: str, 
    user_id: int
) -> bool:
    """
    Async wrapper for delete_document_atomically_sync.
    """
    # Run the synchronous function in a thread pool to avoid blocking
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, 
        delete_document_atomically_sync,
        db, doc_id, user_id
    )

async def cleanup_failed_document(
    db: Session,
    doc_id: str, 
    user_id: int
) -> bool:
    """
    Clean up a failed document processing attempt.
    
    Removes orphaned entries from AI database, vector store, and files
    while updating the main database status appropriately.
    """
    logger.info(f"Cleaning up failed document {doc_id}")
    
    try:
        success = await get_consistency_manager().cleanup_failed_document(doc_id, user_id, db)
        
        if success:
            logger.info(f"Successfully cleaned up failed document {doc_id}")
        else:
            logger.warning(f"Cleanup for document {doc_id} completed with some issues")
            
        return success
        
    except Exception as e:
        logger.error(f"Failed to cleanup document {doc_id}: {e}")
        return False

def check_document_consistency(
    db: Session,
    doc_id: str,
    user_id: int
) -> Dict[str, Any]:
    """
    Check the consistency of a document across all storage systems.
    
    Returns a detailed report of where the document exists and
    identifies any inconsistencies.
    """
    logger.debug(f"Checking consistency for document {doc_id}")
    
    exists = get_consistency_manager().check_document_exists(doc_id, user_id, db)
    
    # Analyze consistency
    main_doc = crud.get_document(db, doc_id, user_id)
    status = main_doc.processing_status if main_doc else None
    
    issues = []
    
    if status == 'completed':
        # Completed documents should exist in at least AI DB or vector store
        # CLI ingestion may not create markdown files, so we don't require them
        # We only require that if a document is marked completed, it has SOME data
        has_data = exists['ai_db'] or exists['vector_store']
        if not has_data:
            issues.append("Missing from both AI database and vector store")
            
    elif status == 'failed':
        # Failed documents should only exist in main database
        if exists['ai_db']:
            issues.append("Orphaned in AI database")
        if exists['vector_store']:
            issues.append("Orphaned in vector store")
        if exists['pdf_file'] or exists['markdown_file'] or exists['metadata_file']:
            issues.append("Orphaned files not cleaned up")
            
    elif status in ['queued', 'processing']:
        # Processing documents should have PDF file and main DB record
        if not exists['pdf_file']:
            issues.append("Missing PDF file for processing")
            
    consistency_report = {
        'doc_id': doc_id,
        'status': status,
        'exists_in': exists,
        'issues': issues,
        'is_consistent': len(issues) == 0
    }
    
    if issues:
        logger.warning(f"Consistency issues found for {doc_id}: {issues}")
    else:
        logger.debug(f"Document {doc_id} is consistent")
        
    return consistency_report

async def cleanup_all_user_orphans(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Clean up all orphaned documents for a specific user.
    
    Returns statistics about what was cleaned up.
    """
    logger.info(f"Cleaning up all orphans for user {user_id}")
    
    try:
        # Get orphan analysis
        orphans = get_consistency_manager().find_orphaned_documents(user_id, db)
        
        # Perform cleanup
        cleanup_stats = await get_consistency_manager().cleanup_all_orphans(user_id, db)
        
        result = {
            'orphans_found': orphans,
            'cleanup_performed': cleanup_stats,
            'total_issues_resolved': sum(cleanup_stats.values())
        }
        
        logger.info(f"Cleanup completed for user {user_id}: {cleanup_stats}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to cleanup orphans for user {user_id}: {e}")
        return {
            'orphans_found': {},
            'cleanup_performed': {},
            'total_issues_resolved': 0,
            'error': str(e)
        }

def get_document_processing_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Get comprehensive document processing statistics for a user."""
    
    try:
        # Get all user documents
        documents = crud.get_user_documents(db, user_id, limit=1000)
        
        stats = {
            'total_documents': len(documents),
            'by_status': {},
            'consistency_issues': 0,
            'storage_usage': {
                'main_db_records': 0,
                'ai_db_records': 0,
                'vector_store_chunks': 0,
                'physical_files': 0
            }
        }
        
        # Count by status
        for doc in documents:
            status = doc.processing_status
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1
            
        # Check for consistency issues
        inconsistent_docs = []
        for doc in documents:
            consistency = check_document_consistency(db, doc.id, user_id)
            if not consistency['is_consistent']:
                inconsistent_docs.append({
                    'doc_id': doc.id,
                    'filename': doc.original_filename,
                    'issues': consistency['issues']
                })
                
        stats['consistency_issues'] = len(inconsistent_docs)
        stats['inconsistent_documents'] = inconsistent_docs
        
        # Get storage system counts
        try:
            # AI database count
            manager = get_consistency_manager()
            ai_db = manager._get_ai_db()
            ai_doc_ids = ai_db.get_all_document_ids()
            user_ai_docs = [doc_id for doc_id in ai_doc_ids 
                          if any(d.id == doc_id for d in documents)]
            stats['storage_usage']['ai_db_records'] = len(user_ai_docs)
            
            # Vector store count
            vector_store = manager._get_vector_store()
            all_doc_ids = vector_store.get_all_document_ids()
            user_doc_ids = {d.id for d in documents}
            user_vector_docs = all_doc_ids.intersection(user_doc_ids)
            stats['storage_usage']['vector_store_chunks'] = len(user_vector_docs)
            
        except Exception as e:
            logger.warning(f"Could not get storage system stats: {e}")
            
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get processing stats for user {user_id}: {e}")
        return {'error': str(e)}

# Wrapper functions for backward compatibility
def delete_document_improved(db: Session, doc_id: str, user_id: int) -> bool:
    """Improved document deletion with consistency management (sync wrapper)."""
    try:
        return asyncio.run(delete_document_atomically(db, doc_id, user_id))
    except Exception as e:
        logger.error(f"Error in delete_document_improved: {e}")
        return False

def cleanup_failed_document_improved(db: Session, doc_id: str, user_id: int) -> bool:
    """Improved failed document cleanup (sync wrapper)."""
    try:
        return asyncio.run(cleanup_failed_document(db, doc_id, user_id))
    except Exception as e:
        logger.error(f"Error in cleanup_failed_document_improved: {e}")
        return False