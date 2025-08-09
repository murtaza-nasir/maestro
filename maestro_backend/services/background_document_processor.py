"""
Background document processor service for handling asynchronous document processing
with real-time progress updates via WebSocket.

This service implements a queue-based system to process documents one at a time
to avoid GPU VRAM conflicts while keeping the processing non-blocking.
"""
import asyncio
import uuid
import json
import traceback
from threading import Thread, RLock, Event
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from sqlalchemy.orm import Session
import time
from dataclasses import dataclass

from ai_researcher.core_rag.processor import DocumentProcessor
from ai_researcher.core_rag.vector_store_manager import VectorStoreManager as VectorStore
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.database import Database
from database import crud, models
from database.database import get_db

@dataclass
class ProcessingJob:
    """Represents a document processing job."""
    job_id: str
    doc_id: str
    user_id: int
    file_path: Path
    original_filename: str
    created_at: datetime

class BackgroundDocumentProcessor:
    """Service for processing documents in the background with progress tracking."""
    
    def __init__(self):
        # Paths to existing document infrastructure
        base_path = Path("/app/ai_researcher/data")
        self.vector_store_path = base_path / "vector_store"
        self.pdf_dir = base_path / "raw_pdfs"
        self.markdown_dir = base_path / "processed" / "markdown"
        self.metadata_dir = base_path / "processed" / "metadata"
        self.db_path = base_path / "processed" / "metadata.db"
        
        # Initialize components lazily (only when needed)
        self._vector_store = None
        self._embedder = None
        self._ai_db = None
        self._processor = None
        self._components_lock = RLock()
        
        self.is_processing = False
        self.current_job: Optional[ProcessingJob] = None
        self.shutdown_event = Event()
        
        # WebSocket connections for progress updates
        self.websocket_connections: Dict[str, List] = {}

    def start(self):
        """Start the background worker thread."""
        print("Document processing worker started")
        self._worker_loop()

    def _worker_loop(self):
        """Main worker loop that polls the database for queued documents."""
        while not self.shutdown_event.is_set():
            job_processed = False
            db = next(get_db())
            try:
                # Fetch the next queued document
                document = crud.get_next_queued_document(db)
                
                if document:
                    job_processed = True
                    self.is_processing = True
                    
                    # Create a job object
                    job = ProcessingJob(
                        job_id=str(uuid.uuid4()), # This can be improved to use a job ID from the DB
                        doc_id=document.id,
                        user_id=document.user_id,
                        file_path=Path(document.file_path),
                        original_filename=document.original_filename,
                        created_at=document.created_at
                    )
                    self.current_job = job
                    
                    print(f"[{job.doc_id}] Found queued document. Starting processing.")
                    
                    # Mark as processing
                    crud.update_document_status(db, document.id, "processing", 0)
                    
                    # Process the document
                    success = self._process_document_sync(job)
                    
                    # Mark as completed or failed, with cleanup if failed
                    final_status = "completed" if success else "failed"
                    crud.update_document_status(db, document.id, final_status, 100)
                    
                    # If processing failed, clean up any orphaned entries
                    if not success:
                        print(f"[{job.doc_id}] Processing failed, performing cleanup...")
                        try:
                            from database.crud_documents_improved import cleanup_failed_document_improved
                            cleanup_success = cleanup_failed_document_improved(db, document.id, document.user_id)
                            if cleanup_success:
                                print(f"[{job.doc_id}] Successfully cleaned up failed processing artifacts")
                            else:
                                print(f"[{job.doc_id}] Warning: Cleanup encountered some issues")
                        except Exception as cleanup_error:
                            print(f"[{job.doc_id}] Error during cleanup: {cleanup_error}")
                    
                    print(f"[{job.doc_id}] Document processing finished with status: {final_status}")
                    
                    self.is_processing = False
                    self.current_job = None

            except Exception as e:
                print(f"Error in worker loop: {e}")
                traceback.print_exc()
                self.is_processing = False
                if self.current_job:
                    crud.update_document_status(db, self.current_job.doc_id, "failed", 0)
                    # Also attempt cleanup for the failed job
                    try:
                        from database.crud_documents_improved import cleanup_failed_document_improved
                        cleanup_failed_document_improved(db, self.current_job.doc_id, self.current_job.user_id)
                        print(f"[{self.current_job.doc_id}] Cleaned up after unexpected error")
                    except Exception as cleanup_error:
                        print(f"[{self.current_job.doc_id}] Cleanup after error failed: {cleanup_error}")
                self.current_job = None
            finally:
                db.close()

            # If no job was processed, wait before polling again
            if not job_processed:
                time.sleep(5) # Poll every 5 seconds
    
    
    def _get_vector_store(self) -> VectorStore:
        """Get or initialize the vector store (thread-safe)."""
        with self._components_lock:
            if self._vector_store is None:
                print("Initializing VectorStore...")
                self._vector_store = VectorStore(persist_directory=str(self.vector_store_path))
            return self._vector_store
    
    def _get_embedder(self) -> TextEmbedder:
        """Get or initialize the embedder (thread-safe)."""
        with self._components_lock:
            if self._embedder is None:
                print("Initializing TextEmbedder...")
                self._embedder = TextEmbedder(model_name="BAAI/bge-m3")
            return self._embedder
    
    def _get_ai_db(self) -> Database:
        """Get or initialize the AI researcher database (thread-safe)."""
        with self._components_lock:
            if self._ai_db is None:
                print("Initializing AI Database...")
                self._ai_db = Database(db_path=self.db_path)
            return self._ai_db
    
    def _get_processor(self) -> DocumentProcessor:
        """Get or initialize the document processor (thread-safe)."""
        with self._components_lock:
            if self._processor is None:
                print("Initializing DocumentProcessor...")
                embedder = self._get_embedder()
                vector_store = self._get_vector_store()
                
                self._processor = DocumentProcessor(
                    pdf_dir=self.pdf_dir,
                    markdown_dir=self.markdown_dir,
                    metadata_dir=self.metadata_dir,
                    db_path=self.db_path,
                    embedder=embedder,
                    vector_store=vector_store,
                    force_reembed=False
                )
            return self._processor
    
    def _get_processor_with_user_settings(self, user_settings: Dict[str, Any]) -> DocumentProcessor:
        """Get or initialize the document processor with user-specific settings (thread-safe)."""
        with self._components_lock:
            print("Initializing DocumentProcessor with user settings...")
            embedder = self._get_embedder()
            vector_store = self._get_vector_store()
            
            # Create a metadata extractor with user settings
            from ai_researcher.core_rag.metadata_extractor import MetadataExtractor
            metadata_extractor = MetadataExtractor.from_user_settings(user_settings)
            
            processor = DocumentProcessor(
                pdf_dir=self.pdf_dir,
                markdown_dir=self.markdown_dir,
                metadata_dir=self.metadata_dir,
                db_path=self.db_path,
                embedder=embedder,
                vector_store=vector_store,
                force_reembed=False
            )
            
            # Replace the default metadata extractor with the user-configured one
            processor.metadata_extractor = metadata_extractor
            
            return processor
    
    def add_websocket_connection(self, user_id: str, websocket):
        """Add a WebSocket connection for a user."""
        if user_id not in self.websocket_connections:
            self.websocket_connections[user_id] = []
        self.websocket_connections[user_id].append(websocket)
    
    def remove_websocket_connection(self, user_id: str, websocket):
        """Remove a WebSocket connection for a user."""
        if user_id in self.websocket_connections:
            try:
                self.websocket_connections[user_id].remove(websocket)
                if not self.websocket_connections[user_id]:
                    del self.websocket_connections[user_id]
            except ValueError:
                pass  # Connection not in list
    
    def _send_progress_update_sync(self, user_id: str, update: Dict[str, Any]):
        """Sends a progress update to the main backend via an internal API call."""
        import requests
        
        # The main backend service is available at this hostname in the Docker network
        backend_url = "http://maestro-backend:8000/api/internal/document-progress"
        
        try:
            # Add user_id to the update payload if it's not already there
            if 'user_id' not in update:
                update['user_id'] = int(user_id)
            
            response = requests.post(backend_url, json=update, timeout=5)
            response.raise_for_status()
            print(f"Successfully sent progress update to backend for user {user_id}")
        except requests.exceptions.RequestException as e:
            print(f"Error sending progress update to backend: {e}")
    
    def _update_document_progress_sync(self, doc_id: str, user_id: int, progress: int, 
                                     status: str, error_message: Optional[str] = None):
        """Update document progress in database and send WebSocket update (synchronous)."""
        # Get database session
        db = next(get_db())
        try:
            # Update document in database
            document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
            if document:
                document.upload_progress = progress
                document.processing_status = status
                if error_message:
                    document.processing_error = error_message
                db.commit()
            
            # Send WebSocket update
            update = {
                "type": "document_progress",
                "doc_id": doc_id,
                "progress": progress,
                "status": status,
                "error": error_message,
                "timestamp": datetime.utcnow().isoformat()
            }
            self._send_progress_update_sync(str(user_id), update)
            
        except Exception as e:
            print(f"Error updating document progress: {e}")
        finally:
            db.close()
    
    def _update_job_progress_sync(self, job_id: str, user_id: int, progress: int, 
                                status: str, error_message: Optional[str] = None):
        """Update processing job progress in database and send WebSocket update (synchronous)."""
        # Get database session
        db = next(get_db())
        try:
            # Update job in database
            job = db.query(models.DocumentProcessingJob).filter(
                models.DocumentProcessingJob.id == job_id,
                models.DocumentProcessingJob.user_id == user_id
            ).first()
            
            if job:
                job.progress = progress
                job.status = status
                if error_message:
                    job.error_message = error_message
                if status == "running" and not job.started_at:
                    job.started_at = datetime.utcnow()
                elif status in ["completed", "failed"]:
                    job.completed_at = datetime.utcnow()
                db.commit()
            
            # Send WebSocket update
            update = {
                "type": "job_progress",
                "job_id": job_id,
                "document_id": job.document_id if job else None,
                "progress": progress,
                "status": status,
                "error_message": error_message,
                "timestamp": datetime.utcnow().isoformat()
            }
            # self._send_progress_update_sync(str(user_id), update) # Websockets not used in this service
            
        except Exception as e:
            print(f"Error updating job progress: {e}")
        finally:
            db.close()
    
    def _process_document_sync(self, job: ProcessingJob) -> bool:
        """Process a document synchronously in the worker thread."""
        doc_id = job.doc_id
        user_id = job.user_id
        file_path = job.file_path
        original_filename = job.original_filename
        job_id = job.job_id
        
        try:
            # Update status to running
            self._update_job_progress_sync(job_id, user_id, 0, "running")
            self._update_document_progress_sync(doc_id, user_id, 0, "processing")
            
            # Step 1: Get user settings and initialize processor (10% progress)
            print(f"[{doc_id}] Getting user settings and initializing document processor...")
            self._update_job_progress_sync(job_id, user_id, 10, "running")
            
            # Get user settings from database
            db = next(get_db())
            try:
                from database import crud
                user = crud.get_user(db, user_id)
                user_settings = user.settings if user and user.settings else {}
                print(f"[{doc_id}] Retrieved user settings for user {user_id}")
            except Exception as e:
                print(f"[{doc_id}] Warning: Could not retrieve user settings: {e}")
                user_settings = {}
            finally:
                db.close()
            
            processor = self._get_processor_with_user_settings(user_settings)
            
            # Step 2: Process PDF to Markdown (30% progress)
            print(f"[{doc_id}] Starting PDF processing with Marker...")
            self._update_job_progress_sync(job_id, user_id, 30, "running")
            self._update_document_progress_sync(doc_id, user_id, 30, "processing")
            
            # Copy the uploaded file to the expected location with the correct name
            target_path = self.pdf_dir / f"{doc_id}_{original_filename}"
            if not target_path.exists():
                import shutil
                shutil.copy2(file_path, target_path)
                print(f"[{doc_id}] Copied file to processor directory: {target_path}")
            
            # Step 3: Extract metadata and convert to Markdown (50% progress)
            print(f"[{doc_id}] Extracting metadata and converting to Markdown...")
            self._update_job_progress_sync(job_id, user_id, 50, "running")
            self._update_document_progress_sync(doc_id, user_id, 50, "processing")
            
            # Extract metadata using the processor's method
            initial_text = processor._extract_header_footer_text(target_path)
            extracted_metadata = processor.metadata_extractor.extract(initial_text)
            
            if extracted_metadata:
                final_metadata = {"doc_id": doc_id, "original_filename": original_filename}
                final_metadata.update(extracted_metadata)
            else:
                final_metadata = {"doc_id": doc_id, "original_filename": original_filename}
            
            # Convert PDF to Markdown using Marker with intelligent table handling
            print(f"[{doc_id}] Converting PDF to Markdown using Marker with intelligent table handling...")
            markdown_content = processor._convert_pdf_with_table_handling(target_path)
            
            if not markdown_content:
                raise Exception("Marker produced empty markdown content")
            
            # Save markdown with our doc_id
            md_filename = f"{doc_id}.md"
            md_save_path = processor.markdown_dir / md_filename
            with open(md_save_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"[{doc_id}] Saved Markdown to: {md_save_path}")
            
            # Save metadata with our doc_id
            metadata_filename = f"{doc_id}.json"
            metadata_save_path = processor.metadata_dir / metadata_filename
            with open(metadata_save_path, "w", encoding="utf-8") as f:
                import json
                json.dump(final_metadata, f, indent=2, ensure_ascii=False)
            print(f"[{doc_id}] Saved metadata to: {metadata_save_path}")
            
            # Add to AI researcher database with our doc_id (with error handling)
            ai_db = processor.database
            try:
                ai_db.add_processed_document(doc_id, original_filename, final_metadata)
                print(f"[{doc_id}] Added to AI researcher database")
            except Exception as e:
                print(f"[{doc_id}] Warning: Failed to add to AI database: {e}")
                # Continue processing but note the failure
                # This will be caught and cleaned up if vector store also fails
            
            # Step 4: Generate embeddings (70% progress)
            print(f"[{doc_id}] Generating embeddings...")
            self._update_job_progress_sync(job_id, user_id, 70, "running")
            self._update_document_progress_sync(doc_id, user_id, 70, "processing")
            
            # Chunk the content
            print(f"[{doc_id}] Chunking Markdown content...")
            chunks = processor.chunker.chunk(markdown_content, doc_metadata=final_metadata)
            print(f"[{doc_id}] Generated {len(chunks)} chunks")
            
            # Step 5: Store in vector database (90% progress)
            print(f"[{doc_id}] Storing in vector database...")
            self._update_job_progress_sync(job_id, user_id, 90, "running")
            self._update_document_progress_sync(doc_id, user_id, 90, "processing")
            
            # Embed and store chunks
            if processor.embedder and processor.vector_store and chunks:
                print(f"[{doc_id}] Embedding {len(chunks)} chunks...")
                chunks_with_embeddings = processor.embedder.embed_chunks(chunks)
                print(f"[{doc_id}] Adding chunks to vector store...")
                processor.vector_store.add_chunks(chunks_with_embeddings)
                chunks_added_count = len(chunks)
                print(f"[{doc_id}] Successfully added {chunks_added_count} chunks to vector store")
            else:
                chunks_added_count = 0
                print(f"[{doc_id}] Skipping embedding/storing: No embedder or vector store")
            
            processing_result = {
                "doc_id": doc_id,
                "original_filename": original_filename,
                "chunks_generated": len(chunks),
                "chunks_added_to_vector_store": chunks_added_count,
                "extracted_metadata": final_metadata
            }
            
            print(f"[{doc_id}] Processing completed successfully!")
            print(f"[{doc_id}] Generated {processing_result.get('chunks_generated', 0)} chunks")
            print(f"[{doc_id}] Added {processing_result.get('chunks_added_to_vector_store', 0)} chunks to vector store")
            
            # Step 6: Complete (100% progress)
            self._update_job_progress_sync(job_id, user_id, 100, "completed")
            self._update_document_progress_sync(doc_id, user_id, 100, "completed")
            
            # Update document metadata with processing results
            db = next(get_db())
            try:
                document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
                if document:
                    # Add processing completion metadata
                    metadata = document.metadata_ or {}
                    extracted_metadata = processing_result.get('extracted_metadata', {})
                    
                    # Merge extracted metadata with existing metadata
                    metadata.update(extracted_metadata)
                    metadata.update({
                        "processed_at": datetime.utcnow().isoformat(),
                        "processing_job_id": job_id,
                        "status": "completed",
                        "chunks_generated": processing_result.get('chunks_generated', 0),
                        "chunks_added_to_vector_store": processing_result.get('chunks_added_to_vector_store', 0)
                    })
                    document.metadata_ = metadata
                    db.commit()
                    print(f"[{doc_id}] Updated document metadata in database")
            except Exception as e:
                print(f"Error updating document metadata: {e}")
            finally:
                db.close()
            
            return True
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            print(f"[{doc_id}] Document processing error: {error_msg}")
            print(traceback.format_exc())
            
            # Update status to failed
            self._update_job_progress_sync(job_id, user_id, 0, "failed", error_msg)
            self._update_document_progress_sync(doc_id, user_id, 0, "failed", error_msg)
            
            return False
            
        finally:
            # This part is handled by the main worker loop now
            pass

    def shutdown(self):
        """Shutdown the background processor."""
        print("Setting shutdown event for background processor.")
        self.shutdown_event.set()

# Global instance
background_processor = BackgroundDocumentProcessor()

if __name__ == "__main__":
    print("Background document processor service starting.")
    try:
        background_processor.start()
    except KeyboardInterrupt:
        print("Shutdown signal received. Stopping processor...")
    finally:
        background_processor.shutdown()
        print("Background processor shut down.")
