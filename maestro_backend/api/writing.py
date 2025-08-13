from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
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


# Enhanced Writing Chat Endpoint

@router.post("/enhanced-chat", response_model=schemas.WritingAgentResponse)
async def enhanced_writing_chat(
    request: schemas.EnhancedWritingChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_from_cookie)
):
    """
    Enhanced chat endpoint for the writing view with document group and web search support.
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

    # Get the writing session to access settings
    writing_session = draft.writing_session

    # Determine document group to use (request override or session default)
    document_group_id = request.document_group_id
    if document_group_id is None:
        document_group_id = writing_session.document_group_id

    # Determine web search setting (request override or session default)
    use_web_search = request.use_web_search
    if use_web_search is None:
        use_web_search = writing_session.use_web_search

    # Verify document group access if specified
    if document_group_id:
        doc_group = db.query(models.DocumentGroup).filter(
            models.DocumentGroup.id == document_group_id,
            models.DocumentGroup.user_id == current_user.id
        ).first()
        
        if not doc_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document group not found or access denied"
            )

    # CRITICAL: Set the user context so ModelDispatcher can access user settings
    set_current_user(current_user)
    
    # Get the user-specific WritingController
    writing_controller = await WritingController.get_instance(current_user)

    # Initialize the simplified agent with the user-specific model dispatcher
    agent = SimplifiedWritingAgent(model_dispatcher=writing_controller.model_dispatcher)

    # Get chat history
    chat_history = db.query(models.Message).filter(
        models.Message.chat_id == draft.writing_session.chat_id
    ).order_by(models.Message.created_at.asc()).all()

    chat_history_str = "\n".join([f"{msg.role}: {msg.content}" for msg in chat_history])

    # Get custom system prompt from user settings
    custom_system_prompt = None
    if current_user.settings and isinstance(current_user.settings, dict):
        writing_settings = current_user.settings.get("writing_settings", {})
        if isinstance(writing_settings, dict):
            custom_system_prompt = writing_settings.get("custom_system_prompt")

    # Get default search settings from user profile if not provided
    user_research_params = current_user.settings.get("research_parameters", {}) if current_user.settings else {}
    user_search_settings = current_user.settings.get("search", {}) if current_user.settings else {}
    
    # Determine defaults based on deep search mode
    if request.deep_search:
        default_iterations = user_research_params.get("writing_deep_search_iterations", 3)
        default_queries = user_research_params.get("writing_deep_search_queries", 10)
    else:
        default_iterations = user_research_params.get("writing_search_max_iterations", 1)
        default_queries = user_research_params.get("writing_search_max_queries", 3)
    
    # Prepare context for the agent based on selected tools
    context_info = {
        "document_group_id": document_group_id,
        "use_web_search": use_web_search,
        "operation_mode": request.operation_mode or "balanced",
        "user_profile": {
            "full_name": current_user.full_name,
            "location": current_user.location,
            "job_title": current_user.job_title,
        },
        "session_id": writing_session.id,  # Add session_id for stats tracking
        "custom_system_prompt": custom_system_prompt,  # Pass custom system prompt to agent
        "search_config": {  # Add search configuration
            "deep_search": request.deep_search or False,
            "max_iterations": request.max_search_iterations or default_iterations,
            "max_decomposed_queries": request.max_decomposed_queries or default_queries,
            "max_results": user_search_settings.get("max_results", 5)  # Use user's search settings
        }
    }

    # Create status update callback for WebSocket updates
    async def status_update_callback(status: str, details: str = ""):
        """Send status updates via WebSocket if available"""
        try:
            from api.websockets import send_agent_status_update, send_streaming_chunk_update
            session_id = writing_session.id
            
            # Handle different status types
            if status == "streaming_chunk":
                # Send streaming content chunk
                await send_streaming_chunk_update(session_id, details)
            else:
                # Send regular status update
                await send_agent_status_update(session_id, status, details)
        except Exception as e:
            logger.warning(f"Failed to send status update: {e}")

    # Run the agent with enhanced context and status updates
    result = await agent.run(
        prompt=request.message,
        draft_content=draft.content,
        chat_history=chat_history_str,
        context_info=context_info,
        status_callback=status_update_callback
    )

    # Check if this is a regeneration by looking for an existing user message with the same content
    # We'll look for the most recent user message with this exact content
    existing_user_message = db.query(models.Message).filter(
        models.Message.chat_id == draft.writing_session.chat_id,
        models.Message.role == "user",
        models.Message.content == request.message
    ).order_by(models.Message.created_at.desc()).first()

    # Only save user message if it doesn't already exist (i.e., this is not a regeneration)
    if not existing_user_message:
        user_message = models.Message(
            id=str(uuid.uuid4()),
            chat_id=draft.writing_session.chat_id,
            role="user",
            content=request.message,
            created_at=datetime.utcnow()
        )
        db.add(user_message)
        logger.info(f"Created new user message for chat {draft.writing_session.chat_id}")
    else:
        logger.info(f"Detected regeneration - reusing existing user message {existing_user_message.id} for chat {draft.writing_session.chat_id}")
        
        # For regeneration, ensure we clean up any orphaned assistant messages
        # that might not have been properly deleted by the frontend call
        orphaned_assistant_messages = db.query(models.Message).filter(
            models.Message.chat_id == draft.writing_session.chat_id,
            models.Message.role == "assistant",
            models.Message.created_at > existing_user_message.created_at
        ).all()
        
        if orphaned_assistant_messages:
            logger.info(f"Cleaning up {len(orphaned_assistant_messages)} orphaned assistant messages for regeneration")
            for msg in orphaned_assistant_messages:
                db.delete(msg)

    # Always save the new agent response (whether new message or regeneration)
    agent_response_msg = models.Message(
        id=str(uuid.uuid4()),
        chat_id=draft.writing_session.chat_id,
        role="assistant",
        content=result["chat_response"],
        sources=result.get("sources", []),  # Save sources to database
        created_at=datetime.utcnow()
    )
    db.add(agent_response_msg)

    db.commit()

    # Generate intelligent chat title after successful AI response (similar to research chat)
    updated_title = None
    try:
        logger.info(f"Attempting to generate intelligent title for writing chat {draft.writing_session.chat_id}")
        title_service = ChatTitleService(writing_controller.model_dispatcher)
        
        # Create a writing-focused title generation prompt
        title_updated = await title_service.update_title_if_needed(
            db=db,
            chat_id=draft.writing_session.chat_id,
            user_id=current_user.id,
            user_message=request.message,
            ai_response=result["chat_response"]
        )
        
        if title_updated:
            logger.info(f"Writing chat title updated successfully for chat {draft.writing_session.chat_id}")
            # Get the updated title to return to frontend
            from database import crud
            updated_chat = crud.get_chat(db, draft.writing_session.chat_id, current_user.id)
            if updated_chat:
                updated_title = updated_chat.title
                
                # Send WebSocket notification about title update
                try:
                    from api.websockets import send_chat_title_update
                    session_id = writing_session.id
                    await send_chat_title_update(session_id, draft.writing_session.chat_id, updated_title)
                    logger.info(f"Sent chat title update via WebSocket for chat {draft.writing_session.chat_id}")
                except Exception as ws_error:
                    logger.warning(f"Failed to send chat title update via WebSocket: {ws_error}")
        else:
            logger.info(f"Writing chat title did not need updating for chat {draft.writing_session.chat_id}")
            
    except Exception as title_error:
        # Don't let title generation errors affect the main chat response
        logger.warning(f"Failed to update writing chat title for {draft.writing_session.chat_id}: {title_error}", exc_info=True)

    # Build context usage response
    context_used = schemas.ContextUsage(
        document_group=bool(document_group_id),
        search_results=use_web_search,
        conversation_history=True,
        full_document=True
    )

    return schemas.WritingAgentResponse(
        message=result["chat_response"],
        sources=result.get("sources", []),  # Include sources from the agent
        operations=[],
        context_used=context_used,
        revision_steps_executed=schemas.RevisionStepsExecuted(),
        error=None,
        updated_title=updated_title  # Include the updated title if it was changed
    )

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
