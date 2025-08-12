import json
import logging
from typing import Optional, Dict, Tuple, Any, List
from pydantic import ValidationError

# Use absolute imports
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
# Import the updated schema and Note
from ai_researcher.agentic_layer.schemas.planning import ReportSection
# Import the updated schema components
from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput, SuggestedSubsectionTopic, OutlineModification
from ai_researcher.agentic_layer.context_manager import MissionContext
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.agentic_layer.schemas.goal import GoalEntry
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry
# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_json_string_recursively,
    sanitize_json_string,
    parse_llm_json_response,
    prepare_for_pydantic_validation,
    extract_non_schema_fields,
    filter_null_values_from_list
)
from ai_researcher.agentic_layer.utils.json_format_helper import (
    get_json_schema_format,
    get_json_object_format,
    enhance_messages_for_json_object,
    should_retry_with_json_object
)

logger = logging.getLogger(__name__)

class ReflectionAgent(BaseAgent):
    """
    Analyzes the current state of the research (plan, notes) and suggests
    Analyzes the current state of research notes for a specific section,
    identifies gaps, contradictions, and areas for improvement, and generates
    questions or suggests structural changes (like subsections) to guide further research.
    """
    def __init__(self, model_dispatcher: ModelDispatcher, controller: Optional[Any] = None):
        # TODO: Consider a dedicated 'reflection' model type in config? For now, use default.
        super().__init__(agent_name="ReflectionAgent", model_dispatcher=model_dispatcher)
        self.controller = controller # Store controller
        self.mission_id = None # Initialize mission_id as None
        logger.info("ReflectionAgent initialized.")

    def _format_notes_for_prompt(self, notes: List[Note]) -> str:
        """Formats the list of Note objects into a string for the prompt."""
        if not notes:
            return "No notes available for this section yet."
        note_lines = []
        for i, note in enumerate(notes):
            # Basic escaping of braces within the content
            escaped_content = note.content.replace('{', '{{').replace('}', '}}')
            source_info = f"(Source: {note.source_type} - {note.source_id})"
            note_lines.append(f"Note {note.note_id}: {escaped_content} {source_info}")
        return "\n".join(note_lines)

    def _format_outline_for_prompt(self, outline: List[ReportSection], level: int = 0) -> List[str]:
        """Recursively formats the report outline into a list of strings with indentation."""
        outline_lines = []
        indent = "  " * level
        for i, section in enumerate(outline):
            prefix = f"{indent}{i+1}." if level == 0 else f"{indent}-" # Use numbers only for top level
            outline_lines.append(f"{prefix} ID: {section.section_id}, Title: {section.title}")
            # Recursively add subsections
            outline_lines.extend(self._format_outline_for_prompt(section.subsections, level + 1))
        return outline_lines

    def _prepare_reflection_prompt(
        self,
        mission_context: MissionContext, # Still needed for overall goal and outline structure
        section_id: str,
        section_title: str, # Added
        section_goal: str,  # Added (was description)
        notes_for_section: List[Note],
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        agent_scratchpad: Optional[str] = None # NEW: Added scratchpad
    ) -> str:
        """
        Prepares the prompt for the LLM based on the current context, notes, active goals, active thoughts, and scratchpad for a specific section.

        Args:
            mission_context: The current state of the mission.
            section_id: The ID of the section currently being analyzed.
            section_title: The title of the section.
            section_goal: The goal/description of the section.
            notes_for_section: List of Note objects gathered for this section.
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.
            agent_scratchpad: Optional string containing the current scratchpad content.

        Returns:
            The formatted prompt string.
        """
        # Section details are now passed directly as arguments
        current_outline_str = "Outline not available."
        if mission_context.plan and mission_context.plan.report_outline:
            outline_lines = self._format_outline_for_prompt(mission_context.plan.report_outline)
            current_outline_str = "Current Report Outline Structure:\n---\n" + "\n".join(outline_lines) + "\n---"

        formatted_notes = self._format_notes_for_prompt(notes_for_section)

        # Include scratchpad content if available
        scratchpad_context = ""
        if agent_scratchpad:
            scratchpad_context = f"\nCurrent Agent Scratchpad:\n---\n{agent_scratchpad}\n---\n"

        # Format active goals
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None"
        
        # Format active thoughts
        thoughts_context = ""
        if active_thoughts:
            thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts])
            thoughts_context = f"\nRecent Thoughts:\n---\n{thoughts_str}\n---\n"
            thoughts_context += "Consider these recent thoughts when analyzing the notes and generating your own thought.\n"

        prompt = f"""
You are a meticulous Research Analyst performing iterative refinement. Your task is to analyze the collected notes for a specific research section, compare them against the section's goal, the overall report outline, active mission goals, and the agent scratchpad, identify areas for improvement, and guide the next research steps for **this section only**.

**Overall Research Goal:**
{mission_context.user_request}

**Active Mission Goals:**
---
{goals_str}
---

{current_outline_str}
{scratchpad_context}

**Current Section Being Analyzed:**
- ID: {section_id}
- Title: {section_title}
- Goal/Description: {section_goal}

**Collected Notes for this Section:**
---
{formatted_notes}
---

**Your Tasks:**
1.  **Assess Notes:** Critically evaluate the provided notes based on their relevance to the section goal, completeness, coherence, potential contradictions or gaps, **AND alignment with the Active Mission Goals (especially tone and audience)**.
2.  **Identify Next Steps:** Based on your assessment, determine what is needed next for *this specific section* to better meet its goal and the overall mission goals.
3.  **Generate Questions for Current Section:** If the notes for *this section* are incomplete, contradictory, lack depth, **or fail to align with Active Mission Goals**, formulate specific, actionable questions (`new_questions`) for the Research Agent to investigate in the *next iteration* for this section. Ensure questions guide towards fulfilling the section goal AND the mission goals. **IMPORTANT: Each question string in the `new_questions` list must contain ONLY the question text itself, without any surrounding context, numbering, or phrases like "Focus on answering:".**
4.  **Suggest Subsections for Current Section:** If the notes for *this section* cover several distinct sub-topics **that align with the mission goals**, suggest these as potential future subsections by defining `suggested_subsection_topics`. Check the outline first to avoid duplicates. Assign relevant existing notes (`relevant_note_ids`) to these suggested topics.
5.  **Suggest Broader Outline Changes (Consider between Research Rounds):** Based on the notes for *this section* AND the *overall outline context* AND the *Active Mission Goals*, if you identify a need for broader structural changes (e.g., a major theme emerging from this section's notes warrants a *new top-level section*, or this section's content strongly suggests *merging* with another existing section), suggest these using `proposed_modifications`. Clearly state the reasoning. Check the existing outline carefully before proposing additions/merges. Use this more judiciously than generating questions or suggesting subsections for the current section.
6.  **Flag for Full Review (RARELY):** Only if the notes for *this section* are **completely irrelevant**, contain **irreparable contradictions**, are otherwise **critically unusable**, **or fundamentally misaligned with mission goals**, add the section ID to `sections_needing_review`. Do not use this for simple incompleteness.
7.  **Identify Notes to Discard:** If any notes are clearly redundant (repeating information already present) or irrelevant (off-topic for the section goal **or mission goals**), list their IDs in `discard_note_ids`. Be conservative; only discard notes that add no value or actively detract.
8.  **Generate Thought:** Based on your analysis, formulate a concise, focused thought (1-2 sentences) capturing a key insight, reminder, or focus point about the research direction for *this section* or the *overall mission* that would be valuable to remember. Populate the `generated_thought` field with this thought.

**Output Format:**
Provide ONLY a single JSON object conforming EXACTLY to the ReflectionOutput schema below. Ensure all fields are present, using empty lists `[]` if no questions, suggestions, modifications, reviews, or discards are needed. IMPORTANT: Never include null values in lists - if you have no items for a list field, use an empty list `[]` instead.

**PERMITTED FIELDS ONLY (DO NOT include any other fields):**
- `overall_assessment` (string): Your detailed assessment 
- `new_questions` (array of strings): Questions for next research iteration
- `suggested_subsection_topics` (array of objects): Subsection suggestions with required fields: title, description, relevant_note_ids, reasoning
- `proposed_modifications` (array of objects): Outline structure changes (use sparingly)  
- `sections_needing_review` (array of strings): Section IDs needing full re-run
- `critical_issues_summary` (string or null): Summary of critical issues
- `discard_note_ids` (array of strings): Note IDs to discard
- `generated_thought` (string or null): Your thought about research direction

```json
{{
  "overall_assessment": "string",
  "new_questions": ["string"],
  "suggested_subsection_topics": [
    {{
      "title": "string",
      "description": "string", 
      "relevant_note_ids": ["string"],
      "reasoning": "string"
    }}
  ],
  "proposed_modifications": [
     {{
       "modification_type": "ADD_SECTION | REMOVE_SECTION | MERGE_SECTIONS | REORDER_SECTIONS | REFRAME_SECTION_TOPIC | SPLIT_SECTION",
       "details": {{}},
       "reasoning": "string"
     }}
  ],
  "sections_needing_review": ["string"],
  "critical_issues_summary": "string or null",
  "discard_note_ids": ["string"],
  "generated_thought": "string or null"
}}
```

**IMPORTANT:** Focus your analysis and generated questions/subsections *only* on the provided notes and the goal of the current section (`{section_id}`), BUT use the provided **Current Report Outline Structure** and **Agent Scratchpad** for context and to avoid proposing redundant sections or subsections. Ensure your entire output is a single, valid JSON object.
"""
        logger.debug(f"Generated ReflectionAgent prompt for section {section_id}:\n{prompt[:500]}...")
        return prompt.strip()

    # Removed _format_summaries_for_prompt as it's not used


    async def run( # <-- Make method async
        self,
        mission_context: MissionContext,
        section_id: str,
        section_title: str, # Added
        section_goal: str,  # Added
        notes_for_section: List[Note],
        agent_scratchpad: Optional[str] = None, # NEW: Added scratchpad input
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        mission_id: Optional[str] = None, # Add mission_id parameter
        log_queue: Optional[Any] = None, # Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None # Add update_callback parameter for UI updates
    ) -> Tuple[Optional[ReflectionOutput], Optional[Dict[str, Any]], Optional[str]]: # Modified return type
        """
        Executes the reflection process for a specific section based on its notes, active goals, and active thoughts.

        Args:
            mission_context: The full context of the current mission.
            section_id: The ID of the section to reflect upon.
            section_title: The title of the section.
            section_goal: The goal/description of the section.
            notes_for_section: List of Note objects gathered for this section.
            agent_scratchpad: Optional string containing the current scratchpad content.
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.
            mission_id: Optional ID of the current mission.
            log_queue: Optional queue for sending log messages to the UI.
            update_callback: Optional callback function for UI updates.

        Returns:
            A tuple containing:
            - A ReflectionOutput object with the agent's analysis and suggestions, or None if the process fails.
            - A dictionary with model call details, or None on failure.
            - An optional string to update the agent scratchpad.
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        logger.info(f"Running ReflectionAgent for section {section_id} in mission {mission_context.mission_id}...")

        # Removed redundant plan check here, as necessary info is passed in
        scratchpad_update = None # Initialize

        prompt = self._prepare_reflection_prompt(
            mission_context=mission_context,
            section_id=section_id,
            section_title=section_title,
            section_goal=section_goal,
            notes_for_section=notes_for_section,
            active_goals=active_goals, # <-- Pass active_goals
            active_thoughts=active_thoughts, # <-- Pass active_thoughts
            agent_scratchpad=agent_scratchpad
        )

        # Use system prompt if defined, otherwise just user prompt
        messages = [{"role": "user", "content": prompt}]
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})

        # Try json_schema format first, with fallback to json_object
        response_format_pydantic = get_json_schema_format(
            pydantic_model=ReflectionOutput,
            schema_name="reflection_output"
        )
        use_json_object = False

        # Add retry logic similar to other agents
        max_retries = 3
        model_call_details = None
        response_model = None # Initialize response_model
        
        for attempt in range(max_retries):
            try:
                logger.info(f"ReflectionAgent attempt {attempt + 1}/{max_retries} for section {section_id}")
                
                # Prepare messages based on format type
                current_messages = messages
                if use_json_object:
                    current_messages = enhance_messages_for_json_object(
                        messages=messages,
                        pydantic_model=ReflectionOutput
                    )
                
                # Use the dispatch method - assuming it returns (response_object, details_dict)
                response, model_call_details = await self.model_dispatcher.dispatch( # <-- Add await
                    messages=current_messages,
                    response_format=response_format_pydantic,
                    model=self.model_name,
                    agent_mode="reflection", # <-- Pass agent_mode
                    log_queue=log_queue, # Pass log_queue for UI updates
                    update_callback=update_callback # Pass update_callback for UI updates
                )

                if response and response.choices and response.choices[0].message.content:
                    raw_json_output = response.choices[0].message.content
                    try:
                        # Use the centralized JSON utilities to parse and prepare the response
                        raw_json_output = response.choices[0].message.content
                        
                        # Parse the JSON response
                        parsed_data = parse_llm_json_response(raw_json_output)
                        
                        # Extract non-schema fields like scratchpad_update
                        extra_fields = extract_non_schema_fields(parsed_data, ReflectionOutput)
                        scratchpad_update = extra_fields.get("scratchpad_update")
                        
                        # Prepare the data for Pydantic validation
                        prepared_data = prepare_for_pydantic_validation(parsed_data, ReflectionOutput)
                        
                        # Special handling for suggested_subsection_topics
                        if 'suggested_subsection_topics' in prepared_data:
                            # Filter out null values
                            if prepared_data['suggested_subsection_topics'] is not None:
                                prepared_data['suggested_subsection_topics'] = filter_null_values_from_list(prepared_data['suggested_subsection_topics'])
                                logger.info(f"Filtered null values from suggested_subsection_topics, resulting in {len(prepared_data['suggested_subsection_topics'])} items")
                                
                                # Check if the first item is a tuple (only if the list is not empty)
                                if len(prepared_data['suggested_subsection_topics']) > 0 and isinstance(prepared_data['suggested_subsection_topics'][0], tuple):
                                    # Flatten the tuple into individual items
                                    prepared_data['suggested_subsection_topics'] = list(prepared_data['suggested_subsection_topics'][0])
                                    logger.info("Flattened tuple in suggested_subsection_topics")
                        
                        # Log the parsed data structure for debugging
                        logger.debug(f"Parsed data after processing: {json.dumps(prepared_data, indent=2)}")
                        
                        # Validate the rest of the data against the schema
                        response_model = ReflectionOutput(**prepared_data)
                        # If we successfully created response_model, break out of retry loop
                        if response_model:
                            break
                            
                    except (json.JSONDecodeError, ValidationError) as e:
                        logger.error(f"Attempt {attempt + 1}/{max_retries}: Failed to parse/validate ReflectionOutput JSON for section {section_id}: {e}\nRaw output: {raw_json_output}", exc_info=True)
                        
                        # Enhanced debugging for validation errors
                        if isinstance(e, ValidationError):
                            logger.error("Validation error details:")
                            for error in e.errors():
                                logger.error(f"  Field: {error['loc']}, Error: {error['msg']}, Input: {error.get('input', 'N/A')}")
                                
                                # If the error is in suggested_subsection_topics, log more details
                                if error['loc'] and error['loc'][0] == 'suggested_subsection_topics':
                                    if 'suggested_subsection_topics' in parsed_data:
                                        logger.error(f"  suggested_subsection_topics content: {parsed_data['suggested_subsection_topics']}")
                                        
                                        # Log the type of each item
                                        for i, topic in enumerate(parsed_data['suggested_subsection_topics']):
                                            logger.error(f"  Item {i} type: {type(topic)}, Value: {topic}")
                        
                        # If this was the last attempt, return None
                        if attempt == max_retries - 1:
                            logger.error(f"All {max_retries} attempts failed for section {section_id}")
                            return None, model_call_details, scratchpad_update
                        else:
                            logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                            continue
                            
                else:
                    logger.error(f"Attempt {attempt + 1}/{max_retries}: ReflectionAgent failed for section {section_id}: No valid response content received from model.")
                    # If this was the last attempt, return None
                    if attempt == max_retries - 1:
                        logger.error(f"All {max_retries} attempts failed for section {section_id}")
                        return None, model_call_details, scratchpad_update
                    else:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                        continue
                    
            except Exception as e:
                # Check if we should retry with json_object format
                if not use_json_object and should_retry_with_json_object(e):
                    logger.info(f"Retrying with json_object format due to: {str(e)[:200]}")
                    response_format_pydantic = get_json_object_format()
                    use_json_object = True
                    # Don't increment attempt counter, retry with new format
                    continue
                
                logger.error(f"Attempt {attempt + 1}/{max_retries}: Error during ReflectionAgent execution for section {section_id}: {e}", exc_info=True)
                # If this was the last attempt, return None
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} attempts failed for section {section_id}")
                    return None, model_call_details, scratchpad_update
                else:
                    logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                    continue
        
        # Handle successful response outside the retry loop
        if response_model:
            # --- Force sections_needing_review to be empty ---
            if response_model.sections_needing_review:
                logger.warning(f"LLM suggested sections for review: {response_model.sections_needing_review}. Overriding to empty list.")
                response_model.sections_needing_review = []
            # --- End override ---

            logger.info(f"ReflectionAgent completed successfully for section {section_id}.")
            # Log key decisions from the updated schema
            logger.info(f"  Assessment: {response_model.overall_assessment[:100]}...")
            logger.info(f"  New Questions: {len(response_model.new_questions)}")
            logger.info(f"  Suggested Subsection Topics: {len(response_model.suggested_subsection_topics)}") # Updated field name
            logger.info(f"  Proposed Modifications: {len(response_model.proposed_modifications)}")
            logger.info(f"  Sections Needing Review: {response_model.sections_needing_review}")
            logger.info(f"  Critical Issues: {bool(response_model.critical_issues_summary)}")
            # --- Log discarded notes ---
            logger.info(f"  Notes Suggested for Discard: {len(response_model.discard_note_ids)}")
            if response_model.discard_note_ids:
                logger.info(f"    Discard IDs: {response_model.discard_note_ids}")
            # --- End log discarded notes ---
            logger.info(f"  Scratchpad Update: {scratchpad_update}")
            return response_model, model_call_details, scratchpad_update
        else:
            # This case means all retries failed
            logger.error(f"ReflectionAgent failed: Could not create response model for section {section_id} after {max_retries} attempts.")
            return None, model_call_details, scratchpad_update
