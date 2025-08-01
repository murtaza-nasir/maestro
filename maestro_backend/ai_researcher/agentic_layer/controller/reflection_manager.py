import logging
from typing import Dict, Any, Optional, List, Callable, Tuple, Set
import queue
import json

from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT, MAX_PLANNING_CONTEXT_CHARS
from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput, SuggestedSubsectionTopic

import asyncio # Added for gather
import itertools # Added for batching

# Import utilities
from ai_researcher.agentic_layer.controller.utils import outline_utils

logger = logging.getLogger(__name__)

# Removed REDUNDANCY_CHECK_BATCH_SIZE as we now process per section

class ReflectionManager:
    """
    Manages the reflection phase of the mission, including running reflection agents
    and processing suggestions to update the research plan.
    """
    
    def __init__(self, controller):
        """
        Initialize the ReflectionManager with a reference to the AgentController.
        
        Args:
            controller: The AgentController instance
        """
        self.controller = controller
        
    async def run_reflection_agent_step(
        self,
        mission_id: str,
        section_id: str,
        section: ReportSection,
        active_goals: Optional[List[Any]] = None,
        active_thoughts: Optional[List[Any]] = None,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None,
        pass_num: int = 0
    ) -> Optional[ReflectionOutput]:
        """
        Runs the reflection agent for a specific section to analyze notes and suggest improvements.
        
        Args:
            mission_id: The ID of the mission.
            section_id: The ID of the section to reflect on.
            section: The ReportSection object containing section details.
            active_goals: Optional list of active goals for the mission.
            active_thoughts: Optional list of recent thoughts.
            log_queue: Optional queue for sending log messages to the UI.
            update_callback: Optional callback function for UI updates.
            pass_num: The current research pass number (for logging).
            
        Returns:
            A ReflectionOutput object with the agent's analysis and suggestions, or None if the process fails.
        """
        logger.info(f"Running reflection for section {section_id} (Pass {pass_num+1})...")
        
        # Get mission context
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
            logger.error(f"Cannot run reflection: Mission context not found for {mission_id}.")
            return None

        # MODIFIED NOTE GATHERING
        # Retrieve all notes once and create a map for efficient lookup
        all_notes_map = {note.note_id: note for note in self.controller.context_manager.get_notes(mission_id)}
        notes_for_section = []
        missing_note_ids = []

        # Use associated_note_ids directly from the section object passed to this method.
        # This relies on the associated_note_ids being correctly updated after research/planning steps.
        ids_to_fetch = section.associated_note_ids or []
        logger.debug(f"  Reflection for {section_id}: Attempting to fetch notes using associated_note_ids: {ids_to_fetch}")
        if ids_to_fetch:
            for note_id in ids_to_fetch:
                note = all_notes_map.get(note_id)
                if note:
                    notes_for_section.append(note)
                else:
                    missing_note_ids.append(note_id)
                    logger.warning(f"Note ID '{note_id}' associated with section '{section.section_id}' not found in context manager notes.")
            logger.info(f"  Gathered {len(notes_for_section)} notes for reflection on section {section.section_id} (Pass {pass_num+1}) based on associated_note_ids.")
            if missing_note_ids:
                 logger.warning(f"Could not find the following associated notes: {missing_note_ids}")
        else:
            logger.info(f"  No associated_note_ids found for section {section.section_id}. Reflection will proceed with 0 notes.")

        # Get current scratchpad
        current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)

        # Call the reflection agent
        try:
            reflection_output, model_details, scratchpad_update = await self.controller.reflection_agent.run(
                mission_context=mission_context,
                section_id=section_id,
                section_title=section.title,
                section_goal=section.description,
                notes_for_section=notes_for_section,
                agent_scratchpad=current_scratchpad,
                active_goals=active_goals,
                active_thoughts=active_thoughts,
                mission_id=mission_id,
                log_queue=log_queue,
                update_callback=update_callback
            )
            
            # Update scratchpad if provided
            if scratchpad_update:
                self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                
            # Log the reflection step
            log_status = "success" if reflection_output else "failure"
            error_message = None if reflection_output else "Reflection agent failed to generate output."
            
            self.controller.context_manager.log_execution_step(
                mission_id=mission_id,
                agent_name="ReflectionAgent",
                action=f"Reflect on Section {section_id} (Pass {pass_num})",
                input_summary=f"Section: {section.title}, Notes: {len(notes_for_section)}",
                output_summary=f"New questions: {len(reflection_output.new_questions) if reflection_output else 0}, Suggested subsections: {len(reflection_output.suggested_subsection_topics) if reflection_output else 0}" if log_status == "success" else error_message,
                status=log_status,
                error_message=error_message,
                full_input={"section_id": section_id, "section_title": section.title, "notes_count": len(notes_for_section)},
                full_output=reflection_output.model_dump() if reflection_output else None,
                model_details=model_details,
                log_queue=log_queue,
                update_callback=update_callback
            )
            
            # Update stats
            if model_details:
                self.controller.context_manager.update_mission_stats(mission_id, model_details, log_queue, update_callback)
                
            # Store generated thought if available
            if reflection_output and reflection_output.generated_thought:
                self.controller.context_manager.add_thought(mission_id, "ReflectionAgent", reflection_output.generated_thought)
                
            return reflection_output
            
        except Exception as e:
            logger.error(f"Error during reflection for section {section_id}: {e}", exc_info=True)
            
            # Log the failure
            self.controller.context_manager.log_execution_step(
                mission_id=mission_id,
                agent_name="ReflectionAgent",
                action=f"Reflect on Section {section_id} (Pass {pass_num+1})",
                input_summary=f"Section: {section.title}, Notes: {len(notes_for_section)}",
                status="failure",
                error_message=str(e),
                log_queue=log_queue,
                update_callback=update_callback
            )
            
            return None

    async def update_outline_from_reflection(
        self, 
        mission_id: str, 
        section_id_reflected_on: str, 
        reflection_output: ReflectionOutput
    ) -> bool:
        """
        Stores subsection suggestions during Pass 1. Does NOT modify the outline directly.
        Also handles generated thoughts from reflection and adds them to the thought pad.
        Returns False as no direct modifications are applied here.
        """
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan:
            logger.error(f"Cannot update outline: Mission context or plan not found for {mission_id}.")
            return False

        # Handle Suggested Subsection Topics (Store them, don't apply yet)
        if reflection_output.suggested_subsection_topics:
            parent_section_id = section_id_reflected_on
            if mission_id not in self.controller.mission_subsection_suggestions:
                 self.controller.mission_subsection_suggestions[mission_id] = {}
            if parent_section_id not in self.controller.mission_subsection_suggestions[mission_id]:
                self.controller.mission_subsection_suggestions[mission_id][parent_section_id] = []
            # Store suggestions associated with their parent section
            self.controller.mission_subsection_suggestions[mission_id][parent_section_id].extend(
                reflection_output.suggested_subsection_topics
            )
            logger.info(f"Stored {len(reflection_output.suggested_subsection_topics)} subsection topic suggestions for parent section {parent_section_id}.")

        # Handle Proposed Top-Level Modifications
        # Log that these are being collected for the inter-pass step
        if reflection_output.proposed_modifications:
            logger.info(f"Collecting {len(reflection_output.proposed_modifications)} proposed structural modifications for section {section_id_reflected_on} for inter-pass revision.")

        # Handle Generated Thought
        if reflection_output.generated_thought:
            # Add the generated thought to the thought pad
            thought_id = self.controller.context_manager.add_thought(
                mission_id=mission_id,
                agent_name="ReflectionAgent",
                content=reflection_output.generated_thought
            )
            if thought_id:
                logger.info(f"Added thought '{thought_id}' from reflection on section {section_id_reflected_on} to thought pad.")
            else:
                logger.warning(f"Failed to add thought from reflection on section {section_id_reflected_on} to thought pad.")

        # Return False as no direct plan modifications are applied by this function.
        # Modifications happen in the Inter-Pass step (process_suggestions_and_update_plan).
        logger.info(f"Reflection suggestions for section {section_id_reflected_on} collected for later processing.")
        return False

    async def process_suggestions_and_update_plan(
        self,
        mission_id: str,
        reflection_data: List[Tuple[str, ReflectionOutput]],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> bool:
        """
        Processes collected reflection outputs (subsection suggestions AND structural modifications),
        calls PlanningAgent to revise the outline, and updates the plan if the outline changes.
        Includes logging for note assignment changes.
        Returns True if successful, False otherwise.
        """
        logger.info(f"--- Starting Inter-Pass Suggestion Processing for mission {mission_id} ---")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)

        if not mission_context or not mission_context.plan:
            logger.error("Cannot process suggestions: Mission context or plan missing.")
            return False
        if not reflection_data:
            logger.info("No reflection outputs collected from the previous round. Proceeding with existing plan.")
            return True

        # Get current notes BEFORE calling planner
        all_notes = self.controller.context_manager.get_notes(mission_id)
        original_outline = mission_context.plan.report_outline

        # Consolidate and Format ALL Suggestions (Subsections and Structural)
        all_suggestion_details = []
        total_subsection_suggestions = 0
        total_structural_suggestions = 0

        # Iterate through the list of tuples
        for section_id, output in reflection_data:
            # Format subsection suggestions
            if output.suggested_subsection_topics:
                # Use section_id from the tuple, not output.section_id
                parent_section_id = section_id
                parent_section = outline_utils.find_section_recursive(mission_context.plan.report_outline, parent_section_id)
                parent_title = parent_section.title if parent_section else parent_section_id
                for topic in output.suggested_subsection_topics:
                    all_suggestion_details.append(
                        f"- Add Subsection Suggestion for Parent '{parent_title}' ({parent_section_id}):\n"
                        f"    Title='{topic.title}', Description='{topic.description}', Reasoning='{topic.reasoning}'"
                    )
                    total_subsection_suggestions += 1

            # Format structural modification suggestions
            if output.proposed_modifications:
                 for mod in output.proposed_modifications:
                      all_suggestion_details.append(
                           # Use section_id from the tuple, not output.section_id
                           f"- Structural Modification Suggestion (for section '{section_id}'):\n"
                           f"    Type='{mod.modification_type}', Target ID='{mod.target_section_id}', "
                           f"New Title='{mod.new_title}', New Description='{mod.new_description}', "
                           f"Reasoning='{mod.reasoning}'"
                      )
                      total_structural_suggestions += 1

        if not all_suggestion_details:
            logger.info("No valid suggestions found in reflection outputs after formatting. Proceeding.")
            return True

        suggestions_context = "Collected Reflection Suggestions (Consider Both Types):\n" + "\n".join(all_suggestion_details)
        current_outline_str = "Current Report Outline Structure:\n" + "\n".join(
            outline_utils.format_outline_for_prompt(mission_context.plan.report_outline)
        )

        # Retrieve and format notes context for revision (with batching)
        all_notes = self.controller.context_manager.get_notes(mission_id)
        notes_context_str = ""

        if not all_notes:
            notes_context_str = "Collected Notes Context (for outline revision):\nNo notes have been collected yet.\n---\n"
        else:
            # Calculate Total Character Count and Check Limit
            total_chars = sum(len(note.content) for note in all_notes)
            char_limit = MAX_PLANNING_CONTEXT_CHARS
            needs_batching = total_chars > char_limit
            logger.info(f"Inter-pass revision: Total characters in notes: {total_chars}. Limit: {char_limit}. Batching needed: {needs_batching}")

            # Prepare Note Batches if Needed
            note_batches: List[List[Note]] = []
            if needs_batching:
                current_batch: List[Note] = []
                current_batch_chars = 0
                for note in all_notes:
                    note_len = len(note.content)
                    if current_batch_chars + note_len > char_limit and current_batch:
                        note_batches.append(current_batch)
                        current_batch = [note]
                        current_batch_chars = note_len
                    else:
                        current_batch.append(note)
                        current_batch_chars += note_len
                if current_batch:
                    note_batches.append(current_batch)
                logger.info(f"Inter-pass revision: Split {len(all_notes)} notes ({total_chars} chars) into {len(note_batches)} batches.")
            else:
                note_batches.append(all_notes)

            # Format Notes Context String from Batches
            full_notes_context_parts = []
            for i, batch in enumerate(note_batches):
                batch_context_header = f"Collected Notes Context (Batch {i + 1}/{len(note_batches)} for outline revision):\n"
                batch_context_header += f"Processing {len(batch)} notes in this batch (out of {len(all_notes)} total). Use these notes and their IDs to inform the outline structure and populate the 'associated_note_ids' field for relevant sections in the revised outline.\n\n"
                batch_notes_str = ""
                for note in batch:
                    batch_notes_str += f"- Note ID: {note.note_id}\n"
                    batch_notes_str += f"  - Source: {note.source_type} - {note.source_id}\n\n"

                full_notes_context_parts.append(batch_context_header + batch_notes_str)

            # Combine all batch contexts
            notes_context_str = "\n---\n".join(full_notes_context_parts)
            notes_context_str += "\n---\n"

        logger.info("Calling PlanningAgent to revise outline based on suggestions...")
        revised_plan_response = None
        model_call_details = None
        scratchpad_update = None
        try:
            # Fetch current scratchpad
            current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)

            # Ask PlanningAgent to integrate suggestions into the current outline with updated instructions
            revise_prompt_context = (
                f"Original User Request:\n{mission_context.user_request}\n\n"
                f"{current_outline_str}\n\n{notes_context_str}\n\n{suggestions_context}\n\n"
                f"Instruction: You are given the 'Current Report Outline Structure', the 'Collected Notes Context', and a list of 'Collected Reflection Suggestions'. "
                f"Your task is to revise the outline by intelligently integrating the most relevant suggestions. "
                f"1. **Structural Changes:** First, evaluate and apply necessary structural modifications (merge, reframe, delete) based on the 'Structural Modification Suggestion' entries. Only apply changes with strong reasoning. Do not flatten an outline that has subsections unless strongly requested by the user. "
                f"2. **Add Subsections:** After applying structural changes, integrate valuable 'Add Subsection Suggestion' entries as new subsections under their respective parents. Prioritize adding valuable subsections (typically 1-3) to the middle sections (e.g., 'literature_review', 'comparison_analysis', any other sections that ore not introductory or concluding) where suggestions indicate clear themes or necessary detail. Add subsections to 'introduction' and 'conclusion' **only if a suggestion addresses a critical gap or provides absolutely essential context**. "
                f"3. **Re-assign Notes:** Critically, after revising the outline structure, you MUST re-evaluate the 'Collected Notes Context' and populate the `associated_note_ids` field for **ALL** sections (new and existing) in the revised `report_outline` with the IDs of the notes most relevant to each section's final description. "
                f"Evaluate all suggestions but only incorporate those that add significant value and clarity. "
                f"**Pay attention to the 'Current Active Mission Goals' and 'Recent Thoughts' to ensure the plan aligns with the overarching mission goals. "
                f"Ensure the final outline does not exceed a depth of {self.controller.max_total_depth} (0=top-level, 1=subsection, 2=sub-subsection). "
                f"**Do not create more than 7 top-level sections in total**. If you need more, break the outline into subsections. "
                f"**Modify the provided 'Current Report Outline Structure' JSON by applying the necessary changes based on the suggestions.** Preserve the original nesting and parent-child relationships unless a specific structural modification suggestion requires changing them (e.g., merging, moving). "
                f"Generate the complete, updated plan including the *modified* outline (with updated `associated_note_ids`) and updated steps reflecting the new structure. "
                f"Output ONLY the JSON object conforming to the SimplifiedPlanResponse schema."
            )

            # Fetch Active Goals & Thoughts
            active_goals = self.controller.context_manager.get_active_goals(mission_id)
            active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)

            # Apply Semaphore
            async with self.controller.maybe_semaphore:
                revised_plan_response, model_call_details, scratchpad_update = await self.controller.planning_agent.run(
                    user_request=mission_context.user_request,
                    revision_context=revise_prompt_context,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

                # ADD AGENT STEP LOGGING
                log_status_planning_rev = "success" if revised_plan_response and not revised_plan_response.parsing_error else "failure"
                log_error_planning_rev = revised_plan_response.parsing_error if revised_plan_response and revised_plan_response.parsing_error else ("Agent returned None" if not revised_plan_response else None)
                self.controller.context_manager.log_execution_step(
                    mission_id=mission_id,
                    agent_name=self.controller.planning_agent.agent_name,
                    action="Revise Outline (Inter-Pass)",
                    input_summary=f"{total_subsection_suggestions} subsection + {total_structural_suggestions} structural suggestions provided.",
                    output_summary=f"Revised outline with {len(revised_plan_response.report_outline) if revised_plan_response else 'N/A'} sections." if log_status_planning_rev == "success" else log_error_planning_rev,
                    status=log_status_planning_rev,
                    error_message=log_error_planning_rev,
                    full_input={'revision_context': revise_prompt_context},
                    full_output=revised_plan_response.model_dump() if revised_plan_response else None,
                    model_details=model_call_details,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

                # Update scratchpad if the agent provided an update
                if scratchpad_update:
                    self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                    logger.info(f"Updated scratchpad after inter-pass plan revision for mission {mission_id}.")

                if log_status_planning_rev == "success":
                    # Compare outlines to see if changes occurred
                    new_outline = revised_plan_response.report_outline
                    original_outline_json = json.dumps([s.model_dump() for s in mission_context.plan.report_outline], sort_keys=True)
                    new_outline_json = json.dumps([s.model_dump() for s in new_outline], sort_keys=True)

                    if original_outline_json == new_outline_json:
                        logger.info("PlanningAgent returned the same outline. No structural changes applied.")
                    else:
                        logger.info("PlanningAgent proposed a revised outline. Applying changes...")
                    
                    # Apply Changes
                    # Convert response to SimplifiedPlan object before storing
                    try:
                        updated_plan = SimplifiedPlan(
                            mission_goal=revised_plan_response.mission_goal,
                            report_outline=revised_plan_response.report_outline
                        )
                        self.controller.context_manager.store_plan(mission_id, updated_plan)
                        logger.info("Revised outline and steps stored.")
                    except Exception as e:
                        logger.error(f"Failed to create/store updated SimplifiedPlan: {e}", exc_info=True)
                        self.controller.context_manager.log_execution_step(
                            mission_id, "AgentController", "Store Revised Plan",
                            input_summary="Storing revised plan from PlanningAgent.",
                            output_summary="Failed to store revised plan.", status="failure", error_message=str(e),
                            full_input=revised_plan_response.model_dump(), model_details=model_call_details,
                            log_queue=log_queue, update_callback=update_callback
                        )
                        return False

                    return True

                else:
                    logger.error(f"PlanningAgent failed to revise outline based on suggestions for mission {mission_id}.")
                    return False

        except Exception as e:
            logger.error(f"Error during Inter-Pass suggestion processing for mission {mission_id}: {e}", exc_info=True)
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Process Suggestions (Inter-Pass)",
                input_summary="Processing collected subsection suggestions.",
                status="failure", error_message=f"Exception: {e}", model_details=model_call_details,
                log_queue=log_queue, update_callback=update_callback
            )
            return False

    async def perform_redundancy_check(
        self,
        mission_id: str,
        notes: List[Note],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ) -> List[Note]:
        """
        Runs the ReflectionAgent to identify and filter out redundant notes from a given list.
        Processes notes grouped by their section_id in parallel.

        Args:
            mission_id: The ID of the mission.
            notes: The list of all notes to check for redundancy.
            log_queue: Optional queue for sending log messages.
            update_callback: Optional callback function for UI updates.

        Returns:
            A list of notes with redundant ones removed.
        """
        logger.info(f"Starting section-based redundancy check for {len(notes)} notes in mission {mission_id}.")
        if not notes:
            logger.warning("No notes provided for redundancy check.")
            return []

        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan:
            logger.error(f"Cannot perform redundancy check: Mission context or plan not found for {mission_id}.")
            # Return original notes if context/plan is missing to avoid data loss
            return notes

        # --- Group Notes by Section ID based on the CURRENT PLAN ---
        notes_by_section: Dict[str, List[Note]] = {}
        all_notes_map = {note.note_id: note for note in notes}
        processed_note_ids: Set[str] = set()

        # Iterate through the sections defined in the current plan using the correct utility function
        for section in outline_utils.get_sections_in_order(mission_context.plan.report_outline):
            section_id = section.section_id
            notes_for_this_section = []
            missing_note_ids = []
            if section.associated_note_ids:
                for note_id in section.associated_note_ids:
                    note = all_notes_map.get(note_id)
                    if note:
                        notes_for_this_section.append(note)
                        processed_note_ids.add(note_id)
                    else:
                        # This note ID is associated but not in the input 'notes' list - log a warning
                        missing_note_ids.append(note_id)
                        logger.warning(f"Note ID '{note_id}' associated with section '{section_id}' in the plan, but not found in the provided notes list for redundancy check.")
            if notes_for_this_section:
                notes_by_section[section_id] = notes_for_this_section
            if missing_note_ids:
                 logger.warning(f"Could not find the following associated notes during redundancy check grouping for section {section_id}: {missing_note_ids}")


        # Handle notes not associated with any section in the current plan
        unassigned_notes = [note for note in notes if note.note_id not in processed_note_ids]
        if unassigned_notes:
            logger.info(f"Found {len(unassigned_notes)} notes not associated with any section in the current plan. Grouping under 'unassigned'.")
            notes_by_section["unassigned"] = unassigned_notes

        logger.info(f"Grouped notes into {len(notes_by_section)} sections based on the current plan for parallel redundancy check.")

        # --- Create Parallel Tasks for Each Section ---
        tasks = []
        sections_to_process_ids = list(notes_by_section.keys())

        for section_id in sections_to_process_ids:
            section_notes = notes_by_section[section_id]
            # Find the section details from the plan for context (if not 'unassigned')
            section_details = None
            if section_id != "unassigned":
                section_details = outline_utils.find_section_recursive(mission_context.plan.report_outline, section_id)

            if len(section_notes) <= 1:
                # No redundancy possible with 0 or 1 note
                logger.debug(f"Skipping redundancy check for section {section_id}: {len(section_notes)} note(s).")
                # Add a task that immediately returns the existing note IDs for this section
                async def _identity_task(notes_in):
                    return {note.note_id for note in notes_in}
                tasks.append(_identity_task(section_notes))
            else:
                # Create a task to check redundancy for this section
                tasks.append(self._check_section_redundancy(
                    mission_id=mission_id,
                    section_id=section_id,
                    section_details=section_details, # Pass section details from plan
                    section_notes=section_notes,
                    mission_context=mission_context,
                    log_queue=log_queue,
                    update_callback=update_callback
                ))

        # --- Execute Tasks in Parallel ---
        logger.info(f"Executing redundancy checks for {len(tasks)} sections in parallel...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # --- Aggregate Results ---
        all_notes_to_keep_ids: Set[str] = set()
        for i, result in enumerate(results):
            section_id = sections_to_process_ids[i] # Get corresponding section_id
            section_note_count = len(notes_by_section[section_id])

            if isinstance(result, Exception):
                logger.error(f"Redundancy check for section {section_id} failed with exception: {result}. Keeping all {section_note_count} notes for this section.", exc_info=result)
                # Keep all notes from this section on error
                all_notes_to_keep_ids.update(note.note_id for note in notes_by_section[section_id])
            elif isinstance(result, set):
                 logger.info(f"Redundancy check for section {section_id} completed. Kept {len(result)} out of {section_note_count} notes.")
                 all_notes_to_keep_ids.update(result)
            else:
                 # Should not happen if _check_section_redundancy returns correctly
                 logger.error(f"Unexpected result type for section {section_id}: {type(result)}. Keeping all {section_note_count} notes for this section.")
                 all_notes_to_keep_ids.update(note.note_id for note in notes_by_section[section_id])


        # --- Filter Original Notes ---
        filtered_notes = [note for note in notes if note.note_id in all_notes_to_keep_ids]

        logger.info(f"Overall redundancy check completed. Kept {len(filtered_notes)} out of {len(notes)} original notes.")
        
        # Log overall result
        self.controller.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name="ReflectionManager",
            action="Perform Redundancy Check (Parallel Per Section)",
            input_summary=f"Input: {len(notes)} notes across {len(notes_by_section)} sections.",
            output_summary=f"Output: {len(filtered_notes)} notes kept.",
            status="success", # Assuming partial success is still overall success
            log_queue=log_queue,
            update_callback=update_callback
        )

        return filtered_notes

    async def _check_section_redundancy(
        self,
        mission_id: str,
        section_id: str, # ID of the section being checked (can be "unassigned")
        section_details: Optional[ReportSection], # Details from the plan, None if "unassigned"
        section_notes: List[Note],
        mission_context: Any, # MissionContext object
        log_queue: Optional[queue.Queue],
        update_callback: Optional[Callable[[queue.Queue, Any], None]]
    ) -> Set[str]:
        """
        Helper async function to perform redundancy check for a single section's notes.
        Returns a set of note IDs to keep for this section.
        """
        num_notes = len(section_notes)
        logger.info(f"Starting redundancy check for section '{section_id}' ({num_notes} notes)...")

        # REMOVED initial log with status="running"

        # Prepare notes content for the prompt (used if we construct a custom prompt later, but not directly passed now)
        # notes_content_for_prompt = ""
        # for note in section_notes:
        #     notes_content_for_prompt += f"--- Note ID: {note.note_id} ---\n"
        #     notes_content_for_prompt += f"Content:\n{note.content}\n\n"

        # Determine section title/goal for context
        section_title = section_details.title if section_details else section_id
        # Construct the goal/instruction for the agent
        if section_details:
            section_goal_instruction = (
                f"Task: Identify redundant notes within this section ('{section_title}' - {section_id}).\n"
                f"Section Goal: {section_details.description}\n"
                f"Instructions: Review the provided notes for this section. Identify notes with substantially overlapping information or duplicates *within this set*. Select the most comprehensive note for each distinct piece of information relevant to the section goal. "
                f"Return ONLY a JSON list containing the string IDs of the notes that should be REMOVED. Example: [\"note_id_1\", \"note_id_3\"]"
            )
        else: # Handle "unassigned" section
             section_goal_instruction = (
                f"Task: Identify redundant notes among these 'unassigned' notes.\n"
                f"Instructions: Review the provided notes. Identify notes with substantially overlapping information or duplicates *within this set*. Select the most comprehensive note for each distinct piece of information. "
                f"Return ONLY a JSON list containing the string IDs of the notes that should be REMOVED. Example: [\"note_id_1\", \"note_id_3\"]"
             )

        # Get active goals and thoughts for context
        active_goals = self.controller.context_manager.get_active_goals(mission_id)
        # Re-initialize notes_content_for_prompt (even though not directly passed to agent, might be useful for logging/debugging later)
        notes_content_for_prompt = ""
        for note in section_notes:
            notes_content_for_prompt += f"--- Note ID: {note.note_id} ---\n"
            # Section ID is context, no need to repeat per note in prompt
            notes_content_for_prompt += f"Content:\n{note.content}\n\n"

        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
        current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id)
        model_details = None
        scratchpad_update = None

        try:
            # Call the reflection agent, respecting the semaphore
            async with self.controller.maybe_semaphore:
                # Call the reflection agent using standard parameters
                agent_response, model_details, scratchpad_update = await self.controller.reflection_agent.run(
                    mission_context=mission_context,
                    section_id=section_id,
                    section_title=section_title,
                    section_goal=section_goal_instruction, # Pass instructions via section_goal
                    notes_for_section=section_notes, # Pass the actual notes
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                    # Removed response_format={"type": "json_object"}
                )

            # Update scratchpad if provided
            if scratchpad_update:
                self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)

            # Process the response (Expecting IDs to REMOVE based on user feedback in prompt)
            notes_to_remove_ids_section: Set[str] = set()
            notes_to_keep_ids_section: Set[str] = {note.note_id for note in section_notes} # Start assuming all are kept
            parsing_error = None
            
            # Handle ReflectionOutput object (new agent response format)
            from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput
            if agent_response and isinstance(agent_response, ReflectionOutput):
                # Use discard_note_ids from the ReflectionOutput object
                if hasattr(agent_response, 'discard_note_ids') and agent_response.discard_note_ids:
                    notes_to_remove_ids_section = set(agent_response.discard_note_ids)
                    
                    # Validate that returned IDs to remove actually belong to this section's input notes
                    valid_ids = {note.note_id for note in section_notes}
                    invalid_returned_ids = notes_to_remove_ids_section - valid_ids
                    if invalid_returned_ids:
                        logger.warning(f"Section {section_id}: Agent suggested removing IDs not part of the input: {invalid_returned_ids}. These will be ignored.")
                        notes_to_remove_ids_section &= valid_ids # Consider only valid IDs for removal

                    # Calculate notes to keep by removing the identified redundant ones
                    notes_to_keep_ids_section = valid_ids - notes_to_remove_ids_section
                    
                    logger.debug(f"Section {section_id}: Agent identified {len(notes_to_remove_ids_section)} notes to remove. Keeping {len(notes_to_keep_ids_section)} out of {num_notes}.")
                else:
                    logger.info(f"Section {section_id}: No notes marked for removal in ReflectionOutput. Keeping all {num_notes} notes.")
            # Keep legacy string handling for backward compatibility
            elif agent_response and isinstance(agent_response, str):
                try:
                    # Handle potential markdown code block ```json ... ```
                    response_content = agent_response.strip()
                    if response_content.startswith("```json"):
                        response_content = response_content[7:-3].strip()
                    elif response_content.startswith("```"):
                         response_content = response_content[3:-3].strip()
                         
                    parsed_json = json.loads(response_content)
                    if isinstance(parsed_json, list) and all(isinstance(item, str) for item in parsed_json):
                        notes_to_remove_ids_section = set(parsed_json)
                        
                        # Validate that returned IDs to remove actually belong to this section's input notes
                        valid_ids = {note.note_id for note in section_notes}
                        invalid_returned_ids = notes_to_remove_ids_section - valid_ids
                        if invalid_returned_ids:
                            logger.warning(f"Section {section_id}: Agent suggested removing IDs not part of the input: {invalid_returned_ids}. These will be ignored.")
                            notes_to_remove_ids_section &= valid_ids # Consider only valid IDs for removal

                        # Calculate notes to keep by removing the identified redundant ones
                        notes_to_keep_ids_section = valid_ids - notes_to_remove_ids_section
                        
                        logger.debug(f"Section {section_id}: Agent identified {len(notes_to_remove_ids_section)} notes to remove. Keeping {len(notes_to_keep_ids_section)} out of {num_notes}.")
                    else:
                        parsing_error = "Agent response was valid JSON but not a list of strings."
                        logger.error(f"Section {section_id}: {parsing_error} Response: {agent_response}")
                except json.JSONDecodeError as json_err:
                    parsing_error = f"Agent response was not valid JSON: {json_err}. Response: {agent_response}"
                    logger.error(f"Section {section_id}: {parsing_error}")
                except Exception as e:
                     parsing_error = f"Unexpected error parsing agent response: {e}. Response: {agent_response}"
                     logger.error(f"Section {section_id}: {parsing_error}", exc_info=True)
            elif not agent_response:
                 parsing_error = "Agent returned an empty response."
                 logger.error(f"Section {section_id}: {parsing_error}")
            else:
                parsing_error = f"Unexpected agent response type: {type(agent_response)}. Expected ReflectionOutput or string."
                logger.error(f"Section {section_id}: {parsing_error}")

            # Log step result
            log_status = "success" if not parsing_error else "failure"
            self.controller.context_manager.log_execution_step(
                mission_id=mission_id,
                agent_name="ReflectionAgent",
                action=f"Redundancy Check (Section: {section_id})",
                input_summary=f"Checked {num_notes} notes.",
                output_summary=f"Kept {len(notes_to_keep_ids_section)} notes." if log_status == "success" else parsing_error,
                status=log_status,
                error_message=parsing_error,
                model_details=model_details,
                log_queue=log_queue,
                update_callback=update_callback
            )

            # Update stats
            if model_details:
                self.controller.context_manager.update_mission_stats(mission_id, model_details, log_queue, update_callback)

            if log_status == "success":
                return notes_to_keep_ids_section
            else:
                # On failure for this section, return all original note IDs for this section
                logger.warning(f"Redundancy check failed for section {section_id}. Keeping all {num_notes} original notes for this section.")
                return {note.note_id for note in section_notes}

        except Exception as e:
            logger.error(f"Exception during redundancy check for section {section_id}: {e}", exc_info=True)
            self.controller.context_manager.log_execution_step(
                mission_id=mission_id,
                agent_name="ReflectionAgent",
                action=f"Redundancy Check (Section: {section_id})",
                input_summary=f"Checking {num_notes} notes.",
                status="failure",
                error_message=f"Exception: {e}",
                model_details=model_details, # Log details even if exception occurred after call
                log_queue=log_queue,
                update_callback=update_callback
            )
            # Keep all notes from the failed section
            logger.warning(f"Redundancy check failed for section {section_id} due to exception. Keeping all {num_notes} original notes for this section.")
            return {note.note_id for note in section_notes}
