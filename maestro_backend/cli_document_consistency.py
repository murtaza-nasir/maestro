#!/usr/bin/env python3
"""
CLI Tool for Document Consistency Management

This tool provides commands to check and fix document consistency issues
across all storage systems in the Maestro application.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any
import logging

# Add the parent directory to the path so we can import from the project
sys.path.insert(0, str(Path(__file__).parent))

from database.database import get_db
from database import crud
from database.crud_documents_improved import (
    check_document_consistency,
    cleanup_all_user_orphans, 
    get_document_processing_stats,
    consistency_manager
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
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

async def cmd_check_document(doc_id: str, user_id: int):
    """Check consistency for a specific document."""
    print_header(f"Document Consistency Check: {doc_id}")
    
    db = next(get_db())
    try:
        consistency_report = check_document_consistency(db, doc_id, user_id)
        
        print_colored(f"Document ID: {consistency_report['doc_id']}", Colors.BOLD)
        print_colored(f"Status: {consistency_report['status']}", Colors.BOLD)
        print()
        
        print_colored("Storage System Presence:", Colors.CYAN)
        exists = consistency_report['exists_in']
        for system, present in exists.items():
            status_color = Colors.GREEN if present else Colors.RED
            status_text = "✓" if present else "✗"
            system_name = system.replace('_', ' ').title()
            print_colored(f"  {status_text} {system_name}: {present}", status_color)
        
        print()
        
        if consistency_report['is_consistent']:
            print_colored("✓ Document is consistent across all systems", Colors.GREEN)
        else:
            print_colored("⚠️  Consistency issues found:", Colors.YELLOW)
            for issue in consistency_report['issues']:
                print_colored(f"  • {issue}", Colors.RED)
            
            print()
            print_colored("Recommended action: Run cleanup command", Colors.CYAN)
            print_colored(f"  python cli_document_consistency.py cleanup-document {doc_id} {user_id}", Colors.CYAN)
        
    except Exception as e:
        print_colored(f"Error checking document consistency: {e}", Colors.RED)
    finally:
        db.close()

async def cmd_cleanup_document(doc_id: str, user_id: int):
    """Clean up a specific document."""
    print_header(f"Cleaning Up Document: {doc_id}")
    
    db = next(get_db())
    try:
        # First show what will be cleaned up
        print_colored("Checking current state...", Colors.BLUE)
        consistency_report = check_document_consistency(db, doc_id, user_id)
        
        if consistency_report['is_consistent']:
            print_colored("Document is already consistent. No cleanup needed.", Colors.GREEN)
            return
        
        print_colored("Issues found:", Colors.YELLOW)
        for issue in consistency_report['issues']:
            print_colored(f"  • {issue}", Colors.YELLOW)
        
        print()
        print_colored("Performing cleanup...", Colors.BLUE)
        
        # Import the cleanup function from improved CRUD
        from database.crud_documents_improved import cleanup_failed_document
        success = await cleanup_failed_document(db, doc_id, user_id)
        
        if success:
            print_colored("✓ Document cleanup completed successfully", Colors.GREEN)
            
            # Verify cleanup
            print_colored("Verifying cleanup...", Colors.BLUE)
            updated_report = check_document_consistency(db, doc_id, user_id)
            if updated_report['is_consistent']:
                print_colored("✓ Document is now consistent", Colors.GREEN)
            else:
                print_colored("⚠️  Some issues may remain:", Colors.YELLOW)
                for issue in updated_report['issues']:
                    print_colored(f"  • {issue}", Colors.YELLOW)
        else:
            print_colored("✗ Document cleanup encountered errors", Colors.RED)
        
    except Exception as e:
        print_colored(f"Error cleaning up document: {e}", Colors.RED)
    finally:
        db.close()

async def cmd_check_user(user_id: int):
    """Check all documents for a user."""
    print_header(f"User Document Analysis: {user_id}")
    
    db = next(get_db())
    try:
        # Get user info
        user = crud.get_user(db, user_id)
        if not user:
            print_colored(f"User {user_id} not found", Colors.RED)
            return
        
        print_colored(f"User: {user.username} (ID: {user_id})", Colors.BOLD)
        print()
        
        # Get processing stats
        print_colored("Analyzing documents...", Colors.BLUE)
        stats = get_document_processing_stats(db, user_id)
        
        if 'error' in stats:
            print_colored(f"Error getting stats: {stats['error']}", Colors.RED)
            return
        
        # Display summary
        print_colored("Document Summary:", Colors.CYAN)
        print(f"  Total Documents: {stats['total_documents']}")
        
        print("\n  By Status:")
        for status, count in stats['by_status'].items():
            print(f"    {status}: {count}")
        
        print(f"\n  Consistency Issues: {stats['consistency_issues']}")
        
        # Storage usage
        storage = stats.get('storage_usage', {})
        print_colored("\nStorage System Usage:", Colors.CYAN)
        print(f"  Main Database Records: {storage.get('main_db_records', 'N/A')}")
        print(f"  AI Database Records: {storage.get('ai_db_records', 'N/A')}")
        print(f"  Vector Store Chunks: {storage.get('vector_store_chunks', 'N/A')}")
        
        # Show inconsistent documents
        if stats['consistency_issues'] > 0:
            print_colored("\nInconsistent Documents:", Colors.YELLOW)
            for doc_info in stats.get('inconsistent_documents', []):
                print_colored(f"  • {doc_info['doc_id']} - {doc_info['filename']}", Colors.YELLOW)
                for issue in doc_info['issues']:
                    print_colored(f"    - {issue}", Colors.RED)
            
            print()
            print_colored("Recommended action: Run cleanup for this user", Colors.CYAN)
            print_colored(f"  python cli_document_consistency.py cleanup-user {user_id}", Colors.CYAN)
        else:
            print_colored("\n✓ All documents are consistent", Colors.GREEN)
        
    except Exception as e:
        print_colored(f"Error checking user documents: {e}", Colors.RED)
    finally:
        db.close()

async def cmd_cleanup_user(user_id: int):
    """Clean up all orphaned documents for a user."""
    print_header(f"User Cleanup: {user_id}")
    
    db = next(get_db())
    try:
        # Get user info
        user = crud.get_user(db, user_id)
        if not user:
            print_colored(f"User {user_id} not found", Colors.RED)
            return
        
        print_colored(f"Cleaning up documents for user: {user.username}", Colors.BOLD)
        print()
        
        # Perform cleanup
        print_colored("Analyzing and cleaning up orphaned documents...", Colors.BLUE)
        result = await cleanup_all_user_orphans(db, user_id)
        
        if 'error' in result:
            print_colored(f"Error during cleanup: {result['error']}", Colors.RED)
            return
        
        # Display results
        orphans_found = result['orphans_found']
        cleanup_performed = result['cleanup_performed']
        
        print_colored("Orphaned Documents Found:", Colors.CYAN)
        for category, items in orphans_found.items():
            if items:
                category_name = category.replace('_', ' ').title()
                print_colored(f"  {category_name}: {len(items)}", Colors.YELLOW)
                for item in items[:5]:  # Show first 5
                    print(f"    - {item}")
                if len(items) > 5:
                    print(f"    ... and {len(items) - 5} more")
        
        print_colored("\nCleanup Actions Performed:", Colors.CYAN)
        for action, count in cleanup_performed.items():
            if count > 0:
                action_name = action.replace('_', ' ').title()
                print_colored(f"  {action_name}: {count}", Colors.GREEN)
        
        total_resolved = result['total_issues_resolved']
        if total_resolved > 0:
            print_colored(f"\n✓ Successfully resolved {total_resolved} consistency issues", Colors.GREEN)
        else:
            print_colored("\n✓ No cleanup was needed - all documents are consistent", Colors.GREEN)
        
    except Exception as e:
        print_colored(f"Error cleaning up user documents: {e}", Colors.RED)
    finally:
        db.close()

async def cmd_system_status():
    """Show overall system consistency status."""
    print_header("System Document Consistency Status")
    
    db = next(get_db())
    try:
        # Get all users
        users = crud.get_users(db, limit=1000)
        
        total_users = len(users)
        total_docs = 0
        total_issues = 0
        users_with_issues = 0
        
        print_colored("Scanning all users...", Colors.BLUE)
        
        for user in users:
            try:
                stats = get_document_processing_stats(db, user.id)
                if 'error' not in stats:
                    user_docs = stats['total_documents']
                    user_issues = stats['consistency_issues']
                    
                    total_docs += user_docs
                    total_issues += user_issues
                    
                    if user_issues > 0:
                        users_with_issues += 1
                        
                    print_colored(f"  {user.username}: {user_docs} docs, {user_issues} issues", 
                                Colors.YELLOW if user_issues > 0 else Colors.GREEN)
                
            except Exception as e:
                print_colored(f"  Error checking {user.username}: {e}", Colors.RED)
        
        print()
        print_colored("System Summary:", Colors.CYAN)
        print(f"  Total Users: {total_users}")
        print(f"  Total Documents: {total_docs}")
        print(f"  Users with Issues: {users_with_issues}")
        print_colored(f"  Total Consistency Issues: {total_issues}", 
                     Colors.RED if total_issues > 0 else Colors.GREEN)
        
        if total_issues > 0:
            print()
            print_colored("Recommended Actions:", Colors.CYAN)
            print_colored("1. Run cleanup for specific users with issues:", Colors.CYAN)
            print_colored("   python cli_document_consistency.py cleanup-user <user_id>", Colors.CYAN)
            print_colored("2. Or cleanup all users at once:", Colors.CYAN)
            print_colored("   python cli_document_consistency.py cleanup-all", Colors.CYAN)
        else:
            print_colored("\n✓ System is consistent - no issues found", Colors.GREEN)
        
    except Exception as e:
        print_colored(f"Error checking system status: {e}", Colors.RED)
    finally:
        db.close()

async def cmd_cleanup_all():
    """Clean up all users' orphaned documents."""
    print_header("System-Wide Cleanup")
    
    print_colored("⚠️  WARNING: This will clean up orphaned documents for ALL users", Colors.YELLOW)
    response = input("Continue? (y/N): ")
    if response.lower() != 'y':
        print_colored("Cancelled", Colors.YELLOW)
        return
    
    db = next(get_db())
    try:
        users = crud.get_users(db, limit=1000)
        
        total_resolved = 0
        
        for user in users:
            print_colored(f"\nCleaning up user: {user.username}", Colors.BLUE)
            
            try:
                result = await cleanup_all_user_orphans(db, user.id)
                user_resolved = result.get('total_issues_resolved', 0)
                total_resolved += user_resolved
                
                if user_resolved > 0:
                    print_colored(f"  Resolved {user_resolved} issues", Colors.GREEN)
                else:
                    print_colored("  No issues found", Colors.GREEN)
                    
            except Exception as e:
                print_colored(f"  Error: {e}", Colors.RED)
        
        print()
        print_colored(f"✓ System cleanup completed. Total issues resolved: {total_resolved}", Colors.GREEN)
        
    except Exception as e:
        print_colored(f"Error during system cleanup: {e}", Colors.RED)
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Document Consistency Management CLI')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Check document command
    check_doc_parser = subparsers.add_parser('check-document', help='Check consistency for a specific document')
    check_doc_parser.add_argument('doc_id', help='Document ID')
    check_doc_parser.add_argument('user_id', type=int, help='User ID')
    
    # Cleanup document command
    cleanup_doc_parser = subparsers.add_parser('cleanup-document', help='Clean up a specific document')
    cleanup_doc_parser.add_argument('doc_id', help='Document ID')
    cleanup_doc_parser.add_argument('user_id', type=int, help='User ID')
    
    # Check user command
    check_user_parser = subparsers.add_parser('check-user', help='Check all documents for a user')
    check_user_parser.add_argument('user_id', type=int, help='User ID')
    
    # Cleanup user command
    cleanup_user_parser = subparsers.add_parser('cleanup-user', help='Clean up all orphaned documents for a user')
    cleanup_user_parser.add_argument('user_id', type=int, help='User ID')
    
    # System status command
    subparsers.add_parser('system-status', help='Show overall system consistency status')
    
    # Cleanup all command
    subparsers.add_parser('cleanup-all', help='Clean up all users\' orphaned documents')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Run the appropriate command
    if args.command == 'check-document':
        asyncio.run(cmd_check_document(args.doc_id, args.user_id))
    elif args.command == 'cleanup-document':
        asyncio.run(cmd_cleanup_document(args.doc_id, args.user_id))
    elif args.command == 'check-user':
        asyncio.run(cmd_check_user(args.user_id))
    elif args.command == 'cleanup-user':
        asyncio.run(cmd_cleanup_user(args.user_id))
    elif args.command == 'system-status':
        asyncio.run(cmd_system_status())
    elif args.command == 'cleanup-all':
        asyncio.run(cmd_cleanup_all())

if __name__ == '__main__':
    main()