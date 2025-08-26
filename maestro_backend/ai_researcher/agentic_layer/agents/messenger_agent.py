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

        # Load the prompt from the file
        lang = kwargs.get("lang", "en")
        prompt_path = f"maestro_backend/ai_researcher/prompts/messenger_agent_system_prompt_{lang}.txt"
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            logger.warning(f"Prompt file not found for language '{lang}', falling back to English.")
            prompt_path = "maestro_backend/ai_researcher/prompts/messenger_agent_system_prompt_en.txt"
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

        prompt = prompt_template.format(
            mission_context_block=mission_context_block,
            history_str=history_str,
            user_message=user_message,
            thoughts_block=thoughts_block,
            scratchpad_block=scratchpad_block,
        )

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
