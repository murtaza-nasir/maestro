"""
Simple Document Consistency Checker

A lightweight consistency checker that avoids complex dependencies and circular imports.
Designed to be called manually or periodically without crashing the system.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class SimpleConsistencyChecker:
    """
    Simple consistency checker that directly queries databases and file systems
    without complex dependencies or circular imports.
    """
    
    def __init__(self):
        self.pdf_dir = Path("/app/ai_researcher/data/raw_pdfs")
        self.vector_store_dir = Path("/app/ai_researcher/data/vector_store")
        self.processed_dir = Path("/app/ai_researcher/data/processed")
        
    def check_document_files(self, doc_id: str) -> Dict[str, bool]:
        """
        Check if physical files exist for a document.
        """
        results = {
            'pdf_exists': False,
            'markdown_exists': False,
            'metadata_exists': False
        }
        
        try:
            # Check for PDF files
            if self.pdf_dir.exists():
                for pdf_file in self.pdf_dir.glob(f"{doc_id}*"):
                    if pdf_file.is_file():
                        results['pdf_exists'] = True
                        break
            
            # Check for markdown files
            markdown_dir = self.processed_dir / "markdown"
            if markdown_dir.exists():
                markdown_file = markdown_dir / f"{doc_id}.md"
                results['markdown_exists'] = markdown_file.exists()
            
            # Check for metadata files
            metadata_dir = self.processed_dir / "metadata"
            if metadata_dir.exists():
                metadata_file = metadata_dir / f"{doc_id}.json"
                results['metadata_exists'] = metadata_file.exists()
                
        except Exception as e:
            logger.error(f"Error checking files for document {doc_id}: {e}")
            
        return results
    
    def check_vector_store(self, doc_id: str) -> Dict[str, Any]:
        """
        Check if document exists in PostgreSQL document_chunks table.
        Returns detailed information about chunks found.
        """
        result = {
            'has_chunks': False,
            'chunk_count': 0,
            'chunks_with_doc_id': 0,
            'chunks_without_doc_id': 0,
            'error': None
        }
        
        try:
            # Check PostgreSQL for chunks
            from database.database import get_db
            from database.models import DocumentChunk
            
            db = next(get_db())
            try:
                # Count chunks for this document
                chunk_count = db.query(DocumentChunk).filter_by(doc_id=doc_id).count()
                result['chunks_with_doc_id'] = chunk_count
                result['chunk_count'] = chunk_count
                result['has_chunks'] = chunk_count > 0
                
                # Orphaned chunks would be checked separately (not per document)
                result['chunks_without_doc_id'] = 0
                
            finally:
                db.close()
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking vector store for document {doc_id}: {e}")
            result['error'] = str(e)
            return result
    
    def get_document_consistency_report(
        self, 
        db: Session, 
        doc_id: str, 
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get a consistency report for a single document.
        """
        report = {
            'doc_id': doc_id,
            'exists_in': {
                'main_db': False,
                'files': {},
                'vector_store_likely': False
            },
            'issues': [],
            'status': None
        }
        
        try:
            # Check main database
            query = "SELECT * FROM documents WHERE id = :doc_id"
            params = {'doc_id': doc_id}
            if user_id:
                query += " AND user_id = :user_id"
                params['user_id'] = user_id
                
            result = db.execute(text(query), params).first()
            
            if result:
                report['exists_in']['main_db'] = True
                report['status'] = result.processing_status
                
                # Check files
                file_status = self.check_document_files(doc_id)
                report['exists_in']['files'] = file_status
                
                # Proper vector store check
                vector_status = self.check_vector_store(doc_id)
                report['exists_in']['vector_store'] = vector_status
                report['exists_in']['vector_store_likely'] = vector_status['has_chunks']
                
                # Report orphaned chunks as an issue
                if vector_status.get('chunks_without_doc_id', 0) > 0:
                    report['issues'].append(f"Found {vector_status['chunks_without_doc_id']} orphaned chunks without doc_id in vector store")
                
                # Identify issues based on status
                if report['status'] == 'completed':
                    # Completed documents should have some processed data
                    if not (file_status['markdown_exists'] or file_status['metadata_exists']):
                        report['issues'].append("Marked as completed but missing processed files")
                    
                    # Completed documents MUST have chunks in vector store
                    if not vector_status['has_chunks']:
                        report['issues'].append(f"Completed document has NO chunks in vector store (unusable for search)")
                        
                elif report['status'] == 'failed':
                    # Failed documents should only have PDF, not processed files
                    if file_status['markdown_exists'] or file_status['metadata_exists']:
                        report['issues'].append("Failed document has orphaned processed files")
                        
                elif report['status'] in ['queued', 'processing']:
                    # Processing documents should have PDF
                    if not file_status['pdf_exists']:
                        report['issues'].append("Processing document missing PDF file")
            else:
                # Document not in main DB - check for orphaned files
                file_status = self.check_document_files(doc_id)
                if any(file_status.values()):
                    report['issues'].append("Orphaned files without database record")
                    report['exists_in']['files'] = file_status
                    
        except Exception as e:
            logger.error(f"Error getting consistency report for {doc_id}: {e}")
            report['issues'].append(f"Error during check: {str(e)}")
            
        report['is_consistent'] = len(report['issues']) == 0
        return report
    
    def check_user_documents(self, db: Session, user_id: int) -> Dict[str, Any]:
        """
        Check consistency for all documents of a user.
        """
        summary = {
            'user_id': user_id,
            'total_documents': 0,
            'consistent_documents': 0,
            'inconsistent_documents': [],
            'by_status': {},
            'total_issues': 0
        }
        
        try:
            # Get all user documents
            query = """
                SELECT id, original_filename, processing_status 
                FROM documents 
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """
            results = db.execute(text(query), {'user_id': user_id}).fetchall()
            
            summary['total_documents'] = len(results)
            
            for row in results:
                doc_id = row.id
                filename = row.original_filename
                status = row.processing_status
                
                # Count by status
                summary['by_status'][status] = summary['by_status'].get(status, 0) + 1
                
                # Check consistency
                report = self.get_document_consistency_report(db, doc_id, user_id)
                
                if report['is_consistent']:
                    summary['consistent_documents'] += 1
                else:
                    summary['inconsistent_documents'].append({
                        'doc_id': doc_id,
                        'filename': filename,
                        'status': status,
                        'issues': report['issues']
                    })
                    summary['total_issues'] += len(report['issues'])
                    
        except Exception as e:
            logger.error(f"Error checking documents for user {user_id}: {e}")
            summary['error'] = str(e)
            
        return summary
    
    def cleanup_orphaned_files(self, doc_id: str) -> Dict[str, int]:
        """
        Clean up orphaned files for a document.
        Returns count of files deleted.
        """
        deleted = {
            'pdfs': 0,
            'markdown': 0,
            'metadata': 0
        }
        
        try:
            # Clean up PDFs
            if self.pdf_dir.exists():
                for pdf_file in self.pdf_dir.glob(f"{doc_id}*"):
                    if pdf_file.is_file():
                        pdf_file.unlink()
                        deleted['pdfs'] += 1
                        logger.info(f"Deleted orphaned PDF: {pdf_file}")
            
            # Clean up markdown
            markdown_file = self.processed_dir / "markdown" / f"{doc_id}.md"
            if markdown_file.exists():
                markdown_file.unlink()
                deleted['markdown'] = 1
                logger.info(f"Deleted orphaned markdown: {markdown_file}")
            
            # Clean up metadata
            metadata_file = self.processed_dir / "metadata" / f"{doc_id}.json"
            if metadata_file.exists():
                metadata_file.unlink()
                deleted['metadata'] = 1
                logger.info(f"Deleted orphaned metadata: {metadata_file}")
                
        except Exception as e:
            logger.error(f"Error cleaning up files for {doc_id}: {e}")
            
        return deleted
    
    def cleanup_old_failed_documents(self, db: Session, hours: int = 24) -> Dict[str, Any]:
        """
        Clean up failed documents older than specified hours.
        """
        cleanup_summary = {
            'documents_deleted': 0,
            'files_cleaned': 0,
            'errors': []
        }
        
        try:
            # Find old failed documents
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            query = """
                SELECT id, original_filename, created_at 
                FROM documents 
                WHERE processing_status = 'failed' 
                AND created_at < :cutoff_time
            """
            
            results = db.execute(text(query), {'cutoff_time': cutoff_time}).fetchall()
            
            for row in results:
                doc_id = row.id
                filename = row.original_filename
                
                try:
                    # Clean up files first
                    deleted_files = self.cleanup_orphaned_files(doc_id)
                    if sum(deleted_files.values()) > 0:
                        cleanup_summary['files_cleaned'] += sum(deleted_files.values())
                    
                    # Delete from database
                    db.execute(text("DELETE FROM documents WHERE id = :doc_id"), {'doc_id': doc_id})
                    cleanup_summary['documents_deleted'] += 1
                    
                    logger.info(f"Cleaned up failed document: {doc_id} ({filename})")
                    
                except Exception as e:
                    error_msg = f"Error cleaning up {doc_id}: {str(e)}"
                    logger.error(error_msg)
                    cleanup_summary['errors'].append(error_msg)
            
            db.commit()
            
        except Exception as e:
            logger.error(f"Error during cleanup of old failed documents: {e}")
            cleanup_summary['errors'].append(str(e))
            db.rollback()
            
        return cleanup_summary
    
    def get_system_summary(self, db: Session) -> Dict[str, Any]:
        """
        Get a system-wide consistency summary.
        """
        summary = {
            'total_users': 0,
            'total_documents': 0,
            'users_checked': 0,
            'users_with_issues': [],
            'total_consistency_issues': 0,
            'orphaned_chunks_without_doc_id': 0,
            'check_timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            # Get all users with documents
            query = """
                SELECT DISTINCT u.id, u.username, COUNT(d.id) as doc_count
                FROM users u
                JOIN documents d ON u.id = d.user_id
                GROUP BY u.id, u.username
                ORDER BY doc_count DESC
            """
            
            users = db.execute(text(query)).fetchall()
            summary['total_users'] = len(users)
            
            # Count total documents
            total_docs_result = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
            summary['total_documents'] = total_docs_result or 0
            
            # Check each user's documents
            for user_row in users:
                user_id = user_row.id
                username = user_row.username
                doc_count = user_row.doc_count
                
                user_check = self.check_user_documents(db, user_id)
                summary['users_checked'] += 1
                
                if user_check['total_issues'] > 0:
                    summary['users_with_issues'].append({
                        'user_id': user_id,
                        'username': username,
                        'document_count': doc_count,
                        'issues_count': user_check['total_issues'],
                        'inconsistent_documents': len(user_check['inconsistent_documents'])
                    })
                    summary['total_consistency_issues'] += user_check['total_issues']
            
            # Check for system-wide orphaned chunks in PostgreSQL
            try:
                from database.database import get_db
                from database.models import DocumentChunk, Document
                
                db = next(get_db())
                try:
                    # Find chunks where doc_id doesn't exist in documents table
                    orphaned_query = db.query(DocumentChunk).outerjoin(
                        Document, DocumentChunk.doc_id == Document.id
                    ).filter(Document.id == None)
                    
                    orphaned_count = orphaned_query.count()
                    
                    summary['orphaned_chunks_without_doc_id'] = orphaned_count
                    if orphaned_count > 0:
                        summary['total_consistency_issues'] += 1
                        logger.warning(f"Found {orphaned_count} orphaned chunks in PostgreSQL without matching document")
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Could not check for orphaned chunks: {e}")
                    
        except Exception as e:
            logger.error(f"Error getting system summary: {e}")
            summary['error'] = str(e)
            
        return summary


# Global instance
simple_checker = SimpleConsistencyChecker()


async def run_consistency_check(db: Session) -> Dict[str, Any]:
    """
    Run a full consistency check across the system.
    This is the main entry point for consistency checking.
    """
    logger.info("Starting simple consistency check")
    
    try:
        # Get system summary
        summary = simple_checker.get_system_summary(db)
        
        # Clean up old failed documents
        cleanup_result = simple_checker.cleanup_old_failed_documents(db)
        summary['cleanup_performed'] = cleanup_result
        
        logger.info(f"Consistency check completed. Found {summary['total_consistency_issues']} issues")
        
        return summary
        
    except Exception as e:
        logger.error(f"Error during consistency check: {e}")
        return {'error': str(e)}


async def check_single_document(
    db: Session, 
    doc_id: str, 
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Check consistency for a single document.
    """
    return simple_checker.get_document_consistency_report(db, doc_id, user_id)


async def check_user_consistency(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Check consistency for all documents of a specific user.
    """
    return simple_checker.check_user_documents(db, user_id)