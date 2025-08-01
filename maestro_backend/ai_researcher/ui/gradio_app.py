import gradio as gr
import asyncio
import os
import sys
import threading
import time
import logging
import queue
import uuid
import html # Add import for html module
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, AsyncGenerator, Tuple, TYPE_CHECKING, Iterable
# --- Gradio Theme Imports ---
from gradio.themes.base import Base
from gradio.themes.utils import colors, fonts, sizes

if TYPE_CHECKING:
    from ai_researcher.agentic_layer.agent_controller import AgentController
    from ai_researcher.agentic_layer.context_manager import ContextManager, ExecutionLogEntry, MissionContext
    from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection, PlanStep
    from ai_researcher.core_rag.embedder import TextEmbedder
    from ai_researcher.core_rag.vector_store import VectorStore
    from ai_researcher.core_rag.reranker import TextReranker
    from ai_researcher.core_rag.retriever import Retriever
    from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
    from ai_researcher.agentic_layer.tool_registry import ToolRegistry
    from ai_researcher.agentic_layer.schemas.research import ResearchResultResponse

# --- Set CUDA device ---
# Force the application to use only the GPU with index 4
os.environ['CUDA_VISIBLE_DEVICES'] = '4'
# --- End CUDA device setting ---

# --- Define Project Root Early ---
try:
    current_file_path = Path(__file__).resolve()
    project_root = current_file_path.parent.parent.parent # Adjust based on actual file location
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    # Ensure ai_researcher parent is also in path if needed
    ai_researcher_dir = project_root / "ai_researcher"
    if str(ai_researcher_dir.parent) not in sys.path:
         sys.path.append(str(ai_researcher_dir.parent))

except NameError:
    # Handle cases where __file__ might not be defined (e.g., interactive)
    project_root = Path.cwd() # Fallback
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

# --- Imports from ai_researcher (Placeholders - adjust as needed) ---
try:
    from ai_researcher.agentic_layer.context_manager import ExecutionLogEntry, MissionContext
    from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection, PlanStep
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
except ImportError as e:
    print(f"Error importing ai_researcher modules: {e}. Check sys.path and project structure.")
    # Define placeholder classes for type checking
    class AgentController:
        """Placeholder class for AgentController when imports fail."""
        pass
    
    class ContextManager:
        """Placeholder class for ContextManager when imports fail."""
        pass
    
    class ExecutionLogEntry:
        """Placeholder class for ExecutionLogEntry when imports fail."""
        pass
    
    class MissionContext:
        """Placeholder class for MissionContext when imports fail."""
        pass
    
    class SimplifiedPlan:
        """Placeholder class for SimplifiedPlan when imports fail."""
        pass
    
    class ReportSection:
        """Placeholder class for ReportSection when imports fail."""
        pass
    
    class PlanStep:
        """Placeholder class for PlanStep when imports fail."""
        pass

# --- Custom Gradio Theme Definition ---
class RetroAcademicTheme(Base):
    def __init__(
        self,
        *,
        primary_hue: colors.Color | str = colors.slate, # Muted blue-gray
        secondary_hue: colors.Color | str = colors.teal, # Muted green-blue
        neutral_hue: colors.Color | str = colors.stone, # Warm gray
        spacing_size: sizes.Size | str = sizes.spacing_lg, # Increased spacing
        radius_size: sizes.Size | str = sizes.radius_md, # More rounded corners
        text_size: sizes.Size | str = sizes.text_lg, # Larger text
        font: fonts.Font
        | str
        | Iterable[fonts.Font | str] = (
            fonts.GoogleFont("Inter"), # Clean sans-serif font
            "ui-sans-serif",
            "system-ui",
            "sans-serif",
        ),
        font_mono: fonts.Font
        | str
        | Iterable[fonts.Font | str] = (
            fonts.GoogleFont("Source Code Pro"), # Clean monospace
            "ui-monospace",
            "monospace",
        ),
    ):
        super().__init__(
            primary_hue=primary_hue,
            secondary_hue=secondary_hue,
            neutral_hue=neutral_hue,
            spacing_size=spacing_size,
            radius_size=radius_size,
            text_size=text_size,
            font=font,
            font_mono=font_mono,
        )
        # Fine-tune specific elements for a more modern look
        super().set(
            # Add subtle shadows for depth
            block_shadow="*shadow_drop",
            button_primary_shadow="*shadow_drop_lg", # Apply to primary buttons
            button_secondary_shadow="*shadow_drop_lg", # Apply to secondary buttons
            # Slightly lighten borders
            block_border_width="1px",
            input_border_color="*neutral_200",
            input_border_color_dark="*neutral_700",
            # Adjust background colors slightly if needed (optional)
            # body_background_fill="*neutral_50",
            # body_background_fill_dark="*neutral_950",
        )

# Instantiate the theme
retro_theme = RetroAcademicTheme()

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration (Mirror Streamlit app or use central config) ---
VECTOR_STORE_PATH = project_root / "ai_researcher" / "data/vector_store"
CONTEXT_SAVE_DIR = project_root / "ai_researcher" / "data/mission_results"
EMBEDDING_MODEL = "BAAI/bge-m3" # Or load from config
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3" # Or load from config

# --- Global State (Simulating st.cache_resource) ---
# Gradio apps run the script once, so global variables can hold state.
# For more complex scenarios, consider a dedicated state management class.
_agent_controller_instance: Optional["AgentController"] = None
_context_manager_instance: Optional["ContextManager"] = None

def initialize_components():
    """Initializes and returns the core components."""
    global _agent_controller_instance, _context_manager_instance
    if _agent_controller_instance is None:
        logger.info("Initializing AI Researcher components for Gradio app...")
        try:
            # Reuse initialization logic from Streamlit app if possible
            embedder = TextEmbedder(model_name=EMBEDDING_MODEL)
            vector_store = VectorStore(persist_directory=VECTOR_STORE_PATH)
            reranker = TextReranker(model_name=RERANKER_MODEL)
            retriever = Retriever(embedder=embedder, vector_store=vector_store, reranker=reranker)
            model_dispatcher = ModelDispatcher()
            tool_registry = ToolRegistry()
            context_manager = ContextManager(save_dir=CONTEXT_SAVE_DIR)
            agent_controller = AgentController(
                model_dispatcher=model_dispatcher,
                context_manager=context_manager,
                tool_registry=tool_registry,
                retriever=retriever,
                reranker=reranker
            )
            _agent_controller_instance = agent_controller
            _context_manager_instance = context_manager
            logger.info("Components initialized successfully.")
        except Exception as e:
            logger.error(f"Fatal Error initializing components: {e}", exc_info=True)
            # Handle error appropriately for Gradio (e.g., display error in UI)
            raise gr.Error(f"Failed to initialize backend components: {e}")
    return _agent_controller_instance, _context_manager_instance

# --- Helper Functions for UI Formatting ---

def format_plan_md(plan: Optional[SimplifiedPlan]) -> str:
    """Formats the SimplifiedPlan into Markdown."""
    if not plan:
        return "No research outline available yet."

    md = f"**Goal:** {plan.mission_goal}\n\n"
    md += "**Outline:**\n"

    def _format_section(section: ReportSection, level=0, prefix=""):
        indent = "&nbsp;" * 4 * level
        section_prefix = f"{prefix}." if prefix else ""
        s_md = f"{indent}{section_prefix} **{section.title}** (`{section.section_id}`)\n"
        if section.description:
            s_md += f"{indent}&nbsp;&nbsp;&nbsp;*Description:* {section.description}\n"
        if section.subsections:
            for i, sub_section in enumerate(section.subsections):
                s_md += _format_section(sub_section, level + 1, prefix=f"{section_prefix}{i+1}")
        return s_md

    if plan.report_outline:
        for i, section in enumerate(plan.report_outline):
            md += _format_section(section, level=0, prefix=str(i+1))
    else:
        md += "*No sections defined.*\n"

    # Optionally add steps if needed
    # md += "\n**Planned Steps:**\n"
    # if plan.steps:
    #     for i, step in enumerate(plan.steps):
    #         md += f"{i+1}. {step.description} (Action: {step.action_type}, Target: {step.target_section_id})\n"
    # else:
    #     md += "*No steps defined.*\n"

    return md

import json # Add json import for formatting full data
from pydantic import BaseModel # Import BaseModel for type checking in helper
# --- Import relevant schemas for parsing ---
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlanResponse # Assuming this is the output
from ai_researcher.agentic_layer.schemas.research import ResearchResultResponse, ResearchFindings
from ai_researcher.agentic_layer.schemas.writing import WritingReflectionOutput
# Add other schemas if needed for specific agent inputs/outputs

# --- Helper function to format data (including Pydantic models) into HTML ---
def _format_data_html(data: Any, indent_level: int = 0) -> str:
    """Recursively formats Python data (including Pydantic models) into HTML."""
    indent = "&nbsp;" * 4 * indent_level
    indent_nested = "&nbsp;" * 4 * (indent_level + 1)
    html_str = ""

    # --- Style definitions using theme variables ---
    dl_style = "margin-bottom: *spacing_sm;"
    dt_style = f"font-weight: 500; color: *body_text_color; margin-left: {indent};"
    dd_style = f"margin-left: {indent_nested}; margin-bottom: *spacing_sm; color: *body_text_color_subdued;"
    list_style = f"list-style-type: disc; margin-left: {indent_nested}; padding-left: *spacing_md;"
    pre_style = """
        white-space: pre-wrap; word-wrap: break-word; margin-top: *spacing_sm;
        padding: *spacing_sm *spacing_md; background-color: *neutral_100;
        border-radius: *radius_sm; border: 1px solid *border_color_accent_subdued;
        color: *body_text_color_subdued; font-family: *font_mono; font-size: 0.9em;
    """ # Slightly smaller font size for pre

    if isinstance(data, BaseModel):
        html_str += f"<div style='{dl_style}'>" # Use div instead of dl for better control
        for field_name, field_info in data.model_fields.items():
            value = getattr(data, field_name, None)
            if value is None and field_info.default is None: # Don't show Nones unless they have a default
                 continue
            display_name = field_name.replace("_", " ").title()
            html_str += f"<div style='{dt_style}'>{display_name}:</div>"
            html_str += f"<div style='{dd_style}'>"
            html_str += _format_data_html(value, indent_level + 1)
            html_str += "</div>"
        html_str += "</div>"
    elif isinstance(data, list):
        if not data:
            html_str += f"<span style='margin-left: {indent}; color: *body_text_color_subdued;'>(Empty List)</span>"
        else:
            html_str += f"<ul style='{list_style}'>"
            for i, item in enumerate(data):
                html_str += f"<li>Item {i+1}:<br>{_format_data_html(item, indent_level + 1)}</li>"
            html_str += "</ul>"
    elif isinstance(data, dict):
        if not data:
            html_str += f"<span style='margin-left: {indent}; color: *body_text_color_subdued;'>(Empty Dictionary)</span>"
        else:
            html_str += f"<div style='{dl_style}'>"
            for key, value in data.items():
                display_key = str(key).replace("_", " ").title()
                html_str += f"<div style='{dt_style}'>{display_key}:</div>"
                html_str += f"<div style='{dd_style}'>"
                html_str += _format_data_html(value, indent_level + 1)
                html_str += "</div>"
            html_str += "</div>"
    elif isinstance(data, (str, int, float, bool)):
         # Escape HTML characters in strings
         escaped_data = html.escape(str(data)) if isinstance(data, str) else str(data)
         # Use <pre> for multi-line strings, otherwise just display inline
         if isinstance(data, str) and ('\n' in data or len(data) > 80):
              html_str += f"<pre style='{pre_style} margin-left: {indent};'>{escaped_data}</pre>"
         else:
              html_str += f"<span style='margin-left: {indent};'>{escaped_data}</span>"
    elif data is None:
         html_str += f"<span style='margin-left: {indent}; color: *body_text_color_subdued;'>None</span>"
    else:
        # Fallback for other types
        try:
            escaped_data = html.escape(str(data))
            html_str += f"<pre style='{pre_style} margin-left: {indent};'>{escaped_data}</pre>"
        except Exception:
             html_str += f"<span style='margin-left: {indent}; color: *error_500;'>(Error formatting data)</span>"

    return html_str


def format_log_md(log_entries: List[ExecutionLogEntry]) -> str:
    """Formats the execution log into expandable HTML cards using theme variables."""
    if not log_entries:
        return "<p style='color: *body_text_color_subdued;'>Execution log is empty.</p>" # Use theme color

    # Define agent colors (can still be specific hex if desired, or map to theme hues)
    # Using specific hex for now for distinctiveness, but theme hues could be used too.
    agent_colors = {
        "PlanningAgent": "#60a5fa", # blue-400
        "ResearchAgent": "#fb923c", # orange-400
        "ReflectionAgent": "#a78bfa", # violet-400
        "WritingAgent": "#34d399", # emerald-400
        "AgentController": "#9ca3af", # gray-400
        "System": "#f87171", # red-400
        "MessengerAgent": "#c084fc", # purple-400
        "NoteAssignmentAgent": "#fbbf24", # amber-400
        "WritingReflectionAgent": "#2dd4bf" # teal-400
    }
    default_color = "*neutral_400" # Use theme neutral color
    success_color = "*success_500" # Use theme success color
    fail_color = "*error_500" # Use theme error color

    html_parts = []
    for i, entry in enumerate(reversed(log_entries)):
        timestamp_str = entry.timestamp.strftime('%H:%M:%S') if hasattr(entry, 'timestamp') and entry.timestamp else "N/A"
        agent_name = getattr(entry, 'agent_name', 'Unknown Agent')
        action = getattr(entry, 'action', 'Unknown Action')
        status = getattr(entry, 'status', 'unknown')
        # Get full data, fall back to summary
        input_content = getattr(entry, 'full_input', getattr(entry, 'input_summary', None))
        output_content = getattr(entry, 'full_output', getattr(entry, 'output_summary', None))
        error_message = getattr(entry, 'error_message', None)

        status_theme_color = success_color if status == "success" else fail_color
        agent_theme_color = agent_colors.get(agent_name, default_color)

        # Card Styling using Theme Variables
        card_style = f"""
            margin-bottom: 10px;
            border: 1px solid *border_color_accent;
            border-radius: *radius_md; /* Use theme radius */
            box-shadow: *shadow_drop; /* Use theme shadow */
            background-color: *neutral_50;
            color: *body_text_color;
            overflow: hidden;
        """
        # Style for the summary element (visible part) - Reduced font size and padding
        summary_style = f"""
            padding: *spacing_sm *spacing_md; /* Reduced padding */
            font-weight: 500;
            font-size: 0.9em; /* Reduced font size */
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: flex-start; /* Align items to the top */
            flex-direction: column; /* Stack main info and status vertically */
            border-bottom: 1px solid *border_color_accent_subdued;
            background-color: *neutral_100; /* Slightly different background for header */
            color: *body_text_color;
            padding-bottom: *spacing_xs; /* Add a bit more space at the bottom for the badge */
        """
        # Style for the content inside the details (hidden part)
        details_content_style = """
            padding: *spacing_md; /* Reduced padding to match summary */
            font-size: 0.9em; /* Keep details font size */
            line-height: 1.5;
            background-color: *neutral_50; /* Match card background */
            color: *body_text_color;
        """
        summary_item_style = "margin-right: *spacing_sm; white-space: nowrap;" # Reduced margin
        pre_style = """
            white-space: pre-wrap;
            word-wrap: break-word;
            margin-top: *spacing_sm;
            padding: *spacing_sm *spacing_md;
            background-color: *neutral_100; /* Background for code/data */
            border-radius: *radius_sm;
            border: 1px solid *border_color_accent_subdued;
            color: *body_text_color_subdued;
            font-family: *font_mono; /* Use theme mono font */
            font-size: 0.95em;
        """
        # Style for the status badge
        status_badge_style = f"""
            display: inline-block; /* Allow padding and border-radius */
            padding: 2px 6px; /* Small padding */
            border-radius: *radius_sm; /* Rounded corners */
            font-size: 0.8em; /* Even smaller font */
            font-weight: 600;
            line-height: 1; /* Tight line height */
            margin-top: *spacing_xs; /* Space above the badge */
            color: white; /* Text color for badge */
            background-color: {status_theme_color}; /* Use status color for background */
        """


        # Build the HTML for one card
        entry_html = f'<details style="{card_style}">'

        # --- Summary (Visible Part) ---
        entry_html += f'<summary style="{summary_style}">'
        # -- Top line with main info --
        entry_html += f'<div style="display: flex; align-items: center; overflow: hidden; text-overflow: ellipsis; width: 100%; margin-bottom: *spacing_xs;">'
        entry_html += f'<span style="{summary_item_style} font-weight: bold;">{len(log_entries)-i}.</span>'
        entry_html += f'<span style="{summary_item_style} color: *body_text_color_subdued;">[{timestamp_str}]</span>'
        entry_html += f'<strong style="{summary_item_style} color: {agent_theme_color};">{agent_name}</strong>'
        entry_html += f'<span style="{summary_item_style} color: *body_text_color_subdued;">- {action}</span>'
        # Add output summary if available
        output_summary = getattr(entry, 'output_summary', None)
        if output_summary:
             # Truncate summary if too long for the summary line
             max_summary_len = 60
             display_summary = (output_summary[:max_summary_len] + '...') if len(output_summary) > max_summary_len else output_summary
             entry_html += f'<span style="{summary_item_style} color: *body_text_color_subdued; font-style: italic; white-space: normal; flex-shrink: 1; min-width: 50px;">: {html.escape(display_summary)}</span>' # Allow shrinking/wrapping
        entry_html += f'</div>'
        # -- Second line with status badge --
        entry_html += f'<div><strong style="{status_badge_style}">{status.upper()}</strong></div>'
        entry_html += f'</summary>'

        # --- Details (Expandable Part) ---
        entry_html += f'<div style="{details_content_style}">'
        has_details = False

        # --- Format Input ---
        if input_content is not None:
            has_details = True
            parsed_input = None
            # Attempt to parse based on agent/action if it's a dict
            if isinstance(input_content, dict):
                try:
                    # Add specific parsing logic here if needed, e.g.,
                    # if agent_name == "PlanningAgent" and action == "...":
                    #     parsed_input = SpecificInputSchema(**input_content)
                    pass # No specific parsing needed for input currently shown
                except Exception as parse_e:
                    logger.debug(f"Could not parse input for {agent_name}/{action}: {parse_e}")
                    parsed_input = None # Fallback to raw display

            entry_html += f'<div style="margin-bottom: *spacing_md;"><strong style="color: *body_text_color;">Input:</strong>'
            if parsed_input:
                 entry_html += _format_data_html(parsed_input)
            else:
                 # Use helper for dicts/lists, otherwise fallback to pre
                 if isinstance(input_content, (dict, list)):
                      entry_html += _format_data_html(input_content)
                 else:
                      entry_html += f'<pre style="{pre_style}">{html.escape(str(input_content))}</pre>'
            entry_html += '</div>'

        # --- Format Output ---
        if output_content is not None:
            has_details = True
            parsed_output = None
            # Attempt to parse based on agent/action if it's a dict
            if isinstance(output_content, dict):
                 try:
                      if agent_name == "PlanningAgent" and "Plan" in action:
                           # SimplifiedPlanResponse is the direct output
                           parsed_output = SimplifiedPlanResponse(**output_content)
                      elif agent_name == "ResearchAgent" and action == "Synthesize Findings":
                           # ResearchResultResponse contains ResearchFindings in 'result'
                           # We format the ResearchResultResponse itself
                           parsed_output = ResearchResultResponse(**output_content)
                      elif agent_name == "WritingReflectionAgent":
                           parsed_output = WritingReflectionOutput(**output_content)
                      # Add more parsing rules based on agent/action as needed
                 except Exception as parse_e:
                      logger.debug(f"Could not parse output for {agent_name}/{action}: {parse_e}")
                      parsed_output = None # Fallback to raw display

            entry_html += f'<div style="margin-bottom: *spacing_md;"><strong style="color: *body_text_color;">Output:</strong>'
            if parsed_output:
                 entry_html += _format_data_html(parsed_output)
            else:
                 # Use helper for dicts/lists, otherwise fallback to pre
                 if isinstance(output_content, (dict, list)):
                      entry_html += _format_data_html(output_content)
                 else:
                      entry_html += f'<pre style="{pre_style}">{html.escape(str(output_content))}</pre>'
            entry_html += '</div>'

        # --- Format Error ---
        if error_message:
            has_details = True
            entry_html += f'<div style="margin-bottom: *spacing_md;"><strong style="color: {fail_color};">Error:</strong><pre style="{pre_style} color: {fail_color};">{html.escape(str(error_message))}</pre></div>'

        if not has_details:
             entry_html += f'<p style="color: *body_text_color_subdued;">No further details available.</p>'
        entry_html += '</div>' # End details content

        entry_html += '</details>'
        html_parts.append(entry_html)

    # Return the combined HTML for all cards
    # No need for the outer container div anymore unless specific styling is needed for the group
    return "".join(html_parts)


# --- Gradio UI Definition ---

# Custom CSS for styling and layout control
CUSTOM_CSS = """
/* Style the execution log container */
.execution-log-container {
    /* Removed max-height and overflow-y from here, apply to the Gradio component wrapper */
}

/* Target the specific Gradio Markdown component holding the log */
/* We need to find the right selector - inspect the element in the browser */
/* Placeholder selector - adjust after inspection */
/* #component-X .output_markdown { */
/*    max-height: 400px; /* Or your desired max height */
/*    overflow-y: auto !important; /* Enable vertical scroll */
/*    border: 1px solid #e0e0e0; /* Optional border */
/*    padding: 10px; */
/* } */

/* Make chatbot take more height */
/* #component-Y .gradio-chatbot { /* Adjust selector */
/*    height: 600px !important; */
/* } */
"""

# --- Gradio Interface Definition ---
# NOTE: The theme instance 'retro_theme' is defined above

with gr.Blocks(theme=retro_theme, css=CUSTOM_CSS) as demo: # Use the new custom theme
    # State object to hold mission details between chat turns
    mission_state = gr.State({})

    gr.Markdown("# AI Research Agent") # Simplified Title

    with gr.Row():
        # --- Left Column ---
        with gr.Column(scale=1):
            gr.Markdown("## Mission Overview")
            status_display = gr.Textbox(label="Status", interactive=False)
            mission_id_display = gr.Textbox(label="Mission ID", interactive=False)
            # Use Markdown for notifications/errors to allow HTML formatting from _prepare_ui_updates
            error_display = gr.Markdown(label="Notifications/Errors", value="No notifications or errors.")

            with gr.Accordion("Research Outline", open=False) as plan_accordion:
                plan_display = gr.Markdown("No research outline available yet.")

            # Execution Log is MOVED from here

        # --- Right Column ---
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(label="Conversation", height=600) # Increased height

            # --- Chat Input Row ---
            with gr.Row(elem_classes=["chat-input-row"]): # Add class for potential CSS
                chat_input = gr.Textbox(
                    label="Your Message", # Keep label for accessibility, hide with CSS if needed
                    placeholder="Type your message or 'start research: [your request]'",
                    show_label=False, # Hide the label visually
                    scale=4 # Give textbox more space
                )
                send_button = gr.Button("Send", scale=1, variant="primary") # Add send button, make primary

            # --- Execution Log Accordion ---
            with gr.Accordion("Execution Log", open=True) as log_accordion:

                 # Use elem_classes to apply custom CSS styling more reliably
                log_display = gr.Markdown("Execution log is empty.", elem_classes=["execution-log-display"])

            with gr.Accordion("Final Report", open=False) as report_accordion:
                report_display = gr.Markdown("Final report will appear here upon completion.")


# Define the update logic separately for clarity, to be called within the generator
def _prepare_ui_updates(state: Dict):
    """Reads state and returns formatted values/updates for UI components."""
    # --- Debug Logging Start ---
    logger.info(f"_prepare_ui_updates called. Current state keys: {list(state.keys())}")
    logger.info(f"State - mission_status: {state.get('mission_status')}")
    logger.info(f"State - mission_id: {state.get('mission_id')}")
    logger.info(f"State - mission_error: {state.get('mission_error')}")
    logger.info(f"State - plan exists: {state.get('mission_plan') is not None}")
    logger.info(f"State - log length: {len(state.get('execution_log', []))}")
    logger.info(f"State - report exists: {state.get('final_report') is not None}")
    logger.info(f"State - notifications: {state.get('notifications')}") # Log notifications list
    # --- Debug Logging End ---

    status = state.get("mission_status", "idle")
    mid = state.get("mission_id", "N/A")
    error = state.get("mission_error", "")
    plan = state.get("mission_plan")
    log = state.get("execution_log", [])
    report = state.get("final_report", "")
    notifications = state.get("notifications", []) # Get the list of notifications

    # Format outputs
    plan_md = format_plan_md(plan)
    log_md = format_log_md(log)
    report_md = report if report else "Report not generated yet."

    # Combine notifications and error for display
    display_messages = []
    # Display the last N notifications (e.g., last 3)
    max_notifications_to_show = 5 # Increased to show more context
    start_index = max(0, len(notifications) - max_notifications_to_show)
    for notif in notifications[start_index:]:
        icon = "ℹ️" # Default icon
        color = "grey" # Default color
        if notif.get("type") == "info":
            icon = "ℹ️"
            color = "dodgerblue"
        elif notif.get("type") == "error": # Example for future error notifications
            icon = "⚠️"
            color = "orange"
        # Simple formatting for now
        display_messages.append(f"<font color='{color}'>{icon} {notif.get('text', '')}</font>")

    if error:
        display_messages.append(f"<font color='red'>**Error:** {error}</font>")

    error_md = "<br>".join(display_messages) if display_messages else "No notifications or errors." # Display one per line

    # Determine accordion visibility/open state based on status
    # Only force state changes in specific conditions to preserve user interaction
    plan_update = gr.update() # Default: leave unchanged
    if status in ["idle", "initializing"]:
        plan_update = gr.update(open=False)
    # elif status == "planning": # Optional: force open during planning
    #     plan_update = gr.update(open=True)

    log_update = gr.update() # Default: leave unchanged
    if status == "idle":
        log_update = gr.update(open=False)
    elif status in ["running", "failed"]: # Optional: force open when active/failed
         log_update = gr.update(open=True)

    report_update = gr.update() # Default: leave unchanged
    if status == "completed":
        report_update = gr.update(open=True) # Force open on completion
    elif status != "idle": # Keep closed if not completed and not idle
         report_update = gr.update(open=False)


    return (
        status.upper(),
        mid,
        error_md,
        gr.update(value=plan_md, visible=True), # Update content
        plan_update, # Update open state based on logic above
        gr.update(value=log_md, visible=True), # Update content
        log_update, # Update open state based on logic above
        gr.update(value=report_md, visible=True), # Update content
        report_update # Update open state based on logic above
    )

async def handle_chat_message(message: str, history: List[Tuple[str, str]], state: Dict) -> AsyncGenerator[Tuple, None]:
    """
    Handles incoming chat messages, interacts with AgentController,
    and streams back responses and UI updates for all components.
    Uses Gradio state to manage mission context.
    """
    # Ignore empty/whitespace messages early
    if not message or not message.strip():
        # Yield original state without changes
        status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)
        yield (
            history, state, status_upd, mid_upd, error_upd,
            plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
            report_disp_upd, report_acc_upd
        )
        return

    logger.info(f"Handling chat message: '{message}'")
    agent_controller, context_manager = initialize_components()

    # Get or initialize mission state
    mission_id = state.get("mission_id")
    mission_status = state.get("mission_status", "idle")
    execution_log = state.get("execution_log", []) # Get local copy from state
    current_mission_id = state.get("mission_id")

    # Append user message immediately (with placeholder for response)
    history.append([message, None])
    # Yield intermediate state to show user message quickly
    status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)
    yield (
        history, state, status_upd, mid_upd, error_upd,
        plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
        report_disp_upd, report_acc_upd
    )
    await asyncio.sleep(0.01) # Small delay to ensure UI updates

    # --- Call AgentController to handle the message ---
    try:
        # Pass history including the latest user message
        messenger_output = await agent_controller.handle_user_message(
            user_message=message,
            chat_history=history, # Pass full history
            mission_id=current_mission_id
        )
        agent_response = messenger_output.get("response", "Sorry, I couldn't process that.")
        action = messenger_output.get("action")
        research_request = messenger_output.get("request")

    except Exception as msg_e:
        logger.error(f"Error calling handle_user_message: {msg_e}", exc_info=True)
        agent_response = f"Sorry, an internal error occurred: {msg_e}"
        action = None
        research_request = None

    # Update the placeholder in history with the agent's response
    if history and history[-1][1] is None:
         history[-1][1] = agent_response
    else:
         # Should not happen with the immediate append above, but log if it does
         logger.warning("History structure unexpected when adding agent response.")
         history.append((message, agent_response)) # Defensive append

    # Prepare UI updates after messenger response
    status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)

    # --- Handle Actions (e.g., Start Research) ---

    if action == "start_research" and research_request:
        if mission_status not in ["idle", "completed", "failed"]:
             # Append a system message to history
             history.append((None, "(System: A mission is already in progress or initializing. Please wait.)"))
             # Yield the current state (including the system message) without starting mission
             # Note: The wrapper adds the chat_input update
             yield (
                 history, state, status_upd, mid_upd, error_upd, # Pass updated history
                 plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
                 report_disp_upd, report_acc_upd
             )
             return # Stop processing here

        logger.info(f"MessengerAgent requested to start research: {research_request}")
        # Update history to acknowledge starting (append system message)
        history.append((None, f"(System: Starting research mission for: '{research_request[:50]}...')"))

        # Reset state for the new mission
        state["mission_status"] = "initializing" # Update state directly
        state["mission_id"] = None
        state["mission_plan"] = None
        state["final_report"] = None
        state["mission_error"] = None
        state["execution_log"] = []
        state["notifications"] = []
        execution_log = [] # Reset local copy too

        # Prepare and yield immediate history update and status change
        status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)
        # Note: The wrapper adds the chat_input update
        yield (
            history, state, status_upd, mid_upd, error_upd, # Pass updated history
            plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
            report_disp_upd, report_acc_upd
        )

        # --- Run mission asynchronously ---
        # --- (Existing research loop logic starts here) ---
        # Make sure all yields inside this try/except block match the expected tuple structure
        # (history, state, status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd)
        try:
            log_queue = queue.Queue()
            def gradio_update_callback(
                q: queue.Queue, # Type hint for clarity
                update_data: Any, # Can be ExecutionLogEntry or dict for feedback
                mid: Optional[str] = None,
                status: Optional[str] = None
            ):
                 """Callback to put updates into the queue for Gradio."""
                 if q:
                      item = {"type": "update", "log_entry": update_data, "mission_id": mid, "status": status}
                      # If it's agent feedback, pass the whole dict
                      if isinstance(update_data, dict) and update_data.get("type") == "agent_feedback":
                           item = update_data
                      q.put(item)

            # Start the mission in a separate thread (existing logic)
            # --- (Existing research loop logic continues here) ---
            # Make sure all yields inside this loop return the correct tuple structure
            # (history, state, status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd)
            # Example modification for a yield inside the loop:
            # status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)
            # yield (
            #     history, state, status_upd, mid_upd, error_upd,
            #     plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
            #     report_disp_upd, report_acc_upd
            # )
            # --- (End of existing research loop logic) ---
            pass # Placeholder to indicate the rest of the try block exists

        except Exception as e: # Handle exceptions during mission run
            logger.error(f"Error running mission from Gradio: {e}", exc_info=True)
            state["mission_status"] = "failed"
            state["mission_error"] = f"Error running mission: {e}"
            history.append((None, f"(System Error: Failed to run mission. {e})"))
            # Prepare and yield final error state
            status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)
            yield (
                history, state, status_upd, mid_upd, error_upd,
                plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
                report_disp_upd, report_acc_upd
            )

    else: # No research action requested
        # Just yield the state after the initial messenger response
        # Note: history was already updated with agent_response above
        status_upd, mid_upd, error_upd, plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd, report_disp_upd, report_acc_upd = _prepare_ui_updates(state)
        yield (
            history, state, status_upd, mid_upd, error_upd,
            plan_disp_upd, plan_acc_upd, log_disp_upd, log_acc_upd,
            report_disp_upd, report_acc_upd
        )


def run_full_mission_sync_wrapper(*args): # Keep this wrapper as is
    """Runs the async mission logic within a new event loop for the thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # This wrapper runs the async AgentController methods in a separate thread's event loop.

        # Placeholder: Simulate running the mission directly (needs proper async handling)
        controller, user_request, log_queue, callback = args
        mission_id = None
        try:
            logger.info(f"[Thread Wrapper] Starting mission for: {user_request}")
            # --- Stage 1: Start Mission ---
            mission_id = loop.run_until_complete(
                 controller.start_mission(user_request, log_queue=log_queue, update_callback=callback)
            )
            if not mission_id:
                 logger.error("[Thread Wrapper] start_mission failed.")
                 callback(log_queue, None, None, "failed")
                 return

            logger.info(f"[Thread Wrapper] Mission started: {mission_id}")
            # --- Stage 2: Run Mission ---
            loop.run_until_complete(
                 controller.run_mission(mission_id, log_queue=log_queue, update_callback=callback)
            )
            logger.info(f"[Thread Wrapper] Mission finished: {mission_id}")
            callback(log_queue, None, mission_id, "completed")

        except Exception as e:
             current_stage = "execution" if mission_id else "initialization"
             log_mission_id = mission_id or "N/A"
             logger.error(f"[Thread Wrapper] Exception during {current_stage} for mission {log_mission_id}: {e}", exc_info=True)
             error_log = ExecutionLogEntry(agent_name="System", action=f"Mission {current_stage.capitalize()}", status="failure", error_message=f"Thread error: {e}", mission_id=mission_id)
             callback(log_queue, error_log, mission_id, "failed") # Log error via callback
             callback(log_queue, None, mission_id, "failed") # Signal thread end with failed status
        finally:
             # Signal thread end if not already done by exception handler
             # callback(log_queue, None, mission_id, state.get("mission_status", "unknown")) # Ensure final signal
             pass

    finally:
        loop.close()
        logger.info("[Thread Wrapper] Closed event loop.")


# --- Remove Duplicate UI Definition ---
# It seems the UI was defined twice. Removing the second definition block.

# --- Modify Original UI Definition ---
# (Inside the first `with gr.Blocks(theme=retro_theme, css=CUSTOM_CSS) as demo:` block)

            # --- (Existing components before chat input) ---

        # --- Right Column ---
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(label="Conversation", height=600) # Increased height

            # --- Chat Input Row ---
            with gr.Row(elem_classes=["chat-input-row"]): # Add class for potential CSS
                chat_input = gr.Textbox(
                    label="Your Message", # Keep label for accessibility, hide with CSS if needed
                    placeholder="Type your message or 'start research: [your request]'",
                    show_label=False, # Hide the label visually
                    scale=4 # Give textbox more space
                )
                send_button = gr.Button("Send", scale=1, variant="primary") # Add send button, make primary

            # --- Execution Log Accordion ---
            with gr.Accordion("Execution Log", open=True) as log_accordion:
                 log_display = gr.Markdown("Execution log is empty.", elem_classes=["execution-log-display"])

            # --- Final Report Accordion ---
            with gr.Accordion("Final Report", open=False) as report_accordion:
                report_display = gr.Markdown("Final report will appear here upon completion.")

    # --- Event Handlers (Defined AFTER components) ---
    output_components = [ # Exclude chat_input from the main handler's outputs
        chatbot, mission_state, # Core updates
        status_display, mission_id_display, error_display, # Overview updates
        plan_display, plan_accordion, # Plan updates
        log_display, log_accordion, # Log updates
        report_display, report_accordion # Report updates
    ]

    # Link Textbox Enter key submit to the main handler function
    chat_msg_submit = chat_input.submit(
        handle_chat_message, # Use the main handler
        inputs=[chat_input, chatbot, mission_state],
        outputs=output_components
    )
    # Add .then() to clear input after submit
    chat_msg_submit.then(lambda: gr.update(value=""), None, [chat_input], queue=False)


    # Link Send button click to the main handler function
    send_button_click = send_button.click(
        handle_chat_message, # Use the main handler
        inputs=[chat_input, chatbot, mission_state],
        outputs=output_components
    )
    # Add .then() to clear input after click
    send_button_click.then(lambda: gr.update(value=""), None, [chat_input], queue=False)


    # Remove the old .then() clearing logic as it's handled by the wrapper now
    # chat_msg.then(lambda: gr.update(value=""), None, [chat_input], queue=False) # REMOVED


# Add CSS specifically for the log display height and scroll AFTER the main Blocks definition
# Also add basic styling for the chat input row if needed
# This is a common pattern as Gradio might wrap components in divs
demo.css = """
.execution-log-display .output_markdown { /* Target Markdown output inside the element with class */
    max-height: 400px !important; /* Max height */
    overflow-y: auto !important; /* Vertical scroll */
    border: 1px solid #e0e0e0;
    padding: 10px;
    background-color: #f9f9f9; /* Light background for contrast */
}
""" + (CUSTOM_CSS if 'CUSTOM_CSS' in locals() else "") # Append existing CSS if defined


if __name__ == "__main__":
    # Initialize components once before launching
    try:
        initialize_components()
        logger.info("Launching Gradio interface...")
        demo.queue().launch() # Use queue() for handling multiple users/requests
    except Exception as e:
        logger.error(f"Failed to launch Gradio app: {e}", exc_info=True)
        print(f"Failed to launch Gradio app: {e}")
