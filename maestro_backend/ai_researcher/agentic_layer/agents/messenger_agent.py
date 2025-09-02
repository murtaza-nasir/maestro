import logging
import json
import os
from typing import Dict, Any, Optional, List, Tuple, Awaitable, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError

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

# Enable debug mode via environment variable
DEBUG_MESSENGER = os.getenv('DEBUG_MESSENGER', 'false').lower() == 'true'
# Use simplified prompt for local LLMs
SIMPLE_PROMPT = os.getenv('MESSENGER_SIMPLE_PROMPT', 'false').lower() == 'true'


class MessengerIntentResponse(BaseModel):
    """Structured output schema for MessengerAgent LLM responses."""
    
    model_config = {"extra": "forbid"}  # This adds additionalProperties: false to the JSON schema
    
    intent: Literal["start_research", "refine_questions", "refine_goal", "approve_questions", "chat"] = Field(
        description="The user's intent - what they want to do"
    )
    
    extracted_content: Optional[str] = Field(
        default=None,
        description="The main topic or request extracted from the user's message. Must be populated for start_research, refine_questions, or refine_goal intents."
    )
    
    formatting_preferences: Optional[str] = Field(
        default=None,
        description="Any style/format preferences mentioned by the user (tone, length, audience, format, etc.)"
    )
    
    response_to_user: str = Field(
        description="Your response to show to the user"
    )
    
    thoughts: str = Field(
        description="Your reasoning about the user's message and why you chose this intent"
    )


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
        
        if DEBUG_MESSENGER:
            logger.info("🔍 MESSENGER AGENT DEBUG MODE ENABLED - Verbose logging active")
            logger.info("   To disable, set environment variable: DEBUG_MESSENGER=false")
        
        if SIMPLE_PROMPT:
            logger.info("📝 MESSENGER AGENT SIMPLE PROMPT MODE ENABLED - Using simplified prompt for local LLMs")
            logger.info("   To disable, set environment variable: MESSENGER_SIMPLE_PROMPT=false")

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

        # Prepare context blocks that will be added to the current user message
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

        # Build system prompt (instructions) and user prompt (task) separately
        # Simplified prompt since Pydantic schema enforces structure
        system_prompt = """You are a research assistant that helps users with research tasks.

Analyze the user's message and determine their intent:

1. "start_research" - User wants you to research, analyze, design, create, or investigate ANYTHING
   - ANY request for information, analysis, help, or creation = start_research
   - Extract the core topic/request as extracted_content
   
2. "refine_questions" - User is giving feedback about previously shown research questions
   - Only use if they're commenting on questions you already showed them
   
3. "refine_goal" - User is providing preferences about output format/style without a new topic
   - Examples: tone, length, audience, format preferences
   
4. "approve_questions" - User approves previously shown questions (yes, ok, proceed, looks good)
   - Only for approving questions already shown, not for new requests
   
5. "chat" - General conversation not about research

Important:
- ALWAYS extract formatting preferences if mentioned (tone, length, audience, format)
- For start_research, refine_questions, and refine_goal: extracted_content MUST be populated
- For approve_questions and chat: extracted_content should be null
- Provide a helpful response_to_user and explain your reasoning in thoughts

Examples:

1. Start Research (without formatting):
User: "Help me understand the key concepts and applications of machine learning"
Response: {
  "intent": "start_research",
  "extracted_content": "key concepts and applications of machine learning",
  "formatting_preferences": null,
  "response_to_user": "I'll help you research the key concepts and applications of machine learning. Let me generate some research questions to guide our exploration.",
  "thoughts": "User is asking for help understanding a topic, which is a research request"
}

2. Start Research (with formatting):
User: "Write a brief report about climate change impacts, keep it simple for high school students"
Response: {
  "intent": "start_research",
  "extracted_content": "climate change impacts",
  "formatting_preferences": "brief report, simple language for high school students",
  "response_to_user": "I'll research climate change impacts and create a brief, simple report suitable for high school students. Let me generate some research questions.",
  "thoughts": "User wants research on climate change with specific formatting requirements"
}

3. Refine Questions:
User: "Can you make the third question more specific to renewable energy solutions?"
Response: {
  "intent": "refine_questions",
  "extracted_content": "make third question more specific to renewable energy solutions",
  "formatting_preferences": null,
  "response_to_user": "I'll refine the third question to focus more specifically on renewable energy solutions.",
  "thoughts": "User is providing feedback about previously shown research questions"
}

4. Refine Goal:
User: "Actually, make it more technical and detailed, I need this for my thesis"
Response: {
  "intent": "refine_goal",
  "extracted_content": "more technical and detailed for thesis",
  "formatting_preferences": "technical, detailed, thesis-level",
  "response_to_user": "I've noted that you need a more technical and detailed analysis suitable for thesis work.",
  "thoughts": "User is changing the output format requirements without changing the topic"
}

5. Approve Questions:
User: "Yes, those questions look good, let's proceed"
Response: {
  "intent": "approve_questions",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "Great! I'll now start the research process with the approved questions.",
  "thoughts": "User is approving the previously generated questions"
}

6. Chat:
User: "How does this research system work?"
Response: {
  "intent": "chat",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "This system helps you conduct research by first defining your topic, generating research questions, and then gathering information to create a comprehensive report. What would you like to research today?",
  "thoughts": "User is asking about the system itself, not requesting research"
}"""
        
        # Complex prompt code commented out - keeping for reference
        if False:  # Was: else:
            # Original complex prompt - split into system and user
            system_prompt = f"""You are a helpful research assistant interface. Your primary role during the initial conversation is to understand the user's research topic, manage the refinement of research questions, and detect when the user wants to start the actual research process.

**CRITICAL INSTRUCTION:** During the initial phases (before research questions are approved and the mission starts), you MUST NOT answer the user's questions directly using your own knowledge or attempt to fulfill requests like writing summaries, notes, or performing actions other than those specified below. Your ONLY functions are:
1.  Identify the user's intended research topic when they first state it (`start_research` intent).
2.  Acknowledge feedback on research questions (`refine_questions` intent).
3.  Recognize when the user approves the questions and wants to begin the research (`approve_questions` intent).
4.  Engage in simple clarification dialogue if the user's request is unclear, or answer basic questions *about the research process itself* (`chat` intent).

**DO NOT SYNTHESIZE ANSWERS OR PERFORM TASKS YOURSELF.** Your role is to facilitate the setup of the research mission.

**CRITICAL FORMATTING PREFERENCE DETECTION:** You MUST carefully analyze the user's message for ANY preferences about how the final output should be presented:

**Tone/Style Preferences:**
- Academic/formal: "academic style", "formal tone", "scholarly", "professional"
- Casual/informal: "casual", "informal", "conversational", "friendly"
- Simplified: "explain like I'm 5", "simple terms", "layman's terms", "non-technical"
- Technical: "technical details", "in-depth", "expert level"

**Length Preferences:**
- Short: "keep it short", "brief", "concise", "summary", "quick overview"
- Medium: "moderate length", "standard report"
- Long: "comprehensive", "detailed", "thorough", "extensive", "in-depth analysis"
- Specific: "one paragraph", "2-3 pages", "500 words"

**Audience Specifications:**
- General: "for general public", "for everyone", "accessible"
- Expert: "for experts", "for researchers", "for professionals"
- Educational: "for students", "for beginners", "for learning"
- Specific groups: "for policymakers", "for investors", "for developers"

**Format Preferences:**
- Structure: "bullet points", "numbered list", "essay format", "Q&A style"
- Sections: "no subsections", "with clear sections", "single section"
- Document type: "report", "memo", "executive summary", "white paper"

**IMPORTANT:** If you detect ANY of these preferences:
1. Extract them into the `formatting_preferences` field
2. If the user is ONLY providing preferences (not a new research topic), use `refine_goal` intent
3. If starting new research WITH preferences, use `start_research` intent but ALSO populate `formatting_preferences`

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

Example 1 (Start Research with Preferences):
User: Tell me about the latest advancements in quantum computing, keep it simple and brief.
Output:
{{
  "intent": "start_research",
  "extracted_content": "latest advancements in quantum computing",
  "formatting_preferences": "simple language, brief summary",
  "response_to_user": "I'll help you research quantum computing advancements with a brief, simple explanation. Let me generate some initial research questions for us to review.",
  "thoughts": "The user wants to start research on quantum computing with specific formatting preferences for simplicity and brevity."
}}

Example 2 (Refine Goal - Preferences Only):
User: Actually, make it more technical and comprehensive, I need this for my PhD thesis.
Output:
{{
  "intent": "refine_goal",
  "extracted_content": "technical and comprehensive content for PhD thesis",
  "formatting_preferences": "technical details, comprehensive analysis, academic level for PhD thesis",
  "response_to_user": "I've noted that you need a technical, comprehensive analysis suitable for a PhD thesis. I'll ensure the research meets these academic standards.",
  "thoughts": "User is providing formatting preferences for the output - needs technical depth and comprehensive coverage for PhD level work."
}}

Example 3 (Start Research without Preferences):
User: What are the ethical implications of AI in healthcare?
Output:
{{
  "intent": "start_research",
  "extracted_content": "ethical implications of AI in healthcare",
  "formatting_preferences": null,
  "response_to_user": "I'll help you research the ethical implications of AI in healthcare. Let me generate some initial research questions for us to review.",
  "thoughts": "Clear research request without specific formatting preferences. Will use default formal academic style."
}}

Example 2 (Start Research with Formatting Preferences):
User: What theoretical frameworks can integrate insights from behavioral economics, information processing theory, and system dynamics to explain and predict how dashboard design characteristics influence managerial attention allocation and strategic decision-making in data-rich environments? keep it super short and informal. dont make a lot of sections, just one section with no subsections.
Output:
{{
  "intent": "start_research",
  "extracted_content": "theoretical frameworks that integrate insights from behavioral economics, information processing theory, and system dynamics to explain and predict how dashboard design characteristics influence managerial attention allocation and strategic decision-making in data-rich environments",
  "formatting_preferences": "keep it super short and informal, one section with no subsections",
  "response_to_user": "Okay, I can help you research that. I've noted your preference for a super short, informal output with just one section. I'll now generate some initial research questions for us to review.",
  "thoughts": "The user wants to start research on a complex topic and has provided specific formatting preferences. I will acknowledge both and hand off to the Research Agent for question generation."
}}

Example 3 (Refine Questions Intent):
User: The second question is too broad, and I'd like to focus more on practical applications rather than theory.
Output:
{{
  "intent": "refine_questions",
  "extracted_content": "second question too broad, focus more on practical applications rather than theory",
  "formatting_preferences": null,
  "response_to_user": "Okay, processing your feedback on the questions...",
  "thoughts": "The user is providing feedback specifically about the generated questions. Intent is refine_questions."
}}

Example 4 (Refine Goal Intent):
User: yes but I don't want a full paper. I want you to note in your goals to provide me a short document, not something lengthy
Output:
{{
  "intent": "refine_goal",
  "extracted_content": "provide me a short document, not something lengthy",
  "formatting_preferences": null,
  "response_to_user": "Okay, I've noted your preference for a short document rather than a full paper.",
  "thoughts": "The user is specifying the desired output format/length. This is feedback on the overall goal. Intent is refine_goal. I must extract the core feedback."
}}

Example 5 (Refine Goal - Tone):
User: Make sure to write the report in the tone of a fifth grader.
Output:
{{
  "intent": "refine_goal",
  "extracted_content": "write the report in the tone of a fifth grader",
  "formatting_preferences": null,
  "response_to_user": "Okay, I've noted your preference for the report to be written in the tone of a fifth grader.",
  "thoughts": "The user is specifying the desired output tone. This is feedback on the overall goal. Intent is refine_goal. I must extract the core feedback about the tone."
}}

Example 6 (Approve Questions Intent):
User: Those questions look good, go ahead.
Output:
{{
  "intent": "approve_questions",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "Great! I'll now start the research process with the approved questions. This may take a moment.",
  "thoughts": "The user has approved the questions and wants to proceed. My role is to confirm this and hand off control."
}}

Example 7 (Chat Intent):
User: How does this system work?
Output:
{{
  "intent": "chat",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "This system helps you conduct research by first defining a topic, then refining specific research questions, and finally executing a research plan to gather and synthesize information into a report. How can I help you set up your research today?",
  "thoughts": "The user is asking about system functionality. I should explain the process briefly and guide them back to starting the research setup."
}}

Example 8 (Forbidden Request):
User: Can you just give me a quick summary of those governance mechanisms now?
Output:
{{
  "intent": "chat",
  "extracted_content": null,
  "formatting_preferences": null,
  "response_to_user": "My current role is to help set up the research plan by defining the topic and refining questions. I can't provide summaries directly at this stage. Shall we continue defining the research questions?",
  "thoughts": "The user is asking for a summary, which I am explicitly forbidden from providing during the setup phase. I need to politely decline and redirect them to the task at hand (defining/refining questions)."
}}"""
        
        # Build the messages list with proper structure
        messages = []
        
        # Add system message
        messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history as alternating user/assistant messages
        for user_msg, assistant_msg in chat_history:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})
        
        # Build the current user message with context blocks
        current_user_content = ""
        
        # Add context blocks if they exist
        if mission_context_block:
            current_user_content += mission_context_block + "\n"
        if thoughts_block:
            current_user_content += thoughts_block + "\n"
        if scratchpad_block:
            current_user_content += scratchpad_block + "\n"
        
        # Add the actual user message with instruction
        if current_user_content:
            current_user_content += "\nNow, analyze the following message and provide the JSON output:\n"
        else:
            current_user_content = "Analyze the following message and provide the JSON output:\n"
        current_user_content += user_message
        
        # Add the current user message to the messages list
        messages.append({"role": "user", "content": current_user_content})

        llm_response_content = None
        model_details = None
        parsed_output = None
        final_response = "Sorry, I couldn't process that request."
        final_action = None
        final_request = None
        formatting_preferences = None  # Initialize formatting_preferences
        scratchpad_update = None # Initialize here
        intent = None  # Initialize intent to avoid UnboundLocalError
        extracted_content = None  # Initialize extracted_content
        response_to_user = None  # Initialize response_to_user

        # DEBUG: Log the messages being sent
        if DEBUG_MESSENGER:
            logger.info("=" * 80)
            logger.info("MESSENGER AGENT DEBUG - MESSAGES BEING SENT TO LLM:")
            logger.info("-" * 80)
            logger.info(f"Total messages: {len(messages)}")
            for i, msg in enumerate(messages):
                logger.info(f"Message {i+1} - Role: {msg['role']}, Length: {len(msg['content'])} chars")
                if i == 0:  # System message
                    if len(msg['content']) <= 2000:
                        logger.info(f"Full content:\n{msg['content']}")
                    else:
                        logger.info(f"Content too long, showing first 500 and last 500 chars:")
                        logger.info(f"BEGINNING:\n{msg['content'][:500]}\n...\n")
                        logger.info(f"END:\n...{msg['content'][-500:]}")
                elif i == len(messages) - 1:  # Current user message
                    logger.info(f"Current user message:\n{msg['content']}")
                else:  # History messages
                    logger.info(f"Content preview: {msg['content'][:100]}...")
            logger.info("=" * 80)
        
        # Retry logic for schema validation failures
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # Using a simple model suitable for intent detection/chat
                # Send the properly structured messages with Pydantic schema
                # Get the schema and ensure it has the required fields properly set
                schema = MessengerIntentResponse.model_json_schema()
                # Ensure the required fields are properly set for OpenAI
                # Only intent, response_to_user, and thoughts are truly required
                schema["required"] = ["intent", "response_to_user", "thoughts", "extracted_content", "formatting_preferences"]
                
                response, model_details = await self.model_dispatcher.dispatch(
                    messages=messages,
                    agent_mode="messenger", # Use the configured messenger role
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "messenger_intent_response",
                            "schema": schema,
                            "strict": True
                        }
                    },  # Use Pydantic schema for structured output
                    log_queue=log_queue, # Pass log_queue for UI updates
                    update_callback=update_callback # Pass update_callback for UI updates
                )

                if response and response.choices and response.choices[0].message.content:
                    llm_response_content = response.choices[0].message.content.strip()
                    
                    # Handle thinking models that might have special tokens or markers
                    # Look for common patterns that indicate the end of thinking
                    thinking_end_markers = [
                        "```json",  # JSON code block start
                        "Output:",  # Explicit output marker
                        "Response:",  # Response marker
                        "Result:",  # Result marker
                        "{\n",  # Direct JSON start
                        '{"',  # JSON object start
                    ]
                
                    # Check if response might contain thinking tokens
                    for marker in thinking_end_markers:
                        if marker in llm_response_content:
                            # Extract content after the marker
                            marker_pos = llm_response_content.rfind(marker)  # Use rfind to get last occurrence
                            if marker_pos != -1:
                                potential_json = llm_response_content[marker_pos:]
                                if DEBUG_MESSENGER:
                                    logger.info(f"Found potential marker '{marker}' at position {marker_pos}")
                                    logger.info(f"Extracting content from that point...")
                                llm_response_content = potential_json
                                break
                
                    # DEBUG: Log the full raw response
                    if DEBUG_MESSENGER:
                        logger.info("=" * 80)
                        logger.info("MESSENGER AGENT DEBUG - RAW LLM RESPONSE (after marker extraction):")
                        logger.info("-" * 80)
                        logger.info(f"Response length: {len(llm_response_content)} characters")
                        logger.info(f"First 500 chars: {llm_response_content[:500]}")
                        if len(llm_response_content) <= 2000:
                            logger.info(f"Full response:\n{llm_response_content}")
                        else:
                            logger.info(f"Response too long, showing first 2000 chars:\n{llm_response_content[:2000]}")
                        logger.info("=" * 80)
                
                    # Extract JSON block
                    json_match = llm_response_content.find('{')
                    if json_match != -1:
                        json_str = llm_response_content[json_match:]
                        # Clean up potential markdown fences using our centralized utility
                        json_str = sanitize_json_string(json_str)
                    
                        # DEBUG: Log the extracted JSON string
                        if DEBUG_MESSENGER:
                            logger.info("MESSENGER AGENT DEBUG - EXTRACTED JSON:")
                            logger.info("-" * 80)
                            logger.info(f"JSON string (after sanitization):\n{json_str[:1000]}")
                            logger.info("-" * 80)

                        try:
                            # Parse and validate using Pydantic model
                            json_data = json.loads(json_str)
                            parsed_response = MessengerIntentResponse(**json_data)
                        
                            # DEBUG: Log successfully parsed JSON
                            if DEBUG_MESSENGER:
                                logger.info("MESSENGER AGENT DEBUG - PARSED JSON DATA:")
                                logger.info("-" * 80)
                                logger.info(f"Validated Pydantic model: {parsed_response.model_dump_json(indent=2)}")
                                logger.info("-" * 80)
                        
                            # Extract data from validated Pydantic model
                            intent = parsed_response.intent
                            extracted_content = parsed_response.extracted_content
                            formatting_preferences = parsed_response.formatting_preferences
                            response_to_user = parsed_response.response_to_user
                            thoughts = parsed_response.thoughts
                            
                            # Set the response to show to the user
                            final_response = response_to_user
                        
                            # Successfully parsed - break out of retry loop
                            break
                        
                        except (json.JSONDecodeError, ValueError, ValidationError) as parse_error:
                            # Store the error for retry
                            last_error = parse_error
                            retry_count += 1
                            logger.warning(f"JSON parsing or Pydantic validation failed (attempt {retry_count}/{max_retries}): {parse_error}")
                            
                            # Try to fix common JSON issues
                            if isinstance(parse_error, json.JSONDecodeError):
                                    logger.info(f"Detected formatting preferences with start_research: '{formatting_preferences}'")
                                    # Store formatting preferences to be added as a goal later
                                    if self.controller and self.mission_id:
                                        try:
                                            # Add formatting preferences as a separate goal
                                            goal_id = await self.controller.context_manager.add_goal(
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
                                        goal_id = await self.controller.context_manager.add_goal(
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
                                        goal_id = await self.controller.context_manager.add_goal(
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
                                        goal_id = await self.controller.context_manager.add_goal(
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
                                if DEBUG_MESSENGER:
                                    logger.info("MESSENGER AGENT DEBUG - UNRECOGNIZED/NONE INTENT:")
                                    logger.info("-" * 80)
                                    logger.info(f"Intent value: {intent!r}")
                                    logger.info(f"Extracted content: {extracted_content!r}")
                                    logger.info(f"This means either intent is None or not a recognized action")
                                    logger.info("-" * 80)
                            
                                # Handle formatting preferences for chat intent too
                                if formatting_preferences and self.controller and self.mission_id:
                                    logger.info(f"Detected formatting preferences with {intent} intent: '{formatting_preferences}'")
                                    try:
                                        # Add formatting preferences as a separate goal
                                        goal_id = await self.controller.context_manager.add_goal(
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

                        except (json.JSONDecodeError, ValueError, ValidationError) as parse_error:
                            # Store the error for retry
                            last_error = parse_error
                            retry_count += 1
                            logger.warning(f"JSON parsing or Pydantic validation failed (attempt {retry_count}/{max_retries}): {parse_error}")
                        
                            # Try to fix common JSON issues
                            if isinstance(parse_error, json.JSONDecodeError):
                                # Attempt simple fix: Insert comma before last '}' if likely missing
                                fixed_json_str = json_str.strip()
                                if "Expecting ',' delimiter" in str(parse_error) and fixed_json_str.endswith('}'):
                                    insertion_point = len(fixed_json_str) - 1
                                    char_before_brace = fixed_json_str[insertion_point - 1].strip() if insertion_point > 0 else ''
                                    if char_before_brace in ('"', ']', '}') or char_before_brace.isdigit():
                                        fixed_json_str = fixed_json_str[:insertion_point] + ',' + fixed_json_str[insertion_point:]
                                        logger.info("Attempting re-parse with added comma before final '}'.")
                                        try:
                                            # Re-attempt parsing with the fix
                                            json_data = json.loads(fixed_json_str)
                                            parsed_response = MessengerIntentResponse(**json_data)
                                        
                                            # Extract data from validated Pydantic model
                                            intent = parsed_response.intent
                                            extracted_content = parsed_response.extracted_content
                                            formatting_preferences = parsed_response.formatting_preferences
                                            response_to_user = parsed_response.response_to_user
                                            thoughts = parsed_response.thoughts
                                        
                                            # Ensure final_response is never None
                                            final_response = response_to_user if response_to_user is not None else "Sorry, I couldn't generate a proper response."

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
                                                          goal_id = await self.controller.context_manager.add_goal(
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
                                                        goal_id = await self.controller.context_manager.add_goal(
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
                                                        goal_id = await self.controller.context_manager.add_goal(
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
                                                        goal_id = await self.controller.context_manager.add_goal(
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
                                                        goal_id = await self.controller.context_manager.add_goal(
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
                                        logger.error(f"JSON parsing failed and simple fix not applicable: {parse_error}")
                                        final_response = "Sorry, I had trouble understanding the format of my own thoughts."
                                else:
                                    logger.error(f"JSON parsing failed: {parse_error}")
                                    final_response = "Sorry, I had trouble understanding the format of my own thoughts."
                    else:
                        logger.error(f"Could not find JSON block in LLM response (attempt {retry_count + 1}/{max_retries})")
                        if DEBUG_MESSENGER:
                            logger.info("MESSENGER AGENT DEBUG - NO JSON FOUND:")
                            logger.info("-" * 80)
                            logger.info(f"Full response that failed to contain JSON:\n{llm_response_content}")
                            logger.info("-" * 80)
                        last_error = "No JSON found in response"
                        retry_count += 1
                else:
                    logger.error(f"LLM response was empty or invalid (attempt {retry_count + 1}/{max_retries}).")
                    if DEBUG_MESSENGER:
                        logger.info("MESSENGER AGENT DEBUG - EMPTY/INVALID RESPONSE:")
                        logger.info("-" * 80)
                        logger.info(f"Response object: {response}")
                        if response:
                            logger.info(f"Response choices: {response.choices}")
                            if response.choices:
                                logger.info(f"First choice: {response.choices[0]}")
                                if response.choices[0]:
                                    logger.info(f"Message: {response.choices[0].message}")
                        logger.info("-" * 80)
                    last_error = "Empty or invalid response from LLM"
                    retry_count += 1
            except Exception as e:
                # Handle authentication and other API errors
                from ai_researcher.agentic_layer.utils.error_messages import handle_api_error
                
                logger.error(f"Error during MessengerAgent LLM call (attempt {retry_count + 1}/{max_retries}): {e}", exc_info=True)
                last_error = e
                retry_count += 1
                
                # If it's an API configuration error (400), don't retry
                if hasattr(e, 'status_code') and e.status_code == 400:
                    final_response = handle_api_error(e)
                    break
        
        # If we exhausted all retries without success, provide error message
        if retry_count >= max_retries and not final_response:
            logger.error(f"Failed to get valid response after {max_retries} attempts. Last error: {last_error}")
            final_response = (
                "The current language model is unable to generate properly structured responses. "
                "This usually means the model doesn't support structured outputs or isn't following instructions correctly. "
                "Please try using a different model (such as GPT-4, Claude, or other models that support JSON schemas) "
                "in your AI settings. Last error: " + str(last_error)
            )
        
        # Process the intent and map to actions (only if we got a valid response)
        if final_response and intent:
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
                            goal_id = await self.controller.context_manager.add_goal(
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
                        goal_id = await self.controller.context_manager.add_goal(
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
                        goal_id = await self.controller.context_manager.add_goal(
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
                        goal_id = await self.controller.context_manager.add_goal(
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
                if DEBUG_MESSENGER:
                    logger.info("MESSENGER AGENT DEBUG - UNRECOGNIZED/NONE INTENT:")
                    logger.info("-" * 80)
                    logger.info(f"Intent value: {intent!r}")
                    logger.info(f"Extracted content: {extracted_content!r}")
                    logger.info(f"This means either intent is None or not a recognized action")
                    logger.info("-" * 80)
                
                # Handle formatting preferences for chat intent too
                if formatting_preferences and self.controller and self.mission_id:
                    logger.info(f"Detected formatting preferences with {intent} intent: '{formatting_preferences}'")
                    try:
                        # Add formatting preferences as a separate goal
                        goal_id = await self.controller.context_manager.add_goal(
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

        # Construct the final output dictionary expected by AgentController
        agent_result = {
            "response": final_response,
            "action": final_action,
            "request": final_request,
            "formatting_preferences": formatting_preferences  # Include formatting_preferences in the result
        }
        
        # DEBUG: Log final output
        if DEBUG_MESSENGER:
            logger.info("MESSENGER AGENT DEBUG - FINAL OUTPUT:")
            logger.info("=" * 80)
            logger.info(f"Returning to controller:")
            logger.info(f"  agent_result: {json.dumps(agent_result, indent=2)}")
            logger.info(f"  model_details: {model_details}")
            logger.info(f"  scratchpad_update: {scratchpad_update[:200] if scratchpad_update else None}")
            logger.info("=" * 80)

        # Return AgentOutput tuple (result_dict, model_details, scratchpad_update)
        # Now includes scratchpad_update if thoughts were captured
        return agent_result, model_details, scratchpad_update
