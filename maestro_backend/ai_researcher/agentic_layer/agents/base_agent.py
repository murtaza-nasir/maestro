import asyncio
import inspect # <-- Import inspect
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import datetime # <--- ADDED IMPORT

# Use absolute imports starting from the top-level package 'ai_researcher'
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry

# Define the standard output structure for agent run methods
# result_dict: The primary output data (e.g., plan, notes, text content, messenger response dict)
# model_details: Information about the LLM call(s) made
# scratchpad_update: Optional string containing updates for the agent's scratchpad
AgentOutput = Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the framework.
    Provides common functionalities like interacting with the ModelDispatcher and ToolRegistry.
    """
    def __init__(
        self,
        agent_name: str,
        model_dispatcher: ModelDispatcher,
        tool_registry: Optional[ToolRegistry] = None, # Tools might be optional for some agents
        system_prompt: Optional[str] = None,
        model_name: Optional[str] = None # Optional: Specific model override for this agent
    ):
        self.agent_name = agent_name
        self.model_dispatcher = model_dispatcher
        self.tool_registry = tool_registry
        # --- MODIFIED LINE ---
        today_date = datetime.date.today().strftime('%Y-%m-%d')
        default_prompt = f"You are the {agent_name}. Your goal is to fulfill your specific role in the research process. Current date: {today_date}"
        self.system_prompt = system_prompt or default_prompt
        # --- END MODIFICATION ---
        self.model_name = model_name # If None, ModelDispatcher will use default for the mode

        print(f"Initialized {self.agent_name} (Model: {self.model_name or 'Default'})")

    def _create_messages(self, user_prompt: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        """Helper method to construct the message list for the LLM."""
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            # Ensure history items are valid dictionaries
            valid_history = [msg for msg in history if isinstance(msg, dict) and "role" in msg and "content" in msg]
            messages.extend(valid_history)
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def _call_llm( # <-- Make async
        self,
        user_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None, # For function/tool calling
        tool_choice: Optional[Any] = None, # e.g., "auto", "required", {"type": "function", "function": {"name": "my_function"}}
        response_format: Optional[Dict[str, str]] = None, # e.g., {"type": "json_schema"}
        agent_mode: Optional[str] = None, # <-- Add agent_mode parameter
        log_queue: Optional[Any] = None, # <-- Add log_queue parameter for UI updates
        update_callback: Optional[Any] = None, # <-- Add update_callback parameter for UI updates
        **kwargs: Any # Accept arbitrary keyword arguments
    ) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]: # Return type: (ChatCompletion, model_details_dict) or (None, None)
        """
        Sends a request to the LLM via the ModelDispatcher, passing along any extra arguments.

        Returns:
             A tuple containing:
             - The raw response object from the LLM client (e.g., ChatCompletion) or None on failure.
             - A dictionary with model call details or None on failure.
        """
        if not self.model_dispatcher:
             print(f"{self.agent_name} Error: ModelDispatcher is not initialized.")
             return None, None

        messages = self._create_messages(user_prompt, history)
        try:
            # Determine the model to use: prioritize kwargs, then agent's default
            model_to_use = kwargs.pop('model', self.model_name) # Get 'model' from kwargs, default to self.model_name, and remove it from kwargs

            # Get mission_id from agent context if available
            mission_id = getattr(self, 'mission_id', None)
            
            # Await the async dispatch method
            response, model_call_details = await self.model_dispatcher.dispatch( # <-- Use await
                messages=messages,
                model=model_to_use, # Pass the determined model
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                agent_mode=agent_mode, # <-- Pass agent_mode to dispatch
                log_queue=log_queue, # <-- Pass log_queue down to dispatch
                update_callback=update_callback, # <-- Pass update_callback down to dispatch
                mission_id=mission_id, # <-- Pass mission_id for status checking
                **kwargs # Pass any extra arguments (like max_tokens, temperature)
            )

            # --- ADD LOGGING FOR ALL LLM CALLS ---
            log_status = "success" if response and response.choices else "failure"
            output_summary = "No response"
            if log_status == "success":
                try:
                    output_summary = f"Response received. Choice 0: {response.choices[0].message.content[:100]}..."
                except Exception:
                    output_summary = "Response received, but summary failed."

            context_manager = None
            if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'context_manager'):
                context_manager = self.controller.context_manager

            if context_manager and mission_id and log_queue and update_callback:
                context_manager.log_execution_step(
                    mission_id=mission_id,
                    agent_name=self.agent_name,
                    action=f"LLM Call ({agent_mode or 'general'})",
                    input_summary=f"Prompt: {user_prompt[:150]}...",
                    output_summary=output_summary,
                    status=log_status,
                    model_details=model_call_details,
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            # --- END LOGGING ---

            # Update mission stats if model_call_details is available
            # This ensures all agents update stats after LLM calls
            if hasattr(self, 'mission_id') and self.mission_id and model_call_details:
                # Import here to avoid circular imports
                from ai_researcher.agentic_layer.agent_controller import AgentController
                # Get the controller instance if available
                controller = getattr(self, 'controller', None)
                # If controller is available and has a context_manager, update stats via context_manager
                if controller and hasattr(controller, 'context_manager'):
                    # Call the update_mission_stats method on the context_manager
                    # The context_manager.update_mission_stats method uses the queue and callback
                    # passed *to it*, not the ones from the agent's context.
                    controller.context_manager.update_mission_stats(
                        self.mission_id,
                        model_call_details
                        # Removed log_queue and update_callback arguments here
                    )

            return response, model_call_details # Return the tuple
        except Exception as e:
            print(f"{self.agent_name} Error: Failed to get response from LLM via ModelDispatcher: {e}")
            # Consider logging the full traceback here
            # import traceback
            # traceback.print_exc()
            # --- ADD ERROR LOGGING ---
            context_manager = None
            if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'context_manager'):
                context_manager = self.controller.context_manager
            mission_id = getattr(self, 'mission_id', None)

            if context_manager and mission_id and log_queue and update_callback:
                context_manager.log_execution_step(
                    mission_id=mission_id,
                    agent_name=self.agent_name,
                    action=f"LLM Call ({agent_mode or 'general'})",
                    input_summary=f"Prompt: {user_prompt[:150]}...",
                    output_summary=f"Error: {e}",
                    status="failure",
                    error_message=str(e),
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            # --- END ERROR LOGGING ---
            return None, None # Return None for both parts of the tuple on error

    async def _execute_tool(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        tool_registry_override: Optional[ToolRegistry] = None,
        log_queue: Optional[Any] = None, # <-- Add log_queue parameter
        update_callback: Optional[Any] = None # <-- Add update_callback parameter
    ) -> Any:
        """
        Executes a tool using the ToolRegistry asynchronously, passing relevant agent context if the tool accepts it.
        Uses tool_registry_override if provided, otherwise defaults to self.tool_registry.
        Logs the execution step and updates stats via the context manager using the provided callbacks.
        """
        registry_to_use = self.tool_registry or tool_registry_override

        if not registry_to_use:
            print(f"{self.agent_name} Error: ToolRegistry not available (neither self.tool_registry nor override provided).")
            return {"error": "Tool execution capability not available."}

        # --- REVISED DEBUG LOGGING ---
        log_message = f"DEBUG ({self.agent_name}): _execute_tool received args for '{tool_name}'."
        if "filepath" in tool_arguments:
            log_message += f" Filepath value: '{tool_arguments['filepath']}'"
        else:
            # Optionally log that filepath is not applicable for this tool
            # log_message += " (Filepath not applicable for this tool)."
            pass # Or just don't add anything if filepath is missing
        print(log_message)
        # --- END REVISED DEBUG LOGGING ---

        # --- Add Check for Path Mismatch on Entry ---
        # Adjust check to use 'in' operator instead of comparing against the default string
        if "filepath" in tool_arguments and "allowed_base_path" in tool_arguments and tool_name == "read_full_document":
            received_filepath_str = tool_arguments["filepath"] # Get actual value
            allowed_base_path_str = tool_arguments["allowed_base_path"] # Get actual value
            try:
                # Skip path check if allowed_base_path_str is None or 'None'
                if allowed_base_path_str is None or allowed_base_path_str == 'None':
                    print(f"DEBUG ({self.agent_name}): Skipping path check because allowed_base_path is None or 'None'")
                else:
                    # Resolve allowed base relative to CWD if needed
                    allowed_base = Path(allowed_base_path_str)
                    if not allowed_base.is_absolute():
                        allowed_base = Path.cwd().joinpath(allowed_base).resolve()
                    else:
                        allowed_base = allowed_base.resolve()

                    # Check if the received filepath string *starts with* the allowed base path string
                    # This is a simpler check that avoids resolve() issues on the potentially bad path
                    if not received_filepath_str.startswith(str(allowed_base)):
                        print(f"CRITICAL WARNING ({self.agent_name}): _execute_tool received MISMATCHED filepath '{received_filepath_str}' which does not start with allowed base '{allowed_base}'!")
            except Exception as path_ex:
                print(f"DEBUG ({self.agent_name}): Path check exception in _execute_tool: {path_ex}")
        # --- End Path Mismatch Check ---


        try:
            # --- ADD PRE-REGISTRY CALL DEBUG ---
            final_filepath = tool_arguments.get("filepath", "FILEPATH_KEY_MISSING_PRE_REGISTRY")
            print(f"DEBUG ({self.agent_name}): PRE-REGISTRY CALL for '{tool_name}'. Filepath value: '{final_filepath}'")
            # --- END PRE-REGISTRY CALL DEBUG ---

            # Get the tool definition
            tool_def = registry_to_use.get_tool(tool_name)
            if not tool_def:
                print(f"{self.agent_name} Error: Tool '{tool_name}' not found in the registry.")
                return {"error": f"Tool '{tool_name}' not found."}

            # Inspect the tool's implementation signature
            tool_func = tool_def.implementation
            sig = inspect.signature(tool_func)
            tool_params = sig.parameters

            # Prepare arguments to pass, starting with the ones provided by the LLM
            final_args = tool_arguments.copy()

            # Check for and add extra context arguments if the tool accepts them and the agent has them
            context_args_map = {
                "mission_id": getattr(self, 'mission_id', None),
                "agent_controller": getattr(self, 'controller', None), # Assuming controller is stored as self.controller
                "log_queue": log_queue,  # Use the parameter passed to _execute_tool
                "update_callback": update_callback,  # Use the parameter passed to _execute_tool
                "agent_name": getattr(self, 'agent_name', None) # Pass agent name too?
            }

            for param_name, agent_attr_value in context_args_map.items():
                if param_name in tool_params and agent_attr_value is not None:
                    # Only add if the tool expects it and the agent has a non-None value
                    if param_name not in final_args: # Avoid overwriting args from LLM
                        final_args[param_name] = agent_attr_value
                        print(f"DEBUG ({self.agent_name}): Adding context arg '{param_name}' to tool '{tool_name}' call.")
                    else:
                        print(f"DEBUG ({self.agent_name}): Context arg '{param_name}' already present in LLM args for tool '{tool_name}'. Skipping.")


            # Await the registry's async execute method using the determined registry and final arguments
            result = await registry_to_use.execute_tool(tool_name, final_args) # Pass the augmented args

            # --- ADD Logging and Stats Update ---
            log_status = "success"
            error_message = None
            result_summary = None # Initialize result_summary

            # Process result for logging and determine status
            if isinstance(result, dict) and "error" in result:
                log_status = "failure"
                error_message = result["error"]
                result_summary = f"Error: {error_message}"
            elif result is None: # Handle case where execute_tool itself might fail before tool impl
                 log_status = "failure"
                 error_message = "Tool execution failed (result was None)."
                 result_summary = error_message
            else:
                # Attempt to create a concise summary for logging
                try:
                    if isinstance(result, list):
                        result_summary = f"Returned list with {len(result)} items."
                    elif isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                        result_summary = f"Returned dict with {len(result['results'])} results."
                    elif isinstance(result, str):
                        result_summary = f"Returned string (length: {len(result)})."
                    else:
                        result_summary = f"Returned result of type {type(result).__name__}."
                except Exception:
                    result_summary = "Could not summarize result."

            # Log the execution step using context manager
            context_manager = None
            if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'context_manager'):
                context_manager = self.controller.context_manager

            if context_manager and hasattr(self, 'mission_id') and self.mission_id and log_queue and update_callback:
                context_manager.log_execution_step(
                    mission_id=self.mission_id,
                    agent_name=self.agent_name, # Logged by the agent calling the tool
                    action=f"Execute Tool: {tool_name}",
                    input_summary=f"Args: {str(tool_arguments)[:100]}...", # Log truncated args
                    output_summary=result_summary,
                    status=log_status,
                    error_message=error_message,
                    # Include full args/result in the detailed log if needed, be mindful of size
                    # full_input=final_args,
                    # full_output=result,
                    tool_calls=[{"tool_name": tool_name, "arguments": tool_arguments, "result_summary": result_summary, "error": error_message}], # Log as a tool call structure
                    log_queue=log_queue,
                    update_callback=update_callback
                )
            else:
                # --- MODIFIED: More detailed warning ---
                missing = []
                if not context_manager: missing.append("context_manager")
                # Check for mission_id attribute existence AND if it has a truthy value
                if not hasattr(self, 'mission_id') or not self.mission_id: missing.append("mission_id")
                if not log_queue: missing.append("log_queue")
                if not update_callback: missing.append("update_callback")
                print(f"WARNING ({self.agent_name}): Could not log tool execution for '{tool_name}'. Missing: {', '.join(missing)}")
                # --- END MODIFICATION ---

            # --- Moved Web Search Count Update (Independent of UI Callbacks) ---
            if context_manager and hasattr(self, 'mission_id') and self.mission_id:
                if tool_name == "web_search" and log_status == "success":
                    # Call increment directly, passing None for queue/callback if they are missing
                    context_manager.increment_web_search_count(
                        self.mission_id,
                        log_queue if log_queue else None,
                        update_callback if update_callback else None
                    )
            # --- END Moved Web Search Count Update ---

            # --- END Logging and Stats Update ---

            # Return the actual result
            return result
        except Exception as e:
            print(f"{self.agent_name} Error: Failed to execute tool '{tool_name}': {e}")
            # Log the failure if possible
            context_manager = None
            if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'context_manager'):
                context_manager = self.controller.context_manager
            if context_manager and hasattr(self, 'mission_id') and self.mission_id and log_queue and update_callback:
                 context_manager.log_execution_step(
                     mission_id=self.mission_id, agent_name=self.agent_name,
                     action=f"Execute Tool: {tool_name}", status="failure", error_message=str(e),
                     tool_calls=[{"tool_name": tool_name, "arguments": tool_arguments, "error": str(e)}],
                     log_queue=log_queue, update_callback=update_callback
                 )
            # Return a structured error
            return {"error": f"Error executing tool '{tool_name}': {e}"}

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """
        The main execution method for the agent.
        Subclasses must implement this method to define the agent's specific behavior.
        """
        pass
