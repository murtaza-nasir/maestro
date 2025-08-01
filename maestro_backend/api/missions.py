from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response
from pydantic import BaseModel
import pypandoc
import io
from typing import Dict, Optional, List, Any
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import queue
import time
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
from database import crud
from database.models import User
from ai_researcher.agentic_layer.context_manager import ContextManager
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.agent_controller import AgentController
import json
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.user_context import set_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

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
            # Use pre-fetched filename mappings
            if source_id:
                from services.document_service import document_service
                document_codes = document_service.extract_document_codes_from_text(source_id)
                if document_codes and document_codes[0] in code_to_filename:
                    transformed["source"] = code_to_filename[document_codes[0]]
                else:
                    transformed["source"] = source_id or "Unknown Document"
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
context_manager: Optional[ContextManager] = None
agent_controller: Optional[AgentController] = None

def initialize_ai_components():
    """Initialize the AI research components."""
    global context_manager, agent_controller
    
    try:
        # Initialize core components
        context_manager = ContextManager(db_session_factory=SessionLocal)
        # Initialize ModelDispatcher with empty user settings for global instance
        # Individual missions will create their own dispatchers with user-specific settings
        model_dispatcher = ModelDispatcher({})
        tool_registry = ToolRegistry()
        
        # Initialize RAG components
        from ai_researcher.core_rag.embedder import TextEmbedder
        from ai_researcher.core_rag.vector_store_manager import VectorStoreManager as VectorStore
        
        embedder = TextEmbedder()
        # Use absolute path to ensure we connect to the existing ChromaDB data
        vector_store = VectorStore(persist_directory="/app/ai_researcher/data/vector_store")
        retriever = Retriever(embedder=embedder, vector_store=vector_store)
        reranker = TextReranker()
        
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

def get_context_manager() -> ContextManager:
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
    
    # Create a user-specific model dispatcher
    user_model_dispatcher = ModelDispatcher(
        user_settings=user_settings,
        semaphore=agent_controller.semaphore,
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
    
    return user_agent_controller

# Import the shared optimization function
from ai_researcher.settings_optimizer import determine_research_parameters as _determine_research_parameters


@router.post("/missions", response_model=MissionResponse)
async def create_mission(
    mission_data: dict,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager),
    controller: AgentController = Depends(get_agent_controller),
    db: Session = Depends(get_db)
):
    """Create a new research mission."""
    try:
        user_request = mission_data.get("request")
        chat_id = mission_data.get("chat_id")
        use_web_search = mission_data.get("use_web_search", True)
        document_group_id = mission_data.get("document_group_id")
        mission_settings_data = mission_data.get("mission_settings")

        if not user_request or not chat_id:
            raise HTTPException(status_code=422, detail="Request and chat_id are required.")

        use_local_rag = document_group_id is not None
        if not use_web_search and not use_local_rag:
            raise HTTPException(status_code=422, detail="At least one information source must be enabled.")

        mission_context = context_mgr.start_mission(user_request, chat_id)
        mission_id = mission_context.mission_id

        # Handle research parameter settings
        user_settings = current_user.settings or {}
        research_params = user_settings.get("research_parameters", {})
        
        final_mission_settings_dict = None

        if research_params.get("auto_optimize_params"):
            logger.info(f"Auto-optimizing research parameters for mission {mission_id}.")
            chat_history = crud.get_chat_messages(db, chat_id=chat_id, user_id=current_user.id)
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
                context_mgr.update_mission_metadata(
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
                context_mgr.log_execution_step(
                    mission_id=mission_id,
                    agent_name="Configuration",
                    action="Applying Research Parameters",
                    output_summary=log_message,
                    status="success"
                )

            except Exception as pydantic_error:
                logger.error(f"Failed to validate/store/log mission settings for {mission_id}: {pydantic_error}", exc_info=True)

        # Store source configuration
        source_config = {
            "tool_selection": {"web_search": use_web_search, "local_rag": use_local_rag},
            "document_group_id": document_group_id
        }
        context_mgr.update_mission_metadata(mission_id, source_config)
        
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
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get the current status of a mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mission not found"
            )
        
        return MissionStatus(
            mission_id=mission_id,
            status=mission_context.status,
            updated_at=mission_context.updated_at,
            error_info=mission_context.error_info
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission status"
        )

@router.get("/missions/{mission_id}/stats", response_model=MissionStats)
async def get_mission_stats(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get mission statistics including cost and token usage."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission stats"
        )

@router.get("/missions/{mission_id}/plan", response_model=MissionPlan)
async def get_mission_plan(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get the research plan for a mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission plan"
        )

@router.get("/missions/{mission_id}/notes")
async def get_mission_notes(
    mission_id: str,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get notes for a given mission with pagination, transformed for frontend consumption."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission notes"
        )

@router.get("/missions/{mission_id}/logs", response_model=MissionLogs)
async def get_mission_logs(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager),
    db: Session = Depends(get_db)
):
    """Get all execution logs for a given mission, merging database and in-memory logs."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mission not found"
            )
        
        # Import document service for filename mapping
        from services.document_service import document_service
        
        # Get logs from database (rich metadata)
        db_logs = crud.get_mission_execution_logs(db, mission_id, current_user.id)
        
        # Get logs from in-memory (simple messages)
        memory_logs = mission_context.execution_log
        
        logger.info(f"Retrieved {len(db_logs)} logs from DB, {len(memory_logs)} from memory for mission {mission_id}")
        
        # Create a dictionary to store merged logs by timestamp
        merged_logs = {}
        
        # Process database logs first (they have rich metadata)
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
            
            # Use timestamp as key for merging (normalize timezone differences)
            timestamp_key = db_log.timestamp.replace(microsecond=0).isoformat() if hasattr(db_log.timestamp, 'replace') else str(db_log.timestamp)
            merged_logs[timestamp_key] = log_entry
        
        # Process in-memory logs (add any that aren't in database)
        for memory_log in memory_logs:
            # Normalize timestamp for comparison
            if hasattr(memory_log.timestamp, 'replace'):
                timestamp_key = memory_log.timestamp.replace(microsecond=0).isoformat()
            else:
                timestamp_key = str(memory_log.timestamp)
            
            # Only add if not already in merged_logs from database
            if timestamp_key not in merged_logs:
                # Replace document codes in the action text
                action_with_filenames = await document_service.replace_document_codes_in_text(memory_log.action)
                
                # Create simple log entry from memory
                log_entry = {
                    "timestamp": memory_log.timestamp.isoformat() if hasattr(memory_log.timestamp, 'isoformat') else str(memory_log.timestamp),
                    "agent_name": memory_log.agent_name,
                    "message": action_with_filenames,
                    "action": action_with_filenames,
                    "input_summary": getattr(memory_log, 'input_summary', None),
                    "output_summary": getattr(memory_log, 'output_summary', None),
                    "status": getattr(memory_log, 'status', 'success'),
                    "error_message": getattr(memory_log, 'error_message', None),
                    "full_input": getattr(memory_log, 'full_input', None),
                    "full_output": getattr(memory_log, 'full_output', None),
                    "model_details": getattr(memory_log, 'model_details', None),
                    "tool_calls": getattr(memory_log, 'tool_calls', None),
                    "file_interactions": getattr(memory_log, 'file_interactions', None),
                    "cost": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "native_tokens": None
                }
                merged_logs[timestamp_key] = log_entry
        
        # Sort logs by timestamp and convert to list
        sorted_logs = sorted(merged_logs.values(), key=lambda x: x["timestamp"])
        
        logger.info(f"Returning {len(sorted_logs)} merged logs for mission {mission_id}")
        
        return MissionLogs(
            mission_id=mission_id,
            logs=sorted_logs
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get mission logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission logs"
        )

@router.get("/missions/{mission_id}/draft", response_model=MissionDraft)
async def get_mission_draft(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get the current draft of the report for a mission."""
    try:
        draft = context_mgr.get_mission_draft(mission_id)
        return MissionDraft(mission_id=mission_id, draft=draft)
    except Exception as e:
        logger.error(f"Failed to get mission draft: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission draft"
        )

@router.get("/missions/{mission_id}/report", response_model=MissionReport)
async def get_mission_report(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get the final research report for a completed mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission report"
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mission not found"
            )

        if mission_context.status != "stopped":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
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
                        "timestamp": update_data.timestamp.isoformat() if hasattr(update_data.timestamp, 'isoformat') else str(update_data.timestamp),
                        "agent_name": update_data.agent_name,
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

        # Resume mission execution in a separate thread from the pool
        loop = asyncio.get_event_loop()
        thread_pool: ThreadPoolExecutor = request.app.state.thread_pool
        
        def run_mission_in_thread():
            """Sets user context and runs the mission."""
            set_current_user(current_user)
            asyncio.run(controller.run_mission(
                mission_id,
                log_queue=log_queue,
                update_callback=websocket_update_callback
            ))

        loop.run_in_executor(thread_pool, run_mission_in_thread)
        
        return {"message": "Mission execution resumed", "mission_id": mission_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume mission execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mission not found"
            )

        controller.stop_mission(mission_id)
        
        return {"message": "Mission execution stopped", "mission_id": mission_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop mission execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop mission execution"
        )

@router.post("/missions/{mission_id}/start")
async def start_mission_execution(
    mission_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager),
    controller: AgentController = Depends(get_user_specific_agent_controller),
    db: Session = Depends(get_db)
):
    """
    Start or resume the execution of a mission.
    This endpoint is the single point of entry for initiating research.
    """
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")

        # Allow starting from 'pending' or 'stopped' states
        if mission_context.status not in ["pending", "stopped", "planning"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mission cannot be started. Current status: {mission_context.status}"
            )

        # --- Self-Sufficiency Check ---
        # If final_questions are not set, generate them now. This makes the start button reliable.
        if not mission_context.metadata.get("final_questions"):
            logger.info(f"Final questions not found for mission {mission_id}. Generating them now...")
            
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
                context_mgr.update_mission_metadata(mission_id, {"final_questions": questions})
                logger.info(f"Generated and stored {len(questions)} questions for mission {mission_id}.")
            else:
                # If question generation fails, create a default set to ensure the mission can proceed
                logger.warning(f"Failed to generate questions for mission {mission_id}. Using default questions.")
                default_questions = [
                    f"What is {mission_context.user_request}?",
                    f"What are the key components or aspects of {mission_context.user_request}?",
                    f"What is the significance or impact of {mission_context.user_request}?"
                ]
                context_mgr.update_mission_metadata(mission_id, {"final_questions": default_questions})
        
        # Set default tool selection if not present
        if not mission_context.metadata.get("tool_selection"):
            context_mgr.update_mission_metadata(mission_id, {"tool_selection": {"local_rag": True, "web_search": True}})

        # Apply auto-optimization logic with comprehensive logging
        try:
            # Get chat_id from mission metadata
            chat_id = mission_context.metadata.get("chat_id") if mission_context.metadata else None
            if not chat_id:
                logger.warning(f"No chat_id found in mission metadata for mission {mission_id}. Skipping auto-optimization.")
                return {"message": "Mission execution started", "mission_id": mission_id}
            
            chat_history = crud.get_chat_messages(db, chat_id=chat_id, user_id=current_user.id)
            
            # Use the shared auto-optimization function for consistent behavior and logging
            from ai_researcher.settings_optimizer import apply_auto_optimization
            await apply_auto_optimization(
                mission_id=mission_id,
                current_user=current_user,
                context_mgr=context_mgr,
                controller=controller,
                chat_history=chat_history
            )
            
        except Exception as e:
            logger.warning(f"Failed to apply auto-optimization for mission {mission_id}: {e}", exc_info=True)

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
                        "timestamp": update_data.timestamp.isoformat() if hasattr(update_data.timestamp, 'isoformat') else str(update_data.timestamp),
                        "agent_name": update_data.agent_name,
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

        # Start mission execution in a separate thread from the pool
        loop = asyncio.get_event_loop()
        thread_pool: ThreadPoolExecutor = request.app.state.thread_pool

        def run_mission_in_thread():
            """Sets user context and runs the mission."""
            set_current_user(current_user)
            asyncio.run(controller.run_mission(
                mission_id,
                log_queue=log_queue,
                update_callback=websocket_update_callback
            ))

        loop.run_in_executor(thread_pool, run_mission_in_thread)
        
        logger.info(f"Started mission execution for {mission_id} in a background thread")
        return {"message": "Mission execution started", "mission_id": mission_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start mission execution for {mission_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start mission execution"
        )

@router.get("/missions/{mission_id}/context", response_model=MissionContextResponse)
async def get_mission_context_data(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get the context data for a mission, including goals and scratchpads."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission context data"
        )

@router.get("/missions/{mission_id}/settings", response_model=MissionSettingsResponse)
async def get_mission_settings(
    mission_id: str,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Get the settings for a mission, including effective settings after fallback."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mission settings"
        )

@router.post("/missions/{mission_id}/settings", response_model=MissionSettingsResponse)
async def update_mission_settings(
    mission_id: str,
    settings_update: MissionSettingsUpdate,
    current_user: User = Depends(get_current_user_from_cookie),
    context_mgr: ContextManager = Depends(get_context_manager)
):
    """Update the settings for a mission."""
    try:
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mission not found"
            )
        
        # Convert settings to dict, excluding None values
        settings_dict = settings_update.settings.model_dump(exclude_none=True)
        
        # Update mission metadata with new settings
        context_mgr.update_mission_metadata(mission_id, {"mission_settings": settings_dict})
        
        logger.info(f"Updated mission settings for {mission_id}: {settings_dict}")
        
        # Return the updated settings response
        return await get_mission_settings(mission_id, current_user, context_mgr)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update mission settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
