import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import asyncio # Import asyncio for async tests
import sys
import logging
from typing import List, Dict, Any, Optional

# Add project root to sys.path for imports
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import the components to be tested/mocked
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.vector_store import VectorStore
from ai_researcher.core_rag.retriever import Retriever
# from ai_researcher.core_rag.reranker import TextReranker # Import if testing reranker integration

# --- Logging ---
# Configure logging for tests if desired (optional)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_retriever")

# --- Test Data & Mocks ---
MOCK_QUERY = "collaboration in palliative care"
MOCK_DENSE_EMBEDDING = [0.1] * 1024 # Example dimension for BGE-M3 dense
MOCK_SPARSE_EMBEDDING_DICT = {10: 0.5, 50: 0.8, 1000: 0.3} # Example sparse dict

# Mock VectorStore query results
MOCK_VS_RESULTS = [
    {'id': 'doc1_0', 'text': 'Details about collaboration...', 'metadata': {'doc_id': 'doc1', 'chunk_id': 0, 'title': 'Doc One'}, 'score': 0.85},
    {'id': 'doc2_5', 'text': 'Palliative care challenges...', 'metadata': {'doc_id': 'doc2', 'chunk_id': 5, 'title': 'Doc Two'}, 'score': 0.75},
    {'id': 'doc1_1', 'text': 'More collaboration details...', 'metadata': {'doc_id': 'doc1', 'chunk_id': 1, 'title': 'Doc One'}, 'score': 0.70},
]

# Use unittest.IsolatedAsyncioTestCase for async tests
class TestRetriever(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up mocked components before each test."""
        logger.info("Setting up TestRetriever...")

        # Mock Embedder
        self.mock_embedder = MagicMock(spec=TextEmbedder)
        # Configure the mock embed_query to return our predefined embeddings
        self.mock_embedder.embed_query.return_value = {
            "dense": MOCK_DENSE_EMBEDDING,
            "sparse": MOCK_SPARSE_EMBEDDING_DICT
        }
        logger.info("Mock Embedder configured.")

        # Mock VectorStore
        self.mock_vector_store = MagicMock(spec=VectorStore)
        # Configure the mock query to return predefined results
        self.mock_vector_store.query.return_value = MOCK_VS_RESULTS
        logger.info("Mock VectorStore configured.")

        # Mock Reranker (Optional - set to None for basic test)
        self.mock_reranker = None
        # If testing reranker:
        # self.mock_reranker = MagicMock(spec=TextReranker)
        # self.mock_reranker.rerank.return_value = MOCK_VS_RESULTS[:2] # Simulate reranker returning top 2

        # Instantiate Retriever with mocks
        self.retriever = Retriever(
            embedder=self.mock_embedder,
            vector_store=self.mock_vector_store,
            reranker=self.mock_reranker
        )
        logger.info("Retriever initialized with mocks.")

    async def test_retrieve_basic_query_no_reranker(self):
        """Test basic retrieval without using the reranker."""
        logger.info("Running test_retrieve_basic_query_no_reranker...")
        n_results_requested = 2

        # Await the async call
        results = await self.retriever.retrieve(
            query_text=MOCK_QUERY,
            n_results=n_results_requested,
            use_reranker=False # Explicitly disable reranker for this test
        )

        # Assertions
        self.assertIsNotNone(results, "Retriever returned None.")
        self.assertIsInstance(results, list, "Retriever did not return a list.")
        self.assertEqual(len(results), n_results_requested, f"Expected {n_results_requested} results, got {len(results)}.")

        # Check if embedder was called correctly
        self.mock_embedder.embed_query.assert_called_once_with(MOCK_QUERY)

        # Check if vector store was called correctly (without reranker, fetch n_results)
        self.mock_vector_store.query.assert_called_once()
        call_args, call_kwargs = self.mock_vector_store.query.call_args
        self.assertEqual(call_kwargs.get('query_dense_embedding'), MOCK_DENSE_EMBEDDING)
        self.assertEqual(call_kwargs.get('query_sparse_embedding_dict'), MOCK_SPARSE_EMBEDDING_DICT)
        self.assertEqual(call_kwargs.get('n_results'), n_results_requested) # Fetch n_results when no reranker
        self.assertIsNone(call_kwargs.get('filter_metadata')) # No filter applied in this test

        # Check content of results (based on mock data)
        self.assertEqual(results[0]['id'], MOCK_VS_RESULTS[0]['id'])
        self.assertEqual(results[1]['id'], MOCK_VS_RESULTS[1]['id'])
        self.assertEqual(results[0]['metadata']['title'], 'Doc One')

        logger.info("test_retrieve_basic_query_no_reranker finished successfully.")

    # Add more tests here, e.g., testing with reranker enabled, testing with filters, testing edge cases (no results)

    # Example test with reranker (requires setting up self.mock_reranker in setUp)
    # @unittest.skip("Enable when reranker mock is configured")
    # def test_retrieve_with_reranker(self):
    #     logger.info("Running test_retrieve_with_reranker...")
    #     n_results_requested = 2
    #     initial_fetch_n = n_results_requested * 3 # As per retriever logic

    #     # Configure reranker mock for this test
    #     self.mock_reranker = MagicMock(spec=TextReranker)
    #     reranked_results = MOCK_VS_RESULTS[:n_results_requested] # Simulate reranker returning top N
    #     self.mock_reranker.rerank.return_value = reranked_results
    #     # Re-initialize retriever with the reranker mock
    #     self.retriever = Retriever(
    #         embedder=self.mock_embedder,
    #         vector_store=self.mock_vector_store,
    #         reranker=self.mock_reranker
    #     )

    #     results = self.retriever.retrieve(
    #         query_text=MOCK_QUERY,
    #         n_results=n_results_requested,
    #         use_reranker=True
    #     )

    #     self.assertIsNotNone(results)
    #     self.assertEqual(len(results), n_results_requested)
    #     self.mock_embedder.embed_query.assert_called_once_with(MOCK_QUERY)
    #     # Check vector store called to fetch MORE results initially
    #     self.mock_vector_store.query.assert_called_once()
    #     call_args, call_kwargs = self.mock_vector_store.query.call_args
    #     self.assertEqual(call_kwargs.get('n_results'), initial_fetch_n)
    #     # Check reranker was called
    #     self.mock_reranker.rerank.assert_called_once_with(MOCK_QUERY, MOCK_VS_RESULTS, top_n=n_results_requested)
    #     # Check final results match reranked results
    #     self.assertEqual(results[0]['id'], reranked_results[0]['id'])
    #     self.assertEqual(results[1]['id'], reranked_results[1]['id'])

    #     logger.info("test_retrieve_with_reranker finished successfully.")


if __name__ == '__main__':
    unittest.main()
