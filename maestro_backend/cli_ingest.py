#!/usr/bin/env python3
"""
Direct CLI tool for synchronous document ingestion into MAESTRO.
This script processes documents immediately with live feedback, bypassing the background queue system.

FIXED VERSION: Creates document records in PostgreSQL BEFORE processing to avoid foreign key violations.
"""

import typer
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
import threading
import multiprocessing
import pickle
import signal
import atexit
import hashlib
from datetime import datetime

# Set multiprocessing start method to 'spawn' for CUDA compatibility
# This MUST be done before any multiprocessing operations
if __name__ != "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set

# Global executor for signal handling
global_executor = None

def signal_handler(signum, frame):
    """Handle interrupt signals to gracefully shutdown the executor."""
    global global_executor
    print("\n\n⚠️  Interrupt received! Shutting down processes gracefully...")
    if global_executor:
        try:
            # First try graceful shutdown with a timeout
            global_executor.shutdown(wait=True, cancel_futures=True)
            print("✓ All processes terminated gracefully.")
        except Exception as e:
            print(f"⚠️  Force terminating processes due to: {e}")
            global_executor.shutdown(wait=False)
    sys.exit(0)

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def cleanup_executor():
    """Cleanup function to ensure executor is shut down on exit."""
    global global_executor
    if global_executor:
        try:
            global_executor.shutdown(wait=False, cancel_futures=True)
        except:
            pass

# Register cleanup function
atexit.register(cleanup_executor)

# Suppress verbose config output during import
captured_output = StringIO()
with redirect_stdout(captured_output), redirect_stderr(captured_output):
    # Add the current directory to Python path for imports
    sys.path.insert(0, '/app')
    
    from database.database import get_db
    from database import crud, models
    from database.models import Document, DocumentGroup
    from auth.security import get_password_hash
    
    # Import AI researcher components for direct processing
    from ai_researcher.core_rag.processor import DocumentProcessor
    from ai_researcher.core_rag.embedder import TextEmbedder
    try:
        from ai_researcher.core_rag.vector_store_safe import SafeVectorStore as VectorStore
    except ImportError:
        from ai_researcher.core_rag.pgvector_store import PGVectorStore as VectorStore

app = typer.Typer(help="MAESTRO Direct Document Processing CLI")

def get_db_session():
    """Get a database session."""
    db = next(get_db())
    try:
        return db
    finally:
        pass  # Don't close here, let caller handle it

def create_document_record(
    db: Session,
    doc_id: str,
    user_id: int,
    file_path: Path,
    group_id: Optional[str] = None
) -> bool:
    """
    Create a document record in PostgreSQL with 'pending' status.
    This must be done BEFORE processing to avoid foreign key violations.
    """
    try:
        # Read file content for hash calculation
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Calculate file hash for deduplication
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Check if document already exists (by hash)
        existing = db.query(models.Document).filter(
            models.Document.user_id == user_id,
            models.Document.metadata_.op('->>')('file_hash') == file_hash
        ).first()
        
        if existing:
            print(f"Document already exists with same content: {existing.filename} (ID: {existing.id})")
            return False
        
        # Save the file to disk (matching UI upload path)
        upload_dir = "/app/data/raw_files"
        os.makedirs(upload_dir, exist_ok=True)
        
        saved_file_path = os.path.join(upload_dir, f"{doc_id}_{file_path.name}")
        with open(saved_file_path, "wb") as f:
            f.write(file_content)
        
        # Create document record with cli_processing status to avoid background processor
        metadata = {
            "title": file_path.name,
            "file_hash": file_hash,
            "upload_timestamp": datetime.utcnow().isoformat()
        }
        
        new_document = models.Document(
            id=doc_id,
            user_id=user_id,
            filename=file_path.name,
            original_filename=file_path.name,
            metadata_=metadata,
            processing_status="cli_processing",  # Use cli_processing to prevent background pickup
            file_size=len(file_content),
            file_path=saved_file_path,
            raw_file_path=saved_file_path,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_document)
        db.commit()
        db.refresh(new_document)
        
        # Add to group if specified
        if group_id:
            crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=user_id)
        
        print(f"Created document record: {file_path.name} (ID: {doc_id})")
        return True
        
    except Exception as e:
        print(f"Error creating document record for {file_path.name}: {e}")
        db.rollback()
        return False

def process_document_in_subprocess(args):
    """
    Process a document in a separate process.
    This function is designed to be pickleable and run in ProcessPoolExecutor.
    Each process gets its own memory space, avoiding Marker threading issues.
    
    NOTE: Document record must already exist in PostgreSQL before calling this.
    """
    import sys
    import os
    from pathlib import Path
    from contextlib import redirect_stdout, redirect_stderr
    from io import StringIO
    import traceback
    
    try:
        # Suppress verbose output during imports
        captured = StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            # Add imports needed for processing
            sys.path.insert(0, '/app')
            from database.database import get_db
            from database import crud, models
            from ai_researcher.core_rag.processor import DocumentProcessor
            from ai_researcher.core_rag.embedder import TextEmbedder
            from ai_researcher.core_rag.metadata_extractor import MetadataExtractor
            try:
                from ai_researcher.core_rag.vector_store_safe import SafeVectorStore as VectorStore
            except ImportError:
                from ai_researcher.core_rag.pgvector_store import PGVectorStore as VectorStore
    except Exception as e:
        print(f"[Process {os.getpid()}] Failed to import modules: {e}")
        traceback.print_exc()
        return (False, "import_error", str(e))
    
    # Unpack arguments
    try:
        (saved_file_path_str, doc_id, user_id, index, total, 
         force_reembed, device, user_settings) = args
        print(f"[Process {os.getpid()}] Processing document with ID: {doc_id}")
    except Exception as e:
        print(f"[Process {os.getpid()}] Failed to unpack arguments: {e}")
        return (False, "unpack_error", str(e))
    
    # Convert back to Path object
    saved_file_path = Path(saved_file_path_str)
    
    # Initialize components for this process
    base_path = Path("/app/ai_researcher/data")
    
    try:
        # Initialize components
        print(f"[Process {os.getpid()}] Initializing components for doc_id: {doc_id}...")
        
        actual_device = device or 'cuda'
        print(f"[Process {os.getpid()}] Using device: {actual_device}")
        
        # Initialize embedder with proper device
        embedder = TextEmbedder(model_name="BAAI/bge-m3", device=actual_device)
        vector_store = VectorStore()
        
        # Create metadata extractor with user settings
        if user_settings:
            metadata_extractor = MetadataExtractor.from_user_settings(user_settings)
        else:
            metadata_extractor = MetadataExtractor()
        
        # Initialize processor
        processor = DocumentProcessor(
            pdf_dir=base_path / "raw_pdfs",
            markdown_dir=base_path / "processed" / "markdown",
            metadata_dir=base_path / "processed" / "metadata",
            db_path=None,
            embedder=embedder,
            vector_store=vector_store,
            force_reembed=force_reembed,
            device=actual_device
        )
        
        # Replace processor's metadata extractor
        processor.metadata_extractor = metadata_extractor
        
        # Get database session
        db = next(get_db())
        
        # Check if document still has cli_processing status (not picked up by background)
        document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
        if not document:
            print(f"[{index}/{total}] Error: Document {doc_id} not found in database")
            db.close()
            return (False, doc_id, "Document not found")
        
        if document.processing_status not in ["cli_processing", "processing"]:
            print(f"[{index}/{total}] Warning: Document {doc_id} status is {document.processing_status}, may be processed by background")
        
        # Update status to processing
        crud.update_document_status(db, doc_id, user_id, "processing", 10)
        
        print(f"[{index}/{total}] Processing document ID: {doc_id}...")
        
        # Process the document with our specific doc_id
        result = processor.process_document(saved_file_path, doc_id=doc_id)
        
        if result is None:
            print(f"[{index}/{total}] Failed: {doc_id}")
            crud.update_document_status(db, doc_id, user_id, "failed", 0)
            db.close()
            return (False, doc_id, "Processing failed")
        
        # Update the existing document record with extracted metadata and completion status
        document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
        if document:
            # Merge extracted metadata with existing metadata
            existing_metadata = document.metadata_ or {}
            extracted_metadata = result.get('extracted_metadata', {})
            merged_metadata = {**existing_metadata, **extracted_metadata}
            
            document.metadata_ = merged_metadata
            document.processing_status = 'completed'
            document.upload_progress = 100
            document.chunk_count = result.get('chunks_generated', 0)
            
            # Also save markdown path if available
            markdown_path = f"/app/data/markdown_files/{doc_id}.md"
            if os.path.exists(markdown_path):
                document.markdown_path = markdown_path
            
            db.commit()
            print(f"[{index}/{total}] Updated document {doc_id} with extracted metadata")
        else:
            print(f"[{index}/{total}] Warning: Could not find document {doc_id} to update")
        
        db.close()
        
        chunks_generated = result.get('chunks_generated', 0)
        chunks_added = result.get('chunks_added_to_vector_store', 0)
        
        print(f"[{index}/{total}] Success: {doc_id} ({chunks_added} chunks)")
        return (True, doc_id, f"Success: {chunks_added} chunks")
        
    except MemoryError as e:
        print(f"[{index}/{total}] Memory Error for {doc_id}")
        return (False, doc_id, "Out of memory")
    except Exception as e:
        error_msg = str(e)
        print(f"[{index}/{total}] Error for {doc_id}: {error_msg[:200]}")
        return (False, doc_id, error_msg[:200])

class LiveProgressCallback:
    """Callback class to provide live progress updates during processing."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.start_time = time.time()
        
    def log_step(self, step: str, details: str = ""):
        """Log a processing step with timestamp."""
        elapsed = time.time() - self.start_time
        timestamp = f"[{elapsed:6.1f}s]"
        if details:
            typer.secho(f"{timestamp} {step}: {details}", fg=typer.colors.BLUE)
        else:
            typer.secho(f"{timestamp} {step}", fg=typer.colors.BLUE)
    
    def log_success(self, message: str):
        """Log a success message."""
        elapsed = time.time() - self.start_time
        timestamp = f"[{elapsed:6.1f}s]"
        typer.secho(f"{timestamp} ✓ {message}", fg=typer.colors.GREEN)
    
    def log_error(self, message: str):
        """Log an error message."""
        elapsed = time.time() - self.start_time
        timestamp = f"[{elapsed:6.1f}s]"
        typer.secho(f"{timestamp} ✗ {message}", fg=typer.colors.RED)
    
    def log_warning(self, message: str):
        """Log a warning message."""
        elapsed = time.time() - self.start_time
        timestamp = f"[{elapsed:6.1f}s]"
        typer.secho(f"{timestamp} ⚠ {message}", fg=typer.colors.YELLOW)

def process_single_document(
    file_path: Path, 
    doc_id: str, 
    user_id: int, 
    db: Session,
    processor: DocumentProcessor,
    progress: LiveProgressCallback
) -> tuple:
    """
    Process a single document with live progress feedback.
    NOTE: Document record must already exist in PostgreSQL before calling this.
    Returns tuple: (success: bool, doc_id: str)
    """
    try:
        progress.log_step("Starting document processing", f"Doc ID: {doc_id}")
        
        # Get the saved file path
        document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
        if not document:
            progress.log_error(f"Document record not found: {doc_id}")
            return False, doc_id
        
        # Check if document still has cli_processing status
        if document.processing_status not in ["cli_processing", "processing"]:
            progress.log_warning(f"Document status is {document.processing_status}, may be processed by background")
        
        saved_file_path = Path(document.file_path)
        file_type = saved_file_path.suffix.lower()
        
        progress.log_step("File analysis", f"Type: {file_type}")
        
        # Update status to processing
        crud.update_document_status(db, doc_id, user_id, "processing", 10)
        
        # Process based on file type
        if file_type == '.pdf':
            progress.log_step("PDF text extraction", "Processing with Marker")
        elif file_type in ['.docx', '.doc']:
            progress.log_step("Word document processing", "Converting to Markdown")
        elif file_type in ['.md', '.markdown']:
            progress.log_step("Markdown file processing", "Reading content")
        
        # Process the document with our specific doc_id
        result = processor.process_document(saved_file_path, doc_id=doc_id)
        
        if result is None:
            progress.log_error("Document processing failed")
            crud.update_document_status(db, doc_id, user_id, "failed", 0)
            return False, doc_id
        
        progress.log_success(f"Generated {result.get('chunks_generated', 0)} chunks")
        progress.log_success(f"Added {result.get('chunks_added_to_vector_store', 0)} chunks to vector store")
        
        # Update the existing document record
        progress.log_step("Updating document record with extracted metadata")
        document = crud.get_document(db, doc_id=doc_id, user_id=user_id)
        if document:
            # Merge metadata
            existing_metadata = document.metadata_ or {}
            extracted_metadata = result.get('extracted_metadata', {})
            merged_metadata = {**existing_metadata, **extracted_metadata}
            
            document.metadata_ = merged_metadata
            document.processing_status = 'completed'
            document.upload_progress = 100
            document.chunk_count = result.get('chunks_generated', 0)
            
            # Also save markdown path if available
            markdown_path = f"/app/data/markdown_files/{doc_id}.md"
            if os.path.exists(markdown_path):
                document.markdown_path = markdown_path
            
            db.commit()
            progress.log_success("Document record updated successfully")
        else:
            progress.log_warning("Could not find document record to update")
        
        progress.log_success(f"Document processing completed successfully")
        return True, doc_id
        
    except Exception as e:
        progress.log_error(f"Processing failed: {str(e)}")
        crud.update_document_status(db, doc_id, user_id, "failed", 0)
        return False, doc_id

@app.command()
def create_user(
    username: str = typer.Argument(..., help="Username for the new user"),
    password: str = typer.Argument(..., help="Password for the new user"),
    full_name: Optional[str] = typer.Option(None, "--full-name", help="Full name of the user"),
    is_admin: bool = typer.Option(False, "--admin", help="Make this user an admin"),
):
    """Create a new user account."""
    try:
        db = get_db_session()
        
        # Check if user already exists
        existing_user = crud.get_user_by_username(db, username=username)
        if existing_user:
            typer.secho(f"Error: User '{username}' already exists.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Create user using the schema
        from api.schemas import UserCreate
        user_create = UserCreate(
            username=username,
            password=password,
            full_name=full_name,
            is_admin=is_admin,
            is_active=True,
            role="admin" if is_admin else "user",
            user_type="individual"
        )
        
        user = crud.create_user(db, user_create)
        
        typer.secho(f"Successfully created user '{username}' with ID {user.id}", fg=typer.colors.GREEN)
        if is_admin:
            typer.secho("User has admin privileges.", fg=typer.colors.YELLOW)
            
    except Exception as e:
        typer.secho(f"Error creating user: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def create_group(
    username: str = typer.Argument(..., help="Username of the user who will own the group"),
    group_name: str = typer.Argument(..., help="Name for the document group"),
    description: Optional[str] = typer.Option(None, "--description", help="Description for the group"),
):
    """Create a new document group for a user."""
    try:
        db = get_db_session()
        
        # Get user
        user = crud.get_user_by_username(db, username=username)
        if not user:
            typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Create group
        group_id = str(uuid.uuid4())
        group = crud.create_document_group(
            db=db,
            group_id=group_id,
            user_id=user.id,
            name=group_name,
            description=description
        )
        
        typer.secho(f"Successfully created group '{group_name}' with ID {group.id} for user '{username}'", fg=typer.colors.GREEN)
        
    except Exception as e:
        typer.secho(f"Error creating group: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def list_groups(
    username: Optional[str] = typer.Option(None, "--user", help="Username to filter groups by (optional)")
):
    """List document groups, optionally filtered by user."""
    try:
        db = get_db_session()
        
        if username:
            user = crud.get_user_by_username(db, username=username)
            if not user:
                typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            groups = crud.get_user_document_groups(db, user_id=user.id)
            typer.echo(f"\n--- Document Groups for {username} ---")
        else:
            groups = db.query(DocumentGroup).all()
            typer.echo("\n--- All Document Groups ---")
        
        if not groups:
            typer.echo("No groups found.")
            return
        
        for group in groups:
            group_user = crud.get_user(db, user_id=group.user_id)
            user_info = f" (User: {group_user.username})" if not username else ""
            doc_count = len(group.documents)
            typer.echo(f"ID: {group.id}, Name: {group.name}, Documents: {doc_count}{user_info}")
            if group.description:
                typer.echo(f"  Description: {group.description}")
            
    except Exception as e:
        typer.secho(f"Error listing groups: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def ingest(
    username: str = typer.Argument(..., help="Username of the user who will own the documents"),
    document_dir: Path = typer.Argument(..., help="Directory containing documents to ingest"),
    group_id: Optional[str] = typer.Option(None, "--group", help="ID of the document group"),
    force_reembed: bool = typer.Option(False, "--force-reembed", help="Force re-processing"),
    device: Optional[str] = typer.Option(None, "--device", help="Device to use (e.g., 'cuda:0', 'cpu')"),
    delete_after_success: bool = typer.Option(False, "--delete-after-success", help="Delete source files after success"),
    batch_size: int = typer.Option(2, "--batch-size", help="Number of documents to process in parallel"),
):
    """
    Directly process documents with live feedback.
    Creates document records BEFORE processing to avoid foreign key violations.
    """
    try:
        db = get_db_session()
        
        # Validate user
        user = crud.get_user_by_username(db, username=username)
        if not user:
            typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Validate group if provided
        group = None
        if group_id:
            group = crud.get_document_group(db, group_id=group_id, user_id=user.id)
            if not group:
                typer.secho(f"Error: Document group '{group_id}' not found.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
        
        # Validate document directory
        document_dir = Path(document_dir).resolve()
        if not document_dir.is_dir():
            typer.secho(f"Error: Document directory not found: {document_dir}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Find supported document files
        supported_extensions = ['*.pdf', '*.docx', '*.doc', '*.md', '*.markdown']
        document_files = []
        
        for extension in supported_extensions:
            files = list(document_dir.glob(extension))
            document_files.extend(files)
        
        if not document_files:
            typer.secho(f"No supported document files found in {document_dir}", fg=typer.colors.YELLOW)
            typer.echo("Supported formats: PDF, DOCX, DOC, MD, MARKDOWN")
            raise typer.Exit()
        
        typer.echo(f"\n=== MAESTRO Direct Document Processing ===")
        typer.echo(f"Target user: {username} (ID: {user.id})")
        if group:
            typer.echo(f"Target group: {group.name} (ID: {group.id})")
        typer.echo(f"Found {len(document_files)} document files to process")
        typer.echo(f"Batch size: {batch_size}")
        typer.echo("=" * 50)
        
        # STEP 1: Create all document records FIRST
        typer.echo("\n📝 Creating document records in database...")
        doc_id_map = {}  # Map file path to doc_id
        created_count = 0
        skipped_count = 0
        
        for file_path in document_files:
            doc_id = str(uuid.uuid4())
            if create_document_record(db, doc_id, user.id, file_path, group_id):
                doc_id_map[file_path] = doc_id
                created_count += 1
            else:
                skipped_count += 1
        
        typer.secho(f"✓ Created {created_count} document records, skipped {skipped_count} duplicates", 
                   fg=typer.colors.GREEN)
        
        if created_count == 0:
            typer.echo("No new documents to process.")
            return
        
        # STEP 2: Process the documents
        typer.echo("\n🔄 Processing documents...")
        
        # Get user settings for LLM configuration
        user_settings = user.settings or {}
        
        # Prepare for processing
        success_count = 0
        error_count = 0
        
        # Determine actual batch size
        actual_batch_size = min(batch_size, created_count)
        
        if actual_batch_size > 1:
            # Parallel processing
            typer.echo(f"Processing in parallel (batch size: {actual_batch_size})...")
            
            try:
                multiprocessing.set_start_method('spawn', force=True)
            except RuntimeError:
                pass
            
            global global_executor
            global_executor = ProcessPoolExecutor(max_workers=actual_batch_size)
            
            try:
                executor = global_executor
                
                # Prepare arguments for processing
                process_args = []
                index = 1
                for file_path, doc_id in doc_id_map.items():
                    # Get the saved file path
                    document = crud.get_document(db, doc_id=doc_id, user_id=user.id)
                    if document:
                        saved_file_path = document.file_path
                        args = (saved_file_path, doc_id, user.id, index, created_count,
                               force_reembed, device, user_settings)
                        process_args.append(args)
                        index += 1
                
                # Submit all tasks
                futures = {executor.submit(process_document_in_subprocess, args): args[1] 
                          for args in process_args}
                
                # Process completed tasks
                for future in as_completed(futures):
                    doc_id = futures[future]
                    try:
                        success, result_id, result_msg = future.result()
                        
                        if success:
                            success_count += 1
                            typer.secho(f"✓ {result_id}: {result_msg}", fg=typer.colors.GREEN)
                        else:
                            error_count += 1
                            typer.secho(f"✗ {result_id}: {result_msg}", fg=typer.colors.RED)
                    except Exception as e:
                        error_count += 1
                        typer.secho(f"✗ Error processing {doc_id}: {e}", fg=typer.colors.RED)
                
            finally:
                if global_executor:
                    global_executor.shutdown(wait=True)
                    global_executor = None
                    
        else:
            # Sequential processing
            typer.echo("Processing documents sequentially...")
            
            # Initialize processor for sequential mode
            embedder = TextEmbedder(model_name="BAAI/bge-m3", device=device)
            vector_store = VectorStore()
            
            from ai_researcher.core_rag.metadata_extractor import MetadataExtractor
            if user_settings:
                metadata_extractor = MetadataExtractor.from_user_settings(user_settings)
            else:
                metadata_extractor = MetadataExtractor()
            
            base_path = Path("/app/ai_researcher/data")
            processor = DocumentProcessor(
                pdf_dir=base_path / "raw_pdfs",
                markdown_dir=base_path / "processed" / "markdown",
                metadata_dir=base_path / "processed" / "metadata",
                db_path=None,
                embedder=embedder,
                vector_store=vector_store,
                force_reembed=force_reembed,
                device=device
            )
            processor.metadata_extractor = metadata_extractor
            
            index = 1
            for file_path, doc_id in doc_id_map.items():
                typer.echo(f"\n--- Processing {index}/{created_count}: {file_path.name} ---")
                
                progress = LiveProgressCallback(file_path.name)
                
                try:
                    success, result_id = process_single_document(
                        file_path=file_path,
                        doc_id=doc_id,
                        user_id=user.id,
                        db=db,
                        processor=processor,
                        progress=progress
                    )
                    
                    if success:
                        success_count += 1
                        typer.secho(f"✓ Successfully processed (ID: {result_id})", 
                                  fg=typer.colors.GREEN)
                        
                        # Delete source file if requested
                        if delete_after_success and file_path.exists():
                            file_path.unlink()
                            typer.echo(f"  Deleted source file: {file_path.name}")
                    else:
                        error_count += 1
                        typer.secho(f"✗ Failed to process", fg=typer.colors.RED)
                        
                except Exception as e:
                    error_count += 1
                    typer.secho(f"✗ Error: {e}", fg=typer.colors.RED)
                
                index += 1
        
        # Summary
        typer.echo("\n" + "=" * 50)
        typer.echo("=== Processing Complete ===")
        typer.secho(f"✓ Successfully processed: {success_count} documents", fg=typer.colors.GREEN)
        if error_count > 0:
            typer.secho(f"✗ Failed: {error_count} documents", fg=typer.colors.RED)
        
        typer.echo("\nAll documents are now available for search and chat.")
        
    except Exception as e:
        typer.secho(f"Error during ingestion: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def status(
    username: Optional[str] = typer.Option(None, "--user", help="Filter by username"),
    group_id: Optional[str] = typer.Option(None, "--group", help="Filter by group ID"),
):
    """Check document processing status."""
    try:
        db = get_db_session()
        
        # Build query
        query = db.query(models.Document)
        
        if username:
            user = crud.get_user_by_username(db, username=username)
            if not user:
                typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            query = query.filter(models.Document.user_id == user.id)
        
        if group_id:
            # Join with document_group_association
            from database.models import document_group_association
            query = query.join(
                document_group_association,
                models.Document.id == document_group_association.c.document_id
            ).filter(document_group_association.c.document_group_id == group_id)
        
        documents = query.all()
        
        if not documents:
            typer.echo("No documents found.")
            return
        
        # Group by status
        status_counts = {}
        for doc in documents:
            status = doc.processing_status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
        
        typer.echo("\n=== Document Status Summary ===")
        for status, count in status_counts.items():
            color = typer.colors.GREEN if status == "completed" else typer.colors.YELLOW
            if status == "failed":
                color = typer.colors.RED
            typer.secho(f"{status}: {count} documents", fg=color)
        
        typer.echo(f"\nTotal: {len(documents)} documents")
        
    except Exception as e:
        typer.secho(f"Error checking status: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def cleanup(
    username: Optional[str] = typer.Option(None, "--user", help="Filter by username"),
    status: str = typer.Option("failed", "--status", help="Status to cleanup"),
    group_id: Optional[str] = typer.Option(None, "--group", help="Filter by group ID"),
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation"),
):
    """Clean up documents with specific status."""
    try:
        db = get_db_session()
        
        # Build query
        query = db.query(models.Document).filter(models.Document.processing_status == status)
        
        if username:
            user = crud.get_user_by_username(db, username=username)
            if not user:
                typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            query = query.filter(models.Document.user_id == user.id)
        
        if group_id:
            from database.models import document_group_association
            query = query.join(
                document_group_association,
                models.Document.id == document_group_association.c.document_id
            ).filter(document_group_association.c.document_group_id == group_id)
        
        documents = query.all()
        
        if not documents:
            typer.echo(f"No documents found with status '{status}'.")
            return
        
        typer.echo(f"Found {len(documents)} documents with status '{status}'")
        
        if not confirm:
            confirm = typer.confirm("Do you want to delete these documents?")
            if not confirm:
                typer.echo("Cleanup cancelled.")
                return
        
        # Delete documents
        deleted_count = 0
        for doc in documents:
            try:
                # Delete file if exists
                if doc.file_path and os.path.exists(doc.file_path):
                    os.remove(doc.file_path)
                
                # Delete from database
                db.delete(doc)
                deleted_count += 1
            except Exception as e:
                typer.secho(f"Error deleting {doc.filename}: {e}", fg=typer.colors.RED)
        
        db.commit()
        typer.secho(f"✓ Deleted {deleted_count} documents", fg=typer.colors.GREEN)
        
    except Exception as e:
        typer.secho(f"Error during cleanup: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def cleanup_cli(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without actually deleting"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt"),
):
    """
    Clean up dangling CLI-ingested documents.
    
    Removes documents that were being processed via CLI but were interrupted
    (e.g., by Ctrl+C) and are now stuck with 'cli_processing' status.
    """
    try:
        db = get_db_session()
        
        # Find all documents with cli_processing status
        cli_documents = db.query(Document).filter(
            Document.processing_status == "cli_processing"
        ).all()
        
        if not cli_documents:
            typer.secho("✓ No dangling CLI documents found.", fg=typer.colors.GREEN)
            return
        
        typer.secho(f"\nFound {len(cli_documents)} dangling CLI documents:", fg=typer.colors.YELLOW)
        typer.echo("-" * 80)
        
        total_size = 0
        for doc in cli_documents:
            user = crud.get_user(db, user_id=doc.user_id)
            username = user.username if user else f"User ID {doc.user_id}"
            
            typer.echo(f"\nDocument ID: {doc.id}")
            typer.echo(f"  User: {username}")
            typer.echo(f"  Filename: {doc.original_filename}")
            typer.echo(f"  Created: {doc.created_at}")
            if doc.file_size:
                typer.echo(f"  File size: {doc.file_size:,} bytes")
                total_size += doc.file_size
            if doc.file_path:
                exists = os.path.exists(doc.file_path) if doc.file_path else False
                typer.echo(f"  File path: {doc.file_path} {'(exists)' if exists else '(missing)'}")
        
        typer.echo("\n" + "-" * 80)
        typer.echo(f"Total documents: {len(cli_documents)}")
        if total_size > 0:
            typer.echo(f"Total size: {total_size:,} bytes ({total_size / (1024*1024):.2f} MB)")
        
        if dry_run:
            typer.secho("\nDRY RUN - No changes made", fg=typer.colors.YELLOW)
            typer.echo("These documents and their associated files would be deleted.")
            return
        
        # Ask for confirmation unless --force is used
        if not force:
            confirm = typer.confirm("\nDo you want to delete these documents and their files?")
            if not confirm:
                typer.echo("Cleanup cancelled.")
                return
        
        # Perform cleanup
        typer.echo("\nCleaning up dangling documents...")
        deleted_count = 0
        errors = []
        
        for doc in cli_documents:
            try:
                typer.echo(f"  Deleting {doc.original_filename}...", nl=False)
                
                # Delete associated files
                files_deleted = []
                
                # Raw file
                if doc.file_path and os.path.exists(doc.file_path):
                    os.remove(doc.file_path)
                    files_deleted.append("raw file")
                
                # Markdown file (if exists)
                markdown_path = f"/app/data/markdown_files/{doc.id}.md"
                if os.path.exists(markdown_path):
                    os.remove(markdown_path)
                    files_deleted.append("markdown")
                
                # Remove from document groups (if any)
                from database.models import document_group_association
                db.execute(
                    document_group_association.delete().where(
                        document_group_association.c.document_id == doc.id
                    )
                )
                
                # Try to delete from vector store
                try:
                    vector_store = VectorStore()
                    for collection_name in ["documents_dense", "documents_sparse"]:
                        try:
                            collection = vector_store.chroma_client.get_collection(collection_name)
                            collection.delete(where={"doc_id": str(doc.id)})
                        except:
                            pass  # Collection might not exist or document might not be in it
                except:
                    pass  # Vector store might not be available
                
                # Delete the document record
                db.delete(doc)
                deleted_count += 1
                
                if files_deleted:
                    typer.secho(f" ✓ (deleted: {', '.join(files_deleted)})", fg=typer.colors.GREEN)
                else:
                    typer.secho(" ✓", fg=typer.colors.GREEN)
                    
            except Exception as e:
                typer.secho(f" ✗ Error: {e}", fg=typer.colors.RED)
                errors.append(f"Document {doc.id}: {str(e)}")
        
        # Commit all deletions
        db.commit()
        
        typer.echo("\n" + "-" * 80)
        typer.secho(f"✓ Successfully cleaned up {deleted_count} dangling CLI documents", fg=typer.colors.GREEN)
        
        if errors:
            typer.secho(f"⚠ {len(errors)} errors encountered:", fg=typer.colors.YELLOW)
            for error in errors[:5]:  # Show first 5 errors
                typer.echo(f"  - {error}")
                
    except Exception as e:
        typer.secho(f"Error during CLI cleanup: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def search(
    username: str = typer.Argument(..., help="Username to search for"),
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", help="Number of results"),
):
    """Search through documents for a specific user."""
    try:
        db = get_db_session()
        
        # Get user
        user = crud.get_user_by_username(db, username=username)
        if not user:
            typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Get user's documents to filter search
        user_docs = crud.get_user_documents(db, user_id=user.id, skip=0, limit=1000)
        if not user_docs:
            typer.echo(f"No documents found for user '{username}'.")
            return
        
        doc_ids = [doc.id for doc in user_docs]
        
        # Initialize vector store for search
        vector_store = VectorStore()
        embedder = TextEmbedder(model_name="BAAI/bge-m3")
        
        # Perform search
        typer.echo(f"Searching for: '{query}'...")
        
        # Embed query
        query_embedding = embedder.embed_query(query)
        
        # Search in vector store using the query method
        results = vector_store.query(
            query_dense_embedding=query_embedding['dense'],
            query_sparse_embedding_dict=query_embedding['sparse'],
            n_results=limit,
            filter_metadata={"doc_id": {"$in": doc_ids}}  # Only search this user's documents
        )
        
        if not results:
            typer.echo("No results found.")
            return
        
        typer.echo(f"\n=== Search Results ({len(results)} found) ===")
        for i, result in enumerate(results, 1):
            doc_id = result.get('doc_id', 'Unknown')
            score = result.get('score', 0)
            chunk_text = result.get('text', '')[:200]
            
            # Get document info
            document = crud.get_document(db, doc_id=doc_id, user_id=user.id)
            if document:
                title = document.metadata_.get('title', document.filename) if document.metadata_ else document.filename
                typer.echo(f"\n{i}. {title} (Score: {score:.3f})")
                typer.echo(f"   ID: {doc_id}")
                typer.echo(f"   Preview: {chunk_text}...")
            else:
                typer.echo(f"\n{i}. Document ID: {doc_id} (Score: {score:.3f})")
                typer.echo(f"   Preview: {chunk_text}...")
        
    except Exception as e:
        typer.secho(f"Error during search: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

if __name__ == "__main__":
    app()
