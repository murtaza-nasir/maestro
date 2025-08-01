#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

import chromadb
from chromadb.config import Settings

def main():
    try:
        # Connect to ChromaDB using the same path as the application
        chroma_path = "/app/ai_researcher/data/vector_store"
        print(f"Connecting to ChromaDB at: {chroma_path}")
        
        client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # List all collections
        collections = client.list_collections()
        print(f"\n=== ChromaDB Collections ===")
        print(f"Found {len(collections)} collections:")
        
        for collection in collections:
            print(f"\nCollection: {collection.name}")
            print(f"  ID: {collection.id}")
            
            # Get collection details
            try:
                count = collection.count()
                print(f"  Document count: {count}")
                
                # Get a few sample documents to check structure
                if count > 0:
                    sample = collection.get(limit=3, include=['metadatas', 'documents'])
                    print(f"  Sample documents:")
                    for i, (doc_id, metadata, document) in enumerate(zip(sample['ids'], sample['metadatas'], sample['documents'])):
                        print(f"    {i+1}. ID: {doc_id}")
                        print(f"       Metadata: {metadata}")
                        print(f"       Document preview: {document[:100]}...")
                        print()
                        
            except Exception as e:
                print(f"  Error getting collection details: {e}")
        
        if not collections:
            print("No collections found! This explains why searches return 0 results.")
            
    except Exception as e:
        print(f"Error connecting to ChromaDB: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
