import asyncio # <-- Import asyncio
from typing import List, Dict, Any, Optional

from .embedder import TextEmbedder
from .vector_store_manager import VectorStoreManager as VectorStore
from .reranker import TextReranker # Optional reranker

class Retriever:
    """
    Handles the retrieval process: embedding queries, querying the vector store,
    and optionally reranking results.
    """
    def __init__(
        self,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        reranker: Optional[TextReranker] = None # Allow optional reranker
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        print("Retriever initialized.")
        if self.reranker:
             print("Retriever: Reranker is enabled.")
        else:
              print("Retriever: Reranker is disabled.")


    async def retrieve( # <-- Make async
        self,
        query_text: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        use_reranker: bool = True, # Flag to control reranking per query
        dense_weight: float = 0.5, # Weight for initial vector store query
        sparse_weight: float = 0.5  # Weight for initial vector store query
    ) -> List[Dict[str, Any]]:
        """
        Retrieves relevant chunks for a given query.

        Args:
            query_text: The user's query string.
            n_results: The final number of results desired.
            filter_metadata: Optional metadata filter for the vector store query.
            use_reranker: Whether to use the reranker if available and enabled.
            dense_weight: Weight for dense embeddings in the initial hybrid search.
            sparse_weight: Weight for sparse embeddings in the initial hybrid search.

        Returns:
            A list of retrieved chunk dictionaries, sorted by relevance.
        """
        print(f"\n--- Retrieving documents for query: '{query_text}' ---")

        # 1. Embed the query (using async method with semaphore)
        print("Embedding query...")
        try:
            # Use the new async embedding method that includes semaphore control
            query_embeddings = await self.embedder.embed_query_async(query_text)
            if not query_embeddings:
                print("Error: Failed to embed query (returned None).")
                return []
        except Exception as e:
            print(f"Error during query embedding: {e}")
            return []

        query_dense = query_embeddings.get("dense")
        query_sparse = query_embeddings.get("sparse") # This is the dict

        if not query_dense or query_sparse is None:
             print("Error: Query embedding generation failed or returned unexpected format.")
             return []

        # 2. Query the Vector Store
        # Fetch potentially more results initially if reranking is enabled
        initial_fetch_n = n_results * 3 if (use_reranker and self.reranker) else n_results
        print(f"Querying vector store (in thread, fetching up to {initial_fetch_n} results)...")
        try:
            # Run the synchronous vector store query in a separate thread
            initial_results = await asyncio.to_thread(
                self.vector_store.query,
                query_dense_embedding=query_dense,
                query_sparse_embedding_dict=query_sparse,
                n_results=initial_fetch_n,
                filter_metadata=filter_metadata,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight
            )
        except Exception as e:
            print(f"Error during vector store query thread execution: {e}")
            initial_results = [] # Ensure it's an empty list on error
        # Removed erroneous lines here

        if not initial_results:
            print("No results found in vector store. Attempting to refresh client and retry...")
            
            # Try refreshing the vector store client and retry once
            try:
                self.vector_store.refresh_client()
                initial_results = await asyncio.to_thread(
                    self.vector_store.query,
                    query_dense_embedding=query_dense,
                    query_sparse_embedding_dict=query_sparse,
                    n_results=initial_fetch_n,
                    filter_metadata=filter_metadata,
                    dense_weight=dense_weight,
                    sparse_weight=sparse_weight
                )
                
                if initial_results:
                    print(f"After refresh: Retrieved {len(initial_results)} results from vector store.")
                else:
                    print("No results found in vector store even after refresh.")
                    return []
            except Exception as e:
                print(f"Error during vector store retry after refresh: {e}")
                return []

        print(f"Retrieved {len(initial_results)} initial results from vector store.")

        # 3. Optionally Rerank (run sync reranker in thread)
        if use_reranker and self.reranker:
            print("Applying reranker (in thread)...")
            try:
                # Run the synchronous rerank method in a separate thread
                # The reranker now returns a list of tuples (score, item)
                reranked_tuples = await asyncio.to_thread(
                    self.reranker.rerank, query_text, initial_results, top_n=n_results
                )
                # Extract just the items from the tuples
                final_results = [item for _, item in reranked_tuples]
                print(f"Returning {len(final_results)} reranked results.")
            except Exception as e:
                 print(f"Error during reranker thread execution: {e}. Falling back to initial results.")
                 # Fallback to initial results if reranking fails
                 final_results = initial_results[:n_results]
        else:
            # If not reranking, just take the top N from the initial results
            final_results = initial_results[:n_results]
            print(f"Returning {len(final_results)} results (reranker disabled or skipped).")


        # 4. TODO: Potentially format results further if needed by agents
        # For now, return the list of dictionaries as retrieved/reranked

        return final_results
