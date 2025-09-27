"""
Async Task Manager for handling cancellable async operations in mission execution.
Provides centralized management of async tasks with proper cancellation support.
"""

import asyncio
import logging
from typing import Dict, Set, Optional, List, Any
from contextlib import asynccontextmanager
import weakref

logger = logging.getLogger(__name__)


class AsyncTaskManager:
    """
    Manages async tasks for missions with proper cancellation support.
    """
    
    def __init__(self):
        # Use weak references to avoid memory leaks
        self._mission_tasks: Dict[str, Set[weakref.ref]] = {}
        self._lock = asyncio.Lock()
        
    async def register_task(self, mission_id: str, task: asyncio.Task) -> None:
        """Register a task for a mission."""
        async with self._lock:
            if mission_id not in self._mission_tasks:
                self._mission_tasks[mission_id] = set()
            
            # Create weak reference to the task
            task_ref = weakref.ref(task, lambda ref: self._cleanup_task_ref(mission_id, ref))
            self._mission_tasks[mission_id].add(task_ref)
            logger.debug(f"Registered task for mission {mission_id}: {task.get_name()}")
    
    def _cleanup_task_ref(self, mission_id: str, task_ref: weakref.ref):
        """Clean up dead task references."""
        if mission_id in self._mission_tasks:
            self._mission_tasks[mission_id].discard(task_ref)
            if not self._mission_tasks[mission_id]:
                del self._mission_tasks[mission_id]
    
    async def cancel_mission_tasks(self, mission_id: str) -> int:
        """
        Cancel all tasks for a mission.
        Returns the number of tasks cancelled.
        """
        async with self._lock:
            if mission_id not in self._mission_tasks:
                logger.info(f"No tasks to cancel for mission {mission_id}")
                return 0
            
            cancelled_count = 0
            task_refs = list(self._mission_tasks.get(mission_id, set()))
            
            for task_ref in task_refs:
                task = task_ref()
                if task and not task.done():
                    task.cancel()
                    cancelled_count += 1
                    logger.debug(f"Cancelled task {task.get_name()} for mission {mission_id}")
            
            # Clean up the mission entry
            if mission_id in self._mission_tasks:
                del self._mission_tasks[mission_id]
            
            logger.info(f"Cancelled {cancelled_count} tasks for mission {mission_id}")
            return cancelled_count
    
    async def create_cancellable_task(self, mission_id: str, coro) -> asyncio.Task:
        """
        Create a task that will be automatically cancelled if the mission is paused/stopped.
        """
        task = asyncio.create_task(coro)
        await self.register_task(mission_id, task)
        return task
    
    async def gather_cancellable(self, mission_id: str, *coros, return_exceptions: bool = False):
        """
        Wrapper around asyncio.gather that makes all tasks cancellable.
        """
        tasks = []
        for coro in coros:
            task = await self.create_cancellable_task(mission_id, coro)
            tasks.append(task)
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=return_exceptions)
            return results
        except asyncio.CancelledError:
            logger.info(f"Gather operation cancelled for mission {mission_id}")
            # Cancel any remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise
    
    @asynccontextmanager
    async def mission_scope(self, mission_id: str):
        """
        Context manager for mission execution that ensures cleanup on exit.
        """
        try:
            yield self
        finally:
            # Cancel all remaining tasks for this mission
            await self.cancel_mission_tasks(mission_id)
    
    def get_active_task_count(self, mission_id: str) -> int:
        """Get count of active tasks for a mission."""
        if mission_id not in self._mission_tasks:
            return 0
        
        count = 0
        for task_ref in self._mission_tasks[mission_id]:
            task = task_ref()
            if task and not task.done():
                count += 1
        return count


# Global instance
_task_manager = AsyncTaskManager()


def get_task_manager() -> AsyncTaskManager:
    """Get the global task manager instance."""
    return _task_manager