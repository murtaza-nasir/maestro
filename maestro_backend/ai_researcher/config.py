import datetime
import os
import sys
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Load environment variables from .env file
load_dotenv()

# --- Timezone Configuration ---
try:
    # Get the timezone name from the environment variable 'TZ'
    # Default to 'UTC' if the variable is not set.
    timezone_name = os.getenv("TZ", "UTC")
    # Create a ZoneInfo object from the timezone name.
    SERVER_TIMEZONE = ZoneInfo(timezone_name)
    print(f"✅ Timezone configured to: {timezone_name}")
except ZoneInfoNotFoundError:
    # If the provided timezone name is invalid, fall back to UTC and log a warning.
    print(f"⚠️ Invalid timezone '{timezone_name}' found in TZ environment variable. Defaulting to UTC.")
    SERVER_TIMEZONE = ZoneInfo("UTC")

def get_current_time() -> datetime:
    """Returns the current time in the server's timezone."""
    from datetime import datetime
    return datetime.now(SERVER_TIMEZONE)

# Import dynamic config for user settings override
try:
    from .dynamic_config import (
        get_setting_with_fallback, get_ai_provider_config, get_fast_llm_provider,
        get_mid_llm_provider, get_intelligent_llm_provider, get_verifier_llm_provider,
        get_web_search_provider, get_tavily_api_key, get_linkup_api_key,
        get_initial_research_max_depth, get_initial_research_max_questions,
        get_structured_research_rounds, get_writing_passes, get_thought_pad_context_limit,
        get_max_concurrent_requests, get_skip_final_replanning,
        get_initial_exploration_doc_results, get_initial_exploration_web_results,
        get_main_research_doc_results, get_main_research_web_results,
        get_max_notes_for_assignment_reranking, get_max_research_cycles_per_section,
        get_max_total_iterations, get_max_total_depth,
        get_min_notes_per_section_assignment, get_max_notes_per_section_assignment,
        get_max_planning_context_chars, get_writing_previous_content_preview_chars,
        get_research_note_content_limit
    )
    DYNAMIC_CONFIG_AVAILABLE = True
except ImportError:
    DYNAMIC_CONFIG_AVAILABLE = False
    def get_setting_with_fallback(setting_name: str, default_value: Any = None, setting_type: type = str) -> Any:
        env_value = os.getenv(setting_name)
        if env_value is not None:
            try:
                if setting_type == bool:
                    return env_value.lower() in ['true', '1', 'yes', 'on']
                elif setting_type == int:
                    return int(env_value)
                elif setting_type == float:
                    return float(env_value)
                else:
                    return env_value
            except (ValueError, TypeError):
                return default_value
        return default_value

    def get_ai_provider_config(provider_name: str) -> Dict[str, Any]:
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
            # This will be handled by the dynamic config system
            return {"api_key": None, "base_url": None}
        else:
            return {"api_key": None, "base_url": None}

    # Fallback functions for common settings
    def get_fast_llm_provider() -> str:
        return get_setting_with_fallback("FAST_LLM_PROVIDER", "openrouter")

    def get_mid_llm_provider() -> str:
        return get_setting_with_fallback("MID_LLM_PROVIDER", "openrouter")

    def get_intelligent_llm_provider() -> str:
        return get_setting_with_fallback("INTELLIGENT_LLM_PROVIDER", "openrouter")

    def get_verifier_llm_provider() -> str:
        return get_setting_with_fallback("VERIFIER_LLM_PROVIDER", "openrouter")

    def get_web_search_provider() -> str:
        return get_setting_with_fallback("WEB_SEARCH_PROVIDER", "tavily", str).lower()

    def get_tavily_api_key() -> Optional[str]:
        return get_setting_with_fallback("TAVILY_API_KEY", None)

    def get_linkup_api_key() -> Optional[str]:
        return get_setting_with_fallback("LINKUP_API_KEY", None)

    # Research parameters
    def get_initial_research_max_depth() -> int:
        return get_setting_with_fallback("INITIAL_RESEARCH_MAX_DEPTH", 2, int)

    def get_initial_research_max_questions() -> int:
        return get_setting_with_fallback("INITIAL_RESEARCH_MAX_QUESTIONS", 10, int)

    def get_structured_research_rounds() -> int:
        return get_setting_with_fallback("STRUCTURED_RESEARCH_ROUNDS", 2, int)

    def get_writing_passes() -> int:
        return get_setting_with_fallback("WRITING_PASSES", 3, int)

    def get_thought_pad_context_limit() -> int:
        return get_setting_with_fallback("THOUGHT_PAD_CONTEXT_LIMIT", 10, int)

    def get_max_concurrent_requests() -> int:
        return get_setting_with_fallback("MAX_CONCURRENT_REQUESTS", 5, int)

    def get_skip_final_replanning() -> bool:
        return get_setting_with_fallback("SKIP_FINAL_REPLANNING", False, bool)

    # Additional research parameters for mission settings
    def get_initial_exploration_doc_results() -> int:
        return get_setting_with_fallback("initial_exploration_doc_results", 5, int)

    def get_initial_exploration_web_results() -> int:
        return get_setting_with_fallback("initial_exploration_web_results", 2, int)

    def get_main_research_doc_results() -> int:
        return get_setting_with_fallback("main_research_doc_results", 5, int)

    def get_main_research_web_results() -> int:
        return get_setting_with_fallback("main_research_web_results", 5, int)

    def get_max_notes_for_assignment_reranking() -> int:
        return get_setting_with_fallback("max_notes_for_assignment_reranking", 80, int)

# --- Hardware Configuration ---
CUDA_DEVICE = os.getenv("CUDA_DEVICE", "0")  # Default to GPU 0 if not specified
FORCE_CPU_MODE = os.getenv("FORCE_CPU_MODE", "false").lower() == "true"  # Force CPU mode for all operations
PREFERRED_DEVICE_TYPE = os.getenv("PREFERRED_DEVICE_TYPE", "auto").lower()  # auto, cuda, rocm, mps, cpu

# Check if running in Docker
def is_running_in_docker():
    """Check if the application is running inside a Docker container."""
    # Check for .dockerenv file
    if os.path.exists('/.dockerenv'):
        return True
    
    # Check for cgroup
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass
    
    return False

# Hardware configuration for non-Docker environments
if not is_running_in_docker():
    # Only set CUDA_VISIBLE_DEVICES if not forcing CPU mode
    if not FORCE_CPU_MODE and PREFERRED_DEVICE_TYPE != "cpu":
        os.environ['CUDA_VISIBLE_DEVICES'] = CUDA_DEVICE
        print(f"Setting CUDA_VISIBLE_DEVICES to {CUDA_DEVICE}")
    elif FORCE_CPU_MODE:
        # Disable GPU visibility when forcing CPU mode
        os.environ['CUDA_VISIBLE_DEVICES'] = ""
        print("CPU mode forced - CUDA_VISIBLE_DEVICES disabled")
    
    # Print device preference
    if PREFERRED_DEVICE_TYPE != "auto":
        print(f"Preferred device type: {PREFERRED_DEVICE_TYPE}")
else:
    # In Docker, just print the current CUDA_VISIBLE_DEVICES value
    docker_cuda_devices = os.getenv("CUDA_VISIBLE_DEVICES", "Not set")
    if FORCE_CPU_MODE:
        print(f"Running in Docker with CPU mode forced")
    else:
        print(f"Running in Docker. CUDA_VISIBLE_DEVICES is {docker_cuda_devices} (managed by Docker)")

# --- LLM Provider Configuration ---
# Set the desired LLM provider for fast and mid models: "openrouter" or "local"
FAST_LLM_PROVIDER = get_fast_llm_provider() # Default fast to openrouter
MID_LLM_PROVIDER = get_mid_llm_provider() # Default mid to openrouter

# --- Local LLM Configuration ---
# Example: Using a local server like LM Studio, Ollama, etc.
# Ensure your local server provides an OpenAI-compatible API endpoint.
# For Docker, use host.docker.internal to connect to the host machine.
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://host.docker.internal:1234/v1")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "none") # Often 'none' or not required for local
# Define local model names (adjust if your local models have different identifiers)
# These might be the actual file names or identifiers used by your local server.
LOCAL_LLM_FAST_MODEL = os.getenv("LOCAL_LLM_FAST_MODEL")
LOCAL_LLM_MID_MODEL = os.getenv("LOCAL_LLM_MID_MODEL")
LOCAL_LLM_INTELLIGENT_MODEL = os.getenv("LOCAL_LLM_INTELLIGENT_MODEL")

# --- LLM Provider Configuration (Intelligent) ---
# Set the desired LLM provider for the intelligent model: "openrouter" or "local"
INTELLIGENT_LLM_PROVIDER = get_intelligent_llm_provider() # Default intelligent to openrouter

# --- LLM Provider Configuration (Verifier) ---
# Set the desired LLM provider for the verifier model: "openrouter" or "local"
VERIFIER_LLM_PROVIDER = get_verifier_llm_provider() # Default verifier to openrouter

# Mapping agent types/modes to the *type* of model needed (fast/mid/intelligent/verifier)
# The dispatcher will then resolve the actual name and provider
AGENT_ROLE_MODEL_TYPE = {
    "planning": "fast", 
    "research": "mid",
    "writing": "mid",
    "simplified_writing": "mid",  # Main writing agent uses medium model
    "reflection": "intelligent", 
    "messenger": "mid",
    "note_assignment": "fast", 
    "query_preparation": "intelligent", 
    "query_strategy": "fast",  # Router uses fast model
    "verifier": "verifier",
    "default": "mid" 
}

# --- OpenRouter Configuration ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# Define OpenRouter model names (can be overridden by environment variables)
OPENROUTER_FAST_MODEL = os.getenv("OPENROUTER_FAST_MODEL")
OPENROUTER_MID_MODEL = os.getenv("OPENROUTER_MID_MODEL")
OPENROUTER_INTELLIGENT_MODEL = os.getenv("OPENROUTER_INTELLIGENT_MODEL")
# --- Verifier Model Configuration ---
# Define the specific model used for verification tasks (e.g., in evaluation scripts)
# Note: VERIFIER_LLM_PROVIDER determines if OPENROUTER_ or LOCAL_ is used.
OPENROUTER_VERIFIER_MODEL = os.getenv("OPENROUTER_VERIFIER_MODEL")
LOCAL_LLM_VERIFIER_MODEL = os.getenv("LOCAL_LLM_VERIFIER_MODEL")

## models
# openai/gpt-4o-mini
# anthropic/claude-3-opus-20240229
# google/gemini-2.5-flash-preview
# deepseek/deepseek-chat-v3-0324
# openai/gpt-4.1-nano
# qwen/qwen-plus
# qwen/qwen-2.5-72b-instruct
# google/gemma-3-27b-it

# --- Agent-Specific Max Tokens Configuration ---
# Define the maximum number of tokens the LLM should generate in its response for each agent role.
# Adjust these values based on the expected output length and complexity for each agent's task.
# Use None for no specific limit (relying on the model's default or other constraints).
AGENT_ROLE_MAX_TOKENS = {
    "planning": int(os.getenv("PLANNING_MAX_TOKENS", 20000)),
    "research": int(os.getenv("RESEARCH_MAX_TOKENS", 4000)),
    "writing": int(os.getenv("WRITING_MAX_TOKENS", 8000)),
    "reflection": int(os.getenv("REFLECTION_MAX_TOKENS", 4000)),
    "messenger": int(os.getenv("MESSENGER_MAX_TOKENS", 2000)),
    "note_assignment": int(os.getenv("NOTE_ASSIGNMENT_MAX_TOKENS", 8192)), # Added role with higher limit
    "verifier": int(os.getenv("VERIFIER_MAX_TOKENS", 1000)), # Added verifier max tokens
    "query_strategy": int(os.getenv("QUERY_STRATEGY_MAX_TOKENS", 2000)), # Increased for thinking models that need reasoning tokens
    "default": int(os.getenv("DEFAULT_MAX_TOKENS", 2048)) # Default max tokens if role not specified
}

# # Temperature settings per agent role (Lower values = more focused, Higher = more creative)
AGENT_ROLE_TEMPERATURE = {
    "default": 0.5,
    "planning": 0.3,  # More deterministic for planning
    "research": 0.5,  # Balanced for note generation/synthesis
    "writing": 0.6,   # Slightly more creative for writing
    "reflection": 0.4, # Focused for analysis
    "writing_reflection": 0.4, # Focused for editing suggestions
    "note_assignment": 0.2, # Very focused for assignment logic
    "query_strategy": 0.1, # Very deterministic for simple routing decisions
    "messenger": 0.7, # More conversational for chat
    "query_preparation": 0.3, # Focused for query generation
    "verifier": 0.1 # Very focused for verification
}

# Temperature settings per agent role (Lower values = more focused, Higher = more creative)
# AGENT_ROLE_TEMPERATURE = {
#     "default": 0.1,
#     "planning": 0.1,  # More deterministic for planning
#     "research": 0.1,  # Balanced for note generation/synthesis
#     "writing": 0.1,   # Slightly more creative for writing
#     "reflection": 0.1, # Focused for analysis
#     "writing_reflection": 0.1, # Focused for editing suggestions
#     "note_assignment": 0.1, # Very focused for assignment logic
#     "messenger": 0.1, # More conversational for chat
#     "query_preparation": 0.1, # Focused for query generation
#     "query_strategy": 0.1 # Focused for strategy selection
# }

# --- Model Selection Logic ---
# Determine the actual model name based on the provider chosen for fast/mid/intelligent roles

def get_model_name(model_type: str) -> str:
    """Gets the appropriate model name based on provider settings."""
    if DYNAMIC_CONFIG_AVAILABLE:
        # Use dynamic config to get model names from user settings
        from .dynamic_config import get_model_name as dynamic_get_model_name
        return dynamic_get_model_name(model_type)
    else:
        # Fallback to static config
        if model_type == "fast" or model_type == "light":  # Support both new and old names
            provider = FAST_LLM_PROVIDER
            model_name = LOCAL_LLM_FAST_MODEL if provider == "local" else OPENROUTER_FAST_MODEL
        elif model_type == "mid" or model_type == "heavy":  # Support both new and old names
            provider = MID_LLM_PROVIDER
            model_name = LOCAL_LLM_MID_MODEL if provider == "local" else OPENROUTER_MID_MODEL
        elif model_type == "intelligent" or model_type == "beast":  # Support both new and old names
            provider = INTELLIGENT_LLM_PROVIDER
            model_name = LOCAL_LLM_INTELLIGENT_MODEL if provider == "local" else OPENROUTER_INTELLIGENT_MODEL
        elif model_type == "verifier": # Added verifier case
            provider = VERIFIER_LLM_PROVIDER
            model_name = LOCAL_LLM_VERIFIER_MODEL if provider == "local" else OPENROUTER_VERIFIER_MODEL
        else:
            raise ValueError(f"Unknown model type '{model_type}' requested. Please configure user AI settings.")
        
        if not model_name:
            raise ValueError(f"No {model_type} model configured for provider '{provider}'. Please set user AI settings or environment variables.")
        
        return model_name


# Model names are now loaded dynamically per user - no startup assignment
# Use get_model_name(model_type, mission_id) to get model names at runtime

# --- Other Configurations (Add as needed) ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 5)) # seconds
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 600.0)) # Timeout in seconds for LLM API calls
# Max concurrent requests for agent operations (0 for no limit)
MAX_CONCURRENT_REQUESTS = get_max_concurrent_requests()

# --- Web Search Configuration ---
# Choose the web search provider: "tavily" or "linkup"
WEB_SEARCH_PROVIDER = get_web_search_provider()
TAVILY_API_KEY = get_tavily_api_key()
LINKUP_API_KEY = get_linkup_api_key()
# Define the cost per web search call (adjust default as needed)
WEB_SEARCH_COST_PER_CALL = float(os.getenv("WEB_SEARCH_COST_PER_CALL", 0.005)) # Default $0.005 per search

# --- Web Fetcher Cache Configuration ---
WEB_CACHE_EXPIRATION_DAYS = int(os.getenv("WEB_CACHE_EXPIRATION_DAYS", 2)) # Days to keep cached web pages

# --- Tool Keys Status ---
print("--- Tool Keys ---")
print(f"Web Search Provider: {WEB_SEARCH_PROVIDER.capitalize()}")
print(f"  Tavily API Key Loaded: {'Yes' if TAVILY_API_KEY else 'No'}")
print(f"  LinkUp API Key Loaded: {'Yes' if LINKUP_API_KEY else 'No'}")
print(f"  Cost Per Search Call: ${WEB_SEARCH_COST_PER_CALL:.4f}") # Added print for cost
print(f"Web Cache Expiration: {WEB_CACHE_EXPIRATION_DAYS} days")

# Example: Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_researcher/data/vector_store/chroma.db") # Example path

# --- Research Loop Configuration ---
MAX_TOTAL_ITERATIONS = get_max_total_iterations() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("MAX_TOTAL_ITERATIONS", 40)) # Overall limit for research/reflection iterations
# Renamed for clarity: Max number of times ResearchAgent is called per section per round.
# E.g., 1 means one initial research call. 2 means initial call + one refinement call if reflection yields questions.
MAX_RESEARCH_CYCLES_PER_SECTION = get_max_research_cycles_per_section() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("MAX_RESEARCH_CYCLES_PER_SECTION", 2)) # Default is 2
MAX_DEPTH_PASS1 = int(os.getenv("MAX_DEPTH_PASS1", 1)) # Max outline depth processed in Pass 1 (Less relevant now?)
MAX_TOTAL_DEPTH = get_max_total_depth() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("MAX_TOTAL_DEPTH", 2)) # Max outline depth allowed after Inter-Pass revision

# --- Advanced Workflow Configuration ---
INITIAL_RESEARCH_MAX_DEPTH = get_initial_research_max_depth() # 3 Max depth for initial question tree
INITIAL_RESEARCH_MAX_QUESTIONS = get_initial_research_max_questions() # 50 Max total questions in initial phase
STRUCTURED_RESEARCH_ROUNDS = get_structured_research_rounds() # def 2: Number of structured research rounds (Set to 1 for single pass)
WRITING_PASSES = get_writing_passes() # Default 3: Number of writing passes (initial + revisions)
# Max characters for notes context passed to PlanningAgent in one go
MAX_PLANNING_CONTEXT_CHARS = get_max_planning_context_chars() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("MAX_PLANNING_CONTEXT_CHARS", 250000))
# Max characters for previewing previously written content passed to WritingAgent
WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS = get_writing_previous_content_preview_chars() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS", 30000)) # Max characters for previewing previously written content (each section)
# Number of recent thoughts to provide as context to agents
THOUGHT_PAD_CONTEXT_LIMIT = get_thought_pad_context_limit() # Default to 5 recent thoughts
# Toggle to skip final outline refinement and note reassignment after structured research
SKIP_FINAL_REPLANNING = get_skip_final_replanning() # Default to False

# --- Research Note Generation ---
RESEARCH_NOTE_CONTENT_LIMIT = get_research_note_content_limit() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("RESEARCH_NOTE_CONTENT_LIMIT", 32000)) # Default 32000: Max characters of source content to feed into note generation prompt

# --- Embedding Configuration ---
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", 8)) # Default 8: Batch size for embedding operations (reduced for memory safety)
EMBEDDING_MAX_CONCURRENT_QUERIES = int(os.getenv("EMBEDDING_MAX_CONCURRENT_QUERIES", 3)) # Default 3: Max concurrent embedding queries
EMBEDDING_MEMORY_MANAGEMENT = os.getenv("EMBEDDING_MEMORY_MANAGEMENT", "True").lower() == "true" # Enable GPU memory management

# --- Initial Exploration Phase ---
CONSULT_RAG_FOR_INITIAL_QUESTIONS = os.getenv("CONSULT_RAG_FOR_INITIAL_QUESTIONS", "True").lower() == "false" # Whether to consult RAG DB for initial question generation
INITIAL_EXPLORATION_DOC_RESULTS = get_initial_exploration_doc_results() # default 10: Number of docs for initial exploration
INITIAL_EXPLORATION_WEB_RESULTS = get_initial_exploration_web_results() # default 2: Number of web results for initial exploration
INITIAL_EXPLORATION_USE_RERANKER = os.getenv("INITIAL_EXPLORATION_USE_RERANKER", "True").lower() == "true" # Whether to rerank initial exploration results

# --- Main Research Phase ---
MAIN_RESEARCH_DOC_RESULTS = get_main_research_doc_results() # default 10: Number of docs for main research cycles
MAIN_RESEARCH_WEB_RESULTS = get_main_research_web_results() # default 5: Number of web results for main research cycles

# Note Assignment Configuration
MIN_NOTES_PER_SECTION_ASSIGNMENT = get_min_notes_per_section_assignment() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("MIN_NOTES_PER_SECTION_ASSIGNMENT", 5)) # Minimum notes per section
MAX_NOTES_PER_SECTION_ASSIGNMENT = get_max_notes_per_section_assignment() if DYNAMIC_CONFIG_AVAILABLE else int(os.getenv("MAX_NOTES_PER_SECTION_ASSIGNMENT", 40)) # Maximum notes per section
# Max notes to pass to NoteAssignmentAgent after reranking (to manage context window)
MAX_NOTES_FOR_ASSIGNMENT_RERANKING: int = get_max_notes_for_assignment_reranking() # Default 100

# --- Provider Details ---
# Store details for easy access by the dispatcher
PROVIDER_CONFIG = {
    "openrouter": {
        "base_url": OPENROUTER_BASE_URL,
        "api_key": OPENROUTER_API_KEY,
        "fast_model": OPENROUTER_FAST_MODEL,
        "mid_model": OPENROUTER_MID_MODEL,
        "intelligent_model": OPENROUTER_INTELLIGENT_MODEL,
        "verifier_model": OPENROUTER_VERIFIER_MODEL, # Use specific OpenRouter verifier model
        # Add aliases for backward compatibility
        "light_model": OPENROUTER_FAST_MODEL,
        "heavy_model": OPENROUTER_MID_MODEL,
        "beast_model": OPENROUTER_INTELLIGENT_MODEL
    },
    "local": {
        "base_url": LOCAL_LLM_BASE_URL,
        "api_key": LOCAL_LLM_API_KEY,
        "fast_model": LOCAL_LLM_FAST_MODEL,
        "mid_model": LOCAL_LLM_MID_MODEL,
        "intelligent_model": LOCAL_LLM_INTELLIGENT_MODEL,
        "verifier_model": LOCAL_LLM_VERIFIER_MODEL, # Use specific local verifier model
        # Add aliases for backward compatibility
        "light_model": LOCAL_LLM_FAST_MODEL,
        "heavy_model": LOCAL_LLM_MID_MODEL,
        "beast_model": LOCAL_LLM_INTELLIGENT_MODEL
    },
    "custom": {
        # Custom provider configuration comes from user settings
        # Base config will be overridden by user-specific settings
        "base_url": None,
        "api_key": None,
        "fast_model": "custom-fast-model",
        "mid_model": "custom-mid-model", 
        "intelligent_model": "custom-intelligent-model",
        "verifier_model": "custom-verifier-model",
        # Add aliases for backward compatibility
        "light_model": "custom-fast-model",
        "heavy_model": "custom-mid-model",
        "beast_model": "custom-intelligent-model"
    }
}

print("--- LLM Configuration ---")
print(f"Fast Model Provider: {FAST_LLM_PROVIDER}")
print(f"Mid Model Provider: {MID_LLM_PROVIDER}")
print(f"Intelligent Model Provider: {INTELLIGENT_LLM_PROVIDER}")
print(f"Verifier Model Provider: {VERIFIER_LLM_PROVIDER}")
print(f"OpenRouter Base URL: {OPENROUTER_BASE_URL}")
print(f"Local LLM Base URL: {LOCAL_LLM_BASE_URL}")
print("NOTE: Model names are loaded dynamically per user session")
print("--- Research Loop Settings ---")
print(f"Max Total Iterations: {MAX_TOTAL_ITERATIONS}")
print(f"Max Research Cycles Per Section: {MAX_RESEARCH_CYCLES_PER_SECTION}") # Updated print statement
# print(f"Max Depth Pass 1: {MAX_DEPTH_PASS1}") # Commented out as less relevant
print(f"Max Total Depth: {MAX_TOTAL_DEPTH}")
print("--- Advanced Workflow Settings ---")
print(f"Initial Research Max Depth: {INITIAL_RESEARCH_MAX_DEPTH}")
print(f"Initial Research Max Questions: {INITIAL_RESEARCH_MAX_QUESTIONS}")
print(f"Structured Research Rounds: {STRUCTURED_RESEARCH_ROUNDS}")
print(f"Writing Passes: {WRITING_PASSES}")
print(f"Max Planning Context Chars: {MAX_PLANNING_CONTEXT_CHARS}")
print(f"Writing Previous Content Preview Chars: {WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS}") # Added print statement
print(f"Thought Pad Context Limit: {THOUGHT_PAD_CONTEXT_LIMIT}") # Added print statement
print(f"Skip Final Replanning: {SKIP_FINAL_REPLANNING}") # Added print for new setting
print("--- Initial Exploration Settings ---")
print(f"Consult RAG for Initial Questions: {CONSULT_RAG_FOR_INITIAL_QUESTIONS}") # Added print for new setting
print(f"Initial Exploration Doc Results: {INITIAL_EXPLORATION_DOC_RESULTS}")
print(f"Initial Exploration Web Results: {INITIAL_EXPLORATION_WEB_RESULTS}") # Added print
print(f"Initial Exploration Use Reranker: {INITIAL_EXPLORATION_USE_RERANKER}")
print(f"Research Note Content Limit: {RESEARCH_NOTE_CONTENT_LIMIT}")
print("--- Main Research Settings ---") # Added section header
print(f"Main Research Doc Results: {MAIN_RESEARCH_DOC_RESULTS}") # Added print
print(f"Main Research Web Results: {MAIN_RESEARCH_WEB_RESULTS}") # Added print
print("--- Agent Max Tokens ---")
for role, tokens in AGENT_ROLE_MAX_TOKENS.items():
    print(f"  {role.capitalize()}: {tokens if tokens is not None else 'Default'}")
print("--- Concurrency Settings ---")
print(f"Max Concurrent Requests: {'Unlimited' if MAX_CONCURRENT_REQUESTS == 0 else MAX_CONCURRENT_REQUESTS}")
print(f"LLM Request Timeout: {LLM_REQUEST_TIMEOUT}s")
print("-------------------------")
