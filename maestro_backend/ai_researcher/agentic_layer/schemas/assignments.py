from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, ClassVar

from ai_researcher.agentic_layer.agents.note_assignment_agent import AssignedNotes

class FullNoteAssignments(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": ["assignments"]
    })  # Ensure additionalProperties: false and explicit required key in schema
    """
    Represents a collection of note assignments for all sections in a report.
    Maps section IDs to their assigned notes.
    """
    assignments: Dict[str, AssignedNotes] = Field(
        default_factory=dict, 
        description="Mapping of section IDs to their assigned notes."
    )
