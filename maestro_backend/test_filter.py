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
        
        # Get the dense collection
        dense_collection = client.get_collection("research_papers_dense")
        print(f"Dense collection has {dense_collection.count()} documents")
        
        # Test the filter that should be used by the document search
        doc_ids = ['1311a207', 'c7066e54', 'd73607d8', '99c885e5']
        filter_metadata = {"doc_id": {"$in": doc_ids}}
        
        print(f"\n=== Testing Filter ===")
        print(f"Filter: {filter_metadata}")
        
        # Test query with filter
        try:
            # Create a simple query embedding (zeros for testing)
            dummy_embedding = [0.0] * 1024  # BGE-M3 dense dimension
            
            results = dense_collection.query(
                query_embeddings=[dummy_embedding],
                n_results=10,
                where=filter_metadata,
                include=["documents", "metadatas", "distances"]
            )
            
            print(f"Query with filter returned {len(results['ids'][0])} results")
            
            if results['ids'][0]:
                print("Sample results:")
                for i, (doc_id, metadata) in enumerate(zip(results['ids'][0][:3], results['metadatas'][0][:3])):
                    print(f"  {i+1}. ID: {doc_id}")
                    print(f"     doc_id: {metadata.get('doc_id')}")
                    print(f"     filename: {metadata.get('original_filename', 'N/A')}")
                    print()
            else:
                print("No results returned with filter!")
                
                # Let's test without filter to see if we get results
                print("\n=== Testing Without Filter ===")
                results_no_filter = dense_collection.query(
                    query_embeddings=[dummy_embedding],
                    n_results=5,
                    include=["documents", "metadatas", "distances"]
                )
                
                print(f"Query without filter returned {len(results_no_filter['ids'][0])} results")
                if results_no_filter['ids'][0]:
                    print("Sample results without filter:")
                    for i, (doc_id, metadata) in enumerate(zip(results_no_filter['ids'][0][:3], results_no_filter['metadatas'][0][:3])):
                        print(f"  {i+1}. ID: {doc_id}")
                        print(f"     doc_id: {metadata.get('doc_id')}")
                        print(f"     filename: {metadata.get('original_filename', 'N/A')}")
                        print()
                
                # Let's also check what doc_ids actually exist
                print("\n=== Checking Available doc_ids ===")
                all_results = dense_collection.get(
                    limit=10,
                    include=["metadatas"]
                )
                
                unique_doc_ids = set()
                for metadata in all_results['metadatas']:
                    doc_id = metadata.get('doc_id')
                    if doc_id:
                        unique_doc_ids.add(doc_id)
                
                print(f"Found doc_ids in first 10 documents: {sorted(unique_doc_ids)}")
                
                # Test with a single doc_id that we know exists
                if unique_doc_ids:
                    test_doc_id = list(unique_doc_ids)[0]
                    print(f"\n=== Testing Filter with Single doc_id: {test_doc_id} ===")
                    
                    single_filter = {"doc_id": test_doc_id}
                    single_results = dense_collection.query(
                        query_embeddings=[dummy_embedding],
                        n_results=5,
                        where=single_filter,
                        include=["documents", "metadatas", "distances"]
                    )
                    
                    print(f"Query with single doc_id filter returned {len(single_results['ids'][0])} results")
                    
        except Exception as e:
            print(f"Error during query: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"Error connecting to ChromaDB: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
