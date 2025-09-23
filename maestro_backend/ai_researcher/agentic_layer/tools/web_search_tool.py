import os
import logging
import queue
import aiohttp
import asyncio
import threading
import time
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

# Import dynamic config to access user-specific provider settings
from ai_researcher.dynamic_config import (
    get_web_search_provider, get_tavily_api_key, get_linkup_api_key, get_searxng_base_url, get_searxng_categories,
    get_jina_api_key, get_search_depth,
    get_jina_read_full_content, get_jina_fetch_favicons, get_jina_bypass_cache
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
    max_results: Optional[int] = Field(None, description="Maximum number of search results desired.") # Will use user settings if not specified
    from_date: Optional[str] = Field(None, description="Start date for filtering results (YYYY-MM-DD format)")
    to_date: Optional[str] = Field(None, description="End date for filtering results (YYYY-MM-DD format)")
    include_domains: Optional[List[str]] = Field(None, description="List of domains to specifically include")
    exclude_domains: Optional[List[str]] = Field(None, description="List of domains to specifically exclude")
    depth: Optional[str] = Field(None, description="Search depth: 'standard' or 'advanced' (affects API costs)")

class WebSearchTool:
    """
    Tool for performing web searches using the configured provider (Tavily or LinkUp).
    """
    # Class-level semaphore for rate limiting (max 2 concurrent requests)
    # Make it lazy to avoid event loop binding issues
    _rate_limit_semaphore = None
    _semaphore_lock = threading.Lock()
    # Add delay between requests to avoid rate limits
    _last_request_time = 0
    _min_request_interval = 1.0  # Minimum 1 second between requests
    
    @classmethod
    def _get_semaphore(cls):
        """Get or create the rate limit semaphore for the current event loop."""
        loop = asyncio.get_event_loop()
        with cls._semaphore_lock:
            # Create a new semaphore for this event loop if needed
            if cls._rate_limit_semaphore is None or cls._rate_limit_semaphore._loop != loop:
                cls._rate_limit_semaphore = asyncio.Semaphore(2)
            return cls._rate_limit_semaphore
    
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
            elif self.provider == "jina":
                if not requests:
                    raise ImportError("Jina provider selected, but 'requests' library not installed.")
                api_key = get_jina_api_key()
                if not api_key:
                    logger.warning("Jina API key not configured in user settings or environment variables.")
                    self.api_key_configured = False
                    return
                self.client = api_key  # Store the API key as the "client" for Jina
                self.api_key_configured = True
                logger.info("WebSearchTool initialized with Jina.")
            else:
                raise ValueError(f"Unsupported web search provider configured: {self.provider}")
        except Exception as e:
            logger.error(f"Failed to initialize WebSearchTool: {e}")
            self.api_key_configured = False

    async def execute(
        self,
        query: str,
        max_results: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        depth: Optional[str] = None,
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
            max_results: Maximum number of results desired (uses user settings if not specified).
            from_date: Optional start date for filtering results.
            to_date: Optional end date for filtering results.
            include_domains: Optional list of domains to include.
            exclude_domains: Optional list of domains to exclude.
            depth: Optional search depth ('standard' or 'advanced').
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
            elif self.provider == "jina":
                user_friendly_error = f"Web search is not available. Please configure your Jina API key in Settings > Search to enable web search functionality."
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

        # Rate limiting: acquire semaphore to limit concurrent requests
        async with self._get_semaphore():
            # Add delay between requests to avoid rate limits
            current_time = time.time()
            time_since_last = current_time - WebSearchTool._last_request_time
            if time_since_last < WebSearchTool._min_request_interval:
                await asyncio.sleep(WebSearchTool._min_request_interval - time_since_last)
            WebSearchTool._last_request_time = time.time()
        
            # The rest of the execute method continues inside the semaphore context
            return await self._execute_search(
                query, max_results, from_date, to_date, include_domains, 
                exclude_domains, depth, update_callback, log_queue, mission_id
            )
    
    async def _execute_search(
        self,
        query: str,
        max_results: Optional[int],
        from_date: Optional[str],
        to_date: Optional[str],
        include_domains: Optional[List[str]],
        exclude_domains: Optional[List[str]],
        depth: Optional[str],
        update_callback: Optional[Callable],
        log_queue: Optional[queue.Queue],
        mission_id: Optional[str]
    ) -> Dict[str, Any]:
        """Internal method that performs the actual search after rate limiting."""
        # max_results is now required - should be passed from research agent
        if max_results is None:
            logger.warning("max_results not provided to WebSearchTool, defaulting to 5")
            max_results = 5  # Fallback to a reasonable default
        
        # Validate max_results based on provider
        if self.provider == 'jina':
            max_results = max(1, min(10, max_results))  # Jina: 1-10
        else:
            max_results = max(1, min(20, max_results))  # Others: 1-20
        
        # Only get depth for providers that use it
        if self.provider in ['tavily', 'linkup']:
            if depth is None:
                depth = get_search_depth(mission_id)
            logger.info(f"Executing {self.provider.capitalize()} search for '{query}' with max_results={max_results}, depth={depth}")
        else:
            # For Jina and SearXNG, depth is not applicable
            logger.info(f"Executing {self.provider.capitalize()} search for '{query}' with max_results={max_results}")
        formatted_results = []
        error_msg = None

        # Only add academic suffix if it's not already in the query
        search_query = query
        if "academic" not in query.lower() and "paper" not in query.lower():
            search_query = query + " academic paper"

        try:
            if self.provider == "tavily":
                # Map depth values for Tavily
                tavily_depth = "basic" if depth == "standard" else "advanced"
                
                # Build Tavily search parameters
                search_params = {
                    "query": search_query,
                    "search_depth": tavily_depth,
                    "max_results": max_results
                }
                
                # Add optional date filters
                if from_date:
                    search_params["start_date"] = from_date
                if to_date:
                    search_params["end_date"] = to_date
                    
                # Add domain filters
                if include_domains:
                    search_params["include_domains"] = include_domains
                if exclude_domains:
                    search_params["exclude_domains"] = exclude_domains
                
                # Tavily client's search method (run in thread to avoid blocking)
                response = await asyncio.to_thread(self.client.search, **search_params)
                search_results = response.get('results', [])
                for result in search_results:
                    formatted_results.append({
                        "title": result.get('title', 'No Title'),
                        "snippet": result.get('content', 'No Snippet'), # Tavily uses 'content'
                        "url": result.get('url', '#')
                    })

            elif self.provider == "linkup":
                # Map depth values for LinkUp
                linkup_depth = "standard" if depth == "standard" else "deep"
                
                # Build LinkUp search parameters for Python client
                search_params = {
                    "query": search_query,  # Python client uses 'query'
                    "depth": linkup_depth,
                    "output_type": "searchResults",  # Python client uses underscore
                    "include_images": False
                }
                
                # Add optional date filters - need to convert string to date objects
                if from_date:
                    try:
                        from datetime import datetime as dt
                        search_params["from_date"] = dt.strptime(from_date, '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(f"Invalid from_date format: {from_date}")
                        
                if to_date:
                    try:
                        from datetime import datetime as dt
                        search_params["to_date"] = dt.strptime(to_date, '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(f"Invalid to_date format: {to_date}")
                    
                # Add domain filters (Python client uses underscore)
                if include_domains:
                    search_params["include_domains"] = include_domains
                if exclude_domains:
                    search_params["exclude_domains"] = exclude_domains
                
                # Linkup client's search method (run in thread to avoid blocking)
                response = await asyncio.to_thread(self.client.search, **search_params)

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
                categories = get_searxng_categories()
                params = {
                    'q': search_query,
                    'format': 'json',
                    'engines': 'google,bing,duckduckgo',  # Use multiple engines for better results
                    'categories': categories,
                    'safesearch': '1'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(search_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        response.raise_for_status()
                        search_data = await response.json()
                search_results = search_data.get('results', [])
                
                # Limit results and format them
                for result in search_results[:max_results]:
                    formatted_results.append({
                        "title": result.get('title', 'No Title'),
                        "snippet": result.get('content', 'No Snippet'),
                        "url": result.get('url', '#')
                    })

            elif self.provider == "jina":
                # Jina search using s.jina.ai API
                search_url = "https://s.jina.ai/"
                
                # Get Jina-specific settings
                read_full_content = get_jina_read_full_content(mission_id)
                fetch_favicons = get_jina_fetch_favicons(mission_id)
                bypass_cache = get_jina_bypass_cache(mission_id)
                
                headers = {
                    "Authorization": f"Bearer {self.client}",  # self.client stores the API key
                    "Accept": "application/json",
                    "X-Respond-With": "json"
                }
                
                # Build Jina search parameters
                params = {
                    "q": search_query
                }
                
                # Add optional parameters based on settings
                if read_full_content:
                    params["read_full_content"] = "true"
                if fetch_favicons:
                    params["fetch_favicons"] = "true"
                if bypass_cache:
                    params["bypass_cache"] = "true"
                
                # Add optional parameters if provided
                if from_date or to_date:
                    # Jina doesn't support date filtering directly, add to query
                    if from_date:
                        search_query += f" after:{from_date}"
                    if to_date:
                        search_query += f" before:{to_date}"
                    params["q"] = search_query
                
                if include_domains:
                    # Add site restrictions to query
                    site_query = " OR ".join([f"site:{domain}" for domain in include_domains])
                    params["q"] = f"{search_query} ({site_query})"
                
                if exclude_domains:
                    # Add exclusions to query
                    for domain in exclude_domains:
                        params["q"] = f"{params['q']} -site:{domain}"
                
                # Make the request
                async with aiohttp.ClientSession() as session:
                    async with session.get(search_url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        response.raise_for_status()
                        # Parse Jina response
                        search_results = await response.json()
                
                # Jina returns a dict with 'code', 'status', 'data', 'meta' fields
                if isinstance(search_results, dict):
                    # Check if results are in 'data' field (standard Jina format)
                    if 'data' in search_results:
                        results_list = search_results['data']
                        # Also check for API errors
                        if search_results.get('code') != 200:
                            logger.warning(f"Jina API returned non-200 code: {search_results.get('code')}, status: {search_results.get('status')}")
                    elif 'results' in search_results:
                        # Alternative format
                        results_list = search_results['results']
                    else:
                        # Unexpected format
                        logger.warning(f"Jina returned dict without 'data' or 'results' field: {search_results.keys()}")
                        results_list = []
                elif isinstance(search_results, list):
                    # Direct list format (less common)
                    results_list = search_results
                else:
                    logger.warning(f"Unexpected Jina response format: {type(search_results)}")
                    results_list = []
                
                # Process the results
                for i, result in enumerate(results_list[:max_results]):
                    if isinstance(result, dict):
                        # Each result has 'title', 'url', 'description', and optionally 'content' fields
                        formatted_results.append({
                            "title": result.get('title', 'No Title'),
                            "snippet": result.get('description') or result.get('content', 'No Snippet')[:500],  # Limit snippet length
                            "url": result.get('url', '#')
                        })
                
                if not formatted_results and not error_msg:
                    logger.info(f"Jina search returned no results for query: {search_query}")
                    # Don't set error_msg here, just return empty results

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
