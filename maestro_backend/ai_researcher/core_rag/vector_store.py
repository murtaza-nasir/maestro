import os
import chromadb
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm
import json # For cleaning metadata

# Define a fixed dimension for the sparse vector representation
# This should ideally match the vocabulary size or a predefined large number
# BGE-M3's vocab size isn't immediately obvious, using 30522 (BERT) or a larger power of 2 is common.
# Let's use a reasonably large fixed size. Check BGE model card if possible.
# Using 30k as a placeholder, adjust if model specifics are known.
SPARSE_DIMENSION = 30000

class VectorStore:
    """
    Manages storing and retrieving text chunks and their embeddings using ChromaDB.
    Handles both dense and sparse embeddings (converting sparse dicts to fixed vectors).
    """
    def __init__(
        self,
        persist_directory: str | Path = "data/vector_store",
        dense_collection_name: str = "research_papers_dense",
        sparse_collection_name: str = "research_papers_sparse",
        batch_size: int = 100 # Batch size for adding documents to Chroma
    ):
        self.persist_directory = str(persist_directory) # Chroma client expects string path
        self.dense_collection_name = dense_collection_name
        self.sparse_collection_name = sparse_collection_name
        self.batch_size = batch_size

        print(f"Initializing VectorStore with persistence directory: {self.persist_directory}")
        try:
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(path=self.persist_directory)

            # Get or create collections
            # Dense collection uses cosine distance (good for normalized embeddings like BGE)
            self.dense_collection = self.client.get_or_create_collection(
                name=self.dense_collection_name,
                metadata={"hnsw:space": "cosine"} # Specify cosine distance
            )
            print(f"Dense collection '{self.dense_collection_name}' loaded/created with {self.dense_collection.count()} items.")

            # Sparse collection - also using cosine for consistency, though L2 might also work
            self.sparse_collection = self.client.get_or_create_collection(
                name=self.sparse_collection_name,
                 metadata={"hnsw:space": "cosine"} # Or "l2"
            )
            print(f"Sparse collection '{self.sparse_collection_name}' loaded/created with {self.sparse_collection.count()} items.")

        except Exception as e:
            print(f"Error initializing ChromaDB client or collections: {e}")
            # Depending on requirements, either raise the error or handle gracefully
            raise

    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Removes None values and converts complex types to strings for ChromaDB compatibility."""
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                cleaned[key] = "" # Replace None with empty string
            elif isinstance(value, (list, dict)):
                 # Convert lists/dicts to JSON strings if not directly supported
                 try:
                      cleaned[key] = json.dumps(value)
                 except TypeError:
                      cleaned[key] = str(value) # Fallback to string conversion
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value # Keep supported primitive types
            else:
                # Convert any other types to string as a fallback
                cleaned[key] = str(value)
        return cleaned

    def _convert_sparse_dict_to_vector(self, sparse_dict: Dict[int, float]) -> List[float]:
        """Converts a sparse dictionary {token_id: weight} to a fixed-size dense vector."""
        sparse_vec = np.zeros(SPARSE_DIMENSION, dtype=np.float32)
        if sparse_dict: # Check if dict is not None or empty
             for idx_str, weight in sparse_dict.items():
                 try:
                      idx = int(idx_str)
                      if 0 <= idx < SPARSE_DIMENSION:
                           sparse_vec[idx] = float(weight)
                 except (ValueError, TypeError):
                      # Ignore indices that are not valid integers or out of bounds
                      # print(f"Warning: Invalid sparse index or weight skipped: index='{idx_str}', weight='{weight}'")
                      pass
        return sparse_vec.tolist()

    def add_chunks(self, chunks_with_embeddings: List[Dict[str, Any]]):
        """
        Adds chunks with their pre-computed embeddings to the ChromaDB collections.

        Args:
            chunks_with_embeddings: A list of chunk dictionaries, each containing
                                    'text', 'metadata', and 'embeddings' (with 'dense' and 'sparse' keys).
        """
        if not chunks_with_embeddings:
            print("No chunks provided to add to VectorStore.")
            return

        num_chunks = len(chunks_with_embeddings)
        print(f"Adding {num_chunks} chunks to VectorStore in batches of {self.batch_size}...")

        added_dense = 0
        added_sparse = 0

        for i in tqdm(range(0, num_chunks, self.batch_size), desc="Adding Chunks to Chroma"):
            batch = chunks_with_embeddings[i : i + self.batch_size]

            # Prepare batch data
            ids = []
            texts = []
            metadatas = []
            dense_embeddings_batch = []
            sparse_vectors_batch = []

            for chunk in batch:
                # Generate a unique ID for each chunk (e.g., doc_id + chunk_id)
                doc_id = chunk.get("metadata", {}).get("doc_id", "unknown")
                chunk_id = chunk.get("metadata", {}).get("chunk_id", i + len(ids)) # Use counter as fallback
                unique_id = f"{doc_id}_{chunk_id}"
                ids.append(unique_id)

                texts.append(chunk.get("text", ""))

                # Clean metadata for ChromaDB
                cleaned_meta = self._clean_metadata(chunk.get("metadata", {}))
                metadatas.append(cleaned_meta)

                # Extract dense embedding
                dense_emb = chunk.get("embeddings", {}).get("dense")
                if dense_emb and isinstance(dense_emb, list):
                     dense_embeddings_batch.append(dense_emb)
                else:
                     print(f"Warning: Missing or invalid dense embedding for chunk {unique_id}. Using zero vector.")
                     # Determine expected dimension (needs embedder info or hardcode)
                     # Assuming 1024 for BGE-M3 dense part
                     dense_embeddings_batch.append([0.0] * 1024)

                # Extract and convert sparse embedding
                sparse_dict = chunk.get("embeddings", {}).get("sparse")
                if sparse_dict and isinstance(sparse_dict, dict):
                     sparse_vec = self._convert_sparse_dict_to_vector(sparse_dict)
                     sparse_vectors_batch.append(sparse_vec)
                else:
                     print(f"Warning: Missing or invalid sparse embedding for chunk {unique_id}. Using zero vector.")
                     sparse_vectors_batch.append([0.0] * SPARSE_DIMENSION)


            # Add batch to collections if data exists
            try:
                if ids and dense_embeddings_batch:
                    self.dense_collection.add(
                        ids=ids,
                        embeddings=dense_embeddings_batch,
                        documents=texts,
                        metadatas=metadatas
                    )
                    added_dense += len(ids)
                if ids and sparse_vectors_batch:
                     self.sparse_collection.add(
                         ids=ids,
                         embeddings=sparse_vectors_batch, # Add the converted sparse vectors
                         documents=texts, # Store text here too for potential retrieval context
                         metadatas=metadatas # Store original metadata
                     )
                     added_sparse += len(ids)
            except Exception as e:
                print(f"Error adding batch starting at index {i} to ChromaDB: {e}")
                # Consider logging failed IDs or attempting retries

        print(f"Finished adding chunks. Added {added_dense} to dense, {added_sparse} to sparse collection.")
        print(f"Total items in dense collection: {self.dense_collection.count()}")
        print(f"Total items in sparse collection: {self.sparse_collection.count()}")


    def query(
        self,
        query_dense_embedding: List[float],
        query_sparse_embedding_dict: Dict[int, float],
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Queries both dense and sparse collections and combines the results using weighted scores.

        Args:
            query_dense_embedding: The dense embedding vector for the query.
            query_sparse_embedding_dict: The sparse embedding dictionary for the query.
            n_results: The desired number of final results.
            filter_metadata: Optional dictionary to filter results based on metadata (e.g., {"doc_id": "xyz"}).
            dense_weight: Weight for dense results score.
            sparse_weight: Weight for sparse results score.

        Returns:
            A list of result dictionaries, sorted by combined score, each containing
            'text', 'metadata', and 'score'.
        """
        if not query_dense_embedding or query_sparse_embedding_dict is None:
             print("Error: Query embeddings missing.")
             return []

        # Convert query sparse dict to vector
        query_sparse_vector = self._convert_sparse_dict_to_vector(query_sparse_embedding_dict)

        # Determine number of results to fetch from each collection initially
        # Fetch more initially to allow for better combination (e.g., 2*n_results)
        fetch_n = n_results * 2

        results_by_type = {}

        # Query Dense Collection
        try:
            print(f"Querying dense collection (n={fetch_n})...")
            dense_results = self.dense_collection.query(
                query_embeddings=[query_dense_embedding],
                n_results=fetch_n,
                where=filter_metadata, # Apply metadata filter if provided
                include=["documents", "metadatas", "distances"]
            )
            results_by_type["dense"] = [
                {'id': id, 'text': doc, 'metadata': meta, 'score': 1.0 - dist if dist is not None else 0.0}
                for id, doc, meta, dist in zip(dense_results['ids'][0], dense_results['documents'][0], dense_results['metadatas'][0], dense_results['distances'][0])
            ]
            print(f"Retrieved {len(results_by_type['dense'])} dense results.")
        except Exception as e:
            print(f"Error querying dense collection: {e}")
            results_by_type["dense"] = []

        # Query Sparse Collection
        try:
            print(f"Querying sparse collection (n={fetch_n})...")
            sparse_results = self.sparse_collection.query(
                query_embeddings=[query_sparse_vector],
                n_results=fetch_n,
                where=filter_metadata, # Apply metadata filter if provided
                include=["documents", "metadatas", "distances"]
            )
            # Assuming cosine distance for sparse too, convert distance to similarity
            results_by_type["sparse"] = [
                 {'id': id, 'text': doc, 'metadata': meta, 'score': 1.0 - dist if dist is not None else 0.0}
                 for id, doc, meta, dist in zip(sparse_results['ids'][0], sparse_results['documents'][0], sparse_results['metadatas'][0], sparse_results['distances'][0])
            ]
            print(f"Retrieved {len(results_by_type['sparse'])} sparse results.")
        except Exception as e:
            print(f"Error querying sparse collection: {e}")
            results_by_type["sparse"] = []

        # Combine and re-score results (Reciprocal Rank Fusion or simple weighted sum)
        # Using simple weighted sum for now
        combined_results = {}
        print("Combining and re-scoring results...")

        # Process dense results
        for result in results_by_type.get("dense", []):
            res_id = result['id']
            if res_id not in combined_results:
                combined_results[res_id] = {
                    'id': res_id,
                    'text': result['text'],
                    'metadata': result['metadata'], # Metadata should be consistent
                    'score': 0.0
                }
            combined_results[res_id]['score'] += result['score'] * dense_weight

        # Process sparse results
        for result in results_by_type.get("sparse", []):
             res_id = result['id']
             if res_id not in combined_results:
                 # If a result only appeared in sparse, initialize it
                 combined_results[res_id] = {
                     'id': res_id,
                     'text': result['text'],
                     'metadata': result['metadata'],
                     'score': 0.0
                 }
             combined_results[res_id]['score'] += result['score'] * sparse_weight

        # Sort by combined score
        final_results = sorted(
            combined_results.values(),
            key=lambda x: x['score'],
            reverse=True
        )

        print(f"Returning top {min(n_results, len(final_results))} combined results.")
        return final_results[:n_results]