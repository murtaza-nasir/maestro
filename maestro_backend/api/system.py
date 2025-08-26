from fastapi import APIRouter, Depends, HTTPException, Request
import logging
import time
import psutil
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from api.schemas import SystemStatus
from auth.dependencies import get_current_user_from_cookie
from database.models import User
from database.database import get_db
from api.locales import get_message

logger = logging.getLogger(__name__)

router = APIRouter()

# Track when the system started
_start_time = time.time()

@router.get("/status", response_model=SystemStatus)
async def get_system_status(fastapi_request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    """Get the current system status and health information."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        # Calculate uptime
        uptime_seconds = time.time() - _start_time
        uptime_delta = timedelta(seconds=int(uptime_seconds))
        uptime_str = str(uptime_delta)
        
        # Check component status
        components = {
            "database": get_message("system.healthy", lang),
            "authentication": get_message("system.healthy", lang),
            "ai_researcher": get_message("system.healthy", lang),
            "context_manager": get_message("system.healthy", lang)
        }
        
        # Try to import and check AI components
        try:
            from ai_researcher.agentic_layer.context_manager import ContextManager
            from ai_researcher.agentic_layer.agent_controller import AgentController
            components["ai_researcher"] = get_message("system.healthy", lang)
        except Exception as e:
            logger.warning(f"AI researcher components not available: {e}")
            components["ai_researcher"] = get_message("system.unavailable", lang)
        
        # Check database connection
        try:
            from database.database import engine
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            components["database"] = get_message("system.healthy", lang)
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            components["database"] = get_message("system.unhealthy", lang)
        
        # Determine overall status
        overall_status = get_message("system.healthy", lang)
        if any(status == get_message("system.unhealthy", lang) for status in components.values()):
            overall_status = get_message("system.unhealthy", lang)
        elif any(status == get_message("system.unavailable", lang) for status in components.values()):
            overall_status = get_message("system.degraded", lang)
        
        return SystemStatus(
            status=overall_status,
            version="2.0.0-alpha",
            components=components,
            uptime=uptime_str
        )
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}", exc_info=True)
        return SystemStatus(
            status=get_message("system.error", lang),
            version="2.0.0-alpha",
            components={"error": get_message("system.failedToCheckComponents", lang)},
            uptime=get_message("system.unknown", lang)
        )

@router.post("/consistency-check")
async def trigger_consistency_check(
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """
    Manually trigger a system-wide consistency check.
    Only available to admin users.
    """
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    # Check if user is admin
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail=get_message("system.adminOnly", lang))
    
    try:
        from services.simple_consistency_checker import run_consistency_check
        
        logger.info(f"Admin {current_user.username} triggered consistency check")
        result = await run_consistency_check(db)
        
        return {
            "status": "success",
            "message": get_message("system.consistencyCheckCompleted", lang),
            "result": result
        }
    except Exception as e:
        logger.error(f"Error running consistency check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/consistency-check/document/{doc_id}")
async def check_document_consistency(
    doc_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """
    Check consistency for a single document.
    Users can only check their own documents.
    """
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        from services.simple_consistency_checker import check_single_document
        
        # Check document ownership unless admin
        if not current_user.is_admin:
            from database import crud
            doc = crud.get_document(db, doc_id, current_user.id)
            if not doc:
                raise HTTPException(status_code=404, detail=get_message("system.docNotFoundOrAccessDenied", lang))
        
        result = await check_single_document(db, doc_id, 
                                            user_id=None if current_user.is_admin else current_user.id)
        
        return {
            "status": "success",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking document consistency: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/consistency-check/user/{user_id}")
async def check_user_consistency(
    user_id: int,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """
    Check consistency for all documents of a user.
    Users can only check their own documents unless they're admin.
    """
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    # Check authorization
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail=get_message("system.accessDenied", lang))
    
    try:
        from services.simple_consistency_checker import check_user_consistency
        
        result = await check_user_consistency(db, user_id)
        
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error checking user consistency: {e}")
        raise HTTPException(status_code=500, detail=str(e))
