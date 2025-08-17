"""
Document Consistency Monitor V2 - Simplified Architecture

This version works with the unified database architecture where:
1. All metadata is in the main database
2. Vector store only contains embeddings
3. Consistency is tracked via flags in the main database

Much simpler and more reliable than the previous multi-database approach.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text

from database.database import get_db
from services.document_service_v2 import UnifiedDocumentService

logger = logging.getLogger(__name__)

class SimplifiedConsistencyMonitor:
    """
    Simplified consistency monitor for unified architecture.
    Only checks for truly problematic inconsistencies.
    """
    
    def __init__(self, check_interval_hours: int = 12):
        self.check_interval_hours = check_interval_hours
        self.is_running = False
        self.last_check = None
        self.initial_delay_minutes = 10  # Wait 10 minutes on startup
        
    async def start_monitoring(self):
        """Start the consistency monitoring loop."""
        if self.is_running:
            logger.warning("Consistency monitor is already running")
            return
            
        self.is_running = True
        logger.info(f"Starting consistency monitor (interval: {self.check_interval_hours} hours)")
        
        # Initial delay to let system stabilize
        logger.info(f"Waiting {self.initial_delay_minutes} minutes before first check...")
        await asyncio.sleep(self.initial_delay_minutes * 60)
        
        while self.is_running:
            try:
                await self._perform_consistency_check()
                
                # Wait for next check
                await asyncio.sleep(self.check_interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"Error in consistency monitoring: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    def stop_monitoring(self):
        """Stop the consistency monitoring."""
        logger.info("Stopping consistency monitor")
        self.is_running = False
    
    async def _perform_consistency_check(self):
        """
        Perform consistency check using unified database.
        Much simpler than before - just check flags.
        """
        logger.info("Starting periodic consistency check")
        self.last_check = datetime.utcnow()
        
        db = next(get_db())
        try:
            issues = await self._check_all_documents(db)
            
            if issues['total_issues'] > 0:
                logger.warning(f"Found {issues['total_issues']} consistency issues")
                await self._handle_issues(db, issues)
            else:
                logger.info("No consistency issues found")
                
        except Exception as e:
            logger.error(f"Error during consistency check: {e}")
        finally:
            db.close()
    
    async def _check_all_documents(self, db: Session) -> Dict[str, Any]:
        """
        Check all documents for consistency issues.
        Returns detailed issue report.
        """
        
        issues = {
            'total_issues': 0,
            'stuck_processing': [],
            'incomplete_completed': [],
            'orphaned_files': [],
            'missing_embeddings': []
        }
        
        # 1. Find documents stuck in processing (> 2 hours)
        stuck_query = text("""
            SELECT id, user_id, original_filename, processing_stage, processing_started_at
            FROM documents
            WHERE processing_status = 'processing'
            AND processing_started_at < :cutoff_time
        """)
        
        cutoff_time = datetime.utcnow() - timedelta(hours=2)
        stuck_docs = db.execute(stuck_query, {'cutoff_time': cutoff_time})
        
        for doc in stuck_docs:
            issues['stuck_processing'].append({
                'doc_id': doc.id,
                'user_id': doc.user_id,
                'filename': doc.original_filename,
                'stage': doc.processing_stage,
                'started_at': doc.processing_started_at
            })
            issues['total_issues'] += 1
        
        # 2. Find completed documents missing required components
        incomplete_query = text("""
            SELECT id, user_id, original_filename,
                   has_ai_metadata, has_vector_embeddings, chunk_count
            FROM documents
            WHERE processing_status = 'completed'
            AND created_at < :grace_period
            AND (
                has_ai_metadata = FALSE OR
                has_vector_embeddings = FALSE OR
                chunk_count = 0
            )
        """)
        
        # Give 30 minutes grace period for recent documents
        grace_period = datetime.utcnow() - timedelta(minutes=30)
        incomplete_docs = db.execute(incomplete_query, {'grace_period': grace_period})
        
        for doc in incomplete_docs:
            missing = []
            if not doc.has_ai_metadata:
                missing.append('metadata')
            if not doc.has_vector_embeddings:
                missing.append('embeddings')
            if doc.chunk_count == 0:
                missing.append('chunks')
                
            issues['incomplete_completed'].append({
                'doc_id': doc.id,
                'user_id': doc.user_id,
                'filename': doc.original_filename,
                'missing': missing
            })
            issues['total_issues'] += 1
        
        # 3. Find failed documents older than 24 hours
        failed_query = text("""
            SELECT id, user_id, original_filename, processing_error
            FROM documents
            WHERE processing_status = 'failed'
            AND created_at < :cutoff_time
            AND (
                has_pdf_file = TRUE OR
                has_markdown_file = TRUE OR
                has_vector_embeddings = TRUE
            )
        """)
        
        failed_cutoff = datetime.utcnow() - timedelta(hours=24)
        failed_docs = db.execute(failed_query, {'cutoff_time': failed_cutoff})
        
        for doc in failed_docs:
            issues['orphaned_files'].append({
                'doc_id': doc.id,
                'user_id': doc.user_id,
                'filename': doc.original_filename,
                'error': doc.processing_error
            })
            issues['total_issues'] += 1
        
        return issues
    
    async def _handle_issues(self, db: Session, issues: Dict[str, Any]):
        """
        Handle discovered issues appropriately.
        More conservative than before - mostly just logging.
        """
        
        # 1. Handle stuck processing documents
        if issues['stuck_processing']:
            logger.warning(f"Found {len(issues['stuck_processing'])} documents stuck in processing")
            
            for doc in issues['stuck_processing']:
                # Mark as failed after being stuck for too long
                update_query = text("""
                    UPDATE documents
                    SET processing_status = 'failed',
                        processing_error = 'Processing timeout - stuck for over 2 hours',
                        processing_stage = 'failed',
                        updated_at = :now
                    WHERE id = :doc_id
                """)
                
                try:
                    db.execute(update_query, {
                        'doc_id': doc['doc_id'],
                        'now': datetime.utcnow()
                    })
                    db.commit()
                    logger.info(f"Marked stuck document {doc['doc_id']} as failed")
                except Exception as e:
                    logger.error(f"Error marking document as failed: {e}")
                    db.rollback()
        
        # 2. Log incomplete completed documents (don't auto-fix)
        if issues['incomplete_completed']:
            logger.warning(f"Found {len(issues['incomplete_completed'])} incomplete 'completed' documents")
            
            for doc in issues['incomplete_completed']:
                logger.warning(
                    f"Document {doc['doc_id']} ({doc['filename']}) "
                    f"missing: {', '.join(doc['missing'])}"
                )
                
                # Could trigger re-processing here if needed
                # For now, just log for manual intervention
        
        # 3. Clean up old failed documents with orphaned files
        if issues['orphaned_files']:
            logger.info(f"Found {len(issues['orphaned_files'])} failed documents with orphaned files")
            
            service = UnifiedDocumentService(db)
            for doc in issues['orphaned_files']:
                try:
                    # Delete the document and all associated files
                    success = await service.delete_document_with_cascade(
                        doc['doc_id'], 
                        doc['user_id']
                    )
                    if success:
                        logger.info(f"Cleaned up failed document {doc['doc_id']}")
                    else:
                        logger.warning(f"Could not clean up document {doc['doc_id']}")
                except Exception as e:
                    logger.error(f"Error cleaning up document {doc['doc_id']}: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current monitor status."""
        return {
            'is_running': self.is_running,
            'check_interval_hours': self.check_interval_hours,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'next_check': (
                self.last_check + timedelta(hours=self.check_interval_hours)
            ).isoformat() if self.last_check else None
        }
    
    async def force_check(self) -> Dict[str, Any]:
        """Manually trigger a consistency check."""
        logger.info("Manual consistency check triggered")
        
        db = next(get_db())
        try:
            start_time = datetime.utcnow()
            issues = await self._check_all_documents(db)
            
            # Don't auto-fix in manual mode, just report
            end_time = datetime.utcnow()
            
            return {
                'success': True,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': (end_time - start_time).total_seconds(),
                'issues': issues
            }
            
        except Exception as e:
            logger.error(f"Error in manual check: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            db.close()

# Global instance
simplified_monitor = SimplifiedConsistencyMonitor()

async def start_monitoring():
    """Start the global consistency monitor."""
    await simplified_monitor.start_monitoring()

def stop_monitoring():
    """Stop the global consistency monitor."""
    simplified_monitor.stop_monitoring()