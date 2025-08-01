#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
from ai_researcher.core_rag.vector_store import VectorStore
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.query_preparer import QueryPreparer
from ai_researcher.core_rag.query_strategist import QueryStrategist
import asyncio

async def test_document_search_fix():
    """Test that the chunk_id warning is fixed"""
    
    print("=== Testing Document Search Fix ===")
    
    # Initialize components
    from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
    
    embedder = TextEmbedder()
    vector_store = VectorStore(persist_directory="/app/ai_researcher/data/vector_store")
    retriever = Retriever(embedder, vector_store)
    
    # Initialize model dispatcher
    model_dispatcher = ModelDispatcher()
    
    query_preparer = QueryPreparer(model_dispatcher)
    query_strategist = QueryStrategist(model_dispatcher)
    
    # Initialize document search tool
    doc_search = DocumentSearchTool(retriever, query_preparer, query_strategist)
    
    # Test with document group filtering (this should trigger the original issue)
    test_doc_ids = ['1311a207', 'c7066e54']
    
    print(f"Testing document search with filter_doc_ids: {test_doc_ids}")
    
    try:
        results = await doc_search.execute(
            query="weather risk",
            n_results=5,
            filter_doc_ids=test_doc_ids,
            use_reranker=False  # Disable reranker for faster testing
        )
        
        print(f"\n✅ Document search completed successfully!")
        print(f"Retrieved {len(results)} results")
        
        # Check if any results have chunk_id = 0 (which was causing the issue)
        for i, result in enumerate(results):
            chunk_id = result.get("metadata", {}).get("chunk_id")
            text_preview = result.get("text", "")[:50]
            print(f"Result {i+1}: chunk_id={chunk_id}, text='{text_preview}...'")
            
            if chunk_id == 0:
                print(f"  ✅ Found chunk with chunk_id=0 - this should no longer trigger a warning!")
                
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_document_search_fix())
