from pydantic import BaseModel, Field
from typing import Dict

from ai_researcher.agentic_layer.agents.note_assignment_agent import AssignedNotes

class FullNoteAssignments(BaseModel):
    """
    Represents a collection of note assignments for all sections in a report.
    Maps section IDs to their assigned notes.
    """
    assignments: Dict[str, AssignedNotes] = Field(
        default_factory=dict, 
        description="Mapping of section IDs to their assigned notes."
    )
