from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal
from datetime import datetime
import uuid

class Note(BaseModel):
    """
    Represents a single piece of information gathered during research,
    linked to its source and potential report sections.
    """
    note_id: str = Field(default_factory=lambda: f"note_{uuid.uuid4().hex[:8]}", description="Unique identifier for the note.")
    content: str = Field(..., description="The textual content of the note.")
    source_type: Literal["document", "web", "internal"] = Field(..., description="The origin type of the information (document chunk, web search result, agent thought).")
    source_id: str = Field(..., description="Identifier for the specific source (e.g., chunk_id, URL, agent_name).")
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about the source (e.g., title, year, original filename, snippet). Crucial for citation.")
    potential_sections: List[str] = Field(default_factory=list, description="List of section IDs from the current outline where this note might be relevant.")
    created_at: datetime = Field(default_factory=datetime.now, description="Timestamp of when the note was created.")
    updated_at: datetime = Field(default_factory=datetime.now, description="Timestamp of when the note was last updated.")
    is_relevant: bool = Field(default=True, description="Flag indicating if the note was deemed relevant during initial research.")

    class Config:
        # Example for potential future use if needed
        # schema_extra = {
        #     "example": {
        #         "note_id": "note_a1b2c3d4",
        #         "content": "Collaboration in palliative care improves patient outcomes by 20%.",
        #         "source_type": "document",
        #         "source_id": "doc_f0e1d2c3_chunk_5",
        #         "source_metadata": {
        #             "title": "Boosting Multi-Professional Collaboration in Palliative Care",
        #             "year": 2022,
        #             "original_filename": "Boosting_Multi-Professional_Collaboration_in_Palli.pdf",
        #             "chunk_text": "...",
        #             "page_number": 3
        #         },
        #         "potential_sections": ["introduction", "findings_collaboration"],
        #         "timestamp": "2024-05-15T10:30:00Z"
        #     }
        # }
        pass # Keep Config simple for now
