# ai_researcher/agentic_layer/schemas/analysis.py
# Removed Literal and Optional imports
from pydantic import BaseModel, Field

# Removed Literal definitions for RequestType, TargetTone, TargetAudience

class RequestAnalysisOutput(BaseModel):
    """Defines the structure for the initial analysis of the user's request."""
    request_type: str = Field(..., description="The primary type of the user's request (e.g., 'Academic Literature Review', 'Informal Explanation', or a custom description).")
    target_tone: str = Field(..., description="The implied or appropriate tone for the final output (e.g., 'Formal Academic', '5th Grader', or a custom description). Prioritizes user goals.")
    target_audience: str = Field(..., description="The likely intended audience for the research output (e.g., 'Researchers/Experts', 'General Public', or a custom description). Prioritizes user goals.")
    requested_length: str = Field(..., description="The requested or appropriate length for the output (e.g., 'Short Summary', 'Comprehensive Report', 'Brief Paragraph', or a custom description). Prioritizes user goals.")
    requested_format: str = Field(..., description="The requested or appropriate format for the output (e.g., 'Full Paper', 'Bullet Points', 'Summary Paragraph', 'Q&A Format', or a custom description). Prioritizes user goals.")
    preferred_source_types: str = Field(..., description="The preferred types of sources to use for research (e.g., 'Academic Literature', 'Legal Sources', 'State Law', 'News Articles'). Prioritizes user goals. Use empty string if no preference specified.")
    analysis_reasoning: str = Field(..., description="Brief reasoning for the classifications.")

    class Config:
        # Example configuration if needed
        pass
