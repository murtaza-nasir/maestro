from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

from database.database import get_db
from database import models, crud
from api import schemas
from auth.dependencies import get_current_user_from_cookie
from services.document_service import DocumentService
from services.reference_service import ReferenceService
from services.chat_title_service import ChatTitleService
from ai_researcher.agentic_layer.controller.writing_controller import WritingController
from ai_researcher.agentic_layer.agents.simplified_writing_agent import SimplifiedWritingAgent
from ai_researcher.user_context import set_current_user
from ai_researcher.dynamic_config import get_writing_mode_doc_results, get_writing_mode_web_results

router = APIRouter(prefix="/api/writing", tags=["writing"])


@router.get("/sessions", response_model=List[schemas.WritingSessionWithChat])
async def get_writing_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get all writing sessions for the current user."""
    
    # Get all writing sessions for the user through chat ownership
    writing_sessions = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.Chat.user_id == current_user.id
    ).order_by(models.WritingSession.updated_at.desc()).all()
    
    # Convert to response model with chat information
    result = []
    for session in writing_sessions:
        chat = db.query(models.Chat).filter(models.Chat.id == session.chat_id).first()
        
        # Get document group name if exists
        doc_group_name = None
        if session.document_group_id:
            doc_group = db.query(models.DocumentGroup).filter(
                models.DocumentGroup.id == session.document_group_id
            ).first()
            if doc_group:
                doc_group_name = doc_group.name
        
        session_data = schemas.WritingSessionWithChat(
            id=session.id,
            name=chat.title if chat else "Untitled Session",
            chat_id=session.chat_id,
            document_group_id=session.document_group_id,
            document_group_name=doc_group_name,
            web_search_enabled=session.use_web_search,
            current_draft_id=session.current_draft_id,
            settings=session.settings,
            created_at=session.created_at,
            updated_at=session.updated_at
        )
        result.append(session_data)
    
    return result

@router.post("/chats", response_model=schemas.Chat)
async def create_writing_chat(
    chat_data: schemas.ChatCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Create a new chat specifically for writing sessions."""
    try:
        chat_id = str(uuid.uuid4())
        
        # Create a writing-specific chat
        db_chat = models.Chat(
            id=chat_id,
            user_id=current_user.id,
            title=chat_data.title,
            chat_type="writing",  # Set chat type to writing
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(db_chat)
        db.commit()
        db.refresh(db_chat)
        
        logger.info(f"Created new writing chat {chat_id} for user {current_user.username}")
        return db_chat
        
    except Exception as e:
        logger.error(f"Error creating writing chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create writing chat: {str(e)}"
        )

@router.post("/sessions", response_model=schemas.WritingSession)
async def create_writing_session(
    session_data: schemas.WritingSessionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Create a new writing session."""
    
    # Verify the chat belongs to the current user and is a writing chat
    chat = db.query(models.Chat).filter(
        models.Chat.id == session_data.chat_id,
        models.Chat.user_id == current_user.id,
        models.Chat.chat_type == "writing"
    ).first()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing chat not found or access denied"
        )
    
    # Verify document group belongs to user if specified
    if session_data.document_group_id:
        doc_group = db.query(models.DocumentGroup).filter(
            models.DocumentGroup.id == session_data.document_group_id,
            models.DocumentGroup.user_id == current_user.id
        ).first()
        
        if not doc_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document group not found or access denied"
            )
    
    # Check if writing session already exists for this chat
    existing_session = db.query(models.WritingSession).filter(
        models.WritingSession.chat_id == session_data.chat_id
    ).first()
    
    if existing_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Writing session already exists for this chat"
        )
    
    # Create new writing session
    writing_session = models.WritingSession(
        id=str(uuid.uuid4()),
        chat_id=session_data.chat_id,
        document_group_id=session_data.document_group_id,
        use_web_search=session_data.use_web_search,
        settings=session_data.settings,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(writing_session)
    db.commit()
    db.refresh(writing_session)
    
    return writing_session

# Writing Session Stats Endpoints

@router.get("/sessions/{session_id}/stats", response_model=schemas.WritingSessionStats)
async def get_writing_session_stats(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get usage statistics for a writing session."""
    
    # Verify writing session access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Get or create stats
    stats = crud.get_or_create_writing_session_stats(db, session_id)
    
    return schemas.WritingSessionStats(
        session_id=session_id,
        total_cost=float(stats.total_cost),
        total_prompt_tokens=stats.total_prompt_tokens,
        total_completion_tokens=stats.total_completion_tokens,
        total_native_tokens=stats.total_native_tokens,
        total_web_searches=stats.total_web_searches,
        total_document_searches=stats.total_document_searches,
        created_at=stats.created_at,
        updated_at=stats.updated_at
    )

@router.post("/sessions/{session_id}/stats", response_model=schemas.WritingSessionStats)
async def update_writing_session_stats(
    session_id: str,
    stats_update: schemas.WritingSessionStatsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Update writing session statistics with delta values."""
    
    # Verify writing session access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Update stats with delta values
    updated_stats = crud.update_writing_session_stats(db, session_id, stats_update)
    
    if not updated_stats:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update writing session stats"
        )
    
    # Send real-time update via WebSocket
    try:
        from api.websockets import send_writing_stats_update
        await send_writing_stats_update(session_id, {
            "total_cost": float(updated_stats.total_cost),
            "total_prompt_tokens": updated_stats.total_prompt_tokens,
            "total_completion_tokens": updated_stats.total_completion_tokens,
            "total_native_tokens": updated_stats.total_native_tokens,
            "total_web_searches": updated_stats.total_web_searches,
            "total_document_searches": updated_stats.total_document_searches
        })
        logger.debug(f"Sent stats update via WebSocket for writing session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to send stats update via WebSocket: {e}")
    
    return schemas.WritingSessionStats(
        session_id=session_id,
        total_cost=float(updated_stats.total_cost),
        total_prompt_tokens=updated_stats.total_prompt_tokens,
        total_completion_tokens=updated_stats.total_completion_tokens,
        total_native_tokens=updated_stats.total_native_tokens,
        total_web_searches=updated_stats.total_web_searches,
        total_document_searches=updated_stats.total_document_searches,
        created_at=updated_stats.created_at,
        updated_at=updated_stats.updated_at
    )

@router.post("/sessions/{session_id}/stats/clear", response_model=schemas.WritingSessionStats)
async def clear_writing_session_stats(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Clear/reset all statistics for a writing session."""
    
    # Verify writing session access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Clear stats
    cleared_stats = crud.clear_writing_session_stats(db, session_id)
    
    if not cleared_stats:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear writing session stats"
        )
    
    # Send real-time update via WebSocket
    try:
        from api.websockets import send_writing_stats_update
        await send_writing_stats_update(session_id, {
            "total_cost": 0.0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_native_tokens": 0,
            "total_web_searches": 0,
            "total_document_searches": 0
        })
        logger.debug(f"Sent stats clear update via WebSocket for writing session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to send stats clear update via WebSocket: {e}")
    
    return schemas.WritingSessionStats(
        session_id=session_id,
        total_cost=0.0,
        total_prompt_tokens=0,
        total_completion_tokens=0,
        total_native_tokens=0,
        total_web_searches=0,
        total_document_searches=0,
        created_at=cleared_stats.created_at,
        updated_at=cleared_stats.updated_at
    )

@router.get("/sessions/{session_id}", response_model=schemas.WritingSessionWithDrafts)
async def get_writing_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get a writing session with its drafts."""
    
    # Get writing session and verify access through chat ownership
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Get all drafts for this session
    drafts = db.query(models.Draft).filter(
        models.Draft.writing_session_id == session_id
    ).order_by(models.Draft.created_at.desc()).all()
    
    # Get current draft
    current_draft = None
    if writing_session.current_draft_id:
        current_draft = db.query(models.Draft).filter(
            models.Draft.id == writing_session.current_draft_id
        ).first()
    
    # Convert to response model
    response_data = schemas.WritingSessionWithDrafts(
        id=writing_session.id,
        chat_id=writing_session.chat_id,
        document_group_id=writing_session.document_group_id,
        use_web_search=writing_session.use_web_search,
        current_draft_id=writing_session.current_draft_id,
        settings=writing_session.settings,
        created_at=writing_session.created_at,
        updated_at=writing_session.updated_at,
        drafts=[schemas.Draft.from_orm(draft) for draft in drafts],
        current_draft=schemas.Draft.from_orm(current_draft) if current_draft else None
    )
    
    return response_data

# Draft Management Endpoints

@router.get("/sessions/{session_id}/messages", response_model=List[schemas.Message])
async def get_writing_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get all messages for a writing session."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Get chat and messages
    chat = db.query(models.Chat).filter(models.Chat.id == writing_session.chat_id).first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )
    
    # Get all messages for this chat, ordered by creation time
    messages = db.query(models.Message).filter(
        models.Message.chat_id == chat.id
    ).order_by(models.Message.created_at.asc()).all()
    
    return messages

@router.get("/sessions/{session_id}/draft", response_model=schemas.DraftWithReferences)
async def get_current_draft(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get the current draft for a writing session."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Get current draft
    current_draft = None
    if writing_session.current_draft_id:
        current_draft = db.query(models.Draft).filter(
            models.Draft.id == writing_session.current_draft_id
        ).first()
    
    if not current_draft:
        # Create a new draft if none exists
        current_draft = models.Draft(
            id=str(uuid.uuid4()),
            writing_session_id=session_id,
            title="Untitled Document",
            content="",  # Start with completely blank content - no placeholder text
            version=1,
            is_current=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(current_draft)
        
        # Update writing session to point to this draft
        writing_session.current_draft_id = current_draft.id
        writing_session.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(current_draft)
        
        logger.info(f"Created new blank draft {current_draft.id} for writing session {session_id}")
    
    # Get references for this draft
    references = db.query(models.Reference).filter(
        models.Reference.draft_id == current_draft.id
    ).all()
    
    # Convert to response model
    response_data = schemas.DraftWithReferences(
        id=current_draft.id,
        writing_session_id=current_draft.writing_session_id,
        title=current_draft.title,
        content=current_draft.content,
        version=current_draft.version,
        is_current=current_draft.is_current,
        created_at=current_draft.created_at,
        updated_at=current_draft.updated_at,
        references=[schemas.Reference.from_orm(ref) for ref in references]
    )
    
    return response_data

@router.put("/sessions/{session_id}/draft", response_model=schemas.Draft)
async def update_current_draft(
    session_id: str,
    draft_update: schemas.DraftUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Update the current draft for a writing session."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Get current draft
    if not writing_session.current_draft_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No current draft found"
        )
    
    current_draft = db.query(models.Draft).filter(
        models.Draft.id == writing_session.current_draft_id
    ).first()
    
    if not current_draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current draft not found"
        )
    
    # Update fields
    update_data = draft_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_draft, field, value)
    
    current_draft.updated_at = datetime.utcnow()
    
    # No need to update metadata since content is now simple markdown
    
    db.commit()
    db.refresh(current_draft)
    
    return current_draft

@router.post("/sessions/{session_id}/versions", response_model=schemas.Draft)
async def create_draft_version(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Create a new version of the current draft."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Get current draft
    if not writing_session.current_draft_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No current draft found"
        )
    
    current_draft = db.query(models.Draft).filter(
        models.Draft.id == writing_session.current_draft_id
    ).first()
    
    if not current_draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current draft not found"
        )
    
    # Mark current draft as not current
    current_draft.is_current = False
    
    # Create new version
    new_version = models.Draft(
        id=str(uuid.uuid4()),
        writing_session_id=session_id,
        title=current_draft.title,
        content=current_draft.content,  # Copy the content string
        version=current_draft.version + 1,
        is_current=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(new_version)
    
    # Update writing session to point to new version
    writing_session.current_draft_id = new_version.id
    writing_session.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(new_version)
    
    return new_version


# Reference Management Endpoints

@router.get("/drafts/{draft_id}/references", response_model=List[schemas.Reference])
async def get_draft_references(
    draft_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get all references for a draft."""
    
    ref_service = ReferenceService(db)
    references = await ref_service.get_references_for_draft(
        draft_id=draft_id,
        user_id=current_user.id
    )
    
    return [schemas.Reference.from_orm(ref) for ref in references]

@router.post("/drafts/{draft_id}/references", response_model=schemas.Reference)
async def create_reference(
    draft_id: str,
    reference_data: schemas.ReferenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Create a new reference for a draft."""
    
    ref_service = ReferenceService(db)
    
    if reference_data.reference_type == "web":
        reference = await ref_service.create_reference_from_web_source(
            draft_id=draft_id,
            web_url=reference_data.web_url,
            title=reference_data.citation_text,  # Using citation_text as title for now
            user_id=current_user.id
        )
    else:
        # For document references, we'll need document_id
        reference = await ref_service.create_reference_from_document_chunk(
            draft_id=draft_id,
            document_chunk_id=reference_data.document_id,
            user_id=current_user.id
        )
    
    return schemas.Reference.from_orm(reference)

@router.put("/sessions/{session_id}", response_model=schemas.WritingSession)
async def update_writing_session(
    session_id: str,
    session_update: schemas.WritingSessionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Update a writing session."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Verify document group belongs to user if being updated
    if session_update.document_group_id is not None:
        if session_update.document_group_id:  # Not empty string
            doc_group = db.query(models.DocumentGroup).filter(
                models.DocumentGroup.id == session_update.document_group_id,
                models.DocumentGroup.user_id == current_user.id
            ).first()
            
            if not doc_group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document group not found or access denied"
                )
    
    # Update fields
    update_data = session_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(writing_session, field, value)
    
    writing_session.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(writing_session)
    
    return writing_session

@router.delete("/sessions/{session_id}")
async def delete_writing_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Delete a writing session and all its drafts."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Delete the session (cascading will handle drafts and references)
    db.delete(writing_session)
    db.commit()
    
    return {"message": "Writing session deleted successfully"}

@router.get("/sessions/by-chat/{chat_id}", response_model=schemas.WritingSessionWithDrafts)
async def get_writing_session_by_chat(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Get writing session for a specific chat."""
    
    # Verify chat belongs to user
    chat = db.query(models.Chat).filter(
        models.Chat.id == chat_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found or access denied"
        )
    
    # Get writing session for this chat
    writing_session = db.query(models.WritingSession).filter(
        models.WritingSession.chat_id == chat_id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No writing session found for this chat"
        )
    
    # Get all drafts for this session
    drafts = db.query(models.Draft).filter(
        models.Draft.writing_session_id == writing_session.id
    ).order_by(models.Draft.created_at.desc()).all()
    
    # Get current draft
    current_draft = None
    if writing_session.current_draft_id:
        current_draft = db.query(models.Draft).filter(
            models.Draft.id == writing_session.current_draft_id
        ).first()
    
    # Convert to response model
    response_data = schemas.WritingSessionWithDrafts(
        id=writing_session.id,
        chat_id=writing_session.chat_id,
        document_group_id=writing_session.document_group_id,
        use_web_search=writing_session.use_web_search,
        current_draft_id=writing_session.current_draft_id,
        settings=writing_session.settings,
        created_at=writing_session.created_at,
        updated_at=writing_session.updated_at,
        drafts=[schemas.Draft.from_orm(draft) for draft in drafts],
        current_draft=schemas.Draft.from_orm(current_draft) if current_draft else None
    )
    
    return response_data

@router.put("/drafts/{draft_id}/references/{reference_id}", response_model=schemas.Reference)
async def update_reference(
    draft_id: str,
    reference_id: str,
    citation_text: str = None,
    context: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Update an existing reference."""
    
    ref_service = ReferenceService(db)
    reference = await ref_service.update_reference(
        reference_id=reference_id,
        citation_text=citation_text,
        context=context,
        user_id=current_user.id
    )
    
    return schemas.Reference.from_orm(reference)


# Enhanced Writing Chat Endpoint - Non-blocking version

@router.post("/enhanced-chat-stream")
async def enhanced_writing_chat_stream(
    request: schemas.EnhancedWritingChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Non-blocking version of enhanced chat that processes in background and streams via WebSocket.
    Returns immediately with a task ID.
    """
    # Verify that the draft exists and the user has access to it.
    draft = db.query(models.Draft).join(
        models.WritingSession, models.Draft.writing_session_id == models.WritingSession.id
    ).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.Draft.id == request.draft_id,
        models.Chat.user_id == current_user.id
    ).first()

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found or access denied")

    # Generate a task ID for tracking
    task_id = str(uuid.uuid4())
    
    # Get the writing session
    writing_session = draft.writing_session
    session_id = writing_session.id
    
    # Check if this is a regeneration by looking for an existing user message with the same content
    # that's recent (within last 10 messages) to avoid false positives
    recent_messages = db.query(models.Message).filter(
        models.Message.chat_id == draft.writing_session.chat_id
    ).order_by(models.Message.created_at.desc()).limit(10).all()
    
    existing_user_message = None
    for msg in recent_messages:
        if msg.role == "user" and msg.content == request.message:
            existing_user_message = msg
            break
    
    if existing_user_message:
        # This is a regeneration - reuse the existing user message
        user_message = existing_user_message
        logger.info(f"Detected regeneration - reusing existing user message {existing_user_message.id} for chat {draft.writing_session.chat_id}")
        
        # Clean up any orphaned assistant messages after this user message
        orphaned_messages = db.query(models.Message).filter(
            models.Message.chat_id == draft.writing_session.chat_id,
            models.Message.created_at > existing_user_message.created_at
        ).all()
        
        if orphaned_messages:
            logger.info(f"Cleaning up {len(orphaned_messages)} orphaned messages for regeneration")
            for msg in orphaned_messages:
                db.delete(msg)
            db.commit()
    else:
        # New message - save it
        user_message = models.Message(
            id=str(uuid.uuid4()),
            chat_id=draft.writing_session.chat_id,
            role="user",
            content=request.message,
            created_at=datetime.utcnow()
        )
        db.add(user_message)
        db.commit()
    
    # Don't send any immediate updates - let the agent handle all status updates
    
    # Add the actual processing to background tasks
    background_tasks.add_task(
        process_writing_chat_in_background,
        task_id=task_id,
        request=request,
        draft_id=draft.id,
        session_id=session_id,
        chat_id=draft.writing_session.chat_id,
        user_id=current_user.id,
        user_message_id=user_message.id
    )
    
    # Return immediately with task ID
    return JSONResponse(
        status_code=202,  # Accepted
        content={
            "task_id": task_id,
            "status": "processing",
            "message": "Your request is being processed. Updates will be streamed via WebSocket."
        }
    )

async def process_writing_chat_in_background(
    task_id: str,
    request: schemas.EnhancedWritingChatRequest,
    draft_id: str,
    session_id: str,
    chat_id: str,
    user_id: int,
    user_message_id: str
):
    """
    Process writing chat in background and send updates via WebSocket.
    """
    from api.websockets import send_agent_status_update, send_draft_content_update
    from database.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Get user and draft
        current_user = db.query(models.User).filter(models.User.id == user_id).first()
        draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
        writing_session = db.query(models.WritingSession).filter(models.WritingSession.id == session_id).first()
        
        if not current_user or not draft or not writing_session:
            await send_streaming_chunk_update(session_id, "\n❌ Error: Session data not found.\n")
            return
        
        # Set user context
        set_current_user(current_user)
        
        # Determine settings (same logic as original endpoint)
        document_group_id = request.document_group_id
        if document_group_id == "" or document_group_id == "none":
            document_group_id = None
        elif document_group_id is None:
            document_group_id = writing_session.document_group_id
        
        use_web_search = request.use_web_search
        if use_web_search is None:
            use_web_search = writing_session.use_web_search
        
        # Get the WritingController
        writing_controller = await WritingController.get_instance(current_user)
        agent = SimplifiedWritingAgent(model_dispatcher=writing_controller.model_dispatcher)
        
        # Get chat history (excluding the message we just added)
        chat_history = db.query(models.Message).filter(
            models.Message.chat_id == chat_id,
            models.Message.id != user_message_id
        ).order_by(models.Message.created_at.asc()).all()
        
        # Convert to list of dictionaries for the agent
        chat_history_messages = [{"role": msg.role, "content": msg.content} for msg in chat_history]
        
        # Prepare context
        custom_system_prompt = None
        if current_user.settings and isinstance(current_user.settings, dict):
            writing_settings = current_user.settings.get("writing_settings", {})
            if isinstance(writing_settings, dict):
                custom_system_prompt = writing_settings.get("custom_system_prompt")
        
        user_research_params = current_user.settings.get("research_parameters", {}) if current_user.settings else {}
        user_search_settings = current_user.settings.get("search", {}) if current_user.settings else {}
        
        if request.deep_search:
            default_iterations = user_research_params.get("writing_deep_search_iterations", 3)
            default_queries = user_research_params.get("writing_deep_search_queries", 5)
        else:
            default_iterations = user_research_params.get("writing_search_max_iterations", 1)
            default_queries = user_research_params.get("writing_search_max_queries", 3)
        
        # Fetch document group name if document_group_id is provided
        document_group_name = None
        if document_group_id:
            document_group = db.query(models.DocumentGroup).filter(
                models.DocumentGroup.id == document_group_id,
                models.DocumentGroup.user_id == current_user.id
            ).first()
            if document_group:
                document_group_name = document_group.name
        
        context_info = {
            "document_group_id": document_group_id,
            "document_group_name": document_group_name,
            "use_web_search": use_web_search,
            "operation_mode": request.operation_mode or "balanced",
            "user_profile": {
                "full_name": current_user.full_name,
                "location": current_user.location,
                "job_title": current_user.job_title,
            },
            "session_id": session_id,
            "custom_system_prompt": custom_system_prompt,
            "search_config": {
                "deep_search": request.deep_search or False,
                "max_iterations": request.max_search_iterations or default_iterations,
                "max_decomposed_queries": request.max_decomposed_queries or default_queries,
                "max_results": get_writing_mode_web_results(),  # Use writing mode web results setting
                "max_doc_results": get_writing_mode_doc_results()  # Use writing mode doc results setting
            }
        }
        
        # Create status callback for agent updates
        async def status_callback(status: str, details: str = ""):
            """Send status updates via WebSocket."""
            try:
                # Map agent status to user-friendly messages
                status_map = {
                    "analyzing": "analyzing",
                    "router_thinking": "thinking",
                    "router_decision": "planning",
                    "searching_web": "searching",
                    "searching_documents": "searching",
                    "assessing_relevance": "evaluating",
                    "fetching_content": "retrieving",
                    "generating_response": "writing",
                    "generating": "writing",
                    "finalizing": "finalizing",
                    "complete": "complete",
                    "error": "error"
                }
                
                mapped_status = status_map.get(status, status)
                await send_agent_status_update(session_id, mapped_status, details)
                
                # Don't stream status messages as content chunks
                logger.debug(f"Status update: {status} - {details}")
            except Exception as e:
                logger.warning(f"Failed to send status update: {e}")
        
        # Don't send initial status - let the agent handle it
        
        # Run the agent with status callback (not streaming callback)
        result = await agent.run(
            prompt=request.message,
            draft_content=draft.content,
            chat_history=chat_history_messages,
            context_info=context_info,
            status_callback=status_callback
        )
        
        # Save the assistant response
        agent_response_msg = models.Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content=result["chat_response"],
            sources=result.get("sources", []),
            created_at=datetime.utcnow()
        )
        db.add(agent_response_msg)
        db.commit()
        
        # Send the complete response via WebSocket (not as streaming chunks)
        await send_agent_status_update(session_id, "completed", "Response generated successfully")
        
        # Send the full response message with sources
        await send_draft_content_update(session_id, {
            "message": result["chat_response"],
            "sources": result.get("sources", []),
            "task_id": task_id
        }, "complete")
        
        # Update chat title if needed
        try:
            title_service = ChatTitleService(writing_controller.model_dispatcher)
            await title_service.update_title_if_needed(
                db=db,
                chat_id=chat_id,
                user_id=user_id,
                user_message=request.message,
                ai_response=result["chat_response"]
            )
        except Exception as e:
            logger.warning(f"Failed to update chat title: {e}")
            
    except Exception as e:
        logger.error(f"Error in background writing chat processing: {e}", exc_info=True)
        try:
            await send_streaming_chunk_update(session_id, f"\n❌ Error: {str(e)}\n")
            await send_agent_status_update(session_id, "error", str(e))
        except:
            pass
    finally:
        db.close()


@router.put("/sessions/{session_id}/settings", response_model=schemas.WritingSession)
async def update_session_settings(
    session_id: str,
    settings_update: schemas.WritingSessionSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Update writing session settings including revision parameters."""
    
    # Get writing session and verify access
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writing session not found or access denied"
        )
    
    # Update settings
    current_settings = writing_session.settings or {}
    new_settings = settings_update.settings.dict(exclude_unset=True)
    current_settings.update(new_settings)
    
    writing_session.settings = current_settings
    writing_session.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(writing_session)
    
    return writing_session


# Word Document Export Endpoint
from pydantic import BaseModel
import pypandoc
import tempfile
import os
from fastapi.responses import FileResponse, Response

class MarkdownContent(BaseModel):
    markdown_content: str
    filename: Optional[str] = None

@router.post("/sessions/{session_id}/draft/docx")
async def export_draft_as_docx(
    session_id: str,
    content: MarkdownContent,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """Export a writing draft as a Word document."""
    
    # Verify the user has access to this writing session
    writing_session = db.query(models.WritingSession).join(
        models.Chat, models.WritingSession.chat_id == models.Chat.id
    ).filter(
        models.WritingSession.id == session_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not writing_session:
        raise HTTPException(status_code=404, detail="Writing session not found or access denied")
    
    try:
        # Create a temporary file for the DOCX output
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Convert markdown to DOCX using pypandoc with output file
            pypandoc.convert_text(
                content.markdown_content,
                'docx',
                format='md',
                outputfile=temp_path,
                extra_args=['--reference-doc=/app/reference.docx'] if os.path.exists('/app/reference.docx') else []
            )
            
            # Read the generated file
            with open(temp_path, 'rb') as docx_file:
                docx_content = docx_file.read()
            
            # Clean up the temp file
            os.unlink(temp_path)
            
            # Return the file response as bytes
            filename = f"{content.filename or 'document'}.docx"
            return Response(
                content=docx_content,
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
            
    except Exception as e:
        logger.error(f"Failed to convert markdown to DOCX: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate Word document: {str(e)}"
        )
