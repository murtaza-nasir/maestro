import os
from typing import Dict, Any, Optional

from ai_researcher.user_context import get_user_settings

# --- Helper function to get mission-specific settings ---
def _get_mission_settings(mission_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not mission_id:
        return None
    try:
        # This is a bit of a hack to avoid circular imports with ContextManager
        # In a real app, you might use a global context manager instance or dependency injection
        from ai_researcher.agentic_layer.context_manager import get_global_context_manager
        context_mgr = get_global_context_manager()
        if context_mgr:
            mission_context = context_mgr.get_mission_context(mission_id)
            if mission_context and mission_context.metadata:
                return mission_context.metadata.get("mission_settings")
    except Exception:
        pass # Fail silently if context manager isn't available
    return None

# --- Generic Setting Getter ---
def get_setting_with_fallback(
    setting_key: str,
    default_value: Any,
    setting_type: type = str,
    mission_id: Optional[str] = None
) -> Any:
    # 1. Check for mission-specific override
    mission_settings = _get_mission_settings(mission_id)
    if mission_settings and setting_key in mission_settings:
        return mission_settings[setting_key]

    # 2. Check for user-level setting
    user_settings = get_user_settings()
    if user_settings:
        user_value = user_settings.get("research_parameters", {}).get(setting_key)
        if user_value is not None:
            return user_value

    # 3. Fallback to environment variable (via os.getenv) and then default
    env_value = os.getenv(setting_key.upper())
    if env_value is not None:
        try:
            if setting_type == bool:
                return env_value.lower() in ['true', '1', 'yes', 'on']
            return setting_type(env_value)
        except (ValueError, TypeError):
            return default_value
            
    return default_value

# --- Re-implemented Getter Functions ---
def get_initial_research_max_depth(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("initial_research_max_depth", 2, int, mission_id)

def get_initial_research_max_questions(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("initial_research_max_questions", 10, int, mission_id)

def get_structured_research_rounds(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("structured_research_rounds", 2, int, mission_id)

def get_writing_passes(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("writing_passes", 3, int, mission_id)

def get_initial_exploration_doc_results(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("initial_exploration_doc_results", 5, int, mission_id)

def get_initial_exploration_web_results(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("initial_exploration_web_results", 2, int, mission_id)

def get_main_research_doc_results(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("main_research_doc_results", 5, int, mission_id)

def get_main_research_web_results(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("main_research_web_results", 2, int, mission_id)

def get_thought_pad_context_limit(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("thought_pad_context_limit", 10, int, mission_id)

def get_max_notes_for_assignment_reranking(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("max_notes_for_assignment_reranking", 80, int, mission_id)

def get_max_concurrent_requests(mission_id: Optional[str] = None) -> int:
    return get_setting_with_fallback("max_concurrent_requests", 5, int, mission_id)

def get_skip_final_replanning(mission_id: Optional[str] = None) -> bool:
    return get_setting_with_fallback("skip_final_replanning", False, bool, mission_id)

# --- Search Provider Settings ---
def get_web_search_provider(mission_id: Optional[str] = None) -> str:
    """Get the web search provider from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        search_settings = user_settings.get("search", {})
        if search_settings and search_settings.get("provider"):
            return search_settings["provider"].lower()
    
    # Fallback to environment variable
    env_value = os.getenv("WEB_SEARCH_PROVIDER", "tavily")
    return env_value.lower()

def get_tavily_api_key(mission_id: Optional[str] = None) -> Optional[str]:
    """Get the Tavily API key from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        search_settings = user_settings.get("search", {})
        if search_settings and search_settings.get("tavily_api_key"):
            return search_settings["tavily_api_key"]
    
    # Fallback to environment variable
    return os.getenv("TAVILY_API_KEY")

def get_linkup_api_key(mission_id: Optional[str] = None) -> Optional[str]:
    """Get the LinkUp API key from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        search_settings = user_settings.get("search", {})
        if search_settings and search_settings.get("linkup_api_key"):
            return search_settings["linkup_api_key"]
    
    # Fallback to environment variable
    return os.getenv("LINKUP_API_KEY")

def get_searxng_base_url(mission_id: Optional[str] = None) -> Optional[str]:
    """Get the SearXNG base URL from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        search_settings = user_settings.get("search", {})
        if search_settings and search_settings.get("searxng_base_url"):
            return search_settings["searxng_base_url"]
    
    # Fallback to environment variable
    return os.getenv("SEARXNG_BASE_URL")

# --- AI Provider Settings ---
def get_ai_provider_config(provider_name: str, mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Get AI provider configuration from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        providers = ai_endpoints.get("providers", {})
        if provider_name in providers:
            provider_config = providers[provider_name]
            if provider_config.get("enabled", False):
                return {
                    "api_key": provider_config.get("api_key"),
                    "base_url": provider_config.get("base_url")
                }
    
    # Fallback to environment variables
    if provider_name == "openrouter":
        return {
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/")
        }
    elif provider_name == "local":
        return {
            "api_key": os.getenv("LOCAL_LLM_API_KEY", "none"),
            "base_url": os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:5000/v1/")
        }
    elif provider_name == "custom":
        # Custom provider configuration comes from user settings
        # This will be handled by the user settings above
        return {"api_key": None, "base_url": None}
    else:
        return {"api_key": None, "base_url": None}

def get_fast_llm_provider(mission_id: Optional[str] = None) -> str:
    """Get the fast LLM provider from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        models = ai_endpoints.get("models", {})
        if "fast" in models:
            # Extract provider from model endpoint
            fast_model = models["fast"]
            if fast_model.startswith("openrouter/"):
                return "openrouter"
            elif fast_model.startswith("local/"):
                return "local"
    
    return get_setting_with_fallback("FAST_LLM_PROVIDER", "openrouter", str, mission_id)

def get_mid_llm_provider(mission_id: Optional[str] = None) -> str:
    """Get the mid LLM provider from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        models = ai_endpoints.get("models", {})
        if "mid" in models:
            # Extract provider from model endpoint
            mid_model = models["mid"]
            if mid_model.startswith("openrouter/"):
                return "openrouter"
            elif mid_model.startswith("local/"):
                return "local"
    
    return get_setting_with_fallback("MID_LLM_PROVIDER", "openrouter", str, mission_id)

def get_intelligent_llm_provider(mission_id: Optional[str] = None) -> str:
    """Get the intelligent LLM provider from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        models = ai_endpoints.get("models", {})
        if "intelligent" in models:
            # Extract provider from model endpoint
            intelligent_model = models["intelligent"]
            if intelligent_model.startswith("openrouter/"):
                return "openrouter"
            elif intelligent_model.startswith("local/"):
                return "local"
    
    return get_setting_with_fallback("INTELLIGENT_LLM_PROVIDER", "openrouter", str, mission_id)

def get_verifier_llm_provider(mission_id: Optional[str] = None) -> str:
    """Get the verifier LLM provider from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        models = ai_endpoints.get("models", {})
        if "verifier" in models:
            # Extract provider from model endpoint
            verifier_model = models["verifier"]
            if verifier_model.startswith("openrouter/"):
                return "openrouter"
            elif verifier_model.startswith("local/"):
                return "local"
    
    return get_setting_with_fallback("VERIFIER_LLM_PROVIDER", "openrouter", str, mission_id)

# --- Model Name Functions ---
def get_fast_model_name(mission_id: Optional[str] = None) -> str:
    """Get the fast model name from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        
        # NEW: Check advanced_models structure first
        advanced_models = ai_endpoints.get("advanced_models", {})
        if "fast" in advanced_models and advanced_models["fast"].get("model_name"):
            model_name = advanced_models["fast"]["model_name"]
            print(f"[DEBUG] Using fast model from user settings: {model_name}")
            return model_name
        
        # OLD: Fallback to old models structure for backward compatibility
        models = ai_endpoints.get("models", {})
        if "fast" in models and models["fast"]:
            model_name = models["fast"]
            print(f"[DEBUG] Using fast model from old settings: {model_name}")
            return model_name
    
    # Fallback to environment variables
    provider = get_fast_llm_provider(mission_id)
    if provider == "local":
        model_name = os.getenv("LOCAL_LLM_FAST_MODEL")
    else:
        model_name = os.getenv("OPENROUTER_FAST_MODEL")
    
    if model_name:
        print(f"[DEBUG] Using fast model from environment: {model_name}")
        return model_name
    
    # No fallback - require user configuration
    print(f"[DEBUG] No fast model found in user settings or environment")
    raise ValueError(f"No fast model configured for provider '{provider}'. Please configure your AI model settings in the user interface.")

def get_mid_model_name(mission_id: Optional[str] = None) -> str:
    """Get the mid model name from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    print(f"[DEBUG] get_mid_model_name: user_settings available: {bool(user_settings)}")
    
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        print(f"[DEBUG] get_mid_model_name: ai_endpoints keys: {list(ai_endpoints.keys())}")
        
        # NEW: Check advanced_models structure first
        advanced_models = ai_endpoints.get("advanced_models", {})
        print(f"[DEBUG] get_mid_model_name: advanced_models keys: {list(advanced_models.keys())}")
        
        if "mid" in advanced_models:
            mid_config = advanced_models["mid"]
            print(f"[DEBUG] get_mid_model_name: mid config: {mid_config}")
            model_name = mid_config.get("model_name")
            if model_name:
                print(f"[DEBUG] Using mid model from user settings: {model_name}")
                return model_name
            else:
                print(f"[DEBUG] get_mid_model_name: mid config exists but no model_name")
        else:
            print(f"[DEBUG] get_mid_model_name: 'mid' not found in advanced_models")
        
        # OLD: Fallback to old models structure for backward compatibility
        models = ai_endpoints.get("models", {})
        print(f"[DEBUG] get_mid_model_name: models keys: {list(models.keys())}")
        
        if "mid" in models and models["mid"]:
            model_name = models["mid"]
            print(f"[DEBUG] Using mid model from old settings: {model_name}")
            return model_name
        else:
            print(f"[DEBUG] get_mid_model_name: 'mid' not found in models or is empty")
    else:
        print(f"[DEBUG] get_mid_model_name: No user settings available")
    
    # Fallback to environment variables
    provider = get_mid_llm_provider(mission_id)
    print(f"[DEBUG] get_mid_model_name: provider: {provider}")
    
    if provider == "local":
        model_name = os.getenv("LOCAL_LLM_MID_MODEL")
    else:
        model_name = os.getenv("OPENROUTER_MID_MODEL")
    
    print(f"[DEBUG] get_mid_model_name: environment model_name: {model_name}")
    
    if model_name:
        print(f"[DEBUG] Using mid model from environment: {model_name}")
        return model_name
    
    # No fallback - require user configuration
    print(f"[DEBUG] No mid model found in user settings or environment")
    raise ValueError(f"No mid model configured for provider '{provider}'. Please configure your AI model settings in the user interface.")

def get_intelligent_model_name(mission_id: Optional[str] = None) -> str:
    """Get the intelligent model name from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        
        # NEW: Check advanced_models structure first
        advanced_models = ai_endpoints.get("advanced_models", {})
        if "intelligent" in advanced_models and advanced_models["intelligent"].get("model_name"):
            model_name = advanced_models["intelligent"]["model_name"]
            print(f"[DEBUG] Using intelligent model from user settings: {model_name}")
            return model_name
        
        # OLD: Fallback to old models structure for backward compatibility
        models = ai_endpoints.get("models", {})
        if "intelligent" in models and models["intelligent"]:
            model_name = models["intelligent"]
            print(f"[DEBUG] Using intelligent model from old settings: {model_name}")
            return model_name
    
    # Fallback to environment variables (no hardcoded defaults)
    provider = get_intelligent_llm_provider(mission_id)
    if provider == "local":
        model_name = os.getenv("LOCAL_LLM_INTELLIGENT_MODEL")
    else:
        model_name = os.getenv("OPENROUTER_INTELLIGENT_MODEL")
    
    if not model_name:
        raise ValueError(f"No intelligent model configured for provider '{provider}'. Please configure your AI model settings in the user interface.")
    
    print(f"[DEBUG] Using intelligent model from environment: {model_name}")
    return model_name

def get_verifier_model_name(mission_id: Optional[str] = None) -> str:
    """Get the verifier model name from user settings or environment."""
    # Check user settings first
    user_settings = get_user_settings()
    if user_settings:
        ai_endpoints = user_settings.get("ai_endpoints", {})
        
        # NEW: Check advanced_models structure first
        advanced_models = ai_endpoints.get("advanced_models", {})
        if "verifier" in advanced_models and advanced_models["verifier"].get("model_name"):
            model_name = advanced_models["verifier"]["model_name"]
            print(f"[DEBUG] Using verifier model from user settings: {model_name}")
            return model_name
        
        # OLD: Fallback to old models structure for backward compatibility
        models = ai_endpoints.get("models", {})
        if "verifier" in models and models["verifier"]:
            model_name = models["verifier"]
            print(f"[DEBUG] Using verifier model from old settings: {model_name}")
            return model_name
    
    # Fallback to environment variables (no hardcoded defaults)
    provider = get_verifier_llm_provider(mission_id)
    if provider == "local":
        model_name = os.getenv("LOCAL_LLM_VERIFIER_MODEL")
    else:
        model_name = os.getenv("OPENROUTER_VERIFIER_MODEL")
    
    if not model_name:
        raise ValueError(f"No verifier model configured for provider '{provider}'. Please configure your AI model settings in the user interface.")
    
    print(f"[DEBUG] Using verifier model from environment: {model_name}")
    return model_name

def get_model_name(model_type: str, mission_id: Optional[str] = None) -> str:
    """Gets the appropriate model name based on user settings and provider configuration."""
    if model_type == "fast" or model_type == "light":  # Support both new and old names
        return get_fast_model_name(mission_id)
    elif model_type == "mid" or model_type == "heavy":  # Support both new and old names
        return get_mid_model_name(mission_id)
    elif model_type == "intelligent" or model_type == "beast":  # Support both new and old names
        return get_intelligent_model_name(mission_id)
    elif model_type == "verifier":
        return get_verifier_model_name(mission_id)
    else:
        # Fallback to mid model
        print(f"Warning: Unknown model type '{model_type}' requested. Falling back to mid model.")
        return get_mid_model_name(mission_id)
