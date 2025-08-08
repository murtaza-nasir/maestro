from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Literal, ClassVar, Optional
from datetime import datetime
import uuid

class SourceMetadata(BaseModel):
    """Metadata about the source of a note."""
    title: Optional[str] = Field(None, description="Title of the source document")
    year: Optional[str] = Field(None, description="Publication year")
    original_filename: Optional[str] = Field(None, description="Original filename")
    snippet: Optional[str] = Field(None, description="Text snippet from source")
    authors: Optional[str] = Field(None, description="Authors of the source")
    url: Optional[str] = Field(None, description="URL if web source")
    
    # Additional fields found in existing data
    beginning_omitted: Optional[bool] = Field(None, description="Whether content was omitted from beginning")
    end_omitted: Optional[bool] = Field(None, description="Whether content was omitted from end")
    original_chunk_ids: Optional[List[str]] = Field(None, description="List of original chunk IDs")
    window_position: Optional[Dict[str, int]] = Field(None, description="Window position with start and end")
    overlapping_chunks: Optional[List[Dict[str, Any]]] = Field(None, description="Information about overlapping chunks")
    fetched_full_content: Optional[bool] = Field(None, description="Whether full content was fetched")
    keywords: Optional[str] = Field(None, description="Keywords from the source")
    abstract: Optional[str] = Field(None, description="Abstract from the source")
    publication_year: Optional[int] = Field(None, description="Publication year as integer")
    doc_id: Optional[str] = Field(None, description="Document ID")
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='allow')  # Allow extra fields for backward compatibility with existing data

class Note(BaseModel):
    """
    Represents a single piece of information gathered during research,
    linked to its source and potential report sections.
    """
    note_id: str = Field(default_factory=lambda: f"note_{uuid.uuid4().hex[:8]}", description="Unique identifier for the note.")
    content: str = Field(..., description="The textual content of the note.")
    source_type: Literal["document", "web", "internal"] = Field(..., description="The origin type of the information (document chunk, web search result, agent thought).")
    source_id: str = Field(..., description="Identifier for the specific source (e.g., chunk_id, URL, agent_name).")
    source_metadata: SourceMetadata = Field(default_factory=SourceMetadata)  # Remove description to avoid $ref conflict
    potential_sections: List[str] = Field(default_factory=list, description="List of section IDs from the current outline where this note might be relevant.")
    created_at: datetime = Field(default_factory=datetime.now, description="Timestamp of when the note was created.")
    updated_at: datetime = Field(default_factory=datetime.now, description="Timestamp of when the note was last updated.")
    is_relevant: bool = Field(default=True, description="Flag indicating if the note was deemed relevant during initial research.")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')  # Prevent additionalProperties and replace legacy Config
    # Removed old Pydantic v1 Config to avoid conflict with model_config
    # class Config:
    #     pass
