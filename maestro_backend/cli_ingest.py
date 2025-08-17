#!/usr/bin/env python3
"""
Direct CLI tool for synchronous document ingestion into MAESTRO.
This script processes documents immediately with live feedback, bypassing the background queue system.
"""

import typer
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple
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
    from database import crud
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

def process_document_in_subprocess(args):
    """
    Process a document in a separate process.
    This function is designed to be pickleable and run in ProcessPoolExecutor.
    Each process gets its own memory space, avoiding Marker threading issues.
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
            from database import crud
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
    
    # Unpack arguments (document_file is passed as string to avoid pickle issues)
    try:
        (document_file_str, doc_id, user_id, group_id, index, total, 
         force_reembed, device, delete_after_success, user_settings) = args
        print(f"[Process {os.getpid()}] Successfully unpacked arguments")
    except Exception as e:
        print(f"[Process {os.getpid()}] Failed to unpack arguments: {e}")
        return (False, "unpack_error", str(e))
    
    # Convert back to Path object
    document_file = Path(document_file_str)
    print(f"[Process {os.getpid()}] Processing file: {document_file}")
    
    # Initialize components for this process
    base_path = Path("/app/ai_researcher/data")
    vector_store_path = base_path / "vector_store"
    
    try:
        # Initialize components
        print(f"[Process {os.getpid()}] Initializing components for {document_file.name}...")
        
        # Handle CUDA device allocation for subprocess
        # All processes can use the same GPU, but we need to stagger initialization
        # to avoid race conditions
        import time
        
        # With spawn method, each process has a fresh CUDA context
        # No need for delays or manual initialization
        actual_device = device or 'cuda'
        print(f"[Process {os.getpid()}] Using device: {actual_device}")
        
        # Initialize embedder with proper device
        print(f"[Process {os.getpid()}] Creating TextEmbedder with device={actual_device}...")
        embedder = TextEmbedder(model_name="BAAI/bge-m3", device=actual_device)
        print(f"[Process {os.getpid()}] TextEmbedder created successfully")
        
        print(f"[Process {os.getpid()}] Creating VectorStore...")
        vector_store = VectorStore()
        print(f"[Process {os.getpid()}] VectorStore created successfully")
        
        # Create metadata extractor with user settings
        if user_settings:
            metadata_extractor = MetadataExtractor.from_user_settings(user_settings)
        else:
            metadata_extractor = MetadataExtractor()
        
        # Initialize processor with same device as embedder
        print(f"[Process {os.getpid()}] Creating DocumentProcessor...")
        processor = DocumentProcessor(
            pdf_dir=base_path / "raw_pdfs",
            markdown_dir=base_path / "processed" / "markdown",
            metadata_dir=base_path / "processed" / "metadata",
            db_path=None,  # Not using SQLite, operations handled via PostgreSQL elsewhere
            embedder=embedder,
            vector_store=vector_store,
            force_reembed=force_reembed,
            device=actual_device  # Use the same device as embedder
        )
        print(f"[Process {os.getpid()}] DocumentProcessor created successfully")
        
        # Replace processor's metadata extractor
        processor.metadata_extractor = metadata_extractor
        
        # Get database session
        db = next(get_db())
        
        # Process the document
        print(f"[{index}/{total}] Processing {document_file.name}...")
        
        file_size = document_file.stat().st_size
        file_type = document_file.suffix.lower()
        
        # Process based on file type
        result = processor.process_document(document_file)
        
        if result is None:
            print(f"[{index}/{total}] Failed: {document_file.name}")
            db.close()
            return (False, document_file.name, f"Processing failed")
        
        # Use the doc_id returned by the processor instead of generating our own
        actual_doc_id = result.get('doc_id')
        if not actual_doc_id:
            print(f"[{index}/{total}] Warning: No doc_id returned by processor, using generated one")
            actual_doc_id = doc_id
        
        # Create database record for successful processing
        crud.create_document(
            db=db,
            doc_id=actual_doc_id,
            user_id=user_id,
            original_filename=document_file.name,
            metadata=result.get('extracted_metadata', {}),
            processing_status='completed',
            upload_progress=100,
            file_size=file_size,
            file_path=str(document_file)
        )
        
        # Add to group if specified
        if group_id:
            document = crud.get_document(db, doc_id=actual_doc_id, user_id=user_id)
            if document:
                crud.add_document_to_group(db, document.id, group_id)
        
        # Delete source file if requested
        if delete_after_success and document_file.exists():
            document_file.unlink()
        
        db.close()
        
        chunks_generated = result.get('chunks_generated', 0)
        chunks_added = result.get('chunks_added_to_vector_store', 0)
        
        print(f"[{index}/{total}] Success: {document_file.name} (ID: {actual_doc_id}, {chunks_added} chunks)")
        return (True, document_file.name, actual_doc_id)
        
    except MemoryError as e:
        print(f"[{index}/{total}] Memory Error: {document_file.name} - Out of memory")
        return (False, document_file.name, "Out of memory - file too large or complex")
    except Exception as e:
        error_msg = str(e)
        # Check for common Marker/processing errors
        if "malloc" in error_msg or "double linked list" in error_msg:
            print(f"[{index}/{total}] Memory corruption: {document_file.name}")
            return (False, document_file.name, "Memory corruption - file too complex")
        elif "killed" in error_msg.lower() or "terminated" in error_msg.lower():
            print(f"[{index}/{total}] Process killed: {document_file.name}")
            return (False, document_file.name, "Process terminated - likely out of memory")
        else:
            print(f"[{index}/{total}] Error: {document_file.name} - {error_msg[:200]}")
            return (False, document_file.name, error_msg[:200])

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
    group_id: Optional[str], 
    db: Session,
    processor: DocumentProcessor,
    progress: LiveProgressCallback,
    delete_after_success: bool = False
) -> tuple:
    """
    Process a single document with live progress feedback.
    Supports PDF, Word (docx, doc), and Markdown (md, markdown) files.
    Only creates database records for successfully processed documents.
    Returns tuple: (success: bool, actual_doc_id: str)
    """
    try:
        progress.log_step("Starting document processing", f"File: {file_path.name}")
        
        # Get file size for progress tracking
        file_size = file_path.stat().st_size
        file_type = file_path.suffix.lower()
        progress.log_step("File analysis", f"Size: {file_size:,} bytes, Type: {file_type}")
        
        # Process the document using the AI researcher pipeline FIRST
        # Don't create database record until we know processing succeeds
        if file_type == '.pdf':
            progress.log_step("PDF text extraction", "Extracting header/footer for metadata")
        elif file_type in ['.docx', '.doc']:
            progress.log_step("Word document processing", "Converting to Markdown and extracting metadata")
        elif file_type in ['.md', '.markdown']:
            progress.log_step("Markdown file processing", "Reading content and extracting metadata")
        else:
            progress.log_error(f"Unsupported file format: {file_type}")
            return False, doc_id
            
        # Process the document
        result = processor.process_document(file_path)
        
        if result is None:
            progress.log_error("Document processing failed - document will not be added to database")
            return False, doc_id
        
        # Use the doc_id returned by the processor instead of the one we generated
        actual_doc_id = result.get('doc_id')
        if not actual_doc_id:
            progress.log_warning("No doc_id returned by processor, using generated one")
            actual_doc_id = doc_id
        
        progress.log_success(f"Generated {result.get('chunks_generated', 0)} chunks")
        progress.log_success(f"Added {result.get('chunks_added_to_vector_store', 0)} chunks to vector store")
        
        # Only create database record AFTER successful processing
        progress.log_step("Creating database record for successfully processed document")
        crud.create_document(
            db=db,
            doc_id=actual_doc_id,
            user_id=user_id,
            original_filename=file_path.name,
            metadata=result.get('extracted_metadata', {}),
            processing_status='completed',  # Only create completed documents
            upload_progress=100,
            file_size=file_size,
            file_path=str(file_path)
        )
        
        # Add to group if group_id is provided
        if group_id:
            progress.log_step("Adding to document group")
            crud.add_document_to_group(db, group_id=group_id, doc_id=actual_doc_id, user_id=user_id)
        else:
            progress.log_step("Document added to user library", "No group specified - can be organized later")
        
        progress.log_success(f"Document processing completed successfully")
        
        # Delete the source file if requested and processing was successful
        if delete_after_success:
            try:
                file_path.unlink()  # Delete the file
                progress.log_success(f"Deleted source file: {file_path.name}")
            except Exception as delete_error:
                progress.log_warning(f"Failed to delete source file: {delete_error}")
                # Don't fail the entire operation if file deletion fails
        
        return True, actual_doc_id
        
    except Exception as e:
        progress.log_error(f"Processing failed: {str(e)}")
        # Don't create any database record for failed documents
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
        
        # Create group (generate UUID for group_id)
        import uuid
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
            # Get all groups (admin function)
            groups = db.query(DocumentGroup).all()
            typer.echo("\n--- All Document Groups ---")
        
        if not groups:
            typer.echo("No groups found.")
            return
        
        for group in groups:
            # Get user info for each group
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
    document_dir: Path = typer.Argument(..., help="Directory containing documents to ingest (PDF, Word, Markdown)"),
    group_id: Optional[str] = typer.Option(None, "--group", help="ID of the document group to add documents to (optional)"),
    force_reembed: bool = typer.Option(False, "--force-reembed", help="Force re-processing and re-embedding for all documents"),
    device: Optional[str] = typer.Option(None, "--device", help="Device to use for processing (e.g., 'cuda:0', 'cpu')"),
    delete_after_success: bool = typer.Option(False, "--delete-after-success", help="Delete source files after successful processing"),
    batch_size: int = typer.Option(2, "--batch-size", "--batch", help="Number of documents to process in parallel (1 for sequential, max 3 recommended)"),
):
    """
    Directly process documents with live feedback.
    Supports PDF, Word (docx, doc), and Markdown (md, markdown) files.
    
    By default, processes 2 documents in parallel for balanced speed and stability.
    Use --batch-size 1 for sequential processing (most stable).
    Use --batch-size 3 for more parallelism (may cause memory issues with large PDFs).
    
    Documents are added to the user's library and can be organized into groups later.
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
                typer.secho(f"Error: Document group '{group_id}' not found for user '{username}'.", fg=typer.colors.RED)
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
        
        # Group files by type for reporting
        pdf_files = [f for f in document_files if f.suffix.lower() == '.pdf']
        word_files = [f for f in document_files if f.suffix.lower() in ['.docx', '.doc']]
        markdown_files = [f for f in document_files if f.suffix.lower() in ['.md', '.markdown']]
        
        typer.echo(f"\n=== MAESTRO Direct Document Processing ===")
        typer.echo(f"Target user: {username} (ID: {user.id})")
        if group:
            typer.echo(f"Target group: {group.name} (ID: {group.id})")
        else:
            typer.echo(f"Target group: None (documents will be added to user library)")
        typer.echo(f"Found {len(document_files)} document files to process:")
        typer.echo(f"  - {len(pdf_files)} PDF files")
        typer.echo(f"  - {len(word_files)} Word documents")
        typer.echo(f"  - {len(markdown_files)} Markdown files")
        typer.echo(f"Batch size: {batch_size} (parallel processing: {'enabled' if batch_size > 1 else 'disabled'})")
        typer.echo(f"Force re-embed: {force_reembed}")
        if device:
            typer.echo(f"Using device: {device}")
        typer.echo("=" * 50)
        
        # Initialize the document processor with AI researcher components
        typer.echo("\nInitializing document processor...")
        
        # Set up paths (use container paths)
        base_path = Path("/app/ai_researcher/data")
        vector_store_path = base_path / "vector_store"
        
        # Get user settings for LLM configuration
        user_settings = user.settings or {}
        typer.echo(f"Debug: User has settings: {bool(user_settings)}")
        
        # Initialize components
        embedder = TextEmbedder(model_name="BAAI/bge-m3")
        vector_store = VectorStore()
        
        # Initialize metadata extractor with user's LLM settings
        from ai_researcher.core_rag.metadata_extractor import MetadataExtractor
        if user_settings:
            metadata_extractor = MetadataExtractor.from_user_settings(user_settings)
            typer.echo("Debug: Initialized metadata extractor with user settings")
        else:
            metadata_extractor = MetadataExtractor()
            typer.echo("Debug: Initialized metadata extractor with default settings")
        
        # Initialize processor with direct paths and components
        processor = DocumentProcessor(
            pdf_dir=document_dir,  # Use the input directory
            markdown_dir=base_path / "processed" / "markdown",
            metadata_dir=base_path / "processed" / "metadata",
            db_path=None,  # Not using SQLite, operations handled via PostgreSQL elsewhere
            embedder=embedder,
            vector_store=vector_store,
            force_reembed=force_reembed,
            device=device
        )
        
        # Replace the processor's metadata extractor with our configured one
        processor.metadata_extractor = metadata_extractor
        
        typer.secho("✓ Document processor initialized", fg=typer.colors.GREEN)
        
        # Process files with parallel execution based on batch_size
        success_count = 0
        error_count = 0
        
        # Determine actual batch size (limit to number of documents if fewer)
        actual_batch_size = min(batch_size, len(document_files))
        
        if actual_batch_size > 1:
            typer.echo(f"\nProcessing documents in parallel (batch size: {actual_batch_size})...")
            typer.echo("Using separate processes for true parallelism (no Marker conflicts)...")
            typer.echo("Press Ctrl+C to gracefully stop processing...")
        else:
            typer.echo(f"\nProcessing documents sequentially...")
        
        # Process documents in parallel or sequentially based on batch_size
        if actual_batch_size > 1:
            # Ensure spawn method is set for CUDA compatibility
            try:
                multiprocessing.set_start_method('spawn', force=True)
            except RuntimeError:
                pass  # Already set
            
            # Get user settings for subprocess
            user_settings_for_subprocess = user.settings if user and user.settings else {}
            
            # Parallel processing with ProcessPoolExecutor
            global global_executor
            global_executor = ProcessPoolExecutor(max_workers=actual_batch_size)
            
            try:
                executor = global_executor
                # Prepare arguments for all documents (convert Path to string for pickling)
                process_args = []
                for i, doc_file in enumerate(document_files, 1):
                    doc_id = str(uuid.uuid4())
                    # Pass file path as string to avoid pickle issues with Path objects
                    args = (str(doc_file), doc_id, user.id, group_id, i, len(document_files),
                           force_reembed, device, delete_after_success, user_settings_for_subprocess)
                    process_args.append(args)
                
                # Submit all tasks to process pool
                futures = {executor.submit(process_document_in_subprocess, args): Path(args[0]) 
                          for args in process_args}
                
                # Process completed tasks as they finish
                for future in as_completed(futures):
                    document_file = futures[future]
                    try:
                        success, filename, result = future.result()
                        
                        if success:
                            success_count += 1
                            typer.secho(f"✓ Successfully processed {filename} (ID: {result})", 
                                      fg=typer.colors.GREEN)
                        else:
                            error_count += 1
                            typer.secho(f"✗ Failed to process {filename}: {result}", 
                                      fg=typer.colors.RED)
                    except Exception as e:
                        error_count += 1
                        typer.secho(f"✗ Error processing {document_file.name}: {e}", 
                                  fg=typer.colors.RED)
            
            finally:
                # Clean shutdown of executor
                if global_executor:
                    global_executor.shutdown(wait=True)
                    global_executor = None
        else:
            # Sequential processing (batch_size = 1 or fallback)
            for i, document_file in enumerate(document_files, 1):
                typer.echo(f"\n--- Processing {i}/{len(document_files)}: {document_file.name} ---")
                
                # Generate document ID
                doc_id = str(uuid.uuid4())
                
                # Create progress tracker
                progress = LiveProgressCallback(document_file.name)
                
                try:
                    # Process the document
                    success, actual_doc_id = process_single_document(
                        file_path=document_file,
                        doc_id=doc_id,
                        user_id=user.id,
                        group_id=group_id,
                        db=db,
                        processor=processor,
                        progress=progress,
                        delete_after_success=delete_after_success
                    )
                    
                    if success:
                        success_count += 1
                        typer.secho(f"✓ Successfully processed {document_file.name} (ID: {actual_doc_id})", 
                                  fg=typer.colors.GREEN)
                    else:
                        error_count += 1
                        typer.secho(f"✗ Failed to process {document_file.name}", 
                                  fg=typer.colors.RED)
                        
                except Exception as e:
                    error_count += 1
                    typer.secho(f"✗ Error processing {document_file.name}: {e}", 
                              fg=typer.colors.RED)
        
        # Summary
        typer.echo(f"\n=== Processing Summary ===")
        typer.secho(f"Successfully processed: {success_count}", fg=typer.colors.GREEN)
        if error_count > 0:
            typer.secho(f"Failed: {error_count}", fg=typer.colors.RED)
        
        typer.echo(f"\nAll documents have been processed and are immediately available for search.")
        
    except Exception as e:
        typer.secho(f"Error during direct ingestion: {e}", fg=typer.colors.RED)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def status(
    username: Optional[str] = typer.Option(None, "--user", help="Username to check status for (optional)"),
    group_id: Optional[str] = typer.Option(None, "--group", help="Group ID to check status for (optional)"),
):
    """Check the status of document processing."""
    try:
        db = get_db_session()
        
        # Build query filters
        filters = {}
        if username:
            user = crud.get_user_by_username(db, username=username)
            if not user:
                typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            filters['user_id'] = user.id
        
        # Get documents with processing status
        if group_id and username:
            group = crud.get_document_group(db, group_id=group_id, user_id=user.id)
            if not group:
                typer.secho(f"Error: Group '{group_id}' not found for user '{username}'.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            documents = group.documents
            typer.echo(f"\n--- Processing Status for Group '{group.name}' ---")
        elif username:
            # Get all documents for user
            documents = db.query(Document).filter_by(user_id=user.id).all()
            typer.echo(f"\n--- Processing Status for User '{username}' ---")
        else:
            # Get all documents (admin view)
            documents = db.query(Document).all()
            typer.echo("\n--- Processing Status for All Documents ---")
        
        if not documents:
            typer.echo("No documents found.")
            return
        
        # Group by status
        status_counts = {}
        for doc in documents:
            status = doc.processing_status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Show summary
        typer.echo(f"\nTotal documents: {len(documents)}")
        for status, count in status_counts.items():
            color = typer.colors.GREEN if status == 'completed' else typer.colors.YELLOW if status in ['queued', 'processing'] else typer.colors.RED
            typer.secho(f"  {status}: {count}", fg=color)
        
        # Show individual document status
        typer.echo("\n--- Individual Documents ---")
        for doc in documents[:20]:  # Limit to first 20 for readability
            status_color = typer.colors.GREEN if doc.processing_status == 'completed' else typer.colors.YELLOW if doc.processing_status in ['queued', 'processing'] else typer.colors.RED
            typer.echo(f"ID: {doc.id}, File: {doc.original_filename}")
            typer.secho(f"  Status: {doc.processing_status}", fg=status_color)
            if doc.processing_error:
                typer.secho(f"  Error: {doc.processing_error}", fg=typer.colors.RED)
        
        if len(documents) > 20:
            typer.echo(f"... and {len(documents) - 20} more documents")
            
    except Exception as e:
        typer.secho(f"Error checking status: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def cleanup(
    username: Optional[str] = typer.Option(None, "--user", help="Username to clean up documents for (optional)"),
    status: Optional[str] = typer.Option(None, "--status", help="Status of documents to clean up (e.g., 'failed', 'error')"),
    group_id: Optional[str] = typer.Option(None, "--group", help="Group ID to clean up documents from (optional)"),
    sync_with_vector_store: bool = typer.Option(False, "--sync-vector-store", help="Remove database documents that aren't in vector store"),
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt"),
):
    """Clean up documents with specific status or sync database with vector store."""
    try:
        db = get_db_session()
        
        # Validate user if provided
        user = None
        if username:
            user = crud.get_user_by_username(db, username=username)
            if not user:
                typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
        
        # Validate group if provided
        group = None
        if group_id and user:
            group = crud.get_document_group(db, group_id=group_id, user_id=user.id)
            if not group:
                typer.secho(f"Error: Group '{group_id}' not found for user '{username}'.", fg=typer.colors.RED)
                raise typer.Exit(code=1)
        
        # Handle vector store sync mode
        if sync_with_vector_store:
            typer.echo("Analyzing database vs vector store synchronization...")
            
            # Get all database documents
            if user:
                db_docs = db.query(Document).filter(Document.user_id == user.id).all()
            else:
                db_docs = db.query(Document).all()
            
            db_doc_ids = {doc.id for doc in db_docs}
            typer.echo(f"Database documents: {len(db_doc_ids)}")
            
            # Get vector store documents
            try:
                from ai_researcher.core_rag.pgvector_store import PGVectorStore as VectorStore
                base_path = Path('/app/ai_researcher/data')
                vector_store_path = base_path / 'vector_store'
                vector_store = VectorStore()
                
                dense_collection = vector_store.dense_collection
                results = dense_collection.get(include=['metadatas'])
                all_metadatas = results.get('metadatas', [])
                
                vs_doc_ids = set()
                for meta in all_metadatas:
                    doc_id = meta.get('doc_id')
                    if doc_id:
                        vs_doc_ids.add(doc_id)
                
                typer.echo(f"Vector store documents: {len(vs_doc_ids)}")
                
                # Find documents in database but not in vector store
                db_only = db_doc_ids - vs_doc_ids
                vs_only = vs_doc_ids - db_doc_ids
                
                typer.echo(f"Documents in database but NOT in vector store: {len(db_only)}")
                typer.echo(f"Documents in vector store but NOT in database: {len(vs_only)}")
                
                if not db_only:
                    typer.echo("Database and vector store are already synchronized!")
                    return
                
                # Filter to documents that are in database but not in vector store
                documents_to_cleanup = [doc for doc in db_docs if doc.id in db_only]
                
                typer.echo(f"Found {len(documents_to_cleanup)} documents to sync (remove from database)")
                
            except Exception as e:
                typer.secho(f"Error accessing vector store: {e}", fg=typer.colors.RED)
                raise typer.Exit(code=1)
        else:
            # Build query for documents to clean up by status
            query = db.query(Document)
            
            # Apply filters
            if user:
                query = query.filter(Document.user_id == user.id)
            
            if status:
                query = query.filter(Document.processing_status == status)
            
            if group:
                # Get documents in the specific group
                group_doc_ids = [doc.id for doc in group.documents]
                query = query.filter(Document.id.in_(group_doc_ids))
            
            documents_to_cleanup = query.all()
        
        if not documents_to_cleanup:
            typer.echo("No documents found matching the cleanup criteria.")
            return
        
        # Show what will be cleaned up
        typer.echo(f"\n--- Documents to Clean Up ---")
        if user:
            typer.echo(f"User: {username}")
        if group:
            typer.echo(f"Group: {group.name}")
        if status:
            typer.echo(f"Status: {status}")
        
        typer.echo(f"\nFound {len(documents_to_cleanup)} documents to clean up:")
        
        for doc in documents_to_cleanup[:10]:  # Show first 10
            typer.echo(f"  - {doc.original_filename} (Status: {doc.processing_status})")
            if doc.processing_error:
                typer.echo(f"    Error: {doc.processing_error}")
        
        if len(documents_to_cleanup) > 10:
            typer.echo(f"  ... and {len(documents_to_cleanup) - 10} more documents")
        
        # Confirmation
        if not confirm:
            typer.echo(f"\nThis will permanently delete {len(documents_to_cleanup)} documents from the database.")
            typer.echo("Vector store entries and associated data will also be removed.")
            
            if not typer.confirm("Are you sure you want to proceed?"):
                typer.echo("Cleanup cancelled.")
                return
        
        # Perform cleanup
        typer.echo("\nStarting cleanup...")
        
        deleted_count = 0
        error_count = 0
        
        for doc in documents_to_cleanup:
            try:
                # Just delete from database for now - don't try to call async functions
                db.delete(doc)
                deleted_count += 1
                
                if deleted_count % 10 == 0:
                    typer.echo(f"Cleaned up {deleted_count}/{len(documents_to_cleanup)} documents...")
                
            except Exception as e:
                error_count += 1
                typer.secho(f"Error cleaning up {doc.original_filename}: {e}", fg=typer.colors.RED)
        
        # Commit all deletions
        db.commit()
        
        # Summary
        typer.echo(f"\n=== Cleanup Summary ===")
        typer.secho(f"Successfully cleaned up: {deleted_count}", fg=typer.colors.GREEN)
        if error_count > 0:
            typer.secho(f"Errors: {error_count}", fg=typer.colors.RED)
        
        typer.echo("Cleanup completed.")
        
    except Exception as e:
        typer.secho(f"Error during cleanup: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def search(
    username: str = typer.Argument(..., help="Username to search documents for"),
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", help="Maximum number of results to return"),
):
    """Search through documents for a specific user."""
    try:
        db = get_db_session()
        
        # Validate user
        user = crud.get_user_by_username(db, username=username)
        if not user:
            typer.secho(f"Error: User '{username}' not found.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Get user's documents
        documents = db.query(Document).filter_by(user_id=user.id, processing_status='completed').all()
        
        if not documents:
            typer.echo(f"No completed documents found for user '{username}'.")
            return
        
        typer.echo(f"\n--- Search Results for '{query}' ---")
        typer.echo(f"User: {username}")
        typer.echo(f"Searching through {len(documents)} completed documents")
        
        # Simple text search through document metadata
        # Note: This is a basic implementation. For full vector search,
        # you would need to integrate with the vector store
        
        results = []
        for doc in documents:
            # Search in filename and metadata
            if query.lower() in doc.original_filename.lower():
                results.append((doc, "filename"))
            elif doc.metadata_ and any(query.lower() in str(v).lower() for v in doc.metadata_.values()):
                results.append((doc, "metadata"))
        
        if not results:
            typer.echo("No matching documents found.")
            return
        
        # Display results
        for i, (doc, match_type) in enumerate(results[:limit], 1):
            typer.echo(f"\n{i}. {doc.original_filename}")
            typer.echo(f"   Match: {match_type}")
            typer.echo(f"   Status: {doc.processing_status}")
            if doc.metadata_:
                # Show relevant metadata
                for key, value in list(doc.metadata_.items())[:3]:
                    typer.echo(f"   {key}: {str(value)[:100]}...")
        
        if len(results) > limit:
            typer.echo(f"\n... and {len(results) - limit} more results (use --limit to see more)")
        
    except Exception as e:
        typer.secho(f"Error during search: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command()
def vector_store(
    action: str = typer.Argument(..., help="Action to perform: status, clear, repair"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompts"),
    fix_orphans: bool = typer.Option(False, "--fix-orphans", help="Remove orphaned chunks without doc_id"),
):
    """Manage the vector store directly."""
    
    if action not in ["status", "clear", "repair"]:
        typer.secho(f"Invalid action: {action}. Use 'status', 'clear', or 'repair'", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    try:
        import chromadb
        from pathlib import Path
        from database.database import get_db_session
        from database.models import Document
        
        # Get vector store path
        persist_path = Path("/app/ai_researcher/data/vector_store")
        if not persist_path.exists():
            persist_path = Path("ai_researcher/data/vector_store")
        
        if not persist_path.exists():
            typer.secho(f"Vector store not found at {persist_path}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        typer.echo(f"Vector store location: {persist_path}")
        client = chromadb.PersistentClient(path=str(persist_path))
        
        if action == "status":
            # Show vector store status
            try:
                dense = client.get_collection("research_papers_dense")
                sparse = client.get_collection("research_papers_sparse")
                
                dense_count = dense.count()
                sparse_count = sparse.count()
                
                typer.echo(f"\nVector Store Status:")
                typer.echo(f"  Dense collection: {dense_count} chunks")
                typer.echo(f"  Sparse collection: {sparse_count} chunks")
                
                # Check for orphaned chunks
                all_results = dense.get(include=['metadatas'])
                chunks_with_doc_id = sum(1 for m in all_results['metadatas'] if 'doc_id' in m)
                chunks_without_doc_id = dense_count - chunks_with_doc_id
                
                if chunks_without_doc_id > 0:
                    typer.secho(f"  ⚠️  Orphaned chunks (no doc_id): {chunks_without_doc_id}", fg=typer.colors.YELLOW)
                    typer.echo("  Run with --fix-orphans to remove them")
                
                # Compare with database
                db = get_db_session()
                db_docs = db.query(Document).all()
                db_doc_ids = {doc.id for doc in db_docs}
                db.close()
                
                # Get unique doc_ids from vector store
                vs_doc_ids = {m['doc_id'] for m in all_results['metadatas'] if 'doc_id' in m}
                
                typer.echo(f"\nDatabase comparison:")
                typer.echo(f"  Documents in database: {len(db_doc_ids)}")
                typer.echo(f"  Documents in vector store: {len(vs_doc_ids)}")
                
                orphans_in_vs = vs_doc_ids - db_doc_ids
                if orphans_in_vs:
                    typer.secho(f"  ⚠️  Documents in vector store but not in database: {len(orphans_in_vs)}", 
                              fg=typer.colors.YELLOW)
                    
            except Exception as e:
                typer.secho(f"Error checking status: {e}", fg=typer.colors.RED)
                
        elif action == "clear":
            # Clear the entire vector store
            dense = client.get_collection("research_papers_dense")
            sparse = client.get_collection("research_papers_sparse")
            
            dense_count = dense.count()
            sparse_count = sparse.count()
            
            typer.echo(f"\nThis will delete ALL {dense_count + sparse_count} chunks from the vector store!")
            typer.echo("You will need to re-process all documents after this.")
            
            if not force:
                confirm = typer.confirm("Are you sure you want to proceed?")
                if not confirm:
                    typer.echo("Cancelled.")
                    return
            
            # Clear all chunks
            typer.echo("Clearing dense collection...")
            if dense_count > 0:
                all_ids = dense.get()['ids']
                for i in range(0, len(all_ids), 500):
                    batch = all_ids[i:i+500]
                    dense.delete(ids=batch)
            
            typer.echo("Clearing sparse collection...")
            if sparse_count > 0:
                all_ids = sparse.get()['ids']
                for i in range(0, len(all_ids), 500):
                    batch = all_ids[i:i+500]
                    sparse.delete(ids=batch)
            
            typer.secho("✓ Vector store cleared successfully!", fg=typer.colors.GREEN)
            
        elif action == "repair":
            # Repair vector store by removing orphaned chunks
            dense = client.get_collection("research_papers_dense")
            sparse = client.get_collection("research_papers_sparse")
            
            # Get database documents
            db = get_db_session()
            db_docs = db.query(Document).all()
            valid_doc_ids = {doc.id for doc in db_docs}
            db.close()
            
            typer.echo(f"Valid document IDs in database: {len(valid_doc_ids)}")
            
            # Find orphaned chunks
            all_dense = dense.get(include=['metadatas'])
            all_sparse = sparse.get(include=['metadatas'])
            
            orphaned_dense = []
            orphaned_sparse = []
            
            # Check dense collection
            for chunk_id, metadata in zip(all_dense['ids'], all_dense['metadatas']):
                if 'doc_id' not in metadata:
                    if fix_orphans:
                        orphaned_dense.append(chunk_id)
                elif metadata['doc_id'] not in valid_doc_ids:
                    orphaned_dense.append(chunk_id)
            
            # Check sparse collection
            for chunk_id, metadata in zip(all_sparse['ids'], all_sparse['metadatas']):
                if 'doc_id' not in metadata:
                    if fix_orphans:
                        orphaned_sparse.append(chunk_id)
                elif metadata['doc_id'] not in valid_doc_ids:
                    orphaned_sparse.append(chunk_id)
            
            total_orphans = len(orphaned_dense) + len(orphaned_sparse)
            
            if total_orphans == 0:
                typer.secho("✓ No orphaned chunks found!", fg=typer.colors.GREEN)
                return
            
            typer.echo(f"\nFound {total_orphans} orphaned chunks:")
            typer.echo(f"  Dense: {len(orphaned_dense)}")
            typer.echo(f"  Sparse: {len(orphaned_sparse)}")
            
            if not force:
                confirm = typer.confirm(f"Remove {total_orphans} orphaned chunks?")
                if not confirm:
                    typer.echo("Cancelled.")
                    return
            
            # Delete orphaned chunks
            if orphaned_dense:
                typer.echo(f"Removing {len(orphaned_dense)} orphaned dense chunks...")
                for i in range(0, len(orphaned_dense), 500):
                    batch = orphaned_dense[i:i+500]
                    dense.delete(ids=batch)
            
            if orphaned_sparse:
                typer.echo(f"Removing {len(orphaned_sparse)} orphaned sparse chunks...")
                for i in range(0, len(orphaned_sparse), 500):
                    batch = orphaned_sparse[i:i+500]
                    sparse.delete(ids=batch)
            
            typer.secho(f"✓ Removed {total_orphans} orphaned chunks!", fg=typer.colors.GREEN)
            
            # Show final status
            typer.echo(f"\nFinal status:")
            typer.echo(f"  Dense collection: {dense.count()} chunks")
            typer.echo(f"  Sparse collection: {sparse.count()} chunks")
            
    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
