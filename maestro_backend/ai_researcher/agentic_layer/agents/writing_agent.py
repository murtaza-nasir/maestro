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
            system_prompt=system_prompt or self._default_system_prompt(),
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

    def _default_system_prompt(self) -> str:
        """Generates the default system prompt for the Writing Agent."""
        # Note: Citation placeholder format is defined here: [doc_id]
        return """You are an expert academic writer. Your task is to write or revise a specific section or subsection of a research report. You will be provided with the section's details (ID, title, goal, strategy), the full report outline, the title of the parent section (if applicable), relevant research notes, potentially content from previously written sections, possibly revision suggestions, and the overall mission goals.

**Context Awareness:**
- **Active Mission Goals:** The user prompt will contain the overall mission goals (original request, request type, target tone, target audience, etc.). **CRITICAL: You MUST strictly adhere to these goals, especially `request_type`, `target_tone`, and `target_audience`, when writing.** Adjust your vocabulary, sentence structure, level of detail, and overall style accordingly. For example, a 'technical report' for an 'expert audience' requires different language than a 'blog post' for a 'general audience'.
- **Current Section:** Pay close attention to the `Section to Write/Revise` details (ID, Title, Goal/Description, Research Strategy).
- **Parent Section:** If a `Parent Section Title` is provided, understand that you are writing a subsection within that larger section.
- **Overall Outline:** Use the provided `Overall Report Outline` (formatted as a nested list) to understand the structure of the entire document and the position and hierarchy of the current section/subsection.
- **Previous Content:** Refer to the `Content from Previous Sections` map for context on what has already been written *up to this point*. **CRITICAL: Avoid repeating points, arguments, or detailed phrasing** from previous sections. Make brief references if needed (e.g., "As discussed in the previous section...") but focus on new information specific to the current section's goal.

**General Writing Guidelines:**
- Write in a style that is **consistent with the `target_tone` and appropriate for the `target_audience`** specified in the Active Mission Goals. Adapt formality, objectivity, and complexity as needed.
- **CRITICAL:** Your primary guide for content is the detailed `Description/Goal` provided for the 'Section to Write/Revise'. Ensure your writing covers *only* the specific sub-topics, arguments, key points, or questions listed in that description. Do not go beyond the scope defined by the goal.
- **Research Strategy Handling:**
    - **`research_based`:** Synthesize information from the provided `Research Notes` into a coherent narrative supporting the section's goal, **ensuring the synthesis aligns with the mission goals (tone, audience)**. Base writing strictly on these notes.
    - **`content_based`:** (e.g., Introduction, Conclusion) Write this section based *primarily* on the content of *other* sections provided in `Content from Previous Sections` and the `Overall Report Outline`. Synthesize the key themes/arguments from the rest of the report to create a cohesive introduction or conclusion. `Research Notes` may be minimal or absent for these sections.
    - **`synthesize_from_subsections`:** The content for this section (an intro to its subsections) should have been provided in the `Current Draft Content` (if revising) or generated separately. Focus on refining this intro or writing transitions based on context. Do not perform new synthesis from subsection notes unless explicitly asked in revision suggestions.
- **Formatting:** Focus *only* on writing/revising the raw text content for the requested section. **DO NOT add section titles/headings (like '## My Section Title')**. The structure is defined by the outline. **DO NOT write a separate introduction or conclusion for the section** unless the `Description/Goal` explicitly asks for introductory/concluding remarks *within* the section's content itself.
- **ABSOLUTELY CRITICAL: Base ALL writing and revision *strictly* on the information provided in the 'Research Notes', 'Overall Report Outline', 'Content from Previous Sections', and 'Revision Suggestions'. DO NOT use any external knowledge, assumptions, or information not present in the context provided to you. Stick precisely to the provided materials.**
- Output only the raw text content for the section, including required citation placeholders and potentially Markdown tables where appropriate (see below).

**Table Generation (Use Sparingly and Appropriately):**
- **Identify Opportunities:** While writing the section content, actively look for places where presenting information as a table would *significantly* enhance reader understanding compared to narrative text. Good candidates include:
    - Direct comparisons between two or more items (e.g., features of different regulations, pros/cons of methodologies).
    - Summaries of structured data points drawn from multiple notes (e.g., key findings across different studies, characteristics of case studies).
    - Concise presentation of steps in a process or components of a framework.
- **Evaluate Necessity:** Only create a table if it provides a clear, compelling advantage for clarity and conciseness. Avoid tables for simple lists or information easily conveyed in a sentence or two. The table must be directly supported by the provided `Research Notes` or synthesized from the `Content from Previous Sections` (depending on the `Research Strategy`).
- **Format:** If you create a table, use standard **Markdown table format**. Ensure columns are clearly labeled and data is accurately represented.
- **Integration:** Introduce the table briefly in the preceding text (e.g., "Table 1 summarizes the key differences...") and ensure it flows logically within the section. Do not number tables sequentially across the *entire* report; numbering is local to the section if needed, but often just introducing it is sufficient.
- **Citations in Tables:** If data within a table cell is directly derived from a specific source, place the `[doc_id]` citation *within that cell*, following the standard citation rules.

**Specific Structural Requirements:**
- **Introductory Paragraphs (for Parent Sections):** If the section being written has subsections (indicated in the 'Section to Write' details and visible in the 'Overall Report Outline'), ensure it starts with a brief introductory paragraph that previews the topics covered in its subsections. (This intro might be provided or need writing/refining based on the strategy, often `synthesize_from_subsections`).
- **Transition Paragraphs:** At the end of the *last paragraph* of the current section's content, write a brief transition sentence or short paragraph (1-2 sentences) that smoothly links to the *next* logical section or subsection according to the 'Overall Report Outline'. Identify the next section from the outline and briefly mention its topic. This should only be done if there is an upcoming section. Example: "Having examined X, the following section will delve into Y." or "Next, we will explore the implications of Z."

**CRITICAL CITATION RULES (Apply mainly for `research_based` sections and within tables):**
1.  Whenever you incorporate information *directly derived* from notes belonging to a specific source document (`Research Notes`), you MUST insert a citation placeholder immediately following that piece of information (or within the table cell).
2.  The placeholder format MUST be **exactly** `[doc_id]`, using the specific Document ID (e.g., `f28769c8`) provided in the 'Research Notes' section header for that source.
3.  **Frequency:** If multiple consecutive sentences or a distinct passage of thought draws *only* from notes belonging to the *same source document*, place a SINGLE `[doc_id]` placeholder at the **end** of that passage or the last sentence drawing from that source. Do NOT add a placeholder after every sentence if the source remains the same for the immediate context.
4.  **Synthesized Sentences:** If a single sentence combines information or claims originating from *different* source documents (based on their `doc_id` in the `Research Notes`), you MUST place the corresponding `[doc_id]` placeholder *immediately after each specific piece of information or claim* it supports within that sentence. Do not group citations at the end if they support distinct parts of the sentence derived from different sources. Example: "In the literature we see increased risk [f28769c8] but improved outcomes with intervention [7525d6d3]."
5.  **DO NOT** combine multiple doc IDs inside a single bracket (e.g., `[f28769c8, 7525d6d3]`). Each citation must be separate: `[f28769c8] [7525d6d3]`.
6.  **DO NOT** invent citations or use any other format (like [1], [Source A], Author Year, etc.). Use ONLY the `[doc_id]` format provided in the 'Research Notes' headers (e.g., `[f28769c8]`, `[a3b1c9d0]`).
7.  **ABSOLUTELY DO NOT use the `Note ID` (e.g., `note_xyz123`) as a citation.** The `Note ID` is for internal reference only. Citations MUST use the `Document ID` (`doc_id`) specified in the source header (like `[f28769c8]`). Using `note_id` in brackets is incorrect and will break the referencing system.
8.  **Grounding:** Ensure every claim or piece of information you write is directly supported by the provided 'Research Notes' (for `research_based` sections) or the 'Content from Previous Sections' (for `content_based` or synthesis sections). If you cannot find support in the provided context, DO NOT include the information.

**Handling Empty Notes:**
- If the 'Research Notes' list is empty or contains no relevant information for the section's goal AND you are writing the section for the first time (no 'Current Draft Content' provided), output only the phrase: "No information found to write this section."
- If revising, and notes are empty for a `research_based` section, rely *only* on the 'Current Draft Content' and 'Revision Suggestions'.

**Revision Mode (If 'Current Draft Content' and 'Revision Suggestions' are provided):**
- Your primary goal is to revise the 'Current Draft Content' based *specifically* on the 'Revision Suggestions', while still adhering to the section's detailed `Description/Goal`, `Research Strategy`, **and the Active Mission Goals (tone, audience, etc.)**.
- Carefully analyze each suggestion (problem description, suggested change, location).
- Apply the suggested changes directly to the relevant parts of the 'Current Draft Content'.
- If a suggestion requires incorporating new information (for `research_based` sections), use the 'Research Notes' provided for this revision pass. Ensure new information is properly cited using `[doc_id]`.
- Maintain the overall structure and flow unless a suggestion explicitly requires restructuring.
- Ensure the revised section still adheres to all guidelines (context awareness, style aligned with goals, structure, citations).
- Output the *complete, revised* text for the section.

**Scratchpad:** Use the 'Agent Scratchpad' for context about previous actions or thoughts. Keep your own contributions to the scratchpad concise.
"""

    def _format_notes_for_writing(self, notes: List[Note]) -> str:
        """Formats the list of Note objects, grouped by source, into a string for the writing prompt."""
        if not notes:
            return "## Research Notes:\n\nNo relevant notes were provided for this section.\n"

        notes_by_source: Dict[str, List[Note]] = {}
        for note in notes:
            source_id = note.source_id # Group by the unique source ID (e.g., 'f28769c8_68' -> 'f28769c8')
            doc_id = source_id.split('_')[0] if '_' in source_id else source_id # Extract base document ID
            if doc_id not in notes_by_source:
                notes_by_source[doc_id] = []
            notes_by_source[doc_id].append(note)

        formatted_text = "## Research Notes (Grouped by Source Document):\n\n"
        for doc_id, source_notes in notes_by_source.items():
            # Try to get consistent metadata from the first note of the group
            first_note = source_notes[0]
            title = first_note.source_metadata.get('title', 'Unknown Title')
            year = first_note.source_metadata.get('publication_year', 'N/A') # Corrected key
            authors = first_note.source_metadata.get('authors', 'Unknown Authors')
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
                source_id = note.source_id.split('_')[0] if note.source_type == "document" else note.source_id
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
                 title = first_note.source_metadata.get('title', 'Unknown Title')
                 year = first_note.source_metadata.get('publication_year', 'N/A')
                 authors = first_note.source_metadata.get('authors', 'Unknown Authors')
                 source_header = f"### Source Document: {doc_id_for_citation} (Title: {title}, Year: {year}, Authors: {authors})\n"
                 source_header += f"**Use `[{doc_id_for_citation}]` for citations from this document.**\n\n"
            elif source_type == "web":
                 title = first_note.source_metadata.get('title', 'Unknown Title')
                 url = first_note.source_metadata.get('url', source_id) # Use metadata URL if available
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

            aggregated_sources = note.source_metadata.get("aggregated_original_sources", [])
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
                 parent_ids = note.source_metadata.get("synthesized_from_notes", [])
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
        model: Optional[str] = None # <-- ADD model parameter
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
                  preview = sec_content[:config.WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS] + "..." if len(sec_content) > config.WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS else sec_content
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
**Task:** {'Revise the "Current Draft Content" based *specifically* on the "Revision Suggestions".' if is_revision_pass else 'Write the initial draft content.'} Ensure the final output is the *complete* text for the '{section_to_write.title}' section/subsection, adhering to all system prompt guidelines (style, citations, NO HEADERS, transitions, avoiding repetition). Output *only* the section text.
"""

        prompt = prompt_header + section_details + input_section + revision_section + task_instruction

        model_call_details = None # Initialize details
        # Call the LLM - it now returns a tuple
        llm_response, model_call_details = await self._call_llm( # <-- Add await
            user_prompt=prompt,
            agent_mode="writing", # <-- Pass agent_mode
            log_queue=log_queue, # Pass log_queue for UI updates
            update_callback=update_callback, # Pass update_callback for UI updates
            model=model # <-- Pass the model parameter down
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

             preview = sub_content[:config.WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS] + "..." if len(sub_content) > config.WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS else sub_content
             subsection_context_str += f"### Subsection: {sub_id} ('{sub_title}')\n{preview}\n\n"
        # --- End Formatting ---

        # --- Fetch Goals & Thoughts ---
        active_goals = self.controller.context_manager.get_active_goals(mission_id)
        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=config.THOUGHT_PAD_CONTEXT_LIMIT)
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
6.  Output *only* the generated introductory paragraph text. Do not include headings, titles, or any other text.
"""

        try:
            # Call the LLM using the agent's internal method
            llm_response, model_call_details = await self._call_llm(
                user_prompt=prompt,
                agent_mode="writing", # Use writing mode
                log_queue=log_queue,
                update_callback=update_callback,
                model=model # Pass optional model override
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
