"""
Enhanced reflection manager with batched Phase 3 processing.
This module contains the improved implementation for handling large revision contexts.
"""

import logging
import json
from typing import Dict, Any, Optional, List, Tuple
import queue

from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT, get_max_suggestions_per_batch
from ai_researcher.dynamic_config import get_max_planning_context_chars
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput

from ai_researcher.agentic_layer.controller.utils import outline_utils

logger = logging.getLogger(__name__)


def is_error_outline(outline: List[ReportSection]) -> bool:
    """
    Check if an outline contains error patterns that indicate LLM confusion.
    
    Args:
        outline: The outline to validate
        
    Returns:
        True if the outline appears to be an error/placeholder
    """
    if not outline:
        return True
    
    # Error patterns that indicate the LLM is confused or asking for input
    error_patterns = [
        'request_outline', 'placeholder', 'outline_request',
        'please provide', 'corrected outline', 'full outline',
        'provide the outline', 'missing outline', 'outline needed'
    ]
    
    for section in outline:
        # Check section ID, title, and description for error patterns
        section_text = f"{section.section_id} {section.title} {section.description}".lower()
        if any(pattern in section_text for pattern in error_patterns):
            logger.warning(f"Detected error pattern in section '{section.section_id}': '{section.title}'")
            return True
    
    return False


async def validate_single_section_intent(
    controller,
    mission_id: str,
    new_outline: List[ReportSection],
    previous_outline: List[ReportSection],
    mission_goal: str
) -> bool:
    """
    Use fast LLM to determine if a single-section outline is intentional.
    
    Args:
        controller: The controller instance
        mission_id: Mission ID
        new_outline: The new outline with single section
        previous_outline: The previous multi-section outline
        mission_goal: The mission goal/user request
        
    Returns:
        True if the single section is appropriate, False if it's likely an error
    """
    if len(new_outline) != 1:
        return True  # Not a single section, so it's fine
    
    # First check for obvious error patterns
    if is_error_outline(new_outline):
        return False
    
    try:
        validation_prompt = f"""You are validating whether an outline revision is appropriate.

Mission Goal: {mission_goal}

Previous outline had {len(previous_outline)} sections:
{', '.join([s.title for s in previous_outline[:5]])}{'...' if len(previous_outline) > 5 else ''}

New outline has only 1 section:
Title: {new_outline[0].title}
Description: {new_outline[0].description[:200]}...

Is this dramatic reduction from {len(previous_outline)} sections to 1 section appropriate for the mission goal?

Consider:
1. Does the single section title/description suggest it's asking for an outline rather than being an outline?
2. Would the mission goal logically require only one section?
3. Does this look like an LLM error or confusion?

Respond with ONLY one word:
- YES if the single section is appropriate for the mission
- NO if this appears to be an error or placeholder
"""
        
        # Use fast model for validation
        response = await controller.model_dispatcher.generate_async(
            prompt=validation_prompt,
            max_tokens=10,
            temperature=0.1,
            model="claude-3-haiku-20240307"  # Use fast model
        )
        
        if response and response.choices and response.choices[0].message.content:
            result = response.choices[0].message.content.strip().upper()
            is_valid = "YES" in result
            
            if not is_valid:
                logger.warning(f"Single section outline deemed invalid by fast LLM validation")
            
            return is_valid
        else:
            logger.error("Fast LLM validation returned empty response, assuming invalid")
            return False
            
    except Exception as e:
        logger.error(f"Error during single section validation: {e}", exc_info=True)
        # On error, assume it's invalid to be safe
        return False


async def process_suggestions_and_update_plan_batched(
    reflection_manager,
    mission_id: str,
    reflection_data: List[Tuple[str, ReflectionOutput]],
    log_queue: Optional[queue.Queue] = None,
    update_callback: Optional[Any] = None
) -> bool:
    """
    Enhanced version of process_suggestions_and_update_plan that handles batching properly.
    
    This method:
    1. Separates structural modifications from subsection suggestions
    2. Applies structural changes first (if they fit in context)
    3. Batches subsection suggestions by parent sections
    4. Ensures note context is included but within limits
    
    Args:
        reflection_manager: The ReflectionManager instance (self)
        mission_id: The mission ID
        reflection_data: List of tuples (section_id, ReflectionOutput)
        log_queue: Optional queue for logging
        update_callback: Optional callback for updates
        
    Returns:
        True if successful, False otherwise
    """
    controller = reflection_manager.controller
    logger.info(f"--- Starting Batched Inter-Pass Suggestion Processing for mission {mission_id} ---")
    
    # Get mission context
    mission_context = controller.context_manager.get_mission_context(mission_id)
    if not mission_context or not mission_context.plan:
        logger.error("Cannot process suggestions: Mission context or plan missing.")
        return False
        
    if not reflection_data:
        logger.info("No reflection outputs collected. Proceeding with existing plan.")
        return True
    
    # Get configuration
    char_limit = get_max_planning_context_chars(mission_id)
    max_suggestions_batch = get_max_suggestions_per_batch(mission_id)
    
    # Get all notes and current outline
    all_notes = controller.context_manager.get_notes(mission_id)
    current_outline = mission_context.plan.report_outline
    
    # Separate suggestions by type
    structural_modifications = []
    subsection_suggestions_by_parent = {}
    
    for section_id, output in reflection_data:
        # Collect structural modifications
        if output.proposed_modifications:
            for mod in output.proposed_modifications:
                structural_modifications.append({
                    'section_id': section_id,
                    'modification': mod
                })
        
        # Collect subsection suggestions
        if output.suggested_subsection_topics:
            if section_id not in subsection_suggestions_by_parent:
                subsection_suggestions_by_parent[section_id] = []
            subsection_suggestions_by_parent[section_id].extend(output.suggested_subsection_topics)
    
    logger.info(f"Collected {len(structural_modifications)} structural modifications and "
               f"{sum(len(s) for s in subsection_suggestions_by_parent.values())} subsection suggestions "
               f"across {len(subsection_suggestions_by_parent)} parent sections")
    
    # Keep track of the evolving outline
    working_outline = current_outline
    overall_success = True
    
    # Phase 3a: Apply structural modifications (if any)
    if structural_modifications:
        logger.info("Phase 3a: Processing structural modifications...")
        
        # Format structural context
        structural_context = _format_structural_context(
            mission_context.user_request,
            working_outline,
            structural_modifications
        )
        
        # Check if it fits in the limit
        if len(structural_context) <= char_limit:
            # Apply all structural changes at once
            revised_outline = await _apply_structural_modifications(
                controller,
                mission_id,
                mission_context.user_request,
                structural_context,
                log_queue,
                update_callback,
                previous_outline=working_outline  # Pass current working outline
            )
            if revised_outline:
                working_outline = revised_outline
                logger.info("Successfully applied structural modifications")
            else:
                logger.warning("Failed to apply structural modifications, continuing with original structure")
        else:
            # Batch structural modifications if needed
            logger.info(f"Structural context too large ({len(structural_context)} chars), batching...")
            mod_batches = _batch_structural_modifications(structural_modifications, char_limit)
            
            for i, batch in enumerate(mod_batches):
                logger.info(f"Processing structural modification batch {i+1}/{len(mod_batches)}")
                batch_context = _format_structural_context(
                    mission_context.user_request,
                    working_outline,
                    batch
                )
                
                revised_outline = await _apply_structural_modifications(
                    controller,
                    mission_id,
                    mission_context.user_request,
                    batch_context,
                    log_queue,
                    update_callback,
                    previous_outline=working_outline  # Pass current working outline
                )
                if revised_outline:
                    working_outline = revised_outline
    
    # Phase 3b: Add subsections with notes (if any)
    if subsection_suggestions_by_parent:
        logger.info("Phase 3b: Processing subsection suggestions...")
        
        # Batch parent sections based on configuration
        if max_suggestions_batch == -1:
            # Process all at once
            parent_batches = [list(subsection_suggestions_by_parent.keys())]
        else:
            # Batch by configured size
            parent_ids = list(subsection_suggestions_by_parent.keys())
            parent_batches = [
                parent_ids[i:i + max_suggestions_batch]
                for i in range(0, len(parent_ids), max_suggestions_batch)
            ]
        
        logger.info(f"Processing subsection suggestions in {len(parent_batches)} batches")
        
        for batch_num, parent_batch in enumerate(parent_batches, 1):
            logger.info(f"Processing subsection batch {batch_num}/{len(parent_batches)} "
                       f"({len(parent_batch)} parent sections)")
            
            # Collect suggestions and relevant notes for this batch
            batch_suggestions = {}
            batch_note_ids = set()
            
            for parent_id in parent_batch:
                batch_suggestions[parent_id] = subsection_suggestions_by_parent[parent_id]
                # Collect relevant note IDs from the suggestions
                for suggestion in batch_suggestions[parent_id]:
                    if suggestion.relevant_note_ids:
                        batch_note_ids.update(suggestion.relevant_note_ids)
            
            # Get the actual notes
            relevant_notes = [n for n in all_notes if n.note_id in batch_note_ids]
            logger.info(f"Collected {len(relevant_notes)} relevant notes for this batch")
            
            # Format the context
            subsection_context = _format_subsection_context(
                mission_context.user_request,
                working_outline,
                batch_suggestions,
                relevant_notes
            )
            
            # Check if we need to batch the notes further
            if len(subsection_context) > char_limit:
                logger.info(f"Subsection context too large ({len(subsection_context)} chars), "
                           f"batching notes...")
                
                # Calculate base context size (without notes)
                base_context = _format_subsection_context(
                    mission_context.user_request,
                    working_outline,
                    batch_suggestions,
                    []  # No notes
                )
                base_size = len(base_context)
                available_for_notes = char_limit - base_size - 1000  # Leave some buffer
                
                if available_for_notes > 0:
                    # Batch notes while keeping suggestions together
                    note_batches = _batch_notes_by_char_limit(
                        relevant_notes,
                        available_for_notes
                    )
                    
                    for note_batch_num, note_batch in enumerate(note_batches, 1):
                        logger.info(f"Processing note sub-batch {note_batch_num}/{len(note_batches)}")
                        
                        batch_context = _format_subsection_context(
                            mission_context.user_request,
                            working_outline,
                            batch_suggestions,
                            note_batch
                        )
                        
                        revised_outline = await _apply_subsection_suggestions(
                            controller,
                            mission_id,
                            batch_context,
                            log_queue,
                            update_callback,
                            previous_outline=working_outline
                        )
                        
                        if revised_outline:
                            working_outline = revised_outline
                else:
                    logger.warning("Base context too large even without notes, skipping this batch")
            else:
                # Context fits, apply directly
                revised_outline = await _apply_subsection_suggestions(
                    controller,
                    mission_id,
                    subsection_context,
                    log_queue,
                    update_callback,
                    previous_outline=working_outline
                )
                
                if revised_outline:
                    working_outline = revised_outline
    
    # Phase 3c: Final note redistribution (if needed)
    # Check if there are unassigned notes
    assigned_note_ids = set()
    for section in outline_utils.flatten_outline(working_outline):
        if section.associated_note_ids:
            assigned_note_ids.update(section.associated_note_ids)
    
    unassigned_notes = [n for n in all_notes if n.note_id not in assigned_note_ids]
    
    if unassigned_notes:
        logger.info(f"Phase 3c: Redistributing {len(unassigned_notes)} unassigned notes...")
        
        # Batch unassigned notes if needed
        note_batches = _batch_notes_by_char_limit(unassigned_notes, char_limit)
        
        for batch_num, note_batch in enumerate(note_batches, 1):
            logger.info(f"Processing redistribution batch {batch_num}/{len(note_batches)}")
            
            redistribution_context = _format_redistribution_context(
                mission_context.user_request,
                working_outline,
                note_batch
            )
            
            revised_outline = await _apply_note_redistribution(
                controller,
                mission_id,
                redistribution_context,
                log_queue,
                update_callback
            )
            
            if revised_outline:
                working_outline = revised_outline
    
    # Store the final updated plan
    if working_outline != current_outline:
        try:
            updated_plan = SimplifiedPlan(
                mission_goal=mission_context.user_request,
                report_outline=working_outline
            )
            await controller.context_manager.store_plan(mission_id, updated_plan)
            logger.info("Successfully stored revised outline")
            return True
        except Exception as e:
            logger.error(f"Failed to store updated plan: {e}", exc_info=True)
            return False
    else:
        logger.info("No changes to outline after processing suggestions")
        return True


def _format_structural_context(user_request: str, outline: List[ReportSection], 
                               modifications: List[Dict]) -> str:
    """Format context for structural modifications."""
    context = f"Original User Request:\n{user_request}\n\n"
    context += "Current Report Outline Structure:\n"
    context += "\n".join(outline_utils.format_outline_for_prompt(outline))
    context += "\n\nStructural Modifications to Apply:\n"
    
    for mod_info in modifications:
        mod = mod_info['modification']
        context += f"- {mod.modification_type}: {mod.reasoning}\n"
        if mod.details:
            context += f"  Details: {json.dumps(mod.details.model_dump(), indent=2)}\n"
    
    return context


def _format_subsection_context(user_request: str, outline: List[ReportSection],
                               suggestions: Dict[str, List], notes: List[Note]) -> str:
    """Format context for subsection additions."""
    context = f"Original User Request:\n{user_request}\n\n"
    context += "Current Report Outline Structure:\n"
    context += "\n".join(outline_utils.format_outline_for_prompt(outline))
    context += "\n\nSubsection Suggestions to Add:\n"
    
    for parent_id, suggestion_list in suggestions.items():
        parent = outline_utils.find_section_recursive(outline, parent_id)
        parent_title = parent.title if parent else parent_id
        context += f"\nFor Parent Section '{parent_title}' (ID: {parent_id}):\n"
        
        for suggestion in suggestion_list:
            context += f"  - {suggestion.title}: {suggestion.description}\n"
            context += f"    Reasoning: {suggestion.reasoning}\n"
            if suggestion.relevant_note_ids:
                context += f"    Relevant Notes: {', '.join(suggestion.relevant_note_ids)}\n"
    
    if notes:
        context += "\n\nRelevant Notes for Context:\n"
        for note in notes:
            context += f"- Note ID: {note.note_id}\n"
            # Include a preview of the note content
            preview_length = 200
            if len(note.content) > preview_length:
                context += f"  Content: {note.content[:preview_length]}...\n"
            else:
                context += f"  Content: {note.content}\n"
            context += f"  Source: {note.source_type} - {note.source_id}\n\n"
    
    return context


def _format_redistribution_context(user_request: str, outline: List[ReportSection],
                                  notes: List[Note]) -> str:
    """Format context for note redistribution."""
    context = f"Original User Request:\n{user_request}\n\n"
    context += "Current Report Outline Structure:\n"
    context += "\n".join(outline_utils.format_outline_for_prompt(outline))
    context += "\n\nUnassigned Notes to Distribute:\n"
    
    for note in notes:
        context += f"- Note ID: {note.note_id}\n"
        # Include a preview
        preview_length = 150
        if len(note.content) > preview_length:
            context += f"  Content: {note.content[:preview_length]}...\n"
        else:
            context += f"  Content: {note.content}\n"
        context += f"  Source: {note.source_type} - {note.source_id}\n\n"
    
    return context


def _batch_structural_modifications(modifications: List[Dict], char_limit: int) -> List[List[Dict]]:
    """Batch structural modifications to fit within char limit."""
    batches = []
    current_batch = []
    current_size = 0
    base_size = 5000  # Estimate for base context
    
    for mod in modifications:
        mod_size = len(json.dumps(mod))
        if current_size + mod_size + base_size > char_limit and current_batch:
            batches.append(current_batch)
            current_batch = [mod]
            current_size = mod_size
        else:
            current_batch.append(mod)
            current_size += mod_size
    
    if current_batch:
        batches.append(current_batch)
    
    return batches


def _batch_notes_by_char_limit(notes: List[Note], char_limit: int) -> List[List[Note]]:
    """Batch notes to fit within character limit."""
    batches = []
    current_batch = []
    current_size = 0
    
    for note in notes:
        # Estimate note size in context (ID + preview + source)
        note_size = len(note.note_id) + min(200, len(note.content)) + 100
        
        if current_size + note_size > char_limit and current_batch:
            batches.append(current_batch)
            current_batch = [note]
            current_size = note_size
        else:
            current_batch.append(note)
            current_size += note_size
    
    if current_batch:
        batches.append(current_batch)
    
    return batches


async def _apply_structural_modifications(controller, mission_id: str, user_request: str,
                                         context: str, log_queue, update_callback,
                                         previous_outline: Optional[List[ReportSection]] = None):
    """Apply structural modifications using the planning agent with retry logic."""
    MAX_RETRIES = 3
    
    # Get the previous outline if not provided
    if previous_outline is None:
        mission_context = controller.context_manager.get_mission_context(mission_id)
        if mission_context and mission_context.plan:
            previous_outline = mission_context.plan.report_outline
    
    for retry in range(MAX_RETRIES):
        try:
            # Get current context
            current_scratchpad = controller.context_manager.get_scratchpad(mission_id)
            active_goals = controller.context_manager.get_active_goals(mission_id)
            active_thoughts = controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
            
            # Add retry context if this is a retry
            retry_context = context
            if retry > 0:
                retry_context = f"""IMPORTANT: Previous attempt produced an invalid outline. Please provide a complete, valid outline with actual sections.
DO NOT request an outline or use placeholder text. Generate the actual revised outline.

{context}"""
            
            # Call planning agent with the structural context
            async with controller.maybe_semaphore:
                response, model_details, scratchpad_update = await controller.planning_agent.run(
                    user_request=user_request,
                    revision_context=retry_context,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            
            if response and response.report_outline:
                revised_outline = response.report_outline
                
                # Validate the outline
                if is_error_outline(revised_outline):
                    logger.warning(f"Structural modifications produced error outline (retry {retry + 1}/{MAX_RETRIES})")
                    if retry < MAX_RETRIES - 1:
                        continue  # Try again
                    else:
                        logger.error("All retries failed to produce valid outline. Using previous outline.")
                        return previous_outline
                
                # Check for single section reduction
                if previous_outline and len(revised_outline) == 1 and len(previous_outline) > 1:
                    is_valid = await validate_single_section_intent(
                        controller, mission_id, revised_outline, previous_outline, user_request
                    )
                    if not is_valid:
                        logger.warning(f"Single section deemed unintentional (retry {retry + 1}/{MAX_RETRIES})")
                        if retry < MAX_RETRIES - 1:
                            continue  # Try again
                        else:
                            logger.error("Single section validation failed after all retries. Using previous outline.")
                            return previous_outline
                
                # Outline is valid
                logger.info(f"Successfully applied structural modifications (attempt {retry + 1})")
                return revised_outline
                
            logger.warning(f"No outline returned from planning agent (retry {retry + 1}/{MAX_RETRIES})")
            
        except Exception as e:
            logger.error(f"Error applying structural modifications (retry {retry + 1}/{MAX_RETRIES}): {e}", exc_info=True)
    
    # All retries failed
    logger.error("Failed to apply structural modifications after all retries. Using previous outline.")
    return previous_outline


async def _apply_subsection_suggestions(controller, mission_id: str, context: str,
                                       log_queue, update_callback,
                                       previous_outline: Optional[List[ReportSection]] = None):
    """Apply subsection suggestions using the planning agent with retry logic."""
    MAX_RETRIES = 3
    
    # Get the previous outline if not provided
    mission_context = controller.context_manager.get_mission_context(mission_id)
    if previous_outline is None:
        if mission_context and mission_context.plan:
            previous_outline = mission_context.plan.report_outline
    
    for retry in range(MAX_RETRIES):
        try:
            # Get current context
            current_scratchpad = controller.context_manager.get_scratchpad(mission_id)
            active_goals = controller.context_manager.get_active_goals(mission_id)
            active_thoughts = controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
            
            # Add retry context if this is a retry
            retry_context = context
            if retry > 0:
                retry_context = f"""IMPORTANT: Previous attempt produced an invalid outline. Please provide a complete, valid outline with actual sections.
DO NOT request an outline or use placeholder text. Generate the actual revised outline with subsections.

{context}"""
            
            # Call planning agent with the subsection context
            async with controller.maybe_semaphore:
                response, model_details, scratchpad_update = await controller.planning_agent.run(
                    user_request=mission_context.user_request,
                    revision_context=retry_context,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            
            if response and response.report_outline:
                revised_outline = response.report_outline
                
                # Validate the outline
                if is_error_outline(revised_outline):
                    logger.warning(f"Subsection suggestions produced error outline (retry {retry + 1}/{MAX_RETRIES})")
                    if retry < MAX_RETRIES - 1:
                        continue  # Try again
                    else:
                        logger.error("All retries failed to produce valid outline. Using previous outline.")
                        return previous_outline
                
                # Check for single section reduction
                if previous_outline and len(revised_outline) == 1 and len(previous_outline) > 1:
                    is_valid = await validate_single_section_intent(
                        controller, mission_id, revised_outline, previous_outline, 
                        mission_context.user_request
                    )
                    if not is_valid:
                        logger.warning(f"Single section deemed unintentional (retry {retry + 1}/{MAX_RETRIES})")
                        if retry < MAX_RETRIES - 1:
                            continue  # Try again
                        else:
                            logger.error("Single section validation failed after all retries. Using previous outline.")
                            return previous_outline
                
                # Outline is valid
                logger.info(f"Successfully applied subsection suggestions (attempt {retry + 1})")
                return revised_outline
                
            logger.warning(f"No outline returned from planning agent (retry {retry + 1}/{MAX_RETRIES})")
            
        except Exception as e:
            logger.error(f"Error applying subsection suggestions (retry {retry + 1}/{MAX_RETRIES}): {e}", exc_info=True)
    
    # All retries failed
    logger.error("Failed to apply subsection suggestions after all retries. Using previous outline.")
    return previous_outline


async def _apply_note_redistribution(controller, mission_id: str, context: str,
                                    log_queue, update_callback):
    """Apply note redistribution using the planning agent."""
    try:
        # Get current context
        current_scratchpad = controller.context_manager.get_scratchpad(mission_id)
        active_goals = controller.context_manager.get_active_goals(mission_id)
        active_thoughts = controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
        mission_context = controller.context_manager.get_mission_context(mission_id)
        
        # Call planning agent with the redistribution context
        async with controller.maybe_semaphore:
            response, model_details, scratchpad_update = await controller.planning_agent.run(
                user_request=mission_context.user_request,
                revision_context=context,
                active_goals=active_goals,
                active_thoughts=active_thoughts,
                agent_scratchpad=current_scratchpad,
                mission_id=mission_id,
                log_queue=log_queue,
                update_callback=update_callback
            )
        
        if response and response.report_outline:
            return response.report_outline
        return None
        
    except Exception as e:
        logger.error(f"Error applying note redistribution: {e}", exc_info=True)
        return None