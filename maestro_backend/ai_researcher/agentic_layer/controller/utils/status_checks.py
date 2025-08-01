import logging
from functools import wraps
from typing import Callable, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

class MissionStoppedException(Exception):
    """Exception raised when a mission is stopped or paused during execution."""
    def __init__(self, mission_id: str, status: str):
        self.mission_id = mission_id
        self.status = status
        super().__init__(f"Mission {mission_id} is {status}")

def acheck_mission_status(func: Callable) -> Callable:
    """
    A decorator for async methods to check the mission status before execution.
    It assumes the decorated method is part of a class that has a 'controller'
    attribute, which in turn has a 'context_manager'.

    The decorated method's signature must include 'mission_id: str'.
    """
    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Optional[Any]:
        mission_id = kwargs.get("mission_id")
        if not mission_id:
            # Try to find mission_id in args if not in kwargs
            arg_names = func.__code__.co_varnames[:func.__code__.co_argcount]
            if 'mission_id' in arg_names:
                try:
                    mission_id_index = arg_names.index('mission_id')
                    # Adjust for 'self' being the first argument
                    if mission_id_index > 0:
                        mission_id = args[mission_id_index - 1]
                except (ValueError, IndexError):
                    pass # mission_id not found in args

        if not mission_id:
            logger.error(f"Decorator @acheck_mission_status on '{func.__name__}' could not find 'mission_id' in arguments. Executing function without check.")
            return await func(self, *args, **kwargs)

        try:
            # Access context_manager through self.controller
            context_manager = self.controller.context_manager
            mission_context = context_manager.get_mission_context(mission_id)

            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(
                    f"Mission {mission_id} is {mission_context.status}. "
                    f"Skipping execution of '{func.__name__}'."
                )
                # Return a value that indicates cancellation or inaction
                # For functions that return a boolean success flag, False is appropriate
                # For functions that return a list, an empty list is good.
                # Returning None is a safe default.
                return None
        except Exception as e:
            logger.error(f"Error checking mission status in decorator for '{func.__name__}': {e}", exc_info=True)
            # Decide whether to proceed or not. Proceeding might be safer.
            logger.warning(f"Proceeding with execution of '{func.__name__}' despite status check error.")

        return await func(self, *args, **kwargs)

    return wrapper

def check_mission_status_sync(controller, mission_id: str) -> bool:
    """
    Synchronous helper function to check if a mission should continue running.
    Returns True if mission should continue, False if stopped/paused.
    
    Args:
        controller: The controller instance with context_manager
        mission_id: The mission ID to check
        
    Returns:
        bool: True if mission should continue, False if stopped/paused
    """
    try:
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if mission_context and mission_context.status in ["stopped", "paused"]:
            logger.info(f"Mission {mission_id} is {mission_context.status}. Stopping execution.")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking mission status for {mission_id}: {e}", exc_info=True)
        # Return True to continue execution if status check fails
        return True

async def check_mission_status_async(controller, mission_id: str) -> bool:
    """
    Asynchronous helper function to check if a mission should continue running.
    Returns True if mission should continue, False if stopped/paused.
    
    Args:
        controller: The controller instance with context_manager
        mission_id: The mission ID to check
        
    Returns:
        bool: True if mission should continue, False if stopped/paused
    """
    try:
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if mission_context and mission_context.status in ["stopped", "paused"]:
            logger.info(f"Mission {mission_id} is {mission_context.status}. Stopping execution.")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking mission status for {mission_id}: {e}", exc_info=True)
        # Return True to continue execution if status check fails
        return True

def raise_if_mission_stopped(controller, mission_id: str) -> None:
    """
    Raises MissionStoppedException if the mission is stopped or paused.
    Use this in loops where you want to immediately exit on mission stop.
    
    Args:
        controller: The controller instance with context_manager
        mission_id: The mission ID to check
        
    Raises:
        MissionStoppedException: If mission is stopped or paused
    """
    try:
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if mission_context and mission_context.status in ["stopped", "paused"]:
            raise MissionStoppedException(mission_id, mission_context.status)
    except MissionStoppedException:
        raise  # Re-raise the mission stopped exception
    except Exception as e:
        logger.error(f"Error checking mission status for {mission_id}: {e}", exc_info=True)
        # Don't raise if status check fails, just log the error
