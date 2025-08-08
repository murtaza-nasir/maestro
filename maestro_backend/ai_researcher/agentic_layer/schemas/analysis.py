# ai_researcher/agentic_layer/schemas/analysis.py
# Removed Literal and Optional imports
from pydantic import BaseModel, Field, ConfigDict
from typing import ClassVar

# Removed Literal definitions for RequestType, TargetTone, TargetAudience

class RequestAnalysisOutput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": [
            "request_type",
            "target_tone",
            "target_audience",
            "requested_length",
            "requested_format",
            "preferred_source_types",
            "analysis_reasoning"
        ]
    })  # Ensure additionalProperties: false and explicit required keys in the schema
    """Defines the structure for the initial analysis of the user's request."""
    request_type: str = Field(..., description="The primary type of the user's request (e.g., 'Academic Literature Review', 'Informal Explanation', or a custom description).")
    target_tone: str = Field(..., description="The implied or appropriate tone for the final output (e.g., 'Formal Academic', '5th Grader', or a custom description). Prioritizes user goals.")
    target_audience: str = Field(..., description="The likely intended audience for the research output (e.g., 'Researchers/Experts', 'General Public', or a custom description). Prioritizes user goals.")
    requested_length: str = Field(..., description="The requested or appropriate length for the output (e.g., 'Short Summary', 'Comprehensive Report', 'Brief Paragraph', or a custom description). Prioritizes user goals.")
    requested_format: str = Field(..., description="The requested or appropriate format for the output (e.g., 'Full Paper', 'Bullet Points', 'Summary Paragraph', 'Q&A Format', or a custom description). Prioritizes user goals.")
    preferred_source_types: str = Field(..., description="The preferred types of sources to use for research (e.g., 'Academic Literature', 'Legal Sources', 'State Law', 'News Articles'). Prioritizes user goals. Use empty string if no preference specified.")
    analysis_reasoning: str = Field(..., description="Brief reasoning for the classifications.")

    # Removed old Pydantic v1 Config to avoid conflict with model_config
    # class Config:
    #     # Example configuration if needed
    #     pass
