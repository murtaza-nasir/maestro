import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal, Callable, Set 
from pydantic import BaseModel, Field, ValidationError
import datetime
import logging
import queue 
import time 
import json 
import asyncio
from sqlalchemy.orm import Session
from database import crud, models

# Use absolute imports starting from the top-level package 'ai_researcher'
from ai_researcher.config import get_current_time
from ai_researcher import config
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, PlanStep, ReportSection # <-- Import ReportSection
from ai_researcher.agentic_layer.schemas.research import ResearchResultResponse
from ai_researcher.agentic_layer.schemas.notes import Note # <-- Import Note schema
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry 
from ai_researcher.agentic_layer.schemas.goal import GoalEntry

# Import WebSocket update functions
from api.websockets import (
    send_plan_update, send_notes_update, send_draft_update,
    send_context_update, send_goal_pad_update, send_thought_pad_update, send_scratchpad_update
)
from api.utils import _make_serializable

logger = logging.getLogger(__name__)


MissionStatus = Literal["planning", "running", "completed", "failed", "paused", "stopped"]

# --- New Schema for Execution Log ---
class ExecutionLogEntry(BaseModel):
    """Represents a single step in the mission execution log."""
    timestamp: datetime.datetime = Field(default_factory=get_current_time)
    agent_name: str
    action: str # e.g., "Generating Plan", "Running Research", "Writing Section"
    input_summary: Optional[str] = None # Brief description of input
    output_summary: Optional[str] = None # Brief description of output/result
    status: Literal["success", "failure", "warning", "running"] = "success" # Added "running"
    error_message: Optional[str] = None
    # --- Added fields for detailed logging ---
    full_input: Optional[Any] = Field(None, description="Detailed input data (e.g., dict, list, long text)")
    full_output: Optional[Any] = Field(None, description="Detailed output data")
    model_details: Optional[Dict[str, Any]] = Field(None, description="Details about the LLM call (model, provider, duration, etc.)")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Details about tool calls made during the step")
    file_interactions: Optional[List[str]] = Field(None, description="Record of files read/written during the step")
    # --- End added fields ---

# --- Updated Mission Context ---
class MissionContext(BaseModel):
    """Holds the state for a single research mission."""
    mission_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_request: str
    status: MissionStatus = "planning"
    plan: Optional[SimplifiedPlan] = None
    step_results: Dict[str, ResearchResultResponse] = Field(default_factory=dict)
    notes: List[Note] = Field(default_factory=list, description="List of notes gathered during research.")
    report_content: Dict[str, str] = Field(default_factory=dict)
    final_report: Optional[str] = None
    message_history: List[Dict[str, str]] = Field(default_factory=list)
    created_at: datetime.datetime = Field(default_factory=get_current_time)
    updated_at: datetime.datetime = Field(default_factory=get_current_time)
    error_info: Optional[str] = None # Store error details if mission fails
    agent_scratchpad: Optional[str] = Field(None, description="Dynamic scratchpad for high-level agent context and insights.") # <-- Add scratchpad
    execution_log: List[ExecutionLogEntry] = Field(default_factory=list, description="Log of agent actions and results.")
    goal_pad: List[GoalEntry] = Field(default_factory=list, description="Persistent list of research goals and guiding thoughts.") # <-- ADDED goal_pad
    thought_pad: List[ThoughtEntry] = Field(default_factory=list, description="Working memory holding recent thoughts and focus points.") # <-- ADDED thought_pad
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata for the mission (e.g., questions, refinements).")

    def update_timestamp(self):
        self.updated_at = get_current_time()

class ContextManager:
    """
    Manages the state and history for multiple research missions.
    Stores context in memory and persists it to the database.
    """
    def __init__(self, db_session_factory: Callable[[], Session]):
        self._missions: Dict[str, MissionContext] = {}
        self.db_session_factory = db_session_factory
        # --- NEW: State for Tracking LLM Usage (Moved from AgentController) ---
        # Stores cumulative stats per mission
        self.mission_stats: Dict[str, Dict[str, float]] = {} # mission_id -> {"total_cost": float, "total_prompt_tokens": float, "total_completion_tokens": float, "total_native_tokens": float, "total_web_search_calls": int}
        self.tracked_calls: Set[str] = set() # Track call IDs to prevent double counting
        # --- End NEW State ---
        
        logger.info("ContextManager initialized with database persistence.")
        self._load_all_missions_from_db()

    def _load_all_missions_from_db(self):
        """Loads all existing missions from the database into the in-memory cache on startup."""
        db = self.db_session_factory()
        try:
            all_db_missions = crud.get_all_missions(db)
            loaded_count = 0
            for db_mission in all_db_missions:
                try:
                    # The mission_context from DB is a dict, convert it back to Pydantic model
                    if db_mission.mission_context:
                        # Migrate notes to add missing timestamp fields before validation
                        migrated_context = self._migrate_mission_context(db_mission.mission_context)
                        mission_context_model = MissionContext(**migrated_context)
                        self._missions[db_mission.id] = mission_context_model
                        loaded_count += 1
                    else:
                        # Handle cases where a mission might exist in DB but with no context
                        # This could be a fallback or recovery mechanism
                        logger.warning(f"Mission '{db_mission.id}' found in DB but has no context. Creating a default.")
                        mission_context_model = MissionContext(
                            mission_id=db_mission.id,
                            user_request=db_mission.user_request,
                            status=db_mission.status,
                            created_at=db_mission.created_at,
                            updated_at=db_mission.updated_at,
                            error_info=db_mission.error_info
                        )
                        self._missions[db_mission.id] = mission_context_model
                        loaded_count += 1

                except ValidationError as e:
                    logger.error(f"Pydantic validation error loading mission '{db_mission.id}' from DB: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Unexpected error loading mission '{db_mission.id}' from DB: {e}", exc_info=True)
            
            logger.info(f"Successfully loaded {loaded_count} missions from the database into memory.")

        finally:
            db.close()

    def _migrate_mission_context(self, context_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrates mission context data to ensure compatibility with current schema.
        Adds missing timestamp fields to notes and handles other schema changes.
        """
        migrated_context = context_dict.copy()
        
        # Migrate notes to add missing timestamp fields
        if 'notes' in migrated_context and isinstance(migrated_context['notes'], list):
            current_time = get_current_time()
            migrated_notes = []
            
            for note_data in migrated_context['notes']:
                if isinstance(note_data, dict):
                    # Add missing timestamp fields if they don't exist
                    if 'created_at' not in note_data:
                        note_data['created_at'] = current_time
                    if 'updated_at' not in note_data:
                        note_data['updated_at'] = current_time
                    migrated_notes.append(note_data)
                else:
                    # Skip invalid note data
                    logger.warning(f"Skipping invalid note data during migration: {note_data}")
            
            migrated_context['notes'] = migrated_notes
            # logger.info(f"Migrated {len(migrated_notes)} notes with timestamp fields")
        
        return migrated_context

    # --- Public Methods ---

    def start_mission(self, user_request: str, chat_id: str) -> MissionContext:
        """Creates and stores context for a new mission."""
        """Creates a new mission, stores it in the database, and adds it to the in-memory cache."""
        mission = MissionContext(user_request=user_request)
        mission.metadata["chat_id"] = chat_id

        self._missions[mission.mission_id] = mission
        
        db = self.db_session_factory()
        try:
            crud.create_mission(
                db=db,
                mission_id=mission.mission_id,
                chat_id=chat_id,
                user_request=user_request,
                mission_context=mission.model_dump(mode='json')
            )
            logger.info(f"Started and saved new mission: {mission.mission_id} for chat: {chat_id}")
        except Exception as e:
            logger.error(f"Database error creating mission {mission.mission_id}: {e}", exc_info=True)
            # If DB write fails, remove from in-memory cache to avoid inconsistent state
            del self._missions[mission.mission_id]
            raise  # Re-raise the exception to be handled by the caller
        finally:
            db.close()
            
        return mission

    def get_mission_context(self, mission_id: str) -> Optional[MissionContext]:
        """
        Retrieves the context for a given mission ID primarily from the in-memory store.
        Loading from disk should happen explicitly, e.g., during initialization if needed.
        """
        """Retrieves the context for a given mission ID from the in-memory cache."""
        mission = self._missions.get(mission_id)
        if not mission:
            logger.warning(f"Mission context not found in memory for ID: {mission_id}. Returning None.")
        return mission

    def update_mission_status(self, mission_id: str, status: MissionStatus, error_info: Optional[str] = None):
        """Updates the status of a mission in memory and in the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.status = status
            mission.error_info = error_info if status == "failed" else None
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_status(db, mission_id=mission_id, status=status, error_info=error_info)
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.info(f"Updated mission '{mission_id}' status to '{status}' in DB.")
            except Exception as e:
                logger.error(f"Database error updating mission status for {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot update status for non-existent mission ID: {mission_id}")

    def store_plan(self, mission_id: str, plan: SimplifiedPlan):
        """Stores the generated plan for a mission in memory and persists the context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.plan = plan
            mission.status = "running"  # Typically moves to running after planning
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                # Persist the entire updated context
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                # Also update the status explicitly in the main mission table
                crud.update_mission_status(db, mission_id=mission_id, status="running")
                logger.info(f"Stored plan and updated context for mission '{mission_id}' in DB.")
                
                # Send WebSocket update for plan
                try:
                    plan_dict = plan.model_dump() if hasattr(plan, 'model_dump') else plan
                    asyncio.create_task(send_plan_update(mission_id, plan_dict, "update"))
                    logger.info(f"Sent plan update via WebSocket for mission '{mission_id}'.")
                except Exception as ws_error:
                    logger.error(f"Failed to send plan update via WebSocket for mission {mission_id}: {ws_error}")
            except Exception as e:
                logger.error(f"Database error storing plan for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot store plan for non-existent mission ID: {mission_id}")

    def store_step_result(self, mission_id: str, result: ResearchResultResponse):
        """Stores the result of a plan step and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            step_id = result.step_id
            mission.step_results[step_id] = result
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.info(f"Stored result for step '{step_id}' in mission '{mission_id}' and updated DB.")
            except Exception as e:
                logger.error(f"Database error storing step result for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot store step result for non-existent mission ID: {mission_id}")

    def get_step_results(self, mission_id: str, step_ids: Optional[List[str]] = None) -> Dict[str, ResearchResultResponse]:
        """Retrieves results for specific steps or all steps if step_ids is None."""
        mission = self.get_mission_context(mission_id)
        if not mission:
            return {}
        if step_ids:
            return {sid: res for sid, res in mission.step_results.items() if sid in step_ids}
        else:
            return mission.step_results # Return all results

    def store_report_section(self, mission_id: str, section_id: str, content: str):
        """Stores report section content and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.report_content[section_id] = content
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.info(f"Stored report section '{section_id}' for mission '{mission_id}' and updated DB.")
                
                # Send WebSocket update for draft
                try:
                    current_draft = self.build_draft_from_context(mission_id)
                    if current_draft:
                        asyncio.create_task(send_draft_update(mission_id, current_draft, "update"))
                        logger.info(f"Sent draft update via WebSocket for mission '{mission_id}'.")
                except Exception as ws_error:
                    logger.error(f"Failed to send draft update via WebSocket for mission {mission_id}: {ws_error}")
            except Exception as e:
                logger.error(f"Database error storing report section for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot store report section for non-existent mission ID: {mission_id}")

    def store_final_report(self, mission_id: str, report_text: str):
        """Stores the final report, updates status, and persists the context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.final_report = report_text
            mission.status = "completed"  # Mark as completed
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_status(db, mission_id=mission_id, status="completed")
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.info(f"Stored final report and set status to 'completed' for mission '{mission_id}' in DB.")
                
                # Send WebSocket update for final report
                try:
                    asyncio.create_task(send_draft_update(mission_id, report_text, "report"))
                    logger.info(f"Sent final report update via WebSocket for mission '{mission_id}'.")
                except Exception as ws_error:
                    logger.error(f"Failed to send final report update via WebSocket for mission {mission_id}: {ws_error}")
            except Exception as e:
                logger.error(f"Database error storing final report for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot store final report for non-existent mission ID: {mission_id}")

    # Add methods for message history if needed
    def add_message_to_history(self, mission_id: str, message: Dict[str, str]):
         mission = self.get_mission_context(mission_id)
         if mission:
              mission.message_history.append(message)
              mission.update_timestamp()
              # Don't save after every message for performance, maybe save periodically or on demand
              # self._save_mission(mission_id)

    # --- Note Management Methods ---

    def add_note(self, mission_id: str, note: Note):
        """Adds a single note and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.notes.append(note)
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.debug(f"Added note {note.note_id} to mission {mission_id} and updated DB.")
                
                # Send WebSocket update for note
                try:
                    # Import and use the transformation function for consistency
                    from api.missions import transform_note_for_frontend
                    note_dict = transform_note_for_frontend(note)
                    asyncio.create_task(send_notes_update(mission_id, [note_dict], "append"))
                    logger.info(f"Sent note update via WebSocket for mission '{mission_id}' (1 note).")
                except Exception as ws_error:
                    logger.error(f"Failed to send note update via WebSocket for mission {mission_id}: {ws_error}")
            except Exception as e:
                logger.error(f"Database error adding note for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot add note for non-existent mission ID: {mission_id}")

    def add_notes(self, mission_id: str, notes: List[Note]):
        """Adds a list of notes and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.notes.extend(notes)
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.info(f"Added {len(notes)} notes to mission {mission_id} and updated DB.")
                
                # Send WebSocket update for notes
                try:
                    # Import and use the transformation function for consistency
                    from api.missions import transform_note_for_frontend
                    notes_list = [transform_note_for_frontend(note) for note in notes]
                    asyncio.create_task(send_notes_update(mission_id, notes_list, "append"))
                    logger.info(f"Sent notes update via WebSocket for mission '{mission_id}' ({len(notes)} notes).")
                except Exception as ws_error:
                    logger.error(f"Failed to send notes update via WebSocket for mission {mission_id}: {ws_error}")
            except Exception as e:
                logger.error(f"Database error adding notes for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot add notes for non-existent mission ID: {mission_id}")

    def get_notes(self, mission_id: str) -> List[Note]:
        """Retrieves all notes for a given mission ID."""
        mission = self.get_mission_context(mission_id)
        if mission:
            return mission.notes
        else:
            logger.warning(f"Cannot get notes for non-existent mission ID: {mission_id}")
            return []

    def remove_notes(self, mission_id: str, note_ids_to_remove: List[str]):
        """Removes notes and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            initial_count = len(mission.notes)
            ids_to_remove_set = set(note_ids_to_remove)
            mission.notes = [note for note in mission.notes if note.note_id not in ids_to_remove_set]
            final_count = len(mission.notes)
            removed_count = initial_count - final_count
            
            if removed_count > 0:
                mission.update_timestamp()
                db = self.db_session_factory()
                try:
                    crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                    logger.info(f"Removed {removed_count} notes from mission {mission_id} and updated DB.")
                except Exception as e:
                    logger.error(f"Database error removing notes for mission {mission_id}: {e}", exc_info=True)
                finally:
                    db.close()
            else:
                logger.warning(f"Attempted to remove notes, but none of the specified IDs were found in mission {mission_id}. IDs: {note_ids_to_remove}")
        else:
            logger.error(f"Cannot remove notes for non-existent mission ID: {mission_id}")

    # --- Scratchpad Management Methods ---

    def update_scratchpad(self, mission_id: str, scratchpad_content: Optional[str]):
        """Updates the agent scratchpad and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            if mission.agent_scratchpad != scratchpad_content:  # Only update if changed
                mission.agent_scratchpad = scratchpad_content
                mission.update_timestamp()
                
                db = self.db_session_factory()
                try:
                    crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                    logger.debug(f"Updated scratchpad for mission {mission_id} and updated DB.")
                    
                    # Send WebSocket update for scratchpad
                    try:
                        asyncio.create_task(send_scratchpad_update(mission_id, scratchpad_content or "", "update"))
                        logger.info(f"Sent scratchpad update via WebSocket for mission '{mission_id}'.")
                    except Exception as ws_error:
                        logger.error(f"Failed to send scratchpad update via WebSocket for mission {mission_id}: {ws_error}")
                except Exception as e:
                    logger.error(f"Database error updating scratchpad for mission {mission_id}: {e}", exc_info=True)
                finally:
                    db.close()
        else:
            logger.error(f"Cannot update scratchpad for non-existent mission ID: {mission_id}")

    def get_scratchpad(self, mission_id: str) -> Optional[str]:
        """Retrieves the current agent scratchpad content for a mission."""
        mission = self.get_mission_context(mission_id)
        if mission:
            return mission.agent_scratchpad
        else:
            logger.warning(f"Cannot get scratchpad for non-existent mission ID: {mission_id}")
            return None
    
    def get_plan(self, mission_id: str) -> Optional[SimplifiedPlan]:
        """Retrieves the current plan for a mission."""
        mission = self.get_mission_context(mission_id)
        if mission:
            return mission.plan
        else:
            logger.warning(f"Cannot get plan for non-existent mission ID: {mission_id}")
            return None
            
    def update_mission_metadata(self, mission_id: str, metadata_update: Dict[str, Any]):
        """Updates mission metadata and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            mission.metadata.update(metadata_update)
            mission.update_timestamp()
            
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                logger.debug(f"Updated metadata for mission {mission_id} with keys: {list(metadata_update.keys())} and updated DB.")
            except Exception as e:
                logger.error(f"Database error updating metadata for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.error(f"Cannot update metadata for non-existent mission ID: {mission_id}")

    # --- New Method for Logging Execution Steps ---
    def log_execution_step(
        self,
        mission_id: str,
        agent_name: str,
        action: str,
        input_summary: Optional[str] = None,
        output_summary: Optional[str] = None,
        status: Literal["success", "failure", "warning", "running"] = "success", # <-- Updated status literal
        error_message: Optional[str] = None,
        # --- Added parameters for detailed logging ---
        full_input: Optional[Any] = None,
        full_output: Optional[Any] = None,
        model_details: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        file_interactions: Optional[List[str]] = None,
        # --- End added parameters ---
        log_queue: Optional[queue.Queue] = None, # <-- Add queue parameter
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None # <-- Modify callback signature
    ):
        """Logs a step in the mission execution process and optionally calls a callback with the queue."""
        mission = self.get_mission_context(mission_id)
        if mission:
            # --- Make detailed fields serializable BEFORE creating ExecutionLogEntry ---
            serializable_input = _make_serializable(full_input)
            serializable_output = _make_serializable(full_output)
            serializable_model_details = _make_serializable(model_details)
            serializable_tool_calls = _make_serializable(tool_calls)
            # file_interactions is already List[str], should be fine
            # --- End serialization step ---

            try: # Add try-except around ExecutionLogEntry creation for robustness
                log_entry = ExecutionLogEntry(
                    agent_name=agent_name,
                    action=action,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    status=status,
                    error_message=error_message,
                    # --- Pass SERIALIZED detailed fields ---
                    full_input=serializable_input,
                    full_output=serializable_output,
                    model_details=serializable_model_details,
                    tool_calls=serializable_tool_calls,
                    file_interactions=file_interactions
                    # --- End detailed fields ---
                )
            except ValidationError as ve:
                 logger.error(f"Pydantic validation error creating ExecutionLogEntry for mission {mission_id}: {ve}", exc_info=True)
                 # Fallback: Create a minimal log entry
                 log_entry = ExecutionLogEntry(
                     agent_name=agent_name,
                     action=action,
                     input_summary=input_summary,
                     output_summary=output_summary,
                     status="failure", # Mark as failure due to logging issue
                     error_message=f"Failed to create detailed log entry: {ve}",
                 )
            except Exception as e:
                 logger.error(f"Unexpected error creating ExecutionLogEntry for mission {mission_id}: {e}", exc_info=True)
                 # Fallback: Create a minimal log entry
                 log_entry = ExecutionLogEntry(
                     agent_name=agent_name,
                     action=action,
                     input_summary=input_summary,
                     output_summary=output_summary,
                     status="failure", # Mark as failure due to logging issue
                     error_message=f"Unexpected error creating log entry: {e}",
                 )


            mission.execution_log.append(log_entry)
            mission.update_timestamp()
            logger.info(f"Logged execution step for mission {mission_id}: Agent={agent_name}, Action={action}, Status={status}")

            # Persist the log entry to the database using the new execution logs table
            db = self.db_session_factory()
            try:
                # Get the mission without user constraint to get the user_id
                mission_db = db.query(models.Mission).filter(models.Mission.id == mission_id).first()
                if mission_db:
                    # Extract cost and token information from model_details
                    cost = None
                    prompt_tokens = None
                    completion_tokens = None
                    native_tokens = None
                    
                    if log_entry.model_details:
                        cost = log_entry.model_details.get('cost')
                        prompt_tokens = log_entry.model_details.get('prompt_tokens')
                        completion_tokens = log_entry.model_details.get('completion_tokens')
                        native_tokens = log_entry.model_details.get('native_total_tokens')
                        
                        # Also try alternative field names that might be used
                        if cost is None:
                            cost = log_entry.model_details.get('total_cost')
                        if native_tokens is None:
                            native_tokens = log_entry.model_details.get('total_tokens')
                    
                    # Debug logging to see what we're actually saving
                    logger.debug(f"Saving execution log to DB for mission {mission_id}:")
                    logger.debug(f"  - cost: {cost} (from model_details: {log_entry.model_details.get('cost') if log_entry.model_details else 'N/A'})")
                    logger.debug(f"  - prompt_tokens: {prompt_tokens}")
                    logger.debug(f"  - completion_tokens: {completion_tokens}")
                    logger.debug(f"  - native_tokens: {native_tokens}")
                    logger.debug(f"  - model_details keys: {list(log_entry.model_details.keys()) if log_entry.model_details else 'None'}")
                    
                    # Create execution log entry in database
                    crud.create_execution_log(
                        db=db,
                        mission_id=mission_id,
                        timestamp=log_entry.timestamp,
                        agent_name=log_entry.agent_name,
                        action=log_entry.action,
                        input_summary=log_entry.input_summary,
                        output_summary=log_entry.output_summary,
                        status=log_entry.status,
                        error_message=log_entry.error_message,
                        full_input=log_entry.full_input,
                        full_output=log_entry.full_output,
                        model_details=log_entry.model_details,
                        tool_calls=log_entry.tool_calls,
                        file_interactions=log_entry.file_interactions,
                        cost=cost,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        native_tokens=native_tokens
                    )
                    logger.debug(f"Persisted execution log entry to database for mission {mission_id}")
                else:
                    logger.error(f"Could not find mission {mission_id} in database to persist execution log")
                
                # Also update the mission context (for backward compatibility)
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
            except Exception as e:
                logger.error(f"Database error saving execution log for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()

            # Call the callback function if provided, passing the queue and log entry
            if update_callback and log_queue is not None:
                try:
                    logger.debug(f"Sending log entry '{log_entry.action}' for agent '{log_entry.agent_name}' to frontend via WebSocket.")
                    # Pass a deep copy to avoid potential issues if the callback modifies the entry
                    update_callback(log_queue, log_entry.model_copy(deep=True))
                except Exception as cb_e:
                    logger.error(f"Error executing update callback for mission {mission_id}: {cb_e}", exc_info=True)
            elif update_callback and log_queue is None:
                 logger.warning(f"log_execution_step called with update_callback but no log_queue for mission {mission_id}. Callback skipped.")
        else:
            logger.error(f"Cannot log execution step for non-existent mission ID: {mission_id}")


    # --- Goal Pad Management Methods ---

    def add_goal(self, mission_id: str, text: str, source_agent: Optional[str] = None) -> Optional[str]:
        """Adds a new goal and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            try:
                new_goal = GoalEntry(text=text, source_agent=source_agent)
                mission.goal_pad.append(new_goal)
                mission.update_timestamp()
                
                db = self.db_session_factory()
                try:
                    crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                    logger.info(f"Added goal '{new_goal.goal_id}' to mission {mission_id} and updated DB.")
                    
                    # Send WebSocket update for goal pad
                    try:
                        goals_list = [goal.model_dump() for goal in mission.goal_pad]
                        asyncio.create_task(send_goal_pad_update(mission_id, goals_list, "update"))
                        logger.info(f"Sent goal pad update via WebSocket for mission '{mission_id}'.")
                    except Exception as ws_error:
                        logger.error(f"Failed to send goal pad update via WebSocket for mission {mission_id}: {ws_error}")
                except Exception as e:
                    logger.error(f"Database error adding goal for mission {mission_id}: {e}", exc_info=True)
                finally:
                    db.close()

                return new_goal.goal_id
            except ValidationError as e:
                logger.error(f"Validation error creating GoalEntry for mission {mission_id}: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error adding goal for mission {mission_id}: {e}", exc_info=True)
                return None
        else:
            logger.error(f"Cannot add goal for non-existent mission ID: {mission_id}")
            return None

    def update_goal_status(self, mission_id: str, goal_id: str, status: Literal["active", "addressed", "obsolete"]) -> bool:
        """Updates a goal's status and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if not mission:
            logger.error(f"Cannot update goal status for non-existent mission ID: {mission_id}")
            return False

        goal_found = False
        should_update_db = False
        for goal in mission.goal_pad:
            if goal.goal_id == goal_id:
                if goal.status != status:
                    goal.status = status
                    mission.update_timestamp()
                    should_update_db = True
                    logger.info(f"Updated status of goal '{goal_id}' to '{status}' for mission {mission_id}.")
                else:
                    logger.debug(f"Goal '{goal_id}' status already '{status}' for mission {mission_id}. No update needed.")
                goal_found = True
                break
        
        if not goal_found:
            logger.warning(f"Goal '{goal_id}' not found in goal_pad for mission {mission_id}. Cannot update status.")
            return False

        if should_update_db:
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
            except Exception as e:
                logger.error(f"Database error updating goal status for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()
        
        return True

    def edit_goal_text(self, mission_id: str, goal_id: str, new_text: str) -> bool:
        """Updates a goal's text and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if not mission:
            logger.error(f"Cannot update goal text for non-existent mission ID: {mission_id}")
            return False

        goal_found = False
        should_update_db = False
        for goal in mission.goal_pad:
            if goal.goal_id == goal_id:
                if goal.text != new_text:
                    goal.text = new_text
                    mission.update_timestamp()
                    should_update_db = True
                    logger.info(f"Updated text of goal '{goal_id}' for mission {mission_id}.")
                else:
                    logger.debug(f"Goal '{goal_id}' text unchanged for mission {mission_id}. No update needed.")
                goal_found = True
                break

        if not goal_found:
            logger.warning(f"Goal '{goal_id}' not found in goal_pad for mission {mission_id}. Cannot update text.")
            return False

        if should_update_db:
            db = self.db_session_factory()
            try:
                crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
            except Exception as e:
                logger.error(f"Database error editing goal text for mission {mission_id}: {e}", exc_info=True)
            finally:
                db.close()

        return True

    def get_goal_pad(self, mission_id: str) -> List[GoalEntry]:
        """Retrieves the full goal pad for a given mission ID."""
        mission = self.get_mission_context(mission_id)
        if mission:
            return mission.goal_pad
        else:
            logger.warning(f"Cannot get goal_pad for non-existent mission ID: {mission_id}")
            return []

    def get_active_goals(self, mission_id: str) -> List[GoalEntry]:
        """Retrieves only the active goals from the goal pad for a given mission ID."""
        mission = self.get_mission_context(mission_id)
        if mission:
            return [goal for goal in mission.goal_pad if goal.status == "active"]
        else:
            logger.warning(f"Cannot get active goals for non-existent mission ID: {mission_id}")
            return []

    # --- End Goal Pad Management Methods ---


    # --- Thought Pad Management Methods ---

    def add_thought(self, mission_id: str, agent_name: str, content: str) -> Optional[str]:
        """Adds a new thought and persists the updated context to the database."""
        mission = self.get_mission_context(mission_id)
        if mission:
            try:
                new_thought = ThoughtEntry(agent_name=agent_name, content=content)
                mission.thought_pad.append(new_thought)
                mission.update_timestamp()

                db = self.db_session_factory()
                try:
                    crud.update_mission_context(db, mission_id=mission_id, mission_context=mission.model_dump(mode='json'))
                    logger.info(f"Added thought '{new_thought.thought_id}' from agent '{agent_name}' to mission {mission_id} and updated DB.")
                    
                    # Send WebSocket update for thought pad
                    try:
                        thoughts_list = [thought.model_dump() for thought in mission.thought_pad]
                        asyncio.create_task(send_thought_pad_update(mission_id, thoughts_list, "update"))
                        logger.info(f"Sent thought pad update via WebSocket for mission '{mission_id}'.")
                    except Exception as ws_error:
                        logger.error(f"Failed to send thought pad update via WebSocket for mission {mission_id}: {ws_error}")
                except Exception as e:
                    logger.error(f"Database error adding thought for mission {mission_id}: {e}", exc_info=True)
                finally:
                    db.close()

                return new_thought.thought_id
            except ValidationError as e:
                logger.error(f"Validation error creating ThoughtEntry for mission {mission_id}: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error adding thought for mission {mission_id}: {e}", exc_info=True)
                return None
        else:
            logger.error(f"Cannot add thought for non-existent mission ID: {mission_id}")
            return None

    def get_recent_thoughts(self, mission_id: str, limit: int = 5) -> List[ThoughtEntry]:
        """Retrieves the most recent thoughts from the thought pad, up to the specified limit."""
        mission = self.get_mission_context(mission_id)
        if mission:
            # Return the last 'limit' thoughts. Slicing handles cases where len < limit.
            return mission.thought_pad[-limit:]
        else:
            logger.warning(f"Cannot get recent thoughts for non-existent mission ID: {mission_id}")
            return []

    # --- End Thought Pad Management Methods ---

    # --- Draft Building Method (Moved from AgentController) ---
    def build_draft_from_context(self, mission_id: str) -> Optional[str]:
        """
        Builds the full draft text from the stored report content, using the plan outline
        for structure and hierarchical numbering. Returns None if prerequisites are missing.
        """
        mission_context = self.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan or not mission_context.report_content:
            logger.error(f"Cannot build draft: Mission context, plan, or report content missing for {mission_id}.")
            return None

        full_draft = ""
        report_outline = mission_context.plan.report_outline
        report_content_map = mission_context.report_content

        # Use recursive function to build draft with hierarchical numbering
        def build_draft_recursive(section_list: List[ReportSection], level: int = 1, prefix: str = ""):
            nonlocal full_draft
            for i, section in enumerate(section_list):
                # Calculate the number for the current section
                current_number = f"{prefix}{i + 1}"
                # Generate the heading markdown
                heading_marker = "#" * level
                # Prepend the number to the title in the heading
                full_draft += f"{heading_marker} {current_number}. {section.title}\n\n"
                # Get the content for the section
                content = report_content_map.get(section.section_id, f"[Content missing for section {section.section_id}]")
                full_draft += f"{content}\n\n"
                # Recursively call for subsections, passing the new prefix
                if section.subsections:
                    build_draft_recursive(section.subsections, level + 1, prefix=f"{current_number}.")

        # Initial call to the recursive function
        build_draft_recursive(report_outline)
        logger.info(f"Successfully built draft for mission {mission_id} from context.")
        return full_draft.strip()

    def get_mission_draft(self, mission_id: str) -> Optional[str]:
        """Retrieves the current draft of the report for a mission."""
        return self.build_draft_from_context(mission_id)
    # --- End Draft Building Method ---


    # --- Stats Management Methods (Moved from AgentController) ---

    def get_mission_stats(self, mission_id: str) -> Dict[str, float]:
        """Retrieves the current statistics for a given mission."""
        return self.mission_stats.get(mission_id, {
            "total_cost": 0.0,
            "total_prompt_tokens": 0.0,
            "total_completion_tokens": 0.0,
            "total_native_tokens": 0.0,
            "total_web_search_calls": 0
        }).copy() # Return a copy

    def increment_web_search_count(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable] = None
    ) -> None:
        """Increments the web search counter for a mission and updates stats."""
        if not mission_id:
            logger.warning("Cannot increment web search count: No mission_id provided")
            return
        web_search_cost = config.WEB_SEARCH_COST_PER_CALL
        model_details = {
            "web_search_count": 1,
            "cost": web_search_cost,
            # Generate a unique ID for this non-LLM stat update
            "call_id": f"web_search_{mission_id}_{time.time()}"
        }
        self.update_mission_stats(mission_id, model_details, log_queue, update_callback, force_update=True)
        logger.debug(f"Incremented web search count and added cost ${web_search_cost:.4f} for mission {mission_id}")

    def update_mission_stats(
        self,
        mission_id: Optional[str],
        model_details: Optional[Dict[str, Any]],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable] = None,
        force_update: bool = False
        ):
        """
        Updates the cumulative cost and token counts for a given mission and sends update via callback.
        Handles both prompt/completion tokens and native_total_tokens for complete tracking.
        Moved from AgentController.
        """
        if not mission_id or not model_details:
            return

        call_id = model_details.get("call_id")
        if not call_id and not force_update:
            timestamp = model_details.get("timestamp", time.time())
            duration = model_details.get("duration_sec", 0)
            model_name = model_details.get("model_name", "unknown")
            call_id = f"{model_name}_{timestamp}_{duration}"
            model_details["call_id"] = call_id

        if not force_update and call_id in self.tracked_calls:
            logger.debug(f"Skipping duplicate stats update for call {call_id} in mission {mission_id}")
            return

        if call_id:
            self.tracked_calls.add(call_id)

        cost = model_details.get("cost")
        prompt_tokens = model_details.get("prompt_tokens")
        completion_tokens = model_details.get("completion_tokens")
        native_total_tokens = model_details.get("native_total_tokens")
        web_search_count = model_details.get("web_search_count", 0)

        if cost is None and prompt_tokens is None and completion_tokens is None and native_total_tokens is None and web_search_count == 0:
            return

        stats = self.mission_stats.setdefault(mission_id, {
            "total_cost": 0.0,
            "total_prompt_tokens": 0.0,
            "total_completion_tokens": 0.0,
            "total_native_tokens": 0.0,
            "total_web_search_calls": 0
        })

        cost_increment = float(cost) if cost is not None else 0.0
        prompt_increment = float(prompt_tokens) if prompt_tokens is not None else 0.0
        completion_increment = float(completion_tokens) if completion_tokens is not None else 0.0
        native_increment = float(native_total_tokens) if native_total_tokens is not None else 0.0
        web_search_increment = int(web_search_count)

        stats["total_cost"] += cost_increment
        stats["total_prompt_tokens"] += prompt_increment
        stats["total_completion_tokens"] += completion_increment
        stats["total_web_search_calls"] += web_search_increment

        if native_increment > 0 and prompt_increment == 0 and completion_increment == 0:
            stats["total_native_tokens"] += native_increment
        elif prompt_increment > 0 or completion_increment > 0:
            stats["total_native_tokens"] = stats["total_prompt_tokens"] + stats["total_completion_tokens"]

        logger.debug(
            f"Updated stats for mission {mission_id}: "
            f"Cost +{cost_increment:.6f}, Prompt +{prompt_increment:.0f}, Completion +{completion_increment:.0f}, "
            f"Native +{native_increment:.0f}, Web Searches +{web_search_increment}. "
            f"New Total: Cost=${stats['total_cost']:.6f}, Prompt={stats['total_prompt_tokens']:.0f}, "
            f"Completion={stats['total_completion_tokens']:.0f}, Native={stats['total_native_tokens']:.0f}, "
            f"Web Searches={stats['total_web_search_calls']}"
        )

        if log_queue and update_callback and (
            cost_increment > 0 or prompt_increment > 0 or completion_increment > 0 or
            native_increment > 0 or web_search_increment > 0
        ):
            try:
                stats_update_message = {
                    "type": "stats_update",
                    "mission_id": mission_id,
                    "payload": stats.copy() # Send a copy of the current totals
                }
                # Pass only the queue and the message payload, as the callback
                # being invoked here is the 2-argument wrapper in some cases.
                update_callback(log_queue, stats_update_message)
                logger.debug(f"Sent stats_update message to UI for mission {mission_id}")
            except Exception as e:
                logger.error(f"Failed to send stats_update message via callback: {e}", exc_info=True)

    # --- End Stats Management Methods ---
