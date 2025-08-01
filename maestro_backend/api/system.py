from fastapi import APIRouter, Depends
import logging
import time
import psutil
from datetime import datetime, timedelta

from api.schemas import SystemStatus
from auth.dependencies import get_current_user_from_cookie
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

# Track when the system started
_start_time = time.time()

@router.get("/status", response_model=SystemStatus)
async def get_system_status(current_user: User = Depends(get_current_user_from_cookie)):
    """Get the current system status and health information."""
    try:
        # Calculate uptime
        uptime_seconds = time.time() - _start_time
        uptime_delta = timedelta(seconds=int(uptime_seconds))
        uptime_str = str(uptime_delta)
        
        # Check component status
        components = {
            "database": "healthy",
            "authentication": "healthy",
            "ai_researcher": "healthy",
            "context_manager": "healthy"
        }
        
        # Try to import and check AI components
        try:
            from ai_researcher.agentic_layer.context_manager import ContextManager
            from ai_researcher.agentic_layer.agent_controller import AgentController
            components["ai_researcher"] = "healthy"
        except Exception as e:
            logger.warning(f"AI researcher components not available: {e}")
            components["ai_researcher"] = "unavailable"
        
        # Check database connection
        try:
            from database.database import engine
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            components["database"] = "healthy"
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            components["database"] = "unhealthy"
        
        # Determine overall status
        overall_status = "healthy"
        if any(status == "unhealthy" for status in components.values()):
            overall_status = "unhealthy"
        elif any(status == "unavailable" for status in components.values()):
            overall_status = "degraded"
        
        return SystemStatus(
            status=overall_status,
            version="2.0.0-alpha",
            components=components,
            uptime=uptime_str
        )
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}", exc_info=True)
        return SystemStatus(
            status="error",
            version="2.0.0-alpha",
            components={"error": "Failed to check components"},
            uptime="unknown"
        )
