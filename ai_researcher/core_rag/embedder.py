import os
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import torch
from FlagEmbedding import BGEM3FlagModel
from tqdm import tqdm

class TextEmbedder:
    """
    Generates dense and sparse vector embeddings for text chunks using BGE-M3.
    """
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: Optional[str] = None,
        batch_size: int = 16, # Adjust based on GPU memory
        max_length: int = 8192 # Max sequence length for BGE-M3
    ):
        # Use device from config if available, otherwise use provided device or fallback
        import os
        from ai_researcher import config
        
        # If a specific device is provided, use it
        if device:
            self.device = device
        # If running in Docker, use Docker's CUDA settings
        elif config.is_running_in_docker():
            # In Docker, CUDA_VISIBLE_DEVICES is managed by Docker
            # We'll use the first available GPU (usually 0 in the container's view)
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        # Otherwise use the configured CUDA device
        else:
            cuda_device = config.CUDA_DEVICE
            self.device = f"cuda:{cuda_device}" if torch.cuda.is_available() and torch.cuda.device_count() > int(cuda_device) else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length

        print(f"Initializing TextEmbedder with model {self.model_name} on device {self.device}")
        try:
            # Initialize the BGE-M3 model
            self.model = BGEM3FlagModel(
                self.model_name,
                # Force fp32 to avoid dtype issues downstream (e.g., in vector store)
                use_fp16=False
            )
            print("BGE-M3 model loaded successfully (forced fp32).")
        except Exception as e:
            print(f"Error loading embedding model {self.model_name}: {e}")
            # Potentially raise the error or handle it depending on desired robustness
            raise

    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generates dense and sparse embeddings for a list of text chunks.

        Args:
            chunks: A list of chunk dictionaries, each expected to have a 'text' key.

        Returns:
            The same list of chunks, with an 'embeddings' dictionary added to each,
            containing 'dense' and 'sparse' vectors. Returns an empty list if input is empty.
        """
        if not chunks:
            return []

        all_texts = [chunk["text"] for chunk in chunks]
        num_chunks = len(all_texts)
        print(f"Generating embeddings for {num_chunks} chunks in batches of {self.batch_size}...")

        # Store results temporarily
        dense_embeddings = []
        sparse_embeddings = [] # Using list of dicts for sparse representation

        for i in tqdm(range(0, num_chunks, self.batch_size), desc="Embedding Chunks"):
            batch_texts = all_texts[i : i + self.batch_size]

            try:
                # Generate embeddings using the BGE-M3 model
                # We need both dense and sparse (lexical_weights)
                outputs = self.model.encode(
                    batch_texts,
                    batch_size=len(batch_texts), # Pass current batch size
                    max_length=self.max_length,
                    return_dense=True,
                    return_sparse=True,
                    return_colbert_vecs=False # Not requested for now
                )

                # Ensure outputs are numpy arrays for consistency before converting
                batch_dense = np.array(outputs["dense_vecs"], dtype=np.float32)
                batch_sparse_dicts = outputs["lexical_weights"] # List of dictionaries

                dense_embeddings.extend(batch_dense.tolist()) # Store as lists
                sparse_embeddings.extend(batch_sparse_dicts)

            except Exception as e:
                print(f"Error embedding batch starting at index {i}: {e}")
                # Handle error: skip batch, add placeholders, or re-raise
                # Adding placeholders for now to maintain list length alignment
                # Attempt to get hidden size safely
                hidden_size = getattr(getattr(self.model, 'model', None), 'config', None).hidden_size if hasattr(self.model, 'model') else 1024 # Default fallback size
                error_placeholder_dense = [0.0] * hidden_size
                error_placeholder_sparse = {}
                dense_embeddings.extend([error_placeholder_dense] * len(batch_texts))
                sparse_embeddings.extend([error_placeholder_sparse] * len(batch_texts))


        # Check if the number of embeddings matches the number of chunks
        if len(dense_embeddings) != num_chunks or len(sparse_embeddings) != num_chunks:
             print(f"Error: Mismatch between number of chunks ({num_chunks}) and generated embeddings ({len(dense_embeddings)} dense, {len(sparse_embeddings)} sparse).")
             # Handle this critical error, maybe return None or raise exception
             # For now, we'll proceed but this indicates a problem
             # Attempt to pad if lengths are mismatched (less ideal)
             hidden_size = getattr(getattr(self.model, 'model', None), 'config', None).hidden_size if hasattr(self.model, 'model') else 1024 # Default fallback size
             error_placeholder_dense = [0.0] * hidden_size
             error_placeholder_sparse = {}
             while len(dense_embeddings) < num_chunks: dense_embeddings.append(error_placeholder_dense)
             while len(sparse_embeddings) < num_chunks: sparse_embeddings.append(error_placeholder_sparse)
             dense_embeddings = dense_embeddings[:num_chunks]
             sparse_embeddings = sparse_embeddings[:num_chunks]


        # Add embeddings back to the original chunk dictionaries
        for i, chunk in enumerate(chunks):
            chunk["embeddings"] = {
                "dense": dense_embeddings[i],
                "sparse": sparse_embeddings[i] # Store sparse as dict {token_id: weight}
            }

        print("Finished generating embeddings.")
        return chunks

    def embed_query(self, query_text: str) -> Optional[Dict[str, Any]]:
        """
        Generates dense and sparse embeddings for a single query text.

        Args:
            query_text: The query string.

        Returns:
            A dictionary containing 'dense' and 'sparse' query embeddings,
            or None if embedding fails.
        """
        if not query_text:
            return None

        outputs = None # Initialize outputs
        try:
            # --- Wrap the encode call itself ---
            outputs = self.model.encode(
                [query_text], # Encode as a list with one item
                max_length=self.max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False
            )
            # --- End wrap ---

            # --- Enhanced checks and logging ---
            # This print might still not be reached if error is inside encode
            # print(f"DEBUG: Raw outputs from model.encode for query '{query_text}': {outputs}")

            if outputs is None: # Check if encode failed and returned None implicitly (though unlikely)
                 print(f"Error: model.encode returned None for query '{query_text}'")
                 return None

            dense_vecs = outputs.get("dense_vecs")
            lexical_weights = outputs.get("lexical_weights")

            # Explicitly check if the lists are None or empty
            if dense_vecs is None or len(dense_vecs) == 0:
                print(f"Error: Embedding model returned empty or None dense vectors for query: '{query_text}'. Dense vecs: {dense_vecs}")
                return None

            if lexical_weights is None or len(lexical_weights) == 0:
                print(f"Error: Embedding model returned empty or None lexical weights for query: '{query_text}'. Lexical weights: {lexical_weights}")
                return None
            # --- End enhanced checks ---

            # Proceed only if checks pass
            dense_vec = np.array(dense_vecs[0], dtype=np.float32).tolist()
            sparse_dict = lexical_weights[0] # Dictionary {token_id: weight}

            return {
                "dense": dense_vec,
                "sparse": sparse_dict
            }
        # --- Catch specific IndexError from encode() ---
        except IndexError as ie:
            print(f"CRITICAL: Caught IndexError directly from model.encode() for query '{query_text}'. Outputs variable state: {outputs}. Error: {ie}")
            # Also log the full traceback if possible, though print might be enough here
            import traceback
            traceback.print_exc()
            return None
        # --- Catch other potential exceptions ---
        except Exception as e:
            print(f"Error embedding query '{query_text}' during or after encode call: {e}")
            import traceback
            traceback.print_exc()
            return None
