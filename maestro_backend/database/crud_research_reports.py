"""
CRUD operations for research report versioning
"""
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from database.models import ResearchReport, Mission
from datetime import datetime

logger = logging.getLogger(__name__)

def create_research_report(
    db: Session,
    mission_id: str,
    content: str,
    title: Optional[str] = None,
    revision_notes: Optional[str] = None,
    make_current: bool = True
) -> ResearchReport:
    """
    Create a new version of a research report for a mission.
    
    Args:
        db: Database session
        mission_id: ID of the mission
        content: Report content
        title: Optional title for the report
        revision_notes: Optional notes about what was revised
        make_current: Whether to mark this as the current version
    
    Returns:
        The created ResearchReport
    """
    try:
        # Get the next version number
        latest_report = db.query(ResearchReport).filter(
            ResearchReport.mission_id == mission_id
        ).order_by(desc(ResearchReport.version)).first()
        
        next_version = (latest_report.version + 1) if latest_report else 1
        
        # If making this current, unset current flag on other versions
        if make_current:
            db.query(ResearchReport).filter(
                and_(
                    ResearchReport.mission_id == mission_id,
                    ResearchReport.is_current == True
                )
            ).update({"is_current": False})
        
        # Create the new report version
        report = ResearchReport(
            mission_id=mission_id,
            version=next_version,
            title=title,
            content=content,
            revision_notes=revision_notes,
            is_current=make_current
        )
        
        db.add(report)
        
        # Update mission's current report version
        if make_current:
            mission = db.query(Mission).filter(Mission.id == mission_id).first()
            if mission:
                mission.current_report_version = next_version
        
        db.commit()
        db.refresh(report)
        
        logger.info(f"Created research report version {next_version} for mission {mission_id}")
        return report
        
    except Exception as e:
        logger.error(f"Failed to create research report: {e}")
        db.rollback()
        raise

def get_current_research_report(db: Session, mission_id: str) -> Optional[ResearchReport]:
    """
    Get the current version of the research report for a mission.
    
    Args:
        db: Database session
        mission_id: ID of the mission
    
    Returns:
        The current ResearchReport or None if not found
    """
    return db.query(ResearchReport).filter(
        and_(
            ResearchReport.mission_id == mission_id,
            ResearchReport.is_current == True
        )
    ).first()

def get_research_report_by_version(
    db: Session,
    mission_id: str,
    version: int
) -> Optional[ResearchReport]:
    """
    Get a specific version of the research report.
    
    Args:
        db: Database session
        mission_id: ID of the mission
        version: Version number
    
    Returns:
        The ResearchReport or None if not found
    """
    return db.query(ResearchReport).filter(
        and_(
            ResearchReport.mission_id == mission_id,
            ResearchReport.version == version
        )
    ).first()

def get_all_research_reports(
    db: Session,
    mission_id: str
) -> List[ResearchReport]:
    """
    Get all versions of research reports for a mission.
    
    Args:
        db: Database session
        mission_id: ID of the mission
    
    Returns:
        List of ResearchReport objects ordered by version (newest first)
    """
    return db.query(ResearchReport).filter(
        ResearchReport.mission_id == mission_id
    ).order_by(desc(ResearchReport.version)).all()

def set_current_research_report(
    db: Session,
    mission_id: str,
    version: int
) -> Optional[ResearchReport]:
    """
    Set a specific version as the current research report.
    
    Args:
        db: Database session
        mission_id: ID of the mission
        version: Version number to set as current
    
    Returns:
        The updated ResearchReport or None if not found
    """
    try:
        # First, unset current flag on all versions
        db.query(ResearchReport).filter(
            and_(
                ResearchReport.mission_id == mission_id,
                ResearchReport.is_current == True
            )
        ).update({"is_current": False})
        
        # Set the specified version as current
        report = db.query(ResearchReport).filter(
            and_(
                ResearchReport.mission_id == mission_id,
                ResearchReport.version == version
            )
        ).first()
        
        if report:
            report.is_current = True
            
            # Update mission's current report version
            mission = db.query(Mission).filter(Mission.id == mission_id).first()
            if mission:
                mission.current_report_version = version
            
            db.commit()
            db.refresh(report)
            logger.info(f"Set research report version {version} as current for mission {mission_id}")
        
        return report
        
    except Exception as e:
        logger.error(f"Failed to set current research report: {e}")
        db.rollback()
        raise

def update_research_report_content(
    db: Session,
    mission_id: str,
    version: int,
    content: str,
    title: Optional[str] = None
) -> Optional[ResearchReport]:
    """
    Update the content of a specific research report version.
    
    Args:
        db: Database session
        mission_id: ID of the mission
        version: Version number to update
        content: New content
        title: Optional new title
    
    Returns:
        The updated ResearchReport or None if not found
    """
    try:
        report = db.query(ResearchReport).filter(
            and_(
                ResearchReport.mission_id == mission_id,
                ResearchReport.version == version
            )
        ).first()
        
        if report:
            report.content = content
            if title is not None:
                report.title = title
            report.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(report)
            logger.info(f"Updated research report version {version} for mission {mission_id}")
        
        return report
        
    except Exception as e:
        logger.error(f"Failed to update research report: {e}")
        db.rollback()
        raise

def delete_research_report_version(
    db: Session,
    mission_id: str,
    version: int
) -> bool:
    """
    Delete a specific version of a research report.
    
    Args:
        db: Database session
        mission_id: ID of the mission
        version: Version number to delete
    
    Returns:
        True if deleted, False if not found
    """
    try:
        report = db.query(ResearchReport).filter(
            and_(
                ResearchReport.mission_id == mission_id,
                ResearchReport.version == version
            )
        ).first()
        
        if report:
            # If deleting current version, make the previous version current
            if report.is_current:
                prev_report = db.query(ResearchReport).filter(
                    and_(
                        ResearchReport.mission_id == mission_id,
                        ResearchReport.version < version
                    )
                ).order_by(desc(ResearchReport.version)).first()
                
                if prev_report:
                    prev_report.is_current = True
                    mission = db.query(Mission).filter(Mission.id == mission_id).first()
                    if mission:
                        mission.current_report_version = prev_report.version
            
            db.delete(report)
            db.commit()
            logger.info(f"Deleted research report version {version} for mission {mission_id}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to delete research report: {e}")
        db.rollback()
        raise