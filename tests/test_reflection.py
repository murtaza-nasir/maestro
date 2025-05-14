import unittest
import sys
import os
import json
from typing import List, Dict, Any, Optional

# Add the parent directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ai_researcher.agentic_layer.utils.json_utils import (
    convert_string_to_subsection_topic,
    prepare_for_pydantic_validation
)

from ai_researcher.agentic_layer.schemas.reflection import ReflectionOutput, SuggestedSubsectionTopic

class TestReflectionUtils(unittest.TestCase):
    
    def test_convert_string_to_subsection_topic(self):
        """Test that convert_string_to_subsection_topic correctly converts a string to a SuggestedSubsectionTopic."""
        # Test with a simple string
        test_str = "Test Topic"
        result = convert_string_to_subsection_topic(test_str)
        
        # Check that the result is a dictionary with the expected keys
        self.assertIsInstance(result, dict)
        self.assertEqual(result["title"], "Test Topic")
        self.assertEqual(result["description"], "Topics related to Test Topic")
        self.assertEqual(result["relevant_note_ids"], [])
        self.assertEqual(result["reasoning"], "This topic was identified as a potential subsection based on the analyzed notes.")
    
    def test_prepare_for_pydantic_validation_with_string_subsection_topics(self):
        """Test that prepare_for_pydantic_validation correctly handles string values in suggested_subsection_topics."""
        # Create a test data structure with string values in suggested_subsection_topics
        test_data = {
            "overall_assessment": "Test assessment",
            "new_questions": ["Question 1", "Question 2"],
            "suggested_subsection_topics": ["Topic 1", "Topic 2", "Topic 3"],
            "proposed_modifications": [],
            "sections_needing_review": [],
            "critical_issues_summary": None,
            "discard_note_ids": [],
            "generated_thought": "Test thought"
        }
        
        # Process the data
        result = prepare_for_pydantic_validation(test_data, ReflectionOutput)
        
        # Check that the strings were converted to SuggestedSubsectionTopic dictionaries
        self.assertEqual(len(result["suggested_subsection_topics"]), 3)
        for i, topic in enumerate(result["suggested_subsection_topics"]):
            self.assertIsInstance(topic, dict)
            self.assertEqual(topic["title"], f"Topic {i+1}")
            self.assertEqual(topic["description"], f"Topics related to Topic {i+1}")
            self.assertEqual(topic["relevant_note_ids"], [])
            self.assertEqual(topic["reasoning"], "This topic was identified as a potential subsection based on the analyzed notes.")
        
        # Try to create a ReflectionOutput object from the processed data
        try:
            reflection_output = ReflectionOutput(**result)
            self.assertEqual(len(reflection_output.suggested_subsection_topics), 3)
            self.assertEqual(reflection_output.suggested_subsection_topics[0].title, "Topic 1")
        except Exception as e:
            self.fail(f"Failed to create ReflectionOutput object: {e}")
    
    def test_prepare_for_pydantic_validation_with_mixed_subsection_topics(self):
        """Test that prepare_for_pydantic_validation correctly handles a mix of string and dictionary values."""
        # Create a valid subsection topic
        subsection_topic = {
            "title": "Dictionary Topic",
            "description": "Test Description",
            "relevant_note_ids": ["note1", "note2"],
            "reasoning": "Test Reasoning"
        }
        
        # Create a test data structure with a mix of string and dictionary values
        test_data = {
            "overall_assessment": "Test assessment",
            "new_questions": ["Question 1", "Question 2"],
            "suggested_subsection_topics": ["String Topic", subsection_topic],
            "proposed_modifications": [],
            "sections_needing_review": [],
            "critical_issues_summary": None,
            "discard_note_ids": [],
            "generated_thought": "Test thought"
        }
        
        # Process the data
        result = prepare_for_pydantic_validation(test_data, ReflectionOutput)
        
        # Check that the string was converted to a SuggestedSubsectionTopic dictionary
        # and the dictionary was preserved
        self.assertEqual(len(result["suggested_subsection_topics"]), 2)
        
        # Check the converted string
        self.assertIsInstance(result["suggested_subsection_topics"][0], dict)
        self.assertEqual(result["suggested_subsection_topics"][0]["title"], "String Topic")
        
        # Check the preserved dictionary
        self.assertIsInstance(result["suggested_subsection_topics"][1], dict)
        self.assertEqual(result["suggested_subsection_topics"][1]["title"], "Dictionary Topic")
        self.assertEqual(result["suggested_subsection_topics"][1]["description"], "Test Description")
        
        # Try to create a ReflectionOutput object from the processed data
        try:
            reflection_output = ReflectionOutput(**result)
            self.assertEqual(len(reflection_output.suggested_subsection_topics), 2)
            self.assertEqual(reflection_output.suggested_subsection_topics[0].title, "String Topic")
            self.assertEqual(reflection_output.suggested_subsection_topics[1].title, "Dictionary Topic")
        except Exception as e:
            self.fail(f"Failed to create ReflectionOutput object: {e}")

if __name__ == "__main__":
    unittest.main()
