from pydantic import BaseModel, Field, ConfigDict # Import ConfigDict
from typing import List, Optional, Dict, Any, Literal, ClassVar

# Define possible action types for plan steps
ActionType = Literal[
    "document_search", # Use the document search tool
    "web_search",      # Use the web search tool
    "calculate",       # Use the calculator tool
    "execute_python",  # Use the python execution tool
    "synthesize",      # Synthesize information from previous steps
    "write_section",   # Write a specific report section
    "final_report",    # Compile the final report (usually the last step)
    "ask_user"         # Ask the user for clarification (if MessengerAgent is used)
]

# NEW: Define research strategies
ResearchStrategy = Literal[
    "research_based",           # Standard research process (search, reflect, etc.)
    "content_based",            # Write based on other sections' content (e.g., intro, conclusion)
    "synthesize_from_subsections" # Synthesize intro from completed subsection research
]

class ReportSection(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": [
            "section_id",
            "title",
            "description",
            "depends_on_steps",
            "associated_note_ids",
            "subsections",
            "research_strategy"
        ]
    })  # Enforce additionalProperties: false and required fields in schema
    """Defines a section in the final report outline."""
    section_id: str = Field(..., description="Unique identifier for the section (e.g., 'introduction', 'lit_review', 'methodology_results', 'conclusion').")
    title: str = Field(..., description="Human-readable title for the report section.")
    description: str = Field(..., description="Brief description of what this section should cover.")
    depends_on_steps: List[str] = Field(default_factory=list, description="List of step_ids whose results are needed to write this section.")
    associated_note_ids: Optional[List[str]] = Field(default=None, description="List of note IDs from the exploratory phase relevant to this section.") # Added field
    subsections: List['ReportSection'] = Field(default_factory=list, description="List of subsections nested under this section.")
    # --- NEW FIELDS ---
    research_strategy: ResearchStrategy = Field(
        default="research_based",
        description="Defines how the research/writing for this section should be approached."
    )
    # is_section_intro field removed as it's redundant with research_strategy='synthesize_from_subsections'
    # --- END NEW FIELDS ---

# Update forward references to allow for recursive subsections
ReportSection.model_rebuild()

class StepParameters(BaseModel):
    """Parameters for different step types."""
    query: Optional[str] = Field(None, description="Search query for document_search or web_search")
    n_results: Optional[int] = Field(None, description="Number of results for search")
    expression: Optional[str] = Field(None, description="Expression to calculate")
    code: Optional[str] = Field(None, description="Python code to execute")
    section_id: Optional[str] = Field(None, description="Section ID for write_section")
    max_results: Optional[int] = Field(None, description="Maximum results for web search")
    filepath: Optional[str] = Field(None, description="File path for read_full_document")
    url: Optional[str] = Field(None, description="URL for fetch_web_page_content")
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": [
            "query",
            "n_results", 
            "expression",
            "code",
            "section_id",
            "max_results",
            "filepath",
            "url"
        ]
    })

class PlanStep(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')  # Enforce additionalProperties: false in schema
    """Defines a single step in the research plan."""
    step_id: str = Field(..., description="Unique identifier for this step (e.g., 'step_1', 'step_2a').")
    action_type: ActionType = Field(..., description="The type of action to perform for this step.")
    description: str = Field(..., description="Detailed description of what needs to be done in this step.")
    parameters: StepParameters = Field(default_factory=StepParameters)  # Remove description to avoid $ref conflict
    depends_on: List[str] = Field(default_factory=list, description="List of step_ids that must be completed before this step can start.")
    produces: Optional[str] = Field(None, description="Optional description of the expected output or artifact from this step (e.g., 'list of relevant paper snippets', 'calculated value', 'synthesized findings on topic X').")

class SimplifiedPlan(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')  # Enforce additionalProperties: false in schema
    """Represents the structured research plan and report outline."""
    mission_goal: str = Field(..., description="The overall goal or research question.")
    report_outline: List[ReportSection] = Field(..., description="The planned structure of the final report.")

# Removed SimplifiedPlan model as its fields are now directly in SimplifiedPlanResponse

class SimplifiedPlanResponse(BaseModel):
    """
    The expected JSON structure returned by the Planning Agent LLM call.
    Represents the structured research plan and report outline directly.
    """
    # Add model_config to enforce no extra fields during Pydantic validation
    # AND ensure 'additionalProperties: false' is included in the generated schema.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": [
            "mission_goal",
            "report_outline",
            "parsing_error",
            "generated_thought"
        ]
    })

    mission_goal: str = Field(..., description="The overall goal or research question.")
    report_outline: List[ReportSection] = Field(..., description="The planned structure of the final report.")
    parsing_error: Optional[str] = Field(None, description="Field to indicate if there was an error parsing the LLM response into the schema.")
    generated_thought: Optional[str] = Field(None, description="A concise thought or reminder generated by the agent to be added to the thought_pad.")
