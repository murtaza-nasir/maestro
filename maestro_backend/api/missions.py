from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Query, Body
from pydantic import BaseModel, Field
import pypandoc
import io
from typing import Dict, Optional, List, Any
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import queue
import time
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from api.schemas import (
    MissionResponse, MissionStatus, 
    MissionStats, MissionPlan, MissionReport, MissionLogs, MissionDraft,
    MissionContextResponse, MissionSettings, MissionSettingsResponse, MissionSettingsUpdate
)
from api.utils import process_execution_log_entry_for_frontend
from auth.dependencies import get_current_user_from_cookie
from database.database import SessionLocal, get_db
from database.async_database import get_async_db_session
from database import crud, async_crud, models
from database.models import User
from ai_researcher.agentic_layer.async_context_manager import AsyncContextManager, set_main_event_loop
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.agent_controller import AgentController
from ai_researcher import config
from ai_researcher.agentic_layer.controller.core_controller import MaybeSemaphore
from services.websocket_manager import websocket_manager
import json
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.user_context import set_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

class CreateDocumentGroupRequest(BaseModel):
    """Request to create a document group from mission documents."""
    include_web_sources: bool = Field(True, description="Include documents fetched from web searches")
    include_database_documents: bool = Field(True, description="Include documents from the document database")
    group_name: Optional[str] = Field(None, description="Custom name for the document group")

async def transform_note_for_frontend_batch(note, code_to_filename: dict) -> dict:
    """
    Optimized version of transform_note_for_frontend that uses pre-fetched filename mappings.
    """
    # Handle both Note objects and dictionaries
    if hasattr(note, 'model_dump'):
        note_dict = note.model_dump()
    else:
        note_dict = note
    
    # Start with the base note data
    transformed = note_dict.copy()
    
    # Map created_at to timestamp for frontend compatibility
    created_at = note_dict.get("created_at")
    updated_at = note_dict.get("updated_at")
    
    if created_at:
        if hasattr(created_at, 'isoformat'):
            transformed["timestamp"] = created_at.isoformat()
        else:
            transformed["timestamp"] = str(created_at)
    elif updated_at:
        if hasattr(updated_at, 'isoformat'):
            transformed["timestamp"] = updated_at.isoformat()
        else:
            transformed["timestamp"] = str(updated_at)
    else:
        from datetime import datetime
        transformed["timestamp"] = datetime.now().isoformat()
    
    # Get source information
    source_type = note_dict.get("source_type")
    source_id = note_dict.get("source_id")
    source_metadata = note_dict.get("source_metadata", {})
    
    # Add frontend-expected fields based on source_type
    if source_type == "web":
        url = source_metadata.get("url") or source_id
        transformed["url"] = url
        title = source_metadata.get("title", "Web Source")
        transformed["source"] = title
        
    elif source_type == "document":
        filename = source_metadata.get("original_filename")
        if filename:
            transformed["source"] = filename
        else:
            # Try to get document title from database if we have a UUID
            if source_id:
                # Check if source_id looks like a UUID
                import re
                uuid_pattern = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', re.IGNORECASE)
                if uuid_pattern.match(source_id):
                    # It's a UUID, fetch document from database
                    from database.database import get_db
                    from database.models import Document
                    db = next(get_db())
                    try:
                        doc = db.query(Document).filter(Document.id == source_id).first()
                        if doc:
                            # Prefer title from metadata, then filename
                            if doc.metadata_ and doc.metadata_.get('title'):
                                transformed["source"] = doc.metadata_['title']
                            elif doc.original_filename:
                                transformed["source"] = doc.original_filename
                            elif doc.filename:
                                transformed["source"] = doc.filename
                            else:
                                transformed["source"] = "Unknown Document"
                        else:
                            # Document not found, try legacy code extraction
                            from services.document_service import document_service
                            document_codes = document_service.extract_document_codes_from_text(source_id)
                            if document_codes and document_codes[0] in code_to_filename:
                                transformed["source"] = code_to_filename[document_codes[0]]
                            else:
                                transformed["source"] = source_id or "Unknown Document"
                    finally:
                        db.close()
                else:
                    # Not a UUID, try legacy code extraction
                    from services.document_service import document_service
                    document_codes = document_service.extract_document_codes_from_text(source_id)
                    if document_codes and document_codes[0] in code_to_filename:
                        transformed["source"] = code_to_filename[document_codes[0]]
                    else:
                        transformed["source"] = source_id or "Unknown Document"
            else:
                transformed["source"] = "Unknown Document"
        
        transformed.pop("url", None)
        
    elif source_type == "document_window":
        # Document window is a content window extracted from a document
        # The source_id should be the doc_id
        if source_id:
            # Check if source_id looks like a UUID
            import re
            uuid_pattern = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', re.IGNORECASE)
            if uuid_pattern.match(source_id):
                # It's a UUID, fetch document from database
                from database.database import get_db
                from database.models import Document
                db = next(get_db())
                try:
                    doc = db.query(Document).filter(Document.id == source_id).first()
                    if doc:
                        # Prefer title from metadata, then filename
                        if doc.metadata_ and doc.metadata_.get('title'):
                            transformed["source"] = doc.metadata_['title']
                        elif doc.original_filename:
                            transformed["source"] = doc.original_filename
                        elif doc.filename:
                            transformed["source"] = doc.filename
                        else:
                            transformed["source"] = "Unknown Document"
                    else:
                        transformed["source"] = source_id or "Unknown Document"
                finally:
                    db.close()
            else:
                transformed["source"] = source_id or "Unknown Document"
        else:
            # Check if we have original_filename in metadata
            filename = source_metadata.get("original_filename")
            if filename:
                transformed["source"] = filename
            else:
                transformed["source"] = "Unknown Document"
        
        transformed.pop("url", None)
        
    elif source_type == "internal":
        transformed.pop("url", None)
        transformed["source"] = "Internal Analysis"
    
    # Remove backend-specific fields
    transformed.pop("created_at", None)
    transformed.pop("updated_at", None)
    transformed.pop("source_type", None)
    transformed.pop("source_id", None)
    transformed.pop("source_metadata", None)
    transformed.pop("potential_sections", None)
    transformed.pop("is_relevant", None)
    
    return transformed

async def transform_note_for_frontend(note) -> dict:
    """
    Transform a backend Note object to the format expected by the frontend.
    
    The frontend expects:
    - 'timestamp' field (mapped from created_at)
    - 'url' field for web sources (to identify and link to web results)
    - 'source' field for document sources (to identify document-based notes)
    - Notes without these fields are treated as "internal"
    """
    # Handle both Note objects and dictionaries
    if hasattr(note, 'model_dump'):
        # It's a Pydantic Note object
        note_dict = note.model_dump()
        note_obj = note
    else:
        # It's already a dictionary
        note_dict = note
        note_obj = None
    
    # Start with the base note data
    transformed = note_dict.copy()
    
    # Map created_at to timestamp for frontend compatibility
    created_at = note_dict.get("created_at")
    updated_at = note_dict.get("updated_at")
    
    if created_at:
        if hasattr(created_at, 'isoformat'):
            transformed["timestamp"] = created_at.isoformat()
        else:
            transformed["timestamp"] = str(created_at)
    elif updated_at:
        if hasattr(updated_at, 'isoformat'):
            transformed["timestamp"] = updated_at.isoformat()
        else:
            transformed["timestamp"] = str(updated_at)
    else:
        # Fallback to current time if no timestamp is available
        from datetime import datetime
        transformed["timestamp"] = datetime.now().isoformat()
    
    # Get source information
    source_type = note_dict.get("source_type")
    source_id = note_dict.get("source_id")
    source_metadata = note_dict.get("source_metadata", {})
    
    # Add frontend-expected fields based on source_type
    if source_type == "web":
        # For web sources, extract URL from source_metadata or use source_id
        url = source_metadata.get("url") or source_id
        transformed["url"] = url
        
        # Also add a source field for consistency
        title = source_metadata.get("title", "Web Source")
        transformed["source"] = title
        
    elif source_type == "document":
        # For document sources, try to get the actual filename
        filename = source_metadata.get("original_filename")
        if filename:
            transformed["source"] = filename
        else:
            # Try to resolve document code to actual filename
            from services.document_service import document_service
            try:
                if source_id:
                    # Extract document codes from source_id
                    document_codes = document_service.extract_document_codes_from_text(source_id)
                    if document_codes:
                        # Get filename mapping for the first document code found
                        code_to_filename = await document_service.get_document_filename_mapping(document_codes)
                        if document_codes[0] in code_to_filename:
                            filename = code_to_filename[document_codes[0]]
                            transformed["source"] = filename
                        else:
                            transformed["source"] = source_id
                    else:
                        transformed["source"] = source_id
                else:
                    transformed["source"] = "Unknown Document"
            except Exception as e:
                logger.warning(f"Failed to resolve document filename for source_id {source_id}: {e}")
                transformed["source"] = source_id or "Unknown Document"
            
        # Ensure no url field for document sources
        transformed.pop("url", None)
        
    elif source_type == "internal":
        # Internal notes should not have url or source fields
        # (or they should be clearly marked as internal)
        transformed.pop("url", None)
        transformed["source"] = "Internal Analysis"
    
    # Remove backend-specific fields that frontend doesn't need
    transformed.pop("created_at", None)
    transformed.pop("updated_at", None)
    transformed.pop("source_type", None)
    transformed.pop("source_id", None)
    transformed.pop("source_metadata", None)
    transformed.pop("potential_sections", None)
    transformed.pop("is_relevant", None)
    
    return transformed

# Global instances - these will be initialized when the app starts
context_manager: Optional[AsyncContextManager] = None
agent_controller: Optional[AgentController] = None

async def initialize_ai_components():
    """Initialize the AI research components."""
    global context_manager, agent_controller
    
    try:
        # Initialize core components
        context_manager = AsyncContextManager()
        await context_manager.async_init()  # Initialize async
        # Initialize ModelDispatcher with empty user settings for global instance
        # Individual missions will create their own dispatchers with user-specific settings
        model_dispatcher = ModelDispatcher({})
        tool_registry = ToolRegistry()
        
        # Initialize RAG components
        from ai_researcher.core_rag.embedder import TextEmbedder
        from ai_researcher.core_rag.pgvector_store import PGVectorStore as VectorStore
        
        # Use cached model instances to avoid repeated initialization
        from ai_researcher.core_rag.model_cache import model_cache
        embedder = model_cache.get_embedder()
        reranker = model_cache.get_reranker()
        # PGVectorStore uses PostgreSQL database connection, no directory needed
        vector_store = VectorStore()
        retriever = Retriever(embedder=embedder, vector_store=vector_store)
        
        # Initialize agent controller
        agent_controller = AgentController(
            model_dispatcher=model_dispatcher,
            context_manager=context_manager,
            tool_registry=tool_registry,
            retriever=retriever,
            reranker=reranker
        )
        
        # Only log at ERROR level or higher based on LOG_LEVEL setting
        return True
    except Exception as e:
        logger.error(f"Failed to initialize AI components: {e}", exc_info=True)
        return False

def get_context_manager() -> AsyncContextManager:
    """Dependency to get the context manager instance."""
    if context_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI research components not initialized"
        )
    return context_manager

def get_agent_controller() -> AgentController:
    """Dependency to get the agent controller instance."""
    if agent_controller is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI research components not initialized"
        )
    return agent_controller

def get_user_specific_agent_controller(
    current_user: User = Depends(get_current_user_from_cookie)
) -> AgentController:
    """
    Dependency to get an agent controller with user-specific model dispatcher.
    This creates a new model dispatcher with the user's API credentials.
    """
    if agent_controller is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI research components not initialized"
        )
    
    # CRITICAL: Set the user context so ModelDispatcher can access user settings
    from ai_researcher.user_context import set_current_user
    set_current_user(current_user)
    
    # Get user settings
    user_settings = current_user.settings or {}
    
    # Create a per-chat semaphore to allow concurrent chats
    # Each chat gets its own semaphore, allowing multiple chats to process simultaneously
    # Use the USER's max_concurrent_requests setting from their profile
    from ai_researcher.dynamic_config import get_max_concurrent_requests
    from ai_researcher.user_context import set_current_user
    
    # Set the current user context so dynamic config can retrieve their settings
    set_current_user(current_user)
    
    # Get the user's max concurrent requests setting (not the global config default)
    user_max_concurrent = get_max_concurrent_requests()
    
    chat_semaphore = None
    if user_max_concurrent > 0:
        # Create a per-chat semaphore using the user's setting
        chat_semaphore = asyncio.Semaphore(user_max_concurrent)
        logger.info(f"Created chat semaphore with user '{current_user.username}' max_concurrent_requests: {user_max_concurrent}")
    
    user_model_dispatcher = ModelDispatcher(
        user_settings=user_settings,
        semaphore=chat_semaphore,  # Use per-chat semaphore for true concurrency
        context_manager=agent_controller.context_manager
    )
    
    # Create a new agent controller with the user-specific model dispatcher
    # We'll reuse the other components from the global instance
    user_agent_controller = AgentController(
        model_dispatcher=user_model_dispatcher,
        context_manager=agent_controller.context_manager,
        tool_registry=agent_controller.tool_registry,
        retriever=agent_controller.retriever,
        reranker=agent_controller.reranker
    )
    
    # IMPORTANT: Disable the controller-level semaphore to allow true per-mission concurrency
    # Mission-specific semaphores in AsyncContextManager handle concurrency per mission
    # This allows multiple missions to run truly concurrently without blocking each other
    # The ModelDispatcher already has the chat_semaphore for rate limiting API calls
    user_agent_controller.semaphore = None
    user_agent_controller.maybe_semaphore = MaybeSemaphore(None)
    
    return user_agent_controller

# Import the shared optimization function
from ai_researcher.settings_optimizer import determine_research_parameters as _determine_research_parameters


@router.post("/missions", response_model=MissionResponse)
async def create_mission(
    mission_data: dict,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager),
    controller: AgentController = Depends(get_agent_controller),
    db: Session = Depends(get_db)
):
    """Create a new research mission."""
    try:
        user_request = mission_data.get("request")
        chat_id = mission_data.get("chat_id")
        use_web_search = mission_data.get("use_web_search", True)
        document_group_id = mission_data.get("document_group_id")
        auto_create_document_group = mission_data.get("auto_create_document_group", False)
        mission_settings_data = mission_data.get("mission_settings")

        if not user_request or not chat_id:
            raise HTTPException(status_code=422, detail="Request and chat_id are required.")

        use_local_rag = document_group_id is not None
        if not use_web_search and not use_local_rag:
            raise HTTPException(status_code=422, detail="At least one information source must be enabled.")

        # Capture all user settings
        user_settings = current_user.settings or {}
        research_params = user_settings.get("research_parameters", {})
        # Add auto_create_document_group from the request to research_params
        research_params["auto_create_document_group"] = auto_create_document_group
        
        # Capture model configuration
        ai_settings = user_settings.get("ai_endpoints", {})
        model_config = {
            "fast_provider": ai_settings.get("fast_llm_provider"),
            "fast_model": ai_settings.get("fast_llm_model"),
            "mid_provider": ai_settings.get("mid_llm_provider"),
            "mid_model": ai_settings.get("mid_llm_model"),
            "intelligent_provider": ai_settings.get("intelligent_llm_provider"),
            "intelligent_model": ai_settings.get("intelligent_llm_model"),
            "verifier_provider": ai_settings.get("verifier_llm_provider"),
            "verifier_model": ai_settings.get("verifier_llm_model"),
        }
        
        # Capture search settings
        search_settings = user_settings.get("search", {})
        web_fetch_settings = user_settings.get("web_fetch", {})
        
        # Get document group name if ID is provided
        document_group_name = None
        if document_group_id:
            async_db = await get_async_db_session()
            try:
                doc_group = await async_crud.get_document_group(async_db, document_group_id=document_group_id, user_id=current_user.id)
                if doc_group:
                    document_group_name = doc_group.name
            finally:
                await async_db.close()
        
        # Create mission with all settings
        mission_context = await context_mgr.start_mission(
            user_request=user_request,
            chat_id=chat_id,
            document_group_id=document_group_id,
            document_group_name=document_group_name,
            use_web_search=use_web_search,
            llm_config=model_config,
            research_params=research_params
        )
        mission_id = mission_context.mission_id
        
        # Store comprehensive mission metadata including all settings
        comprehensive_settings = {
            # Tool selection
            "use_web_search": use_web_search,
            "use_local_rag": use_local_rag,
            "auto_create_document_group": research_params.get("auto_create_document_group", False) if research_params else False,
            "document_group_id": document_group_id,
            "document_group_name": document_group_name,
            
            # Model configuration at mission creation
            "model_config": model_config,
            
            # Research parameters at mission creation
            "research_params": research_params,
            
            # Search and web fetch settings
            "search_provider": search_settings.get("provider"),
            "web_fetch_settings": web_fetch_settings,
            
            # Store the complete user settings for reference
            "all_user_settings": user_settings,
            
            # Timestamp for when settings were captured
            "settings_captured_at": datetime.utcnow().isoformat()
        }
        
        # Store all metadata in one update to avoid conflicts
        all_metadata = {
            "comprehensive_settings": comprehensive_settings,
            "tool_selection": {"web_search": use_web_search, "local_rag": use_local_rag},
            "document_group_id": document_group_id,
            "document_group_name": document_group_name,
            "use_web_search": use_web_search,
            "use_local_rag": use_local_rag
        }
        
        # Update mission metadata with all settings at once
        await context_mgr.update_mission_metadata(mission_id, all_metadata)
        
        # Keep backward compatibility
        all_settings = {
            "search_provider": search_settings.get("provider"),
            "web_fetch": web_fetch_settings,
            "document_group_id": document_group_id,
            "document_group_name": document_group_name,
            "use_web_search": use_web_search
        }
        mission_context.mission_settings = all_settings
        
        final_mission_settings_dict = None

        if research_params.get("auto_optimize_params"):
            logger.info(f"Auto-optimizing research parameters for mission {mission_id}.")
            async_db = await get_async_db_session()
            try:
                chat_history = await async_crud.get_chat_messages(async_db, chat_id=chat_id, user_id=current_user.id)
            finally:
                await async_db.close()
            final_mission_settings_dict = await _determine_research_parameters(chat_history, controller)
            if not final_mission_settings_dict:
                logger.warning(f"AI parameter optimization failed for mission {mission_id}. Proceeding without mission-specific settings.")
        elif mission_settings_data:
            logger.info(f"Using mission-specific settings for mission {mission_id}.")
            final_mission_settings_dict = mission_settings_data
        
        if final_mission_settings_dict:
            # Validate with Pydantic model before storing
            try:
                validated_settings = MissionSettings(**final_mission_settings_dict)
                await context_mgr.update_mission_metadata(
                    mission_id, 
                    {"mission_settings": validated_settings.model_dump(exclude_none=True)}
                )
                logger.info(f"Stored settings for mission {mission_id}: {validated_settings.model_dump(exclude_none=True)}")

                # Log the settings to the frontend
                log_message = (
                    f"**User Default Settings:**\n```json\n{json.dumps(research_params, indent=2)}\n```\n\n"
                    f"**Mission-Specific Overrides (AI-Generated or Manual):**\n```json\n{json.dumps(final_mission_settings_dict, indent=2)}\n```\n\n"
                    f"**Effective Settings for this Mission:**\n```json\n{json.dumps(validated_settings.model_dump(), indent=2)}\n```"
                )
                await context_mgr.log_execution_step(
                    mission_id=mission_id,
                    agent_name="Configuration",
                    action="Applying Research Parameters",
                    output_summary=log_message,
                    status="success"
                )

            except Exception as pydantic_error:
                logger.error(f"Failed to validate/store/log mission settings for {mission_id}: {pydantic_error}", exc_info=True)

        # Source configuration already stored in comprehensive metadata above
        
        logger.info(f"Created new mission {mission_id} for user {current_user.username} in chat {chat_id}")
        
        return MissionResponse(
            mission_id=mission_id,
            status=mission_context.status,
            created_at=mission_context.created_at,
            user_request=mission_context.user_request
        )
    except Exception as e:
        logger.error(f"Failed to create mission: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create mission")

@router.get("/missions/{mission_id}/status", response_model=MissionStatus)
async def get_mission_status(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get the current status of a mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Include tool_selection in the status response
        tool_selection = mission_context.metadata.get("tool_selection") if mission_context.metadata else None
        document_group_id = mission_context.metadata.get("document_group_id") if mission_context.metadata else None
        generated_document_group_id = mission_context.metadata.get("generated_document_group_id") if mission_context.metadata else None
        
        return MissionStatus(
            mission_id=mission_id,
            status=mission_context.status,
            updated_at=mission_context.updated_at,
            error_info=mission_context.error_info,
            tool_selection=tool_selection,
            document_group_id=document_group_id,
            generated_document_group_id=generated_document_group_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission status"
        )

@router.get("/missions/{mission_id}/stats", response_model=MissionStats)
async def get_mission_stats(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get mission statistics including cost and token usage from in-memory context."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        stats = context_mgr.get_mission_stats(mission_id)
        
        return MissionStats(
            mission_id=mission_id,
            total_cost=stats.get("total_cost", 0.0),
            total_prompt_tokens=stats.get("total_prompt_tokens", 0.0),
            total_completion_tokens=stats.get("total_completion_tokens", 0.0),
            total_native_tokens=stats.get("total_native_tokens", 0.0),
            total_web_search_calls=stats.get("total_web_search_calls", 0)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission stats"
        )

@router.get("/missions/{mission_id}/complete-stats", response_model=MissionStats)
async def get_complete_mission_stats(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Get complete mission statistics by calculating from all database logs."""
    try:
        # Get all logs from database
        from database.async_database import get_async_db_session
        from database import async_crud
        
        async_db = await get_async_db_session()
        try:
            # Fetch ALL logs for this mission (no limit)
            logs = await async_crud.get_mission_execution_logs(
                async_db, 
                mission_id, 
                current_user.id,
                skip=0, 
                limit=10000  # High limit to get all logs
            )
            
            # Calculate stats from logs
            total_cost = 0.0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_native_tokens = 0
            total_web_search_calls = 0
            
            for log in logs:
                # Add cost (convert Decimal to float)
                if hasattr(log, 'cost') and log.cost:
                    total_cost += float(log.cost)
                    
                # Add tokens (convert to int/float as needed)
                if hasattr(log, 'prompt_tokens') and log.prompt_tokens:
                    total_prompt_tokens += int(log.prompt_tokens) if log.prompt_tokens else 0
                if hasattr(log, 'completion_tokens') and log.completion_tokens:
                    total_completion_tokens += int(log.completion_tokens) if log.completion_tokens else 0
                if hasattr(log, 'native_tokens') and log.native_tokens:
                    total_native_tokens += int(log.native_tokens) if log.native_tokens else 0
                
                # Count web searches from tool calls
                if hasattr(log, 'tool_calls') and log.tool_calls:
                    for tool_call in log.tool_calls:
                        if isinstance(tool_call, dict):
                            tool_name = tool_call.get('tool_name', '').lower()
                        else:
                            tool_name = getattr(tool_call, 'tool_name', '').lower() if hasattr(tool_call, 'tool_name') else ''
                        
                        if 'search' in tool_name or 'web' in tool_name or 'tavily' in tool_name:
                            total_web_search_calls += 1
            
            return MissionStats(
                mission_id=mission_id,
                total_cost=total_cost,
                total_prompt_tokens=float(total_prompt_tokens),
                total_completion_tokens=float(total_completion_tokens),
                total_native_tokens=float(total_native_tokens),
                total_web_search_calls=total_web_search_calls
            )
            
        finally:
            await async_db.close()
            
    except Exception as e:
        logger.error(f"Failed to get complete mission stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get complete mission stats"
        )

@router.get("/missions/{mission_id}/plan", response_model=MissionPlan)
async def get_mission_plan(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get the research plan for a mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        plan_data = None
        if mission_context.plan:
            # Convert the plan to a dictionary for JSON serialization
            plan_data = mission_context.plan.model_dump()
        
        return MissionPlan(
            mission_id=mission_id,
            plan=plan_data
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission plan: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission plan"
        )

@router.get("/missions/{mission_id}/notes")
async def get_mission_notes(
    mission_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get notes for a given mission with pagination, transformed for frontend consumption."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Get total count
        total_notes = len(mission_context.notes)
        
        # Apply pagination - get the most recent notes first
        sorted_notes = sorted(mission_context.notes, key=lambda n: n.created_at, reverse=True)
        paginated_notes = sorted_notes[offset:offset + limit]
        
        # Transform notes in batch for better performance
        transformed_notes = []
        
        # Pre-fetch document filename mappings for all notes at once
        document_codes_to_resolve = set()
        for note in paginated_notes:
            note_dict = note.model_dump() if hasattr(note, 'model_dump') else note
            if note_dict.get("source_type") == "document" and note_dict.get("source_id"):
                from services.document_service import document_service
                codes = document_service.extract_document_codes_from_text(note_dict["source_id"])
                document_codes_to_resolve.update(codes)
        
        # Get all filename mappings in one batch
        code_to_filename = {}
        if document_codes_to_resolve:
            from services.document_service import document_service
            code_to_filename = await document_service.get_document_filename_mapping(list(document_codes_to_resolve))
        
        # Transform each note with pre-fetched mappings
        for note in paginated_notes:
            transformed_note = await transform_note_for_frontend_batch(note, code_to_filename)
            transformed_notes.append(transformed_note)
        
        logger.info(f"Returning {len(transformed_notes)} of {total_notes} transformed notes for mission {mission_id} (offset: {offset}, limit: {limit})")
        
        return {
            "notes": transformed_notes,
            "total": total_notes,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total_notes
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission notes: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission notes"
        )

@router.get("/missions/{mission_id}/logs", response_model=MissionLogs)
@router.get("/missions/{mission_id}/activity-logs", response_model=MissionLogs)  # Alias for frontend compatibility
async def get_mission_logs(
    mission_id: str,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(1000, ge=1, le=10000, description="Number of records to return"),
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager),
    db: Session = Depends(get_db)
):
    """Get all execution logs for a given mission from the database."""
    try:
        # Check if the mission exists and belongs to the current user
        async_db = await get_async_db_session()
        try:
            mission = await async_crud.get_mission(async_db, mission_id, current_user.id)
            if not mission:
                raise HTTPException(
                    status_code=404,
                    detail="Mission not found"
                )
            
            # Import document service for filename mapping
            from services.document_service import document_service
            
            # Get logs from database only - these are the source of truth
            # Live updates come through WebSocket, not through this endpoint
            db_logs = await async_crud.get_mission_execution_logs(
                async_db, 
                mission_id, 
                current_user.id,
                skip=skip,
                limit=limit
            )
            
            # Get total count for pagination info
            total_logs_count = await async_crud.get_mission_execution_logs_count(async_db, mission_id, current_user.id)
        finally:
            await async_db.close()
        
        logger.info(f"Retrieved {len(db_logs)} logs from DB for mission {mission_id} (skip={skip}, limit={limit}, total={total_logs_count})")
        
        # Process database logs
        logs = []
        for db_log in db_logs:
            # Replace document codes in the action text
            action_with_filenames = await document_service.replace_document_codes_in_text(db_log.action)
            
            # Convert database log to frontend format with rich metadata
            log_entry = {
                "timestamp": db_log.timestamp.isoformat() if hasattr(db_log.timestamp, 'isoformat') else str(db_log.timestamp),
                "agent_name": db_log.agent_name,
                "message": action_with_filenames,
                "action": action_with_filenames,
                "input_summary": db_log.input_summary,
                "output_summary": db_log.output_summary,
                "status": db_log.status,
                "error_message": db_log.error_message,
                "full_input": db_log.full_input,
                "full_output": db_log.full_output,
                "model_details": db_log.model_details,
                "tool_calls": db_log.tool_calls,
                "file_interactions": db_log.file_interactions,
                "cost": float(db_log.cost) if db_log.cost else None,
                "prompt_tokens": db_log.prompt_tokens,
                "completion_tokens": db_log.completion_tokens,
                "native_tokens": db_log.native_tokens
            }
            logs.append(log_entry)
        
        # Sort logs by timestamp
        sorted_logs = sorted(logs, key=lambda x: x["timestamp"])
        
        logger.info(f"Returning {len(sorted_logs)} logs for mission {mission_id}")
        
        return MissionLogs(
            mission_id=mission_id,
            logs=sorted_logs,
            total=total_logs_count,
            has_more=(skip + len(sorted_logs)) < total_logs_count,
            skip=skip,
            limit=limit
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission logs"
        )

@router.get("/missions/{mission_id}/draft", response_model=MissionDraft)
async def get_mission_draft(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get the current draft of the report for a mission."""
    try:
        draft = context_mgr.get_mission_draft(mission_id)
        return MissionDraft(mission_id=mission_id, draft=draft)
    except Exception as e:
        logger.error(f"Failed to get mission draft: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission draft"
        )

@router.get("/missions/{mission_id}/report", response_model=MissionReport)
async def get_mission_report(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get the final research report for a completed mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        return MissionReport(
            mission_id=mission_id,
            final_report=mission_context.final_report
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission report: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission report"
        )

@router.get("/missions/{mission_id}/reports")
async def get_mission_reports(
    mission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Get all report versions for a mission."""
    # Import models here to avoid circular import
    from database import models
    
    # Verify mission belongs to user through chat
    mission = db.query(models.Mission).join(
        models.Chat, models.Mission.chat_id == models.Chat.id
    ).filter(
        models.Mission.id == mission_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    # Get all report versions
    reports = db.query(models.ResearchReport).filter(
        models.ResearchReport.mission_id == mission_id
    ).order_by(models.ResearchReport.version.desc()).all()
    
    # Find current version
    current_report = next((r for r in reports if r.is_current), None)
    current_version = current_report.version if current_report else 1
    
    return {
        "reports": reports,
        "current_version": current_version
    }

@router.get("/missions/{mission_id}/reports/{version}")
async def get_mission_report_version(
    mission_id: str,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Get a specific version of a mission report."""
    # Import models here to avoid circular import
    from database import models
    
    # Verify mission belongs to user through chat
    mission = db.query(models.Mission).join(
        models.Chat, models.Mission.chat_id == models.Chat.id
    ).filter(
        models.Mission.id == mission_id,
        models.Chat.user_id == current_user.id
    ).first()
    
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    
    # Get specific report version
    report = db.query(models.ResearchReport).filter(
        models.ResearchReport.mission_id == mission_id,
        models.ResearchReport.version == version
    ).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report version not found")
    
    return report

@router.put("/missions/{mission_id}/report")
async def update_mission_report(
    mission_id: str,
    report_content: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager),
    db: Session = Depends(get_db)
):
    """Update the mission report content without updating chat timestamp."""
    try:
        # Get mission context
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Verify user owns the mission
        async_db = await get_async_db_session()
        try:
            mission = await async_crud.get_mission(async_db, mission_id, current_user.id)
            if not mission:
                raise HTTPException(
                    status_code=404,
                    detail="Mission not found or access denied"
                )
        finally:
            await async_db.close()
        
        # Update the final report in context
        mission_context.final_report = report_content
        
        # Store the updated context in database WITHOUT updating chat timestamp
        async_db = await get_async_db_session()
        try:
            # Update only the mission_context field in the missions table WITHOUT updating timestamp
            await async_crud.update_mission_context_no_timestamp(
                async_db, 
                mission_id=mission_id, 
                mission_context=mission_context.model_dump(mode='json')
            )
            logger.info(f"Updated report content for mission {mission_id} without updating chat timestamp")
        finally:
            await async_db.close()
        
        # Save report version if mission is completed
        if mission_context.status == "completed":
            from database import models
            import uuid
            
            # Mark all existing reports for this mission as not current
            db.query(models.ResearchReport).filter(
                models.ResearchReport.mission_id == mission_id
            ).update({"is_current": False})
            
            # Get the next version number
            existing_reports = db.query(models.ResearchReport).filter(
                models.ResearchReport.mission_id == mission_id
            ).order_by(models.ResearchReport.version.desc()).first()
            
            next_version = 1 if not existing_reports else existing_reports.version + 1
            
            # Create new report version
            new_report = models.ResearchReport(
                id=str(uuid.uuid4()),
                mission_id=mission_id,
                version=next_version,
                title=f"Report Version {next_version}",
                content=report_content,
                is_current=True,
                revision_notes="Manual edit"
            )
            db.add(new_report)
            db.commit()
            logger.info(f"Created report version {next_version} for mission {mission_id}")
        
        return MissionReport(
            mission_id=mission_id,
            final_report=report_content
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update mission report: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to update mission report"
        )

@router.post("/missions/{mission_id}/resume")
async def resume_mission_execution(
    mission_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    controller: AgentController = Depends(get_user_specific_agent_controller)
):
    """Resume a stopped mission."""
    try:
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
            logger.error(f"Mission {mission_id} not found in context manager")
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        logger.info(f"Attempting to resume mission {mission_id} with status: {mission_context.status}")

        # Allow resuming from multiple states (including running which might have been paused)
        resumable_statuses = ["stopped", "paused", "failed"]
        if mission_context.status not in resumable_statuses:
            if mission_context.status == "completed":
                raise HTTPException(
                    status_code=400,
                    detail=f"Mission is already completed. Cannot resume a completed mission."
                )
            elif mission_context.status == "running":
                # Mission might appear as running but actually be paused - check if there are active tasks
                logger.warning(f"Mission {mission_id} status is 'running' but resume was requested. Allowing resume.")
                # Don't raise error, allow resume to proceed
            elif mission_context.status == "planning":
                logger.info(f"Mission {mission_id} is in planning phase. Continuing from planning.")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mission cannot be resumed. Current status: {mission_context.status}"
                )

        # Create a queue and callback function for WebSocket updates
        log_queue = queue.Queue()
        
        def websocket_update_callback(
            q: queue.Queue,
            update_data: Any
        ):
            """Callback to send updates via WebSocket."""
            try:
                # Import send_logs_update function locally to avoid circular imports
                from api.websockets import send_logs_update
                
                if isinstance(update_data, dict) and update_data.get("type") == "agent_feedback":
                    # Handle agent feedback messages (these are already formatted correctly)
                    # These are sent directly via WebSocket without queue processing
                    pass
                elif hasattr(update_data, 'agent_name') and hasattr(update_data, 'action'):
                    # This is an ExecutionLogEntry object, transform it for frontend
                    log_entry_dict = {
                        "log_id": getattr(update_data, 'log_id', None),  # Include the unique log ID
                        "timestamp": update_data.timestamp.isoformat() if hasattr(update_data.timestamp, 'isoformat') else str(update_data.timestamp),
                        "agent_name": update_data.agent_name,
                        "message": update_data.action,  # Add message field for frontend compatibility
                        "action": update_data.action,
                        "input_summary": getattr(update_data, 'input_summary', None),
                        "output_summary": getattr(update_data, 'output_summary', None),
                        "status": getattr(update_data, 'status', 'success'),
                        "error_message": getattr(update_data, 'error_message', None),
                        "full_input": getattr(update_data, 'full_input', None),
                        "full_output": getattr(update_data, 'full_output', None),
                        "model_details": getattr(update_data, 'model_details', None),
                        "tool_calls": getattr(update_data, 'tool_calls', None),
                        "file_interactions": getattr(update_data, 'file_interactions', None)
                    }
                    
                    # Process the log entry to clean tool calls and replace document codes
                    try:
                        import asyncio
                        # Create a new event loop if needed for the async processing
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        # Process the log entry asynchronously
                        if loop.is_running():
                            # If loop is already running, we can't use run_until_complete
                            # So we'll just clean the tool calls and input summary synchronously for now
                            from api.utils import clean_tool_call_arguments, clean_input_summary_for_display
                            if log_entry_dict.get('tool_calls'):
                                log_entry_dict['tool_calls'] = clean_tool_call_arguments(log_entry_dict['tool_calls'])
                            if log_entry_dict.get('input_summary'):
                                log_entry_dict['input_summary'] = clean_input_summary_for_display(log_entry_dict['input_summary'])
                        else:
                            # If loop is not running, we can process fully
                            processed_entry = loop.run_until_complete(
                                process_execution_log_entry_for_frontend(log_entry_dict)
                            )
                            log_entry_dict = processed_entry
                    except Exception as process_error:
                        logger.warning(f"Failed to process log entry for frontend: {process_error}")
                        # Fall back to basic tool call cleaning
                        from api.utils import clean_tool_call_arguments
                        if log_entry_dict.get('tool_calls'):
                            log_entry_dict['tool_calls'] = clean_tool_call_arguments(log_entry_dict['tool_calls'])
                    
                    # Send the log entry via WebSocket
                    import asyncio
                    import json
                    try:
                        # Create a new event loop if needed
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        # Run the async function in the event loop
                        if loop.is_running():
                            # If loop is already running, create a task
                            loop.create_task(send_logs_update(mission_id, [log_entry_dict]))
                        else:
                            # If loop is not running, run until complete
                            loop.run_until_complete(send_logs_update(mission_id, [log_entry_dict]))
                    except Exception as ws_error:
                        logger.error(f"Failed to send log update via WebSocket for mission {mission_id}: {ws_error}")
            except Exception as e:
                logger.error(f"Error in websocket_update_callback for mission {mission_id}: {e}")

        # Update status to indicate resuming
        await controller.context_manager.update_mission_status(mission_id, "running")
        
        # Resume mission execution in a separate thread from the pool
        loop = asyncio.get_event_loop()
        thread_pool: ThreadPoolExecutor = request.app.state.thread_pool
        
        async def run_mission_async():
            """Resume the mission from where it left off."""
            try:
                await controller.resume_mission(
                    mission_id,
                    log_queue=log_queue,
                    update_callback=websocket_update_callback
                )
            finally:
                # Clean up the model dispatcher to prevent connection errors
                if hasattr(controller, 'model_dispatcher') and hasattr(controller.model_dispatcher, 'cleanup'):
                    try:
                        await controller.model_dispatcher.cleanup()
                        logger.debug(f"Cleaned up model dispatcher for resumed mission {mission_id}")
                    except Exception as cleanup_error:
                        logger.warning(f"Error cleaning up model dispatcher for resumed mission {mission_id}: {cleanup_error}")
        
        def run_mission_in_thread():
            """Sets user context and runs the async mission."""
            set_current_user(current_user)
            asyncio.run(run_mission_async())

        loop.run_in_executor(thread_pool, run_mission_in_thread)
        
        logger.info(f"Mission {mission_id} resume initiated successfully")
        return {"message": "Mission execution resumed", "mission_id": mission_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume mission execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to resume mission execution"
        )


@router.post("/missions/{mission_id}/stop")
async def stop_mission_execution(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    controller: AgentController = Depends(get_agent_controller)
):
    """Stop a running mission."""
    try:
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )

        await controller.stop_mission(mission_id)
        
        return {"message": "Mission execution stopped", "mission_id": mission_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop mission execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to stop mission execution"
        )


@router.post("/missions/{mission_id}/resume-round/{round_num}")
async def resume_from_round(
    mission_id: str,
    round_num: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    controller: AgentController = Depends(get_user_specific_agent_controller),
    db: Session = Depends(get_db)
):
    """Resume mission from a specific research round."""
    try:
        # First, try to get mission context from memory
        mission_context = controller.context_manager.get_mission_context(mission_id)
        
        # If not in memory, load from database
        if not mission_context:
            logger.info(f"Mission {mission_id} not in memory, loading from database")
            
            # Get mission from database
            async_db = await get_async_db_session()
            try:
                db_mission = await async_crud.get_mission(async_db, mission_id, user_id=current_user.id)
                if not db_mission:
                    raise HTTPException(
                        status_code=404,
                        detail="Mission not found in database"
                    )
                
                # Restore mission context from database
                if db_mission.mission_context:
                    from ai_researcher.agentic_layer.async_context_manager import MissionContext
                    # Parse the stored mission context
                    mission_context = MissionContext(**db_mission.mission_context)
                    # Add it to the context manager
                    controller.context_manager._missions[mission_id] = mission_context
                    logger.info(f"Successfully restored mission {mission_id} from database")
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Mission context is empty in database"
                    )
            finally:
                await async_db.close()
        
        # Verify mission context now exists
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Failed to load mission context"
            )
        
        # Validate round number
        if round_num < 1:
            raise HTTPException(
                status_code=400,
                detail="Round number must be 1 or greater"
            )
        
        # Log the mission context for debugging
        if mission_context and mission_context.plan:
            logger.info(f"Mission {mission_id} has plan with {len(mission_context.plan.report_outline)} sections")
            for section in mission_context.plan.report_outline[:3]:  # Log first 3 sections
                logger.info(f"  Section: {section.section_id} - {section.title} (strategy: {getattr(section, 'research_strategy', 'unknown')})")
        
        # Use global websocket_manager imported at the top
        
        # Create log queue and update callback
        log_queue = queue.Queue()
        
        def websocket_update_callback(log_queue_arg, entry, mission_id_arg=None, custom_event_type=None):
            """Callback to send updates via WebSocket."""
            try:
                # Import send_logs_update function locally to avoid circular imports
                from api.websockets import send_logs_update
                
                if isinstance(entry, dict) and entry.get("type") == "agent_feedback":
                    # Handle agent feedback messages
                    pass
                elif hasattr(entry, 'agent_name') and hasattr(entry, 'action'):
                    # This is an ExecutionLogEntry object, transform it for frontend
                    log_entry_dict = {
                        "log_id": getattr(entry, 'log_id', None),
                        "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, 'isoformat') else str(entry.timestamp),
                        "agent_name": entry.agent_name,
                        "message": entry.action,
                        "action": entry.action,
                        "input_summary": getattr(entry, 'input_summary', None),
                        "output_summary": getattr(entry, 'output_summary', None),
                        "status": getattr(entry, 'status', 'success'),
                        "error_message": getattr(entry, 'error_message', None),
                        "full_input": getattr(entry, 'full_input', None),
                        "full_output": getattr(entry, 'full_output', None),
                        "model_details": getattr(entry, 'model_details', None),
                        "tool_calls": getattr(entry, 'tool_calls', None),
                        "file_interactions": getattr(entry, 'file_interactions', None)
                    }
                    
                    # Send update via WebSocket - use create_task since we're already in an event loop
                    asyncio.create_task(send_logs_update(mission_id, [log_entry_dict]))
            except Exception as e:
                logger.error(f"Error in websocket update callback: {e}")
        
        # Update mission status to running before resuming
        await controller.context_manager.update_mission_status(mission_id, "running")
        
        # Execute resume in background
        loop = asyncio.get_event_loop()
        thread_pool = request.app.state.thread_pool
        
        def run_resume_in_thread():
            """Resume mission in thread with user context."""
            set_current_user(current_user)
            asyncio.run(controller.resume_from_round(
                mission_id,
                round_num,
                log_queue=log_queue,
                update_callback=websocket_update_callback
            ))
        
        loop.run_in_executor(thread_pool, run_resume_in_thread)
        
        # Send immediate WebSocket update about status change
        from services.websocket_manager import websocket_manager
        await websocket_manager.send_to_mission(
            mission_id,
            {
                "type": "mission_status_update",
                "mission_id": mission_id,
                "status": "running",
                "message": f"Resuming from round {round_num}"
            }
        )
        
        logger.info(f"Mission {mission_id} resume from round {round_num} initiated")
        return {
            "message": f"Mission resuming from round {round_num}", 
            "mission_id": mission_id,
            "status": "running"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume mission from round: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to resume mission from round"
        )


class ReviseOutlineRequest(BaseModel):
    """Request body for outline revision."""
    feedback: str = Field(..., min_length=1, description="User feedback for outline revision")
    round_num: int = Field(..., ge=1, description="Round number to resume from")
    outline_id: Optional[str] = Field(None, description="Specific outline ID to use (overrides round_num)")
    outline_data: Optional[Dict] = Field(None, description="The actual outline data if provided")


class UnifiedResumeRequest(BaseModel):
    """Request body for unified resume/revise endpoint."""
    round_num: int = Field(..., ge=1, description="Round number to resume from")
    feedback: Optional[str] = Field(None, description="Optional user feedback for outline revision")
    outline_id: Optional[str] = Field(None, description="Specific outline ID to use (overrides round_num)")
    outline_data: Optional[Dict] = Field(None, description="The actual outline data if provided")


@router.post("/missions/{mission_id}/revise-outline")
async def revise_and_resume(
    mission_id: str,
    revision_request: ReviseOutlineRequest,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    controller: AgentController = Depends(get_user_specific_agent_controller)
):
    """Revise mission outline based on user feedback and resume from specified round."""
    try:
        # Validate mission exists and user has access
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # If a specific outline is provided, use it instead of the current one
        if revision_request.outline_data and 'outline' in revision_request.outline_data:
            # Parse the provided outline data
            from ai_researcher.agentic_layer.schemas.planning import ReportSection
            outline_data = revision_request.outline_data['outline']
            
            # Convert outline data to ReportSection objects
            new_outline = []
            for section_data in outline_data:
                if isinstance(section_data, dict):
                    # Recursively convert subsections if they exist
                    if 'subsections' in section_data:
                        section_data['subsections'] = [
                            ReportSection(**subsec) if isinstance(subsec, dict) else subsec
                            for subsec in section_data['subsections']
                        ]
                    new_outline.append(ReportSection(**section_data) if isinstance(section_data, dict) else section_data)
            
            # Update the mission context with the specific outline
            mission_context.plan.report_outline = new_outline
            logger.info(f"Using specific outline with ID {revision_request.outline_id} for mission {mission_id}")
        
        # Check if mission has an outline
        if not mission_context.plan or not mission_context.plan.report_outline:
            raise HTTPException(
                status_code=400,
                detail="Mission has no outline to revise"
            )
        
        # Use global websocket_manager imported at the top
        
        # Create log queue and update callback
        log_queue = queue.Queue()
        
        def websocket_update_callback(log_queue_arg, entry, mission_id_arg=None, custom_event_type=None):
            """Callback to send updates via WebSocket."""
            try:
                # Import send_logs_update function locally to avoid circular imports
                from api.websockets import send_logs_update
                
                if isinstance(entry, dict) and entry.get("type") == "agent_feedback":
                    # Handle agent feedback messages
                    pass
                elif hasattr(entry, 'agent_name') and hasattr(entry, 'action'):
                    # This is an ExecutionLogEntry object, transform it for frontend
                    log_entry_dict = {
                        "log_id": getattr(entry, 'log_id', None),
                        "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, 'isoformat') else str(entry.timestamp),
                        "agent_name": entry.agent_name,
                        "message": entry.action,
                        "action": entry.action,
                        "input_summary": getattr(entry, 'input_summary', None),
                        "output_summary": getattr(entry, 'output_summary', None),
                        "status": getattr(entry, 'status', 'success'),
                        "error_message": getattr(entry, 'error_message', None),
                        "full_input": getattr(entry, 'full_input', None),
                        "full_output": getattr(entry, 'full_output', None),
                        "model_details": getattr(entry, 'model_details', None),
                        "tool_calls": getattr(entry, 'tool_calls', None),
                        "file_interactions": getattr(entry, 'file_interactions', None)
                    }
                    
                    # Send update via WebSocket - use create_task since we're already in an event loop
                    asyncio.create_task(send_logs_update(mission_id, [log_entry_dict]))
            except Exception as e:
                logger.error(f"Error in websocket update callback: {e}")
        
        # Update mission status to running before resuming
        await controller.context_manager.update_mission_status(mission_id, "running")
        
        # Execute revision and resume in background
        loop = asyncio.get_event_loop()
        thread_pool = request.app.state.thread_pool
        
        def run_revise_in_thread():
            """Revise outline and resume in thread with user context."""
            set_current_user(current_user)
            asyncio.run(controller.revise_outline_and_resume(
                mission_id,
                revision_request.round_num,
                revision_request.feedback,
                log_queue=log_queue,
                update_callback=websocket_update_callback
            ))
        
        loop.run_in_executor(thread_pool, run_revise_in_thread)
        
        logger.info(f"Mission {mission_id} outline revision and resume initiated")
        return {
            "message": "Outline revision and resume initiated",
            "mission_id": mission_id,
            "round_num": revision_request.round_num
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revise outline and resume: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to revise outline and resume"
        )


@router.get("/missions/{mission_id}/outline-history")
async def get_outline_history(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    controller: AgentController = Depends(get_user_specific_agent_controller)
):
    """Get the history of outlines for each successful research round."""
    try:
        # Get mission context
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Get execution logs from database
        from database.async_database import get_async_db_session
        async_db = await get_async_db_session()
        try:
            logs = await async_crud.get_mission_execution_logs(
                async_db, 
                mission_id, 
                current_user.id,
                skip=0, 
                limit=1000
            )
        finally:
            await async_db.close()
        
        # Extract outlines from planning steps and revisions in each round
        outline_history = []
        current_round = 0
        round_started = False
        last_round_completed = 0
        
        for log in logs:
            # Access attributes directly from the MissionExecutionLog model
            agent_name = log.agent_name or ""
            action = log.action or ""
            log_status = log.status or ""
            full_output = log.full_output
            
            # Track when a new research round starts
            if ("ResearchManager" in agent_name or "AgentController" in agent_name) and "Starting Research Round" in action:
                import re
                match = re.search(r'Round (\d+)', action)
                if match:
                    current_round = int(match.group(1))
                    round_started = True
            
            # Track when a research round completes
            elif ("ResearchManager" in agent_name or "AgentController" in agent_name) and "Completed Research Round" in action:
                import re
                match = re.search(r'Round (\d+)', action)
                if match:
                    last_round_completed = int(match.group(1))
            
            # Capture initial plan generation and batch outlines
            if (agent_name == "PlanningAgent" and 
                ("Generate Plan" in action or "Generate Preliminary Outline" in action) and 
                log_status == "success" and 
                full_output):
                
                # Extract outline from full_output
                outline_data = full_output
                if isinstance(outline_data, dict) and 'report_outline' in outline_data:
                    # Extract batch number if present
                    import re
                    batch_match = re.search(r'Batch (\d+)', action)
                    batch_num = int(batch_match.group(1)) if batch_match else 0
                    
                    outline_history.append({
                        "round": batch_num,  # Use batch number as round
                        "timestamp": log.created_at.isoformat() if hasattr(log.created_at, 'isoformat') else str(log.created_at),
                        "outline": outline_data['report_outline'],
                        "mission_goal": outline_data.get('mission_goal'),
                        "action": action  # Keep original action name
                    })
            
            # Capture batch revisions
            elif (agent_name == "PlanningAgent" and 
                  "Revise Outline (Batch" in action and 
                  log_status == "success" and 
                  full_output):
                
                # Extract outline from full_output  
                outline_data = full_output
                if isinstance(outline_data, dict) and 'report_outline' in outline_data:
                    # Extract batch number
                    import re
                    batch_match = re.search(r'Batch (\d+)', action)
                    batch_num = int(batch_match.group(1)) if batch_match else 0
                    
                    outline_history.append({
                        "round": batch_num,  # Use batch number as round
                        "timestamp": log.created_at.isoformat() if hasattr(log.created_at, 'isoformat') else str(log.created_at),
                        "outline": outline_data['report_outline'],
                        "mission_goal": outline_data.get('mission_goal'),
                        "action": action  # Keep original action name
                    })
            
            # Capture finalized outline
            elif (agent_name == "AgentController" and 
                  "Finalize Preliminary Outline" in action and 
                  log_status == "success" and 
                  full_output):
                
                # Extract outline from full_output
                outline_data = full_output
                if isinstance(outline_data, dict) and 'report_outline' in outline_data:
                    outline_history.append({
                        "round": 99,  # Final outline gets a high round number
                        "timestamp": log.created_at.isoformat() if hasattr(log.created_at, 'isoformat') else str(log.created_at),
                        "outline": outline_data['report_outline'],
                        "mission_goal": outline_data.get('mission_goal'),
                        "action": "Finalized Outline"
                    })
            
            # Capture Inter-Pass revisions and other revisions
            elif ((agent_name in ["PlanningAgent", "ReflectionAgent", "AgentController"]) and 
                  ("Revise Outline" in action and "Batch" not in action) and 
                  log_status == "success" and 
                  full_output):
                
                # Extract outline from full_output
                outline_data = full_output
                if isinstance(outline_data, dict) and 'report_outline' in outline_data:
                    # Determine which round this outline is for
                    round_for_outline = current_round
                    if "Inter-Round" in action or "Inter-Pass" in action:
                        # Inter-round/pass revisions create the outline for the next round
                        # Use a special round number for final revision
                        if last_round_completed > 0 and current_round == last_round_completed:
                            round_for_outline = 98  # Special number for final revised outline
                        else:
                            round_for_outline = current_round + 1 if current_round > 0 else 1
                    
                    # Create appropriate action description
                    action_desc = "Initial Plan"
                    if "Inter-Round" in action or "Inter-Pass" in action:
                        if round_for_outline == 98:
                            action_desc = f"Final Revised Outline (After Research)"
                        else:
                            action_desc = f"Revised after Round {current_round}"
                    elif "Store Revised Plan" in action:
                        action_desc = f"Stored Revised Plan (Round {current_round})"
                    elif current_round > 0:
                        action_desc = f"Revised for Round {round_for_outline}"
                    
                    outline_history.append({
                        "round": round_for_outline,
                        "timestamp": log.created_at.isoformat() if hasattr(log.created_at, 'isoformat') else str(log.created_at),
                        "outline": outline_data['report_outline'],
                        "mission_goal": outline_data.get('mission_goal'),
                        "action": action_desc
                    })
        
        # Add the current outline from mission_context as the final outline
        if mission_context.plan and mission_context.plan.report_outline:
            # Get the last logged timestamp or use mission updated time
            last_timestamp = outline_history[-1]['timestamp'] if outline_history else str(mission_context.created_at)
            # Use mission's updated_at if available, otherwise use a timestamp slightly after the last log
            if hasattr(mission_context, 'updated_at') and mission_context.updated_at:
                current_timestamp = mission_context.updated_at.isoformat() if hasattr(mission_context.updated_at, 'isoformat') else str(mission_context.updated_at)
            else:
                # Add 1 second to the last timestamp to ensure it's the most recent
                from datetime import datetime, timedelta
                if outline_history:
                    last_dt = datetime.fromisoformat(last_timestamp.replace('+00:00', ''))
                    current_timestamp = (last_dt + timedelta(seconds=1)).isoformat()
                else:
                    current_timestamp = str(mission_context.created_at)
            
            # Add as final outline
            current_outline_data = {
                "round": 999,  # Special high number for sorting
                "timestamp": current_timestamp,
                "outline": [section.model_dump() for section in mission_context.plan.report_outline],
                "mission_goal": mission_context.plan.mission_goal if hasattr(mission_context.plan, 'mission_goal') else None,
                "action": "Final Outline",
                "is_current": True  # Mark this as the current/final outline
            }
            outline_history.append(current_outline_data)
        
        # Sort outline history by timestamp first
        outline_history.sort(key=lambda x: x['timestamp'])
        
        # Deduplicate based on content
        unique_outlines = []
        seen_content = {}  # Map content hash to the item
        
        for item in outline_history:
            # Create a content hash based on outline structure
            outline = item.get('outline', [])
            content_key = (
                len(outline),
                tuple((section.get('title', section.get('section_id', '')), 
                       len(section.get('subsections', [])) if isinstance(section, dict) else 0) 
                      for section in outline)
            )
            
            # Check if this is the current outline from database
            is_current = item.get('is_current', False)
            
            if content_key not in seen_content:
                # First time seeing this content - keep it
                seen_content[content_key] = item
                unique_outlines.append(item)
            elif is_current:
                # This is the current outline from database
                # Update the existing entry if it's not already marked as final
                existing = seen_content[content_key]
                if existing.get('round', 0) < 999:
                    # Replace with the current outline entry
                    unique_outlines = [item if o == existing else o for o in unique_outlines]
                    seen_content[content_key] = item
            # else: skip duplicates
        
        # Clean up and renumber rounds for display
        final_history = []
        round_counter = 1
        version_counters = {}  # Track versions per round
        
        for item in sorted(unique_outlines, key=lambda x: x['timestamp']):
            # Skip "Finalize Preliminary Outline" entries as they're usually duplicates
            if "Finalize" in item.get('action', '') and not item.get('is_current', False):
                continue
                
            # Generate a unique ID for this outline entry
            # Use timestamp + first 8 chars of content hash
            import hashlib
            content_str = str(item.get('outline', []))
            content_hash = hashlib.md5(content_str.encode()).hexdigest()[:8]
            unique_id = f"{item['timestamp']}_{content_hash}"
            item['id'] = unique_id
            
            # Assign clean round numbers and better action labels
            if item.get('is_current', False) or item['round'] == 999:
                # This is the final/current outline
                item['round'] = 999
                item['action'] = 'Final Outline'
            elif item['round'] in [0, 1] or "Batch 1" in item.get('action', ''):
                # Track versions for Round 1
                if 1 not in version_counters:
                    version_counters[1] = 0
                version_counters[1] += 1
                
                item['round'] = 1
                # Add version info if there are multiple versions
                if version_counters[1] == 1:
                    item['action'] = 'Round 1 Outline'
                else:
                    item['action'] = f'Round 1 Outline (v{version_counters[1]})'
            elif item['round'] == 2 or "Batch 2" in item.get('action', ''):
                # Track versions for Round 2
                if 2 not in version_counters:
                    version_counters[2] = 0
                version_counters[2] += 1
                
                item['round'] = 2
                # Add version info if there are multiple versions
                if version_counters[2] == 1:
                    item['action'] = 'Round 2 Outline'
                else:
                    item['action'] = f'Round 2 Outline (v{version_counters[2]})'
            elif item['round'] == 98 or "Inter-Pass" in item.get('action', '') or "Inter-Round" in item.get('action', ''):
                # This is a revised outline after research
                item['round'] = round_counter + 1
                item['action'] = f'Round {round_counter + 1} Outline (Revised)'
                round_counter += 1
            else:
                # Track versions for other rounds
                round_num = item['round'] if item['round'] > 0 else round_counter
                if round_num not in version_counters:
                    version_counters[round_num] = 0
                version_counters[round_num] += 1
                
                item['round'] = round_num
                # Add version info if there are multiple versions
                if version_counters[round_num] == 1:
                    item['action'] = f'Round {round_num} Outline'
                else:
                    item['action'] = f'Round {round_num} Outline (v{version_counters[round_num]})'
                
                if round_num == round_counter:
                    round_counter += 1
            
            final_history.append(item)
        
        # Sort by round number for final output
        final_history.sort(key=lambda x: x['round'])
        unique_history = final_history
        
        return {
            "mission_id": mission_id,
            "outline_history": unique_history,
            "current_outline": mission_context.plan.model_dump() if mission_context.plan else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get outline history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get outline history"
        )


@router.post("/missions/{mission_id}/unified-resume")
async def unified_resume(
    mission_id: str,
    resume_request: UnifiedResumeRequest,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    controller: AgentController = Depends(get_user_specific_agent_controller),
    db: Session = Depends(get_db)
):
    """Unified endpoint for resume/revise - handles both with optional feedback."""
    try:
        # Validate mission exists
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
            # Try to load from database
            chat = crud.get_chat(db, mission_id)
            if not chat or chat.user_id != current_user.id:
                raise HTTPException(
                    status_code=404,
                    detail="Mission not found or access denied"
                )
            # Load mission context from database
            await controller.context_manager.load_mission_from_database(mission_id)
            mission_context = controller.context_manager.get_mission_context(mission_id)
            if not mission_context:
                raise HTTPException(
                    status_code=404,
                    detail="Failed to load mission context"
                )
        
        # Create log queue and update callback
        log_queue = queue.Queue()
        
        def websocket_update_callback(log_queue_arg, entry, mission_id_arg=None, custom_event_type=None):
            """Callback to send updates via WebSocket."""
            try:
                from api.websockets import send_logs_update
                
                if isinstance(entry, dict) and entry.get("type") == "agent_feedback":
                    pass
                elif hasattr(entry, 'agent_name') and hasattr(entry, 'action'):
                    log_entry_dict = {
                        "log_id": getattr(entry, 'log_id', None),
                        "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, 'isoformat') else str(entry.timestamp),
                        "agent_name": entry.agent_name,
                        "message": entry.action,
                        "action": entry.action,
                        "input_summary": getattr(entry, 'input_summary', None),
                        "output_summary": getattr(entry, 'output_summary', None),
                        "status": getattr(entry, 'status', 'success'),
                        "error_message": getattr(entry, 'error_message', None),
                        "full_input": getattr(entry, 'full_input', None),
                        "full_output": getattr(entry, 'full_output', None),
                        "model_details": getattr(entry, 'model_details', None),
                        "tool_calls": getattr(entry, 'tool_calls', None),
                        "file_interactions": getattr(entry, 'file_interactions', None)
                    }
                    asyncio.create_task(send_logs_update(mission_id, [log_entry_dict]))
            except Exception as e:
                logger.error(f"Error in websocket update callback: {e}")
        
        # Send truncation notification to frontend
        from api.websockets import send_mission_update
        await send_mission_update(mission_id, {
            "type": "truncate_data",
            "round_num": resume_request.round_num,
            "message": f"Clearing logs and notes after round {resume_request.round_num - 1}"
        })
        
        # If a specific outline is provided, use it instead of the current one
        if resume_request.outline_data and 'outline' in resume_request.outline_data:
            # Parse the provided outline data
            from ai_researcher.agentic_layer.schemas.planning import ReportSection
            outline_data = resume_request.outline_data['outline']
            
            # Convert outline data to ReportSection objects
            new_outline = []
            for section_data in outline_data:
                if isinstance(section_data, dict):
                    # Recursively convert subsections if they exist
                    if 'subsections' in section_data:
                        section_data['subsections'] = [
                            ReportSection(**subsec) if isinstance(subsec, dict) else subsec
                            for subsec in section_data['subsections']
                        ]
                    new_outline.append(ReportSection(**section_data) if isinstance(section_data, dict) else section_data)
            
            # Update the mission context with the specific outline
            if mission_context.plan:
                mission_context.plan.report_outline = new_outline
                # Store the updated plan to persist it
                await controller.context_manager.store_plan(mission_id, mission_context.plan)
                logger.info(f"Using specific outline with ID {resume_request.outline_id} for mission {mission_id}")
        
        # Update mission status to running
        await controller.context_manager.update_mission_status(mission_id, "running")
        
        # Execute in background
        loop = asyncio.get_event_loop()
        thread_pool = request.app.state.thread_pool
        
        if resume_request.feedback:
            # With feedback - revise outline and resume
            def run_revise_in_thread():
                """Revise outline and resume in thread with user context."""
                set_current_user(current_user)
                asyncio.run(controller.revise_outline_and_resume(
                    mission_id,
                    resume_request.round_num,
                    resume_request.feedback,
                    log_queue=log_queue,
                    update_callback=websocket_update_callback
                ))
            
            loop.run_in_executor(thread_pool, run_revise_in_thread)
            
            logger.info(f"Mission {mission_id} outline revision and resume initiated")
            return {
                "message": "Outline revision and resume initiated",
                "mission_id": mission_id,
                "round_num": resume_request.round_num,
                "has_feedback": True
            }
        else:
            # Without feedback - just resume from round
            def run_resume_in_thread():
                """Resume mission in thread with user context."""
                set_current_user(current_user)
                asyncio.run(controller.resume_from_round(
                    mission_id,
                    resume_request.round_num,
                    log_queue=log_queue,
                    update_callback=websocket_update_callback
                ))
            
            loop.run_in_executor(thread_pool, run_resume_in_thread)
            
            logger.info(f"Mission {mission_id} resuming from round {resume_request.round_num}")
            return {
                "message": f"Mission resuming from round {resume_request.round_num}",
                "mission_id": mission_id,
                "round_num": resume_request.round_num,
                "has_feedback": False
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute unified resume: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to execute unified resume"
        )


@router.post("/missions/{mission_id}/start")
async def start_mission_execution(
    mission_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager),
    controller: AgentController = Depends(get_user_specific_agent_controller),
    db: Session = Depends(get_db)
):
    """
    Start or resume the execution of a mission.
    This endpoint is the single point of entry for initiating research.
    IMPORTANT: This now returns immediately and runs all heavy operations in background.
    """
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        # IMPORTANT: Capture user's current settings at the time of starting the research
        # This ensures we use the most recent settings, not what was stored at mission creation
        logger.info(f"Capturing current user settings for mission {mission_id} at research start time")
        
        # Get user's current research parameters
        async_db = await get_async_db_session()
        try:
            user_settings = await async_crud.get_user_settings(async_db, current_user.id)
        finally:
            await async_db.close()
        current_research_params = None
        if user_settings:
            # user_settings is already a dict from get_user_settings
            settings_dict = json.loads(user_settings) if isinstance(user_settings, str) else user_settings
            # Fixed: Use "research_parameters" not "research" to match the actual settings structure
            research_settings = settings_dict.get("research_parameters", {})
            
            # Extract research parameters from user's current settings
            current_research_params = {
                "initial_research_max_depth": research_settings.get("initial_research_max_depth"),
                "initial_research_max_questions": research_settings.get("initial_research_max_questions"),
                "structured_research_rounds": research_settings.get("structured_research_rounds"),
                "writing_passes": research_settings.get("writing_passes"),
                "initial_exploration_doc_results": research_settings.get("initial_exploration_doc_results"),
                "initial_exploration_web_results": research_settings.get("initial_exploration_web_results"),
                "main_research_doc_results": research_settings.get("main_research_doc_results"),
                "main_research_web_results": research_settings.get("main_research_web_results"),
                "thought_pad_context_limit": research_settings.get("thought_pad_context_limit"),
                "max_notes_for_assignment_reranking": research_settings.get("max_notes_for_assignment_reranking"),
                "max_concurrent_requests": research_settings.get("max_concurrent_requests"),
                "skip_final_replanning": research_settings.get("skip_final_replanning"),
                "auto_create_document_group": research_settings.get("auto_create_document_group"),
                "max_research_cycles_per_section": research_settings.get("max_research_cycles_per_section"),
                "max_total_iterations": research_settings.get("max_total_iterations"),
                "max_total_depth": research_settings.get("max_total_depth"),
                "min_notes_per_section_assignment": research_settings.get("min_notes_per_section_assignment"),
                "max_notes_per_section_assignment": research_settings.get("max_notes_per_section_assignment"),
                "max_planning_context_chars": research_settings.get("max_planning_context_chars"),
                "writing_previous_content_preview_chars": research_settings.get("writing_previous_content_preview_chars"),
                "max_suggestions_per_batch": research_settings.get("max_suggestions_per_batch"),
            }
            
            # Remove None values
            current_research_params = {k: v for k, v in current_research_params.items() if v is not None}
            
            logger.info(f"Captured {len(current_research_params)} research parameters from user settings at start time")
        
        # Update mission with current settings if they exist
        if current_research_params:
            # Get existing metadata
            existing_metadata = mission_context.metadata or {}
            
            # Preserve auto_create_document_group if it was already set
            existing_research_params = existing_metadata.get("research_params", {})
            if "auto_create_document_group" in existing_research_params:
                current_research_params["auto_create_document_group"] = existing_research_params["auto_create_document_group"]
            
            # Update research_params with current settings
            existing_metadata["research_params"] = current_research_params
            existing_metadata["settings_captured_at_start"] = True
            existing_metadata["start_time_capture"] = datetime.now().isoformat()
            
            # Update comprehensive_settings if it exists
            if "comprehensive_settings" in existing_metadata:
                existing_metadata["comprehensive_settings"]["research_params"] = current_research_params
                existing_metadata["comprehensive_settings"]["settings_captured_at_start"] = True
                existing_metadata["comprehensive_settings"]["start_time_capture"] = datetime.now().isoformat()
            
            # Store the updated metadata
            await context_mgr.update_mission_metadata(mission_id, existing_metadata)
            logger.info(f"Updated mission {mission_id} with current research settings captured at start time")

        # Allow starting from 'pending' or 'stopped' states
        if mission_context.status not in ["pending", "stopped", "planning"]:
            raise HTTPException(
                status_code=400,
                detail=f"Mission cannot be started. Current status: {mission_context.status}"
            )

        # Get thread pool and event loop for background execution
        thread_pool: ThreadPoolExecutor = request.app.state.thread_pool
        loop = asyncio.get_event_loop()
        
        # Define the background task that handles ALL preparation and execution
        async def prepare_and_run_mission():
            """Background task to prepare mission (planning + optimization) and start execution."""
            try:
                # Update status to indicate we're preparing
                await context_mgr.update_mission_metadata(mission_id, {"status": "planning"})
                
                # --- Self-Sufficiency Check ---
                # Check for questions from the chat interaction in all possible metadata fields
                # Priority order: final_questions > refined_questions > initial_questions > questions
                existing_questions = (
                    mission_context.metadata.get("final_questions") or 
                    mission_context.metadata.get("refined_questions") or 
                    mission_context.metadata.get("initial_questions") or
                    mission_context.metadata.get("questions")
                )
                
                # Log what we found
                if existing_questions:
                    logger.info(f"Found {len(existing_questions)} existing questions in metadata for mission {mission_id}")
                    # Log which field contained the questions for debugging
                    for field in ["final_questions", "refined_questions", "initial_questions", "questions"]:
                        if mission_context.metadata.get(field):
                            logger.info(f"Questions found in metadata field: {field}")
                            break
                else:
                    logger.info(f"No questions found in any metadata field for mission {mission_id}")
                
                if not existing_questions:
                    # DO NOT use plan outline as questions - that's for structured research, not initial questions
                    # Only generate new questions if we truly don't have any
                    logger.info(f"No questions found for mission {mission_id}. Will need to generate them...")
                    
                    # Log to frontend that we're generating questions
                    await context_mgr.log_execution_step(
                        mission_id=mission_id,
                        agent_name="PlanningAgent",
                        action="Generating Research Questions",
                        output_summary="Creating initial research questions based on your request...",
                        status="running"
                    )
                    
                    # Generate questions using the planning agent
                    plan_response, _, _ = await controller.planning_agent.run(
                        user_request=mission_context.user_request,
                        mission_id=mission_id
                    )
                    
                    if plan_response and plan_response.report_outline:
                        questions = [section.title for section in plan_response.report_outline if section.title]
                        if not questions: # Fallback if titles are empty
                            questions = [f"What are the key aspects of {mission_context.user_request}?"]
                        
                        # Store the generated questions as the final questions
                        await context_mgr.update_mission_metadata(mission_id, {"final_questions": questions})
                        logger.info(f"Generated and stored {len(questions)} questions for mission {mission_id}.")
                        
                        # Log success to frontend
                        await context_mgr.log_execution_step(
                            mission_id=mission_id,
                            agent_name="PlanningAgent",
                            action="Questions Generated",
                            output_summary=f"Generated {len(questions)} research questions successfully.",
                            status="success"
                        )
                    else:
                        # If question generation fails, create a default set to ensure the mission can proceed
                        logger.warning(f"Failed to generate questions for mission {mission_id}. Using default questions.")
                        default_questions = [
                            f"What is {mission_context.user_request}?",
                            f"What are the key components or aspects of {mission_context.user_request}?",
                            f"What is the significance or impact of {mission_context.user_request}?"
                        ]
                        await context_mgr.update_mission_metadata(mission_id, {"final_questions": default_questions})
                        
                        # Log warning to frontend
                        await context_mgr.log_execution_step(
                            mission_id=mission_id,
                            agent_name="PlanningAgent",
                            action="Using Default Questions",
                            output_summary="Using default research questions due to generation failure.",
                            status="warning"
                        )
                else:
                    # If we have questions from chat interaction, make sure they're stored as final_questions
                    if not mission_context.metadata.get("final_questions"):
                        await context_mgr.update_mission_metadata(mission_id, {"final_questions": existing_questions})
                        logger.info(f"Copied existing questions to final_questions field for mission {mission_id}")
                    logger.info(f"Using existing {len(existing_questions)} questions for mission {mission_id}:")
                    for i, q in enumerate(existing_questions, 1):
                        logger.info(f"  Question {i}: {q}")
                
                # Tool selection should already be set during mission creation
                # Log if it's missing for debugging purposes
                if not mission_context.metadata.get("tool_selection"):
                    logger.warning(f"Tool selection not found in mission {mission_id} metadata. This should not happen.")
                    # Use conservative defaults - no web search to avoid unintended behavior
                    await context_mgr.update_mission_metadata(mission_id, {"tool_selection": {"local_rag": True, "web_search": False}})

                # Apply auto-optimization logic with comprehensive logging
                try:
                    # Get chat_id from mission metadata
                    chat_id = mission_context.metadata.get("chat_id") if mission_context.metadata else None
                    if chat_id:
                        async_db = await get_async_db_session()
                        try:
                            chat_history = await async_crud.get_chat_messages(async_db, chat_id=chat_id, user_id=current_user.id)
                        finally:
                            await async_db.close()
                        
                        # Log that we're optimizing
                        await context_mgr.log_execution_step(
                            mission_id=mission_id,
                            agent_name="Configuration",
                            action="Optimizing Research Parameters",
                            output_summary="Analyzing your request to optimize research parameters...",
                            status="running"
                        )
                        
                        # Use the shared auto-optimization function for consistent behavior and logging
                        from ai_researcher.settings_optimizer import apply_auto_optimization
                        await apply_auto_optimization(
                            mission_id=mission_id,
                            current_user=current_user,
                            context_mgr=context_mgr,
                            controller=controller,
                            chat_history=chat_history
                        )
                        
                        # Log optimization complete
                        await context_mgr.log_execution_step(
                            mission_id=mission_id,
                            agent_name="Configuration",
                            action="Optimization Complete",
                            output_summary="Research parameters optimized successfully.",
                            status="success"
                        )
                    else:
                        logger.warning(f"No chat_id found in mission metadata for mission {mission_id}. Skipping auto-optimization.")
                    
                except Exception as e:
                    logger.warning(f"Failed to apply auto-optimization for mission {mission_id}: {e}", exc_info=True)
                    # Log warning but continue
                    await context_mgr.log_execution_step(
                        mission_id=mission_id,
                        agent_name="Configuration",
                        action="Optimization Skipped",
                        output_summary="Using default parameters due to optimization failure.",
                        status="warning"
                    )

                # Now start the actual mission execution
                # Create a queue and callback function for WebSocket updates
                log_queue = queue.Queue()
                
                def websocket_update_callback(
                    q: queue.Queue,
                    update_data: Any
                ):
                    """Callback to send updates via WebSocket."""
                    try:
                        # Import send_logs_update function locally to avoid circular imports
                        from api.websockets import send_logs_update
                        
                        if isinstance(update_data, dict) and update_data.get("type") == "agent_feedback":
                            # Handle agent feedback messages (these are already formatted correctly)
                            # These are sent directly via WebSocket without queue processing
                            pass
                        elif hasattr(update_data, 'agent_name') and hasattr(update_data, 'action'):
                            # This is an ExecutionLogEntry object, transform it for frontend
                            log_entry_dict = {
                                "log_id": getattr(update_data, 'log_id', None),  # Include the unique log ID
                                "timestamp": update_data.timestamp.isoformat() if hasattr(update_data.timestamp, 'isoformat') else str(update_data.timestamp),
                                "agent_name": update_data.agent_name,
                                "message": update_data.action,  # Add message field for frontend compatibility
                                "action": update_data.action,
                                "input_summary": getattr(update_data, 'input_summary', None),
                                "output_summary": getattr(update_data, 'output_summary', None),
                                "status": getattr(update_data, 'status', 'success'),
                                "error_message": getattr(update_data, 'error_message', None),
                                "full_input": getattr(update_data, 'full_input', None),
                                "full_output": getattr(update_data, 'full_output', None),
                                "model_details": getattr(update_data, 'model_details', None),
                                "tool_calls": getattr(update_data, 'tool_calls', None),
                                "file_interactions": getattr(update_data, 'file_interactions', None)
                            }
                            
                            # Process the log entry to clean tool calls and replace document codes
                            try:
                                import asyncio
                                # Create a new event loop if needed for the async processing
                                try:
                                    loop = asyncio.get_event_loop()
                                except RuntimeError:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                
                                # Process the log entry asynchronously
                                if loop.is_running():
                                    # If loop is already running, we can't use run_until_complete
                                    # So we'll just clean the tool calls and input summary synchronously for now
                                    from api.utils import clean_tool_call_arguments, clean_input_summary_for_display
                                    if log_entry_dict.get('tool_calls'):
                                        log_entry_dict['tool_calls'] = clean_tool_call_arguments(log_entry_dict['tool_calls'])
                                    if log_entry_dict.get('input_summary'):
                                        log_entry_dict['input_summary'] = clean_input_summary_for_display(log_entry_dict['input_summary'])
                                else:
                                    # If loop is not running, we can process fully
                                    processed_entry = loop.run_until_complete(
                                        process_execution_log_entry_for_frontend(log_entry_dict)
                                    )
                                    log_entry_dict = processed_entry
                            except Exception as process_error:
                                logger.warning(f"Failed to process log entry for frontend: {process_error}")
                                # Fall back to basic tool call cleaning
                                from api.utils import clean_tool_call_arguments
                                if log_entry_dict.get('tool_calls'):
                                    log_entry_dict['tool_calls'] = clean_tool_call_arguments(log_entry_dict['tool_calls'])
                            
                            # Send the log entry via WebSocket
                            import asyncio
                            try:
                                # Create a new event loop if needed
                                try:
                                    loop = asyncio.get_event_loop()
                                except RuntimeError:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                
                                # Run the async function in the event loop
                                if loop.is_running():
                                    # If loop is already running, create a task
                                    loop.create_task(send_logs_update(mission_id, [log_entry_dict]))
                                else:
                                    # If loop is not running, run until complete
                                    loop.run_until_complete(send_logs_update(mission_id, [log_entry_dict]))
                            except Exception as ws_error:
                                logger.error(f"Failed to send log update via WebSocket for mission {mission_id}: {ws_error}")
                    except Exception as e:
                        logger.error(f"Error in websocket_update_callback for mission {mission_id}: {e}")
                
                # Create document group if auto_create_document_group is enabled
                # Check both current_research_params and mission metadata for the flag
                mission_metadata = mission_context.metadata or {}
                mission_research_params = mission_metadata.get("research_params", {})
                auto_create_flag = (
                    (current_research_params and current_research_params.get("auto_create_document_group")) or
                    mission_research_params.get("auto_create_document_group")
                )
                logger.info(f"Checking auto_create_document_group for mission {mission_id}: current_params={current_research_params}, mission_params={mission_research_params}, flag={auto_create_flag}")
                if auto_create_flag:
                    logger.info(f"auto_create_document_group is enabled for mission {mission_id}, creating document group...")
                    
                    # Get database session
                    db = next(get_db())
                    try:
                        # Get the mission's chat
                        mission_db = crud.get_mission(db, mission_id=mission_id, user_id=current_user.id)
                        chat_db = crud.get_chat(db, chat_id=mission_db.chat_id, user_id=current_user.id) if mission_db else None
                        
                        # Create a new document group with concise name
                        # Extract first meaningful part of request for concise name
                        request_words = mission_context.user_request.split()[:5]  # First 5 words
                        concise_request = " ".join(request_words)
                        if len(mission_context.user_request.split()) > 5:
                            concise_request += "..."
                        group_name = f"Research: {concise_request}"
                        group_id = str(uuid.uuid4())
                        document_group = crud.create_document_group(
                            db=db,
                            group_id=group_id,
                            user_id=current_user.id,
                            name=group_name,
                            description=f"Auto-generated documents from research: {mission_context.user_request}"
                        )
                        
                        # Update document group with mission reference
                        document_group.source_mission_id = mission_id
                        document_group.auto_generated = True
                        
                        # Store the document group ID in the mission
                        mission_db.generated_document_group_id = group_id
                        
                        # Also link the document group to the chat if it exists
                        if chat_db:
                            chat_db.document_group_id = group_id
                        
                        db.commit()
                        
                        # Update mission metadata to include the document group ID
                        await context_mgr.update_mission_metadata(mission_id, {
                            "generated_document_group_id": group_id,
                            "generated_document_group_name": group_name
                        })
                        
                        logger.info(f"Created auto document group {group_id} for mission {mission_id}")
                        
                        # Log to frontend
                        await context_mgr.log_execution_step(
                            mission_id=mission_id,
                            agent_name="System",
                            action="Document Group Created",
                            output_summary=f"Auto-created document group '{group_name}' for collecting research documents.",
                            status="success"
                        )
                    except Exception as e:
                        logger.error(f"Failed to create auto document group for mission {mission_id}: {e}")
                        # Continue without document group - this shouldn't block the mission
                    finally:
                        db.close()
                
                # Run the actual mission
                logger.info(f"Starting main mission execution for {mission_id}")
                await controller.run_mission(
                    mission_id,
                    log_queue=log_queue,
                    update_callback=websocket_update_callback
                )
                
            except Exception as e:
                logger.error(f"Error in mission preparation/execution for {mission_id}: {e}", exc_info=True)
                # Update mission status to failed
                await context_mgr.update_mission_metadata(mission_id, {"status": "failed", "error_info": str(e)})
                # Log error to frontend
                await context_mgr.log_execution_step(
                    mission_id=mission_id,
                    agent_name="System",
                    action="Mission Failed",
                    output_summary=f"Mission failed: {str(e)}",
                    status="failure",
                    error_message=str(e)
                )
            finally:
                # Clean up the model dispatcher to prevent connection errors
                if hasattr(controller, 'model_dispatcher') and hasattr(controller.model_dispatcher, 'cleanup'):
                    try:
                        await controller.model_dispatcher.cleanup()
                        logger.debug(f"Cleaned up model dispatcher for mission {mission_id}")
                    except Exception as cleanup_error:
                        logger.warning(f"Error cleaning up model dispatcher for mission {mission_id}: {cleanup_error}")
        
        # Start the background task that handles everything
        def run_background_task():
            """Wrapper to run async task in thread with user context."""
            set_current_user(current_user)
            asyncio.run(prepare_and_run_mission())
        
        # Execute in background thread pool
        loop.run_in_executor(thread_pool, run_background_task)
        
        # Update status to indicate we're starting
        await context_mgr.update_mission_metadata(mission_id, {"status": "planning"})
        
        logger.info(f"Mission {mission_id} preparation and execution started in background")
        return {"message": "Mission execution started", "mission_id": mission_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start mission execution for {mission_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to start mission execution"
        )

@router.get("/missions/{mission_id}/context", response_model=MissionContextResponse)
async def get_mission_context_data(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get the context data for a mission, including goals and scratchpads."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        return MissionContextResponse(
            mission_id=mission_id,
            goal_pad=mission_context.goal_pad,
            thought_pad=mission_context.thought_pad,
            agent_scratchpad=mission_context.agent_scratchpad
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission context data: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission context data"
        )

@router.get("/missions/{mission_id}/info")
async def get_mission_info(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get complete mission information including tool_selection and document_group_id."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Extract all relevant metadata
        metadata = mission_context.metadata or {}
        tool_selection = metadata.get("tool_selection")
        document_group_id = metadata.get("document_group_id")
        document_group_name = metadata.get("document_group_name")
        use_web_search = metadata.get("use_web_search")
        use_local_rag = metadata.get("use_local_rag")
        
        # Also check comprehensive settings if available
        comprehensive = metadata.get("comprehensive_settings", {})
        if comprehensive:
            # Use comprehensive settings as the source of truth
            document_group_id = document_group_id or comprehensive.get("document_group_id")
            document_group_name = document_group_name or comprehensive.get("document_group_name")
            use_web_search = use_web_search if use_web_search is not None else comprehensive.get("use_web_search")
            use_local_rag = use_local_rag if use_local_rag is not None else comprehensive.get("use_local_rag")
        
        return {
            "mission_id": mission_id,
            "status": mission_context.status,
            "user_request": mission_context.user_request,
            "created_at": mission_context.created_at,
            "updated_at": mission_context.updated_at,
            "tool_selection": tool_selection,
            "document_group_id": document_group_id,
            "document_group_name": document_group_name,
            "use_web_search": use_web_search,
            "use_local_rag": use_local_rag,
            "error_info": mission_context.error_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission info"
        )

@router.get("/missions/{mission_id}/settings", response_model=MissionSettingsResponse)
async def get_mission_settings(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get the settings for a mission, including effective settings after fallback."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Get mission-specific settings
        mission_settings_data = mission_context.metadata.get("mission_settings") if mission_context.metadata else None
        mission_settings = MissionSettings(**mission_settings_data) if mission_settings_data else None
        
        # Import dynamic config functions to get effective settings
        from ai_researcher.dynamic_config import (
            get_initial_research_max_depth, get_initial_research_max_questions,
            get_structured_research_rounds, get_writing_passes,
            get_initial_exploration_doc_results, get_initial_exploration_web_results,
            get_main_research_doc_results, get_main_research_web_results,
            get_thought_pad_context_limit, get_max_notes_for_assignment_reranking,
            get_max_concurrent_requests, get_skip_final_replanning
        )
        
        # Get effective settings (after fallback)
        effective_settings = MissionSettings(
            initial_research_max_depth=get_initial_research_max_depth(mission_id),
            initial_research_max_questions=get_initial_research_max_questions(mission_id),
            structured_research_rounds=get_structured_research_rounds(mission_id),
            writing_passes=get_writing_passes(mission_id),
            initial_exploration_doc_results=get_initial_exploration_doc_results(mission_id),
            initial_exploration_web_results=get_initial_exploration_web_results(mission_id),
            main_research_doc_results=get_main_research_doc_results(mission_id),
            main_research_web_results=get_main_research_web_results(mission_id),
            thought_pad_context_limit=get_thought_pad_context_limit(mission_id),
            max_notes_for_assignment_reranking=get_max_notes_for_assignment_reranking(mission_id),
            max_concurrent_requests=get_max_concurrent_requests(mission_id),
            skip_final_replanning=get_skip_final_replanning(mission_id)
        )
        
        return MissionSettingsResponse(
            mission_id=mission_id,
            settings=mission_settings,
            effective_settings=effective_settings
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get mission settings"
        )

@router.get("/missions/{mission_id}/comprehensive-settings")
async def get_comprehensive_mission_settings(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Get comprehensive mission settings including all parameters used when creating the mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Get comprehensive settings stored at mission creation
        comprehensive_settings = mission_context.metadata.get("comprehensive_settings") if mission_context.metadata else None
        
        # Check if research_params are stored at top level of metadata (from our fix)
        research_params = mission_context.metadata.get("research_params") if mission_context.metadata else None
        
        # If research_params exist at top level, add them to comprehensive_settings
        if research_params and comprehensive_settings:
            comprehensive_settings = dict(comprehensive_settings)  # Make a copy
            comprehensive_settings["research_params"] = research_params
            comprehensive_settings["settings_captured_at_start"] = mission_context.metadata.get("settings_captured_at_start", False)
            comprehensive_settings["start_method"] = mission_context.metadata.get("start_method")
            comprehensive_settings["start_time_capture"] = mission_context.metadata.get("start_time_capture")
        elif research_params and not comprehensive_settings:
            # If only research_params exist, create comprehensive_settings with them
            comprehensive_settings = {
                "research_params": research_params,
                "settings_captured_at_start": mission_context.metadata.get("settings_captured_at_start", False),
                "start_method": mission_context.metadata.get("start_method"),
                "start_time_capture": mission_context.metadata.get("start_time_capture"),
                "use_web_search": mission_context.metadata.get("tool_selection", {}).get("web_search", False),
                "use_local_rag": mission_context.metadata.get("tool_selection", {}).get("local_rag", False),
                "document_group_id": mission_context.metadata.get("document_group_id")
            }
        elif not research_params and not comprehensive_settings:
            # No settings were captured for this mission
            # Don't show defaults as that would be misleading - just return empty/minimal info
            comprehensive_settings = {
                "settings_not_captured": True,
                "message": "Settings were not captured for this mission. This feature was added after this mission started.",
                "use_web_search": mission_context.metadata.get("tool_selection", {}).get("web_search", False) if mission_context.metadata else False,
                "use_local_rag": mission_context.metadata.get("tool_selection", {}).get("local_rag", False) if mission_context.metadata else False,
                "document_group_id": mission_context.metadata.get("document_group_id") if mission_context.metadata else None
            }
        
        # Also get mission-specific settings if they exist
        mission_settings = mission_context.metadata.get("mission_settings") if mission_context.metadata else None
        
        # Get tool selection and document group info
        tool_selection = mission_context.metadata.get("tool_selection") if mission_context.metadata else None
        document_group_id = mission_context.metadata.get("document_group_id") if mission_context.metadata else None
        
        # Get stats from mission context
        total_cost = mission_context.total_cost if hasattr(mission_context, 'total_cost') else 0
        total_tokens = {
            "prompt": mission_context.total_prompt_tokens if hasattr(mission_context, 'total_prompt_tokens') else 0,
            "completion": mission_context.total_completion_tokens if hasattr(mission_context, 'total_completion_tokens') else 0,
            "native": mission_context.total_native_prompt_tokens if hasattr(mission_context, 'total_native_prompt_tokens') else 0
        }
        total_web_searches = mission_context.total_web_searches if hasattr(mission_context, 'total_web_searches') else 0
        
        return {
            "mission_id": mission_id,
            "status": mission_context.status,
            "created_at": mission_context.created_at,
            "user_request": mission_context.user_request,
            "comprehensive_settings": comprehensive_settings,
            "mission_specific_settings": mission_settings,
            "tool_selection": tool_selection,
            "document_group_id": document_group_id,
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "total_web_searches": total_web_searches
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get comprehensive mission settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get comprehensive mission settings"
        )

@router.post("/missions/{mission_id}/settings", response_model=MissionSettingsResponse)
async def update_mission_settings(
    mission_id: str,
    settings_update: MissionSettingsUpdate,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: AsyncContextManager = Depends(get_context_manager)
):
    """Update the settings for a mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=404,
                detail="Mission not found"
            )
        
        # Convert settings to dict, excluding None values
        settings_dict = settings_update.settings.model_dump(exclude_none=True)
        
        # Update mission metadata with new settings
        await context_mgr.update_mission_metadata(mission_id, {"mission_settings": settings_dict})
        
        logger.info(f"Updated mission settings for {mission_id}: {settings_dict}")
        
        # Return the updated settings response
        return await get_mission_settings(mission_id, current_user, context_mgr)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update mission settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to update mission settings"
        )

class MarkdownContent(BaseModel):
    markdown_content: str
    filename: Optional[str] = None

@router.post("/missions/{mission_id}/report/docx")
async def download_report_as_docx(
    mission_id: str,
    content: MarkdownContent,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Converts Markdown content to a DOCX file and returns it for download."""
    try:
        # Create a temporary file for the DOCX output
        import tempfile
        import os
        
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
            
            # Use custom filename if provided, otherwise fallback to mission ID
            filename = content.filename if content.filename else f"research-draft-{mission_id[:8]}"
            
            # Create response with proper headers
            response = Response(
                content=docx_content,
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}.docx"'
                }
            )
            
            logger.info(f"Successfully converted report to DOCX for mission {mission_id}")
            return response
            
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    except Exception as e:
        logger.error(f"Failed to convert report to DOCX for mission {mission_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to convert report to DOCX: {str(e)}")

@router.post("/missions/{mission_id}/create-document-group")
async def create_document_group_from_mission(
    mission_id: str,
    request: CreateDocumentGroupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Create a document group from all relevant documents used in a mission.
    This includes documents from web searches and the document database that were deemed relevant.
    """
    import hashlib
    
    try:
        # Get the mission
        mission = crud.get_mission(db, mission_id=mission_id, user_id=current_user.id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        # Check if a document group was already generated for this mission
        if mission.generated_document_group_id:
            existing_group = crud.get_document_group(db, group_id=str(mission.generated_document_group_id), user_id=current_user.id)
            if existing_group:
                return {
                    "message": "Document group already exists for this mission",
                    "document_group_id": str(existing_group.id),
                    "document_group_name": existing_group.name,
                    "document_count": len(existing_group.documents)
                }
        
        # Get mission context to extract notes
        context_manager = AsyncContextManager()
        mission_context = context_manager.get_mission_context(mission_id)
        
        if not mission_context:
            raise HTTPException(status_code=404, detail="Mission context not found")
        
        # Collect unique document IDs and web sources
        document_ids = set()
        web_sources = []
        
        # Extract documents from notes
        notes = mission_context.notes if hasattr(mission_context, 'notes') and mission_context.notes else []
        
        for note in notes:
            # Only include relevant notes
            if hasattr(note, 'is_relevant') and not note.is_relevant:
                continue
                
            source_type = note.source_type if hasattr(note, 'source_type') else None
            source_id = note.source_id if hasattr(note, 'source_id') else None
            
            if source_type == "document" and request.include_database_documents and source_id:
                # Extract document ID from source_id (might be chunk_id)
                if hasattr(note, 'source_metadata') and note.source_metadata:
                    if hasattr(note.source_metadata, 'doc_id') and note.source_metadata.doc_id:
                        document_ids.add(note.source_metadata.doc_id)
                    elif '_' in source_id:
                        # Try to extract doc_id from chunk_id format
                        doc_id = source_id.split('_')[0]
                        document_ids.add(doc_id)
                        
            elif source_type == "web" and request.include_web_sources and source_id:
                # Collect web source info
                web_source = {
                    "url": source_id,
                    "title": None,
                    "content": note.content if hasattr(note, 'content') else None
                }
                
                if hasattr(note, 'source_metadata') and note.source_metadata:
                    if hasattr(note.source_metadata, 'title'):
                        web_source["title"] = note.source_metadata.title
                    if hasattr(note.source_metadata, 'url'):
                        web_source["url"] = note.source_metadata.url or source_id
                        
                web_sources.append(web_source)
        
        # Create documents for web sources if needed
        created_doc_ids = []
        if request.include_web_sources and web_sources:
            # Group web sources by URL to avoid duplicates
            unique_web_sources = {}
            for source in web_sources:
                url = source["url"]
                if url not in unique_web_sources:
                    unique_web_sources[url] = source
                elif source.get("title") and not unique_web_sources[url].get("title"):
                    # Update title if we found a better one
                    unique_web_sources[url]["title"] = source["title"]
            
            # Create document entries for web sources
            for url, source in unique_web_sources.items():
                # Generate a hash for the URL to use as doc ID
                url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
                doc_id = f"web_{url_hash}"
                
                # Check if document already exists
                existing_doc = crud.get_document_by_id(db, doc_id=doc_id, user_id=current_user.id)
                if not existing_doc:
                    # Create a new document entry for web source
                    title = source.get("title") or f"Web Source: {url[:50]}..."
                    now = crud.get_current_time()
                    
                    web_doc = models.Document(
                        id=doc_id,
                        user_id=current_user.id,
                        title=title,
                        original_filename=url,
                        content_hash=url_hash,
                        source_type="web",
                        processing_status="completed",
                        created_at=now,
                        updated_at=now,
                        metadata={
                            "url": url,
                            "source": "mission_web_search",
                            "mission_id": mission_id
                        }
                    )
                    db.add(web_doc)
                    created_doc_ids.append(doc_id)
                else:
                    created_doc_ids.append(existing_doc.id)
        
        # Combine all document IDs
        all_doc_ids = list(document_ids) + created_doc_ids
        
        if not all_doc_ids:
            raise HTTPException(status_code=400, detail="No relevant documents found in mission")
        
        # Create document group with concise name
        if request.group_name:
            group_name = request.group_name
        else:
            # Extract first meaningful part of request for concise name
            request_words = mission.user_request.split()[:5]  # First 5 words
            concise_request = " ".join(request_words)
            if len(mission.user_request.split()) > 5:
                concise_request += "..."
            group_name = f"Research: {concise_request}"
        group_id = str(uuid.uuid4())
        
        document_group = crud.create_document_group(
            db=db,
            group_id=group_id,
            user_id=current_user.id,
            name=group_name,
            description=f"Documents from research mission: {mission.user_request}"
        )
        
        # Update document group with additional fields
        document_group.source_mission_id = mission_id
        document_group.auto_generated = True
        
        # Add documents to the group
        for doc_id in all_doc_ids:
            document = crud.get_document_by_id(db, doc_id=doc_id, user_id=current_user.id)
            if document:
                document_group.documents.append(document)
        
        # Update mission to reference the generated document group
        mission.generated_document_group_id = group_id
        
        # Commit all changes
        db.commit()
        db.refresh(document_group)
        
        logger.info(f"Created document group {group_id} with {len(all_doc_ids)} documents for mission {mission_id}")
        
        return {
            "message": "Document group created successfully",
            "document_group_id": group_id,
            "document_group_name": document_group.name,
            "document_count": len(document_group.documents),
            "web_sources_count": len(created_doc_ids),
            "database_documents_count": len(document_ids)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create document group for mission {mission_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create document group: {str(e)}")

@router.get("/missions/{mission_id}/document-group")
async def get_mission_document_group(
    mission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Get the document group that was generated from this mission, if any.
    """
    try:
        # Get the mission
        mission = crud.get_mission(db, mission_id=mission_id, user_id=current_user.id)
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        if not mission.generated_document_group_id:
            return {
                "has_document_group": False,
                "document_group": None
            }
        
        # Get the document group
        document_group = crud.get_document_group(db, group_id=str(mission.generated_document_group_id), user_id=current_user.id)
        if not document_group:
            return {
                "has_document_group": False,
                "document_group": None
            }
        
        return {
            "has_document_group": True,
            "document_group": {
                "id": str(document_group.id),
                "name": document_group.name,
                "description": document_group.description,
                "document_count": len(document_group.documents),
                "created_at": document_group.created_at.isoformat() if document_group.created_at else None,
                "auto_generated": document_group.auto_generated if hasattr(document_group, 'auto_generated') else False
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document group for mission {mission_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get document group: {str(e)}")
