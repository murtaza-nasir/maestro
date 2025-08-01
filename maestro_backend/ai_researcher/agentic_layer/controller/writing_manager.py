from collections import deque
import logging
from typing import Dict, Any, Optional, List, Callable, Tuple, Set
import asyncio
import queue

from ai_researcher import config
from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT
from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry
from ai_researcher.agentic_layer.schemas.planning import ReportSection
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.writing import WritingReflectionOutput, WritingChangeSuggestion
from ai_researcher.agentic_layer.schemas.assignments import FullNoteAssignments

# Import utilities
from ai_researcher.agentic_layer.controller.utils import outline_utils
from ai_researcher.agentic_layer.controller.utils.status_checks import acheck_mission_status, check_mission_status_async

logger = logging.getLogger(__name__)

class WritingManager:
    """
    Manages the writing phase of the mission, including multi-pass writing,
    section content generation, and writing reflection.
    """
    
    def __init__(self, controller):
        """
        Initialize the WritingManager with a reference to the AgentController.
        
        Args:
            controller: The AgentController instance
        """
        self.controller = controller
        
    @acheck_mission_status
    async def run_writing_phase(
        self,
        mission_id: str,
        assigned_notes: FullNoteAssignments,
        active_goals: List[Any],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> bool:
        """
        Manages the multi-pass writing process including initial draft, reflection, and revisions.
        Accepts FullNoteAssignments containing the mapping from section_id to AssignedNotes.
        """
        # Import dynamic config functions to get mission-specific settings
        from ai_researcher.dynamic_config import get_writing_passes
        num_writing_passes = get_writing_passes(mission_id)
        logger.info(f"--- Starting Writing Phase ({num_writing_passes} Passes) for mission {mission_id} ---")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan:
            logger.error(f"Cannot start writing phase: Mission context or plan not found for {mission_id}.")
            return False

        # Convert FullNoteAssignments to the Dict[str, List[Note]] format expected by _write_section_content
        # This requires looking up Note objects based on the IDs in AssignedNotes.
        notes_for_writing: Dict[str, List[Note]] = {}
        all_notes_dict = {note.note_id: note for note in self.controller.context_manager.get_notes(mission_id)}
        if assigned_notes and assigned_notes.assignments:
            for section_id, assignment_data in assigned_notes.assignments.items():
                section_notes = []
                for note_id in assignment_data.relevant_note_ids:
                    if note_id in all_notes_dict:
                        section_notes.append(all_notes_dict[note_id])
                    else:
                        logger.warning(f"Note ID '{note_id}' assigned to section '{section_id}' not found in context manager notes.")
                notes_for_writing[section_id] = section_notes
        else:
            logger.warning(f"No note assignments provided to writing phase for mission {mission_id}. Writing may be incomplete.")

        change_suggestions: List[WritingChangeSuggestion] = []  # Store suggestions between passes

        for pass_num in range(num_writing_passes):
            logger.info(f"--- Starting Writing Pass {pass_num + 1}/{num_writing_passes} ---")
            mission_context = self.controller.context_manager.get_mission_context(mission_id)  # Refresh context
            current_outline = mission_context.plan.report_outline
            written_content_context: Dict[str, str] = mission_context.report_content.copy()  # Start with existing content if any

            if pass_num == 0:
                # Pass 1: Initial Draft Generation (Specific Order)
                logger.info("Writing initial draft in specified order (Middle -> Last -> First)...")

                # 1. Identify section categories
                first_section_id: Optional[str] = None
                last_section_id: Optional[str] = None
                middle_section_ids = set()  # Use set for efficient lookup

                # Use a helper to get sections in depth-first order for processing
                sections_in_write_order = outline_utils.get_sections_in_order(current_outline)

                # Identify first/last based on common titles or position in top-level
                top_level_ids = {sec.section_id for sec in current_outline}
                for i, sec in enumerate(current_outline):
                    title_lower = sec.title.lower()
                    if i == 0 and "introduction" in title_lower:
                        first_section_id = sec.section_id
                    elif i == len(current_outline) - 1 and ("conclusion" in title_lower or "summary" in title_lower):
                        last_section_id = sec.section_id

                # Fallback if titles don't match
                if not first_section_id and current_outline:
                    first_section_id = current_outline[0].section_id
                    logger.warning(f"Could not identify 'Introduction' by title, using first top-level section: {first_section_id}")
                if not last_section_id and len(current_outline) > 1:
                    last_section_id = current_outline[-1].section_id
                    logger.warning(f"Could not identify 'Conclusion' by title, using last top-level section: {last_section_id}")
                elif not last_section_id and len(current_outline) == 1:
                    last_section_id = first_section_id  # Only one section
                    logger.warning("Only one section found, treating as first and last.")

                # Populate middle sections (all sections not first or last)
                for sec in sections_in_write_order:
                    if sec.section_id != first_section_id and sec.section_id != last_section_id:
                        middle_section_ids.add(sec.section_id)

                # 2. Define writing order list
                ordered_sections_to_write: List[ReportSection] = []
                # Add middle sections (already in depth-first order from _get_sections_in_order)
                ordered_sections_to_write.extend([sec for sec in sections_in_write_order if sec.section_id in middle_section_ids])
                # Add last section (and its subsections, already handled by depth-first order)
                if last_section_id:
                    ordered_sections_to_write.extend([sec for sec in sections_in_write_order if sec.section_id == last_section_id or outline_utils.is_descendant(current_outline, last_section_id, sec.section_id)])
                # Add first section (if different from last)
                if first_section_id and first_section_id != last_section_id:
                    ordered_sections_to_write.extend([sec for sec in sections_in_write_order if sec.section_id == first_section_id or outline_utils.is_descendant(current_outline, first_section_id, sec.section_id)])

                # Remove duplicates just in case (though logic should prevent it)
                final_write_order_ids = set()
                final_write_order = []
                for sec in ordered_sections_to_write:
                    if sec.section_id not in final_write_order_ids:
                        final_write_order.append(sec)
                        final_write_order_ids.add(sec.section_id)

                # 3. Execute writing tasks sequentially, updating context
                logger.info(f"Executing {len(final_write_order)} writing tasks for Pass 1...")
                for section_to_write in final_write_order:
                    # Check mission status before writing each section
                    if not await check_mission_status_async(self.controller, mission_id):
                        logger.info(f"Mission {mission_id} stopped/paused during writing phase (Pass 1). Stopping section writing.")
                        return False
                    
                    # Synthesis for intros should happen *before* writing the intro section itself
                    if section_to_write.research_strategy == "synthesize_from_subsections":
                        # Call the WritingAgent's synthesize_intro method
                        await self.controller.writing_agent.synthesize_intro(mission_id, section_to_write, log_queue, update_callback)
                        # Refresh context after synthesis
                        written_content_context = self.controller.context_manager.get_mission_context(mission_id).report_content.copy()
                        # ADDED CHECK: Skip WritingAgent for synthesized intros in Pass 1
                        logger.info(f"Skipping WritingAgent for synthesized intro section {section_to_write.section_id} in Pass 1.")
                        continue  # Move to the next section in the write order

                    # This call will now be skipped if the continue statement above is hit
                    await self._write_section_content(
                        mission_id=mission_id,
                        section=section_to_write,
                        relevant_notes=notes_for_writing.get(section_to_write.section_id, []),
                        pass_num=pass_num,
                        active_goals=active_goals,
                        log_queue=log_queue,
                        update_callback=update_callback,
                        written_content_context=written_content_context.copy()  # Pass copy of current context
                    )
                    # Update context map *after* writing is done and stored by _write_section_content
                    written_content_context = self.controller.context_manager.get_mission_context(mission_id).report_content.copy()

            else:
                # Subsequent Passes: Revision based on Reflection
                logger.info(f"Applying {len(change_suggestions)} suggestions from previous reflection...")
                if not change_suggestions:
                    logger.info("No changes suggested. Skipping revision pass.")
                    continue  # Skip to next pass (or finish if last)

                # Group suggestions by section_id for potentially batching revisions later
                suggestions_by_section: Dict[str, List[WritingChangeSuggestion]] = {}
                for sugg in change_suggestions:
                    suggestions_by_section.setdefault(sugg.section_id, []).append(sugg)

                # Process revisions section by section based on suggestions
                # Determine order? For simplicity, process in outline order for revisions.
                sections_to_revise = outline_utils.get_sections_in_order(current_outline)
                revision_tasks = []

                for section in sections_to_revise:
                    # ADDED CHECK: Skip revisions for synthesized intros
                    if section.research_strategy == "synthesize_from_subsections":
                        logger.info(f"Skipping WritingAgent revision for synthesized intro section {section.section_id} in Pass {pass_num + 1}.")
                        continue  # Skip to the next section

                    if section.section_id in suggestions_by_section:
                        suggestions_for_section = suggestions_by_section[section.section_id]
                        logger.info(f"Scheduling revision for section {section.section_id} based on {len(suggestions_for_section)} suggestions...")
                        # Schedule the revision task, passing current context
                        revision_tasks.append(
                            self._write_section_content(
                                mission_id=mission_id,
                                section=section,
                                relevant_notes=notes_for_writing.get(section.section_id, []),
                                pass_num=pass_num,
                                active_goals=active_goals,
                                log_queue=log_queue,
                                update_callback=update_callback,
                                revision_suggestions=suggestions_for_section,
                                written_content_context=written_content_context.copy()  # Pass copy
                            )
                        )

                # Execute revision tasks concurrently using asyncio.gather
                if revision_tasks:
                    logger.info(f"Executing {len(revision_tasks)} revision tasks concurrently for Pass {pass_num + 1}...")
                    # The semaphore within _write_section_content will limit actual concurrency
                    await asyncio.gather(*revision_tasks)
                    # Refresh context *after* all concurrent revisions are done
                    written_content_context = self.controller.context_manager.get_mission_context(mission_id).report_content.copy()
                    logger.info(f"Completed concurrent revisions for Pass {pass_num + 1}.")
                else:
                    logger.warning(f"No revision tasks scheduled for Pass {pass_num + 1}.")

            # Inter-Pass Reflection (if not the last pass)
            if pass_num < num_writing_passes - 1:
                # Use the method moved to ContextManager
                current_draft_text = self.controller.context_manager.build_draft_from_context(mission_id)
                if not current_draft_text:
                    logger.error(f"Cannot run writing reflection after pass {pass_num + 1}: Failed to build current draft.")
                    return False  # Abort if draft is empty

                reflection_output = await self._run_writing_reflection_step(
                    mission_id, current_draft_text, pass_num + 1, log_queue, update_callback
                )
                if reflection_output:
                    change_suggestions = reflection_output.change_suggestions  # Store for next pass
                else:
                    logger.warning(f"Writing reflection failed after pass {pass_num + 1}. Proceeding without revisions.")
                    change_suggestions = []  # Clear suggestions if reflection failed

        # Refresh context before final synthesis
        written_content_context = self.controller.context_manager.get_mission_context(mission_id).report_content.copy()
        
        # Post-processing: Synthesize content for top-level sections from their subsections
        logger.info("--- Starting Post-Processing: Synthesizing Top-Level Sections ---")
        await self._synthesize_top_level_sections(mission_id, log_queue, update_callback)
        
        logger.info(f"--- Writing Phase Completed ({num_writing_passes} Passes) ---")
        return True

    async def _write_section_content(
        self,
        mission_id: str,
        section: ReportSection,
        relevant_notes: List[Note],  # Notes assigned specifically to this section
        pass_num: int,
        active_goals: List[Any],  # Pass goals
        log_queue: Optional[queue.Queue],
        update_callback: Optional[Callable],
        revision_suggestions: Optional[List[WritingChangeSuggestion]] = None,
        written_content_context: Optional[Dict[str, str]] = None  # Context of ALL previously written sections
    ):
        """
        Helper to call WritingAgent for a section (initial draft or revision),
        passing appropriate context (notes OR written content) based on section strategy,
        and storing the result.
        """
        action_name = f"Write Section: {section.section_id} (Pass {pass_num + 1})"
        input_desc = f"Section: '{section.title}'"
        if revision_suggestions:
            action_name = f"Revise Section: {section.section_id} (Pass {pass_num + 1})"
            input_desc += f", Suggestions: {len(revision_suggestions)}"

        logger.info(f"Preparing context for WritingAgent: {action_name}...")
        model_call_details = None
        log_status = "failure"  # Default to failure
        error_message = "Unknown error during writing/revision preparation"
        section_content = f"[Error: Failed to generate content for section '{section.title}']"  # Default error content
        notes_for_agent: List[Note] = []
        previous_content_for_agent: Dict[str, str] = written_content_context or {}

        try:
            # Fetch current scratchpad and thoughts
            current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)
            active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)

            # Get Full Outline and Parent Context
            mission_context = self.controller.context_manager.get_mission_context(mission_id)
            full_outline: Optional[List[ReportSection]] = None
            parent_section_title: Optional[str] = None
            if mission_context and mission_context.plan:
                full_outline = mission_context.plan.report_outline
                parent_list, current_sec_obj = outline_utils.find_parent_and_section(full_outline, section.section_id)
                if parent_list is not None and current_sec_obj is not None and parent_list is not full_outline:
                    q = deque([(full_outline, None)])
                    found_parent_obj = None
                    while q:
                        current_list, potential_parent = q.popleft()
                        if current_list is parent_list:
                            found_parent_obj = potential_parent
                            break
                        for item in current_list:
                            if item.subsections:
                                q.append((item.subsections, item))
                    if found_parent_obj:
                        parent_section_title = found_parent_obj.title
                        logger.debug(f"Found parent '{parent_section_title}' for section '{section.title}'")
                    else:
                        logger.warning(f"Could not find parent object for section '{section.title}'")
                elif parent_list is full_outline:
                    logger.debug(f"Section '{section.title}' is a top-level section.")
                else:
                    logger.warning(f"Could not find section '{section.title}' or its parent list.")
            else:
                logger.warning("Mission context or plan not available for outline/parent context.")

            # Determine Context Type based on Strategy
            strategy = section.research_strategy
            section_title_lower = section.title.lower()
            is_synthesis_section = (
                strategy == "synthesize_from_subsections" or
                strategy == "synthesize_from_other_sections" or  # Added explicit strategy check
                "introduction" in section_title_lower or  # Implicit check for intro/conclusion
                "conclusion" in section_title_lower
            )

            if is_synthesis_section:
                logger.info(f"  Section '{section.section_id}' is a synthesis section. Preparing written content context.")
                notes_for_agent = []  # Synthesis sections primarily use written content, not notes
                input_desc += ", Context: Written Content"

                # Identify dependent sections based on strategy or type
                dependent_section_ids = set()
                if strategy == "synthesize_from_subsections" and section.subsections:
                    dependent_section_ids = {sub.section_id for sub in section.subsections}
                    logger.info(f"    Synthesizing from {len(dependent_section_ids)} subsections.")
                elif strategy == "synthesize_from_other_sections" or "introduction" in section_title_lower or "conclusion" in section_title_lower:
                    # Assume intro/conclusion synthesize from all *other* top-level sections
                    if full_outline:
                        all_top_level_ids = {s.section_id for s in full_outline}
                        dependent_section_ids = all_top_level_ids - {section.section_id}
                        logger.info(f"    Synthesizing from {len(dependent_section_ids)} other top-level sections.")
                    else:
                        logger.warning("    Cannot determine dependent sections for intro/conclusion: Full outline missing.")

                # Filter previous_content_for_agent to include only dependent sections if needed
                # Currently, previous_content_for_agent contains *all* previously written content,
                # which is generally useful context for the WritingAgent anyway.
                # No explicit filtering here, agent prompt should guide focus.

            else:  # Default to research_based or other note-driven strategies
                logger.info(f"  Section '{section.section_id}' is note-based. Using assigned notes.")
                notes_for_agent = relevant_notes  # Use the notes passed in
                input_desc += f", Context: {len(notes_for_agent)} Notes"

            # Call Writing Agent
            error_message = "Unknown error during writing/revision execution"  # Reset error message
            async with self.controller.maybe_semaphore:
                section_content, model_call_details, scratchpad_update = await self.controller.writing_agent.run(
                    section_to_write=section,
                    notes_for_section=notes_for_agent,  # Pass the determined notes list (empty for synthesis)
                    previous_sections_content=previous_content_for_agent,  # Pass the full map of previous content
                    full_outline=full_outline,
                    parent_section_title=parent_section_title,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    current_draft_content=previous_content_for_agent.get(section.section_id) if revision_suggestions else None,
                    revision_suggestions=revision_suggestions,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

            # Update scratchpad if the agent provided an update
            if scratchpad_update:
                self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                logger.info(f"Updated scratchpad after writing/revising section {section.section_id} (Pass {pass_num + 1}).")

            log_status = "success"
            error_message = None

        except Exception as e:
            # Log error during preparation or execution
            logger.error(f"WritingAgent failed for {action_name}: {e}", exc_info=True)
            error_message = str(e)
            # Keep default error content and failure status

        # Log the step (using updated input_desc)
        self.controller.context_manager.log_execution_step(
            mission_id, "WritingAgent", action_name,
            input_summary=input_desc,  # Use the description built based on context type
            output_summary=f"Generated/Revised content length: {len(section_content)}" if log_status == "success" else error_message,
            status=log_status, error_message=error_message,
            full_input={'section': section.model_dump(), 'notes_provided_count': len(notes_for_agent), 'revision_suggestions': [s.model_dump() for s in revision_suggestions] if revision_suggestions else None},
            full_output={
                "section_title": section.title,
                "section_goal": section.description,
                "notes_used_count": len(notes_for_agent),
                "revision_suggestions_count": len(revision_suggestions) if revision_suggestions else 0,
                "generated_content_preview": section_content[:200] + "..." if section_content else ""
            },
            model_details=model_call_details,
            log_queue=log_queue, update_callback=update_callback
        )

        # Store the generated/revised (or error) content for this section
        self.controller.context_manager.store_report_section(mission_id, section.section_id, section_content)

    async def _synthesize_top_level_sections(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> None:
        """
        Post-processing step to synthesize content for top-level sections from their subsections.
        This ensures that sections with subsections get proper content even if they
        weren't explicitly marked with research_strategy="synthesize_from_subsections".
        """
        logger.info("Synthesizing content for top-level sections from their subsections...")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan:
            logger.error("Cannot synthesize top-level sections: Mission context or plan missing.")
            return

        # Get the full outline
        full_outline = mission_context.plan.report_outline
        
        # Identify top-level sections that have subsections but no content or placeholder content
        for section in full_outline:
            if section.subsections:
                current_content = mission_context.report_content.get(section.section_id, "")
                
                # Check if section has no content or just placeholder content
                if not current_content or current_content == "No information found to write this section." or "[Error:" in current_content:
                    logger.info(f"Synthesizing content for top-level section {section.section_id}: '{section.title}'")
                    
                    # Check if all subsections have content
                    all_subsections_have_content = True
                    for subsec in section.subsections:
                        subsec_content = mission_context.report_content.get(subsec.section_id, "")
                        if not subsec_content or subsec_content == "No information found to write this section." or "[Error:" in subsec_content:
                            all_subsections_have_content = False
                            logger.warning(f"Subsection {subsec.section_id} has no valid content. Skipping synthesis for parent section {section.section_id}.")
                            break
                    
                    if all_subsections_have_content:
                        # Temporarily set research_strategy to synthesize_from_subsections
                        original_strategy = section.research_strategy
                        section.research_strategy = "synthesize_from_subsections"
                        
                        # Call synthesize_intro to generate content
                        await self.controller.writing_agent.synthesize_intro(
                            mission_id=mission_id,
                            section=section,
                            log_queue=log_queue,
                            update_callback=update_callback
                        )
                        
                        # Restore original strategy
                        section.research_strategy = original_strategy
                        
                        logger.info(f"Successfully synthesized content for top-level section {section.section_id}")
                    else:
                        logger.warning(f"Not all subsections have content for section {section.section_id}. Skipping synthesis.")
        
        logger.info("Completed post-processing synthesis of top-level sections.")

    async def _run_writing_reflection_step(
        self,
        mission_id: str,
        current_draft_text: str,
        pass_num: int,  # Pass number (e.g., 1, 2) for logging
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> Optional[WritingReflectionOutput]:
        """
        Runs the WritingReflectionAgent to analyze the current draft and suggest changes.
        """
        logger.info(f"Running writing reflection after Pass {pass_num}...")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan:
            logger.error("Cannot run writing reflection: Mission context or plan missing.")
            return None

        # Fetch necessary context
        active_goals = self.controller.context_manager.get_active_goals(mission_id)
        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
        current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)
        full_outline = mission_context.plan.report_outline

        reflection_output: Optional[WritingReflectionOutput] = None
        model_details: Optional[Dict[str, Any]] = None
        scratchpad_update: Optional[str] = None
        log_status = "failure"
        error_message = "Writing reflection agent failed or returned None."

        try:
            # Apply semaphore
            async with self.controller.maybe_semaphore:
                reflection_output, model_details, scratchpad_update = await self.controller.writing_reflection_agent.run(
                    outline=full_outline,
                    draft_content=current_draft_text,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

            # Update scratchpad if provided
            if scratchpad_update:
                self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                logger.info(f"Updated scratchpad after writing reflection (Pass {pass_num}).")

            if reflection_output:
                log_status = "success"
                error_message = None
                logger.info(f"Writing reflection successful after Pass {pass_num}. Suggestions: {len(reflection_output.change_suggestions)}")
            else:
                # Agent returned None, keep status as failure
                logger.error(f"Writing reflection agent returned None after Pass {pass_num}.")

        except Exception as e:
            logger.error(f"Error during writing reflection step after Pass {pass_num}: {e}", exc_info=True)
            error_message = f"Exception: {e}"
            # Keep reflection_output as None

        # Log the step
        self.controller.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name=self.controller.writing_reflection_agent.agent_name,
            action=f"Reflect on Draft (After Pass {pass_num})",
            input_summary=f"Draft length: {len(current_draft_text)}",
            output_summary=f"Generated {len(reflection_output.change_suggestions) if reflection_output else 0} suggestions." if log_status == "success" else error_message,
            status=log_status,
            error_message=error_message,
            full_input={'draft_length': len(current_draft_text)},
            full_output=reflection_output.model_dump() if reflection_output else None,
            model_details=model_details,
            log_queue=log_queue,
            update_callback=update_callback
        )

        return reflection_output
