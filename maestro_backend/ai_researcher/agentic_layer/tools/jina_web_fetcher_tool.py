import logging
import aiohttp
import asyncio
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Callable
import queue
import hashlib
import datetime
import pathlib
import json
import os
from ai_researcher.dynamic_config import (
    get_jina_api_key, get_jina_browser_engine, get_jina_content_format, get_jina_remove_images
)

logger = logging.getLogger(__name__)

# Global semaphore to limit concurrent web fetches
# This prevents blocking the thread pool when multiple fetches happen
WEB_FETCH_SEMAPHORE = asyncio.Semaphore(3)  # Allow max 3 concurrent fetches

# Define cache directory for Jina fetcher (shared with native fetcher for consistency)
CACHE_DIR = pathlib.Path("ai_researcher/data/web_cache/")

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
        
        # Ensure cache directory exists
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache directory ensured at: {CACHE_DIR.resolve()}")
        except Exception as e:
            logger.error(f"Failed to create cache directory {CACHE_DIR}: {e}", exc_info=True)

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

        # --- Cache Check ---
        cache_key = hashlib.sha256(f"jina_{url}".encode()).hexdigest()  # Prefix with "jina_" to avoid conflicts
        cache_content_path = CACHE_DIR / f"{cache_key}.cache"
        cache_meta_path = CACHE_DIR / f"{cache_key}.meta.json"
        cache_hit = False

        # Check if cache exists and is valid (24 hour expiration)
        if cache_content_path.exists() and cache_meta_path.exists():
            try:
                with open(cache_meta_path, 'r', encoding='utf-8') as f:
                    cache_meta = json.load(f)
                
                cached_time = datetime.datetime.fromisoformat(cache_meta['timestamp'])
                cache_age = datetime.datetime.now() - cached_time
                
                # Use 24-hour cache expiration (same as native fetcher)
                if cache_age < datetime.timedelta(hours=24):
                    # Cache is valid, load content
                    with open(cache_content_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    logger.info(f"Cache hit for URL: {url} (age: {cache_age}, provider: jina)")
                    
                    # Send feedback for cache hit
                    if update_callback and log_queue:
                        feedback_payload = {
                            "type": "web_fetch_cache_hit", 
                            "url": url, 
                            "provider": "jina",
                            "cache_age_seconds": int(cache_age.total_seconds())
                        }
                        try:
                            update_callback(log_queue, feedback_payload)
                        except Exception as e:
                            logger.error(f"Failed to send cache hit feedback: {e}")
                    
                    return cache_data
                else:
                    logger.info(f"Cache expired for URL: {url} (age: {cache_age})")
            except Exception as e:
                logger.warning(f"Failed to load cache for URL {url}: {e}")

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
            # Use semaphore to limit concurrent fetches
            async with WEB_FETCH_SEMAPHORE:
                logger.debug(f"Acquired semaphore for Jina fetch of {url}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(jina_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                        response.raise_for_status()
                        response_text = await response.text()
                        response_headers = response.headers
                logger.debug(f"Released semaphore for Jina fetch of {url}")
            
            # Parse response based on format
            if content_format == "json" and response_headers.get('content-type', '').startswith('application/json'):
                # JSON response format
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
            
            # Prepare result
            result = {
                "text": extracted_text,
                "title": extracted_title,
                "metadata": extracted_metadata
            }
            
            # --- Save to Cache ---
            try:
                # Save content
                with open(cache_content_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                # Save metadata
                cache_metadata = {
                    "url": url,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "provider": "jina",
                    "browser_engine": browser_engine,
                    "content_format": content_format
                }
                with open(cache_meta_path, 'w', encoding='utf-8') as f:
                    json.dump(cache_metadata, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Cached Jina response for URL: {url}")
            except Exception as e:
                logger.warning(f"Failed to cache response for URL {url}: {e}")
            
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
            
            return result
            
        except aiohttp.ClientTimeout:
            error_msg = f"Timeout occurred while fetching URL via Jina: {url}"
            logger.error(error_msg)
            return {"error": error_msg, "error_type": "timeout", "url": url}
        except aiohttp.ClientResponseError as e:
            if e.status == 403:
                if self.api_key:
                    error_msg = f"Access denied (403) for URL via Jina: {url}. API key may be invalid or rate limited."
                else:
                    error_msg = f"Access denied (403) for URL via Jina: {url}. Consider adding an API key for higher rate limits."
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "access_denied", "status_code": 403, "url": url}
            elif e.status == 404:
                error_msg = f"Page not found (404) for URL: {url}"
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "not_found", "status_code": 404, "url": url}
            elif e.status == 429:
                error_msg = f"Rate limit exceeded for Jina Reader. Please try again later or add an API key."
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "rate_limit", "status_code": 429, "url": url}
            else:
                error_msg = f"HTTP error {e.status} occurred while fetching URL via Jina {url}: {e}"
                logger.error(error_msg)
                return {"error": error_msg, "error_type": "http_error", "status_code": e.status, "url": url}
        except aiohttp.ClientError as e:
            error_msg = f"Network error occurred while fetching URL via Jina {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg, "error_type": "network_error", "url": url}
        except Exception as e:
            error_msg = f"An unexpected error occurred while processing URL via Jina {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg, "url": url}