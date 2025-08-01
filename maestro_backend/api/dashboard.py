from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from database.database import get_db
from database import crud
from api.schemas import DashboardStats
from auth.dependencies import get_current_user_from_cookie
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics for the current user."""
    try:
        # Get stats from database
        stats_data = crud.get_dashboard_stats(db, current_user.id)
        
        # Create response model
        dashboard_stats = DashboardStats(
            total_chats=stats_data["total_chats"],
            total_documents=stats_data["total_documents"],
            total_writing_sessions=stats_data["total_writing_sessions"],
            total_missions=stats_data["total_missions"],
            recent_activity=stats_data["recent_activity"],
            research_sessions=stats_data["research_sessions"],
            writing_sessions=stats_data["writing_sessions"],
            completed_missions=stats_data["completed_missions"],
            active_missions=stats_data["active_missions"]
        )
        
        logger.info(f"Retrieved dashboard stats for user {current_user.id}: {stats_data}")
        return dashboard_stats
        
    except Exception as e:
        logger.error(f"Failed to get dashboard stats for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard statistics"
        )
