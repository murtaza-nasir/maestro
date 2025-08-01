from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

# Define the types of modifications the Reflection Agent can suggest
OutlineModificationType = Literal[
    "ADD_SECTION",
    "REMOVE_SECTION",
    "MERGE_SECTIONS",
    "REORDER_SECTIONS",
    "REFRAME_SECTION_TOPIC", # Change the focus/topic of an existing section
    "SPLIT_SECTION" # Split one section into multiple
]

class OutlineModification(BaseModel):
    """
    Represents a single proposed modification to the research outline.
    """
    modification_type: OutlineModificationType = Field(..., description="The type of change proposed.")
    details: Dict[str, Any] = Field(..., description="Specific parameters for the modification (e.g., section IDs, new titles, topics, target order).")
    reasoning: str = Field(..., description="Explanation from the agent on why this modification is suggested.")

    class Config:
        schema_extra = {
            "examples": [
                {
                    "modification_type": "ADD_SECTION",
                    "details": {"new_title": "Ethical Considerations", "topic": "Discuss potential ethical issues arising from the findings.", "after_section_id": "sec_discussion"},
                    "reasoning": "Emerging theme in notes suggests ethical implications need dedicated discussion."
                },
                {
                    "modification_type": "REMOVE_SECTION",
                    "details": {"section_id_to_remove": "sec_background_history"},
                    "reasoning": "Notes indicate minimal relevant information found, and topic overlaps heavily with Introduction."
                },
                 {
                    "modification_type": "REFRAME_SECTION_TOPIC",
                    "details": {"section_id": "sec_results_a", "new_topic": "Focus specifically on quantitative results for metric X.", "new_title": "Quantitative Analysis of Metric X"},
                    "reasoning": "Initial topic was too broad; notes primarily support analysis of metric X."
                }
            ]
        }

class SuggestedSubsectionTopic(BaseModel):
    """Represents a suggested topic for a potential new subsection based on analyzed notes."""
    # subsection_id is removed - will be assigned later if approved
    title: str = Field(..., description="A concise title for the suggested subsection topic.")
    description: str = Field(..., description="A brief description of the specific topic this potential subsection should cover.")
    relevant_note_ids: List[str] = Field(default_factory=list, description="IDs of existing notes that are highly relevant to this suggested topic.")
    reasoning: str = Field(..., description="Why this topic is being suggested as a potential subsection (e.g., 'Notes cover distinct subtopic X').")

class ReflectionOutput(BaseModel):
    """
    Represents the output of the ReflectionAgent's analysis based on detailed notes.
    Focuses on iterative refinement within or across sections.
    """
    overall_assessment: str = Field(..., description="A high-level summary of the analysis of the provided notes, focusing on relevance, completeness, coherence, and potential issues within the scope of the current section(s).")
    # proceed_as_planned: bool = Field(..., description="True if the agent recommends continuing without major structural changes, False otherwise.") # Less relevant for iterative refinement?
    new_questions: List[str] = Field(default_factory=list, description="Specific questions generated based on gaps, contradictions, or areas needing deeper exploration in the analyzed notes. These guide the next research iteration for the *current* section.")
    suggested_subsection_topics: List[SuggestedSubsectionTopic] = Field(default_factory=list, description="Suggestions for potential new subsection topics based on diverse themes found in the notes. These are *suggestions* and will be reviewed/approved later.")
    # Keep outline modifications for potential broader changes, though subsection proposal might overlap
    proposed_modifications: List[OutlineModification] = Field(default_factory=list, description="A list of specific changes suggested for the overall research outline structure (e.g., adding/removing top-level sections). These might be deferred or handled differently in a multi-pass system.")
    sections_needing_review: List[str] = Field(default_factory=list, description="List of existing section IDs (can include the current one) that require a *full* re-research cycle due to major issues identified.")
    critical_issues_summary: Optional[str] = Field(None, description="A summary of any critical contradictions, major gaps, or significant deviations identified *within the analyzed notes*.")
    # --- Added fields for discarding notes ---
    discard_note_ids: List[str] = Field(default_factory=list, description="IDs of notes deemed redundant or irrelevant and should be discarded.")
    # --- End added fields ---
    # --- Added field for thought_pad ---
    generated_thought: Optional[str] = Field(None, description="A concise thought or reminder generated by the agent to be added to the thought_pad.")
    # --- End added field ---

    class Config:
        schema_extra = {
            "example": {
                "overall_assessment": "Notes for section 'sec_compass_method' cover the core algorithm but lack detail on parameter tuning and comparison setup mentioned in the goal. Note N5 contradicts N2 regarding data preprocessing.",
                "new_questions": [
                    "What are the recommended parameter ranges for the COMPASS algorithm based on the original paper?",
                    "How was the dataset preprocessed before applying COMPASS in source X?",
                    "Clarify the discrepancy in preprocessing steps between Note N5 and Note N2."
                ],
                "suggested_subsection_topics": [ # Updated field name and structure
                    {
                        # No subsection_id here
                        "title": "Parameter Tuning",
                        "description": "Focus on the selection and impact of different parameters for the COMPASS method.",
                        "relevant_note_ids": ["N7", "N8"],
                        "reasoning": "Sufficient notes exist on parameters to warrant suggesting this as a potential subsection."
                    }
                ],
                "proposed_modifications": [], # No changes to overall outline structure proposed this cycle
                "sections_needing_review": [], # Current section needs more detail via new_questions, not a full re-run yet
                "critical_issues_summary": "Contradiction identified in data preprocessing steps between notes N5 and N2.",
                "discard_note_ids": ["N10", "N15"], # Example: Suggest discarding these notes
                "generated_thought": "Parameter tuning for COMPASS algorithm needs deeper investigation; contradictory preprocessing methods identified."
            }
        }
