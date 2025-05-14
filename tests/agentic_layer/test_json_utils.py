import unittest
import sys
import os
import json
from typing import List, Dict, Any, Optional

# Add the parent directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ai_researcher.agentic_layer.utils.json_utils import (
    parse_json_string_recursively,
    sanitize_json_string,
    parse_llm_json_response,
    prepare_for_pydantic_validation,
    extract_non_schema_fields,
    filter_null_values_from_list
)

from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput, SuggestedSubsectionTopic

class TestJsonUtils(unittest.TestCase):
    
    def test_filter_null_values_from_list(self):
        """Test that filter_null_values_from_list correctly removes null values from a list."""
        # Test with a list containing null values
        test_list = [1, None, 2, None, 3]
        result = filter_null_values_from_list(test_list)
        self.assertEqual(result, [1, 2, 3])
        
        # Test with a list containing no null values
        test_list = [1, 2, 3]
        result = filter_null_values_from_list(test_list)
        self.assertEqual(result, [1, 2, 3])
        
        # Test with an empty list
        test_list = []
        result = filter_null_values_from_list(test_list)
        self.assertEqual(result, [])
        
        # Test with a list containing only null values
        test_list = [None, None, None]
        result = filter_null_values_from_list(test_list)
        self.assertEqual(result, [])
    
    def test_prepare_for_pydantic_validation_with_null_in_list(self):
        """Test that prepare_for_pydantic_validation correctly handles null values in lists."""
        # Create a test data structure with a list containing a null value
        test_data = {
            "overall_assessment": "Test assessment",
            "new_questions": ["Question 1", "Question 2"],
            "suggested_subsection_topics": [None],
            "proposed_modifications": [],
            "sections_needing_review": [],
            "critical_issues_summary": None,
            "discard_note_ids": [],
            "generated_thought": "Test thought"
        }
        
        # Process the data
        result = prepare_for_pydantic_validation(test_data, ReflectionOutput)
        
        # Check that the null value was removed from the list
        self.assertEqual(result["suggested_subsection_topics"], [])
        
        # Try to create a ReflectionOutput object from the processed data
        try:
            reflection_output = ReflectionOutput(**result)
            self.assertEqual(reflection_output.suggested_subsection_topics, [])
        except Exception as e:
            self.fail(f"Failed to create ReflectionOutput object: {e}")
    
    def test_prepare_for_pydantic_validation_with_valid_subsection_topic(self):
        """Test that prepare_for_pydantic_validation correctly handles valid subsection topics."""
        # Create a valid subsection topic
        subsection_topic = {
            "title": "Test Title",
            "description": "Test Description",
            "relevant_note_ids": ["note1", "note2"],
            "reasoning": "Test Reasoning"
        }
        
        # Create a test data structure with a valid subsection topic
        test_data = {
            "overall_assessment": "Test assessment",
            "new_questions": ["Question 1", "Question 2"],
            "suggested_subsection_topics": [subsection_topic],
            "proposed_modifications": [],
            "sections_needing_review": [],
            "critical_issues_summary": None,
            "discard_note_ids": [],
            "generated_thought": "Test thought"
        }
        
        # Process the data
        result = prepare_for_pydantic_validation(test_data, ReflectionOutput)
        
        # Check that the subsection topic was preserved
        self.assertEqual(len(result["suggested_subsection_topics"]), 1)
        self.assertEqual(result["suggested_subsection_topics"][0]["title"], "Test Title")
        
        # Try to create a ReflectionOutput object from the processed data
        try:
            reflection_output = ReflectionOutput(**result)
            self.assertEqual(len(reflection_output.suggested_subsection_topics), 1)
            self.assertEqual(reflection_output.suggested_subsection_topics[0].title, "Test Title")
        except Exception as e:
            self.fail(f"Failed to create ReflectionOutput object: {e}")

if __name__ == "__main__":
    unittest.main()
