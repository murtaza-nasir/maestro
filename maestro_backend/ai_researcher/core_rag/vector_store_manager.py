import os
import time
import fcntl
import chromadb
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm
import json
import threading
from contextlib import contextmanager

# Define a fixed dimension for the sparse vector representation
SPARSE_DIMENSION = 30000

class VectorStoreManager:
    """
    Thread-safe wrapper around VectorStore that handles concurrent access
    using file locking to prevent database corruption.
    """
    def __init__(
        self,
        persist_directory: str | Path = "data/vector_store",
        dense_collection_name: str = "research_papers_dense",
        sparse_collection_name: str = "research_papers_sparse",
        batch_size: int = 100,
        lock_timeout: int = 30
    ):
        self.persist_directory = str(persist_directory)
        self.dense_collection_name = dense_collection_name
        self.sparse_collection_name = sparse_collection_name
        self.batch_size = batch_size
        self.lock_timeout = 300  # 5 minutes timeout for better concurrent access
        
        # Create lock file path
        self.lock_file_path = Path(self.persist_directory) / "chroma.lock"
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        
        # Thread-local storage for client instances
        self._local = threading.local()
        
        print(f"Initializing VectorStoreManager with persistence directory: {self.persist_directory}")

    @contextmanager
    def _file_lock(self, operation_type="read"):
        """
        Context manager for file-based locking to prevent concurrent access.
        """
        lock_file = None
        try:
            # Create lock file if it doesn't exist
            lock_file = open(self.lock_file_path, 'w')
            
            # Try to acquire lock with timeout
            start_time = time.time()
            while True:
                try:
                    if operation_type == "write":
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    else:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                    break
                except IOError:
                    if time.time() - start_time > self.lock_timeout:
                        raise TimeoutError(f"Could not acquire {operation_type} lock within {self.lock_timeout} seconds")
                    time.sleep(0.1)
            
            print(f"Acquired {operation_type} lock for ChromaDB access")
            yield
            
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                    print(f"Released {operation_type} lock for ChromaDB access")
                except:
                    pass

    def _get_client(self):
        """Get or create a thread-local ChromaDB client with retry logic."""
        if not hasattr(self._local, 'client'):
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self._local.client = chromadb.PersistentClient(path=self.persist_directory)
                    
                    # Get or create collections with retry
                    self._local.dense_collection = self._local.client.get_or_create_collection(
                        name=self.dense_collection_name,
                        metadata={"hnsw:space": "cosine"}
                    )
                    
                    self._local.sparse_collection = self._local.client.get_or_create_collection(
                        name=self.sparse_collection_name,
                        metadata={"hnsw:space": "cosine"}
                    )
                    break
                    
                except Exception as e:
                    print(f"ChromaDB connection attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1)  # Wait before retry
                        # Clear any partial state
                        if hasattr(self._local, 'client'):
                            delattr(self._local, 'client')
                        if hasattr(self._local, 'dense_collection'):
                            delattr(self._local, 'dense_collection')
                        if hasattr(self._local, 'sparse_collection'):
                            delattr(self._local, 'sparse_collection')
                    else:
                        raise e
            
        return self._local.client, self._local.dense_collection, self._local.sparse_collection

    def refresh_client(self):
        """
        Refresh the thread-local ChromaDB client to pick up newly added documents.
        Call this after adding new documents to ensure queries can access them.
        """
        print("Refreshing ChromaDB client to pick up new documents...")
        
        # Clear existing thread-local client
        if hasattr(self._local, 'client'):
            delattr(self._local, 'client')
        if hasattr(self._local, 'dense_collection'):
            delattr(self._local, 'dense_collection')
        if hasattr(self._local, 'sparse_collection'):
            delattr(self._local, 'sparse_collection')
        
        # Force recreation of client on next access
        self._get_client()
        print("ChromaDB client refreshed successfully")

    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Removes None values and converts complex types to strings for ChromaDB compatibility."""
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                cleaned[key] = ""
            elif isinstance(value, (list, dict)):
                try:
                    cleaned[key] = json.dumps(value)
                except TypeError:
                    cleaned[key] = str(value)
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        return cleaned

    def _convert_sparse_dict_to_vector(self, sparse_dict: Dict[int, float]) -> List[float]:
        """Converts a sparse dictionary {token_id: weight} to a fixed-size dense vector."""
        sparse_vec = np.zeros(SPARSE_DIMENSION, dtype=np.float32)
        if sparse_dict:
            for idx_str, weight in sparse_dict.items():
                try:
                    idx = int(idx_str)
                    if 0 <= idx < SPARSE_DIMENSION:
                        sparse_vec[idx] = float(weight)
                except (ValueError, TypeError):
                    pass
        return sparse_vec.tolist()

    def add_chunks(self, chunks_with_embeddings: List[Dict[str, Any]]):
        """
        Thread-safe method to add chunks with their pre-computed embeddings to ChromaDB.
        """
        if not chunks_with_embeddings:
            print("No chunks provided to add to VectorStore.")
            return

        with self._file_lock("write"):
            client, dense_collection, sparse_collection = self._get_client()
            
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
                    doc_id = chunk.get("metadata", {}).get("doc_id", "unknown")
                    chunk_id = chunk.get("metadata", {}).get("chunk_id", i + len(ids))
                    unique_id = f"{doc_id}_{chunk_id}"
                    ids.append(unique_id)

                    texts.append(chunk.get("text", ""))
                    cleaned_meta = self._clean_metadata(chunk.get("metadata", {}))
                    metadatas.append(cleaned_meta)

                    # Extract dense embedding
                    dense_emb = chunk.get("embeddings", {}).get("dense")
                    if dense_emb and isinstance(dense_emb, list):
                        dense_embeddings_batch.append(dense_emb)
                    else:
                        print(f"Warning: Missing or invalid dense embedding for chunk {unique_id}. Using zero vector.")
                        dense_embeddings_batch.append([0.0] * 1024)

                    # Extract and convert sparse embedding
                    sparse_dict = chunk.get("embeddings", {}).get("sparse")
                    if sparse_dict and isinstance(sparse_dict, dict):
                        sparse_vec = self._convert_sparse_dict_to_vector(sparse_dict)
                        sparse_vectors_batch.append(sparse_vec)
                    else:
                        print(f"Warning: Missing or invalid sparse embedding for chunk {unique_id}. Using zero vector.")
                        sparse_vectors_batch.append([0.0] * SPARSE_DIMENSION)

                # Add batch to collections
                try:
                    if ids and dense_embeddings_batch:
                        dense_collection.add(
                            ids=ids,
                            embeddings=dense_embeddings_batch,
                            documents=texts,
                            metadatas=metadatas
                        )
                        added_dense += len(ids)
                    if ids and sparse_vectors_batch:
                        sparse_collection.add(
                            ids=ids,
                            embeddings=sparse_vectors_batch,
                            documents=texts,
                            metadatas=metadatas
                        )
                        added_sparse += len(ids)
                except Exception as e:
                    print(f"Error adding batch starting at index {i} to ChromaDB: {e}")

            print(f"Finished adding chunks. Added {added_dense} to dense, {added_sparse} to sparse collection.")
            print(f"Total items in dense collection: {dense_collection.count()}")
            print(f"Total items in sparse collection: {sparse_collection.count()}")

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
        Thread-safe method to query both dense and sparse collections.
        """
        if not query_dense_embedding or query_sparse_embedding_dict is None:
            print("Error: Query embeddings missing.")
            return []

        with self._file_lock("read"):
            client, dense_collection, sparse_collection = self._get_client()
            
            query_sparse_vector = self._convert_sparse_dict_to_vector(query_sparse_embedding_dict)
            fetch_n = n_results * 2
            results_by_type = {}

            # Query Dense Collection
            try:
                print(f"Querying dense collection (n={fetch_n})...")
                dense_results = dense_collection.query(
                    query_embeddings=[query_dense_embedding],
                    n_results=fetch_n,
                    where=filter_metadata,
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
                sparse_results = sparse_collection.query(
                    query_embeddings=[query_sparse_vector],
                    n_results=fetch_n,
                    where=filter_metadata,
                    include=["documents", "metadatas", "distances"]
                )
                results_by_type["sparse"] = [
                    {'id': id, 'text': doc, 'metadata': meta, 'score': 1.0 - dist if dist is not None else 0.0}
                    for id, doc, meta, dist in zip(sparse_results['ids'][0], sparse_results['documents'][0], sparse_results['metadatas'][0], sparse_results['distances'][0])
                ]
                print(f"Retrieved {len(results_by_type['sparse'])} sparse results.")
            except Exception as e:
                print(f"Error querying sparse collection: {e}")
                results_by_type["sparse"] = []

            # Combine and re-score results
            combined_results = {}
            print("Combining and re-scoring results...")

            # Process dense results
            for result in results_by_type.get("dense", []):
                res_id = result['id']
                if res_id not in combined_results:
                    combined_results[res_id] = {
                        'id': res_id,
                        'text': result['text'],
                        'metadata': result['metadata'],
                        'score': 0.0
                    }
                combined_results[res_id]['score'] += result['score'] * dense_weight

            # Process sparse results
            for result in results_by_type.get("sparse", []):
                res_id = result['id']
                if res_id not in combined_results:
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

    def get_collection_counts(self) -> Tuple[int, int]:
        """Get the count of items in both collections."""
        with self._file_lock("read"):
            client, dense_collection, sparse_collection = self._get_client()
            return dense_collection.count(), sparse_collection.count()


# Backward compatibility - create an alias
VectorStore = VectorStoreManager
