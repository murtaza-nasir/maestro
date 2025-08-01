import logging
import json
from typing import Dict, Any, Optional, List, Tuple, Awaitable
from datetime import datetime

# Import the JSON utilities
from ai_researcher.agentic_layer.utils.json_utils import (
    parse_llm_json_response,
    sanitize_json_string
)

from ai_researcher.agentic_layer.agents.base_agent import BaseAgent, AgentOutput
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.schemas.messenger import MessengerResponse, IntentType
from ai_researcher.agentic_layer.schemas.thought import ThoughtEntry # Added import

logger = logging.getLogger(__name__)

class MessengerAgent(BaseAgent):
    """
    Agent responsible for interacting with the user, understanding intent,
    and deciding whether to initiate a research mission.
    """
    agent_name = "MessengerAgent"
    agent_description = "Handles user conversation and initiates research tasks."

    def __init__(self, model_dispatcher: ModelDispatcher, controller: Optional[Any] = None):
        self.model_dispatcher = model_dispatcher
        self.controller = controller # Store controller
        self.mission_id = None # Initialize mission_id as None

    async def run(
        self,
        user_message: str,
        chat_history: List[Tuple[str, str]],
        mission_context_summary: Optional[str] = None,
        active_thoughts: Optional[List[ThoughtEntry]] = None, # <-- NEW: Add active thoughts
        agent_scratchpad: Optional[str] = None,
        mission_id: Optional[str] = None,
        log_queue: Optional[Any] = None, # Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None, # Add update_callback parameter for UI updates
        **kwargs: Any
    ) -> AgentOutput:
        """
        Processes the user message, determines intent, and returns a response and action.

        Args:
            user_message: The latest message from the user.
            chat_history: The history of the conversation.
            mission_context_summary: Optional summary of the current mission state.
            active_thoughts: Optional list of recent thoughts from the thought pad.
            agent_scratchpad: Optional current scratchpad content.
            mission_id: Optional ID of the current mission.
            log_queue: Optional queue for logging.
            update_callback: Optional callback for UI updates.
            **kwargs: Additional keyword arguments.

        Returns:
            A dictionary containing:
            - "response": The text response to show the user.
            - "action": "start_research" or None.
            - "request": The extracted research request if action is "start_research".
        """
        # Store mission_id as instance attribute for the duration of this call
        # This allows _call_llm to access it for updating mission stats
        self.mission_id = mission_id
        
        logger.info(f"{self.agent_name} received message: '{user_message}'")

        # Prepare context for the LLM
        history_str = "\n".join([f"User: {u}\nAssistant: {a}" for u, a in chat_history])
        
        # Add mission context if available
        mission_context_block = ""
        if mission_context_summary:
            mission_context_block = f"""
Current Mission Context:
{mission_context_summary}
"""

        # Add scratchpad if available
        scratchpad_block = ""
        if agent_scratchpad:
            scratchpad_block = f"""
Agent Scratchpad (Your previous thoughts):
{agent_scratchpad}
"""
        # Add thoughts if available
        thoughts_block = ""
        if active_thoughts:
            thoughts_str = "\n".join([f"- [{t.timestamp.strftime('%Y-%m-%d %H:%M')}] {t.agent_name}: {t.content}" for t in active_thoughts])
            thoughts_block = f"""
Recent Thoughts (Consider these for context):
{thoughts_str}
"""

        # CORRECTED PROMPT: Minimal response for refine_questions
        # --- MODIFIED PROMPT START ---
        prompt = f"""You are a helpful research assistant interface. Your primary role during the initial conversation is to understand the user's research topic, manage the refinement of research questions, and detect when the user wants to start the actual research process.

**CRITICAL INSTRUCTION:** During the initial phases (before research questions are approved and the mission starts), you MUST NOT answer the user's questions directly using your own knowledge or attempt to fulfill requests like writing summaries, notes, or performing actions other than those specified below. Your ONLY functions are:
1.  Identify the user's intended research topic when they first state it (`start_research` intent).
2.  Acknowledge feedback on research questions (`refine_questions` intent).
3.  Recognize when the user approves the questions and wants to begin the research (`approve_questions` intent).
4.  Engage in simple clarification dialogue if the user's request is unclear, or answer basic questions *about the research process itself* (`chat` intent).

**DO NOT SYNTHESIZE ANSWERS OR PERFORM TASKS YOURSELF.** Your role is to facilitate the setup of the research mission.

**CRITICAL FORMATTING PREFERENCE DETECTION:** You MUST carefully analyze the user's message for any formatting preferences such as:
- Desired output length (e.g., "keep it short", "brief summary", "comprehensive report")
- Tone preferences (e.g., "informal tone", "academic style", "write like a 5th grader")
- Format specifications (e.g., "no subsections", "bullet points only", "one section")
- Audience indications (e.g., "for general public", "for experts")

If you detect ANY formatting preferences, you MUST extract them as part of the `refine_goal` intent, even if the message also contains a research topic or question feedback.

{mission_context_block}
Current Conversation History:
{history_str}
User: {user_message}
{thoughts_block}
{scratchpad_block}

Analyze the user's latest message in the context of the conversation, mission context, recent thoughts, and scratchpad.

1. **Determine Intent:** Identify what the user wants:
   - "start_research": User wants to start a new research task.
   - "refine_questions": User is providing feedback *ONLY about the wording, number, or focus of the previously proposed research questions*. **This intent MUST NOT be used if the feedback is about the final output format, length, or overall scope.**
   - "refine_goal": User is providing feedback about the *overall research objective, desired output format (e.g., 'short note', 'full paper', 'brief summary'), scope, constraints, or other high-level goals*. **Use this intent for feedback concerning the length or type of the final document.**
   - "approve_questions": User approves the proposed research questions and wants to proceed with the actual research (e.g., "looks good", "proceed", "yes", "go ahead", "start the research", "let's begin", "ok").
   - "chat": General conversation or questions about the system.

2. **Extract Information:**
   - If "start_research": Extract the core research topic or question. **IMPORTANT: If the message also contains formatting preferences (e.g., "keep it short", "informal tone"), you MUST ALSO extract these as a separate `formatting_preferences` field.**
   - If "refine_questions": **CRITICAL: Extract the specific feedback *on the questions themselves***. The `extracted_content` MUST NOT be null or empty for this intent.
   - If "refine_goal": **CRITICAL: Extract the core feedback *on the overall goal, scope, or output format/length*** (e.g., "write in the tone of a fifth grader", "provide a short document"). The `extracted_content` MUST NOT be null or empty for this intent.
   - If "approve_questions": Set `extracted_content` to null.
   - If "chat": Set `extracted_content` to null.

3. **Generate Response:**
   - If "start_research": Acknowledge that you'll help research the topic and that the next step is generating questions.
   - If "refine_questions": Provide a *minimal* acknowledgment (e.g., "Okay, processing your feedback on the questions..."). Do NOT attempt to refine or display questions yourself.
   - If "refine_goal": Acknowledge that you've noted the feedback on the overall goal/scope (e.g., "Okay, I've noted your preference for [brief summary of feedback, e.g., 'a short note'].").
   - If "approve_questions": Confirm that the research process will now begin with the approved questions.
   - If "chat": Provide a helpful, conversational response *related to the research setup process* or clarify the user's request. If the user asks a question you are forbidden from answering, politely state that your role is to set up the research and you cannot answer directly, then guide them back to defining the topic or refining questions/goals.

**Output Format:** Respond ONLY with a valid JSON object containing the following keys. Ensure all strings are properly quoted and that there is a comma `,` separating each key-value pair (except the last one).
* `intent`: (string) "start_research", "refine_questions", "refine_goal", "approve_questions", or "chat"
* `extracted_content`: (string or null) The extracted research topic or feedback. **MUST be populated** if intent is `start_research`, `refine_questions`, or `refine_goal`. MUST be `null` if intent is `approve_questions` or `chat`.
* `formatting_preferences`: (string or null) Any detected formatting preferences like tone, length, format, or audience. **MUST be populated** if any formatting preferences are detected, regardless of the primary intent.
* `response_to_user`: (string) The text response to show the user
* `thoughts`: (string) Your analysis of the user's message and reasoning (not shown to user)

Example 1 (Start Research Intent):
User: Tell me about the latest advancements in quantum computing.
Output:
```json
{{
  "intent": "start_research",
  "extracted_content": "latest advancements in quantum computing",
  "formatting_preferences": null,
  "response_to_user": "Okay, I can help you research that. I'll now generate some initial research questions for us to review.",
  "thoughts": "The user wants to start research on quantum computing advancements. This is a clear research request. My role is to acknowledge this and hand off to the Research Agent to generate high-quality initial questions."
}}
```

Example 2 (Start Research with Formatting Preferences):
User: What theoretical frameworks can integrate insights from behavioral economics, information processing theory, and system dynamics to explain and predict how dashboard design characteristics influence managerial attention allocation and strategic decision-making in data-rich environments? keep it super short and informal. dont make a lot of sections, just one section with no subsections.
Output:
```json
{{
  "intent": "start_research",
  "extracted_content": "theoretical frameworks that integrate insights from behavioral economics, information processing theory, and system dynamics to explain and predict how dashboard design characteristics influence managerial attention allocation and strategic decision-making in data-rich environments",
  "formatting_preferences": "keep it super short and informal, one section with no subsections",
  "response_to_user": "Okay, I can help you research that. I've noted your preference for a super short, informal output with just one section. I'll now generate some initial research questions for us to review.",
  "thoughts": "The user wants to start research on a complex topic and has provided specific formatting preferences. I will acknowledge both and hand off to the Research Agent for question generation."
}}
```

Example 3 (Refine Questions Intent):
User: The second question is too broad, and I'd like to focus more on practical applications rather than theory.
Output:
```json
{{
  "intent": "refine_questions",
  "extracted_content": "second question too broad, focus more on practical applications rather than theory",
  "formatting_preferences": null,
  "response_to_user": "Okay, processing your feedback on the questions...",
  "thoughts": "The user is providing feedback specifically about the generated questions. Intent is refine_questions."
}}
```

Example 4 (Refine Goal Intent):
User: yes but I don't want a full paper. I want you to note in your goals to provide me a short document, not something lengthy
Output:
```json
{{
  "intent": "refine_goal",
  "extracted_content": "provide me a short document, not something lengthy",
  "formatting_preferences": null,
  "response_to_user": "Okay, I've noted your preference for a short document rather than a full paper.",
  "thoughts": "The user is specifying the desired output format/length. This is feedback on the overall goal. Intent is refine_goal. I must extract the core feedback."
}}
```

Example 5 (Refine Goal - Tone):
User: Make sure to write the report in the tone of a fifth grader.
Output:
```json
{{
  "intent": "refine_goal",
  "extracted_content": "write the report in the tone of a fifth grader",
  "formatting_preferences": null,
  "response_to_user": "Okay, I've noted your preference for the report to be written in the tone of a fifth grader.",
  "thoughts": "The user is specifying the desired output tone. This is feedback on the overall goal. Intent is refine_goal. I must extract the core feedback about the tone."
}}
```

Example 6 (Approve Questions Intent):
User: Those questions look good, go ahead.
Output:
```json
{{
  "intent": "approve_questions",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "Great! I'll now start the research process with the approved questions. This may take a moment.",
  "thoughts": "The user has approved the questions and wants to proceed. My role is to confirm this and hand off control."
}}
```

Example 7 (Chat Intent):
User: How does this system work?
Output:
```json
{{
  "intent": "chat",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "This system helps you conduct research by first defining a topic, then refining specific research questions, and finally executing a research plan to gather and synthesize information into a report. How can I help you set up your research today?",
  "thoughts": "The user is asking about system functionality. I should explain the process briefly and guide them back to starting the research setup."
}}
```

Example 8 (Forbidden Request):
User: Can you just give me a quick summary of those governance mechanisms now?
Output:
```json
{{
  "intent": "chat",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "My current role is to help set up the research plan by defining the topic and refining questions. I can't provide summaries directly at this stage. Shall we continue defining the research questions?",
  "thoughts": "The user is asking for a summary, which I am explicitly forbidden from providing during the setup phase. I need to politely decline and redirect them to the task at hand (defining/refining questions)."
}}
```
# --- MODIFIED PROMPT END ---

Now, analyze the last user message and provide the JSON output.
User: {user_message}
Output:
```json
"""

        llm_response_content = None
        model_details = None
        parsed_output = None
        final_response = "Sorry, I couldn't process that request."
        final_action = None
        final_request = None
        formatting_preferences = None  # Initialize formatting_preferences
        scratchpad_update = None # Initialize here

        try:
            # Using a simple model suitable for intent detection/chat
            response, model_details = await self.model_dispatcher.dispatch(
                messages=[{"role": "user", "content": prompt}],
                agent_mode="messenger", # Use the configured messenger role
                log_queue=log_queue, # Pass log_queue for UI updates
                update_callback=update_callback # Pass update_callback for UI updates
            )

            if response and response.choices and response.choices[0].message.content:
                llm_response_content = response.choices[0].message.content.strip()
                # Extract JSON block
                json_match = llm_response_content.find('{')
                if json_match != -1:
                    json_str = llm_response_content[json_match:]
                    # Clean up potential markdown fences using our centralized utility
                    json_str = sanitize_json_string(json_str)

                    try:
                        # Use the centralized JSON utilities to parse the response
                        json_data = parse_llm_json_response(json_str)
                        
                        # Extract data from JSON
                        intent = json_data.get("intent")
                        extracted_content = json_data.get("extracted_content")
                        formatting_preferences = json_data.get("formatting_preferences")  # Extract formatting preferences
                        response_to_user = json_data.get("response_to_user")
                        thoughts = json_data.get("thoughts")

                        # Set the response to show to the user
                        final_response = response_to_user

                        # Map intents to actions
                        if intent == "start_research" and extracted_content:
                            final_action = "start_research"
                            final_request = extracted_content
                            logger.info(f"Detected start_research intent. Request: '{final_request}'")
                            
                            # Handle formatting preferences if present
                            if formatting_preferences:
                                logger.info(f"Detected formatting preferences with start_research: '{formatting_preferences}'")
                                # Store formatting preferences to be added as a goal later
                                if self.controller and self.mission_id:
                                    try:
                                        # Add formatting preferences as a separate goal
                                        goal_id = self.controller.context_manager.add_goal(
                                            mission_id=self.mission_id,
                                            text=formatting_preferences,
                                            source_agent=self.agent_name
                                        )
                                        if goal_id:
                                            logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                    except Exception as e:
                                        logger.error(f"Failed to add formatting preferences as goal: {e}")
                                
                        elif intent == "refine_questions" and extracted_content:
                            final_action = "refine_questions"
                            final_request = extracted_content
                            logger.info(f"Detected refine_questions intent. Feedback: '{final_request}'")
                            
                            # Handle formatting preferences if present with refine_questions
                            if formatting_preferences and self.controller and self.mission_id:
                                logger.info(f"Detected formatting preferences with refine_questions: '{formatting_preferences}'")
                                try:
                                    # Add formatting preferences as a separate goal
                                    goal_id = self.controller.context_manager.add_goal(
                                        mission_id=self.mission_id,
                                        text=formatting_preferences,
                                        source_agent=self.agent_name
                                    )
                                    if goal_id:
                                        logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                except Exception as e:
                                    logger.error(f"Failed to add formatting preferences as goal: {e}")
                                
                        elif intent == "refine_goal" and extracted_content:
                            final_action = "refine_goal"
                            final_request = extracted_content
                            logger.info(f"Detected refine_goal intent. Goal: '{final_request}'")
                            
                            # For refine_goal, the extracted_content already contains the formatting preferences
                            # But if there are additional formatting preferences, handle them too
                            if formatting_preferences and formatting_preferences != extracted_content and self.controller and self.mission_id:
                                logger.info(f"Detected additional formatting preferences with refine_goal: '{formatting_preferences}'")
                                try:
                                    # Add additional formatting preferences as a separate goal
                                    goal_id = self.controller.context_manager.add_goal(
                                        mission_id=self.mission_id,
                                        text=formatting_preferences,
                                        source_agent=self.agent_name
                                    )
                                    if goal_id:
                                        logger.info(f"Added additional formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                except Exception as e:
                                    logger.error(f"Failed to add additional formatting preferences as goal: {e}")
                                
                        elif intent == "approve_questions":
                            final_action = "approve_questions"
                            final_request = None
                            logger.info("Detected approve_questions intent.")
                            
                            # Handle formatting preferences if present with approve_questions
                            if formatting_preferences and self.controller and self.mission_id:
                                logger.info(f"Detected formatting preferences with approve_questions: '{formatting_preferences}'")
                                try:
                                    # Add formatting preferences as a separate goal
                                    goal_id = self.controller.context_manager.add_goal(
                                        mission_id=self.mission_id,
                                        text=formatting_preferences,
                                        source_agent=self.agent_name
                                    )
                                    if goal_id:
                                        logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                except Exception as e:
                                    logger.error(f"Failed to add formatting preferences as goal: {e}")
                                
                        else:
                            logger.info(f"Detected {intent} intent or failed to extract content.")
                            
                            # Handle formatting preferences for chat intent too
                            if formatting_preferences and self.controller and self.mission_id:
                                logger.info(f"Detected formatting preferences with {intent} intent: '{formatting_preferences}'")
                                try:
                                    # Add formatting preferences as a separate goal
                                    goal_id = self.controller.context_manager.add_goal(
                                        mission_id=self.mission_id,
                                        text=formatting_preferences,
                                        source_agent=self.agent_name
                                    )
                                    if goal_id:
                                        logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                except Exception as e:
                                    logger.error(f"Failed to add formatting preferences as goal: {e}")
                            
                        # Store thoughts in scratchpad if available
                        if thoughts:
                            # Format the scratchpad entry with timestamp
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Combine with existing scratchpad if available
                            if agent_scratchpad:
                                scratchpad_update = f"{agent_scratchpad}\n\n[{timestamp}] {thoughts}"
                            else:
                                scratchpad_update = f"[{timestamp}] {thoughts}"

                    except json.JSONDecodeError as json_e:
                        logger.warning(f"Initial JSON parsing failed: {json_e}. Attempting simple fix for missing comma.")
                        # Attempt simple fix: Insert comma before last '}' if likely missing
                        fixed_json_str = json_str.strip()
                        if "Expecting ',' delimiter" in str(json_e) and fixed_json_str.endswith('}') and not fixed_json_str.endswith(',}') and not fixed_json_str.endswith('{'):
                             # Find the last key-value pair ending quote or bracket/brace
                             last_quote_idx = fixed_json_str.rfind('"')
                             last_bracket_idx = fixed_json_str.rfind(']')
                             last_inner_brace_idx = fixed_json_str.rfind('}', 0, len(fixed_json_str) - 1) # Exclude the final brace
                             
                             # Find the index right before the final '}'
                             insertion_point = len(fixed_json_str) - 1
                             
                             # Check if the character before '}' is likely the end of a value
                             char_before_brace = fixed_json_str[insertion_point -1].strip()
                             if char_before_brace in ('"', ']', '}') or char_before_brace.isdigit():
                                  fixed_json_str = fixed_json_str[:insertion_point] + ',' + fixed_json_str[insertion_point:]
                                  logger.info("Attempting re-parse with added comma before final '}'.")
                                  try:
                                      # Re-attempt parsing with the fix
                                      json_data = json.loads(fixed_json_str, strict=False)
                                      
                                      # Extract data from JSON
                                      intent = json_data.get("intent")
                                      extracted_content = json_data.get("extracted_content")
                                      formatting_preferences = json_data.get("formatting_preferences")  # Extract formatting preferences
                                      response_to_user = json_data.get("response_to_user")
                                      thoughts = json_data.get("thoughts")
                                      
                                      final_response = response_to_user

                                      if intent == "start_research" and extracted_content:
                                          final_action = "start_research"
                                          final_request = extracted_content
                                          logger.info(f"Detected start_research intent. Request: '{final_request}'")
                                          
                                          # Handle formatting preferences if present
                                          if formatting_preferences:
                                              logger.info(f"Detected formatting preferences with start_research: '{formatting_preferences}'")
                                              # Store formatting preferences to be added as a goal later
                                              if self.controller and self.mission_id:
                                                  try:
                                                      # Add formatting preferences as a separate goal
                                                      goal_id = self.controller.context_manager.add_goal(
                                                          mission_id=self.mission_id,
                                                          text=formatting_preferences,
                                                          source_agent=self.agent_name
                                                      )
                                                      if goal_id:
                                                          logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                                  except Exception as e:
                                                      logger.error(f"Failed to add formatting preferences as goal: {e}")
                                              
                                      elif intent == "refine_questions" and extracted_content:
                                          final_action = "refine_questions"
                                          final_request = extracted_content
                                          logger.info(f"Detected refine_questions intent. Feedback: '{final_request}'")
                                          
                                          # Handle formatting preferences if present with refine_questions
                                          if formatting_preferences and self.controller and self.mission_id:
                                              logger.info(f"Detected formatting preferences with refine_questions: '{formatting_preferences}'")
                                              try:
                                                  # Add formatting preferences as a separate goal
                                                  goal_id = self.controller.context_manager.add_goal(
                                                      mission_id=self.mission_id,
                                                      text=formatting_preferences,
                                                      source_agent=self.agent_name
                                                  )
                                                  if goal_id:
                                                      logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                              except Exception as e:
                                                  logger.error(f"Failed to add formatting preferences as goal: {e}")
                                              
                                      elif intent == "refine_goal" and extracted_content:
                                          final_action = "refine_goal"
                                          final_request = extracted_content
                                          logger.info(f"Detected refine_goal intent. Goal: '{final_request}'")
                                          
                                          # For refine_goal, the extracted_content already contains the formatting preferences
                                          # But if there are additional formatting preferences, handle them too
                                          if formatting_preferences and formatting_preferences != extracted_content and self.controller and self.mission_id:
                                              logger.info(f"Detected additional formatting preferences with refine_goal: '{formatting_preferences}'")
                                              try:
                                                  # Add additional formatting preferences as a separate goal
                                                  goal_id = self.controller.context_manager.add_goal(
                                                      mission_id=self.mission_id,
                                                      text=formatting_preferences,
                                                      source_agent=self.agent_name
                                                  )
                                                  if goal_id:
                                                      logger.info(f"Added additional formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                              except Exception as e:
                                                  logger.error(f"Failed to add additional formatting preferences as goal: {e}")
                                              
                                      elif intent == "approve_questions":
                                          final_action = "approve_questions"
                                          final_request = None
                                          logger.info("Detected approve_questions intent.")
                                          
                                          # Handle formatting preferences if present with approve_questions
                                          if formatting_preferences and self.controller and self.mission_id:
                                              logger.info(f"Detected formatting preferences with approve_questions: '{formatting_preferences}'")
                                              try:
                                                  # Add formatting preferences as a separate goal
                                                  goal_id = self.controller.context_manager.add_goal(
                                                      mission_id=self.mission_id,
                                                      text=formatting_preferences,
                                                      source_agent=self.agent_name
                                                  )
                                                  if goal_id:
                                                      logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                              except Exception as e:
                                                  logger.error(f"Failed to add formatting preferences as goal: {e}")
                                              
                                      else:
                                          logger.info(f"Detected {intent} intent or failed to extract content.")
                                          
                                          # Handle formatting preferences for chat intent too
                                          if formatting_preferences and self.controller and self.mission_id:
                                              logger.info(f"Detected formatting preferences with {intent} intent: '{formatting_preferences}'")
                                              try:
                                                  # Add formatting preferences as a separate goal
                                                  goal_id = self.controller.context_manager.add_goal(
                                                      mission_id=self.mission_id,
                                                      text=formatting_preferences,
                                                      source_agent=self.agent_name
                                                  )
                                                  if goal_id:
                                                      logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                                              except Exception as e:
                                                  logger.error(f"Failed to add formatting preferences as goal: {e}")
                                      
                                      if thoughts:
                                          timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                          if agent_scratchpad:
                                              scratchpad_update = f"{agent_scratchpad}\n\n[{timestamp}] {thoughts}"
                                          else:
                                              scratchpad_update = f"[{timestamp}] {thoughts}"
                                      
                                      # If we reached here, the fix worked, skip the original error handling
                                      logger.info("JSON parsing successful after simple fix.")
                                  except Exception as retry_e:
                                      logger.error(f"Failed to parse JSON even after fix: {retry_e}")
                                      final_response = "Sorry, I had trouble understanding the format of my own thoughts."
                             else:
                                  logger.error(f"JSON parsing failed and simple fix not applicable: {json_e}")
                                  final_response = "Sorry, I had trouble understanding the format of my own thoughts."
                        else:
                             logger.error(f"JSON parsing failed: {json_e}")
                             final_response = "Sorry, I had trouble understanding the format of my own thoughts."
                else:
                    logger.error(f"Could not find JSON block in LLM response: {llm_response_content}")
                    final_response = "Sorry, I couldn't structure my response correctly."
            else:
                logger.error("LLM response was empty or invalid.")
                final_response = "Sorry, I received an empty response from the language model."
        except Exception as e:
            # Handle authentication and other API errors with user-friendly messages
            from ai_researcher.agentic_layer.utils.error_messages import handle_api_error
            
            logger.error(f"Error during MessengerAgent LLM call: {e}", exc_info=True)
            final_response = handle_api_error(e)

        # Construct the final output dictionary expected by AgentController
        agent_result = {
            "response": final_response,
            "action": final_action,
            "request": final_request,
            "formatting_preferences": formatting_preferences  # Include formatting_preferences in the result
        }

        # Return AgentOutput tuple (result_dict, model_details, scratchpad_update)
        # Now includes scratchpad_update if thoughts were captured
        return agent_result, model_details, scratchpad_update
