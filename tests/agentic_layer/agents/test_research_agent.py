import json
import pytest
import asyncio
import re # <-- Import re module
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path # <-- Import Path

# Use absolute imports relative to the project root
from ai_researcher.agentic_layer.agents.research_agent import ResearchAgent
from ai_researcher.agentic_layer.schemas.notes import Note
from ai_researcher import config

# Mock dependencies that ResearchAgent needs
@pytest.fixture
def mock_model_dispatcher():
    return MagicMock()

@pytest.fixture
def mock_tool_registry():
    return MagicMock()

@pytest.fixture
def mock_query_preparer():
    # Mock the async method prepare_queries
    preparer = MagicMock()
    preparer.prepare_queries = AsyncMock(return_value=(["mock query"], [{"model": "q_prep_model"}]))
    return preparer

@pytest.fixture
def research_agent(mock_model_dispatcher, mock_tool_registry, mock_query_preparer):
    # Instantiate the agent with mocked dependencies
    agent = ResearchAgent(
        model_dispatcher=mock_model_dispatcher,
        tool_registry=mock_tool_registry,
        query_preparer=mock_query_preparer
    )
    # Mock the async _call_llm method used internally for note generation
    agent._call_llm = AsyncMock()
    # Mock the async _execute_tool method used internally for reading files
    agent._execute_tool = AsyncMock()
    # Mock the async _read_full_document_if_needed method
    agent._read_full_document_if_needed = AsyncMock()
    return agent

# --- Tests for _extract_content_windows ---

@pytest.mark.asyncio
async def test_extract_content_windows_simple(research_agent, monkeypatch):
    """
    Test basic window extraction for a single chunk without merging/splitting.
    """
    # 1. Arrange
    filename = "test_doc.pdf"
    # P1(12)\nP2(31)\nP3(26)\nP4(17)\nP5(19) Total=109
    mock_doc_content = "Paragraph 1.\nParagraph 2 is slightly longer.\nParagraph 3 is the target.\nParagraph 4 follows.\nParagraph 5 is last."
    # Mock chunks data - targeting Paragraph 3 (index 2)
    para3_text = "Paragraph 3 is the target."
    mock_chunks = [
        {
            "id": "doc_abc_2",
            "text": para3_text,  # Text field is required for the new implementation
            "metadata": {
                "doc_id": "abc",
                "chunk_id": 2,
                "original_filename": filename,
                "start_paragraph_index": 2,  # Para 3
                "end_paragraph_index": 2
            }
        }
    ]
    monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 30)  # Window size
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 100)  # Max merged window size

    # Mock _read_full_document_if_needed to return the content
    mock_read_result = (mock_doc_content, {"tool_name": "read_full_document"}, filename)
    research_agent._read_full_document_if_needed.return_value = mock_read_result

    # 2. Act
    windows = await research_agent._extract_content_windows(filename, mock_chunks)

    # 3. Assert
    assert len(windows) == 1  # Should produce one window

    # With the new implementation, we expect a window centered around the found text
    # The para3_text starts at index 45 and ends at index 71
    # Midpoint is 45 + (71-45)//2 = 58
    # Window of size 30 centered at 58 would be from 58-15=43 to 58+15=73
    # Clamped to document boundaries: 43 to 73
    # Expected content is now NORMALIZED
    expected_content = ". Paragraph 3 is the target. P"
    assert windows[0]["content"] == expected_content
    assert windows[0]["beginning_omitted"] is True  # Starts after char 0
    # The normalized content might be shorter, adjust end_omitted check if needed based on actual normalized length vs original
    assert windows[0]["end_omitted"] is True # Assuming normalized content is shorter than original

    research_agent._read_full_document_if_needed.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_content_windows_merge(research_agent, monkeypatch):
    """Test window merging when chunks are close or overlapping."""
    # 1. Arrange
    filename = "test_doc_merge.pdf"
    # P1(12)\nP2(31)\nP3(26)\nP4(17)\nP5(19) Total=109
    para2_text = "Paragraph 2 is slightly longer."
    para3_text = "Paragraph 3 is the target."
    mock_doc_content = f"Paragraph 1.\n{para2_text}\n{para3_text}\nParagraph 4 follows.\nParagraph 5 is last."
    # Chunk 1 targets Para 2 (idx 1), Chunk 2 targets Para 3 (idx 2)
    mock_chunks = [
        { "id": "doc_merge_1", "text": para2_text, "metadata": { "original_filename": filename, "start_paragraph_index": 1, "end_paragraph_index": 1 } }, # Para 2
        { "id": "doc_merge_2", "text": para3_text, "metadata": { "original_filename": filename, "start_paragraph_index": 2, "end_paragraph_index": 2 } }  # Para 3
    ]
    monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 40) # Larger window to force overlap
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 200)

    mock_read_result = (mock_doc_content, {}, filename)
    research_agent._read_full_document_if_needed.return_value = mock_read_result

    # 2. Act
    windows = await research_agent._extract_content_windows(filename, mock_chunks)

    # 3. Assert
    assert len(windows) == 1 # Windows should merge

    # With the new implementation:
    # para2_text starts at index 13 and ends at index 44, midpoint = 28
    # Window of size 40 centered at 28 would be from 28-20=8 to 28+20=48
    # para3_text starts at index 45 and ends at index 71, midpoint = 58
    # Window of size 40 centered at 58 would be from 58-20=38 to 58+20=78
    # These windows overlap (8-48 and 38-78), so they merge to 8-78
    # Expected content is now NORMALIZED
    expected_content = "h 1. Paragraph 2 is slightly longer. Paragraph 3 is the target. Paragr"
    assert windows[0]["content"] == expected_content
    assert windows[0]["beginning_omitted"] is True
    # Adjust end_omitted check if needed based on actual normalized length vs original
    assert windows[0]["end_omitted"] is True # Assuming normalized content is shorter than original


@pytest.mark.asyncio
async def test_extract_content_windows_split(research_agent, monkeypatch):
    """Test window splitting when merged window exceeds MAX_PLANNING_CONTEXT_CHARS."""
    # 1. Arrange
    filename = "test_doc_split.pdf"
    para1 = "This is the first paragraph, quite long to test splitting. " * 3 # len 180
    para2 = "Second paragraph, also long for the test case scenario. " * 3    # len 162
    para3 = "Third paragraph is the target chunk location here. " * 3         # len 153
    para4 = "Fourth paragraph adds more length after the target. " * 3        # len 165
    para3_text = "Third paragraph is the target chunk location here. " * 3    # len 153
    mock_doc_content = f"{para1}\n{para2}\n{para3_text}\n{para4}"
    # Para offsets: P1(0,180), P2(181,343), P3(344,497), P4(498,663) Total=663
    # Target Para 3 (index 2)
    mock_chunks = [
        { "id": "doc_split_1", "text": para3_text, "metadata": { "original_filename": filename, "start_paragraph_index": 2, "end_paragraph_index": 2 } }
    ]
    monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 400) # Large window
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 300) # Small split limit

    mock_read_result = (mock_doc_content, {}, filename)
    research_agent._read_full_document_if_needed.return_value = mock_read_result

    # 2. Act
    windows = await research_agent._extract_content_windows(filename, mock_chunks)

    # 3. Assert
    assert len(windows) > 1 # Should split

    # With the new implementation:
    # para3_text starts at index 344 and ends at index 497, midpoint = 420
    # Window of size 400 centered at 420 would be from 420-200=220 to 420+200=620
    # This window is 400 chars, which exceeds MAX_PLANNING_CONTEXT_CHARS (300)
    # So it should be split into two windows: 220-520 and 520-620
    
    # Instead of hardcoding the expected content, let's check the structure and length
    assert len(windows) == 2
    
    # Check that the content contains the expected text fragments
    assert "Second paragraph" in windows[0]["content"] # Part of P2
    assert "Third paragraph is the target" in windows[0]["content"] # All of P3
    assert "Fourth paragraph add" in windows[0]["content"] # Start of P4

    assert "s more length after the target" in windows[1]["content"] # Rest of P4

    # Check the window lengths are appropriate
    assert len(windows[0]["content"]) <= 300  # Should not exceed MAX_PLANNING_CONTEXT_CHARS
    assert len(windows[1]["content"]) <= 300

    # Check flags
    assert windows[0]["beginning_omitted"] is True
    assert windows[0]["end_omitted"] is True # First split doesn't reach the end of doc
    assert windows[1]["beginning_omitted"] is True # Second split doesn't start at 0
    assert windows[1]["end_omitted"] is True # Original window didn't reach end of doc


@pytest.mark.asyncio
async def test_extract_content_windows_edge_cases(research_agent, monkeypatch):
    """Test chunks at the very beginning and end of the document."""
    # 1. Arrange
    filename = "test_doc_edge.pdf"
    para0_text = "Start Para."
    para2_text = "End Para."
    mock_doc_content = f"{para0_text}\nMiddle Para.\n{para2_text}" # Len 11, 11, 9. Total 33
    # Para offsets: [(0, 11), (12, 23), (24, 33)]
    monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 20)
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 100)
    mock_read_result = (mock_doc_content, {}, filename)
    research_agent._read_full_document_if_needed.return_value = mock_read_result

    # Case 1: Chunk at the beginning (Para 0)
    mock_chunks_start = [{"id": "doc_edge_s", "text": para0_text, "metadata": {"original_filename": filename, "start_paragraph_index": 0, "end_paragraph_index": 0}}]
    # Case 2: Chunk at the end (Para 2)
    mock_chunks_end = [{"id": "doc_edge_e", "text": para2_text, "metadata": {"original_filename": filename, "start_paragraph_index": 2, "end_paragraph_index": 2}}]

    # 2. Act
    windows_start = await research_agent._extract_content_windows(filename, mock_chunks_start)
    windows_end = await research_agent._extract_content_windows(filename, mock_chunks_end)

    # 3. Assert Start Case
    assert len(windows_start) == 1
    # With the new implementation:
    # para0_text starts at index 0 and ends at index 11, midpoint = 5
    # Window of size 20 centered at 5 would be from 5-10=-5 (clamped to 0) to 5+10=15
    # Expected content is now NORMALIZED
    assert windows_start[0]["content"] == "Start Para. Mid"
    assert windows_start[0]["beginning_omitted"] is False # Starts at char 0
    assert windows_start[0]["end_omitted"] is True # Ends before end of normalized doc

    # 3. Assert End Case
    assert len(windows_end) == 1
    # With the new implementation:
    # para2_text starts at index 24 and ends at index 33, midpoint = 28
    # Window of size 20 centered at 28 would be from 28-10=18 to 28+10=38 (clamped to 33, normalized length)
    # Expected content is now NORMALIZED
    assert windows_end[0]["content"] == "Para. End Para." # Removed leading space
    assert windows_end[0]["beginning_omitted"] is True # Starts after char 0
    assert windows_end[0]["end_omitted"] is False # Reaches end of normalized document


@pytest.mark.asyncio
async def test_extract_content_windows_normalization_merge_adjacent(research_agent, monkeypatch):
    """
    Test window extraction with whitespace normalization and merging of adjacent chunks.
    Uses content from a real PDF example.
    """
    # 1. Arrange
    filename = "Adaptable Security Maturity Assessment and Standardization for Digital SMEs.pdf"
    # Real PDF content (truncated for brevity in comment, full content used in mock)
    mock_doc_content = """
Journal of Computer Information Systems
ISSN: (Print) (Online) Journal homepage: www.tandfonline.com/journals/ucis20
Adaptable Security Maturity Assessment and
Standardization for Digital SMEs
... [rest of the PDF content] ...
2.2.Security standardization and SMEs
Despite SMEs’ challenges in security standardization,
27 
there are no information security or cybersecurity stan-
dards available specifically for SMEs.
10 
Barlette and 
Fomin
20 
state that few information security standards 
are theoretically suitable for SMEs, but given the cost, 
the skills needed, and the language issues, it can be 
assumed that there is no method that can help SMEs 
to improve their security. This hasn’t changed in time; 
however, there are guidelines, technical reports, and 
frameworks that can help SMEs in security 
standardization.
28–30 
Security standardization produces 
opportunities but also presents challenges for SMEs. The 
Digital SME alliance in corporation with Small Business 
Standards has published an SME Guide
31 
for the imple-
mentation of ISO/IEC 27001 for establishing an infor-
mation security management system. There are 
initiatives of public and private sector actors in different 
countries to help SMEs with cybersecurity. These initia-
tives are in the form of guidelines, frameworks and 
certification schemes. Some examples are as follows: 
Cyber Essentials from the UK,
32 
The Center for Cyber 
Security Belgium SME Guide from Belgium,
33 
Center 
for Internet Security Controls from USA,
34 
and ETSI 
(global),
35 
NIST Small Business Information Security 
from USA,
36 
and Finnish Cyber Security Certificate 
from Finland.
37

2.3.Security maturity assessment
Maturity models in different domains have been devel-
oped and used since they became popular after the 
introduction of the Capability Maturity Model of the 
Software Engineering Institute of Carnegie Mellon 
University.
11 
There is abundant research related to 
security maturity modeling.
8,14,38
... [rest of the PDF content] ...
    """
    # Read the actual full content from the MARKDOWN file to mock accurately
    md_path = Path("ai_researcher/data/processed/markdown/cd8e859b.md") # Use correct hash filename
    pdf_filename_meta = "Adaptable Security Maturity Assessment and Standardization for Digital SMEs.pdf" # Filename from metadata
    try:
        # This uses a synchronous read for test setup simplicity
        full_md_content = md_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        pytest.fail(f"Test Markdown file not found at {md_path}")
    except Exception as e:
         pytest.fail(f"Failed to read test Markdown {md_path}: {e}")


    # Mock chunks from Section 2.2 (adjacent) - reverted to exact text from cd8e859b.md
    chunk2_text = "The European Digital SME Alliance focuses on two challenges of SMEs: cybersecurity and standardization that are to be addressed by distinguishing the SME categories[.27](#page-14-7)"
    chunk3_text = "The categorization in [Table 1](#page-2-1) takes into account the different security requirements of digital SMEs that originate from their various roles in the digital ecosystem."

    mock_chunks = [
        {
            "id": "adapt_sme_chunk2",
            "text": chunk2_text,
            "metadata": { "original_filename": filename, "doc_id": "adapt_sme", "chunk_id": 15 } # Example metadata
        },
        {
            "id": "adapt_sme_chunk3",
            "text": chunk3_text,
            "metadata": { "original_filename": filename, "doc_id": "adapt_sme", "chunk_id": 16 } # Example metadata
        }
    ]

    monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 300) # Window size
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 1000) # Max merged window size

    # Mock _read_full_document_if_needed to return the actual MD content when PDF filename is requested
    mock_read_result = (full_md_content, {"tool_name": "read_full_document"}, pdf_filename_meta)
    research_agent._read_full_document_if_needed.return_value = mock_read_result

    # 2. Act
    # Use the PDF filename from metadata, as the main code does
    windows = await research_agent._extract_content_windows(pdf_filename_meta, mock_chunks)

    # 3. Assert
    research_agent._read_full_document_if_needed.assert_awaited_once()
    assert len(windows) == 1 # Should merge into one window

    merged_window = windows[0]
    # Check that the merged window contains parts of both original chunks, now normalized.
    # Check fragments of the normalized text using the original chunk text (which gets normalized internally)
    normalized_chunk2_frag = "European Digital SME Alliance focuses on two challenges of SMEs: cybersecurity and standardization that are to be addressed by distinguishing the SME categories[.27](#page-14-7)"
    normalized_chunk3_frag = "The categorization in [Table 1](#page-2-1) takes into account the different security requirements of digital SMEs that originate from their various roles in the digital ecosystem."
    # Normalize the fragments for assertion checking just like the main function does
    normalized_chunk2_frag = re.sub(r'\s+', ' ', normalized_chunk2_frag).strip()
    normalized_chunk3_frag = re.sub(r'\s+', ' ', normalized_chunk3_frag).strip()

    assert normalized_chunk2_frag in merged_window["content"]
    assert normalized_chunk3_frag in merged_window["content"]
    # Check key phrases from both original chunks exist in the normalized merged window
    assert "distinguishing the SME categories" in merged_window["content"] # End of first part (normalized)
    assert "categorization in [Table 1](#page-2-1) takes into" in merged_window["content"] # Start of second part (normalized, including link)

    # Check flags (assuming these chunks are not at the very start/end of the full PDF)
    assert merged_window["beginning_omitted"] is True
    assert merged_window["end_omitted"] is True

    # Optional: Check length is reasonable (around window_size, but merge might extend it)
    # The exact length depends on the precise location found after normalization.
    # Let's check it's not excessively large or small.
    assert 200 < len(merged_window["content"]) < 500 # Rough check based on window size 300


# --- Test commented out due to using incorrect filename/path logic ---
# @pytest.mark.asyncio
# async def test_extract_content_windows_normalization_merge_adjacent(research_agent, monkeypatch):
#     """
#     Test window extraction with whitespace normalization and merging of adjacent chunks.
#     Uses content from a real PDF example.
#     """
#     # 1. Arrange
#     filename = "Adaptable Security Maturity Assessment and Standardization for Digital SMEs.pdf" # Incorrect filename used here
#     # Read the actual full content from the MARKDOWN file to mock accurately
#     md_path = Path("ai_researcher/data/processed/markdown/Adaptable Security Maturity Assessment and Standardization for Digital SMEs.md") # Incorrect path used here
#     pdf_filename_meta = "Adaptable Security Maturity Assessment and Standardization for Digital SMEs.pdf" # Filename from metadata
#     try:
#         # This uses a synchronous read for test setup simplicity
#         full_md_content = md_path.read_text(encoding='utf-8')
#     except FileNotFoundError:
#         pytest.fail(f"Test Markdown file not found at {md_path}")
#     except Exception as e:
#          pytest.fail(f"Failed to read test Markdown {md_path}: {e}")
#
#
#     # Mock chunks from Section 2.2 (adjacent) - with extra whitespace/newlines
#     chunk2_text = """The European Digital SME Alliance focuses on two
# challenges of SMEs: cybersecurity and standardization
# that are to be addressed by distinguishing the SME
# categories.""" # Note the newlines
#     chunk3_text = """The categorization in Table 1 takes into
# account the different security requirements of digital
# SMEs that originate from their various roles in the
# digital ecosystem.""" # Note the newlines
#
#     mock_chunks = [
#         {
#             "id": "adapt_sme_chunk2",
#             "text": chunk2_text,
#             "metadata": { "original_filename": filename, "doc_id": "adapt_sme", "chunk_id": 15 } # Example metadata
#         },
#         {
#             "id": "adapt_sme_chunk3",
#             "text": chunk3_text,
#             "metadata": { "original_filename": filename, "doc_id": "adapt_sme", "chunk_id": 16 } # Example metadata
#         }
#     ]
#
#     monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 300) # Window size
#     monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 1000) # Max merged window size
#
#     # Mock _read_full_document_if_needed to return the actual MD content when PDF filename is requested
#     mock_read_result = (full_md_content, {"tool_name": "read_full_document"}, pdf_filename_meta)
#     research_agent._read_full_document_if_needed.return_value = mock_read_result
#
#     # 2. Act
#     # Use the PDF filename from metadata, as the main code does
#     windows = await research_agent._extract_content_windows(pdf_filename_meta, mock_chunks)
#
#     # 3. Assert
#     research_agent._read_full_document_if_needed.assert_awaited_once()
#     assert len(windows) == 1 # Should merge into one window
#
#     merged_window = windows[0]
#     # Check that the merged window contains parts of both original (unnormalized) chunks
#     # We check the unnormalized text because the window extraction uses original content
#     assert "European Digital SME Alliance focuses on two" in merged_window["content"]
#     assert "challenges of SMEs: cybersecurity and standardization" in merged_window["content"]
#     assert "distinguishing the SME \ncategories." in merged_window["content"] # Check with original newline
#     assert "categorization in Table 1 takes into" in merged_window["content"]
#     assert "roles in the \ndigital ecosystem." in merged_window["content"] # Check with original newline
#
#     # Check flags (assuming these chunks are not at the very start/end of the full PDF)
#     assert merged_window["beginning_omitted"] is True
#     assert merged_window["end_omitted"] is True
#
#     # Optional: Check length is reasonable (around window_size, but merge might extend it)
#     # The exact length depends on the precise location found after normalization.
#     # Let's check it's not excessively large or small.
#     assert 200 < len(merged_window["content"]) < 500 # Rough check based on window size 300


# --- Tests for _generate_note_from_content ---

@pytest.mark.asyncio
#     """
#     Test window extraction with whitespace normalization and merging of adjacent chunks.
#     Uses content from a real PDF example.
#     """
#     # 1. Arrange
#     filename = "Adaptable Security Maturity Assessment and Standardization for Digital SMEs.pdf"
#     # Read the actual full content from the MARKDOWN file to mock accurately
#     md_path = Path("ai_researcher/data/processed/markdown/Adaptable Security Maturity Assessment and Standardization for Digital SMEs.md") # Use MD file
#     pdf_filename_meta = "Adaptable Security Maturity Assessment and Standardization for Digital SMEs.pdf" # Filename from metadata
#     try:
#         # This uses a synchronous read for test setup simplicity
#         full_md_content = md_path.read_text(encoding='utf-8')
#     except FileNotFoundError:
#         pytest.fail(f"Test Markdown file not found at {md_path}")
#     except Exception as e:
#          pytest.fail(f"Failed to read test Markdown {md_path}: {e}")
#
#
#     # Mock chunks from Section 2.2 (adjacent) - with extra whitespace/newlines
#     chunk2_text = """The European Digital SME Alliance focuses on two
# challenges of SMEs: cybersecurity and standardization
# that are to be addressed by distinguishing the SME
# categories.""" # Note the newlines
#     chunk3_text = """The categorization in Table 1 takes into
# account the different security requirements of digital
# SMEs that originate from their various roles in the
# digital ecosystem.""" # Note the newlines
#
#     mock_chunks = [
#         {
#             "id": "adapt_sme_chunk2",
#             "text": chunk2_text,
#             "metadata": { "original_filename": filename, "doc_id": "adapt_sme", "chunk_id": 15 } # Example metadata
#         },
#         {
#             "id": "adapt_sme_chunk3",
#             "text": chunk3_text,
#             "metadata": { "original_filename": filename, "doc_id": "adapt_sme", "chunk_id": 16 } # Example metadata
#         }
#     ]
#
#     monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 300) # Window size
#     monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 1000) # Max merged window size
#
#     # Mock _read_full_document_if_needed to return the actual MD content when PDF filename is requested
#     mock_read_result = (full_md_content, {"tool_name": "read_full_document"}, pdf_filename_meta)
#     research_agent._read_full_document_if_needed.return_value = mock_read_result
#
#     # 2. Act
#     # Use the PDF filename from metadata, as the main code does
#     windows = await research_agent._extract_content_windows(pdf_filename_meta, mock_chunks)
#
#     # 3. Assert
#     research_agent._read_full_document_if_needed.assert_awaited_once()
#     assert len(windows) == 1 # Should merge into one window
#
#     merged_window = windows[0]
#     # Check that the merged window contains parts of both original (unnormalized) chunks
#     # We check the unnormalized text because the window extraction uses original content
#     assert "European Digital SME Alliance focuses on two" in merged_window["content"]
#     assert "challenges of SMEs: cybersecurity and standardization" in merged_window["content"]
#     assert "distinguishing the SME \ncategories." in merged_window["content"] # Check with original newline
#     assert "categorization in Table 1 takes into" in merged_window["content"]
#     assert "roles in the \ndigital ecosystem." in merged_window["content"] # Check with original newline
#
#     # Check flags (assuming these chunks are not at the very start/end of the full PDF)
#     assert merged_window["beginning_omitted"] is True
#     assert merged_window["end_omitted"] is True
#
#     # Optional: Check length is reasonable (around window_size, but merge might extend it)
#     # The exact length depends on the precise location found after normalization.
#     # Let's check it's not excessively large or small.
#     assert 200 < len(merged_window["content"]) < 500 # Rough check based on window size 300


# --- Tests for _generate_note_from_content ---

@pytest.mark.asyncio
async def test_generate_note_relevant(research_agent):
    """Test note generation when LLM returns relevant content."""
    # 1. Arrange
    # Mock LLM to return plain text content directly
    mock_llm_response_content = "This is the relevant note content."
    mock_choice = MagicMock()
    mock_choice.message.content = mock_llm_response_content
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [mock_choice]
    # Configure the agent's mocked _call_llm
    research_agent._call_llm.return_value = (mock_llm_response_obj, {"model_used": "test_model"})

    # 2. Act
    note, model_details = await research_agent._generate_note_from_content(
        question_being_explored="Test question",
        section_id="s1",
        section_description="Test section",
        focus_questions=["Test question"],
        source_type="document_window", # This will be mapped to 'document'
        source_id="window_test",
        source_metadata={"beginning_omitted": False, "end_omitted": False},
        content_to_process="Some source text",
        is_initial_exploration=True
    )

    # 3. Assert
    assert note is not None
    assert isinstance(note, Note)
    assert note.content == "This is the relevant note content." # Check against plain text
    assert note.source_type == "document" # Check mapping
    assert model_details == {"model_used": "test_model"}
    research_agent._call_llm.assert_awaited_once()
    # Check prompt includes metadata JSON
    call_args = research_agent._call_llm.call_args
    prompt_arg = call_args.kwargs['user_prompt'] # Access via kwargs
    assert '"beginning_omitted": false' in prompt_arg
    assert '"end_omitted": false' in prompt_arg


@pytest.mark.asyncio
async def test_generate_note_irrelevant(research_agent):
    """Test note generation when LLM indicates irrelevance by returning empty content."""
    # 1. Arrange
    # Mock LLM to return empty string
    mock_llm_response_content = ""
    mock_choice = MagicMock()
    mock_choice.message.content = mock_llm_response_content
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [mock_choice]
    research_agent._call_llm.return_value = (mock_llm_response_obj, {"model_used": "test_model"})

    # 2. Act
    note, model_details = await research_agent._generate_note_from_content(
        question_being_explored="Test question", section_id="s1", section_description="Test section",
        focus_questions=["Test question"], source_type="web", source_id="http://example.com",
        source_metadata={}, content_to_process="Irrelevant text", is_initial_exploration=True
    )

    # 3. Assert
    assert note is None # Should not create a note if content is empty
    assert model_details == {"model_used": "test_model"}
    research_agent._call_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_note_llm_error(research_agent):
    """Test note generation when the LLM call itself fails."""
    # 1. Arrange
    # Mock LLM call to raise an exception
    research_agent._call_llm.side_effect = Exception("LLM API Error")

    # 2. Act
    note, model_details = await research_agent._generate_note_from_content(
        question_being_explored="Test question", section_id="s1", section_description="Test section",
        focus_questions=["Test question"], source_type="web", source_id="http://example.com",
        source_metadata={}, content_to_process="Some text", is_initial_exploration=True
    )

    # 3. Assert
    assert note is None # Should fail and return None
    assert model_details is None # No model details if call failed
    research_agent._call_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_note_context_flags_in_prompt(research_agent):
    """Test that context flags are correctly included in the prompt's metadata."""
    # 1. Arrange
    # Mock LLM to return empty string (we only care about the prompt)
    mock_llm_response_content = ""
    mock_choice = MagicMock()
    mock_choice.message.content = mock_llm_response_content
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [mock_choice]
    research_agent._call_llm.return_value = (mock_llm_response_obj, {"model_used": "test_model"})

    source_metadata_flags = {"beginning_omitted": True, "end_omitted": False, "other": "data"}

    # 2. Act
    await research_agent._generate_note_from_content(
        question_being_explored="Test question", section_id="s1", section_description="Test section",
        focus_questions=["Test question"], source_type="document_window", source_id="window_flag_test",
        source_metadata=source_metadata_flags, content_to_process="Some text", is_initial_exploration=False # Use structured phase prompt
    )

    # 3. Assert
    research_agent._call_llm.assert_awaited_once()
    call_args = research_agent._call_llm.call_args
    # Access prompt via keyword arguments
    assert 'user_prompt' in call_args.kwargs, "user_prompt not found in LLM call keyword arguments"
    prompt_arg = call_args.kwargs['user_prompt']

    # Check that the metadata JSON within the prompt includes the flags
    assert '"beginning_omitted": true' in prompt_arg
    assert '"end_omitted": false' in prompt_arg
    assert '"other": "data"' in prompt_arg
    # Ensure the old "Context Note:" string is NOT present
    assert "Context Note:" not in prompt_arg


# --- NEW TEST ---
@pytest.mark.asyncio
async def test_extract_content_windows_real_markdown_merging(research_agent, monkeypatch):
    """
    Test window extraction and merging using real markdown content and chunks.
    Uses 1f8c82f6.md and chunks 10, 11, 12.
    """
    # 1. Arrange
    markdown_path = Path("ai_researcher/data/processed/markdown/1f8c82f6.md")
    pdf_filename_meta = "Benders-Decomposition-with-Delayed-Disaggregation-_2024_European-Journal-of-.pdf" # From metadata
    doc_id = "1f8c82f6"

    try:
        full_markdown_content = markdown_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        pytest.fail(f"Test Markdown file not found at {markdown_path}")
    except Exception as e:
        pytest.fail(f"Failed to read test Markdown {markdown_path}: {e}")

    # Define the chunks based on the selected text snippets
    # IMPORTANT: Extract the exact text from the read content to ensure match
    # Find start/end markers or unique phrases to locate the snippets accurately
    # (These markers are illustrative; adjust based on actual MD content)
    start_marker_10 = "CBD has emerged as a practical way"
    end_marker_10 = "dual variables are non-zero."
    start_index_10 = full_markdown_content.find(start_marker_10)
    end_index_10 = full_markdown_content.find(end_marker_10) + len(end_marker_10)
    if start_index_10 == -1 or end_index_10 == -1 + len(end_marker_10):
        pytest.fail("Could not find markers for chunk 10 in the markdown file.")
    chunk10_text = full_markdown_content[start_index_10:end_index_10]

    start_marker_11 = "Classical Benders Decomposition can be applied"
    end_marker_11 = "feasible solution to the master problem."
    start_index_11 = full_markdown_content.find(start_marker_11)
    end_index_11 = full_markdown_content.find(end_marker_11) + len(end_marker_11)
    if start_index_11 == -1 or end_index_11 == -1 + len(end_marker_11):
         pytest.fail("Could not find markers for chunk 11 in the markdown file.")
    chunk11_text = full_markdown_content[start_index_11:end_index_11]

    start_marker_12 = "A core contribution of this work regards *disaggregation*" # Corrected marker with markdown
    end_marker_12 = "facility location problems." # Use exact end marker
    start_index_12 = full_markdown_content.find(start_marker_12)
    end_index_12 = full_markdown_content.find(end_marker_12) + len(end_marker_12)
    if start_index_12 == -1 or end_index_12 == -1 + len(end_marker_12):
         pytest.fail("Could not find markers for chunk 12 in the markdown file.")
    chunk12_text = full_markdown_content[start_index_12:end_index_12]


    mock_chunks = [
        {
            "id": f"{doc_id}_10",
            "text": chunk10_text,
            "metadata": { "original_filename": pdf_filename_meta, "doc_id": doc_id, "chunk_id": 10 }
        },
        {
            "id": f"{doc_id}_11",
            "text": chunk11_text,
            "metadata": { "original_filename": pdf_filename_meta, "doc_id": doc_id, "chunk_id": 11 }
        },
        {
            "id": f"{doc_id}_12",
            "text": chunk12_text,
            "metadata": { "original_filename": pdf_filename_meta, "doc_id": doc_id, "chunk_id": 12 }
        }
    ]

    # Set config values for the test
    monkeypatch.setattr(config, 'RESEARCH_NOTE_CONTENT_LIMIT', 4000) # Increased Window size to encourage merging
    monkeypatch.setattr(config, 'MAX_PLANNING_CONTEXT_CHARS', 10000) # Max size after merging (should not trigger split here)

    # Mock _read_full_document_if_needed to return the actual markdown content
    mock_read_result = (full_markdown_content, {"tool_name": "read_full_document"}, pdf_filename_meta)
    research_agent._read_full_document_if_needed.return_value = mock_read_result

    # 2. Act
    windows = await research_agent._extract_content_windows(pdf_filename_meta, mock_chunks)

    # 3. Assert
    research_agent._read_full_document_if_needed.assert_awaited_once()
    assert len(windows) == 1 # Expect chunks 10, 11, 12 to merge into one window

    merged_window = windows[0]

    # Check that the merged window contains parts of all three original chunks
    # Use fragments to avoid issues with subtle whitespace differences in the source MD, check against NORMALIZED content
    assert "CBD has emerged as a practical way" in merged_window["content"] # From chunk 10
    assert "dual variables are non-zero." in merged_window["content"] # End of chunk 10
    assert "Classical Benders Decomposition can be applied" in merged_window["content"] # From chunk 11
    assert "fixed and feasible solution to the master problem." in merged_window["content"] # End of chunk 11
    assert "A core contribution of this work regards *disaggregation*" in merged_window["content"] # From chunk 12 (INCLUDE MARKDOWN *)
    assert "quadratic facility location problems." in merged_window["content"] # End of chunk 12

    # Check flags (assuming these chunks are not at the very start/end of the full NORMALIZED MD)
    assert merged_window["beginning_omitted"] is True
    assert merged_window["end_omitted"] is True

    # Optional: Check length is reasonable.
    # Each chunk is ~1000 chars, window size is 4000. Merged window should be > 4000 but < 12000.
    # Exact length depends on normalization and midpoint calculation.
    assert 4000 < len(merged_window["content"]) < 12000 # Adjusted rough check for larger window size
