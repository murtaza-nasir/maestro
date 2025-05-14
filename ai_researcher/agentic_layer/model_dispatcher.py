import openai # Keep for potential type hints if needed, but primary client is async
from openai import AsyncOpenAI # <-- Import AsyncOpenAI
from typing import List, Dict, Any, Optional, Tuple
import time
import logging
import asyncio
import random # <-- Import random for jitter
import httpx # <-- Import httpx again for pricing fetch
from decimal import Decimal, InvalidOperation # <-- Import Decimal for accurate cost calculation
from ai_researcher import config # Use absolute import

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelDispatcher:
    """
    Handles interactions with configured LLM APIs (OpenRouter and/or Local) asynchronously.
    Selects appropriate models and clients based on agent mode/request and manages API calls, using settings from config.py.
    Allows mixing providers for fast and mid tasks.
    """
    def __init__(self, semaphore: Optional[asyncio.Semaphore] = None): # <-- Add semaphore parameter
        self.max_retries = config.MAX_RETRIES
        self.retry_delay = config.RETRY_DELAY
        self.clients: Dict[str, Optional[AsyncOpenAI]] = {} # <-- Type hint for Async client
        self.semaphore = semaphore # <-- Store the semaphore
        # Removed self.http_client initialization - now creating per-request clients
        self.model_pricing_cache: Dict[str, Dict[str, Decimal]] = {} # <-- Cache for model pricing {model_id: {"prompt": Decimal, "completion": Decimal}}
        # REMOVED: self._pricing_cache_lock = asyncio.Lock()

        # Determine which providers are actually needed by checking all configured roles
        providers_in_use = set([
            config.FAST_LLM_PROVIDER,
            config.MID_LLM_PROVIDER,
            config.INTELLIGENT_LLM_PROVIDER,
            config.VERIFIER_LLM_PROVIDER # Added verifier provider
        ])
        logger.info(f"Dispatcher will attempt to initialize clients for providers: {providers_in_use}")

        for provider_name in providers_in_use:
            if provider_name not in config.PROVIDER_CONFIG:
                logger.error(f"Configuration for provider '{provider_name}' not found in config.PROVIDER_CONFIG.")
                continue

            provider_details = config.PROVIDER_CONFIG[provider_name]
            api_key = provider_details.get("api_key")
            base_url = provider_details.get("base_url")

            # Check for API key only if required (currently assume OpenRouter needs it)
            if provider_name == "openrouter" and not api_key:
                logger.error(f"Provider '{provider_name}' selected, but required API key (OPENROUTER_API_KEY) is not set. Client for this provider cannot be initialized.")
                self.clients[provider_name] = None
                continue

            if not base_url:
                 logger.error(f"Base URL for provider '{provider_name}' is not configured. Client cannot be initialized.")
                 self.clients[provider_name] = None
                 continue

            try:
                # Initialize the ASYNCHRONOUS client with a longer timeout
                client = AsyncOpenAI( # <-- Use AsyncOpenAI
                    base_url=base_url,
                    api_key=api_key,
                    timeout=config.LLM_REQUEST_TIMEOUT # <-- Use timeout from config
                )
                self.clients[provider_name] = client
                logger.info(f"AsyncOpenAI client initialized successfully for provider: {provider_name} ({base_url}) with timeout={config.LLM_REQUEST_TIMEOUT}s")
            except Exception as e:
                logger.error(f"Error initializing AsyncOpenAI client for provider {provider_name}: {e}", exc_info=True)
                self.clients[provider_name] = None

    def _select_model_and_client(self, requested_model: Optional[str] = None, agent_mode: Optional[str] = None) -> Tuple[Optional[openai.OpenAI], Optional[str], Optional[str]]:
        """
        Selects the appropriate async client, model name, and provider name based on request or agent mode.

        Returns:
            A tuple containing (AsyncOpenAI_client_instance, model_name, provider_name) or (None, None, None) if unavailable.
        """
        # <<< CHANGE DEBUG TO INFO >>>
        logger.info(f"[_select_model_and_client] Received: requested_model='{requested_model}', agent_mode='{agent_mode}'")
        # <<< END CHANGE >>>

        provider_name = None
        model_name = None
        model_type = None # 'fast', 'mid', 'intelligent', 'verifier'

        # Determine model type (fast/mid/intelligent/verifier) based on agent mode first
        effective_agent_mode = agent_mode or "default" # Use default if no mode specified
        model_type = config.AGENT_ROLE_MODEL_TYPE.get(effective_agent_mode, config.AGENT_ROLE_MODEL_TYPE["default"])

        # Determine the intended provider based on the model type
        if model_type == "fast":
            provider_name = config.FAST_LLM_PROVIDER
        elif model_type == "mid":
            provider_name = config.MID_LLM_PROVIDER
        elif model_type == "intelligent":
            provider_name = config.INTELLIGENT_LLM_PROVIDER
        elif model_type == "verifier":
            provider_name = config.VERIFIER_LLM_PROVIDER
        else:
            logger.error(f"Invalid model type '{model_type}' derived for agent mode '{effective_agent_mode}'.")
            return None, None, None

        # Now, determine the model name
        if requested_model:
            # If a specific model is requested, use it directly with the provider determined above.
            # Assume the requested model exists on the intended provider.
            logger.warning(f"Specific model '{requested_model}' requested. Using provider '{provider_name}' determined by agent mode '{effective_agent_mode}' (type: {model_type}).")
            model_name = requested_model
        else:
            # If no specific model requested, get the default model for the provider and type
            # Get the default model name from the provider's config based on the determined type
            provider_config = config.PROVIDER_CONFIG.get(provider_name, {})
            model_key = f"{model_type}_model" # e.g., "mid_model"
            if model_key not in provider_config:
                logger.error(f"Default model for type '{model_type}' ('{model_key}') not configured for provider '{provider_name}'.")
                return None, None, None
            model_name = provider_config[model_key]
            logger.info(f"Agent mode '{effective_agent_mode}' requires '{model_type}' model. Using provider '{provider_name}' with default model '{model_name}'.")

        # Get the client for the determined provider (provider_name was set based on model_type)
        client = self.clients.get(provider_name)
        if not client:
            logger.error(f"Async Client for provider '{provider_name}' is not available or not initialized.")
            return None, None, None

        # Ensure the return type matches the async client
        return client, model_name, provider_name

    async def _fetch_and_cache_pricing(self):
        """
        Fetches model pricing from OpenRouter /models endpoint and caches it.
        Uses a lock to prevent race conditions during cache updates.
        Creates a new HTTP client for each request to ensure proper cleanup.
        """
        # Check if OpenRouter is configured and has an API key
        openrouter_config = config.PROVIDER_CONFIG.get("openrouter", {})
        api_key = openrouter_config.get("api_key")
        base_url = openrouter_config.get("base_url", "https://openrouter.ai/api/v1")

        if not api_key:
            logger.warning("Cannot fetch OpenRouter pricing: OPENROUTER_API_KEY not found in config.")
            return

        models_url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        # Create a new HTTP client for this request with a timeout
        async with httpx.AsyncClient(timeout=config.LLM_REQUEST_TIMEOUT) as client:
            try:
                logger.info(f"Fetching model pricing from {models_url}...")
                response = await client.get(models_url, headers=headers)
                response.raise_for_status()
                models_data = response.json()

                if not isinstance(models_data, dict) or "data" not in models_data or not isinstance(models_data["data"], list):
                    logger.error(f"Unexpected format received from OpenRouter /models endpoint: {models_data}")
                    return

                new_cache: Dict[str, Dict[str, Decimal]] = {}
                for model_info in models_data["data"]:
                    model_id = model_info.get("id")
                    pricing = model_info.get("pricing")
                    if model_id and isinstance(pricing, dict):
                        try:
                            # Use Decimal for precision, default to 0 if price is missing/invalid
                            prompt_cost = Decimal(pricing.get("prompt", "0"))
                            completion_cost = Decimal(pricing.get("completion", "0"))
                            new_cache[model_id] = {
                                "prompt": prompt_cost,
                                "completion": completion_cost,
                            }
                        except (InvalidOperation, TypeError) as e:
                            logger.warning(f"Could not parse pricing for model '{model_id}': {pricing}. Error: {e}. Setting costs to 0.")
                            new_cache[model_id] = {"prompt": Decimal("0"), "completion": Decimal("0")} # Store default on error

                # Update the cache directly (removed lock)
                self.model_pricing_cache = new_cache
                logger.info(f"Successfully fetched and cached pricing for {len(self.model_pricing_cache)} models from OpenRouter.")

            except httpx.RequestError as e:
                logger.error(f"Error fetching OpenRouter model pricing (Request Error): {e}", exc_info=True)
            except httpx.HTTPStatusError as e:
                logger.error(f"Error fetching OpenRouter model pricing (HTTP Status {e.response.status_code}): {e.response.text}", exc_info=True)
            except Exception as e: # Catch broader exceptions like JSONDecodeError
                logger.error(f"Unexpected error fetching or processing OpenRouter model pricing: {e}", exc_info=True)

    async def _ensure_pricing_loaded(self):
        """Ensures the pricing cache is populated, fetching if necessary."""
        # Removed lock - potential for multiple fetches if called concurrently before cache is populated, but avoids deadlock.
        if not self.model_pricing_cache:
            logger.info("Pricing cache empty, attempting to fetch...") # Added log
            await self._fetch_and_cache_pricing()
        # else: # Optional: Log cache hit
            # logger.debug("Pricing cache already populated.")

    async def dispatch( # <-- Make method async
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None, # Specific model override
        agent_mode: Optional[str] = None, # e.g., 'planning', 'writing'
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        response_format: Optional[Dict[str, str]] = None,
        log_queue: Optional[Any] = None, # <-- Add log_queue parameter
        update_callback: Optional[Any] = None # <-- Add update_callback parameter (currently unused but added for consistency)
    ) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]: # Return type: (ChatCompletion, model_details_dict) or (None, None)
        """
        Selects the appropriate LLM client and model, sends the request with retry logic,
        logs details to the provided queue, and returns the response along with details.

        Args:
            messages: List of message dictionaries for the chat completion.
            model: Optional specific model name to override selection logic.
            agent_mode: Optional mode hint for model selection (e.g., 'planning').
            max_tokens: Maximum tokens for the response.
            temperature: Sampling temperature.
            tools: Optional list of tools for function calling.
            tool_choice: Optional tool choice constraint.
            response_format: Optional response format constraint (e.g., JSON).

        Returns:
            A tuple containing:
            - The API response object (e.g., ChatCompletion) or None if selection or all retries fail.
            - A dictionary with model call details (provider, model_name, duration_sec) or None on failure.
        """
        # Type hint for the async client
        client: Optional[AsyncOpenAI]
        client, selected_model_name, provider_name = self._select_model_and_client(requested_model=model, agent_mode=agent_mode)

        if not client or not selected_model_name or not provider_name:
            logger.error("Could not select a valid Async LLM client, model name, or provider. Cannot dispatch request.")
            return None, None

        # Determine max_tokens AND temperature based on agent_mode using the config
        effective_agent_mode = agent_mode or "default"
        max_tokens_for_call = config.AGENT_ROLE_MAX_TOKENS.get(effective_agent_mode, config.AGENT_ROLE_MAX_TOKENS["default"])
        # --- NEW: Get temperature from config ---
        temperature_for_call = config.AGENT_ROLE_TEMPERATURE.get(effective_agent_mode, config.AGENT_ROLE_TEMPERATURE["default"])
        # --- END NEW ---

        # --- UPDATED LOGGING ---
        logger.info(f"Dispatching request via client for '{client.base_url}' to model: {selected_model_name} (Agent Mode: {effective_agent_mode}, Max Tokens: {max_tokens_for_call}, Temp: {temperature_for_call})")
        # --- END UPDATED LOGGING ---


        request_params = {
            "model": selected_model_name,
            "messages": messages,
            "max_tokens": max_tokens_for_call, # Use the value determined from config
            "temperature": temperature_for_call, # <-- Use temperature from config
            # Add other potential parameters from config if needed later (e.g., top_p)
        }
        
        # Only add OpenAI headers if the provider is OpenRouter
        if provider_name == "openrouter":
            request_params["extra_headers"] = {
                "HTTP-Referer": "https://github.com/murtaza-nasir/maestro.git", 
                "X-Title": "MAESTRO", 
            }
        if tools:
            request_params["tools"] = tools
        if tool_choice:
            request_params["tool_choice"] = tool_choice
        if response_format:
            request_params["response_format"] = response_format

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                # Use the selected ASYNC client instance and await the call
                response = await client.chat.completions.create(**request_params) # <-- Use await
                end_time = time.time()
                duration = end_time - start_time
                logger.info(f"Async LLM call successful using model '{selected_model_name}' in {duration:.2f}s (Attempt {attempt + 1}/{self.max_retries})")

                model_call_details = {
                    "provider": provider_name,
                    "model_name": selected_model_name,
                    "duration_sec": round(duration, 2),
                    # Initialize token fields - will be populated from response.usage
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "cost": None, # Initialize cost field
                }

                # --- NEW: Extract usage and calculate cost ---
                prompt_tokens = 0
                completion_tokens = 0
                if response and response.usage:
                    prompt_tokens = response.usage.prompt_tokens or 0
                    completion_tokens = response.usage.completion_tokens or 0
                    total_tokens = response.usage.total_tokens or 0
                    model_call_details["prompt_tokens"] = prompt_tokens
                    model_call_details["completion_tokens"] = completion_tokens
                    model_call_details["total_tokens"] = total_tokens
                    logger.info(f"Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

                    # Calculate cost if provider is OpenRouter and pricing is available
                    if provider_name == "openrouter":
                        await self._ensure_pricing_loaded() # Ensure pricing is loaded (lazy load)
                        model_pricing = self.model_pricing_cache.get(selected_model_name)
                        if model_pricing:
                            prompt_cost_per_token = model_pricing.get("prompt", Decimal("0"))
                            completion_cost_per_token = model_pricing.get("completion", Decimal("0"))
                            total_cost = (Decimal(prompt_tokens) * prompt_cost_per_token) + (Decimal(completion_tokens) * completion_cost_per_token)
                            # Calculate cost only if tokens are non-zero to avoid potential issues
                            if prompt_tokens > 0 or completion_tokens > 0:
                                 total_cost = (Decimal(prompt_tokens) * prompt_cost_per_token) + (Decimal(completion_tokens) * completion_cost_per_token)
                            # Store cost as float in details
                            model_call_details["cost"] = float(total_cost)
                            # Log here, inside the openrouter check, as cost is specific to it
                            # logger.info(f"Calculated cost for {selected_model_name}: ${total_cost:.6f}") # MOVED logging below
                        else:
                            logger.warning(f"Pricing information not found in cache for model: {selected_model_name}. Cost cannot be calculated.")
                            model_call_details["cost"] = 0.0 # Set cost to 0 if pricing not found
                    else:
                         logger.info(f"Cost calculation skipped: Provider '{provider_name}' is not OpenRouter. Setting cost to $0.00.")
                         model_call_details["cost"] = 0.0 # Set cost to 0 for non-OpenRouter

                    # --- MOVE LOGGING HERE ---
                    # Log the calculated cost (even if 0) AFTER it's determined for ANY provider
                    # Ensure model_call_details["cost"] exists before logging
                    final_cost_float = model_call_details.get("cost", 0.0)
                    logger.info(f"Calculated cost for {selected_model_name}: ${final_cost_float:.6f}")
                    # --- END MOVED LOGGING ---

                else:
                    logger.warning("Usage information not found in the response object. Cost cannot be calculated.")
                    # Ensure cost is set to 0 if usage is missing
                    model_call_details["cost"] = 0.0
                    # Log cost as 0.000000 when usage is missing
                    logger.info(f"Calculated cost for {selected_model_name}: $0.000000")
                # --- END NEW ---

                # More robust check for valid response structure
                if response and response.choices and response.choices[0].message: # Check message exists, content check below
                     # Check if content is non-empty string OR if there are tool calls
                     has_content = isinstance(response.choices[0].message.content, str) and response.choices[0].message.content.strip()
                     has_tool_calls = bool(response.choices[0].message.tool_calls)

                     if has_content or has_tool_calls:
                          # --- NEW: Log details to queue and call update_callback if provided ---
                          if log_queue:
                              try:
                                  # Create a message with model call details
                                  model_details_message = {"type": "model_call_details", "data": model_call_details.copy()}
                                  
                                  # If update_callback is provided, use it to send the message
                                  if update_callback:
                                      try:
                                          # Call update_callback with log_queue and the message
                                          update_callback(log_queue, model_details_message)
                                          logger.debug(f"Called update_callback with model_call_details for model {selected_model_name}")
                                      except Exception as cb_err:
                                          logger.error(f"Failed to call update_callback with model details: {cb_err}")
                                          # Fall back to direct queue.put_nowait if callback fails
                                          log_queue.put_nowait(model_details_message)
                                  else:
                                      # No callback, put directly on queue
                                      log_queue.put_nowait(model_details_message)
                              except Exception as q_err:
                                  logger.error(f"Failed to log model details: {q_err}")
                          # --- END NEW ---
                          return response, model_call_details
                     else:
                          # Log the problematic content before warning (if it exists)
                          problematic_content = response.choices[0].message.content
                          logger.warning(f"LLM response content is empty or not a string, and no tool calls present (Attempt {attempt + 1}). Type: {type(problematic_content)}, Content: {problematic_content}")
                          # Treat as failure and retry - Calculate backoff below
                else:
                     # Log the full response object structure for debugging
                     try:
                          response_details = response.model_dump_json(indent=2) if response else "None" # Use Pydantic's dump for clarity
                     except Exception:
                          response_details = str(response) # Fallback to string representation
                     logger.warning(f"LLM response structure invalid (missing choices/message) (Attempt {attempt + 1}). Response object details:\n{response_details}")
                     # Treat as a failure and retry if possible - Handled in exception block or below

            # Catch specific async-related errors
            except openai.RateLimitError as e:
                if attempt < self.max_retries - 1:
                    base_delay = self.retry_delay
                    backoff_delay = base_delay * (2 ** attempt)
                    jitter = random.uniform(0, backoff_delay * 0.1)
                    sleep_duration = backoff_delay + jitter
                    logger.warning(f"Rate limit error (Attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {sleep_duration:.2f}s...")
                    await asyncio.sleep(sleep_duration)
                else:
                    logger.error(f"LLM call failed after {self.max_retries} attempts due to RateLimitError: {e}")
                    return None, None # Failed after all retries
            except openai.APIConnectionError as e:
                if attempt < self.max_retries - 1:
                    base_delay = self.retry_delay
                    backoff_delay = base_delay * (2 ** attempt)
                    jitter = random.uniform(0, backoff_delay * 0.1)
                    sleep_duration = backoff_delay + jitter
                    logger.warning(f"API connection error (Attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {sleep_duration:.2f}s...")
                    await asyncio.sleep(sleep_duration)
                else:
                     logger.error(f"LLM call failed after {self.max_retries} attempts due to APIConnectionError: {e}")
                     return None, None # Failed after all retries
            except openai.APIStatusError as e:
                 logger.error(f"API status error (Attempt {attempt + 1}/{self.max_retries}): Status={e.status_code}, Response={e.response}. No retry for status errors.", exc_info=True)
                 return None, None # Don't retry on definitive API status errors (like 4xx)
            except Exception as e:
                # Handle unexpected errors
                if attempt < self.max_retries - 1:
                    base_delay = self.retry_delay
                    backoff_delay = base_delay * (2 ** attempt)
                    jitter = random.uniform(0, backoff_delay * 0.1)
                    sleep_duration = backoff_delay + jitter
                    logger.error(f"Unexpected error during LLM call (Attempt {attempt + 1}/{self.max_retries}): {e}. Retrying in {sleep_duration:.2f}s...", exc_info=True)
                    await asyncio.sleep(sleep_duration)
                else:
                    logger.error(f"LLM call failed after {self.max_retries} attempts due to an unexpected error: {e}", exc_info=True)
                    return None, None # Failed after all retries

            # Handle retry for invalid/empty response outside of exception block
            # Check if we are here *after* a successful API call but with invalid content
            # and if we still have retries left
            if attempt < self.max_retries - 1:
                 # Check if 'response' exists and indicates an invalid/empty content issue
                 is_invalid_response = 'response' in locals() and (
                     not response or not response.choices or not response.choices[0].message or
                     (not (isinstance(response.choices[0].message.content, str) and response.choices[0].message.content.strip()) and not bool(response.choices[0].message.tool_calls))
                 )
                 if is_invalid_response:
                     base_delay = self.retry_delay
                     backoff_delay = base_delay * (2 ** attempt)
                     jitter = random.uniform(0, backoff_delay * 0.1)
                     sleep_duration = backoff_delay + jitter
                     logger.warning(f"Invalid or empty response detected (Attempt {attempt + 1}/{self.max_retries}). Retrying in {sleep_duration:.2f}s...")
                     await asyncio.sleep(sleep_duration)
                     # Continue to the next iteration of the loop
                     continue

            # If we reach here after the last attempt without returning successfully, it's a final failure.
            if attempt == self.max_retries - 1:
                 # Check if the failure was due to invalid/empty response on the last try
                 is_invalid_response_final = 'response' in locals() and (
                     not response or not response.choices or not response.choices[0].message or
                     (not (isinstance(response.choices[0].message.content, str) and response.choices[0].message.content.strip()) and not bool(response.choices[0].message.tool_calls))
                 )
                 if is_invalid_response_final:
                      logger.error(f"LLM call failed after {self.max_retries} attempts due to invalid or empty response on the final attempt.")
                 # Note: Specific exception errors on the last attempt are handled within their except blocks.
                 # This final return covers the case where the loop finishes without success or specific error return.
                 return None, None

        # This part should ideally not be reached if logic above is correct, but serves as a fallback.
        logger.error("LLM call failed after all retries (reached end of dispatch function).")
        return None, None
