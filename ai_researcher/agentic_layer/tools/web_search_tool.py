import os
import logging
import queue
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Callable

# Import config to access provider settings
from ai_researcher import config

logger = logging.getLogger(__name__)

# Dynamically import clients based on availability and configuration
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None
    if config.WEB_SEARCH_PROVIDER == "tavily":
        logger.warning("Tavily provider selected, but 'tavily-python' library not installed. Please run: pip install tavily-python")

try:
    from linkup import LinkupClient
except ImportError:
    LinkupClient = None
    if config.WEB_SEARCH_PROVIDER == "linkup":
        logger.warning("LinkUp provider selected, but 'linkup-python' library not installed. Please run: pip install linkup-python")

# --- Add specific type import for LinkUp ---
try:
    from linkup.types import LinkupSearchResults # <-- Import the specific type
except ImportError:
    LinkupSearchResults = None # Define as None if linkup is not installed
# --- End Add ---


# Define the input schema (Renamed for generality)
class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query for the web search engine.")
    max_results: int = Field(5, description="Maximum number of search results desired.") # Default to 5

class WebSearchTool:
    """
    Tool for performing web searches using the configured provider (Tavily or LinkUp).
    """
    def __init__(self, controller=None):
        self.provider = config.WEB_SEARCH_PROVIDER
        self.client = None
        self.controller = controller  # Store the controller reference
        # Use a consistent, generic name for registration
        self.name = "web_search"
        self.description = f"Performs a web search using the configured provider ({self.provider.capitalize()}) to find up-to-date information."
        self.parameters_schema = WebSearchInput

        if self.provider == "tavily":
            if not TavilyClient:
                 raise ImportError("Tavily provider selected, but 'tavily-python' library not installed.")
            api_key = config.TAVILY_API_KEY
            if not api_key:
                raise ValueError("TAVILY_API_KEY environment variable not set, but Tavily is selected as the provider.")
            self.client = TavilyClient(api_key=api_key)
            logger.info("WebSearchTool initialized with TavilyClient.")
        elif self.provider == "linkup":
            if not LinkupClient:
                raise ImportError("LinkUp provider selected, but 'linkup-python' library not installed.")
            api_key = config.LINKUP_API_KEY
            if not api_key:
                raise ValueError("LINKUP_API_KEY environment variable not set, but LinkUp is selected as the provider.")
            self.client = LinkupClient(api_key=api_key)
            logger.info("WebSearchTool initialized with LinkupClient.")
        else:
            raise ValueError(f"Unsupported web search provider configured: {self.provider}")

    async def execute(
        self,
        query: str,
        max_results: int = 5,
        update_callback: Optional[Callable] = None,
        log_queue: Optional[queue.Queue] = None,
        mission_id: Optional[str] = None
        # Removed agent_controller parameter
    ) -> Dict[str, Any]:
        """
        Executes the web search using the configured provider's API.
        Optionally sends feedback via a callback.

        Args:
            query: The search query string.
            max_results: Maximum number of results desired.
            update_callback: Optional callback function for sending updates.
            log_queue: Optional queue for logging.
            mission_id: Optional mission ID for tracking web search calls.

        Returns:
            A dictionary containing a list under the key 'results' on success,
            or a dictionary with an 'error' key on failure.
        """
        logger.info(f"Executing {self.provider.capitalize()} search for '{query}' with max_results={max_results}")
        formatted_results = []
        error_msg = None

        # --- REMOVED: Web Search Count Update Logic ---
        # This responsibility is moved to the agent calling the tool.

        query = query + " academic paper" # Keep academic paper suffix for now

        try:
            if self.provider == "tavily":
                # Tavily client's search method (synchronous)
                response = self.client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=max_results
                )
                search_results = response.get('results', [])
                for result in search_results:
                    formatted_results.append({
                        "title": result.get('title', 'No Title'),
                        "snippet": result.get('content', 'No Snippet'), # Tavily uses 'content'
                        "url": result.get('url', '#')
                    })

            elif self.provider == "linkup":
                # Linkup client's search method (assuming synchronous)
                response = self.client.search(
                    query=query,
                    depth="standard", # As per example
                    output_type="searchResults", # To get structured results
                    include_images=False,
                    # Linkup might not have a direct 'max_results', handle post-fetch
                )

                # Adapt parsing based on actual Linkup response structure
                if LinkupSearchResults and isinstance(response, LinkupSearchResults): # Check for the specific type
                    search_results = response.results[:max_results] # Access .results attribute and slice
                    for result in search_results:
                        # Check if result has the expected attributes (like LinkupSearchTextResult)
                        if hasattr(result, 'name') and hasattr(result, 'content') and hasattr(result, 'url'):
                            formatted_results.append({
                                "title": result.name,
                                "snippet": result.content,
                                "url": result.url
                            })
                        else:
                            logger.warning(f"Linkup result item has unexpected structure: {result}")
                elif isinstance(response, dict) and 'error' in response:
                     error_msg = f"LinkUp API error: {response['error']}"
                     logger.error(error_msg)
                # Add handling for other potential error formats if Linkup API has them
                # elif ... other error conditions ...
                else:
                    # Handle truly unexpected response format (neither LinkupSearchResults nor known error dict)
                    error_msg = f"Unexpected LinkUp response format: {type(response)}"
                    logger.warning(f"{error_msg}. Response: {response}")


            if error_msg:
                 return {"error": error_msg}

            logger.info(f"{self.provider.capitalize()} search successful, returning {len(formatted_results)} results.")

            # --- Send Feedback: Search Complete ---
            if update_callback: # No need for log_queue here if callback handles it
                feedback_payload = {
                    "type": "web_search_complete", # Specific type for UI handling
                    "provider": self.provider,
                    "query": query,
                    "num_results": len(formatted_results)
                }
                try:
                    # Wrap payload and call with required arguments
                    formatted_message = {"type": "agent_feedback", "payload": feedback_payload}
                    # Pass log_queue as first argument and formatted_message as second argument
                    update_callback(log_queue, formatted_message)
                    logger.debug(f"Sent web_search_complete feedback payload for query '{query}' via {self.provider}")
                except Exception as cb_e:
                    # Log the specific callback error, but don't necessarily crash the tool
                    logger.error(f"Failed to send web_search_complete feedback payload via callback: {cb_e}", exc_info=False) # exc_info=False to avoid redundant traceback if handled upstream
            # --- End Feedback ---

            return {"results": formatted_results}

        except Exception as e:
            error_msg = f"An error occurred during {self.provider.capitalize()} search for query '{query}': {e}"
            logger.error(error_msg, exc_info=True)
            # --- Send Feedback: Search Error ---
            if update_callback:
                feedback_payload = {
                    "type": "web_search_error",
                    "provider": self.provider,
                    "query": query,
                    "error": str(e) # Send simplified error message
                }
                try:
                    # Wrap payload and call with required arguments
                    formatted_message = {"type": "agent_feedback", "payload": feedback_payload}
                    # Pass log_queue as first argument and formatted_message as second argument
                    update_callback(log_queue, formatted_message)
                    logger.debug(f"Sent web_search_error feedback payload for query '{query}'")
                except Exception as cb_e:
                     logger.error(f"Failed to send web_search_error feedback payload via callback: {cb_e}", exc_info=False)
            # --- End Feedback ---
            return {"error": error_msg}
