import logging
from typing import Dict, Any, Optional, List, Callable, Tuple, Set
import asyncio
import queue
import json
from collections import deque

from ai_researcher import config
from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT
from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection, SimplifiedPlanResponse
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput, SuggestedSubsectionTopic
from ai_researcher.agentic_layer.agents.note_assignment_agent import AssignedNotes

# Import utilities
from ai_researcher.agentic_layer.controller.utils import outline_utils
from ai_researcher.agentic_layer.controller.utils.status_checks import acheck_mission_status, check_mission_status_async, MissionStoppedException
from ai_researcher.agentic_layer.schemas.assignments import FullNoteAssignments

# Import config at the top
from ai_researcher import config 

logger = logging.getLogger(__name__)

class ResearchManager:
    """
    Manages the research phase of the mission, including initial research,
    outline generation, and research plan execution.
    """
    
    def __init__(self, controller):
        """
        Initialize the ResearchManager with a reference to the AgentController.
        
        Args:
            controller: The AgentController instance
        """
        self.controller = controller
        
    @acheck_mission_status
    async def run_initial_research_phase(
        self,
        mission_id: str,
        user_request: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None,
        feedback_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        initial_questions_override: Optional[List[str]] = None,
        tool_selection: Optional[Dict[str, bool]] = None
    ) -> Tuple[List[Note], Optional[str]]:
        """
        Orchestrates the initial question exploration phase using ResearchAgent.explore_question.
        If initial_questions_override is provided, uses those questions; otherwise, generates them.
        Returns the list of relevant notes gathered and the final agent scratchpad content.
        Accepts an optional feedback_callback for UI updates.
        """
        logger.info(f"--- Starting Initial Research Phase for mission {mission_id} ---")
        
        # Import dynamic config functions to get mission-specific settings
        from ai_researcher.dynamic_config import (
            get_initial_research_max_depth, 
            get_initial_research_max_questions,
            get_initial_exploration_doc_results,
            get_initial_exploration_web_results
        )
        max_depth = get_initial_research_max_depth(mission_id)
        max_questions = get_initial_research_max_questions(mission_id)
        initial_doc_results = get_initial_exploration_doc_results(mission_id)
        initial_web_results = get_initial_exploration_web_results(mission_id)
        logger.info(f"Limits: Max Depth={max_depth}, Max Questions={max_questions}")
        logger.info(f"Initial exploration settings: Doc results={initial_doc_results}, Web results={initial_web_results}")
        
        # Get Tool Selection and Filter Tools
        if tool_selection is None:
            # Try to get tool selection from mission metadata
            mission_context = self.controller.context_manager.get_mission_context(mission_id)
            if mission_context and mission_context.metadata:
                tool_selection = mission_context.metadata.get("tool_selection", {'local_rag': True, 'web_search': True})
            else:
                # Default if not provided and not in metadata
                tool_selection = {'local_rag': True, 'web_search': True}
                
        logger.info(f"Initial Research Phase using tool selection: {tool_selection}")
        
        # Create filtered tool registry based on selection
        filtered_tool_registry = ToolRegistry()
        
        # Register only enabled tools
        if tool_selection.get('local_rag', True):
            doc_search_tool = self.controller.tool_registry.get_tool("document_search")
            if doc_search_tool: 
                filtered_tool_registry.register_tool(doc_search_tool)
                logger.info("Document search tool registered for initial research phase")
                
        if tool_selection.get('web_search', True):
            web_search_tool = self.controller.tool_registry.get_tool("web_search")
            if web_search_tool:
                filtered_tool_registry.register_tool(web_search_tool)
                logger.info("Web search tool registered for initial research phase")
            # Also register fetch_web_page_content if web search is enabled
            web_fetcher_tool = self.controller.tool_registry.get_tool("fetch_web_page_content")
            if web_fetcher_tool:
                filtered_tool_registry.register_tool(web_fetcher_tool)
                logger.info("Web page fetcher tool registered for initial research phase")

        # Always include calculator and file reader tools
        calc_tool = self.controller.tool_registry.get_tool("calculator")
        if calc_tool: filtered_tool_registry.register_tool(calc_tool)
        file_reader_tool = self.controller.tool_registry.get_tool("read_full_document")
        if file_reader_tool: filtered_tool_registry.register_tool(file_reader_tool)
        
        logger.info(f"Initial Research Phase using filtered tools: {list(filtered_tool_registry._tools.keys())}")

        initial_questions: List[str] = []
        if initial_questions_override:
            logger.info(f"Using {len(initial_questions_override)} provided initial questions.")
            initial_questions = initial_questions_override
        else:
            # Generate initial questions if not overridden
            logger.info("Generating initial questions as none were provided.")
            # Pass queue and callback to _generate_first_level_questions
            generated_questions, model_details = await self._generate_first_level_questions(
                user_request,
                log_queue=log_queue,
                update_callback=update_callback
            )
            
            if generated_questions:
                self.controller.context_manager.log_execution_step(
                    mission_id, "AgentController", "Generate Initial Questions (Controller)",
                    input_summary=f"User Request: {user_request[:50]}...",
                    output_summary=f"Generated {len(generated_questions)} initial questions.",
                    status="success" if generated_questions and user_request not in generated_questions else "failure",
                    full_input={'user_request': user_request},
                    full_output=generated_questions,
                    model_details=model_details,
                    log_queue=log_queue, update_callback=update_callback
                )
            
            # Update Stats for the _generate_first_level_questions call
            if model_details:
                self.controller.context_manager.update_mission_stats(mission_id, model_details, log_queue, update_callback)
                
            initial_questions = generated_questions

        if not initial_questions:
            logger.error("Failed to generate any initial questions. Aborting initial research.")
            return [], None

        # Initialize exploration state
        question_queue = deque([(q, 0) for q in initial_questions])  # (question, depth)
        questions_explored_count = 0
        all_relevant_notes: List[Note] = []
        current_scratchpad: Optional[str] = self.controller.context_manager.get_scratchpad(mission_id)
        processed_questions = set()
        
        # Add counters for questions at each depth
        questions_by_depth = {0: len(initial_questions)}
        questions_processed_by_depth = {0: 0}
        sub_questions_generated_by_depth = {0: 0}
        
        # Log initial queue state
        logger.info(f"Initial question queue: {len(question_queue)} questions at depth 0")

        # Concurrency Setup
        running_tasks = set()
        max_concurrent = config.MAX_CONCURRENT_REQUESTS if config.MAX_CONCURRENT_REQUESTS > 0 else float('inf')

        # Loop while there are questions to process or tasks running
        while question_queue or running_tasks:
            # Check mission status at the beginning of each loop iteration
            if not await check_mission_status_async(self.controller, mission_id):
                logger.info(f"Mission {mission_id} stopped/paused during initial research phase. Cancelling remaining tasks.")
                # Cancel all running tasks
                for task in running_tasks:
                    task.cancel()
                # Wait for tasks to complete cancellation
                if running_tasks:
                    await asyncio.gather(*running_tasks, return_exceptions=True)
                logger.info(f"Initial research phase terminated early for mission {mission_id}. Processed {questions_explored_count} questions.")
                return all_relevant_notes, current_scratchpad
            
            # Launch New Tasks
            if max_concurrent == float('inf'):
                can_launch_potential = float('inf')
            else:
                can_launch_potential = max(0, max_concurrent - len(running_tasks))

            if can_launch_potential == float('inf'):
                can_launch = float('inf')
            else:
                can_launch = int(can_launch_potential)

            launch_counter_this_batch = 0
            while can_launch > 0 and question_queue and questions_explored_count < max_questions:
                current_question, current_depth = question_queue.popleft()

                if current_question in processed_questions:
                    logger.debug(f"Skipping already processed question: {current_question}")
                    continue
                
                if current_depth > max_depth:
                    logger.info(f"Skipping question due to max depth ({max_depth}): {current_question}")
                    continue

                questions_explored_count += 1
                processed_questions.add(current_question)
                
                questions_processed_by_depth[current_depth] = questions_processed_by_depth.get(current_depth, 0) + 1

                logger.info(f"Launching task for Q {questions_explored_count}/{max_questions} (Depth {current_depth}): '{current_question}'")

                async def explore_task_coro(q, d, q_count, scratch):
                    try:
                        # Fetch Active Goals & Thoughts INSIDE the task
                        active_goals = self.controller.context_manager.get_active_goals(mission_id)
                        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)

                        # Apply Semaphore INSIDE the task
                        async with self.controller.maybe_semaphore:
                            # Call the agent's explore_question method
                            result_tuple = await self.controller.research_agent.explore_question(
                                question=q,
                                mission_id=mission_id,
                                mission_goal=user_request,
                                active_goals=active_goals,
                                active_thoughts=active_thoughts,
                                current_depth=d,
                                max_depth=max_depth,
                                max_questions=max_questions,
                                questions_explored_count=q_count,
                                agent_scratchpad=scratch,
                                feedback_callback=feedback_callback,
                                log_queue=log_queue,
                                update_callback=update_callback,
                                tool_registry=filtered_tool_registry
                            )
                        return (q, d, result_tuple)
                    except Exception as task_e:
                        logger.error(f"Error in exploration task for question '{q}': {task_e}", exc_info=True)
                        return (q, d, task_e)

                task = asyncio.create_task(explore_task_coro(current_question, current_depth, questions_explored_count, current_scratchpad))
                running_tasks.add(task)

                if can_launch != float('inf'):
                    can_launch -= 1
                launch_counter_this_batch += 1

            # Wait for Tasks to Complete
            if not running_tasks:
                break

            done, pending = await asyncio.wait(running_tasks, return_when=asyncio.FIRST_COMPLETED)

            # Process Completed Tasks
            last_scratchpad_update_in_batch = None
            for task in done:
                running_tasks.remove(task)
                
                try:
                    task_result = task.result()
                    original_question, original_depth, result_data = task_result

                    if isinstance(result_data, Exception):
                        logger.error(f"Exploration task for '{original_question}' failed: {result_data}")
                        self.controller.context_manager.log_execution_step(
                            mission_id=mission_id, agent_name=self.controller.research_agent.agent_name,
                            action=f"Explore Question (Depth {original_depth})",
                            input_summary=f"Q: {original_question[:60]}...", status="failure", error_message=str(result_data),
                            full_input={"question": original_question, "depth": original_depth, "scratchpad": current_scratchpad},
                            log_queue=log_queue, update_callback=update_callback
                        )
                        continue

                    relevant_notes_with_context, new_sub_questions, updated_scratchpad, exec_details = result_data
                    actual_notes = [note_tuple[0] for note_tuple in relevant_notes_with_context]

                    self.controller.context_manager.log_execution_step(
                        mission_id, self.controller.research_agent.agent_name, f"Explore Question (Depth {original_depth})",
                        input_summary=f"Q: {original_question[:60]}...",
                        output_summary=f"{len(actual_notes)} relevant notes found. {len(new_sub_questions)} new sub-Q generated.",
                        status="success",
                        full_input={"question": original_question, "depth": original_depth, "scratchpad": current_scratchpad},
                        full_output={
                            "relevant_notes": [note.model_dump() for note in actual_notes],
                            "new_sub_questions": new_sub_questions,
                            "updated_scratchpad": updated_scratchpad,
                            "note_contents": [note.content[:100] + "..." for note in actual_notes]
                        },
                        model_details=exec_details.get("model_calls")[0] if exec_details.get("model_calls") else None,
                        tool_calls=exec_details.get("tool_calls"),
                        file_interactions=exec_details.get("file_interactions"),
                        log_queue=log_queue, update_callback=update_callback
                    )

                    if actual_notes:
                        all_relevant_notes.extend(actual_notes)
                        self.controller.context_manager.add_notes(mission_id, actual_notes)

                    if updated_scratchpad is not None:
                        last_scratchpad_update_in_batch = updated_scratchpad

                    if new_sub_questions:
                        sub_questions_generated_by_depth[original_depth] = sub_questions_generated_by_depth.get(original_depth, 0) + len(new_sub_questions)
                        
                        next_depth = original_depth + 1
                        added_to_queue = 0
                        if (questions_explored_count + len(question_queue) + len(running_tasks)) < max_questions:
                            for sub_q in new_sub_questions:
                                if sub_q not in processed_questions:
                                    question_queue.append((sub_q, next_depth))
                                    added_to_queue += 1
                            
                            if added_to_queue > 0:
                                questions_by_depth[next_depth] = questions_by_depth.get(next_depth, 0) + added_to_queue
                                logger.info(f"Added {added_to_queue} sub-questions at depth {next_depth} to queue. Current queue size: {len(question_queue)}")
                        else:
                            logger.warning(f"Max questions limit ({max_questions}) reached or approached. Cannot add {len(new_sub_questions)} new sub-questions to queue.")

                except Exception as task_exec_e:
                    logger.error(f"Error retrieving result from exploration task: {task_exec_e}", exc_info=True)
                    self.controller.context_manager.log_execution_step(
                        mission_id=mission_id, agent_name=self.controller.research_agent.agent_name,
                        action="Explore Question Task Execution",
                        input_summary="N/A", status="failure", error_message=f"Task execution error: {task_exec_e}",
                        log_queue=log_queue, update_callback=update_callback
                    )

            # Apply Scratchpad Update (Last Write Wins in Batch)
            if last_scratchpad_update_in_batch is not None and last_scratchpad_update_in_batch != current_scratchpad:
                logger.info("Applying scratchpad update from last completed task in batch.")
                current_scratchpad = last_scratchpad_update_in_batch
                self.controller.context_manager.update_scratchpad(mission_id, current_scratchpad)

            # Log Queue State
            depth_counts = {}
            for _, d in question_queue: depth_counts[d] = depth_counts.get(d, 0) + 1
            depth_info = ", ".join([f"Depth {d}: {count}" for d, count in sorted(depth_counts.items())])
            logger.info(f"Current queue: {len(question_queue)} questions ({depth_info}). Running tasks: {len(running_tasks)}.")

        # Log final statistics
        logger.info(f"--- Initial Research Phase Completed for mission {mission_id} ---")
        logger.info(f"Tasks launched (approx. questions explored): {questions_explored_count}/{max_questions}")
        logger.info(f"Questions by depth: {questions_by_depth}")
        logger.info(f"Questions processed by depth: {questions_processed_by_depth}")
        logger.info(f"Sub-questions generated by depth: {sub_questions_generated_by_depth}")
        logger.info(f"Termination reason: {'Max questions reached' if questions_explored_count >= max_questions else 'Queue empty'}")
        logger.info(f"Total relevant notes found: {len(all_relevant_notes)}")
        
        return all_relevant_notes, current_scratchpad

    @acheck_mission_status
    async def _generate_first_level_questions(
        self,
        user_request: str,
        n_questions: int = 5,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> Tuple[List[str], Optional[Dict[str, Any]]]:
        """
        Generates the first set of high-level research questions, informed by an initial document search.
        Accepts log_queue and update_callback for logging.
        """
        logger.info(f"Generating initial high-level research questions for: '{user_request[:50]}...'")
        
        # Step 1: Initial Document Search (Conditional)
        search_context_str = "Initial document search skipped by configuration."
        search_tool_results = None
        search_log_details = {}

        if config.CONSULT_RAG_FOR_INITIAL_QUESTIONS:
            logger.info("Configuration allows consulting RAG for initial questions. Attempting document search...")
            try:
                doc_search_tool = self.controller.tool_registry.get_tool("document_search")
                if doc_search_tool:
                    logger.info("Performing initial document search...")
                    # Use mission-specific setting for initial exploration doc results
                    num_results = 3  # This should use mission-specific setting
                    async with self.controller.maybe_semaphore:
                        search_tool_results = await doc_search_tool.implementation(query=user_request, n_results=num_results)

                    if search_tool_results and isinstance(search_tool_results, list) and search_tool_results:
                        snippets = [f"- {result.get('content', 'N/A')}" for result in search_tool_results]
                        search_context_str = f"Initial Document Search Context (Top {len(snippets)} results):\n" + "\n".join(snippets)
                        logger.info(f"Found {len(snippets)} relevant snippets from initial search.")
                        search_log_details = {"tool_name": "document_search", "arguments": {"query": user_request, "n_results": num_results}, "result_summary": f"{len(snippets)} snippets found."}
                    else:
                        search_context_str = "Initial document search returned no relevant snippets."
                        logger.info(search_context_str)
                        search_log_details = {"tool_name": "document_search", "arguments": {"query": user_request, "n_results": num_results}, "result_summary": "No snippets found."}
                else:
                    search_context_str = "DocumentSearchTool not found in registry. Skipping initial search."
                    logger.warning(search_context_str)
                    search_log_details = {"error": "DocumentSearchTool not found"}

            except Exception as search_e:
                logger.error(f"Error during initial document search: {search_e}", exc_info=True)
                search_context_str = f"Error during initial search: {search_e}"
                search_log_details = {"error": str(search_e)}
        else:
            logger.info("Configuration disables consulting RAG for initial questions. Skipping document search.")
            search_log_details = {"skipped": "Configuration disabled initial RAG consultation"}

        # Step 2: Generate Questions using Search Context
        prompt_context = f"""
Based on the user's research request AND the initial document search context below, generate {n_questions} distinct, high-level research questions that need to be answered to fulfill the request. These questions should guide a detailed exploration, taking into account the preliminary findings.

User Request: "{user_request}"

{search_context_str}

Instructions:
- Generate {n_questions} questions.
- Ensure questions are distinct and high-level.
- Focus on breaking down the core request into its main components, informed by the search context.
- Output ONLY the list of questions, each on a new line. Do not number the questions.
"""
        model_details = None
        try:
            messages = [{"role": "user", "content": prompt_context}]
            async with self.controller.maybe_semaphore:
                response, model_details = await self.controller.model_dispatcher.dispatch(messages=messages, agent_mode="planning")

            if model_details:
                model_details["initial_search_details"] = search_log_details
            else:
                model_details = {"initial_search_details": search_log_details}

            if response and response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                questions = [q.strip() for q in content.strip().split('\n') if q.strip()]
                logger.info(f"Generated first-level questions: {questions}")
                return questions[:n_questions], model_details
            else:
                logger.error("LLM failed to generate initial questions.")
                return [user_request], model_details
        except Exception as e:
            logger.error(f"Error generating first-level questions: {e}", exc_info=True)
            return [user_request], {"error": str(e)}
            
    @acheck_mission_status
    async def generate_preliminary_outline(
        self,
        mission_id: str,
        user_request: str,
        initial_notes: List[Note],
        initial_scratchpad: Optional[str],
        tool_selection: Dict[str, bool],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> Optional[SimplifiedPlan]:
        """
        Generates the initial research outline based on the richer context from the initial research phase,
        considering the user's tool selection.
        Handles batching of notes context if it exceeds MAX_PLANNING_CONTEXT_CHARS.
        """
        # Add Default for tool_selection if None
        if tool_selection is None:
            logger.warning(f"tool_selection was None in generate_preliminary_outline for mission {mission_id}. Defaulting to all tools enabled.")
            tool_selection = {'local_rag': True, 'web_search': True}

        logger.info(f"Generating preliminary outline for mission {mission_id} using initial research findings and tool selection: {tool_selection}...")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)

        # Calculate Total Character Count and Check Limit
        total_chars = sum(len(note.content) for note in initial_notes)
        char_limit = config.MAX_PLANNING_CONTEXT_CHARS
        needs_batching = total_chars > char_limit
        logger.info(f"Total characters in initial notes: {total_chars}. Limit: {char_limit}. Batching needed: {needs_batching}")

        # Prepare Note Batches if Needed
        note_batches: List[List[Note]] = []
        if needs_batching:
            current_batch: List[Note] = []
            current_batch_chars = 0
            for note in initial_notes:
                note_len = len(note.content)
                # If adding the current note exceeds the limit AND the current batch is not empty, finalize the batch
                if current_batch_chars + note_len > char_limit and current_batch:
                    note_batches.append(current_batch)
                    current_batch = [note]
                    current_batch_chars = note_len
                else:
                    # Add to current batch (even if it's the first note and already over limit)
                    current_batch.append(note)
                    current_batch_chars += note_len
            # Add the last batch if it's not empty
            if current_batch:
                note_batches.append(current_batch)
            logger.info(f"Split {len(initial_notes)} notes ({total_chars} chars) into {len(note_batches)} batches.")
        else:
            note_batches.append(initial_notes)  # Single batch containing all notes

        # Format Notes Context String Helper
        def format_notes_context(notes_batch: List[Note], batch_num: int = 0, total_batches: int = 1) -> str:
            # Use a slightly different header for the context string
            context_str = f"Collected Notes Context (Batch {batch_num + 1}/{total_batches} for outline generation):\n"
            if notes_batch:
                # Add total note count for context
                context_str += f"Processing {len(notes_batch)} notes in this batch (out of {len(initial_notes)} total). Use these notes and their IDs to inform the outline structure and populate the 'associated_note_ids' field for relevant sections.\n\n"
                for note in notes_batch:
                    # Add the missing "- " prefix here
                    context_str += f"- Note ID: {note.note_id}\n"
                    # Temporarily remove content preview for debugging
                    # context_str += f"  - Content Preview: {note.content[:50]}...\n" # Using note.content directly, no escape needed if not printing
                    context_str += f"  - Source: {note.source_type} - {note.source_id}\n\n"
            else:
                context_str += "No notes in this batch.\n"
            return context_str

        # Call Planning Agent (Iteratively if Batching)
        plan_response: Optional[SimplifiedPlanResponse] = None
        final_plan_obj: Optional[SimplifiedPlan] = None
        model_call_details_list: List[Dict[str, Any]] = []  # Collect details from all calls
        last_successful_plan_response: Optional[SimplifiedPlanResponse] = None  # Keep track of the last good plan

        for i, batch in enumerate(note_batches):
            logger.info(f"Processing planning batch {i+1}/{len(note_batches)}...")
            # Fetch latest scratchpad before each call
            current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)
            batch_plan_response = None
            batch_model_details = None
            batch_scratchpad_update = None
            log_action = f"Generate/Revise Outline (Batch {i+1})"  # Generic action name

            try:
                if i == 0:
                    # First Batch: Use final_outline_context
                    notes_context_str = format_notes_context(batch, i, len(note_batches))
                    # Use initial_scratchpad only for the very first call
                    context_scratchpad = initial_scratchpad if initial_scratchpad is not None else current_scratchpad
                    if context_scratchpad:
                        notes_context_str += f"\nAgent's Initial Thoughts/Scratchpad:\n---\n{context_scratchpad}\n---\n"

                    # Add Tool Availability Context
                    tool_context = "\nAvailable Research Tools:\n"
                    if tool_selection.get('local_rag', True):
                        tool_context += "- Local Document Search (RAG) is ENABLED.\n"
                    else:
                        tool_context += "- Local Document Search (RAG) is DISABLED.\n"
                    if tool_selection.get('web_search', True):
                        tool_context += "- Web Search is ENABLED.\n"
                    else:
                        tool_context += "- Web Search is DISABLED.\n"
                    tool_context += "Generate research steps ONLY using the ENABLED tools.\n"
                    notes_context_str += tool_context  # Append tool info to the main context

                    # Fetch Active Goals & Thoughts
                    active_goals = self.controller.context_manager.get_active_goals(mission_id)
                    active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)

                    async with self.controller.maybe_semaphore:
                        batch_plan_response, batch_model_details, batch_scratchpad_update = await self.controller.planning_agent.run(
                            user_request=user_request,
                            final_outline_context=notes_context_str,  # Context now includes tool info
                            active_goals=active_goals,
                            active_thoughts=active_thoughts,
                            agent_scratchpad=context_scratchpad,
                            mission_id=mission_id,
                            log_queue=log_queue,
                            update_callback=update_callback
                        )
                    log_action = "Generate Preliminary Outline (Batch 1)"

                    # ADD AGENT STEP LOGGING
                    log_status_planning = "success" if batch_plan_response and not batch_plan_response.parsing_error else "failure"
                    log_error_planning = batch_plan_response.parsing_error if batch_plan_response and batch_plan_response.parsing_error else ("Agent returned None" if not batch_plan_response else None)
                    self.controller.context_manager.log_execution_step(
                        mission_id=mission_id,
                        agent_name=self.controller.planning_agent.agent_name,
                        action=log_action,
                        input_summary=f"User Request: {user_request[:50]}..., Batch 1 Notes Context",
                        output_summary=f"Generated outline with {len(batch_plan_response.report_outline) if batch_plan_response else 'N/A'} sections." if log_status_planning == "success" else log_error_planning,
                        status=log_status_planning,
                        error_message=log_error_planning,
                        full_input={'user_request': user_request, 'final_outline_context': notes_context_str},
                        full_output=batch_plan_response.model_dump() if batch_plan_response else None,
                        model_details=batch_model_details,
                        log_queue=log_queue,
                        update_callback=update_callback
                    )

                    # Handle Generated Thought
                    if batch_plan_response and hasattr(batch_plan_response, 'generated_thought') and batch_plan_response.generated_thought:
                        self.controller.context_manager.add_thought(mission_id, self.controller.planning_agent.agent_name, batch_plan_response.generated_thought)
                        logger.info(f"PlanningAgent generated thought (Batch 1): {batch_plan_response.generated_thought}")

                else:
                    # Subsequent Batches: Use revision_context
                    # Use the plan from the *last successful* batch for revision
                    if not last_successful_plan_response:
                        logger.error(f"Cannot process batch {i+1}: Previous planning step failed or produced no plan.")
                        raise RuntimeError("Previous planning step failed, cannot continue batching.")

                    notes_context_str = format_notes_context(batch, i, len(note_batches))
                    current_outline_str = "Current Report Outline Structure (from previous batch):\n" + "\n".join(
                        outline_utils.format_outline_for_prompt(last_successful_plan_response.report_outline)
                    )
                    # Add current scratchpad to revision context
                    revision_scratchpad_context = f"\nCurrent Agent Scratchpad:\n---\n{current_scratchpad or 'None'}\n---\n"

                    # Add Tool Availability Context for Revision
                    tool_context = "\nAvailable Research Tools:\n"
                    if tool_selection.get('local_rag', True):
                        tool_context += "- Local Document Search (RAG) is ENABLED.\n"
                    else:
                        tool_context += "- Local Document Search (RAG) is DISABLED.\n"
                    if tool_selection.get('web_search', True):
                        tool_context += "- Web Search is ENABLED.\n"
                    else:
                        tool_context += "- Web Search is DISABLED.\n"
                    tool_context += "Ensure research steps ONLY use the ENABLED tools.\n"

                    revision_prompt = (
                        f"Original User Request:\n{user_request}\n\n"
                        f"{current_outline_str}\n\n{notes_context_str}\n\n{revision_scratchpad_context}\n{tool_context}\n"
                        f"Instruction: You are refining a research plan. Integrate the notes provided in the 'Collected Notes Context (Batch {i+1}/{len(note_batches)})' into the 'Current Report Outline Structure'. "
                        f"Assign the `note_id`s from this batch to the most relevant sections in the outline by updating the `associated_note_ids` field. "
                        f"You MAY slightly adjust section descriptions or add minor subsections IF the new notes strongly justify it, but prioritize assigning notes to the existing structure. "
                        f"Ensure the final outline remains coherent and adheres to depth limits. "
                        f"Generate the complete, updated plan including the revised outline and steps. "
                        f"Output ONLY the JSON object conforming to the SimplifiedPlanResponse schema."
                    )
                    # Fetch Active Goals & Thoughts
                    active_goals = self.controller.context_manager.get_active_goals(mission_id)
                    active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
                    
                    async with self.controller.maybe_semaphore:
                        batch_plan_response, batch_model_details, batch_scratchpad_update = await self.controller.planning_agent.run(
                            user_request=user_request,
                            revision_context=revision_prompt,
                            active_goals=active_goals,
                            active_thoughts=active_thoughts,
                            agent_scratchpad=current_scratchpad,
                            mission_id=mission_id,
                            log_queue=log_queue,
                            update_callback=update_callback
                        )
                    log_action = f"Revise Outline (Batch {i+1})"

                    # ADD AGENT STEP LOGGING
                    log_status_planning_rev = "success" if batch_plan_response and not batch_plan_response.parsing_error else "failure"
                    log_error_planning_rev = batch_plan_response.parsing_error if batch_plan_response and batch_plan_response.parsing_error else ("Agent returned None" if not batch_plan_response else None)
                    self.controller.context_manager.log_execution_step(
                        mission_id=mission_id,
                        agent_name=self.controller.planning_agent.agent_name,
                        action=log_action,
                        input_summary=f"Revision Context Batch {i+1}",
                        output_summary=f"Revised outline with {len(batch_plan_response.report_outline) if batch_plan_response else 'N/A'} sections." if log_status_planning_rev == "success" else log_error_planning_rev,
                        status=log_status_planning_rev,
                        error_message=log_error_planning_rev,
                        full_input={'revision_context': revision_prompt},
                        full_output=batch_plan_response.model_dump() if batch_plan_response else None,
                        model_details=batch_model_details,
                        log_queue=log_queue,
                        update_callback=update_callback
                    )

                    # Handle Generated Thought
                    if batch_plan_response and hasattr(batch_plan_response, 'generated_thought') and batch_plan_response.generated_thought:
                        self.controller.context_manager.add_thought(mission_id, self.controller.planning_agent.agent_name, batch_plan_response.generated_thought)
                        logger.info(f"PlanningAgent generated thought (Batch {i+1}): {batch_plan_response.generated_thought}")

                # Process Batch Result
                if batch_model_details:
                    model_call_details_list.append(batch_model_details)
                if batch_scratchpad_update:
                    self.controller.context_manager.update_scratchpad(mission_id, batch_scratchpad_update)
                    logger.info(f"Updated scratchpad after planning batch {i+1}.")

                if not batch_plan_response or not isinstance(batch_plan_response, SimplifiedPlanResponse) or batch_plan_response.parsing_error:
                    error_msg = "PlanningAgent failed or returned invalid/error response"
                    if batch_plan_response and batch_plan_response.parsing_error:
                        error_msg += f": {batch_plan_response.parsing_error}"
                    logger.error(f"{error_msg} for batch {i+1}.")
                    self.controller.context_manager.log_execution_step(
                        mission_id, "PlanningAgent", log_action,
                        input_summary=f"Processing batch {i+1} notes.", status="failure",
                        error_message=error_msg, model_details=batch_model_details,
                        log_queue=log_queue, update_callback=update_callback
                    )
                    # Don't update last_successful_plan_response on failure
                    if i == 0:  # Fail mission if the first batch fails
                        raise RuntimeError(f"Planning agent failed for initial batch {i+1}")
                    else:  # Continue with the last successful plan if a later batch fails
                        logger.warning(f"Continuing mission with plan from batch {i}, as batch {i+1} failed.")
                        plan_response = last_successful_plan_response  # Restore last good plan
                        break  # Exit the batch loop

                # Update the main plan_response and the last successful one
                plan_response = batch_plan_response
                last_successful_plan_response = plan_response  # Store the latest good plan
                logger.info(f"Successfully processed planning batch {i+1}/{len(note_batches)}.")
            except Exception as batch_e:
                logger.error(f"Error processing planning batch {i+1}: {batch_e}", exc_info=True)
                # Log failure
                self.controller.context_manager.log_execution_step(
                    mission_id, "PlanningAgent", log_action,
                    input_summary=f"Processing batch {i+1} notes.", status="failure",
                    error_message=str(batch_e), model_details=batch_model_details,
                    log_queue=log_queue, update_callback=update_callback
                )
                if i == 0:  # Fail mission if the first batch fails
                    raise  # Re-raise to stop the mission start
                else:  # Continue with the last successful plan
                    logger.warning(f"Continuing mission with plan from batch {i}, as batch {i+1} encountered an exception.")
                    plan_response = last_successful_plan_response
                    break  # Exit the batch loop

        # Final Processing after all batches
        if plan_response:  # Use the final plan_response (either last successful or from single batch)
            try:
                # Convert the final response to SimplifiedPlan
                final_plan_obj = SimplifiedPlan(
                    mission_goal=plan_response.mission_goal,
                    report_outline=plan_response.report_outline
                )
                
                # Fix: If there's only one section, automatically convert it to research-based
                if len(final_plan_obj.report_outline) == 1:
                    logger.info(f"Auto-converting single section to research_based for mission {mission_id}")
                    final_plan_obj.report_outline[0].research_strategy = "research_based"
                
                # Validate the outline has at least one section and at least one research-based section
                validation_result = self.controller._validate_outline_minimum_requirements(final_plan_obj.report_outline)
                if not validation_result["valid"]:
                    logger.error(f"Outline validation failed: {validation_result['reason']}")
                    self.controller.context_manager.log_execution_step(
                        mission_id, "AgentController", "Validate Outline",
                        input_summary="Checking minimum outline requirements",
                        output_summary=f"Validation failed: {validation_result['reason']}",
                        status="failure",
                        error_message=validation_result['reason'],
                        log_queue=log_queue, update_callback=update_callback
                    )
                    return None
                
                logger.info(f"Preliminary outline generated/finalized for mission {mission_id} after {len(note_batches)} batches.")
                # Log final success summary
                self.controller.context_manager.log_execution_step(
                    mission_id, "AgentController", "Finalize Preliminary Outline",
                    input_summary=f"Processed {len(note_batches)} batches.",
                    output_summary=f"Final outline has {len(final_plan_obj.report_outline)} sections.",
                    status="success",
                    full_output=final_plan_obj.model_dump(),
                    # Pass details of the first model call from the batch processing
                    model_details=model_call_details_list[0] if model_call_details_list else None,
                    log_queue=log_queue, update_callback=update_callback
                )
                return final_plan_obj
            except Exception as e:
                logger.error(f"Error creating final SimplifiedPlan from batched response: {e}", exc_info=True)
                self.controller.context_manager.log_execution_step(
                    mission_id, "AgentController", "Finalize Preliminary Outline",
                    input_summary="Converting final batched response.", status="failure", error_message=str(e),
                    full_input=plan_response.model_dump() if plan_response else None,
                    # Pass details of the first model call from the batch processing
                    model_details=model_call_details_list[0] if model_call_details_list else None,
                    log_queue=log_queue, update_callback=update_callback
                )
                return None
        else:
            # This case implies failure during batching (likely first batch)
            logger.error(f"PlanningAgent failed to generate preliminary outline for mission {mission_id} (batching failed).")
            return None
            
    @acheck_mission_status
    async def execute_research_plan(
        self,
        mission_id: str,
        plan: SimplifiedPlan,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ) -> bool:
        """
        Manages the core structured research loop based on mission-specific settings.
        Includes research, reflection, and potential outline revision between rounds.
        """
        # Import dynamic config functions to get mission-specific settings
        from ai_researcher.dynamic_config import (
            get_structured_research_rounds,
            get_max_concurrent_requests,
            get_thought_pad_context_limit,
            get_skip_final_replanning
        )
        num_rounds = get_structured_research_rounds(mission_id)
        max_cycles_per_section = self.controller.max_research_cycles_per_section
        
        # Get mission-specific settings
        max_concurrent_requests = get_max_concurrent_requests(mission_id)
        thought_pad_context_limit = get_thought_pad_context_limit(mission_id)
        skip_final_replanning = get_skip_final_replanning(mission_id)
        
        logger.info(f"--- Starting Research Plan Execution ({num_rounds} Rounds, Max {max_cycles_per_section} cycles/section) for mission {mission_id} ---")
        logger.info(f"Mission-specific settings: max_concurrent={max_concurrent_requests}, thought_pad_limit={thought_pad_context_limit}, skip_final_replanning={skip_final_replanning}")

        # Create Mission-Specific Feedback Callback
        mission_feedback_callback = None
        if update_callback and log_queue:
            def _feedback_callback_impl(caller_log_queue: queue.Queue, feedback_data: Dict[str, Any]):
                try:
                    update_callback(log_queue, feedback_data)
                except Exception as e:
                    logger.error(f"Error calling update_callback with feedback message: {e}", exc_info=True)
            mission_feedback_callback = _feedback_callback_impl

        for round_num in range(1, num_rounds + 1):
            logger.info(f"--- Starting Research Round {round_num}/{num_rounds} ---")
            mission_context = self.controller.context_manager.get_mission_context(mission_id)
            if not mission_context or not mission_context.plan:
                logger.error(f"Mission context or plan missing at start of Round {round_num}. Aborting.")
                return False
            
            current_plan = mission_context.plan

            # Get Tool Selection and Filter Tools
            tool_selection = mission_context.metadata.get("tool_selection", {'local_rag': True, 'web_search': True})
            filtered_tool_registry = ToolRegistry()
            
            # Register only enabled tools
            if tool_selection.get('local_rag', True):
                doc_search_tool = self.controller.tool_registry.get_tool("document_search")
                if doc_search_tool: filtered_tool_registry.register_tool(doc_search_tool)
            if tool_selection.get('web_search', True):
                web_search_tool = self.controller.tool_registry.get_tool("web_search")
                if web_search_tool: filtered_tool_registry.register_tool(web_search_tool)
                # Also include web page fetcher if web search is enabled
                web_fetcher_tool = self.controller.tool_registry.get_tool("fetch_web_page_content")
                if web_fetcher_tool: filtered_tool_registry.register_tool(web_fetcher_tool)

            # Always include non-research tools
            calc_tool = self.controller.tool_registry.get_tool("calculator")
            if calc_tool: filtered_tool_registry.register_tool(calc_tool)
            file_reader_tool = self.controller.tool_registry.get_tool("read_full_document")
            if file_reader_tool: filtered_tool_registry.register_tool(file_reader_tool)
            
            logger.info(f"Round {round_num}: Using filtered tools based on selection {tool_selection}. Available: {list(filtered_tool_registry._tools.keys())}")

            # Send Tool Usage Feedback to UI
            if mission_feedback_callback:
                try:
                    tool_status_payload = {
                        "type": "tool_usage_status",
                        "round": round_num,
                        "local_rag_enabled": tool_selection.get('local_rag', True),
                        "web_search_enabled": tool_selection.get('web_search', True)
                    }
                    mission_feedback_callback(log_queue, tool_status_payload)
                    logger.info(f"Sent tool_usage_status feedback for Round {round_num}: {tool_status_payload}")
                except Exception as fb_err:
                    logger.error(f"Failed to send tool_usage_status feedback via callback: {fb_err}", exc_info=True)

            # Get sections in depth-first order for research from the *current* plan
            sections_in_research_order = outline_utils.get_sections_in_order(current_plan.report_outline)
            if not sections_in_research_order:
                logger.warning(f"No sections found in the outline for Round {round_num}. Skipping round.")
                continue

            processed_sections_this_round = set()
            refinement_iterations_this_round = {}
            round_focus_questions = {}
            round_reflection_outputs = []

            # Iterate through sections in depth-first order
            for section in sections_in_research_order:
                # Check mission status before processing each section
                if not await check_mission_status_async(self.controller, mission_id):
                    logger.info(f"Mission {mission_id} stopped/paused during research plan execution (Round {round_num}). Stopping section processing.")
                    return False
                
                section_id = section.section_id
                strategy = section.research_strategy

                logger.info(f"Round {round_num}: Processing section {section_id} ('{section.title}') - Strategy: {strategy}")

                # Check Strategy and Subsections BEFORE proceeding
                if strategy != "research_based":
                    logger.info(f"  Skipping research/reflection for section {section_id} ('{section.title}') due to strategy: {strategy}.")
                    processed_sections_this_round.add(section_id)
                    continue
                elif section.subsections:
                    logger.warning(f"  Skipping research/reflection for section {section_id} ('{section.title}'). It's marked 'research_based' but has subsections (likely an outline issue). Treating as a parent section.")
                    processed_sections_this_round.add(section_id)
                    continue
                else:
                    # Strategy is research_based AND it's a leaf node
                    logger.info(f"  Proceeding with research/reflection for leaf section {section_id} ('{section.title}').")
                    # Fetch Goals & Thoughts only for sections being researched
                    active_goals = self.controller.context_manager.get_active_goals(mission_id)
                    active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)

                    # Standard Research/Refinement Loop
                    current_focus_questions = round_focus_questions.get(section_id)
                    section_fully_refined = False
                    cycle_count = refinement_iterations_this_round.get(section_id, 0)

                    while cycle_count < max_cycles_per_section and not section_fully_refined:
                        logger.info(f"  Round {round_num} Research cycle {cycle_count+1}/{max_cycles_per_section} for section {section_id}...")

                        # Fetch context needed for ResearchAgent.run
                        current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)
                        all_mission_notes = self.controller.context_manager.get_notes(mission_id)
                        all_notes_dict = {note.note_id: note for note in all_mission_notes}

                        # Fetch notes already associated with this section from the plan
                        existing_notes_for_section = None
                        if hasattr(section, 'associated_note_ids') and section.associated_note_ids:
                            notes_to_pass = [all_notes_dict[note_id] for note_id in section.associated_note_ids if note_id in all_notes_dict]
                            if len(notes_to_pass) != len(section.associated_note_ids):
                                logger.warning(f"Could not find all associated notes for section {section.section_id} during research step. Found {len(notes_to_pass)}/{len(section.associated_note_ids)}.")
                            if notes_to_pass:
                                existing_notes_for_section = notes_to_pass
                                logger.info(f"  Passing {len(existing_notes_for_section)} existing associated notes to ResearchAgent for section {section.section_id}.")

                        # Run Research Agent - PASS THE FILTERED REGISTRY and Goals/Thoughts
                        generated_notes, research_details, scratchpad_update = await self.controller.research_agent.run(
                            mission_id=mission_id,
                            section=section,
                            focus_questions=current_focus_questions,
                            existing_notes=existing_notes_for_section,
                            agent_scratchpad=current_scratchpad,
                            feedback_callback=mission_feedback_callback,
                            log_queue=log_queue,
                            update_callback=update_callback,
                            tool_registry=filtered_tool_registry,
                            all_mission_notes=all_mission_notes,
                            active_goals=active_goals,
                            active_thoughts=active_thoughts
                        )

                        # ADD AGENT STEP LOGGING
                        log_input_summary = f"Section: '{section.title}'"
                        if current_focus_questions: log_input_summary += f", Focus Questions: {len(current_focus_questions)}"
                        log_cycle_num = cycle_count + 1
                        log_status = "success" if generated_notes is not None else "failure"
                        log_error_msg = None if log_status == "success" else "ResearchAgent failed to generate notes."

                        self.controller.context_manager.log_execution_step(
                            mission_id=mission_id,
                            agent_name=self.controller.research_agent.agent_name,
                            action=f"Research Section: {section.section_id} (Pass {round_num}, Cycle {log_cycle_num})",
                            input_summary=log_input_summary,
                            output_summary=f"Generated {len(generated_notes) if generated_notes else 0} notes.",
                            status=log_status,
                            error_message=log_error_msg,
                            full_input={'mission_id': mission_id, 'section': section.model_dump(), 'focus_questions': current_focus_questions},
                            full_output={
                                "generated_notes": [note.model_dump() for note in generated_notes] if generated_notes else [],
                                "note_contents": [note.content[:100] + "..." for note in generated_notes] if generated_notes else []
                            },
                            model_details=research_details.get("model_calls")[0] if research_details.get("model_calls") else None,
                            tool_calls=research_details.get("tool_calls"),
                            file_interactions=research_details.get("file_interactions"),
                            log_queue=log_queue,
                            update_callback=update_callback
                        )

                        # Update scratchpad if agent returned an update
                        if scratchpad_update:
                            self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                            logger.info(f"Updated scratchpad after research step for section {section.section_id} (Pass {round_num}, Cycle {log_cycle_num}).")

                        # Check if research failed critically
                        if generated_notes is None:
                            logger.warning(f"ResearchAgent failed to generate notes for section {section_id} in cycle {cycle_count+1}. Skipping reflection and stopping refinement for this section.")
                            section_fully_refined = True
                            continue
                        elif generated_notes:
                            # Add notes to context manager and associate with section
                            try:
                                # First, add the generated notes to the context manager
                                if generated_notes:
                                    self.controller.context_manager.add_notes(mission_id, generated_notes)
                                    logger.info(f"  Added {len(generated_notes)} notes to context manager for mission {mission_id}.")
                                
                                # Then associate the note IDs with the section
                                current_plan_for_update = self.controller.context_manager.get_mission_context(mission_id).plan
                                if current_plan_for_update:
                                    section_obj_to_update = outline_utils.find_section_recursive(current_plan_for_update.report_outline, section_id)
                                    if section_obj_to_update:
                                        new_note_ids = {note.note_id for note in generated_notes}
                                        # Ensure associated_note_ids exists and is a list
                                        if not hasattr(section_obj_to_update, 'associated_note_ids') or section_obj_to_update.associated_note_ids is None:
                                            section_obj_to_update.associated_note_ids = []
                                        
                                        # Use a set for efficient update and avoid duplicates
                                        existing_ids = set(section_obj_to_update.associated_note_ids)
                                        updated_ids = existing_ids.union(new_note_ids)
                                        
                                        if len(updated_ids) > len(existing_ids):
                                            section_obj_to_update.associated_note_ids = sorted(list(updated_ids))
                                            self.controller.context_manager.store_plan(mission_id, current_plan_for_update)
                                            logger.info(f"  Associated {len(new_note_ids)} new notes with section {section_id}. Total associated: {len(section_obj_to_update.associated_note_ids)}.")
                                        else:
                                            logger.debug(f"  No new note IDs to associate with section {section_id}.")
                                    else:
                                        logger.error(f"Could not find section {section_id} in plan to associate notes.")
                                else:
                                    logger.error(f"Could not retrieve plan to associate notes for section {section_id}.")
                            except Exception as assoc_err:
                                logger.error(f"Error adding notes to context manager or associating with section {section_id}: {assoc_err}", exc_info=True)

                        # Run Reflection Cycle - Pass Goals/Thoughts
                        reflection_output = await self.controller.reflection_manager.run_reflection_agent_step(
                            mission_id=mission_id,
                            section_id=section_id,
                            section=section,
                            active_goals=active_goals,
                            active_thoughts=active_thoughts,
                            log_queue=log_queue,
                            update_callback=update_callback,
                            pass_num=round_num
                        )

                        if reflection_output:
                            round_reflection_outputs.append((section_id, reflection_output))

                            if reflection_output.new_questions:
                                logger.info(f"  Round {round_num} Reflection generated {len(reflection_output.new_questions)} new questions for section {section_id}.")
                                current_focus_questions = reflection_output.new_questions
                                round_focus_questions[section_id] = reflection_output.new_questions
                                cycle_count += 1
                                refinement_iterations_this_round[section_id] = cycle_count
                                if cycle_count >= max_cycles_per_section:
                                    logger.info(f"  Reached max research cycles ({max_cycles_per_section}) for section {section_id} in Round {round_num}.")
                                    section_fully_refined = True
                                else:
                                    section_fully_refined = False
                            else:
                                logger.info(f"  No new questions. Section {section_id} refinement complete for Round {round_num}.")
                                section_fully_refined = True

                            # Store suggestions for inter-round revision
                            if reflection_output.suggested_subsection_topics or reflection_output.proposed_modifications:
                                await self.controller.reflection_manager.update_outline_from_reflection(mission_id, section_id, reflection_output)

                            if reflection_output.critical_issues_summary:
                                logger.warning(f"  Round {round_num} Reflection flagged critical issues for section {section_id}: {reflection_output.critical_issues_summary}")
                        else:
                            logger.error(f"Reflection cycle failed for section {section_id} in Round {round_num}. Stopping refinement.")
                            section_fully_refined = True
                    
                    processed_sections_this_round.add(section_id)

            # Trigger Synthesis for Section Intros (after processing all sections in order)
            logger.info(f"Round {round_num}: Checking for section intros to synthesize...")
            sections_to_synthesize = []
            mission_context = self.controller.context_manager.get_mission_context(mission_id)
            current_outline_for_synthesis = mission_context.plan.report_outline if mission_context.plan else []

            def find_synthesis_sections(section_list: List[ReportSection]):
                for section in section_list:
                    if section.research_strategy == "synthesize_from_subsections":
                        # Check if all subsections were processed this round
                        all_subs_processed = True
                        if not section.subsections:
                            all_subs_processed = True
                        else:
                            for sub in section.subsections:
                                if sub.section_id not in processed_sections_this_round:
                                    all_subs_processed = False
                                    logger.debug(f"Subsection {sub.section_id} not processed yet, delaying synthesis for {section.section_id}")
                                    break
                        if all_subs_processed:
                            sections_to_synthesize.append(section)
                    # Recursively check subsections
                    if section.subsections:
                        find_synthesis_sections(section.subsections)

            find_synthesis_sections(current_outline_for_synthesis)

            if sections_to_synthesize:
                synthesis_tasks = [
                    self.controller.writing_agent.synthesize_intro(mission_id, sec, log_queue, update_callback)
                    for sec in sections_to_synthesize
                ]
                logger.info(f"Running synthesis for {len(synthesis_tasks)} section intros...")
                await asyncio.gather(*synthesis_tasks)
            else:
                logger.info("No section intros ready for synthesis in this round.")

            logger.info(f"--- Completed Research Round {round_num}/{num_rounds} ---")

            # Inter-Round Outline Revision (Conditional)
            # Only run revision if it's NOT the last round
            # For the last round, only run if SKIP_FINAL_REPLANNING is False
            if round_num < num_rounds or (round_num == num_rounds and not config.SKIP_FINAL_REPLANNING):
                logger.info(f"--- Starting Inter-Round Outline Revision after Round {round_num} ---")
                revision_success = await self.controller.reflection_manager.process_suggestions_and_update_plan(
                    mission_id,
                    round_reflection_outputs,
                    log_queue,
                    update_callback
                )
                if not revision_success:
                    logger.error(f"Inter-Round outline revision failed after Round {round_num}. Continuing with existing outline.")
                else:
                    logger.info(f"--- Completed Inter-Round Outline Revision after Round {round_num} ---")
            else:
                logger.info(f"--- Skipping final Inter-Round Outline Revision after Round {round_num} because SKIP_FINAL_REPLANNING is True ---")

        logger.info(f"--- Research Plan Execution Completed ({num_rounds} Rounds) for mission {mission_id} ---")
        self.controller.context_manager.log_execution_step(
            mission_id, "AgentController", "Execute Research Plan",
            input_summary=f"Executed {num_rounds} research rounds.",
            status="success", output_summary="Research plan execution phase completed.",
            log_queue=log_queue, update_callback=update_callback
        )
        return True
        
    @acheck_mission_status
    async def reassign_notes_to_final_outline(
        self,
        mission_id: str,
        active_goals: List[Any],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> Optional[FullNoteAssignments]:
        """
        Uses TextReranker and NoteAssignmentAgent sequentially to assign all collected notes
        to each section of the final plan outline.
        Returns a FullNoteAssignments object containing all assignments, or None on failure.
        """
        logger.info(f"Starting sequential note reassignment phase with reranking for mission {mission_id}...")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)

        if not mission_context:
            logger.error(f"Cannot reassign notes: Mission context not found for {mission_id}.")
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Reassign Notes Setup",
                status="failure", error_message="Mission context not found.",
                log_queue=log_queue, update_callback=update_callback
            )
            return None

        final_plan = mission_context.plan
        all_notes = mission_context.notes
        all_notes_dict = {note.note_id: note for note in all_notes}

        if not final_plan or not final_plan.report_outline:
            logger.error(f"Cannot reassign notes: Final plan or report outline not found for mission {mission_id}.")
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Reassign Notes Setup",
                status="failure", error_message="Final plan or outline not found.",
                log_queue=log_queue, update_callback=update_callback
            )
            return None

        if not all_notes:
            logger.warning(f"No notes found in context for mission {mission_id}. Proceeding with empty note assignments.")
            return FullNoteAssignments(assignments={})

        # Import dynamic config functions to get mission-specific settings
        from ai_researcher.dynamic_config import (
            get_max_notes_for_assignment_reranking,
            get_thought_pad_context_limit
        )
        
        # Get mission-specific config values
        min_notes = config.MIN_NOTES_PER_SECTION_ASSIGNMENT
        max_notes = config.MAX_NOTES_PER_SECTION_ASSIGNMENT
        max_notes_for_reranking = get_max_notes_for_assignment_reranking(mission_id)
        thought_pad_context_limit = get_thought_pad_context_limit(mission_id)
        
        logger.info(f"Mission-specific note assignment settings: max_reranking={max_notes_for_reranking}, thought_pad_limit={thought_pad_context_limit}")

        # Fetch other necessary context
        current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)
        mission_goal = final_plan.mission_goal

        # Get sections in processing order
        sections_to_process = outline_utils.get_sections_in_order(final_plan.report_outline)
        total_sections = len(sections_to_process)
        logger.info(f"Found {total_sections} sections in the outline to process sequentially for note assignment.")

        all_assignments = {}
        globally_assigned_note_ids = set()
        any_critical_failure = False
        processed_count = 0

        # Sequential Loop through Sections
        for section in sections_to_process:
            # Check mission status before processing each section
            if not await check_mission_status_async(self.controller, mission_id):
                logger.info(f"Mission {mission_id} stopped/paused during note reassignment. Stopping section processing.")
                return None
            
            processed_count += 1
            logger.info(f"Processing section {processed_count}/{total_sections}: '{section.section_id}' ('{section.title}')")

            # Step 1: Rerank Notes for the Section
            reranked_notes_subset = []
            try:
                # Prepare query for reranker (use section title and description)
                reranker_query = f"{section.title}\n{section.description}"
                logger.debug(f"  Reranking {len(all_notes)} notes for section '{section.section_id}' with query: '{reranker_query[:100]}...'")

                # Call reranker
                reranked_results_with_scores = self.controller.reranker.rerank(
                    query=reranker_query,
                    results=all_notes,
                    top_n=max_notes_for_reranking
                )
                # Extract Note objects from the results
                reranked_notes_subset = [note for score, note in reranked_results_with_scores]

                logger.info(f"  Reranked notes for section '{section.section_id}'. Kept top {len(reranked_notes_subset)} notes.")
                # Log reranking step
                self.controller.context_manager.log_execution_step(
                    mission_id, "TextReranker", f"Rerank Notes for Section {section.section_id}",
                    input_summary=f"Query: {reranker_query[:60]}..., Notes: {len(all_notes)}",
                    output_summary=f"Reranked {len(reranked_notes_subset)} notes.",
                    status="success",
                    log_queue=log_queue, update_callback=update_callback
                )

            except Exception as rerank_e:
                logger.error(f"  Error during note reranking for section '{section.section_id}': {rerank_e}", exc_info=True)
                self.controller.context_manager.log_execution_step(
                    mission_id, "TextReranker", f"Rerank Notes for Section {section.section_id}",
                    input_summary=f"Query: {reranker_query[:60]}..., Notes: {len(all_notes)}",
                    status="failure", error_message=str(rerank_e),
                    log_queue=log_queue, update_callback=update_callback
                )

            # Step 2: Call Note Assignment Agent with Reranked Subset
            assignment_result = None
            model_details = None
            scratchpad_update = None
            log_status = "failure"
            error_message = None
            assignment_output_summary = f"Failed for section {section.section_id}"

            try:
                # Fetch latest thoughts just before the call
                active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
                
                # Call the note assignment agent
                async with self.controller.maybe_semaphore:
                    assignment_result, model_details, scratchpad_update = await self.controller.note_assignment_agent.run(
                        mission_goal=mission_goal,
                        section=section,
                        all_notes=reranked_notes_subset,
                        min_notes=min_notes,
                        max_notes=max_notes,
                        previously_assigned_note_ids=globally_assigned_note_ids.copy(),
                        agent_scratchpad=current_scratchpad,
                        active_goals=active_goals,
                        active_thoughts=active_thoughts,
                        mission_id=mission_id,
                        log_queue=log_queue,
                        update_callback=update_callback
                    )
                
                # Process the result
                if assignment_result and isinstance(assignment_result, AssignedNotes):
                    log_status = "success"
                    assignment_output_summary = f"Assigned {len(assignment_result.relevant_note_ids)} notes to section {section.section_id}"
                    
                    # Add to global assignments
                    all_assignments[section.section_id] = assignment_result
                    globally_assigned_note_ids.update(assignment_result.relevant_note_ids)
                    
                    # Update scratchpad if provided
                    if scratchpad_update:
                        self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                        logger.info(f"  Updated scratchpad after note assignment for section {section.section_id}.")
                else:
                    log_status = "failure"
                    error_message = "NoteAssignmentAgent returned invalid or empty result"
                    logger.error(f"  {error_message} for section {section.section_id}.")
                
                # Log the step
                self.controller.context_manager.log_execution_step(
                    mission_id=mission_id,
                    agent_name=self.controller.note_assignment_agent.agent_name,
                    action=f"Assign Notes to Section {section.section_id}",
                    input_summary=f"Section: '{section.title}', Notes: {len(reranked_notes_subset)}",
                    output_summary=assignment_output_summary,
                    status=log_status,
                    error_message=error_message,
                    full_input={'section': section.model_dump(), 'notes_count': len(reranked_notes_subset)},
                    full_output=assignment_result.model_dump() if assignment_result else None,
                    model_details=model_details,
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            except Exception as assign_e:
                logger.error(f"  Error during note assignment for section '{section.section_id}': {assign_e}", exc_info=True)
                self.controller.context_manager.log_execution_step(
                    mission_id=mission_id,
                    agent_name=self.controller.note_assignment_agent.agent_name,
                    action=f"Assign Notes to Section {section.section_id}",
                    input_summary=f"Section: '{section.title}', Notes: {len(reranked_notes_subset)}",
                    status="failure",
                    error_message=str(assign_e),
                    log_queue=log_queue,
                    update_callback=update_callback
                )
                any_critical_failure = True
                
        # Create and return the final FullNoteAssignments object
        logger.info(f"Note assignment phase completed for mission {mission_id}. Assigned notes to {len(all_assignments)} sections.")
        logger.info(f"Total unique notes assigned: {len(globally_assigned_note_ids)} out of {len(all_notes)} available.")
        
        # Create the final result object
        result = FullNoteAssignments(assignments=all_assignments)
        
        # Log the final step
        self.controller.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name="AgentController",
            action="Complete Note Assignment Phase",
            input_summary=f"Processed {len(sections_to_process)} sections",
            output_summary=f"Assigned {len(globally_assigned_note_ids)} unique notes across {len(all_assignments)} sections",
            status="success" if not any_critical_failure else "warning",
            error_message="Some sections had assignment failures" if any_critical_failure else None,
            full_output=result.model_dump(),
            log_queue=log_queue,
            update_callback=update_callback
        )
        
        return result
