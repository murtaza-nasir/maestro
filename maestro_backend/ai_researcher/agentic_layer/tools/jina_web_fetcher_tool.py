import logging
import aiohttp
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Callable
import queue
from ai_researcher.dynamic_config import (
    get_jina_api_key, get_jina_browser_engine, get_jina_content_format, get_jina_remove_images
)

logger = logging.getLogger(__name__)

# Define the input schema
class JinaWebFetcherInput(BaseModel):
    url: str = Field(..., description="The URL of the web page to fetch and extract content from.")

class JinaWebFetcherTool:
    """
    Tool for fetching web page content using Jina Reader API (r.jina.ai).
    Provides advanced options for browser rendering and content extraction.
    """
    def __init__(self):
        self.name = "jina_fetch_web_page"
        self.description = "Fetches web page content using Jina Reader API with advanced browser rendering options."
        self.parameters_schema = JinaWebFetcherInput
        
        # Check if Jina API key is configured
        self.api_key = get_jina_api_key()
        self.api_key_configured = bool(self.api_key)
        
        if self.api_key_configured:
            logger.info("JinaWebFetcherTool initialized with API key.")
        else:
            logger.warning("JinaWebFetcherTool initialized without API key. Will work with rate limits.")

    async def execute(
        self,
        url: str,
        update_callback: Optional[Callable] = None,
        log_queue: Optional[queue.Queue] = None,
        mission_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes web page fetching using Jina Reader API.

        Args:
            url: The URL of the web page.
            update_callback: Optional callback function for sending updates.
            log_queue: Optional queue for logging updates.
            mission_id: Optional ID of the current mission for context.

        Returns:
            A dictionary containing the extracted text, title, and metadata on success,
            or a dictionary with an 'error' key on failure.
        """
        logger.info(f"Executing JinaWebFetcherTool for URL: {url}")

        # Send feedback: Starting fetch
        if update_callback and log_queue:
            feedback_payload = {"type": "web_fetch_start", "url": url, "provider": "jina"}
            try:
                update_callback(log_queue, feedback_payload)
                logger.debug(f"Sent jina_web_fetch_start feedback payload for URL '{url}'")
            except Exception as cb_e:
                logger.error(f"Failed to send web_fetch_start feedback: {cb_e}", exc_info=False)

        try:
            # Build Jina Reader URL
            jina_url = f"https://r.jina.ai/{url}"
            
            # Prepare headers
            headers = {
                "Accept": "text/plain"  # Get markdown format by default
            }
            
            # Add API key if available
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Get configuration from settings
            browser_engine = get_jina_browser_engine(mission_id)
            content_format = get_jina_content_format(mission_id)
            remove_images = get_jina_remove_images(mission_id)
            
            # Add optional headers based on configuration
            if browser_engine != "default":
                headers["X-Browser-Engine"] = browser_engine
            
            if content_format == "json":
                headers["Accept"] = "application/json"
                headers["X-Respond-With"] = "json"
            
            # Remove images from response if configured (default is True)
            if remove_images:
                headers["X-Remove-Images"] = "true"
            
            # Make the request with longer timeout (60 seconds for slow sites)
            async with aiohttp.ClientSession() as session:
                async with session.get(jina_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    response.raise_for_status()
                    response_text = await response.text()
                    response_headers = response.headers
            
            # Parse response based on format
            if content_format == "json" and response_headers.get('content-type', '').startswith('application/json'):
                # JSON response format
                import json
                result = json.loads(response_text)
                
                # Jina Reader also returns a dict with 'code', 'status', 'data', 'meta' fields
                if isinstance(result, dict) and 'data' in result:
                    # Standard Jina format
                    data = result['data']
                    if isinstance(data, dict):
                        extracted_text = data.get('content', '')
                        extracted_title = data.get('title', url)
                        extracted_metadata = {
                            'url': data.get('url', url),
                            'timestamp': data.get('timestamp'),
                            'source': 'jina_reader'
                        }
                    else:
                        # Data might be the content directly
                        extracted_text = str(data)
                        extracted_title = url
                        extracted_metadata = {'url': url, 'source': 'jina_reader'}
                else:
                    # Direct format (older API or different endpoint)
                    extracted_text = result.get('content', '')
                    extracted_title = result.get('title', url)
                    extracted_metadata = {
                        'url': result.get('url', url),
                        'timestamp': result.get('timestamp'),
                        'source': 'jina_reader'
                    }
            else:
                # Plain text/markdown response
                extracted_text = response_text
                # Try to extract title from markdown (first # heading)
                lines = extracted_text.split('\n')
                extracted_title = url
                for line in lines[:10]:  # Check first 10 lines
                    if line.startswith('# '):
                        extracted_title = line[2:].strip()
                        break
                extracted_metadata = {
                    'url': url,
                    'source': 'jina_reader'
                }
            
            if not extracted_text:
                logger.warning(f"Jina Reader returned empty content for URL: {url}")
                return {"error": f"No content could be extracted from: {url}"}
            
            logger.info(f"Successfully extracted ~{len(extracted_text)} characters from URL: {url}")
            
            # Send feedback: Fetch complete
            if update_callback and log_queue:
                feedback_payload = {
                    "type": "web_fetch_complete",
                    "url": url,
                    "title": extracted_title,
                    "content_length": len(extracted_text),
                    "provider": "jina",
                    "metadata_extracted": bool(extracted_metadata)
                }
                try:
                    update_callback(log_queue, feedback_payload)
                    logger.debug(f"Sent jina_web_fetch_complete feedback payload for URL '{url}'")
                except Exception as cb_e:
                    logger.error(f"Failed to send web_fetch_complete feedback: {cb_e}", exc_info=False)
            
            return {
                "text": extracted_text,
                "title": extracted_title,
                "metadata": extracted_metadata
            }
            
        except requests.exceptions.Timeout:
            error_msg = f"Timeout occurred while fetching URL via Jina: {url}"
            logger.error(error_msg)
            return {"error": error_msg, "error_type": "timeout", "url": url}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                if self.api_key:
                    error_msg = f"Access denied (403) for URL via Jina: {url}. API key may be invalid or rate limited."
                else:
                    error_msg = f"Access denied (403) for URL via Jina: {url}. Consider adding an API key for higher rate limits."
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "access_denied", "status_code": 403, "url": url}
            elif e.response.status_code == 404:
                error_msg = f"Page not found (404) for URL: {url}"
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "not_found", "status_code": 404, "url": url}
            elif e.response.status_code == 429:
                error_msg = f"Rate limit exceeded for Jina Reader. Please try again later or add an API key."
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "rate_limit", "status_code": 429, "url": url}
            else:
                error_msg = f"HTTP error {e.response.status_code} occurred while fetching URL via Jina {url}: {e}"
                logger.error(error_msg)
                return {"error": error_msg, "error_type": "http_error", "status_code": e.response.status_code, "url": url}
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error occurred while fetching URL via Jina {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg, "error_type": "network_error", "url": url}
        except Exception as e:
            error_msg = f"An unexpected error occurred while processing URL via Jina {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg, "url": url}