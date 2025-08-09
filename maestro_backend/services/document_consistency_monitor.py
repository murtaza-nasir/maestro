"""
Document Consistency Monitor

This service periodically checks for and cleans up orphaned documents
to prevent data inconsistencies from accumulating over time.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session

from database.database import get_db
from database import crud
from database.models import Document
from database.crud_documents_improved import (
    cleanup_all_user_orphans,
    get_document_processing_stats,
    consistency_manager
)

logger = logging.getLogger(__name__)

class DocumentConsistencyMonitor:
    """Monitors and maintains document consistency across all storage systems."""
    
    def __init__(self, check_interval_minutes: int = 60):
        self.check_interval_minutes = check_interval_minutes
        self.is_running = False
        self.last_check = None
        
    async def start_monitoring(self):
        """Start the consistency monitoring loop."""
        if self.is_running:
            logger.warning("Consistency monitor is already running")
            return
            
        self.is_running = True
        logger.info(f"Starting document consistency monitor (check interval: {self.check_interval_minutes} minutes)")
        
        while self.is_running:
            try:
                await self._perform_consistency_check()
                
                # Wait for next check interval
                await asyncio.sleep(self.check_interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Error in consistency monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
                
    def stop_monitoring(self):
        """Stop the consistency monitoring."""
        logger.info("Stopping document consistency monitor")
        self.is_running = False
        
    async def _perform_consistency_check(self):
        """Perform a full consistency check and cleanup."""
        logger.info("Starting periodic consistency check")
        self.last_check = datetime.utcnow()
        
        db = next(get_db())
        try:
            # Get all users
            users = crud.get_users(db, limit=1000)
            
            total_issues_found = 0
            total_issues_resolved = 0
            users_with_issues = 0
            
            for user in users:
                try:
                    # Check for consistency issues
                    stats = get_document_processing_stats(db, user.id)
                    
                    if 'error' in stats:
                        logger.warning(f"Could not check consistency for user {user.id}: {stats['error']}")
                        continue
                        
                    user_issues = stats.get('consistency_issues', 0)
                    
                    if user_issues > 0:
                        users_with_issues += 1
                        total_issues_found += user_issues
                        
                        logger.warning(f"Found {user_issues} consistency issues for user {user.username}")
                        
                        # Perform automatic cleanup
                        cleanup_result = await cleanup_all_user_orphans(db, user.id)
                        issues_resolved = cleanup_result.get('total_issues_resolved', 0)
                        total_issues_resolved += issues_resolved
                        
                        if issues_resolved > 0:
                            logger.info(f"Automatically resolved {issues_resolved} issues for user {user.username}")
                        
                except Exception as e:
                    logger.error(f"Error checking consistency for user {user.id}: {e}")
                    continue
                    
            # Log summary
            if total_issues_found > 0:
                logger.warning(f"Consistency check completed: Found {total_issues_found} issues across {users_with_issues} users")
                logger.info(f"Automatically resolved {total_issues_resolved} issues")
            else:
                logger.info("Consistency check completed: No issues found")
                
            # Also check for old failed documents that should be cleaned up
            await self._cleanup_old_failed_documents(db)
            
        except Exception as e:
            logger.error(f"Error during consistency check: {e}")
        finally:
            db.close()
            
    async def _cleanup_old_failed_documents(self, db: Session):
        """Clean up failed documents that are older than 24 hours."""
        try:
            # Find failed documents older than 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            failed_docs = db.query(Document).filter(
                Document.processing_status == 'failed',
                Document.created_at < cutoff_time
            ).all()
            
            if failed_docs:
                logger.info(f"Found {len(failed_docs)} old failed documents to clean up")
                
                for doc in failed_docs:
                    try:
                        # Check if it has orphaned entries
                        exists = consistency_manager.check_document_exists(doc.id, doc.user_id, db)
                        
                        has_orphans = any([
                            exists['ai_db'],
                            exists['vector_store'],
                            exists['pdf_file'],
                            exists['markdown_file'],
                            exists['metadata_file']
                        ])
                        
                        if has_orphans:
                            from database.crud_documents_improved import cleanup_failed_document
                            await cleanup_failed_document(db, doc.id, doc.user_id)
                            logger.info(f"Cleaned up orphaned data for old failed document: {doc.id}")
                            
                    except Exception as e:
                        logger.error(f"Error cleaning up old failed document {doc.id}: {e}")
                        
        except Exception as e:
            logger.error(f"Error cleaning up old failed documents: {e}")
            
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """Get the current monitoring status."""
        return {
            'is_running': self.is_running,
            'check_interval_minutes': self.check_interval_minutes,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'next_check': (self.last_check + timedelta(minutes=self.check_interval_minutes)).isoformat() 
                         if self.last_check else None
        }
        
    async def force_consistency_check(self) -> Dict[str, Any]:
        """Force an immediate consistency check (for manual triggering)."""
        logger.info("Performing manual consistency check")
        
        start_time = datetime.utcnow()
        await self._perform_consistency_check()
        end_time = datetime.utcnow()
        
        return {
            'check_completed': True,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': (end_time - start_time).total_seconds()
        }

# Global monitor instance
consistency_monitor = DocumentConsistencyMonitor()

async def start_consistency_monitoring():
    """Start the global consistency monitor."""
    await consistency_monitor.start_monitoring()
    
def stop_consistency_monitoring():
    """Stop the global consistency monitor."""
    consistency_monitor.stop_monitoring()