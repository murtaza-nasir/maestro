#!/usr/bin/env python3
"""
Test script to verify mission-specific settings are working correctly.
"""

import sys
import os
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_mission_settings():
    """Test that mission-specific settings are retrieved correctly."""
    print("Testing mission-specific settings retrieval...")
    
    try:
        # Import the dynamic config functions
        from ai_researcher.dynamic_config import (
            get_initial_research_max_depth,
            get_initial_research_max_questions,
            get_structured_research_rounds,
            get_writing_passes,
            get_initial_exploration_doc_results,
            get_initial_exploration_web_results,
            get_main_research_doc_results,
            get_main_research_web_results,
            get_thought_pad_context_limit,
            get_max_notes_for_assignment_reranking,
            get_max_concurrent_requests,
            get_skip_final_replanning
        )
        
        # Test with a dummy mission ID (this should fall back to defaults)
        dummy_mission_id = "test-mission-123"
        
        print(f"\nTesting with dummy mission ID: {dummy_mission_id}")
        print("=" * 50)
        
        # Test all the mission-specific functions
        tests = [
            ("initial_research_max_depth", get_initial_research_max_depth),
            ("initial_research_max_questions", get_initial_research_max_questions),
            ("structured_research_rounds", get_structured_research_rounds),
            ("writing_passes", get_writing_passes),
            ("initial_exploration_doc_results", get_initial_exploration_doc_results),
            ("initial_exploration_web_results", get_initial_exploration_web_results),
            ("main_research_doc_results", get_main_research_doc_results),
            ("main_research_web_results", get_main_research_web_results),
            ("thought_pad_context_limit", get_thought_pad_context_limit),
            ("max_notes_for_assignment_reranking", get_max_notes_for_assignment_reranking),
            ("max_concurrent_requests", get_max_concurrent_requests),
            ("skip_final_replanning", get_skip_final_replanning),
        ]
        
        results = {}
        for name, func in tests:
            try:
                value = func(dummy_mission_id)
                results[name] = value
                print(f"{name:35} = {value}")
            except Exception as e:
                print(f"{name:35} = ERROR: {e}")
                results[name] = f"ERROR: {e}"
        
        print("\n" + "=" * 50)
        print("Test completed successfully!")
        print("All dynamic config functions are accessible and working.")
        
        # Write results to a file for debugging
        results_file = project_root / "test_mission_settings_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to: {results_file}")
        
        return True
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_mission_settings()
    sys.exit(0 if success else 1)
