import os
import json
import csv
import datetime
import logging
import re
import sys
import tiktoken
import argparse
from typing import List, Dict, Any, Optional, Tuple

# --- Set CUDA device ---
# Force the application to use only the GPU with index 4
os.environ['CUDA_VISIBLE_DEVICES'] = '4'
# --- End CUDA device setting ---

# Add the project root to the Python path to allow importing ai_researcher modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Attempt to import necessary components from ai_researcher
try:
    from ai_researcher import config # Import the config module itself
    from ai_researcher.config import (
        PROVIDER_CONFIG, AGENT_ROLE_MODEL_TYPE, AGENT_ROLE_TEMPERATURE,
        AGENT_ROLE_MAX_TOKENS, LLM_REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
        RESEARCH_NOTE_CONTENT_LIMIT, MAIN_RESEARCH_DOC_RESULTS, MAIN_RESEARCH_WEB_RESULTS,
        WRITING_PREVIOUS_CONTENT_PREVIEW_CHARS, MAX_PLANNING_CONTEXT_CHARS,
        MIN_NOTES_PER_SECTION_ASSIGNMENT, MAX_NOTES_PER_SECTION_ASSIGNMENT,
        MAX_NOTES_FOR_ASSIGNMENT_RERANKING
    )
    # Core Agentic Layer components
    from ai_researcher.agentic_layer.agent_controller import AgentController # May not be needed directly
    from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher # Removed dispatch_model import
    from ai_researcher.agentic_layer.tool_registry import ToolRegistry, ToolDefinition
    from ai_researcher.agentic_layer.agents.research_agent import ResearchAgent
    from ai_researcher.agentic_layer.agents.writing_agent import WritingAgent # Import WritingAgent
    # Schemas
    from ai_researcher.agentic_layer.schemas.notes import Note
    from ai_researcher.agentic_layer.schemas.planning import ReportSection # Needed for dummy section
    # Core RAG components
    from ai_researcher.core_rag.database import Database
    from ai_researcher.core_rag.vector_store import VectorStore
    from ai_researcher.core_rag.embedder import TextEmbedder # Assuming default embedder setup
    from ai_researcher.core_rag.reranker import TextReranker # Assuming default reranker setup
    from ai_researcher.core_rag.retriever import Retriever
    from ai_researcher.core_rag.query_preparer import QueryPreparer
    from ai_researcher.core_rag.query_strategist import QueryStrategist
    # Tool Implementations
    from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
    from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
    from ai_researcher.agentic_layer.tools.web_page_fetcher_tool import WebPageFetcherTool
    from ai_researcher.agentic_layer.tools.file_reader_tool import FileReaderTool
    from ai_researcher.agentic_layer.tools.calculator_tool import CalculatorTool
    # Other necessary imports
    import asyncio # For semaphore
except ImportError as e:
    print(f"Error importing ai_researcher components: {e}")
    print("Please ensure the script is run from the project root or the ai_researcher package is correctly installed.")
    sys.exit(1)

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description='Run parallel LLM accuracy evaluation')
parser.add_argument('--simple-verification', action='store_true', 
                    help='Use simplified verification without reasoning, supported_parts, and unsupported_parts')
args = parser.parse_args()

# Log the verification mode
logging.info(f"Verification mode: {'Simple (result only)' if args.simple_verification else 'Detailed (with reasoning)'}")

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define LLMs to test (Replace with actual model identifiers from your config/providers)
LLMS_TO_TEST = [
    "qwen/qwen3-32b",
    "qwen/qwen3-235b-a22b",
    "qwen/qwen3-30b-a3b",
    "qwen/qwen3-8b",
    "qwen/qwen3-14b",
    "openai/gpt-4o-mini",
    "meta-llama/llama-4-maverick",
    "deepseek/deepseek-chat-v3-0324",
    "openai/gpt-4.1-nano",
    "qwen/qwen-2.5-72b-instruct",
    "google/gemini-2.5-flash-preview",
    "anthropic/claude-3.7-sonnet",
    "amazon/nova-lite-v1",
    "google/gemma-3-27b-it",
    "microsoft/phi-4",
    "qwen/qwen-2.5-7b-instruct",
    "qwen/qwen2.5-coder-7b-instruct"
    # "nvidia/llama-3.1-nemotron-nano-8b-v1:free"
    # Add more models as needed, e.g., "anthropic/claude-3-haiku-20240307"
]

# Define the Verifier Models
VERIFIER_MODELS = [
    "qwen/qwen3-30b-a3b",
    "anthropic/claude-3.7-sonnet",
    "meta-llama/llama-4-maverick"
]

# Paths
QUESTIONS_FILE = "questions.txt"
PROMPT_TEMPLATE_PATH = "evaluation/prompts/verifier_prompt.txt"
RESULTS_DIR = "evaluation/results"

# Load Verifier Prompt Template
try:
    with open(PROMPT_TEMPLATE_PATH, 'r') as f:
        VERIFIER_PROMPT_TEMPLATE = f.read()
except FileNotFoundError:
    logging.error(f"Verifier prompt template not found at {PROMPT_TEMPLATE_PATH}")
    sys.exit(1)

# Load Questions
try:
    with open(QUESTIONS_FILE, 'r') as f:
        RESEARCH_QUESTIONS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    logging.error(f"Questions file not found at {QUESTIONS_FILE}")
    sys.exit(1)

# --- Helper Functions ---

# --- Token Counting Function ---
def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Count the number of tokens in a text string using tiktoken.
    
    Args:
        text: The text to count tokens for
        model: The model to use for token counting (default: gpt-4)
        
    Returns:
        The number of tokens in the text
    """
    try:
        # Get the encoding for the specified model
        encoding = tiktoken.encoding_for_model(model)
        # Count tokens
        token_count = len(encoding.encode(text))
        return token_count
    except Exception as e:
        logging.warning(f"Error counting tokens: {e}. Using fallback method.")
        # Fallback: approximate token count (1 token ≈ 4 chars in English)
        return len(text) // 4

# --- Global Variables ---
# These will be initialized once in initialize_components()
global_semaphore = None
global_model_dispatcher = None
global_tool_registry = None
global_research_agent = None
global_writing_agent = None
global_retriever = None
global_query_preparer = None
global_query_strategist = None
components_initialized = False

# Create a lock for model configuration
model_config_lock = asyncio.Lock()

def initialize_components():
    """Initialize all global components once and only once"""
    global global_semaphore, global_model_dispatcher, global_tool_registry
    global global_research_agent, global_writing_agent, global_retriever
    global global_query_preparer, global_query_strategist, components_initialized
    
    if components_initialized:
        logging.info("Components already initialized, skipping initialization")
        return
    
    logging.info("Initializing global components...")
    
    # Increase the semaphore limit to allow more concurrent requests
    max_concurrent = config.MAX_CONCURRENT_REQUESTS
    if max_concurrent < 10:  # Ensure we have enough concurrency for parallel processing
        max_concurrent = 10
    
    # Semaphore for concurrency limiting
    global_semaphore = asyncio.Semaphore(max_concurrent)

    # Model Dispatcher (Single instance for all calls)
    global_model_dispatcher = ModelDispatcher(semaphore=global_semaphore)

    # RAG Components
    try:
        db = Database(config.DATABASE_URL) # Database object, not used by VectorStore init
        embedder = TextEmbedder() # Uses default model from config/env
        vector_store_persist_path = "ai_researcher/data/vector_store" # Assuming this is the correct path
        vector_store = VectorStore(persist_directory=vector_store_persist_path)
        reranker = TextReranker() # Uses default model from config/env
        global_retriever = Retriever(embedder, vector_store, reranker) # Corrected argument order
        global_query_preparer = QueryPreparer(global_model_dispatcher) # Use global dispatcher
        global_query_strategist = QueryStrategist(global_model_dispatcher) # Use global dispatcher
    except Exception as e:
        logging.error(f"Fatal error initializing RAG components: {e}", exc_info=True)
        sys.exit(1)

    # Tool Registry and Tools
    try:
        global_tool_registry = ToolRegistry()
        # Document Search
        doc_search_tool = DocumentSearchTool(global_retriever, global_query_preparer, global_query_strategist)
        global_tool_registry.register_tool(ToolDefinition(
            name=doc_search_tool.name, description=doc_search_tool.description,
            parameters_schema=doc_search_tool.parameters_schema, implementation=doc_search_tool.execute
        ))
        # Web Search
        web_search_tool = WebSearchTool()
        global_tool_registry.register_tool(ToolDefinition(
            name=web_search_tool.name, description=web_search_tool.description,
            parameters_schema=web_search_tool.parameters_schema, implementation=web_search_tool.execute
        ))
        # Web Fetcher
        web_fetcher_tool = WebPageFetcherTool()
        global_tool_registry.register_tool(ToolDefinition(
            name=web_fetcher_tool.name, description=web_fetcher_tool.description,
            parameters_schema=web_fetcher_tool.parameters_schema, implementation=web_fetcher_tool.execute
        ))
        # File Reader
        file_reader_tool = FileReaderTool()
        global_tool_registry.register_tool(ToolDefinition(
            name=file_reader_tool.name, description=file_reader_tool.description,
            parameters_schema=file_reader_tool.parameters_schema, implementation=file_reader_tool.execute
        ))
        # Calculator
        calculator_tool = CalculatorTool()
        global_tool_registry.register_tool(ToolDefinition(
            name=calculator_tool.name, description=calculator_tool.description,
            parameters_schema=calculator_tool.parameters_schema, implementation=calculator_tool.execute
        ))
    except Exception as e:
        logging.error(f"Fatal error initializing Tools: {e}", exc_info=True)
        sys.exit(1)

    # Agents (Initialized once, model override happens per call via config patching)
    try:
        # Research Agent - uses global dispatcher, registry, preparer
        global_research_agent = ResearchAgent(
            model_dispatcher=global_model_dispatcher,
            tool_registry=global_tool_registry,
            query_preparer=global_query_preparer
            # controller=None, feedback_callback=None # Not needed for direct call
        )
        # Writing Agent - uses global dispatcher
        global_writing_agent = WritingAgent(model_dispatcher=global_model_dispatcher)
    except Exception as e:
        logging.error(f"Fatal error initializing Agents: {e}", exc_info=True)
        sys.exit(1)
    
    components_initialized = True
    logging.info("Global components initialized successfully")
# --- End Global Variables ---


async def call_verifier(
    # model_dispatcher parameter removed, uses global_model_dispatcher
    context: str,
    claim: str,
    verifier_model: str
) -> Dict[str, Any]:
    """Calls the verifier LLM with the provided context and claim using the global dispatcher."""
    # Ensure components are initialized
    if not components_initialized:
        initialize_components()
        
    logging.debug(f"Calling verifier {verifier_model} for claim: '{claim[:100]}...'")
    
    # Choose prompt and JSON schema based on command line argument
    if args.simple_verification:
        # Simplified prompt that only asks for verification_result
        prompt = f"""You are a fact-checking expert. Your task is to carefully analyze the provided article and assess whether it supports the specified claim.

Following is the article to analyze:

<<article>>
{context}
<</article>>

Please verify if the article supports this claim:

<<claim>>
{claim}
<</claim>>

Based on the article above, analyze whether the claim is supported by the article's content. Provide your answer strictly in the following JSON format:
{{
  "verification_result": "yes | no | partial"
}}"""
    else:
        # Full prompt with reasoning and partial verification details
        prompt = VERIFIER_PROMPT_TEMPLATE.format(context=context, claim=claim)
    
    # Choose JSON schema based on command line argument
    if args.simple_verification:
        # Simplified schema with only verification_result
        json_schema = {
            "type": "object",
            "properties": {
                "verification_result": {"type": "string", "enum": ["yes", "no", "partial"]}
            },
            "required": ["verification_result"]
        }
        logging.debug("Using simplified verification schema (result only)")
    else:
        # Full schema with reasoning and partial verification details
        json_schema = {
            "type": "object",
            "properties": {
                "verification_result": {"type": "string", "enum": ["yes", "no", "partial"]},
                "reasoning": {"type": ["string", "null"], "description": "Reasoning for 'yes' or 'no'. Null/empty for 'partial'."},
                "supported_parts": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of supported parts for 'partial'. Null/empty otherwise."},
                "unsupported_parts": {"type": ["array", "null"], "items": {"type": "string"}, "description": "List of unsupported parts for 'partial'. Null/empty otherwise."}
            },
            "required": ["verification_result"] # Only result is always required
            # "reasoning", "supported_parts", "unsupported_parts" are conditionally required based on verification_result
        }

    try:
        # Use the global dispatcher instance's dispatch method
        messages = [{"role": "user", "content": prompt}]
        response_obj, model_details = await global_model_dispatcher.dispatch(
            messages=messages,
            model=verifier_model,
            response_format={"type": "json_object"},
            # Optional: Define a specific 'verifier' agent_mode in config.py
            # and use it here if you want separate temperature/max_tokens settings.
            # agent_mode="verifier",
            # Temperature/max_tokens are now handled by dispatch based on agent_mode or defaults
            # We can override here if needed, but let's rely on dispatcher logic first.
            # temperature=0.2,
            # max_tokens=500,
        )

        # Process the response object
        if response_obj and response_obj.choices and response_obj.choices[0].message.content:
            response_content = response_obj.choices[0].message.content
            try:
                # Attempt to find JSON within potential markdown fences
                # First try to extract from code blocks
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_content)
                if match:
                    json_str = match.group(1)
                else:
                    # If no code blocks, try to find JSON object directly
                    # Look for the first { and the last } to capture the entire JSON object
                    first_brace = response_content.find('{')
                    last_brace = response_content.rfind('}')
                    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
                        json_str = response_content[first_brace:last_brace+1]
                    else:
                        json_str = response_content # Assume raw JSON as last resort

                result_json = json.loads(json_str)
                logging.debug(f"Verifier response: {result_json}")
                # Add verifier_model to the result
                result_json["verifier_model"] = verifier_model
                return result_json
            except json.JSONDecodeError:
                 logging.error(f"Verifier returned non-JSON response or failed parsing: {response_content}")
                 return {"verification_result": "error", "reasoning": "Failed to parse LLM response", "verifier_model": verifier_model}
        else:
            logging.error(f"Verifier LLM call failed or returned empty content. Response object: {response_obj}")
            return {"verification_result": "error", "reasoning": "LLM call failed or returned empty content", "verifier_model": verifier_model}

    except Exception as e:
        logging.error(f"Error calling verifier LLM ({verifier_model}): {e}", exc_info=True)
        return {"verification_result": "error", "reasoning": str(e), "verifier_model": verifier_model}


# --- NEW Helper Function for Note Verification ---
async def process_note_verification(note: Note, context: str, token_count: int, llm_id: str, question: str, context_idx: int, verifier_model: str) -> Dict[str, Any]:
    """Verifies an initial note against its context using a specific verifier model."""
    try:
        # Verify the note against the context
        verification_result = await call_verifier(context, note.content, verifier_model)

        # Create the base result dictionary
        result = {
            "llm": llm_id,
            "question": question,
            "stage": "note", # Stage is 'note' verification
            "context_index": context_idx,
            "claim": note.content, # The note's content is the claim
            "context_length": len(context),
            "token_count": token_count,
            "verification_result": verification_result.get("verification_result", "error"),
            "verifier_model": verifier_model,  # Add the verifier model
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Add optional fields if they exist in the verification result
        # These fields will be absent when using --simple-verification
        if "reasoning" in verification_result:
            result["verifier_reasoning"] = verification_result.get("reasoning")
        else:
            result["verifier_reasoning"] = None if args.simple_verification else ""
            
        if "supported_parts" in verification_result:
            result["supported_parts"] = json.dumps(verification_result.get("supported_parts")) if verification_result.get("supported_parts") else ""
        else:
            result["supported_parts"] = ""
            
        if "unsupported_parts" in verification_result:
            result["unsupported_parts"] = json.dumps(verification_result.get("unsupported_parts")) if verification_result.get("unsupported_parts") else ""
        else:
            result["unsupported_parts"] = ""
            
        return result
    except Exception as e:
        logging.error(f"Error in process_note_verification for note {note.note_id} (LLM: {llm_id}, Verifier: {verifier_model}): {e}", exc_info=True)
        return {
            "llm": llm_id,
            "question": question,
            "stage": "note",
            "context_index": context_idx,
            "claim": note.content if note else "Note object missing",
            "context_length": len(context),
            "token_count": token_count,
            "verification_result": "error",
            "verifier_model": verifier_model,  # Add the verifier model
            "verifier_reasoning": f"Critical failure during note verification: {str(e)}",
            "supported_parts": "",
            "unsupported_parts": "",
            "timestamp": datetime.datetime.now().isoformat()
        }
# --- End NEW Helper Function ---


# --- Modify generate_research_context signature ---
async def generate_research_context(question: str, llm_id_for_context: str) -> List[Tuple[str, int, Note]]: # Add llm_id param
    """
    Generates research context for a given question USING A SPECIFIC LLM.
    Returns a list of tuples containing (context, token_count, original_note).
    The 'original_note' here is the note generated by llm_id_for_context from the context.
    """
    logging.info(f"Generating research context for question: '{question}' using LLM: {llm_id_for_context}") # Log LLM used

    # Ensure components are initialized
    if not components_initialized:
        initialize_components()

    # Create a dummy ReportSection for the agent
    import hashlib
    question_hash = hashlib.md5(question.encode()).hexdigest()[:8]
    dummy_section = ReportSection(
        section_id=f"eval_{question_hash}",
        title=f"Evaluation Section for: {question[:50]}...",
        description=question, # Use the question as the goal/description
        subsections=[],
        research_strategy="research_based" # Assume direct research
    )

    # Generate a temporary mission_id for this run
    temp_mission_id = f"eval_mission_{question_hash}_{llm_id_for_context.replace('/', '_')}" # Include LLM in mission ID
    logging.info(f"Using temporary mission_id: {temp_mission_id}")

    # Collect contexts and their token counts
    contexts_with_tokens_and_notes = []

    try:
        # Call the context-capturing method using the global agent and registry
        # Pass the llm_id_for_context as the 'model' parameter
        notes_context_tuples, exec_details, scratchpad_update = await global_research_agent.run_and_capture_context(
            mission_id=temp_mission_id,
            section=dummy_section,
            focus_questions=[question], # Use the main question as the focus question
            agent_scratchpad=None, # Start with no scratchpad for isolated test
            feedback_callback=None, # No UI feedback needed here
            log_queue=None, # No UI logging needed here
            update_callback=None, # No UI updates needed here
            tool_registry=global_tool_registry, # Pass the global registry
            model=llm_id_for_context, # <<< Pass the specific LLM ID here >>>
            active_goals=None, # <-- Pass None for testing
            active_thoughts=None # <-- Pass None for testing
        )

        # Process each note and its context
        for note, context in notes_context_tuples:
            # Count tokens in the context
            token_count = count_tokens(context)
            contexts_with_tokens_and_notes.append((context, token_count, note)) # Store context, token count, and the generated note
            logging.info(f"Generated context and note {note.note_id} using {llm_id_for_context} ({token_count} tokens)")

        logging.info(f"Returning {len(contexts_with_tokens_and_notes)} (context, token_count, note) tuples generated by {llm_id_for_context}")
        return contexts_with_tokens_and_notes

    except Exception as e:
        logging.error(f"Error generating research context for question '{question}' using LLM {llm_id_for_context}: {e}", exc_info=True)
        return []


# --- Keep generate_note_with_llm - Might be useful for other tests, but not used in this script's main flow anymore ---
async def generate_note_with_llm(llm_id: str, context: str, question: str) -> Tuple[Optional[Note], Dict[str, Any]]:
    """
    Generates a note using the specified LLM with the given context.
    Returns the generated note and model call details.
    """
    logging.info(f"Generating note with LLM {llm_id} for question: '{question}'")
    
    # Ensure components are initialized
    if not components_initialized:
        initialize_components()
    
    # Removed config override - model is passed directly
    
    # Create a dummy section for note generation
    import hashlib
    question_hash = hashlib.md5(question.encode()).hexdigest()[:8]
    section_id = f"eval_{question_hash}"
    
    # Generate a note using the context
    try:
        # Create a temporary mission_id
        temp_mission_id = f"eval_mission_{question_hash}_{llm_id.replace('/', '_')}"
        
        # Set up the global research agent's mission_id
        global_research_agent.mission_id = temp_mission_id
        
        # Generate a note from the context
        note, model_details = await global_research_agent._generate_note_from_content(
            question_being_explored=question,
            section_id=section_id,
            section_description=question,
            focus_questions=[question],
            source_type="document", # Treat as document source
            source_id=f"context_{question_hash}",
            source_metadata={"title": f"Context for {question}", "doc_id": f"context_{question_hash}"},
            content_to_process=context,
            is_initial_exploration=False,
            model=llm_id # <-- Pass the specific model ID here
        )
        
        return note, model_details
    
    except Exception as e:
        logging.error(f"Error generating note with LLM {llm_id} for question '{question}': {e}", exc_info=True)
        return None, {"error": str(e)}


async def generate_writing_with_llm(llm_id: str, notes: List[Note], question: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Generates writing content using the specified LLM with the given notes.
    Returns the generated content and model call details.
    """
    logging.info(f"Generating writing with LLM {llm_id} for question: '{question}'")
    
    # Ensure components are initialized
    if not components_initialized:
        initialize_components()
    
    # Removed config override - model is passed directly
    
    # Create a dummy section for writing
    import hashlib
    question_hash = hashlib.md5(question.encode()).hexdigest()[:8]
    dummy_section = ReportSection(
        section_id=f"eval_writing_{question_hash}",
        title=f"Evaluation Writing Section for: {question[:40]}...",
        description=f"Write a brief paragraph summarizing the findings related to the question: {question}",
        subsections=[],
        research_strategy="research_based"
    )
    
    try:
        # Create a temporary mission_id
        temp_mission_id = f"eval_mission_{question_hash}_{llm_id.replace('/', '_')}"
        
        # Call the writing agent
        generated_content, exec_details, scratchpad_update = await global_writing_agent.run(
            section_to_write=dummy_section,
            notes_for_section=notes,
            previous_sections_content={},
            full_outline=None,
            parent_section_title=None,
            current_draft_content=None,
            revision_suggestions=None,
            agent_scratchpad=None,
            mission_id=temp_mission_id,
            log_queue=None,
            update_callback=None,
            model=llm_id # <-- Pass the specific model ID here
        )
        
        return generated_content, exec_details
    
    except Exception as e:
        logging.error(f"Error generating writing with LLM {llm_id} for question '{question}': {e}", exc_info=True)
        return None, {"error": str(e)}


async def extract_claims_from_writing(writing_content: str, notes: List[Note]) -> List[Dict[str, Any]]:
    """
    Extracts claims from writing content, matching them with their source notes.
    Returns a list of dictionaries containing claim text and context.
    """
    if not writing_content:
        logging.warning("No writing content provided for claim extraction.")
        return []
    
    claims_with_context = []
    
    try:
        # Create maps for both note IDs and document IDs
        note_map = {note.note_id: note for note in notes}
        
        # Create a map of document IDs to notes
        # Extract doc_id from source_id (e.g., "f28769c8_68" -> "f28769c8")
        doc_id_map = {}
        for note in notes:
            source_id = note.source_id
            doc_id = source_id.split('_')[0] if '_' in source_id else source_id
            doc_id_map[doc_id] = note
        
        # Log the available doc_ids for debugging
        logging.info(f"Available doc_ids for matching: {list(doc_id_map.keys())}")
        
        # First try to find note IDs (for backward compatibility)
        note_id_pattern = re.compile(r"\[(note_[a-f0-9]{8})\]", re.IGNORECASE)
        found_note_ids = note_id_pattern.findall(writing_content)
        
        # Then try to find document IDs (which is what the WritingAgent actually uses)
        # Look for any alphanumeric ID in brackets that's not prefixed with "note_"
        doc_id_pattern = re.compile(r"\[([a-f0-9]{8}(?:_[a-f0-9]+)?)\]", re.IGNORECASE)
        found_doc_ids = doc_id_pattern.findall(writing_content)
        
        logging.info(f"Found {len(found_note_ids)} note IDs and {len(found_doc_ids)} doc IDs in writing content")
        
        # Process each referenced note ID (backward compatibility)
        for note_id in found_note_ids:
            if note_id in note_map:
                try:
                    note_pos = writing_content.index(f"[{note_id}]")
                    
                    # Find sentence boundaries
                    sent_start = writing_content.rfind('.', 0, note_pos)
                    sent_start_q = writing_content.rfind('?', 0, note_pos)
                    sent_start_e = writing_content.rfind('!', 0, note_pos)
                    sent_start = max(sent_start, sent_start_q, sent_start_e)
                    
                    if sent_start == -1:
                        sent_start = 0
                    else:
                        sent_start += 1
                    
                    sent_end = writing_content.find('.', note_pos)
                    sent_end_q = writing_content.find('?', note_pos)
                    sent_end_e = writing_content.find('!', note_pos)
                    
                    possible_ends = [e for e in [sent_end, sent_end_q, sent_end_e] if e != -1]
                    if not possible_ends:
                        sent_end = len(writing_content)
                    else:
                        sent_end = min(possible_ends) + 1
                    
                    # Extract the sentence
                    sentence = writing_content[sent_start:sent_end].strip()
                    
                    # Get the note's content as context
                    note = note_map[note_id]
                    
                    claims_with_context.append({
                        "claim": sentence,
                        "context": note.content,
                        "context_length": len(note.content),
                        "token_count": count_tokens(note.content),
                        "note_id": note_id
                    })
                    
                except ValueError:
                    logging.warning(f"Could not find position for note_id '{note_id}' in writing content.")
            else:
                logging.warning(f"Referenced note_id '{note_id}' not found in notes.")
        
        # Process each referenced document ID (what the WritingAgent actually uses)
        for doc_id in found_doc_ids:
            if doc_id in doc_id_map:
                try:
                    doc_pos = writing_content.index(f"[{doc_id}]")
                    
                    # Find sentence boundaries
                    sent_start = writing_content.rfind('.', 0, doc_pos)
                    sent_start_q = writing_content.rfind('?', 0, doc_pos)
                    sent_start_e = writing_content.rfind('!', 0, doc_pos)
                    sent_start = max(sent_start, sent_start_q, sent_start_e)
                    
                    if sent_start == -1:
                        sent_start = 0
                    else:
                        sent_start += 1
                    
                    sent_end = writing_content.find('.', doc_pos)
                    sent_end_q = writing_content.find('?', doc_pos)
                    sent_end_e = writing_content.find('!', doc_pos)
                    
                    possible_ends = [e for e in [sent_end, sent_end_q, sent_end_e] if e != -1]
                    if not possible_ends:
                        sent_end = len(writing_content)
                    else:
                        sent_end = min(possible_ends) + 1
                    
                    # Extract the sentence
                    sentence = writing_content[sent_start:sent_end].strip()
                    
                    # Get the note's content as context
                    note = doc_id_map[doc_id]
                    
                    claims_with_context.append({
                        "claim": sentence,
                        "context": note.content,
                        "context_length": len(note.content),
                        "token_count": count_tokens(note.content),
                        "note_id": note.note_id,
                        "doc_id": doc_id
                    })
                    
                except ValueError:
                    logging.warning(f"Could not find position for doc_id '{doc_id}' in writing content.")
            else:
                logging.warning(f"Referenced doc_id '{doc_id}' not found in notes. Available doc_ids: {list(doc_id_map.keys())[:5]}...")
    
    except Exception as e:
        logging.error(f"Error extracting claims from writing: {e}", exc_info=True)
    
    return claims_with_context


async def process_writing_generation(llm_id: str, notes: List[Note], question: str, context_idx: int) -> Dict[str, Any]:
    """
    Process writing generation for a single LLM and its notes.
    Returns a dictionary with the results.
    """
    try:
        # Generate writing with the LLM
        writing_content, writing_details = await generate_writing_with_llm(llm_id, notes, question)
        
        if not writing_content:
            logging.warning(f"Failed to generate writing with {llm_id}")
            return {
                "llm": llm_id,
                "success": False,
                "writing_content": None,
                "claims": [],
                "context_idx": context_idx
            }
        
        # Extract claims from writing
        claims = await extract_claims_from_writing(writing_content, notes)
        
        # Return the results
        return {
            "llm": llm_id,
            "success": True,
            "writing_content": writing_content,
            "claims": claims,
            "context_idx": context_idx
        }
    except Exception as e:
        logging.error(f"Error in process_writing_generation for {llm_id}: {e}")
        return {
            "llm": llm_id,
            "success": False,
            "writing_content": None,
            "claims": [],
            "context_idx": context_idx,
            "error": str(e)
        }


async def process_claim_verification(claim_data: Dict[str, Any], llm_id: str, question: str, context_idx: int, verifier_model: str) -> Dict[str, Any]:
    """
    Process claim verification for a single claim using a specific verifier model.
    Returns a dictionary with the verification results.
    """
    try:
        # Verify the claim against its context
        verification_result = await call_verifier(claim_data["context"], claim_data["claim"], verifier_model)
        
        # Create the base result dictionary
        result = {
            "llm": llm_id,
            "question": question,
            "stage": "writing",
            "context_index": context_idx,
            "claim": claim_data["claim"],
            "context_length": claim_data["context_length"],
            "token_count": claim_data["token_count"],
            "verification_result": verification_result.get("verification_result", "error"),
            "verifier_model": verifier_model,  # Add the verifier model
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Add optional fields if they exist in the verification result
        # These fields will be absent when using --simple-verification
        if "reasoning" in verification_result:
            result["verifier_reasoning"] = verification_result.get("reasoning")
        else:
            result["verifier_reasoning"] = None if args.simple_verification else ""
            
        if "supported_parts" in verification_result:
            result["supported_parts"] = json.dumps(verification_result.get("supported_parts")) if verification_result.get("supported_parts") else ""
        else:
            result["supported_parts"] = ""
            
        if "unsupported_parts" in verification_result:
            result["unsupported_parts"] = json.dumps(verification_result.get("unsupported_parts")) if verification_result.get("unsupported_parts") else ""
        else:
            result["unsupported_parts"] = ""
            
        return result
    except Exception as e:
        logging.error(f"Error in process_claim_verification: {e}")
        return {
            "llm": llm_id,
            "question": question,
            "stage": "writing",
            "context_index": context_idx,
            "claim": claim_data.get("claim", "Unknown claim"),
            "context_length": claim_data.get("context_length", 0),
            "token_count": claim_data.get("token_count", 0),
            "verification_result": "error",
            "verifier_model": verifier_model,  # Add the verifier model
            "verifier_reasoning": f"Error during verification: {str(e)}",
            "supported_parts": "",
            "unsupported_parts": "",
            "timestamp": datetime.datetime.now().isoformat()
        }


async def main():
    """Main function to orchestrate the parallel LLM accuracy evaluation."""
    start_time = datetime.datetime.now()
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    results_filename = os.path.join(RESULTS_DIR, f"accuracy_report_parallel_v3_{timestamp}.csv")
    cost_report_filename = os.path.join(RESULTS_DIR, f"cost_report_parallel_v3_{timestamp}.csv")

    all_results = []
    # Dictionary to track costs by model
    cost_tracking = {}
    
    # Initialize cost tracking for each verifier model
    for verifier_model in VERIFIER_MODELS:
        cost_tracking[verifier_model] = {"model": verifier_model, "total_tokens": 0, "total_cost": 0.0, "calls": 0}
    
    # Initialize cost tracking for each LLM
    for llm_id in LLMS_TO_TEST:
        cost_tracking[llm_id] = {"model": llm_id, "total_tokens": 0, "total_cost": 0.0, "calls": 0}

    logging.info("Starting Parallel LLM Accuracy Evaluation with Multiple Verifiers (v3)...")
    
    # Initialize components once before starting the evaluation
    initialize_components()
    
    logging.info(f"Testing LLMs: {LLMS_TO_TEST}")
    logging.info(f"Verifier LLMs: {VERIFIER_MODELS}")
    logging.info(f"Questions: {len(RESEARCH_QUESTIONS)}")
    
    # Monkey patch the model_dispatcher's dispatch method to track costs
    original_dispatch = global_model_dispatcher.dispatch

    async def dispatch_with_cost_tracking(*args, **kwargs):
        model = kwargs.get('model', 'unknown')
        # --- Added Logging Start ---
        logging.debug(f"Cost Tracking: Calling original dispatch for model: {model}")
        # --- Added Logging End ---
        result, model_details = await original_dispatch(*args, **kwargs)

        # --- Added Logging Start ---
        logging.debug(f"Cost Tracking: Received model_details: {model_details}")
        # Check if model_details exists and access 'cost' using dictionary methods
        cost = 0.0
        if model_details:
            # Use dictionary access .get() which returns None if key is missing
            cost_value = model_details.get('cost')
            if cost_value is not None:
                cost = float(cost_value) # Ensure it's a float
                logging.debug(f"Cost Tracking: Extracted cost from model_details['cost']: {cost}")
            else:
                # Log if the 'cost' key is missing or None, but don't warn if it's just missing (expected behavior)
                if 'cost' in model_details:
                     logging.info(f"Cost Tracking: model_details for model {model} has 'cost' key but its value is None.")
                # else: # Optional: Log if key is entirely missing
                #    logging.debug(f"Cost Tracking: model_details for model {model} does not have 'cost' key.")
        else:
            logging.warning(f"Cost Tracking: model_details object is None for model {model}.")
        # --- Cost extraction logic updated ---

        # Extract usage information if available
        if hasattr(result, 'usage') and result.usage:
            total_tokens = result.usage.total_tokens if hasattr(result.usage, 'total_tokens') else 0
            # Determine which cost tracker to update
            tracker_key = model

            if tracker_key in cost_tracking:
                # Update the cost tracker using the 'cost' variable derived above
                cost_tracking[tracker_key]["total_tokens"] += total_tokens
                cost_tracking[tracker_key]["total_cost"] += cost # Use the cost extracted using .get()
                cost_tracking[tracker_key]["calls"] += 1

                logging.info(f"Cost tracking: {tracker_key} - Tokens: {total_tokens}, Cost: ${cost:.6f} | Total Tokens: {cost_tracking[tracker_key]['total_tokens']}, Total Cost: ${cost_tracking[tracker_key]['total_cost']:.6f}, Calls: {cost_tracking[tracker_key]['calls']}")
            # --- Logging moved inside the 'if tracker_key in cost_tracking' block ---
            # logging.info(f"Cost tracking: {tracker_key} - Total tokens: {cost_tracking[tracker_key]['total_tokens']}, Total cost: ${cost_tracking[tracker_key]['total_cost']:.4f}, Calls: {cost_tracking[tracker_key]['calls']}")

        return result, model_details

    # Replace the dispatch method with our cost-tracking version
    global_model_dispatcher.dispatch = dispatch_with_cost_tracking

    question_index = 0 # Initialize outside loops for error logging
    llm_id = "N/A" # Initialize outside loops for error logging
    total_questions = len(RESEARCH_QUESTIONS)
    try: # Add top-level try block for main loop
        # --- RESTRUCTURED LOOP: Iterate LLMs first, then questions ---
        for llm_id in LLMS_TO_TEST:
            logging.info(f"===== Starting Evaluation for LLM: {llm_id} =====")
            # llm_specific_notes = {} # Store notes generated by this LLM for each question/context - Removed as notes_for_writing is used directly

            for question_index, question in enumerate(RESEARCH_QUESTIONS):
                logging.info(f"--- Processing Question {question_index + 1}/{total_questions} for {llm_id}: {question[:80]}... ---")

                # Generate research context AND initial notes using the specific llm_id
                contexts_notes_tuples = await generate_research_context(question, llm_id) # Pass llm_id
                if not contexts_notes_tuples:
                    logging.warning(f"No research context/notes generated for question '{question}' using LLM {llm_id}")
                    continue # Skip to the next question for this LLM

                logging.info(f"Generated {len(contexts_notes_tuples)} (context, token_count, note) tuples for question using {llm_id}")

                # --- Verify the initial notes generated by llm_id with all verifier models ---
                notes_for_writing = [] # Collect notes for the writing phase
                
                for context_idx, (context, token_count, generated_note) in enumerate(contexts_notes_tuples):
                    logging.info(f"Verifying note {generated_note.note_id} from context {context_idx+1}/{len(contexts_notes_tuples)} (LLM: {llm_id})")
                    
                    # Create verification tasks for each verifier model
                    note_verification_tasks = []
                    for verifier_model in VERIFIER_MODELS:
                        note_verification_tasks.append(
                            process_note_verification(generated_note, context, token_count, llm_id, question, context_idx, verifier_model)
                        )
                    
                    # Run note verification tasks in parallel
                    note_verification_results = await asyncio.gather(*note_verification_tasks)
                    all_results.extend(note_verification_results) # Add note verification results to the main results list
                    
                    notes_for_writing.append(generated_note) # Add note for writing phase

                # --- Proceed to Writing Phase using notes_for_writing ---
                if notes_for_writing:
                    logging.info(f"Generating writing content for question '{question}' using {len(notes_for_writing)} notes from LLM {llm_id}")
                    # Assuming we generate one writing piece per question using all notes from that question's context generation
                    # The context_idx here might represent the 'set' of notes from the initial context generation for the question
                    writing_result = await process_writing_generation(llm_id, notes_for_writing, question, context_idx=0) # Use context_idx=0 for simplicity

                    if writing_result["success"]:
                        claims = writing_result["claims"]
                        logging.info(f"Extracted {len(claims)} claims from writing generated by {llm_id} for question '{question}'")

                        # Debug: Log the actual writing content
                        logging.info(f"Writing content generated: {writing_result['writing_content'][:200]}...")
                        
                        # Verify claims with all verifier models
                        for claim_data in claims:
                            claim_tasks = []
                            for verifier_model in VERIFIER_MODELS:
                                claim_tasks.append(
                                    process_claim_verification(claim_data, llm_id, question, context_idx=0, verifier_model=verifier_model)
                                )
                            
                            claim_verification_results = await asyncio.gather(*claim_tasks)
                            all_results.extend(claim_verification_results) # Add claim verification results
                    else:
                        logging.error(f"Writing generation failed for LLM {llm_id}, question '{question}'. Error: {writing_result.get('error', 'Unknown error')}")
                else:
                    logging.warning(f"No notes available for writing phase for LLM {llm_id}, question '{question}'.")

                logging.info(f"--- Finished Processing Question {question_index + 1}/{total_questions} for {llm_id} ---")
            logging.info(f"===== Finished Evaluation for LLM: {llm_id} =====")

    except Exception as main_loop_error:
        # Log error with potentially incorrect question_index if error happens outside the inner loop
        logging.error(f"--- UNHANDLED EXCEPTION IN MAIN LOOP (around question index {question_index} for LLM {llm_id if 'llm_id' in locals() else 'N/A'}) ---", exc_info=True)
        logging.error(f"--- Attempting to save partial results... ---")
    finally: # Ensure results are saved even if an error occurs
        # --- Save Results ---
        if all_results:
            logging.info(f"Saving {len(all_results)} results to {results_filename}")
            try: # Correctly indented try block for saving results
                # Explicitly define fieldnames to ensure order and inclusion of all columns
                fieldnames = [
                "llm", "question", "stage", "context_index", "claim", 
                "context_length", "token_count", "verification_result", 
                "verifier_model", "verifier_reasoning", "supported_parts", "unsupported_parts", 
                "timestamp"
                ]
                with open(results_filename, 'w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                        writer.writeheader()
                        writer.writerows(all_results)
            except Exception as e: # Correctly indented except block
                logging.error(f"Failed to save results to CSV: {e}")
                # Fallback: try saving as JSON
                json_filename = results_filename.replace(".csv", ".json") # Correct indentation
                logging.info(f"Attempting to save results as JSON: {json_filename}") # Correct indentation
                try: # Correctly indented nested try
                    with open(json_filename, 'w', encoding='utf-8') as jsonfile:
                        json.dump(all_results, jsonfile, indent=2)
                except Exception as je: # Correctly indented nested except
                     logging.error(f"Failed to save results as JSON: {je}")
        else: # Correctly indented else block
            logging.warning("No results were generated during the test run.")

        # --- Save Cost Report ---
        logging.info(f"Saving cost report to {cost_report_filename}")
        try: # Correctly indented try block for saving cost report
            # Convert cost tracking dictionary to a list of records
            cost_records = []
            for model_key, stats in cost_tracking.items(): # Correct indentation
                cost_records.append({ # Correct indentation
                    "model": stats["model"],
                    "total_tokens": stats["total_tokens"],
                    "total_cost": stats["total_cost"],
                    "calls": stats["calls"],
                    "avg_tokens_per_call": stats["total_tokens"] / stats["calls"] if stats["calls"] > 0 else 0,
                    "avg_cost_per_call": stats["total_cost"] / stats["calls"] if stats["calls"] > 0 else 0
                })

            # Define fieldnames for the cost report
            cost_fieldnames = [ # Correct indentation
                "model", "total_tokens", "total_cost", "calls",
                "avg_tokens_per_call", "avg_cost_per_call"
            ]

            # Write the cost report to CSV
            with open(cost_report_filename, 'w', newline='', encoding='utf-8') as csvfile: # Correct indentation
                writer = csv.DictWriter(csvfile, fieldnames=cost_fieldnames)
                writer.writeheader()
                writer.writerows(cost_records)

            # Add a summary row with total cost
            total_cost = sum(stats["total_cost"] for stats in cost_tracking.values()) # Correct indentation
            total_tokens = sum(stats["total_tokens"] for stats in cost_tracking.values()) # Correct indentation
            total_calls = sum(stats["calls"] for stats in cost_tracking.values()) # Correct indentation

            logging.info(f"Total evaluation cost: ${total_cost:.4f}") # Correct indentation
            logging.info(f"Total tokens used: {total_tokens}") # Correct indentation
            logging.info(f"Total API calls: {total_calls}") # Correct indentation

        except Exception as e: # Correctly indented except block
            logging.error(f"Failed to save cost report to CSV: {e}")

    # Calculate and log total execution time
    end_time = datetime.datetime.now()
    execution_time = end_time - start_time
    logging.info(f"Total execution time: {execution_time}")
    logging.info(f"Evaluation complete. Results saved to {results_filename}")
    
    return all_results


if __name__ == "__main__":
    # Create results directory if it doesn't exist
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Run the main function
    asyncio.run(main())
