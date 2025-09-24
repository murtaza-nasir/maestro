"""
API endpoints for research report versioning
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database.database import get_db
from database.models import User
from database import crud, crud_research_reports
from api.auth import get_current_user_from_cookie

router = APIRouter(prefix="/api", tags=["research_reports"])

class ResearchReportResponse(BaseModel):
    """Response model for research report"""
    id: str
    mission_id: str
    version: int
    title: Optional[str]
    content: str
    is_current: bool
    revision_notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

class ResearchReportListResponse(BaseModel):
    """Response model for list of research reports"""
    reports: List[ResearchReportResponse]
    current_version: int

class SetCurrentVersionRequest(BaseModel):
    """Request to set a specific version as current"""
    version: int

@router.get("/missions/{mission_id}/reports")
async def get_mission_reports(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get all research report versions for a mission."""
    # Verify mission ownership
    mission = crud.get_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    # Get the chat to verify ownership
    chat = crud.get_chat(db, mission.chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all report versions
    reports = crud_research_reports.get_all_research_reports(db, mission_id)
    
    # Find current version
    current_version = 1
    for report in reports:
        if report.is_current:
            current_version = report.version
            break
    
    return ResearchReportListResponse(
        reports=[
            ResearchReportResponse(
                id=str(report.id),
                mission_id=str(report.mission_id),
                version=report.version,
                title=report.title,
                content=report.content,
                is_current=report.is_current,
                revision_notes=report.revision_notes,
                created_at=report.created_at,
                updated_at=report.updated_at
            )
            for report in reports
        ],
        current_version=current_version
    )

@router.get("/missions/{mission_id}/reports/current")
async def get_current_report(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get the current research report for a mission."""
    # Verify mission ownership
    mission = crud.get_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    chat = crud.get_chat(db, mission.chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    report = crud_research_reports.get_current_research_report(db, mission_id)
    if not report:
        # Fall back to mission context if no versioned report exists
        if mission.mission_context and mission.mission_context.get('final_report'):
            return ResearchReportResponse(
                id="legacy",
                mission_id=mission_id,
                version=1,
                title=None,
                content=mission.mission_context['final_report'],
                is_current=True,
                revision_notes=None,
                created_at=mission.created_at,
                updated_at=mission.updated_at
            )
        raise HTTPException(status_code=404, detail="No report found for this mission")
    
    return ResearchReportResponse(
        id=str(report.id),
        mission_id=str(report.mission_id),
        version=report.version,
        title=report.title,
        content=report.content,
        is_current=report.is_current,
        revision_notes=report.revision_notes,
        created_at=report.created_at,
        updated_at=report.updated_at
    )

@router.get("/missions/{mission_id}/reports/{version}")
async def get_report_by_version(
    mission_id: str,
    version: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get a specific version of the research report."""
    # Verify mission ownership
    mission = crud.get_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    chat = crud.get_chat(db, mission.chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    report = crud_research_reports.get_research_report_by_version(db, mission_id, version)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report version {version} not found")
    
    return ResearchReportResponse(
        id=str(report.id),
        mission_id=str(report.mission_id),
        version=report.version,
        title=report.title,
        content=report.content,
        is_current=report.is_current,
        revision_notes=report.revision_notes,
        created_at=report.created_at,
        updated_at=report.updated_at
    )

@router.post("/missions/{mission_id}/reports/set-current")
async def set_current_version(
    mission_id: str,
    request: SetCurrentVersionRequest,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Set a specific version as the current research report."""
    # Verify mission ownership
    mission = crud.get_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    chat = crud.get_chat(db, mission.chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    report = crud_research_reports.set_current_research_report(db, mission_id, request.version)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report version {request.version} not found")
    
    return {
        "success": True,
        "message": f"Version {request.version} is now the current report",
        "current_version": request.version
    }

@router.delete("/missions/{mission_id}/reports/{version}")
async def delete_report_version(
    mission_id: str,
    version: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete a specific version of the research report."""
    # Verify mission ownership
    mission = crud.get_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    chat = crud.get_chat(db, mission.chat_id)
    if not chat or chat.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Don't allow deleting the only version
    all_reports = crud_research_reports.get_all_research_reports(db, mission_id)
    if len(all_reports) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only report version")
    
    success = crud_research_reports.delete_research_report_version(db, mission_id, version)
    if not success:
        raise HTTPException(status_code=404, detail=f"Report version {version} not found")
    
    return {
        "success": True,
        "message": f"Version {version} has been deleted"
    }