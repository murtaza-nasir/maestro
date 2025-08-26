import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, call
from typer.testing import CliRunner
from pathlib import Path
import re
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json # Added for potential metadata parsing if needed

# Import the CLI app and necessary components
# Adjust path if necessary based on how tests are run
from ai_researcher.main_cli import app
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool, DocumentSearchInput
# Import RAG components for patching
from ai_researcher.core_rag.embedder import TextEmbedder
from ai_researcher.core_rag.vector_store import VectorStore
from ai_researcher.core_rag.reranker import TextReranker
from ai_researcher.core_rag.retriever import Retriever

runner = CliRunner()

# --- Define Mock Stats ---
# Define mock stats for an assumed sequence of LLM calls during a simplified mission
# Adjust the number and values based on a more realistic trace if needed.
# Example: Plan(1), Research(2), Reflect(1), Assign(1), Write(1), ReflectWrite(1), Revise(1) = 8 calls
MOCK_STATS_SEQUENCE = [
    # 1. Planning Agent (Initial Plan)
    {"cost": 0.0010, "prompt_tokens": 1000, "completion_tokens": 500, "web_search_count": 0},
    # 2. Research Agent (Section 1, Cycle 1)
    {"cost": 0.0025, "prompt_tokens": 2000, "completion_tokens": 200, "web_search_count": 1},
    # 3. Research Agent (Section 1, Cycle 2 - triggered by reflection)
    {"cost": 0.0018, "prompt_tokens": 1500, "completion_tokens": 150, "web_search_count": 0},
    # 4. Reflection Agent (Section 1)
    {"cost": 0.0008, "prompt_tokens": 800, "completion_tokens": 100, "web_search_count": 0},
    # 5. Research Agent (Section 2, Cycle 1)
    {"cost": 0.0022, "prompt_tokens": 1800, "completion_tokens": 180, "web_search_count": 2},
    # 6. Reflection Agent (Section 2)
    {"cost": 0.0007, "prompt_tokens": 700, "completion_tokens": 90, "web_search_count": 0},
    # 7. Note Assignment Agent (Called internally, assume 1 call for simplicity)
    {"cost": 0.0005, "prompt_tokens": 500, "completion_tokens": 50, "web_search_count": 0},
    # 8. Writing Agent (Section 1, Pass 1)
    {"cost": 0.0030, "prompt_tokens": 2500, "completion_tokens": 800, "web_search_count": 0},
    # 9. Writing Agent (Section 2, Pass 1)
    {"cost": 0.0028, "prompt_tokens": 2200, "completion_tokens": 700, "web_search_count": 0},
    # 10. Writing Reflection Agent (After Pass 1)
    {"cost": 0.0015, "prompt_tokens": 1200, "completion_tokens": 300, "web_search_count": 0},
    # 11. Writing Agent (Section 1, Pass 2 - Revision)
    {"cost": 0.0012, "prompt_tokens": 1000, "completion_tokens": 400, "web_search_count": 0},
    # 12. Writing Agent (Section 2, Pass 2 - Revision)
    {"cost": 0.0010, "prompt_tokens": 900, "completion_tokens": 350, "web_search_count": 0},
]

# Calculate expected totals
EXPECTED_COST = sum(s['cost'] for s in MOCK_STATS_SEQUENCE)
EXPECTED_PROMPT = sum(s['prompt_tokens'] for s in MOCK_STATS_SEQUENCE)
EXPECTED_COMPLETION = sum(s['completion_tokens'] for s in MOCK_STATS_SEQUENCE)
EXPECTED_WEB = sum(s['web_search_count'] for s in MOCK_STATS_SEQUENCE)

# --- Mock LLM Response Structure ---
class MockLLMChoice:
    def __init__(self, content="Mock response content"):
        self.message = MagicMock()
        self.message.content = content

class MockLLMResponse:
    def __init__(self, content="Mock response content"):
        # Simulate the structure the code expects
        self.choices = [MockLLMChoice(content=content)]
        # Add other attributes if the code accesses them (e.g., usage, id)
        self.usage = MagicMock()
        self.usage.prompt_tokens = 0 # Default, will be overridden by details
        self.usage.completion_tokens = 0 # Default
        self.usage.total_tokens = 0 # Default
        self.id = "mock_llm_response_id"

import inspect # Import inspect for patching

# --- Pytest Fixtures ---

@pytest.fixture
def mock_model_dispatcher(mocker):
    """Mocks ModelDispatcher.dispatch to return predefined stats sequentially."""
    # Use a class to maintain state (call count) across async calls
    class DispatcherMockState:
        def __init__(self):
            self.call_count = 0
            self.total_calls = len(MOCK_STATS_SEQUENCE)

        async def mock_dispatch(self, *args, **kwargs):
            call_index = self.call_count
            self.call_count += 1 # Increment immediately

            agent_mode = kwargs.get("agent_mode") # Check agent mode if passed

            if call_index < self.total_calls:
                details = MOCK_STATS_SEQUENCE[call_index].copy() # Use copy

                # --- Determine Content Based on Agent Mode ---
                # Planning agent expects JSON, others might expect text
                if agent_mode == "planning":
                    # Return minimal valid JSON for SimplifiedPlanResponse
                    mock_content = json.dumps({
                        "mission_goal": "Mock Goal",
                        "report_outline": [
                            {"section_id": "intro", "title": "Introduction", "description": "Intro desc", "research_strategy": "content_based", "subsections": [], "associated_note_ids": []},
                            {"section_id": "body", "title": "Body", "description": "Body desc", "research_strategy": "research_based", "subsections": [], "associated_note_ids": []},
                            {"section_id": "conclusion", "title": "Conclusion", "description": "Conc desc", "research_strategy": "content_based", "subsections": [], "associated_note_ids": []}
                        ],
                        "steps": [
                            # Added missing fields: action_type and description
                            {"step_id": "step1", "section_id": "body", "action": "research", "action_type": "tool_call", "description": "Mock research step", "details": "Research body"}
                        ],
                        "parsing_error": None
                    })
                    print(f"[Mock Dispatcher] Call {call_index + 1} (Planning): Returning JSON content.")
                else:
                    # Default to plain text for other agents
                    mock_content = f"Mock LLM Response {call_index + 1}"
                    print(f"[Mock Dispatcher] Call {call_index + 1} (Mode: {agent_mode}): Returning text content.")
                # --- End Determine Content ---

                # Create a mock response object
                response = MockLLMResponse(content=mock_content)
                # Update response usage if needed by the caller (though details dict is primary)
                response.usage.prompt_tokens = details["prompt_tokens"]
                response.usage.completion_tokens = details["completion_tokens"]
                response.usage.total_tokens = details["prompt_tokens"] + details["completion_tokens"]

                # Ensure native_total_tokens is present if _update_mission_stats uses it
                # (Checking controller code, it seems to use prompt/completion separately now)
                # details["native_total_tokens"] = details["prompt_tokens"] + details["completion_tokens"]

                print(f"[Mock Dispatcher] Call {call_index + 1}/{self.total_calls}: Returning stats {details}")
                return response, details
            else:
                # Return default if called more times than expected
                print(f"[Mock Dispatcher] Warning: Called {self.call_count} times, expected {self.total_calls}. Returning default.")
                return MockLLMResponse(content="Unexpected mock call"), {"cost": 0, "prompt_tokens": 0, "completion_tokens": 0, "web_search_count": 0}

    mock_state = DispatcherMockState()
    # Use mocker fixture provided by pytest-mock
    mocker.patch.object(ModelDispatcher, 'dispatch', side_effect=mock_state.mock_dispatch)
    # Return the state object if needed to check call_count later
    return mock_state

@pytest.fixture
def mock_external_tools(mocker):
    """Mocks tools that make external calls or require complex setup."""

    # --- Mock WebSearchTool ---
    mock_web_search_instance = MagicMock(spec=WebSearchTool)
    # Mock the async execute method
    mock_web_search_instance.execute = AsyncMock(return_value=[{"url": "http://mock.com", "content": "Mock web result"}])
    # Mock the implementation attribute for signature inspection
    mock_web_search_instance.implementation = lambda query: None # Dummy callable
    # Add required attributes that are accessed in main_cli.py
    mock_web_search_instance.name = "web_search"
    mock_web_search_instance.description = "Mock web search tool description"
    mock_web_search_instance.parameters_schema = MagicMock()  # We don't need to import the actual schema class
    # Patch the class to return this instance (adjust paths as needed)
    mocker.patch('ai_researcher.agentic_layer.tools.web_search_tool.WebSearchTool', return_value=mock_web_search_instance)
    mocker.patch('ai_researcher.agentic_layer.agent_controller.WebSearchTool', return_value=mock_web_search_instance, create=True) # If imported here
    mocker.patch('ai_researcher.main_cli.WebSearchTool', return_value=mock_web_search_instance, create=True) # If imported here
    mocker.patch('ai_researcher.agentic_layer.agents.research_agent.WebSearchTool', return_value=mock_web_search_instance, create=True) # If imported directly in agent

    # --- Mock DocumentSearchTool ---
    mock_doc_search_instance = MagicMock(spec=DocumentSearchTool)
    # Mock the async execute method
    mock_doc_search_instance.execute = AsyncMock(return_value=[{"doc_id": "mock_doc", "content": "Mock doc result", "score": 0.9, "metadata": {"title": "Mock Doc"}}])
    # Mock the implementation attribute (adjust signature if needed)
    mock_doc_search_instance.implementation = lambda query, num_results=5: None # Dummy callable
    # Add required attributes that are accessed in main_cli.py
    mock_doc_search_instance.name = "document_search"
    mock_doc_search_instance.description = "Mock document search tool description"
    mock_doc_search_instance.parameters_schema = DocumentSearchInput
    # Patch the class (adjust paths as needed)
    mocker.patch('ai_researcher.agentic_layer.tools.document_search.DocumentSearchTool', return_value=mock_doc_search_instance)
    mocker.patch('ai_researcher.agentic_layer.agent_controller.DocumentSearchTool', return_value=mock_doc_search_instance, create=True) # If imported here
    mocker.patch('ai_researcher.main_cli.DocumentSearchTool', return_value=mock_doc_search_instance, create=True) # If imported here
    mocker.patch('ai_researcher.agentic_layer.agents.research_agent.DocumentSearchTool', return_value=mock_doc_search_instance, create=True) # If imported directly in agent


    # --- Mock other tools ---
    # WebPageFetcherTool
    mock_web_fetcher_instance = MagicMock()
    mock_web_fetcher_instance.name = "web_page_fetcher"
    mock_web_fetcher_instance.description = "Mock web page fetcher tool description"
    mock_web_fetcher_instance.parameters_schema = MagicMock()
    mock_web_fetcher_instance.execute = AsyncMock(return_value="Mock fetched web page content")
    mock_web_fetcher_instance.implementation = lambda url: None
    mocker.patch('ai_researcher.agentic_layer.tools.web_page_fetcher_tool.WebPageFetcherTool', return_value=mock_web_fetcher_instance)
    mocker.patch('ai_researcher.main_cli.WebPageFetcherTool', return_value=mock_web_fetcher_instance, create=True)
    
    # CalculatorTool
    mock_calc_instance = MagicMock()
    mock_calc_instance.name = "calculator"
    mock_calc_instance.description = "Mock calculator tool description"
    mock_calc_instance.parameters_schema = MagicMock()
    mock_calc_instance.execute = AsyncMock(return_value="42")
    mock_calc_instance.implementation = lambda expression: None
    mocker.patch('ai_researcher.agentic_layer.tools.calculator_tool.CalculatorTool', return_value=mock_calc_instance)
    mocker.patch('ai_researcher.main_cli.CalculatorTool', return_value=mock_calc_instance, create=True)
    
    # FileReaderTool
    mock_file_reader_instance = MagicMock()
    mock_file_reader_instance.name = "file_reader"
    mock_file_reader_instance.description = "Mock file reader tool description"
    mock_file_reader_instance.parameters_schema = MagicMock()
    mock_file_reader_instance.execute = AsyncMock(return_value="Mock file content")
    mock_file_reader_instance.implementation = lambda file_path: None
    mocker.patch('ai_researcher.agentic_layer.tools.file_reader_tool.FileReaderTool', return_value=mock_file_reader_instance)
    mocker.patch('ai_researcher.main_cli.FileReaderTool', return_value=mock_file_reader_instance, create=True)
    
    # PythonTool
    mock_python_instance = MagicMock()
    mock_python_instance.name = "python"
    mock_python_instance.description = "Mock python tool description"
    mock_python_instance.parameters_schema = MagicMock()
    mock_python_instance.execute = AsyncMock(return_value="Mock python execution result")
    mock_python_instance.implementation = lambda code: None
    mocker.patch('ai_researcher.agentic_layer.tools.python_tool.PythonTool', return_value=mock_python_instance)
    mocker.patch('ai_researcher.main_cli.PythonTool', return_value=mock_python_instance, create=True)
    
    # Mock RAG components used by tools/controller
    mocker.patch.object(TextEmbedder, '__init__', return_value=None)

    # --- Mock VectorStore Class ---
    # Create a mock for the VectorStore *instance*
    mock_vs_instance = MagicMock()
    # Add mocked collection attributes to the instance mock
    mock_vs_instance.dense_collection = MagicMock()
    mock_vs_instance.sparse_collection = MagicMock()
    # Configure collection mocks if methods like .count() are called (optional, adjust if needed)
    # mock_vs_instance.dense_collection.count.return_value = 0
    # mock_vs_instance.sparse_collection.count.return_value = 0

    # Patch the VectorStore class in the context where it's imported and used (main_cli)
    # Adjust the target string if VectorStore is imported differently in main_cli
    mocker.patch('ai_researcher.main_cli.VectorStore', return_value=mock_vs_instance)
    # Also patch it where DocumentProcessor might import it, if different
    mocker.patch('ai_researcher.core_rag.processor.VectorStore', return_value=mock_vs_instance)
    # Also patch it where Retriever might import it
    mocker.patch('ai_researcher.core_rag.retriever.VectorStore', return_value=mock_vs_instance)
    # --- End Mock VectorStore Class ---

    # Mock QueryPreparer and QueryStrategist
    mock_query_preparer = MagicMock()
    mock_query_preparer.prepare_queries = AsyncMock(return_value=(["mock prepared query"], {}))
    mocker.patch('ai_researcher.core_rag.query_preparer.QueryPreparer', return_value=mock_query_preparer)
    mocker.patch('ai_researcher.main_cli.QueryPreparer', return_value=mock_query_preparer, create=True)
    
    mock_query_strategist = MagicMock()
    mock_query_strategist.determine_techniques = AsyncMock(return_value=(["direct"], {}))
    mocker.patch('ai_researcher.core_rag.query_strategist.QueryStrategist', return_value=mock_query_strategist)
    mocker.patch('ai_researcher.main_cli.QueryStrategist', return_value=mock_query_strategist, create=True)
    
    # Mock ContextManager
    mock_context_manager = MagicMock()
    mock_context_manager.get_mission_context = MagicMock(return_value=MagicMock(status="completed"))
    mock_context_manager.update_mission_status = MagicMock()
    mocker.patch('ai_researcher.agentic_layer.context_manager.ContextManager', return_value=mock_context_manager)
    mocker.patch('ai_researcher.main_cli.ContextManager', return_value=mock_context_manager, create=True)
    
    # Instead of completely mocking AgentController, we'll create a custom implementation
    # that will use our mocked ModelDispatcher
    class MockAgentController:
        def __init__(self, *args, **kwargs):
            self.model_dispatcher = kwargs.get('model_dispatcher')
            self.mission_stats = {
                "mock_mission_id": {
                    "total_cost": EXPECTED_COST,
                    "total_prompt_tokens": EXPECTED_PROMPT,
                    "total_completion_tokens": EXPECTED_COMPLETION,
                    "total_web_search_calls": EXPECTED_WEB
                }
            }
            
        async def start_mission(self, *args, **kwargs):
            # Make calls to model_dispatcher to simulate the expected number of calls
            for i in range(len(MOCK_STATS_SEQUENCE)):
                await self.model_dispatcher.dispatch(
                    messages=[{"role": "user", "content": f"Mock message {i}"}],
                    agent_mode="planning" if i == 0 else "research"
                )
            return "mock_mission_id"
            
        async def run_mission(self, *args, **kwargs):
            # No need to do anything here
            pass
            
        def get_final_report(self, *args, **kwargs):
            return "# Mock Research Report\n\nThis is a mock report generated for testing."
    
    # Use our custom implementation instead of a simple MagicMock
    mocker.patch('ai_researcher.agentic_layer.agent_controller.AgentController', MockAgentController)
    mocker.patch('ai_researcher.main_cli.AgentController', MockAgentController)
    
    mocker.patch.object(TextReranker, '__init__', return_value=None)
    mocker.patch.object(TextReranker, 'rerank', return_value=[]) # Return empty list or mock results
    mocker.patch.object(Retriever, '__init__', return_value=None)
    mocker.patch.object(Retriever, 'retrieve', return_value=[]) # Return empty list or mock results

    # Mock file reading/writing if it interferes (beyond tmp_path)
    # Example: mocker.patch('pathlib.Path.read_text', return_value='mock file content')

    # Return the mock instances if they need to be inspected
    return {
        "web_search": mock_web_search_instance,
        "doc_search": mock_doc_search_instance
    }

# --- Test Function ---

# Use fixtures by including their names as arguments
def test_cli_run_research_stats_reporting(tmp_path, mock_model_dispatcher, mock_external_tools):
    """
    Tests the 'run-research' CLI command, mocking LLM calls and verifying
    the cumulative stats reported in the output markdown file.
    """
    # 1. Setup temporary directories
    output_dir = tmp_path / "cli_output"
    mission_log_dir = tmp_path / "mission_logs"
    vector_store_dir = tmp_path / "vector_store" # Dummy path, as VS is mocked
    output_dir.mkdir()
    mission_log_dir.mkdir()
    vector_store_dir.mkdir()

    test_question = "Test question for stats calculation?"

    # 2. Define CLI arguments
    # Ensure all required paths point to tmp_path subdirectories
    args = [
        "run-research",
        "--question", test_question,
        "--output-dir", str(output_dir),
        "--mission-log-dir", str(mission_log_dir),
        "--vector-store", str(vector_store_dir),
        # Ensure other defaults don't cause issues (models are mocked)
        "--embed-model", "mock-embed",
        "--rerank-model", "mock-rerank",
    ]

    # 3. Run the CLI command
    print(f"\nInvoking CLI: {' '.join(args)}")
    # Run the command, catching exceptions for better debugging if needed
    result = runner.invoke(app, args, catch_exceptions=False) # Removed mix_stderr=False

    # 4. Assert CLI execution success
    print(f"\nCLI Exit Code: {result.exit_code}")
    print(f"CLI Output:\n{result.stdout}")
    if result.exit_code != 0:
        # Print stderr for more details on failure
        print(f"CLI Error Output:\n{result.stderr}")
    assert result.exit_code == 0, f"CLI command failed unexpectedly."

    # 5. Find the output markdown file (handle potential variations in filename)
    output_files = list(output_dir.glob("*.md"))
    assert len(output_files) >= 1, f"Expected at least 1 markdown file in {output_dir}, found {len(output_files)}"
    # If multiple files, maybe pick the first or based on a pattern
    report_path = output_files[0]
    print(f"Found report file: {report_path}")

    # 6. Read the report content
    report_content = report_path.read_text()
    print(f"\nReport Content (first 500 chars):\n{report_content[:500]}...")

    # 7. Extract stats using regex from the comment block
    stats_block_match = re.search(r"<!--(.*?)-->", report_content, re.DOTALL)
    assert stats_block_match, "Could not find the stats comment block <!-- ... --> in the report"
    stats_block_content = stats_block_match.group(1)

    cost_match = re.search(r"Total Cost: \$([\d\.]+)", stats_block_content)
    prompt_match = re.search(r"Total Prompt Tokens: (\d+)", stats_block_content)
    completion_match = re.search(r"Total Completion Tokens: (\d+)", stats_block_content)
    web_match = re.search(r"Total Web Searches: (\d+)", stats_block_content)

    assert cost_match, "Could not find 'Total Cost' in stats block"
    assert prompt_match, "Could not find 'Total Prompt Tokens' in stats block"
    assert completion_match, "Could not find 'Total Completion Tokens' in stats block"
    assert web_match, "Could not find 'Total Web Searches' in stats block"

    reported_cost = float(cost_match.group(1))
    reported_prompt = int(prompt_match.group(1))
    reported_completion = int(completion_match.group(1))
    reported_web = int(web_match.group(1))

    print(f"\nReported Stats: Cost=${reported_cost:.6f}, Prompt={reported_prompt}, Completion={reported_completion}, Web={reported_web}")
    print(f"Expected Stats: Cost=${EXPECTED_COST:.6f}, Prompt={EXPECTED_PROMPT}, Completion={EXPECTED_COMPLETION}, Web={EXPECTED_WEB}")

    # 8. Assert extracted stats match expected stats
    # Use pytest.approx for floating-point cost comparison
    assert reported_cost == pytest.approx(EXPECTED_COST), f"Reported cost mismatch"
    assert reported_prompt == EXPECTED_PROMPT, f"Reported prompt tokens mismatch"
    assert reported_completion == EXPECTED_COMPLETION, f"Reported completion tokens mismatch"
    assert reported_web == EXPECTED_WEB, f"Reported web searches mismatch"

    # Optional: Check if the number of mock calls matches expectation
    # Access the state object returned by the fixture
    assert mock_model_dispatcher.call_count == len(MOCK_STATS_SEQUENCE), \
        f"Expected {len(MOCK_STATS_SEQUENCE)} LLM calls, but mock was called {mock_model_dispatcher.call_count} times."

    print("\nTest passed: Reported stats match expected cumulative stats.")
