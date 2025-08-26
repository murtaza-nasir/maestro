from typing import Optional, List, Dict, Any, Tuple
from pydantic import ValidationError
import logging
import re # <-- Add import for regex

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    prepare_for_pydantic_validation
)

# Use absolute imports starting from the top-level package 'ai_researcher'
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
# Note: MODEL_MAPPING was removed from model_dispatcher, we should get it from config now
from ai_researcher import config # Import config to get model mapping
from ai_researcher.dynamic_config import get_writing_previous_content_preview_chars, get_thought_pad_context_limit
# Writing agent typically doesn't need tools directly
# from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.agentic_layer.schemas.planning import ReportSection # Needed for section context
# from ai_researcher.agentic_layer.schemas.research import ResearchFindings # No longer primary input
from ai_researcher.agentic_layer.schemas.notes import Note # <-- Import Note schema
from ai_researcher.agentic_layer.schemas.writing import WritingChangeSuggestion # <-- Import revision suggestion schema
from ai_researcher.agentic_layer.schemas.goal import GoalEntry # <-- Import GoalEntry
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Added import
# Import deque for finding next section
from collections import deque

logger = logging.getLogger(__name__)

class WritingAgent(BaseAgent):
    """
    Agent responsible for writing individual sections of the research report
    based on synthesized findings and the report outline.
    """
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        controller: Optional[Any] = None # Add controller parameter
    ):
        agent_name = "WritingAgent"
        # Determine the correct model name based on the 'writing' role from config
        writing_model_type = config.AGENT_ROLE_MODEL_TYPE.get("writing", "mid") # Default to mid if not specified
        if writing_model_type == "fast":
            provider = config.FAST_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["fast_model"]
        elif writing_model_type == "mid": # Explicitly check for mid
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]
        elif writing_model_type == "intelligent": # Add check for intelligent
            provider = config.INTELLIGENT_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["intelligent_model"]
        else: # Fallback if type is unknown
            logger.warning(f"Unknown writing model type '{writing_model_type}', falling back to mid.")
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]

        # Override with specific model_name if provided by the user during instantiation
        effective_model_name = model_name or effective_model_name

        super().__init__(
            agent_name=agent_name,
            model_dispatcher=model_dispatcher,
            tool_registry=None, # Writing agent doesn't execute tools
            model_name=effective_model_name
        )
        self.controller = controller # Store controller
        self.mission_id = None # Initialize mission_id as None

    def _sort_consecutive_citations(self, text: str) -> str:
        """Finds consecutive citation brackets like [10][2] or [abc][10] and sorts them numerically/lexicographically -> [2][10] or [10][abc]."""
        if not text:
            return ""

        # Regex to find sequences of two or more citation brackets: \[([^\]]+)\]
        # (\[[^\]]+\])     - Captures a single citation bracket like [abc] or [123]
        # (?:...)         - Non-capturing group for repetition
        # \s*             - Optional whitespace between brackets
        # (?:\s*\[[^\]]+\])+ - Matches one or more subsequent brackets with optional whitespace
        citation_pattern = re.compile(r"(\[[^\]]+\])((?:\s*\[[^\]]+\])+)")

        def replace_match(match):
            # Extract all citation brackets from the full match
            all_brackets = re.findall(r"\[([^\]]+)\]", match.group(0))

            # Define a sort key: try converting to int, fallback to string
            def sort_key(item):
                try:
                    # Return a tuple with 0 first to ensure numbers sort before strings
                    return (0, int(item))
                except ValueError:
                    # Return a tuple with 1 first to ensure strings sort after numbers
                    return (1, item) # Sort numbers first, then strings alphabetically

            # Sort the extracted IDs
            sorted_ids = sorted(all_brackets, key=sort_key)

            # Reconstruct the sorted string
            return "".join([f"[{id_}]" for id_ in sorted_ids])

        # Use re.sub with the callback function
        sorted_text = citation_pattern.sub(replace_match, text)
        return sorted_text

    def _default_system_prompt(self, language: str = "en") -> str:
        """Generates the default system prompt for the Writing Agent."""
        prompt_path = f"maestro_backend/ai_researcher/prompts/writing_agent_system_prompt_{language}.txt"
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Prompt file not found for language '{language}', falling back to English.")
            prompt_path = "maestro_backend/ai_researcher/prompts/writing_agent_system_prompt_en.txt"
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()

    def _format_notes_for_writing(self, notes: List[Note]) -> str:
        """Formats the list of Note objects, grouped by source, into a string for the writing prompt."""
        if not notes:
            return "## Research Notes:\n\nNo relevant notes were provided for this section.\n"

        notes_by_source: Dict[str, List[Note]] = {}
        for note in notes:
            source_id = note.source_id # Group by the unique source ID
            # For documents, source_id is already the full UUID, no need to split
            doc_id = source_id
            if doc_id not in notes_by_source:
                notes_by_source[doc_id] = []
            notes_by_source[doc_id].append(note)

        formatted_text = "## Research Notes (Grouped by Source Document):\n\n"
        for doc_id, source_notes in notes_by_source.items():
            # Try to get consistent metadata from the first note of the group
            first_note = source_notes[0]
            title = getattr(first_note.source_metadata, 'title', None) or 'Unknown Title'
            year = getattr(first_note.source_metadata, 'publication_year', None) or 'N/A' # Corrected key
            authors = getattr(first_note.source_metadata, 'authors', None) or 'Unknown Authors'
            source_header = f"### Source Document: {doc_id} (Title: {title}, Year: {year}, Authors: {authors})\n"
            formatted_text += source_header
            for note in source_notes:
                formatted_text += f"- **Note ID: {note.note_id}**\n"
                formatted_text += f"  - Content: {note.content}\n"
                # Optional: Add chunk ID if useful, but might be too much detail
                # chunk_id = note.source_metadata.get('chunk_id', 'N/A')
                # formatted_text += f"  - (Origin Chunk: {chunk_id})\n"
            formatted_text += "\n" # Add space between source groups

        return formatted_text

    def _format_revision_suggestions(self, suggestions: List[WritingChangeSuggestion]) -> str:
        """Formats the list of revision suggestions into a string for the prompt."""
        if not suggestions:
            return "No specific revision suggestions provided for this pass.\n"

        formatted_text = "## Revision Suggestions:\n\n"
        for i, suggestion in enumerate(suggestions):
            formatted_text += f"### Suggestion {i+1}:\n"
            formatted_text += f"- **Problem:** {suggestion.issue_description}\n"
            formatted_text += f"- **Suggested Change:** {suggestion.suggested_change}\n"
            # Removed check for non-existent location_context
            # if suggestion.location_context:
            #     formatted_text += f"- **Location Context:** \"...{suggestion.location_context}...\"\n"
            formatted_text += "\n"
        return formatted_text

    def _format_notes_for_writing(self, notes: List[Note]) -> str:
        """Formats the list of Note objects, grouped by source, into a string for the writing prompt."""
        if not notes:
            return "## Research Notes:\n\nNo relevant notes were provided for this section.\n"

        formatted_text = "## Research Notes (Grouped by Source Document/Synthesis):\n\n"
        processed_internal_notes = set() # Keep track of internal notes already processed via aggregation

        # First pass: Process notes with original sources (document/web)
        notes_by_original_source: Dict[str, List[Note]] = {}
        internal_notes_to_process: List[Note] = []

        for note in notes:
            if note.source_type in ["document", "web"]:
                # Group by original source ID (doc_id or URL)
                # For documents, source_id is the full UUID; for web, it's the URL
                source_id = note.source_id
                if source_id not in notes_by_original_source:
                    notes_by_original_source[source_id] = []
                notes_by_original_source[source_id].append(note)
            elif note.source_type == "internal":
                internal_notes_to_process.append(note)
            else:
                 logger.warning(f"Unexpected note source_type '{note.source_type}' encountered in _format_notes_for_writing.")

        # Format original source notes
        for source_id, source_notes in notes_by_original_source.items():
            first_note = source_notes[0]
            source_type = first_note.source_type
            doc_id_for_citation = source_id # This is already the base doc_id or URL

            # --- Determine Header based on source_type ---
            if source_type == "document":
                 title = getattr(first_note.source_metadata, 'title', None) or 'Unknown Title'
                 year = getattr(first_note.source_metadata, 'publication_year', None) or 'N/A'
                 authors = getattr(first_note.source_metadata, 'authors', None) or 'Unknown Authors'
                 source_header = f"### Source Document: {doc_id_for_citation} (Title: {title}, Year: {year}, Authors: {authors})\n"
                 source_header += f"**Use `[{doc_id_for_citation}]` for citations from this document.**\n\n"
            elif source_type == "web":
                 title = getattr(first_note.source_metadata, 'title', None) or 'Unknown Title'
                 url = getattr(first_note.source_metadata, 'url', None) or source_id # Use metadata URL if available
                 # For web sources, the doc_id for citation IS the URL
                 source_header = f"### Web Source: {url} (Title: {title})\n"
                 # Instruct LLM to use URL as citation ID for web sources? Or stick to doc_id format?
                 # Let's stick to doc_id format for consistency, using a hash of the URL?
                 # For now, let's use the URL directly but warn the LLM.
                 # Alternative: Generate a stable ID for web sources earlier.
                 # Let's assume doc_id format is required. We need a stable ID.
                 # Hashing URL might be an option, but let's use the note's source_id for now if it's web.
                 # This needs refinement based on how citation processing handles web URLs.
                 # For now, let's use the URL itself as the placeholder content, but this will break _process_citations.
                 # --> REVISED APPROACH: Use the first 8 chars of URL hash as doc_id for web?
                 import hashlib
                 web_doc_id = hashlib.sha1(url.encode()).hexdigest()[:8]
                 source_header += f"**Use `[{web_doc_id}]` for citations from this web page.**\n\n"
                 doc_id_for_citation = web_doc_id # Use the generated hash for citation
            else: # Should not happen based on filtering
                 source_header = f"### Unknown Source Type: {source_id}\n"
            # --- End Header Determination ---

            formatted_text += source_header
            for note in source_notes:
                formatted_text += f"- **Note ID: {note.note_id}**\n"
                formatted_text += f"  - Content: {note.content}\n"
            formatted_text += "\n"

        # Second pass: Process internal notes and their aggregated sources
        for note in internal_notes_to_process:
            if note.note_id in processed_internal_notes: continue # Skip if already handled via aggregation

            formatted_text += f"### Synthesized Information (Note ID: {note.note_id})\n"
            formatted_text += f"- Content: {note.content}\n"

            aggregated_sources = getattr(note.source_metadata, "aggregated_original_sources", None) or []
            if aggregated_sources:
                formatted_text += "- **Derived from Original Sources:**\n"
                for agg_source in aggregated_sources:
                    agg_source_type = agg_source.get("source_type")
                    agg_source_id = agg_source.get("source_id") # This is base doc_id or URL
                    agg_metadata = agg_source.get("source_metadata", {})
                    
                    citation_id_for_agg = agg_source_id # Default to URL or base doc_id
                    if agg_source_type == "web":
                         # Generate consistent hash for web source citation ID
                         import hashlib
                         citation_id_for_agg = hashlib.sha1(agg_source_id.encode()).hexdigest()[:8]

                    if agg_source_type == "document":
                         title = agg_metadata.get('title', 'Unknown Title')
                         year = agg_metadata.get('publication_year', 'N/A')
                         authors = agg_metadata.get('authors', 'Unknown Authors')
                         formatted_text += f"  - Document: {citation_id_for_agg} (Title: {title}, Year: {year}, Authors: {authors})\n"
                         formatted_text += f"    **Use `[{citation_id_for_agg}]` when citing information derived from this document via the synthesis note.**\n"
                    elif agg_source_type == "web":
                         title = agg_metadata.get('title', 'Unknown Title')
                         url = agg_metadata.get('url', agg_source_id)
                         formatted_text += f"  - Web Page: {url} (Title: {title})\n"
                         formatted_text += f"    **Use `[{citation_id_for_agg}]` when citing information derived from this web page via the synthesis note.**\n"
                    else:
                         formatted_text += f"  - Unknown Original Source Type: {agg_source_id}\n"
            else:
                 # This case might occur if the internal note was created before the aggregation logic was added,
                 # or if the trace-back failed.
                 parent_ids = getattr(note.source_metadata, "synthesized_from_notes", None) or []
                 formatted_text += f"- **Origin:** Synthesized from notes: {parent_ids}. Original sources could not be traced.\n"
                 formatted_text += "  **WARNING: Cannot generate specific citation placeholders for this synthesized content.**\n"

            formatted_text += "\n"
            processed_internal_notes.add(note.note_id)

        return formatted_text.strip() # Remove trailing newline

    async def run(
        self,
        section_to_write: ReportSection,
        notes_for_section: List[Note],
        previous_sections_content: Optional[Dict[str, str]] = None,
        full_outline: Optional[List[ReportSection]] = None, # NEW: Full outline structure
        parent_section_title: Optional[str] = None, # NEW: Title of the parent section
        current_draft_content: Optional[str] = None, # New: Existing draft for revision
        revision_suggestions: Optional[List[WritingChangeSuggestion]] = None, # New: Suggestions for revision
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        agent_scratchpad: Optional[str] = None, # NEW: Added scratchpad input
        mission_id: Optional[str] = None, # Add mission_id parameter
        log_queue: Optional[Any] = None, # Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None, # Add update_callback parameter for UI updates
        model: Optional[str] = None, # <-- ADD model parameter
        lang: str = "en"
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]: # Modified return type
        """
        Generates or revises the text content for a specific report section, considering active goals.

        Args:
            section_to_write: The ReportSection object defining the section to write/revise.
            notes_for_section: A list of Note objects relevant to this section/revision.
            previous_sections_content: Optional dictionary of content from previously written sections (for context).
            full_outline: Optional list representing the entire report outline structure.
            parent_section_title: Optional string, the title of the parent section if this is a subsection.
            current_draft_content: Optional string containing the existing draft of this section (for revision passes).
            revision_suggestions: Optional list of WritingChangeSuggestion objects (for revision passes).
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.
            agent_scratchpad: Optional string containing the current scratchpad content.
            mission_id: Optional ID of the current mission.
            log_queue: Optional queue for sending log messages to the UI.
            update_callback: Optional callback function for UI updates.
            model: Optional specific model name to use for this call.


        Returns:
            A tuple containing:
            - The generated text content for the section as a string (with citation placeholders), or None on failure.
            - A dictionary with model call details, or None on failure.
            - An optional string to update the agent scratchpad.
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        is_revision_pass = current_draft_content is not None # Revision if draft exists
        action = "Revising" if is_revision_pass else "Writing"
        logger.info(f"{self.agent_name}: {action} section '{section_to_write.section_id}' - '{section_to_write.title}'")
        scratchpad_update = None # Initialize
        notes_context = "## Research Notes:\n\n[Notes are intentionally excluded for this section based on its research strategy.]\n" # Default for non-research sections

        # Handle empty notes case specifically for research_based strategy on the first pass
        if section_to_write.research_strategy == "research_based":
            if not notes_for_section and not is_revision_pass:
                logger.warning(f"No notes provided for initial writing of research_based section {section_to_write.section_id}. Returning placeholder.")
                scratchpad_update = f"Skipped writing section {section_to_write.section_id}: No notes provided for initial pass (research_based)."
                return "No information found to write this section.", None, scratchpad_update
            elif not notes_for_section and is_revision_pass:
                logger.info(f"No *new* notes provided for revision of research_based section {section_to_write.section_id}. Proceeding with draft and suggestions.")
                # Proceed without notes if revising, scratchpad update will be set later
            else:
                # Format notes only if research_based and notes exist
                notes_context = self._format_notes_for_writing(notes_for_section)
        elif not notes_for_section and is_revision_pass:
             # Log if revising a non-research section without new notes (though notes aren't primary input here)
             logger.info(f"No *new* notes provided for revision of non-research_based section {section_to_write.section_id}. Proceeding with draft and suggestions.")

        # Format inputs for the LLM
        revision_context = self._format_revision_suggestions(revision_suggestions or [])

        # --- Format Outline Context ---
        outline_context_str = "## Overall Report Outline:\n\n"
        if full_outline:
            outline_context_str += "\n".join(self._format_outline_for_prompt(full_outline))
        else:
            outline_context_str += "[Outline not provided]\n"
        outline_context_str += "\n"
        # --- End Format Outline Context ---

        # --- Format Previous Sections Context ---
        previous_context = ""
        if previous_sections_content:
             previous_context += "## Content from Previous Sections (for context and to avoid repetition):\n\n"
             # Simple approach: provide all previous sections passed in. Limit length.
             # TODO: Consider providing only immediately preceding sections or summaries?
             for sec_id, sec_content in previous_sections_content.items():
                  # Limit length to avoid excessive context
                  char_limit = get_writing_previous_content_preview_chars(self.mission_id)
                  preview = sec_content[:char_limit] + "..." if len(sec_content) > char_limit else sec_content
                  previous_context += f"### Section: {sec_id}\n{preview}\n\n"
        else:
             previous_context += "## Content from Previous Sections:\n\n[No previous sections written yet or provided]\n\n"
        # --- End Format Previous Sections Context ---

        # Construct the prompt based on whether it's a revision pass
        prompt_header = f"""Please {'revise' if is_revision_pass else 'write'} the content for the following research report section/subsection, following all instructions in the system prompt.
"""
        # Include scratchpad content if available
        scratchpad_context = ""
        if agent_scratchpad:
            scratchpad_context = f"\nCurrent Agent Scratchpad:\n---\n{agent_scratchpad}\n---\n"

        # Format active goals
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None" # Use g.status directly
        active_goals_context = f"""
**Active Mission Goals (Consider these for tone, audience, and overall direction):**
---
{goals_str}
---
"""
        # Format active thoughts
        thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts]) if active_thoughts else "None"
        active_thoughts_context = f"""
**Recent Thoughts (Consider these for context and focus):**
---
{thoughts_str}
---
"""

        section_details = f"""{scratchpad_context}
{active_goals_context}
{active_thoughts_context}
**Section to Write/Revise:**
- **ID:** {section_to_write.section_id}
- **Title:** {section_to_write.title}
- **Parent Section Title:** {parent_section_title or 'N/A (This is a top-level section)'}
- **Description/Goal:** {section_to_write.description}
- **Has Subsections:** {'Yes' if section_to_write.subsections else 'No'}
- **Research Strategy:** {section_to_write.research_strategy}
"""

        input_section = f"""
**Input Information:**
---
{outline_context_str}
---
{notes_context}
---
{previous_context}
---
"""

        revision_section = ""
        if is_revision_pass:
            revision_section = f"""
**Current Draft Content (to be revised):**
---
{current_draft_content}
---

**Revision Suggestions (apply these to the draft):**
---
{revision_context}
---
"""

        task_instruction = f"""
**Task:** {'Revise the "Current Draft Content" based *specifically* on the "Revision Suggestions".' if is_revision_pass else 'Write the initial draft content.'} Ensure the final output is the *complete* text for the '{section_to_write.title}' section/subsection, adhering to all system prompt guidelines (style, citations, NO HEADERS, transitions, avoiding repetition). 

**CRITICAL:** Output *only* the section text. Do NOT include any meta-commentary, agent thoughts, or scratchpad content. Do NOT prefix your response with "Agent Scratchpad:" or any similar text.
"""

        prompt = prompt_header + section_details + input_section + revision_section + task_instruction

        model_call_details = None # Initialize details
        system_prompt = self._default_system_prompt(language=lang)
        # Call the LLM - it now returns a tuple
        llm_response, model_call_details = await self._call_llm( # <-- Add await
            user_prompt=prompt,
            system_prompt_override=system_prompt,
            agent_mode="writing", # <-- Pass agent_mode
            log_queue=log_queue, # Pass log_queue for UI updates
            update_callback=update_callback, # Pass update_callback for UI updates
            model=model, # <-- Pass the model parameter down
            log_llm_call=False # Disable duplicate LLM call logging since writing operations are logged by higher-level methods
            # Temperature is handled by the ModelDispatcher based on model defaults/config
            # No specific response format needed, expect raw text
        )

        if not llm_response or not llm_response.choices:
            logger.error(f"{self.agent_name} Error: Failed to get response from LLM for section '{section_to_write.section_id}'.")
            scratchpad_update = f"LLM call failed during {action} of section {section_to_write.section_id}."
            return None, model_call_details, scratchpad_update # Return details even on failure

        section_content = llm_response.choices[0].message.content
        if not section_content:
             logger.error(f"{self.agent_name} Error: LLM returned empty content for section '{section_to_write.section_id}'.")
             scratchpad_update = f"LLM returned empty content during {action} of section {section_to_write.section_id}."
             return None, model_call_details, scratchpad_update # Return details even on empty content

        logger.info(f"{self.agent_name}: Successfully generated content for section '{section_to_write.section_id}'.")
        scratchpad_update = f"Successfully {action.lower()} section {section_to_write.section_id} ('{section_to_write.title}')."
        
        # --- Sort consecutive citations ---
        sorted_section_content = self._sort_consecutive_citations(section_content.strip())
        # --- End sort ---
        
        return sorted_section_content, model_call_details, scratchpad_update # Return sorted content, details, and scratchpad update

    # --- NEW: Helper to format outline for prompt ---
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

    # --- NEW: Method for Synthesizing Section Intros ---
    async def synthesize_intro(
        self,
        mission_id: str,
        section: ReportSection,
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None,
        model: Optional[str] = None # Allow overriding model
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        Generates introductory content for a section based on its subsections' content.
        Moved from AgentController.
        """
        self.mission_id = mission_id # Set mission_id for _call_llm
        action_name = f"Synthesize Intro: {section.section_id}"
        logger.info(f"{self.agent_name}: {action_name} ('{section.title}')")
        scratchpad_update = None
        model_call_details = None
        synthesized_content = f"[Error: Failed to synthesize intro for section '{section.title}']" # Default error content

        if not self.controller:
            logger.error(f"{self.agent_name} Error: Controller reference not set. Cannot access context manager.")
            return None, None, "Controller reference missing in WritingAgent."

        if not section.subsections:
            logger.warning(f"Section {section.section_id} has no subsections. Cannot synthesize intro.")
            scratchpad_update = f"Skipped synthesizing intro for section {section.section_id}: No subsections found."
            # Return empty string or a placeholder? Let's return a placeholder indicating it wasn't needed.
            return "[Intro synthesis not applicable: No subsections]", None, scratchpad_update

        # --- Gather Subsection Content ---
        subsection_content_map: Dict[str, str] = {}
        missing_content = False
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context:
             logger.error(f"Cannot synthesize intro for {section.section_id}: Mission context not found.")
             return None, None, f"Mission context {mission_id} not found during intro synthesis."

        for sub in section.subsections:
            content = mission_context.report_content.get(sub.section_id)
            if content:
                subsection_content_map[sub.section_id] = content
            else:
                logger.warning(f"Content missing for subsection {sub.section_id} needed for synthesizing intro of {section.section_id}.")
                missing_content = True
                # Optionally include a placeholder in the map?
                subsection_content_map[sub.section_id] = f"[Content missing for subsection {sub.section_id}]"

        if not subsection_content_map: # Should not happen if subsections exist, but safety check
             logger.error(f"No subsection content found for section {section.section_id} despite subsections existing.")
             scratchpad_update = f"Failed synthesizing intro for section {section.section_id}: No subsection content available."
             return synthesized_content, None, scratchpad_update

        # --- Format Subsection Content for Prompt ---
        subsection_context_str = "## Subsection Content (to synthesize introduction from):\n\n"
        for sub_id, sub_content in subsection_content_map.items():
             # Find subsection title
             sub_title = "Unknown Subsection"
             # Need to search the outline structure for the title
             # This requires access to the full outline, let's assume it's available via section.subsections
             found_sub = next((s for s in section.subsections if s.section_id == sub_id), None)
             if found_sub:
                  sub_title = found_sub.title

             char_limit = get_writing_previous_content_preview_chars(self.mission_id)
             preview = sub_content[:char_limit] + "..." if len(sub_content) > char_limit else sub_content
             subsection_context_str += f"### Subsection: {sub_id} ('{sub_title}')\n{preview}\n\n"
        # --- End Formatting ---

        # --- Fetch Goals & Thoughts ---
        active_goals = self.controller.context_manager.get_active_goals(mission_id)
        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=get_thought_pad_context_limit(mission_id))
        # Ensure only GoalEntry objects are processed
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals if isinstance(g, GoalEntry)]) if active_goals else "None" # Use g.status directly
        active_goals_context = f"**Active Mission Goals:**\n---\n{goals_str}\n---\n"
        thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts]) if active_thoughts else "None"
        active_thoughts_context = f"**Recent Thoughts:**\n---\n{thoughts_str}\n---\n"
        # --- End Fetch Goals & Thoughts ---

        # Construct the prompt
        prompt = f"""You are an expert academic writer. Your task is to write a concise introductory paragraph for a specific section of a research report, based *only* on the provided content of its immediate subsections.

{active_goals_context}
{active_thoughts_context}
**Section Requiring Introduction:**
- **ID:** {section.section_id}
- **Title:** {section.title}
- **Description/Goal:** {section.description}

{subsection_context_str}

**Instructions:**
1.  Read the content previews of all subsections carefully.
2.  Identify the main themes, topics, or arguments covered across the subsections.
3.  Write a single, concise introductory paragraph (typically 3-5 sentences) that:
    - Briefly introduces the overall topic of the parent section ('{section.title}').
    - Clearly previews the specific topics or structure that will be covered in the subsequent subsections (based on their content).
    - Provides a smooth transition into the first subsection.
4.  **CRITICAL:** Base the introduction *strictly* on the provided subsection content. Do not introduce new information, concepts, or citations not present in the subsections.
5.  Adhere to the `target_tone` and `target_audience` specified in the Active Mission Goals.
6.  **CRITICAL:** Output *only* the generated introductory paragraph text. Do NOT include headings, titles, meta-commentary, agent thoughts, or scratchpad content. Do NOT prefix your response with "Agent Scratchpad:" or any similar text.
"""

        try:
            # Call the LLM using the agent's internal method
            llm_response, model_call_details = await self._call_llm(
                user_prompt=prompt,
                agent_mode="writing", # Use writing mode
                log_queue=log_queue,
                update_callback=update_callback,
                model=model, # Pass optional model override
                log_llm_call=False # Disable duplicate LLM call logging since synthesis operations are logged by higher-level methods
            )

            if llm_response and llm_response.choices and llm_response.choices[0].message.content:
                synthesized_content = llm_response.choices[0].message.content.strip()
                if synthesized_content:
                    # Store the synthesized content
                    self.controller.context_manager.store_report_section(mission_id, section.section_id, synthesized_content)
                    logger.info(f"Successfully synthesized and stored intro for section {section.section_id}.")
                    scratchpad_update = f"Synthesized intro for section {section.section_id}."
                else:
                    logger.error(f"LLM returned empty content for synthesizing intro of section {section.section_id}.")
                    scratchpad_update = f"LLM returned empty content during intro synthesis for section {section.section_id}."
                    # Store the default error message
                    self.controller.context_manager.store_report_section(mission_id, section.section_id, synthesized_content)

            else:
                logger.error(f"LLM response invalid or missing content for synthesizing intro of section {section.section_id}.")
                scratchpad_update = f"LLM call failed during intro synthesis for section {section.section_id}."
                # Store the default error message
                self.controller.context_manager.store_report_section(mission_id, section.section_id, synthesized_content)


        except Exception as e:
            logger.error(f"Error during intro synthesis LLM call for section {section.section_id}: {e}", exc_info=True)
            scratchpad_update = f"Exception during intro synthesis for section {section.section_id}: {e}"
            # Store the default error message
            self.controller.context_manager.store_report_section(mission_id, section.section_id, synthesized_content)

        # Log the step (using controller's context manager for consistency)
        log_status = "success" if synthesized_content and not synthesized_content.startswith("[Error:") else "failure"
        self.controller.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name=self.agent_name, # Use agent's name
            action=action_name,
            input_summary=f"Synthesizing intro for '{section.title}' based on {len(section.subsections)} subsections.",
            output_summary=f"Generated intro length: {len(synthesized_content)}" if log_status == "success" else f"Failed: {scratchpad_update}",
            status=log_status,
            error_message=scratchpad_update if log_status == "failure" else None,
            full_input={'section': section.model_dump(), 'subsection_ids': list(subsection_content_map.keys())},
            full_output=synthesized_content,
            model_details=model_call_details,
            log_queue=log_queue,
            update_callback=update_callback
        )

        return synthesized_content, model_call_details, scratchpad_update
    # --- End Synthesize Intro Method ---
