import json
from typing import Optional, List, Dict, Any, Tuple
from pydantic import ValidationError

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    prepare_for_pydantic_validation
)
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Import ThoughtEntry

# Use absolute imports starting from the top-level package 'ai_researcher'
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
# Note: MODEL_MAPPING was removed from model_dispatcher, we should get it from config now
from ai_researcher import config # Import config to get model mapping
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlanResponse, SimplifiedPlan # Import the schemas
from ai_researcher.agentic_layer.schemas.goal import GoalEntry # Import GoalEntry
import logging # <-- Add logging

logger = logging.getLogger(__name__) # <-- Add logger

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

    def _default_system_prompt(self) -> str:
        """Generates the default system prompt including tool descriptions."""
        # Base prompt
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

        prompt += """# This section has been removed as steps are no longer required

Planning Guidelines:
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
        // No depends_on_steps field needed
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

        # Construct the user prompt for the LLM, including context if provided
        prompt = f"User Research Request:\n---\n{user_request}\n---\n"

        # Include active goals if available
        if active_goals:
            # Corrected: Access g.status directly as it's a Literal (string-like)
            goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals])
            prompt += f"\nCurrent Active Mission Goals:\n---\n{goals_str}\n---\n"
            prompt += "Ensure the plan directly addresses these goals.\n"
            
        # Include active thoughts if available
        if active_thoughts:
            thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts])
            prompt += f"\nRecent Thoughts:\n---\n{thoughts_str}\n---\n"
            prompt += "Consider these recent thoughts when creating your plan and generating your own thought.\n"

        # Include scratchpad content if available
        if agent_scratchpad:
            prompt += f"\nCurrent Agent Scratchpad:\n---\n{agent_scratchpad}\n---\n"

        planning_mode = "initial" # Default mode

        if initial_context:
             logger.info(f"{self.agent_name}: Using initial search context for preliminary planning.")
             prompt += f"\nInitial Search Context (for preliminary outline):\n---\n{initial_context}\n---\n"
             prompt += "\nPlease generate a PRELIMINARY research plan and outline based on the request and initial context."
             planning_mode = "preliminary"
        elif final_outline_context:
             logger.info(f"{self.agent_name}: Using collected notes context for final outline generation.")
             prompt += f"\nCollected Notes Context (for final outline generation):\n---\n{final_outline_context}\n---\n"
             prompt += "\nPlease generate a FINAL, REFINED research plan and outline based on the original request and the collected notes context. Ensure the outline is logical, minimizes redundancy, and covers key findings from the notes."
             planning_mode = "final"
        elif revision_context:
             logger.info(f"{self.agent_name}: Using revision context for inter-pass outline update.")
             # The revision_context should already contain the necessary instructions, current outline, and suggestions.
             prompt += f"\nOutline Revision Context:\n---\n{revision_context}\n---\n"
             # Instructions are embedded within the revision_context by the controller
             planning_mode = "revision"
        else:
             # Default case (no specific context provided - likely first call without initial context)
             prompt += "\nPlease generate the research plan as a JSON object matching the SimplifiedPlanResponse schema."
             planning_mode = "initial" # Already set, but explicit

        # Ensure the final instruction about JSON output is always present
        prompt += "\n\nOutput ONLY the single JSON object conforming to the SimplifiedPlanResponse schema."

        # Define the expected response format using the Pydantic schema,
        # structured according to OpenRouter's json_schema requirements.
        # Get the schema dictionary generated by Pydantic.
        # The 'additionalProperties: false' constraint is now handled by
        # ConfigDict(extra='forbid') in the SimplifiedPlanResponse model definition.
        
        response_format_pydantic = {
            "type": "json_schema",
            "json_schema": {
                "name": "research_plan", # Descriptive name for the schema
                # "strict": True, # Ensure stricter adherence to the schema
                "schema": SimplifiedPlanResponse.model_json_schema() # The actual Pydantic schema
            }
        }

        # --- TEMPORARY DEBUGGING: Print the exact schema being sent ---
        # print("\n--- DEBUG: Schema being sent to LLM ---") # Keep commented out for now
        # import pprint
        # pprint.pprint(response_format_pydantic)
        # print("--- END DEBUG ---\n")
        # --- END TEMPORARY DEBUGGING ---

        # Call the LLM - it now returns a tuple
        llm_response, model_call_details = await self._call_llm( # Add await here
            user_prompt=prompt,
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
            else:
                # Fallback or error if no valid JSON object markers found
                logger.error(f"{self.agent_name} Error: Could not find valid JSON object markers '{{' and '}}' in the response.")
                logger.error(f"Raw response was:\n{raw_response_content}") # Changed to error for debugging
                return None, model_call_details, scratchpad_update

            # --- End Robust JSON Extraction ---

            # Use the centralized JSON utilities to parse and prepare the response
            parsed_data = parse_llm_json_response(json_str)
            prepared_data = prepare_for_pydantic_validation(parsed_data, SimplifiedPlanResponse)

            # --- Remove steps field if present (since it's no longer needed) ---
            if 'steps' in parsed_data:
                logger.info(f"{self.agent_name}: Removing 'steps' field from response as it's no longer needed.")
                del parsed_data['steps']
            # --- End Remove steps field ---

            plan_response = SimplifiedPlanResponse(**parsed_data)

            if plan_response.parsing_error:
                  logger.error(f"{self.agent_name} Error: LLM indicated a parsing error: {plan_response.parsing_error}")
                  return None, model_call_details, scratchpad_update # Return details even on parsing error
            
            # Post-process the outline to correct section strategies using LLM
            await self._correct_section_strategies_with_llm(plan_response)
            
            logger.info(f"{self.agent_name}: Successfully parsed and validated the plan.")
            # Generate scratchpad update based on the planning mode
            if planning_mode == "preliminary":
                scratchpad_update = "Generated preliminary plan and outline based on initial context."
            elif planning_mode == "final":
                scratchpad_update = "Generated final plan and outline based on collected notes."
            elif planning_mode == "revision":
                scratchpad_update = "Revised plan and outline based on reflection suggestions."
            else: # initial
                scratchpad_update = "Generated initial plan and outline."

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
