import logging
from typing import Dict, Any, Optional, List, Type, Callable, Tuple, Awaitable, Set
import asyncio
import queue
from collections import deque

from ai_researcher import config
from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT
from ai_researcher.dynamic_config import get_skip_final_replanning
from ai_researcher.agentic_layer.async_context_manager import AsyncContextManager, MissionContext, ExecutionLogEntry
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry, ToolDefinition
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, PlanStep, ReportSection, SimplifiedPlanResponse
from ai_researcher.agentic_layer.schemas.research import ResearchResultResponse, ResearchFindings
from ai_researcher.agentic_layer.schemas.analysis import RequestAnalysisOutput
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput, SuggestedSubsectionTopic
from ai_researcher.agentic_layer.schemas.writing import WritingReflectionOutput, WritingChangeSuggestion
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry
# AssignedNotes is now imported directly where needed to avoid potential circular dependency issues if moved here.

# Import agents
from ai_researcher.agentic_layer.agents.planning_agent import PlanningAgent
from ai_researcher.agentic_layer.agents.research_agent import ResearchAgent
from ai_researcher.agentic_layer.agents.writing_agent import WritingAgent
from ai_researcher.agentic_layer.agents.reflection_agent import ReflectionAgent
from ai_researcher.agentic_layer.agents.messenger_agent import MessengerAgent
from ai_researcher.agentic_layer.agents.writing_reflection_agent import WritingReflectionAgent
from ai_researcher.agentic_layer.agents.note_assignment_agent import NoteAssignmentAgent

# Import core RAG components
from ai_researcher.core_rag.query_strategist import QueryStrategist
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.core_rag.query_preparer import QueryPreparer

# Import tools
from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
from ai_researcher.agentic_layer.tools.calculator_tool import CalculatorTool
from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
from ai_researcher.agentic_layer.tools.python_tool import PythonTool
from ai_researcher.agentic_layer.tools.file_reader_tool import FileReaderTool
from ai_researcher.agentic_layer.tools.web_page_fetcher_tool import WebPageFetcherTool

from pydantic import BaseModel, Field

# Import managers from the controller package
from ai_researcher.agentic_layer.controller.research_manager import ResearchManager
from ai_researcher.agentic_layer.controller.writing_manager import WritingManager
from ai_researcher.agentic_layer.controller.reflection_manager import ReflectionManager
from ai_researcher.agentic_layer.controller.user_interaction import UserInteractionManager
from ai_researcher.agentic_layer.controller.report_generator import ReportGenerator

logger = logging.getLogger(__name__)

# Import FullNoteAssignments from schemas
from ai_researcher.agentic_layer.schemas.assignments import FullNoteAssignments
# SectionAssignment was incorrect, AssignedNotes is imported below where needed.

# Semaphore Context Manager
class MaybeSemaphore:
    def __init__(self, semaphore: Optional[asyncio.Semaphore]):
        self._semaphore = semaphore

    async def __aenter__(self):
        if self._semaphore:
            await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._semaphore:
            self._semaphore.release()
        return False


async def gather_with_status_check(controller, mission_id: str, *coroutines, return_exceptions: bool = False):
    """
    Custom gather function that checks mission status before running tasks.
    If mission is paused/stopped, cancels all pending tasks.
    
    Args:
        controller: The AgentController instance
        mission_id: The mission ID to check status for
        *coroutines: The coroutines to gather
        return_exceptions: Whether to return exceptions or raise them
    
    Returns:
        Results from gathered coroutines
    """
    # Check mission status before starting
    mission_context = controller.context_manager.get_mission_context(mission_id)
    if mission_context and mission_context.status in ["stopped", "paused"]:
        logger.info(f"Mission {mission_id} is {mission_context.status}, skipping gather operation")
        return []
    
    # Create tasks and register them as subtasks
    tasks = []
    for coro in coroutines:
        task = asyncio.create_task(coro)
        controller.add_mission_subtask(mission_id, task)
        tasks.append(task)
        
        # Add a callback to remove the task when it's done
        task.add_done_callback(lambda t: controller.remove_mission_subtask(mission_id, t))
    
    try:
        # Run the tasks with periodic status checks
        results = []
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        
        # Check if we should cancel pending tasks
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if mission_context and mission_context.status in ["stopped", "paused"]:
            logger.info(f"Mission {mission_id} was {mission_context.status} during gather, cancelling pending tasks")
            for task in pending:
                task.cancel()
            # Wait for cancellation to complete
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        
        # Collect results
        for task in done:
            try:
                result = await task
                results.append(result)
            except Exception as e:
                if return_exceptions:
                    results.append(e)
                else:
                    raise
        
        # If there are still pending tasks, wait for them
        if pending and mission_context.status not in ["stopped", "paused"]:
            pending_results = await asyncio.gather(*pending, return_exceptions=return_exceptions)
            results.extend(pending_results)
        
        return results
    except Exception as e:
        # Cancel any remaining tasks on error
        for task in tasks:
            if not task.done():
                task.cancel()
        raise

class AgentController:
    """
    Orchestrates the research process by managing agents, context, and plan execution.
    This is the main controller class that coordinates all the components.
    """
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        context_manager: AsyncContextManager,
        tool_registry: ToolRegistry,
        retriever: Optional[Retriever],
        reranker: Optional[TextReranker]
    ):
        # Concurrency Limiter
        if config.MAX_CONCURRENT_REQUESTS > 0:
            self.semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)
            logger.debug(f"LLM request concurrency limited to {config.MAX_CONCURRENT_REQUESTS} requests by semaphore.")
        else:
            self.semaphore = None
            logger.info("LLM request concurrency is unlimited.")
        self.maybe_semaphore = MaybeSemaphore(self.semaphore)
        
        # Task registry for tracking running asyncio tasks
        self.mission_tasks: Dict[str, asyncio.Task] = {}  # Main task per mission
        self.mission_subtasks: Dict[str, Set[asyncio.Task]] = {}  # Subtasks per mission

        # Store core components
        self.model_dispatcher = model_dispatcher
        self.context_manager = context_manager
        self.tool_registry = tool_registry
        self.retriever = retriever
        self.reranker = reranker
        # Query components will be initialized per-mission to use user-specific models
        self.query_preparer = None
        self.query_strategist = None
        
        # State for inter-round suggestions
        self.mission_subsection_suggestions: Dict[str, Dict[str, List[SuggestedSubsectionTopic]]] = {}
        
        # Configuration parameters
        self.max_total_depth = config.MAX_TOTAL_DEPTH
        self.max_total_iterations = config.MAX_TOTAL_ITERATIONS
        self.max_research_cycles_per_section = config.MAX_RESEARCH_CYCLES_PER_SECTION

        # Initialize agents
        self.planning_agent = PlanningAgent(self.model_dispatcher, self.tool_registry, controller=self)
        self.research_agent = ResearchAgent(
            self.model_dispatcher,
            self.tool_registry,
            self.query_preparer,
            controller=self
        )
        self.writing_agent = WritingAgent(self.model_dispatcher, controller=self)
        self.reflection_agent = ReflectionAgent(self.model_dispatcher, controller=self)
        self.writing_reflection_agent = WritingReflectionAgent(self.model_dispatcher, controller=self)
        self.note_assignment_agent = NoteAssignmentAgent(self.model_dispatcher, controller=self)
        self.messenger_agent = MessengerAgent(self.model_dispatcher, controller=self)

        # Initialize component managers
        self.research_manager = ResearchManager(self)
        self.writing_manager = WritingManager(self)
        self.reflection_manager = ReflectionManager(self)
        self.user_interaction_manager = UserInteractionManager(self)
        self.report_generator = ReportGenerator(self)

        logger.info("AgentController initialized with agents, context manager, tool registry.")
        # Settings now loaded from user configuration dynamically
        logger.debug(f"  Research Loop Settings: max_research_cycles_per_section={self.max_research_cycles_per_section}")
        logger.debug(f"  Writing Settings: writing_passes={config.WRITING_PASSES}")
        self._register_core_tools()

    def _initialize_query_components(self, mission_id: str):
        """Initialize query components with mission-specific user settings."""
        if not self.query_preparer or not self.query_strategist:
            self.query_preparer = QueryPreparer(self.model_dispatcher, mission_id)
            self.query_strategist = QueryStrategist(self.model_dispatcher, mission_id)
            logger.info(f"Initialized query components for mission {mission_id}")

    def _register_core_tools(self):
        """Registers the standard tools with the ToolRegistry."""
        logger.info("Registering core tools...")
        try:
            # Register RAG components if available
            if self.retriever:
                self._register_document_search_tool()

            # Web Search Tool
            web_search_instance = WebSearchTool(controller=self)
            web_search_def = ToolDefinition(
                name=web_search_instance.name,
                description=web_search_instance.description,
                parameters_schema=web_search_instance.parameters_schema,
                implementation=web_search_instance.execute
            )
            self.tool_registry.register_tool(web_search_def)

            # Python Tool
            python_tool_instance = PythonTool()
            python_tool_def = ToolDefinition(
                name=python_tool_instance.name,
                description=python_tool_instance.description,
                parameters_schema=python_tool_instance.parameters_schema,
                implementation=python_tool_instance.execute
            )
            self.tool_registry.register_tool(python_tool_def)

            # File Reader Tool
            file_reader_instance = FileReaderTool()
            file_reader_def = ToolDefinition(
                name=file_reader_instance.name,
                description=file_reader_instance.description,
                parameters_schema=file_reader_instance.parameters_schema,
                implementation=file_reader_instance.execute
            )
            self.tool_registry.register_tool(file_reader_def)

            # Web Page Fetcher Tool
            web_fetcher_instance = WebPageFetcherTool()
            web_fetcher_def = ToolDefinition(
                name=web_fetcher_instance.name,
                description=web_fetcher_instance.description,
                parameters_schema=web_fetcher_instance.parameters_schema,
                implementation=web_fetcher_instance.execute
            )
            self.tool_registry.register_tool(web_fetcher_def)

            logger.info("Core tools registered successfully.")
        except Exception as e:
            logger.error(f"Failed to register core tools: {e}", exc_info=True)
            raise

    def _register_document_search_tool(self):
        """Registers the document search tool if a retriever is available."""
        # Note: query_preparer and query_strategist will be None initially
        # The DocumentSearchTool will need to handle this and get them from the controller
        document_search_instance = DocumentSearchTool(
            retriever=self.retriever,
            query_preparer=None,  # Will be set per-mission
            query_strategist=None,  # Will be set per-mission
            controller=self  # Pass controller so tool can access query components
        )
        document_search_def = ToolDefinition(
            name=document_search_instance.name,
            description=document_search_instance.description,
            parameters_schema=document_search_instance.parameters_schema,
            implementation=document_search_instance.execute
        )
        self.tool_registry.register_tool(document_search_def)
        logger.info("Document Search tool registered.")

    def _validate_outline_minimum_requirements(self, outline: List[ReportSection]) -> Dict[str, Any]:
        """
        Validates that the outline meets minimum requirements:
        1. Has at least one section overall
        2. Has at least one section with research_strategy = "research_based"
        
        Returns a dictionary with:
        - "valid": Boolean indicating if the outline meets requirements
        - "reason": String explanation if invalid, None if valid
        """
        # Check if outline has at least one section
        if not outline:
            return {
                "valid": False,
                "reason": "Outline has no sections. At least one section is required."
            }
            
        # Check if there's at least one research-based section
        has_research_based = False
        
        def check_research_based(sections):
            nonlocal has_research_based
            for section in sections:
                if section.research_strategy == "research_based":
                    has_research_based = True
                    return True
                if section.subsections:
                    if check_research_based(section.subsections):
                        return True
            return False
            
        check_research_based(outline)
        
        if not has_research_based:
            return {
                "valid": False,
                "reason": "Outline has no research-based sections. At least one section with research_strategy = 'research_based' is required."
            }
            
        # All checks passed
        return {
            "valid": True,
            "reason": None
        }
    
    async def get_outline_at_round_start(self, mission_id: str, round_num: int) -> Optional[List[Any]]:
        """
        Retrieve the outline that was active at the start of a specific research round.
        This searches through execution logs to find the last valid outline before the specified round.
        
        Args:
            mission_id: The mission ID
            round_num: The round number to resume from (we'll get the outline from round_num - 1)
            
        Returns:
            The outline from the previous round, or None if not found
        """
        try:
            logger.info(f"Retrieving outline for mission {mission_id} at round {round_num}")
            
            # Get execution logs from database to find the outline from previous rounds
            from database.async_database import get_async_db_session
            from database import async_crud
            
            async_db = await get_async_db_session()
            try:
                # Get all execution logs for this mission
                execution_logs = await async_crud.get_mission_execution_logs(
                    async_db, mission_id, user_id=None, limit=1000
                )
                
                # Look for outline revision or planning logs that contain the full outline
                # We want the outline from BEFORE the requested round (so round_num - 1)
                target_round = round_num - 1 if round_num > 1 else 1
                
                # Search for logs that contain outline information
                outline_logs = []
                for log in execution_logs:
                    # Check if this log contains an outline (usually from PlanningAgent or outline revision)
                    if log.agent_name in ["PlanningAgent", "ReflectionManager", "AgentController"]:
                        if "outline" in log.action.lower() or "plan" in log.action.lower():
                            # Check if full_output contains outline data
                            if log.full_output and isinstance(log.full_output, dict):
                                if "report_outline" in log.full_output:
                                    outline_logs.append(log)
                                elif "revised_outline" in log.full_output:
                                    outline_logs.append(log)
                                elif "outline" in log.full_output:
                                    outline_logs.append(log)
                
                logger.info(f"Found {len(outline_logs)} logs with outline information")
                
                # Find the most recent outline before the target round
                if outline_logs:
                    # Sort by timestamp descending to get the most recent first
                    outline_logs.sort(key=lambda x: x.timestamp, reverse=True)
                    
                    for log in outline_logs:
                        # Extract the outline from the log
                        outline_data = None
                        if isinstance(log.full_output, dict):
                            outline_data = (
                                log.full_output.get("report_outline") or
                                log.full_output.get("revised_outline") or
                                log.full_output.get("outline")
                            )
                        
                        if outline_data:
                            logger.info(f"Found outline from {log.agent_name} at {log.timestamp}")
                            
                            # Parse the outline if it's a string (JSON)
                            if isinstance(outline_data, str):
                                import json
                                try:
                                    outline_data = json.loads(outline_data)
                                except:
                                    pass
                            
                            # Convert to ReportSection objects if needed
                            if isinstance(outline_data, list) and len(outline_data) > 0:
                                from ai_researcher.agentic_layer.schemas.planning import ReportSection
                                
                                # Check if this is a valid outline (not just request_outline)
                                if len(outline_data) > 1 or (
                                    len(outline_data) == 1 and 
                                    outline_data[0].get("section_id") != "request_outline"
                                ):
                                    # Convert dict to ReportSection objects
                                    try:
                                        outline_sections = [
                                            ReportSection(**section) if isinstance(section, dict) else section
                                            for section in outline_data
                                        ]
                                        logger.info(f"Successfully retrieved outline with {len(outline_sections)} sections")
                                        return outline_sections
                                    except Exception as e:
                                        logger.warning(f"Failed to parse outline: {e}")
                                        continue
                
                # If no outline found in logs, fall back to current context
                logger.warning(f"No valid outline found in execution logs for round {target_round}")
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.plan:
                    current_outline = mission_context.plan.report_outline
                    # Only return if it's a valid outline
                    if len(current_outline) > 1 or (
                        len(current_outline) == 1 and 
                        current_outline[0].section_id != "request_outline"
                    ):
                        return current_outline
                    
            finally:
                await async_db.close()
                
        except Exception as e:
            logger.error(f"Error retrieving outline at round {round_num} for mission {mission_id}: {e}")
        
        return None
    
    async def _truncate_data_after_round(
        self,
        mission_id: str,
        mission_context: MissionContext,
        round_num: int
    ):
        """
        Truncate logs and notes that were created after the specified round.
        This ensures a clean state when resuming from a specific point.
        
        Args:
            mission_id: The mission ID
            mission_context: The mission context
            round_num: The round number we're resuming from (keep data up to round_num - 1)
        """
        try:
            logger.info(f"Truncating data for mission {mission_id} after round {round_num - 1}")
            
            # Find the timestamp of when the specified round started
            # We need to find logs that indicate the start of the round we're resuming from
            round_start_timestamp = None
            
            # Search through execution logs to find when this round started
            for log in mission_context.execution_log:
                # Look for log indicating start of the round
                if log.agent_name == "ResearchManager" and f"Round {round_num}:" in log.action:
                    round_start_timestamp = log.timestamp
                    break
            
            if not round_start_timestamp:
                # If we can't find exact round start, look for section processing in that round
                for log in mission_context.execution_log:
                    if log.agent_name == "ResearchAgent" and f"[Round {round_num}]" in log.action:
                        round_start_timestamp = log.timestamp
                        break
            
            if round_start_timestamp:
                logger.info(f"Found round {round_num} start at {round_start_timestamp}")
                
                # Truncate execution logs after this timestamp
                original_log_count = len(mission_context.execution_log)
                mission_context.execution_log = [
                    log for log in mission_context.execution_log 
                    if log.timestamp < round_start_timestamp
                ]
                truncated_logs = original_log_count - len(mission_context.execution_log)
                logger.info(f"Truncated {truncated_logs} execution logs")
                
                # Truncate notes created after this timestamp
                original_note_count = len(mission_context.notes)
                mission_context.notes = [
                    note for note in mission_context.notes 
                    if note.created_at < round_start_timestamp
                ]
                truncated_notes = original_note_count - len(mission_context.notes)
                logger.info(f"Truncated {truncated_notes} notes")
                
                # Clear any report content that was generated after this round
                # Keep only sections that were completed before this round
                if mission_context.report_content:
                    sections_to_keep = []
                    for log in mission_context.execution_log:
                        if "WritingAgent" in log.agent_name and "Completed writing section" in log.action:
                            # Extract section ID from the action
                            for section_id in mission_context.report_content.keys():
                                if section_id in log.action:
                                    sections_to_keep.append(section_id)
                    
                    # Keep only the sections that were completed before the truncation point
                    new_report_content = {}
                    for section_id in sections_to_keep:
                        if section_id in mission_context.report_content:
                            new_report_content[section_id] = mission_context.report_content[section_id]
                    
                    removed_sections = len(mission_context.report_content) - len(new_report_content)
                    mission_context.report_content = new_report_content
                    logger.info(f"Removed {removed_sections} report sections")
                
                # Clear final report if it exists (will be regenerated)
                if mission_context.final_report:
                    mission_context.final_report = None
                    logger.info("Cleared final report")
                
                # Update the mission context in the context manager
                await self.context_manager.save_mission_context(mission_id)
                
                # Also truncate database logs
                async with get_async_db() as db:
                    # Get all logs for this mission
                    db_logs = await crud.get_mission_execution_logs(db, mission_id)
                    
                    if db_logs and round_start_timestamp:
                        # Find logs to delete (those created after round_start_timestamp)
                        logs_to_delete = [
                            log for log in db_logs 
                            if log.timestamp >= round_start_timestamp
                        ]
                        
                        if logs_to_delete:
                            # Delete the logs from database
                            for log in logs_to_delete:
                                await crud.delete_mission_execution_log(db, log.id)
                            
                            logger.info(f"Deleted {len(logs_to_delete)} execution logs from database")
                
            else:
                logger.warning(f"Could not find timestamp for round {round_num} start, keeping all data")
            
        except Exception as e:
            logger.error(f"Error truncating data for mission {mission_id}: {e}", exc_info=True)
            # Don't fail the resume operation if truncation fails
    
    async def resume_from_round(
        self,
        mission_id: str,
        round_num: int,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ):
        """
        Resume mission from the beginning of a specific research round.
        Sets up the state and then calls run_mission with resume parameters.
        
        Args:
            mission_id: The mission ID
            round_num: The round number to resume from
            log_queue: Optional queue for logging
            update_callback: Optional callback for updates
        """
        try:
            logger.info(f"Resuming mission {mission_id} from round {round_num}")
            
            # Stop current execution if running
            mission_context = self.context_manager.get_mission_context(mission_id)
            current_status = mission_context.status if mission_context else None
            if current_status == "running":
                await self.context_manager.update_mission_status(mission_id, "paused")
                # Wait a moment for execution to stop
                await asyncio.sleep(1)
            
            # Check if mission context and plan exist
            if not mission_context:
                logger.error(f"Mission context not found for mission {mission_id}")
                await self.context_manager.update_mission_status(mission_id, "failed", "Mission context not found")
                return False
            
            if not mission_context.plan:
                logger.error(f"Mission plan not found for mission {mission_id}")
                await self.context_manager.update_mission_status(mission_id, "failed", "Mission plan not found")
                return False
            
            # Truncate logs and notes created after the resume point
            await self._truncate_data_after_round(mission_id, mission_context, round_num)
            
            # Check if we already have a valid outline (e.g., from revision)
            # Only retrieve from database if the current outline is missing or empty
            if not mission_context.plan.report_outline:
                # Get the outline from the previous round (the last valid outline)
                outline = await self.get_outline_at_round_start(mission_id, round_num)
                if not outline:
                    logger.error(f"Could not retrieve a valid outline for round {round_num}")
                    await self.context_manager.update_mission_status(mission_id, "failed", "Could not retrieve valid outline for resume")
                    return False
                
                # Replace the current (empty) outline with the valid one from previous round
                logger.info(f"Setting outline from database: {len(outline)} sections")
                mission_context.plan.report_outline = outline
            else:
                # Use the existing outline (which may have been revised)
                logger.info(f"Using existing outline (potentially revised): {len(mission_context.plan.report_outline)} sections")
            
            # Log the outline being used
            current_outline = mission_context.plan.report_outline
            logger.info(f"Outline for mission {mission_id}:")
            for i, section in enumerate(current_outline[:5]):  # Log first 5 sections
                logger.info(f"  {i+1}. {section.section_id}: {section.title}")
            
            # Create resume checkpoint to start from the specified round
            resume_checkpoint = {
                'phase': 'structured_research',  # Important: mark this as structured research phase
                'current_round': round_num,
                'completed_sections': []  # Start fresh from this round
            }
            
            # Store the checkpoint in context for run_mission to use
            self.context_manager.store_resume_checkpoint(mission_id, resume_checkpoint)
            
            logger.info(f"Stored checkpoint and prepared mission state for resume from round {round_num}")
            
            # Now call run_mission with resume_from_phase set to "structured_research"
            # This will make run_mission skip the initial phases and start from the research plan execution
            await self.run_mission(
                mission_id=mission_id,
                log_queue=log_queue,
                update_callback=update_callback,
                resume_from_phase="structured_research"
            )
            
            # run_mission handles all the phases including writing and citation processing
            # No need to duplicate that logic here
            return True
            
        except Exception as e:
            logger.error(f"Error resuming mission {mission_id} from round {round_num}: {e}", exc_info=True)
            await self.context_manager.update_mission_status(mission_id, "failed", f"Resume failed: {e}")
            return False
    
    async def resume_writing_phase(
        self,
        mission_id: str,
        writing_pass: int = 0,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ):
        """
        Resume mission from the writing phase at a specific pass.
        
        Args:
            mission_id: The mission ID
            writing_pass: The writing pass to resume from (0-based)
            log_queue: Optional queue for logging
            update_callback: Optional callback for updates
        """
        try:
            logger.info(f"Resuming writing phase for mission {mission_id} from pass {writing_pass}")
            
            # Check if mission context and plan exist
            mission_context = self.context_manager.get_mission_context(mission_id)
            if not mission_context:
                logger.error(f"Mission context not found for mission {mission_id}")
                await self.context_manager.update_mission_status(mission_id, "failed", "Mission context not found")
                return False
            
            if not mission_context.plan:
                logger.error(f"Mission plan not found for mission {mission_id}")
                await self.context_manager.update_mission_status(mission_id, "failed", "Mission plan not found")
                return False
            
            # Create resume checkpoint for writing phase
            resume_checkpoint = {
                'phase': 'writing',
                'current_pass': writing_pass,
                'completed_sections': []  # Will be loaded from saved checkpoint if available
            }
            
            # Load any existing checkpoint data
            existing_checkpoint = await self.context_manager.get_phase_checkpoint(mission_id, 'writing')
            if existing_checkpoint:
                # Merge with existing checkpoint
                if 'completed_sections' in existing_checkpoint and writing_pass == existing_checkpoint.get('current_pass', 0):
                    resume_checkpoint['completed_sections'] = existing_checkpoint['completed_sections']
                    logger.info(f"Loaded {len(resume_checkpoint['completed_sections'])} completed sections from checkpoint")
            
            # Store the checkpoint in context for run_mission to use
            self.context_manager.store_resume_checkpoint(mission_id, resume_checkpoint)
            
            logger.info(f"Stored checkpoint and prepared mission state for writing phase resume from pass {writing_pass}")
            
            # Call run_mission with resume_from_phase set to "writing"
            await self.run_mission(
                mission_id=mission_id,
                log_queue=log_queue,
                update_callback=update_callback,
                resume_from_phase="writing"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error resuming writing phase for mission {mission_id}: {e}", exc_info=True)
            await self.context_manager.update_mission_status(mission_id, "failed", f"Writing phase resume failed: {e}")
            return False
    
    async def revise_outline_and_resume(
        self,
        mission_id: str,
        round_num: int,
        user_feedback: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ):
        """
        Apply user feedback to revise the outline and resume from a specific round.
        
        Args:
            mission_id: The mission ID
            round_num: The round number to resume from
            user_feedback: User's feedback for outline revision
            log_queue: Optional queue for logging
            update_callback: Optional callback for updates
        """
        try:
            logger.info(f"Revising outline and resuming mission {mission_id} from round {round_num}")
            
            # Stop current execution if running
            mission_context = self.context_manager.get_mission_context(mission_id)
            current_status = mission_context.status if mission_context else None
            if current_status == "running":
                await self.context_manager.update_mission_status(mission_id, "paused")
                # Wait a moment for execution to stop
                await asyncio.sleep(1)
            
            await self.context_manager.update_mission_status(mission_id, "revising")
            
            # Get current mission context
            mission_context = self.context_manager.get_mission_context(mission_id)
            if not mission_context or not mission_context.plan:
                logger.error(f"Mission context or plan not found for {mission_id}")
                await self.context_manager.update_mission_status(mission_id, "failed", "Mission context not found")
                return False
            
            # Call PlanningAgent with user feedback to revise the outline
            current_outline = mission_context.plan.report_outline
            user_request = mission_context.user_request
            
            # Format the outline for display
            from ai_researcher.agentic_layer.controller.utils import outline_utils
            formatted_outline = outline_utils.format_outline_for_prompt(current_outline)
            
            revision_context = f"""User Feedback for Outline Revision:
{user_feedback}

Current Outline:
{chr(10).join(formatted_outline)}

Please revise the outline based on the user's feedback while maintaining the overall mission goal.
Make sure to address the user's specific concerns and suggestions."""
            
            # Get revised outline from PlanningAgent
            active_goals = self.context_manager.get_active_goals(mission_id)
            active_thoughts = self.context_manager.get_recent_thoughts(mission_id, limit=5)
            current_scratchpad = self.context_manager.get_scratchpad(mission_id)
            
            async with self.maybe_semaphore:
                response, model_details, scratchpad_update = await self.planning_agent.run(
                    user_request=user_request,
                    revision_context=revision_context,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            
            if response and response.report_outline:
                # Validate the revised outline
                from ai_researcher.agentic_layer.controller.reflection_manager_batched import is_error_outline
                if is_error_outline(response.report_outline):
                    logger.error("Revised outline contains error patterns")
                    await self.context_manager.update_mission_status(mission_id, "failed", "Invalid revised outline")
                    return False
                
                # Update the outline in mission context
                mission_context.plan.report_outline = response.report_outline
                
                # Store the updated plan to persist it and send to frontend via websocket
                await self.context_manager.store_plan(mission_id, mission_context.plan)
                logger.info(f"Stored revised outline with {len(response.report_outline)} sections to database and sent to frontend")
                
                # Update scratchpad if provided
                if scratchpad_update:
                    await self.context_manager.update_scratchpad(mission_id, scratchpad_update)
                
                # Log the revision
                await self.context_manager.log_execution_step(
                    mission_id, "AgentController", "Revise Outline from User Feedback",
                    input_summary=f"User feedback: {user_feedback[:100]}...",
                    output_summary=f"Revised outline with {len(response.report_outline)} sections",
                    status="success",
                    log_queue=log_queue,
                    update_callback=update_callback
                )
                
                # Truncate logs and notes created after the resume point
                # Note: This is done inside resume_from_round, not here, to avoid double truncation
                
                # Resume from the specified round with the new outline
                return await self.resume_from_round(mission_id, round_num, log_queue, update_callback)
            else:
                logger.error("Failed to get revised outline from PlanningAgent")
                await self.context_manager.update_mission_status(mission_id, "failed", "Failed to revise outline")
                return False
                
        except Exception as e:
            logger.error(f"Error revising outline for mission {mission_id}: {e}", exc_info=True)
            await self.context_manager.update_mission_status(mission_id, "failed", str(e))
            return False
    
    async def resume_mission(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ):
        """
        Resumes a mission from where it left off based on completed phases and checkpoint data.
        Intelligently determines the correct phase based on all available mission data.
        """
        mission_context = self.context_manager.get_mission_context(mission_id)
        if not mission_context:
            logger.error(f"Mission {mission_id} not found in context")
            return
        
        # First, check if we have checkpoint data that indicates an in-progress phase
        phase_checkpoint = mission_context.phase_checkpoint
        
        # Check for structured research checkpoint
        if 'structured_research' in phase_checkpoint and phase_checkpoint['structured_research']:
            sr_checkpoint = phase_checkpoint['structured_research']
            # If structured research has checkpoint data but isn't marked complete
            if 'structured_research' not in mission_context.completed_phases:
                logger.info(f"Mission {mission_id} has structured research checkpoint at round {sr_checkpoint.get('current_round', 0)}")
                # Restore the checkpoint and resume from structured research
                self.context_manager.store_resume_checkpoint(mission_id, sr_checkpoint)
                await self.run_mission(mission_id, log_queue, update_callback, resume_from_phase="structured_research")
                return
        
        # Check for writing phase checkpoint
        if 'writing' in phase_checkpoint and phase_checkpoint['writing']:
            writing_checkpoint = phase_checkpoint['writing']
            # If writing has checkpoint data but isn't marked complete
            if 'writing' not in mission_context.completed_phases:
                logger.info(f"Mission {mission_id} has writing checkpoint at pass {writing_checkpoint.get('current_pass', 0)}")
                # Restore the checkpoint and resume from writing
                self.context_manager.store_resume_checkpoint(mission_id, writing_checkpoint)
                await self.run_mission(mission_id, log_queue, update_callback, resume_from_phase="writing")
                return
        
        # Check based on what data exists in the mission context
        # If we have a plan and notes, we've at least completed initial research
        has_plan = mission_context.plan is not None
        has_notes = mission_context.notes and len(mission_context.notes) > 0
        has_report_content = mission_context.report_content and len(mission_context.report_content) > 0
        
        # Determine phase based on available data
        if has_report_content:
            # If there's report content, we're at least in the writing phase
            if 'writing' not in mission_context.completed_phases:
                logger.info(f"Mission {mission_id} has report content, resuming from writing phase")
                await self.run_mission(mission_id, log_queue, update_callback, resume_from_phase="writing")
                return
        
        if has_plan and has_notes:
            # If we have both plan and notes, check if we need to continue structured research
            if 'structured_research' not in mission_context.completed_phases:
                # Check if we have enough notes or need more research
                logger.info(f"Mission {mission_id} has plan and {len(mission_context.notes)} notes, checking structured research status")
                # Look for any indication we were in structured research
                if mission_context.current_phase_display and 'Structured Research' in str(mission_context.current_phase_display):
                    logger.info(f"Mission {mission_id} was in structured research, resuming")
                    await self.run_mission(mission_id, log_queue, update_callback, resume_from_phase="structured_research")
                    return
        
        # Fall back to the standard phase detection
        next_phase = self.context_manager.get_next_phase(mission_id)
        
        if next_phase == "completed":
            logger.info(f"Mission {mission_id} is already completed")
            return
        
        logger.info(f"Resuming mission {mission_id} from phase: {next_phase} (standard detection)")
        
        # Call run_mission which will now check for completed phases
        await self.run_mission(mission_id, log_queue, update_callback, resume_from_phase=next_phase)
    
    async def run_mission(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None,
        resume_from_phase: Optional[str] = None
    ):
        """
        Runs the full research mission using the workflow.
        Accepts optional queue and callback function to report execution steps and UI feedback.
        Can resume from a specific phase if provided.
        """
        try:
            if resume_from_phase:
                logger.info(f"Resuming mission {mission_id} from phase: {resume_from_phase}")
            else:
                logger.info(f"Executing mission {mission_id} with new workflow...")
            
            await self.context_manager.update_mission_status(mission_id, "running")

            # Initialize query components with user-specific models for this mission
            self._initialize_query_components(mission_id)

            # Get Mission Context
            mission_context = self.context_manager.get_mission_context(mission_id)
            if not mission_context:
                logger.error(f"Mission context not found for {mission_id} at the start of run_mission. Aborting.")
                if update_callback and log_queue:
                    error_log = ExecutionLogEntry(
                        mission_id=mission_id, agent_name="AgentController", action="Run Mission Start",
                        status="failure", error_message="Mission context not found."
                    )
                    update_callback(log_queue, error_log)
                await self.context_manager.update_mission_status(mission_id, "failed", "Mission context not found at start.")
                return
            
            user_request = mission_context.user_request
            
            # Step 1: Initial Request Analysis
            if "initial_analysis" not in mission_context.completed_phases:
                await self.context_manager.update_execution_phase(mission_id, "initial_analysis")
                await self.context_manager.update_phase_display(mission_id, {
                    "phase": "Initial Analysis",
                    "step": "Analyzing user request",
                    "progress": 0
                })
                
                analysis_result = await self.user_interaction_manager.analyze_request_type(
                    mission_id=mission_id,
                    user_request=user_request,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

                # Step 2: Goal Pad & Thought Pad Initialization
                initial_thought_content = f"Starting mission. Core user request: {user_request[:150]}..."
                await self.context_manager.add_thought(mission_id, "AgentController", initial_thought_content)
                logger.info(f"Added initial focus thought to thought_pad for mission {mission_id}.")

                if analysis_result:
                    logger.info(f"Initializing goal pad for mission {mission_id} based on analysis.")
                    try:
                        # Add original request as a goal
                        await self.context_manager.add_goal(mission_id, user_request)
                        # Add analysis results as goals
                        await self.context_manager.add_goal(mission_id, f"Request Type is {analysis_result.request_type}")
                        await self.context_manager.add_goal(mission_id, f"Target Tone is {analysis_result.target_tone}")
                        await self.context_manager.add_goal(mission_id, f"Target Audience is {analysis_result.target_audience}")
                        await self.context_manager.add_goal(mission_id, f"Requested Length is {analysis_result.requested_length}")
                        await self.context_manager.add_goal(mission_id, f"Requested Format is {analysis_result.requested_format}")
                        # Add preferred source types as a goal if present
                        if analysis_result.preferred_source_types:
                            await self.context_manager.add_goal(mission_id, f"Preferred Source Types: {analysis_result.preferred_source_types}")
                            logger.info(f"Added preferred source types '{analysis_result.preferred_source_types}' to goal pad.")
                        logger.info("Added analysis results to goal pad.")
                    except Exception as goal_exc:
                        logger.error(f"Failed to add analysis results to goal pad for mission {mission_id}: {goal_exc}", exc_info=True)
                        await self.context_manager.log_execution_step(
                            mission_id, "AgentController", "Initialize Goal Pad",
                            status="warning", error_message=f"Failed to add goals: {goal_exc}",
                            log_queue=log_queue, update_callback=update_callback
                        )
                else:
                    logger.warning(f"Request analysis failed for mission {mission_id}. Proceeding without analysis goals.")
                    await self.context_manager.add_goal(mission_id, user_request)
                
                # Mark initial analysis as completed
                await self.context_manager.mark_phase_completed(mission_id, "initial_analysis")
            else:
                logger.info(f"Skipping initial_analysis phase - already completed for mission {mission_id}")

            # Create Mission-Specific Feedback Callback
            mission_feedback_callback = None
            if update_callback and log_queue:
                def _feedback_callback_impl(log_queue_arg, feedback_data: Dict[str, Any]):
                    try:
                        update_callback(log_queue_arg, feedback_data, mission_id, None)
                    except Exception as e:
                        logger.error(f"Error calling update_callback with feedback message: {e}", exc_info=True)
                mission_feedback_callback = _feedback_callback_impl

            # Phase 1: Initial Research Phase (Skip if resuming from structured_research)
            mission_context = self.context_manager.get_mission_context(mission_id)
            user_request = mission_context.user_request
            tool_selection = mission_context.metadata.get("tool_selection", {'local_rag': True, 'web_search': True})
            
            # Initialize preliminary_plan variable
            preliminary_plan = None
            
            # Only run initial research and outline generation if NOT resuming from structured_research
            if resume_from_phase != "structured_research":
                final_questions = mission_context.metadata.get("final_questions")

                if not final_questions:
                    logger.error(f"Cannot start research phase: Final questions not found in metadata for mission {mission_id}.")
                    await self.context_manager.update_mission_status(mission_id, "failed", "Final questions missing before research phase.")
                    return

                # Check if mission was stopped or paused before starting research
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.status in ["stopped", "paused"]:
                    logger.info(f"Mission {mission_id} was {mission_context.status} before research phase. Aborting.")
                    return

                logger.info(f"Starting initial research phase for mission {mission_id} with {len(final_questions)} questions.")
                initial_notes, final_scratchpad = await self.research_manager.run_initial_research_phase(
                    mission_id=mission_id,
                    user_request=user_request,
                    log_queue=log_queue,
                    update_callback=update_callback,
                    feedback_callback=update_callback,
                    initial_questions_override=final_questions,
                    tool_selection=tool_selection
                )
                
                # Check if mission was stopped or paused during research
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.status in ["stopped", "paused"]:
                    logger.info(f"Mission {mission_id} was {mission_context.status} during initial research phase. Aborting.")
                    return
                    
                logger.info(f"Initial research phase completed for mission {mission_id}. Found {len(initial_notes)} notes.")

                # Phase 2: Preliminary Outline Generation
                # Check if mission was stopped or paused before outline generation
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.status in ["stopped", "paused"]:
                    logger.info(f"Mission {mission_id} was {mission_context.status} before outline generation. Aborting.")
                    return

                active_goals = self.context_manager.get_active_goals(mission_id)
                preliminary_plan = await self.research_manager.generate_preliminary_outline(
                    mission_id=mission_id,
                    user_request=user_request,
                    initial_notes=initial_notes,
                    initial_scratchpad=final_scratchpad,
                    tool_selection=tool_selection,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

                # Check if mission was stopped or paused during outline generation
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.status in ["stopped", "paused"]:
                    logger.info(f"Mission {mission_id} was {mission_context.status} during outline generation. Aborting.")
                    return

                if not preliminary_plan:
                    logger.error(f"Failed to generate preliminary outline for mission {mission_id}. Aborting.")
                    await self.context_manager.update_mission_status(mission_id, "failed", "Preliminary outline generation failed.")
                    return
                else:
                    await self.context_manager.store_plan(mission_id, preliminary_plan)
                    logger.info(f"Successfully generated and stored preliminary outline for mission {mission_id}.")
            else:
                # We're resuming from structured_research - use the existing plan (which may have been revised)
                logger.info(f"Resuming from structured_research phase - skipping initial research and using existing outline")
                preliminary_plan = self.context_manager.get_plan(mission_id)
                if not preliminary_plan:
                    logger.error(f"No plan found for mission {mission_id} when resuming from structured_research")
                    await self.context_manager.update_mission_status(mission_id, "failed", "No plan found when resuming")
                    return
                logger.info(f"Using existing outline with {len(preliminary_plan.report_outline)} sections for structured research")

            # Phase 2b: Execute Research Plan
            # Check if mission was stopped or paused before plan execution
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} before plan execution. Aborting.")
                return

            # Get checkpoint data if resuming
            resume_checkpoint = None
            if resume_from_phase == "structured_research":
                resume_checkpoint = self.context_manager.get_resume_checkpoint(mission_id)
                if resume_checkpoint and resume_checkpoint.get('phase') == 'structured_research':
                    logger.info(f"Found structured_research checkpoint for mission {mission_id}: {resume_checkpoint}")
            else:
                # Starting structured research fresh - save initial checkpoint
                logger.info(f"Starting structured research phase for mission {mission_id}")
                initial_checkpoint = {
                    'phase': 'structured_research',
                    'current_round': 0,
                    'completed_sections': []
                }
                await self.context_manager.save_phase_checkpoint(mission_id, 'structured_research', initial_checkpoint)

            plan_execution_success = await self.research_manager.execute_research_plan(
                mission_id=mission_id,
                plan=preliminary_plan,
                log_queue=log_queue,
                update_callback=update_callback,
                resume_checkpoint=resume_checkpoint
            )
            
            # Check if mission was stopped or paused during plan execution
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} during plan execution. Aborting.")
                return
                
            if not plan_execution_success:
                logger.error(f"Research plan execution phase failed for mission {mission_id}. Aborting.")
                if self.context_manager.get_mission_context(mission_id).status != "failed":
                    await self.context_manager.update_mission_status(mission_id, "failed", "Research plan execution failed.")
                return

            # Phase 3: Prepare Notes for Writing (Conditional based on config) 
            active_goals = self.context_manager.get_active_goals(mission_id)
            full_note_assignments: Optional[FullNoteAssignments] = None

            # Only run note assignment phase if NOT resuming from writing
            if resume_from_phase != "writing":
                skip_final_replanning = get_skip_final_replanning(mission_id)
                if not skip_final_replanning:
                    logger.info(f"Running final outline refinement and note reassignment for mission {mission_id}.")
                    await self.context_manager.log_execution_step(
                    mission_id=mission_id, agent_name="AgentController", action="Prepare Notes (Standard)",
                    status="success", output_summary="Running final outline refinement and note reassignment.", # Use output_summary
                    log_queue=log_queue, update_callback=update_callback
                    )
                    full_note_assignments = await self.research_manager.reassign_notes_to_final_outline(
                    mission_id=mission_id,
                    active_goals=active_goals,
                    log_queue=log_queue,
                    update_callback=update_callback
                    )

                    if full_note_assignments is None:
                        logger.error(f"Standard note assignment phase failed critically for mission {mission_id}. Aborting.")
                        await self.context_manager.update_mission_status(mission_id, "failed", "Standard note assignment phase failed critically.")
                        return
                    elif not full_note_assignments.assignments:
                        logger.warning(f"Standard note assignment phase for mission {mission_id} resulted in empty assignments. Proceeding, but writing phase might be affected.")
                    
                    await self.context_manager.log_execution_step(
                        mission_id=mission_id, agent_name="AgentController", action="Prepare Notes (Standard)",
                        status="success", output_summary=f"Completed standard note reassignment. {len(full_note_assignments.assignments)} sections assigned.", # Use output_summary
                        log_queue=log_queue, update_callback=update_callback
                    )
                    
                    # Save note assignments to checkpoint for potential writing phase resume
                    await self.context_manager.save_phase_checkpoint(
                        mission_id, 'writing', 
                        {'note_assignments': full_note_assignments.dict()}
                    )

                else:
                    logger.info(f"Skipping final replanning. Running redundancy reflection for mission {mission_id}.")
                    await self.context_manager.log_execution_step(
                        mission_id=mission_id, agent_name="AgentController", action="Prepare Notes (Skip Replanning)",
                        status="success", output_summary="Skipping final replanning. Running redundancy reflection.", # Use output_summary
                        log_queue=log_queue, update_callback=update_callback
                    )
                    
                    # 1. Get all notes generated so far
                    all_notes = self.context_manager.get_notes(mission_id)
                    if not all_notes:
                        logger.warning(f"No notes found for redundancy check in mission {mission_id}. Proceeding without reflection.")
                        # Create an empty assignment structure to proceed
                        current_plan = self.context_manager.get_plan(mission_id)
                        if not current_plan:
                            logger.error(f"Cannot create empty assignments: Plan not found for mission {mission_id}.")
                            await self.context_manager.update_mission_status(mission_id, "failed", "Plan not found when skipping replanning.")
                            return # Abort if plan is missing
                        
                        # Import AssignedNotes here, locally within the method scope
                        from ai_researcher.agentic_layer.agents.note_assignment_agent import AssignedNotes
                        
                        empty_assignments: Dict[str, AssignedNotes] = {}
                        # Need to recursively process the outline to create empty assignments for all sections/subsections
                        def process_empty_sections(sections: List[ReportSection]):
                            for section in sections:
                                empty_assignments[section.section_id] = AssignedNotes(
                                    section_id=section.section_id, 
                                    relevant_note_ids=[], 
                                    reasoning="No notes available for this section."
                                )
                                if section.subsections:
                                    process_empty_sections(section.subsections)
                        process_empty_sections(current_plan.report_outline)
                        full_note_assignments = FullNoteAssignments(assignments=empty_assignments)
                        logger.info(f"Created empty note assignments for {len(empty_assignments)} sections.")

                    else:
                        logger.info(f"Found {len(all_notes)} notes for redundancy reflection.")
                        # 2. Run redundancy reflection (using ReflectionManager)
                        # Assuming ReflectionManager has a method like this, or we add it.
                        try:
                            filtered_notes = await self.reflection_manager.perform_redundancy_check(
                            mission_id=mission_id,
                            notes=all_notes,
                            log_queue=log_queue,
                            update_callback=update_callback
                            )
                            logger.info(f"Redundancy check completed. {len(filtered_notes)} notes remaining.")
                            
                            # 3. Update notes in context (optional, depends on how perform_redundancy_check works)
                            # If the check returns only the notes to keep, we might need to update the context
                            # or just use filtered_notes directly. Let's assume we use filtered_notes.

                            # 4. Create a simple FullNoteAssignments structure based on the *existing* plan
                            # We map the filtered notes back to their original sections without re-assigning.
                            current_plan = self.context_manager.get_plan(mission_id)
                            if not current_plan:
                                logger.error(f"Cannot assign filtered notes: Plan not found for mission {mission_id}.")
                                await self.context_manager.update_mission_status(mission_id, "failed", "Plan not found when skipping replanning.")
                                return # Abort if plan is missing
                            
                            # Import AssignedNotes here, locally within the method scope
                            from ai_researcher.agentic_layer.agents.note_assignment_agent import AssignedNotes

                            assignments: Dict[str, AssignedNotes] = {}
                            # Create a map of filtered notes by ID for efficient lookup
                            filtered_notes_map = {note.note_id: note for note in filtered_notes}
                            filtered_note_ids_set = set(filtered_notes_map.keys())

                            # Iterate through the plan sections to assign filtered notes
                            def process_sections_for_assignment(sections: List[ReportSection]):
                                for section in sections:
                                    # Get note IDs originally associated with this section from the plan
                                    original_associated_ids = set(section.associated_note_ids or [])
                                    
                                    # Find which of the originally associated notes survived the redundancy check
                                    kept_associated_ids = original_associated_ids.intersection(filtered_note_ids_set)
                                    
                                    # Retrieve the actual Note objects for the kept IDs
                                    section_notes_kept = [filtered_notes_map[note_id] for note_id in kept_associated_ids]
                                    
                                    # Create the AssignedNotes object for this section
                                    kept_note_ids = [note.note_id for note in section_notes_kept]
                                    assignments[section.section_id] = AssignedNotes(
                                        section_id=section.section_id,
                                        relevant_note_ids=kept_note_ids,
                                        reasoning=f"Notes automatically assigned based on existing section associations after redundancy check."
                                    )
                                    logger.debug(f"Assigned {len(section_notes_kept)} filtered notes to section {section.section_id} (Skip Replanning).")
                                    
                                    # Recursively process subsections
                                    if section.subsections:
                                        process_sections_for_assignment(section.subsections)

                            process_sections_for_assignment(current_plan.report_outline)
                            full_note_assignments = FullNoteAssignments(assignments=assignments)
                            logger.info(f"Created simple note assignments for {len(assignments)} sections based on filtered notes (Skip Replanning).")

                        except Exception as reflect_err:
                            logger.error(f"Error during redundancy reflection for mission {mission_id}: {reflect_err}", exc_info=True)
                            await self.context_manager.log_execution_step(
                            mission_id, "AgentController", "Prepare Notes (Skip Replanning)",
                            status="failure", error_message=f"Redundancy reflection failed: {reflect_err}",
                            log_queue=log_queue, update_callback=update_callback
                            )
                            await self.context_manager.update_mission_status(mission_id, "failed", "Redundancy reflection failed.")
                            return # Abort on reflection error

                    await self.context_manager.log_execution_step(
                        mission_id=mission_id, agent_name="AgentController", action="Prepare Notes (Skip Replanning)",
                        status="success", output_summary=f"Completed redundancy reflection. Prepared notes for writing.", # Use output_summary
                        log_queue=log_queue, update_callback=update_callback
                    )
                    
                    # Save note assignments to checkpoint for potential writing phase resume (skip replanning path)
                    if full_note_assignments:
                        await self.context_manager.save_phase_checkpoint(
                            mission_id, 'writing', 
                            {'note_assignments': full_note_assignments.dict()}
                        )

            else:
                # We're resuming from writing phase - need to reconstruct note assignments
                logger.info("Resuming from writing phase - loading or reconstructing note assignments")
                
                # Check if we have saved note assignments in the phase checkpoint
                writing_checkpoint = await self.context_manager.get_phase_checkpoint(mission_id, 'writing')
                if writing_checkpoint and 'note_assignments' in writing_checkpoint:
                    # Load from checkpoint
                    full_note_assignments = FullNoteAssignments(**writing_checkpoint['note_assignments'])
                    logger.info(f"Loaded note assignments from checkpoint: {len(full_note_assignments.assignments)} sections")
                else:
                    # Need to reconstruct from existing plan and notes
                    logger.info("No saved note assignments found - reconstructing from plan")
                    mission_context = self.context_manager.get_mission_context(mission_id)
                    current_plan = mission_context.plan if mission_context else None
                    
                    if not current_plan:
                        logger.error(f"Cannot reconstruct note assignments: Plan not found for mission {mission_id}")
                        await self.context_manager.update_mission_status(mission_id, "failed", "Plan not found when resuming writing phase")
                        return
                    
                    # Import AssignedNotes locally
                    from ai_researcher.agentic_layer.agents.note_assignment_agent import AssignedNotes
                    
                    # Create assignments from the existing plan's associated_note_ids
                    assignments: Dict[str, AssignedNotes] = {}
                    
                    def reconstruct_assignments(sections: List[ReportSection]):
                        for section in sections:
                            associated_ids = section.associated_note_ids or []
                            assignments[section.section_id] = AssignedNotes(
                                section_id=section.section_id,
                                relevant_note_ids=associated_ids,
                                reasoning="Reconstructed from existing plan for resume"
                            )
                            if section.subsections:
                                reconstruct_assignments(section.subsections)
                    
                    reconstruct_assignments(current_plan.report_outline)
                    full_note_assignments = FullNoteAssignments(assignments=assignments)
                    logger.info(f"Reconstructed note assignments for {len(assignments)} sections")
                    
                    # Save to checkpoint for future resumes
                    await self.context_manager.save_phase_checkpoint(
                        mission_id, 'writing', 
                        {'note_assignments': full_note_assignments.dict()}
                    )

            # Ensure full_note_assignments is not None before proceeding
            if full_note_assignments is None:
                 logger.error(f"Critical error: full_note_assignments is None before writing phase for mission {mission_id}. Aborting.")
                 await self.context_manager.update_mission_status(mission_id, "failed", "Note assignment structure missing before writing phase.")
                 return

            # Phase 4: Multi-Pass Writing Phase
            # Check if mission was stopped or paused before writing phase
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} before writing phase. Aborting.")
                return

            # Get checkpoint data if resuming from writing phase
            writing_checkpoint = None
            if resume_from_phase == "writing":
                writing_checkpoint = self.context_manager.get_resume_checkpoint(mission_id)
                if writing_checkpoint and writing_checkpoint.get('phase') == 'writing':
                    logger.info(f"Found writing checkpoint for mission {mission_id}: {writing_checkpoint}")

            writing_success = await self.writing_manager.run_writing_phase(
                mission_id=mission_id,
                assigned_notes=full_note_assignments,
                active_goals=active_goals,
                log_queue=log_queue,
                update_callback=update_callback,
                resume_checkpoint=writing_checkpoint
            )
            if not writing_success:
                logger.error(f"Writing phase failed for mission {mission_id}. Aborting.")
                if self.context_manager.get_mission_context(mission_id).status != "failed":
                    await self.context_manager.update_mission_status(mission_id, "failed", "Writing phase failed.")
                return

            # Check if mission was stopped or paused after writing phase
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} after writing phase. Aborting.")
                return

            # Phase 5: Generate Report Title
            try:
                active_goals = self.context_manager.get_active_goals(mission_id)
                title_success = await self.report_generator.generate_report_title(
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )
                if not title_success:
                    logger.warning(f"Failed to generate report title for mission {mission_id}. Report generation will continue without title.")
                    await self.context_manager.log_execution_step(
                        mission_id, "AgentController", "Generate Report Title",
                        status="warning", error_message="Title generation failed, proceeding without title.",
                        log_queue=log_queue, update_callback=update_callback
                    )
                else:
                    logger.info(f"Successfully generated report title for mission {mission_id}.")
            except Exception as title_e:
                logger.error(f"Error during title generation phase for mission {mission_id}: {title_e}", exc_info=True)
                await self.context_manager.log_execution_step(
                    mission_id, "AgentController", "Generate Report Title",
                    status="warning", error_message=f"Exception during title generation: {title_e}",
                    log_queue=log_queue, update_callback=update_callback
                )

            # Phase 6: Citation Processing
            citation_success = await self.report_generator.process_citations(
                mission_id, 
                log_queue, 
                update_callback
            )
            if not citation_success:
                logger.error(f"Citation processing failed for mission {mission_id}. Aborting.")
                if self.context_manager.get_mission_context(mission_id).status != "failed":
                    await self.context_manager.update_mission_status(mission_id, "failed", "Citation processing failed.")
                return
            
            # Check if mission was stopped or paused after citation processing
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} after citation processing. Aborting.")
                return

            # Final status check
            final_status = self.context_manager.get_mission_context(mission_id).status
            logger.info(f"Mission {mission_id} execution finished with final status: {final_status}")

        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            logger.info(f"Mission {mission_id} was cancelled")
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status not in ["stopped", "paused"]:
                await self.context_manager.update_mission_status(mission_id, "stopped", "Mission cancelled by user")
            if update_callback and log_queue:
                try:
                    cancel_log = ExecutionLogEntry(
                        mission_id=mission_id, agent_name="AgentController", 
                        action="Mission Cancelled",
                        status="success", 
                        output_summary="Mission was successfully cancelled"
                    )
                    update_callback(log_queue, cancel_log)
                except Exception as cb_err:
                    logger.error(f"Failed to log mission cancellation via callback: {cb_err}")
            raise  # Re-raise to properly propagate cancellation
        except Exception as e:
            err_msg = f"Critical error during mission execution: {e}"
            logger.error(err_msg, exc_info=True)
            if self.context_manager.get_mission_context(mission_id).status != "failed":
                await self.context_manager.update_mission_status(mission_id, "failed", err_msg)
            if update_callback and log_queue:
                try:
                    error_log = ExecutionLogEntry(
                        mission_id=mission_id, agent_name="AgentController", action="Run Mission (Top Level)",
                        status="failure", error_message=f"Critical error: {e}"
                    )
                    update_callback(log_queue, error_log)
                except Exception as cb_err:
                    logger.error(f"Failed to log top-level mission error via callback: {cb_err}")

    def register_mission_task(self, mission_id: str, task: asyncio.Task):
        """Register the main task for a mission."""
        self.mission_tasks[mission_id] = task
        logger.debug(f"Registered main task for mission {mission_id}")
    
    def unregister_mission_task(self, mission_id: str):
        """Unregister the main task for a mission."""
        if mission_id in self.mission_tasks:
            del self.mission_tasks[mission_id]
            logger.debug(f"Unregistered main task for mission {mission_id}")
    
    def add_mission_subtask(self, mission_id: str, task: asyncio.Task):
        """Add a subtask for a mission."""
        if mission_id not in self.mission_subtasks:
            self.mission_subtasks[mission_id] = set()
        self.mission_subtasks[mission_id].add(task)
        logger.debug(f"Added subtask for mission {mission_id}, total: {len(self.mission_subtasks[mission_id])}")
    
    def remove_mission_subtask(self, mission_id: str, task: asyncio.Task):
        """Remove a subtask for a mission."""
        if mission_id in self.mission_subtasks:
            self.mission_subtasks[mission_id].discard(task)
            if not self.mission_subtasks[mission_id]:
                del self.mission_subtasks[mission_id]
            logger.debug(f"Removed subtask for mission {mission_id}")
    
    async def stop_mission(self, mission_id: str):
        """Pauses a running mission and cancels all associated tasks with proper timeout."""
        logger.info(f"Pausing mission {mission_id}...")
        
        # First update the status to paused to prevent new tasks from starting
        await self.context_manager.update_mission_status(mission_id, "paused")
        
        # Store checkpoint for resuming later
        mission_context = self.context_manager.get_mission_context(mission_id)
        if mission_context:
            self.context_manager.store_resume_checkpoint(
                mission_id, 
                {
                    "status": "paused",
                    "timestamp": asyncio.get_event_loop().time()
                }
            )
        
        # Collect all tasks to cancel
        tasks_to_cancel = []
        
        # Add main task if it exists
        if mission_id in self.mission_tasks:
            main_task = self.mission_tasks[mission_id]
            if not main_task.done():
                tasks_to_cancel.append(main_task)
        
        # Add all subtasks if they exist
        if mission_id in self.mission_subtasks:
            for task in self.mission_subtasks[mission_id]:
                if not task.done():
                    tasks_to_cancel.append(task)
        
        if tasks_to_cancel:
            logger.info(f"Attempting to cancel {len(tasks_to_cancel)} tasks for mission {mission_id}")
            
            # First, request cancellation for all tasks
            for task in tasks_to_cancel:
                task.cancel()
            
            # Give tasks 5 seconds to finish gracefully
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                    timeout=5.0
                )
                logger.info(f"All tasks cancelled gracefully for mission {mission_id}")
            except asyncio.TimeoutError:
                logger.warning(f"Some tasks did not cancel within 5 seconds for mission {mission_id}, forcing cancellation")
                # Tasks that didn't finish will remain cancelled
            
            # Count how many were actually cancelled vs completed
            cancelled_count = sum(1 for task in tasks_to_cancel if task.cancelled())
            completed_count = sum(1 for task in tasks_to_cancel if task.done() and not task.cancelled())
            logger.info(f"Mission {mission_id}: {cancelled_count} tasks cancelled, {completed_count} completed")
        
        # Clean up task registries
        if mission_id in self.mission_tasks:
            del self.mission_tasks[mission_id]
        if mission_id in self.mission_subtasks:
            del self.mission_subtasks[mission_id]
        
        await self.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name="AgentController",
            action="Pause Mission",
            status="success"
        )
        logger.info(f"Mission {mission_id} stopped and all tasks cancelled.")

    async def pause_mission(self, mission_id: str):
        """Pauses a running mission."""
        logger.info(f"Pausing mission {mission_id}...")
        await self.context_manager.update_mission_status(mission_id, "paused")
        await self.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name="AgentController",
            action="Pause Mission",
            status="success"
        )
        logger.info(f"Mission {mission_id} paused.")

    # Delegate methods to the appropriate managers
    async def refine_questions(self, mission_id: str, user_feedback: str, current_questions: List[str], 
                              log_queue: Optional[queue.Queue] = None, 
                              update_callback: Optional[Callable[[queue.Queue, Any], None]] = None) -> Tuple[List[str], str]:
        return await self.user_interaction_manager.refine_questions(
            mission_id, user_feedback, current_questions, log_queue, update_callback
        )

    async def confirm_questions_and_run(self, mission_id: str, final_questions: List[str], tool_selection: Dict[str, bool],
                                       log_queue: Optional[queue.Queue] = None,
                                       update_callback: Optional[Callable[[queue.Queue, Any], None]] = None) -> bool:
        return await self.user_interaction_manager.confirm_questions_and_run(
            mission_id, final_questions, tool_selection, log_queue, update_callback
        )

    async def handle_user_message(self, user_message: str, chat_history: List[Tuple[str, str]],
                                 chat_id: str,
                                 mission_id: Optional[str] = None,
                                 log_queue: Optional[queue.Queue] = None,
                                 update_callback: Optional[Callable[[queue.Queue, Any], None]] = None,
                                 use_web_search: Optional[bool] = True,
                                 document_group_id: Optional[str] = None,
                                 auto_create_document_group: Optional[bool] = False) -> Dict[str, Any]:
        return await self.user_interaction_manager.handle_user_message(
            user_message, chat_history, chat_id, mission_id, log_queue, update_callback,
            use_web_search, document_group_id, auto_create_document_group
        )

    def get_final_report(self, mission_id: str) -> Optional[str]:
        """Retrieves the final report for a completed mission."""
        mission = self.context_manager.get_mission_context(mission_id)
        if mission and mission.status == "completed":
            return mission.final_report
        elif mission:
            logger.warning(f"Cannot get final report for mission {mission_id}: Status is '{mission.status}'.")
            return None
        else:
            logger.error(f"Mission context not found for {mission_id} when retrieving final report.")
            return None
