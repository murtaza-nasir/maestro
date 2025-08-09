#!/usr/bin/env python3
"""
Database Reset Script for Maestro Application

This script safely resets ALL databases and storage systems to maintain data consistency.

IMPORTANT: All databases MUST be reset together because they are tightly coupled:
- Main DB tracks document records and processing status
- AI DB stores extracted metadata for the same documents
- Vector Store contains embeddings for the same documents
- Files on disk correspond to database records

Database Locations:
- Main DB: maestro_backend/data/maestro.db
- AI DB: When created, will be at ai_researcher/data/processed/metadata.db or /app/ai_researcher/data/processed/metadata.db (Docker)
- Vector Store: When created, will be at ai_researcher/data/vector_store or /app/ai_researcher/data/vector_store (Docker)
- Documents: ai_researcher/data/raw_pdfs and ai_researcher/data/processed/

Usage:
    python reset_databases.py           # Interactive mode with confirmation
    python reset_databases.py --backup  # Create backups before reset
    python reset_databases.py --force   # Skip confirmation (DANGEROUS!)
    python reset_databases.py --stats   # Show current statistics only
    python reset_databases.py --check   # Check data consistency
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime
import sqlite3
import json

# Color codes for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_colored(message, color=Colors.WHITE):
    """Print colored message to terminal."""
    print(f"{color}{message}{Colors.RESET}")

def print_header(message):
    """Print a formatted header."""
    print()
    print_colored("=" * 60, Colors.CYAN)
    print_colored(message, Colors.CYAN + Colors.BOLD)
    print_colored("=" * 60, Colors.CYAN)
    print()

def confirm_action(message, force=False):
    """Ask for user confirmation unless force flag is set."""
    if force:
        return True
    
    print_colored(f"\n{Colors.YELLOW}⚠️  WARNING: {message}{Colors.RESET}")
    print_colored("This will reset ALL databases to maintain consistency:", Colors.YELLOW)
    print_colored("  • Main application database (users, chats, documents)", Colors.YELLOW)
    print_colored("  • AI researcher database (extracted metadata)", Colors.YELLOW)
    print_colored("  • ChromaDB vector store (embeddings and chunks)", Colors.YELLOW)
    print_colored("  • All document files (PDFs, markdown, metadata)", Colors.YELLOW)
    print()
    response = input(f"{Colors.BOLD}Are you sure? Type 'yes' to confirm: {Colors.RESET}")
    return response.lower() == 'yes'

def create_backup(file_path, backup_dir="backups"):
    """Create a backup of a file or directory."""
    if not os.path.exists(file_path):
        return None
    
    # Create backup directory
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = Path(file_path).name
    backup_file = backup_path / f"{file_name}.{timestamp}.backup"
    
    try:
        if os.path.isfile(file_path):
            shutil.copy2(file_path, backup_file)
        else:
            backup_file = backup_path / f"{file_name}_{timestamp}_backup"
            shutil.copytree(file_path, backup_file)
        
        print_colored(f"✓ Backup created: {backup_file}", Colors.GREEN)
        return backup_file
    except Exception as e:
        print_colored(f"✗ Backup failed for {file_path}: {e}", Colors.RED)
        return None

def get_database_locations():
    """Get all possible database locations based on environment."""
    locations = {
        'main_db': [
            Path("maestro_backend/data/maestro.db"),  # Local development
            Path("data/maestro.db"),  # Alternative local
        ],
        'ai_db': [
            Path("ai_researcher/data/processed/metadata.db"),  # Local (when created)
            Path("maestro_backend/ai_researcher/data/processed/metadata.db"),  # Alternative local
            Path("/app/ai_researcher/data/processed/metadata.db"),  # Docker container
        ],
        'vector_store': [
            Path("ai_researcher/data/vector_store"),  # Local (when created)
            Path("maestro_backend/ai_researcher/data/vector_store"),  # Alternative local
            Path("/app/ai_researcher/data/vector_store"),  # Docker container
        ],
        'pdf_dir': [
            Path("ai_researcher/data/raw_pdfs"),  # Local (when created)
            Path("maestro_backend/ai_researcher/data/raw_pdfs"),  # Alternative local
            Path("/app/ai_researcher/data/raw_pdfs"),  # Docker container
        ],
        'markdown_dir': [
            Path("ai_researcher/data/processed/markdown"),  # Local (when created)
            Path("maestro_backend/ai_researcher/data/processed/markdown"),  # Alternative local
            Path("/app/ai_researcher/data/processed/markdown"),  # Docker container
        ],
        'metadata_dir': [
            Path("ai_researcher/data/processed/metadata"),  # Local (when created)
            Path("maestro_backend/ai_researcher/data/processed/metadata"),  # Alternative local
            Path("/app/ai_researcher/data/processed/metadata"),  # Docker container
        ]
    }
    return locations

def find_existing_path(paths):
    """Find the first existing path from a list of possible paths."""
    for path in paths:
        if path.exists():
            return path
    return None

def reset_main_database(backup=False):
    """Reset the main application database."""
    print_colored("Resetting main application database...", Colors.BLUE)
    
    locations = get_database_locations()
    db_path = find_existing_path(locations['main_db'])
    
    if db_path:
        if backup:
            create_backup(db_path)
        
        # Remove the database file
        os.remove(db_path)
        print_colored(f"✓ Removed: {db_path}", Colors.GREEN)
    else:
        print_colored(f"ℹ Main database not found at:", Colors.YELLOW)
        for path in locations['main_db']:
            print_colored(f"    • {path}", Colors.YELLOW)
    
    # Run migrations to recreate the database
    print_colored("Running migrations to recreate database...", Colors.BLUE)
    try:
        # Change to backend directory to run migrations
        os.chdir("maestro_backend")
        from database.migrations.run_migrations import run_all_migrations
        from database.database import engine
        
        run_all_migrations(engine)
        os.chdir("..")
        print_colored("✓ Main database recreated with fresh schema", Colors.GREEN)
    except Exception as e:
        os.chdir("..")
        print_colored(f"✗ Failed to run migrations: {e}", Colors.RED)
        print_colored("You may need to run migrations manually from maestro_backend directory", Colors.YELLOW)

def reset_ai_database(backup=False):
    """Reset the AI researcher database."""
    print_colored("Resetting AI researcher database...", Colors.BLUE)
    
    locations = get_database_locations()
    db_path = find_existing_path(locations['ai_db'])
    
    if db_path:
        if backup:
            create_backup(db_path)
        
        os.remove(db_path)
        print_colored(f"✓ Removed: {db_path}", Colors.GREEN)
    else:
        print_colored("ℹ AI researcher database not found (will be created when first document is processed)", Colors.CYAN)
        print_colored("  Expected locations:", Colors.CYAN)
        for path in locations['ai_db']:
            print_colored(f"    • {path}", Colors.CYAN)
    
    print_colored("✓ AI researcher database will be recreated on first use", Colors.GREEN)

def reset_vector_store(backup=False):
    """Reset the ChromaDB vector store."""
    print_colored("Resetting ChromaDB vector store...", Colors.BLUE)
    
    locations = get_database_locations()
    vector_path = find_existing_path(locations['vector_store'])
    
    if vector_path:
        if backup:
            create_backup(vector_path)
        
        shutil.rmtree(vector_path)
        print_colored(f"✓ Removed: {vector_path}", Colors.GREEN)
    else:
        print_colored("ℹ Vector store not found (will be created when first document is processed)", Colors.CYAN)
        print_colored("  Expected locations:", Colors.CYAN)
        for path in locations['vector_store']:
            print_colored(f"    • {path}", Colors.CYAN)
    
    print_colored("✓ Vector store will be recreated on first use", Colors.GREEN)

def clear_document_files(backup=False):
    """Clear all document files (PDFs, markdown, metadata)."""
    print_colored("Clearing document files...", Colors.BLUE)
    
    locations = get_database_locations()
    
    # Clear each type of document directory
    for dir_type in ['pdf_dir', 'markdown_dir', 'metadata_dir']:
        dir_path = find_existing_path(locations[dir_type])
        
        if dir_path:
            if backup:
                create_backup(dir_path)
            
            # Clear directory contents but keep the directory
            for item in dir_path.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            
            print_colored(f"✓ Cleared: {dir_path}", Colors.GREEN)
        else:
            print_colored(f"ℹ {dir_type.replace('_', ' ').title()} not found", Colors.CYAN)
    
    print_colored("✓ Document files cleared", Colors.GREEN)

def show_database_stats():
    """Show current database statistics."""
    print_header("Current Database Statistics")
    
    locations = get_database_locations()
    
    # Check main database
    db_path = find_existing_path(locations['main_db'])
    
    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get table counts
            tables = [
                ('users', 'Users'),
                ('documents', 'Documents'),
                ('chats', 'Chats'),
                ('messages', 'Messages'),
                ('document_groups', 'Document Groups')
            ]
            
            print_colored(f"Main Database: {db_path}", Colors.CYAN)
            for table, name in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"  • {name}: {count}")
                except:
                    pass
            
            conn.close()
            
            # Show file size
            size_mb = db_path.stat().st_size / (1024 * 1024)
            print(f"  • Size: {size_mb:.2f} MB")
        except Exception as e:
            print_colored(f"Could not read main database: {e}", Colors.YELLOW)
    else:
        print_colored("Main database not found", Colors.YELLOW)
        print_colored("  Expected at:", Colors.YELLOW)
        for path in locations['main_db']:
            print_colored(f"    • {path}", Colors.YELLOW)
    
    print()
    
    # Check AI researcher database
    ai_db_path = find_existing_path(locations['ai_db'])
    
    if ai_db_path:
        try:
            conn = sqlite3.connect(ai_db_path)
            cursor = conn.cursor()
            
            print_colored(f"AI Researcher Database: {ai_db_path}", Colors.CYAN)
            cursor.execute("SELECT COUNT(*) FROM processed_documents")
            count = cursor.fetchone()[0]
            print(f"  • Processed Documents: {count}")
            
            conn.close()
            
            # Show file size
            size_mb = ai_db_path.stat().st_size / (1024 * 1024)
            print(f"  • Size: {size_mb:.2f} MB")
        except Exception as e:
            print_colored(f"Could not read AI database: {e}", Colors.YELLOW)
    else:
        print_colored("AI researcher database not found (not yet created)", Colors.CYAN)
    
    print()
    
    # Check vector store
    vector_path = find_existing_path(locations['vector_store'])
    
    if vector_path:
        print_colored(f"Vector Store (ChromaDB): {vector_path}", Colors.CYAN)
        # Count subdirectories and files
        subdirs = list(vector_path.iterdir())
        print(f"  • Collections: {len([d for d in subdirs if d.is_dir()])}")
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in vector_path.rglob('*') if f.is_file())
        size_mb = total_size / (1024 * 1024)
        print(f"  • Size: {size_mb:.2f} MB")
    else:
        print_colored("Vector store not found (not yet created)", Colors.CYAN)
    
    print()

def check_data_consistency():
    """Check for potential data inconsistencies across databases."""
    print_header("Data Consistency Check")
    
    locations = get_database_locations()
    issues = []
    
    # Get document IDs from main database
    main_docs = set()
    db_path = find_existing_path(locations['main_db'])
    
    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM documents WHERE processing_status = 'completed'")
            main_docs = {row[0] for row in cursor.fetchall()}
            conn.close()
            print(f"Main DB: {len(main_docs)} completed documents")
        except Exception as e:
            issues.append(f"Could not read main database: {e}")
    else:
        print_colored("Main database not found", Colors.YELLOW)
    
    # Get document IDs from AI researcher database
    ai_docs = set()
    ai_db_path = find_existing_path(locations['ai_db'])
    
    if ai_db_path:
        try:
            conn = sqlite3.connect(ai_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id FROM processed_documents")
            ai_docs = {row[0] for row in cursor.fetchall()}
            conn.close()
            print(f"AI DB: {len(ai_docs)} processed documents")
        except Exception as e:
            issues.append(f"Could not read AI database: {e}")
    else:
        print_colored("AI researcher database not found (not yet created)", Colors.CYAN)
    
    # Check for mismatches - any difference indicates inconsistency
    if main_docs or ai_docs:  # If either database has documents
        only_in_main = main_docs - ai_docs
        only_in_ai = ai_docs - main_docs
        
        if only_in_main:
            issues.append(f"{len(only_in_main)} documents in main DB but not in AI DB")
            print_colored(f"⚠️  Documents only in main DB: {list(only_in_main)[:5]}{'...' if len(only_in_main) > 5 else ''}", Colors.YELLOW)
        
        if only_in_ai:
            issues.append(f"{len(only_in_ai)} documents in AI DB but not in main DB")
            print_colored(f"⚠️  Documents only in AI DB: {list(only_in_ai)[:5]}{'...' if len(only_in_ai) > 5 else ''}", Colors.YELLOW)
        
        # Check for count mismatch even if no document details available
        if len(main_docs) != len(ai_docs):
            count_issue = f"Document count mismatch: Main DB has {len(main_docs)}, AI DB has {len(ai_docs)}"
            if count_issue not in [issue for issue in issues if "count mismatch" in issue.lower()]:
                issues.append(count_issue)
        
        if not only_in_main and not only_in_ai and main_docs and ai_docs and len(main_docs) == len(ai_docs):
            print_colored("✓ Databases are synchronized", Colors.GREEN)
    
    if issues:
        print()
        print_colored("⚠️  Data inconsistencies detected:", Colors.YELLOW)
        for issue in issues:
            print_colored(f"  • {issue}", Colors.YELLOW)
        print()
        print_colored("These inconsistencies will be resolved by resetting all databases.", Colors.CYAN)
    elif main_docs or ai_docs:
        print_colored("✓ No data inconsistencies detected", Colors.GREEN)
    else:
        print_colored("\nℹ️  Status:", Colors.CYAN)
        if not db_path and not ai_db_path:
            print_colored("  • No databases found - system appears to be clean", Colors.CYAN)
        elif not main_docs and not ai_docs:
            print_colored("  • Databases exist but contain no documents", Colors.CYAN)
        print_colored("  • This is normal for a fresh installation", Colors.CYAN)
    
    print()

def reset_all_databases(backup=False):
    """Reset all databases and files to maintain consistency."""
    print_header("Resetting All Databases and Files")
    
    print_colored("📊 Data Synchronization Notice:", Colors.CYAN + Colors.BOLD)
    print_colored("All databases must be reset together to maintain data consistency.", Colors.CYAN)
    print_colored("The system relies on synchronized data across:", Colors.CYAN)
    print_colored("  1. Main DB ← → AI DB (document metadata)", Colors.CYAN)
    print_colored("  2. AI DB ← → Vector Store (embeddings match metadata)", Colors.CYAN)
    print_colored("  3. All DBs ← → File System (files match records)", Colors.CYAN)
    print()
    
    # Reset everything in the correct order
    reset_main_database(backup)
    reset_ai_database(backup)
    reset_vector_store(backup)
    clear_document_files(backup)
    
    print()
    print_colored("✓ All databases and files have been reset", Colors.GREEN)
    print_colored("✓ Data consistency maintained", Colors.GREEN)

def main():
    parser = argparse.ArgumentParser(
        description='Reset ALL Maestro databases to maintain data consistency',
        epilog='Note: Selective reset is not available to prevent data inconsistencies.'
    )
    parser.add_argument('--backup', action='store_true', 
                       help='Create backups before reset')
    parser.add_argument('--force', action='store_true', 
                       help='Skip confirmation prompts (DANGEROUS!)')
    parser.add_argument('--stats', action='store_true', 
                       help='Show database statistics only')
    parser.add_argument('--check', action='store_true',
                       help='Check data consistency across databases')
    
    args = parser.parse_args()
    
    # Show header
    print_header("Maestro Database Reset Tool")
    
    # If only stats requested, show and exit
    if args.stats:
        show_database_stats()
        return
    
    # If consistency check requested
    if args.check:
        check_data_consistency()
        return
    
    # Show current stats and check consistency before reset
    show_database_stats()
    check_data_consistency()
    
    # Confirm the complete reset
    message = "This will DELETE ALL DATABASES and document files!"
    if not confirm_action(message, args.force):
        print_colored("Operation cancelled", Colors.YELLOW)
        return
    
    # Perform complete reset
    reset_all_databases(args.backup)
    
    print_header("Reset Complete")
    print_colored("ℹ️  Next steps:", Colors.CYAN)
    print_colored("  1. Restart the application", Colors.CYAN)
    print_colored("  2. Re-upload any documents you need", Colors.CYAN)
    print_colored("  3. Documents will be processed and synchronized across all databases", Colors.CYAN)
    
    if args.backup:
        print()
        print_colored(f"ℹ️  Backups saved in: ./backups/", Colors.CYAN)
        print_colored("  You can restore from backups if needed", Colors.CYAN)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_colored("\n\nOperation cancelled by user", Colors.YELLOW)
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n✗ Error: {e}", Colors.RED)
        import traceback
        traceback.print_exc()
        sys.exit(1)