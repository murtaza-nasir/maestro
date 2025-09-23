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
            "subsections",
            "research_strategy"
        ]
    })  # Enforce additionalProperties: false and required fields in schema
    """Defines a section in the final report outline."""
    section_id: str = Field(..., description="Unique identifier for the section (e.g., 'introduction', 'lit_review', 'methodology_results', 'conclusion').")
    title: str = Field(..., description="Human-readable title for the report section.")
    description: str = Field(..., description="Detailed description of what this section should cover, including specific subtopics and questions to address.")
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

# Simplified schemas for each planning phase
class SimplifiedSection(BaseModel):
    """Simplified section for initial outline generation (Phase 1) and revision (Phase 3)."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": [
            "title",
            "description",
            "research_strategy",
            "subsections"
        ]
    })
    section_id: Optional[str] = Field(None, description="Unique identifier for the section (e.g., 'introduction', 'section_1').")
    title: str = Field(..., description="Human-readable title for the report section.")
    description: str = Field(..., description="Detailed description of what this section should cover, including specific subtopics and questions to address.")
    research_strategy: ResearchStrategy = Field(
        default="research_based",
        description="Defines how the research/writing for this section should be approached: 'research_based' for sections needing research, 'content_based' for intro/conclusion, 'synthesize_from_subsections' for parent sections."
    )
    associated_note_ids: Optional[List[str]] = Field(None, description="List of note IDs associated with this section (for Phase 3 revision).")
    subsections: List['SimplifiedSection'] = Field(default_factory=list, description="List of subsections nested under this section (max depth of 2).")

# Update forward references
SimplifiedSection.model_rebuild()

class SectionWithNotes(BaseModel):
    """Section with note assignments for Phase 2."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid', json_schema_extra={
        "required": [
            "title",
            "description", 
            "research_strategy",
            "associated_note_ids",
            "subsections"
        ]
    })
    title: str = Field(..., description="Human-readable title for the report section.")
    description: str = Field(..., description="Detailed description of what this section should cover.")
    research_strategy: ResearchStrategy = Field(..., description="Research strategy for this section.")
    associated_note_ids: List[str] = Field(default_factory=list, description="List of note IDs from research that are relevant to this section.")
    subsections: List['SectionWithNotes'] = Field(default_factory=list, description="List of subsections.")

# Update forward references
SectionWithNotes.model_rebuild()

# Response schemas for each phase
class Phase1PlanResponse(BaseModel):
    """Response for Phase 1: Initial Outline Generation."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
    mission_goal: str = Field(..., description="The overall research goal restated clearly.")
    generated_thought: str = Field(..., description="Your analytical thought about the research task and your planning approach.")
    report_outline: List[SimplifiedSection] = Field(..., description="The planned structure of the report.")

class Phase2PlanResponse(BaseModel):
    """Response for Phase 2: Outline with Note Assignment."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
    mission_goal: str = Field(..., description="The overall research goal.")
    generated_thought: str = Field(..., description="Your thought about how the notes map to the outline.")
    report_outline: List[SectionWithNotes] = Field(..., description="The outline with notes assigned to sections.")

class Phase3PlanResponse(BaseModel):
    """Response for Phase 3: Outline Revision."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
    mission_goal: str = Field(..., description="The overall research goal.")
    generated_thought: str = Field(..., description="Your thought about the revisions made.")
    report_outline: List[SimplifiedSection] = Field(..., description="The revised outline structure.")

class Phase3aStructuralResponse(BaseModel):
    """Response for Phase 3a: Structural Modifications Only."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
    mission_goal: str = Field(..., description="The overall research goal.")
    generated_thought: str = Field(..., description="Summary of structural changes applied.")
    report_outline: List[SimplifiedSection] = Field(..., description="The structurally modified outline.")
    modifications_applied: List[str] = Field(default_factory=list, description="List of modification types that were successfully applied.")

class Phase3bSubsectionResponse(BaseModel):
    """Response for Phase 3b: Subsection Addition with Notes."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
    mission_goal: str = Field(..., description="The overall research goal.")
    generated_thought: str = Field(..., description="Summary of subsections added and notes assigned.")
    report_outline: List[SectionWithNotes] = Field(..., description="The outline with new subsections and note assignments.")

class Phase3cNoteRedistributionResponse(BaseModel):
    """Response for Phase 3c: Final Note Redistribution."""
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')
    mission_goal: str = Field(..., description="The overall research goal.")
    generated_thought: str = Field(..., description="Summary of note redistribution.")
    report_outline: List[SectionWithNotes] = Field(..., description="The outline with finalized note assignments.")

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
    
    model_config: ClassVar[ConfigDict] = ConfigDict(extra='forbid')

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
