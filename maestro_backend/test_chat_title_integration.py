#!/usr/bin/env python3
"""
Integration test for chat title generation.
This tests the actual chat endpoint to verify title generation works.
"""

import asyncio
import aiohttp
import json
import sys
import os

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_USER = "testuser"
TEST_PASSWORD = "testpass123"

async def test_chat_title_generation():
    """Test the chat title generation through the actual API."""
    
    async with aiohttp.ClientSession() as session:
        print("🧪 Testing Chat Title Generation Integration")
        print("=" * 50)
        
        # Step 1: Login to get authentication
        print("1. Logging in...")
        login_data = {
            "username": TEST_USER,
            "password": TEST_PASSWORD
        }
        
        async with session.post(f"{BASE_URL}/api/auth/login", data=login_data) as response:
            if response.status != 200:
                print(f"❌ Login failed: {response.status}")
                return False
            
            # Get cookies for authentication
            cookies = session.cookie_jar
            print("✅ Login successful")
        
        # Step 2: Create a new chat
        print("2. Creating new chat...")
        chat_data = {
            "title": "Test Chat for Title Generation"
        }
        
        async with session.post(f"{BASE_URL}/api/chats", json=chat_data) as response:
            if response.status != 200:
                print(f"❌ Chat creation failed: {response.status}")
                return False
            
            chat_response = await response.json()
            chat_id = chat_response["id"]
            print(f"✅ Chat created with ID: {chat_id}")
        
        # Step 3: Send a message that should trigger title generation
        print("3. Sending message to trigger title generation...")
        message_data = {
            "message": "Can you help me research sustainable energy solutions for small businesses?",
            "chat_id": chat_id,
            "conversation_history": [],
            "use_web_search": True
        }
        
        async with session.post(f"{BASE_URL}/api/chat", json=message_data) as response:
            if response.status != 200:
                print(f"❌ Chat message failed: {response.status}")
                response_text = await response.text()
                print(f"Response: {response_text}")
                return False
            
            chat_response = await response.json()
            print(f"✅ AI Response received: {chat_response['response'][:100]}...")
            
            if chat_response.get('action'):
                print(f"   Action detected: {chat_response['action']}")
            if chat_response.get('mission_id'):
                print(f"   Mission created: {chat_response['mission_id']}")
        
        # Step 4: Check if the chat title was updated
        print("4. Checking if chat title was updated...")
        async with session.get(f"{BASE_URL}/api/chats/{chat_id}") as response:
            if response.status != 200:
                print(f"❌ Failed to get chat: {response.status}")
                return False
            
            updated_chat = await response.json()
            new_title = updated_chat["title"]
            
            print(f"   Original title: 'Test Chat for Title Generation'")
            print(f"   Updated title:  '{new_title}'")
            
            if new_title != "Test Chat for Title Generation":
                print("✅ Chat title was updated!")
                
                # Check if it's an intelligent title (not just the user message)
                user_message = message_data["message"]
                if new_title != user_message and not user_message.startswith(new_title):
                    print("✅ Title appears to be intelligently generated!")
                    return True
                else:
                    print("⚠️  Title was updated but appears to be the user message")
                    return False
            else:
                print("❌ Chat title was not updated")
                return False

async def main():
    """Run the integration test."""
    try:
        success = await test_chat_title_generation()
        
        print("\n" + "=" * 50)
        if success:
            print("✅ Integration test PASSED!")
            print("Chat title generation is working correctly.")
        else:
            print("❌ Integration test FAILED!")
            print("Chat title generation needs debugging.")
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
