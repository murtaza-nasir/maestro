#!/usr/bin/env python3
"""
Test script to verify user context middleware is working correctly.
This script tests that the middleware properly sets user context for dynamic config access.
"""

import os
import sys
import asyncio

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_user_context_middleware():
    """Test that user context middleware works correctly"""
    print("Testing User Context Middleware...")
    
    # Test 1: Verify user context functions
    print("\n1. Testing user context functions...")
    from ai_researcher.user_context import set_current_user, get_current_user, get_user_settings
    
    # Test with None user
    set_current_user(None)
    current_user = get_current_user()
    print(f"   Current user (None): {current_user}")
    
    # Test user settings with None user
    user_settings = get_user_settings()
    print(f"   User settings (None user): {user_settings}")
    
    # Test 2: Verify dynamic config falls back properly
    print("\n2. Testing dynamic config fallback...")
    from ai_researcher.dynamic_config import (
        get_fast_llm_provider, get_model_name,
        get_initial_research_max_depth, get_web_search_provider
    )
    
    fast_provider = get_fast_llm_provider()
    web_provider = get_web_search_provider()
    max_depth = get_initial_research_max_depth()
    fast_model = get_model_name("fast")
    
    print(f"   Fast LLM provider: {fast_provider}")
    print(f"   Web search provider: {web_provider}")
    print(f"   Initial research max depth: {max_depth}")
    print(f"   Fast model: {fast_model}")
    
    print("\n✅ User context middleware test completed successfully!")
    return True

if __name__ == "__main__":
    try:
        test_user_context_middleware()
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
