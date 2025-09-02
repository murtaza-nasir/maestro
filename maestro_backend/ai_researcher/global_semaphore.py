"""
Global semaphore for limiting concurrent requests to LLM endpoints.
This ensures we don't overwhelm the VLLM server regardless of how many users/chats are active.
"""

import asyncio
import os
import logging
from weakref import WeakKeyDictionary

logger = logging.getLogger(__name__)

# Store semaphores per event loop to avoid "bound to different event loop" errors
# Using WeakKeyDictionary so semaphores are cleaned up when event loops are destroyed
_semaphores_by_loop = WeakKeyDictionary()

def get_global_llm_semaphore(max_concurrent: int = None) -> asyncio.Semaphore:
    """
    Get or create the global LLM semaphore for the current event loop.
    
    Args:
        max_concurrent: Maximum concurrent requests. If not provided, uses env var or default.
    
    Returns:
        The global semaphore instance for the current event loop
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, create a new semaphore without binding to any loop
        # This will bind to the loop when first used
        if max_concurrent is None:
            max_concurrent = int(os.getenv("GLOBAL_MAX_CONCURRENT_LLM_REQUESTS", "200"))
        return asyncio.Semaphore(max_concurrent)
    
    # Check if we already have a semaphore for this loop
    if loop not in _semaphores_by_loop:
        # If max_concurrent not provided, get from environment or use default
        if max_concurrent is None:
            max_concurrent = int(os.getenv("GLOBAL_MAX_CONCURRENT_LLM_REQUESTS", "200"))  # Higher default to prevent bottlenecks
        
        _semaphores_by_loop[loop] = asyncio.Semaphore(max_concurrent)
        logger.info(f"Created global LLM semaphore for loop {id(loop)} with limit: {max_concurrent}")
    
    return _semaphores_by_loop[loop]

def reset_global_semaphore():
    """Reset all global semaphores (mainly for testing)."""
    global _semaphores_by_loop
    _semaphores_by_loop.clear()
    logger.info("Reset all global LLM semaphores")