import openai # Keep for potential type hints if needed, but primary client is async
from openai import AsyncOpenAI # <-- Import AsyncOpenAI
from typing import List, Dict, Any, Optional, Tuple
import time
import logging
import asyncio
import random # <-- Import random for jitter
import httpx # <-- Import httpx again for pricing fetch
from decimal import Decimal, InvalidOperation # <-- Import Decimal for accurate cost calculation
import json
import os
from pathlib import Path
from ai_researcher import config # Use absolute import
from ai_researcher.dynamic_config import get_model_name
from ai_researcher.user_context import get_user_settings
from ai_researcher.global_semaphore import get_global_llm_semaphore

# Configure logging - respect LOG_LEVEL environment variable
logger = logging.getLogger(__name__)

class ModelDispatcher:
    """
    Handles interactions with configured LLM APIs (OpenRouter and/or Local) asynchronously.
    Selects appropriate models and clients based on agent mode/request and manages API calls.
    This version is initialized with user-specific settings to allow for per-user API keys.
    """
    def __init__(self, user_settings: Dict[str, Any], semaphore: Optional[asyncio.Semaphore] = None, context_manager=None):
        self.max_retries = config.MAX_RETRIES
        self.retry_delay = config.RETRY_DELAY
        self.clients: Dict[str, Optional[AsyncOpenAI]] = {}
        self.semaphore = semaphore
        self.context_manager = context_manager
        self.model_pricing_cache: Dict[str, Dict[str, Decimal]] = {}
        self.openai_pricing: Dict[str, Dict[str, Decimal]] = {}
        self.user_settings = user_settings
        
        # Load OpenAI pricing on initialization
        self._load_openai_pricing()

        # Determine the providers to initialize based on user settings and system config
        providers_in_use = self._get_providers_from_settings()
        logger.info(f"Dispatcher initializing for user with providers: {providers_in_use}")

        for provider_name in providers_in_use:
            # Get base config from config.py
            provider_details = config.PROVIDER_CONFIG.get(provider_name, {}).copy()
            logger.info(f"[DEBUG] Base config for {provider_name}: {provider_details}")
            
            # Override with user-specific settings
            user_provider_config = self._get_user_provider_config(provider_name)
            logger.info(f"[DEBUG] User config for {provider_name}: {user_provider_config}")
            if user_provider_config:
                provider_details.update(user_provider_config)

            api_key = provider_details.get("api_key")
            base_url = provider_details.get("base_url")
            
            # Log API key status (masked for security)
            api_key_status = "present" if api_key else "missing"
            if api_key:
                api_key_preview = f"{api_key[:8]}..." if len(api_key) > 8 else "short_key"
            else:
                api_key_preview = "None"
            logger.info(f"[DEBUG] Provider {provider_name}: API key {api_key_status} ({api_key_preview}), Base URL: {base_url}")

            # For custom providers, use a dummy API key if none provided
            # as the OpenAI client requires it even if the server doesn't
            if not api_key:
                if provider_name == "custom":
                    api_key = "dummy-key-for-local-llm"
                    logger.info(f"Using dummy API key for custom provider without authentication")
                else:
                    logger.debug(f"API key for provider '{provider_name}' not provided. Client will be initialized when user settings are available.")
                    self.clients[provider_name] = None
                    continue
            
            if not base_url:
                logger.error(f"Base URL for provider '{provider_name}' is not configured. Client cannot be initialized.")
                self.clients[provider_name] = None
                continue

            try:
                client = AsyncOpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    timeout=config.LLM_REQUEST_TIMEOUT
                )
                self.clients[provider_name] = client
                logger.info(f"AsyncOpenAI client initialized successfully for provider: {provider_name} at {base_url}")
            except Exception as e:
                logger.error(f"Error initializing AsyncOpenAI client for provider {provider_name}: {e}", exc_info=True)
                self.clients[provider_name] = None

    def _get_providers_from_settings(self) -> set:
        """Determines which providers to configure based on user and global settings."""
        providers = set()
        # Add providers from global config
        providers.add(config.FAST_LLM_PROVIDER)
        providers.add(config.MID_LLM_PROVIDER)
        providers.add(config.INTELLIGENT_LLM_PROVIDER)
        providers.add(config.VERIFIER_LLM_PROVIDER)

        # Add enabled providers from user settings
        if self.user_settings and "ai_endpoints" in self.user_settings:
            user_providers = self.user_settings["ai_endpoints"].get("providers", {})
            for provider_name, provider_config in user_providers.items():
                if provider_config.get("enabled", False):
                    providers.add(provider_name.lower())
            
            # Also add providers from advanced_models configuration
            advanced_models = self.user_settings["ai_endpoints"].get("advanced_models", {})
            for model_config in advanced_models.values():
                if model_config.get("provider"):
                    providers.add(model_config["provider"].lower())
        
        return providers

    def _get_user_provider_config(self, provider_name: str) -> Optional[Dict[str, str]]:
        """Extracts API key and base URL for a given provider from user settings."""
        if not self.user_settings or "ai_endpoints" not in self.user_settings:
            return None

        config_data = {}
        
        # First check enabled providers
        user_providers = self.user_settings["ai_endpoints"].get("providers", {})
        provider_config = user_providers.get(provider_name, {})
        
        if provider_config.get("enabled", False):
            if provider_config.get("api_key"):
                config_data["api_key"] = provider_config["api_key"]
            if provider_config.get("base_url"):
                config_data["base_url"] = provider_config["base_url"]
        
        # Also check advanced_models for this provider's credentials
        advanced_models = self.user_settings["ai_endpoints"].get("advanced_models", {})
        for model_config in advanced_models.values():
            if model_config.get("provider") == provider_name:
                # Use API key from advanced model if not already set
                if not config_data.get("api_key") and model_config.get("api_key"):
                    config_data["api_key"] = model_config["api_key"]
                # Use base URL from advanced model if not already set
                if not config_data.get("base_url") and model_config.get("base_url"):
                    config_data["base_url"] = model_config["base_url"]
                # If we have both, we can break early
                if config_data.get("api_key") and config_data.get("base_url"):
                    break
        
        return config_data if config_data else None

    async def cleanup(self):
        """Cleanup method to properly close all AsyncOpenAI clients."""
        for provider_name, client in self.clients.items():
            if client is not None:
                try:
                    # AsyncOpenAI clients have an httpx AsyncClient that needs to be closed
                    if hasattr(client, '_client'):
                        await client._client.aclose()
                    logger.debug(f"Closed AsyncOpenAI client for provider: {provider_name}")
                except Exception as e:
                    logger.warning(f"Error closing AsyncOpenAI client for provider {provider_name}: {e}")
        self.clients.clear()

    def _get_or_create_client(self, provider_name: str, current_user_settings: Optional[Dict[str, Any]]) -> Optional[AsyncOpenAI]:
        """
        Gets an existing client or creates a new one with fresh credentials if needed.
        This allows for dynamic credential updates without restarting the application.
        """
        # Get fresh provider config from current user settings
        fresh_provider_config = None
        if current_user_settings and "ai_endpoints" in current_user_settings:
            # Use a temporary instance method to get fresh config
            temp_user_settings = self.user_settings
            self.user_settings = current_user_settings
            fresh_provider_config = self._get_user_provider_config(provider_name)
            self.user_settings = temp_user_settings
        
        # Get base config from config.py
        provider_details = config.PROVIDER_CONFIG.get(provider_name, {}).copy()
        
        # Override with fresh user-specific settings
        if fresh_provider_config:
            provider_details.update(fresh_provider_config)
        
        api_key = provider_details.get("api_key")
        base_url = provider_details.get("base_url")
        
        logger.info(f"[DEBUG] _get_or_create_client for {provider_name}: API key {'present' if api_key else 'missing'}, Base URL: {base_url}")
        
        if not api_key or not base_url:
            logger.error(f"Missing credentials for provider '{provider_name}': API key {'missing' if not api_key else 'present'}, Base URL {'missing' if not base_url else 'present'}")
            return None
        
        # Check if we have an existing client and if its credentials match
        existing_client = self.clients.get(provider_name)
        if existing_client:
            # For now, always create a fresh client to ensure we use the latest credentials
            # In the future, we could compare credentials to avoid unnecessary recreation
            logger.info(f"[DEBUG] Creating fresh client for {provider_name} with updated credentials")
        
        try:
            client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=config.LLM_REQUEST_TIMEOUT
            )
            # Update the cached client
            self.clients[provider_name] = client
            logger.info(f"[DEBUG] Fresh AsyncOpenAI client created successfully for provider: {provider_name} at {base_url}")
            return client
        except Exception as e:
            logger.error(f"Error creating fresh AsyncOpenAI client for provider {provider_name}: {e}", exc_info=True)
            return None

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

        # NEW: Get FRESH user settings dynamically instead of using cached settings
        current_user_settings = get_user_settings()
        logger.info(f"[DEBUG] Fresh user settings retrieved: {bool(current_user_settings)}")
        
        if current_user_settings and "ai_endpoints" in current_user_settings:
            ai_endpoints = current_user_settings["ai_endpoints"]
            advanced_models = ai_endpoints.get("advanced_models", {})
            
            logger.info(f"[DEBUG] Available advanced_models: {list(advanced_models.keys())}")
            logger.info(f"[DEBUG] Looking for model_type: {model_type}")
            
            if model_type in advanced_models:
                model_config = advanced_models[model_type]
                provider_name = model_config.get("provider")
                model_name = model_config.get("model_name")
                
                # If provider or model name are still missing, log and attempt to recover from other dynamic config keys
                if not provider_name or not model_name:
                    logger.warning(f"[DEBUG] Incomplete config for '{model_type}' in advanced_models: {model_config}. Attempting dynamic_config.get_model_name as fallback.")
                    try:
                        model_name = get_model_name(model_type)
                        if not provider_name and model_name:
                            if model_name.startswith("local/"):
                                provider_name = "local"
                            else:
                                provider_name = "openrouter"
                        logger.info(f"[DEBUG] Fallback recovered values: provider='{provider_name}', model='{model_name}'")
                    except Exception as e:
                        logger.error(f"[DEBUG] dynamic_config.get_model_name failed for '{model_type}': {e}")
                
                # Override with requested_model if provided
                if requested_model:
                    logger.warning(f"Specific model '{requested_model}' requested, overriding user setting '{model_name}'.")
                    model_name = requested_model
            else:
                logger.warning(f"Model type '{model_type}' not found in user's advanced_models. Attempting dynamic_config.get_model_name as ultimate fallback.")
                try:
                    model_name = get_model_name(model_type)
                    if model_name.startswith('local/'):
                        provider_name = 'local'
                    else:
                        provider_name = 'openrouter'
                except Exception as e:
                    logger.error(f"[DEBUG] dynamic_config.get_model_name failed for '{model_type}': {e}")
        
        # Fallback to global config if still incomplete
        if not provider_name or not model_name:
            logger.error(f"Model configuration missing or incomplete for model type '{model_type}'.")
            raise ValueError(f"No valid model configured for '{model_type}'. User settings exist but values may be incomplete.")

        # Get the client for the determined provider, but check if we need fresh credentials
        client = self._get_or_create_client(provider_name, current_user_settings)
        if not client:
            logger.error(f"Async Client for provider '{provider_name}' is not available or could not be initialized.")
            return None, None, None

        # # Clean up model name based on provider
        # cleaned_model_name = self._clean_model_name(model_name, provider_name)
        # if cleaned_model_name != model_name:
        #     logger.info(f"[DEBUG] Cleaned model name for {provider_name}: '{model_name}' -> '{cleaned_model_name}'")

        # Ensure the return type matches the async client
        return client, model_name, provider_name

    def _load_openai_pricing(self):
        """
        Load OpenAI pricing from the JSON configuration file.
        Converts prices from per-million to per-token for consistent calculation.
        """
        try:
            # Get the path to the pricing file
            current_dir = Path(__file__).parent.parent  # Go up to ai_researcher directory
            pricing_file = current_dir / "openai_pricing.json"
            
            if not pricing_file.exists():
                logger.warning(f"OpenAI pricing file not found at {pricing_file}")
                return
            
            # Load the pricing data
            with open(pricing_file, 'r') as f:
                pricing_data = json.load(f)
            
            # Parse the pricing into our cache format
            models = pricing_data.get("models", {})
            per_tokens = pricing_data.get("per_tokens", 1000000)  # Default to per million
            
            for model_id, prices in models.items():
                # Convert from per-million to per-token pricing
                input_price = Decimal(str(prices.get("input", 0))) / Decimal(str(per_tokens))
                output_price = Decimal(str(prices.get("output", 0))) / Decimal(str(per_tokens))
                
                self.openai_pricing[model_id] = {
                    "prompt": input_price,
                    "completion": output_price
                }
            
            logger.info(f"Loaded OpenAI pricing for {len(self.openai_pricing)} models from {pricing_file}")
            
        except Exception as e:
            logger.error(f"Failed to load OpenAI pricing: {e}", exc_info=True)
            # Initialize with empty dict on failure
            self.openai_pricing = {}

    async def _fetch_and_cache_pricing(self):
        """
        Fetches model pricing from OpenRouter /models endpoint and caches it.
        Uses a lock to prevent race conditions during cache updates.
        Creates a new HTTP client for each request to ensure proper cleanup.
        """
        # Get fresh user settings to access OpenRouter API key
        current_user_settings = get_user_settings()
        
        # Try to get OpenRouter config from user settings first
        api_key = None
        base_url = "https://openrouter.ai/api/v1"
        
        if current_user_settings and "ai_endpoints" in current_user_settings:
            user_providers = current_user_settings["ai_endpoints"].get("providers", {})
            openrouter_config = user_providers.get("openrouter", {})
            
            if openrouter_config.get("enabled", False):
                api_key = openrouter_config.get("api_key")
                if openrouter_config.get("base_url"):
                    base_url = openrouter_config["base_url"]
        
        # Fallback to global config if not found in user settings
        if not api_key:
            openrouter_config = config.PROVIDER_CONFIG.get("openrouter", {})
            api_key = openrouter_config.get("api_key")
            if openrouter_config.get("base_url"):
                base_url = openrouter_config["base_url"]

        if not api_key:
            logger.warning("Cannot fetch OpenRouter pricing: OPENROUTER_API_KEY not found in user settings or global config.")
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
        update_callback: Optional[Any] = None, # <-- Add update_callback parameter (currently unused but added for consistency)
        mission_id: Optional[str] = None, # <-- Add mission_id parameter for status checking
        **kwargs: Any  # Accept additional keyword arguments (like agent_logged)
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
            mission_id: Optional mission ID for status checking.

        Returns:
            A tuple containing:
            - The API response object (e.g., ChatCompletion) or None if selection or all retries fail.
            - A dictionary with model call details (provider, model_name, duration_sec) or None on failure.
        """
        logger.info(f"DISPATCH_CALLED|agent_mode={agent_mode}|mission_id={mission_id}")
        
        # Log warning if cost tracking parameters are missing
        if not mission_id or not log_queue or not update_callback:
            logger.warning(
                f"dispatch called without complete cost tracking params - "
                f"agent_mode={agent_mode}, mission_id={bool(mission_id)}, "
                f"log_queue={bool(log_queue)}, update_callback={bool(update_callback)}. "
                f"Costs may not be properly tracked."
            )
        
        # Check mission status before proceeding with LLM call
        if self.context_manager and mission_id:
            try:
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.status in ["stopped", "paused"]:
                    logger.info(f"Mission {mission_id} is {mission_context.status}. Cancelling LLM call to prevent new tasks.")
                    return None, {"cancelled": True, "reason": f"Mission {mission_context.status}"}
            except Exception as status_check_error:
                logger.warning(f"Error checking mission status for {mission_id}: {status_check_error}. Proceeding with LLM call.")
        
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

        # --- CRITICAL DEBUG LOGGING ---
        # print(f"🚀🚀🚀 DISPATCHING LLM REQUEST 🚀🚀🚀")
        # print(f"   Provider: {provider_name}")
        # print(f"   Base URL: {client.base_url}")
        # print(f"   Model: {selected_model_name}")
        # print(f"   Agent Mode: {effective_agent_mode}")
        # print(f"   Max Tokens: {max_tokens_for_call}")
        # print(f"   Temperature: {temperature_for_call}")
        # logger.error(f"🚀🚀🚀 DISPATCHING LLM REQUEST: Provider={provider_name}, Model={selected_model_name}, URL={client.base_url}")
        # --- END CRITICAL DEBUG LOGGING ---


        # Check if this is a GPT-5 model that requires special handling
        is_gpt5_model = any(x in selected_model_name.lower() for x in ['gpt-5', 'gpt5'])
        
        # Get thinking_level from user settings if available
        thinking_level = None
        if is_gpt5_model and provider_name == "openai":
            # Try to get thinking level from user settings
            ai_endpoints = self.user_settings.get("ai_endpoints", {})
            advanced_models = ai_endpoints.get("advanced_models", {})
            for model_config in advanced_models.values():
                if model_config.get("model_name") == selected_model_name:
                    thinking_level = model_config.get("thinking_level", "low")
                    break
            if not thinking_level:
                thinking_level = "low"  # Default thinking level
        
        # Build request parameters based on model type
        if is_gpt5_model and provider_name == "openai":
            # GPT-5 models via OpenAI API require special parameters
            request_params = {
                "model": selected_model_name,
                "messages": messages,
                "max_completion_tokens": max_tokens_for_call,  # Use max_completion_tokens for GPT-5
                # Don't set temperature unless it's 1 (default) for GPT-5
            }
            # Only add temperature if it's 1
            if temperature_for_call == 1:
                request_params["temperature"] = 1
            
            # Add reasoning_effort for GPT-5 models
            if thinking_level:
                request_params["extra_body"] = {"reasoning_effort": thinking_level}
                logger.info(f"Using GPT-5 model {selected_model_name} with thinking_level: {thinking_level}")
        else:
            # Standard parameters for non-GPT-5 models or GPT-5 via OpenRouter
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


        # --- DEBUGGING ADDITION START ---
        try:
            logger.info("[DEBUG] Dispatch request parameters: "
                         f"Provider={provider_name}, "
                         f"BaseURL={getattr(client, 'base_url', None)}, "
                         f"Model={selected_model_name}, "
                         f"AgentMode={effective_agent_mode}, "
                         f"MaxTokens={max_tokens_for_call}, "
                         f"Temperature={temperature_for_call}, "
                         f"MessagesCount={len(messages)}, "
                         f"FirstMessagePreview={messages[0] if messages else None}")
        except Exception as dbg_e:
            logger.error(f"[DEBUG] Failed to log dispatch request params: {dbg_e}", exc_info=True)
        # --- DEBUGGING ADDITION END ---

        for attempt in range(self.max_retries):
            # Generate unique attempt ID for tracking
            import uuid
            attempt_id = str(uuid.uuid4())[:8]  # Short ID for logging
            
            try:
                start_time = time.time()
                
                # Log attempt start
                logger.info(
                    f"API_ATTEMPT_START|attempt_id={attempt_id}|attempt={attempt+1}/{self.max_retries}|"
                    f"model={selected_model_name}|mission_id={mission_id or 'NONE'}|"
                    f"agent_mode={effective_agent_mode}|timestamp={start_time}"
                )
                
                # Use the selected ASYNC client instance and await the call
                # Apply BOTH user semaphore AND global semaphore to limit concurrent requests
                # User semaphore limits per-user concurrency, global limits total server load
                global_semaphore = get_global_llm_semaphore()
                
                if self.semaphore and global_semaphore:
                    # Acquire both semaphores - user limit AND global limit
                    async with self.semaphore:
                        async with global_semaphore:
                            response = await client.chat.completions.create(**request_params)
                elif self.semaphore:
                    # Only user semaphore
                    async with self.semaphore:
                        response = await client.chat.completions.create(**request_params)
                elif global_semaphore:
                    # Only global semaphore
                    async with global_semaphore:
                        response = await client.chat.completions.create(**request_params)
                else:
                    # No semaphores
                    response = await client.chat.completions.create(**request_params)
                end_time = time.time()
                duration = end_time - start_time
                
                # Log successful API call
                logger.info(
                    f"API_ATTEMPT_END|attempt_id={attempt_id}|success=True|duration={duration:.2f}|"
                    f"timestamp={end_time}"
                )
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

                    # Calculate cost based on provider
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
                    elif provider_name == "openai":
                        # Use loaded OpenAI pricing from configuration file
                        model_pricing = self.openai_pricing.get(selected_model_name)
                        if model_pricing:
                            prompt_cost_per_token = model_pricing.get("prompt", Decimal("0"))
                            completion_cost_per_token = model_pricing.get("completion", Decimal("0"))
                            total_cost = (Decimal(prompt_tokens) * prompt_cost_per_token) + (Decimal(completion_tokens) * completion_cost_per_token)
                            model_call_details["cost"] = float(total_cost)
                            logger.info(f"Calculated OpenAI cost for {selected_model_name}: ${float(total_cost):.6f}")
                        else:
                            logger.warning(f"OpenAI pricing not found for model: {selected_model_name}. Cost set to $0.00. Please update openai_pricing.json")
                            model_call_details["cost"] = 0.0
                    else:
                         logger.info(f"Cost calculation skipped: Provider '{provider_name}' is not OpenRouter or OpenAI. Setting cost to $0.00.")
                         model_call_details["cost"] = 0.0 # Set cost to 0 for other providers

                    # --- COMPREHENSIVE COST TRACKING LOGS ---
                    # Log the calculated cost with detailed tracking info for analysis
                    final_cost_float = model_call_details.get("cost", 0.0)
                    logger.info(f"Calculated cost for {selected_model_name}: ${final_cost_float:.6f}")
                    
                    # Special formatted log for cost analysis
                    logger.info(
                        f"COST_TRACK|"
                        f"mission_id={mission_id or 'NONE'}|"
                        f"agent_mode={agent_mode or 'NONE'}|"
                        f"model={selected_model_name}|"
                        f"provider={provider_name}|"
                        f"prompt_tokens={prompt_tokens}|"
                        f"completion_tokens={completion_tokens}|"
                        f"cost=${final_cost_float:.6f}|"
                        f"has_log_queue={bool(log_queue)}|"
                        f"has_callback={bool(update_callback)}|"
                        f"timestamp={time.time()}"
                    )
                    # --- END COMPREHENSIVE COST TRACKING ---

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
                     
                     # Special handling for router/query_strategy mode - allow empty responses
                     # since the agent handles defaults for empty responses
                     is_router_mode = effective_agent_mode == "query_strategy"
                     
                     # For thinking models (like o1-mini), sometimes the response is empty due to 
                     # token consumption during reasoning. Allow empty responses for router.
                     has_valid_empty_response = (is_router_mode and 
                                                isinstance(response.choices[0].message.content, str))

                     if has_content or has_tool_calls or has_valid_empty_response:
                          # Log special case for router with empty response
                          if has_valid_empty_response and not has_content:
                              logger.info(f"Router/query_strategy mode returned empty response (likely thinking model). Accepting as valid.")
                          # --- NEW: Log details to queue and call update_callback if provided ---
                          cost_saved = False
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
                                          cost_saved = True
                                      except Exception as cb_err:
                                          logger.error(f"Failed to call update_callback with model details: {cb_err}")
                                          # Fall back to direct queue.put_nowait if callback fails
                                          log_queue.put_nowait(model_details_message)
                                  else:
                                      # No callback, put directly on queue
                                      log_queue.put_nowait(model_details_message)
                              except Exception as q_err:
                                  logger.error(f"Failed to log model details: {q_err}")
                          
                          # --- CRITICAL FIX: Call update_mission_stats for ALL LLM calls with costs ---
                          # This ensures QueryPreparer and other non-agent components get logged
                          # BUT avoid duplicate logging when agent already logs the call
                          if self.context_manager and mission_id and model_call_details:
                              # Check if agent is already handling the logging
                              agent_logged = kwargs.get('agent_logged', False)
                              
                              # Add agent_mode to model_call_details for NON_AGENT_LOG code
                              model_call_details_with_mode = model_call_details.copy()
                              model_call_details_with_mode["agent_mode"] = effective_agent_mode
                              
                              # If agent is logging, mark it in model_details to prevent NON_AGENT_LOG
                              if agent_logged:
                                  model_call_details_with_mode["agent_logged"] = True
                              
                              # Call update_mission_stats to trigger NON_AGENT_LOG code
                              logger.debug(f"ModelDispatcher calling update_mission_stats for {effective_agent_mode} with cost ${model_call_details.get('cost', 0):.6f} (agent_logged={agent_logged})")
                              
                              # Schedule the async update_mission_stats call
                              asyncio.create_task(self.context_manager.update_mission_stats(
                                  mission_id,
                                  model_call_details_with_mode,
                                  log_queue,
                                  update_callback
                              ))
                          
                          # Log whether cost was saved to database
                          logger.info(
                              f"COST_SAVE|mission_id={mission_id or 'NONE'}|"
                              f"cost_saved={cost_saved}|"
                              f"cost=${model_call_details.get('cost', 0.0):.6f}"
                          )
                          
                          # Track orphan costs (without mission_id) separately
                          if not mission_id and model_call_details.get('cost', 0) > 0:
                              logger.warning(
                                  f"ORPHAN_COST|agent_mode={effective_agent_mode}|"
                                  f"model={selected_model_name}|cost=${model_call_details.get('cost', 0):.6f}|"
                                  f"prompt_tokens={model_call_details.get('prompt_tokens', 0)}|"
                                  f"completion_tokens={model_call_details.get('completion_tokens', 0)}|"
                                  f"timestamp={time.time()}"
                              )
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
                # Log failed attempt
                logger.info(
                    f"API_ATTEMPT_END|attempt_id={attempt_id}|success=False|error=RateLimitError|"
                    f"timestamp={time.time()}"
                )
                
                # Track estimated cost for failed attempt (OpenRouter still charges for rate limited calls)
                # Estimate based on request size
                if provider_name == "openrouter":
                    estimated_prompt_tokens = sum(len(str(msg.get("content", ""))) for msg in messages) // 4
                    estimated_cost = estimated_prompt_tokens * 0.000001  # Rough estimate
                    logger.info(
                        f"COST_TRACK_FAILED|attempt_id={attempt_id}|mission_id={mission_id or 'NONE'}|"
                        f"agent_mode={effective_agent_mode}|model={selected_model_name}|"
                        f"estimated_cost=${estimated_cost:.6f}|error_type=RateLimitError"
                    )
                
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
                # Log failed attempt
                logger.info(
                    f"API_ATTEMPT_END|attempt_id={attempt_id}|success=False|error=APIConnectionError|"
                    f"timestamp={time.time()}"
                )
                
                # Track estimated cost for failed attempt
                if provider_name == "openrouter":
                    estimated_prompt_tokens = sum(len(str(msg.get("content", ""))) for msg in messages) // 4
                    estimated_cost = estimated_prompt_tokens * 0.000001  # Rough estimate
                    logger.info(
                        f"COST_TRACK_FAILED|attempt_id={attempt_id}|mission_id={mission_id or 'NONE'}|"
                        f"agent_mode={effective_agent_mode}|model={selected_model_name}|"
                        f"estimated_cost=${estimated_cost:.6f}|error_type=APIConnectionError"
                    )
                
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
                # Log failed attempt
                logger.info(
                    f"API_ATTEMPT_END|attempt_id={attempt_id}|success=False|error=APIStatusError_{e.status_code}|"
                    f"timestamp={time.time()}"
                )
                
                # Track actual cost if available in error response, or estimate
                if provider_name == "openrouter":
                    # Try to extract token usage from error response if available
                    estimated_prompt_tokens = sum(len(str(msg.get("content", ""))) for msg in messages) // 4
                    estimated_cost = estimated_prompt_tokens * 0.000001  # Rough estimate
                    logger.info(
                        f"COST_TRACK_FAILED|attempt_id={attempt_id}|mission_id={mission_id or 'NONE'}|"
                        f"agent_mode={effective_agent_mode}|model={selected_model_name}|"
                        f"estimated_cost=${estimated_cost:.6f}|error_type=APIStatusError_{e.status_code}"
                    )
                
                # Check for GPT-5 parameter errors and retry with correct parameters
                error_msg = str(e)
                if e.status_code == 400 and provider_name == "openai":
                    # Check for max_tokens vs max_completion_tokens error
                    if "max_tokens" in error_msg and "max_completion_tokens" in error_msg:
                        logger.info(f"Detected GPT-5 parameter error, retrying with max_completion_tokens...")
                        # Rebuild request params with max_completion_tokens
                        if "max_tokens" in request_params:
                            request_params["max_completion_tokens"] = request_params.pop("max_tokens")
                        # GPT-5 models don't support custom temperature
                        if "temperature" in request_params and request_params["temperature"] != 1:
                            request_params.pop("temperature")
                        # Add reasoning effort if not already present
                        if "extra_body" not in request_params:
                            request_params["extra_body"] = {"reasoning_effort": "low"}
                        
                        # Retry with corrected parameters
                        try:
                            if self.semaphore and global_semaphore:
                                async with self.semaphore:
                                    async with global_semaphore:
                                        response = await client.chat.completions.create(**request_params)
                            elif self.semaphore:
                                async with self.semaphore:
                                    response = await client.chat.completions.create(**request_params)
                            elif global_semaphore:
                                async with global_semaphore:
                                    response = await client.chat.completions.create(**request_params)
                            else:
                                response = await client.chat.completions.create(**request_params)
                            
                            logger.info(f"GPT-5 fallback successful with max_completion_tokens")
                            # Process the response as normal - jump to success handling
                            end_time = time.time()
                            duration = end_time - start_time
                            
                            # Continue with normal response processing (simplified here)
                            model_call_details = {
                                "provider": provider_name,
                                "model_name": selected_model_name,
                                "duration_sec": round(duration, 2),
                                "cost": 0.0  # GPT-5 via OpenAI, cost tracking TBD
                            }
                            
                            if response and response.choices and len(response.choices) > 0:
                                if response.usage:
                                    model_call_details["prompt_tokens"] = response.usage.prompt_tokens or 0
                                    model_call_details["completion_tokens"] = response.usage.completion_tokens or 0
                                    model_call_details["total_tokens"] = response.usage.total_tokens or 0
                                
                                return response, model_call_details
                                
                        except Exception as retry_error:
                            logger.error(f"GPT-5 fallback failed: {retry_error}")
                            # Continue with original error handling
                    
                    # Check for temperature not supported error
                    elif "temperature" in error_msg and "does not support" in error_msg:
                        logger.info(f"Detected GPT-5 temperature error, retrying without custom temperature...")
                        # Remove temperature or set to 1
                        if "temperature" in request_params:
                            request_params["temperature"] = 1
                        # Continue with retry logic below
                
                # Check if this is a schema-related error that might be fixed by fallback
                from ai_researcher.agentic_layer.utils.json_format_helper import should_retry_with_json_object
                
                if e.status_code == 400 and should_retry_with_json_object(e):
                    # This is likely a json_schema compatibility issue, re-raise so agent can handle fallback
                    logger.warning(f"API status error appears to be schema-related (Status=400): {str(e)[:200]}... Re-raising for potential fallback.")
                    raise e
                else:
                    logger.error(f"API status error (Attempt {attempt + 1}/{self.max_retries}): Status={e.status_code}, Response={e.response}. No retry for status errors.", exc_info=True)
                    # Re-raise the exception so the calling code can handle it with proper error details
                    raise e
            except Exception as e:
                # Log failed attempt
                logger.info(
                    f"API_ATTEMPT_END|attempt_id={attempt_id}|success=False|error={type(e).__name__}|"
                    f"timestamp={time.time()}"
                )
                
                # Track estimated cost for failed attempt
                if provider_name == "openrouter":
                    estimated_prompt_tokens = sum(len(str(msg.get("content", ""))) for msg in messages) // 4
                    estimated_cost = estimated_prompt_tokens * 0.000001  # Rough estimate
                    logger.info(
                        f"COST_TRACK_FAILED|attempt_id={attempt_id}|mission_id={mission_id or 'NONE'}|"
                        f"agent_mode={effective_agent_mode}|model={selected_model_name}|"
                        f"estimated_cost=${estimated_cost:.6f}|error_type={type(e).__name__}"
                    )
                
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

    async def dispatch_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        agent_mode: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        response_format: Optional[Dict[str, str]] = None,
        mission_id: Optional[str] = None
    ):
        """
        Streams the LLM response using the appropriate client and model.
        
        Args:
            messages: List of message dictionaries for the chat completion.
            model: Optional specific model name to override selection logic.
            agent_mode: Optional mode hint for model selection (e.g., 'writing').
            tools: Optional list of tools for function calling.
            tool_choice: Optional tool choice constraint.
            response_format: Optional response format constraint.
            mission_id: Optional mission ID for status checking.

        Yields:
            Streaming response chunks from the LLM.
        """
        # Check mission status before proceeding with LLM call
        if self.context_manager and mission_id:
            try:
                mission_context = self.context_manager.get_mission_context(mission_id)
                if mission_context and mission_context.status in ["stopped", "paused"]:
                    logger.info(f"Mission {mission_id} is {mission_context.status}. Cancelling streaming LLM call.")
                    return
            except Exception as status_check_error:
                logger.warning(f"Error checking mission status for {mission_id}: {status_check_error}. Proceeding with streaming LLM call.")
        
        # Type hint for the async client
        client: Optional[AsyncOpenAI]
        client, selected_model_name, provider_name = self._select_model_and_client(requested_model=model, agent_mode=agent_mode)

        if not client or not selected_model_name or not provider_name:
            logger.error("Could not select a valid Async LLM client, model name, or provider. Cannot dispatch streaming request.")
            return

        # Determine max_tokens AND temperature based on agent_mode using the config
        effective_agent_mode = agent_mode or "default"
        max_tokens_for_call = config.AGENT_ROLE_MAX_TOKENS.get(effective_agent_mode, config.AGENT_ROLE_MAX_TOKENS["default"])
        temperature_for_call = config.AGENT_ROLE_TEMPERATURE.get(effective_agent_mode, config.AGENT_ROLE_TEMPERATURE["default"])

        logger.info(f"Dispatching streaming request via client for '{client.base_url}' to model: {selected_model_name} (Agent Mode: {effective_agent_mode}, Max Tokens: {max_tokens_for_call}, Temp: {temperature_for_call})")

        request_params = {
            "model": selected_model_name,
            "messages": messages,
            "max_tokens": max_tokens_for_call,
            "temperature": temperature_for_call,
            "stream": True,  # Enable streaming
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

        try:
            start_time = time.time()
            # Use the selected ASYNC client instance and await the streaming call
            # For streaming, we acquire semaphores only for the initial request, not for the entire stream
            global_semaphore = get_global_llm_semaphore()
            
            if self.semaphore and global_semaphore:
                # Acquire both semaphores for initial connection only
                async with self.semaphore:
                    async with global_semaphore:
                        stream = await client.chat.completions.create(**request_params)
                logger.info(f"Started streaming LLM call using model '{selected_model_name}' (both semaphores released)")
            elif self.semaphore:
                async with self.semaphore:
                    stream = await client.chat.completions.create(**request_params)
                logger.info(f"Started streaming LLM call using model '{selected_model_name}' (user semaphore released)")
            elif global_semaphore:
                async with global_semaphore:
                    stream = await client.chat.completions.create(**request_params)
                logger.info(f"Started streaming LLM call using model '{selected_model_name}' (global semaphore released)")
            else:
                stream = await client.chat.completions.create(**request_params)
                logger.info(f"Started streaming LLM call using model '{selected_model_name}')")
            
            # Yield each chunk from the stream (semaphore already released)
            async for chunk in stream:
                yield chunk
                
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"Completed streaming LLM call using model '{selected_model_name}' in {duration:.2f}s")
            
        except openai.RateLimitError as e:
            logger.error(f"Rate limit error during streaming LLM call: {e}")
            raise e
        except openai.APIConnectionError as e:
            logger.error(f"API connection error during streaming LLM call: {e}")
            raise e
        except openai.APIStatusError as e:
            logger.error(f"API status error during streaming LLM call: Status={e.status_code}, Response={e.response}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during streaming LLM call: {e}", exc_info=True)
            raise e
