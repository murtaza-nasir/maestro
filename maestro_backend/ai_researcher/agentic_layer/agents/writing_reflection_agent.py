import logging
import re
from typing import Optional, List, Dict, Any, Tuple

from pydantic import ValidationError

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    prepare_for_pydantic_validation
)

# Use absolute imports starting from the top-level package 'ai_researcher'
from ai_researcher.agentic_layer.agents.base_agent import BaseAgent
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher import config
from ai_researcher.agentic_layer.schemas.planning import ReportSection # May need outline context
from ai_researcher.agentic_layer.schemas.writing import WritingReflectionOutput, WritingChangeSuggestion
from ai_researcher.agentic_layer.schemas.goal import GoalEntry # <-- Import GoalEntry
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Added import

logger = logging.getLogger(__name__)

class WritingReflectionAgent(BaseAgent):
    """
    Agent responsible for reflecting on a written draft, identifying issues like
    repetition, lack of clarity, or poor flow, and suggesting specific revisions.
    """
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        controller: Optional[Any] = None # Add controller parameter
    ):
        agent_name = "WritingReflectionAgent"
        # Determine model based on 'reflection' role in config (or a new 'writing_reflection' role if defined)
        reflection_model_type = config.AGENT_ROLE_MODEL_TYPE.get("reflection", "fast") # Default to fast
        if reflection_model_type == "fast":
            provider = config.FAST_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["fast_model"]
        elif reflection_model_type == "mid": # Explicitly check for mid
            provider = config.MID_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["mid_model"]
        elif reflection_model_type == "intelligent": # Add check for intelligent
            provider = config.INTELLIGENT_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["intelligent_model"]
        else: # Fallback if type is unknown
            logger.warning(f"Unknown reflection model type '{reflection_model_type}', falling back to fast.") # Fallback to fast for reflection? Or mid? Let's use fast.
            provider = config.FAST_LLM_PROVIDER
            effective_model_name = config.PROVIDER_CONFIG[provider]["fast_model"]

        # Override with specific model_name if provided by the user during instantiation
        effective_model_name = model_name or effective_model_name

        super().__init__(
            agent_name=agent_name,
            model_dispatcher=model_dispatcher,
            tool_registry=None, # No tools needed for reflection
            system_prompt=system_prompt or self._default_system_prompt(),
            model_name=effective_model_name
        )
        self.controller = controller # Store controller
        self.mission_id = None # Initialize mission_id as None

    def _default_system_prompt(self) -> str:
        """Generates the default system prompt for the Writing Reflection Agent."""
        return """You are an expert academic editor. Your task is to review a draft of a research report section (or the full report) and provide constructive feedback for improvement, considering the overall mission goals.

You will be given the draft text, potentially the report outline, and the active mission goals. Your goal is to identify issues related to:
- **Alignment with Goals:** **CRITICAL:** Does the draft strictly align with the specified `request_type`, `target_tone`, and `target_audience` defined in the 'Active Mission Goals'? Is the language, style, and level of detail appropriate? Does it fulfill the core objectives?
- Clarity and Conciseness: Is the writing easy to understand? Is there unnecessary jargon or wordiness?
- Coherence and Flow: Do ideas connect logically? Are transitions between paragraphs and sections smooth?
- Repetition: Is the same information or phrasing repeated unnecessarily?
- Accuracy (based *only* on the provided text): Are there internal contradictions?
- Completeness (relative to outline/goals if provided): Does the draft seem to address the intended scope?
- Adherence to Academic Style: Is the tone objective and formal?

Based on your review, provide:
1. A brief 'overall_assessment' (1-2 sentences).
2. A list of specific, actionable 'change_suggestions'. Each suggestion should include:
    - 'section_id': The ID of the section/subsection where the issue occurs.
    - 'issue_description': A clear explanation of the problem.
    - 'suggested_change': Concrete advice on how to fix it.
    - 'priority': (Optional, default 1 for High).
3. A concise 'scratchpad_update' summarizing this reflection step.
4. A concise 'generated_thought' (1-2 sentences) capturing a key insight or focus point about the writing quality or alignment with goals that should be remembered.

Output ONLY a JSON object conforming to the WritingReflectionOutput schema (including `scratchpad_update` and `generated_thought`).
If no significant issues are found, provide a positive overall assessment, an empty list for 'change_suggestions', a simple scratchpad update like "Reviewed draft, no major issues found.", and a relevant positive thought for `generated_thought`.
- **Scratchpad:** Use the 'Agent Scratchpad' for context about previous actions or thoughts. Keep your own contributions to the scratchpad concise.
"""

    async def run(
        self,
        draft_content: str,
        outline: Optional[List[ReportSection]] = None, # Optional outline for context
        active_goals: Optional[List[GoalEntry]] = None, # <-- NEW: Add active goals
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        agent_scratchpad: Optional[str] = None, # NEW: Added scratchpad input
        mission_id: Optional[str] = None, # Add mission_id parameter
        log_queue: Optional[Any] = None, # Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None # Add update_callback parameter for UI updates
        ) -> Tuple[Optional[WritingReflectionOutput], Optional[Dict[str, Any]], Optional[str]]: # Modified return type
        """
        Analyzes the draft content, considering active goals, and returns suggestions for revision.

        Args:
            draft_content: The text of the report draft to review.
            outline: The report outline structure (optional, for context).
            active_goals: Optional list of active GoalEntry objects for the mission.
            active_thoughts: Optional list of ThoughtEntry objects containing recent thoughts.
            agent_scratchpad: Optional string containing the current scratchpad content.
            mission_id: Optional ID of the current mission.
            log_queue: Optional queue for sending log messages to the UI.
            update_callback: Optional callback function for UI updates.

        Returns:
            A tuple containing:
            - A WritingReflectionOutput object with assessment and suggestions, or None on failure.
            - A dictionary with model call details, or None on failure.
            - An optional string to update the agent scratchpad.
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        logger.info(f"{self.agent_name}: Reflecting on draft content (length: {len(draft_content)} chars)...")
        scratchpad_update = None # Initialize

        outline_context = ""
        if outline:
             # Format outline for context (reuse controller helper if possible, or simple format here)
             outline_lines = []
             def format_outline_recursive(section_list: List[ReportSection], level: int = 0):
                 indent = "  " * level
                 for i, section in enumerate(section_list):
                     prefix = f"{indent}{i+1}." if level == 0 else f"{indent}-"
                     outline_lines.append(f"{prefix} ID: {section.section_id}, Title: {section.title}")
                     if section.subsections:
                         format_outline_recursive(section.subsections, level + 1)
             format_outline_recursive(outline)
             outline_context = "\n\nReport Outline Structure (for context):\n---\n" + "\n".join(outline_lines) + "\n---"

        # Include scratchpad content if available
        scratchpad_context = ""
        if agent_scratchpad:
            scratchpad_context = f"\nCurrent Agent Scratchpad:\n---\n{agent_scratchpad}\n---\n"

        # Format active goals
        # Consistent with other agents, access g.status directly (assuming it's string-like)
        goals_str = "\n".join([f"- Goal ID: {g.goal_id}, Status: {g.status}, Text: {g.text}" for g in active_goals]) if active_goals else "None"
        active_goals_context = f"""
Active Mission Goals (Consider these for tone, audience, and overall direction):
---
{goals_str}
---
"""
        # Format active thoughts
        thoughts_context = ""
        if active_thoughts:
            thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts])
            thoughts_context = f"\nRecent Thoughts (Consider these for context and focus):\n---\n{thoughts_str}\n---\n"

        prompt = f"""Please review the following draft report content. **CRITICAL: Evaluate the draft primarily against the 'Active Mission Goals' (especially request_type, target_tone, target_audience) and 'Recent Thoughts'.** Also identify issues related to clarity, coherence, flow, repetition, and academic style. Provide an overall assessment, specific actionable suggestions for revision (referencing section_id if possible), and a concise scratchpad update summarizing your reflection.{scratchpad_context}{active_goals_context}{thoughts_context}{outline_context}

Draft Content:
---
{draft_content}
---

Task: Output ONLY a JSON object conforming to the WritingReflectionOutput schema, containing your 'overall_assessment', a list of 'change_suggestions' (prioritizing suggestions related to goal alignment), and a 'scratchpad_update'.
"""

        messages = [{"role": "user", "content": prompt}]
        model_call_details = None
        response_model = None # Initialize
        try:
            response, model_call_details = await self._call_llm(
                user_prompt=prompt,
                agent_mode="reflection", # Use reflection model type
                response_format={"type": "json_object"}, # Expect JSON output
                log_queue=log_queue, # Pass log_queue for UI updates
                update_callback=update_callback # Pass update_callback for UI updates
            )

            if response and response.choices and response.choices[0].message.content:
                json_str = response.choices[0].message.content
                # Attempt to find JSON within potential markdown fences
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
                if match:
                    json_str = match.group(1)

                try:
                    # Parse the JSON content using our centralized utilities
                    parsed_json = parse_llm_json_response(json_str)
                    # Prepare the data for Pydantic validation
                    prepared_data = prepare_for_pydantic_validation(parsed_json, WritingReflectionOutput)
                    # Validate using the Pydantic model
                    response_model = WritingReflectionOutput(**prepared_data)
                    scratchpad_update = response_model.scratchpad_update # Extract scratchpad update
                    logger.info(f"{self.agent_name}: Reflection complete. Assessment: {response_model.overall_assessment}. Suggestions: {len(response_model.change_suggestions)}")
                    logger.info(f"  Scratchpad Update: {scratchpad_update}")
                    return response_model, model_call_details, scratchpad_update
                except Exception as e:
                    logger.error(f"{self.agent_name}: Failed to parse or validate JSON response: {e}. Response: {json_str}", exc_info=True)
                    return None, model_call_details, scratchpad_update # Return scratchpad_update (which might be None)
            else:
                logger.error(f"{self.agent_name}: LLM call failed or returned empty content.")
                return None, model_call_details, scratchpad_update # Return scratchpad_update (which might be None)

        except Exception as e:
            logger.error(f"{self.agent_name}: Error during reflection: {e}", exc_info=True)
            return None, model_call_details, scratchpad_update # Return scratchpad_update (which might be None)
