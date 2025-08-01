#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

from ai_researcher.core_rag.vector_store import VectorStore

def check_chunk_metadata():
    """Check what metadata fields are available in ChromaDB chunks"""
    
    # Initialize vector store
    vector_store = VectorStore(persist_directory="/app/ai_researcher/data/vector_store")
    
    print("=== Checking ChromaDB Chunk Metadata ===")
    
    # Get a few sample chunks to examine their metadata
    try:
        # Get collection info first
        dense_count = vector_store.dense_collection.count()
        sparse_count = vector_store.sparse_collection.count()
        
        print(f"\nDense collection count: {dense_count}")
        print(f"Sparse collection count: {sparse_count}")
        
        # Get some chunks directly without querying (to avoid embedding issues)
        dense_results = vector_store.dense_collection.get(limit=5)
        
        print(f"\nFound {len(dense_results['ids'])} dense chunks")
        
        # Examine metadata of first few chunks
        for i, (chunk_id, metadata) in enumerate(zip(dense_results['ids'], dense_results['metadatas'])):
            print(f"\nChunk {i+1}:")
            print(f"  ID: {chunk_id}")
            print(f"  Metadata keys: {list(metadata.keys()) if metadata else 'None'}")
            if metadata:
                for key, value in metadata.items():
                    print(f"    {key}: {value}")
            
            # Check if chunk_id exists in metadata
            if metadata and 'chunk_id' in metadata:
                print(f"  ✅ Has chunk_id: {metadata['chunk_id']}")
            else:
                print(f"  ❌ Missing chunk_id")
                
        # Also check sparse collection
        print(f"\n=== Sparse Collection ===")
        sparse_results = vector_store.sparse_collection.get(limit=3)
        
        print(f"Found {len(sparse_results['ids'])} sparse chunks")
        
        for i, (chunk_id, metadata) in enumerate(zip(sparse_results['ids'], sparse_results['metadatas'])):
            print(f"\nSparse Chunk {i+1}:")
            print(f"  ID: {chunk_id}")
            print(f"  Metadata keys: {list(metadata.keys()) if metadata else 'None'}")
            if metadata and 'chunk_id' in metadata:
                print(f"  ✅ Has chunk_id: {metadata['chunk_id']}")
            else:
                print(f"  ❌ Missing chunk_id")
                
    except Exception as e:
        print(f"Error checking metadata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_chunk_metadata()
