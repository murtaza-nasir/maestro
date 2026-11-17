"""Focused provider checks, without loading the unrelated RAG/model stack.

Run with DATABASE_URL=sqlite:///:memory: PYTHONPATH=maestro_backend python -m unittest
 tests.agentic_layer.tools.test_parallel_web_search
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx

from ai_researcher import dynamic_config
from ai_researcher.agentic_layer.tool_registry import ToolDefinition, ToolRegistry
from ai_researcher.user_context import current_user_var

# tools/__init__.py eagerly imports GPU/RAG services. Load the actual search
# module directly so these tests need neither model downloads nor a database.
SEARCH_PATH = Path(__file__).resolve().parents[3] / 'maestro_backend/ai_researcher/agentic_layer/tools/web_search_tool.py'
spec = importlib.util.spec_from_file_location('maestro_search_under_test', SEARCH_PATH)
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


class TestParallelWebSearch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_token = current_user_var.set(SimpleNamespace(settings={'search': {'provider': 'parallel'}}))
        self.addCleanup(current_user_var.reset, self.user_token)
        limiter = patch.object(search.WebSearchTool, '_min_request_interval', 0)
        limiter.start()
        self.addCleanup(limiter.stop)
        self.requests = []
        self.payload = {'results': [
            {'title': 'Asyncio docs', 'url': 'https://docs.python.org/3/library/asyncio-task.html',
             'excerpts': ['Task cancellation.', 'Use try/finally.'], 'publish_date': '2025-01-01'},
            {'title': 'Duplicate', 'url': 'https://docs.python.org/3/library/asyncio-task.html',
             'excerpts': ['Repeated source.']},
            {'title': 'Futures', 'url': 'https://docs.python.org/3/library/asyncio-future.html?x=1',
             'excerpts': ['Future objects.']},
        ]}
        self.tool_error = False
        self.structured = False
        self.http_error = None
        real_client = self.real_http_client = httpx.AsyncClient
        handler = self.handle_http
        class TestHTTPClient(real_client):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, transport=httpx.MockTransport(handler), **kwargs)
        client_patch = patch('httpx.AsyncClient', TestHTTPClient)
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def handle_http(self, request):
        self.requests.append(request)
        if self.http_error:
            raise self.http_error
        if request.method != 'POST':
            return httpx.Response(405)
        message = json.loads(request.content)
        method = message['method']
        if 'id' not in message:
            return httpx.Response(202)
        if method == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'search-test-double', 'version': '1'}}
        elif method == 'tools/list':
            result = {'tools': [{'name': 'web_search', 'inputSchema': {'type': 'object'}}]}
        elif method == 'tools/call':
            result = {'content': [{'type': 'text', 'text': json.dumps(self.payload)}],
                      'isError': self.tool_error}
            if self.structured:
                result['structuredContent'] = self.payload
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': message['id'], 'result': result})

    def registry(self):
        tool = search.WebSearchTool()
        registry = ToolRegistry()
        registry.register_tool(ToolDefinition(tool.name, tool.description, tool.parameters_schema, tool.execute))
        return registry

    async def test_registry_dispatch_metadata_deduplication_and_headers(self):
        result = await self.registry().execute_tool('web_search', {'query': 'Python asyncio cancellation', 'max_results': 2})
        self.assertEqual(result, {'results': [
            {'title': 'Asyncio docs', 'snippet': 'Task cancellation.\n\nUse try/finally.',
             'url': self.payload['results'][0]['url'], 'publish_date': '2025-01-01'},
            {'title': 'Futures', 'snippet': 'Future objects.',
             'url': self.payload['results'][2]['url'], 'publish_date': None},
        ]})
        self.assertTrue(self.requests)
        for request in self.requests:
            self.assertEqual(str(request.url), 'https://mcp.parallel.ai/mcp')
            self.assertEqual(request.headers['User-Agent'], 'Maestro/ParallelSearch')
            self.assertNotIn('authorization', request.headers)
        messages = [json.loads(r.content) for r in self.requests if r.method == 'POST']
        call = next(m for m in messages if m['method'] == 'tools/call')
        self.assertEqual(call['params'], {'name': 'web_search', 'arguments': {
            'objective': 'Python asyncio cancellation academic paper',
            'search_queries': ['Python asyncio cancellation academic paper'],
        }})

    async def test_structured_results_and_limits(self):
        self.structured = True
        result = await self.registry().execute_tool('web_search', {'query': 'public documentation', 'max_results': 1})
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['url'], self.payload['results'][0]['url'])

    async def test_invalid_sources_are_skipped_without_consuming_limit(self):
        self.payload['results'] = [None, {}, {'url': 'javascript:alert(1)', 'excerpts': ['bad']},
            {'url': 'https://[invalid', 'excerpts': ['bad']},
            {'url': 'https://example.com/empty', 'excerpts': [None, '']},
            {'url': 'https://example.com/wrong-excerpts', 'excerpts': 'not a list'},
            *self.payload['results']]
        result = await self.registry().execute_tool('web_search', {'query': 'public docs', 'max_results': 2})
        self.assertEqual(len(result['results']), 2)
        self.assertEqual(len({r['url'] for r in result['results']}), 2)

    async def test_empty_results_send_normal_completion_feedback(self):
        self.payload = {'results': []}
        callback = MagicMock()
        result = await search.WebSearchTool().execute('public docs', update_callback=callback)
        self.assertEqual(result, {'results': []})
        self.assertEqual(callback.call_args.args[1]['payload']['type'], 'web_search_complete')
        self.assertEqual(callback.call_args.args[1]['payload']['num_results'], 0)

    async def test_tool_error_and_malformed_payload_use_existing_error_feedback(self):
        for payload, tool_error in [({'results': []}, True), ({'unexpected': []}, False),
                                    ({'results': None}, False)]:
            with self.subTest(payload=payload, tool_error=tool_error):
                self.payload, self.tool_error = payload, tool_error
                callback = MagicMock()
                result = await search.WebSearchTool().execute('public docs', update_callback=callback)
                self.assertIn('error', result)
                self.assertNotIn('API key', result['error'])
                self.assertEqual(callback.call_args.args[1]['payload']['type'], 'web_search_error')

    async def test_unavailable_and_timeout_return_search_error(self):
        for error in (httpx.ConnectError('offline'), httpx.ReadTimeout('timeout')):
            with self.subTest(error=type(error).__name__):
                self.http_error = error
                result = await self.registry().execute_tool('web_search', {'query': 'public docs'})
                self.assertIn('error', result)

    async def test_cancellation_propagates(self):
        with patch.object(search.WebSearchTool, '_search_parallel', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.registry().execute_tool('web_search', {'query': 'public docs'})

    async def test_cancellation_during_transport_propagates(self):
        started = asyncio.Event()
        async def wait_for_cancellation(request):
            started.set()
            await asyncio.Event().wait()
        # Replace the transport for this test; the production MCP client still runs.
        real_client = self.real_http_client
        class WaitingClient(real_client):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, transport=httpx.MockTransport(wait_for_cancellation), **kwargs)
        with patch('httpx.AsyncClient', WaitingClient):
            task = asyncio.create_task(search.WebSearchTool().execute('public docs'))
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)

    async def test_filters_fail_before_network(self):
        for args in ({'from_date': '2025-01-01'}, {'to_date': '2025-12-31'},
                     {'include_domains': ['python.org']}, {'exclude_domains': ['example.com']}):
            callback = MagicMock()
            result = await search.WebSearchTool().execute('public docs', update_callback=callback, **args)
            self.assertEqual(callback.call_args.args[1]['payload']['type'], 'web_search_error')
            self.assertIn('does not support date or domain filters', result['error'])
        self.assertEqual(self.requests, [])

    async def test_default_and_inactive_provider_never_contact_parallel(self):
        current_user_var.set(None)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(dynamic_config.get_web_search_provider(), 'tavily')
            client = MagicMock()
            client.search.return_value = {'results': [{'title': 'Existing source', 'content': 'Snippet', 'url': 'https://example.com'}]}
            with patch.object(search, 'TavilyClient', return_value=client), patch.object(search, 'get_tavily_api_key', return_value='test-only-key'):
                result = await self.registry().execute_tool('web_search', {'query': 'public docs'})
        self.assertEqual(result['results'][0]['title'], 'Existing source')
        client.search.assert_called_once()
        self.assertEqual(self.requests, [])

    async def test_env_selection_and_user_override(self):
        current_user_var.set(None)
        with patch.dict(os.environ, {'WEB_SEARCH_PROVIDER': 'parallel'}):
            self.assertEqual(search.WebSearchTool().provider, 'parallel')
            current_user_var.set(SimpleNamespace(settings={'search': {'provider': 'tavily'}}))
            self.assertEqual(dynamic_config.get_web_search_provider(), 'tavily')


if __name__ == '__main__':
    unittest.main()
