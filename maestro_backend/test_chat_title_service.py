#!/usr/bin/env python3
"""
Test script for the ChatTitleService functionality.
This script tests the title generation logic without requiring a full API setup.
"""

import asyncio
import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.chat_title_service import ChatTitleService
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from database.models import Chat, Message
from datetime import datetime

class MockModelDispatcher:
    """Mock model dispatcher for testing."""
    
    async def dispatch_request(self, agent_role, model_type, messages, max_tokens=None, temperature=None):
        """Mock dispatch request that returns a sample title."""
        user_content = messages[0]["content"] if messages else ""
        
        # Extract key information from the prompt to generate a mock title
        if "Wichita" in user_content and "restaurants" in user_content:
            return {"content": "Wichita Restaurant Research"}
        elif "AI" in user_content and "ethics" in user_content:
            return {"content": "AI Ethics Literature Review"}
        elif "climate" in user_content.lower():
            return {"content": "Climate Change Analysis"}
        elif "python" in user_content.lower() and "performance" in user_content.lower():
            return {"content": "Python Performance Optimization"}
        else:
            # Generic research title
            return {"content": "Research Topic Analysis"}

class MockChat:
    """Mock chat object for testing."""
    
    def __init__(self, chat_id, title, messages):
        self.id = chat_id
        self.title = title
        self.messages = messages

class MockMessage:
    """Mock message object for testing."""
    
    def __init__(self, role, content):
        self.role = role
        self.content = content
        self.created_at = datetime.now()

async def test_title_generation():
    """Test the title generation functionality."""
    print("Testing ChatTitleService...")
    
    # Create mock dispatcher and service
    mock_dispatcher = MockModelDispatcher()
    title_service = ChatTitleService(mock_dispatcher)
    
    # Test cases
    test_cases = [
        {
            "name": "Restaurant Research",
            "user_message": "Can you help me find the best places to eat in Wichita?",
            "ai_response": "I'll help you research restaurants in Wichita. Let me generate some initial research questions...",
            "expected_contains": "Wichita"
        },
        {
            "name": "AI Ethics Research",
            "user_message": "I need to research AI ethics for my thesis",
            "ai_response": "I can help you conduct comprehensive research on AI ethics. This is an important and evolving field...",
            "expected_contains": "AI Ethics"
        },
        {
            "name": "Climate Research",
            "user_message": "What are the latest findings on climate change impacts?",
            "ai_response": "I'll help you research the latest climate change findings and impacts...",
            "expected_contains": "Climate"
        }
    ]
    
    print("\n=== Title Generation Tests ===")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"User: {test_case['user_message']}")
        print(f"AI: {test_case['ai_response'][:50]}...")
        
        try:
            generated_title = await title_service.generate_title(
                test_case['user_message'],
                test_case['ai_response']
            )
            
            print(f"Generated Title: '{generated_title}'")
            
            if test_case['expected_contains'].lower() in generated_title.lower():
                print("✅ PASS - Title contains expected content")
            else:
                print("❌ FAIL - Title doesn't contain expected content")
                
        except Exception as e:
            print(f"❌ ERROR - {e}")

def test_should_update_title():
    """Test the should_update_title logic."""
    print("\n=== Should Update Title Tests ===")
    
    title_service = ChatTitleService(None)  # No dispatcher needed for this test
    
    test_cases = [
        {
            "name": "Title is first user message",
            "title": "Can you help me find the best places to eat in Wichita?",
            "messages": [
                MockMessage("user", "Can you help me find the best places to eat in Wichita?"),
                MockMessage("assistant", "I'll help you research restaurants...")
            ],
            "should_update": True
        },
        {
            "name": "Title is truncated first user message",
            "title": "Can you help me find the best places to eat...",
            "messages": [
                MockMessage("user", "Can you help me find the best places to eat in Wichita? I'm looking for authentic local cuisine."),
                MockMessage("assistant", "I'll help you research restaurants...")
            ],
            "should_update": True
        },
        {
            "name": "Title is generic",
            "title": "New Chat",
            "messages": [
                MockMessage("user", "Research AI ethics"),
                MockMessage("assistant", "I'll help you research AI ethics...")
            ],
            "should_update": True
        },
        {
            "name": "Title already updated",
            "title": "AI Ethics Literature Review",
            "messages": [
                MockMessage("user", "Research AI ethics"),
                MockMessage("assistant", "I'll help you research AI ethics...")
            ],
            "should_update": False
        },
        {
            "name": "Not enough messages",
            "title": "Research question",
            "messages": [
                MockMessage("user", "Research question")
            ],
            "should_update": False
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"Title: '{test_case['title']}'")
        print(f"Messages: {len(test_case['messages'])}")
        
        mock_chat = MockChat("test-chat", test_case['title'], test_case['messages'])
        
        result = title_service.should_update_title(mock_chat)
        expected = test_case['should_update']
        
        if result == expected:
            print(f"✅ PASS - Should update: {result}")
        else:
            print(f"❌ FAIL - Expected: {expected}, Got: {result}")

async def main():
    """Run all tests."""
    print("🧪 ChatTitleService Test Suite")
    print("=" * 50)
    
    # Test title generation
    await test_title_generation()
    
    # Test should update logic
    test_should_update_title()
    
    print("\n" + "=" * 50)
    print("✅ Test suite completed!")
    print("\nNote: This is a basic test using mock objects.")
    print("For full integration testing, use the actual API endpoints.")

if __name__ == "__main__":
    asyncio.run(main())
