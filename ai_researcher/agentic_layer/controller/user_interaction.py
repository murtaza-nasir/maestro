import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
import queue
import json

from ai_researcher.config import THOUGHT_PAD_CONTEXT_LIMIT
from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry
from ai_researcher.agentic_layer.schemas.analysis import RequestAnalysisOutput

logger = logging.getLogger(__name__)

class UserInteractionManager:
    """
    Manages user interactions, including message handling, request analysis,
    and question refinement.
    """
    
    def __init__(self, controller):
        """
        Initialize the UserInteractionManager with a reference to the AgentController.
        
        Args:
            controller: The AgentController instance
        """
        self.controller = controller
        
    async def analyze_request_type(
        self,
        mission_id: str,
        user_request: str,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, ExecutionLogEntry], None]] = None
    ) -> Optional[RequestAnalysisOutput]:
        """
        Analyzes the user request to determine type, tone, and audience using an LLM call,
        considering any pre-existing goals for the mission.
        """
        logger.info(f"Analyzing request type for mission {mission_id}, considering existing goals...")

        # Fetch existing goals
        active_goals = self.controller.context_manager.get_active_goals(mission_id)
        goals_context = "\nExisting Mission Goals (Consider these, especially user preferences):\n---\n"
        
        # Extract goal texts for both prompt and structured input
        goal_texts = []
        if active_goals:
            for goal in active_goals:
                goal_text = None
                if hasattr(goal, 'text'):
                    goal_text = goal.text
                elif isinstance(goal, str):
                    goal_text = goal
                else:
                    goal_text = str(goal)
                    
                goals_context += f"- {goal_text}\n"
                goal_texts.append(goal_text)
        else:
            goals_context += "No existing goals found.\n"
        goals_context += "---\n"

        # Define the prompt for the analysis LLM call, now including goals
        analysis_prompt = f"""
Analyze the following user research request, considering any existing mission goals provided, to determine its primary type, the appropriate tone for the output, the likely target audience, the requested length, the requested format, and any preferred source types.

**CRITICAL:** If the 'Existing Mission Goals' specify a particular tone, audience, length, format, output style, or source type preference (e.g., "write in 5th grader tone", "target audience: general public", "output: short summary", "format: bullet points", "use academic literature sources"), **you MUST prioritize that user preference** in your determination below, even if the raw 'User Research Request' text suggests something different (e.g., a formal academic topic).

Existing Mission Goals:
---
{goals_context}

User Research Request:
---
{user_request}
---

Instructions:
**CRITICAL PRIORITIZATION:**
- If 'Existing Mission Goals' contain specific instructions about the desired TONE (e.g., "write like a 5th grader", "use formal language"), you **MUST** select that exact `target_tone`.
- If 'Existing Mission Goals' contain specific instructions about the intended AUDIENCE (e.g., "explain for the general public", "target audience: experts"), you **MUST** select that exact `target_audience`.
- If 'Existing Mission Goals' contain specific instructions about the desired LENGTH (e.g., "brief summary", "comprehensive report"), you **MUST** select that exact `requested_length`.
- If 'Existing Mission Goals' contain specific instructions about the desired FORMAT (e.g., "bullet points", "full paper"), you **MUST** select that exact `requested_format`.
- If 'Existing Mission Goals' or 'User Research Request' contain specific instructions about PREFERRED SOURCE TYPES (e.g., "use academic literature", "prioritize legal sources", "focus on state law"), you **MUST** extract and include these in `preferred_source_types`.
- These explicit user preferences from the goals **OVERRIDE** any interpretation based solely on the 'User Research Request' text.

1.  **Classify Request Type:** Determine the most appropriate classification for the request. The value should be a concise string. Examples include:
    - "Academic Literature Review"
    - "Informal Explanation"
    - "General Web Search Summary"
    - "Technical Comparison"
    - "Creative Writing"
    - "Code Generation"
    - "Data Analysis"
    *You are not limited to these examples. Provide the most accurate classification based on the request.*
2.  **Determine Target Tone:** Determine the most appropriate tone for the final output, prioritizing any tone specified in the 'Existing Mission Goals'. The value should be a concise string. Examples include:
    - "Formal Academic"
    - "Neutral/Objective"
    - "Informal/Conversational"
    - "Technical"
    - "Creative"
    - "5th Grader" (Example of a specific user goal)
    *You are not limited to these examples. Provide the most accurate tone, especially if specified by the user.*
3.  **Identify Target Audience:** Determine the most likely intended audience, prioritizing any audience specified in the 'Existing Mission Goals'. The value should be a concise string. Examples include:
    - "Researchers/Experts"
    - "General Public"
    - "Technical Team"
    - "Students"
    - "Specific Stakeholder" (e.g., "Marketing Department")
    *You are not limited to these examples. Provide the most accurate audience, especially if specified by the user.*
4.  **Determine Requested Length:** Determine the most appropriate length for the final output, prioritizing any length specified in the 'Existing Mission Goals'. The value should be a concise string. Examples include:
    - "Short Summary"
    - "Comprehensive Report"
    - "Brief Paragraph"
    - "Extended Analysis"
    - "Concise Overview"
    *You are not limited to these examples. Provide the most accurate length, especially if specified by the user.*
5.  **Determine Requested Format:** Determine the most appropriate format for the final output, prioritizing any format specified in the 'Existing Mission Goals'. The value should be a concise string. Examples include:
    - "Full Paper"
    - "Bullet Points"
    - "Summary Paragraph"
    - "Q&A Format"
    - "Structured Report"
    - "Comparative Table"
    *You are not limited to these examples. Provide the most accurate format, especially if specified by the user.*
6.  **Identify Preferred Source Types:** Identify any specific source types the user wants to prioritize or focus on. The value should be a concise string. Examples include:
    - "Academic Literature"
    - "Legal Sources"
    - "State Law"
    - "News Articles"
    - "Government Reports"
    - "Scientific Journals"
    - "Industry Publications"
    *You are not limited to these examples. Provide the most accurate source type preferences, especially if specified by the user.*
7.  **Provide Reasoning:** Briefly explain your choices for type, tone, audience, length, format, and preferred source types, referencing specific goals if they influenced your decision.

Output ONLY a single JSON object conforming EXACTLY to the RequestAnalysisOutput schema. Ensure your choices reflect any user preferences found in the 'Existing Mission Goals'. The values for all fields should be strings, but do not have to be chosen from the examples provided above if a different string is more accurate.
```json
{{
  "request_type": "...", // A string describing the request type (can be custom)
  "target_tone": "...", // A string describing the target tone (PRIORITIZE user preference from goals, can be custom)
  "target_audience": "...", // A string describing the target audience (PRIORITIZE user preference from goals, can be custom)
  "requested_length": "...", // A string describing the requested length (PRIORITIZE user preference from goals, can be custom)
  "requested_format": "...", // A string describing the requested format (PRIORITIZE user preference from goals, can be custom)
  "preferred_source_types": "...", // A string describing preferred source types (PRIORITIZE user preference from goals/request, can be custom)
  "analysis_reasoning": "Brief justification for the choices."
}}
```
"""
        # Create a structured message that includes both the user request and goal texts
        messages = [
            {"role": "system", "content": "Consider these active goals when analyzing the request: " + json.dumps({"active_goals": goal_texts})},
            {"role": "user", "content": analysis_prompt}
        ]
        # Add the 'name' field required by some providers (like Azure via OpenRouter)
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "request_analysis_output",
                "schema": RequestAnalysisOutput.model_json_schema()  # Nest the schema under the 'schema' key
            }
        }
        analysis_result: Optional[RequestAnalysisOutput] = None
        model_details = None

        try:
            # Use a model suitable for analysis and instruction following (planning model is good)
            async with self.controller.maybe_semaphore:
                response, model_details = await self.controller.model_dispatcher.dispatch(
                    messages=messages,
                    response_format=response_format,
                    agent_mode="planning"  # Use planning model for structured output and instruction following
                )

            if response and response.choices and response.choices[0].message.content:
                raw_json = response.choices[0].message.content
                try:
                    analysis_result = RequestAnalysisOutput.model_validate_json(raw_json)
                    logger.info(f"Request analysis successful for mission {mission_id}: Type={analysis_result.request_type}, Tone={analysis_result.target_tone}, Audience={analysis_result.target_audience}")
                    log_status = "success"
                    error_msg = None
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse/validate request analysis JSON for mission {mission_id}: {e}\nRaw: {raw_json}")
                    log_status = "failure"
                    error_msg = f"JSON Parse/Validation Error: {e}"
            else:
                logger.error(f"Request analysis LLM call failed or returned empty content for mission {mission_id}.")
                log_status = "failure"
                error_msg = "LLM call failed or returned empty content."

        except Exception as e:
            logger.error(f"Error during request analysis LLM call for mission {mission_id}: {e}", exc_info=True)
            log_status = "failure"
            error_msg = f"Exception during analysis: {e}"

        # Log the analysis step
        self.controller.context_manager.log_execution_step(
            mission_id=mission_id,
            agent_name="AgentController",
            action="Analyze Request Type",
            input_summary=f"User Request: {user_request[:60]}..., Goals Provided: {len(active_goals) if active_goals else 0}",
            output_summary=(f"Type: {analysis_result.request_type}, Tone: {analysis_result.target_tone}, Audience: {analysis_result.target_audience}" if analysis_result else "Analysis failed.") if log_status == "success" else error_msg,
            status=log_status,
            error_message=error_msg,
            full_input={"user_request": user_request, "active_goals": goal_texts},
            full_output=analysis_result.model_dump() if analysis_result else None,
            model_details=model_details,
            log_queue=log_queue,
            update_callback=update_callback
        )

        # Update stats (Now handled by ContextManager)
        if model_details:
            self.controller.context_manager.update_mission_stats(mission_id, model_details, log_queue, update_callback)

        return analysis_result

    async def handle_user_message(
        self,
        user_message: str,
        chat_history: List[Tuple[str, str]],
        mission_id: Optional[str] = None,
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ) -> Dict[str, Any]:
        """
        Handles a user message using the MessengerAgent.
        Returns a dictionary containing the agent's response and potential actions.
        """
        logger.info(f"Handling user message via MessengerAgent: '{user_message[:50]}...'")
        # Fetch relevant context if needed (e.g., current mission status, plan summary)
        mission_context_summary = None
        if mission_id:
            context = self.controller.context_manager.get_mission_context(mission_id)
            if context:
                mission_context_summary = f"Current Mission ({mission_id}): Status={context.status}"
                if context.plan:
                    mission_context_summary += f", Goal='{context.plan.mission_goal[:50]}...'"

        # Fetch current scratchpad
        current_scratchpad = self.controller.context_manager.get_scratchpad(mission_id) if mission_id else None
        # Fetch Active Goals & Thoughts
        active_goals = self.controller.context_manager.get_active_goals(mission_id) if mission_id else None
        active_thoughts = self.controller.context_manager.get_recent_thoughts(mission_id, limit=THOUGHT_PAD_CONTEXT_LIMIT) if mission_id else None

        try:
            # Apply Semaphore
            async with self.controller.maybe_semaphore:
                # Call the MessengerAgent's run method
                agent_output, model_details, scratchpad_update = await self.controller.messenger_agent.run(
                    user_message=user_message,
                    chat_history=chat_history,
                    mission_context_summary=mission_context_summary,
                    active_goals=active_goals,
                    active_thoughts=active_thoughts,
                    agent_scratchpad=current_scratchpad,
                    mission_id=mission_id,
                    log_queue=log_queue,
                    update_callback=update_callback
                )

            # Update scratchpad if the agent provided an update and mission_id exists
            if scratchpad_update and mission_id:
                self.controller.context_manager.update_scratchpad(mission_id, scratchpad_update)
                logger.info(f"Updated scratchpad after MessengerAgent interaction for mission {mission_id}.")

            if not agent_output:
                raise ValueError("MessengerAgent returned None")

            # Log the interaction
            self.controller.context_manager.log_execution_step(
                mission_id=mission_id or "N/A",  # Use N/A if no mission context
                agent_name=self.controller.messenger_agent.agent_name,
                action="Handle User Message",
                input_summary=f"User: {user_message[:60]}...",
                output_summary=f"Agent: {agent_output.get('response', '')[:60]}... Action: {agent_output.get('action')}",
                status="success",
                full_input={"user_message": user_message, "history_len": len(chat_history), "context_summary": mission_context_summary},
                full_output=agent_output,
                model_details=model_details,
            )

            # Intercept and Handle Actions
            action = agent_output.get("action")
            request_content = agent_output.get("request")  # This holds the feedback/goal text
            original_user_message_for_goal = user_message  # Capture the original message
            formatting_preferences = agent_output.get("formatting_preferences")  # Extract formatting preferences if present

            # Handle start_research action - Create mission and check for formatting preferences
            if action == "start_research" and request_content:
                logger.info(f"Handling 'start_research' action. Request: '{request_content[:60]}...'")
                # Create mission first
                mission_context = self.controller.context_manager.start_mission(user_request=request_content)
                mission_id = mission_context.mission_id
                logger.info(f"Created new mission with ID: {mission_id}")
                
                # Now check if there were formatting preferences in the agent output
                if formatting_preferences:
                    goal_id = self.controller.context_manager.add_goal(
                        mission_id=mission_id,
                        text=formatting_preferences,
                        source_agent=self.controller.messenger_agent.agent_name
                    )
                    logger.info(f"Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")
                
                # Return the agent output with the mission_id added
                agent_output["mission_id"] = mission_id
                return agent_output
            
            # Handle refine_goal even if content extraction failed
            elif action == "refine_goal" and mission_id:
                goal_text_to_add = request_content  # Prioritize extracted content
                if not goal_text_to_add:
                    logger.warning(f"MessengerAgent detected 'refine_goal' but failed to extract content. Falling back to using the original user message as goal text.")
                    goal_text_to_add = original_user_message_for_goal  # Fallback to user message

                logger.info(f"Handling 'refine_goal' action for mission {mission_id}. Adding goal: '{goal_text_to_add[:60]}...'")
                # Add the goal to the context manager
                goal_id = self.controller.context_manager.add_goal(
                    mission_id=mission_id,
                    text=goal_text_to_add,  # Use extracted content or fallback
                    source_agent=self.controller.messenger_agent.agent_name  # Record who added it
                )
                if goal_id:
                    logger.info(f"Added goal '{goal_id}' to mission {mission_id}: '{request_content[:50]}...'")
                    # Log the specific goal addition step
                    self.controller.context_manager.log_execution_step(
                        mission_id=mission_id,
                        agent_name="AgentController",
                        action="Add User Goal",
                        input_summary=f"User goal feedback: {request_content[:60]}...",
                        output_summary=f"Stored goal {goal_id}.",
                        status="success",
                        full_input={'goal_text': request_content},
                        full_output={'goal_id': goal_id},
                        log_queue=log_queue,
                        update_callback=update_callback
                    )
                else:
                    logger.error(f"Failed to add goal to context manager for mission {mission_id}.")
                    # Log the failure
                    self.controller.context_manager.log_execution_step(
                        mission_id=mission_id,
                        agent_name="AgentController",
                        action="Add User Goal",
                        input_summary=f"User goal feedback: {request_content[:60]}...",
                        output_summary="Failed to store goal.",
                        status="failure",
                        error_message="ContextManager.add_goal returned None.",
                        log_queue=log_queue,
                        update_callback=update_callback
                    )
                # Return the original agent_output, which contains the user-facing response
                return agent_output
            else:
                # For other actions or if conditions aren't met, return the original output.
                # The UI layer will handle actions like 'start_research', 'refine_questions', 'approve_questions'.
                return agent_output

        except Exception as e:
            logger.error(f"Error during MessengerAgent execution or goal handling: {e}", exc_info=True)
            # Return a default error response
            return {
                "response": f"Sorry, I encountered an error trying to process your message: {e}",
                "action": None,
                "request": None
            }

    async def refine_questions(
        self,
        mission_id: str,
        user_feedback: str,
        current_questions: List[str],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ) -> Tuple[List[str], str]:
        """
        Refines the research questions based on user feedback.
        Returns a tuple containing the updated list of questions and a response string for the user.
        """
        logger.info(f"Refining questions for mission {mission_id} based on user feedback: '{user_feedback[:50]}...'")
        
        # Prepare the prompt for question refinement
        prompt = f"""
You are a research assistant helping to refine research questions. Based on the user's feedback, modify the current list of research questions.

Current Questions:
{chr(10).join([f"- {q}" for q in current_questions])}

User Feedback:
{user_feedback}

Instructions:
1. Analyze the user's feedback carefully.
2. **If the feedback asks to increase the number of questions or add variety:** Keep the existing 'Current Questions' and ADD new, distinct questions based on the feedback and the original topic. Aim to expand the scope or explore different angles.
3. **If the feedback asks for other changes (e.g., rephrasing, focusing, removing):** Modify the 'Current Questions' list accordingly. You can rephrase, merge, remove, or replace questions.
4. Ensure all questions in the final list are clear, specific, and focused on the research topic.
5. Maintain a reasonable number of questions (typically 3-8, but allow more if explicitly requested).
6. Return ONLY the final list of questions, one per line, with no numbering or bullet points. Ensure the list includes both the original questions (if kept) and any new ones.
"""
        
        try:
            # Call the LLM to refine the questions
            async with self.controller.maybe_semaphore:
                response, model_details = await self.controller.model_dispatcher.dispatch(
                    messages=[{"role": "user", "content": prompt}],
                    agent_mode="planning"
                )
            
            # Update Stats
            if model_details:
                self.controller.context_manager.update_mission_stats(mission_id, model_details, log_queue, update_callback)
            
            if response and response.choices and response.choices[0].message.content:
                content = response.choices[0].message.content
                refined_questions = [q.strip() for q in content.strip().split('\n') if q.strip()]
                
                # Log the refinement
                self.controller.context_manager.log_execution_step(
                    mission_id, "AgentController", "Refine Questions",
                    input_summary=f"User Feedback: {user_feedback[:50]}...",
                    output_summary=f"Refined questions from {len(current_questions)} to {len(refined_questions)}.",
                    status="success",
                    full_input={'user_feedback': user_feedback, 'current_questions': current_questions},
                    full_output=refined_questions,
                    model_details=model_details,
                    log_queue=log_queue, update_callback=update_callback
                )
                
                # Update the questions in the mission context
                self.controller.context_manager.update_mission_metadata(mission_id, {"refined_questions": refined_questions})

                # Construct the response string for the user
                response_string = "I've updated the questions based on your feedback:\n\n"
                response_string += "\n".join([f"- {q}" for q in refined_questions])
                response_string += "\n\nAny further changes, or type 'start research' to proceed."

                return refined_questions, response_string
            else:
                logger.error("LLM failed to refine questions.")
                error_response = "Sorry, I had trouble refining the questions. Please try again or proceed with the current ones:\n\n"
                error_response += "\n".join([f"- {q}" for q in current_questions])
                error_response += "\n\nType 'start research' to proceed."
                return current_questions, error_response  # Return original questions and error message

        except Exception as e:
            err_msg = f"Error refining questions: {e}"
            logger.error(err_msg, exc_info=True)
            
            # Log the failure
            self.controller.context_manager.log_execution_step(
                mission_id, "AgentController", "Refine Questions",
                input_summary=f"User Feedback: {user_feedback[:50]}...",
                status="failure",
                error_message=err_msg,
                log_queue=log_queue, update_callback=update_callback
            )

            error_response = f"Sorry, an error occurred while refining questions: {e}\nPlease try again or proceed with the current ones:\n\n"
            error_response += "\n".join([f"- {q}" for q in current_questions])
            error_response += "\n\nType 'start research' to proceed."
            return current_questions, error_response  # Return original questions and error message

    async def confirm_questions_and_run(
        self,
        mission_id: str,
        final_questions: List[str],
        tool_selection: Dict[str, bool],
        log_queue: Optional[queue.Queue] = None,
        update_callback: Optional[Callable[[queue.Queue, Any], None]] = None
    ) -> bool:
        """
        Confirms the final questions, stores tool selection, and prepares for research.
        Returns True if the process was started successfully.
        """
        logger.info(f"Confirming questions and settings for mission {mission_id}...")
        
        # Store final questions and tool selection in metadata
        self.controller.context_manager.update_mission_metadata(mission_id, {
            "final_questions": final_questions,
            "tool_selection": tool_selection
        })
        logger.info(f"Stored final questions and tool selection ({tool_selection}) for mission {mission_id}.")
        
        # Log the confirmation step
        self.controller.context_manager.log_execution_step(
            mission_id, "AgentController", "Confirm Questions and Settings",
            input_summary=f"Final Questions: {len(final_questions)}, Tools: {tool_selection}",
            output_summary="Confirmed questions and tool selection.",
            status="success",
            full_input={'final_questions': final_questions, 'tool_selection': tool_selection},
            log_queue=log_queue, update_callback=update_callback
        )

        # The actual start of the research (plan generation, execution) is triggered
        # by the UI based on the 'initializing' state set before calling this.
        # This function now primarily serves to store the confirmed data.
        return True
