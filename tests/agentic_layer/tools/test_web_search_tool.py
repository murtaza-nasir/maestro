import unittest
from unittest.mock import patch, MagicMock, AsyncMock # Import AsyncMock
import sys
from pathlib import Path
import json
import asyncio # Import asyncio for async tests
import httpx # Import httpx for exception types

# Add project root to sys.path for imports
project_root = Path(__file__).resolve().parents[3] # Go up three levels from tests/agentic_layer/tools
sys.path.insert(0, str(project_root))
print(f"Added to sys.path for testing: {project_root}")

from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool, WebSearchInput

# --- Mock Data ---
MOCK_SEARXNG_URL = "http://mock-searxng:8080"
MOCK_QUERY = "test query"
MOCK_NUM_RESULTS = 2

# Mock successful SearXNG JSON response
MOCK_SUCCESS_RESPONSE_JSON = {
    "results": [
        {
            "title": "Test Result 1",
            "url": "http://example.com/result1",
            "content": "This is the snippet for result 1." # SearXNG uses 'content' for snippet
        },
        {
            "title": "Test Result 2",
            "url": "http://example.com/result2",
            "content": "Snippet for result number two."
        }
    ],
    "query": MOCK_QUERY,
    "number_of_results": 2
}

# Mock SearXNG response for no results
MOCK_NO_RESULTS_RESPONSE_JSON = {
    "results": [],
    "query": MOCK_QUERY,
    "number_of_results": 0
}

# Use unittest.IsolatedAsyncioTestCase for async tests
class TestWebSearchTool(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Instantiate the tool and start patches."""
        self.search_tool = WebSearchTool(searxng_base_url=MOCK_SEARXNG_URL)
        # Start patcher for httpx.AsyncClient.get - use AsyncMock as it's an async method
        self.patcher = patch('httpx.AsyncClient.get', new_callable=AsyncMock)
        self.mock_async_get = self.patcher.start()
        # Ensure the patch is stopped automatically after the test
        self.addCleanup(self.patcher.stop)

    async def test_execute_success(self):
        """Test successful execution path."""
        # Configure the mock response for the async mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SUCCESS_RESPONSE_JSON
        # Mock raise_for_status to do nothing on success
        mock_response.raise_for_status = MagicMock()
        self.mock_async_get.return_value = mock_response

        # Execute the tool (await the async call)
        results_dict = await self.search_tool.execute(query=MOCK_QUERY, num_results=MOCK_NUM_RESULTS)

        # Assertions (Corrected Indentation)
        self.mock_async_get.assert_awaited_once() # Check if the async mock was awaited
        # Check call arguments (httpx passes url as first arg, then keywords)
        call_args, call_kwargs = self.mock_async_get.call_args
        self.assertTrue(call_args[0].startswith(MOCK_SEARXNG_URL)) # Check base URL passed as first arg
        # Correct assertion: Check the value associated with the 'q' key in params
        self.assertEqual(call_kwargs['params']['q'], MOCK_QUERY)
        self.assertEqual(call_kwargs['params']['format'], 'json')

        self.assertIsInstance(results_dict, dict)
        self.assertNotIn("error", results_dict)
        self.assertIn("results", results_dict)
        results_list = results_dict["results"]
        self.assertEqual(len(results_list), MOCK_NUM_RESULTS)
        self.assertEqual(results_list[0]['title'], "Test Result 1")
        self.assertEqual(results_list[0]['url'], "http://example.com/result1")
        # Check if 'content' was correctly mapped to 'snippet'
        self.assertEqual(results_list[0]['snippet'], "This is the snippet for result 1.")
        self.assertEqual(results_list[1]['title'], "Test Result 2")

    async def test_execute_no_results(self):
        """Test execution when SearXNG returns no results."""
        # Configure the mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_NO_RESULTS_RESPONSE_JSON
        mock_response.raise_for_status = MagicMock() # Mock raise_for_status
        self.mock_async_get.return_value = mock_response

        # Execute the tool (await the async call)
        results_dict = await self.search_tool.execute(query=MOCK_QUERY, num_results=MOCK_NUM_RESULTS)

        self.assertIsInstance(results_dict, dict)
        self.assertNotIn("error", results_dict)
        self.assertIn("results", results_dict)
        self.assertEqual(len(results_dict["results"]), 0)

    async def test_execute_http_error(self):
        """Test execution when the HTTP request fails."""
        # Configure the mock response
        mock_response = MagicMock()
        mock_response.status_code = 500 # Simulate server error
        # Mock raise_for_status to raise an httpx exception
        # Need to import httpx for this exception type
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        self.mock_async_get.return_value = mock_response

        # Execute the tool (await the async call)
        results_dict = await self.search_tool.execute(query=MOCK_QUERY, num_results=MOCK_NUM_RESULTS)

        self.assertIsInstance(results_dict, dict)
        self.assertIn("error", results_dict)
        # Check for the specific error message format from the tool
        self.assertTrue(f"SearXNG search failed for query '{MOCK_QUERY}' with status 500" in results_dict["error"])

    async def test_execute_request_exception(self):
        """Test execution when httpx.AsyncClient.get raises an exception."""
        # Configure the mock side effect (e.g., httpx.RequestError)
        # Need to import httpx for this exception type
        self.mock_async_get.side_effect = httpx.RequestError("Connection Timeout", request=MagicMock())

        # Execute the tool (await the async call)
        results_dict = await self.search_tool.execute(query=MOCK_QUERY, num_results=MOCK_NUM_RESULTS)

        self.assertIsInstance(results_dict, dict)
        self.assertIn("error", results_dict)
        # Check for the actual error message format from the tool
        self.assertTrue(f"SearXNG search request failed for query '{MOCK_QUERY}'" in results_dict["error"])
        self.assertTrue("Connection Timeout" in results_dict["error"]) # Check original exception message

    def test_empty_url_init(self):
        """Test if tool initialization fails with an empty URL."""
        with self.assertRaises(ValueError):
            WebSearchTool(searxng_base_url="") # Test with empty string

# Note: Running this file directly with `python test_web_search_tool.py` might not work
# correctly for async tests. Use `pytest` which handles `unittest.IsolatedAsyncioTestCase`.
# if __name__ == '__main__':
#     unittest.main()
