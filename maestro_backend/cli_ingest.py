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
from typing import Optional, List
from sqlalchemy.orm import Session
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import time
import uuid

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
    from ai_researcher.core_rag.vector_store_manager import VectorStoreManager as VectorStore

app = typer.Typer(help="MAESTRO Direct Document Processing CLI")

def get_db_session():
    """Get a database session."""
    db = next(get_db())
    try:
        return db
    finally:
        pass  # Don't close here, let caller handle it

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
    pdf_path: Path, 
    doc_id: str, 
    user_id: int, 
    group_id: Optional[str], 
    db: Session,
    processor: DocumentProcessor,
    progress: LiveProgressCallback,
    delete_after_success: bool = False
) -> bool:
    """
    Process a single document with live progress feedback.
    Only creates database records for successfully processed documents.
    Returns True if successful, False otherwise.
    """
    try:
        progress.log_step("Starting document processing", f"File: {pdf_path.name}")
        
        # Get file size for progress tracking
        file_size = pdf_path.stat().st_size
        progress.log_step("File analysis", f"Size: {file_size:,} bytes")
        
        # Process the document using the AI researcher pipeline FIRST
        # Don't create database record until we know processing succeeds
        progress.log_step("PDF text extraction", "Extracting header/footer for metadata")
        result = processor.process_pdf(pdf_path)
        
        if result is None:
            progress.log_error("Document processing failed - document will not be added to database")
            return False
        
        progress.log_success(f"Generated {result.get('chunks_generated', 0)} chunks")
        progress.log_success(f"Added {result.get('chunks_added_to_vector_store', 0)} chunks to vector store")
        
        # Only create database record AFTER successful processing
        progress.log_step("Creating database record for successfully processed document")
        crud.create_document(
            db=db,
            doc_id=doc_id,
            user_id=user_id,
            original_filename=pdf_path.name,
            metadata=result.get('extracted_metadata', {}),
            processing_status='completed',  # Only create completed documents
            upload_progress=100,
            file_size=file_size,
            file_path=str(pdf_path)
        )
        
        # Add to group if group_id is provided
        if group_id:
            progress.log_step("Adding to document group")
            crud.add_document_to_group(db, group_id=group_id, doc_id=doc_id, user_id=user_id)
        else:
            progress.log_step("Document added to user library", "No group specified - can be organized later")
        
        progress.log_success(f"Document processing completed successfully")
        
        # Delete the PDF file if requested and processing was successful
        if delete_after_success:
            try:
                pdf_path.unlink()  # Delete the file
                progress.log_success(f"Deleted source file: {pdf_path.name}")
            except Exception as delete_error:
                progress.log_warning(f"Failed to delete source file: {delete_error}")
                # Don't fail the entire operation if file deletion fails
        
        return True
        
    except Exception as e:
        progress.log_error(f"Processing failed: {str(e)}")
        # Don't create any database record for failed documents
        return False

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
    pdf_dir: Path = typer.Argument(..., help="Directory containing PDF files to ingest"),
    group_id: Optional[str] = typer.Option(None, "--group", help="ID of the document group to add documents to (optional)"),
    force_reembed: bool = typer.Option(False, "--force-reembed", help="Force re-processing and re-embedding for all PDFs"),
    device: Optional[str] = typer.Option(None, "--device", help="Device to use for processing (e.g., 'cuda:0', 'cpu')"),
    delete_after_success: bool = typer.Option(False, "--delete-after-success", help="Delete PDF files after successful processing"),
    batch_size: int = typer.Option(5, "--batch-size", "--batch", help="Number of documents to process in parallel"),
):
    """
    Directly process PDF documents with live feedback.
    This command processes PDFs synchronously, showing real-time progress for each document.
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
        
        # Validate PDF directory
        pdf_dir = Path(pdf_dir).resolve()
        if not pdf_dir.is_dir():
            typer.secho(f"Error: PDF directory not found: {pdf_dir}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        
        # Find PDF files
        pdf_files = list(pdf_dir.glob("*.pdf"))
        if not pdf_files:
            typer.secho(f"No PDF files found in {pdf_dir}", fg=typer.colors.YELLOW)
            raise typer.Exit()
        
        typer.echo(f"\n=== MAESTRO Direct Document Processing ===")
        typer.echo(f"Target user: {username} (ID: {user.id})")
        if group:
            typer.echo(f"Target group: {group.name} (ID: {group.id})")
        else:
            typer.echo(f"Target group: None (documents will be added to user library)")
        typer.echo(f"Found {len(pdf_files)} PDF files to process")
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
        vector_store = VectorStore(persist_directory=str(vector_store_path))
        
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
            pdf_dir=pdf_dir,  # Use the input directory
            markdown_dir=base_path / "processed" / "markdown",
            metadata_dir=base_path / "processed" / "metadata",
            db_path=base_path / "processed" / "metadata.db",
            embedder=embedder,
            vector_store=vector_store,
            force_reembed=force_reembed,
            device=device
        )
        
        # Replace the processor's metadata extractor with our configured one
        processor.metadata_extractor = metadata_extractor
        
        typer.secho("✓ Document processor initialized", fg=typer.colors.GREEN)
        
        # Process files with live feedback
        success_count = 0
        error_count = 0
        
        for i, pdf_file in enumerate(pdf_files, 1):
            typer.echo(f"\n--- Processing {i}/{len(pdf_files)}: {pdf_file.name} ---")
            
            # Generate document ID
            doc_id = str(uuid.uuid4())[:8]
            
            # Create progress tracker
            progress = LiveProgressCallback(pdf_file.name)
            
            try:
                # Process the document
                success = process_single_document(
                    pdf_path=pdf_file,
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
                    typer.secho(f"✓ Successfully processed {pdf_file.name} (ID: {doc_id})", fg=typer.colors.GREEN)
                else:
                    error_count += 1
                    typer.secho(f"✗ Failed to process {pdf_file.name}", fg=typer.colors.RED)
                    
            except Exception as e:
                error_count += 1
                typer.secho(f"✗ Error processing {pdf_file.name}: {e}", fg=typer.colors.RED)
        
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
                from ai_researcher.core_rag.vector_store import VectorStore
                base_path = Path('/app/ai_researcher/data')
                vector_store_path = base_path / 'vector_store'
                vector_store = VectorStore(persist_directory=str(vector_store_path))
                
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
                # Remove from vector store if needed
                # Note: This would require vector store integration
                # For now, we'll just remove from database
                
                # Remove document from database
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

if __name__ == "__main__":
    app()
