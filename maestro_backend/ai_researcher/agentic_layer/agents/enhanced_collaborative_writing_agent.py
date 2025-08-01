"""
Enhanced Collaborative Writing Agent for MAESTRO - Agentic Workflow
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
import asyncio

from .base_agent import BaseAgent
from ..context.writing_context_manager import WritingContextManager
from ..tool_registry import ToolRegistry, ToolDefinition
from ..tools import writing_tools # Import our new tools
from ai_researcher import config

logger = logging.getLogger(__name__)

class EnhancedCollaborativeWritingAgent(BaseAgent):
    """
    An agent that uses an LLM-driven, plan-and-execute workflow to assist with writing.
    """
    
    def __init__(
        self,
        model_dispatcher,
        db_session,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        controller: Optional[Any] = None
    ):
        agent_name = "EnhancedCollaborativeWritingAgent"
        
        # Determine model from config, allowing override
        writing_model_type = config.AGENT_ROLE_MODEL_TYPE.get("writing", "intelligent")
        provider = config.PROVIDER_CONFIG[config.INTELLIGENT_LLM_PROVIDER]
        effective_model_name = model_name or provider[f"{writing_model_type}_model"]

        super().__init__(
            agent_name=agent_name,
            model_dispatcher=model_dispatcher,
            tool_registry=self._setup_tool_registry(), # Initialize with its own tools
            system_prompt=system_prompt or self._default_system_prompt(),
            model_name=effective_model_name
        )
        
        self.controller = controller
        self.mission_id = None
        self.context_manager = WritingContextManager(db_session)

    def _setup_tool_registry(self) -> ToolRegistry:
        """Creates and populates the ToolRegistry for this agent."""
        registry = ToolRegistry()
        
        # Register all the writing tools
        registry.register_tool(ToolDefinition(
            name="respond_to_user",
            description="Sends a direct message to the user. Use this when a direct answer is needed or to confirm completion of a task.",
            parameters_schema=writing_tools.RespondToUserInput,
            implementation=writing_tools.respond_to_user
        ))
        registry.register_tool(ToolDefinition(
            name="document_search",
            description="Searches for relevant information within the currently selected document group.",
            parameters_schema=writing_tools.DocumentSearchInput,
            implementation=writing_tools.document_search
        ))
        registry.register_tool(ToolDefinition(
            name="web_search",
            description="Performs a web search to find external, up-to-date information.",
            parameters_schema=writing_tools.WebSearchInput,
            implementation=writing_tools.web_search
        ))
        registry.register_tool(ToolDefinition(
            name="add_section",
            description="Adds a new section to the document.",
            parameters_schema=writing_tools.AddSectionInput,
            implementation=writing_tools.add_section
        ))
        registry.register_tool(ToolDefinition(
            name="add_paragraph",
            description="Adds a new paragraph to a specified section.",
            parameters_schema=writing_tools.AddParagraphInput,
            implementation=writing_tools.add_paragraph
        ))
        registry.register_tool(ToolDefinition(
            name="propose_and_add_paragraph",
            description="Generates content for a new paragraph, proposes it to the user for approval, and adds it to the document upon confirmation.",
            parameters_schema=writing_tools.ProposeAndAddParagraphInput,
            implementation=writing_tools.propose_and_add_paragraph
        ))
        
        return registry

    def _default_system_prompt(self) -> str:
        """The system prompt that instructs the agent on its collaborative workflow."""
        return """You are an advanced collaborative writing assistant. Your goal is to help users create and edit documents by being a proactive and intelligent partner.

**Your Core Workflow:**

1.  **Analyze the Request:** Carefully understand the user's message, the conversation history, and the current state of the document.
2.  **Think Step-by-Step:** Decide on the best course of action. This could involve searching for information, adding a new section, or writing new content.
3.  **Execute or Propose:**
    *   For direct commands or information retrieval (e.g., `web_search`, `document_search`), execute the tool directly.
    *   **For any action that modifies the document content (`add_paragraph`, `add_section`), you MUST first propose the change to the user.** Use the `propose_and_add_paragraph` tool for this. This tool will generate the content and ask for the user's approval.
    *   If the user asks a simple question or a greeting, use the `respond_to_user` tool to chat with them.

**Interaction Model:**

*   **User:** "Add a paragraph about the importance of AI ethics."
*   **You (Action):** Decide to use `propose_and_add_paragraph`.
    *   **Internal Step 1 (Content Generation):** You will be asked to generate the content for the paragraph based on the request.
    *   **Internal Step 2 (Proposal to User):** The system will show your generated content to the user and ask: "I've drafted the following content. Shall I add it to the document?"
*   **User:** "Yes, that looks great."
*   **You (Action):** The system will then automatically call the `add_paragraph` tool with the approved content.

**Key Rules:**

*   **NEVER** call `add_paragraph` or `add_section` directly. Always use `propose_and_add_paragraph` to initiate content changes.
*   Your primary role is to decide **which tool to use** based on the user's request. The system handles the multi-step interaction for proposals.
*   When using `propose_and_add_paragraph`, you only need to provide the `section_id` and a `prompt` for the content generation. The system will handle the rest.
*   Always use exact `section_id` values from the document outline provided in the context. Do not make up IDs.
*   If no sections exist, your first step should be to use `add_section` (which will also be a proposal).
"""

    async def run(
        self,
        user_message: str,
        draft_id: str,
        draft: Any,
        session_settings: Optional[Dict[str, Any]] = None,
        context_override: Optional[Dict[str, Any]] = None,
        operation_mode: str = "balanced",
        mission_id: str = None,
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None,
        **kwargs
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
        """
        Main execution method for the agentic writing workflow.
        This version supports a multi-step, interactive process.
        """
        self.mission_id = mission_id
        logger.info(f"{self.agent_name}: Starting agentic workflow for draft {draft_id}")

        try:
            user_id = kwargs.get('user_id', 1)
            
            # Check for a pending confirmation
            is_confirmation = context_override and context_override.get("is_confirmation", False)
            
            if is_confirmation:
                # This is the second step: user has confirmed a proposal
                return await self._handle_confirmation(context_override, draft_id, user_id, log_queue, update_callback)

            # This is the first step: a new user request
            return await self._handle_new_request(user_message, draft_id, draft, session_settings, context_override, operation_mode, user_id, log_queue, update_callback)

        except Exception as e:
            logger.error(f"Error in EnhancedCollaborativeWritingAgent.run: {e}", exc_info=True)
            error_response = {'message': f"I encountered an error: {str(e)}"}
            return error_response, None, f"Error in agentic workflow: {str(e)}"

    def _create_planning_prompt(self, user_message: str, context: Dict[str, Any]) -> str:
        """Creates the prompt for the LLM to generate a plan."""
        
        document_outline = context.get("document_outline", {})
        sections_info = [{'id': s.get('id'), 'title': s.get('title')} for s in document_outline.get('sections', [])]
        
        context_summary = {
            "draft_title": context.get("draft_title"),
            "word_count": document_outline.get("total_word_count", 0),
            "sections": sections_info,
            "conversation_history": context.get("conversation_history", [])[-5:],
            "document_group_id": context.get("document_group", {}).get("group_id")
        }

        prompt = f"""
User Request: "{user_message}"

Current Context:
{json.dumps(context_summary, indent=2)}

Based on the user's request and the current context, generate a JSON plan of a SINGLE tool call to move forward.
Remember the rules: to add content, you must use 'propose_and_add_paragraph'.
"""
        return prompt

    def _create_content_generation_prompt(self, user_prompt: str, context: Dict[str, Any]) -> str:
        """Creates a prompt for the LLM to generate content for a proposal."""
        return f"""
A user wants to add a paragraph to their document. Based on their request and the document's context, please write the content for this new paragraph.

User's Request: "{user_prompt}"

Document Context:
{json.dumps(context, indent=2)}

Please provide only the text for the paragraph as a raw string, without any JSON formatting.
"""

    async def _handle_new_request(
        self, user_message, draft_id, draft, session_settings, context_override, operation_mode, user_id, log_queue, update_callback
    ):
        """Handles the initial user request to generate and execute a plan."""
        # 1. Assemble Context
        context = await self.context_manager.assemble_context(
            draft_id=draft_id, draft=draft, user_id=user_id,
            request_type=operation_mode, settings=session_settings,
            context_override=context_override
        )
        
        # 2. Generate Plan (LLM Call 1)
        planning_prompt = self._create_planning_prompt(user_message, context)
        llm_response, model_details = await self._call_llm(
            user_prompt=planning_prompt,
            agent_mode="writing_planner",
            response_format={"type": "json_object"}
        )

        if not llm_response or not llm_response.choices:
            raise Exception("Failed to generate a plan from the LLM.")

        plan_json = json.loads(llm_response.choices[0].message.content)
        plan = plan_json.get("plan", [])
        
        if not plan:
            return {"message": "I'm not sure how to proceed. Could you please clarify your request?"}, None, "No plan generated."

        # 3. Execute the first step of the plan
        step = plan[0]
        tool_name = step.get("tool_name")
        arguments = step.get("arguments", {})

        # Add necessary context for tool execution
        arguments.update({
            'agent_controller': self.controller,
            'writing_context_manager': self.context_manager,
            'draft_id': draft_id,
            'user_id': user_id,
            'context': context,
            'model_dispatcher': self.model_dispatcher,
            'content_generation_prompt_creator': self._create_content_generation_prompt
        })

        if update_callback:
            await update_callback({"type": "agent_status", "status": f"Executing: {tool_name}..."})

        result = await self._execute_tool(tool_name, arguments, log_queue=log_queue, update_callback=update_callback)

        # If the tool requires confirmation, the result will contain `is_proposal=True`
        if isinstance(result, dict) and result.get("is_proposal"):
            return result, model_details, "Proposal sent to user."

        final_response = {
            "message": result.get("message", "Task completed."),
            "operations_executed": [{"tool": tool_name, "result": result}]
        }
        return final_response, model_details, "Agentic workflow completed successfully."

    async def _handle_confirmation(self, context_override, draft_id, user_id, log_queue, update_callback):
        """Handles the user's confirmation of a proposed action."""
        logger.info("Handling user confirmation.")
        
        original_tool_name = context_override.get("tool_name")
        original_arguments = context_override.get("arguments", {})

        if not original_tool_name:
            raise ValueError("Confirmation context is missing the original tool name.")

        # The "real" tool to execute is derived from the proposal tool
        # e.g., 'propose_and_add_paragraph' becomes 'add_paragraph'
        execution_tool_name = original_tool_name.replace("propose_and_", "")

        # Add context for the actual tool execution
        original_arguments.update({
            'agent_controller': self.controller,
            'writing_context_manager': self.context_manager,
            'draft_id': draft_id,
            'user_id': user_id
        })

        if update_callback:
            await update_callback({"type": "agent_status", "status": f"Confirmed. Executing: {execution_tool_name}..."})

        result = await self._execute_tool(execution_tool_name, original_arguments, log_queue=log_queue, update_callback=update_callback)

        final_response = {
            "message": result.get("message", "Action completed successfully."),
            "operations_executed": [{"tool": execution_tool_name, "result": result}]
        }
        return final_response, None, "Confirmed action completed."
