import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- GPU Configuration ---
CUDA_DEVICE = os.getenv("CUDA_DEVICE", "0")  # Default to GPU 0 if not specified

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

# In Docker, CUDA_VISIBLE_DEVICES is typically set by Docker itself
# For non-Docker environments, we'll set it from our config
if not is_running_in_docker():
    os.environ['CUDA_VISIBLE_DEVICES'] = CUDA_DEVICE
    print(f"Setting CUDA_VISIBLE_DEVICES to {CUDA_DEVICE}")
else:
    # In Docker, just print the current CUDA_VISIBLE_DEVICES value
    docker_cuda_devices = os.getenv("CUDA_VISIBLE_DEVICES", "Not set")
    print(f"Running in Docker. CUDA_VISIBLE_DEVICES is {docker_cuda_devices} (managed by Docker)")

# --- LLM Provider Configuration ---
# Set the desired LLM provider for fast and mid models: "openrouter" or "local"
FAST_LLM_PROVIDER = os.getenv("FAST_LLM_PROVIDER", "openrouter") # Default fast to openrouter
MID_LLM_PROVIDER = os.getenv("MID_LLM_PROVIDER", "openrouter") # Default mid to openrouter

# --- Local LLM Configuration ---
# Example: Using a local server like LM Studio, Ollama, etc.
# Ensure your local server provides an OpenAI-compatible API endpoint.
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:5000/v1/") # Default local URL
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "none") # Often 'none' or not required for local
# Define local model names (adjust if your local models have different identifiers)
# These might be the actual file names or identifiers used by your local server.
LOCAL_LLM_FAST_MODEL = os.getenv("LOCAL_LLM_FAST_MODEL", "local-fast-model-id") # Replace with your actual local fast model ID
LOCAL_LLM_MID_MODEL = os.getenv("LOCAL_LLM_MID_MODEL", "local-mid-model-id") # Replace with your actual local mid model ID
LOCAL_LLM_INTELLIGENT_MODEL = os.getenv("LOCAL_LLM_INTELLIGENT_MODEL", "local-intelligent-model-id") # Replace with your actual local intelligent model ID

# --- LLM Provider Configuration (Intelligent) ---
# Set the desired LLM provider for the intelligent model: "openrouter" or "local"
INTELLIGENT_LLM_PROVIDER = os.getenv("INTELLIGENT_LLM_PROVIDER", "openrouter") # Default intelligent to openrouter

# --- LLM Provider Configuration (Verifier) ---
# Set the desired LLM provider for the verifier model: "openrouter" or "local"
VERIFIER_LLM_PROVIDER = os.getenv("VERIFIER_LLM_PROVIDER", "openrouter") # Default verifier to openrouter

# Mapping agent types/modes to the *type* of model needed (fast/mid/intelligent/verifier)
# The dispatcher will then resolve the actual name and provider
AGENT_ROLE_MODEL_TYPE = {
    "planning": "fast", 
    "research": "mid",
    "writing": "mid",
    "reflection": "intelligent", 
    "messenger": "mid",
    "note_assignment": "fast", 
    "query_preparation": "intelligent", 
    "query_strategy": "fast", 
    "verifier": "verifier", 
    "default": "mid" 
}

# --- OpenRouter Configuration ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# Define OpenRouter model names (can be overridden by environment variables)
OPENROUTER_FAST_MODEL = os.getenv("OPENROUTER_FAST_MODEL", "openai/gpt-4o-mini")
OPENROUTER_MID_MODEL = os.getenv("OPENROUTER_MID_MODEL", "google/gemma-3-27b-it")
OPENROUTER_INTELLIGENT_MODEL = os.getenv("OPENROUTER_INTELLIGENT_MODEL", "google/gemma-3-27b-it") # Default intelligent model if not set in .env
# --- Verifier Model Configuration ---
# Define the specific model used for verification tasks (e.g., in evaluation scripts)
# Note: VERIFIER_LLM_PROVIDER determines if OPENROUTER_ or LOCAL_ is used.
OPENROUTER_VERIFIER_MODEL = os.getenv("OPENROUTER_VERIFIER_MODEL", "anthropic/claude-3.7-sonnet") # Default OpenRouter verifier
LOCAL_LLM_VERIFIER_MODEL = os.getenv("LOCAL_LLM_VERIFIER_MODEL", "local-verifier-model-id") # Default local verifier

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
    "messenger": 0.7, # More conversational for chat
    "query_preparation": 0.3, # Focused for query generation
    "query_strategy": 0.3, # Focused for strategy selection
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
    if model_type == "fast" or model_type == "light":  # Support both new and old names
        provider = FAST_LLM_PROVIDER
        return LOCAL_LLM_FAST_MODEL if provider == "local" else OPENROUTER_FAST_MODEL
    elif model_type == "mid" or model_type == "heavy":  # Support both new and old names
        provider = MID_LLM_PROVIDER
        return LOCAL_LLM_MID_MODEL if provider == "local" else OPENROUTER_MID_MODEL
    elif model_type == "intelligent" or model_type == "beast":  # Support both new and old names
        provider = INTELLIGENT_LLM_PROVIDER
        return LOCAL_LLM_INTELLIGENT_MODEL if provider == "local" else OPENROUTER_INTELLIGENT_MODEL
    elif model_type == "verifier": # Added verifier case
        provider = VERIFIER_LLM_PROVIDER
        return LOCAL_LLM_VERIFIER_MODEL if provider == "local" else OPENROUTER_VERIFIER_MODEL
    else:
        # Fallback or error? For now, let's default to mid model via its provider
        print(f"Warning: Unknown model type '{model_type}' requested. Falling back to mid model.")
        provider = MID_LLM_PROVIDER
        return LOCAL_LLM_MID_MODEL if provider == "local" else OPENROUTER_MID_MODEL


# Assign model names based on the function
FAST_MODEL_NAME = get_model_name("fast")
MID_MODEL_NAME = get_model_name("mid")
INTELLIGENT_MODEL_NAME = get_model_name("intelligent")
VERIFIER_MODEL_NAME = get_model_name("verifier") # Assign verifier model name using the function

# --- Other Configurations (Add as needed) ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 5)) # seconds
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 600.0)) # Timeout in seconds for LLM API calls
# Max concurrent requests for agent operations (0 for no limit)
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", 25))

# --- Web Search Configuration ---
# Choose the web search provider: "tavily" or "linkup"
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "tavily").lower()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LINKUP_API_KEY = os.getenv("LINKUP_API_KEY")
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
MAX_TOTAL_ITERATIONS = int(os.getenv("MAX_TOTAL_ITERATIONS", 40)) # Overall limit for research/reflection iterations
# Renamed for clarity: Max number of times ResearchAgent is called per section per round.
# E.g., 1 means one initial research call. 2 means initial call + one refinement call if reflection yields questions.
MAX_RESEARCH_CYCLES_PER_SECTION = int(os.getenv("MAX_RESEARCH_CYCLES_PER_SECTION", 2)) # Default is 2
MAX_DEPTH_PASS1 = int(os.getenv("MAX_DEPTH_PASS1", 1)) # Max outline depth processed in Pass 1 (Less relevant now?)
MAX_TOTAL_DEPTH = int(os.getenv("MAX_TOTAL_DEPTH", 2)) # Max outline depth allowed after Inter-Pass revision

# --- Advanced Workflow Configuration ---
INITIAL_RESEARCH_MAX_DEPTH = int(os.getenv("INITIAL_RESEARCH_MAX_DEPTH", 2)) # 3 Max depth for initial question tree
INITIAL_RESEARCH_MAX_QUESTIONS = int(os.getenv("INITIAL_RESEARCH_MAX_QUESTIONS", 20)) # 50 Max total questions in initial phase
STRUCTURED_RESEARCH_ROUNDS = int(os.getenv("STRUCTURED_RESEARCH_ROUNDS", 2)) # def 2: Number of structured research rounds (Set to 1 for single pass)
WRITING_PASSES = int(os.getenv("WRITING_PASSES", 2)) # Default 3: Number of writing passes (initial + revisions)
# Max characters for notes context passed to PlanningAgent in one go
MAX_PLANNING_CONTEXT_CHARS = int(os.getenv("MAX_PLANNING_CONTEXT_CHARS", 250000))
# Max characters for previewing previously written content passed to WritingAgent
WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS = int(os.getenv("WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS", 30000)) # Max characters for previewing previously written content (each section)
# Number of recent thoughts to provide as context to agents
THOUGHT_PAD_CONTEXT_LIMIT = int(os.getenv("THOUGHT_PAD_CONTEXT_LIMIT", 30)) # Default to 5 recent thoughts
# Toggle to skip final outline refinement and note reassignment after structured research
SKIP_FINAL_REPLANNING = os.getenv("SKIP_FINAL_REPLANNING", "False").lower() == "true" # Default to False

# --- Research Note Generation ---
RESEARCH_NOTE_CONTENT_LIMIT = int(os.getenv("RESEARCH_NOTE_CONTENT_LIMIT", 32000)) # Default 32000: Max characters of source content to feed into note generation prompt

# --- Initial Exploration Phase ---
CONSULT_RAG_FOR_INITIAL_QUESTIONS = os.getenv("CONSULT_RAG_FOR_INITIAL_QUESTIONS", "True").lower() == "false" # Whether to consult RAG DB for initial question generation
INITIAL_EXPLORATION_DOC_RESULTS = int(os.getenv("INITIAL_EXPLORATION_DOC_RESULTS", 5)) # default 10: Number of docs for initial exploration
INITIAL_EXPLORATION_WEB_RESULTS = int(os.getenv("INITIAL_EXPLORATION_WEB_RESULTS", 2)) # default 2: Number of web results for initial exploration
INITIAL_EXPLORATION_USE_RERANKER = os.getenv("INITIAL_EXPLORATION_USE_RERANKER", "True").lower() == "true" # Whether to rerank initial exploration results

# --- Main Research Phase ---
MAIN_RESEARCH_DOC_RESULTS = int(os.getenv("MAIN_RESEARCH_DOC_RESULTS", 5)) # default 10: Number of docs for main research cycles
MAIN_RESEARCH_WEB_RESULTS = int(os.getenv("MAIN_RESEARCH_WEB_RESULTS", 2)) # default 5: Number of web results for main research cycles

# Note Assignment Configuration
MIN_NOTES_PER_SECTION_ASSIGNMENT = int(os.getenv("MIN_NOTES_PER_SECTION_ASSIGNMENT", 5)) # Minimum notes per section
MAX_NOTES_PER_SECTION_ASSIGNMENT = int(os.getenv("MAX_NOTES_PER_SECTION_ASSIGNMENT", 40)) # Maximum notes per section
# Max notes to pass to NoteAssignmentAgent after reranking (to manage context window)
MAX_NOTES_FOR_ASSIGNMENT_RERANKING: int = int(os.getenv("MAX_NOTES_FOR_ASSIGNMENT_RERANKING", 80)) # Default 100

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
    }
}

print("--- LLM Configuration ---")
print(f"Fast Model Provider: {FAST_LLM_PROVIDER}")
print(f"  Model Name: {FAST_MODEL_NAME}")
print(f"Mid Model Provider: {MID_LLM_PROVIDER}")
print(f"  Model Name: {MID_MODEL_NAME}")
print(f"Intelligent Model Provider: {INTELLIGENT_LLM_PROVIDER}")
print(f"  Model Name: {INTELLIGENT_MODEL_NAME}")
print(f"Verifier Model Provider: {VERIFIER_LLM_PROVIDER}") # Print verifier provider
print(f"  Model Name: {VERIFIER_MODEL_NAME}") # Print verifier model name
print(f"OpenRouter Base URL: {OPENROUTER_BASE_URL}")
print(f"Local LLM Base URL: {LOCAL_LLM_BASE_URL}")
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
