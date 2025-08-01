import logging
import requests
import fitz # PyMuPDF
import io
from newspaper import Article, ArticleException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Callable
import queue
import os
import hashlib
import datetime
import pathlib
import json
from ai_researcher import config # Import config to access cache settings
from ai_researcher.core_rag.metadata_extractor import MetadataExtractor # Import the extractor

logger = logging.getLogger(__name__)

# Define cache directory relative to this file or project root
# Assuming the script runs from the project root where ai_researcher dir exists
CACHE_DIR = pathlib.Path("ai_researcher/data/web_cache/")

# Define the input schema
class WebPageFetcherInput(BaseModel):
    url: str = Field(..., description="The URL of the web page to fetch and extract content from.")
    # Optional: Add timeout? User-agent?

class WebPageFetcherTool:
    """
    Tool for fetching the main content of a web page given its URL.
    Uses 'requests' for download, 'newspaper3k'/'PyMuPDF' for text extraction,
    and 'MetadataExtractor' for structured metadata. Caches results.
    """
    def __init__(self):
        self.name = "fetch_web_page_content"
        self.description = "Fetches web page content (HTML/PDF), extracts text, and attempts to extract structured metadata (title, authors, etc.). Uses a local cache."
        self.parameters_schema = WebPageFetcherInput
        # Instantiate the metadata extractor
        # Consider making API key/model configurable if needed outside default .env/config
        self.metadata_extractor = MetadataExtractor()
        logger.info("WebPageFetcherTool initialized with MetadataExtractor.")
        # Ensure cache directory exists
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache directory ensured at: {CACHE_DIR.resolve()}")
        except Exception as e:
            logger.error(f"Failed to create cache directory {CACHE_DIR}: {e}", exc_info=True)


    async def execute(
        self,
         url: str,
         update_callback: Optional[Callable] = None, # Added callback
         log_queue: Optional[queue.Queue] = None,     # Added queue
         mission_id: Optional[str] = None      # <-- Add mission_id
    ) -> Dict[str, Any]:
        """
        Executes the web page fetching and content extraction.

         Args:
             url: The URL of the web page.
             update_callback: Optional callback function for sending updates.
             log_queue: Optional queue for logging updates.
            mission_id: Optional ID of the current mission for context in callbacks.


        Returns:
            A dictionary containing the extracted text under the key 'text', 'title', and 'metadata' on success,
            or a dictionary with an 'error' key on failure.
        """
        logger.info(f"Executing WebPageFetcherTool for URL: {url}")

        # --- Cache Check ---
        cache_key = hashlib.sha256(url.encode()).hexdigest()
        cache_content_path = CACHE_DIR / f"{cache_key}.cache"
        cache_meta_path = CACHE_DIR / f"{cache_key}.meta.json"
        cache_hit = False
        extracted_text = None
        extracted_title = None
        extracted_metadata = None # Initialize metadata variable

        if cache_content_path.exists() and cache_meta_path.exists():
            try:
                mod_time_timestamp = os.path.getmtime(cache_content_path)
                mod_time = datetime.datetime.fromtimestamp(mod_time_timestamp, tz=datetime.timezone.utc) # Use timezone-aware datetime
                expiration_delta = datetime.timedelta(days=config.WEB_CACHE_EXPIRATION_DAYS)
                now = datetime.datetime.now(datetime.timezone.utc) # Use timezone-aware datetime

                if (now - mod_time) < expiration_delta:
                    logger.info(f"Cache hit for URL: {url} (Key: {cache_key})")
                    # Read metadata first
                    with open(cache_meta_path, 'r', encoding='utf-8') as f_meta:
                        metadata_cache = json.load(f_meta) # Rename to avoid conflict
                    content_type = metadata_cache.get('content_type', '').lower()
                    extracted_title = metadata_cache.get('title', url) # Use URL as fallback title from cache
                    extracted_metadata = metadata_cache.get('extracted_metadata') # Load cached metadata

                    # Read cached content
                    with open(cache_content_path, 'rb') as f_content:
                        cached_content_bytes = f_content.read()

                    # Process cached content based on stored content type
                    is_pdf = 'application/pdf' in content_type

                    if is_pdf:
                        logger.info(f"Processing cached PDF content for URL: {url}")
                        try:
                            doc = fitz.open(stream=cached_content_bytes, filetype="pdf")
                            extracted_pdf_text = ""
                            for page_num in range(len(doc)):
                                page = doc.load_page(page_num)
                                extracted_pdf_text += page.get_text("text") + "\n"
                            doc.close()
                            extracted_text = extracted_pdf_text.strip()
                            if not extracted_text:
                                logger.warning(f"PyMuPDF extracted no text from cached PDF: {url}")
                                # Fall through to re-fetch if cached extraction failed
                            else:
                                cache_hit = True
                                logger.info(f"Successfully extracted ~{len(extracted_text)} characters from cached PDF: {url}")
                        except Exception as pdf_err:
                            logger.error(f"Error processing cached PDF content from {url}: {pdf_err}. Will re-fetch.", exc_info=True)
                            # Invalidate cache by removing files if processing fails
                            cache_content_path.unlink(missing_ok=True)
                            cache_meta_path.unlink(missing_ok=True)

                    else: # Process as HTML
                        logger.info(f"Processing cached HTML content for URL: {url}")
                        try:
                            # Decode bytes using UTF-8 (common default, newspaper might handle others)
                            cached_html = cached_content_bytes.decode('utf-8', errors='replace')
                            article = Article(url)
                            article.set_html(cached_html)
                            article.parse()
                            extracted_text = article.text
                            # Use title from metadata, but newspaper might find a better one if metadata was just URL
                            if not extracted_title or extracted_title == url:
                                extracted_title = article.title if article.title else url

                            if not extracted_text:
                                logger.warning(f"Newspaper3k could not extract main text from cached HTML: {url}. Title: '{extracted_title}'")
                                # Fall through to re-fetch
                            else:
                                cache_hit = True
                                logger.info(f"Successfully extracted ~{len(extracted_text)} characters from cached HTML: {url}. Title: '{extracted_title}'")
                        except Exception as html_err: # Catch broader errors during cached processing
                            logger.error(f"Error processing cached HTML content from {url}: {html_err}. Will re-fetch.", exc_info=True)
                            # Invalidate cache
                            cache_content_path.unlink(missing_ok=True)
                            cache_meta_path.unlink(missing_ok=True)

                else:
                    logger.info(f"Cache expired for URL: {url} (Key: {cache_key}). Will re-fetch.")
                    # Optionally remove expired files here or let them be overwritten
                    cache_content_path.unlink(missing_ok=True)
                    cache_meta_path.unlink(missing_ok=True)

            except Exception as cache_err:
                logger.error(f"Error reading cache for URL {url} (Key: {cache_key}): {cache_err}. Will re-fetch.", exc_info=True)
                # Attempt to remove potentially corrupted cache files
                cache_content_path.unlink(missing_ok=True)
                cache_meta_path.unlink(missing_ok=True)
        else:
             logger.info(f"Cache miss for URL: {url} (Key: {cache_key}). Will fetch.")


        # --- If Cache Hit and Processed Successfully, Return ---
        if cache_hit and extracted_text is not None:
            logger.info(f"Returning cached content and metadata for {url}")
            # Return cached text, title, and metadata
            return {"text": extracted_text, "title": extracted_title, "metadata": extracted_metadata}


        # --- Cache Miss or Failure: Proceed with Live Fetch ---
        logger.info(f"Proceeding with live fetch for URL: {url}")
        # --- Send Feedback: Starting Fetch ---
        if update_callback and log_queue:
            feedback_payload = {"type": "web_fetch_start", "url": url}
            try:
                # Pass only the queue and the payload, matching the 2-arg wrapper
                update_callback(log_queue, feedback_payload)
                logger.debug(f"Sent web_fetch_start feedback payload for URL '{url}'")
            except Exception as cb_e:
                logger.error(f"Failed to send web_fetch_start feedback payload via callback: {cb_e}", exc_info=False)
        # --- End Feedback ---

        try:
            # Configure requests session with more browser-like headers
            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36', # Updated Chrome version
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br', # Allow compressed responses
                'DNT': '1', # Do Not Track
                'Upgrade-Insecure-Requests': '1'
            }
            session.headers.update(headers)

            # Download the content with a timeout, using the session headers
            response = session.get(url, timeout=30) # Increased timeout slightly for potential larger files
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # --- Content successfully downloaded, save to cache before processing ---
            downloaded_content_bytes = response.content
            content_type = response.headers.get('Content-Type', '').lower()
            is_pdf = 'application/pdf' in content_type or url.lower().endswith('.pdf')
            # Attempt to get a title early for metadata, default to URL
            preliminary_title = url
            if not is_pdf:
                try:
                    temp_article = Article(url)
                    temp_article.set_html(response.text) # Use decoded text for temp parse
                    temp_article.parse()
                    if temp_article.title:
                        preliminary_title = temp_article.title
                except Exception:
                    logger.debug(f"Preliminary title extraction failed for {url}, using URL.")


            try:
                # Save content
                with open(cache_content_path, 'wb') as f_content:
                    f_content.write(downloaded_content_bytes)
                # Save metadata
                metadata = {
                    'url': url,
                    'content_type': content_type,
                    'title': preliminary_title, # Store preliminary title
                    'fetch_time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                with open(cache_meta_path, 'w', encoding='utf-8') as f_meta:
                    # --- Metadata Extraction (Live Fetch) ---
                    extracted_metadata = None # Reset for live fetch
                    if extracted_text and self.metadata_extractor:
                        logger.info(f"Attempting metadata extraction for URL: {url}")
                        try:
                            # Use the first part of the text for extraction
                            text_sample = extracted_text[:self.metadata_extractor.max_text_sample]
                            extracted_metadata = self.metadata_extractor.extract(text_sample)
                            if extracted_metadata:
                                logger.info(f"Successfully extracted metadata for URL: {url}")
                                # Ensure the original URL is part of the metadata for linking
                                extracted_metadata['url'] = url
                                # Update title if metadata extractor found a better one
                                if extracted_metadata.get('title'):
                                     extracted_title = extracted_metadata['title']
                                     metadata['title'] = extracted_title # Update title in cache metadata too
                            else:
                                logger.warning(f"Metadata extraction returned None for URL: {url}")
                        except Exception as meta_err:
                            logger.error(f"Error during metadata extraction for {url}: {meta_err}", exc_info=True)
                    else:
                        logger.warning(f"Skipping metadata extraction for {url} (no text or extractor unavailable).")

                    # Add extracted metadata (or None) to the cache metadata dictionary
                    metadata['extracted_metadata'] = extracted_metadata

                    # Save metadata (now including extracted_metadata)
                    json.dump(metadata, f_meta, indent=4)

                logger.info(f"Saved content and metadata (including extracted) to cache for URL: {url} (Key: {cache_key})")
            except Exception as cache_write_err:
                logger.error(f"Failed to write to cache for URL {url} (Key: {cache_key}): {cache_write_err}", exc_info=True)
                # If caching fails, proceed without it, but log the error. Don't delete files yet.


            # --- Now process the *downloaded* content ---
            if is_pdf:
                logger.info(f"Processing downloaded PDF content for URL: {url}.")
                try:
                    # Use the bytes already read
                    doc = fitz.open(stream=downloaded_content_bytes, filetype="pdf")
                    extracted_pdf_text = ""
                    for page_num in range(len(doc)):
                        page = doc.load_page(page_num)
                        extracted_pdf_text += page.get_text("text") + "\n" # Add newline between pages
                    doc.close()

                    if not extracted_pdf_text.strip():
                         logger.warning(f"PyMuPDF extracted no text from PDF: {url}")
                         return {"error": f"Successfully downloaded PDF, but no text could be extracted: {url}"}

                    # Use the title saved in metadata (which defaults to URL if needed)
                    extracted_title = preliminary_title
                    extracted_text = extracted_pdf_text.strip()
                    logger.info(f"Successfully extracted ~{len(extracted_text)} characters of text from PDF: {url}")

                except Exception as pdf_err:
                    error_msg = f"Error processing PDF content from {url}: {pdf_err}"
                    logger.error(error_msg, exc_info=True)
                    return {"error": error_msg}
            else:
                # --- Process as HTML using newspaper3k ---
                logger.info(f"Processing downloaded non-PDF content for URL: {url} with newspaper3k.")
                try:
                    article = Article(url)
                    # Use response.text (already decoded by requests) from the live response
                    article.set_html(response.text)
                    article.parse()

                    extracted_text = article.text
                    # Use newspaper's title if better than preliminary, else keep preliminary
                    extracted_title = article.title if article.title else preliminary_title

                    if not extracted_text:
                        logger.warning(f"Newspaper3k could not extract main text from HTML: {url}. Title found: '{extracted_title}'")
                        return {"error": f"Could not extract main text content from HTML page, although title '{extracted_title}' was found."}

                    logger.info(f"Successfully extracted ~{len(extracted_text)} characters of text from HTML: {url}. Title: '{extracted_title}'")

                except ArticleException as article_err:
                    error_msg = f"Newspaper3k failed to process HTML URL {url}: {article_err}"
                    logger.error(error_msg, exc_info=True)
                    return {"error": error_msg}
                # --- End HTML processing ---

            # --- Metadata Extraction (Live Fetch - Placed after text extraction) ---
            # This block is moved up slightly to be before the cache write

            # --- Send Feedback: Fetch Complete (Common for both PDF and HTML) ---
            if extracted_text is None: extracted_text = ""
            if extracted_title is None: extracted_title = url

            if update_callback and log_queue:
                feedback_payload = {
                    "type": "web_fetch_complete",
                    "url": url,
                    "title": extracted_title, # Use potentially updated title
                    "content_length": len(extracted_text),
                    "metadata_extracted": extracted_metadata is not None # Indicate if metadata was found
                }
                try:
                    # Pass only the queue and the payload, matching the 2-arg wrapper
                    update_callback(log_queue, feedback_payload)
                    logger.debug(f"Sent web_fetch_complete feedback payload for URL '{url}'")
                except Exception as cb_e:
                    logger.error(f"Failed to send web_fetch_complete feedback payload via callback: {cb_e}", exc_info=False)
            # --- End Feedback ---

            # Return text, title, and the extracted metadata
            return {"text": extracted_text, "title": extracted_title, "metadata": extracted_metadata}

        except requests.exceptions.Timeout:
            error_msg = f"Timeout occurred while trying to fetch URL: {url}"
            logger.error(error_msg)
            return {"error": error_msg, "error_type": "timeout", "url": url}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                error_msg = f"Access denied (403 Forbidden) for URL: {url}. This website blocks automated access."
                logger.warning(error_msg)
                return {
                    "error": error_msg, 
                    "error_type": "access_denied", 
                    "status_code": 403,
                    "url": url,
                    "suggestion": "This website restricts automated access. Consider using alternative sources or manual research for this content."
                }
            elif e.response.status_code == 404:
                error_msg = f"Page not found (404) for URL: {url}"
                logger.warning(error_msg)
                return {"error": error_msg, "error_type": "not_found", "status_code": 404, "url": url}
            else:
                error_msg = f"HTTP error {e.response.status_code} occurred while fetching URL {url}: {e}"
                logger.error(error_msg)
                return {"error": error_msg, "error_type": "http_error", "status_code": e.response.status_code, "url": url}
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error occurred while fetching URL {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg, "error_type": "network_error", "url": url}
        except ArticleException as e:
            error_msg = f"Newspaper3k failed to process URL {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"An unexpected error occurred while processing URL {url}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}
