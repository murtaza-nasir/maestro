#!/usr/bin/env python3
"""
Script to diagnose document group count discrepancies.
"""

import sys
import os
sys.path.append('/app')

from database.database import get_db
from database import crud
from services.document_service import document_service

def diagnose_group_counts():
    """Diagnose document group count issues."""
    
    print("🔍 Diagnosing document group counts...")
    
    # Get database session
    db = next(get_db())
    
    try:
        # Get all document groups
        groups = crud.get_user_document_groups(db, user_id=1, skip=0, limit=100)  # testuser has ID 1
        
        print(f"📊 Found {len(groups)} document groups")
        
        total_db_docs = 0
        
        for group in groups:
            print(f"\n📁 Group: {group.name} (ID: {group.id})")
            print(f"   Database count: {len(group.documents)}")
            
            # List all document IDs in this group
            doc_ids = [doc.id for doc in group.documents]
            print(f"   Document IDs: {doc_ids}")
            
            # Check if these documents exist in vector store
            vector_store = document_service._get_vector_store()
            collection = vector_store.dense_collection
            
            existing_in_vector = []
            missing_from_vector = []
            
            for doc_id in doc_ids:
                results = collection.get(where={"doc_id": doc_id}, limit=1)
                if results.get('metadatas') and len(results['metadatas']) > 0:
                    existing_in_vector.append(doc_id)
                else:
                    missing_from_vector.append(doc_id)
            
            print(f"   Exist in vector store: {len(existing_in_vector)}")
            print(f"   Missing from vector store: {len(missing_from_vector)}")
            
            if missing_from_vector:
                print(f"   ❌ Missing IDs: {missing_from_vector}")
            
            total_db_docs += len(group.documents)
        
        print(f"\n📊 Total documents across all groups: {total_db_docs}")
        
        # Get total unique documents in database
        all_db_documents = crud.get_user_documents(db, user_id=1, skip=0, limit=1000)
        print(f"📊 Total unique documents in database: {len(all_db_documents)}")
        
        # Get total documents in vector store
        vector_store = document_service._get_vector_store()
        collection = vector_store.dense_collection
        results = collection.get(include=['metadatas'])
        vector_doc_ids = set()
        for meta in results.get('metadatas', []):
            doc_id = meta.get('doc_id')
            if doc_id:
                vector_doc_ids.add(doc_id)
        
        print(f"📊 Total unique documents in vector store: {len(vector_doc_ids)}")
        
        # Check for duplicate group associations
        print(f"\n🔍 Checking for duplicate group associations...")
        all_group_doc_ids = []
        for group in groups:
            for doc in group.documents:
                all_group_doc_ids.append(doc.id)
        
        unique_group_doc_ids = set(all_group_doc_ids)
        duplicates = len(all_group_doc_ids) - len(unique_group_doc_ids)
        
        if duplicates > 0:
            print(f"❌ Found {duplicates} duplicate document associations across groups!")
            
            # Find which documents are duplicated
            from collections import Counter
            doc_counts = Counter(all_group_doc_ids)
            for doc_id, count in doc_counts.items():
                if count > 1:
                    print(f"   Document {doc_id} appears in {count} groups")
        else:
            print(f"✅ No duplicate associations found")
            
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    diagnose_group_counts()
