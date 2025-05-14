import asyncio # <-- Import asyncio
from typing import Dict, List, Optional, Type, Any
from pydantic import BaseModel, Field
import inspect

# --- Base Tool Schema ---
# Define a base schema for tool parameters if needed, or rely on individual tool schemas.
# Example:
class BaseToolInputSchema(BaseModel):
    pass # Tools will define their own specific parameters

# --- Tool Definition ---
# A simple structure to hold tool information
class ToolDefinition:
    def __init__(self, name: str, description: str, parameters_schema: Type[BaseModel], implementation: callable):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.implementation = implementation # The actual function/method to call

    def get_schema_for_llm(self) -> Dict[str, Any]:
        """Generates a JSON schema description suitable for LLM function calling."""
        # Use Pydantic's schema generation, removing titles for cleaner LLM prompt
        schema = self.parameters_schema.model_json_schema()
        # Remove 'title' fields recursively if they exist, as they can clutter the prompt
        def remove_title(d):
            if isinstance(d, dict):
                d.pop('title', None)
                for key, value in d.items():
                    remove_title(value)
            elif isinstance(d, list):
                for item in d:
                    remove_title(item)
        remove_title(schema)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }

# --- Tool Registry ---
class ToolRegistry:
    """
    Manages the tools available to the agents.
    Allows registering tools and retrieving their definitions/schemas.
    """
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        print("ToolRegistry initialized.")

    def register_tool(self, tool: ToolDefinition):
        """Registers a tool definition."""
        if tool.name in self._tools:
            print(f"Warning: Tool '{tool.name}' is already registered. Overwriting.")
        self._tools[tool.name] = tool
        print(f"Tool '{tool.name}' registered.")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retrieves a tool definition by name."""
        return self._tools.get(name)

    def get_all_tools(self) -> List[ToolDefinition]:
        """Returns a list of all registered tool definitions."""
        return list(self._tools.values())

    def get_tool_schemas_for_llm(self) -> List[Dict[str, Any]]:
        """
        Generates a list of tool schemas formatted for LLM function/tool calling.
        """
        return [tool.get_schema_for_llm() for tool in self._tools.values()]

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any: # <-- Make async
        """
        Executes a registered tool by name with the provided arguments, handling both sync and async tools.

        Args:
            name: The name of the tool to execute.
            arguments: A dictionary of arguments validated against the tool's schema.

        Returns:
            The result of the tool's execution.

        Raises:
            ValueError: If the tool is not found or if arguments are invalid
                        (though validation should ideally happen before calling this).
            Exception: If the tool implementation raises an error.
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry.")

        # Basic check: Ensure implementation is callable
        if not callable(tool.implementation):
             raise ValueError(f"Implementation for tool '{name}' is not callable.")

        print(f"Executing tool '{name}' with arguments: {arguments}")
        try:
            # Validate arguments using Pydantic model before execution
            # This ensures the implementation receives data in the expected format
            validated_args = tool.parameters_schema(**arguments)
            # Execute the tool's implementation function/method
            # Pydantic models have a .model_dump() method to get dict if needed by func
            # Or pass the model instance directly if the func expects it
            # Assuming the implementation function takes keyword arguments matching the schema:

            # Check if the implementation is an async function
            if asyncio.iscoroutinefunction(tool.implementation):
                result = await tool.implementation(**arguments) # <-- Await async tool
            else:
                # Run synchronous tools in a thread pool to avoid blocking the event loop
                # Note: This assumes the synchronous tool might be blocking (like compute or sync I/O)
                # If a sync tool is known to be very fast and non-blocking, direct call might be okay,
                # but using to_thread is safer for generality.
                loop = asyncio.get_running_loop()
                # We need to pass the function and its arguments to to_thread
                # Use a lambda or functools.partial if needed, but direct call with kwargs works
                result = await asyncio.to_thread(tool.implementation, **arguments)

            print(f"Tool '{name}' execution finished.")
            return result
        except Exception as e:
            print(f"Error executing tool '{name}': {e}")
            # Re-raise the exception to be handled by the agent/controller
            raise
