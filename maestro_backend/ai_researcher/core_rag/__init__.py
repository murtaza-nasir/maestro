"""
Core RAG module initialization.

This module provides direct access to the vector store.
"""

# Import the PGVectorStore as VectorStore for backward compatibility
from .pgvector_store import PGVectorStore as VectorStore

# Make it available for import
__all__ = ['VectorStore']