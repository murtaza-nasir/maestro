import json
import os
import re
from typing import Optional, List, Dict, Any, Tuple
from pydantic import ValidationError

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    prepare_for_pydantic_validation
)
from ai_researcher.agentic_layer.utils.json_format_helper import (
    get_json_schema_format,
    get_json_object_format,
    enhance_messages_for_json_object,
    should_retry_with_json_object
)
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Import ThoughtEntry

# Use absolute imports starting from the top-level package 'ai_researcher'
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
# Note: MODEL_MAPPING was removed from model_dispatcher, we should get it from config now
from ai_researcher import config # Import config to get model mapping
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlanResponse, SimplifiedPlan, ReportSection # Import the schemas
from ai_researcher.agentic_layer.schemas.goal import GoalEntry # Import GoalEntry
import logging # <-- Add logging

logger = logging.getLogger(__name__) # <-- Add logger

# Enable debug mode via environment variable
DEBUG_PLANNING = os.getenv('DEBUG_PLANNING', 'false').lower() == 'true'

class PlanningAgent(BaseAgent):
    """
    Agent responsible for creating a step-by-step research plan based on the user request
    and available tools.
    """
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        tool_registry: ToolRegistry, # Planning agent needs tool descriptions
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        controller: Optional[Any] = None # Add controller parameter
    ):
        agent_name = "PlanningAgent"
        # Determine the correct model name based on the 'planning' role from config
        planning_model_type = config.AGENT_ROLE_MODEL_TYPE.get("planning", "fast") # Default to fast if not specified
        if planning_model_type == "fast":
            provider = config.FAST_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["fast_model"]
        elif planning_model_type == "mid": # Explicitly check for mid
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]
        elif planning_model_type == "intelligent": # Add check for intelligent
            provider = config.INTELLIGENT_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["intelligent_model"]
        else: # Fallback if type is unknown (shouldn't happen with current config)
            logger.warning(f"Unknown planning model type '{planning_model_type}', falling back to mid.")
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]

        # Override with specific model_name if provided by the user during instantiation
        # This allows overriding the config-based selection if needed for specific instances
        effective_model_name = model_name or effective_model_name

        # Call super().__init__ first to set self.tool_registry etc.
        super().__init__(
            agent_name=agent_name,
            model_dispatcher=model_dispatcher,
            tool_registry=tool_registry, # Pass it to BaseAgent
            system_prompt="Placeholder", # Use a placeholder first
            model_name=effective_model_name
        )
        self.controller = controller # Store controller
        self.mission_id = None # Initialize mission_id as None
        # Now that self.tool_registry exists, set the actual system prompt
        self.system_prompt = system_prompt or self._default_system_prompt()
        # Update the print statement if needed, though BaseAgent already prints
        # print(f"Initialized {self.agent_name} (Model: {self.model_name or 'Default'}) with system prompt.")
        logger.info(f"{self.agent_name} initialized (Model: {self.model_name or 'Default'})")
        
        if DEBUG_PLANNING:
            logger.info("🔍 PLANNING AGENT DEBUG MODE ENABLED - Verbose logging active")
            logger.info("   To disable, set environment variable: DEBUG_PLANNING=false")

    def _phase1_system_prompt(self) -> str:
        """Phase 1: Initial Outline Generation - Simple, focused prompt."""
        # Get max depth from controller if available, otherwise use dynamic config
        if hasattr(self, 'controller') and self.controller:
            max_depth = self.controller.max_total_depth
        else:
            # Fallback to dynamic config if controller not available
            from ai_researcher.dynamic_config import get_max_total_depth
            mission_id = getattr(self, 'mission_id', None)
            max_depth = get_max_total_depth(mission_id)
        
        # Convert depth to human-readable format
        depth_description = "sections only (flat structure)" if max_depth == 1 else f"sections and subsections only (max {max_depth} levels)"
        
        prompt = f"""You are an expert research planner. Your task is to create a clear, logical outline for a research report.

**Your Task:**
Create a structured outline that will guide the research and writing process. Focus on:
1. Breaking down the research question into logical sections
2. Ensuring each section has a clear purpose and detailed description
3. Determining the appropriate research strategy for each section
4. AVOIDING DUPLICATION - ensure each topic is covered in exactly one place

**Critical Rules to Prevent Duplication:**
- Each topic/concept should appear in ONLY ONE section
- Avoid creating sections with similar or overlapping titles
- Do not repeat the same content areas in different sections
- If a topic could fit in multiple places, choose the most logical single location
- Subsections should be distinct and non-overlapping within their parent section

**Research Strategy Guidelines (CRITICAL - READ CAREFULLY):**
For each section, you MUST choose the appropriate strategy based on these STRICT rules:

1. **`research_based`** (MOST COMMON - DEFAULT FOR LEAF SECTIONS):
   - Use for ALL sections WITHOUT subsections (leaf sections) EXCEPT intro/conclusion
   - Use for sections that need to gather and analyze information
   - Examples: "Methodology", "Results", "Analysis", "Case Studies", "Technical Details"
   - AT LEAST ONE SECTION MUST BE research_based or the outline will fail!

2. **`content_based`** (ONLY for intro/conclusion):
   - Use ONLY for Introduction (first section) and Conclusion (last section)
   - Use for sections with titles like: "Introduction", "Conclusion", "Summary", "Final Thoughts"
   - These sections synthesize content from other sections

3. **`synthesize_from_subsections`** (ONLY for parent sections):
   - Use ONLY when a section HAS subsections
   - The parent section summarizes its subsections
   - Never use for leaf sections (sections without subsections)

**Outline Structure Rules:**
- Create 3-8 top-level sections based on the research complexity
- Each section can have up to 4 subsections (optional)
- STRICT MAXIMUM DEPTH: {max_depth} {"level" if max_depth == 1 else "levels"} ({depth_description})
- Each section MUST have a detailed description explaining what it will cover
- Ensure no duplicate or highly similar sections exist at any level

**Output Format:**
Generate a JSON object with:
- `mission_goal`: Clear restatement of the research objective
- `generated_thought`: Your analysis of the research task and planning approach
- `report_outline`: Array of sections with title, description, research_strategy, and optional subsections

Remember: Keep it focused, logical, and actionable. Do NOT include section IDs - those will be added programmatically. The outline will be automatically validated for depth and duplication."""
        return prompt

    def _phase2_system_prompt(self) -> str:
        """Phase 2: Outline with Note Assignment - Assigns collected notes to sections."""
        prompt = """You are an expert research planner. Your task is to assign research notes to the appropriate sections of an outline AND ensure correct research strategies.

**Your Task:**
1. Assign collected notes to relevant sections
2. Set appropriate research strategies for each section

**Research Strategy Rules (CRITICAL):**
You MUST assign the correct `research_strategy` to each section based on these rules:

1. **`content_based`** - Use ONLY for:
   - Introduction sections (typically first section)
   - Conclusion/Summary sections (typically last section)
   - Sections with titles containing: "Introduction", "Conclusion", "Summary", "Discussion", "Final Thoughts"
   - These sections synthesize content from other sections, no dedicated research

2. **`synthesize_from_subsections`** - Use ONLY for:
   - Parent sections that HAVE subsections
   - These sections summarize their subsections' content
   - They don't conduct their own research

3. **`research_based`** - Use for:
   - ALL leaf sections (sections WITHOUT subsections) that aren't intro/conclusion
   - Core content sections that need data gathering
   - Sections about specific topics, methods, results, analysis
   - DEFAULT for most middle sections

**CRITICAL REQUIREMENT:** At least ONE section MUST be `research_based` or the outline will be rejected!

**Note Assignment Guidelines:**
- Match notes to sections based on content relevance
- A note can be assigned to multiple relevant sections
- Distribute notes logically to avoid redundancy

**Output Format:**
Generate a JSON object with:
- `mission_goal`: The research objective
- `generated_thought`: Your analysis of note distribution and strategy assignment
- `report_outline`: Array of sections with:
  - `title`: Section title
  - `description`: What the section covers
  - `research_strategy`: One of: "research_based", "content_based", or "synthesize_from_subsections"
  - `associated_note_ids`: List of relevant note IDs for this section
  - `subsections`: Optional array of subsections (same structure)

**Example Structure:**
```json
{
  "report_outline": [
    {
      "title": "Introduction",
      "research_strategy": "content_based",  // Intro is always content_based
      "associated_note_ids": []
    },
    {
      "title": "Literature Review",
      "research_strategy": "synthesize_from_subsections",  // Has subsections
      "subsections": [
        {
          "title": "Historical Context",
          "research_strategy": "research_based",  // Leaf section = research_based
          "associated_note_ids": ["note_123", "note_456"]
        }
      ]
    },
    {
      "title": "Methodology",
      "research_strategy": "research_based",  // No subsections = research_based
      "associated_note_ids": ["note_789"]
    },
    {
      "title": "Conclusion",
      "research_strategy": "content_based",  // Conclusion is always content_based
      "associated_note_ids": []
    }
  ]
}
```"""
        return prompt

    def _phase3_system_prompt(self) -> str:
        """Phase 3: Outline Revision - Refines existing outline based on feedback."""
        prompt = """You are an expert research planner. Your task is to revise an existing outline based on suggestions and feedback.

**Your Task:**
Refine the outline by:
1. Incorporating suggested improvements
2. Adding, removing, or merging sections as needed
3. Improving section descriptions for clarity
4. Ensuring logical flow and coverage

**Revision Guidelines:**
- Focus on refinement, not complete restructuring
- Maintain the same depth constraints (max 2 levels)
- Keep the number of sections reasonable (3-8 top-level)
- Preserve what works well in the current outline
- Do NOT add "References", "Bibliography", or "Citations" sections (these are auto-generated)

**Output Format:**
Generate a JSON object with:
- `mission_goal`: The research objective
- `generated_thought`: Your analysis of the revisions made
- `report_outline`: An array of section objects, where each section must have:
  - `section_id`: Unique identifier (e.g., "introduction", "section_1")
  - `title`: Section title
  - `description`: Detailed description of what the section covers
  - `research_strategy`: One of "content_based", "research_based", or "synthesize_from_subsections"
  - `subsections`: (optional) Array of subsection objects with the same structure
  - `associated_note_ids`: (optional) Array of note IDs, can be empty []

Example format:
```json
{
  "mission_goal": "Research goal here",
  "generated_thought": "Analysis of revisions",
  "report_outline": [
    {
      "section_id": "introduction",
      "title": "Introduction",
      "description": "Overview of the research topic",
      "research_strategy": "content_based",
      "associated_note_ids": []
    }
  ]
}
```"""
        return prompt
    
    def _phase3a_structural_prompt(self) -> str:
        """Phase 3a: Structural Modifications Only - Apply structural changes to outline."""
        prompt = """You are an expert research planner. Your task is to apply structural modifications to an existing outline.

**Your Task:**
Apply ONLY structural changes such as:
- ADD_SECTION: Add new top-level sections
- REMOVE_SECTION: Remove existing sections
- MERGE_SECTIONS: Combine related sections
- REFRAME_SECTION_TOPIC: Change the focus/topic of sections
- REORDER_SECTIONS: Change the order of sections

**Important Rules:**
- Apply only the structural modifications provided
- Do NOT add subsections in this phase
- Maintain logical flow and coherence
- Keep descriptions detailed and clear

**Output Format:**
Generate a JSON object with:
- `mission_goal`: The research objective
- `generated_thought`: Summary of structural changes applied
- `report_outline`: The structurally modified outline
- `modifications_applied`: List of modification types that were successfully applied"""
        return prompt
    
    def _phase3b_subsection_prompt(self) -> str:
        """Phase 3b: Add Subsections with Notes - Add subsections and assign their relevant notes."""
        prompt = """You are an expert research planner. Your task is to add suggested subsections to an outline and assign relevant notes.

**Your Task:**
1. Add the suggested subsections under their parent sections
2. Assign the provided relevant notes to these new subsections
3. Ensure subsections have clear, detailed descriptions
4. Maintain the existing outline structure

**Note Assignment Rules:**
- Each suggested subsection comes with relevant_note_ids
- Assign these notes to the new subsections you create
- You can also reassign notes from parent sections if appropriate
- Ensure notes are distributed logically

**Output Format:**
Generate a JSON object with:
- `mission_goal`: The research objective
- `generated_thought`: Summary of subsections added and notes assigned
- `report_outline`: The outline with new subsections and note assignments"""
        return prompt
    
    def _phase3c_note_redistribution_prompt(self) -> str:
        """Phase 3c: Final Note Redistribution - Ensure all notes are properly assigned."""
        prompt = """You are an expert research planner. Your task is to ensure all research notes are properly assigned to sections.

**Your Task:**
1. Review the current note assignments across all sections
2. Identify any unassigned notes from the provided list
3. Redistribute notes to appropriate sections based on relevance
4. Ensure balanced distribution without overloading sections

**Distribution Rules:**
- Every note should be assigned to at least one section
- Avoid redundant assignments unless truly relevant to multiple sections
- Prioritize relevance over equal distribution
- Maintain existing good assignments

**Output Format:**
Generate a JSON object with:
- `mission_goal`: The research objective
- `generated_thought`: Summary of note redistribution
- `report_outline`: The outline with finalized note assignments"""
        return prompt

    def _default_system_prompt(self) -> str:
        """Fallback to Phase 1 prompt if no specific phase is determined."""
        return self._phase1_system_prompt()
    
    def _old_default_system_prompt(self) -> str:
        """DEPRECATED - Old complex prompt kept for reference."""
        # This contains the old complex prompt
        prompt = f"""You are an expert research planner. Your goal is to create a detailed, step-by-step plan to answer the user's research request, ensuring the plan aligns with the overarching mission goals provided.

**Active Mission Goals and Thoughts:**
- The user prompt will contain sections listing the 'Current Active Mission Goals' and 'Recent Thoughts'.
- You MUST consult these goals when creating the plan.
- CRITICAL: The 'Current Active Mission Goals' will contain important user preferences including:
  - Request Type (e.g., "Academic Literature Review", "Informal Explanation")
  - Target Tone (e.g., "Formal Academic", "5th Grader")
  - Target Audience (e.g., "Researchers/Experts", "General Public")
  - Requested Length (e.g., "Short Summary", "Comprehensive Report")
  - Requested Format (e.g., "Full Paper", "Bullet Points")
- These preferences MUST guide your outline structure and complexity.
- Review the 'Recent Thoughts' to maintain focus and build on previous insights.
- Ensure the plan's steps and the report outline directly contribute to achieving these active goals. Prioritize actions that address open goals.

You must structure your output as a JSON object conforming exactly to the provided `SimplifiedPlanResponse` schema, including a `generated_thought` field.

**Adapting to User Preferences:**
- CRITICAL: You MUST adapt the outline complexity and structure based on the Requested Length and Format found in the 'Current Active Mission Goals':
  - For "Short Summary" length: Create a concise outline with 2-3 top-level sections and minimal subsections
  - For "Brief Paragraph" length: Create a very simple outline with 1-2 sections and no subsections
  - For "Comprehensive Report" length: Allow a more detailed structure with appropriate subsections
  - For "Bullet Points" format: Design a flatter structure optimized for bullet-point presentation
  - For "Q&A Format" format: Structure the outline as a series of questions with research to answer them
  - For "Summary Paragraph" format: Create a minimal outline with just essential sections

**Task Type Determination:**
- Use the "Request Type" from the Current Active Mission Goals to determine if this is primarily:
  1. A literature review/synthesis of existing knowledge, OR
  2. An empirical work involving experiments, data analysis, or methodology development
- This determination will guide your section selection.

The plan should include:
1.  `mission_goal`: A clear restatement of the user's overall research objective.
2.  `report_outline`: A list of sections for the final report, including `section_id`, `title`, and `description` (which MUST be detailed).

**Report Outline Generation (Adaptive):**
- Based on your Task Type Determination and the Requested Length/Format, generate an appropriate `report_outline`.
- **CRITICAL REQUIREMENTS:**
  - The outline MUST have at least one section.
  - The outline MUST have at least one section with `research_strategy: "research_based"`. This ensures that the research plan includes actual research steps rather than just synthesis or content-based sections.
  - Failure to meet these requirements will result in the outline being rejected.
  - Ensure the final outline does not exceed a depth of {self.controller.max_total_depth} (0=top-level, 1=subsection, 2=sub-subsection). 
- **Literature Review Task:**
    - Typical sections: Introduction, Literature Search Strategy (Optional), Thematic Synthesis (can have subsections for themes), Discussion (of the literature), Conclusion.
    - **CRITICAL:** Do NOT include standard "Methodology" or "Results" sections unless the user's request explicitly mentions analyzing specific data or conducting an experiment.
    - For shorter formats, consider combining or simplifying these sections.
- **Empirical Study Task:**
    - Typical sections: Introduction, Literature Review/Background, Methodology, Results, Discussion (of own results), Conclusion.
    - For shorter formats, consider combining Literature Review with Introduction, or Discussion with Conclusion.
- **General Outline Rules:**
    - Ensure section titles are descriptive.
    - The `description` field for each section MUST be detailed, breaking down the section's goal into specific sub-topics, arguments, or questions to be addressed by the Writing Agent. Do NOT simply repeat the title.
    - CRITICAL: The complexity and depth of the outline MUST match the Requested Length and Format.
    - **IMPORTANT: Do NOT include a "References", "Bibliography", or "Citations" section.** These will be automatically generated and appended to the final report.

**Report Outline Section Strategy:**
- For each section in `report_outline`, you MUST determine its `research_strategy`. Choose ONE of the following:
    - **`research_based`**: (DEFAULT) Use for sections/subsections requiring dedicated research steps (document search, web search, etc.).
    - **`synthesize_from_subsections`**: Use ONLY for a parent section whose content should be an introduction/summary derived *solely* from its direct subsections. These sections DO NOT get their own research steps.
    - **`content_based`**: **CRITICAL:** Use ONLY for top-level sections explicitly titled 'Introduction', 'Conclusion', 'Summary', or 'Abstract'. These sections are written based on the content of *other* sections and MUST NOT have dedicated research steps. Do NOT use `research_based` for these specific sections.
- Ensure the `research_strategy` field is correctly set for each `ReportSection` object in the `report_outline`. **Pay close attention to assigning `content_based` correctly to Introductory and Concluding sections (like Introduction, Intro to X, Conclusion, Final Thoughts, etc).**

Available Research Tools:
"""
        # Add tool descriptions from the registry
        if self.tool_registry:
            tool_schemas = self.tool_registry.get_all_tools() # Get ToolDefinition objects
            if tool_schemas:
                 prompt += "\n"
                 for tool_def in tool_schemas:
                      # Extract relevant info for the planner's context
                      param_desc = ", ".join([f"{name}: {props.get('description', 'No description')}"
                                               for name, props in tool_def.parameters_schema.model_json_schema().get('properties', {}).items()])
                      prompt += f"- Action Type: `{tool_def.name}`\n"
                      prompt += f"  - Description: {tool_def.description}\n"
                      prompt += f"  - Parameters: {param_desc}\n\n"
            else:
                 prompt += "- No tools seem to be registered.\n\n"
        else:
            prompt += "- Tool registry not available.\n\n"

        prompt += """Planning Guidelines:
- **VERY IMPORTANT:** For each section in the `report_outline`, the `description` field MUST be detailed. It should clearly list the specific sub-topics, arguments, key points, or questions that the Writing Agent needs to address within that section. **Crucially, these points/questions should break down the section's goal into distinct components and should NOT simply repeat or rephrase the section title or overall goal.** This detailed, distinct description is vital for guiding the writing process and preventing repetitive search queries later.
- **Note Assignment (If Context Provided):** If provided with 'Collected Notes Context' containing notes from initial research (each with a unique `note_id`), analyze these notes. For each section you define in the `report_outline`, identify the `note_id`s that are most relevant to that section's specific goal/description. Populate the `associated_note_ids` field for that section with the list of relevant note IDs. Distribute notes logically, ensure coherence, and avoid assigning the same core information redundantly across multiple sections.

- **Outline Structure Constraints:**
    - **Maximum Depth:** The `report_outline` MUST NOT exceed two levels of nesting. This means you can have top-level sections, and those sections can have subsections, but subsections cannot have further sub-subsections.
    - **Number of Top-Level Sections:** Aim for a concise structure. The number of top-level sections should generally be between 3 and 8, depending on the complexity required by the `mission_goal`. Avoid creating too many top-level sections.
    - **Number of Subsections:** Within each top-level section, limit the number of subsections to a maximum of 4. Keep subsections focused and avoid unnecessary granularity.
    - **Revision Conciseness:** When revising an outline ('Outline Revision Context'), focus on refining the existing structure based on suggestions. Avoid drastically increasing the number of sections or subsections unless absolutely necessary to incorporate critical new information or address specific revision requests. The goal is refinement, not exponential growth.

- **Outline Revision:** If provided with 'Outline Revision Context', prioritize incorporating the suggested subsection topics and structural modifications (add/remove/merge sections) intelligently into the existing outline while respecting the structure constraints defined above (depth, section counts) and avoiding redundancy. Ensure the `description` field for all sections (new and existing) is detailed as described above.
- **Subsection Structure Example:** When adding subsections based on suggestions (if you deem appropriate based on the stated goals, thoughts, and user request, as these pertain to the section at hand), you MUST modify the `subsections` array of the parent section in the JSON output. Each entry in the `subsections` array MUST be a complete JSON object representing the subsection, structured like this:
    ```json
    {
    "section_id": "parent_section_id",
    "title": "Parent Section Title",
    "description": "Parent section description.",
    "associated_note_ids": ["note_parent_A"], // Notes relevant to the parent overall
    "subsections": [
        {
        "section_id": "parent_section_id_subsection_1", // Generate a unique ID (e.g., parent_id + _ + subsection_title_slug)
        "title": "Subsection Title 1", // From suggestion
        "description": "Detailed description for subsection 1.", // From suggestion or generated based on goal
        "associated_note_ids": ["note_sub_B", "note_sub_C"], // Notes specific to this subsection
        "subsections": [], // Subsections CANNOT have further nesting (depth limit)
        "research_strategy": "research_based" // Or other appropriate strategy based on analysis
        }
        // Add other subsections here if needed
    ],
    "research_strategy": "synthesize_from_subsections" // Or other appropriate strategy for the parent
    }
    ```
- Remember to generate unique `section_id`s for new subsections.
- Assign relevant `associated_note_ids` specifically to the subsection if the notes pertain directly to its topic.
- Ensure the `description` for the new subsection is detailed and specific to its focus.
- **Scratchpad:** Use the 'Agent Scratchpad' for context about previous actions or thoughts. Keep your own contributions to the scratchpad concise.
- **Generated Thought:** Include a concise, focused thought in the `generated_thought` field of your response. This should capture a key insight, reminder, or focus point about the research plan that would be valuable to remember throughout the mission. Focus on the core research direction, potential pitfalls to avoid, or critical aspects of the user's request that must be maintained.
- Ensure the output is a single JSON object matching the `SimplifiedPlanResponse` schema.
"""
        return prompt

    async def run( # Make the method async
        self,
        user_request: str,
        initial_context: Optional[str] = None, # Added for preliminary outline
        final_outline_context: Optional[str] = None, # Added for final outline
        revision_context: Optional[str] = None, # NEW: Added for inter-pass revision
        agent_scratchpad: Optional[str] = None, # NEW: Added scratchpad input
        active_goals: Optional[List[GoalEntry]] = None, # NEW: Added active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None, # NEW: Added active thoughts
        mission_id: Optional[str] = None, # Add mission_id parameter
        log_queue: Optional[Any] = None, # Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None # Add update_callback parameter for UI updates
        ) -> Tuple[Optional[SimplifiedPlanResponse], Optional[Dict[str, Any]], Optional[str]]: # Modified return type
        """
        Generates or revises a research plan based on the user request, active goals, active thoughts, and optional context.

        Args:
            user_request: The user's research question or goal.
            initial_context: Optional context from initial searches for preliminary planning.
            final_outline_context: Optional context from collected notes for final planning.
            revision_context: Optional context containing current outline and suggestions for revision.
            agent_scratchpad: Optional string containing the current scratchpad content.
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.
            mission_id: Optional ID of the current mission.
            log_queue: Optional queue for sending log messages to the UI.
            update_callback: Optional callback function for UI updates.

        Returns:
            A tuple containing:
            - A SimplifiedPlanResponse object if successful, None otherwise.
            - A dictionary with model call details, or None on failure.
            - An optional string to update the agent scratchpad.
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        logger.info(f"{self.agent_name}: Generating plan for request: '{user_request}'")
        scratchpad_update = None # Initialize scratchpad update

        # Import the new schemas
        from ai_researcher.agentic_layer.schemas.planning import (
            Phase1PlanResponse, Phase2PlanResponse, Phase3PlanResponse,
            SimplifiedSection, SectionWithNotes
        )

        # Determine planning phase and select appropriate prompt/schema
        planning_phase = 1  # Default to phase 1
        system_prompt = self._phase1_system_prompt()  # No need to pass mission_id anymore
        response_schema = Phase1PlanResponse
        
        # Construct the user prompt based on phase
        user_prompt = f"Research Request: {user_request}\n\n"
        
        if final_outline_context:
            # Phase 2: Note assignment
            planning_phase = 2
            system_prompt = self._phase2_system_prompt()
            response_schema = Phase2PlanResponse
            logger.info(f"{self.agent_name}: Phase 2 - Note assignment to outline")
            user_prompt += f"Collected Research Notes:\n{final_outline_context}\n\n"
            user_prompt += "Assign these notes to the appropriate sections of the outline."
            
        elif revision_context:
            # Phase 3: Outline revision
            # Check if the revision context is too large and needs to be handled in sub-phases
            from ai_researcher.dynamic_config import get_max_planning_context_chars
            char_limit = get_max_planning_context_chars(mission_id)
            
            # If revision context is too large, we'll need to handle it differently
            # For now, still use the standard Phase 3 but we'll enhance this later
            planning_phase = 3
            system_prompt = self._phase3_system_prompt()
            response_schema = Phase3PlanResponse
            logger.info(f"{self.agent_name}: Phase 3 - Outline revision")
            
            # Check the size of the revision context
            if len(revision_context) > char_limit:
                logger.warning(f"{self.agent_name}: Revision context ({len(revision_context)} chars) exceeds limit ({char_limit} chars)")
                # We'll need to implement sub-phase handling here
                # For now, truncate the context intelligently
                # TODO: Implement proper sub-phase handling
                
            user_prompt += f"Revision Context:\n{revision_context}\n\n"
            user_prompt += "Revise the outline based on the feedback provided."
            
        else:
            # Phase 1: Initial outline generation
            logger.info(f"{self.agent_name}: Phase 1 - Initial outline generation")
            if initial_context:
                user_prompt += f"Initial Context:\n{initial_context}\n\n"
            user_prompt += "Generate a structured outline for this research task."

        # Add goals and thoughts if available (for all phases)
        if active_goals:
            goals_str = "\n".join([f"- {g.text}" for g in active_goals])
            user_prompt += f"\n\nActive Goals to Consider:\n{goals_str}\n"
            
        if active_thoughts:
            thoughts_str = "\n".join([f"- {t.content}" for t in active_thoughts[-3:]])  # Last 3 thoughts
            user_prompt += f"\n\nRecent Thoughts:\n{thoughts_str}\n"

        # Final instruction
        user_prompt += f"\n\nGenerate the JSON response following the Phase {planning_phase} format."

        # Start with json_schema format, with fallback to json_object
        response_format_pydantic = get_json_schema_format(
            pydantic_model=response_schema,
            schema_name=f"phase_{planning_phase}_plan"
        )

        # DEBUG: Log the prompts and schema being sent
        if DEBUG_PLANNING:
            logger.info("=" * 80)
            logger.info(f"PLANNING AGENT DEBUG - PHASE {planning_phase} PROMPTS:")
            logger.info("-" * 80)
            logger.info(f"System prompt length: {len(system_prompt)} characters")
            logger.info(f"System prompt:\n{system_prompt}")
            logger.info("-" * 40)
            logger.info(f"User prompt length: {len(user_prompt)} characters")
            logger.info(f"User prompt:\n{user_prompt}")
            logger.info("-" * 40)
            logger.info("Schema being requested:")
            import pprint
            logger.info(pprint.pformat(response_format_pydantic))
            logger.info("=" * 80)

        # Update system prompt for the agent
        self.system_prompt = system_prompt

        # Call the LLM - it now returns a tuple
        llm_response, model_call_details = await self._call_llm( # Add await here
            user_prompt=user_prompt,
            response_format=response_format_pydantic,
            agent_mode="planning", # <-- Pass agent_mode
            log_queue=log_queue, # Pass log_queue for UI updates
            update_callback=update_callback, # Pass update_callback for UI updates
            log_llm_call=False # Disable duplicate LLM call logging since planning operations are logged by the research manager
            # max_tokens is now handled by ModelDispatcher based on agent_mode ('planning')
            # Use the planning model specified during init or the default planning model
        )

        if not llm_response or not llm_response.choices:
            logger.error(f"{self.agent_name} Error: Failed to get response from LLM.")
            return None, model_call_details, scratchpad_update # Return details even on LLM failure if available

        raw_response_content = llm_response.choices[0].message.content
        if not raw_response_content:
             logger.error(f"{self.agent_name} Error: LLM returned empty content.")
             return None, model_call_details, scratchpad_update # Return details even on empty content

        logger.info(f"{self.agent_name}: Received raw plan response from LLM.")
        
        # DEBUG: Log the raw response
        if DEBUG_PLANNING:
            logger.info("=" * 80)
            logger.info("PLANNING AGENT DEBUG - RAW LLM RESPONSE:")
            logger.info("-" * 80)
            logger.info(f"Response length: {len(raw_response_content)} characters")
            # Always show full response for debugging, no truncation
            logger.info(f"Full response:\n{raw_response_content}")
            logger.info("=" * 80)
        else:
            logger.debug(f"Raw content:\n{raw_response_content}") # Debugging: Log raw response before parsing

        # Parse and validate the response using the Pydantic schema
        try:
            # --- Robust JSON Extraction ---
            # Find the start and end of the main JSON object ({...})
            # This handles potential leading/trailing text or markdown fences.
            json_start = raw_response_content.find('{')
            json_end = raw_response_content.rfind('}')

            if json_start != -1 and json_end != -1 and json_end > json_start:
                json_str = raw_response_content[json_start:json_end+1]
                
                # DEBUG: Log extracted JSON
                if DEBUG_PLANNING:
                    logger.info("PLANNING AGENT DEBUG - EXTRACTED JSON:")
                    logger.info("-" * 80)
                    if len(json_str) <= 2000:
                        logger.info(f"Extracted JSON:\n{json_str}")
                    else:
                        logger.info(f"Extracted JSON (first 1000 chars):\n{json_str[:1000]}")
                    logger.info("-" * 80)
            else:
                # Fallback or error if no valid JSON object markers found
                logger.error(f"{self.agent_name} Error: Could not find valid JSON object markers '{{' and '}}' in the response.")
                if DEBUG_PLANNING:
                    logger.error(f"Raw response was:\n{raw_response_content}")
                return None, model_call_details, scratchpad_update

            # --- End Robust JSON Extraction ---

            # Use the centralized JSON utilities to parse the response
            parsed_data = parse_llm_json_response(json_str)
            
            # Parse with the appropriate schema based on phase
            try:
                if planning_phase == 1:
                    plan_response = Phase1PlanResponse(**parsed_data)
                elif planning_phase == 2:
                    plan_response = Phase2PlanResponse(**parsed_data)
                else:  # Phase 3
                    plan_response = Phase3PlanResponse(**parsed_data)
                    
                logger.info(f"{self.agent_name}: Successfully parsed Phase {planning_phase} response")
                
                # Add section IDs programmatically
                plan_response = self._add_section_ids(plan_response)
                
                # Convert to SimplifiedPlanResponse for backward compatibility
                # This allows the rest of the system to work with the existing structure
                from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlanResponse, ReportSection
                
                # Convert the phase-specific response to SimplifiedPlanResponse
                unified_response = self._convert_to_simplified_response(plan_response, planning_phase)
                plan_response = unified_response
                
            except ValidationError as e:
                logger.error(f"{self.agent_name} Error: Failed to validate Phase {planning_phase} response: {e}")
                if DEBUG_PLANNING:
                    logger.error(f"Parsed data that failed validation:\n{json.dumps(parsed_data, indent=2)}")
                return None, model_call_details, scratchpad_update
            
            logger.info(f"{self.agent_name}: Successfully parsed and validated the plan.")
            
            # First apply programmatic strategy correction based on section characteristics
            if plan_response and plan_response.report_outline:
                logger.info(f"{self.agent_name}: Applying programmatic strategy correction")
                self._correct_section_strategies_programmatically(plan_response)
            
            # Apply validation and reflection loop to refine the outline
            # This will check for duplicates, depth violations, strategy issues, and other problems
            if plan_response and plan_response.report_outline:
                logger.info(f"{self.agent_name}: Applying validation and reflection loop to refine the outline")
                plan_response = await self._validate_and_refine_outline_with_reflection(
                    plan_response,
                    mission_id=mission_id,
                    max_iterations=3
                )
            
            # Generate scratchpad update based on the planning phase
            if planning_phase == 2:
                scratchpad_update = "Generated outline with notes assigned to sections. Validated and refined with reflection loop."
            elif planning_phase == 3:
                scratchpad_update = "Revised the outline based on the provided suggestions and context. Applied validation and refinement."
            else:  # Phase 1
                scratchpad_update = "Generated initial plan and outline. Validated structure and removed duplicates."

            return plan_response, model_call_details, scratchpad_update # Return the validated plan, model details, and scratchpad update

        except json.JSONDecodeError as e:
            logger.error(f"{self.agent_name} Error: Failed to decode JSON response from LLM: {e}")
            logger.error(f"Raw response was:\n{raw_response_content}") # Changed to error for debugging
            return None, model_call_details, scratchpad_update # Return details even on JSON error
        except ValidationError as e:
            logger.error(f"{self.agent_name} Error: Plan validation failed against Pydantic schema: {e}")
            logger.error(f"Raw response was:\n{raw_response_content}") # Changed to error for debugging
            return None, model_call_details, scratchpad_update # Return details even on validation error
        except Exception as e:
            logger.error(f"{self.agent_name} Error: An unexpected error occurred during plan processing: {e}", exc_info=True)
            logger.error(f"Raw response was:\n{raw_response_content}") # Changed to error for debugging
            return None, model_call_details, scratchpad_update # Return details even on other errors
            
    def _add_section_ids(self, plan_response):
        """Add section IDs programmatically to the outline."""
        import re
        
        def generate_id(title):
            """Generate a clean ID from a title."""
            # Convert to lowercase, replace spaces with underscores, remove special chars
            clean_id = re.sub(r'[^a-z0-9_]+', '', title.lower().replace(' ', '_'))
            return clean_id[:50]  # Limit length
        
        def add_ids_recursive(sections, parent_id=""):
            """Recursively add IDs to sections and subsections."""
            for i, section in enumerate(sections):
                # Generate section ID
                if parent_id:
                    section_id = f"{parent_id}_{i+1}"
                else:
                    section_id = generate_id(section.title)
                
                # Add ID if the section object supports it (Phase 1 and 3 don't have section_id)
                if not hasattr(section, 'section_id'):
                    # For SimplifiedSection, we'll need to convert it later
                    section._temp_id = section_id
                else:
                    section.section_id = section_id
                
                # Process subsections
                if section.subsections:
                    add_ids_recursive(section.subsections, section_id)
        
        add_ids_recursive(plan_response.report_outline)
        return plan_response
    
    def _convert_to_simplified_response(self, plan_response, planning_phase):
        """Convert phase-specific response to SimplifiedPlanResponse for compatibility."""
        from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlanResponse, ReportSection
        
        def convert_section(section):
            """Convert a phase-specific section to ReportSection."""
            # Get the section ID (either from attribute or temp storage)
            section_id = getattr(section, 'section_id', getattr(section, '_temp_id', 'unknown'))
            
            # Convert subsections recursively
            subsections = []
            if section.subsections:
                subsections = [convert_section(sub) for sub in section.subsections]
            
            # Create ReportSection
            return ReportSection(
                section_id=section_id,
                title=section.title,
                description=section.description,
                research_strategy=section.research_strategy,
                associated_note_ids=getattr(section, 'associated_note_ids', None),
                subsections=subsections
            )
        
        # Convert all sections
        converted_outline = [convert_section(section) for section in plan_response.report_outline]
        
        # Create SimplifiedPlanResponse
        return SimplifiedPlanResponse(
            mission_goal=plan_response.mission_goal,
            report_outline=converted_outline,
            generated_thought=getattr(plan_response, 'generated_thought', None)
        )
    
    def _correct_section_strategies_programmatically(self, plan_response: SimplifiedPlanResponse) -> None:
        """
        Programmatically corrects research strategies based on section characteristics.
        This ensures strategies are logical regardless of what the LLM initially set.
        
        Rules:
        1. Introduction/Overview sections → content_based
        2. Conclusion/Summary/Discussion sections → content_based  
        3. Sections WITH subsections → synthesize_from_subsections
        4. Leaf sections (no subsections) in the middle → research_based
        5. Ensure at least one research_based section exists
        """
        if not plan_response or not plan_response.report_outline:
            return
        
        logger.info(f"{self.agent_name}: Starting programmatic strategy correction")
        corrections_made = []
        has_research_based = False
        
        def correct_strategies_recursive(sections: List, is_top_level: bool = True):
            nonlocal has_research_based
            
            for i, section in enumerate(sections):
                if not hasattr(section, 'research_strategy'):
                    section.research_strategy = "research_based"  # Default if missing
                
                title_lower = section.title.lower() if section.title else ""
                old_strategy = section.research_strategy
                new_strategy = old_strategy  # Start with current
                
                # Determine correct strategy based on characteristics
                
                # Rule 1: Introduction (first top-level section with intro-like title)
                if is_top_level and i == 0 and any(kw in title_lower for kw in ["introduction", "intro", "overview", "background"]):
                    new_strategy = "content_based"
                
                # Rule 2: Conclusion/Summary/Discussion sections (by title)
                elif any(kw in title_lower for kw in ["conclusion", "summary", "discussion", "future", "implications", "final", "recommendations"]):
                    new_strategy = "content_based"
                
                # Rule 3: Sections with subsections should synthesize from them
                elif section.subsections and len(section.subsections) > 0:
                    new_strategy = "synthesize_from_subsections"
                    # Process subsections recursively
                    correct_strategies_recursive(section.subsections, is_top_level=False)
                
                # Rule 4: Leaf sections (no subsections) - default to research_based
                elif not section.subsections or len(section.subsections) == 0:
                    # Only if not already identified as intro/conclusion
                    if new_strategy == old_strategy:  # Hasn't been changed by rules 1 or 2
                        new_strategy = "research_based"
                
                # Apply the correction if needed
                if old_strategy != new_strategy:
                    section.research_strategy = new_strategy
                    corrections_made.append({
                        "section": section.title,
                        "old": old_strategy,
                        "new": new_strategy
                    })
                    logger.info(f"  Corrected '{section.title}': {old_strategy} → {new_strategy}")
                
                # Track if we have research_based sections
                if section.research_strategy == "research_based":
                    has_research_based = True
        
        # Apply corrections recursively
        correct_strategies_recursive(plan_response.report_outline, is_top_level=True)
        
        # Rule 5: Ensure at least one research_based section exists
        if not has_research_based:
            logger.warning(f"{self.agent_name}: No research_based sections found after correction. Forcing one.")
            # Find a suitable leaf section to convert
            for section in plan_response.report_outline:
                if not section.subsections:
                    title_lower = section.title.lower() if section.title else ""
                    # Avoid intro/conclusion sections
                    if not any(kw in title_lower for kw in ["introduction", "conclusion", "summary", "intro", "discussion"]):
                        old_strategy = section.research_strategy
                        section.research_strategy = "research_based"
                        corrections_made.append({
                            "section": section.title,
                            "old": old_strategy,
                            "new": "research_based",
                            "reason": "Forced to ensure at least one research section"
                        })
                        logger.info(f"  Forced '{section.title}' to research_based (was {old_strategy})")
                        break
        
        if corrections_made:
            logger.info(f"{self.agent_name}: Made {len(corrections_made)} strategy corrections")
        else:
            logger.info(f"{self.agent_name}: No strategy corrections needed")
    
    async def _validate_and_refine_outline_with_reflection(
        self,
        plan_response: SimplifiedPlanResponse,
        mission_id: Optional[str] = None,
        max_iterations: int = 3
    ) -> SimplifiedPlanResponse:
        """
        Validates and refines the outline using a reflection loop with programmatic checks.
        
        Args:
            plan_response: The initial plan response to validate and refine
            mission_id: Optional mission ID for context
            max_iterations: Maximum number of reflection iterations (default: 3)
            
        Returns:
            The refined SimplifiedPlanResponse after validation and reflection
        """
        from ai_researcher.agentic_layer.controller.utils.outline_validator import OutlineValidator, create_reflection_prompt
        
        logger.info(f"{self.agent_name}: Starting outline validation and reflection loop (max {max_iterations} iterations)")
        
        current_response = plan_response
        iteration_reports = []
        
        for iteration in range(max_iterations):
            logger.info(f"{self.agent_name}: Reflection iteration {iteration + 1}/{max_iterations}")
            
            # Step 1: Validate and auto-correct the outline
            validator = OutlineValidator(mission_id=mission_id, controller=self.controller)
            corrected_outline, validation_report = validator.validate_and_correct(
                current_response.report_outline,
                auto_correct=True
            )
            
            # Update the response with corrected outline
            current_response.report_outline = corrected_outline
            iteration_reports.append(validation_report)
            
            # Log validation results
            logger.info(f"  - Validation complete: {len(validation_report['issues'])} issues found, "
                       f"{len(validation_report['corrections'])} corrections applied")
            logger.info(f"  - Outline depth: {validation_report['actual_max_depth']} "
                       f"(max allowed: {validation_report['max_depth_setting']})")
            logger.info(f"  - Total sections: {validation_report['total_sections']}")
            
            # If no issues found and depth is within limits, we're done
            if (validation_report['valid'] and 
                validation_report['actual_max_depth'] <= validation_report['max_depth_setting']):
                logger.info(f"{self.agent_name}: Outline validation successful after {iteration + 1} iterations")
                break
            
            # Step 2: Create reflection prompt for improvement
            reflection_prompt = create_reflection_prompt(
                corrected_outline,
                validation_report,
                current_response.mission_goal
            )
            
            # Step 3: Get reflection suggestions from LLM
            try:
                messages = [
                    {"role": "system", "content": self._phase3_system_prompt()},
                    {"role": "user", "content": reflection_prompt}
                ]
                
                llm_response, _ = await self.model_dispatcher.dispatch(
                    messages=messages,
                    response_format={"type": "json_object"},
                    agent_mode="planning"
                )
                
                if not llm_response or not llm_response.choices:
                    logger.warning(f"{self.agent_name}: No response from reflection LLM, keeping current outline")
                    break
                
                # Parse the reflection response
                reflection_data = parse_llm_json_response(llm_response.choices[0].message.content)
                
                # If we get a new outline suggestion, update it
                if reflection_data and "report_outline" in reflection_data:
                    logger.info(f"{self.agent_name}: Applying reflection suggestions to outline")
                    
                    # Validate and convert the report_outline to ReportSection objects
                    new_outline = []
                    for section in reflection_data["report_outline"]:
                        try:
                            # Check if section is already a dict with the right structure
                            if isinstance(section, dict):
                                # Ensure required fields are present
                                if "section_id" not in section and "title" in section:
                                    # Generate section_id from title if missing
                                    section["section_id"] = section["title"].lower().replace(" ", "_")
                                
                                # Ensure description exists
                                if "description" not in section:
                                    section["description"] = f"Section covering {section.get('title', 'topic')}"
                                
                                # Create ReportSection object
                                new_outline.append(ReportSection(**section))
                            elif isinstance(section, str):
                                # If it's just a string (section title), create a minimal ReportSection
                                logger.warning(f"{self.agent_name}: Reflection returned string instead of dict for section: {section}")
                                new_outline.append(ReportSection(
                                    section_id=section.lower().replace(" ", "_"),
                                    title=section,
                                    description=f"Section covering {section}",
                                    research_strategy="research_based"
                                ))
                            else:
                                logger.warning(f"{self.agent_name}: Unexpected type for section in reflection: {type(section)}")
                        except Exception as e:
                            logger.warning(f"{self.agent_name}: Failed to create ReportSection from reflection data: {e}. Section data: {section}")
                            # Keep the current section if we can't parse the new one
                            continue
                    
                    # Only update if we successfully parsed some sections
                    if new_outline:
                        current_response.report_outline = new_outline
                    else:
                        logger.warning(f"{self.agent_name}: No valid sections parsed from reflection, keeping current outline")
                    
                    # Update thought if provided
                    if "generated_thought" in reflection_data:
                        current_response.generated_thought += f"\n\nReflection {iteration + 1}: {reflection_data['generated_thought']}"
                
            except Exception as e:
                logger.error(f"{self.agent_name}: Error during reflection iteration {iteration + 1}: {str(e)}")
                # Continue with the current corrected outline
                break
        
        # Final validation to ensure everything is correct
        final_validator = OutlineValidator(mission_id=mission_id, controller=self.controller)
        final_outline, final_report = final_validator.validate_and_correct(
            current_response.report_outline,
            auto_correct=True
        )
        current_response.report_outline = final_outline
        
        # Log final summary
        logger.info(f"{self.agent_name}: Reflection loop complete. Final outline has "
                   f"{final_report['total_sections']} sections with max depth "
                   f"{final_report['actual_max_depth']}")
        
        # Add validation summary to the thought
        validation_summary = (
            f"Outline validated: {final_report['total_sections']} sections, "
            f"max depth {final_report['actual_max_depth']}/{final_report['max_depth_setting']}, "
            f"{len(final_report['corrections'])} auto-corrections applied."
        )
        
        if current_response.generated_thought:
            current_response.generated_thought += f"\n\n{validation_summary}"
        else:
            current_response.generated_thought = validation_summary
        
        return current_response
    
    async def _correct_section_strategies_with_llm(self, plan_response: SimplifiedPlanResponse) -> None:
        """
        Uses an LLM to analyze the outline structure and determine appropriate research strategies
        for each section based on its content, position, and relationship to other sections.
        
        Args:
            plan_response: The SimplifiedPlanResponse object containing the outline to analyze and correct.
        """
        if not plan_response.report_outline:
            logger.warning(f"{self.agent_name}: No outline to analyze for section strategies.")
            return
            
        # Format the outline for analysis
        outline_str = self._format_outline_for_analysis(plan_response.report_outline)
        
        # Construct the prompt for the LLM
        prompt = f"""
You are an expert research planner analyzing a report outline structure to determine the appropriate research strategy for each section.

For each section in the outline, you need to assign ONE of the following research strategies:

1. **content_based**: For sections that should be written based on the content of other sections, not requiring their own research. 
   - Typically used for Introduction and Conclusion sections
   - These sections synthesize and frame the overall report
   - They don't need dedicated research steps as they draw from other sections' content

2. **synthesize_from_subsections**: For parent sections that should be derived solely from their direct subsections.
   - Used when a section has multiple subsections and its content should be a summary/synthesis of those subsections
   - These sections don't get their own research steps
   - The parent section serves as an introduction or overview of its subsections

3. **research_based**: For sections requiring dedicated research steps (document search, web search, etc.).
   - Default strategy for most content sections
   - These sections need their own data gathering and analysis
   - Used for the core content sections that aren't introductory or concluding in nature

Here is the current outline structure:

{outline_str}

Analyze each section in the provided simplified structure and determine the most appropriate research strategy based *only* on:
1. The section's title (e.g., does it suggest Introduction, Conclusion, etc.?)
2. The section's position in the outline (e.g., is it the first or last top-level section?)
3. Whether the section has subsections (`Has Subsections: Yes/No`)

Return a JSON object with section_id as keys and the appropriate research_strategy as values:
```json
{{
  "section_id_1": "content_based",
  "section_id_2": "research_based",
  "section_id_3": "synthesize_from_subsections",
  "subsection_id_1": "research_based",
  "subsection_id_2": "content_based"
}}
```

IMPORTANT GUIDELINES:
- Introduction sections (typically the first section) should usually be "content_based"
- Conclusion sections (typically the last section) should usually be "content_based"
- Sections with subsections might be "synthesize_from_subsections" if they primarily serve to introduce their subsections
- Most middle sections with specific content focus should be "research_based"
- Be thoughtful about the logical flow of the document and how sections relate to each other
- CRITICAL: You must analyze and assign strategies to BOTH top-level sections AND their subsections

Example of a hierarchical outline and appropriate strategies:
1. Introduction (section_id: "introduction") → content_based (draws from other sections)
2. Literature Review (section_id: "literature_review") → synthesize_from_subsections (has subsections and serves as their overview)
   2.1. Historical Context (section_id: "historical_context") → research_based (needs dedicated research)
   2.2. Current Approaches (section_id: "current_approaches") → research_based (needs dedicated research)
3. Methodology (section_id: "methodology") → research_based (core content section)
4. Results (section_id: "results") → research_based (core content section)
5. Discussion (section_id: "discussion") → research_based (core content section)
6. Conclusion (section_id: "conclusion") → content_based (synthesizes from other sections)
"""

        try:
            # Call the LLM to analyze the outline
            messages = [{"role": "user", "content": prompt}]
            response_format = {"type": "json_object"}
            
            llm_response, _ = await self.model_dispatcher.dispatch(
                messages=messages,
                response_format=response_format,
                agent_mode="planning"  # Use planning model for this analysis
            )
            
            if not llm_response or not llm_response.choices or not llm_response.choices[0].message.content:
                logger.error(f"{self.agent_name}: Failed to get response from LLM for section strategy analysis.")
                return
                
            # Parse the response using the robust JSON utility
            strategy_map = parse_llm_json_response(llm_response.choices[0].message.content)
            
            # Apply the strategies to the outline
            sections_updated = 0
            for section in plan_response.report_outline:
                self._apply_strategies_recursive(section, strategy_map)
                sections_updated += 1
                
            logger.info(f"{self.agent_name}: Successfully analyzed and updated research strategies for {sections_updated} sections.")
            
        except Exception as e:
            logger.error(f"{self.agent_name}: Error during section strategy analysis: {e}", exc_info=True)
            # Continue with the existing strategies rather than failing the whole process

    def _format_outline_for_analysis(self, outline: List[Any], level: int = 0) -> str:
        """
        Formats the outline into a *simplified structural* string representation
        for the LLM strategy analysis call. Omits descriptions and current strategies
        to force the LLM to rely only on structure, title, and position.

        Args:
            outline: List of ReportSection objects
            level: Current nesting level (for indentation)

        Returns:
            A simplified formatted string representation of the outline structure.
        """
        result = ""
        for i, section in enumerate(outline):
            indent = "  " * level
            has_subsections = bool(section.subsections)

            # Format simplified section info (Title, ID, Subsection Presence)
            result += f"{indent}Section {i+1}: {section.title} (ID: {section.section_id})\n"
            result += f"{indent}Has Subsections: {'Yes' if has_subsections else 'No'}\n"

            # Add subsections if they exist
            if has_subsections:
                result += f"{indent}Subsections:\n"
                result += self._format_outline_for_analysis(section.subsections, level + 1)
            
            result += "\n"
            
        return result
    
    def _apply_strategies_recursive(self, section: Any, strategy_map: Dict[str, str]) -> None:
        """
        Recursively applies the strategies from the strategy_map to the outline.
        
        Args:
            section: A ReportSection object
            strategy_map: Dictionary mapping section_ids to research strategies
        """
        section_id = section.section_id
        
        if section_id in strategy_map:
            new_strategy = strategy_map[section_id]
            old_strategy = section.research_strategy
            
            # Only update if the strategy is different
            if new_strategy != old_strategy:
                section.research_strategy = new_strategy
                logger.info(f"{self.agent_name}: Updated strategy for section '{section.title}' from '{old_strategy}' to '{new_strategy}'")
        
        # Process subsections recursively
        if section.subsections:
            for subsection in section.subsections:
                self._apply_strategies_recursive(subsection, strategy_map)
