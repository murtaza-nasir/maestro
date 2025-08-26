import unittest
from unittest.mock import MagicMock, patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import logging
from typing import List, Dict, Any, Optional

# Configure logging for tests
logging.basicConfig(level=logging.INFO)

# Import the ReportGenerator class
from ai_researcher.agentic_layer.controller.report_generator import ReportGenerator
from ai_researcher.agentic_layer.schemas.notes import Note

class TestReportGenerator(unittest.TestCase):
    """Test cases for the ReportGenerator class, focusing on citation processing."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock controller
        self.mock_controller = MagicMock()
        # Create the ReportGenerator instance with the mock controller
        self.report_generator = ReportGenerator(self.mock_controller)
        
    def test_map_note_id_to_doc_id(self):
        """Test the _map_note_id_to_doc_id method for different source types."""
        # Create test notes
        test_notes = [
            # Document note
            Note(
                note_id="note_38c7c6a2",
                content="Test document note content",
                source_type="document",
                source_id="f28769c8_chunk_5",
                source_metadata={"title": "Test Document"}
            ),
            # Web note
            Note(
                note_id="note_7525d6d3",
                content="Test web note content",
                source_type="web",
                source_id="https://example.com",
                source_metadata={"title": "Test Web Page"}
            ),
            # Internal note
            Note(
                note_id="note_a3b1c9d0",
                content="Test internal note content",
                source_type="internal",
                source_id="internal_synthesis_1",
                source_metadata={"synthesized_from_notes": ["note_38c7c6a2", "note_7525d6d3"]}
            )
        ]
        
        # Test document note mapping
        doc_id = self.report_generator._map_note_id_to_doc_id("note_38c7c6a2", test_notes)
        self.assertEqual(doc_id, "f28769c8", "Document note ID should map to the base doc_id")
        
        # Test web note mapping
        web_id = self.report_generator._map_note_id_to_doc_id("note_7525d6d3", test_notes)
        # For web sources, we expect a hash of the URL
        import hashlib
        expected_web_id = hashlib.sha1("https://example.com".encode()).hexdigest()[:8]
        self.assertEqual(web_id, expected_web_id, "Web note ID should map to a hash of the URL")
        
        # Test internal note mapping
        internal_id = self.report_generator._map_note_id_to_doc_id("note_a3b1c9d0", test_notes)
        self.assertEqual(internal_id, "internal_synthesis_1", "Internal note ID should map to the source_id")
        
        # Test non-existent note ID
        non_existent_id = self.report_generator._map_note_id_to_doc_id("note_nonexistent", test_notes)
        self.assertIsNone(non_existent_id, "Non-existent note ID should map to None")
        
    def test_process_citations_with_note_ids(self):
        """Test that process_citations correctly handles note IDs in citations."""
        # This is a more complex test that would require mocking the context_manager
        # and other components. For now, we'll just test the mapping functionality.
        # A full integration test would be more appropriate for the process_citations method.
        pass

if __name__ == "__main__":
    unittest.main()
