# ai_researcher/agentic_layer/agents/note_assignment_agent.py
import logging
from typing import List, Dict, Any, Optional, Tuple, Set # <-- Import Set
from pydantic import BaseModel, Field, ValidationError # <-- Import ValidationError

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    prepare_for_pydantic_validation
)

# Use absolute imports
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.planning import ReportSection
from ai_researcher.agentic_layer.schemas.goal import GoalEntry # <-- Import GoalEntry
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Added import

logger = logging.getLogger(__name__)

class AssignedNotes(BaseModel):
    """Defines the structure for notes assigned to a specific section."""
    section_id: str = Field(..., description="The ID of the section these notes are assigned to.")
    relevant_note_ids: List[str] = Field(..., description="List of IDs of the notes deemed most relevant for this section.")
    reasoning: str = Field(..., description="Brief justification for selecting these notes for this specific section.")

class NoteAssignmentAgent(BaseAgent):
    """
    An agent responsible for selecting the most relevant notes for a given report section
    based on the section's goal and the content of the notes.
    """
    agent_name = "NoteAssignmentAgent"
    agent_description = "Assigns relevant notes to specific sections of a report outline."

    def __init__(self, model_dispatcher: ModelDispatcher, controller: Optional[Any] = None):
        """
        Initializes the NoteAssignmentAgent.

        Args:
            model_dispatcher: An instance of ModelDispatcher to interact with LLMs.
            controller: Optional controller instance for tracking LLM usage costs.
        """
        # Pass agent_name explicitly to the BaseAgent constructor
        super().__init__(agent_name="NoteAssignmentAgent", model_dispatcher=model_dispatcher)
        self.controller = controller # Store controller
        self.mission_id = None # Initialize mission_id as None
        logger.info(f"{self.agent_name} initialized.")

    async def run(
        self,
        mission_goal: str,
        section: ReportSection,
        all_notes: List[Note],
        min_notes: int, # <-- Changed from max_notes_per_section
        max_notes: int, # <-- Added max_notes
        previously_assigned_note_ids: Set[str], # <-- Added previously assigned IDs
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        agent_scratchpad: Optional[str] = None,
        mission_id: Optional[str] = None, # Add mission_id parameter
        log_queue: Optional[Any] = None, # Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None # Add update_callback parameter for UI updates
        # full_outline: Optional[List[ReportSection]] = None # Optional full outline context
    ) -> Tuple[Optional[AssignedNotes], Optional[Dict[str, Any]], Optional[str]]:
        """
        Executes the note assignment task for a single section, considering active goals.

        Args:
            mission_goal: The overall goal of the research mission.
            section: The specific ReportSection object to assign notes for.
            all_notes: A list of all available Note objects for the mission.
            min_notes: The minimum number of notes to assign.
            max_notes: The maximum number of notes to assign.
            previously_assigned_note_ids: Set of note IDs already assigned to other sections.
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.
            agent_scratchpad: Optional existing scratchpad content for the agent.
            mission_id: Optional ID of the current mission.
            log_queue: Optional queue for sending log messages to the UI.
            update_callback: Optional callback function for UI updates.

        Returns:
            A tuple containing:
            - An AssignedNotes object with the selected note IDs and reasoning, or None on failure.
            - A dictionary with model call details, or None.
            - The updated agent scratchpad content, or None if unchanged.
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        logger.info(f"Running {self.agent_name} for section '{section.section_id}' ('{section.title}')...")

        if not all_notes:
            logger.warning(f"No notes provided to {self.agent_name} for section {section.section_id}. Returning empty assignment.")
            # Return an empty assignment object, model details None, and original scratchpad
            return AssignedNotes(section_id=section.section_id, relevant_note_ids=[], reasoning="No notes available to assign."), None, agent_scratchpad


        prompt = self._create_prompt(
            mission_goal,
            section,
            all_notes,
            min_notes=min_notes, # <-- Pass min_notes
            max_notes=max_notes, # <-- Pass max_notes
            previously_assigned_note_ids=previously_assigned_note_ids, # <-- Pass previously assigned IDs
            active_goals=active_goals # <-- Pass active goals
        )
        # Use a model suitable for reasoning and JSON output
        # Removed call to get_default_params

        output_model = AssignedNotes

        # Call the LLM using the base agent's method
        raw_response, model_details = await self._call_llm(
            user_prompt=prompt,
            agent_mode="note_assignment", # Use dedicated mode for note assignment
            response_format={"type": "json_object"}, # Pass response_format directly
            log_queue=log_queue, # Pass log_queue for UI updates
            update_callback=update_callback, # Pass update_callback for UI updates
            log_llm_call=False # Disable duplicate LLM call logging since the overall operation is logged by the research manager
            # history=... if needed,
            # agent_scratchpad is not directly handled by _call_llm, manage separately if needed
        )

        parsed_output = None
        updated_scratchpad = agent_scratchpad # Assume scratchpad isn't modified by this specific call for now

        # Parse the response
        if raw_response and raw_response.choices and raw_response.choices[0].message and raw_response.choices[0].message.content:
            json_content = raw_response.choices[0].message.content
            try:
                # Parse the JSON content using our centralized utilities
                parsed_json = parse_llm_json_response(json_content)
                # Prepare the data for Pydantic validation
                prepared_data = prepare_for_pydantic_validation(parsed_json, AssignedNotes)
                # Validate using the Pydantic model
                parsed_output = AssignedNotes(**prepared_data)
                logger.info(f"Successfully parsed LLM response for section {section.section_id}.")
            except Exception as e:
                logger.error(f"Failed to parse/validate response for section {section.section_id}: {e}\nRaw Content Snippet: {json_content[:500]}...", exc_info=True)
        else:
            logger.error(f"LLM call failed or returned empty/invalid response structure for section {section.section_id}.")


        if parsed_output:
            # Validate that the returned section_id matches the input section_id (already done if parsing succeeded)
            if parsed_output.section_id != section.section_id:
                logger.warning(f"{self.agent_name} returned assignment for wrong section ID "
                               f"(expected '{section.section_id}', got '{parsed_output.section_id}'). Correcting.")
                parsed_output.section_id = section.section_id # Correct the ID

            logger.info(f"Assigned {len(parsed_output.relevant_note_ids)} notes to section {section.section_id}.")
        else:
            logger.error(f"{self.agent_name} failed to generate valid assignment for section {section.section_id}.")
            # Optionally return a default empty assignment on failure?
            # parsed_output = AssignedNotes(section_id=section.section_id, relevant_note_ids=[], reasoning="Agent failed to generate assignment.")


        return parsed_output, model_details, updated_scratchpad

    def _create_prompt(
        self,
        mission_goal: str,
        section: ReportSection,
        all_notes: List[Note],
        min_notes: int, # <-- Changed from max_notes
        max_notes: int, # <-- Added max_notes
        previously_assigned_note_ids: Set[str], # <-- Added previously assigned IDs
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None # <-- NEW: Add active thoughts
    ) -> str:
        """Creates the prompt for the LLM call, including active goals and thoughts."""
        # Truncate note content to manage prompt size
        notes_string = "\n".join([
            f"Note ID: {note.note_id}\n"
            f"Content Snippet: {note.content[:350]}...\n" # Increased snippet size slightly
            f"Source Type: {note.source_type}\n"
            f"Source ID: {note.source_id}\n"
            f"Metadata: {str(note.source_metadata)[:150]}...\n" # Add some metadata context
            "---"
            for note in all_notes
        ])

        # Format previously assigned notes for context
        prev_assigned_str = "None"
        if previously_assigned_note_ids:
            prev_assigned_str = ", ".join(sorted(list(previously_assigned_note_ids)))

        # Format active goals
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None" # <-- Removed .value
        # Format active thoughts
        thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts]) if active_thoughts else "None"

        prompt = f"""
You are an expert editor responsible for assigning relevant research notes to specific sections of a final report outline. Your goal is to ensure the writing agent receives the most pertinent information for each section, avoiding redundancy where possible, while staying aligned with the overall mission goals and recent thoughts.

Overall Mission Goal:
{mission_goal}

Active Mission Goals:
---
{goals_str}
---

Recent Thoughts:
---
{thoughts_str}
---

Current Section to Assign Notes For:
Section ID: {section.section_id}
Section Title: {section.title}
Section Description/Goal: {section.description}

Available Notes ({len(all_notes)} total):
---
{notes_string}
---

Note IDs Already Assigned to PREVIOUS Sections:
---
{prev_assigned_str}
---

Assignment Instructions:
1.  **Understand Context:** Deeply understand the 'Overall Mission Goal', the 'Active Mission Goals' (especially request type, tone, audience), the 'Recent Thoughts', and the specific 'Section Description/Goal' for the 'Current Section'.
2.  **Review Notes:** Carefully review the 'Content Snippet', 'Source Type', 'Source ID', and 'Metadata' for all 'Available Notes'.
3.  **Assess Section Needs:** Evaluate the complexity and information requirements of the 'Current Section' based on its description **and how it relates to the Active Mission Goals and Recent Thoughts**.
4.  **Select Best Fit (Dynamic Count):** Choose between {min_notes} and {max_notes} notes that are MOST DIRECTLY relevant and essential for writing THIS SPECIFIC section ('{section.title}'), **ensuring the selected notes align with the Active Mission Goals (e.g., tone, audience, request type) and Recent Thoughts**.
    *   Aim for a number of notes within the range [{min_notes}-{max_notes}] that appropriately matches the section's needs (more complex sections might need closer to {max_notes}, simpler ones closer to {min_notes}).
    *   Prioritize notes that provide core definitions, key arguments/evidence, or crucial context for *this* section, **in line with the mission goals and recent thoughts**.
    *   **Crucially, select notes with minimal overlap in the core information they provide.** Aim for diverse, complementary perspectives or data points relevant to the section goal **and mission goals/thoughts**.
5.  **Avoid Redundancy:** Consider the 'Note IDs Already Assigned to PREVIOUS Sections'. While a note *can* be assigned again if its content is uniquely critical to *this* section's specific focus, actively AVOID re-assigning notes if their primary contribution or core information has likely already been covered based on their assignment to previous sections. Use your judgment to minimize repetitive information across the final report.
6.  **Justify Selection:** Provide a concise overall reasoning explaining *why* this specific group of notes (mention the count selected) is the most relevant selection for *this particular section*, considering its goal, complexity, **alignment with Active Mission Goals and Recent Thoughts**, and the need for non-redundant information.
7.  **Format Output:** Return ONLY a single JSON object containing the `section_id`, the list of selected `relevant_note_ids`, and your `reasoning`. Adhere strictly to the specified JSON schema.

JSON Output Schema:
{{
  "section_id": "{section.section_id}",
  "relevant_note_ids": ["note_id_1", "note_id_2", ...], // List of selected note IDs (between {min_notes} and {max_notes})
  "reasoning": "Brief justification for selecting these specific notes (mention count) for this section, considering relevance, complexity, and non-redundancy."
}}

Ensure your output is only the valid JSON object. Do not include any other text before or after the JSON.
"""
        return prompt
