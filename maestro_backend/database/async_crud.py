"""
Async CRUD operations for database interactions.
These operations use SQLAlchemy's async capabilities with asyncpg driver.
"""
import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.orm import selectinload
from . import models
from api import schemas

logger = logging.getLogger(__name__)

def get_current_time() -> datetime:
    """Get current UTC time for consistent timestamp handling."""
    return datetime.now(timezone.utc)

# ============================================================================
# MISSION OPERATIONS
# ============================================================================

async def create_mission(
    db: AsyncSession,
    mission_id: str,
    chat_id: str,
    user_request: str,
    mission_context: Optional[Dict[str, Any]] = None
) -> models.Mission:
    """Create a new mission asynchronously."""
    db_mission = models.Mission(
        id=mission_id,
        chat_id=chat_id,
        user_request=user_request,
        status="pending",
        mission_context=mission_context,
        created_at=get_current_time(),
        updated_at=get_current_time()
    )
    db.add(db_mission)
    await db.commit()
    await db.refresh(db_mission)
    logger.info(f"Created mission {mission_id} in database")
    return db_mission

async def get_mission(
    db: AsyncSession,
    mission_id: str,
    user_id: Optional[int] = None
) -> Optional[models.Mission]:
    """Get a mission by ID asynchronously."""
    query = select(models.Mission).where(models.Mission.id == mission_id)
    
    # If user_id is provided, join with chat to verify ownership
    if user_id is not None:
        query = query.join(models.Chat).where(models.Chat.user_id == user_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_all_missions(db: AsyncSession) -> List[models.Mission]:
    """Get all missions from the database asynchronously."""
    result = await db.execute(select(models.Mission))
    return result.scalars().all()

async def update_mission_status(
    db: AsyncSession,
    mission_id: str,
    status: str,
    error_info: Optional[str] = None
) -> Optional[models.Mission]:
    """Update mission status asynchronously."""
    stmt = (
        update(models.Mission)
        .where(models.Mission.id == mission_id)
        .values(
            status=status,
            error_info=error_info,
            updated_at=get_current_time()
        )
        .returning(models.Mission)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one_or_none()

async def update_mission_context(
    db: AsyncSession,
    mission_id: str,
    mission_context: Dict[str, Any]
) -> Optional[models.Mission]:
    """Update mission context asynchronously."""
    stmt = (
        update(models.Mission)
        .where(models.Mission.id == mission_id)
        .values(
            mission_context=mission_context,
            updated_at=get_current_time()
        )
        .returning(models.Mission)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one_or_none()

async def update_mission_context_no_timestamp(
    db: AsyncSession,
    mission_id: str,
    mission_context: Dict[str, Any]
) -> Optional[models.Mission]:
    """Update mission context without updating the timestamp (for user edits)."""
    stmt = (
        update(models.Mission)
        .where(models.Mission.id == mission_id)
        .values(
            mission_context=mission_context
            # Note: NOT updating updated_at timestamp
        )
        .returning(models.Mission)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one_or_none()

async def delete_mission(
    db: AsyncSession,
    mission_id: str,
    user_id: int
) -> bool:
    """Delete a mission asynchronously."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return False
    
    stmt = delete(models.Mission).where(models.Mission.id == mission_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

# ============================================================================
# EXECUTION LOG OPERATIONS
# ============================================================================

async def create_execution_log(
    db: AsyncSession,
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
) -> models.MissionExecutionLog:
    """Create a new execution log entry asynchronously - EXACT SAME SIGNATURE AS SYNC VERSION."""
    log_id = str(uuid.uuid4())
    now = get_current_time()
    
    db_log = models.MissionExecutionLog(
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
    await db.commit()
    await db.refresh(db_log)
    return db_log

async def get_mission_execution_logs(
    db: AsyncSession,
    mission_id: str,
    user_id: int,
    skip: int = 0,
    limit: int = 1000,
    agent_name: Optional[str] = None,
    status: Optional[str] = None
) -> List[models.MissionExecutionLog]:
    """Get execution logs for a mission, ensuring the mission belongs to the user."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return []
    
    query = select(models.MissionExecutionLog).where(
        models.MissionExecutionLog.mission_id == mission_id
    )
    
    if agent_name:
        query = query.where(models.MissionExecutionLog.agent_name == agent_name)
    
    if status:
        query = query.where(models.MissionExecutionLog.status == status)
    
    query = query.order_by(models.MissionExecutionLog.timestamp.asc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_execution_log_count(db: AsyncSession, mission_id: str, user_id: int) -> int:
    """Get the total count of execution logs for a mission."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return 0
    
    from sqlalchemy import func
    query = select(func.count(models.MissionExecutionLog.id)).where(
        models.MissionExecutionLog.mission_id == mission_id
    )
    result = await db.execute(query)
    return result.scalar() or 0

# Alias for consistency with other function names
async def get_mission_execution_logs_count(db: AsyncSession, mission_id: str, user_id: int) -> int:
    """Alias for get_execution_log_count for consistency."""
    return await get_execution_log_count(db, mission_id, user_id)

async def get_latest_execution_logs(
    db: AsyncSession,
    mission_id: str,
    user_id: int,
    limit: int = 50
) -> List[models.MissionExecutionLog]:
    """Get the most recent execution logs for a mission."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return []
    
    query = select(models.MissionExecutionLog).where(
        models.MissionExecutionLog.mission_id == mission_id
    ).order_by(models.MissionExecutionLog.timestamp.desc()).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def delete_mission_execution_logs(db: AsyncSession, mission_id: str, user_id: int) -> int:
    """Delete all execution logs for a mission, ensuring the mission belongs to the user."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return 0
    
    stmt = delete(models.MissionExecutionLog).where(
        models.MissionExecutionLog.mission_id == mission_id
    )
    result = await db.execute(stmt)
    await db.commit()
    logger.info(f"Deleted {result.rowcount} execution logs for mission {mission_id}")
    return result.rowcount

async def delete_mission_execution_log(db: AsyncSession, log_id: str) -> bool:
    """Delete a single execution log by its ID."""
    stmt = delete(models.MissionExecutionLog).where(
        models.MissionExecutionLog.id == log_id
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

async def get_execution_logs_since_timestamp(
    db: AsyncSession,
    mission_id: str,
    user_id: int,
    since_timestamp: datetime,
    limit: int = 100
) -> List[models.MissionExecutionLog]:
    """Get execution logs for a mission since a specific timestamp."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return []
    
    query = select(models.MissionExecutionLog).where(
        and_(
            models.MissionExecutionLog.mission_id == mission_id,
            models.MissionExecutionLog.timestamp > since_timestamp
        )
    ).order_by(models.MissionExecutionLog.timestamp.asc()).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_execution_log_stats(db: AsyncSession, mission_id: str, user_id: int) -> Dict[str, Any]:
    """Get statistics about execution logs for a mission."""
    # First verify the mission belongs to the user
    mission = await get_mission(db, mission_id, user_id)
    if not mission:
        return {}
    
    from sqlalchemy import func
    
    # Get total count
    total_query = select(func.count(models.MissionExecutionLog.id)).where(
        models.MissionExecutionLog.mission_id == mission_id
    )
    total_result = await db.execute(total_query)
    total_logs = total_result.scalar() or 0
    
    # Get count by status
    status_counts = {}
    for status in ['success', 'failure', 'warning', 'running']:
        count_query = select(func.count(models.MissionExecutionLog.id)).where(
            and_(
                models.MissionExecutionLog.mission_id == mission_id,
                models.MissionExecutionLog.status == status
            )
        )
        count_result = await db.execute(count_query)
        status_counts[status] = count_result.scalar() or 0
    
    # Get count by agent
    agent_query = select(
        models.MissionExecutionLog.agent_name,
        func.count(models.MissionExecutionLog.id).label('count')
    ).where(
        models.MissionExecutionLog.mission_id == mission_id
    ).group_by(models.MissionExecutionLog.agent_name)
    
    agent_result = await db.execute(agent_query)
    agent_counts = {row[0]: row[1] for row in agent_result.all()}
    
    # Get time range
    time_query = select(
        func.min(models.MissionExecutionLog.timestamp).label('first_log'),
        func.max(models.MissionExecutionLog.timestamp).label('last_log')
    ).where(models.MissionExecutionLog.mission_id == mission_id)
    
    time_result = await db.execute(time_query)
    time_row = time_result.one_or_none()
    
    return {
        'total_logs': total_logs,
        'status_counts': status_counts,
        'agent_counts': agent_counts,
        'first_log_time': time_row[0] if time_row else None,
        'last_log_time': time_row[1] if time_row else None
    }

# Keep the old function for backwards compatibility
async def get_execution_logs(
    db: AsyncSession,
    mission_id: str,
    user_id: Optional[int] = None,
    limit: Optional[int] = None
) -> List[models.MissionExecutionLog]:
    """Get execution logs for a mission asynchronously (deprecated - use get_mission_execution_logs)."""
    if user_id is not None:
        return await get_mission_execution_logs(db, mission_id, user_id, skip=0, limit=limit or 1000)
    
    # Direct query without user verification (for backwards compatibility)
    query = select(models.MissionExecutionLog).where(
        models.MissionExecutionLog.mission_id == mission_id
    )
    
    query = query.order_by(models.MissionExecutionLog.timestamp.asc())
    
    if limit:
        query = query.limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

# ============================================================================
# USER OPERATIONS
# ============================================================================

async def get_user(db: AsyncSession, user_id: int) -> Optional[models.User]:
    """Get a user by ID asynchronously."""
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    return result.scalar_one_or_none()

async def get_user_settings(
    db: AsyncSession,
    user_id: int
) -> Optional[Dict[str, Any]]:
    """Get user settings asynchronously."""
    user = await get_user(db, user_id)
    return user.settings if user else None

async def update_user_settings(
    db: AsyncSession,
    user_id: int,
    settings: Dict[str, Any]
) -> Optional[models.User]:
    """Update user settings asynchronously."""
    user = await get_user(db, user_id)
    if not user:
        return None
    
    user.settings = settings
    user.updated_at = get_current_time()
    await db.commit()
    await db.refresh(user)
    return user

# ============================================================================
# CHAT OPERATIONS
# ============================================================================

async def get_chat(
    db: AsyncSession,
    chat_id: str,
    user_id: int
) -> Optional[models.Chat]:
    """Get a chat by ID asynchronously."""
    result = await db.execute(
        select(models.Chat)
        .options(
            selectinload(models.Chat.messages),
            selectinload(models.Chat.missions)
        )
        .where(
            and_(
                models.Chat.id == chat_id,
                models.Chat.user_id == user_id
            )
        )
    )
    return result.scalar_one_or_none()

async def get_chat_messages(
    db: AsyncSession,
    chat_id: str,
    user_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[models.Message]:
    """Get messages for a chat asynchronously."""
    # First verify the chat belongs to the user
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return []
    
    result = await db.execute(
        select(models.Message)
        .where(models.Message.chat_id == chat_id)
        .order_by(models.Message.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

# ============================================================================
# DOCUMENT OPERATIONS
# ============================================================================

async def get_document(
    db: AsyncSession,
    doc_id: str,
    user_id: Optional[int] = None
) -> Optional[models.Document]:
    """Get a document by ID asynchronously."""
    query = select(models.Document).where(models.Document.id == doc_id)
    
    if user_id is not None:
        query = query.where(models.Document.user_id == user_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_document_group(
    db: AsyncSession,
    document_group_id: str,
    user_id: int
) -> Optional[models.DocumentGroup]:
    """Get a document group by ID asynchronously."""
    result = await db.execute(
        select(models.DocumentGroup)
        .options(selectinload(models.DocumentGroup.documents))
        .where(
            and_(
                models.DocumentGroup.id == document_group_id,
                models.DocumentGroup.user_id == user_id
            )
        )
    )
    return result.scalar_one_or_none()

async def get_documents_in_group(
    db: AsyncSession,
    document_group_id: str,
    user_id: int
) -> List[str]:
    """Get document IDs in a group asynchronously."""
    group = await get_document_group(db, document_group_id, user_id)
    if not group:
        return []
    
    return [doc.id for doc in group.documents]

# ============================================================================
# COMPLETE USER OPERATIONS
# ============================================================================

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[models.User]:
    """Get a user by username asynchronously."""
    result = await db.execute(
        select(models.User).where(models.User.username == username)
    )
    return result.scalar_one_or_none()

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[models.User]:
    """Get a user by email asynchronously."""
    result = await db.execute(
        select(models.User).where(models.User.email == email)
    )
    return result.scalar_one_or_none()

async def get_users(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.User]:
    """Get a list of users asynchronously."""
    result = await db.execute(
        select(models.User).offset(skip).limit(limit)
    )
    return result.scalars().all()

async def create_user(db: AsyncSession, user: schemas.UserCreate) -> models.User:
    """Create a new user asynchronously."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        created_at=get_current_time(),
        updated_at=get_current_time()
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user(db: AsyncSession, user_id: int, user_update: schemas.UserUpdate) -> Optional[models.User]:
    """Update a user asynchronously."""
    user = await get_user(db, user_id)
    if not user:
        return None
    
    update_data = user_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    user.updated_at = get_current_time()
    await db.commit()
    await db.refresh(user)
    return user

async def delete_user(db: AsyncSession, user_id: int) -> Optional[models.User]:
    """Delete a user asynchronously."""
    user = await get_user(db, user_id)
    if not user:
        return None
    
    await db.delete(user)
    await db.commit()
    return user

async def update_user_profile(db: AsyncSession, user_id: int, profile_update: schemas.UserProfileUpdate) -> Optional[models.User]:
    """Update user profile asynchronously."""
    user = await get_user(db, user_id)
    if not user:
        return None
    
    if profile_update.full_name is not None:
        user.full_name = profile_update.full_name
    if profile_update.avatar_url is not None:
        user.avatar_url = profile_update.avatar_url
    
    user.updated_at = get_current_time()
    await db.commit()
    await db.refresh(user)
    return user

async def update_user_password(db: AsyncSession, user_id: int, new_password: str) -> Optional[models.User]:
    """Update user password with proper hashing"""
    from api.auth import get_password_hash
    
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        return None
    
    db_user.hashed_password = get_password_hash(new_password)
    db_user.updated_at = get_current_time()
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def update_user_appearance(db: AsyncSession, user_id: int, appearance_settings: schemas.AppearanceSettings) -> Optional[models.User]:
    """Update user appearance settings asynchronously."""
    user = await get_user(db, user_id)
    if not user:
        return None
    
    if not user.settings:
        user.settings = {}
    
    user.settings['appearance'] = appearance_settings.dict()
    user.updated_at = get_current_time()
    await db.commit()
    await db.refresh(user)
    return user

# ============================================================================
# COMPLETE CHAT OPERATIONS
# ============================================================================

async def create_chat(db: AsyncSession, chat_id: str, user_id: int, title: str, 
                     document_group_id: Optional[str] = None, chat_type: str = "research") -> models.Chat:
    """Create a new chat asynchronously."""
    db_chat = models.Chat(
        id=chat_id,
        user_id=user_id,
        title=title,
        document_group_id=document_group_id,
        chat_type=chat_type,
        created_at=get_current_time(),
        updated_at=get_current_time()
    )
    db.add(db_chat)
    await db.commit()
    await db.refresh(db_chat, attribute_names=['messages', 'missions'])
    return db_chat

async def get_user_chats(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> List[models.Chat]:
    """Get chats for a user asynchronously."""
    result = await db.execute(
        select(models.Chat)
        .where(models.Chat.user_id == user_id)
        .order_by(models.Chat.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def get_user_chats_by_type(db: AsyncSession, user_id: int, chat_type: str, 
                                 skip: int = 0, limit: int = 100, search_query: str = None) -> List[models.Chat]:
    """Get chats by type for a user asynchronously with optional search."""
    query = select(models.Chat).options(
        selectinload(models.Chat.messages),
        selectinload(models.Chat.missions)
    ).where(and_(models.Chat.user_id == user_id, models.Chat.chat_type == chat_type))
    
    # Add search filter if provided
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.where(models.Chat.title.ilike(search_pattern))
    
    query = query.order_by(models.Chat.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def count_user_chats_by_type(db: AsyncSession, user_id: int, chat_type: str, search_query: str = None) -> int:
    """Count total chats by type for a user with optional search."""
    query = select(func.count(models.Chat.id)).where(
        and_(models.Chat.user_id == user_id, models.Chat.chat_type == chat_type)
    )
    
    # Add search filter if provided
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.where(models.Chat.title.ilike(search_pattern))
    
    result = await db.execute(query)
    return result.scalar()

async def count_chat_messages(db: AsyncSession, chat_id: str, user_id: int) -> int:
    """Count messages for a specific chat."""
    # First verify the chat belongs to the user
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return 0
    
    query = select(func.count(models.Message.id)).where(
        models.Message.chat_id == chat_id
    )
    result = await db.execute(query)
    return result.scalar() or 0

async def count_active_missions_for_chat(db: AsyncSession, chat_id: str, user_id: int) -> int:
    """Count active missions for a specific chat."""
    # First verify the chat belongs to the user
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return 0
    
    query = select(func.count(models.Mission.id)).where(
        and_(
            models.Mission.chat_id == chat_id,
            models.Mission.status.in_(['running', 'pending'])
        )
    )
    result = await db.execute(query)
    return result.scalar() or 0

async def get_chats_with_counts(db: AsyncSession, user_id: int, chat_type: str, skip: int = 0, limit: int = 100, search_query: str = None) -> List[Dict]:
    """Get chats with message and mission counts in a single query."""
    # Main chat query
    chat_query = select(models.Chat).where(
        and_(models.Chat.user_id == user_id, models.Chat.chat_type == chat_type)
    )
    
    # Add search filter if provided
    if search_query:
        search_pattern = f"%{search_query}%"
        chat_query = chat_query.where(models.Chat.title.ilike(search_pattern))
    
    # Apply pagination - order by created_at for consistent chronological display
    chat_query = chat_query.order_by(models.Chat.created_at.desc()).offset(skip).limit(limit)
    
    # Execute query
    result = await db.execute(chat_query)
    chats = result.scalars().all()
    
    # Get all chat IDs
    chat_ids = [chat.id for chat in chats]
    
    if not chat_ids:
        return []
    
    # Get message counts for all chats in one query
    message_counts_query = select(
        models.Message.chat_id,
        func.count(models.Message.id).label('message_count')
    ).where(
        models.Message.chat_id.in_(chat_ids)
    ).group_by(models.Message.chat_id)
    
    message_result = await db.execute(message_counts_query)
    message_counts = {row.chat_id: row.message_count for row in message_result}
    
    # Get active mission counts for all chats in one query
    mission_counts_query = select(
        models.Mission.chat_id,
        func.count(models.Mission.id).label('mission_count')
    ).where(
        and_(
            models.Mission.chat_id.in_(chat_ids),
            models.Mission.status.in_(['running', 'pending'])
        )
    ).group_by(models.Mission.chat_id)
    
    mission_result = await db.execute(mission_counts_query)
    mission_counts = {row.chat_id: row.mission_count for row in mission_result}
    
    # Combine the results
    result_list = []
    for chat in chats:
        result_list.append({
            'chat': chat,
            'message_count': message_counts.get(chat.id, 0),
            'active_mission_count': mission_counts.get(chat.id, 0)
        })
    
    return result_list

async def update_chat_title(db: AsyncSession, chat_id: str, user_id: int, title: str) -> Optional[models.Chat]:
    """Update chat title asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return None
    
    chat.title = title
    chat.updated_at = get_current_time()
    await db.commit()
    await db.refresh(chat, attribute_names=['messages', 'missions'])
    return chat

async def update_chat_settings(db: AsyncSession, chat_id: str, user_id: int, settings: Dict[str, Any]) -> Optional[models.Chat]:
    """Update chat settings asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return None
    
    chat.settings = settings
    chat.updated_at = get_current_time()
    await db.commit()
    await db.refresh(chat, attribute_names=['messages', 'missions'])
    return chat

async def delete_chat(db: AsyncSession, chat_id: str, user_id: int) -> bool:
    """Delete a chat and all its messages asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return False
    
    # Delete all messages first
    await db.execute(
        delete(models.Message).where(models.Message.chat_id == chat_id)
    )
    
    # Delete the chat
    await db.delete(chat)
    await db.commit()
    return True

# ============================================================================
# MESSAGE OPERATIONS
# ============================================================================

async def create_message(db: AsyncSession, message_id: str, chat_id: str, 
                        content: str, role: str) -> models.Message:
    """Create a new message asynchronously."""
    db_message = models.Message(
        id=message_id,
        chat_id=chat_id,
        content=content,
        role=role,
        created_at=get_current_time()
    )
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message

async def clear_chat_messages(db: AsyncSession, chat_id: str, user_id: int) -> bool:
    """Clear all messages from a chat asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return False
    
    result = await db.execute(
        delete(models.Message).where(models.Message.chat_id == chat_id)
    )
    await db.commit()
    return result.rowcount > 0

async def delete_message(db: AsyncSession, message_id: str, chat_id: str, user_id: int) -> bool:
    """Delete a single message asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return False
    
    result = await db.execute(
        delete(models.Message).where(
            and_(models.Message.id == message_id, models.Message.chat_id == chat_id)
        )
    )
    await db.commit()
    return result.rowcount > 0

async def delete_message_pair(db: AsyncSession, message_id: str, chat_id: str, user_id: int) -> int:
    """Delete a message and the following assistant message asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return 0
    
    # Get the target message
    result = await db.execute(
        select(models.Message).where(
            and_(models.Message.id == message_id, models.Message.chat_id == chat_id)
        )
    )
    target_message = result.scalar_one_or_none()
    if not target_message:
        return 0
    
    # Find the next assistant message
    result = await db.execute(
        select(models.Message).where(
            and_(
                models.Message.chat_id == chat_id,
                models.Message.created_at > target_message.created_at,
                models.Message.role == "assistant"
            )
        ).order_by(models.Message.created_at.asc()).limit(1)
    )
    next_assistant = result.scalar_one_or_none()
    
    # Delete both messages
    deleted_count = 0
    await db.delete(target_message)
    deleted_count += 1
    
    if next_assistant:
        await db.delete(next_assistant)
        deleted_count += 1
    
    await db.commit()
    return deleted_count

async def delete_messages_from_point(db: AsyncSession, chat_id: str, from_message_id: str, user_id: int) -> int:
    """Delete all messages from a specific point onwards asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return 0
    
    # Get the starting message
    result = await db.execute(
        select(models.Message).where(
            and_(models.Message.id == from_message_id, models.Message.chat_id == chat_id)
        )
    )
    start_message = result.scalar_one_or_none()
    if not start_message:
        return 0
    
    # Delete all messages from this point onwards
    result = await db.execute(
        delete(models.Message).where(
            and_(
                models.Message.chat_id == chat_id,
                models.Message.created_at >= start_message.created_at
            )
        )
    )
    await db.commit()
    return result.rowcount

# ============================================================================
# MISSION OPERATIONS (Additional)
# ============================================================================

async def get_chat_missions(db: AsyncSession, chat_id: str, user_id: int) -> List[models.Mission]:
    """Get all missions for a chat asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return []
    
    result = await db.execute(
        select(models.Mission)
        .where(models.Mission.chat_id == chat_id)
        .order_by(models.Mission.created_at.desc())
    )
    return result.scalars().all()

async def get_active_missions_for_chat(db: AsyncSession, chat_id: str, user_id: int) -> List[models.Mission]:
    """Get active missions for a chat asynchronously."""
    chat = await get_chat(db, chat_id, user_id)
    if not chat:
        return []
    
    active_statuses = ['pending', 'running', 'planning']
    result = await db.execute(
        select(models.Mission)
        .where(
            and_(
                models.Mission.chat_id == chat_id,
                models.Mission.status.in_(active_statuses)
            )
        )
        .order_by(models.Mission.created_at.desc())
    )
    return result.scalars().all()

async def get_user_missions(db: AsyncSession, user_id: int, status: Optional[str] = None,
                           skip: int = 0, limit: int = 100) -> List[models.Mission]:
    """Get missions for a user asynchronously."""
    query = select(models.Mission).join(models.Chat).where(models.Chat.user_id == user_id)
    
    if status:
        query = query.where(models.Mission.status == status)
    
    query = query.order_by(models.Mission.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

# ============================================================================
# DOCUMENT OPERATIONS (Complete)
# ============================================================================

async def create_document(db: AsyncSession, doc_id: str, user_id: int, 
                         original_filename: str, metadata: Dict[str, Any],
                         content_hash: Optional[str] = None) -> models.Document:
    """Create a new document asynchronously."""
    db_document = models.Document(
        id=doc_id,
        user_id=user_id,
        original_filename=original_filename,
        content_hash=content_hash,
        processing_status="pending",
        upload_progress=0,
        metadata_=metadata,
        created_at=get_current_time(),
        updated_at=get_current_time()
    )
    db.add(db_document)
    await db.commit()
    await db.refresh(db_document)
    return db_document

async def get_user_documents(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> List[models.Document]:
    """Get documents for a user asynchronously."""
    result = await db.execute(
        select(models.Document)
        .where(models.Document.user_id == user_id)
        .order_by(models.Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def delete_document(db: AsyncSession, doc_id: str, user_id: int) -> bool:
    """Delete a document asynchronously."""
    document = await get_document(db, doc_id, user_id)
    if not document:
        return False
    
    # Remove from groups first
    await db.execute(
        delete(models.document_group_association)
        .where(models.document_group_association.c.document_id == doc_id)
    )
    
    # Delete the document
    await db.delete(document)
    await db.commit()
    return True

async def delete_document_simple(db: AsyncSession, doc_id: str, user_id: int) -> bool:
    """Simplified async deletion - only deletes from main database."""
    db_document = await get_document(db, doc_id, user_id)
    if db_document:
        try:
            await db.delete(db_document)
            await db.commit()
            logger.info(f"Deleted document {doc_id} from main database (async mode)")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id} from main database: {e}")
            await db.rollback()
    return False

async def update_document_status(db: AsyncSession, doc_id: str, user_id: int, status: str,
                                progress: Optional[int] = None, error: Optional[str] = None,
                                chunk_count: Optional[int] = None) -> Optional[models.Document]:
    """Update document processing status asynchronously."""
    document = await get_document(db, doc_id, user_id)
    if not document:
        return None
    
    document.processing_status = status
    if progress is not None:
        document.upload_progress = progress
    if error is not None:
        if not document.metadata_:
            document.metadata_ = {}
        document.metadata_['processing_error'] = error
    if chunk_count is not None:
        document.chunk_count = chunk_count
    
    document.updated_at = get_current_time()
    await db.commit()
    await db.refresh(document)
    return document

async def get_next_queued_document(db: AsyncSession) -> Optional[models.Document]:
    """Get the next document in queue for processing asynchronously."""
    result = await db.execute(
        select(models.Document)
        .where(models.Document.processing_status == "queued")
        .order_by(models.Document.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()

# ============================================================================
# DOCUMENT GROUP OPERATIONS
# ============================================================================

async def create_document_group(db: AsyncSession, group_id: str, user_id: int, 
                               name: str, description: Optional[str] = None) -> models.DocumentGroup:
    """Create a new document group asynchronously."""
    db_group = models.DocumentGroup(
        id=group_id,
        user_id=user_id,
        name=name,
        description=description,
        created_at=get_current_time(),
        updated_at=get_current_time()
    )
    db.add(db_group)
    await db.commit()
    await db.refresh(db_group)
    return db_group

async def get_user_document_groups(db: AsyncSession, user_id: int, 
                                  skip: int = 0, limit: int = 100) -> List[models.DocumentGroup]:
    """Get document groups for a user asynchronously."""
    result = await db.execute(
        select(models.DocumentGroup)
        .options(selectinload(models.DocumentGroup.documents))
        .where(models.DocumentGroup.user_id == user_id)
        .order_by(models.DocumentGroup.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()

async def update_document_group(db: AsyncSession, group_id: str, user_id: int,
                               name: str, description: Optional[str] = None) -> Optional[models.DocumentGroup]:
    """Update a document group asynchronously."""
    group = await get_document_group(db, group_id, user_id)
    if not group:
        return None
    
    group.name = name
    if description is not None:
        group.description = description
    group.updated_at = get_current_time()
    
    await db.commit()
    await db.refresh(group)
    return group

async def delete_document_group(db: AsyncSession, group_id: str, user_id: int) -> bool:
    """Delete a document group asynchronously."""
    group = await get_document_group(db, group_id, user_id)
    if not group:
        return False
    
    await db.delete(group)
    await db.commit()
    return True

async def add_document_to_group(db: AsyncSession, group_id: str, doc_id: str, user_id: int) -> Optional[models.DocumentGroup]:
    """Add a document to a group asynchronously."""
    group = await get_document_group(db, group_id, user_id)
    document = await get_document(db, doc_id, user_id)
    
    if not group or not document:
        return None
    
    # Check if already in group
    if document not in group.documents:
        group.documents.append(document)
        group.updated_at = get_current_time()
        await db.commit()
        await db.refresh(group)
    
    return group

async def remove_document_from_group(db: AsyncSession, group_id: str, doc_id: str, user_id: int) -> Optional[models.DocumentGroup]:
    """Remove a document from a group asynchronously."""
    group = await get_document_group(db, group_id, user_id)
    if not group:
        return None
    
    # Remove document from group
    group.documents = [doc for doc in group.documents if doc.id != doc_id]
    group.updated_at = get_current_time()
    
    await db.commit()
    await db.refresh(group)
    return group

# ============================================================================
# WRITING SESSION STATS OPERATIONS
# ============================================================================

async def get_or_create_writing_session_stats(db: AsyncSession, session_id: str) -> models.WritingSessionStats:
    """Get or create writing session stats asynchronously."""
    result = await db.execute(
        select(models.WritingSessionStats)
        .where(models.WritingSessionStats.session_id == session_id)
    )
    stats = result.scalar_one_or_none()
    
    if not stats:
        stats = models.WritingSessionStats(
            session_id=session_id,
            total_cost=0.0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_native_tokens=0,
            total_web_searches=0,
            total_document_searches=0,
            created_at=get_current_time(),
            updated_at=get_current_time()
        )
        db.add(stats)
        await db.commit()
        await db.refresh(stats)
    
    return stats

async def update_writing_session_stats(db: AsyncSession, session_id: str, 
                                      stats_update: schemas.WritingSessionStatsUpdate) -> Optional[models.WritingSessionStats]:
    """Update writing session stats asynchronously."""
    stats = await get_or_create_writing_session_stats(db, session_id)
    
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
    await db.commit()
    await db.refresh(stats)
    return stats

async def get_writing_session_stats(db: AsyncSession, session_id: str) -> Optional[models.WritingSessionStats]:
    """Get writing session stats asynchronously."""
    result = await db.execute(
        select(models.WritingSessionStats)
        .where(models.WritingSessionStats.session_id == session_id)
    )
    return result.scalar_one_or_none()

async def clear_writing_session_stats(db: AsyncSession, session_id: str) -> Optional[models.WritingSessionStats]:
    """Clear writing session stats asynchronously."""
    stats = await get_writing_session_stats(db, session_id)
    if stats:
        stats.total_cost = 0.0
        stats.total_prompt_tokens = 0
        stats.total_completion_tokens = 0
        stats.total_native_tokens = 0
        stats.total_web_searches = 0
        stats.total_document_searches = 0
        stats.updated_at = get_current_time()
        await db.commit()
        await db.refresh(stats)
    return stats

# ============================================================================
# DASHBOARD STATS OPERATIONS
# ============================================================================

async def get_dashboard_stats(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """Get dashboard statistics for a user asynchronously."""
    # Get total chats
    result = await db.execute(
        select(models.Chat).where(models.Chat.user_id == user_id)
    )
    total_chats = len(result.scalars().all())
    
    # Get research sessions
    result = await db.execute(
        select(models.Chat).where(
            and_(models.Chat.user_id == user_id, models.Chat.chat_type == "research")
        )
    )
    research_sessions = len(result.scalars().all())
    
    # Get writing sessions
    result = await db.execute(
        select(models.Chat).where(
            and_(models.Chat.user_id == user_id, models.Chat.chat_type == "writing")
        )
    )
    writing_sessions = len(result.scalars().all())
    
    # Get total documents
    result = await db.execute(
        select(models.Document).where(models.Document.user_id == user_id)
    )
    total_documents = len(result.scalars().all())
    
    # Get total document groups
    result = await db.execute(
        select(models.DocumentGroup).where(models.DocumentGroup.user_id == user_id)
    )
    total_document_groups = len(result.scalars().all())
    
    # Get total missions
    result = await db.execute(
        select(models.Mission).join(models.Chat).where(models.Chat.user_id == user_id)
    )
    total_missions = len(result.scalars().all())
    
    # Get completed missions
    result = await db.execute(
        select(models.Mission).join(models.Chat).where(
            and_(models.Chat.user_id == user_id, models.Mission.status == "completed")
        )
    )
    completed_missions = len(result.scalars().all())
    
    # Get active missions
    result = await db.execute(
        select(models.Mission).join(models.Chat).where(
            and_(
                models.Chat.user_id == user_id,
                models.Mission.status.in_(["pending", "running", "planning"])
            )
        )
    )
    active_missions = len(result.scalars().all())
    
    return {
        "total_chats": total_chats,
        "research_sessions": research_sessions,
        "writing_sessions": writing_sessions,
        "total_documents": total_documents,
        "total_document_groups": total_document_groups,
        "total_missions": total_missions,
        "completed_missions": completed_missions,
        "active_missions": active_missions
    }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


# ============================================================================
# SYSTEM SETTINGS OPERATIONS
# ============================================================================

async def get_system_setting(db: AsyncSession, key: str) -> Optional[models.SystemSetting]:
    """Retrieve a system setting by its key."""
    result = await db.execute(
        select(models.SystemSetting).where(models.SystemSetting.key == key)
    )
    return result.scalar_one_or_none()

async def create_system_setting(db: AsyncSession, key: str, value: Any) -> models.SystemSetting:
    """Create a new system setting."""
    now = get_current_time()
    db_setting = models.SystemSetting(
        key=key,
        value=value,
        created_at=now,
        updated_at=now
    )
    db.add(db_setting)
    await db.commit()
    await db.refresh(db_setting)
    return db_setting

async def update_system_setting(db: AsyncSession, key: str, value: Any) -> models.SystemSetting:
    """Update an existing system setting or create it if it doesn't exist."""
    db_setting = await get_system_setting(db, key)
    if db_setting:
        db_setting.value = value
        db_setting.updated_at = get_current_time()
        await db.commit()
        await db.refresh(db_setting)
        return db_setting
    else:
        return await create_system_setting(db, key, value)

# ============================================================================
# TEST FUNCTIONS
# ============================================================================

async def test_async_crud_connection(db: AsyncSession) -> bool:
    """Test that async CRUD operations work."""
    try:
        # Simple query to test connection
        result = await db.execute(select(models.User).limit(1))
        result.scalar_one_or_none()
        return True
    except Exception as e:
        logger.error(f"Async CRUD connection test failed: {e}")
        return False