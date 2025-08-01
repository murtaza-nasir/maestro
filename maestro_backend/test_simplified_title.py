#!/usr/bin/env python3
"""
Test the simplified chat title generation.
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.chat_title_service import ChatTitleService
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher

async def test_simplified_title_generation():
    """Test the simplified title generation directly."""
    
    print("🧪 Testing Simplified Chat Title Generation")
    print("=" * 50)
    
    try:
        # Initialize the model dispatcher
        model_dispatcher = ModelDispatcher()
        
        # Create the title service
        title_service = ChatTitleService(model_dispatcher)
        
        # Test cases
        test_cases = [
            {
                "user_message": "Can you help me research sustainable energy solutions for small businesses?",
                "ai_response": "I can help you research that. I'll now generate some initial research questions for us to review."
            },
            {
                "user_message": "What are some things to do in Wichita?",
                "ai_response": "I can help you research that. I'll now generate some initial research questions for us to review."
            },
            {
                "user_message": "I need to analyze the latest trends in artificial intelligence for healthcare applications",
                "ai_response": "I can help you research that. I'll now generate some initial research questions for us to review."
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i}. Testing title generation:")
            print(f"   User: {test_case['user_message']}")
            print(f"   AI: {test_case['ai_response'][:50]}...")
            
            try:
                title = await title_service.generate_title(
                    test_case['user_message'], 
                    test_case['ai_response']
                )
                print(f"   Generated Title: '{title}'")
                
                # Check if it's a good title (not just the user message)
                if title != test_case['user_message'] and len(title) <= 60:
                    print(f"   ✅ Title looks good!")
                else:
                    print(f"   ⚠️  Title might need improvement")
                    
            except Exception as e:
                print(f"   ❌ Error generating title: {e}")
        
        print(f"\n✅ Simplified title generation test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run the test."""
    success = await test_simplified_title_generation()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
