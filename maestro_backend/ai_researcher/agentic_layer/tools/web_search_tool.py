import os
import logging
import queue
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Callable

# Import dynamic config to access user-specific provider settings
from ai_researcher.dynamic_config import (
    get_web_search_provider, get_tavily_api_key, get_linkup_api_key, get_searxng_base_url
)

logger = logging.getLogger(__name__)

# Dynamically import clients based on availability and configuration
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from linkup import LinkupClient
except ImportError:
    LinkupClient = None

# --- Add specific type import for LinkUp ---
try:
    from linkup.types import LinkupSearchResults # <-- Import the specific type
except ImportError:
    LinkupSearchResults = None # Define as None if linkup is not installed
# --- End Add ---

# SearXNG doesn't require a specific client library - we'll use requests
try:
    import requests
except ImportError:
    requests = None


# Define the input schema (Renamed for generality)
class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query for the web search engine.")
    max_results: int = Field(5, description="Maximum number of search results desired.") # Default to 5

class WebSearchTool:
    """
    Tool for performing web searches using the configured provider (Tavily or LinkUp).
    """
    def __init__(self, controller=None):
        # Get provider and API keys from user settings or environment
        self.provider = get_web_search_provider()
        self.client = None
        self.controller = controller  # Store the controller reference
        # Use a consistent, generic name for registration
        self.name = "web_search"
        self.description = f"Performs a web search using the configured provider ({self.provider.capitalize()}) to find up-to-date information."
        self.parameters_schema = WebSearchInput
        self.api_key_configured = False

        try:
            if self.provider == "tavily":
                if not TavilyClient:
                     raise ImportError("Tavily provider selected, but 'tavily-python' library not installed.")
                api_key = get_tavily_api_key()
                if not api_key:
                    logger.warning("Tavily API key not configured in user settings or environment variables.")
                    self.api_key_configured = False
                    return
                self.client = TavilyClient(api_key=api_key)
                self.api_key_configured = True
                logger.info("WebSearchTool initialized with TavilyClient.")
            elif self.provider == "linkup":
                if not LinkupClient:
                    raise ImportError("LinkUp provider selected, but 'linkup-python' library not installed.")
                api_key = get_linkup_api_key()
                if not api_key:
                    logger.warning("LinkUp API key not configured in user settings or environment variables.")
                    self.api_key_configured = False
                    return
                self.client = LinkupClient(api_key=api_key)
                self.api_key_configured = True
                logger.info("WebSearchTool initialized with LinkupClient.")
            elif self.provider == "searxng":
                if not requests:
                    raise ImportError("SearXNG provider selected, but 'requests' library not installed.")
                base_url = get_searxng_base_url()
                if not base_url:
                    logger.warning("SearXNG base URL not configured in user settings or environment variables.")
                    self.api_key_configured = False
                    return
                self.client = base_url.rstrip('/')  # Store the base URL as the "client"
                self.api_key_configured = True
                logger.info("WebSearchTool initialized with SearXNG.")
            else:
                raise ValueError(f"Unsupported web search provider configured: {self.provider}")
        except Exception as e:
            logger.error(f"Failed to initialize WebSearchTool: {e}")
            self.api_key_configured = False

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
        # Check if configuration is available
        if not self.api_key_configured:
            if self.provider == "searxng":
                user_friendly_error = f"Web search is not available. Please configure your SearXNG base URL in Settings > Search to enable web search functionality."
            else:
                user_friendly_error = f"Web search is not available. Please configure your {self.provider.capitalize()} API key in Settings > Search to enable web search functionality."
            logger.warning(f"Web search attempted but {self.provider} configuration not available")
            
            # Send user-friendly feedback
            if update_callback:
                feedback_payload = {
                    "type": "web_search_config_error",
                    "provider": self.provider,
                    "query": query,
                    "error": user_friendly_error
                }
                try:
                    formatted_message = {"type": "agent_feedback", "payload": feedback_payload}
                    update_callback(log_queue, formatted_message)
                except Exception as cb_e:
                    logger.error(f"Failed to send web_search_config_error feedback: {cb_e}")
            
            return {"error": user_friendly_error}

        logger.info(f"Executing {self.provider.capitalize()} search for '{query}' with max_results={max_results}")
        formatted_results = []
        error_msg = None

        # Add academic paper suffix for better results
        search_query = query + " academic paper"

        try:
            if self.provider == "tavily":
                # Tavily client's search method (synchronous)
                response = self.client.search(
                    query=search_query,
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
                    query=search_query,
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

            elif self.provider == "searxng":
                # SearXNG search using requests
                search_url = f"{self.client}/search"
                params = {
                    'q': search_query,
                    'format': 'json',
                    'engines': 'google,bing,duckduckgo',  # Use multiple engines for better results
                    'categories': 'general',
                    'safesearch': '1'
                }
                
                response = requests.get(search_url, params=params, timeout=30)
                response.raise_for_status()
                
                search_data = response.json()
                search_results = search_data.get('results', [])
                
                # Limit results and format them
                for result in search_results[:max_results]:
                    formatted_results.append({
                        "title": result.get('title', 'No Title'),
                        "snippet": result.get('content', 'No Snippet'),
                        "url": result.get('url', '#')
                    })

            if error_msg:
                 return {"error": error_msg}

            logger.info(f"{self.provider.capitalize()} search successful, returning {len(formatted_results)} results.")

            # --- Send Feedback: Search Complete ---
            if update_callback:
                feedback_payload = {
                    "type": "web_search_complete", # Specific type for UI handling
                    "provider": self.provider,
                    "query": query,
                    "num_results": len(formatted_results)
                }
                try:
                    formatted_message = {"type": "agent_feedback", "payload": feedback_payload}
                    update_callback(log_queue, formatted_message)
                    logger.debug(f"Sent web_search_complete feedback payload for query '{query}' via {self.provider}")
                except Exception as cb_e:
                    logger.error(f"Failed to send web_search_complete feedback payload via callback: {cb_e}", exc_info=False)

            return {"results": formatted_results}

        except Exception as e:
            # Handle specific authentication errors more gracefully
            user_friendly_error = None
            
            # Check for authentication/authorization errors
            if "authentication" in str(e).lower() or "authorization" in str(e).lower() or "403" in str(e) or "401" in str(e):
                user_friendly_error = f"Web search failed due to invalid {self.provider.capitalize()} API key. Please check your API key in Settings > Search and ensure it's valid and has sufficient credits."
            elif "quota" in str(e).lower() or "limit" in str(e).lower():
                user_friendly_error = f"Web search quota exceeded for {self.provider.capitalize()}. Please check your account limits or try again later."
            elif "network" in str(e).lower() or "connection" in str(e).lower():
                user_friendly_error = f"Web search temporarily unavailable due to network issues. Please try again in a moment."
            else:
                user_friendly_error = f"Web search temporarily unavailable. Please try again or check your {self.provider.capitalize()} API key configuration in Settings."
            
            # Log the technical error for debugging
            logger.error(f"Web search error for query '{query}': {e}", exc_info=True)
            
            # Send user-friendly feedback
            if update_callback:
                feedback_payload = {
                    "type": "web_search_error",
                    "provider": self.provider,
                    "query": query,
                    "error": user_friendly_error
                }
                try:
                    formatted_message = {"type": "agent_feedback", "payload": feedback_payload}
                    update_callback(log_queue, formatted_message)
                    logger.debug(f"Sent web_search_error feedback payload for query '{query}'")
                except Exception as cb_e:
                     logger.error(f"Failed to send web_search_error feedback payload via callback: {cb_e}", exc_info=False)
            
            return {"error": user_friendly_error}
