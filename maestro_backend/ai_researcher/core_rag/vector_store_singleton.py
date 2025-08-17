"""
Singleton wrapper for PGVectorStore to ensure consistent access across the application.

This module provides a singleton instance of PGVectorStore to ensure
consistent database access throughout the application.
"""

import threading
from typing import Optional
from .pgvector_store import PGVectorStore as VectorStore
import logging

logger = logging.getLogger(__name__)

class VectorStoreSingleton:
    """Singleton manager for VectorStore instance."""
    
    _instance: Optional[VectorStore] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> VectorStore:
        """
        Get the singleton VectorStore instance.
        
        Returns:
            The singleton VectorStore instance
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check pattern
                if cls._instance is None:
                    logger.info("Creating new PGVectorStore singleton instance (PostgreSQL with pgvector)")
                    cls._instance = VectorStore()
                else:
                    logger.debug("Returning existing PGVectorStore singleton instance")
        else:
            logger.debug("Returning existing PGVectorStore singleton instance (no lock)")
        
        return cls._instance
    
    @classmethod
    def reset(cls):
        """
        Reset the singleton instance.
        Only use this for testing or when you need to force a reconnection.
        """
        with cls._lock:
            if cls._instance is not None:
                logger.warning("Resetting PGVectorStore singleton instance")
                cls._instance = None

# Convenience function for easy import
def get_vector_store() -> VectorStore:
    """
    Get the singleton VectorStore instance.
    
    This is the preferred way to get a VectorStore instance throughout
    the application to ensure consistency.
    
    Returns:
        The singleton VectorStore instance
    """
    return VectorStoreSingleton.get_instance()

# Export the main function
__all__ = ['get_vector_store', 'VectorStoreSingleton']