import logging
from typing import List, Optional, Tuple
from collections import deque

# Import ReportSection from the planning schema
from ai_researcher.agentic_layer.schemas.planning import ReportSection

logger = logging.getLogger(__name__)

def find_section_recursive(section_list: List[ReportSection], section_id: str) -> Optional[ReportSection]:
    """Recursively searches for a section by its ID within a list of sections."""
    for section in section_list:
        if section.section_id == section_id:
            return section
        if section.subsections:
            found = find_section_recursive(section.subsections, section_id)
            if found:
                return found
    return None

def format_outline_for_prompt(outline: List[ReportSection]) -> List[str]:
    """Recursively formats the report outline into an indented list of strings for prompts."""
    formatted_lines = []

    def _format_section(section: ReportSection, indent_level: int):
        indent = "  " * indent_level
        formatted_lines.append(f"{indent}- {section.title} (ID: {section.section_id})")
        if section.description:
            formatted_lines.append(f"{indent}  Description: {section.description}")
        if section.associated_note_ids:
            formatted_lines.append(f"{indent}  Notes: {', '.join(section.associated_note_ids)}")
        # Recursively format subsections
        for subsection in section.subsections:
            _format_section(subsection, indent_level + 1)

    for top_level_section in outline:
        _format_section(top_level_section, 0)

    return formatted_lines

def get_sections_in_order(outline: List[ReportSection]) -> List[ReportSection]:
    """Flattens the outline into a depth-first ordered list of sections."""
    ordered_sections = []
    def _traverse(sections: List[ReportSection]):
        for section in sections:
            ordered_sections.append(section)
            if section.subsections:
                _traverse(section.subsections)
    _traverse(outline)
    return ordered_sections

def is_descendant(section_list: List[ReportSection], parent_id: str, child_id: str) -> bool:
    """Checks if child_id is a descendant of parent_id in the outline."""
    for section in section_list:
        if section.section_id == parent_id:
            # Check direct subsections and their descendants
            queue = deque(section.subsections)
            while queue:
                current = queue.popleft()
                if current.section_id == child_id:
                    return True
                queue.extend(current.subsections)
            return False # Not found under this parent
        # Check recursively in subsections if current section is not the parent
        if section.subsections and is_descendant(section.subsections, parent_id, child_id):
             return True # Found in a deeper branch
    return False

def find_parent_and_section(
    section_list: List[ReportSection], section_id: str
) -> Tuple[Optional[List[ReportSection]], Optional[ReportSection]]:
    """
    Recursively searches for a section by ID and returns the list it belongs to
    and the section object itself. Returns (None, None) if not found.
    """
    for i, section in enumerate(section_list):
        if section.section_id == section_id:
            return section_list, section
        if section.subsections:
            parent_list, found_section = find_parent_and_section(section.subsections, section_id)
            if found_section:
                return parent_list, found_section
    return None, None
