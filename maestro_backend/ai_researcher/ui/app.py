import streamlit as st
import sys
import os
import threading
import time
import io
import base64
from pathlib import Path
import logging
import json
import queue
import asyncio # <-- Import asyncio
import uuid # <-- Import uuid
import datetime # <-- Import datetime
from typing import Optional, Callable, Dict, Any, List # Added Dict, Any, List
from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry
from ai_researcher.ui.file_converters import markdown_to_pdf, markdown_to_docx

# Import schemas needed for plan parsing
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection, PlanStep

# --- Define Project Root Early ---
# Needed for path configurations below
try:
    current_file_path = Path(__file__).resolve()
    project_root = current_file_path.parent.parent.parent
except NameError:
    # Handle cases where __file__ might not be defined (e.g., interactive)
    project_root = Path.cwd() # Fallback to current working directory

# --- Imports ---
# Assuming the script is run as a module from the project root
try:
    from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry # Import for type hint
    from ai_researcher.core_rag.embedder import TextEmbedder
    from ai_researcher.core_rag.vector_store import VectorStore
    from ai_researcher.core_rag.reranker import TextReranker
    from ai_researcher.core_rag.retriever import Retriever
    from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
    from ai_researcher.agentic_layer.tool_registry import ToolRegistry
    from ai_researcher.agentic_layer.context_manager import ContextManager
    from ai_researcher.agentic_layer.agent_controller import AgentController
    # Import schemas needed later if not already imported by controller/agents
    from ai_researcher.agentic_layer.schemas.research import ResearchResultResponse
    from ai_researcher import config # Import config to access model names

except ImportError as e:
    st.error(f"Failed to import necessary modules. Check sys.path and module structure. Error: {e}")
    st.stop() # Stop execution if imports fail

# --- Configure Logging ---
# Streamlit runs the script multiple times, so configure logging carefully
# Define log file path relative to project root
log_file_path = project_root / "streamlit_app.log"

# Get the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # Set level on the root logger

# Define formatter
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Check if handlers are already configured to avoid duplicates during Streamlit reruns
if not root_logger.handlers:
    # Add File Handler
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    # Add Stream Handler (to console)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(log_formatter)
    root_logger.addHandler(stream_handler)

    root_logger.info("Logging configured with FileHandler and StreamHandler.")
else:
    # Optional: Log that handlers were already present (useful for debugging Streamlit reruns)
    # root_logger.debug("Logging handlers already configured.")
    pass

# Get logger for this specific module
logger = logging.getLogger(__name__)

# --- Configuration (Match main_cli.py defaults or use config file) ---
# Define paths relative to the project root
# project_root is defined above
VECTOR_STORE_PATH = project_root / "ai_researcher" / "data/vector_store" # Corrected path
CONTEXT_SAVE_DIR = project_root / "ai_researcher" / "data/mission_results" # Assuming context is also under ai_researcher
UI_OUTPUT_DIR = project_root / "ui_research_output" # Directory for UI reports
EMBEDDING_MODEL = "BAAI/bge-m3"
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# --- Initialize Components (Singleton Pattern using st.cache_resource) ---
# Use st.cache_resource to initialize components only once per session
@st.cache_resource
def initialize_components():
    logger.info("Initializing AI Researcher components for Streamlit app...")
    try:
        embedder = TextEmbedder(model_name=EMBEDDING_MODEL)
        vector_store = VectorStore(persist_directory=VECTOR_STORE_PATH)
        reranker = TextReranker(model_name=RERANKER_MODEL) # Optional
        retriever = Retriever(embedder=embedder, vector_store=vector_store, reranker=reranker)
        model_dispatcher = ModelDispatcher() # Uses env var for API key
        tool_registry = ToolRegistry()
        context_manager = ContextManager(save_dir=CONTEXT_SAVE_DIR)
        agent_controller = AgentController(
            model_dispatcher=model_dispatcher,
            context_manager=context_manager,
            tool_registry=tool_registry,
            retriever=retriever,
            reranker=reranker # <-- Pass the reranker instance
        )
        logger.info("Components initialized successfully.")
        return agent_controller, context_manager
    except Exception as e:
        st.error(f"Fatal Error initializing components: {e}")
        logger.error(f"Fatal Error initializing components: {e}", exc_info=True)
        st.stop() # Stop if core components fail

# --- Helper function to generate report filenames (UI version) ---
def generate_ui_report_filename(mission_id: str) -> str:
    """Generates a filename for a UI report using current date and time."""
    now = datetime.datetime.now()
    date_time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    # Sanitize mission_id slightly for filename (replace common problematic chars)
    safe_mission_id = mission_id.replace(":", "_").replace("/", "_")
    # Create filename with date_time at the start for better sorting
    return f"{date_time_str}_ui_report_{safe_mission_id}.md"

# --- Streamlit App Layout ---
st.set_page_config(layout="wide", page_title="MAESTRO: Multi-Agent Execution System & Tool-driven Research Orchestrator")
st.title("MAESTRO")
st.subheader("Multi-Agent Execution System & Tool-driven Research Orchestrator")
# Initialize components using caching
try:
    agent_controller, context_manager = initialize_components()
except Exception:
    # Error already handled by initialize_components using st.error and st.stop
    pass


# --- Session State Management ---
if 'mission_id' not in st.session_state:
    st.session_state.mission_id = None
if 'mission_status' not in st.session_state:
    # Updated states: idle, awaiting_request, refining_questions, initializing, running, completed, failed
    st.session_state.mission_status = "awaiting_request"
if 'messages' not in st.session_state: # For chat history
    st.session_state.messages = []
if 'current_questions' not in st.session_state: # To hold questions during refinement
    st.session_state.current_questions = []
if 'mission_plan' not in st.session_state: # Keep for later stages
    st.session_state.mission_plan = None
if 'mission_error' not in st.session_state:
    st.session_state.mission_error = None
if 'final_report' not in st.session_state:
    st.session_state.final_report = None
if 'step_results' not in st.session_state: # Kept for potential future use, but not populated now
    st.session_state.step_results = {}
if 'execution_log' not in st.session_state: # This will hold the log displayed in the UI
    st.session_state.execution_log = []
if 'mission_thread' not in st.session_state: # Holds the background thread object
    st.session_state.mission_thread = None
if 'log_queue' not in st.session_state: # Holds the queue for log updates
    st.session_state.log_queue = None
# Flag to indicate if an agent is currently processing user input
if 'agent_processing' not in st.session_state:
    st.session_state.agent_processing = False
# Tool selection state
if 'tool_selection' not in st.session_state:
    st.session_state.tool_selection = {'local_rag': True, 'web_search': True}
# Tool usage display state (for showing feedback)
if 'tool_usage_display' not in st.session_state:
    st.session_state.tool_usage_display = None
# Flag to track if the report has been saved (to prevent multiple saves)
if 'report_saved' not in st.session_state:
    st.session_state.report_saved = False
# Stats tracking state
if 'total_cost' not in st.session_state:
    st.session_state.total_cost = 0.0
if 'total_native_tokens' not in st.session_state:
    st.session_state.total_native_tokens = 0.0
if 'total_web_search_calls' not in st.session_state:
    st.session_state.total_web_search_calls = 0

# --- Initialize Messenger Agent (Needs ModelDispatcher) ---
# We need the dispatcher instance from initialize_components
try:
    agent_controller, context_manager = initialize_components()
    # Instantiate MessengerAgent here if not already part of controller or easily accessible
    # Assuming we can access the dispatcher from the controller for now
    from ai_researcher.agentic_layer.agents.messenger_agent import MessengerAgent
    messenger_agent = MessengerAgent(agent_controller.model_dispatcher)
except Exception as e:
    st.error(f"Failed to initialize components or MessengerAgent: {e}")
    st.stop()


# --- Background Task Function (Handles Planning and Execution) ---
def run_full_mission_background(
    controller: AgentController,
    mission_id: str,
    log_queue: queue.Queue,
    update_callback: Callable[[queue.Queue, Any, Optional[str], Optional[str]], None] # Changed type hint for update_data
):
    """Target function for the background thread, handling plan generation and mission execution."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # --- DIAGNOSTIC FEEDBACK ---
        try:
            feedback_payload = {
                "type": "agent_feedback",
                "payload": {
                    "type": "thread_status",
                    "status": "Starting mission execution (includes planning)"
                }
            }
            log_queue.put(feedback_payload)
        except Exception as fb_e:
            logger.error(f"Failed to send diagnostic feedback: {fb_e}")
        # --- END DIAGNOSTIC FEEDBACK ---

        logger.info(f"Background thread: Starting mission execution (including planning) for mission {mission_id}...")
        # Directly run the mission. The controller's run_mission handles planning internally.
        loop.run_until_complete(
            controller.run_mission(mission_id, log_queue=log_queue, update_callback=update_callback)
        )

        # --- DIAGNOSTIC FEEDBACK ---
        try:
            feedback_payload = {
                "type": "agent_feedback",
                "payload": {
                    "type": "thread_status",
                    "status": "Mission execution completed (or failed internally)"
                }
            }
            log_queue.put(feedback_payload)
        except Exception as fb_e:
            logger.error(f"Failed to send diagnostic feedback: {fb_e}")
        # --- END DIAGNOSTIC FEEDBACK ---

        logger.info(f"Background thread: Finished mission {mission_id} execution attempt.")
        # run_mission should handle logging completion/failure status via the callback

    except Exception as e:
        # Catch errors during the run_mission call itself
        phase = "execution (including planning)"
        log_mission_id = mission_id
        logger.error(f"Exception in background thread during {phase} phase for mission {log_mission_id}: {e}", exc_info=True)
        # Log error via callback
        try:
            error_log = ExecutionLogEntry(
                agent_name="System", action=f"Mission {phase.capitalize()} Phase", status="failure",
                error_message=f"Background thread error during {phase}: {e}",
                mission_id=mission_id
            )
            # Use a default queue if log_queue is None, though it shouldn't be here
            q = log_queue if log_queue else queue.Queue()
            update_callback(q, error_log, mission_id, "failed") # Signal failure
        except Exception as cb_e:
            logger.error(f"Failed to log background thread error via callback: {cb_e}")
            # Still try to signal failure completion if possible
            if log_queue:
                try:
                    # Send a generic failure signal if specific logging failed
                    update_callback(log_queue, None, mission_id, "failed")
                except Exception as final_cb_e:
                     logger.error(f"Failed to signal failure via callback in exception handler: {final_cb_e}")

        # Update context manager status directly as a fallback
        try:
            controller.context_manager.update_mission_status(mission_id, "failed", f"Background thread error during {phase} phase: {e}")
        except Exception as context_e:
            logger.error(f"Failed to update context status from background thread exception handler: {context_e}")

    finally:
        # Ensure the loop is closed
        try:
            loop.close()
            log_mission_id = mission_id
            logger.info(f"Closed event loop for mission {log_mission_id} background thread.")
        except Exception as loop_close_e:
            log_mission_id = mission_id
            logger.error(f"Error closing event loop for mission {log_mission_id}: {loop_close_e}")



# --- Define UI Update Callback (Remains the same) ---
def ui_update_callback(
    log_queue: queue.Queue,
    update_data: Any, # Can be ExecutionLogEntry, dict (feedback/stats/known_types), or None
    mission_id: Optional[str] = None, # Add mission_id
    status: Optional[str] = None       # Add status
):
    """Puts an update item (log entry, feedback, stats, or status/id update) into the queue, wrapping known dict types."""
    if log_queue is not None:
        try:
            queue_item = None # Initialize queue_item

            # 1. Handle ExecutionLogEntry and None (completion signal)
            if isinstance(update_data, ExecutionLogEntry) or update_data is None:
                queue_item = {
                    "type": "update",
                    "log_entry": update_data,
                    "mission_id": mission_id,
                    "status": status
                }
            # 2. Handle Dictionaries
            elif isinstance(update_data, dict):
                dict_type = update_data.get("type")

                # 2a. Already correctly formatted agent_feedback or stats_update
                if dict_type in ["agent_feedback", "stats_update"]:
                    queue_item = update_data # Queue directly
                # 2b. Handle stats_increment: Re-queue as stats_update for centralized handling later
                elif dict_type == "stats_increment":
                    stat_type = update_data.get("stat_type")
                    received_mission_id = update_data.get("mission_id")
                    increment_value = update_data.get("increment_value", 1) # Assume default increment is 1

                    # --- DEBUG LOGGING ---
                    logger.info(f"DEBUG: Checking stats_increment condition. received_mission_id='{received_mission_id}' (type: {type(received_mission_id)}), stat_type='{stat_type}' (type: {type(stat_type)})")
                    # --- END DEBUG LOGGING ---

                    # Only re-queue if essential info is present
                    if received_mission_id and stat_type: # <--- Condition check
                        # Create a stats_update payload to be handled later by the main loop
                        stats_update_payload = {
                            "type": "stats_update", # Target the existing handler
                            "mission_id": received_mission_id,
                            "payload": {
                                # Indicate this is an increment
                                f"increment_{stat_type}": increment_value
                            }
                        }
                        queue_item = stats_update_payload # Queue the new message
                        logger.debug(f"UI Callback: Re-queued stats_increment for '{stat_type}' as stats_update for mission {received_mission_id}.")
                    else:
                        logger.warning(f"UI Callback: Dropping stats_increment due to missing mission_id or stat_type. Data: {update_data}")
                        queue_item = None # Don't queue incomplete increments
                # 2c. Handle model_call_details: Wrap as standard update to pass downstream
                elif dict_type == "model_call_details":
                    logger.debug(f"UI Callback: Wrapping 'model_call_details' as standard update. Content: {update_data}")
                    # Wrap the original dictionary as the log_entry within a standard 'update' item
                    queue_item = {
                        "type": "update",
                        "log_entry": update_data, # Pass the original dict here
                        "mission_id": mission_id,
                        "status": status # Pass status if provided
                    }
                # 2d. Known feedback types that need wrapping into agent_feedback
                elif dict_type in [
                    "file_read", "web_search_complete", "web_fetch_start",
                    "web_fetch_complete", "note_generated", "note_updated_from_full_content",
                    "tool_usage_status", "thread_status" # Add any other known types passed directly
                ]:
                    logger.debug(f"Wrapping known dict type '{dict_type}' into agent_feedback.")
                    queue_item = {
                        "type": "agent_feedback",
                        "payload": update_data # The original dict becomes the payload
                    }
            # 2e. Handle the 'conducting_research' signal (treat as status update)
            elif dict_type == "conducting_research":
                logger.info(f"UI Callback: Received 'conducting_research' signal dict. Treating as status update.")
                # This signal primarily updates the status and potentially fetches the plan.
                # We can queue it as a standard update with the status.
                queue_item = {
                    "type": "update",
                    "log_entry": None, # No specific log entry associated with this signal itself
                    "mission_id": mission_id, # Pass along the mission ID if available
                    "status": "conducting_research" # Set the status explicitly
                }

            # 2f. Handle other unexpected dictionaries (Log warning, wrap as before for now)
            else:
                logger.warning(f"ui_update_callback received unexpected dict type: '{dict_type}'. Content: {update_data}. Wrapping as standard update.")
                queue_item = {
                    "type": "update",
                    "log_entry": update_data, # Pass the unexpected dict as log_entry
                    "mission_id": mission_id,
                    "status": status
                }
            # Put the processed item onto the queue
            if queue_item:
                log_queue.put(queue_item)
            else:
                 # Log the problematic data that resulted in queue_item being None
                 logger.error(f"Failed to create a queue_item in ui_update_callback. Received update_data type: {type(update_data)}, content: {update_data}")

        except Exception as e:
            # Log errors during queue operation or item creation, including the data being processed
            logger.error(f"Error processing item in ui_update_callback: {e}. Data was: {update_data}", exc_info=True)
            logger.error(f"Error putting item into queue: {e}", exc_info=True)
    else:
        # Corrected logging format string
        logger.error(f"ui_update_callback called with None queue. Update dropped: {update_data}, {mission_id}, {status}")


# --- UI Elements (Main Area) ---

# --- Add Initial Chat Message if needed (Ensure it happens only once) ---
# This needs to happen before the loop that displays messages
if 'messages_initialized' not in st.session_state:
    if not st.session_state.messages: # Double check if empty
        initial_message = "Hello! What research topic are you interested in today?"
        st.session_state.messages.append({"role": "assistant", "content": initial_message})
    st.session_state.messages_initialized = True # Mark as initialized

# --- Chat Area (Directly in Main Area - Following Streamlit Example) ---
# st.subheader("Chat") # Add a header for the chat section

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Tool Selection Checkboxes and Start Research Button (Only during refining_questions) ---
if st.session_state.mission_status == "refining_questions":
    st.markdown("---") # Visual separator
    st.markdown("**Select Research Sources:**")
    col1, col2 = st.columns(2)
    with col1:
        # Read current state for the value argument
        current_local_rag_value = st.session_state.tool_selection.get('local_rag', True)
        # Render checkbox and get its new state from this run
        new_local_rag_value = st.checkbox(
            "Use Local Documents (RAG)",
            value=current_local_rag_value,
            key="local_rag_checkbox",
            disabled=st.session_state.agent_processing
        )
        # Update session state only if the value changed
        if new_local_rag_value != current_local_rag_value:
            st.session_state.tool_selection['local_rag'] = new_local_rag_value
            # Optional: Log the change
            # logger.info(f"UI: local_rag checkbox changed to {new_local_rag_value}")

    with col2:
        # Read current state for the value argument
        current_web_search_value = st.session_state.tool_selection.get('web_search', True)
        # Render checkbox and get its new state from this run
        new_web_search_value = st.checkbox(
            "Use Web Search",
            value=current_web_search_value,
            key="web_search_checkbox",
            disabled=st.session_state.agent_processing
        )
        # Update session state only if the value changed
        if new_web_search_value != current_web_search_value:
            st.session_state.tool_selection['web_search'] = new_web_search_value
            # Optional: Log the change
            # logger.info(f"UI: web_search checkbox changed to {new_web_search_value}")
    
    # Add Start Research button
    start_research_button = st.button(
        "Start Research",
        key="start_research_button",
        disabled=st.session_state.agent_processing,
        type="primary"  # Make it stand out as the primary action
    )
    
    # Handle button click
    if start_research_button:
        # Add a message to the chat history as if the user typed "start research"
        st.session_state.messages.append({"role": "user", "content": "start research"})
        # Set processing flag to trigger agent processing
        st.session_state.agent_processing = True
        # Rerun to process the simulated message
        st.rerun()
    
    st.markdown("---") # Visual separator

# --- Chat Input Logic (Directly in Main Area) ---
# Determine if chat input should be disabled
# Disable if agent is processing OR if mission is in a non-interactive state
chat_disabled = st.session_state.agent_processing or st.session_state.mission_status not in ["awaiting_request", "refining_questions"]
prompt_text = "Ask about research or refine questions..." if st.session_state.mission_status == "awaiting_request" else "Provide feedback or type 'start research'..."

if user_input := st.chat_input(prompt_text, disabled=chat_disabled, key="chat_input"):
    # Add user message to chat history and display it immediately
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # --- Set processing flag and rerun to disable input ---
    st.session_state.agent_processing = True
    st.rerun() # Rerun immediately to disable the input field

# --- Agent Processing Logic (Only run if agent_processing is True) ---
# This block now runs *after* the rerun caused by setting agent_processing = True
if st.session_state.agent_processing:
    # Get the last user message (which triggered this processing)
    # Note: This assumes the last message is always the user's trigger
    last_user_input = st.session_state.messages[-1]["content"] if st.session_state.messages and st.session_state.messages[-1]["role"] == "user" else None

    if last_user_input:
        try:
            # --- Handle Awaiting Request State ---
            if st.session_state.mission_status == "awaiting_request":
                with st.chat_message("assistant"):
                    message_placeholder = st.empty()
                    message_placeholder.markdown("Thinking...")
                    try:
                        # Prepare chat history for MessengerAgent (exclude last user input here)
                        history_tuples = [(msg["content"], "") if msg["role"] == "user" else ("", msg["content"])
                                          for msg in st.session_state.messages[:-1]]

                        # Run MessengerAgent to check intent
                        messenger_output, _, scratchpad_update = asyncio.run(messenger_agent.run(
                            user_message=last_user_input, # Use the captured input
                            chat_history=history_tuples
                        ))

                        assistant_response = messenger_output.get("response", "Sorry, I couldn't process that.")
                        action = messenger_output.get("action")
                        request = messenger_output.get("request") # Holds topic for start_research, feedback for refine_*, null otherwise

                        message_placeholder.markdown(assistant_response)
                        st.session_state.messages.append({"role": "assistant", "content": assistant_response})

                        # --- Handle Actions from Messenger ---
                        # Note: refine_goal is handled in the refining_questions block now
                        if action == "start_research" and request:
                            logger.info(f"UI: Research intent detected. Request: '{request}'")
                            try:
                                # Create a new mission context
                                mission_context = context_manager.start_mission(user_request=request)
                                mission_id = mission_context.mission_id
                                st.session_state.mission_id = mission_id # Store the mission ID
                                # Reset the report_saved flag for the new mission
                                st.session_state.report_saved = False
                                logger.info(f"UI: Created new mission with ID: {mission_id}")

                                # Check if there were formatting preferences in the agent output
                                formatting_preferences = messenger_output.get("formatting_preferences")
                                if formatting_preferences:
                                    goal_id = context_manager.add_goal(
                                        mission_id=mission_id,
                                        text=formatting_preferences,
                                        source_agent="MessengerAgent"
                                    )
                                    logger.info(f"UI: Added formatting preferences as goal '{goal_id}': '{formatting_preferences}'")

                                # 2. Generate Initial Questions (Correct Unpacking)
                                initial_questions, model_details = asyncio.run(agent_controller.research_manager._generate_first_level_questions(
                                    user_request=request, # Use the research topic request here
                                    log_queue=st.session_state.log_queue,
                                    update_callback=ui_update_callback
                                ))

                                # --- FIX: Update stats for the question generation call ---
                                if model_details:
                                    # Call the method on context_manager instead
                                    context_manager.update_mission_stats(mission_id, model_details, st.session_state.log_queue, ui_update_callback)
                                # --- End FIX ---

                                # 3. Update Session State Correctly
                                st.session_state.mission_status = "refining_questions"
                                st.session_state.current_questions = initial_questions # Store the actual questions
                                logger.info(f"UI: Transitioning to refining_questions. Mission ID: {mission_id}. Questions generated: {len(initial_questions)}")

                                # 4. Format and Display Questions Correctly
                                questions_text = "I've generated some initial questions based on your request:\n\n"
                                # Iterate over the correct 'initial_questions' list
                                for i, q in enumerate(initial_questions):
                                    questions_text += f"{i+1}. {q}\n"
                                questions_text += "\nHow do these look? You can suggest changes, additions, or type 'start research' to proceed."
                                st.session_state.messages.append({"role": "assistant", "content": questions_text})
                                # State change will trigger rerun naturally

                            except Exception as e:
                                error_message = f"Error starting mission or generating initial questions: {e}"
                                logger.error(error_message, exc_info=True)
                                message_placeholder.error(error_message)
                                st.session_state.messages.append({"role": "assistant", "content": f"Error: {error_message}"})

                    except Exception as e:
                        logger.error(f"Error calling MessengerAgent (awaiting_request): {e}", exc_info=True)
                        error_message = f"Sorry, an error occurred: {e}"
                        message_placeholder.markdown(error_message)
                        st.session_state.messages.append({"role": "assistant", "content": error_message})

            # --- Handle Refining Questions State ---
            elif st.session_state.mission_status == "refining_questions":
                with st.chat_message("assistant"):
                    message_placeholder = st.empty()
                    message_placeholder.markdown("Processing feedback...")
                    try:
                        # Prepare chat history (exclude last user input)
                        history_tuples = [(msg["content"], "") if msg["role"] == "user" else ("", msg["content"])
                                         for msg in st.session_state.messages[:-1]]
                        # Run MessengerAgent to check intent (approval, refinement, or chat)
                        # Correctly unpack the three return values
                        agent_output, model_details, scratchpad_update = asyncio.run(messenger_agent.run(
                            user_message=last_user_input,
                            chat_history=history_tuples,
                            mission_context_summary=f"Current Mission ({st.session_state.mission_id}): Refining questions." # Provide context
                        ))
                        # Access results from the agent_output dictionary
                        action = agent_output.get("action")
                        assistant_response = agent_output.get("response", "Sorry, I couldn't process that.")
                        request = agent_output.get("request") # Holds goal text for refine_goal, null otherwise

                        # Display agent's response first
                        message_placeholder.markdown(assistant_response)
                        st.session_state.messages.append({"role": "assistant", "content": assistant_response})

                        # --- Handle Action ---
                        if action == "refine_goal" and request:
                            # Directly add the goal since mission_id exists
                            if st.session_state.mission_id:
                                try:
                                    goal_id = context_manager.add_goal(st.session_state.mission_id, request, source_agent="MessengerAgent (Refining)")
                                    if goal_id:
                                        logger.info(f"UI: Added goal '{request[:50]}...' (ID: {goal_id}) during refining_questions state.")
                                        # Agent's response already shown, no extra message needed here.
                                    else:
                                        logger.error(f"UI: Failed to add goal '{request[:50]}...' during refining_questions state.")
                                        # Optionally add an error message to chat?
                                        st.session_state.messages.append({"role": "assistant", "content": f"Error: Could not save the goal: '{request[:50]}...'"})
                                except Exception as add_goal_e:
                                    logger.error(f"UI: Error adding goal during refining_questions state: {add_goal_e}", exc_info=True)
                                    st.session_state.messages.append({"role": "assistant", "content": f"Error adding goal: {add_goal_e}"})
                            else:
                                logger.error("UI: Cannot add goal during refining_questions state because mission_id is missing.")
                                st.session_state.messages.append({"role": "assistant", "content": "Internal Error: Cannot save goal, mission context lost."})
                            # Stay in refining_questions state

                        elif action == "approve_questions":
                            logger.info(f"UI: User triggered 'approve_questions' (via MessengerAgent) for mission {st.session_state.mission_id}.")

                            # --- Validation: Check if at least one tool is selected ---
                            use_local = st.session_state.tool_selection.get('local_rag', False)
                            use_web = st.session_state.tool_selection.get('web_search', False)

                            if not use_local and not use_web:
                                logger.warning(f"UI: Validation failed for mission {st.session_state.mission_id}. No research source selected.")
                                # Agent's approval response was already added, add the validation error message
                                validation_error_msg = "⚠️ **Validation Error:** Please select at least one research source (Local Documents or Web Search) using the checkboxes above before starting the research."
                                st.session_state.messages.append({"role": "assistant", "content": validation_error_msg})
                                # Stay in refining_questions state, reset processing flag later in finally block
                            else:
                                logger.info(f"UI: Tool selection validated for mission {st.session_state.mission_id} (Local: {use_local}, Web: {use_web}). Proceeding to confirmation.")
                                # No need for a separate approval message, agent's response should cover it.
                                st.session_state.mission_status = "initializing"
                                st.session_state.log_queue = queue.Queue() # Create queue before starting thread
                                try:
                                    # 1. Confirm questions (synchronous, updates context)
                                    # Pass tool selection to confirm_questions_and_run
                                    confirm_success = asyncio.run(agent_controller.confirm_questions_and_run(
                                        mission_id=st.session_state.mission_id,
                                        final_questions=st.session_state.current_questions,
                                        tool_selection=st.session_state.tool_selection, # <-- Pass the selection state
                                        log_queue=st.session_state.log_queue, # Pass queue for potential logging during confirm
                                        update_callback=ui_update_callback
                                    ))

                                    if confirm_success:
                                        logger.info(f"UI: Questions confirmed for mission {st.session_state.mission_id}. Status set to 'initializing' to trigger background thread.")
                                        # State is already 'initializing', log queue is created.
                                        # The background thread will be started on the next rerun by the 'initializing' state check.
                                    else:
                                        # Handle confirmation failure
                                        error_message = "Failed to confirm questions with the backend."
                                        logger.error(error_message)
                                        # Agent's response already shown, maybe add an error message?
                                        st.session_state.messages.append({"role": "assistant", "content": f"Error: {error_message}"})
                                        st.session_state.mission_status = "failed"
                                        st.session_state.mission_error = error_message

                                except Exception as e:
                                    error_message = f"Error during mission preparation (confirming questions): {e}"
                                    logger.error(error_message, exc_info=True)
                                    st.session_state.messages.append({"role": "assistant", "content": f"Error: {error_message}"})
                                    st.session_state.mission_status = "failed"
                                    st.session_state.mission_error = error_message

                        elif action == "refine_questions":
                            logger.info(f"UI: Refining questions based on feedback (via MessengerAgent): '{last_user_input}'")
                            # Unpack the tuple: (list_of_questions, response_string_for_user)
                            refined_questions, response_string = asyncio.run(agent_controller.refine_questions(
                                mission_id=st.session_state.mission_id,
                                user_feedback=last_user_input, # Use the original user input as feedback
                                current_questions=st.session_state.current_questions,
                                log_queue=st.session_state.log_queue,
                                update_callback=ui_update_callback
                            ))
                            st.session_state.current_questions = refined_questions
                            # Agent's initial response ("Processing feedback...") is already shown.
                            # Now, add the complete response string from the controller, which includes the refined questions.
                            st.session_state.messages.append({"role": "assistant", "content": response_string})
                            # Rerun will display the new message containing the refined questions and prompt.

                        else: # Handle "chat" or other unexpected actions
                            logger.info(f"UI: MessengerAgent returned action '{action}'. No state change.")
                            # Agent's response is already displayed. Stay in refining_questions state.

                    except Exception as e:
                        logger.error(f"Error calling MessengerAgent or processing action (refining_questions): {e}", exc_info=True)
                        error_message = f"Sorry, an error occurred: {e}"
                        message_placeholder.markdown(error_message) # Update placeholder with error
                        st.session_state.messages.append({"role": "assistant", "content": error_message})

        finally:
            # --- Reset processing flag and rerun ---
            st.session_state.agent_processing = False
            st.rerun() # Rerun to re-enable input and show results
    else:
        # If last_user_input is None (shouldn't happen with this logic), reset flag
        st.session_state.agent_processing = False
        st.rerun()

# Initialize rerun flags before the processing/checking section
needs_immediate_rerun = False
schedule_polling_rerun = False
thread_is_currently_alive = False

# --- Start Background Thread if Initializing ---
# This block runs on every script rerun.
# It checks if we are in the initializing state AND the thread hasn't been started yet.
if st.session_state.mission_status == "initializing" and st.session_state.mission_thread is None:
    # Check if mission_id and log_queue exist (questions should be confirmed by now)
    mission_id = st.session_state.get('mission_id')
    log_queue = st.session_state.get('log_queue')

    if mission_id and log_queue:
        logger.info(f"UI: Initializing state detected. Starting background thread (planning & execution) for mission {mission_id}.")
        thread = threading.Thread(
            target=run_full_mission_background, # Use the new background function
            args=(
                agent_controller, # Pass controller
                mission_id,       # Pass mission_id
                log_queue,        # Pass log_queue
                ui_update_callback # Pass callback
            ),
            daemon=True
        )
        st.session_state.mission_thread = thread # Assign thread to session state
        thread.start()
        # Transition to 'running' state immediately after starting thread
        # Note: The background thread will first run planning, then execution.
        # The UI will show 'running' during both phases, but log entries will differentiate.
        st.session_state.mission_status = "running"
        logger.info("UI: Status set to 'running' after starting background thread.")
        needs_immediate_rerun = True # Rerun to reflect 'running' status and start polling
    elif not log_queue:
         logger.error(f"UI Error: In 'initializing' state but log_queue is None. Cannot start thread.")
         st.session_state.mission_status = "failed"
         st.session_state.mission_error = "Internal UI error: Log queue not initialized before thread start."
         needs_immediate_rerun = True
    elif not mission_id:
         logger.error(f"UI Error: In 'initializing' state but mission_id is None. Cannot start thread.")
         st.session_state.mission_status = "failed"
         st.session_state.mission_error = "Internal UI error: Mission ID missing before thread start."
         needs_immediate_rerun = True


# --- Process Queue and Check Thread (For running and conducting_research states) ---
# This logic applies to both the planning/execution phase and the research phase

# Combined check for running and conducting_research states
# Note: 'initializing' is now a very brief state, mostly handled by the block above.
# We monitor both 'running' and 'conducting_research' states to ensure continuous feedback.
if st.session_state.mission_status in ["running", "conducting_research", "warning", "failed", "completed"]:
    # Mission ID should be set by now
    mission_id = st.session_state.mission_id
    current_log_queue = st.session_state.log_queue # Get the queue for this mission

    # Ensure thread exists if we are in 'running' state
    if st.session_state.mission_thread is None and current_log_queue is not None:
         # If status is 'running' but thread is None, something went wrong after the 'initializing' start block
         logger.error(f"UI Error: In status 'running' but mission_thread is None. Resetting.")
         st.session_state.mission_status = "failed"
         st.session_state.mission_error = "Internal UI error: Background execution thread lost."
         needs_immediate_rerun = True
    elif current_log_queue is not None:
        # --- DIAGNOSTIC TOAST ---
        # st.toast("UI: Checking log queue...", icon="📬")
        # --- END DIAGNOSTIC TOAST ---
        # Process items from the queue (Keep existing queue processing logic)
        log_updated = False
        temp_log_list = st.session_state.execution_log[:] # Copy current log
        toasts_to_show = [] # Initialize list to collect toasts for this cycle
        while not current_log_queue.empty():
            try:
                queue_item = current_log_queue.get_nowait() # Get the dictionary

                # Check the type of update
                update_type = queue_item.get("type")

                if update_type == "update":
                    log_entry = queue_item.get("log_entry")
                    received_mission_id = queue_item.get("mission_id")
                    received_status = queue_item.get("status")

                    # --- Handle Mission ID Update (Should match current mission) ---
                    if received_mission_id and st.session_state.mission_id != received_mission_id:
                         logger.warning(f"UI: Received log for mission {received_mission_id} but current mission is {st.session_state.mission_id}. Ignoring.")
                         continue # Skip processing if ID doesn't match

                     # --- Handle Status Update ---
                    if received_status and st.session_state.mission_status != received_status:
                        # --- Handle Non-Terminal Statuses (like 'conducting_research') ---
                        if received_status == "conducting_research":
                            logger.info(f"UI: Received 'conducting_research' signal for mission {received_mission_id}. Fetching plan...")
                            try:
                                mission_context = context_manager.get_mission_context(received_mission_id)
                                if mission_context and mission_context.plan:
                                    st.session_state.mission_plan = mission_context.plan
                                    st.session_state.mission_status = "conducting_research"
                                    logger.info(f"UI: Updated mission plan in session state and set status to 'conducting_research'.")
                                    log_updated = True # Trigger rerun to display the plan
                                else:
                                    logger.warning(f"UI: 'conducting_research' signal received, but context or plan not found for mission {received_mission_id}.")
                            except Exception as fetch_e:
                                logger.error(f"UI: Error fetching plan after 'conducting_research' signal: {fetch_e}", exc_info=True)
                        # --- Handle Terminal Status Updates (completed, failed) ---
                        elif received_status in ["completed", "failed"]:
                            # Only update if the current status isn't already terminal
                            if st.session_state.mission_status not in ["completed", "failed"]:
                                st.session_state.mission_status = received_status
                                logger.info(f"UI: Status updated to terminal state '{received_status}' via callback for mission {st.session_state.mission_id}.")
                                log_updated = True # Rerun needed to display final status
                                # If status becomes failed, try to get error from log entry if present
                                if received_status == "failed" and log_entry and hasattr(log_entry, 'error_message') and log_entry.error_message:
                                     st.session_state.mission_error = log_entry.error_message
                            else:
                                # Log if we receive a different terminal status than the current one (e.g., completed then failed)
                                if st.session_state.mission_status != received_status:
                                     logger.warning(f"UI: Received terminal status '{received_status}' but current status is already terminal '{st.session_state.mission_status}'. Updating anyway.")
                                     st.session_state.mission_status = received_status # Allow update if different terminal state
                                     log_updated = True
                                     if received_status == "failed" and log_entry and hasattr(log_entry, 'error_message') and log_entry.error_message:
                                          st.session_state.mission_error = log_entry.error_message
                                else:
                                     logger.info(f"UI: Ignoring status update '{received_status}' because current status is already terminal '{st.session_state.mission_status}'.")
                        # --- Ignore 'warning' status for overall mission state ---
                        elif received_status == "warning":
                            logger.info(f"UI: Received 'warning' status log for mission {st.session_state.mission_id}. Ignoring for overall mission status update.")
                            # Do NOT change st.session_state.mission_status based on a warning
                        else:
                            # Handle other potential non-terminal statuses if needed, or log unexpected ones
                            logger.warning(f"UI: Received unexpected non-terminal status '{received_status}' for mission {st.session_state.mission_id}. Ignoring for overall mission status update.")

                    # --- Handle Log Entry ---
                    if log_entry is not None:
                        # --- MODIFIED Type Check and Routing: Route Tool Executions to Toasts ---
                        if isinstance(log_entry, ExecutionLogEntry):
                            is_tool_execution = hasattr(log_entry, 'action') and log_entry.action.startswith("Execute Tool:")

                            if is_tool_execution:
                                pass
                                # --- Route to Toast ---
                                # agent_name = getattr(log_entry, 'agent_name', 'Agent')
                                # action = getattr(log_entry, 'action', 'Tool Execution')
                                # status = getattr(log_entry, 'status', 'unknown').upper()
                                # error_msg = getattr(log_entry, 'error_message', None)
                                # output_summary = getattr(log_entry, 'output_summary', None)

                                # # Extract tool name from action
                                # tool_name = action.replace("Execute Tool:", "").strip()

                                # toast_msg = f"{agent_name} - {tool_name}: {status}"
                                # if status == "FAILURE" and error_msg:
                                #     toast_msg += f" - Error: {error_msg[:100]}" # Truncate long errors
                                # elif status == "SUCCESS" and output_summary:
                                #      toast_msg += f" - {output_summary[:100]}" # Truncate long summaries

                                # toast_icon = "🛠️" # Default tool icon
                                # if status == "FAILURE": toast_icon = "❌"
                                # elif status == "SUCCESS": toast_icon = "✅"

                                # toasts_to_show.append({"message": toast_msg, "icon": toast_icon})
                                # log_updated = True # Ensure UI refreshes for toasts even if main log doesn't change

                            else:
                                # --- Route to Main Execution Log ---
                                temp_log_list.append(log_entry)
                                log_updated = True # Flag that the log display needs updating

                            # --- Fallback Status Update from Log Entry Status (Applies to both routes) ---
                            # Only update to 'failed' if the log entry status is 'failure' AND the current mission status isn't already terminal
                            # AND the error is not just a network error for fetching a URL (which shouldn't fail the entire mission)
                            if log_entry.status == "failure" and st.session_state.mission_status not in ["completed", "failed"]:
                                # Check if this is a network error for fetching a URL or content extraction error
                                error_msg = log_entry.error_message or ""
                                is_url_fetch_error = "Network error occurred while fetching URL" in error_msg or "403" in error_msg
                                is_content_extraction_error = "Could not extract main text content from HTML page" in error_msg
                                
                                if not is_url_fetch_error and not is_content_extraction_error:
                                    # Only set mission to failed if it's not a URL fetch error or content extraction error
                                    st.session_state.mission_status = "failed"
                                    st.session_state.mission_error = error_msg or "Mission failed (reported via log)."
                                    logger.warning(f"UI: Mission status set to failed due to 'failure' status in log entry (fallback): {error_msg}")
                                else:
                                    # Log the URL fetch or content extraction error but don't fail the mission
                                    logger.warning(f"UI: Ignoring non-critical error (not failing mission): {error_msg}")
                            # Explicitly ignore 'warning' status from log entry for overall mission status
                            elif log_entry.status == "warning":
                                 logger.info(f"UI: Log entry received with status 'warning'. Not changing overall mission status.")

                            # --- Check for Plan Generation/Update (from log entry) (Keep this logic) ---
                            if (log_entry.agent_name == "PlanningAgent" and
                                log_entry.action in ["Generate Preliminary Outline", "Revise Outline (Inter-Pass)", "Generate Plan from Confirmed Qs", "Finalize Preliminary Outline", "Revise Outline (Batch 2)"] and # Added more planning actions
                                log_entry.status == "success" and
                                isinstance(log_entry.full_output, dict)):
                                try:
                                    plan_data = log_entry.full_output
                                    if 'mission_goal' in plan_data and 'report_outline' in plan_data and 'steps' in plan_data:
                                        # Attempt to fetch/parse plan (keep existing parsing logic)
                                        fetched_plan = None
                                        if st.session_state.mission_id:
                                            mission_context = context_manager.get_mission_context(st.session_state.mission_id)
                                            if mission_context and mission_context.plan:
                                                fetched_plan = mission_context.plan

                                        if fetched_plan:
                                             st.session_state.mission_plan = fetched_plan
                                             logger.info(f"UI: Updated mission plan from context after '{log_entry.action}' log.")
                                        else:
                                             # Fallback: try parsing from log entry directly
                                             def parse_sections(section_data_list: List[Dict[str, Any]]) -> List[ReportSection]:
                                                 sections = []
                                                 for data in section_data_list:
                                                     subsections = parse_sections(data.get('subsections', []))
                                                     sections.append(ReportSection(
                                                         section_id=data.get('section_id', str(uuid.uuid4())),
                                                         title=data.get('title', 'Untitled Section'),
                                                         description=data.get('description', ''),
                                                         subsections=subsections
                                                     ))
                                                 return sections
                                             parsed_outline = parse_sections(plan_data.get('report_outline', []))
                                             parsed_steps = []
                                             for step_data in plan_data.get('steps', []):
                                                  parsed_steps.append(PlanStep(
                                                      step_id=step_data.get('step_id', str(uuid.uuid4())),
                                                      description=step_data.get('description', 'No description'),
                                                      action_type=step_data.get('action_type'), # <-- Added missing field
                                                      target_section_id=step_data.get('target_section_id')
                                                  ))
                                             parsed_plan = SimplifiedPlan(
                                                 mission_goal=plan_data.get('mission_goal', 'Goal not specified'),
                                                 report_outline=parsed_outline,
                                                 steps=parsed_steps
                                             )
                                             st.session_state.mission_plan = parsed_plan
                                             logger.info(f"UI: Updated mission plan by parsing '{log_entry.action}' log entry.")
                                    else:
                                        logger.warning(f"UI: Planning log entry '{log_entry.action}' missing expected keys in full_output: {plan_data.keys()}")
                                except Exception as parse_e:
                                    logger.error(f"UI: Failed to process plan from '{log_entry.action}' log entry: {parse_e}", exc_info=True)
                            # --- End Plan Check ---
                        # --- ADDED: Handle other dictionary types within 'update' message ---
                        elif isinstance(log_entry, dict):
                            # Log that we received it, but don't add it to the main execution log display
                            dict_type = log_entry.get("type", "unknown_dict")
                            logger.info(f"UI: Received dictionary of type '{dict_type}' within 'update' message. Ignoring for main log display. Content: {str(log_entry)[:200]}...")
                            # Optionally, handle specific dict types like 'model_call_details' differently if needed later
                        else:
                            # Log if it's neither ExecutionLogEntry nor dict
                            logger.warning(f"UI: Received unexpected data type '{type(log_entry)}' in 'log_entry' of 'update' message. Ignoring. Content: {str(log_entry)[:200]}...")
                        # --- END ADDED ---

                    # --- Handle Thread Completion Signal (log_entry is None) ---
                    elif log_entry is None:
                         log_mission_id = received_mission_id or st.session_state.mission_id # Should have mission_id
                         log_status = received_status or "unknown"
                         logger.info(f"UI: Received completion signal (None log_entry) from queue for mission {log_mission_id} with status '{log_status}'.")
                         # Update status if provided in the signal
                         if received_status and st.session_state.mission_status != received_status:
                              # Only update if status actually changed and isn't overwriting a final state inappropriately
                              if st.session_state.mission_status not in ["completed", "failed"] or received_status in ["completed", "failed"]:
                                   st.session_state.mission_status = received_status
                         # Thread finished, let the thread check logic below handle final state update

                elif update_type == "agent_feedback":
                    # --- Handle Agent Feedback Message ---
                    feedback_payload = queue_item.get("payload", {})
                    feedback_type = feedback_payload.get("type")
                    toast_msg = None
                    toast_icon = None
                    if feedback_type == "file_read":
                        original_filename = feedback_payload.get("original_filename")
                        markdown_filename = feedback_payload.get("filename", "Unknown file")
                        display_name = original_filename if original_filename else markdown_filename
                        toast_msg = f"Read: {display_name}"
                        toast_icon = "📄"
                    elif feedback_type == "web_search_complete":
                        query = feedback_payload.get("query", "Unknown query")
                        num_results = feedback_payload.get("num_results", 0)
                        toast_msg = f"Web Search: Found {num_results} results for '{query[:50]}...'" # Truncate query
                        toast_icon = "🌐"
                    elif feedback_type == "web_fetch_start": # <-- Add handler
                        url = feedback_payload.get("url", "Unknown URL")
                        toast_msg = f"Fetching content from: {url}"
                        toast_icon = "⏳"
                    elif feedback_type == "web_fetch_complete": # <-- Add handler
                        url = feedback_payload.get("url", "Unknown URL")
                        title = feedback_payload.get("title", "Unknown Title")
                        length = feedback_payload.get("content_length", 0)
                        toast_msg = f"Fetched ~{length} chars from '{title}' ({url})"
                        toast_icon = "✅"
                    elif feedback_type == "note_generated":
                        note_id = feedback_payload.get("note_id", "Unknown")
                        source_type = feedback_payload.get("source_type", "Unknown")
                        source_id = feedback_payload.get("source_id", "Unknown")
                        raw_preview = feedback_payload.get("content_preview", "")
                        preview = raw_preview.replace('`', '')
                        source_metadata = feedback_payload.get("source_metadata", {})
                        display_source = source_id # Default to source_id (URL or doc_id)
                        if source_type == "document_window":
                            # Try to get original filename from the first chunk's metadata
                            overlapping_chunks = source_metadata.get("overlapping_chunks", [])
                            if overlapping_chunks and isinstance(overlapping_chunks[0], dict):
                                display_source = overlapping_chunks[0].get("original_filename", source_id)
                        elif source_type == "web":
                            # For web, use the title if available, else the URL
                            display_source = source_metadata.get("title", source_id)

                        toast_msg = f"Created: {note_id} from '{display_source}' - '{preview}'"
                        toast_icon = "📝"
                    elif feedback_type == "note_updated_from_full_content": # <-- Add handler
                        new_note_id = feedback_payload.get("new_note_id", "Unknown")
                        source_id = feedback_payload.get("source_id", "Unknown URL") # Should be URL
                        raw_preview = feedback_payload.get("content_preview", "")
                        preview = raw_preview.replace('`', '')
                        toast_msg = f"Updated Note {new_note_id} from full content: {source_id} - '{preview}'"
                        toast_icon = "✨"
                    elif feedback_type == "tool_usage_status": # <-- Enhanced handler for tool status
                        local_enabled = feedback_payload.get("local_rag_enabled", False)
                        web_enabled = feedback_payload.get("web_search_enabled", False)
                        round_num = feedback_payload.get("round", 1)
                        # Store the status in session state for display elsewhere
                        st.session_state.tool_usage_display = {"local": local_enabled, "web": web_enabled}
                        log_updated = True # Trigger UI update to show the status
                        
                        # Create a more prominent toast message
                        status_parts = []
                        if local_enabled: status_parts.append("Local Docs: ON")
                        else: status_parts.append("Local Docs: OFF")
                        if web_enabled: status_parts.append("Web Search: ON")
                        else: status_parts.append("Web Search: OFF")
                        
                        # Make the message more informative with round number
                        toast_msg = f"Research Round {round_num}: Using {', '.join(status_parts)}"
                        toast_icon = "🔍" # Changed to a search icon for better visibility
                    else:
                        # Generic fallback feedback toast - IMPROVED
                        keys = ", ".join(feedback_payload.keys())
                        toast_msg = f"Agent Info ({feedback_type}): Keys=[{keys}]" # Show type and keys instead of full JSON
                        toast_icon = "ℹ️"

                    # Append toast details to list instead of calling st.toast here
                    if toast_msg:
                        toasts_to_show.append({"message": toast_msg, "icon": toast_icon})

                elif update_type == "stats_update":
                    # --- Handle Stats Update Message (Absolute and Incremental) ---
                    stats_payload = queue_item.get("payload", {})
                    received_mission_id = queue_item.get("mission_id")

                    # Ensure update is for the current mission and mission_id exists in state
                    if received_mission_id and 'mission_id' in st.session_state and st.session_state.mission_id == received_mission_id:
                        # Check for absolute updates first
                        new_cost = stats_payload.get("total_cost")
                        new_tokens = stats_payload.get("total_native_tokens")
                        # Note: Absolute web search calls update is less likely now, but keep for robustness
                        new_web_search_calls = stats_payload.get("total_web_search_calls")

                        if new_cost is not None:
                            st.session_state.total_cost = float(new_cost)
                            log_updated = True
                        if new_tokens is not None:
                            st.session_state.total_native_tokens = float(new_tokens)
                            log_updated = True
                        if new_web_search_calls is not None:
                            st.session_state.total_web_search_calls = int(new_web_search_calls)
                            log_updated = True

                        # Check for incremental updates (e.g., from re-queued stats_increment)
                        web_search_increment = stats_payload.get("increment_web_search")
                        # Add checks for other potential increments here if needed

                        if web_search_increment is not None:
                            try:
                                current_calls = st.session_state.get('total_web_search_calls', 0)
                                st.session_state.total_web_search_calls = current_calls + int(web_search_increment)
                                logger.info(f"UI: Incremented web search calls by {web_search_increment} to {st.session_state.total_web_search_calls} for mission {received_mission_id}.")
                                log_updated = True
                            except (ValueError, TypeError) as e:
                                logger.error(f"UI: Error processing web_search increment value '{web_search_increment}': {e}")

                        # Log final state if any update occurred
                        if log_updated:
                            logger.debug(f"UI: Updated stats state: Cost=${st.session_state.total_cost:.6f}, Tokens={st.session_state.total_native_tokens}, Web Searches={st.session_state.total_web_search_calls}")
                            # log_updated = True # Already set if any update happened

                    elif received_mission_id: # Log mismatch only if received_mission_id was present
                        logger.warning(f"UI: Received stats_update for mission {received_mission_id} but current mission is {st.session_state.get('mission_id', 'None')}. Ignoring.")
                    # else: # No mission ID received, cannot process
                    #    logger.warning(f"UI: Received stats_update without mission_id. Ignoring. Payload: {stats_payload}")
                    # --- End Handle Stats Update ---

                else:
                    logger.warning(f"UI: Received unexpected item type from queue: {type(queue_item)}")

                current_log_queue.task_done()
            except queue.Empty:
                break # No more items for now
            except Exception as q_e:
                logger.error(f"Error processing log queue: {q_e}")
                break

        # --- Display collected toasts AFTER processing the queue ---
        for toast_info in toasts_to_show:
            st.toast(toast_info["message"], icon=toast_info["icon"])

        # Update session state log only once after processing queue if changes occurred
        if log_updated:
            st.session_state.execution_log = temp_log_list
            needs_immediate_rerun = True # Force rerun after log update

        # Check thread status
        # --- DIAGNOSTIC TOAST ---
        # st.toast("UI: Checking background thread status...", icon="🧵")
        # --- END DIAGNOSTIC TOAST ---
        # Check thread status
        if st.session_state.mission_thread and st.session_state.mission_thread.is_alive():
            thread_is_currently_alive = True
            # ALWAYS schedule polling if the thread is alive to keep checking queue/status
            schedule_polling_rerun = True
        elif st.session_state.mission_thread: # Thread is not alive, must have finished
            # --- DIAGNOSTIC TOAST ---
            # st.toast("UI: Background thread detected as finished.", icon="🏁")
            # --- END DIAGNOSTIC TOAST ---
            log_mission_id = st.session_state.mission_id # Should have mission_id
            logger.info(f"UI: Background thread for mission {log_mission_id} confirmed finished.")

            # Fetch final context state using the mission_id
            final_context = context_manager.get_mission_context(st.session_state.mission_id)

            if final_context:
                st.session_state.mission_status = final_context.status
                st.session_state.mission_plan = final_context.plan
                st.session_state.final_report = final_context.final_report
                st.session_state.mission_error = final_context.error_info
                st.session_state.execution_log = final_context.execution_log[:] # Ensure final log state
            else:
                # If context couldn't be retrieved, mark as failed
                st.session_state.mission_status = "failed"
                st.session_state.mission_error = st.session_state.mission_error or "Failed to retrieve final mission context."

            # Correct status if thread died unexpectedly during initializing/running
            if st.session_state.mission_status in ["initializing", "running"]:
                st.session_state.mission_status = "failed"
                st.session_state.mission_error = st.session_state.mission_error or "Background thread finished unexpectedly."

            st.session_state.mission_thread = None
            st.session_state.log_queue = None
            needs_immediate_rerun = True # Rerun to show final state


# --- Display Area (Main Page - Conditionally Show Mission Details) ---

# Define placeholder outside the condition
status_placeholder = None

# Ensure mission_status is initialized before accessing it
if 'mission_status' not in st.session_state:
    st.session_state.mission_status = "awaiting_request"
    
# Only show the Mission Status & Results section if a mission is active or finished
if st.session_state.mission_status not in ["awaiting_request", "refining_questions"]:
    st.header("Mission Status & Results")

# Display Status and Spinner/Info Message
status_text = st.session_state.mission_status.upper().replace("_", " ") # Format status nicely
# Update info messages to reflect chat is now in main area
if st.session_state.mission_status == "awaiting_request":
     # Message removed as per user request. Chat input serves as prompt.
     pass
     # If agent_processing is True, the placeholder in the chat area shows "Thinking..."
elif st.session_state.mission_status == "refining_questions":
     # Check if agent is processing before showing the default message
     if not st.session_state.agent_processing:
        st.info("Please review and refine the research questions in the chat area below, or type 'start research'.")
     # If agent_processing is True, the placeholder in the chat area shows "Processing feedback..."
elif st.session_state.mission_status == "initializing":
    status_text += " (Starting...)" # Status while waiting for thread to start
    status_placeholder = st.empty()
    status_placeholder.info("Initializing mission... (Starting background task for planning and execution)")
elif st.session_state.mission_status == "running":
    if thread_is_currently_alive: # Use the flag set during thread check
        status_text += " (Planning & Execution...)" # Indicate both phases might be running
        status_placeholder = st.empty()
        # Check log for latest phase hint (optional improvement)
        last_log_action = st.session_state.execution_log[-1].action if st.session_state.execution_log else ""
        if "Planning" in last_log_action or not st.session_state.execution_log:
             status_placeholder.info("Generating research plan...")
        else:
             status_placeholder.info("Executing research plan... (Running agents, gathering data, writing)")
    else:
        # If status is still 'running' but thread is dead, mark as failed
        status_text = "FAILED (Ended Unexpectedly)"
        if st.session_state.mission_status == "running": # Only change if still running
            st.session_state.mission_status = "failed"
            st.session_state.mission_error = st.session_state.mission_error or "Mission ended unexpectedly during execution."
        status_placeholder = st.empty() # Clear placeholder on unexpected end

st.write(f"**Status:** {status_text}")

# --- Helper function to display nested sections (Remains the same) ---
def display_section(section, level=0, prefix=""):
    """Recursively displays a report section and its subsections."""
    indent = "&nbsp;" * 4 * level # Indentation using non-breaking spaces
    section_prefix = f"{prefix}." if prefix else ""
    st.markdown(f"{indent}{section_prefix} **{section.title}** (`{section.section_id}`)")
    if section.description:
        st.caption(f"{indent}&nbsp;&nbsp;&nbsp;Description: {section.description}")
    if section.subsections:
        for i, sub_section in enumerate(section.subsections):
            display_section(sub_section, level + 1, prefix=f"{section_prefix}{i+1}")

# --- Helper function to display nested sections (Sidebar) ---
def display_section_sidebar(sections, level=0, prefix=""):
    """Recursively displays a report section and its subsections in the sidebar."""
    # Use st.sidebar consistently for output within this function
    for i, section in enumerate(sections):
        indent = "&nbsp;" * 4 * level # Indentation using non-breaking spaces
        section_prefix = f"{prefix}{i+1}." if prefix else f"{i+1}."
        # Use st.sidebar.markdown for sidebar display
        st.sidebar.markdown(f"{indent}{section_prefix} **{section.title}**")
        # Optionally display description if needed, keep it concise for sidebar
        # if section.description:
        #     st.sidebar.caption(f"{indent}&nbsp;&nbsp;&nbsp;{section.description}")
        if section.subsections:
            # Pass updated prefix for correct numbering
            display_section_sidebar(section.subsections, level + 1, prefix=f"{section_prefix}")

# --- Sidebar ---
with st.sidebar:
    st.header("Mission Context")

    # --- Display Mission Status and ID (Moved Here) ---
    # Calculate status text first (needed for display)
    status_text_sidebar = "UNKNOWN" # Default
    if 'mission_status' in st.session_state:
        status_text_sidebar = st.session_state.mission_status.upper().replace("_", " ")
        # Add dynamic status info like in the main area if needed
        if st.session_state.mission_status == "initializing":
            status_text_sidebar += " (Starting...)"
        elif st.session_state.mission_status == "running":
             # Check if thread is alive (using the flag determined earlier)
             if thread_is_currently_alive: # Use the flag set during thread check
                 status_text_sidebar += " (Planning & Execution...)"
             else:
                 # If status is 'running' but thread is dead, reflect failure
                 status_text_sidebar = "FAILED (Ended Unexpectedly)"


    # Only display if a mission is active or finished
    if st.session_state.get('mission_status') not in ["awaiting_request", "refining_questions"]:
        st.write(f"**Status:** {status_text_sidebar}")
        if st.session_state.get('mission_id'):
            st.write(f"**Mission ID:** `{st.session_state.mission_id}`")
        else:
             st.caption("Mission ID: (Not Available)")
        
        # --- Display Tool Usage Status (Enhanced) ---
        # Always show tool selection when mission is active, even if tool_usage_display isn't set yet
        if st.session_state.get('tool_usage_display'):
            # Use the feedback from the agent controller
            local_status = "ON" if st.session_state.tool_usage_display.get('local') else "OFF"
            web_status = "ON" if st.session_state.tool_usage_display.get('web') else "OFF"
            st.caption(f"**Tools Used:** Local Docs [{local_status}], Web Search [{web_status}]")
        else:
            # Fallback to the initial selection if feedback not received yet
            local_status = "ON" if st.session_state.tool_selection.get('local_rag', True) else "OFF"
            web_status = "ON" if st.session_state.tool_selection.get('web_search', True) else "OFF"
            st.caption(f"**Tools Selected:** Local Docs [{local_status}], Web Search [{web_status}]")
        # --- End Tool Usage Display ---

        st.divider() # Add a divider after status/ID/tool usage

        # --- LLM Usage Stats (Moved Up within active mission context) ---
        st.subheader("LLM Usage")
        # Display cost and tokens using captions for smaller size
        cost_str = f"Est. Cost: ${st.session_state.total_cost:.6f}"
        tokens_str = f"Tokens: {int(st.session_state.total_native_tokens)}"
        web_searches_str = f"Web Searches: {int(st.session_state.total_web_search_calls)}"
        st.caption(cost_str)
        st.caption(tokens_str)
        st.caption(web_searches_str)
        st.divider() # Divider after LLM stats
        # --- End LLM Usage Stats ---

    # --- Research Outline ---
    st.subheader("Research Outline")

    # --- ADDED: Explicitly check context manager for plan before rendering ---
    current_plan = st.session_state.get('mission_plan') # Get current plan from state
    if st.session_state.mission_id and st.session_state.mission_status in ["running", "conducting_research", "completed", "failed", "warning"]:
        try:
            mission_context = context_manager.get_mission_context(st.session_state.mission_id)
            if mission_context and mission_context.plan:
                # If context has a plan, update the session state *and* use it for rendering this cycle
                if current_plan != mission_context.plan: # Only update state if different
                    st.session_state.mission_plan = mission_context.plan
                    logger.info("UI Sidebar: Updated session plan from context manager.")
                current_plan = mission_context.plan # Use the fetched plan for this render cycle
            # else: # Context doesn't have plan yet, keep using the one from session state (if any)
            #    logger.debug("UI Sidebar: Context manager does not have plan yet, using session state plan.")
        except Exception as fetch_e:
            logger.error(f"UI Sidebar: Error fetching plan from context manager: {fetch_e}")
            # Keep using the plan from session state on error

    # --- Render using the potentially updated current_plan ---
    if current_plan: # Use the variable holding the latest plan
        plan_goal = getattr(current_plan, 'mission_goal', 'N/A')
        report_outline = getattr(current_plan, 'report_outline', [])

        # Add a styled container using markdown (Adjusted style)
        st.sidebar.markdown("""
        <div style="border: 1px solid #e6e6e6; border-radius: 5px; padding: 5px; margin-bottom: 5px; background-color: #f9f9f9;">
        """, unsafe_allow_html=True) # Reduced padding and margin-bottom

        st.sidebar.markdown(f"**Goal:** {plan_goal}") # Display goal inside the box
        if report_outline:
            display_section_sidebar(report_outline) # Call the sidebar display function
        else:
            # If plan exists but outline is empty
            st.sidebar.caption("Outline generated but empty.") # Display caption inside the box

        # Close the styled container div
        st.sidebar.markdown("</div>", unsafe_allow_html=True)

    else:
        # If current_plan is None
        st.sidebar.caption("Outline not available.") # Display caption outside if no plan exists

    st.divider() # Divider after outline

    # --- Document Store Info ---
    st.subheader("Document Store")
    try:
        # Access vector_store through the initialized agent_controller and retriever
        vector_store_instance = agent_controller.retriever.vector_store
        collection = vector_store_instance.dense_collection # Use the dense collection

        # 1. Get total chunk count
        total_chunks = collection.count()
        st.metric("Indexed Chunks", total_chunks)

        # 2. Get unique document count
        if total_chunks > 0:
            try:
                # Fetch metadata (potentially memory intensive for very large stores)
                results = collection.get(include=['metadatas'])
                all_metadatas = results.get('metadatas', [])

                if all_metadatas:
                    unique_docs = set()
                    for meta in all_metadatas:
                        doc_id = meta.get('doc_id')
                        if doc_id:
                            unique_docs.add(doc_id)
                    unique_doc_count = len(unique_docs)
                    st.metric("Unique Documents", unique_doc_count)
                else:
                    st.caption("Unique Docs: (No metadata found)")
            except Exception as meta_e:
                st.caption(f"Unique Docs: (Error: {meta_e})")
                logger.warning(f"Failed to retrieve or process metadata for unique doc count: {meta_e}", exc_info=True)
        else:
             st.metric("Unique Documents", 0) # Show 0 if no chunks

    except AttributeError:
        # Handle cases where the collection attribute might be wrong
        st.caption("Could not retrieve store stats (AttributeError).")
        logger.warning("Failed to get store stats via vector_store_instance.dense_collection", exc_info=True)
        st.caption("Store statistics unavailable.")
    except Exception as e:
        st.caption(f"Could not retrieve store stats: {e}")
        logger.error(f"Error retrieving store stats: {e}", exc_info=True)

    st.divider() # Divider after store stats

# --- Display Content Based on Status (Main Area) ---
# Show results area if mission is in execution phase or finished
# Status and Mission ID are now displayed in the sidebar
# Ensure mission_status is initialized before accessing it
if 'mission_status' not in st.session_state:
    st.session_state.mission_status = "awaiting_request"
    
# if st.session_state.mission_status in ["initializing", "running", "conducting_research", "completed", "failed", "warning"]:

#     # Display Error if present (Keep this in main area)
#     if st.session_state.mission_error:
#         st.error(f"**Error:** {st.session_state.mission_error}")

#         # Display Execution Log (Modified to show newest at bottom)
#         if st.session_state.execution_log:
#             st.subheader("Execution Log")
#             st.caption("Log of agent actions during the mission (Newest at bottom):")
            
#             # Add a filter for agent types
#             agent_types = ["All"] + sorted(list(set([entry.agent_name for entry in st.session_state.execution_log if hasattr(entry, 'agent_name')])))
#             selected_agent = st.selectbox("Filter by agent:", agent_types)
            
#             agent_colors = {
#                 "PlanningAgent": "blue", "ResearchAgent": "orange", "ReflectionAgent": "violet",
#                 "WritingAgent": "green", "AgentController": "grey", "System": "red",
#             }
#         # Iterate without reversing to show oldest first
#         filtered_log = st.session_state.execution_log
#         if selected_agent != "All":
#             filtered_log = [entry for entry in st.session_state.execution_log 
#                             if hasattr(entry, 'agent_name') and entry.agent_name == selected_agent]
            
#         for i, entry in enumerate(filtered_log):
#             # --- ADDED: Error handling for individual log entry rendering ---
#             try:
#                 timestamp_str = entry.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(entry, 'timestamp') and entry.timestamp else "N/A"
#                 agent_name = getattr(entry, 'agent_name', 'Unknown Agent')
#                 action = getattr(entry, 'action', 'Unknown Action')
                
#                 status = getattr(entry, 'status', 'unknown')
#                 input_summary = getattr(entry, 'input_summary', None)
#                 output_summary = getattr(entry, 'output_summary', None)
#                 error_message = getattr(entry, 'error_message', None)
#                 full_input = getattr(entry, 'full_input', None)
#                 full_output = getattr(entry, 'full_output', None)
#                 model_details = getattr(entry, 'model_details', None)
#                 tool_calls = getattr(entry, 'tool_calls', None)
#                 file_interactions = getattr(entry, 'file_interactions', None)
#                 # Determine status color based on value
#                 if status == "success":
#                     status_color = "green"
#                 elif status == "failure":
#                     status_color = "red"
#                 elif status == "warning":
#                     status_color = "orange"
#                 else:
#                     status_color = "grey" # Default for unknown status
#                 agent_color = agent_colors.get(agent_name, "grey")
#                 # Determine status color based on value
#                 if status == "success":
#                     status_color = "green"
#                 elif status == "failure":
#                     status_color = "red"
#                 elif status == "warning":
#                     status_color = "orange"
#                 else:
#                     status_color = "grey" # Default for unknown status
#                 agent_color = agent_colors.get(agent_name, "grey")

#                 # Use i+1 for chronological numbering
#                 st.markdown(f"**{i+1}. [{timestamp_str}]** :{agent_color}[{agent_name}] **- {action}** - :{status_color}[{status.upper()}]")
#                 if input_summary: st.caption(f"   Input Summary: {input_summary}")
#                 if output_summary: st.caption(f"   Output Summary: {output_summary}")
#                 if error_message: st.caption(f"   Error: {error_message}")

#                 with st.expander("Show Details"):
#                     if model_details:
#                         st.markdown("**Model Call:**")
#                         provider = model_details.get('provider', 'N/A')
#                         model_name_detail = model_details.get('model_name', 'N/A')
#                         duration = model_details.get('duration_sec', 'N/A')
#                         st.markdown(f"- Provider: `{provider}`\n- Model: `{model_name_detail}`\n- Duration: `{duration}s`")
#                     if tool_calls:
#                         st.markdown("**Tool Calls:**")
#                         for tc_idx, tool_call in enumerate(tool_calls):
#                             tool_name = tool_call.get('tool_name', 'N/A')
#                             tool_args = tool_call.get('arguments', {})
#                             tool_result = tool_call.get('result_summary', None)
#                             tool_error = tool_call.get('error', None)
#                             st.markdown(f"  - **Call {tc_idx+1}: `{tool_name}`**")
#                             st.markdown("    Arguments:"); st.json(tool_args, expanded=False)
#                             if tool_result: st.markdown(f"    Result Summary: `{tool_result}`")
#                             if tool_error: st.markdown(f"    Error: `{tool_error}`")
#                     if file_interactions:
#                         st.markdown("**File Interactions:**")
#                         for interaction in file_interactions: st.markdown(f"- `{interaction}`")
#                     if full_input is not None and not isinstance(full_input, (str, int, float, bool)):
#                         st.markdown("**Full Input:**"); st.json(full_input, expanded=False)
#                     elif isinstance(full_input, str) and len(full_input) > 100:
#                         st.markdown("**Full Input:**"); st.code(full_input, language='text')
#                     if full_output is not None and not isinstance(full_output, (str, int, float, bool)):
#                         st.markdown("**Full Output:**"); st.json(full_output, expanded=False)
#                     elif isinstance(full_output, str) and len(full_output) > 100:
#                         st.markdown("**Full Output:**"); st.markdown(full_output)
#                     if not model_details and not tool_calls and not file_interactions and full_input is None and full_output is None:
#                         st.caption("No detailed information available for this step.")
#                 st.divider()
#                 # --- ADDED: End of try block and except block ---
#             except Exception as render_e:
#                 st.error(f"Error rendering log entry {i+1}: {render_e}")
#                 logger.error(f"Error rendering log entry {i+1} (Agent: {getattr(entry, 'agent_name', 'N/A')}, Action: {getattr(entry, 'action', 'N/A')}): {render_e}", exc_info=True)
#                 # Optionally display raw entry data on error
#                 try:
#                     st.json(entry.model_dump() if hasattr(entry, 'model_dump') else entry, expanded=False)
#                 except Exception:
#                     st.write("Could not display raw entry data.")
#                 st.divider()
#             # --- END ADDED ---

# --- Display Execution Log and Final Report upon Completion ---
if st.session_state.mission_status == "completed":
    # --- Display Execution Log first (above the report) ---
    if st.session_state.execution_log:
        st.subheader("Execution Log")
        st.caption("Log of agent actions during the mission (Newest at bottom):")

        # Add a filter for agent types
        agent_types = ["All"] + sorted(list(set([entry.agent_name for entry in st.session_state.execution_log if hasattr(entry, 'agent_name')])))
        selected_agent = st.selectbox("Filter by agent:", agent_types, key="log_filter_completed") # Use a unique key

        agent_colors = {
            "PlanningAgent": "blue", "ResearchAgent": "orange", "ReflectionAgent": "violet",
            "WritingAgent": "green", "AgentController": "grey", "System": "red",
        }
        # Iterate without reversing to show oldest first
        filtered_log = st.session_state.execution_log
        if selected_agent != "All":
            filtered_log = [entry for entry in st.session_state.execution_log
                            if hasattr(entry, 'agent_name') and entry.agent_name == selected_agent]

        for i, entry in enumerate(filtered_log):
            # --- ADDED: Error handling for individual log entry rendering ---
            try:
                timestamp_str = entry.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(entry, 'timestamp') and entry.timestamp else "N/A"
                agent_name = getattr(entry, 'agent_name', 'Unknown Agent')
                action = getattr(entry, 'action', 'Unknown Action')

                status = getattr(entry, 'status', 'unknown')
                input_summary = getattr(entry, 'input_summary', None)
                output_summary = getattr(entry, 'output_summary', None)
                error_message = getattr(entry, 'error_message', None)
                full_input = getattr(entry, 'full_input', None)
                full_output = getattr(entry, 'full_output', None)
                model_details = getattr(entry, 'model_details', None)
                tool_calls = getattr(entry, 'tool_calls', None)
                file_interactions = getattr(entry, 'file_interactions', None)
                # Determine status color based on value
                if status == "success":
                    status_color = "green"
                elif status == "failure":
                    status_color = "red"
                elif status == "warning":
                    status_color = "orange"
                else:
                    status_color = "grey" # Default for unknown status
                agent_color = agent_colors.get(agent_name, "grey")

                # Use i+1 for chronological numbering
                st.markdown(f"**{i+1}. [{timestamp_str}]** :{agent_color}[{agent_name}] **- {action}** - :{status_color}[{status.upper()}]")
                if input_summary: st.caption(f"   Input Summary: {input_summary}")
                if output_summary: st.caption(f"   Output Summary: {output_summary}")
                if error_message: st.caption(f"   Error: {error_message}")

                with st.expander("Show Details"): # Removed key argument
                    if model_details:
                        st.markdown("**Model Call:**")
                        provider = model_details.get('provider', 'N/A')
                        model_name_detail = model_details.get('model_name', 'N/A')
                        duration = model_details.get('duration_sec', 'N/A')
                        st.markdown(f"- Provider: `{provider}`\n- Model: `{model_name_detail}`\n- Duration: `{duration}s`")
                    if tool_calls:
                        st.markdown("**Tool Calls:**")
                        for tc_idx, tool_call in enumerate(tool_calls):
                            tool_name = tool_call.get('tool_name', 'N/A')
                            tool_args = tool_call.get('arguments', {})
                            tool_result = tool_call.get('result_summary', None)
                            tool_error = tool_call.get('error', None)
                            st.markdown(f"  - **Call {tc_idx+1}: `{tool_name}`**")
                            st.markdown("    Arguments:"); st.json(tool_args, expanded=False)
                            if tool_result: st.markdown(f"    Result Summary: `{tool_result}`")
                            if tool_error: st.markdown(f"    Error: `{tool_error}`")
                    if file_interactions:
                        st.markdown("**File Interactions:**")
                        for interaction in file_interactions: st.markdown(f"- `{interaction}`")
                    if full_input is not None and not isinstance(full_input, (str, int, float, bool)):
                        st.markdown("**Full Input:**"); st.json(full_input, expanded=False)
                    elif isinstance(full_input, str) and len(full_input) > 100:
                        st.markdown("**Full Input:**"); st.code(full_input, language='text')
                    if full_output is not None and not isinstance(full_output, (str, int, float, bool)):
                        st.markdown("**Full Output:**"); st.json(full_output, expanded=False)
                    elif isinstance(full_output, str) and len(full_output) > 100:
                        st.markdown("**Full Output:**"); st.markdown(full_output)
                    if not model_details and not tool_calls and not file_interactions and full_input is None and full_output is None:
                        st.caption("No detailed information available for this step.")
                st.divider()
                # --- ADDED: End of try block and except block ---
            except Exception as render_e:
                st.error(f"Error rendering log entry {i+1}: {render_e}")
                logger.error(f"Error rendering log entry {i+1} (Agent: {getattr(entry, 'agent_name', 'N/A')}, Action: {getattr(entry, 'action', 'N/A')}): {render_e}", exc_info=True)
                # Optionally display raw entry data on error
                try:
                    st.json(entry.model_dump() if hasattr(entry, 'model_dump') else entry, expanded=False)
                except Exception:
                    st.write("Could not display raw entry data.")
                st.divider()
                # --- END ADDED ---
    elif not st.session_state.execution_log:
         st.caption("Execution log is empty.")

    # --- Display Final Report after the execution log ---
    if st.session_state.final_report:
        st.header("Final Report")
        st.markdown(st.session_state.final_report)

        # --- Add Download Buttons and Reset Button ---
        report_content = st.session_state.final_report
        mission_id_str = st.session_state.get('mission_id', 'unknown_mission')
        md_file_name = f"research_report_{mission_id_str}.md"
        pdf_file_name = f"research_report_{mission_id_str}.pdf"
        docx_file_name = f"research_report_{mission_id_str}.docx"
        
        # Create columns for the buttons - 5 columns for better spacing
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Download as Markdown button
            st.download_button(
                label="Download as Markdown",
                data=report_content,
                file_name=md_file_name,
                mime="text/markdown"
            )
            
        with col2:
            # Download as PDF button
            try:
                pdf_data = markdown_to_pdf(report_content)
                st.download_button(
                    label="Download as PDF",
                    data=pdf_data,
                    file_name=pdf_file_name,
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"PDF conversion error: {e}")
                logger.error(f"Error converting to PDF: {e}", exc_info=True)
        
        with col3:
            # Download as DOCX button
            try:
                docx_data = markdown_to_docx(report_content)
                st.download_button(
                    label="Download as DOCX",
                    data=docx_data,
                    file_name=docx_file_name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            except Exception as e:
                st.error(f"DOCX conversion error: {e}")
                logger.error(f"Error converting to DOCX: {e}", exc_info=True)
            
        with col4:
            # Reset button
            if st.button("Start New Research", type="primary"):
                # Reset session state to start a new task
                st.session_state.mission_status = "awaiting_request"
                st.session_state.mission_id = None
                st.session_state.mission_plan = None
                st.session_state.final_report = None
                st.session_state.mission_error = None
                st.session_state.execution_log = []
                st.session_state.report_saved = False
                st.session_state.total_cost = 0.0
                st.session_state.total_native_tokens = 0.0
                st.session_state.total_web_search_calls = 0
                # Keep the messages but add a system message indicating reset
                st.session_state.messages.append({"role": "assistant", "content": "I've reset the system. What research topic would you like to explore next?"})
                st.rerun()
        # --- End Download Buttons and Reset Button ---

        # --- Save Report with Stats ---
        # Only save the report if it hasn't been saved yet
        if not st.session_state.report_saved:
            try:
                # 1. Ensure output directory exists
                UI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                # 2. Retrieve stats from session state
                total_cost = st.session_state.get('total_cost', 0.0)
                # Note: CLI used prompt/completion, UI uses 'native' tokens
                total_native_tokens = st.session_state.get('total_native_tokens', 0.0)
                total_web_searches = st.session_state.get('total_web_search_calls', 0)

                # --- Get OpenRouter Model Names Directly from Config ---
                light_model = config.OPENROUTER_FAST_MODEL
                heavy_model = config.OPENROUTER_MID_MODEL
                beast_model = config.OPENROUTER_INTELLIGENT_MODEL

                # 3. Format stats header (adjusting token names and adding models)
                stats_header = (
                    f"<!--\n"
                    f"Mission ID: {mission_id_str}\n"
                    f"OpenRouter Models Configured:\n"
                    f"  Light: {light_model}\n"
                    f"  Heavy: {heavy_model}\n"
                    f"  Beast: {beast_model}\n"
                    f"Stats:\n"
                    f"  Total Cost: ${total_cost:.6f}\n"
                    f"  Total Native Tokens: {total_native_tokens:.0f}\n" # Changed token name
                    f"  Total Web Searches: {total_web_searches}\n"
                    f"Generated via: Streamlit UI\n" # Add source info
                    f"-->\n\n"
                )

                # 4. Generate filename and path
                output_filename = generate_ui_report_filename(mission_id_str)
                output_path = UI_OUTPUT_DIR / output_filename

                # 5. Write file (prepend stats)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(stats_header + report_content)

                # 6. Display success message
                st.success(f"Report saved to: `{output_path}`")
                logger.info(f"UI: Successfully saved report with stats to {output_path}")
                
                # 7. Set the flag to indicate the report has been saved
                st.session_state.report_saved = True
                
            except Exception as save_e:
                error_msg = f"Failed to automatically save report: {save_e}"
                st.error(error_msg)
                logger.error(error_msg, exc_info=True)
        else:
            # Report has already been saved, just show a message
            st.info("Report was previously saved to the ui_research_output directory.")
        # --- End Save Report ---
    else:
        # If completed but no report
        st.warning("Mission completed, but no final report was generated.")

# --- Display Log for other states (running, failed, etc.) ---
elif st.session_state.mission_status in ["initializing", "running", "conducting_research", "failed", "warning"]:
    # Display Error if present (Keep this in main area)
    if st.session_state.mission_error:
        st.error(f"**Error:** {st.session_state.mission_error}")

    # Display Execution Log (Modified to show newest at bottom)
    if st.session_state.execution_log:
        st.subheader("Execution Log")
        st.caption("Log of agent actions during the mission (Newest at bottom):")

        # Add a filter for agent types
        agent_types = ["All"] + sorted(list(set([entry.agent_name for entry in st.session_state.execution_log if hasattr(entry, 'agent_name')])))
        selected_agent = st.selectbox("Filter by agent:", agent_types, key="log_filter_running") # Use a unique key

        agent_colors = {
            "PlanningAgent": "blue", "ResearchAgent": "orange", "ReflectionAgent": "violet",
            "WritingAgent": "green", "AgentController": "grey", "System": "red",
        }
        # Iterate without reversing to show oldest first
        filtered_log = st.session_state.execution_log
        if selected_agent != "All":
            filtered_log = [entry for entry in st.session_state.execution_log
                            if hasattr(entry, 'agent_name') and entry.agent_name == selected_agent]

        for i, entry in enumerate(filtered_log):
            # --- ADDED: Error handling for individual log entry rendering ---
            try:
                timestamp_str = entry.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(entry, 'timestamp') and entry.timestamp else "N/A"
                agent_name = getattr(entry, 'agent_name', 'Unknown Agent')
                action = getattr(entry, 'action', 'Unknown Action')

                status = getattr(entry, 'status', 'unknown')
                input_summary = getattr(entry, 'input_summary', None)
                output_summary = getattr(entry, 'output_summary', None)
                error_message = getattr(entry, 'error_message', None)
                full_input = getattr(entry, 'full_input', None)
                full_output = getattr(entry, 'full_output', None)
                model_details = getattr(entry, 'model_details', None)
                tool_calls = getattr(entry, 'tool_calls', None)
                file_interactions = getattr(entry, 'file_interactions', None)
                # Determine status color based on value
                if status == "success":
                    status_color = "green"
                elif status == "failure":
                    status_color = "red"
                elif status == "warning":
                    status_color = "orange"
                else:
                    status_color = "grey" # Default for unknown status
                agent_color = agent_colors.get(agent_name, "grey")

                # Use i+1 for chronological numbering
                st.markdown(f"**{i+1}. [{timestamp_str}]** :{agent_color}[{agent_name}] **- {action}** - :{status_color}[{status.upper()}]")
                if input_summary: st.caption(f"   Input Summary: {input_summary}")
                if output_summary: st.caption(f"   Output Summary: {output_summary}")
                if error_message: st.caption(f"   Error: {error_message}") # Corrected indentation

                with st.expander("Show Details"): # Removed key argument
                    if model_details:
                        st.markdown("**Model Call:**")
                        provider = model_details.get('provider', 'N/A')
                        model_name_detail = model_details.get('model_name', 'N/A')
                        duration = model_details.get('duration_sec', 'N/A')
                        st.markdown(f"- Provider: `{provider}`\n- Model: `{model_name_detail}`\n- Duration: `{duration}s`")
                    if tool_calls:
                        st.markdown("**Tool Calls:**")
                        for tc_idx, tool_call in enumerate(tool_calls):
                            tool_name = tool_call.get('tool_name', 'N/A')
                            tool_args = tool_call.get('arguments', {})
                            tool_result = tool_call.get('result_summary', None)
                            tool_error = tool_call.get('error', None)
                            st.markdown(f"  - **Call {tc_idx+1}: `{tool_name}`**")
                            st.markdown("    Arguments:"); st.json(tool_args, expanded=False)
                            if tool_result: st.markdown(f"    Result Summary: `{tool_result}`")
                            if tool_error: st.markdown(f"    Error: `{tool_error}`")
                    if file_interactions:
                        st.markdown("**File Interactions:**")
                        for interaction in file_interactions: st.markdown(f"- `{interaction}`")
                    if full_input is not None and not isinstance(full_input, (str, int, float, bool)):
                        st.markdown("**Full Input:**"); st.json(full_input, expanded=False)
                    elif isinstance(full_input, str) and len(full_input) > 100:
                        st.markdown("**Full Input:**"); st.code(full_input, language='text')
                    if full_output is not None and not isinstance(full_output, (str, int, float, bool)):
                        st.markdown("**Full Output:**"); st.json(full_output, expanded=False)
                    elif isinstance(full_output, str) and len(full_output) > 100:
                        st.markdown("**Full Output:**"); st.markdown(full_output)
                    if not model_details and not tool_calls and not file_interactions and full_input is None and full_output is None:
                        st.caption("No detailed information available for this step.")
                st.divider()
                # --- ADDED: End of try block and except block ---
            except Exception as render_e:
                st.error(f"Error rendering log entry {i+1}: {render_e}")
                logger.error(f"Error rendering log entry {i+1} (Agent: {getattr(entry, 'agent_name', 'N/A')}, Action: {getattr(entry, 'action', 'N/A')}): {render_e}", exc_info=True)
                # Optionally display raw entry data on error
                try:
                    st.json(entry.model_dump() if hasattr(entry, 'model_dump') else entry, expanded=False)
                except Exception:
                    st.write("Could not display raw entry data.")
                st.divider()
            # --- END ADDED ---
    elif not st.session_state.execution_log:
         st.caption("Execution log is empty.")

# Handle initial states explicitly (awaiting_request, refining_questions handled by chat)

    # Clear status placeholder only if it was created and the mission is NOT initializing or running
    if status_placeholder is not None and st.session_state.mission_status not in ["initializing", "running"]:
        status_placeholder.empty()
# --- End Conditional Display Block ---

# --- Trigger Rerun (Remains the same logic) ---
if needs_immediate_rerun:
    try: st.rerun()
    except Exception as rerun_e: logger.warning(f"Immediate rerun failed unexpectedly: {rerun_e}")
elif schedule_polling_rerun:
    time.sleep(2.0) # Polling interval
    try: st.rerun()
    except Exception as rerun_e:
         logger.warning(f"Polling rerun failed unexpectedly: {rerun_e}")
         time.sleep(1)
