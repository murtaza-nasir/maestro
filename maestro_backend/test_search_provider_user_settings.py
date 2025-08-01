#!/usr/bin/env python3
"""
Test script to verify that search provider settings are correctly picked up from user settings.
"""

import sys
import os
import asyncio
from unittest.mock import patch, MagicMock

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_researcher.dynamic_config import (
    get_web_search_provider, get_tavily_api_key, get_linkup_api_key
)
from ai_researcher.user_context import set_current_user
from database.models import User

def test_search_provider_fallback_to_env():
    """Test that search provider settings fall back to environment variables when no user is set."""
    print("=== Testing fallback to environment variables ===")
    
    # Clear any existing user context
    set_current_user(None)
    
    # Test with environment variables
    with patch.dict(os.environ, {
        'WEB_SEARCH_PROVIDER': 'tavily',
        'TAVILY_API_KEY': 'test-tavily-key',
        'LINKUP_API_KEY': 'test-linkup-key'
    }):
        provider = get_web_search_provider()
        tavily_key = get_tavily_api_key()
        linkup_key = get_linkup_api_key()
        
        print(f"Provider: {provider}")
        print(f"Tavily API Key: {tavily_key}")
        print(f"LinkUp API Key: {linkup_key}")
        
        assert provider == "tavily", f"Expected 'tavily', got '{provider}'"
        assert tavily_key == "test-tavily-key", f"Expected 'test-tavily-key', got '{tavily_key}'"
        assert linkup_key == "test-linkup-key", f"Expected 'test-linkup-key', got '{linkup_key}'"
        
        print("✅ Environment variable fallback working correctly")

def test_search_provider_user_settings():
    """Test that search provider settings are correctly picked up from user settings."""
    print("\n=== Testing user settings override ===")
    
    # Create a mock user with search settings
    mock_user = MagicMock(spec=User)
    mock_user.settings = {
        "search": {
            "provider": "linkup",
            "tavily_api_key": "user-tavily-key",
            "linkup_api_key": "user-linkup-key"
        }
    }
    
    # Set the user context
    set_current_user(mock_user)
    
    # Test that user settings override environment variables
    with patch.dict(os.environ, {
        'WEB_SEARCH_PROVIDER': 'tavily',
        'TAVILY_API_KEY': 'env-tavily-key',
        'LINKUP_API_KEY': 'env-linkup-key'
    }):
        provider = get_web_search_provider()
        tavily_key = get_tavily_api_key()
        linkup_key = get_linkup_api_key()
        
        print(f"Provider: {provider}")
        print(f"Tavily API Key: {tavily_key}")
        print(f"LinkUp API Key: {linkup_key}")
        
        assert provider == "linkup", f"Expected 'linkup', got '{provider}'"
        assert tavily_key == "user-tavily-key", f"Expected 'user-tavily-key', got '{tavily_key}'"
        assert linkup_key == "user-linkup-key", f"Expected 'user-linkup-key', got '{linkup_key}'"
        
        print("✅ User settings override working correctly")

def test_search_provider_partial_user_settings():
    """Test behavior when user has partial search settings."""
    print("\n=== Testing partial user settings ===")
    
    # Create a mock user with partial search settings
    mock_user = MagicMock(spec=User)
    mock_user.settings = {
        "search": {
            "provider": "tavily",
            "tavily_api_key": "user-tavily-key"
            # No linkup_api_key
        }
    }
    
    # Set the user context
    set_current_user(mock_user)
    
    # Test that user settings are used where available, env vars for missing
    with patch.dict(os.environ, {
        'WEB_SEARCH_PROVIDER': 'linkup',
        'TAVILY_API_KEY': 'env-tavily-key',
        'LINKUP_API_KEY': 'env-linkup-key'
    }):
        provider = get_web_search_provider()
        tavily_key = get_tavily_api_key()
        linkup_key = get_linkup_api_key()
        
        print(f"Provider: {provider}")
        print(f"Tavily API Key: {tavily_key}")
        print(f"LinkUp API Key: {linkup_key}")
        
        assert provider == "tavily", f"Expected 'tavily', got '{provider}'"
        assert tavily_key == "user-tavily-key", f"Expected 'user-tavily-key', got '{tavily_key}'"
        assert linkup_key == "env-linkup-key", f"Expected 'env-linkup-key', got '{linkup_key}'"
        
        print("✅ Partial user settings working correctly")

def test_search_provider_no_settings():
    """Test behavior when user has no search settings."""
    print("\n=== Testing user with no search settings ===")
    
    # Create a mock user with no search settings
    mock_user = MagicMock(spec=User)
    mock_user.settings = {}
    
    # Set the user context
    set_current_user(mock_user)
    
    # Test that environment variables are used
    with patch.dict(os.environ, {
        'WEB_SEARCH_PROVIDER': 'tavily',
        'TAVILY_API_KEY': 'env-tavily-key',
        'LINKUP_API_KEY': 'env-linkup-key'
    }):
        provider = get_web_search_provider()
        tavily_key = get_tavily_api_key()
        linkup_key = get_linkup_api_key()
        
        print(f"Provider: {provider}")
        print(f"Tavily API Key: {tavily_key}")
        print(f"LinkUp API Key: {linkup_key}")
        
        assert provider == "tavily", f"Expected 'tavily', got '{provider}'"
        assert tavily_key == "env-tavily-key", f"Expected 'env-tavily-key', got '{tavily_key}'"
        assert linkup_key == "env-linkup-key", f"Expected 'env-linkup-key', got '{linkup_key}'"
        
        print("✅ No search settings fallback working correctly")

async def test_web_search_tool_initialization():
    """Test that WebSearchTool can be initialized with user settings."""
    print("\n=== Testing WebSearchTool initialization ===")
    
    # Create a mock user with search settings
    mock_user = MagicMock(spec=User)
    mock_user.settings = {
        "search": {
            "provider": "tavily",
            "tavily_api_key": "user-tavily-key"
        }
    }
    
    # Set the user context
    set_current_user(mock_user)
    
    # Mock the TavilyClient to avoid actual API calls
    with patch('ai_researcher.agentic_layer.tools.web_search_tool.TavilyClient') as mock_tavily:
        mock_tavily_instance = MagicMock()
        mock_tavily.return_value = mock_tavily_instance
        
        from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
        
        try:
            tool = WebSearchTool()
            print(f"Tool provider: {tool.provider}")
            print(f"Tool client: {tool.client}")
            
            assert tool.provider == "tavily", f"Expected 'tavily', got '{tool.provider}'"
            assert tool.client is mock_tavily_instance, "Client should be the mocked TavilyClient instance"
            
            # Verify TavilyClient was called with the user's API key
            mock_tavily.assert_called_once_with(api_key="user-tavily-key")
            
            print("✅ WebSearchTool initialization working correctly")
            
        except Exception as e:
            print(f"❌ WebSearchTool initialization failed: {e}")
            raise

def main():
    """Run all tests."""
    print("Testing Search Provider User Settings Integration")
    print("=" * 50)
    
    try:
        test_search_provider_fallback_to_env()
        test_search_provider_user_settings()
        test_search_provider_partial_user_settings()
        test_search_provider_no_settings()
        asyncio.run(test_web_search_tool_initialization())
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! Search provider user settings are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    finally:
        # Clean up user context
        set_current_user(None)

if __name__ == "__main__":
    main()
