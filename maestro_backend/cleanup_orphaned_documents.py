#!/usr/bin/env python3
"""
Script to clean up orphaned documents in the database that no longer exist in the vector store.
"""

import sys
import os
sys.path.append('/app')

from database.database import get_db
from database import crud
from services.document_service import document_service

def cleanup_orphaned_documents():
    """Remove documents from database that no longer exist in the vector store."""
    
    print("🧹 Starting cleanup of orphaned documents...")
    
    # Get database session
    db = next(get_db())
    
    try:
        # Get all documents from database
        all_db_documents = crud.get_user_documents(db, user_id=1, skip=0, limit=1000)  # testuser has ID 1
        print(f"📊 Found {len(all_db_documents)} documents in database")
        
        # Get all documents from vector store
        vector_store = document_service._get_vector_store()
        collection = vector_store.dense_collection
        
        # Get all unique document IDs from vector store
        results = collection.get(include=['metadatas'])
        vector_doc_ids = set()
        for meta in results.get('metadatas', []):
            doc_id = meta.get('doc_id')
            if doc_id:
                vector_doc_ids.add(doc_id)
        
        print(f"📊 Found {len(vector_doc_ids)} unique documents in vector store")
        
        # Find orphaned documents (in database but not in vector store)
        orphaned_docs = []
        for db_doc in all_db_documents:
            if db_doc.id not in vector_doc_ids:
                orphaned_docs.append(db_doc)
        
        print(f"🔍 Found {len(orphaned_docs)} orphaned documents in database")
        
        if orphaned_docs:
            print("\n📋 Orphaned documents:")
            for doc in orphaned_docs:
                print(f"  - {doc.id}: {doc.original_filename}")
            
            # Ask for confirmation
            response = input(f"\n❓ Delete these {len(orphaned_docs)} orphaned documents from database? (y/N): ")
            
            if response.lower() == 'y':
                deleted_count = 0
                for doc in orphaned_docs:
                    try:
                        # Delete from database only (not vector store since it's already gone)
                        db.delete(doc)
                        db.commit()
                        deleted_count += 1
                        print(f"✅ Deleted {doc.id}: {doc.original_filename}")
                    except Exception as e:
                        print(f"❌ Failed to delete {doc.id}: {e}")
                        db.rollback()
                
                print(f"\n🎉 Successfully deleted {deleted_count} orphaned documents from database")
            else:
                print("❌ Cleanup cancelled")
        else:
            print("✅ No orphaned documents found - database is clean!")
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_orphaned_documents()
