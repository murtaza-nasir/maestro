#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')
sys.path.append('/app/ai_researcher')

from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.vector_store import VectorStore
from ai_researcher.core_rag.retriever import Retriever

def test_vectorstore_connection():
    """Test that VectorStore connects to the correct ChromaDB data."""
    print("Testing VectorStore connection with correct path...")
    
    try:
        # Initialize components with the correct absolute path
        embedder = TextEmbedder()
        vector_store = VectorStore(persist_directory="/app/ai_researcher/data/vector_store")
        retriever = Retriever(embedder=embedder, vector_store=vector_store)
        
        print(f"✅ VectorStore initialized successfully")
        print(f"   Dense collection count: {vector_store.dense_collection.count()}")
        print(f"   Sparse collection count: {vector_store.sparse_collection.count()}")
        
        # Test a simple query with document filtering
        test_doc_ids = ['1311a207', 'c7066e54', 'd73607d8', '99c885e5']
        filter_metadata = {"doc_id": {"$in": test_doc_ids}}
        
        # Create a simple test query
        test_query = "machine learning"
        query_embeddings = embedder.embed_query(test_query)
        
        print(f"\n🔍 Testing query with document filter...")
        print(f"   Query: '{test_query}'")
        print(f"   Filter: {filter_metadata}")
        
        results = vector_store.query(
            query_dense_embedding=query_embeddings["dense"],
            query_sparse_embedding_dict=query_embeddings["sparse"],
            n_results=5,
            filter_metadata=filter_metadata
        )
        
        print(f"   Results found: {len(results)}")
        
        if results:
            print("✅ Document search is working!")
            for i, result in enumerate(results[:3]):
                doc_id = result.get('metadata', {}).get('doc_id', 'unknown')
                score = result.get('score', 0)
                text_preview = result.get('text', '')[:100] + '...'
                print(f"   Result {i+1}: doc_id={doc_id}, score={score:.3f}")
                print(f"              text='{text_preview}'")
        else:
            print("❌ No results found - there may still be an issue")
            
        return len(results) > 0
        
    except Exception as e:
        print(f"❌ Error testing VectorStore: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_vectorstore_connection()
    if success:
        print("\n🎉 VectorStore fix appears to be working!")
    else:
        print("\n💥 VectorStore fix needs more work")
    
    sys.exit(0 if success else 1)
