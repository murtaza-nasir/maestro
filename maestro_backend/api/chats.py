from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import math

from auth.dependencies import get_current_user_from_cookie, get_db
from database.async_database import get_async_db_session
from database.models import User
from database import crud, async_crud
from api import schemas
from ai_researcher.agentic_layer.schemas.thought import generate_uuid

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/chats", response_model=schemas.Chat)
async def create_chat(
    chat_data: schemas.ChatCreate,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Create a new chat for the current user."""
    try:
        chat_id = generate_uuid()
        async_db = await get_async_db_session()
        try:
            db_chat = await async_crud.create_chat(
                db=async_db,
                chat_id=chat_id,
                user_id=current_user.id,
                title=chat_data.title,
                chat_type=getattr(chat_data, 'chat_type', 'research')  # Default to research for backward compatibility
            )
            logger.info(f"Created new chat {chat_id} for user {current_user.username}")
            return db_chat
        finally:
            await async_db.close()
    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create chat: {str(e)}"
        )

@router.get("/chats", response_model=schemas.PaginatedChatsResponse)
async def get_user_chats(
    page: int = 1,
    page_size: int = 20,
    chat_type: str = "research",
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get paginated chats for the current user by type with optional search."""
    try:
        async_db = await get_async_db_session()
        try:
            # Calculate skip based on page
            skip = (page - 1) * page_size
            
            # Get chats with counts in a single optimized query
            chats_with_counts = await async_crud.get_chats_with_counts(
                db=async_db,
                user_id=current_user.id,
                chat_type=chat_type,
                skip=skip,
                limit=page_size,
                search_query=search
            )
            
            # Get total count for pagination
            total = await async_crud.count_user_chats_by_type(
                db=async_db,
                user_id=current_user.id,
                chat_type=chat_type,
                search_query=search
            )
            
            # Calculate total pages
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            
            # Convert to ChatSummary with additional info
            chat_summaries = []
            for item in chats_with_counts:
                chat = item['chat']
                chat_summary = schemas.ChatSummary(
                    id=chat.id,
                    user_id=chat.user_id,
                    title=chat.title,
                    created_at=chat.created_at,
                    updated_at=chat.updated_at,
                    message_count=item['message_count'],
                    active_mission_count=item['active_mission_count']
                )
                chat_summaries.append(chat_summary)
            
            return schemas.PaginatedChatsResponse(
                items=chat_summaries,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )
        finally:
            await async_db.close()
    except Exception as e:
        logger.error(f"Error getting user chats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chats: {str(e)}"
        )

@router.get("/chats/{chat_id}", response_model=schemas.Chat)
async def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get a specific chat with all messages and missions."""
    try:
        async_db = await get_async_db_session()
        try:
            db_chat = await async_crud.get_chat(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not db_chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            return db_chat
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get chat: {str(e)}"
        )

@router.put("/chats/{chat_id}", response_model=schemas.Chat)
async def update_chat(
    chat_id: str,
    chat_update: schemas.ChatUpdate,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Update a chat (title and/or settings)."""
    try:
        async_db = await get_async_db_session()
        try:
            if chat_update.title is None and chat_update.settings is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No update data provided"
                )
            
            db_chat = None
            
            # Update title if provided
            if chat_update.title is not None:
                db_chat = await async_crud.update_chat_title(
                    db=async_db,
                    chat_id=chat_id,
                    user_id=current_user.id,
                    title=chat_update.title
                )
            
            # Update settings if provided
            if chat_update.settings is not None:
                logger.info(f"Updating chat {chat_id} settings: {chat_update.settings}")
                db_chat = await async_crud.update_chat_settings(
                    db=async_db,
                    chat_id=chat_id,
                    user_id=current_user.id,
                    settings=chat_update.settings
                )
                logger.info(f"Chat {chat_id} settings updated successfully")
            
            if not db_chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            
            if chat_update.title:
                logger.info(f"Updated chat {chat_id} title to '{chat_update.title}'")
            return db_chat
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update chat: {str(e)}"
        )

@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete a chat and all its messages and missions."""
    try:
        async_db = await get_async_db_session()
        try:
            success = await async_crud.delete_chat(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            
            logger.info(f"Deleted chat {chat_id} for user {current_user.username}")
            return {"message": "Chat deleted successfully"}
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete chat: {str(e)}"
        )

@router.post("/chats/{chat_id}/messages", response_model=schemas.Message)
async def add_message_to_chat(
    chat_id: str,
    message_data: schemas.MessageCreate,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Add a message to a chat."""
    try:
        async_db = await get_async_db_session()
        try:
            # Verify chat exists and belongs to user
            db_chat = await async_crud.get_chat(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not db_chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            
            message_id = generate_uuid()
            db_message = await async_crud.create_message(
                db=async_db,
                message_id=message_id,
                chat_id=chat_id,
                content=message_data.content,
                role=message_data.role
            )
            
            logger.info(f"Added message to chat {chat_id}")
            return db_message
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding message to chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add message: {str(e)}"
        )

@router.get("/chats/{chat_id}/messages", response_model=List[schemas.Message])
async def get_chat_messages(
    chat_id: str,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get messages for a chat."""
    try:
        async_db = await get_async_db_session()
        try:
            messages = await async_crud.get_chat_messages(
            db=async_db,
            chat_id=chat_id,
            user_id=current_user.id,
            skip=skip,
            limit=limit
            )
            return messages
        finally:
            await async_db.close()
    except Exception as e:
        logger.error(f"Error getting messages for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}"
        )

@router.get("/chats/{chat_id}/missions", response_model=List[schemas.Mission])
async def get_chat_missions(
    chat_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get all missions for a chat."""
    try:
        async_db = await get_async_db_session()
        try:
            missions = await async_crud.get_chat_missions(db=async_db, chat_id=chat_id, user_id=current_user.id)
            return missions
        finally:
            await async_db.close()
    except Exception as e:
        logger.error(f"Error getting missions for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get missions: {str(e)}"
        )

@router.get("/chats/{chat_id}/active-missions", response_model=List[schemas.Mission])
async def get_chat_active_missions(
    chat_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Get active missions (pending or running) for a chat."""
    try:
        async_db = await get_async_db_session()
        try:
            active_missions = await async_crud.get_active_missions_for_chat(
                db=async_db,
                chat_id=chat_id,
                user_id=current_user.id
            )
            return active_missions
        finally:
            await async_db.close()
    except Exception as e:
        logger.error(f"Error getting active missions for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active missions: {str(e)}"
        )

@router.delete("/chats/{chat_id}/messages")
async def clear_chat_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Clear all messages from a chat."""
    try:
        async_db = await get_async_db_session()
        try:
            # Verify chat exists and belongs to user
            db_chat = await async_crud.get_chat(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not db_chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            
            # Delete all messages for this chat
            success = await async_crud.clear_chat_messages(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to clear chat messages"
                )
        
            logger.info(f"Cleared all messages from chat {chat_id}")
            return {"message": "Chat messages cleared successfully"}
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing messages for chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear messages: {str(e)}"
        )

@router.delete("/chats/{chat_id}/messages/{message_id}")
async def delete_message_pair(
    chat_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete a user-assistant message pair from a chat."""
    logger.info(f"Delete request received for message {message_id} in chat {chat_id} by user {current_user.username}")
    try:
        async_db = await get_async_db_session()
        try:
            # Verify chat exists and belongs to user
            db_chat = await async_crud.get_chat(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not db_chat:
                logger.warning(f"Chat {chat_id} not found for user {current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            
            # Delete the message pair (user message + assistant response)
            deleted_count = await async_crud.delete_message_pair(db=async_db, message_id=message_id, chat_id=chat_id, user_id=current_user.id)
            if deleted_count == 0:
                logger.warning(f"Message pair {message_id} not found in chat {chat_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Message pair not found"
                )
        
            logger.info(f"Successfully deleted {deleted_count} messages (pair) starting from {message_id} in chat {chat_id}")
            return {"message": f"Deleted {deleted_count} messages in the conversation pair"}
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message pair from {message_id} in chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete message pair: {str(e)}"
        )

@router.delete("/chats/{chat_id}/messages/from/{message_id}")
async def delete_messages_from_point(
    chat_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """Delete all messages from a specific message onwards (for regeneration)."""
    try:
        async_db = await get_async_db_session()
        try:
            # Verify chat exists and belongs to user
            db_chat = await async_crud.get_chat(db=async_db, chat_id=chat_id, user_id=current_user.id)
            if not db_chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found"
                )
            
            # Delete messages from the specified point onwards
            deleted_count = await async_crud.delete_messages_from_point(
                db=async_db, 
                chat_id=chat_id, 
                from_message_id=message_id, 
                user_id=current_user.id
            )
        
            logger.info(f"Deleted {deleted_count} messages from message {message_id} onwards in chat {chat_id}")
            return {"message": f"Deleted {deleted_count} messages from specified point onwards"}
        finally:
            await async_db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting messages from point {message_id} in chat {chat_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete messages from point: {str(e)}"
        )
