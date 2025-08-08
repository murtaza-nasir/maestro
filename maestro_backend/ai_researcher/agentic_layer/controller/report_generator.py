import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
import queue
import re
import datetime
import json

from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT
from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry
from ai_researcher.agentic_layer.schemas.planning import ReportSection

logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    Manages the report generation phase of the mission, including title generation
    and citation processing.
    """
    
    def __init__(self, controller):
        """
        Initialize the ReportGenerator with a reference to the AgentController.
        
        Args:
            controller: The AgentController instance
        """
        self.controller = controller
        
    async def generate_report_title(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> bool:
        """
        Generates a title for the final report using the WritingAgent based on the
        original query, active goals/thoughts, and the first/last sections of the report.
        """
        logger.info(f"Generating report title for mission {mission_id}...")
        mission_context = self.controller.context_manager.get_mission_context(mission_id)

        if not mission_context or not mission_context.plan or not mission_context.report_content:
            logger.error(f"Cannot generate title: Mission context, plan, or report content missing for {mission_id}.")
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Generate Report Title",
                status="failure", error_message="Prerequisites missing (context, plan, or content).",
                log_queue=log_queue, update_callback=update_callback
            )
            return False

        user_request = mission_context.user_request
        report_outline = mission_context.plan.report_outline
        report_content_map = mission_context.report_content

        first_section_content = "[First section content not found]"
        last_section_content = "[Last section content not found]"

        # Get first top-level section ID and content
        if report_outline:
            first_section_id = report_outline[0].section_id
            first_section_content = report_content_map.get(first_section_id, f"[Content missing for section {first_section_id}]")

            # Get last top-level section ID and content
            # Need to handle nested structures to find the *true* last section content
            # Let's get the last top-level section object first
            last_top_level_section = report_outline[-1]
            # Now find the very last section in the depth-first order originating from this last top-level section
            # Use the utility function get_sections_in_order
            from ai_researcher.agentic_layer.controller.utils import outline_utils
            last_section_overall_id = outline_utils.get_sections_in_order([last_top_level_section])[-1].section_id  # Get last section in DFS order of the last top-level branch
            last_section_content = report_content_map.get(last_section_overall_id, f"[Content missing for section {last_section_overall_id}]")

        # Limit content length to avoid excessive token usage
        max_content_length = 1500  # Characters per section for context
        first_section_snippet = first_section_content[:max_content_length]
        last_section_snippet = last_section_content[:max_content_length]

        # Fetch Active Thoughts
        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT)
        thoughts_context = "\nRecent Thoughts (Focus Points & Reminders):\n---\n"
        if active_thoughts:
            for thought in active_thoughts:
                thoughts_context += f"- [{thought.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] ({thought.agent_name}): {thought.content}\n"
        else:
            thoughts_context += "No recent thoughts.\n"
        thoughts_context += "---\n"

        # Format Active Goals
        active_goals = self.controller.context_manager.get_active_goals(mission_id)
        goals_context = "\nActive Goals:\n---\n"
        if active_goals:
            for goal in active_goals:
                # Check if goal is an object with description or just a string
                if hasattr(goal, 'description'):
                    goals_context += f"- {goal.description}\n"
                elif isinstance(goal, str):
                    goals_context += f"- {goal}\n"
                else:
                    goals_context += f"- {str(goal)}\n"  # Fallback
        else:
            goals_context += "No active goals.\n"
        goals_context += "---\n"

        # Construct the prompt for the title generation
        prompt = f"""
Generate a concise and compelling title for a research report based on the original user query, active goals, recent thoughts, and the content of the first and last sections.

Original User Query:
---
{user_request}
---
{goals_context}
{thoughts_context}
First Section Content (Snippet):
---
{first_section_snippet}
---

Last Section Content (Snippet):
---
{last_section_snippet}
---

Instructions:
1. Analyze the Original User Query, Active Goals, and Recent Thoughts to understand the core request, key objectives, and latest focus points. Determine the likely tone (e.g., academic, technical, general interest).
2. Consider the First Section (likely introduction/background) and Last Section (likely conclusion/summary) to grasp the report's scope and key takeaways.
3. Generate a title that accurately reflects the report's main topic and findings, incorporating insights from the goals and thoughts.
4. Match the title's tone to the inferred tone of the Original User Query and Goals.
5. The title should be concise (ideally 5-15 words).
6. Output ONLY the generated title text, with no extra formatting, quotes, or explanations.

CRITICAL: Do NOT include formatting like "**Title:**", "Title:", markdown, or any prefixes. Return ONLY the plain title text itself.
"""

        generated_title = None
        model_details = None
        log_status = "failure"
        error_message = "LLM call failed or returned empty content."

        try:
            # Use the model dispatcher directly with the 'writing' model configuration
            async with self.controller.maybe_semaphore:
                response, model_details = await self.controller.model_dispatcher.dispatch(
                    messages=[{"role": "user", "content": prompt}],
                    agent_mode="writing"  # Use the writing model configuration
                )

            if response and response.choices and response.choices[0].message.content:
                generated_title = response.choices[0].message.content.strip().strip('"')  # Remove surrounding quotes if any
                
                # Clean up common formatting patterns from thinking models
                generated_title = re.sub(r'^\*\*Title:\*\*\s*', '', generated_title, flags=re.IGNORECASE)
                generated_title = re.sub(r'^Title:\s*', '', generated_title, flags=re.IGNORECASE)
                generated_title = re.sub(r'^\*\*.*?\*\*:\s*', '', generated_title)  # Remove any **Label:** pattern
                generated_title = generated_title.strip()
                
                if generated_title:
                    # Store the title in metadata
                    self.controller.context_manager.update_mission_metadata(mission_id, {"report_title": generated_title})
                    log_status = "success"
                    error_message = None
                    logger.info(f"Generated report title: '{generated_title}'")
                else:
                    error_message = "LLM returned empty content for title."
            else:
                error_message = "LLM response was invalid or missing content."

            # Update stats if details are available
            if model_details:
                self.controller.context_manager.update_mission_stats(mission_id, model_details, log_queue, update_callback)

        except Exception as e:
            logger.error(f"Error during title generation LLM call for mission {mission_id}: {e}", exc_info=True)
            error_message = f"Exception during LLM call: {e}"
            # Keep generated_title as None

        # Log the outcome
        self.controller.context_manager.log_execution_step(
            mission_id, "AgentController", "Generate Report Title",
            input_summary=f"Query: {user_request[:50]}..., First/Last section snippets provided.",
            output_summary=f"Generated Title: '{generated_title}'" if log_status == "success" else f"Failed: {error_message}",
            status=log_status, error_message=error_message,
            full_input={'user_request': user_request, 'first_section_snippet': first_section_snippet, 'last_section_snippet': last_section_snippet},
            full_output={'generated_title': generated_title}, model_details=model_details,
            log_queue=log_queue, update_callback=update_callback
        )

        return log_status == "success"

    def _map_note_id_to_doc_id(self, note_id: str, all_notes: List[Any]) -> Optional[str]:
        """
        Maps a note ID to its corresponding document ID.
        
        Args:
            note_id: The note ID to map (e.g., 'note_38c7c6a2')
            all_notes: List of all Note objects for the mission
            
        Returns:
            The corresponding document ID if found, None otherwise
        """
        # Find the note with the given ID
        note = next((n for n in all_notes if n.note_id == note_id), None)
        if not note:
            logger.warning(f"Could not find note with ID '{note_id}' in the mission notes.")
            return None
            
        # Extract the document ID from the source_id
        source_id_full = note.source_id
        source_type = note.source_type
        doc_id = None
        
        if source_type == "document":
            # Extract base doc_id from source_id (e.g., 'doc_abc_123' -> 'abc')
            doc_id = source_id_full.split('_')[0]
        elif source_type == "web":
            # Generate a stable ID for web sources
            import hashlib
            url_str = str(source_id_full)
            doc_id = hashlib.sha1(url_str.encode()).hexdigest()[:8]
        elif source_type == "internal":
            doc_id = source_id_full
        else:
            # Fallback
            doc_id = source_id_full
            
        return doc_id
    
    def process_citations(
        self,
        mission_id: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> bool:
        """Processes citation placeholders and generates the reference list."""
        logger.info(f"Processing citations for mission {mission_id}...")
        self.controller.context_manager.log_execution_step(
            mission_id, "AgentController", "Process Citations",
            input_summary="Starting citation processing.", status="success",
            log_queue=log_queue, update_callback=update_callback
        )
        mission_context = self.controller.context_manager.get_mission_context(mission_id)
        if not mission_context or not mission_context.plan or not mission_context.report_content:
            logger.error(f"Cannot process citations: Mission context, plan, or report content missing for {mission_id}.")
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Process Citations",
                input_summary="Checking prerequisites", status="failure",
                error_message="Mission context, plan, or report content missing.",
                log_queue=log_queue, update_callback=update_callback
            )
            return False

        # Use recursive function to build draft with hierarchical numbering
        full_draft = ""
        # Modify the recursive function to accept and generate numbering prefixes
        def build_draft_recursive(section_list: List[ReportSection], level: int = 1, prefix: str = ""):
            nonlocal full_draft
            for i, section in enumerate(section_list):
                # Calculate the number for the current section
                current_number = f"{prefix}{i + 1}"
                # Generate the heading markdown
                heading_marker = "#" * level
                # Prepend the number to the title in the heading
                full_draft += f"{heading_marker} {current_number}. {section.title}\n\n"
                # Get the content for the section
                content = mission_context.report_content.get(section.section_id, f"[Content missing for section {section.section_id}]")
                full_draft += f"{content}\n\n"
                # Recursively call for subsections, passing the new prefix
                if section.subsections:
                    build_draft_recursive(section.subsections, level + 1, prefix=f"{current_number}.")

        # Initial call to the recursive function
        build_draft_recursive(mission_context.plan.report_outline)

        # Regex to find placeholders like [id1] or [id1, id2, id3] or [note_id1]
        # It captures the full content inside the brackets.
        placeholder_pattern = re.compile(r'\[((?:[a-f0-9]{8}|note_[a-f0-9]{8})(?:\s*,\s*(?:[a-f0-9]{8}|note_[a-f0-9]{8}))*)\]')
        # Regex to extract individual 8-char hex IDs or note_IDs from the content within brackets
        id_pattern = re.compile(r'([a-f0-9]{8}|note_[a-f0-9]{8})')

        # Build doc_metadata_source (mapping doc_id -> Note object for metadata lookup)
        all_notes = self.controller.context_manager.get_notes(mission_id)
        doc_metadata_source: Dict[str, Any] = {}
        note_id_to_doc_id_map: Dict[str, str] = {}  # Map note_ids to doc_ids
        
        for note in all_notes:
            source_id_full = note.source_id  # e.g., doc_abc_123 or https://...
            source_type = note.source_type
            lookup_key = ""
            if source_type == "document":
                lookup_key = source_id_full.split('_')[0]  # Use base doc_id
            elif source_type == "web":
                import hashlib
                url_str = str(source_id_full)
                lookup_key = hashlib.sha1(url_str.encode()).hexdigest()[:8]
            elif source_type == "internal":
                lookup_key = source_id_full
            else:
                lookup_key = source_id_full  # Fallback

            if lookup_key and lookup_key not in doc_metadata_source:
                doc_metadata_source[lookup_key] = note
                
            # Store mapping from note_id to doc_id
            note_id_to_doc_id_map[note.note_id] = lookup_key

        # Find and Validate Used IDs
        used_doc_ids = set()
        all_matches = list(placeholder_pattern.finditer(full_draft))  # Find all potential placeholders first

        for match in all_matches:
            content_inside_brackets = match.group(1)
            potential_ids_in_match = id_pattern.findall(content_inside_brackets)
            for potential_id in potential_ids_in_match:
                # Check if it's a note_id and map it to doc_id if needed
                if potential_id.startswith('note_'):
                    if potential_id in note_id_to_doc_id_map:
                        mapped_doc_id = note_id_to_doc_id_map[potential_id]
                        logger.info(f"Mapped note ID '{potential_id}' to document ID '{mapped_doc_id}'")
                        # Use the mapped doc_id instead
                        potential_id = mapped_doc_id
                    else:
                        # Try to map it using the helper method
                        mapped_doc_id = self._map_note_id_to_doc_id(potential_id, all_notes)
                        if mapped_doc_id:
                            logger.info(f"Mapped note ID '{potential_id}' to document ID '{mapped_doc_id}' using helper method")
                            # Use the mapped doc_id instead
                            potential_id = mapped_doc_id
                        else:
                            logger.warning(f"Could not map note ID '{potential_id}' to a document ID")
                            continue  # Skip this ID
                
                # Validate against known sources BEFORE adding to used_doc_ids
                if potential_id in doc_metadata_source:
                    used_doc_ids.add(potential_id)
                else:
                    # Log invalid IDs found within a potential placeholder pattern
                    logger.warning(f"Found potential but invalid/unknown doc ID '{potential_id}' inside brackets: {match.group(0)}")

        if not used_doc_ids:
            logger.info(f"No valid citation placeholders containing known document IDs found in the draft for mission {mission_id}.")
            self.controller.context_manager.store_final_report(mission_id, full_draft.strip())
            self.controller.context_manager.update_mission_status(mission_id, "completed")
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Process Citations",
                output_summary="Completed (No citations found/needed).", status="success",
                full_input={'draft_length': len(full_draft)}, full_output=full_draft.strip(),
                log_queue=log_queue, update_callback=update_callback
            )
            return True

        doc_citation_map = {}
        reference_entries = {}
        citation_counter = 1
        processed_text = full_draft  # Start with the original draft for replacement

        # Build map and reference list ONLY for validated IDs
        for doc_id in sorted(list(used_doc_ids)):  # Sort for consistent numbering
            if doc_id not in doc_citation_map:
                doc_citation_map[doc_id] = citation_counter
                # Metadata source already validated, so doc_id MUST be in doc_metadata_source
                metadata_note = doc_metadata_source[doc_id]
                ref_entry = f"{citation_counter}. Unknown Source ({doc_id})"  # Default reference

                if metadata_note:
                    source_type = metadata_note.source_type
                    metadata = metadata_note.source_metadata

                    if source_type == "document" and 'overlapping_chunks' in metadata and metadata['overlapping_chunks']:
                        # Document Source Handling
                        chunk_metadata = metadata['overlapping_chunks'][0]
                        title = chunk_metadata.get('title')  # Get raw value or None
                        year = chunk_metadata.get('publication_year')  # Get raw value or None
                        authors = chunk_metadata.get('authors')  # Get raw value or None
                        journal = chunk_metadata.get('journal_or_source')  # Extract journal

                        # Process authors only if available and not the default placeholder
                        authors_str = None
                        if authors and authors != 'Unknown Authors':
                            try:
                                if isinstance(authors, str) and authors.startswith('[') and authors.endswith(']'):
                                    import ast
                                    authors_list = ast.literal_eval(authors)
                                    if isinstance(authors_list, list) and authors_list:  # Check if list is not empty
                                        authors_str = ", ".join(authors_list)
                                elif isinstance(authors, list) and authors:  # Check if list is not empty
                                    authors_str = ", ".join(authors)
                                elif isinstance(authors, str):  # Handle plain string authors if not list format
                                    authors_str = authors
                                # If parsing fails or authors is an empty list/string, authors_str remains None
                            except (SyntaxError, ValueError, TypeError) as parse_err:
                                logger.warning(f"Could not parse authors field for doc_id '{doc_id}': {authors}. Error: {parse_err}")
                                # Keep authors_str as None

                        # Check if year is available and not the default placeholder
                        year_str = str(year) if year and year != 'N/A' else None

                        # Check if title is available and not the default placeholder
                        title_str = title if title and title != 'Unknown Title' else None
                        # Check if journal is available and not the default placeholder
                        journal_str = journal if journal and journal != 'Unknown Journal/Source' else None

                        # Build APA-like reference string piece by piece
                        ref_parts = [f"{citation_counter}."]
                        if authors_str:
                            ref_parts.append(f"{authors_str}.")  # APA ends author list with '.'
                        if year_str:
                            ref_parts.append(f"({year_str}).")  # Year in parentheses with '.'
                        if title_str:
                            # APA uses sentence case for article titles, keeping original for now
                            ref_parts.append(f"{title_str}.")  # Title ends with '.'
                        if journal_str:
                            ref_parts.append(f"*{journal_str}*.")  # Journal italicized, ends with '.'

                        # Join the parts with spaces. If only counter exists, use default.
                        if len(ref_parts) > 1:
                            ref_entry = " ".join(ref_parts)
                        else:
                            # Fallback if no meaningful metadata was found
                            ref_entry = f"{citation_counter}. Unknown Document ({doc_id})"
                            logger.warning(f"Using fallback reference for doc_id '{doc_id}' as no meaningful metadata (authors/year/title/journal) was found.")

                    elif source_type == "web":
                        # Web Source Handling
                        title = metadata.get('title', 'Unknown Title')
                        url = metadata.get('url', doc_id)  # Use doc_id (which should be URL hash or similar) as fallback

                        # Get timestamp from the Note object itself
                        access_timestamp = metadata_note.created_at
                        access_date_str = "Unknown Date"
                        if isinstance(access_timestamp, datetime.datetime):
                            # Format as "Month Day, Year" e.g., "April 16, 2025"
                            access_date_str = access_timestamp.strftime("%B %d, %Y")
                        elif isinstance(access_timestamp, str):
                            # Attempt to parse if it's a string (ISO format expected)
                            try:
                                dt_obj = datetime.datetime.fromisoformat(access_timestamp.replace('Z', '+00:00'))  # Handle Z timezone
                                access_date_str = dt_obj.strftime("%B %d, %Y")
                            except ValueError:
                                logger.warning(f"Could not parse timestamp string '{access_timestamp}' for web source {doc_id}.")
                                access_date_str = access_timestamp  # Use raw string if parsing fails

                        # Web Source Handling (Academic Style + URL)
                        # Extract metadata fields similar to document sources
                        # The metadata here comes from the Note's source_metadata,
                        # which should now contain the output from MetadataExtractor
                        web_title = metadata.get('title', 'Unknown Title')
                        web_year = metadata.get('publication_year')  # Get raw value or None
                        web_authors = metadata.get('authors')  # Get raw value or None
                        web_source_name = metadata.get('journal_or_source')  # e.g., website name

                        # Process authors (similar to document handling)
                        web_authors_str = None
                        if web_authors and web_authors != 'Unknown Authors':
                            try:
                                if isinstance(web_authors, str) and web_authors.startswith('[') and web_authors.endswith(']'):
                                    import ast
                                    authors_list = ast.literal_eval(web_authors)
                                    if isinstance(authors_list, list) and authors_list:
                                        web_authors_str = ", ".join(authors_list)
                                elif isinstance(web_authors, list) and web_authors:
                                    web_authors_str = ", ".join(web_authors)
                                elif isinstance(web_authors, str):
                                    web_authors_str = web_authors
                            except (SyntaxError, ValueError, TypeError) as parse_err:
                                logger.warning(f"Could not parse authors field for web source '{doc_id}': {web_authors}. Error: {parse_err}")

                        web_year_str = str(web_year) if web_year else None
                        web_title_str = web_title if web_title and web_title != 'Unknown Title' else None
                        web_source_name_str = web_source_name if web_source_name else None

                        # Build APA-like reference string piece by piece
                        ref_parts = [f"{citation_counter}."]
                        if web_authors_str:
                            ref_parts.append(f"{web_authors_str}.")
                        if web_year_str:
                            ref_parts.append(f"({web_year_str}).")
                        if web_title_str:
                            # Use italics for web page titles? APA often uses sentence case. Let's keep it plain for now.
                            ref_parts.append(f"{web_title_str}.")
                        if web_source_name_str:
                            # Website name usually isn't italicized unless it's a formal publication name
                            ref_parts.append(f"Retrieved from {web_source_name_str}.")  # Indicate retrieval source

                        # Append URL and Access Date
                        ref_parts.append(f"Available at: {url}")
                        ref_parts.append(f"(Accessed: {access_date_str})")

                        # Join the parts. Use fallback if only counter and URL/Date exist.
                        if len(ref_parts) > 3:  # Check if more than just counter, URL, date exist
                            ref_entry = " ".join(ref_parts)
                        else:
                            # Fallback if minimal metadata was extracted
                            ref_entry = f"{citation_counter}. {web_title_str or 'Web Page'}. Available at: {url} (Accessed: {access_date_str})"
                            logger.warning(f"Using fallback reference for web source '{doc_id}' as minimal metadata was found.")

                    elif source_type == "internal":
                        # Internal/Synthesized Note Handling (Optional)
                        # Decide how to represent these if they are ever cited directly
                        ref_entry = f"{citation_counter}. Internal Synthesis ({doc_id}). Based on notes: {metadata.get('synthesized_from_notes', [])}"
                        logger.warning(f"Cited an internal note '{doc_id}'. Representation may need refinement.")

                    else:
                        # Fallback for unknown source types or missing specific metadata
                        logger.warning(f"Could not determine reference format for doc_id '{doc_id}' (Source Type: {source_type}). Using default.")
                        ref_entry = f"{citation_counter}. Unknown Source Type ({doc_id})"

                else:
                    # Fallback if no metadata note was found for the doc_id
                    logger.warning(f"Could not find any metadata source note for doc_id '{doc_id}' used in text.")
                    # Keep the default ref_entry = f"{citation_counter}. Unknown Source ({doc_id})"

                reference_entries[citation_counter] = ref_entry
                citation_counter += 1

        # Replacement function to handle single or multiple IDs within brackets
        def replace_placeholder(match):
            content_inside_brackets = match.group(1)
            # Extract individual IDs from the matched content
            individual_ids_in_match = id_pattern.findall(content_inside_brackets)

            # Process each ID, mapping note_ids to doc_ids if needed
            processed_ids = []
            for id_str in individual_ids_in_match:
                if id_str.startswith('note_'):
                    # Map note_id to doc_id
                    if id_str in note_id_to_doc_id_map:
                        processed_ids.append(note_id_to_doc_id_map[id_str])
                    else:
                        # Try to map it using the helper method
                        mapped_doc_id = self._map_note_id_to_doc_id(id_str, all_notes)
                        if mapped_doc_id:
                            processed_ids.append(mapped_doc_id)
                        else:
                            logger.warning(f"Could not map note ID '{id_str}' to a document ID during replacement")
                else:
                    # It's already a doc_id
                    processed_ids.append(id_str)

            # Look up numbers ONLY for VALID IDs found in this placeholder
            numbers = [str(doc_citation_map.get(doc_id)) for doc_id in processed_ids if doc_id in doc_citation_map]

            if numbers:
                # Sort the numbers numerically before joining
                sorted_numbers = sorted(numbers, key=int)
                # Format the replacement string, e.g., "[1, 2, 3]"
                return f"[{', '.join(sorted_numbers)}]"
            else:
                # This case now means the placeholder matched the pattern but contained ONLY invalid/unknown IDs
                logger.warning(f"Placeholder '{match.group(0)}' matched pattern but contained no known document IDs. Leaving unchanged.")
                return match.group(0)  # Leave it unchanged

        final_text_body = placeholder_pattern.sub(replace_placeholder, processed_text)

        num_references = len(reference_entries)
        references_section = ""
        if reference_entries:
            sorted_references = [reference_entries[i] for i in sorted(reference_entries.keys())]
            references_section = "\n\n## References\n\n" + "\n".join(sorted_references)

        # Prepend Report Title
        final_report_string = ""
        mission_context_for_title = self.controller.context_manager.get_mission_context(mission_id)  # Re-fetch context
        if mission_context_for_title and mission_context_for_title.metadata:
            report_title = mission_context_for_title.metadata.get("report_title")
            if report_title:
                final_report_string += f"# {report_title}\n\n"
                logger.info(f"Prepending report title: '{report_title}'")
            else:
                logger.warning(f"Report title not found in metadata for mission {mission_id}. Final report will not have a title.")
        else:
            logger.warning(f"Mission context or metadata not found when trying to prepend title for mission {mission_id}.")

        final_report_string += final_text_body.strip() + references_section

        self.controller.context_manager.store_final_report(mission_id, final_report_string.strip())
        self.controller.context_manager.update_mission_status(mission_id, "completed")
        logger.info(f"Citation processing complete. {num_references} unique references generated for mission {mission_id}.")
        self.controller.context_manager.log_execution_step(
            mission_id, "AgentController", "Process Citations",
            output_summary=f"Completed ({num_references} references generated).", status="success",
            full_input={'draft_length': len(full_draft), 'used_doc_ids': list(used_doc_ids)},
            full_output={'final_text': final_text_body.strip(), 'references': reference_entries},
            log_queue=log_queue, update_callback=update_callback
        )
        return True
