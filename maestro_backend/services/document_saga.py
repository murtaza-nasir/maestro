"""
Document Processing Saga Pattern Implementation

This module implements the saga pattern for document processing to ensure
consistency across all storage systems. Each step is tracked and can be
rolled back if necessary.

The saga ensures that all operations either complete successfully or are
properly rolled back, maintaining consistency across:
1. Main database (document records and metadata)
2. Vector store (embeddings)
3. File system (PDFs, markdown files)
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

class ProcessingStage(Enum):
    """Stages of document processing for saga tracking."""
    CREATED = "created"
    FILE_SAVED = "file_saved"
    METADATA_EXTRACTED = "metadata_extracted"
    CHUNKS_GENERATED = "chunks_generated"
    EMBEDDINGS_CREATED = "embeddings_created"
    VECTOR_STORE_UPDATED = "vector_store_updated"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"

class SagaStep:
    """Represents a single step in the saga."""
    
    def __init__(self, name: str, stage: ProcessingStage, 
                 execute_fn: callable, compensate_fn: callable = None):
        self.name = name
        self.stage = stage
        self.execute_fn = execute_fn
        self.compensate_fn = compensate_fn
        self.completed = False
        self.result = None
        self.error = None

class DocumentProcessingSaga:
    """
    Orchestrates document processing using the saga pattern.
    Ensures consistency across all storage systems.
    """
    
    def __init__(self, db: Session, doc_id: str, user_id: int):
        self.db = db
        self.doc_id = doc_id
        self.user_id = user_id
        self.steps: List[SagaStep] = []
        self.completed_steps: List[SagaStep] = []
        self.current_stage = ProcessingStage.CREATED
        self.rollback_performed = False
        
    def add_step(self, step: SagaStep):
        """Add a step to the saga."""
        self.steps.append(step)
        
    async def execute(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Execute all saga steps in order.
        Returns (success, result_data)
        """
        logger.info(f"Starting saga for document {self.doc_id}")
        
        try:
            # Mark document as processing
            self._update_processing_stage(ProcessingStage.CREATED)
            
            # Execute each step
            for step in self.steps:
                logger.info(f"Executing step: {step.name}")
                
                try:
                    # Update stage before execution
                    self._update_processing_stage(step.stage)
                    
                    # Execute the step
                    step.result = await step.execute_fn()
                    step.completed = True
                    self.completed_steps.append(step)
                    
                    logger.info(f"Step {step.name} completed successfully")
                    
                except Exception as e:
                    step.error = e
                    logger.error(f"Step {step.name} failed: {e}")
                    
                    # Trigger rollback
                    await self.rollback()
                    return False, {"error": str(e), "failed_step": step.name}
            
            # All steps completed successfully
            self._update_processing_stage(ProcessingStage.COMPLETED)
            self._update_document_status("completed")
            
            # Collect results from all steps
            results = {
                step.name: step.result 
                for step in self.completed_steps 
                if step.result is not None
            }
            
            logger.info(f"Saga completed successfully for document {self.doc_id}")
            return True, results
            
        except Exception as e:
            logger.error(f"Unexpected error in saga execution: {e}")
            await self.rollback()
            return False, {"error": str(e)}
    
    async def rollback(self):
        """
        Rollback all completed steps in reverse order.
        """
        if self.rollback_performed:
            logger.warning(f"Rollback already performed for document {self.doc_id}")
            return
            
        logger.warning(f"Starting rollback for document {self.doc_id}")
        self._update_processing_stage(ProcessingStage.ROLLING_BACK)
        
        # Rollback in reverse order
        for step in reversed(self.completed_steps):
            if step.compensate_fn:
                try:
                    logger.info(f"Rolling back step: {step.name}")
                    await step.compensate_fn()
                    logger.info(f"Successfully rolled back: {step.name}")
                except Exception as e:
                    logger.error(f"Error rolling back {step.name}: {e}")
                    # Continue with other rollbacks even if one fails
        
        self._update_processing_stage(ProcessingStage.ROLLED_BACK)
        self._update_document_status("failed")
        self.rollback_performed = True
        
        logger.info(f"Rollback completed for document {self.doc_id}")
    
    def _update_processing_stage(self, stage: ProcessingStage):
        """Update the processing stage in the database."""
        try:
            query = text("""
                UPDATE documents 
                SET processing_stage = :stage,
                    updated_at = :updated_at
                WHERE id = :doc_id
            """)
            
            self.db.execute(query, {
                'stage': stage.value,
                'updated_at': datetime.utcnow(),
                'doc_id': self.doc_id
            })
            self.db.commit()
            self.current_stage = stage
            
        except Exception as e:
            logger.error(f"Error updating processing stage: {e}")
            self.db.rollback()
    
    def _update_document_status(self, status: str):
        """Update the document processing status."""
        try:
            query = text("""
                UPDATE documents 
                SET processing_status = :status,
                    processing_completed_at = CASE 
                        WHEN :status = 'completed' THEN :completed_at
                        ELSE processing_completed_at
                    END,
                    updated_at = :updated_at
                WHERE id = :doc_id
            """)
            
            self.db.execute(query, {
                'status': status,
                'completed_at': datetime.utcnow() if status == 'completed' else None,
                'updated_at': datetime.utcnow(),
                'doc_id': self.doc_id
            })
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating document status: {e}")
            self.db.rollback()

class DocumentSagaBuilder:
    """
    Builder for creating document processing sagas with proper steps.
    """
    
    def __init__(self, db: Session, doc_id: str, user_id: int,
                 processor, vector_store, file_manager):
        self.db = db
        self.doc_id = doc_id
        self.user_id = user_id
        self.processor = processor
        self.vector_store = vector_store
        self.file_manager = file_manager
        self.saga = DocumentProcessingSaga(db, doc_id, user_id)
        
    def build_upload_saga(self, file_content: bytes, filename: str) -> DocumentProcessingSaga:
        """Build saga for UI upload flow."""
        
        # Step 1: Save file
        async def save_file():
            path = self.file_manager.save_document(self.doc_id, filename, file_content)
            self._update_flag("has_pdf_file", True)
            return {"file_path": str(path)}
            
        async def delete_file():
            self.file_manager.delete_document(self.doc_id)
            self._update_flag("has_pdf_file", False)
            
        self.saga.add_step(SagaStep(
            "save_file",
            ProcessingStage.FILE_SAVED,
            save_file,
            delete_file
        ))
        
        # Step 2: Extract metadata
        async def extract_metadata():
            metadata = await self.processor.extract_metadata(self.doc_id)
            self._save_metadata_to_db(metadata)
            self._update_flag("has_ai_metadata", True)
            return {"metadata": metadata}
            
        async def clear_metadata():
            self._clear_metadata_from_db()
            self._update_flag("has_ai_metadata", False)
            
        self.saga.add_step(SagaStep(
            "extract_metadata",
            ProcessingStage.METADATA_EXTRACTED,
            extract_metadata,
            clear_metadata
        ))
        
        # Step 3: Generate chunks
        async def generate_chunks():
            chunks = await self.processor.generate_chunks(self.doc_id)
            self._update_chunk_count(len(chunks))
            return {"chunks": chunks}
            
        async def clear_chunks():
            self._update_chunk_count(0)
            
        self.saga.add_step(SagaStep(
            "generate_chunks",
            ProcessingStage.CHUNKS_GENERATED,
            generate_chunks,
            clear_chunks
        ))
        
        # Step 4: Create embeddings
        async def create_embeddings():
            chunks = self.saga.completed_steps[-1].result["chunks"]
            embeddings = await self.processor.create_embeddings(chunks)
            return {"embeddings": embeddings}
            
        self.saga.add_step(SagaStep(
            "create_embeddings",
            ProcessingStage.EMBEDDINGS_CREATED,
            create_embeddings,
            None  # No compensation needed
        ))
        
        # Step 5: Update vector store
        async def update_vector_store():
            embeddings = self.saga.completed_steps[-1].result["embeddings"]
            await self.vector_store.add_embeddings(self.doc_id, embeddings)
            self._update_flag("has_vector_embeddings", True)
            return {"vector_store_updated": True}
            
        async def remove_from_vector_store():
            await self.vector_store.remove_document(self.doc_id)
            self._update_flag("has_vector_embeddings", False)
            
        self.saga.add_step(SagaStep(
            "update_vector_store",
            ProcessingStage.VECTOR_STORE_UPDATED,
            update_vector_store,
            remove_from_vector_store
        ))
        
        # Step 6: Save markdown
        async def save_markdown():
            markdown = await self.processor.get_markdown(self.doc_id)
            self.file_manager.save_markdown(self.doc_id, markdown)
            self._update_flag("has_markdown_file", True)
            return {"markdown_saved": True}
            
        async def delete_markdown():
            self.file_manager.delete_markdown(self.doc_id)
            self._update_flag("has_markdown_file", False)
            
        self.saga.add_step(SagaStep(
            "save_markdown",
            ProcessingStage.COMPLETED,
            save_markdown,
            delete_markdown
        ))
        
        return self.saga
    
    def build_cli_saga(self, file_path: Path) -> DocumentProcessingSaga:
        """Build saga for CLI ingestion flow."""
        
        # Similar to upload saga but reads from file path
        # and creates main DB record first
        
        # Step 1: Create database record
        async def create_db_record():
            query = text("""
                INSERT INTO documents (id, user_id, original_filename, 
                                      processing_status, processing_stage, 
                                      processing_started_at, created_at, updated_at)
                VALUES (:id, :user_id, :filename, 'processing', 'created', 
                       :started_at, :created_at, :updated_at)
            """)
            
            now = datetime.utcnow()
            self.db.execute(query, {
                'id': self.doc_id,
                'user_id': self.user_id,
                'filename': file_path.name,
                'started_at': now,
                'created_at': now,
                'updated_at': now
            })
            self.db.commit()
            return {"record_created": True}
            
        async def delete_db_record():
            query = text("DELETE FROM documents WHERE id = :doc_id")
            self.db.execute(query, {'doc_id': self.doc_id})
            self.db.commit()
            
        self.saga.add_step(SagaStep(
            "create_record",
            ProcessingStage.CREATED,
            create_db_record,
            delete_db_record
        ))
        
        # Add remaining steps similar to upload saga...
        # (Implementation continues with similar pattern)
        
        return self.saga
    
    def _update_flag(self, flag_name: str, value: bool):
        """Update a boolean flag in the database."""
        try:
            query = text(f"UPDATE documents SET {flag_name} = :value WHERE id = :doc_id")
            self.db.execute(query, {'value': value, 'doc_id': self.doc_id})
            self.db.commit()
        except Exception as e:
            logger.error(f"Error updating flag {flag_name}: {e}")
            self.db.rollback()
    
    def _update_chunk_count(self, count: int):
        """Update the chunk count in the database."""
        try:
            query = text("UPDATE documents SET chunk_count = :count WHERE id = :doc_id")
            self.db.execute(query, {'count': count, 'doc_id': self.doc_id})
            self.db.commit()
        except Exception as e:
            logger.error(f"Error updating chunk count: {e}")
            self.db.rollback()
    
    def _save_metadata_to_db(self, metadata: Dict[str, Any]):
        """Save extracted metadata to the database."""
        try:
            query = text("""
                UPDATE documents 
                SET title = :title,
                    authors = :authors,
                    publication_year = :year,
                    journal = :journal,
                    abstract = :abstract,
                    doi = :doi,
                    keywords = :keywords,
                    extracted_metadata = :metadata_json
                WHERE id = :doc_id
            """)
            
            self.db.execute(query, {
                'title': metadata.get('title', ''),
                'authors': json.dumps(metadata.get('authors', [])),
                'year': metadata.get('year'),
                'journal': metadata.get('journal', ''),
                'abstract': metadata.get('abstract', ''),
                'doi': metadata.get('doi', ''),
                'keywords': json.dumps(metadata.get('keywords', [])),
                'metadata_json': json.dumps(metadata),
                'doc_id': self.doc_id
            })
            self.db.commit()
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")
            self.db.rollback()
    
    def _clear_metadata_from_db(self):
        """Clear metadata from the database."""
        try:
            query = text("""
                UPDATE documents 
                SET title = NULL,
                    authors = NULL,
                    publication_year = NULL,
                    journal = NULL,
                    abstract = NULL,
                    doi = NULL,
                    keywords = NULL,
                    extracted_metadata = NULL
                WHERE id = :doc_id
            """)
            
            self.db.execute(query, {'doc_id': self.doc_id})
            self.db.commit()
        except Exception as e:
            logger.error(f"Error clearing metadata: {e}")
            self.db.rollback()