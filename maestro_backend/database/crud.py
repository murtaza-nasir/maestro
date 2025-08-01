from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from database.models import User, Chat, Message, Mission, Document, DocumentGroup, WritingSessionStats, SystemSetting, MissionExecutionLog
from api import schemas
from auth.security import get_password_hash
from typing import List, Optional, Dict, Any
from datetime import datetime
from ai_researcher.config import SERVER_TIMEZONE
import logging
import uuid

logger = logging.getLogger(__name__)

def get_current_time() -> datetime:
    """Returns the current time in the server's timezone."""
    return datetime.now(SERVER_TIMEZONE)

# User CRUD operations
def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str):
    # Assuming username is the email for now
    return db.query(User).filter(User.username == email).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(User).offset(skip).limit(limit).all()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    now = get_current_time()
    db_user = User(
        username=user.username, 
        hashed_password=hashed_password,
        created_at=now,
        updated_at=now
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate) -> Optional[User]:
    """Update a user's details."""
    db_user = get_user(db, user_id)
    if db_user:
        update_data = user_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_user, key, value)
        db_user.updated_at = get_current_time()
        db.commit()
        db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int) -> Optional[User]:
    """Delete a user."""
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user

def update_user_settings(db: Session, user_id: int, settings: Dict[str, Any]) -> Optional[User]:
    """Update a user's settings."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db_user.settings = settings
        db_user.updated_at = get_current_time()
        db.commit()
        db.refresh(db_user)
        return db_user
    return None

def update_user_profile(db: Session, user_id: int, profile_update: schemas.UserProfileUpdate) -> Optional[User]:
    """Update a user's profile."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        update_data = profile_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_user, key, value)
        db_user.updated_at = get_current_time()
        db.commit()
        db.refresh(db_user)
        return db_user
    return None

def update_user_appearance(db: Session, user_id: int, appearance_settings: schemas.AppearanceSettings) -> Optional[User]:
    """Update a user's appearance settings."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db_user.theme = appearance_settings.theme
        db_user.color_scheme = appearance_settings.color_scheme
        db_user.updated_at = get_current_time()
        db.commit()
        db.refresh(db_user)
        return db_user
    return None

# Chat CRUD operations
def create_chat(db: Session, chat_id: str, user_id: int, title: str, document_group_id: Optional[str] = None, chat_type: str = "research") -> Chat:
    """Create a new chat for a user."""
    now = get_current_time()
    db_chat = Chat(
        id=chat_id,
        user_id=user_id,
        title=title,
        document_group_id=document_group_id,
        chat_type=chat_type,
        created_at=now,
        updated_at=now
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return db_chat

def get_chat(db: Session, chat_id: str, user_id: int) -> Optional[Chat]:
    """Get a chat by ID, ensuring it belongs to the user."""
    return db.query(Chat).filter(
        and_(Chat.id == chat_id, Chat.user_id == user_id)
    ).first()

def get_user_chats(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Chat]:
    """Get all chats for a user, ordered by most recent."""
    return db.query(Chat).filter(Chat.user_id == user_id).order_by(
        Chat.updated_at.desc()
    ).offset(skip).limit(limit).all()

def get_user_chats_by_type(db: Session, user_id: int, chat_type: str, skip: int = 0, limit: int = 100) -> List[Chat]:
    """Get chats for a user filtered by chat type, ordered by most recent."""
    return db.query(Chat).filter(
        and_(Chat.user_id == user_id, Chat.chat_type == chat_type)
    ).order_by(Chat.updated_at.desc()).offset(skip).limit(limit).all()

def update_chat_title(db: Session, chat_id: str, user_id: int, title: str) -> Optional[Chat]:
    """Update a chat's title."""
    db_chat = get_chat(db, chat_id, user_id)
    if db_chat:
        db_chat.title = title
        db_chat.updated_at = get_current_time()
        db.commit()
        db.refresh(db_chat)
        
        # Send WebSocket update to notify frontend of title change
        try:
            # Import here to avoid circular imports
            from database.models import WritingSession
            
            logger.debug(f"Looking for writing session with chat_id {chat_id}")
            
            # Get the writing session ID for this chat
            writing_session = db.query(WritingSession).filter(
                WritingSession.chat_id == chat_id
            ).first()
            
            if writing_session:
                logger.debug(f"Found writing session {writing_session.id} for chat {chat_id}")
                from api.websockets import send_chat_title_update
                import asyncio
                
                # Send the update asynchronously
                asyncio.create_task(send_chat_title_update(
                    session_id=writing_session.id,
                    chat_id=chat_id,
                    title=title
                ))
                logger.info(f"Sent WebSocket chat title update for session {writing_session.id}")
            else:
                logger.debug(f"No writing session found for chat {chat_id}, skipping WebSocket update")
                # Let's also check what writing sessions exist
                all_sessions = db.query(WritingSession).all()
                logger.debug(f"All writing sessions: {[(s.id, s.chat_id) for s in all_sessions]}")
                
        except Exception as e:
            logger.error(f"Error sending WebSocket chat title update: {e}", exc_info=True)
            # Don't fail the title update if WebSocket fails
            
    return db_chat

def delete_chat(db: Session, chat_id: str, user_id: int) -> bool:
    """Delete a chat and all its messages, missions, and execution logs."""
    db_chat = get_chat(db, chat_id, user_id)
    if db_chat:
        # First, delete all execution logs for all missions in this chat
        missions = get_chat_missions(db, chat_id, user_id)
        total_deleted_logs = 0
        for mission in missions:
            deleted_logs_count = delete_mission_execution_logs(db, mission.id, user_id)
            total_deleted_logs += deleted_logs_count
        
        if total_deleted_logs > 0:
            logger.info(f"Deleted {total_deleted_logs} execution logs for chat {chat_id}")
        
        # Then delete the chat (which will cascade delete messages and missions due to foreign key constraints)
        db.delete(db_chat)
        db.commit()
        logger.info(f"Deleted chat {chat_id} with all associated data")
        return True
    return False

# Message CRUD operations
def create_message(db: Session, message_id: str, chat_id: str, content: str, role: str) -> Message:
    """Create a new message in a chat."""
    db_message = Message(
        id=message_id,
        chat_id=chat_id,
        content=content,
        role=role,
        created_at=get_current_time()
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def get_chat_messages(db: Session, chat_id: str, user_id: int, skip: int = 0, limit: int = 100) -> List[Message]:
    """Get messages for a chat, ensuring the chat belongs to the user."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return []
    
    return db.query(Message).filter(Message.chat_id == chat_id).order_by(
        Message.created_at.asc()
    ).offset(skip).limit(limit).all()

def clear_chat_messages(db: Session, chat_id: str, user_id: int) -> bool:
    """Clear all messages from a chat, ensuring the chat belongs to the user."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return False
    
    # Delete all messages for this chat
    deleted_count = db.query(Message).filter(Message.chat_id == chat_id).delete()
    db.commit()
    
    logger.info(f"Cleared {deleted_count} messages from chat {chat_id}")
    return True

def delete_message(db: Session, message_id: str, chat_id: str, user_id: int) -> bool:
    """Delete a specific message from a chat, ensuring the chat belongs to the user."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return False
    
    # Find and delete the specific message
    message = db.query(Message).filter(
        and_(Message.id == message_id, Message.chat_id == chat_id)
    ).first()
    
    if message:
        db.delete(message)
        db.commit()
        logger.info(f"Deleted message {message_id} from chat {chat_id}")
        return True
    
    return False

def delete_message_pair(db: Session, message_id: str, chat_id: str, user_id: int) -> int:
    """Delete a user-assistant message pair from a chat, ensuring the chat belongs to the user."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return 0
    
    # Get all messages for this chat ordered by creation time
    all_messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at.asc()).all()
    
    if not all_messages:
        return 0
    
    # Find the target message
    target_message = None
    target_index = -1
    for i, msg in enumerate(all_messages):
        if msg.id == message_id:
            target_message = msg
            target_index = i
            break
    
    if not target_message:
        return 0
    
    # Determine which messages to delete based on the target message
    messages_to_delete = []
    
    if target_message.role == 'user':
        # If user message is clicked, delete the user message and the following assistant message (if exists)
        messages_to_delete.append(target_message)
        if target_index + 1 < len(all_messages) and all_messages[target_index + 1].role == 'assistant':
            messages_to_delete.append(all_messages[target_index + 1])
    else:
        # If assistant message is clicked, find the preceding user message and delete both
        # Look backwards for the user message that started this conversation pair
        user_message = None
        for i in range(target_index - 1, -1, -1):
            if all_messages[i].role == 'user':
                user_message = all_messages[i]
                break
        
        if user_message:
            messages_to_delete.append(user_message)
            messages_to_delete.append(target_message)
        else:
            # If no preceding user message found, just delete the assistant message
            messages_to_delete.append(target_message)
    
    # Delete the identified messages
    deleted_count = 0
    for msg in messages_to_delete:
        db.delete(msg)
        deleted_count += 1
    
    db.commit()
    
    logger.info(f"Deleted {deleted_count} messages in pair starting from message {message_id} in chat {chat_id}")
    return deleted_count

def delete_messages_from_point(db: Session, chat_id: str, from_message_id: str, user_id: int) -> int:
    """Delete all messages from a specific message onwards (for regeneration), ensuring the chat belongs to the user."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return 0
    
    # Get the timestamp of the message we're starting from
    from_message = db.query(Message).filter(
        and_(Message.id == from_message_id, Message.chat_id == chat_id)
    ).first()
    
    if not from_message:
        return 0
    
    # Delete all messages from this timestamp onwards (including the message itself)
    deleted_count = db.query(Message).filter(
        and_(
            Message.chat_id == chat_id,
            Message.created_at >= from_message.created_at
        )
    ).delete()
    
    db.commit()
    
    logger.info(f"Deleted {deleted_count} messages from message {from_message_id} onwards in chat {chat_id}")
    return deleted_count

# Mission CRUD operations
def create_mission(db: Session, mission_id: str, chat_id: str, user_request: str, 
                  mission_context: Optional[Dict[str, Any]] = None) -> Mission:
    """Create a new mission associated with a chat."""
    now = get_current_time()
    db_mission = Mission(
        id=mission_id,
        chat_id=chat_id,
        user_request=user_request,
        status="pending",
        mission_context=mission_context,
        created_at=now,
        updated_at=now
    )
    db.add(db_mission)
    db.commit()
    db.refresh(db_mission)
    return db_mission

def get_mission(db: Session, mission_id: str, user_id: int) -> Optional[Mission]:
    """Get a mission by ID, ensuring it belongs to the user through the chat."""
    return db.query(Mission).join(Chat).filter(
        and_(Mission.id == mission_id, Chat.user_id == user_id)
    ).first()

def get_chat_missions(db: Session, chat_id: str, user_id: int) -> List[Mission]:
    """Get all missions for a chat, ensuring the chat belongs to the user."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return []
    
    return db.query(Mission).filter(Mission.chat_id == chat_id).order_by(
        Mission.created_at.desc()
    ).all()

def get_active_missions_for_chat(db: Session, chat_id: str, user_id: int) -> List[Mission]:
    """Get active missions (pending or running) for a chat."""
    # First verify the chat belongs to the user
    chat = get_chat(db, chat_id, user_id)
    if not chat:
        return []
    
    return db.query(Mission).filter(
        and_(
            Mission.chat_id == chat_id,
            or_(Mission.status == "pending", Mission.status == "running")
        )
    ).all()

def update_mission_status(db: Session, mission_id: str, status: str, 
                         error_info: Optional[str] = None) -> Optional[Mission]:
    """Update a mission's status."""
    db_mission = db.query(Mission).filter(Mission.id == mission_id).first()
    if db_mission:
        db_mission.status = status
        if error_info:
            db_mission.error_info = error_info
        db_mission.updated_at = get_current_time()
        db.commit()
        db.refresh(db_mission)
    return db_mission

def update_mission_context(db: Session, mission_id: str, 
                          mission_context: Dict[str, Any]) -> Optional[Mission]:
    """Update a mission's context data."""
    db_mission = db.query(Mission).filter(Mission.id == mission_id).first()
    if db_mission:
        db_mission.mission_context = mission_context
        db_mission.updated_at = get_current_time()
        db.commit()
        db.refresh(db_mission)
    return db_mission

def get_user_missions(db: Session, user_id: int, status: Optional[str] = None, 
                     skip: int = 0, limit: int = 100) -> List[Mission]:
    """Get missions for a user, optionally filtered by status."""
    query = db.query(Mission).join(Chat).filter(Chat.user_id == user_id)
    
    if status:
        query = query.filter(Mission.status == status)
    
    return query.order_by(Mission.created_at.desc()).offset(skip).limit(limit).all()

def get_all_missions(db: Session) -> List[Mission]:
    """
    Retrieves all missions from the database.
    Used for loading missions into memory on application startup.
    """
    return db.query(Mission).order_by(Mission.created_at.desc()).all()

def delete_mission(db: Session, mission_id: str, user_id: int) -> bool:
    """Delete a mission and all associated execution logs, ensuring it belongs to the user."""
    db_mission = get_mission(db, mission_id, user_id)
    if db_mission:
        # First delete all execution logs for this mission
        deleted_logs_count = delete_mission_execution_logs(db, mission_id, user_id)
        logger.info(f"Deleted {deleted_logs_count} execution logs for mission {mission_id}")
        
        # Then delete the mission itself
        db.delete(db_mission)
        db.commit()
        logger.info(f"Deleted mission {mission_id}")
        return True
    return False

# Document CRUD operations
def create_document(db: Session, doc_id: str, user_id: int, original_filename: str, metadata: Dict[str, Any],
                   processing_status: str = "pending", upload_progress: int = 0, 
                   file_size: Optional[int] = None, file_path: Optional[str] = None) -> Document:
    """Create a new document record."""
    db_document = Document(
        id=doc_id,
        user_id=user_id,
        original_filename=original_filename,
        metadata_=metadata,
        processing_status=processing_status,
        upload_progress=upload_progress,
        file_size=file_size,
        file_path=file_path,
        created_at=get_current_time()
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

def get_document(db: Session, doc_id: str, user_id: int) -> Optional[Document]:
    """Get a document by ID, ensuring it belongs to the user."""
    return db.query(Document).filter(
        and_(Document.id == doc_id, Document.user_id == user_id)
    ).first()

def get_user_documents(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Document]:
    """Get all documents for a user."""
    return db.query(Document).filter(Document.user_id == user_id).order_by(
        Document.created_at.desc()
    ).offset(skip).limit(limit).all()

def delete_document(db: Session, doc_id: str, user_id: int) -> bool:
    """Delete a document from database and vector store."""
    db_document = get_document(db, doc_id, user_id)
    if db_document:
        # Remove from vector store first
        try:
            from services.document_service import document_service
            # Get vector store and remove document chunks
            vector_store = document_service._get_vector_store()
            
            # Remove from dense collection
            dense_collection = vector_store.dense_collection
            dense_results = dense_collection.get(where={"doc_id": doc_id})
            if dense_results['ids']:
                dense_collection.delete(ids=dense_results['ids'])
                logger.info(f"Removed {len(dense_results['ids'])} chunks from dense collection for document {doc_id}")
            
            # Remove from sparse collection
            sparse_collection = vector_store.sparse_collection
            sparse_results = sparse_collection.get(where={"doc_id": doc_id})
            if sparse_results['ids']:
                sparse_collection.delete(ids=sparse_results['ids'])
                logger.info(f"Removed {len(sparse_results['ids'])} chunks from sparse collection for document {doc_id}")
                
        except Exception as e:
            logger.warning(f"Failed to remove document {doc_id} from vector store: {e}")
            # Continue with database deletion even if vector store cleanup fails
        
        # Remove from database
        db.delete(db_document)
        db.commit()
        logger.info(f"Deleted document {doc_id} from database")
        return True
    return False

# DocumentGroup CRUD operations
def create_document_group(db: Session, group_id: str, user_id: int, name: str, description: Optional[str] = None) -> DocumentGroup:
    """Create a new document group."""
    now = get_current_time()
    db_group = DocumentGroup(
        id=group_id,
        user_id=user_id,
        name=name,
        description=description,
        created_at=now,
        updated_at=now
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group

def get_document_group(db: Session, group_id: str, user_id: int) -> Optional[DocumentGroup]:
    """Get a document group by ID, ensuring it belongs to the user."""
    return db.query(DocumentGroup).options(joinedload(DocumentGroup.documents)).filter(
        and_(DocumentGroup.id == group_id, DocumentGroup.user_id == user_id)
    ).first()

def get_user_document_groups(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[DocumentGroup]:
    """Get all document groups for a user."""
    return db.query(DocumentGroup).filter(DocumentGroup.user_id == user_id).order_by(
        DocumentGroup.created_at.desc()
    ).offset(skip).limit(limit).all()

def update_document_group(db: Session, group_id: str, user_id: int, name: str, description: Optional[str] = None) -> Optional[DocumentGroup]:
    """Update a document group's name and description."""
    db_group = get_document_group(db, group_id, user_id)
    if db_group:
        db_group.name = name
        db_group.description = description
        db_group.updated_at = get_current_time()
        db.commit()
        db.refresh(db_group)
    return db_group

def delete_document_group(db: Session, group_id: str, user_id: int) -> bool:
    """Delete a document group."""
    db_group = get_document_group(db, group_id, user_id)
    if db_group:
        db.delete(db_group)
        db.commit()
        return True
    return False

def add_document_to_group(db: Session, group_id: str, doc_id: str, user_id: int) -> Optional[DocumentGroup]:
    """Add a document to a document group."""
    db_group = get_document_group(db, group_id, user_id)
    db_document = get_document(db, doc_id, user_id)
    if db_group and db_document:
        # Check if document is already in the group to avoid duplicate constraint error
        if db_document not in db_group.documents:
            try:
                db_group.documents.append(db_document)
                db.commit()
                db.refresh(db_group)
                logger.info(f"Added document {doc_id} to group {group_id}")
            except Exception as e:
                logger.error(f"Error adding document {doc_id} to group: {e}")
                db.rollback()
                return None
        else:
            logger.info(f"Document {doc_id} is already in group {group_id}")
    return db_group

def remove_document_from_group(db: Session, group_id: str, doc_id: str, user_id: int) -> Optional[DocumentGroup]:
    """Remove a document from a document group."""
    db_group = get_document_group(db, group_id, user_id)
    db_document = get_document(db, doc_id, user_id)
    if db_group and db_document and db_document in db_group.documents:
        db_group.documents.remove(db_document)
        db.commit()
        db.refresh(db_group)
    return db_group

def get_next_queued_document(db: Session) -> Optional[Document]:
    """Get the next document with 'queued' status."""
    return db.query(Document).filter(Document.processing_status == 'queued').order_by(Document.created_at).first()

def update_document_status(db: Session, doc_id: str, user_id: int, status: str, 
                          progress: Optional[int] = None, error: Optional[str] = None) -> Optional[Document]:
    """Update the processing status and progress of a document."""
    document = db.query(Document).filter(
        and_(Document.id == doc_id, Document.user_id == user_id)
    ).first()
    if document:
        document.processing_status = status
        if progress is not None:
            document.upload_progress = progress
        if error is not None:
            # Store error in metadata
            if not document.metadata_:
                document.metadata_ = {}
            document.metadata_['processing_error'] = error
        document.updated_at = get_current_time()
        db.commit()
        db.refresh(document)
        return document
    return None

# WritingSessionStats CRUD operations
def get_or_create_writing_session_stats(db: Session, session_id: str) -> WritingSessionStats:
    """Get existing stats or create new ones for a writing session."""
    stats = db.query(WritingSessionStats).filter(WritingSessionStats.session_id == session_id).first()
    if not stats:
        now = get_current_time()
        stats = WritingSessionStats(
            session_id=session_id,
            total_cost=0.0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_native_tokens=0,
            total_web_searches=0,
            total_document_searches=0,
            created_at=now,
            updated_at=now
        )
        db.add(stats)
        db.commit()
        db.refresh(stats)
    return stats

def update_writing_session_stats(db: Session, session_id: str, stats_update: schemas.WritingSessionStatsUpdate) -> Optional[WritingSessionStats]:
    """Update writing session stats with delta values."""
    stats = get_or_create_writing_session_stats(db, session_id)
    
    # Apply delta updates
    if stats_update.cost_delta:
        stats.total_cost = float(stats.total_cost) + stats_update.cost_delta
    if stats_update.prompt_tokens_delta:
        stats.total_prompt_tokens += stats_update.prompt_tokens_delta
    if stats_update.completion_tokens_delta:
        stats.total_completion_tokens += stats_update.completion_tokens_delta
    if stats_update.native_tokens_delta:
        stats.total_native_tokens += stats_update.native_tokens_delta
    if stats_update.web_searches_delta:
        stats.total_web_searches += stats_update.web_searches_delta
    if stats_update.document_searches_delta:
        stats.total_document_searches += stats_update.document_searches_delta
    
    stats.updated_at = get_current_time()
    db.commit()
    db.refresh(stats)
    return stats

def get_writing_session_stats(db: Session, session_id: str) -> Optional[WritingSessionStats]:
    """Get writing session stats by session ID."""
    return db.query(WritingSessionStats).filter(WritingSessionStats.session_id == session_id).first()

def clear_writing_session_stats(db: Session, session_id: str) -> Optional[WritingSessionStats]:
    """Reset all stats for a writing session to zero."""
    stats = db.query(WritingSessionStats).filter(WritingSessionStats.session_id == session_id).first()
    if stats:
        stats.total_cost = 0.0
        stats.total_prompt_tokens = 0
        stats.total_completion_tokens = 0
        stats.total_native_tokens = 0
        stats.total_web_searches = 0
        stats.total_document_searches = 0
        stats.updated_at = get_current_time()
        db.commit()
        db.refresh(stats)
    return stats

# Dashboard Stats CRUD operations
def get_dashboard_stats(db: Session, user_id: int) -> Dict[str, Any]:
    """Get dashboard statistics for a user."""
    from database.models import WritingSession
    
    logger.info(f"Getting dashboard stats for user_id: {user_id}")
    
    # Get total chats
    total_chats = db.query(Chat).filter(Chat.user_id == user_id).count()
    logger.info(f"Total chats for user {user_id}: {total_chats}")
    
    # Get research sessions (chats with type 'research')
    research_sessions = db.query(Chat).filter(
        and_(Chat.user_id == user_id, Chat.chat_type == "research")
    ).count()
    logger.info(f"Research sessions for user {user_id}: {research_sessions}")
    
    # Get writing sessions (chats with type 'writing') - Fixed to count writing chats, not WritingSession records
    writing_sessions = db.query(Chat).filter(
        and_(Chat.user_id == user_id, Chat.chat_type == "writing")
    ).count()
    logger.info(f"Writing sessions for user {user_id}: {writing_sessions}")
    
    # Get total documents (only count successfully processed documents)
    total_documents = db.query(Document).filter(
        and_(Document.user_id == user_id, Document.processing_status == 'completed')
    ).count()
    logger.info(f"Total completed documents for user {user_id}: {total_documents}")
    
    # Debug: Let's also check what users exist in the database
    all_users = db.query(User.id, User.username).all()
    logger.info(f"All users in database: {[(u.id, u.username) for u in all_users]}")
    
    # Debug: Check what documents exist and their user_ids
    all_docs = db.query(Document.id, Document.user_id, Document.original_filename).limit(5).all()
    logger.info(f"Sample documents: {[(d.id, d.user_id, d.original_filename) for d in all_docs]}")
    
    # Debug: Check what chats exist and their user_ids
    all_chats = db.query(Chat.id, Chat.user_id, Chat.title, Chat.chat_type).limit(5).all()
    logger.info(f"Sample chats: {[(c.id, c.user_id, c.title, c.chat_type) for c in all_chats]}")
    
    # Get total writing session records (the actual WritingSession table)
    total_writing_session_records = db.query(WritingSession).join(Chat).filter(
        Chat.user_id == user_id
    ).count()
    logger.info(f"Total WritingSession records for user {user_id}: {total_writing_session_records}")
    
    # Get total missions
    total_missions = db.query(Mission).join(Chat).filter(
        Chat.user_id == user_id
    ).count()
    logger.info(f"Total missions for user {user_id}: {total_missions}")
    
    # Get completed missions
    completed_missions = db.query(Mission).join(Chat).filter(
        and_(Chat.user_id == user_id, Mission.status == "completed")
    ).count()
    logger.info(f"Completed missions for user {user_id}: {completed_missions}")
    
    # Get active missions (pending or running)
    active_missions = db.query(Mission).join(Chat).filter(
        and_(
            Chat.user_id == user_id,
            or_(Mission.status == "pending", Mission.status == "running")
        )
    ).count()
    logger.info(f"Active missions for user {user_id}: {active_missions}")
    
    # Get recent activity (most recent chat update)
    recent_activity = None
    latest_chat = db.query(Chat).filter(Chat.user_id == user_id).order_by(
        Chat.updated_at.desc()
    ).first()
    
    if latest_chat:
        now = get_current_time()
        # Ensure both datetimes have timezone info for comparison
        chat_updated_at = latest_chat.updated_at
        if chat_updated_at.tzinfo is None:
            # If the stored datetime is naive, assume it's in the server timezone
            chat_updated_at = chat_updated_at.replace(tzinfo=SERVER_TIMEZONE)
        elif now.tzinfo is None:
            # If current time is naive, add server timezone
            now = now.replace(tzinfo=SERVER_TIMEZONE)
        
        time_diff = now - chat_updated_at
        
        if time_diff.days > 0:
            recent_activity = f"{time_diff.days} day{'s' if time_diff.days > 1 else ''} ago"
        elif time_diff.seconds > 3600:
            hours = time_diff.seconds // 3600
            recent_activity = f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif time_diff.seconds > 60:
            minutes = time_diff.seconds // 60
            recent_activity = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            recent_activity = "Just now"
    else:
        recent_activity = "No recent activity"
    
    stats_result = {
        "total_chats": total_chats,
        "total_documents": total_documents,
        "total_writing_sessions": writing_sessions,  # Fixed to use writing chats count
        "total_missions": total_missions,
        "recent_activity": recent_activity,
        "research_sessions": research_sessions,
        "writing_sessions": writing_sessions,  # Fixed to use writing chats count
        "completed_missions": completed_missions,
        "active_missions": active_missions
    }
    
    logger.info(f"Dashboard stats result for user {user_id}: {stats_result}")
    return stats_result

def update_user_password(db: Session, user_id: int, new_password: str):
    """Update user password with proper hashing"""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return None
    
    db_user.hashed_password = get_password_hash(new_password)
    db_user.updated_at = get_current_time()
    db.commit()
    db.refresh(db_user)
    return db_user

# System Settings CRUD
def get_system_setting(db: Session, key: str) -> Optional[SystemSetting]:
    """Retrieve a system setting by its key."""
    return db.query(SystemSetting).filter(SystemSetting.key == key).first()

def create_system_setting(db: Session, key: str, value: Any) -> SystemSetting:
    """Create a new system setting."""
    now = get_current_time()
    db_setting = SystemSetting(
        key=key,
        value=value,
        created_at=now,
        updated_at=now
    )
    db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting

def update_system_setting(db: Session, key: str, value: Any) -> SystemSetting:
    """Update an existing system setting or create it if it doesn't exist."""
    db_setting = get_system_setting(db, key)
    if db_setting:
        db_setting.value = value
        db_setting.updated_at = get_current_time()
        db.commit()
        db.refresh(db_setting)
        return db_setting
    else:
        return create_system_setting(db, key, value)

# Mission Execution Log CRUD operations
def create_execution_log(
    db: Session,
    mission_id: str,
    timestamp: datetime,
    agent_name: str,
    action: str,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    full_input: Optional[Dict[str, Any]] = None,
    full_output: Optional[Dict[str, Any]] = None,
    model_details: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    file_interactions: Optional[List[str]] = None,
    cost: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    native_tokens: Optional[int] = None
) -> MissionExecutionLog:
    """Create a new execution log entry for a mission."""
    log_id = str(uuid.uuid4())
    now = get_current_time()
    
    db_log = MissionExecutionLog(
        id=log_id,
        mission_id=mission_id,
        timestamp=timestamp,
        agent_name=agent_name,
        action=action,
        input_summary=input_summary,
        output_summary=output_summary,
        status=status,
        error_message=error_message,
        full_input=full_input,
        full_output=full_output,
        model_details=model_details,
        tool_calls=tool_calls,
        file_interactions=file_interactions,
        cost=cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        native_tokens=native_tokens,
        created_at=now
    )
    
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

def get_mission_execution_logs(
    db: Session,
    mission_id: str,
    user_id: int,
    skip: int = 0,
    limit: int = 1000,
    agent_name: Optional[str] = None,
    status: Optional[str] = None
) -> List[MissionExecutionLog]:
    """Get execution logs for a mission, ensuring the mission belongs to the user."""
    # First verify the mission belongs to the user
    mission = get_mission(db, mission_id, user_id)
    if not mission:
        return []
    
    query = db.query(MissionExecutionLog).filter(MissionExecutionLog.mission_id == mission_id)
    
    if agent_name:
        query = query.filter(MissionExecutionLog.agent_name == agent_name)
    
    if status:
        query = query.filter(MissionExecutionLog.status == status)
    
    return query.order_by(MissionExecutionLog.timestamp.asc()).offset(skip).limit(limit).all()

def get_execution_log_count(db: Session, mission_id: str, user_id: int) -> int:
    """Get the total count of execution logs for a mission."""
    # First verify the mission belongs to the user
    mission = get_mission(db, mission_id, user_id)
    if not mission:
        return 0
    
    return db.query(MissionExecutionLog).filter(MissionExecutionLog.mission_id == mission_id).count()

def get_latest_execution_logs(
    db: Session,
    mission_id: str,
    user_id: int,
    limit: int = 50
) -> List[MissionExecutionLog]:
    """Get the most recent execution logs for a mission."""
    # First verify the mission belongs to the user
    mission = get_mission(db, mission_id, user_id)
    if not mission:
        return []
    
    return db.query(MissionExecutionLog).filter(
        MissionExecutionLog.mission_id == mission_id
    ).order_by(MissionExecutionLog.timestamp.desc()).limit(limit).all()

def delete_mission_execution_logs(db: Session, mission_id: str, user_id: int) -> int:
    """Delete all execution logs for a mission, ensuring the mission belongs to the user."""
    # First verify the mission belongs to the user
    mission = get_mission(db, mission_id, user_id)
    if not mission:
        return 0
    
    deleted_count = db.query(MissionExecutionLog).filter(
        MissionExecutionLog.mission_id == mission_id
    ).delete()
    
    db.commit()
    logger.info(f"Deleted {deleted_count} execution logs for mission {mission_id}")
    return deleted_count

def get_execution_logs_since_timestamp(
    db: Session,
    mission_id: str,
    user_id: int,
    since_timestamp: datetime,
    limit: int = 100
) -> List[MissionExecutionLog]:
    """Get execution logs for a mission since a specific timestamp."""
    # First verify the mission belongs to the user
    mission = get_mission(db, mission_id, user_id)
    if not mission:
        return []
    
    return db.query(MissionExecutionLog).filter(
        and_(
            MissionExecutionLog.mission_id == mission_id,
            MissionExecutionLog.timestamp > since_timestamp
        )
    ).order_by(MissionExecutionLog.timestamp.asc()).limit(limit).all()

def get_execution_log_stats(db: Session, mission_id: str, user_id: int) -> Dict[str, Any]:
    """Get statistics about execution logs for a mission."""
    # First verify the mission belongs to the user
    mission = get_mission(db, mission_id, user_id)
    if not mission:
        return {}
    
    # Get total count
    total_logs = db.query(MissionExecutionLog).filter(
        MissionExecutionLog.mission_id == mission_id
    ).count()
    
    # Get count by status
    status_counts = {}
    for status in ['success', 'failure', 'warning', 'running']:
        count = db.query(MissionExecutionLog).filter(
            and_(
                MissionExecutionLog.mission_id == mission_id,
                MissionExecutionLog.status == status
            )
        ).count()
        status_counts[status] = count
    
    # Get count by agent
    agent_counts = {}
    agent_results = db.query(
        MissionExecutionLog.agent_name,
        db.func.count(MissionExecutionLog.id).label('count')
    ).filter(
        MissionExecutionLog.mission_id == mission_id
    ).group_by(MissionExecutionLog.agent_name).all()
    
    for agent_name, count in agent_results:
        agent_counts[agent_name] = count
    
    # Calculate total costs and tokens
    cost_sum = db.query(db.func.sum(MissionExecutionLog.cost)).filter(
        and_(
            MissionExecutionLog.mission_id == mission_id,
            MissionExecutionLog.cost.isnot(None)
        )
    ).scalar() or 0.0
    
    prompt_tokens_sum = db.query(db.func.sum(MissionExecutionLog.prompt_tokens)).filter(
        and_(
            MissionExecutionLog.mission_id == mission_id,
            MissionExecutionLog.prompt_tokens.isnot(None)
        )
    ).scalar() or 0
    
    completion_tokens_sum = db.query(db.func.sum(MissionExecutionLog.completion_tokens)).filter(
        and_(
            MissionExecutionLog.mission_id == mission_id,
            MissionExecutionLog.completion_tokens.isnot(None)
        )
    ).scalar() or 0
    
    return {
        "total_logs": total_logs,
        "status_counts": status_counts,
        "agent_counts": agent_counts,
        "total_cost": float(cost_sum),
        "total_prompt_tokens": prompt_tokens_sum,
        "total_completion_tokens": completion_tokens_sum,
        "total_tokens": prompt_tokens_sum + completion_tokens_sum
    }
