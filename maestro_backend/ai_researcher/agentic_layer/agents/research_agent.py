import json
import logging
import re
import asyncio
import queue # <-- Add queue import
import inspect # <-- Add inspect import
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable, Awaitable, Set # Added Callable, Awaitable, Set
from pydantic import ValidationError
from collections import defaultdict, deque # Added defaultdict and deque

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    sanitize_json_string,
    parse_json_string_recursively
)

# Use absolute imports starting from the top-level package 'ai_researcher'
import ai_researcher # Import the package itself to find its path
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher import config # Import config to get model mapping
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.core_rag.query_preparer import QueryPreparer, QueryRewritingTechnique # <-- Import QueryPreparer
from ai_researcher.agentic_layer.schemas.planning import PlanStep, ActionType, ReportSection
from ai_researcher.agentic_layer.schemas.research import ResearchFindings, ResearchResultResponse, Source
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.goal import GoalEntry # Import GoalEntry
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Added import
# from ai_researcher.agentic_layer.context_manager import ContextManager

logger = logging.getLogger(__name__) # <-- Initialize logger

class ResearchAgent(BaseAgent):
    """
    Agent responsible for executing research steps: using tools for information
    gathering (document search, web search, calculation) and synthesizing results.
    Can also synthesize existing notes if no specific focus questions are provided.
    """
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        tool_registry: ToolRegistry,
        query_preparer: QueryPreparer, # <-- Add QueryPreparer dependency
        # context_manager: ContextManager,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # Type hint already correct, ensuring it stays
        controller: Optional[Any] = None # Add controller parameter
    ):
        agent_name = "ResearchAgent"
        # Determine the correct model name based on the 'research' role from config
        research_model_type = config.AGENT_ROLE_MODEL_TYPE.get("research", "mid") # Default to mid if not specified
        if research_model_type == "fast":
            provider = config.FAST_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["fast_model"]
        elif research_model_type == "mid": # Explicitly check for mid
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]
        elif research_model_type == "intelligent": # Add check for intelligent
            provider = config.INTELLIGENT_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["intelligent_model"]
        else: # Fallback if type is unknown
            logger.warning(f"Unknown research model type '{research_model_type}', falling back to mid.")
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]

        # Override with specific model_name if provided by the user during instantiation
        effective_model_name = model_name or effective_model_name

        super().__init__(
            agent_name=agent_name,
            model_dispatcher=model_dispatcher,
            tool_registry=tool_registry,
            system_prompt=system_prompt or self._default_system_prompt(),
            model_name=effective_model_name
        )
        self.query_preparer = query_preparer # <-- Store QueryPreparer
        self.feedback_callback = feedback_callback # <-- Store feedback_callback
        self.controller = controller # <-- Store controller
        self.mission_id = None # Initialize mission_id as None
        # self.context_manager = context_manager
        
        # Initialize paragraph split pattern for content windows
        self._paragraph_split_pattern = re.compile(r'(\n\s*\n+)')

    def _default_system_prompt(self) -> str:
        """Generates the default system prompt for the Research Agent."""
        # Updated prompt to include synthesis task and active goals
        return """You are a specialized Research Agent. Your primary goal is to gather and synthesize information relevant to a specific research section topic, ensuring alignment with the overall mission goals.

**Active Mission Goals:**
- The user prompt will contain a section listing the 'Overall Mission Goals'.
- **CRITICAL:** You MUST consult these goals (e.g., original request, tone, audience) at every step: when generating search queries, evaluating relevance of information, and synthesizing notes or summaries.
- Ensure your outputs (notes, synthesis) directly contribute to achieving these active goals. Prioritize information that addresses open goals.
- Review the 'Recent Thoughts' (if provided in the user prompt) to maintain focus and build on previous insights.

You will be given a section topic/goal and potentially specific focus questions or existing notes.

**Mode 1: Answering Focus Questions**
If you receive 'Focus Questions':
1. Generate relevant search queries based on the section goal AND the focus questions.
2. Execute searches using available tools (`document_search`, `web_search`).
3. Analyze the search results (snippets or full documents if necessary via `read_full_document`).
4. For each piece of information found that DIRECTLY answers a focus question, create a structured "Note".
5. Return a list of generated Note objects. Focus on accuracy, relevance to the questions, and capturing source info.

**Mode 2: Synthesizing Existing Notes**
If you DO NOT receive 'Focus Questions' but receive 'Existing Relevant Notes':
1. Review the 'Existing Relevant Notes' provided for the section.
2. Synthesize the key information related to the 'Section Goal'.
3. Identify any obvious gaps or contradictions if present.
4. Produce a concise summary (1-3 sentences) of the synthesized information as a new 'internal' note.
5. If the existing notes are insufficient or irrelevant, state that clearly in the output.
6. Return ONLY the single synthesis note (or the statement of insufficiency).

**General Guidelines:**
- Focus on accuracy and relevance to the section topic/goal or specific questions.
- Capture source information meticulously for later citation when generating notes from searches. Use the `[doc_id]` format as specified in note generation prompts.
- Use the 'Agent Scratchpad' for context about previous actions or thoughts. Keep your own contributions to the scratchpad concise.
- Consult 'Recent Thoughts' (if provided) for additional context and focus.
- **CRITICAL: Base ALL generated notes and synthesis *strictly* on the information found in the provided search results or existing notes. DO NOT use any external knowledge or information not present in the context provided to you.**
"""

    # --- Helper Methods ---

    # --- NEW: Helper for tracing original sources ---
    def _get_aggregated_original_sources(self, parent_note_ids: List[str], all_notes_map: Dict[str, Note]) -> List[Dict[str, Any]]:
        """
        Traces back through note lineage to find unique original sources (document/web).
        """
        original_sources = {} # Use dict to store unique sources by source_id
        queue = deque(parent_note_ids)
        processed_ids = set(parent_note_ids)

        while queue:
            note_id = queue.popleft()
            note = all_notes_map.get(note_id)
            if not note:
                logger.warning(f"Note ID '{note_id}' not found in all_notes_map during source aggregation.")
                continue

            if note.source_type in ["document", "web"]:
                # Found an original source, store its essential info
                # Use doc_id for documents, URL for web
                original_id = note.source_id.split('_')[0] if note.source_type == "document" else note.source_id
                if original_id not in original_sources:
                     # Store a copy of the metadata to avoid modifying the original note's metadata
                     metadata_copy = note.source_metadata.copy()
                     # Optional: Clean up metadata further if needed (e.g., remove large fields like 'snippet' if not needed for citation)
                     # metadata_copy.pop('snippet', None)
                     # metadata_copy.pop('overlapping_chunks', None) # Example cleanup
                     original_sources[original_id] = {
                          "source_type": note.source_type,
                          "source_id": original_id, # Store the base ID
                          "source_metadata": metadata_copy # Store relevant metadata copy
                     }
            elif note.source_type == "internal" and hasattr(note.source_metadata, "synthesized_from_notes"):
                # Follow the synthesis chain
                for next_note_id in getattr(note.source_metadata, "synthesized_from_notes", None) or []:
                    if next_note_id not in processed_ids:
                        processed_ids.add(next_note_id)
                        queue.append(next_note_id)

        return list(original_sources.values()) # Return list of unique source dicts
    # --- End Helper for tracing original sources ---

    # --- Core Method ---
    async def run( # Fully async now
        self,
        mission_id: str,
        section: ReportSection,
        focus_questions: Optional[List[str]] = None, # <-- Add optional focus_questions
        existing_notes: Optional[List[Note]] = None,
        agent_scratchpad: Optional[str] = None,
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # Type hint already correct, ensuring it stays
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue
        update_callback: Optional[Callable] = None, # <-- ADD update_callback
        tool_registry: Optional[ToolRegistry] = None, # <-- Add optional tool_registry override
        all_mission_notes: Optional[List[Note]] = None, # <-- NEW: Add all notes for synthesis trace-back
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None # <-- NEW: Add active thoughts
    ) -> Tuple[List[Note], Dict[str, Any], Optional[str]]:
        """
        Generates research notes for a specific section, guided by active goals, using the provided tool_registry if available.
        If focus_questions are provided, it performs searches and generates notes from new findings.
        If focus_questions are NOT provided, it attempts to synthesize existing_notes for the section.
        Returns the notes and details about the execution (model calls, tool calls).

        Args:
            mission_id: The ID of the current mission.
            section: The ReportSection object defining the section to research.
            focus_questions: Optional list of specific questions to focus on.
            existing_notes: Optional list of notes already gathered for this section (used for synthesis).
            agent_scratchpad: Optional string containing the current scratchpad content.
            all_mission_notes: Optional list of all notes in the mission (for synthesis trace-back).
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.

        Returns:
            A tuple containing:
            - A list of generated Note objects (can be search-based or synthesis-based).
            - A dictionary containing execution details ('model_calls', 'tool_calls', 'file_interactions').
            - An optional string to update the agent scratchpad.
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        log_prefix = f"{self.agent_name} (Section {section.section_id})"
        print(f"\n{log_prefix}: Generating notes for Title: '{section.title}'")
        print(f"{log_prefix}: Section Topic/Goal: {section.description}")
        if focus_questions:
            print(f"{log_prefix}: Focusing on questions: {focus_questions}")
        else:
            print(f"{log_prefix}: No focus questions. Attempting synthesis of existing notes.")

        all_generated_notes: List[Note] = []
        model_calls_list: List[Dict[str, Any]] = []
        tool_calls_list: List[Dict[str, Any]] = []
        file_interactions_list: List[str] = []
        scratchpad_update: Optional[str] = None # Initialize scratchpad update

        # --- Conditional Logic: Search or Synthesize ---
        if focus_questions:
            # --- Perform Search-Based Research ---
            logger.info(f"{log_prefix}: Performing search-based research for focus questions.")
            # 1. Generate Search Queries asynchronously
            # TODO: Make query techniques configurable
            query_techniques: List[QueryRewritingTechnique] = ["sub_query", "step_back"] # Example techniques
            search_queries, preparer_model_details = await self._generate_section_queries(
                section=section,
                techniques=query_techniques,
                focus_questions=focus_questions,
                active_goals=active_goals, # <-- Pass active_goals
                log_queue=log_queue, # <-- Pass log_queue
                update_callback=update_callback # <-- Pass update_callback
            )
            model_calls_list.extend(preparer_model_details) # Add details from preparer

            if not search_queries:
                print(f"{log_prefix}: No search queries generated.")
                # Return empty list and collected details
                return all_generated_notes, {"model_calls": model_calls_list, "tool_calls": tool_calls_list, "file_interactions": file_interactions_list}, scratchpad_update

            # 2. Execute Searches (Doc & Web) in parallel using the provided/default registry
            search_results, search_tool_calls = await self._execute_searches_parallel(
                search_queries,
                update_callback=feedback_callback, # Pass callback
                log_queue=log_queue, # Pass queue
                tool_registry_override=tool_registry, # Pass the override
                active_goals=active_goals # Pass active_goals
            )
            tool_calls_list.extend(search_tool_calls)

            # 3. Process Results and Generate Notes in parallel
            if not search_results.get("document") and not search_results.get("web"):
                print(f"{log_prefix}: No search results found.")
                # Return empty list and collected details
                return all_generated_notes, {"model_calls": model_calls_list, "tool_calls": tool_calls_list, "file_interactions": file_interactions_list}, scratchpad_update

            # --- Process Search Results ---
            note_generation_tasks = []
            processed_source_ids = set() # Track processed web sources

            # --- NEW: Group Document Results by Filename ---
            doc_results_by_file = defaultdict(list)
            for doc_result in search_results.get("document", []):
                filename = doc_result.get("metadata", {}).get("original_filename")
                if filename:
                    doc_results_by_file[filename].append(doc_result)
                else:
                    logger.warning(f"Document result missing original_filename in metadata: {doc_result.get('id')}")

            # --- Process Each Document (Extract Windows, Schedule Note Gen) ---
            for filename, chunks in doc_results_by_file.items():
                logger.info(f"Processing {len(chunks)} chunks from document: {filename}")
                # Extract content windows for this document, passing the callback and registry override
                content_windows = await self._extract_content_windows(
                    filename,
                    chunks,
                    feedback_callback,
                    log_queue=log_queue, # <-- Pass log_queue
                    tool_registry_override=tool_registry # Pass the override
                )

                # Schedule note generation for each window
                for window in content_windows:
                    # Create a unique window ID (still useful internally if needed) and get doc_id
                    first_chunk_id = window["original_chunk_ids"][0] if window["original_chunk_ids"] else "unknown"
                    window_source_id = f"window_{first_chunk_id}" # Keep for potential internal use
                    
                    # Use the enhanced window metadata
                    window_metadata = {
                        "beginning_omitted": window["beginning_omitted"],
                        "end_omitted": window["end_omitted"],
                        "original_chunk_ids": window["original_chunk_ids"],
                        "window_position": {
                            "start": window["window_metadata"]["start_pos"],
                            "end": window["window_metadata"]["end_pos"]
                        },
                        "overlapping_chunks": window["window_metadata"]["overlapping_chunks"] # This metadata will be cleaned later
                    }
                    
                    # --- Get doc_id for the primary source_id ---
                    doc_id_for_note = "unknown_doc"
                    if window_metadata["overlapping_chunks"]:
                        doc_id_for_note = window_metadata["overlapping_chunks"][0].get("doc_id", "unknown_doc")
                    # --- End get doc_id ---

                    note_generation_tasks.append(
                        self._process_single_result(
                            section=section,
                            focus_questions=focus_questions,
                            active_goals=active_goals, # <-- Pass active_goals
                            active_thoughts=active_thoughts, # <-- ADDED active_thoughts
                            result_item={ # Construct a result-like item for the window
                                "content": window["content"],
                                "source_id": doc_id_for_note, # <<< Use doc_id instead of window_id
                                "metadata": window_metadata # Pass full metadata for now, will be cleaned in _process_single_result if needed
                            },
                            source_type="document_window", # Use a distinct type
                            feedback_callback=feedback_callback,
                            log_queue=log_queue, # <-- Pass log_queue
                            update_callback=update_callback, # <-- Pass update_callback
                            is_initial_exploration=False, # Assuming structured research here
                            tool_registry_override=tool_registry # Pass the override
                        )
                    )

            # --- Process Web Results (Remains Similar) ---
            for web_result in search_results.get("web", []):
                web_source_id = web_result.get("url", "unknown_url")
                if web_source_id in processed_source_ids: continue
                processed_source_ids.add(web_source_id)
                note_generation_tasks.append(
                    self._process_single_result(
                        section=section,
                        focus_questions=focus_questions,
                        active_goals=active_goals, # <-- Pass active_goals
                        result_item=web_result, # Pass the original web result item
                        source_type="web",
                        feedback_callback=feedback_callback,
                        log_queue=log_queue, # <-- Pass log_queue
                        update_callback=update_callback, # <-- Pass update_callback
                        is_initial_exploration=False, # Assuming structured research here
                        tool_registry_override=tool_registry, # Pass the override
                        active_thoughts=active_thoughts # <-- ADDED active_thoughts
                    )
                )

            # --- Execute Note Generation Concurrently ---
            if note_generation_tasks:
                print(f"{log_prefix}: Generating notes from {len(note_generation_tasks)} content sources (windows/web) in parallel...")
                note_processing_results = await asyncio.gather(*note_generation_tasks)

                # Collect results from parallel processing
                for note, note_model_details, _ in note_processing_results: # Unpack 3 values, ignore context here
                    # read_tool_call and file_read are handled within _extract_content_windows
                    if note:
                        all_generated_notes.append(note)
                    if note_model_details:
                        model_calls_list.append(note_model_details)
                    # Tool calls/file reads happened during window extraction
            else:
                print(f"{log_prefix}: No content windows or web results to generate notes from.")


            print(f"{log_prefix}: Finished generating notes from search. Found {len(all_generated_notes)} notes.")
            # Determine scratchpad update based on action taken (INSIDE the 'if focus_questions' block)
            scratchpad_update = f"Performed search-based research for section '{section.section_id}' focusing on {len(focus_questions)} questions. Found {len(all_generated_notes)} notes."

        else: # This 'else' corresponds to the 'if focus_questions:' block
            # --- Cycle 1 (No Focus Questions): Proactive Search Only ---
            # Synthesis of existing notes is disabled as per user request.
            logger.info(f"{log_prefix}: Cycle 1: No focus questions provided. Performing proactive search based on section goal (synthesis disabled).")
            scratchpad_parts = [] # Collect parts for the final scratchpad update
            scratchpad_parts.append("Synthesis of existing notes skipped.") # Add note about skipping synthesis

            # Perform Proactive Search based on Section Goal
            logger.info(f"{log_prefix}: Performing proactive search based on section goal.")
            # Use simpler query techniques for proactive search? Or standard? Let's use standard for now.
            proactive_query_techniques: List[QueryRewritingTechnique] = ["sub_query", "step_back"]
            proactive_search_queries, proactive_preparer_details = await self._generate_section_queries(
                section=section,
                techniques=proactive_query_techniques,
                focus_questions=None, # No focus questions here
                active_goals=active_goals, # <-- Pass active_goals
                log_queue=log_queue, # <-- Pass log_queue
                update_callback=update_callback # <-- Pass update_callback
            )
            if proactive_preparer_details: model_calls_list.extend(proactive_preparer_details)

            if not proactive_search_queries:
                logger.warning(f"{log_prefix}: No proactive search queries generated.")
                scratchpad_parts.append("No proactive search queries generated.")
            else:
                # Execute searches using the provided/default registry
                proactive_search_results, proactive_search_tool_calls = await self._execute_searches_parallel(
                    proactive_search_queries,
                    update_callback=feedback_callback, # Pass callback
                    log_queue=log_queue, # Pass queue
                    tool_registry_override=tool_registry, # Pass the override
                    active_goals=active_goals # Pass active_goals
                )
                if proactive_search_tool_calls: tool_calls_list.extend(proactive_search_tool_calls)

                # Process results and generate notes
                if not proactive_search_results.get("document") and not proactive_search_results.get("web"):
                    logger.info(f"{log_prefix}: No proactive search results found.")
                    scratchpad_parts.append("No proactive search results found.")
                else:
                    proactive_note_tasks = []
                    processed_proactive_ids = set()

                    # --- NEW: Group Document Results by Filename (Cycle 1) ---
                    proactive_doc_results_by_file = defaultdict(list)
                    for doc_result in proactive_search_results.get("document", []):
                        filename = doc_result.get("metadata", {}).get("original_filename")
                        if filename:
                            proactive_doc_results_by_file[filename].append(doc_result)
                        else:
                            logger.warning(f"Proactive search: Document result missing original_filename: {doc_result.get('id')}")

                    # --- Process Each Document (Extract Windows, Schedule Note Gen - Cycle 1) ---
                    for filename, chunks in proactive_doc_results_by_file.items():
                        logger.info(f"Proactive search: Processing {len(chunks)} chunks from document: {filename}")
                        # Pass callback and registry override
                        content_windows = await self._extract_content_windows(
                            filename,
                            chunks,
                    feedback_callback,
                    log_queue=log_queue, # <-- Pass log_queue
                    tool_registry_override=tool_registry # Pass the override
                )

                        for window in content_windows:
                            # Create a unique window ID (still useful internally if needed) and get doc_id
                            first_chunk_id = window["original_chunk_ids"][0] if window["original_chunk_ids"] else "unknown"
                            window_source_id = f"window_{first_chunk_id}" # Keep for potential internal use
                            
                            # Use the enhanced window metadata
                            window_metadata = {
                                "beginning_omitted": window["beginning_omitted"],
                                "end_omitted": window["end_omitted"],
                                "original_chunk_ids": window["original_chunk_ids"],
                                "window_position": {
                                    "start": window["window_metadata"]["start_pos"],
                                    "end": window["window_metadata"]["end_pos"]
                                },
                                "overlapping_chunks": window["window_metadata"]["overlapping_chunks"] # This metadata will be cleaned later
                            }
                            
                            # --- Get doc_id for the primary source_id ---
                            doc_id_for_note = "unknown_doc"
                            if window_metadata["overlapping_chunks"]:
                                doc_id_for_note = window_metadata["overlapping_chunks"][0].get("doc_id", "unknown_doc")
                            # --- End get doc_id ---

                            proactive_note_tasks.append(
                                self._process_single_result(
                                    section=section,
                                    focus_questions=None, # No specific focus Qs
                                    active_goals=active_goals, # <-- Pass active_goals
                                    result_item={ # Construct window item
                                        "content": window["content"],
                                        "source_id": doc_id_for_note, # <<< Use doc_id instead of window_id
                                        "metadata": window_metadata # Pass full metadata for now, will be cleaned in _process_single_result if needed
                                    },
                                    source_type="document_window", # Use distinct type
                                    is_initial_exploration=False, # Structured research
                                    feedback_callback=feedback_callback,
                                    log_queue=log_queue, # <-- Pass log_queue
                                    tool_registry_override=tool_registry, # Pass the override
                                    active_thoughts=active_thoughts # <-- ADDED active_thoughts
                                )
                            )

                    # --- Process Web Results (Cycle 1 - Remains Similar) ---
                    for web_result in proactive_search_results.get("web", []):
                        web_source_id = web_result.get("url", "unknown_url")
                        if web_source_id in processed_proactive_ids: continue
                        processed_proactive_ids.add(web_source_id)
                        proactive_note_tasks.append(
                                self._process_single_result(
                                    section=section,
                                    focus_questions=None, # No specific focus Qs
                                    active_goals=active_goals, # <-- Pass active_goals
                                    result_item=web_result, # Pass original web item
                                    source_type="web",
                                    is_initial_exploration=False, # Structured research
                                    feedback_callback=feedback_callback,
                                    log_queue=log_queue, # <-- Pass log_queue
                                    tool_registry_override=tool_registry, # Pass the override
                                    active_thoughts=active_thoughts # <-- ADDED active_thoughts
                                )
                            )

                    # --- Execute Note Generation Concurrently (Cycle 1) ---
                    if proactive_note_tasks:
                        logger.info(f"{log_prefix}: Generating notes from proactive search ({len(proactive_note_tasks)} sources)...")
                        proactive_note_results = await asyncio.gather(*proactive_note_tasks)

                        # Collect results
                        proactive_notes_generated = 0
                        # --- Add logging for gather results ---
                        logger.info(f"Processing {len(proactive_note_results)} results from proactive note generation gather.")
                        for i, result_tuple in enumerate(proactive_note_results):
                            logger.info(f"Proactive note result {i}: Type={type(result_tuple)}, Value={str(result_tuple)[:200]}...") # Log type and preview
                            # Unpack 3 values, ignore context here
                            if isinstance(result_tuple, tuple) and len(result_tuple) == 3:
                                note, note_model_details, _ = result_tuple # Unpack if valid tuple
                                if note:
                                    all_generated_notes.append(note)
                                    proactive_notes_generated += 1
                                if note_model_details: model_calls_list.append(note_model_details)
                            else:
                                logger.error(f"Unexpected result format from proactive note generation task {i}: {result_tuple}")
                        # --- End added logging ---
                            # Tool calls/file reads handled in _extract_content_windows
                    else:
                        logger.info(f"{log_prefix}: No proactive content windows or web results to generate notes from.")

                    logger.info(f"{log_prefix}: Finished generating notes from proactive search. Found {proactive_notes_generated} notes.")
                    scratchpad_parts.append(f"Proactive search found {proactive_notes_generated} notes.")

            # Combine scratchpad updates
            scratchpad_update = f"Cycle 1 for section '{section.section_id}': " + " ".join(scratchpad_parts)


        # --- Return aggregated results ---
        research_details = {
            "model_calls": model_calls_list,
            "tool_calls": tool_calls_list, # Note: This might be less accurate now for docs
            "file_interactions": file_interactions_list # Note: This might be less accurate now for docs
        }
        return all_generated_notes, research_details, scratchpad_update


    # --- NEW: Method specifically for testing to capture context ---
    async def run_and_capture_context(
        self,
        mission_id: str,
        section: ReportSection,
        focus_questions: List[str], # Required for this testing method
        agent_scratchpad: Optional[str] = None,
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable] = None,
        tool_registry: Optional[ToolRegistry] = None,
        model: Optional[str] = None, # <<< RE-ADD model parameter >>>
        active_goals: Optional[List[GoalEntry]] = None, # <-- ADD active_goals
        active_thoughts: Optional[List[ThoughtEntry]] = None # <-- ADD active_thoughts
    ) -> Tuple[List[Tuple[Note, str]], Dict[str, Any], Optional[str]]:
        """
        Similar to run(), but specifically for search-based research with focus questions,
        and designed to return the generated notes along with the context used to generate them.
        Used primarily for evaluation/testing purposes.

        Returns:
            A tuple containing:
            - A list of (Note, context_used) tuples.
            - A dictionary containing execution details ('model_calls', 'tool_calls', 'file_interactions').
            - An optional string to update the agent scratchpad.
        """
        self.mission_id = mission_id
        log_prefix = f"{self.agent_name} [Test Context Capture] (Section {section.section_id})"
        print(f"\n{log_prefix}: Generating notes with context capture for Title: '{section.title}'")
        print(f"{log_prefix}: Focusing on questions: {focus_questions}")

        notes_with_context: List[Tuple[Note, str]] = [] # Store (Note, context) tuples
        model_calls_list: List[Dict[str, Any]] = []
        tool_calls_list: List[Dict[str, Any]] = []
        file_interactions_list: List[str] = []
        scratchpad_update: Optional[str] = None

        # --- Perform Search-Based Research (Copied & Adapted from run()) ---
        logger.info(f"{log_prefix}: Performing search-based research for focus questions.")
        query_techniques: List[QueryRewritingTechnique] = ["sub_query", "step_back"]
        search_queries, preparer_model_details = await self._generate_section_queries(
            section, 
            query_techniques, 
            focus_questions,
            log_queue=log_queue,
            update_callback=update_callback
        )
        model_calls_list.extend(preparer_model_details)

        if not search_queries:
            print(f"{log_prefix}: No search queries generated.")
            return notes_with_context, {"model_calls": model_calls_list, "tool_calls": tool_calls_list, "file_interactions": file_interactions_list}, scratchpad_update

        search_results, search_tool_calls = await self._execute_searches_parallel(
            search_queries,
            update_callback=feedback_callback,
            log_queue=log_queue,
            tool_registry_override=tool_registry,
            active_goals=active_goals # Pass active_goals
        )
        tool_calls_list.extend(search_tool_calls)

        if not search_results.get("document") and not search_results.get("web"):
            print(f"{log_prefix}: No search results found.")
            return notes_with_context, {"model_calls": model_calls_list, "tool_calls": tool_calls_list, "file_interactions": file_interactions_list}, scratchpad_update

        note_generation_tasks = []
        processed_source_ids = set()

        doc_results_by_file = defaultdict(list)
        for doc_result in search_results.get("document", []):
            filename = doc_result.get("metadata", {}).get("original_filename")
            if filename:
                doc_results_by_file[filename].append(doc_result)
            else:
                logger.warning(f"Document result missing original_filename in metadata: {doc_result.get('id')}")

        for filename, chunks in doc_results_by_file.items():
            content_windows = await self._extract_content_windows(
                filename, chunks, feedback_callback, log_queue=log_queue, tool_registry_override=tool_registry, update_callback=update_callback
            )
            for window in content_windows:
                first_chunk_id = window["original_chunk_ids"][0] if window["original_chunk_ids"] else "unknown"
                window_metadata = {
                    "beginning_omitted": window["beginning_omitted"],
                    "end_omitted": window["end_omitted"],
                    "original_chunk_ids": window["original_chunk_ids"],
                    "window_position": {
                        "start": window["window_metadata"]["start_pos"],
                        "end": window["window_metadata"]["end_pos"]
                    },
                    "overlapping_chunks": window["window_metadata"]["overlapping_chunks"]
                }
                doc_id_for_note = "unknown_doc"
                if window_metadata["overlapping_chunks"]:
                    doc_id_for_note = window_metadata["overlapping_chunks"][0].get("doc_id", "unknown_doc")

                note_generation_tasks.append(
                    self._process_single_result(
                        section=section,
                        focus_questions=focus_questions,
                        result_item={
                            "content": window["content"],
                            "source_id": doc_id_for_note,
                            "metadata": window_metadata
                        },
                        source_type="document_window",
                        feedback_callback=feedback_callback,
                        log_queue=log_queue,
                        update_callback=update_callback,
                        is_initial_exploration=False,
                        tool_registry_override=tool_registry,
                        model=model, # <<< RE-ADD model parameter pass >>>
                        active_goals=active_goals, # <-- Pass active_goals
                        active_thoughts=active_thoughts # <-- Pass active_thoughts
                    )
                )

        for web_result in search_results.get("web", []):
            web_source_id = web_result.get("url", "unknown_url")
            if web_source_id in processed_source_ids: continue
            processed_source_ids.add(web_source_id)
            note_generation_tasks.append(
                self._process_single_result(
                    section=section,
                    focus_questions=focus_questions,
                    result_item=web_result,
                    source_type="web",
                    feedback_callback=feedback_callback,
                    log_queue=log_queue,
                        update_callback=update_callback,
                        is_initial_exploration=False,
                        tool_registry_override=tool_registry,
                        model=model, # <<< RE-ADD model parameter pass >>>
                        active_goals=active_goals, # <-- Pass active_goals
                        active_thoughts=active_thoughts # <-- Pass active_thoughts
                    )
                )

        if note_generation_tasks:
            print(f"{log_prefix}: Generating notes with context from {len(note_generation_tasks)} sources...")
            note_processing_results = await asyncio.gather(*note_generation_tasks)

            # Collect results including context
            for note, note_model_details, context_used in note_processing_results: # Unpack 3 values
                if note and context_used is not None: # Ensure context was captured
                    notes_with_context.append((note, context_used))
                if note_model_details:
                    model_calls_list.append(note_model_details)
        else:
            print(f"{log_prefix}: No content windows or web results to generate notes from.")

        print(f"{log_prefix}: Finished generating notes with context. Found {len(notes_with_context)} notes.")
        scratchpad_update = f"Performed test research with context capture for section '{section.section_id}'. Found {len(notes_with_context)} notes."

        research_details = {
            "model_calls": model_calls_list,
            "tool_calls": tool_calls_list,
            "file_interactions": file_interactions_list
        }
        return notes_with_context, research_details, scratchpad_update
    # --- End testing method ---


    async def generate_initial_questions(
        self,
        mission_id: str,
        user_request: str,
        active_goals: Optional[List[GoalEntry]] = None,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable] = None,
    ) -> Tuple[List[str], Optional[Dict[str, Any]]]:
        """
        Generates high-quality initial research questions based on the user's request
        using the 'intelligent' model.
        """
        self.mission_id = mission_id
        log_prefix = f"{self.agent_name} (Generate Initial Questions)"
        logger.info(f"{log_prefix}: Generating initial questions for request: '{user_request[:100]}...'")

        goals_str = "\n".join([f"- {g.text}" for g in active_goals]) if active_goals else "None"

        prompt = f"""
You are an expert research strategist. Your task is to analyze a user's research request and any associated goals to generate a set of 3-5 insightful, open-ended, and high-quality exploratory questions. These questions will form the foundation of a comprehensive research mission.

**User's Research Request:**
"{user_request}"

**User's Formatting/Scope Goals (if any):**
{goals_str}

**Instructions:**
1.  **Analyze the Core Topic:** Deconstruct the user's request to understand the central theme, key entities, and the underlying intent.
2.  **Consider the Goals:** Pay close attention to any specified goals regarding tone, audience, length, or format. These goals should influence the *angle* and *scope* of the questions you generate. For example, a request for a "brief summary for the general public" should lead to broader, more foundational questions than a request for a "detailed academic report for experts."
3.  **Brainstorm Insightful Questions:** Generate questions that are:
    *   **Open-ended:** Avoid simple yes/no questions.
    *   **Exploratory:** Encourage deep and broad investigation.
    *   **Non-obvious:** Go beyond the most superficial questions.
    *   **Actionable:** Frame them in a way that a research agent can tackle them.
4.  **Refine and Select:** From your brainstormed list, select the best 3-5 questions that provide a solid foundation for the research.
5.  **Output Format:** Return ONLY a JSON object with a single key "questions" containing a list of the final string questions.

**Example:**
User Request: "Tell me about the impact of remote work on cybersecurity."
User Goals: "Provide a comprehensive report for a technical audience."

**Your Output:**
```json
{{
  "questions": [
    "What are the primary attack vectors and vulnerabilities that have been amplified or newly introduced by the widespread adoption of remote work?",
    "How have traditional enterprise security models (e.g., perimeter-based defense) evolved to address the challenges of a decentralized, remote workforce?",
    "What are the key technological solutions and best practices organizations are implementing to secure remote endpoints, networks, and cloud access?",
    "What is the role of human factors, such as employee training and security awareness, in mitigating cybersecurity risks in a remote work environment?",
    "How do emerging technologies like Zero Trust Network Access (ZTNA) and Secure Access Service Edge (SASE) address the long-term security implications of hybrid and remote work models?"
  ]
}}
```

Now, generate the questions for the provided research request.
"""
        messages = [{"role": "user", "content": prompt}]
        model_details = None
        questions = []

        try:
            response, model_details = await self._call_llm(
                user_prompt=prompt,
                agent_mode="intelligent",  # Use the most capable model for this critical task
                response_format={"type": "json_object"},
                log_queue=log_queue,
                update_callback=update_callback,
                log_llm_call=False # Disable duplicate LLM call logging since this is called by controller methods that already log
            )

            if response and response.choices and response.choices[0].message.content:
                json_str = response.choices[0].message.content
                parsed_data = parse_llm_json_response(json_str)
                questions = parsed_data.get("questions", [])
                if questions and all(isinstance(q, str) for q in questions):
                    logger.info(f"{log_prefix}: Successfully generated {len(questions)} initial questions.")
                else:
                    logger.error(f"{log_prefix}: Failed to extract a valid list of questions from LLM response: {json_str}")
                    questions = [] # Reset to empty list on failure
            else:
                logger.error(f"{log_prefix}: LLM response was empty or invalid.")

        except Exception as e:
            logger.error(f"{log_prefix}: Error during initial question generation LLM call: {e}", exc_info=True)
            # Fallback to a single, simple question
            questions = [f"What are the key aspects and recent developments regarding '{user_request}'?"]
            logger.warning(f"{log_prefix}: Falling back to a single basic question due to error.")

        return questions, model_details


    # --- NEW: Method for Initial Question Exploration ---
    async def explore_question(
        self,
        question: str,
        mission_id: str,
        mission_goal: str, # NEW: Pass mission goal for context
        current_depth: int,
        max_depth: int,
        max_questions: int,
        questions_explored_count: int,
        agent_scratchpad: Optional[str] = None,
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # Type hint already correct, ensuring it stays
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue
        update_callback: Optional[Callable] = None, # <-- ADD update_callback (4-arg)
        tool_registry: Optional[ToolRegistry] = None, # <-- Add optional tool_registry override
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        active_goals: Optional[List[GoalEntry]] = None # <-- NEW: Add active goals (needed for prompt)
    ) -> Tuple[List[Tuple[Note, str]], List[str], Optional[str], Dict[str, Any]]:
        """
        Explores a single question during the initial research phase using the provided tool_registry if available.
        Generates relevant notes, identifies sub-questions, and updates the scratchpad.

        Args:
            question: The specific question to explore.
            mission_id: The ID of the current mission.
            mission_goal: The overall goal of the mission.
            current_depth: The current exploration depth.
            max_depth: The maximum allowed exploration depth.
            max_questions: The maximum number of questions to explore in total.
            questions_explored_count: The number of questions explored so far.
            agent_scratchpad: Optional current scratchpad content.
            feedback_callback: Optional callback for UI feedback.
            log_queue: Optional queue for logging.
            update_callback: Optional callback for UI updates.
            tool_registry: Optional specific tool registry to use.
            active_thoughts: Optional list of recent thoughts.

        Returns:
            Tuple: (relevant_notes_with_context, new_sub_questions, updated_scratchpad, execution_details)
                   where relevant_notes_with_context is List[Tuple[Note, str]]
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        log_prefix = f"{self.agent_name} (Explore Q Depth {current_depth})"
        print(f"\n{log_prefix}: Exploring Question: '{question}'")

        relevant_notes_with_context: List[Tuple[Note, str]] = [] # Store (Note, context_used) tuples
        new_sub_questions: List[str] = []
        updated_scratchpad: Optional[str] = agent_scratchpad # Start with current
        model_calls_list: List[Dict[str, Any]] = []
        tool_calls_list: List[Dict[str, Any]] = []
        file_interactions_list: List[str] = []

        # 1. Generate Search Queries for the specific question
        # Use simpler query prep for single question? Or reuse existing? Let's reuse for now.
        query_techniques: List[QueryRewritingTechnique] = ["simple", "sub_query", "step_back"] # Maybe just simple for initial exploration
        # Create a temporary ReportSection-like object for query generation
        temp_section_for_query = ReportSection(
            section_id=f"q_{current_depth}_{questions_explored_count}",
            title=f"Exploration: {question[:30]}...",
            description=question,
            subsections=[] # Ensure subsections is an empty list
        )
        search_queries, preparer_model_details = await self._generate_section_queries(
            section=temp_section_for_query,
            techniques=query_techniques,
            focus_questions=[question], # Focus explicitly on the question
            mission_goal=mission_goal, # Pass mission goal for context
            log_queue=log_queue, # <-- Pass log_queue
            update_callback=update_callback # <-- Pass update_callback
        )
        model_calls_list.extend(preparer_model_details)

        if not search_queries:
            print(f"{log_prefix}: No search queries generated for question.")
            return relevant_notes_with_context, new_sub_questions, updated_scratchpad, {"model_calls": model_calls_list, "tool_calls": tool_calls_list, "file_interactions": file_interactions_list}

        # 2. Execute Searches (Doc & Web) in parallel using config values
        n_doc_results_config = config.INITIAL_EXPLORATION_DOC_RESULTS
        use_reranker_config = config.INITIAL_EXPLORATION_USE_RERANKER
        # Use config for initial web results
        n_web_results_config = config.INITIAL_EXPLORATION_WEB_RESULTS
        search_results, search_tool_calls = await self._execute_searches_parallel(
            queries=search_queries,
            n_doc_results=n_doc_results_config,
            n_web_results=n_web_results_config, # Use config value
            use_doc_reranker=use_reranker_config, # Pass reranker flag for docs
            update_callback=feedback_callback, # Pass callback
            log_queue=log_queue, # Pass queue
            tool_registry_override=tool_registry, # Pass the override
            active_goals=active_goals # Pass active_goals
        )
        tool_calls_list.extend(search_tool_calls)

        # 3. Process Results and Generate *Relevant* Notes in parallel
        if not search_results.get("document") and not search_results.get("web"):
            print(f"{log_prefix}: No search results found for question.")
            return relevant_notes_with_context, new_sub_questions, updated_scratchpad, {"model_calls": model_calls_list, "tool_calls": tool_calls_list, "file_interactions": file_interactions_list}

        note_generation_tasks = []
        processed_source_ids = set()
        # Create a temporary ReportSection for passing to _process_single_result
        temp_section_for_notes = ReportSection(
             section_id=f"q_{current_depth}_{questions_explored_count}",
             title=f"Exploration: {question[:30]}...",
             description=question,
             subsections=[]
        )

        # --- NEW: Group Document Results by Filename (Initial Exploration) ---
        initial_doc_results_by_file = defaultdict(list)
        for doc_result in search_results.get("document", []):
            filename = doc_result.get("metadata", {}).get("original_filename")
            if filename:
                initial_doc_results_by_file[filename].append(doc_result)
            else:
                logger.warning(f"Initial exploration: Document result missing original_filename: {doc_result.get('id')}")

        # --- Process Each Document (Extract Windows, Schedule Note Gen - Initial Exploration) ---
        for filename, chunks in initial_doc_results_by_file.items():
            logger.info(f"Initial exploration: Processing {len(chunks)} chunks from document: {filename}")
            # Pass callback and registry override
            content_windows = await self._extract_content_windows(
                filename,
                chunks,
                    feedback_callback,
                    log_queue=log_queue, # <-- Pass log_queue
                    tool_registry_override=tool_registry, # Pass the override
                    update_callback=update_callback # <-- Pass update_callback
                )

            for window in content_windows:
                # Create a unique window ID (still useful internally if needed) and get doc_id
                first_chunk_id = window["original_chunk_ids"][0] if window["original_chunk_ids"] else "unknown"
                window_source_id = f"window_{first_chunk_id}" # Keep for potential internal use
                
                # Use the enhanced window metadata
                window_metadata = {
                    "beginning_omitted": window["beginning_omitted"],
                    "end_omitted": window["end_omitted"],
                "original_chunk_ids": window["original_chunk_ids"],
                "window_position": {
                    "start": window["window_metadata"]["start_pos"],
                    "end": window["window_metadata"]["end_pos"]
                },
                    "overlapping_chunks": window["window_metadata"]["overlapping_chunks"] # This metadata will be cleaned later
                }
                
                # --- Get doc_id for the primary source_id ---
                doc_id_for_note = "unknown_doc"
                if window_metadata["overlapping_chunks"]:
                    doc_id_for_note = window_metadata["overlapping_chunks"][0].get("doc_id", "unknown_doc")
                # --- End get doc_id ---

                note_generation_tasks.append(
                    self._process_single_result(
                        section=temp_section_for_notes, # Pass dummy section
                        focus_questions=[question], # Pass the question being explored
                        result_item={ # Construct window item
                            "content": window["content"],
                            "source_id": doc_id_for_note, # <<< Use doc_id instead of window_id
                            "metadata": window_metadata # Pass full metadata for now, will be cleaned in _process_single_result if needed
                        },
                            source_type="document_window", # Use distinct type
                            is_initial_exploration=True, # Flag for relevance check
                            feedback_callback=feedback_callback,
                            log_queue=log_queue, # <-- Pass log_queue
                            update_callback=update_callback, # <-- Pass update_callback
                            tool_registry_override=tool_registry, # Pass the override
                            active_goals=active_goals, # <-- ADD active_goals
                            active_thoughts=active_thoughts # <-- ADD active_thoughts
                        )
                    )

        # --- Process Web Results (Initial Exploration - Remains Similar) ---
        for web_result in search_results.get("web", []):
            web_source_id = web_result.get("url", "unknown_url")
            if web_source_id in processed_source_ids: continue
            processed_source_ids.add(web_source_id)
            note_generation_tasks.append(
                self._process_single_result(
                    section=temp_section_for_notes, # Pass dummy section
                    focus_questions=[question], # Pass the question being explored
                    result_item=web_result, # Pass original web item
                    source_type="web",
                    is_initial_exploration=True, # Flag for relevance check
                    feedback_callback=feedback_callback,
                    log_queue=log_queue, # <-- Pass log_queue
                    update_callback=update_callback, # <-- Pass update_callback
                    tool_registry_override=tool_registry, # Pass the override
                    active_goals=active_goals, # <-- ADD active_goals
                    active_thoughts=active_thoughts # <-- ADD active_thoughts
                ) # Removed extra parenthesis here
            )

        # --- Execute Note Generation Concurrently (Initial Exploration) ---
        if note_generation_tasks:
            print(f"{log_prefix}: Generating relevant notes for {len(note_generation_tasks)} sources...")
            # *** FIX: Use a different variable name for the gather result ***
            gathered_note_results = await asyncio.gather(*note_generation_tasks)

            # Collect *only relevant* notes and details
            # --- Add logging for gather results ---
            logger.info(f"Processing {len(gathered_note_results)} results from initial exploration note generation gather.")
            for i, result_tuple in enumerate(gathered_note_results):
                logger.info(f"Initial exploration note result {i}: Type={type(result_tuple)}, Value={str(result_tuple)[:200]}...") # Log type and preview
                # Unpack 3 values
                if isinstance(result_tuple, tuple) and len(result_tuple) == 3:
                    note, note_model_details, context_used = result_tuple # Unpack if valid tuple
                    if note and context_used is not None: # Note is only returned if relevant, ensure context exists
                        relevant_notes_with_context.append((note, context_used))
                    if note_model_details:
                        model_calls_list.append(note_model_details)
                else:
                    logger.error(f"Unexpected result format from initial exploration note generation task {i}: {result_tuple}")
            # --- End added logging ---
            # Tool calls/file reads handled in _extract_content_windows
        else:
            print(f"{log_prefix}: No content windows or web results to generate notes from for initial exploration.")


        print(f"{log_prefix}: Finished generating notes. Found {len(relevant_notes_with_context)} relevant notes for the question.")

        # 4. Synthesize findings, generate sub-questions, update scratchpad (if limits allow)
        if current_depth < max_depth and (questions_explored_count + 1) < max_questions:
            print(f"{log_prefix}: Synthesizing findings and generating potential sub-questions...")
            # Format active goals and thoughts for the prompt
            goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None"
            thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts]) if active_thoughts else "None"

            synthesis_prompt = f"""
You are exploring the question: "{question}" (Depth: {current_depth}).

Overall Mission Goal: {mission_goal}
Active Mission Goals:
---
{goals_str}
---
Recent Thoughts:
---
{thoughts_str}
---
Current Scratchpad Context:
---
{agent_scratchpad or "None"}
---

Relevant Notes Found:
---
{chr(10).join([f"- {n.content}" for n, ctx in relevant_notes_with_context]) if relevant_notes_with_context else "None"}
---

Task:
1. Briefly synthesize the key findings from the 'Relevant Notes Found' related to the original question, ensuring alignment with the 'Active Mission Goals' and 'Recent Thoughts'.
2. Based on the findings, scratchpad context, goals, and thoughts, identify 1-3 specific, unanswered sub-questions that require further exploration to fully address the original question. Only generate sub-questions if the findings suggest clear avenues for deeper inquiry. Do not number the sub-questions in the list.
3. Provide an updated 'Scratchpad Context' incorporating the synthesis and any critical insights gained from exploring this question, considering the goals and thoughts. Keep it concise.

Output ONLY a JSON object with the following structure:
{{
  "synthesis": "Brief synthesis of findings...",
  "sub_questions": ["Specific sub-question 1?", "Specific sub-question 2?"],
  "updated_scratchpad": "Updated concise scratchpad content..."
}}
If no relevant sub-questions are identified, return an empty list for "sub_questions".
"""
            messages = [{"role": "user", "content": synthesis_prompt}]
            synthesis_response_obj, synthesis_model_details = await self._call_llm(
                user_prompt=synthesis_prompt, # Pass full prompt
                agent_mode="research", # Use research model
                response_format={"type": "json_object"}, # Request JSON output
                log_queue=log_queue if 'log_queue' in locals() else None, # Pass log_queue for UI updates
                update_callback=update_callback, # <-- Pass the correct update_callback
                log_llm_call=False # Disable duplicate LLM call logging since explore_question is logged by the research manager
            )
            model_calls_list.append(synthesis_model_details)

            if synthesis_response_obj and synthesis_response_obj.choices and synthesis_response_obj.choices[0].message.content:
                try:
                    synthesis_json_str = synthesis_response_obj.choices[0].message.content
                    # Use the centralized JSON utilities to parse the response
                    synthesis_data = parse_llm_json_response(synthesis_json_str)
                    new_sub_questions = synthesis_data.get("sub_questions", [])
                    # Filter out non-string items just in case
                    new_sub_questions = [q for q in new_sub_questions if isinstance(q, str)]
                    updated_scratchpad = synthesis_data.get("updated_scratchpad", updated_scratchpad) # Keep old if not updated
                    print(f"{log_prefix}: Synthesis: {synthesis_data.get('synthesis', 'N/A')}")
                    if new_sub_questions:
                        # Limit number of new questions to avoid explosion
                        max_new_q_per_step = 3
                        new_sub_questions = new_sub_questions[:max_new_q_per_step]
                        print(f"{log_prefix}: Generated {len(new_sub_questions)} sub-questions: {new_sub_questions}")
                    else:
                        print(f"{log_prefix}: No further sub-questions generated.")
                except json.JSONDecodeError as e:
                    logger.error(f"{log_prefix}: Failed to parse JSON response for synthesis/sub-questions: {e}. Response: {synthesis_json_str}")
                except Exception as e:
                    logger.error(f"{log_prefix}: Error processing synthesis/sub-question response: {e}", exc_info=True)
            else:
                logger.warning(f"{log_prefix}: LLM call for synthesis/sub-questions failed or returned empty content.")
        else:
            print(f"{log_prefix}: Max depth ({max_depth}) or max questions ({max_questions}) reached. Not generating sub-questions.")


        # Aggregate execution details
        execution_details = {
            "model_calls": model_calls_list,
            "tool_calls": tool_calls_list,
            "file_interactions": file_interactions_list
        }
        return relevant_notes_with_context, new_sub_questions, updated_scratchpad, execution_details


    async def _extract_content_windows(
        self,
        filename: str,
        chunks: List[Dict[str, Any]],
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # Type hint already correct, ensuring it stays
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue parameter
        tool_registry_override: Optional[ToolRegistry] = None, # <-- Add override parameter
        update_callback: Optional[Callable] = None # <-- Add update_callback parameter
    ) -> List[Dict[str, Any]]:
        """
        Reads a document using the provided/default tool registry, finds chunk locations,
        calculates content windows centered around each chunk, merges overlapping windows,
        and returns the processed windows.
        """
        logger.debug(f"Extracting content windows for {filename} from {len(chunks)} chunks.")
        if not chunks: return []
        
        # Use metadata from first chunk to read document, passing callback and registry override
        first_chunk_metadata = chunks[0].get("metadata", {})
        full_content_original, read_tool_call, file_read = await self._read_full_document_if_needed(
            source_info={"source_type": "document", "metadata": first_chunk_metadata},
            feedback_callback=feedback_callback, # Pass callback down
            log_queue=log_queue, # <-- Pass log_queue down
            tool_registry_override=tool_registry_override, # Pass the override
            update_callback=update_callback # <-- Pass update_callback
        )

        if not full_content_original:
            logger.warning(f"Could not read full content for {filename}. Cannot extract windows.")
            return []

        logger.debug(f"Processing full content for {filename} (length: {len(full_content_original)} chars)")
        logger.debug(f"First 500 chars of content: {repr(full_content_original[:500])}")
        logger.debug(f"Last 500 chars of content: {repr(full_content_original[-500:])}")

        # Track processed chunks and their windows
        processed_chunks: Dict[str, Dict[str, Any]] = {}
        window_size = config.RESEARCH_NOTE_CONTENT_LIMIT
        max_window_size = config.MAX_PLANNING_CONTEXT_CHARS

        # First pass: Find each chunk's position and calculate its window
        for chunk in chunks:
            chunk_id = chunk.get("id", "unknown")
            if chunk_id in processed_chunks:
                continue

            chunk_text = chunk.get("text", "").strip()
            if not chunk_text:
                logger.warning(f"Chunk {chunk_id} has no text content. Skipping.")
                continue

            try:
                # Split into paragraphs exactly like the chunker
                parts = self._paragraph_split_pattern.split(full_content_original)
                paragraphs = []
                current_paragraph = ""
                
                logger.debug(f"Initial split resulted in {len(parts)} parts for {filename}")
                logger.debug("First few parts:")
                for i, part in enumerate(parts[:5]):
                    logger.debug(f"  Part {i}: {repr(part[:100])}")
                
                for part in parts:
                    if part:  # Ignore empty strings from split
                        if self._paragraph_split_pattern.match(part):
                            # If it's a separator, append it to current paragraph and start new one
                            if current_paragraph:  # Avoid empty paragraphs
                                current_paragraph += part  # Add separator to current paragraph
                                paragraphs.append(current_paragraph.strip())  # Strip when adding
                                logger.debug(f"Added paragraph {len(paragraphs)}: {repr(current_paragraph[:100])}")
                            current_paragraph = ""  # Reset for next paragraph
                        else:
                            # If it's text, append to current paragraph
                            current_paragraph += part
                            logger.debug(f"Building paragraph: {repr(current_paragraph[:100])}")
                
                # Add final paragraph if not empty
                if current_paragraph.strip():  # Check stripped version
                    paragraphs.append(current_paragraph.strip())  # Strip when adding
                    logger.debug(f"Added final paragraph {len(paragraphs)}: {repr(current_paragraph[:100])}")
                
                logger.debug(f"Document has {len(paragraphs)} paragraphs")
                logger.debug("First few paragraphs:")
                for i, p in enumerate(paragraphs[:3]):
                    logger.debug(f"  Paragraph {i}: {repr(p[:100])}")
                
                # Get indices from metadata
                chunk_start_idx = chunk.get("metadata", {}).get("start_paragraph_index")
                chunk_end_idx = chunk.get("metadata", {}).get("end_paragraph_index")
                
                if chunk_start_idx is None or chunk_end_idx is None:
                    logger.warning(f"Chunk {chunk_id} missing paragraph indices in metadata. Skipping.")
                    continue
                
                # Validate indices
                if not (0 <= chunk_start_idx < len(paragraphs) and 0 <= chunk_end_idx < len(paragraphs)):
                    logger.warning(f"Chunk {chunk_id} has invalid paragraph indices: {chunk_start_idx}-{chunk_end_idx}. Document has {len(paragraphs)} paragraphs.")
                    continue
                
                # Get paragraphs for this chunk
                chunk_paragraphs = paragraphs[chunk_start_idx:chunk_end_idx + 1]
                chunk_text = "".join(chunk_paragraphs)
                
                # Calculate character positions
                full_content_so_far = "".join(paragraphs[:chunk_start_idx])
                chunk_start = len(full_content_so_far)
                chunk_end = chunk_start + len(chunk_text)
                
                # Create a match object with the found positions
                class TextMatch:
                    def __init__(self, start, end):
                        self.start_pos = start
                        self.end_pos = end
                    def start(self): return self.start_pos
                    def end(self): return self.end_pos
                
                match = TextMatch(chunk_start, chunk_end)

                # Calculate window boundaries centered on chunk
                chunk_start = match.start()
                chunk_end = match.end()
                chunk_length = chunk_end - chunk_start
                chunk_midpoint = chunk_start + (chunk_length // 2)
                
                # Calculate ideal window boundaries
                half_window = window_size // 2
                window_start = max(0, chunk_midpoint - half_window)
                window_end = min(len(full_content_original), window_start + window_size)
                
                # Adjust start if end was clamped
                if window_end < window_start + window_size:
                    window_start = max(0, window_end - window_size)

                processed_chunks[chunk_id] = {
                    "start": window_start,
                    "end": window_end,
                    "chunk_start": chunk_start,
                    "chunk_end": chunk_end,
                    "metadata": chunk.get("metadata", {})
                }
                logger.debug(f"Found chunk {chunk_id} at [{chunk_start}:{chunk_end}], window: [{window_start}:{window_end}]")

            except Exception as e:
                logger.error(f"Error processing chunk {chunk_id}: {str(e)}", exc_info=True)
                continue

        if not processed_chunks:
            logger.warning(f"No valid chunks found in {filename}")
            return []

        # Second pass: Merge overlapping windows
        sorted_windows = sorted(processed_chunks.items(), key=lambda x: x[1]["start"])
        merged_windows: List[Dict[str, Any]] = []
        current_window = {
            "start": sorted_windows[0][1]["start"],
            "end": sorted_windows[0][1]["end"],
            "chunk_ids": [sorted_windows[0][0]],
            "chunks_info": [sorted_windows[0][1]]
        }

        for chunk_id, window_info in sorted_windows[1:]:
            if window_info["start"] <= current_window["end"]:
                # Merge overlapping windows
                current_window["end"] = max(current_window["end"], window_info["end"])
                current_window["chunk_ids"].append(chunk_id)
                current_window["chunks_info"].append(window_info)
            else:
                # Start new window
                merged_windows.append(current_window)
                current_window = {
                    "start": window_info["start"],
                    "end": window_info["end"],
                    "chunk_ids": [chunk_id],
                    "chunks_info": [window_info]
                }
        merged_windows.append(current_window)

        # Final pass: Split large windows and create final window objects
        final_windows: List[Dict[str, Any]] = []
        for merged_window in merged_windows:
            window_length = merged_window["end"] - merged_window["start"]
            
            if window_length > max_window_size:
                # Split large window into smaller ones
                current_pos = merged_window["start"]
                while current_pos < merged_window["end"]:
                    split_end = min(current_pos + max_window_size, merged_window["end"])
                    
                    # Find chunks that overlap with this split
                    overlapping_chunks_info = [
                        info for info in merged_window["chunks_info"]
                        if info["chunk_start"] < split_end and info["chunk_end"] > current_pos
                    ]
                    
                    # --- Clean overlapping_chunks metadata ---
                    cleaned_overlapping_chunks_metadata = []
                    keys_to_keep_subsequent = {"chunk_id", "doc_id", "original_filename", "start_paragraph_index", "end_paragraph_index"}
                    for i, chunk_info in enumerate(overlapping_chunks_info):
                        meta = chunk_info.get("metadata", {})
                        if i == 0:
                            cleaned_overlapping_chunks_metadata.append(meta) # Keep all keys for the first one
                        else:
                            cleaned_meta = {k: v for k, v in meta.items() if k in keys_to_keep_subsequent}
                            cleaned_overlapping_chunks_metadata.append(cleaned_meta)
                    # --- End cleaning ---
                    
                    window_content = full_content_original[current_pos:split_end]
                    window_obj = {
                        "content": window_content,
                        "beginning_omitted": current_pos > 0,
                        "end_omitted": split_end < len(full_content_original),
                        "original_chunk_ids": merged_window["chunk_ids"], # Keep original chunk IDs list
                        "window_metadata": {
                            "start_pos": current_pos,
                            "end_pos": split_end,
                            "overlapping_chunks": cleaned_overlapping_chunks_metadata # Use cleaned list
                        }
                    }
                    logger.debug(f"Split window {len(final_windows)+1}: [{current_pos}:{split_end}] ({len(window_content)} chars)")
                    final_windows.append(window_obj)
                    current_pos = split_end
            else:
                # Add window as-is
                window_content = full_content_original[merged_window["start"]:merged_window["end"]]
                window_obj = {
                    "content": window_content,
                    "beginning_omitted": merged_window["start"] > 0,
                    "end_omitted": merged_window["end"] < len(full_content_original),
                    "original_chunk_ids": merged_window["chunk_ids"], # Keep original chunk IDs list
                    "window_metadata": {
                        "start_pos": merged_window["start"],
                        "end_pos": merged_window["end"],
                        # --- Clean overlapping_chunks metadata ---
                        "overlapping_chunks": [
                            chunk_info.get("metadata", {}) if i == 0 else {k: v for k, v in chunk_info.get("metadata", {}).items() if k in {"chunk_id", "doc_id", "original_filename", "start_paragraph_index", "end_paragraph_index"}}
                            for i, chunk_info in enumerate(merged_window["chunks_info"])
                        ]
                        # --- End cleaning ---
                    }
                }
                logger.debug(f"Full window {len(final_windows)+1}: [{merged_window['start']}:{merged_window['end']}] ({len(window_content)} chars)")
                final_windows.append(window_obj)

        logger.info(f"Extracted {len(final_windows)} final content windows for {filename}")
        return final_windows


    async def _generate_section_queries(
        self,
        section: ReportSection,
        techniques: List[QueryRewritingTechnique],
        focus_questions: Optional[List[str]] = None,
        mission_goal: Optional[str] = None, # NEW: Add mission_goal for context
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue parameter
        update_callback: Optional[Callable] = None # <-- Add update_callback parameter
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Generates search queries using the QueryPreparer, considering active goals.
        Uses the first focus question if available, otherwise uses the section description.
        Includes mission goal and active goals in the domain context.
        """
        logger.info(f"Preparing search queries for section: '{section.title}' using techniques: {techniques}...")
        # --- Construct a simplified initial query ---
        if focus_questions:
            # Use the first focus question as the primary query
            initial_query = focus_questions[0]
            logger.info(f"Using first focus question as initial query for section {section.section_id}: '{initial_query}'")
        else:
            # If no focus questions, use the section description directly
            initial_query = section.description
            logger.info(f"Using section description as initial query for section {section.section_id}: '{initial_query}'")
        # --- End simplified query construction ---

        # --- Define domain context for QueryPreparer (can still be useful) ---
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None"
        domain_context_for_preparer = f"Overall Mission Goal: {mission_goal or 'Not specified'}\nActive Goals:\n{goals_str}\nCurrent Section Focus: '{section.title}' - {section.description}"
        # --- End define domain context ---

        try:
            # Get query preparer from controller if not available
            query_preparer = self.query_preparer
            if not query_preparer and self.controller:
                query_preparer = self.controller.query_preparer
                
            if not query_preparer:
                logger.warning(f"Query preparer not available for section {section.section_id}. Using initial query without enhancement.")
                prepared_queries = [initial_query]
                model_details_list = []
            else:
                # Await the async query preparer, passing log_queue and update_callback
                prepared_queries, model_details_list = await query_preparer.prepare_queries(
                    original_query=initial_query,
                    techniques=techniques,
                    domain_context=domain_context_for_preparer # Pass domain context here
                    # Removed log_queue and update_callback arguments
                )
            # Ensure at least one query is returned (fallback to initial)
            if not prepared_queries:
                logger.warning(f"Query preparation returned no queries for section {section.section_id}. Falling back to initial query.")
                prepared_queries = [initial_query] # Fallback to the initial query (which might be focus Q or description)
                
            logger.info(f"Prepared queries for section {section.section_id}: {prepared_queries}")
            return prepared_queries, model_details_list # Return list of details
        except Exception as e:
            logger.error(f"Failed to prepare queries for section {section.section_id}: {e}", exc_info=True)
            # Fallback: use the initial query
            logger.warning(f"Falling back to initial query due to QueryPreparer error: '{initial_query}'")
            return [initial_query], [{"error": f"Query preparation failed: {e}"}]

    async def _execute_single_search(
        self,
        tool_name: str,
        query: str,
        args: Dict[str, Any],
        update_callback: Optional[Callable] = None, # <-- Add callback
        log_queue: Optional[queue.Queue] = None,     # <-- Add queue
        tool_registry_override: Optional[ToolRegistry] = None, # <-- Add override parameter
        mission_id: Optional[str] = None # <-- Add mission_id parameter
    ) -> Tuple[Optional[Any], Dict[str, Any]]:
        """
        Helper to execute a single search tool call asynchronously using the provided/default registry.
        """
        tool_call_details = {"tool_name": tool_name, "arguments": args}
        registry_to_use = tool_registry_override if tool_registry_override is not None else self.tool_registry

        if not registry_to_use:
            logger.error(f"ToolRegistry not available for executing tool '{tool_name}'.")
            tool_call_details["error"] = "ToolRegistry not available."
            return None, tool_call_details

        try:
            # --- Get tool instance from the chosen registry ---
            tool_instance = registry_to_use.get_tool(tool_name)
            if not tool_instance:
                raise ValueError(f"Tool '{tool_name}' not found in the specified registry.")

            # --- Call tool's implementation method directly ---
            # Ensure the implementation is callable
            if not callable(tool_instance.implementation):
                 raise TypeError(f"Tool '{tool_name}' implementation is not callable.")

            sig = inspect.signature(tool_instance.implementation) # <-- Use .implementation
            tool_params = sig.parameters

            execute_args = args.copy() # Start with standard args

            # --- NEW: Add document_group_id for document search tool ---
            if tool_name == "document_search":
                logger.info(f"DEBUG: Processing document_search tool for mission {mission_id or self.mission_id}")
                logger.info(f"DEBUG: self.controller exists: {hasattr(self, 'controller')}")
                logger.info(f"DEBUG: self.controller value: {getattr(self, 'controller', 'NOT_SET')}")
                
                # Use mission_id parameter or fall back to instance attribute
                current_mission_id = mission_id or self.mission_id
                
                if hasattr(self, 'controller') and self.controller and current_mission_id:
                    try:
                        # Get mission context to extract document_group_id
                        logger.info(f"DEBUG: Attempting to get mission context for mission {current_mission_id}")
                        mission_context = self.controller.context_manager.get_mission_context(current_mission_id)
                        if mission_context and mission_context.metadata:
                            logger.info(f"DEBUG: Mission context found. Metadata keys: {list(mission_context.metadata.keys())}")
                            logger.info(f"DEBUG: Full mission metadata: {mission_context.metadata}")
                            document_group_id = mission_context.metadata.get("document_group_id")
                            if document_group_id:
                                execute_args['document_group_id'] = str(document_group_id)  # Ensure it's a string
                                logger.info(f"DEBUG: Added document_group_id={document_group_id} to document search for mission {current_mission_id}")
                            else:
                                logger.warning(f"DEBUG: No document_group_id found in mission {current_mission_id} metadata. Available keys: {list(mission_context.metadata.keys())}")
                        else:
                            logger.warning(f"DEBUG: Could not get mission context for mission {current_mission_id} - context: {mission_context}")
                    except Exception as e:
                        logger.error(f"DEBUG: Error extracting document_group_id for mission {current_mission_id}: {e}", exc_info=True)
                else:
                    logger.warning(f"DEBUG: Controller not available or no mission_id for document search. Controller: {hasattr(self, 'controller')}, Mission ID: {current_mission_id}")
            # --- End document_group_id addition ---

            # Add callback and queue if the tool accepts them
            if 'update_callback' in tool_params:
                execute_args['update_callback'] = update_callback
            if 'log_queue' in tool_params:
                execute_args['log_queue'] = log_queue
            # --- FIX: Call self._execute_tool instead of implementation directly ---
            # This ensures context args (mission_id, agent_controller) are injected by BaseAgent
            result = await self._execute_tool(
                tool_name,
                execute_args, # Pass the prepared args
                tool_registry_override=registry_to_use, # Pass the correct registry
                log_queue=log_queue, # <-- Pass log_queue
                update_callback=update_callback # <-- Pass update_callback
            )
            # --- End FIX ---

            # --- Process result (check for potential error dict from _execute_tool) ---
            if isinstance(result, dict) and "error" in result:
                # Handle error returned by _execute_tool or the tool itself
                logger.warning(f"{tool_name} failed for query '{query}': {result['error']}")
                tool_call_details["error"] = result['error']
                result = None # Indicate failure
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        item.setdefault('metadata', {})['query_source'] = query
                tool_call_details["result_summary"] = f"{len(result)} results found"
            elif isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                 # Handle web search format
                 web_results = result["results"]
                 for item in web_results:
                     if isinstance(item, dict):
                         item.setdefault('metadata', {})['query_source'] = query
                 tool_call_details["result_summary"] = f"{len(web_results)} results found"
                 result = web_results # Return just the list for consistency downstream
            # Note: Error case is handled above now
            # elif isinstance(result, dict) and "error" in result:
            #     logger.warning(f"{tool_name} failed for query '{query}': {result['error']}")
            #     tool_call_details["error"] = result['error']
            #     result = None # Indicate failure
            elif result is None: # Handle case where _execute_tool failed before calling implementation
                 logger.warning(f"Tool execution failed for {tool_name} (query: '{query}'). Result was None.")
                 # tool_call_details should already have error from _execute_single_search exception block
                 if "error" not in tool_call_details: # Add generic error if missing
                      tool_call_details["error"] = "Tool execution failed, result was None."
                 # result is already None
            else: # Unexpected format (should be list or None/error dict now)
                logger.warning(f"{tool_name} returned unexpected format for query '{query}': {str(result)[:100]}")
                tool_call_details["error"] = "Unexpected result format"
                tool_call_details["result_preview"] = str(result)[:100]
                result = None # Indicate failure
            return result, tool_call_details
        except Exception as e:
            logger.error(f"Error during {tool_name} tool execution for query '{query}': {e}", exc_info=True)
            tool_call_details["error"] = str(e)
            return None, tool_call_details


    async def _execute_searches_parallel(
        self,
        queries: List[str],
        n_doc_results: int = config.MAIN_RESEARCH_DOC_RESULTS, # Use config default
        n_web_results: int = config.MAIN_RESEARCH_WEB_RESULTS, # Use config default
        use_doc_reranker: bool = True, # Default to TRUE now for all document searches
        update_callback: Optional[Callable] = None, # <-- Add callback
        log_queue: Optional[queue.Queue] = None,     # <-- Add queue
        tool_registry_override: Optional[ToolRegistry] = None, # <-- Add override parameter
        active_goals: Optional[List[GoalEntry]] = None # <-- Add active_goals parameter
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """
        Executes document and web searches in parallel for all queries using the provided/default registry.
        """
        registry_to_use = tool_registry_override if tool_registry_override is not None else self.tool_registry
        if not registry_to_use:
            logger.error("ToolRegistry not available for executing searches.")
            return {"document": [], "web": []}, []

        logger.info(f"Preparing parallel searches for {len(queries)} queries...")
        search_tasks = []
        
        # Check if there's a preferred source type in active goals
        preferred_source_type = None
        
        # First try to get from the active_goals parameter if available
        if active_goals:
            for goal in active_goals:
                if hasattr(goal, 'text') and "Preferred Source Types:" in goal.text:
                    source_type_match = re.search(r"Preferred Source Types:?\s*([^\n]+)", goal.text, re.IGNORECASE)
                    if source_type_match:
                        preferred_source_type = source_type_match.group(1).strip()
                        logger.info(f"Found preferred source type in active_goals parameter: '{preferred_source_type}'")
                        break
        
        # If not found in active_goals parameter, try to get from the controller
        if not preferred_source_type and hasattr(self, 'controller') and self.controller:
            try:
                # Try to get active goals from the controller
                controller_goals = self.controller.get_active_goals() if hasattr(self.controller, 'get_active_goals') else None
                if controller_goals:
                    for goal in controller_goals:
                        if hasattr(goal, 'text') and "Preferred Source Types:" in goal.text:
                            source_type_match = re.search(r"Preferred Source Types:?\s*([^\n]+)", goal.text, re.IGNORECASE)
                            if source_type_match:
                                preferred_source_type = source_type_match.group(1).strip()
                                logger.info(f"Found preferred source type in controller goals: '{preferred_source_type}'")
                                break
            except Exception as e:
                logger.warning(f"Error accessing controller goals: {e}")
        
        # Fallback: Check if "Legal Sources" is mentioned in any query
        if not preferred_source_type:
            for query in queries:
                if "legal sources" in query.lower():
                    preferred_source_type = "Legal Sources"
                    logger.info(f"Inferred preferred source type from query content: '{preferred_source_type}'")
                    break
        
        for query in queries:
            # Append preferred source type to query if found
            enhanced_query = query
            if preferred_source_type:
                # Only append if not already present in the query
                if preferred_source_type.lower() not in query.lower():
                    enhanced_query = f"{query} {preferred_source_type}"
                    logger.info(f"Enhanced query with source type: '{enhanced_query}'")
            
            # Document Search Task - Check if tool exists before adding
            if registry_to_use.get_tool("document_search"):
                doc_args = {
                    "query": enhanced_query,  # Use enhanced query
                    "n_results": n_doc_results,
                    "use_reranker": use_doc_reranker # Pass the flag here
                }
                search_tasks.append(self._execute_single_search(
                    "document_search",
                    enhanced_query,  # Use enhanced query for logging
                    doc_args,
                    update_callback=update_callback, # Pass down
                    log_queue=log_queue, # Pass down
                    tool_registry_override=tool_registry_override, # Pass override
                    mission_id=self.mission_id # Pass mission_id for document_group_id extraction
                ))
            else:
                logger.warning("Document search tool not found in registry. Skipping document search for query.")

            # Web Search Task - Check if tool exists before adding
            if registry_to_use.get_tool("web_search"):
                web_query = enhanced_query  # Use enhanced query
                if len(web_query) > 400:
                    logger.warning(f"Web search query exceeds 400 chars ({len(web_query)}). Truncating. Original: '{web_query}'")
                    web_query = web_query[:400]
                    logger.info(f"Truncated web search query: '{web_query}'")

                web_args = {"query": web_query, "max_results": n_web_results} # Use potentially truncated query
                # Pass the enhanced query to _execute_single_search for logging context
                search_tasks.append(self._execute_single_search(
                    "web_search", # Use the generic tool name
                    enhanced_query,  # Use enhanced query for logging (before truncation)
                    web_args,
                    update_callback=update_callback, # Pass down
                    log_queue=log_queue, # Pass down
                    tool_registry_override=tool_registry_override, # Pass override
                    mission_id=self.mission_id # Pass mission_id (though not used for web search)
                ))
            else:
                logger.warning("Web search tool not found in registry. Skipping web search for query.")

        # Execute all searches concurrently
        if not search_tasks:
            logger.warning("No search tasks could be scheduled (tools might be missing from registry).")
            return {"document": [], "web": []}, [] # Return empty results and calls

        logger.info(f"Executing {len(search_tasks)} search tasks in parallel...")
        search_task_results = await asyncio.gather(*search_tasks)

        # Process and aggregate results
        aggregated_results = {"document": [], "web": []}
        tool_calls_list = []
        for i, (result_list, tool_call_details) in enumerate(search_task_results):
            tool_calls_list.append(tool_call_details)
            if result_list: # Only extend if results were found and no error occurred
                # Determine if it was doc or web based on index/tool name
                tool_name = tool_call_details["tool_name"]
                if tool_name == "document_search":
                    aggregated_results["document"].extend(result_list)
                elif tool_name == "web_search": # Check against the generic tool name
                    aggregated_results["web"].extend(result_list)

        # TODO: Add deduplication logic here if needed
        logger.info(f"Parallel search execution complete. Found {len(aggregated_results['document'])} doc results, {len(aggregated_results['web'])} web results.")
        return aggregated_results, tool_calls_list


    async def _read_full_document_if_needed(
        self,
        source_info: Dict[str, Any],
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # Type hint already correct, ensuring it stays
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue parameter
        tool_registry_override: Optional[ToolRegistry] = None, # <-- Add override parameter
        update_callback: Optional[Callable] = None # <-- Add update_callback parameter
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        Checks if full document is needed, uses FileReaderTool via the provided/default registry,
        returns content, tool call details, and file path read.
        """
        tool_call_details = None
        file_path_read = None
        # TODO: Implement logic to decide if snippet is sufficient.
        # Placeholder: Always try to read full doc for now if it's a document source.
        needs_full_doc = source_info.get("source_type") == "document" # Basic check

        if needs_full_doc:
            metadata = source_info.get("metadata", {})
            filename = metadata.get("original_filename")

            if filename:
                target_path_abs_unresolved = None # Initialize
                allowed_base_path_abs = None # Initialize
                try:
                    # --- ENVIRONMENT-AWARE PATH LOGIC START ---
                    # Detect if we're running in Docker by checking for common Docker indicators
                    import os
                    is_docker = (
                        os.path.exists('/.dockerenv') or 
                        os.environ.get('DOCKER_CONTAINER') == 'true' or
                        os.path.exists('/app/ai_researcher')  # Check if the Docker app structure exists
                    )
                    
                    if is_docker:
                        # Use absolute Docker paths
                        allowed_base_path = "/app/ai_researcher/data/processed/markdown"
                        logger.info("Detected Docker environment, using absolute paths")
                    else:
                        # Use relative paths for local development
                        allowed_base_path = "ai_researcher/data/processed/markdown"
                        logger.info("Detected local environment, using relative paths")
                    
                    # Get doc_id from metadata
                    doc_id = metadata.get("doc_id")
                    if not doc_id:
                        logger.error(f"Could not find doc_id in metadata: {metadata}")
                        return None, None, None # Return tuple

                    # Construct the markdown path using doc_id and environment-appropriate path
                    target_path = Path(allowed_base_path) / f"{doc_id}.md"
                    target_path_abs_unresolved = str(target_path)
                    logger.info(f"Constructed target path for tool: {target_path_abs_unresolved}")
                    # --- ENVIRONMENT-AWARE PATH LOGIC END ---

                    # Check if the constructed path actually exists before trying to read
                    # This check remains synchronous as it's fast local FS check
                    if not Path(target_path_abs_unresolved).is_file():
                         logger.error(f"Constructed file path does not exist or is not a file: {target_path_abs_unresolved}. Check if file '{doc_id}.md' exists in '{allowed_base_path}'.")
                         return None, None, None # Give up if the primary path doesn't work

                    logger.info(f"Attempting to read full document via async tool: {target_path_abs_unresolved}")
                    logger.info(f"Passing allowed base path to tool: {allowed_base_path}")

                    # --- Get original_filename from metadata ---
                    original_filename_for_tool = metadata.get("original_filename")
                    # --- End get original_filename ---

                    tool_args = {
                        "filepath": str(target_path_abs_unresolved),
                        "allowed_base_path": allowed_base_path,
                        "feedback_callback": feedback_callback, # <-- Pass callback to tool args
                        "original_filename": original_filename_for_tool, # <-- Pass original filename
                        "log_queue": log_queue # <-- ADD log_queue to tool args
                        }
                    logger.info(f"DEBUG (ResearchAgent): Arguments prepared for _execute_tool (using unresolved path): {tool_args}")

                    try:
                        # Await the async file reader tool with timeout, passing the registry override
                        full_text_result = await asyncio.wait_for(
                            self._execute_tool(
                                "read_full_document",
                                tool_args,
                                tool_registry_override=tool_registry_override, # Pass override
                                log_queue=log_queue, # <-- Pass log_queue
                                update_callback=update_callback # <-- Pass update_callback
                            ),
                            timeout=30.0  # 30 second timeout
                        )

                        # Process result (check for error string)
                        if isinstance(full_text_result, str) and not full_text_result.startswith("Error:"):
                            logger.info(f"Successfully read full text for {filename}.")
                            file_path_read = str(target_path_abs_unresolved) # Record file path read
                            tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args, "result_summary": f"Read {len(full_text_result)} chars"}
                            return full_text_result, tool_call_details, file_path_read
                        elif isinstance(full_text_result, str) and full_text_result.startswith("Error:"):
                            error_msg = full_text_result # Already formatted error string
                            logger.warning(f"Failed to read full document {filename} using tool: {error_msg}")
                            tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args, "error": error_msg}
                            return None, tool_call_details, None
                        else: # Unexpected result format (shouldn't happen if tool returns str or error str)
                            error_msg = f"Unexpected result format from read_full_document: {str(full_text_result)[:100]}"
                            logger.warning(f"Failed to read full document {filename} using tool: {error_msg}")
                            tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args, "error": error_msg}
                            return None, tool_call_details, None
                    except asyncio.TimeoutError:
                        error_msg = f"Timeout while reading document {filename}"
                        logger.warning(error_msg)
                        tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args, "error": error_msg}
                        return None, tool_call_details, None
                    except Exception as e:
                        error_msg = f"Error reading document {filename}: {str(e)}"
                        logger.error(error_msg)
                        tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args, "error": error_msg}
                        return None, tool_call_details, None
                except FileNotFoundError: # This might be less likely now with the is_file check
                    logger.error(f"File not found error during read attempt for {filename}. Path: {target_path_abs_unresolved}")
                    tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args if 'tool_args' in locals() else {}, "error": "FileNotFoundError"}
                    return None, tool_call_details, None
                except Exception as e:
                    logger.error(f"Error executing read_full_document tool for {filename}: {e}", exc_info=True)
                    tool_call_details = {"tool_name": "read_full_document", "arguments": tool_args if 'tool_args' in locals() else {}, "error": str(e)}
                    return None, tool_call_details, None
            else:
                logger.warning("Cannot read full document: original_filename missing in metadata.")
                return None, None, None
        else:
            # Snippet is sufficient or not a document source
            return None, None, None # Indicate full text not read/needed, no tool call, no file read


    async def _generate_note_from_content(
        self,
        question_being_explored: str, # New parameter for the specific question context
        section_id: str, # Still useful for tagging notes, even if derived from question
        section_description: str, # Can be the question itself or section goal
        focus_questions: Optional[List[str]], # May be redundant if question_being_explored is primary
        active_goals: Optional[List[GoalEntry]], # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]], # <-- NEW: Add active thoughts
        source_type: str,
        source_id: str,
        source_metadata: Dict,
        content_to_process: str,
        is_initial_exploration: bool = False, # Flag to modify prompt for relevance check
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # <-- Add feedback_callback
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue
        update_callback: Optional[Callable] = None, # <-- ADD update_callback
        tool_registry_override: Optional[ToolRegistry] = None, # <-- Add override parameter (needed for _process_single_result)
        model: Optional[str] = None # <-- ADD model parameter
    ) -> Tuple[Optional[Note], Optional[Dict[str, Any]]]:
        """Uses LLM asynchronously to generate a Note object, returning the note and model call details."""
        # Note: tool_registry_override is accepted here but not directly used by _generate_note_from_content itself.
        # It's needed because _process_single_result calls this method and also needs the override for its own tool calls.
        logger.debug(f"Generating note for question '{question_being_explored}' / section {section_id} from {source_type}: {source_id}")

        # Construct prompt
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None"
        thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts]) if active_thoughts else "None"

        if is_initial_exploration:
            # Prompt focused on the specific question during initial exploration, including thoughts
            prompt = f"""
You are analyzing content related to the specific research question: "{question_being_explored}"

**CRITICAL: Remember the overall mission goals and recent thoughts, ensuring your analysis aligns with them:**
---
Active Goals:
{goals_str}
---
Recent Thoughts:
{thoughts_str}
---

Content Source Details:
- Type: {source_type}
- ID: {source_id}
- Metadata: {json.dumps(source_metadata, indent=2)}

Content to Analyze (first {config.RESEARCH_NOTE_CONTENT_LIMIT} chars):
---
{content_to_process[:config.RESEARCH_NOTE_CONTENT_LIMIT]}...
---

Task: Extract all information directly relevant to answering the specific research question: "{question_being_explored}". Synthesize these findings into a detailed and comprehensive note. Ensure all key details, context, and nuances from the source content that help answer the question are included. 

**CRITICAL INSTRUCTIONS:**
1. Extract information *only* from the 'Content to Analyze' provided above. Do not infer, assume, or add any information not explicitly present in the text.
2. Pay special attention to any "Preferred Source Types" mentioned in the Active Goals. If the user has specified preferred source types (e.g., "academic literature", "legal sources", "state law"), prioritize information that aligns with these source preferences.
3. Output ONLY the detailed note content.
4. If the content is IRRELEVANT to the question: Return the text "Content reviewed, but not relevant to the question."
"""
        else:
            # Original prompt focused on section goal (for structured research phase)
            prompt = f"""
Analyze the following content obtained from source '{source_id}' (Type: {source_type}).
The goal is to extract information relevant to the research section, **ensuring it aligns with the overall mission goals and recent thoughts**:

**CRITICAL: Overall Mission Goals & Recent Thoughts (Consult these for relevance, tone, audience, focus):**
---
Active Goals:
{goals_str}
---
Recent Thoughts:
{thoughts_str}
---

Current Section Details:
- Section ID: '{section_id}'
- Section Goal: '{section_description}'
"""
            if focus_questions: # Keep focus questions for structured phase
                prompt += f"\nSpecifically focus on answering these questions if possible: {'; '.join(focus_questions)}\n"

            prompt += f"""
Source Metadata:
{json.dumps(source_metadata, indent=2)}

Content to Analyze (first {config.RESEARCH_NOTE_CONTENT_LIMIT} chars):
---
{content_to_process[:config.RESEARCH_NOTE_CONTENT_LIMIT]}...
---

Task: Extract all key information relevant to the section goal (and focus questions, if provided). Synthesize these findings into a detailed and comprehensive note. Ensure all key details, context, and nuances from the source content relevant to the goal/questions are included.

**CRITICAL INSTRUCTIONS:**
1. Extract information *only* from the 'Content to Analyze' provided above. Do not infer, assume, or add any information not explicitly present in the text.
2. Pay special attention to any "Preferred Source Types" mentioned in the Active Goals. If the user has specified preferred source types (e.g., "academic literature", "legal sources", "state law"), prioritize information that aligns with these source preferences.
3. Output ONLY the detailed note content. Do not include explanations, apologies, or introductory phrases like "The note is...".
4. If the content excerpt is irrelevant to the section goal/questions or contains no clear relevant point, return the text "Content reviewed, but not relevant to the section goal/questions."
"""
 
        # --- Add logging before LLM call ---
        logger.info(f"Content being sent to LLM for note generation (source: {source_id}, total length: {len(content_to_process)}, first 500 chars): {repr(content_to_process[:500])}")
        logger.debug(f"Full prompt for note generation (source: {source_id}):\n{prompt}")
        # --- End added logging ---

        messages = [{"role": "user", "content": prompt}]
        model_call_details = None
        try:
            # Await the async LLM call
            response, model_call_details = await self._call_llm(
                user_prompt=prompt, # Pass the constructed prompt
                agent_mode="research", # Use research model
                log_queue=log_queue if 'log_queue' in locals() else None, # Pass log_queue for UI updates
                update_callback=update_callback, # <-- Pass correct update_callback
                model=model, # <-- Pass the model parameter down
                log_llm_call=False # Disable duplicate LLM call logging since this is an internal helper method
            )
            note_content = ""
            raw_llm_response_content = "" # <-- Add variable to store raw response
            if response and response.choices and response.choices[0].message.content:
                 raw_llm_response_content = response.choices[0].message.content # <-- Store raw response
                 note_content = raw_llm_response_content.strip()

            # --- Add logging after LLM call ---
            # logger.info(f"LLM raw response for note generation (source: {source_id}): {repr(raw_llm_response_content)}")
            # logger.info(f"Stripped note content (source: {source_id}): {repr(note_content)}")
            # --- End added logging ---


            # Check if the LLM indicated irrelevance or returned actual content
            irrelevance_markers = [
                "content reviewed, but not relevant to the question.",
                "content reviewed, but not relevant to the section goal/questions."
            ]
            is_irrelevant = any(marker in note_content.lower() for marker in irrelevance_markers)

            if note_content and not is_irrelevant:
                # Map 'document_window' to 'document' for Note schema validation
                actual_source_type = "document" if source_type == "document_window" else source_type
                # Ensure actual_source_type is one of the allowed literals
                if actual_source_type not in ["document", "web", "internal"]:
                    logger.error(f"Invalid source type '{actual_source_type}' derived from '{source_type}' for note creation.")
                    return None, model_call_details # Cannot create note

                try:
                    from ai_researcher.config import get_current_time
                    now = get_current_time()
                    new_note = Note(
                        content=note_content,
                        source_type=actual_source_type, # Use mapped type
                        source_id=source_id,
                        source_metadata=source_metadata,
                        potential_sections=[section_id], # Removed is_relevant field
                        created_at=now,
                        updated_at=now
                    )
                except ValidationError as e:
                     logger.error(f"Pydantic validation failed creating Note for source {source_id}: {e}")
                     return None, model_call_details # Return None if validation fails

                log_msg = f"Generated relevant note {new_note.note_id}"
                if is_initial_exploration:
                    log_msg += f" for question '{question_being_explored}'."
                else:
                    log_msg += f" for section {section_id}."
                logger.info(log_msg)
                return new_note, model_call_details
            elif is_irrelevant:
                # LLM explicitly stated irrelevance
                log_msg = f"Content from source {source_id} explicitly deemed irrelevant by LLM"
                if is_initial_exploration:
                    log_msg += f" to question '{question_being_explored}'."
                else:
                    log_msg += f" to section {section_id} goal."
                logger.info(log_msg)
                # Add specific log for why fetcher won't be called
                if source_type == "web":
                    logger.info(f"Web content fetch skipped for {source_id} because snippet was deemed irrelevant by LLM.")
                # Return None for the note, but still return model details
                return None, model_call_details
            else: # note_content was empty or only whitespace
                # LLM returned empty or whitespace response
                log_msg = f"LLM returned empty/whitespace response for source {source_id}, indicating irrelevance or issue."
                if is_initial_exploration:
                    log_msg += f" (Question: '{question_being_explored}')"
                else:
                    log_msg += f" to section {section_id} goal."
                logger.info(log_msg)
                # Add specific log for why fetcher won't be called
                if source_type == "web":
                    logger.info(f"Web content fetch skipped for {source_id} because LLM returned empty/whitespace response for snippet.")
                # Return None for the note, but still return model details
                return None, model_call_details
        except Exception as e:
            logger.error(f"Async LLM call failed during note generation for source {source_id}: {e}", exc_info=True)
            # Return None for the note, but still return model details if available
            return None, model_call_details


    async def _process_single_result(
        self,
        section: ReportSection, # Still used for section_id tagging, even if description comes from question
        focus_questions: Optional[List[str]], # Passed down, primary context depends on phase
        active_goals: Optional[List[GoalEntry]], # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]], # <-- NEW: Add active thoughts
        result_item: Dict[str, Any],
        source_type: str,
        is_initial_exploration: bool = False,
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None, # Type hint already correct, ensuring it stays
        log_queue: Optional[queue.Queue] = None, # <-- Add log_queue
        update_callback: Optional[Callable] = None, # <-- ADD update_callback
        tool_registry_override: Optional[ToolRegistry] = None, # <-- Add override parameter
        model: Optional[str] = None # <-- ADD model parameter
    ) -> Tuple[Optional[Note], Optional[Dict[str, Any]], Optional[str]]:
        """
        Processes a single search result (web or document_window) using the provided/default registry.
        Generates a note from the initial content (snippet or window).
        If it's a web source and the snippet is relevant, attempts to fetch the full page
        content using 'fetch_web_page_content' tool and generate a richer note.

        Returns:
            Tuple: (Relevant_Note | None, model_call_details | None, context_used_for_note | None)
        """
        context_used_for_note: Optional[str] = None # Initialize context capture
        # Determine the primary question/goal for note generation based on the phase
        question_or_goal = section.description if not is_initial_exploration else (focus_questions[0] if focus_questions else section.description)

        content_to_process = ""
        source_id = ""
        source_metadata = {}
        read_tool_call = None # Initialize to None, as it's no longer expected to be generated here
        file_read = None # Initialize to None

        # --- Correctly set source_id and initial metadata based on source_type ---
        if source_type == "document_window":
            # source_id is the doc_id passed in result_item
            source_id = result_item.get("source_id", "unknown_doc_id")
            source_metadata = result_item.get("metadata", {})
            content_to_process = result_item.get("content", "")
            logger.info(f"Processing document window. Source ID (doc_id): {source_id}")
            # Metadata is already cleaned in _extract_content_windows

        elif source_type == "web":
            # source_id should be the URL from the web result item
            source_id = result_item.get("url", "unknown_url") # <-- Get URL correctly
            content_to_process = result_item.get("snippet", "") # Or use 'content' if available from tool
            source_metadata = {
                "title": result_item.get("title", "Unknown Title"),
                "url": source_id, # Use the correctly assigned source_id (URL)
                "snippet": content_to_process
                # Add other relevant fields if available
            }
            logger.info(f"Processing web result. Source ID (URL): {source_id}")
        else:
            # Handle unexpected source types if necessary
            logger.error(f"Unknown source_type '{source_type}' encountered in _process_single_result.")
            return None, None, None # Return tuple (note, details, context)
        # --- End setting source_id and initial metadata ---

        # Proceed only if we have content
        # Capture the initial content before potentially fetching full web content
        initial_content_to_process = content_to_process

        if not content_to_process:
            logger.warning(f"No content available for {source_type} source {source_id}. Skipping note generation.")
            return None, None, None # Return tuple (note, details, context)

        # Generate note from the initial content (snippet or window), passing the specific question for relevance check if needed
        logger.info(f"Calling _generate_note_from_content for source {source_id} using initial content. Length: {len(initial_content_to_process)}")
        context_used_for_note = initial_content_to_process # Capture initial context
        note, note_model_details = await self._generate_note_from_content(
            question_being_explored=question_or_goal, # Pass the relevant question/goal
            section_id=section.section_id,
            section_description=section.description, # Keep original section desc for context if needed
            focus_questions=focus_questions, # Pass along focus questions
            active_goals=active_goals, # <-- Pass active_goals
            active_thoughts=active_thoughts, # <-- Pass active thoughts
            source_type=source_type,
            source_id=source_id,
            source_metadata=source_metadata,
            content_to_process=initial_content_to_process, # Use initial content here
            is_initial_exploration=is_initial_exploration, # Pass the flag
            feedback_callback=feedback_callback, # Pass feedback_callback
            log_queue=log_queue, # Pass log_queue
            update_callback=update_callback, # <-- Pass update_callback
            tool_registry_override=tool_registry_override, # Pass override (needed by signature)
            model=model # <-- Pass model parameter
        )

        # --- UI Feedback: Note Generated ---
        if note and feedback_callback:
            try:
                feedback_data = {
                    "type": "note_generated",
                    "note_id": note.note_id,
                    "source_type": source_type, # This is 'document_window' or 'web'
                    "source_id": source_id,     # This is doc_id or url
                    "content_preview": note.content[:75] + "...",
                    "source_metadata": note.source_metadata # Pass the metadata stored in the note
                }
                # Wrap the payload before calling the callback
                formatted_message = {"type": "agent_feedback", "payload": feedback_data}
                # Call with log_queue and formatted_message arguments
                feedback_callback(log_queue, formatted_message)
            except Exception as cb_err:
                    logger.error(f"Feedback callback failed for note_generated: {cb_err}", exc_info=False) # Don't log full trace for callback errors
            # --- End UI Feedback ---

        # --- Attempt to Fetch Full Content for Relevant Web Snippets ---
        if source_type == "web" and note: # Only if it's web and snippet was relevant
            logger.info(f"Web snippet for {source_id} deemed relevant. Attempting to fetch full content...")
            fetch_args = {
                "url": source_id, # URL is the source_id for web results
                "update_callback": feedback_callback, # Pass callback
                "log_queue": log_queue # Pass queue
            }
            fetch_result = None # Initialize fetch_result
            try:
                # Use _execute_tool (from BaseAgent) to run the fetcher, passing the registry override
                # _execute_tool handles finding the tool in the registry and running it
                # We assume _execute_tool logs its own call details internally or via callback
                fetch_result = await self._execute_tool(
                    "fetch_web_page_content",
                    fetch_args,
                    tool_registry_override=tool_registry_override, # Pass override
                    log_queue=log_queue, # <-- Pass log_queue
                    update_callback=update_callback # <-- Pass update_callback
                )

                if isinstance(fetch_result, dict) and "text" in fetch_result and "error" not in fetch_result:
                    full_text = fetch_result["text"]
                    fetched_title = fetch_result.get("title", source_metadata.get("title", "Unknown Title")) # Use fetched title if available
                    logger.info(f"Successfully fetched full text ({len(full_text)} chars) for {source_id}. Generating new note.")

                    # Create new metadata for the full content note
                    full_content_metadata = source_metadata.copy() # Start with original metadata (snippet, url)
                    full_content_metadata["title"] = fetched_title # Update title with potentially better one from fetcher
                    full_content_metadata["fetched_full_content"] = True
                    full_content_metadata["original_snippet"] = content_to_process # Keep original snippet

                    # --- Merge extracted metadata from the fetcher tool ---
                    fetched_metadata = fetch_result.get("metadata") # Get the metadata dict returned by the fetcher
                    if isinstance(fetched_metadata, dict):
                        logger.info(f"Merging extracted metadata from fetcher for {source_id}: {list(fetched_metadata.keys())}")
                        # Merge fetched metadata into full_content_metadata, prioritizing fetched values
                        # but keeping essential original keys like 'url' if not present in fetched.
                        # We avoid overwriting 'title', 'fetched_full_content', 'original_snippet' which we set explicitly above.
                        keys_to_avoid_overwrite = {"title", "fetched_full_content", "original_snippet", "url"}
                        for key, value in fetched_metadata.items():
                            if key not in keys_to_avoid_overwrite:
                                full_content_metadata[key] = value
                        # Ensure URL is present if it wasn't in fetched_metadata
                        if 'url' not in full_content_metadata:
                             full_content_metadata['url'] = source_id
                    else:
                        logger.warning(f"No valid metadata dictionary found in fetch_result for {source_id}. Using only original metadata.")
                    # --- End Merge ---

                    # Generate a new note using the full content
                    logger.info(f"Calling _generate_note_from_content for source {source_id} using full fetched content. Length: {len(full_text)}")
                    context_used_for_note = full_text # Capture full text context
                    full_note, full_model_details = await self._generate_note_from_content(
                        question_being_explored=question_or_goal,
                        section_id=section.section_id,
                        section_description=section.description,
                        focus_questions=focus_questions,
                        active_goals=active_goals, # <-- Pass active_goals
                        active_thoughts=active_thoughts, # <-- Pass active thoughts
                        source_type=source_type, # Still 'web'
                        source_id=source_id,     # Still the URL
                        source_metadata=full_content_metadata, # Use updated metadata
                        content_to_process=full_text, # Use the full fetched text
                        is_initial_exploration=is_initial_exploration,
                        feedback_callback=feedback_callback, # Pass feedback_callback
                        log_queue=log_queue, # Pass log_queue
                        update_callback=update_callback, # <-- Pass update_callback
                        tool_registry_override=tool_registry_override, # Pass override (needed by signature)
                        model=model # <-- Pass model parameter
                    )

                    if full_note:
                        logger.info(f"Successfully generated richer note {full_note.note_id} from full content for {source_id}. Replacing snippet-based note.")
                        # --- Send Feedback: Note Updated ---
                        if feedback_callback:
                            try:
                                feedback_data = {
                                    "type": "note_updated_from_full_content",
                                    "original_note_id": note.note_id, # ID of the note being replaced
                                    "new_note_id": full_note.note_id,
                                    "source_id": source_id,
                                    "content_preview": full_note.content[:75] + "..."
                                }
                                # Wrap the payload before calling the callback
                                formatted_message = {"type": "agent_feedback", "payload": feedback_data}
                                # Call with log_queue and formatted_message arguments
                                feedback_callback(log_queue, formatted_message)
                            except Exception as cb_err:
                                logger.error(f"Feedback callback failed for note_updated: {cb_err}", exc_info=False)
                        # --- End Feedback ---
                        # Return the new note, its details, and the context used (full text)
                        return full_note, full_model_details, context_used_for_note
                    else:
                        logger.warning(f"Failed to generate note from fetched full content for {source_id}. Falling back to snippet-based note {note.note_id if note else 'None'}.")
                        # Fall through to return original snippet note (and its context)

                elif isinstance(fetch_result, dict) and "error" in fetch_result:
                    # Log fetch errors as warnings
                    logger.warning(f"Failed to fetch/process full content for {source_id}: {fetch_result['error']}. Using snippet-based note {note.note_id if note else 'None'}.")
                    # Fall through to return original snippet note (and its context)
                else:
                    logger.warning(f"Unexpected result from fetch_web_page_content tool for {source_id}: {str(fetch_result)[:100]}. Using snippet-based note {note.note_id if note else 'None'}.")
                    # Fall through to return original snippet note (and its context)
            except Exception as e:
                logger.error(f"Error occurred during full content fetch or processing for {source_id}: {e}. Using snippet-based note {note.note_id if note else 'None'}.", exc_info=True)
                # Fall through to return original snippet note (and its context)
            # Removed misindented comment

        # Return the original note (or None if irrelevant), its details, and the context used (initial content)
        return note, note_model_details, context_used_for_note
