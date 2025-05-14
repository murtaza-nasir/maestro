import os
import threading # Import the threading module
from typing import List, Dict, Any, Optional, Tuple
import torch
from FlagEmbedding import FlagReranker
from tqdm import tqdm

class TextReranker:
    """
    Reranks search results using a cross-encoder model (e.g., BGE-Reranker).
    """
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3", # Default BGE reranker
        device: Optional[str] = None,
        batch_size: int = 32 # Adjust based on GPU memory and model
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

        print(f"Initializing TextReranker with model {self.model_name} on device {self.device}")
        try:
            # Initialize the FlagReranker model
            # use_fp16=True is recommended on GPU
            self.model = FlagReranker(self.model_name, use_fp16=(self.device == "cuda"))
            print("Reranker model loaded successfully.")
        except Exception as e:
            print(f"Error loading reranker model {self.model_name}: {e}")
            self.model = None # Indicate failure
            # Optionally raise

        # Add a lock for thread safety
        self._lock = threading.Lock()

    def rerank(self, query: str, results: List[Any], top_n: Optional[int] = None) -> List[Tuple[float, Any]]:
        """
        Reranks a list of retrieved documents based on their relevance to the query.

        Args:
            query: The original search query string.
            results: A list of items to rerank. Can be dictionaries with a 'text' key,
                    Pydantic models with a 'content' field (like Note objects), or other objects
                    that can be converted to strings.
            top_n: The maximum number of results to return after reranking. If None, returns all reranked results.

        Returns:
            A list of tuples (score, item) sorted by score in descending order, potentially truncated to top_n.
            Each tuple contains the reranking score (float) and the original item from the results list.
            If reranking fails, returns the original items with default scores of 0.0.
        """
        if not self.model:
            print("Warning: Reranker model not loaded. Returning original results order with default scores.")
            return [(0.0, result) for result in results]
        if not results:
            return []
        if not query:
             print("Warning: Empty query provided for reranking. Returning original results with default scores.")
             return [(0.0, result) for result in results]

        print(f"Reranking {len(results)} results for query: '{query}'...")

        # Prepare pairs for the reranker: [query, document_text]
        # Handle both dictionary results and Pydantic models like Note
        pairs = []
        for result in results:
            if hasattr(result, 'model_fields') and hasattr(result, 'content'):
                # This is likely a Pydantic model like Note with a 'content' field
                document_text = result.content
            elif isinstance(result, dict):
                # This is a dictionary with a 'text' key
                document_text = result.get("text", "")
            else:
                # Try to get a string representation as fallback
                document_text = str(result)
            pairs.append([query, document_text])

        all_scores = []
        try:
            # Acquire the lock before accessing the shared model
            with self._lock:
                # Compute scores in batches
                with torch.no_grad(): # Ensure no gradients are computed
                     for i in tqdm(range(0, len(pairs), self.batch_size), desc="Reranking"):
                          batch_pairs = pairs[i : i + self.batch_size]
                          # Compute scores for the batch
                          # This part is now protected by the lock
                          scores = self.model.compute_score(batch_pairs, normalize=True) # Normalize scores (optional, often 0-1)

                          # Ensure scores is always treated as a list-like structure of individual scores
                          processed_scores = []
                          if isinstance(scores, list):
                               processed_scores = scores
                          else:
                               # Attempt to convert common return types (numpy array, torch tensor) to list
                               try:
                                    processed_scores = scores.tolist() # Common method for numpy/torch
                               except AttributeError:
                                    # If it's a single scalar value, wrap it in a list
                                    if isinstance(scores, (int, float)):
                                         processed_scores = [scores]
                                    else:
                                         # If conversion fails and it's not a scalar, log an error
                                         print(f"Error: Unexpected return type from reranker compute_score: {type(scores)}. Cannot process scores for this batch.")
                                         # Skip extending for this batch if type is unknown
                                         continue # This is now correctly inside the loop

                          all_scores.extend(processed_scores)

        except Exception as e:
             print(f"Error during reranking computation: {e}")
             # Fallback: return original results with default scores if reranking fails critically
             return [(0.0, result) for result in results]

        # Check if scores length matches results length
        if len(all_scores) != len(results):
             print(f"Warning: Mismatch between number of results ({len(results)}) and computed reranker scores ({len(all_scores)}). Returning original results with default scores.")
             return [(0.0, result) for result in results]


        # Create a list of (score, result) tuples
        scored_results = list(zip(all_scores, results))
        
        # Sort by score in descending order
        reranked_results = sorted(scored_results, key=lambda x: x[0], reverse=True)
        
        print(f"Reranking complete. Top score: {reranked_results[0][0]:.4f}" if reranked_results else "Reranking complete. No results.")
        
        # Return top N if specified
        if top_n is not None:
            return reranked_results[:top_n]
        else:
            return reranked_results
