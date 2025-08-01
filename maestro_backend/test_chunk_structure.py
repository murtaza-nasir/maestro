#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

from ai_researcher.core_rag.vector_store import VectorStore
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.retriever import Retriever
import asyncio

async def test_chunk_structure():
    """Test the exact structure of chunks returned by the retriever"""
    
    print("=== Testing Chunk Structure from Retriever ===")
    
    # Initialize components
    embedder = TextEmbedder()
    vector_store = VectorStore(persist_directory="/app/ai_researcher/data/vector_store")
    retriever = Retriever(embedder, vector_store)
    
    # Test with a simple query and document filter
    test_doc_ids = ['1311a207', 'c7066e54']
    filter_metadata = {"doc_id": {"$in": test_doc_ids}}
    
    print(f"Testing retrieval with filter: {filter_metadata}")
    
    try:
        results = await retriever.retrieve(
            query_text="weather risk",
            n_results=3,
            filter_metadata=filter_metadata,
            use_reranker=False  # Disable reranker to see raw results
        )
        
        print(f"\nRetrieved {len(results)} results")
        
        for i, chunk in enumerate(results):
            print(f"\n--- Chunk {i+1} ---")
            print(f"Type: {type(chunk)}")
            print(f"Keys: {list(chunk.keys()) if isinstance(chunk, dict) else 'Not a dict'}")
            
            if isinstance(chunk, dict):
                # Check for chunk_id at top level
                if 'chunk_id' in chunk:
                    print(f"✅ Top-level chunk_id: {chunk['chunk_id']}")
                else:
                    print("❌ No top-level chunk_id")
                
                # Check for chunk_id in metadata
                metadata = chunk.get('metadata', {})
                print(f"Metadata type: {type(metadata)}")
                print(f"Metadata keys: {list(metadata.keys()) if isinstance(metadata, dict) else 'Not a dict'}")
                
                if isinstance(metadata, dict) and 'chunk_id' in metadata:
                    print(f"✅ Metadata chunk_id: {metadata['chunk_id']}")
                else:
                    print("❌ No chunk_id in metadata")
                
                # Show first 100 chars of text
                text = chunk.get('text', '')
                print(f"Text preview: {text[:100]}...")
                
                # Show score
                score = chunk.get('score', 'N/A')
                print(f"Score: {score}")
                
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_chunk_structure())
