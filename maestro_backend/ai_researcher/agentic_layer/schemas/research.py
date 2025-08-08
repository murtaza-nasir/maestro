from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal, ClassVar

class Source(BaseModel):
    """Represents a source document or chunk used for a finding."""
    doc_id: str = Field(..., description="The unique identifier of the source document.")
    chunk_id: Optional[str] = Field(None, description="The specific chunk ID within the document, if applicable.")
    text_preview: Optional[str] = Field(None, description="A short preview of the relevant text from the source.")
    # Add other relevant source metadata like original filename, title, authors if available and needed
    original_filename: Optional[str] = Field(None)
    title: Optional[str] = Field(None)
    score: Optional[float] = Field(None, description="Relevance score from retrieval/reranking, if applicable.")
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

class Finding(BaseModel):
    """Represents a single synthesized finding or piece of information."""
    finding_id: str = Field(..., description="Unique ID for this finding within the synthesis.")
    content: str = Field(..., description="The synthesized piece of information or answer.")
    sources: List[Source] = Field(default_factory=list, description="List of sources supporting this finding.")
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

class ResearchFindings(BaseModel):
    """Structured output for synthesis steps."""
    summary: str = Field(..., description="A concise summary of the key findings related to the synthesis goal.")
    detailed_findings: List[Finding] = Field(default_factory=list, description="A list of specific, sourced findings.")
    # Optional: Add fields for unanswered questions or areas needing more research
    unanswered_questions: Optional[List[str]] = Field(None)
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

class ResearchResultResponse(BaseModel):
    """
    Standard response structure for research steps (tool execution or synthesis).
    Can hold either direct tool output or structured ResearchFindings.
    """
    step_id: str = Field(..., description="The ID of the plan step this result corresponds to.")
    action_type: str = Field(..., description="The action type performed (e.g., 'document_search', 'synthesize').")
    status: Literal["success", "failure"] = Field(...)
    result: Optional[Any] = Field(None, description="The direct output from a tool (e.g., list from search, number from calc) or ResearchFindings object for synthesis.")
    error_message: Optional[str] = Field(None, description="Error message if status is 'failure'.")
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
