import logging
from typing import Dict, Any, Optional, List, Type, Callable, Tuple, Awaitable, Set
import asyncio
import queue
from collections import deque

from ai_researcher import config
from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT
from ai_researcher.agentic_layer.context_manager import ContextManager, MissionContext, ExecutionLogEntry
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

class AgentController:
    """
    Orchestrates the research process by managing agents, context, and plan execution.
    This is the main controller class that coordinates all the components.
    """
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        context_manager: ContextManager,
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

        logger.info(f"AgentController initialized with agents, context manager, tool registry.")
        logger.info(f"  Research Loop Settings: max_research_cycles_per_section={self.max_research_cycles_per_section}")
        logger.info(f"  Writing Settings: writing_passes={config.WRITING_PASSES}")
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
    async def run_mission(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ):
        """
        Runs the full research mission using the workflow.
        Accepts optional queue and callback function to report execution steps and UI feedback.
        """
        logger.info(f"Executing mission {mission_id} with new workflow...")
        self.context_manager.update_mission_status(mission_id, "running")

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
            self.context_manager.update_mission_status(mission_id, "failed", "Mission context not found at start.")
            return
        
        user_request = mission_context.user_request

        # Main Execution Block with Top-Level Error Handling
        try:
            # Step 1: Initial Request Analysis
            analysis_result = await self.user_interaction_manager.analyze_request_type(
                mission_id=mission_id,
                user_request=user_request,
                log_queue=log_queue,
                update_callback=update_callback
            )

            # Step 2: Goal Pad & Thought Pad Initialization
            initial_thought_content = f"Starting mission. Core user request: {user_request[:150]}..."
            self.context_manager.add_thought(mission_id, "AgentController", initial_thought_content)
            logger.info(f"Added initial focus thought to thought_pad for mission {mission_id}.")

            if analysis_result:
                logger.info(f"Initializing goal pad for mission {mission_id} based on analysis.")
                try:
                    # Add original request as a goal
                    self.context_manager.add_goal(mission_id, user_request)
                    # Add analysis results as goals
                    self.context_manager.add_goal(mission_id, f"Request Type is {analysis_result.request_type}")
                    self.context_manager.add_goal(mission_id, f"Target Tone is {analysis_result.target_tone}")
                    self.context_manager.add_goal(mission_id, f"Target Audience is {analysis_result.target_audience}")
                    self.context_manager.add_goal(mission_id, f"Requested Length is {analysis_result.requested_length}")
                    self.context_manager.add_goal(mission_id, f"Requested Format is {analysis_result.requested_format}")
                    # Add preferred source types as a goal if present
                    if analysis_result.preferred_source_types:
                        self.context_manager.add_goal(mission_id, f"Preferred Source Types: {analysis_result.preferred_source_types}")
                        logger.info(f"Added preferred source types '{analysis_result.preferred_source_types}' to goal pad.")
                    logger.info("Added analysis results to goal pad.")
                except Exception as goal_exc:
                    logger.error(f"Failed to add analysis results to goal pad for mission {mission_id}: {goal_exc}", exc_info=True)
                    self.context_manager.log_execution_step(
                        mission_id, "AgentController", "Initialize Goal Pad",
                        status="warning", error_message=f"Failed to add goals: {goal_exc}",
                        log_queue=log_queue, update_callback=update_callback
                    )
            else:
                logger.warning(f"Request analysis failed for mission {mission_id}. Proceeding without analysis goals.")
                self.context_manager.add_goal(mission_id, user_request)

            # Create Mission-Specific Feedback Callback
            mission_feedback_callback = None
            if update_callback and log_queue:
                def _feedback_callback_impl(log_queue_arg, feedback_data: Dict[str, Any]):
                    try:
                        update_callback(log_queue_arg, feedback_data, mission_id, None)
                    except Exception as e:
                        logger.error(f"Error calling update_callback with feedback message: {e}", exc_info=True)
                mission_feedback_callback = _feedback_callback_impl

            # Phase 1: Initial Research Phase
            mission_context = self.context_manager.get_mission_context(mission_id)
            user_request = mission_context.user_request
            tool_selection = mission_context.metadata.get("tool_selection", {'local_rag': True, 'web_search': True})
            final_questions = mission_context.metadata.get("final_questions")

            if not final_questions:
                logger.error(f"Cannot start research phase: Final questions not found in metadata for mission {mission_id}.")
                self.context_manager.update_mission_status(mission_id, "failed", "Final questions missing before research phase.")
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
                self.context_manager.update_mission_status(mission_id, "failed", "Preliminary outline generation failed.")
                return
            else:
                self.context_manager.store_plan(mission_id, preliminary_plan)
                logger.info(f"Successfully generated and stored preliminary outline for mission {mission_id}.")

            # Phase 2b: Execute Research Plan
            # Check if mission was stopped or paused before plan execution
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} before plan execution. Aborting.")
                return

            plan_execution_success = await self.research_manager.execute_research_plan(
                mission_id=mission_id,
                plan=preliminary_plan,
                log_queue=log_queue,
                update_callback=update_callback
            )
            
            # Check if mission was stopped or paused during plan execution
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} during plan execution. Aborting.")
                return
                
            if not plan_execution_success:
                logger.error(f"Research plan execution phase failed for mission {mission_id}. Aborting.")
                if self.context_manager.get_mission_context(mission_id).status != "failed":
                    self.context_manager.update_mission_status(mission_id, "failed", "Research plan execution failed.")
                return

            # Phase 3: Prepare Notes for Writing (Conditional based on config)
            active_goals = self.context_manager.get_active_goals(mission_id)
            full_note_assignments: Optional[FullNoteAssignments] = None

            if not config.SKIP_FINAL_REPLANNING:
                logger.info(f"Running final outline refinement and note reassignment for mission {mission_id}.")
                self.context_manager.log_execution_step(
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
                    self.context_manager.update_mission_status(mission_id, "failed", "Standard note assignment phase failed critically.")
                    return
                elif not full_note_assignments.assignments:
                    logger.warning(f"Standard note assignment phase for mission {mission_id} resulted in empty assignments. Proceeding, but writing phase might be affected.")
                
                self.context_manager.log_execution_step(
                    mission_id=mission_id, agent_name="AgentController", action="Prepare Notes (Standard)",
                    status="success", output_summary=f"Completed standard note reassignment. {len(full_note_assignments.assignments)} sections assigned.", # Use output_summary
                    log_queue=log_queue, update_callback=update_callback
                )

            else:
                logger.info(f"Skipping final replanning. Running redundancy reflection for mission {mission_id}.")
                self.context_manager.log_execution_step(
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
                         self.context_manager.update_mission_status(mission_id, "failed", "Plan not found when skipping replanning.")
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
                    process_empty_sections(current_plan.outline)
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
                            self.context_manager.update_mission_status(mission_id, "failed", "Plan not found when skipping replanning.")
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
                        self.context_manager.log_execution_step(
                            mission_id, "AgentController", "Prepare Notes (Skip Replanning)",
                            status="failure", error_message=f"Redundancy reflection failed: {reflect_err}",
                            log_queue=log_queue, update_callback=update_callback
                        )
                        self.context_manager.update_mission_status(mission_id, "failed", "Redundancy reflection failed.")
                        return # Abort on reflection error

                self.context_manager.log_execution_step(
                    mission_id=mission_id, agent_name="AgentController", action="Prepare Notes (Skip Replanning)",
                    status="success", output_summary=f"Completed redundancy reflection. Prepared notes for writing.", # Use output_summary
                    log_queue=log_queue, update_callback=update_callback
                )

            # Ensure full_note_assignments is not None before proceeding
            if full_note_assignments is None:
                 logger.error(f"Critical error: full_note_assignments is None before writing phase for mission {mission_id}. Aborting.")
                 self.context_manager.update_mission_status(mission_id, "failed", "Note assignment structure missing before writing phase.")
                 return

            # Phase 4: Multi-Pass Writing Phase
            # Check if mission was stopped or paused before writing phase
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} before writing phase. Aborting.")
                return

            writing_success = await self.writing_manager.run_writing_phase(
                mission_id=mission_id,
                assigned_notes=full_note_assignments,
                active_goals=active_goals,
                log_queue=log_queue,
                update_callback=update_callback
            )
            if not writing_success:
                logger.error(f"Writing phase failed for mission {mission_id}. Aborting.")
                if self.context_manager.get_mission_context(mission_id).status != "failed":
                    self.context_manager.update_mission_status(mission_id, "failed", "Writing phase failed.")
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
                    self.context_manager.log_execution_step(
                        mission_id, "AgentController", "Generate Report Title",
                        status="warning", error_message="Title generation failed, proceeding without title.",
                        log_queue=log_queue, update_callback=update_callback
                    )
                else:
                    logger.info(f"Successfully generated report title for mission {mission_id}.")
            except Exception as title_e:
                logger.error(f"Error during title generation phase for mission {mission_id}: {title_e}", exc_info=True)
                self.context_manager.log_execution_step(
                    mission_id, "AgentController", "Generate Report Title",
                    status="warning", error_message=f"Exception during title generation: {title_e}",
                    log_queue=log_queue, update_callback=update_callback
                )

            # Phase 6: Citation Processing
            citation_success = self.report_generator.process_citations(
                mission_id, 
                log_queue, 
                update_callback
            )
            if not citation_success:
                logger.error(f"Citation processing failed for mission {mission_id}. Aborting.")
                if self.context_manager.get_mission_context(mission_id).status != "failed":
                    self.context_manager.update_mission_status(mission_id, "failed", "Citation processing failed.")
                return
            
            # Check if mission was stopped or paused after citation processing
            mission_context = self.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.status in ["stopped", "paused"]:
                logger.info(f"Mission {mission_id} was {mission_context.status} after citation processing. Aborting.")
                return

            # Final status check
            final_status = self.context_manager.get_mission_context(mission_id).status
            logger.info(f"Mission {mission_id} execution finished with final status: {final_status}")

        except Exception as e:
            err_msg = f"Critical error during mission execution: {e}"
            logger.error(err_msg, exc_info=True)
            if self.context_manager.get_mission_context(mission_id).status != "failed":
                self.context_manager.update_mission_status(mission_id, "failed", err_msg)
            if update_callback and log_queue:
                try:
                    error_log = ExecutionLogEntry(
                        mission_id=mission_id, agent_name="AgentController", action="Run Mission (Top Level)",
                        status="failure", error_message=f"Critical error: {e}"
                    )
                    update_callback(log_queue, error_log)
                except Exception as cb_err:
                    logger.error(f"Failed to log top-level mission error via callback: {cb_err}")

    def stop_mission(self, mission_id: str):
        """Stops a running mission."""
        logger.info(f"Stopping mission {mission_id}...")
        self.context_manager.update_mission_status(mission_id, "stopped")
        self.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name="AgentController",
            action="Stop Mission",
            status="success"
        )
        logger.info(f"Mission {mission_id} stopped.")

    def pause_mission(self, mission_id: str):
        """Pauses a running mission."""
        logger.info(f"Pausing mission {mission_id}...")
        self.context_manager.update_mission_status(mission_id, "paused")
        self.context_manager.log_execution_step(
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
                                 document_group_id: Optional[str] = None) -> Dict[str, Any]:
        return await self.user_interaction_manager.handle_user_message(
            user_message, chat_history, chat_id, mission_id, log_queue, update_callback,
            use_web_search, document_group_id
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
