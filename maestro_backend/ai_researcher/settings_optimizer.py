"""
Shared settings optimization logic for both API endpoints and chat workflows.
"""
import logging
import json
from typing import Dict, Any, Optional, List
from database.models import User
from ai_researcher.agentic_layer.agent_controller import AgentController
from ai_researcher.agentic_layer.context_manager import ContextManager
from ai_researcher.agentic_layer.utils.json_utils import parse_llm_json_response
from api.schemas import MissionSettings

logger = logging.getLogger(__name__)

async def determine_research_parameters(
    chat_history: List[Any], 
    controller: AgentController
) -> Optional[Dict[str, Any]]:
    """
    Uses an AI agent to determine the optimal research parameters based on chat history.
    """
    logger.info("Determining research parameters via AI agent...")
    formatted_history = "\n".join([f"{msg.role}: {msg.content}" for msg in chat_history])

    prompt = f"""You are a master Research Strategist. Your primary function is to analyze the nuances of a user's request—both explicit and implicit—to configure the optimal parameters for a sophisticated, agentic research and writing process. You must move beyond simple keyword analysis and interpret the user's underlying intent, context, and desired output.

Based on the provided conversation history, you will generate a JSON object that fine-tunes the research agent's behavior.

**Heuristics for Parameter Determination:**

Your analysis should be guided by the following principles.

---
### **0. Guiding Principle: Prioritize the User's Voice**
**This is your most important instruction.** The conversation history contains messages from both the user and an automated agent. Your primary goal is to determine the user's *true intent* by focusing on **the user's messages**.

* **Rule of Misalignment:** The agent's generated research questions can often inflate the complexity of a simple request. If you detect a mismatch between the simplicity/scope of a user's prompt (e.g., 'Why is the sky blue?') and the academic complexity of the agent's follow-up questions, you **must anchor your parameter choices to the user's original, simpler request.**
* **Trust User Keywords:** Explicit constraints from the user like 'give me a short...', 'simple explanation,' or 'brief overview' are the most powerful signals and should override any complexity introduced by the agent.
---

**1. Complexity and Scope:**
   - **Simple & Factual:** A request for a single, verifiable fact (e.g., 'What is the capital of Mongolia?'). This requires minimal research.
     - *Parameters:* Low `structured_research_rounds`, low `initial_research_max_questions`, low `writing_passes`.
   - **Broad & Exploratory:** A request to learn about a wide topic without a specific thesis (e.g., 'Tell me about the Renaissance'). This requires a wide initial search to frame the topic.
     - *Parameters:* High `initial_research_max_questions`, high `initial_exploration_web_results`, moderate `structured_research_rounds`.
   - **Narrow & Deep:** A request to investigate a very specific question (e.g., 'What was the effect of the 1982 Tylenol crisis on pharmaceutical packaging regulations?'). This requires less exploration but more focused, iterative digging.
     - *Parameters:* Low `initial_research_max_questions`, high `structured_research_rounds`, high `main_research_web/doc_results`.
   - **Comparative & Analytical:** A request to compare two or more things, often requiring synthesis and evaluation (e.g., 'Compare and contrast the economic policies of Hayek and Keynes'). This is highly complex.
     - *Parameters:* High values across the board, especially `structured_research_rounds` and `writing_passes` to refine the nuanced argument.

**2. User Intent, Formality, and Tone:**
   - **Formality (Academic/Professional):** Formal language, citation requests, or discussion of specific methodologies implies a need for high rigor and depth.
     - *Parameters:* Increase `writing_passes` for polish, increase `main_research_doc/web_results` for source depth. Prioritize `doc_results` if academic papers are mentioned.
   - **Intensity & Urgency (e.g., 'I need this for a meeting tomorrow'):** This requires a balance of speed and comprehensiveness. The research must be thorough, but the writing may need to be slightly less polished to meet a deadline.
     - *Parameters:* High `structured_research_rounds`, but potentially fewer `writing_passes` (e.g., 2-3 instead of 4-5) to produce a 'strong draft' quickly.
   - **Verbosity:** A long, detailed prompt provides many clues. The user has a clear, complex model in their head. A short prompt for a complex topic may require the agent to do more initial framing work.
     - *Parameters:* For a verbose, complex prompt, increase `structured_research_rounds`. For a short, complex prompt, increase `initial_research_max_questions` to clarify the user's intent.
   - **Tone (Curious vs. Demanding):** A curious tone ('I wonder how...') suggests exploration. A demanding tone ('Generate a report that proves...') suggests a need to find specific, supporting evidence, requiring deeper, more targeted research.

**3. Source Emphasis (Local vs. Web):**
   - **Explicit Mention of Local Docs:** If the user says 'my papers,' 'in this folder,' 'my PDF collection,' or refers to specific authors they've collected, the agent must prioritize local document search.
     - *Parameters:* Significantly increase `initial_exploration_doc_results` and `main_research_doc_results`.
   - **Current Events or Web-Native Topics:** If the topic is a recent event, a tech product, or market trends, the agent must prioritize web search.
     - *Parameters:* Significantly increase `initial_exploration_web_results` and `main_research_web_results`.
   - **Mixed Sources:** A request combining historical theory with modern applications requires a balanced approach.
     - *Parameters:* Set both `doc_results` and `web_results` to high values.

### **Final Instruction:**
Critically analyze the provided `formatted_history` against these principles, with special attention to the **Guiding Principle**. Anchor your analysis in the user's direct messages and tone, not the agent's elaborations. Then, return only the JSON object with the determined parameters.

**Return a JSON object with the following keys and value ranges:**
- `initial_research_max_depth`: int (1-3)
- `initial_research_max_questions`: int (5-15)
- `structured_research_rounds`: int (1-3)
- `writing_passes`: int (2-4)
- `initial_exploration_doc_results`: int (2-5)
- `initial_exploration_web_results`: int (2-5)
- `main_research_doc_results`: int (2-7)
- `main_research_web_results`: int (2-5)
- `max_research_cycles_per_section`: int (1-4) - How many refinement cycles per section
- `max_total_iterations`: int (20-60) - Overall iteration limit
- `max_total_depth`: int (1-4) - Outline complexity
- `min_notes_per_section_assignment`: int (3-10) - Minimum coverage per section
- `max_notes_per_section_assignment`: int (20-60) - Maximum to prevent overload

---
### **Examples of Requests and Resulting Parameters**
---

#### **Scenario 1: Casual & Child-Oriented**

* **Conversation:** `User: "My daughter is asking me what a supernova is and how it works. Can you explain it in a simple way for an 8-year-old?"`
* **Analysis:** This is a simple, factual request. The complexity is low, and the tone is casual. The goal is a simple explanation, not a research paper. It requires minimal depth, few clarifying questions, and minimal refinement. The source will be exclusively web-based.
* **Resulting JSON Parameters:**
    ```json
    {{
        "initial_research_max_depth": 1,
        "initial_research_max_questions": 5,
        "structured_research_rounds": 1,
        "writing_passes": 2,
        "initial_exploration_doc_results": 2,
        "initial_exploration_web_results": 5,
        "main_research_doc_results": 2,
        "main_research_web_results": 4,
        "max_research_cycles_per_section": 1,
        "max_total_iterations": 20,
        "max_total_depth": 1,
        "min_notes_per_section_assignment": 3,
        "max_notes_per_section_assignment": 20
    }}
    ```

---

#### **Scenario 2: Broad Academic Exploration**

* **Conversation:** `User: "I'm a college sophomore starting a term paper for my sociology class. The topic is 'The Social Impact of the Internet.' It's pretty broad, so I need help understanding the main areas of debate and research. Can you give me an overview of the key themes, like its effect on community, politics, and identity?"`
* **Analysis:** This is a broad, exploratory request with a formal, academic context. The user needs to map out a large topic. This calls for a high number of initial questions to narrow down the scope and a wide initial web search for foundational sources. The research doesn't need to be incredibly deep yet, but the writing should be decent.
* **Resulting JSON Parameters:**
    ```json
    {{
        "initial_research_max_depth": 3,
        "initial_research_max_questions": 20,
        "structured_research_rounds": 2,
        "writing_passes": 3,
        "initial_exploration_doc_results": 2,
        "initial_exploration_web_results": 5,
        "main_research_doc_results": 7,
        "main_research_web_results": 5,
        "max_research_cycles_per_section": 2,
        "max_total_iterations": 40,
        "max_total_depth": 3,
        "min_notes_per_section_assignment": 5,
        "max_notes_per_section_assignment": 40
    }}
    ```

---

#### **Scenario 3: Narrow & Deep Professional/Technical Analysis**

* **Conversation:** `User: "I need to compare the performance characteristics of the new M3 MacBook Air with the Dell XPS 13, specifically for video editing workflows in DaVinci Resolve. Focus on export times for 4K H.265 footage, timeline scrubbing performance, and thermal throttling under sustained load. Get data from reputable tech review sites and forums."`
* **Analysis:** This is a narrow, deep, and technical request. The user knows exactly what they want. This requires very little initial exploration but many rounds of focused research to find specific data points and synthesize them. The output needs to be precise. Web results are paramount.
* **Resulting JSON Parameters:**
    ```json
    {{
        "initial_research_max_depth": 4,
        "initial_research_max_questions": 8,
        "structured_research_rounds": 4,
        "writing_passes": 3,
        "initial_exploration_doc_results": 2,
        "initial_exploration_web_results": 5,
        "main_research_doc_results": 2,
        "main_research_web_results": 10,
        "max_research_cycles_per_section": 3,
        "max_total_iterations": 50,
        "max_total_depth": 2,
        "min_notes_per_section_assignment": 8,
        "max_notes_per_section_assignment": 50
    }}
    ```

---

#### **Scenario 4: Complex Synthesis with Mixed Local & Web Sources**

* **Conversation:** `User: "I'm working on my dissertation. I need you to synthesize an argument about the influence of Stoic philosophy on modern Cognitive Behavioral Therapy (CBT). You need to heavily use my local document collection, which includes the complete works of Seneca and Epictetus, and several core CBT manuals in PDF. Please supplement this with recent peer-reviewed articles from PubMed and Google Scholar to trace the direct therapeutic lineages."`
* **Analysis:** This is a highly complex, analytical request combining historical texts with modern science. The user's tone is formal and the stakes are high (dissertation). The key feature is the heavy emphasis on the local document collection, supplemented by deep web-based academic research. This requires maximum depth, rounds, and writing refinement.
* **Resulting JSON Parameters:**
    ```json
    {{
        "initial_research_max_depth": 5,
        "initial_research_max_questions": 18,
        "structured_research_rounds": 4,
        "writing_passes": 3,
        "initial_exploration_doc_results": 5,
        "initial_exploration_web_results": 4,
        "main_research_doc_results": 7,
        "main_research_web_results": 5,
        "max_research_cycles_per_section": 4,
        "max_total_iterations": 60,
        "max_total_depth": 4,
        "min_notes_per_section_assignment": 10,
        "max_notes_per_section_assignment": 60
    }}
    ```

---

#### **Scenario 5: Urgent Professional Report**

* **Conversation:** `User: "We have an emergency board meeting on Monday. I need a concise but thorough report on the key market drivers and risks for renewable energy investments in Southeast Asia for the next 3 years. Focus on Vietnam and Indonesia. I need data on government subsidies, supply chain stability, and public-private partnership opportunities. The output should be a professional, data-driven brief."`
* **Analysis:** This request is professional, intense, and urgent. The scope is defined but complex, requiring significant data gathering from web sources (market reports, news). The research needs to be deep and multi-faceted (`structured_research_rounds` = 3). However, the urgency implies a need for a polished draft quickly, so `writing_passes` is high but not maxed out, prioritizing getting a usable, well-structured report over literary perfection.
* **Resulting JSON Parameters:**
    ```json
    {{
        "initial_research_max_depth": 4,
        "initial_research_max_questions": 15,
        "structured_research_rounds": 3,
        "writing_passes": 3,
        "initial_exploration_doc_results": 2,
        "initial_exploration_web_results": 5,
        "main_research_doc_results": 4,
        "main_research_web_results": 7,
        "max_research_cycles_per_section": 2,
        "max_total_iterations": 45,
        "max_total_depth": 3,
        "min_notes_per_section_assignment": 6,
        "max_notes_per_section_assignment": 45
    }}
    ```
    
**Provide your analysis based on the following Conversation:**
---
{formatted_history}
---
"""
    try:
        # Use the model dispatcher directly for this JSON generation task
        messages = [{"role": "user", "content": prompt}]
        response_format = {"type": "json_object"}
        
        response, _ = await controller.model_dispatcher.dispatch(
            messages=messages,
            response_format=response_format,
            agent_mode="planning"
        )
        
        if response and response.choices and response.choices[0].message.content:
            logger.info(f"AI returned raw parameters: {response.choices[0].message.content}")
            # Parse the JSON response using robust JSON utility
            params = parse_llm_json_response(response.choices[0].message.content)
            # Ensure auto_optimize_params is set correctly
            params['auto_optimize_params'] = True
            return params
    except Exception as e:
        logger.error(f"AI parameter generation failed: {e}", exc_info=True)
    return None

async def apply_auto_optimization(
    mission_id: str,
    current_user: User,
    context_mgr: ContextManager,
    controller: AgentController,
    chat_history: List[Any],
    log_queue=None,
    update_callback=None
) -> Optional[Dict[str, Any]]:
    """
    Apply auto-optimization logic and comprehensive logging for settings.
    Returns the final mission settings dict if optimization was applied, None otherwise.
    """
    try:
        user_settings = current_user.settings or {}
        research_params = user_settings.get("research_parameters", {})
        
        logger.info(f"Checking auto-optimization for mission {mission_id}. User auto_optimize_params: {research_params.get('auto_optimize_params')}")
        
        final_mission_settings_dict = None
        
        if research_params.get("auto_optimize_params"):
            logger.info(f"Auto-optimizing research parameters for mission {mission_id}.")
            final_mission_settings_dict = await determine_research_parameters(chat_history, controller)
            if not final_mission_settings_dict:
                logger.warning(f"AI parameter optimization failed for mission {mission_id}. Using default settings.")
        
        # Get current mission settings from metadata
        mission_context = context_mgr.get_mission_context(mission_id)
        existing_mission_settings = mission_context.metadata.get("mission_settings", {}) if mission_context and mission_context.metadata else {}
        
        # If we have new AI-generated settings, store them
        if final_mission_settings_dict:
            try:
                # Validate with Pydantic model before storing
                validated_settings = MissionSettings(**final_mission_settings_dict)
                context_mgr.update_mission_metadata(
                    mission_id, 
                    {"mission_settings": validated_settings.model_dump(exclude_none=True)}
                )
                logger.info(f"Stored AI-generated settings for mission {mission_id}: {validated_settings.model_dump(exclude_none=True)}")
                existing_mission_settings = validated_settings.model_dump(exclude_none=True)
            except Exception as pydantic_error:
                logger.error(f"Failed to validate/store AI-generated mission settings for {mission_id}: {pydantic_error}", exc_info=True)
                final_mission_settings_dict = None
        
        # Now get the effective settings using the dynamic config functions
        from ai_researcher.dynamic_config import (
            get_initial_research_max_depth, get_initial_research_max_questions,
            get_structured_research_rounds, get_writing_passes,
            get_initial_exploration_doc_results, get_initial_exploration_web_results,
            get_main_research_doc_results, get_main_research_web_results,
            get_thought_pad_context_limit, get_max_notes_for_assignment_reranking,
            get_max_concurrent_requests, get_skip_final_replanning,
            get_max_research_cycles_per_section, get_max_total_iterations,
            get_max_total_depth, get_min_notes_per_section_assignment,
            get_max_notes_per_section_assignment, get_max_planning_context_chars,
            get_writing_previous_content_preview_chars, get_research_note_content_limit
        )
        
        effective_settings = {
            "initial_research_max_depth": get_initial_research_max_depth(mission_id),
            "initial_research_max_questions": get_initial_research_max_questions(mission_id),
            "structured_research_rounds": get_structured_research_rounds(mission_id),
            "writing_passes": get_writing_passes(mission_id),
            "initial_exploration_doc_results": get_initial_exploration_doc_results(mission_id),
            "initial_exploration_web_results": get_initial_exploration_web_results(mission_id),
            "main_research_doc_results": get_main_research_doc_results(mission_id),
            "main_research_web_results": get_main_research_web_results(mission_id),
            "thought_pad_context_limit": get_thought_pad_context_limit(mission_id),
            "max_notes_for_assignment_reranking": get_max_notes_for_assignment_reranking(mission_id),
            "max_concurrent_requests": get_max_concurrent_requests(mission_id),
            "skip_final_replanning": get_skip_final_replanning(mission_id),
            # Advanced parameters now properly imported
            "max_research_cycles_per_section": get_max_research_cycles_per_section(mission_id),
            "max_total_iterations": get_max_total_iterations(mission_id),
            "max_total_depth": get_max_total_depth(mission_id),
            "min_notes_per_section_assignment": get_min_notes_per_section_assignment(mission_id),
            "max_notes_per_section_assignment": get_max_notes_per_section_assignment(mission_id),
            "max_planning_context_chars": get_max_planning_context_chars(mission_id),
            "writing_previous_content_preview_chars": get_writing_previous_content_preview_chars(mission_id),
            "research_note_content_limit": get_research_note_content_limit(mission_id)
        }
        
        # Create comprehensive log message
        log_message_parts = []
        
        # User default settings
        log_message_parts.append(f"**User Default Settings:**\n```json\n{json.dumps(research_params, indent=2)}\n```")
        
        # Mission-specific overrides
        if final_mission_settings_dict:
            log_message_parts.append(f"**Mission-Specific Overrides (AI-Generated):**\n```json\n{json.dumps(final_mission_settings_dict, indent=2)}\n```")
        elif existing_mission_settings:
            log_message_parts.append(f"**Mission-Specific Overrides (Manual):**\n```json\n{json.dumps(existing_mission_settings, indent=2)}\n```")
        else:
            log_message_parts.append("**Mission-Specific Overrides:** None")
        
        # Effective settings
        log_message_parts.append(f"**Effective Settings for this Mission:**\n```json\n{json.dumps(effective_settings, indent=2)}\n```")
        
        log_message = "\n\n".join(log_message_parts)
        
        # Log the settings configuration
        context_mgr.log_execution_step(
            mission_id=mission_id,
            agent_name="Configuration",
            action="Applying Research Parameters",
            output_summary=log_message,
            status="success",
            log_queue=log_queue,
            update_callback=update_callback
        )
        
        logger.info(f"Logged comprehensive settings for mission {mission_id}")
        
        return final_mission_settings_dict
        
    except Exception as e:
        logger.error(f"Failed to apply auto-optimization for mission {mission_id}: {e}", exc_info=True)
        # Log the failure
        context_mgr.log_execution_step(
            mission_id=mission_id,
            agent_name="Configuration",
            action="Applying Research Parameters",
            output_summary=f"Failed to apply settings optimization: {str(e)}",
            status="failure",
            error_message=str(e),
            log_queue=log_queue,
            update_callback=update_callback
        )
        return None
