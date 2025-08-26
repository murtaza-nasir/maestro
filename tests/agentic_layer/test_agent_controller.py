import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pytest
import asyncio
import unittest
from unittest.mock import MagicMock, patch, call, AsyncMock # Import call and AsyncMock
import re
from typing import List, Dict, Optional

# Adjust imports based on your project structure
from ai_researcher.agentic_layer.agent_controller import AgentController
from ai_researcher.agentic_layer.context_manager import ContextManager, MissionContext
# Import SimplifiedPlanResponse as well
from ai_researcher.agentic_layer.schemas.planning import SimplifiedPlan, ReportSection, SimplifiedPlanResponse
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher.core_rag.retriever import Retriever # <-- Import Retriever
from ai_researcher.core_rag.reranker import TextReranker # Need reranker for init
from ai_researcher import config # Import config

# Mock dependencies needed for AgentController instantiation
@pytest.fixture
def mock_model_dispatcher():
    return MagicMock()

@pytest.fixture
def mock_tool_registry():
    return MagicMock()

@pytest.fixture
def mock_retriever():
    return MagicMock(spec=Retriever)

@pytest.fixture
def mock_reranker():
    # Mock the reranker dependency added in AgentController.__init__
    return MagicMock(spec=TextReranker)

@pytest.fixture
def mock_context_manager():
    # Provide a mock context manager for tests
    return MagicMock(spec=ContextManager)

@pytest.fixture
def agent_controller(mock_model_dispatcher, mock_context_manager, mock_tool_registry, mock_retriever, mock_reranker):
    # Instantiate AgentController with all mocked dependencies
    # Patch the _register_core_tools method to avoid issues during init
    with patch.object(AgentController, '_register_core_tools', return_value=None):
        controller = AgentController(
            model_dispatcher=mock_model_dispatcher,
            context_manager=mock_context_manager,
            tool_registry=mock_tool_registry,
            retriever=mock_retriever,
            reranker=mock_reranker # Pass the mocked reranker
        )
    return controller

# Helper to create mock notes with specific content lengths
def create_mock_note(note_id: str, content_len: int) -> Note:
    """Creates a mock Note with specified content length."""
    return Note(
        note_id=note_id,
        content="A" * content_len, # Content of specified length
        source_type="document",
        source_id=f"doc_{note_id}",
        source_metadata={},
        potential_sections=["test"],
        timestamp="2024-01-01T12:00:00"
    )

# Helper to create a mock PlanningAgent response
def create_mock_plan_response(batch_num: int) -> SimplifiedPlanResponse:
    """Creates a mock SimplifiedPlanResponse for testing."""
    return SimplifiedPlanResponse(
        mission_goal="Test Goal",
        report_outline=[ReportSection(section_id=f"sec_{batch_num}", title=f"Section {batch_num}", description=f"Desc {batch_num}")],
        steps=[]
    )

# --- Tests for _generate_preliminary_outline Batching ---

@pytest.mark.asyncio
async def test_generate_preliminary_outline_no_batching(agent_controller, mock_context_manager, monkeypatch):
    """Test outline generation when total chars are below the limit."""
    # 1. Arrange
    mission_id = "test_no_batch"
    user_request = "Test request"
    # Notes well below limit
    notes = [create_mock_note("n1", 100), create_mock_note("n2", 150)]
    total_chars = 250
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 300) # Limit > total_chars

    # Mock context manager methods
    mock_context_manager.get_scratchpad.return_value = "Initial scratchpad"
    # Mock PlanningAgent.run to return a successful response
    mock_plan_response = create_mock_plan_response(1)
    mock_planning_agent_run = AsyncMock(return_value=(mock_plan_response, {"model": "m1"}, "Updated scratchpad"))
    agent_controller.planning_agent.run = mock_planning_agent_run # Attach mock

    # 2. Act
    result_plan = await agent_controller._generate_preliminary_outline(
        mission_id, user_request, notes, "Initial scratchpad"
    )

    # 3. Assert
    assert result_plan is not None
    assert isinstance(result_plan, SimplifiedPlan) # Check final type
    mock_planning_agent_run.assert_awaited_once() # Should be called only once
    # Check the context passed to the single call
    call_args, call_kwargs = mock_planning_agent_run.call_args
    assert call_kwargs.get("final_outline_context") is not None
    assert call_kwargs.get("revision_context") is None
    assert "Batch 1/1" in call_kwargs["final_outline_context"]
    # Check for the specific Note ID format in the context string
    # Corrected assertion to match actual note ID format
    assert "- Note ID: n1" in call_kwargs["final_outline_context"]
    assert "- Note ID: n2" in call_kwargs["final_outline_context"]
    # Check scratchpad update
    mock_context_manager.update_scratchpad.assert_called_once_with(mission_id, "Updated scratchpad")


@pytest.mark.asyncio
async def test_generate_preliminary_outline_with_batching(agent_controller, mock_context_manager, monkeypatch):
    """Test outline generation with multiple batches due to character limit."""
    # 1. Arrange
    mission_id = "test_batching"
    user_request = "Test request batching"
    # Notes that will exceed the limit and require 2 batches
    notes = [
        create_mock_note("n1", 100),
        create_mock_note("n2", 120), # Batch 1 total = 220
        create_mock_note("n3", 50)   # Batch 2 total = 50
    ]
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 250) # Limit

    mock_context_manager.get_scratchpad.side_effect = ["Initial scratchpad", "Scratchpad after batch 1"]
    # Mock PlanningAgent.run to return different responses for each call
    mock_plan_response_b1 = create_mock_plan_response(1)
    mock_plan_response_b2 = create_mock_plan_response(2) # Simulate revision
    mock_planning_agent_run = AsyncMock(side_effect=[
        (mock_plan_response_b1, {"model": "m1"}, "Scratchpad after batch 1"), # Call 1 (Batch 1)
        (mock_plan_response_b2, {"model": "m2"}, "Scratchpad after batch 2")  # Call 2 (Batch 2)
    ])
    agent_controller.planning_agent.run = mock_planning_agent_run

    # 2. Act
    result_plan = await agent_controller._generate_preliminary_outline(
        mission_id, user_request, notes, "Initial scratchpad"
    )

    # 3. Assert
    assert result_plan is not None
    assert isinstance(result_plan, SimplifiedPlan)
    # Check the final plan reflects the last batch's response
    assert result_plan.report_outline[0].section_id == "sec_2"

    # Check PlanningAgent calls
    assert mock_planning_agent_run.await_count == 2 # Called twice

    # Call 1 assertions
    call1_args, call1_kwargs = mock_planning_agent_run.await_args_list[0]
    assert call1_kwargs.get("final_outline_context") is not None
    assert call1_kwargs.get("revision_context") is None
    assert "Batch 1/2" in call1_kwargs["final_outline_context"]
    # Check for the specific Note ID format in the context string
    # Corrected assertion to match actual note ID format
    assert "- Note ID: n1" in call1_kwargs["final_outline_context"]
    assert "- Note ID: n2" in call1_kwargs["final_outline_context"]
    assert "- Note ID: n3" not in call1_kwargs["final_outline_context"] # Check n3 is NOT in batch 1
    assert call1_kwargs.get("agent_scratchpad") == "Initial scratchpad"

    # Call 2 assertions
    call2_args, call2_kwargs = mock_planning_agent_run.await_args_list[1]
    assert call2_kwargs.get("final_outline_context") is None
    assert call2_kwargs.get("revision_context") is not None
    assert "Batch 2/2" in call2_kwargs["revision_context"]
    # Corrected assertion to check for the formatted note ID string
    assert "- Note ID: n3" in call2_kwargs["revision_context"]
    assert "- Note ID: n1" not in call2_kwargs["revision_context"] # Check n1 is not in batch 2 context
    # Check if previous outline is in revision context
    assert "Current Report Outline Structure" in call2_kwargs["revision_context"]
    assert "sec_1" in call2_kwargs["revision_context"] # From mock_plan_response_b1
    assert call2_kwargs.get("agent_scratchpad") == "Scratchpad after batch 1"

    # Check scratchpad updates
    assert mock_context_manager.update_scratchpad.call_count == 2
    mock_context_manager.update_scratchpad.assert_has_calls([
        call(mission_id, "Scratchpad after batch 1"),
        call(mission_id, "Scratchpad after batch 2")
    ])


@pytest.mark.asyncio
async def test_generate_preliminary_outline_batching_failure(agent_controller, mock_context_manager, monkeypatch):
    """Test handling when a subsequent batch fails during planning."""
    # 1. Arrange
    mission_id = "test_batch_fail"
    user_request = "Test request batch fail"
    notes = [
        create_mock_note("n1", 100),
        create_mock_note("n2", 120), # Batch 1
        create_mock_note("n3", 50)   # Batch 2 (will fail)
    ]
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 250)

    mock_context_manager.get_scratchpad.side_effect = ["Initial scratchpad", "Scratchpad after batch 1"]
    mock_plan_response_b1 = create_mock_plan_response(1)
    # Simulate failure on the second call (returns None for plan)
    mock_planning_agent_run = AsyncMock(side_effect=[
        (mock_plan_response_b1, {"model": "m1"}, "Scratchpad after batch 1"),
        (None, {"model": "m2", "error": "LLM Error"}, "Scratchpad unchanged") # Simulate failure
    ])
    agent_controller.planning_agent.run = mock_planning_agent_run

    # 2. Act
    result_plan = await agent_controller._generate_preliminary_outline(
        mission_id, user_request, notes, "Initial scratchpad"
    )

    # 3. Assert
    # Should return the plan from the last successful batch (batch 1)
    assert result_plan is not None
    assert isinstance(result_plan, SimplifiedPlan)
    assert result_plan.report_outline[0].section_id == "sec_1" # From batch 1 response

    # Check PlanningAgent calls
    assert mock_planning_agent_run.await_count == 2 # Called twice

    # Check logging for the failure (mock context_manager.log_execution_step if needed)
    # This requires more complex mocking of context_manager or checking logs directly


# --- Tests for Citation Processing (Original Tests Refactored for pytest) ---

# Helper to create mock notes for citation tests
def _create_mock_citation_note(note_id: str, doc_id: str, chunk_id: int, title: str, year: int, authors: List[str]) -> Note:
    """Helper to create a mock Note object for citation tests."""
    return Note(
        note_id=note_id,
        content=f"Content for {note_id} from doc {doc_id}",
        source_type="document",
        source_id=f"{doc_id}_{chunk_id}", # Simulate source_id format
        source_metadata={
            "doc_id": doc_id, # Keep original doc_id easily accessible if needed
            "chunk_id": chunk_id,
            "title": title,
            "publication_year": year,
            "authors": str(authors) # Store as string list representation, as seen in example
        },
        potential_sections=["test_section"],
        timestamp="2024-01-01T12:00:00"
    )

def setup_mock_context_for_citations(mock_cm: MagicMock, mission_id: str, notes: List[Note], report_content: Dict[str, str], plan: Optional[SimplifiedPlan] = None):
    """Sets up the mock context manager for citation tests."""
    if plan is None:
        # Create a default plan if none provided
        plan = SimplifiedPlan(
            mission_goal="Test Goal",
            report_outline=[
                ReportSection(section_id=sec_id, title=f"Section {sec_id.upper()}", description=f"Desc {sec_id}")
                for sec_id in report_content.keys()
            ],
            steps=[]
        )

    mock_mission = MagicMock(spec=MissionContext)
    mock_mission.mission_id = mission_id
    mock_mission.plan = plan
    mock_mission.report_content = report_content
    mock_mission.notes = notes # Store notes directly on mock if needed, though get_notes is mocked

    mock_cm.get_mission_context.return_value = mock_mission
    mock_cm.get_notes.return_value = notes


def test_basic_citation_processing(agent_controller, mock_context_manager):
    """Test replacing [doc_id] placeholders and generating references."""
    mission_id = "test_cite_basic"
    doc1_id = "f1a2b3c4"
    doc2_id = "d5e6f7a8"
    notes = [
        _create_mock_citation_note("note_001", doc1_id, 1, "Doc One Title", 2023, ["Author A"]),
        _create_mock_citation_note("note_002", doc2_id, 5, "Doc Two Title", 2022, ["Author B", "Author C"]),
        _create_mock_citation_note("note_003", doc1_id, 10, "Doc One Title", 2023, ["Author A"]), # Another note from doc1
    ]
    report_content = {
        "intro": f"This is the introduction mentioning doc one [{doc1_id}].",
        "body": f"The body discusses doc two [{doc2_id}] and revisits doc one [{doc1_id}]."
    }
    setup_mock_context_for_citations(mock_context_manager, mission_id, notes, report_content)

    # Run the method under test
    success = agent_controller._process_citations(mission_id)
    assert success is True

    # Check what was stored
    mock_context_manager.store_final_report.assert_called_once()
    stored_report = mock_context_manager.store_final_report.call_args[0][1]

    # --- More Robust Assertions ---
    # 1. Find the assigned numbers using regex
    matches = re.findall(r'\[(\d+)\]', stored_report)
    assert len(matches) >= 3, "Should find at least 3 numerical citations"
    num_for_intro_doc1 = matches[0]
    num_for_body_doc2 = matches[1]
    num_for_body_doc1 = matches[2]

    # 2. Check consistency: both mentions of doc1 should have the same number
    assert num_for_intro_doc1 == num_for_body_doc1, "Both mentions of doc1 should have the same citation number"
    # 3. Check difference: doc1 and doc2 should have different numbers
    assert num_for_intro_doc1 != num_for_body_doc2, "doc1 and doc2 should have different citation numbers"

    # 4. Check reference list content (order might vary, so check presence)
    expected_ref1_content = f"{num_for_intro_doc1}. Author A. (2023). *Doc One Title*."
    expected_ref2_content = f"{num_for_body_doc2}. Author B, Author C. (2022). *Doc Two Title*."
    assert expected_ref1_content in stored_report
    assert expected_ref2_content in stored_report
    assert "## References" in stored_report

    # Check status update
    mock_context_manager.update_mission_status.assert_called_with(mission_id, "completed")


def test_no_placeholders(agent_controller, mock_context_manager):
    """Test behavior when no placeholders are present."""
    mission_id = "test_no_cite"
    doc1_id = "f1a2b3c4"
    notes = [
        _create_mock_citation_note("note_001", doc1_id, 1, "Doc One Title", 2023, ["Author A"]),
    ]
    report_content = {
        "intro": "This text has no placeholders.",
    }
    # Create a simple plan for context
    plan = SimplifiedPlan(mission_goal="G", report_outline=[ReportSection(section_id="intro", title="Intro", description="D")], steps=[])
    setup_mock_context_for_citations(mock_context_manager, mission_id, notes, report_content, plan)

    success = agent_controller._process_citations(mission_id)
    assert success is True

    # Check stored report - should not have references section
    mock_context_manager.store_final_report.assert_called_once()
    stored_report = mock_context_manager.store_final_report.call_args[0][1]
    # Note: The exact output depends on _build_draft_from_context, assuming simple structure
    expected_text = "# Intro\n\nThis text has no placeholders." # Simplified expected output
    assert expected_text in stored_report.strip()
    assert "## References" not in stored_report

    # Check status update
    mock_context_manager.update_mission_status.assert_called_with(mission_id, "completed")


def test_placeholder_for_unknown_doc(agent_controller, mock_context_manager):
    """Test behavior when a placeholder refers to a doc_id not in notes metadata."""
    mission_id = "test_unknown_cite"
    doc1_id = "f1a2b3c4"
    unknown_doc_id = "deadbeef"
    notes = [
        _create_mock_citation_note("note_001", doc1_id, 1, "Doc One Title", 2023, ["Author A"]),
    ]
    report_content = {
        "intro": f"Known doc [{doc1_id}] and unknown doc [{unknown_doc_id}].",
    }
    setup_mock_context_for_citations(mock_context_manager, mission_id, notes, report_content)

    # Run the method - we no longer expect a warning during replacement
    success = agent_controller._process_citations(mission_id)
    assert success is True

    # Check stored report - unknown placeholder should be replaced, and reference added
    mock_context_manager.store_final_report.assert_called_once()
    stored_report = mock_context_manager.store_final_report.call_args[0][1]

    # Find the numbers assigned
    matches = re.findall(r'\[(\d+)\]', stored_report)
    assert len(matches) == 2, "Should find 2 numerical citations"
    num_known = matches[0]
    num_unknown = matches[1]
    assert num_known != num_unknown

    # Check text replacement (simplified check)
    assert f"Known doc [{num_known}]" in stored_report
    assert f"unknown doc [{num_unknown}]" in stored_report

    # Check reference list content
    expected_ref_known = f"{num_known}. Author A. (2023). *Doc One Title*."
    expected_ref_unknown = f"{num_unknown}. Unknown Document ({unknown_doc_id})" # Check fallback reference
    assert expected_ref_known in stored_report
    assert expected_ref_unknown in stored_report
    assert "## References" in stored_report

    # Check status update
    mock_context_manager.update_mission_status.assert_called_with(mission_id, "completed")


def test_missing_context_elements(agent_controller, mock_context_manager):
    """Test failure modes when context, plan, or content is missing."""
    mission_id = "test_missing_ctx"

    # Case 1: Missing context
    mock_context_manager.reset_mock() # Reset mocks for clean state
    mock_context_manager.get_mission_context.return_value = None
    success = agent_controller._process_citations(mission_id)
    assert success is False
    mock_context_manager.store_final_report.assert_not_called()

    # Case 2: Missing plan
    mock_context_manager.reset_mock()
    mock_mission_no_plan = MagicMock(spec=MissionContext)
    mock_mission_no_plan.plan = None
    mock_mission_no_plan.report_content = {"intro": "Test"}
    mock_context_manager.get_mission_context.return_value = mock_mission_no_plan
    success = agent_controller._process_citations(mission_id)
    assert success is False
    mock_context_manager.store_final_report.assert_not_called()

    # Case 3: Missing report_content
    mock_context_manager.reset_mock()
    mock_mission_no_content = MagicMock(spec=MissionContext)
    mock_mission_no_content.plan = SimplifiedPlan(mission_goal="G", report_outline=[], steps=[])
    mock_mission_no_content.report_content = None
    mock_context_manager.get_mission_context.return_value = mock_mission_no_content
    success = agent_controller._process_citations(mission_id)
    assert success is False
    mock_context_manager.store_final_report.assert_not_called()

# Note: If using pytest, the `if __name__ == '__main__':` block is not needed.
# You would run tests using the `pytest` command in the terminal.
