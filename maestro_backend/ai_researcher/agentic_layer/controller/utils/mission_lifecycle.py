"""
Mission lifecycle management utilities.
Provides centralized control over mission execution threads and cleanup.
"""

import asyncio
import logging
import threading
from typing import Dict, Optional, Set
from concurrent.futures import Future
import weakref

logger = logging.getLogger(__name__)


class MissionLifecycleManager:
    """
    Manages the lifecycle of mission execution threads.
    Ensures missions can be properly stopped and cleaned up.
    """
    
    def __init__(self):
        # Track running mission threads
        self._mission_threads: Dict[str, threading.Thread] = {}
        # Track mission futures for cancellation
        self._mission_futures: Dict[str, Future] = {}
        # Track mission event loops
        self._mission_loops: Dict[str, asyncio.AbstractEventLoop] = {}
        # Lock for thread-safe operations
        self._lock = threading.Lock()
        
    def register_mission_thread(self, mission_id: str, thread: threading.Thread) -> None:
        """Register a thread running a mission."""
        with self._lock:
            self._mission_threads[mission_id] = thread
            logger.info(f"Registered thread for mission {mission_id}")
    
    def register_mission_loop(self, mission_id: str, loop: asyncio.AbstractEventLoop) -> None:
        """Register the event loop for a mission."""
        with self._lock:
            self._mission_loops[mission_id] = loop
            logger.info(f"Registered event loop for mission {mission_id}")
    
    def register_mission_future(self, mission_id: str, future: Future) -> None:
        """Register a future for a mission."""
        with self._lock:
            self._mission_futures[mission_id] = future
            logger.info(f"Registered future for mission {mission_id}")
    
    def stop_mission(self, mission_id: str) -> bool:
        """
        Stop a running mission by:
        1. Cancelling its future
        2. Stopping its event loop
        3. Interrupting its thread
        Returns True if mission was stopped, False if not found.
        """
        with self._lock:
            stopped = False
            
            # Cancel the future if it exists
            if mission_id in self._mission_futures:
                future = self._mission_futures[mission_id]
                if not future.done():
                    future.cancel()
                    logger.info(f"Cancelled future for mission {mission_id}")
                del self._mission_futures[mission_id]
                stopped = True
            
            # Stop the event loop if it exists
            if mission_id in self._mission_loops:
                loop = self._mission_loops[mission_id]
                if loop.is_running():
                    # Schedule loop stop from within the loop
                    loop.call_soon_threadsafe(loop.stop)
                    logger.info(f"Scheduled stop for event loop of mission {mission_id}")
                del self._mission_loops[mission_id]
                stopped = True
            
            # Note: We don't forcefully terminate threads as it's unsafe in Python
            # The thread should check mission status and exit gracefully
            if mission_id in self._mission_threads:
                thread = self._mission_threads[mission_id]
                if thread.is_alive():
                    logger.warning(f"Thread for mission {mission_id} is still alive. It should exit on next status check.")
                del self._mission_threads[mission_id]
                stopped = True
            
            return stopped
    
    def cleanup_mission(self, mission_id: str) -> None:
        """
        Clean up all resources for a mission.
        Called when mission completes or is deleted.
        """
        with self._lock:
            # Remove from all tracking dicts
            self._mission_futures.pop(mission_id, None)
            self._mission_loops.pop(mission_id, None)
            self._mission_threads.pop(mission_id, None)
            logger.info(f"Cleaned up resources for mission {mission_id}")
    
    def is_mission_running(self, mission_id: str) -> bool:
        """Check if a mission is currently running."""
        with self._lock:
            # Check if thread exists and is alive
            if mission_id in self._mission_threads:
                thread = self._mission_threads[mission_id]
                return thread.is_alive()
            return False
    
    def get_running_missions(self) -> Set[str]:
        """Get set of currently running mission IDs."""
        with self._lock:
            return {
                mission_id 
                for mission_id, thread in self._mission_threads.items() 
                if thread.is_alive()
            }
    
    def stop_all_missions(self) -> int:
        """
        Stop all running missions.
        Returns count of missions stopped.
        """
        with self._lock:
            mission_ids = list(self._mission_threads.keys())
            
        stopped_count = 0
        for mission_id in mission_ids:
            if self.stop_mission(mission_id):
                stopped_count += 1
        
        logger.info(f"Stopped {stopped_count} missions")
        return stopped_count


# Global instance
_lifecycle_manager = MissionLifecycleManager()


def get_lifecycle_manager() -> MissionLifecycleManager:
    """Get the global lifecycle manager instance."""
    return _lifecycle_manager