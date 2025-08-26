from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
import logging

from auth.dependencies import get_current_user_from_cookie, get_db
from database.models import User
from database import crud
from api import schemas
from ai_researcher.agentic_layer.schemas.thought import generate_uuid
from api.locales import get_message

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/chats", response_model=schemas.Chat)
async def create_chat(
    chat_data: schemas.ChatCreate,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Create a new chat for the current user."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        chat_id = generate_uuid()
        db_chat = crud.create_chat(
            db=db,
            chat_id=chat_id,
            user_id=current_user.id,
            title=chat_data.title,
            chat_type=getattr(chat_data, 'chat_type', 'research')  # Default to research for backward compatibility
        )
        logger.info(f"Created new chat {chat_id} for user {current_user.username}")
        return db_chat
    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.createFailed", lang, error=str(e))
        )

@router.get("/chats", response_model=List[schemas.ChatSummary])
async def get_user_chats(
    fastapi_request: Request,
    skip: int = 0,
    limit: int = 100,
    chat_type: str = "research",
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get chats for the current user by type."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        # Get chats by type (research or writing)
        db_chats = crud.get_user_chats_by_type(db=db, user_id=current_user.id, chat_type=chat_type, skip=skip, limit=limit)
        
        # Convert to ChatSummary with additional info
        chat_summaries = []
        for chat in db_chats:
            # Count messages and active missions
            messages = crud.get_chat_messages(db=db, chat_id=chat.id, user_id=current_user.id)
            active_missions = crud.get_active_missions_for_chat(db=db, chat_id=chat.id, user_id=current_user.id)
            
            chat_summary = schemas.ChatSummary(
                id=chat.id,
                user_id=chat.user_id,
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                message_count=len(messages),
                active_mission_count=len(active_missions)
            )
            chat_summaries.append(chat_summary)
        
        return chat_summaries
    except Exception as e:
        logger.error(f"Error getting user chats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.getChatsFailed", lang, error=str(e))
        )

@router.get("/chats/{chat_id}", response_model=schemas.Chat)
async def get_chat(
    chat_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get a specific chat with all messages and missions."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        db_chat = crud.get_chat(db=db, chat_id=chat_id, user_id=current_user.id)
        if not db_chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        return db_chat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.getChatFailed", lang, error=str(e))
        )

@router.put("/chats/{chat_id}", response_model=schemas.Chat)
async def update_chat(
    chat_id: str,
    chat_update: schemas.ChatUpdate,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Update a chat (currently only title)."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        if chat_update.title is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=get_message("chats.noUpdateData", lang)
            )
        
        db_chat = crud.update_chat_title(
            db=db,
            chat_id=chat_id,
            user_id=current_user.id,
            title=chat_update.title
        )
        
        if not db_chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        
        logger.info(f"Updated chat {chat_id} title to '{chat_update.title}'")
        return db_chat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.updateFailed", lang, error=str(e))
        )

@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete a chat and all its messages and missions."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        success = crud.delete_chat(db=db, chat_id=chat_id, user_id=current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        
        logger.info(f"Deleted chat {chat_id} for user {current_user.username}")
        return {"message": get_message("chats.deleteSuccess", lang)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.deleteFailed", lang, error=str(e))
        )

@router.post("/chats/{chat_id}/messages", response_model=schemas.Message)
async def add_message_to_chat(
    chat_id: str,
    message_data: schemas.MessageCreate,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Add a message to a chat."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        # Verify chat exists and belongs to user
        db_chat = crud.get_chat(db=db, chat_id=chat_id, user_id=current_user.id)
        if not db_chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        
        message_id = generate_uuid()
        db_message = crud.create_message(
            db=db,
            message_id=message_id,
            chat_id=chat_id,
            content=message_data.content,
            role=message_data.role
        )
        
        logger.info(f"Added message to chat {chat_id}")
        return db_message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding message to chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.addMessageFailed", lang, error=str(e))
        )

@router.get("/chats/{chat_id}/messages", response_model=List[schemas.Message])
async def get_chat_messages(
    chat_id: str,
    fastapi_request: Request,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get messages for a chat."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        messages = crud.get_chat_messages(
            db=db,
            chat_id=chat_id,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )
        return messages
    except Exception as e:
        logger.error(f"Error getting messages for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.getMessagesFailed", lang, error=str(e))
        )

@router.get("/chats/{chat_id}/missions", response_model=List[schemas.Mission])
async def get_chat_missions(
    chat_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get all missions for a chat."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        missions = crud.get_chat_missions(db=db, chat_id=chat_id, user_id=current_user.id)
        return missions
    except Exception as e:
        logger.error(f"Error getting missions for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.getMissionsFailed", lang, error=str(e))
        )

@router.get("/chats/{chat_id}/active-missions", response_model=List[schemas.Mission])
async def get_chat_active_missions(
    chat_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get active missions (pending or running) for a chat."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        active_missions = crud.get_active_missions_for_chat(
            db=db,
            chat_id=chat_id,
            user_id=current_user.id
        )
        return active_missions
    except Exception as e:
        logger.error(f"Error getting active missions for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.getActiveMissionsFailed", lang, error=str(e))
        )

@router.delete("/chats/{chat_id}/messages")
async def clear_chat_messages(
    chat_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Clear all messages from a chat."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        # Verify chat exists and belongs to user
        db_chat = crud.get_chat(db=db, chat_id=chat_id, user_id=current_user.id)
        if not db_chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        
        # Delete all messages for this chat
        success = crud.clear_chat_messages(db=db, chat_id=chat_id, user_id=current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=get_message("chats.clearMessagesFailed", lang)
            )
        
        logger.info(f"Cleared all messages from chat {chat_id}")
        return {"message": get_message("chats.clearMessagesSuccess", lang)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing messages for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.clearMessagesError", lang, error=str(e))
        )

@router.delete("/chats/{chat_id}/messages/{message_id}")
async def delete_message_pair(
    chat_id: str,
    message_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete a user-assistant message pair from a chat."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        # Verify chat exists and belongs to user
        db_chat = crud.get_chat(db=db, chat_id=chat_id, user_id=current_user.id)
        if not db_chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        
        # Delete the message pair (user message + assistant response)
        deleted_count = crud.delete_message_pair(db=db, message_id=message_id, chat_id=chat_id, user_id=current_user.id)
        if deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.messagePairNotFound", lang)
            )
        
        logger.info(f"Deleted {deleted_count} messages (pair) starting from {message_id} in chat {chat_id}")
        return {"message": get_message("chats.deleteMessagePairSuccess", lang, count=deleted_count)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message pair from {message_id} in chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.deleteMessagePairFailed", lang, error=str(e))
        )

@router.delete("/chats/{chat_id}/messages/from/{message_id}")
async def delete_messages_from_point(
    chat_id: str,
    message_id: str,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete all messages from a specific message onwards (for regeneration)."""
    lang = fastapi_request.headers.get('Accept-Language', 'en').split(',')[0].split('-')[0]
    try:
        # Verify chat exists and belongs to user
        db_chat = crud.get_chat(db=db, chat_id=chat_id, user_id=current_user.id)
        if not db_chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=get_message("chats.chatNotFound", lang)
            )
        
        # Delete messages from the specified point onwards
        deleted_count = crud.delete_messages_from_point(
            db=db, 
            chat_id=chat_id, 
            from_message_id=message_id, 
            user_id=current_user.id
        )
        
        logger.info(f"Deleted {deleted_count} messages from message {message_id} onwards in chat {chat_id}")
        return {"message": get_message("chats.deleteMessagesFromPointSuccess", lang, count=deleted_count)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting messages from point {message_id} in chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=get_message("chats.deleteMessagesFromPointFailed", lang, error=str(e))
        )
