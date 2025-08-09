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
    """Remove documents from database that no longer exist in vector store or AI researcher database."""
    
    print("🧹 Starting comprehensive cleanup of orphaned documents...")
    
    # Get database session
    db = next(get_db())
    
    try:
        # Get all documents from main database
        all_db_documents = crud.get_user_documents(db, user_id=1, skip=0, limit=1000)  # testuser has ID 1
        print(f"📊 Found {len(all_db_documents)} documents in main database")
        
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
        
        # Get all documents from AI researcher database
        ai_db = document_service._get_ai_db()
        ai_db_documents = ai_db.get_all_documents()
        ai_db_doc_ids = {doc['id'] for doc in ai_db_documents}
        print(f"📊 Found {len(ai_db_doc_ids)} documents in AI researcher database")
        
        # Find documents that exist anywhere (vector store OR AI researcher database)
        existing_doc_ids = vector_doc_ids.union(ai_db_doc_ids)
        print(f"📊 Total {len(existing_doc_ids)} documents exist in storage systems")
        
        # Find orphaned documents (in main database but not in any storage system)
        orphaned_docs = []
        for db_doc in all_db_documents:
            if db_doc.id not in existing_doc_ids:
                orphaned_docs.append(db_doc)
        
        print(f"🔍 Found {len(orphaned_docs)} orphaned documents in main database")
        
        # Also find documents that exist only in AI researcher database but not in main database
        ai_only_docs = []
        main_db_doc_ids = {doc.id for doc in all_db_documents}
        for ai_doc_id in ai_db_doc_ids:
            if ai_doc_id not in main_db_doc_ids:
                ai_only_docs.append(ai_doc_id)
        
        print(f"🔍 Found {len(ai_only_docs)} documents only in AI researcher database")
        
        total_cleanup_needed = len(orphaned_docs) + len(ai_only_docs)
        
        if total_cleanup_needed > 0:
            print("\n📋 Cleanup needed:")
            if orphaned_docs:
                print(f"  Orphaned in main database ({len(orphaned_docs)}):")
                for doc in orphaned_docs:
                    print(f"    - {doc.id}: {doc.original_filename}")
            
            if ai_only_docs:
                print(f"  AI researcher database only ({len(ai_only_docs)}):")
                for doc_id in ai_only_docs[:10]:  # Limit display
                    print(f"    - {doc_id}")
                if len(ai_only_docs) > 10:
                    print(f"    ... and {len(ai_only_docs) - 10} more")
            
            # Ask for confirmation
            response = input(f"\n❓ Clean up these {total_cleanup_needed} inconsistent documents? (y/N): ")
            
            if response.lower() == 'y':
                import asyncio
                deleted_count = 0
                
                # Delete orphaned documents completely (from ALL storage systems)
                print("🧹 Deleting orphaned documents from all storage systems...")
                for doc in orphaned_docs:
                    try:
                        # Use the complete deletion method (same as UI)
                        success = asyncio.run(
                            document_service.delete_document_completely(doc.id, 1)  # testuser has ID 1
                        )
                        
                        # Also delete from main database if it exists there
                        try:
                            db.delete(doc)
                            db.commit()
                            print(f"✅ Deleted from main DB: {doc.id}: {doc.original_filename}")
                        except Exception as e:
                            print(f"⚠️  Main DB deletion failed for {doc.id}: {e}")
                            db.rollback()
                        
                        if success:
                            deleted_count += 1
                            print(f"✅ Complete deletion successful: {doc.id}: {doc.original_filename}")
                        else:
                            print(f"⚠️  Partial deletion for {doc.id}: {doc.original_filename}")
                    except Exception as e:
                        print(f"❌ Failed complete deletion for {doc.id}: {e}")
                
                # Clean up documents that exist only in AI researcher database
                print("🧹 Cleaning up AI researcher database orphans...")
                for ai_doc_id in ai_only_docs:
                    try:
                        # Use complete deletion for these too
                        success = asyncio.run(
                            document_service.delete_document_completely(ai_doc_id, 1)  # testuser has ID 1
                        )
                        if success:
                            deleted_count += 1
                            print(f"✅ Complete deletion successful: {ai_doc_id}")
                        else:
                            print(f"⚠️  Document {ai_doc_id} not found in storage systems")
                    except Exception as e:
                        print(f"❌ Failed complete deletion for {ai_doc_id}: {e}")
                
                print(f"\n🎉 Successfully cleaned up {deleted_count} documents from all storage systems")
            else:
                print("❌ Cleanup cancelled")
        else:
            print("✅ No cleanup needed - all databases are consistent!")
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_orphaned_documents()
