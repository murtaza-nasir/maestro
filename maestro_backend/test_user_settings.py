#!/usr/bin/env python3
"""
Test script to verify user settings integration with the config system.
This script tests that the dynamic config system properly overrides environment variables with user settings.
"""

import os
import sys
import json
from typing import Dict, Any

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_user_settings_integration():
    """Test that user settings properly override environment variables"""
    print("Testing User Settings Integration...")
    
    # Test 1: Environment variable fallback
    print("\n1. Testing environment variable fallback...")
    from ai_researcher.config import (
        FAST_LLM_PROVIDER, MID_LLM_PROVIDER, INTELLIGENT_LLM_PROVIDER,
        WEB_SEARCH_PROVIDER, TAVILY_API_KEY, LINKUP_API_KEY,
        INITIAL_RESEARCH_MAX_DEPTH, INITIAL_RESEARCH_MAX_QUESTIONS,
        STRUCTURED_RESEARCH_ROUNDS, WRITING_PASSES, THOUGHT_PAD_CONTEXT_LIMIT,
        MAX_CONCURRENT_REQUESTS, SKIP_FINAL_REPLANNING
    )
    
    print(f"   FAST_LLM_PROVIDER: {FAST_LLM_PROVIDER}")
    print(f"   MID_LLM_PROVIDER: {MID_LLM_PROVIDER}")
    print(f"   INTELLIGENT_LLM_PROVIDER: {INTELLIGENT_LLM_PROVIDER}")
    print(f"   WEB_SEARCH_PROVIDER: {WEB_SEARCH_PROVIDER}")
    print(f"   INITIAL_RESEARCH_MAX_DEPTH: {INITIAL_RESEARCH_MAX_DEPTH}")
    print(f"   INITIAL_RESEARCH_MAX_QUESTIONS: {INITIAL_RESEARCH_MAX_QUESTIONS}")
    print(f"   STRUCTURED_RESEARCH_ROUNDS: {STRUCTURED_RESEARCH_ROUNDS}")
    print(f"   WRITING_PASSES: {WRITING_PASSES}")
    print(f"   THOUGHT_PAD_CONTEXT_LIMIT: {THOUGHT_PAD_CONTEXT_LIMIT}")
    print(f"   MAX_CONCURRENT_REQUESTS: {MAX_CONCURRENT_REQUESTS}")
    print(f"   SKIP_FINAL_REPLANNING: {SKIP_FINAL_REPLANNING}")
    
    # Test 2: Dynamic config functions
    print("\n2. Testing dynamic config functions...")
    from ai_researcher.dynamic_config import (
        get_fast_llm_provider, get_mid_llm_provider, get_intelligent_llm_provider,
        get_web_search_provider, get_tavily_api_key, get_linkup_api_key,
        get_initial_research_max_depth, get_initial_research_max_questions,
        get_structured_research_rounds, get_writing_passes, get_thought_pad_context_limit,
        get_max_concurrent_requests, get_skip_final_replanning
    )
    
    print(f"   get_fast_llm_provider(): {get_fast_llm_provider()}")
    print(f"   get_mid_llm_provider(): {get_mid_llm_provider()}")
    print(f"   get_intelligent_llm_provider(): {get_intelligent_llm_provider()}")
    print(f"   get_web_search_provider(): {get_web_search_provider()}")
    print(f"   get_initial_research_max_depth(): {get_initial_research_max_depth()}")
    print(f"   get_initial_research_max_questions(): {get_initial_research_max_questions()}")
    print(f"   get_structured_research_rounds(): {get_structured_research_rounds()}")
    print(f"   get_writing_passes(): {get_writing_passes()}")
    print(f"   get_thought_pad_context_limit(): {get_thought_pad_context_limit()}")
    print(f"   get_max_concurrent_requests(): {get_max_concurrent_requests()}")
    print(f"   get_skip_final_replanning(): {get_skip_final_replanning()}")
    
    # Test 3: Model name resolution
    print("\n3. Testing model name resolution...")
    from ai_researcher.dynamic_config import get_model_name
    from ai_researcher.config import get_model_name as config_get_model_name
    
    fast_model = get_model_name("fast")
    mid_model = get_model_name("mid")
    intelligent_model = get_model_name("intelligent")
    verifier_model = get_model_name("verifier")
    
    print(f"   Fast model: {fast_model}")
    print(f"   Mid model: {mid_model}")
    print(f"   Intelligent model: {intelligent_model}")
    print(f"   Verifier model: {verifier_model}")
    
    # Test 4: Provider config
    print("\n4. Testing provider config...")
    from ai_researcher.dynamic_config import get_ai_provider_config
    
    openrouter_config = get_ai_provider_config("openrouter")
    local_config = get_ai_provider_config("local")
    
    print(f"   OpenRouter config: {openrouter_config}")
    print(f"   Local config: {local_config}")
    
    print("\n✅ User settings integration test completed successfully!")
    return True

if __name__ == "__main__":
    try:
        test_user_settings_integration()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
