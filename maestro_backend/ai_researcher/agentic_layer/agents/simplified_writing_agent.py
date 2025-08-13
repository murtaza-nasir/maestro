import asyncio
from datetime import datetime
import logging
from typing import Dict, Any, Optional, List

from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher import config

logger = logging.getLogger(__name__)


class WritingStatsTracker:
    """
    Tracks usage statistics for writing sessions and sends updates via WebSocket.
    """
    
    def __init__(self):
        self.session_stats = {}  # session_id -> accumulated stats
    
    async def track_llm_call(self, session_id: str, model_details: Dict[str, Any]):
        """Track token usage and cost from an LLM call."""
        if not session_id or not model_details:
            return
            
        # Extract token and cost information
        prompt_tokens = model_details.get("prompt_tokens", 0)
        completion_tokens = model_details.get("completion_tokens", 0)
        native_tokens = model_details.get("native_total_tokens", 0)
        cost = model_details.get("cost", 0.0)
        
        # Calculate native tokens if not provided
        if not native_tokens and (prompt_tokens or completion_tokens):
            native_tokens = prompt_tokens + completion_tokens
        
        # Send stats update via WebSocket
        await self._send_stats_update(session_id, {
            "prompt_tokens_delta": prompt_tokens,
            "completion_tokens_delta": completion_tokens,
            "native_tokens_delta": native_tokens,
            "cost_delta": float(cost) if cost else 0.0
        })
        
        logger.debug(f"Tracked LLM call for session {session_id}: "
                    f"prompt={prompt_tokens}, completion={completion_tokens}, "
                    f"native={native_tokens}, cost=${cost:.6f}")
    
    async def track_web_search(self, session_id: str):
        """Track a web search operation."""
        if not session_id:
            return
            
        # Send stats update via WebSocket
        await self._send_stats_update(session_id, {
            "web_searches_delta": 1
        })
        
        logger.debug(f"Tracked web search for session {session_id}")
    
    async def track_document_search(self, session_id: str):
        """Track a document search operation."""
        if not session_id:
            return
            
        # Send stats update via WebSocket
        await self._send_stats_update(session_id, {
            "document_searches_delta": 1
        })
        
        logger.debug(f"Tracked document search for session {session_id}")
    
    async def _send_stats_update(self, session_id: str, stats_delta: Dict[str, Any]):
        """Send stats update via WebSocket using the global writing manager."""
        try:
            # Import here to avoid circular imports
            from database.database import SessionLocal
            from database import crud
            from api.websockets import send_writing_stats_update
            
            # Update the database stats first
            db = SessionLocal()
            try:
                # Convert delta to the expected schema format
                from api.schemas import WritingSessionStatsUpdate
                stats_update = WritingSessionStatsUpdate(**stats_delta)
                
                # Update stats in database
                updated_stats = crud.update_writing_session_stats(db, session_id, stats_update)
                
                if updated_stats:
                    # Send real-time update via WebSocket
                    await send_writing_stats_update(session_id, {
                        "total_cost": float(updated_stats.total_cost),
                        "total_prompt_tokens": updated_stats.total_prompt_tokens,
                        "total_completion_tokens": updated_stats.total_completion_tokens,
                        "total_native_tokens": updated_stats.total_native_tokens,
                        "total_web_searches": updated_stats.total_web_searches,
                        "total_document_searches": updated_stats.total_document_searches
                    })
                    logger.debug(f"Successfully updated stats for session {session_id} via WebSocket")
                else:
                    logger.warning(f"Failed to update stats in database for session {session_id}")
                    
            finally:
                db.close()
                    
        except Exception as e:
            logger.error(f"Error sending stats update for session {session_id}: {e}")


class SimplifiedWritingAgent:
    """
    A stateless agent for handling writing tasks. It uses a two-step process:
    1. Router: Decides if external information is needed.
    2. Main: Generates the response and any document modifications.
    """

    def __init__(self, model_dispatcher: ModelDispatcher):
        self.model_dispatcher = model_dispatcher
        self.stats_tracker = WritingStatsTracker()

    async def run(self, prompt: str, draft_content: str, chat_history: str, context_info: Optional[Dict[str, Any]] = None, status_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Executes the two-step writing process with optional context information and status updates.
        """
        context_info = context_info or {}
        session_id = context_info.get("session_id")  # Extract session_id for stats tracking
        
        # Extract search configuration from context_info
        search_config = context_info.get("search_config", {})
        use_deep_search = search_config.get("deep_search", False)
        max_search_iterations = search_config.get("max_iterations", 3 if use_deep_search else 1)
        max_decomposed_queries = search_config.get("max_decomposed_queries", 10 if use_deep_search else 3)
        max_search_results = search_config.get("max_results", 5)  # Get max_results from config
        
        logger.info(f"SimplifiedWritingAgent.run called with prompt: {prompt[:100]}...")
        logger.info(f"Available tools - Web search: {context_info.get('use_web_search', False)}, Document group: {context_info.get('document_group_id')}")
        
        try:
            # Send initial status
            if status_callback:
                await status_callback("analyzing", "Analyzing your request...")
            
            # Step 1: Router LLM call - determine if external tools are needed
            if status_callback:
                await status_callback("router_thinking", "Router agent is deciding which tools to use...")
            
            router_decision = await self._run_router(prompt, chat_history, context_info, status_callback)
            logger.info(f"Router decision: {router_decision}")
            
            # Send router decision feedback to frontend
            if status_callback:
                decision_message = self._get_router_decision_message(router_decision, context_info)
                await status_callback("router_decision", decision_message)

            # Step 2: Gather external information with iterative improvement
            external_context = ""
            tools_used = {"web_search": False, "document_search": False}
            sources = []  # Track sources for attribution
            
            if router_decision in ["search", "both"] and context_info.get("use_web_search"):
                if status_callback:
                    search_mode = "deep web search" if use_deep_search else "web search"
                    await status_callback("searching_web", f"Performing {search_mode} for relevant information...")
                
                logger.info(f"Performing iterative web search (deep={use_deep_search}, max_iterations={max_search_iterations})...")
                web_results, web_sources = await self._perform_iterative_web_search(
                    prompt, chat_history, session_id, status_callback, 
                    max_attempts=max_search_iterations,
                    max_decomposed_queries=max_decomposed_queries,
                    max_search_results=max_search_results
                )
                external_context += web_results
                sources.extend(web_sources)
                tools_used["web_search"] = True
            
            if router_decision in ["search", "documents", "both"] and context_info.get("document_group_id"):
                if status_callback:
                    search_mode = "deep document search" if use_deep_search else "document search"
                    await status_callback("searching_documents", f"Performing {search_mode} in your collection...")
                
                logger.info(f"Performing iterative document search in group: {context_info['document_group_id']} (deep={use_deep_search})")
                doc_results, doc_sources = await self._perform_iterative_document_search(
                    prompt, context_info["document_group_id"], chat_history, session_id, status_callback,
                    max_attempts=max_search_iterations,
                    max_decomposed_queries=max_decomposed_queries
                )
                external_context += doc_results
                sources.extend(doc_sources)
                tools_used["document_search"] = True
            
            logger.info(f"External context gathered: {len(external_context)} characters")
            
            if status_callback:
                await status_callback("generating", "Generating response based on gathered information...")
            
            # Step 3: Main LLM call with all available context
            main_response = await self._run_main_llm(prompt, draft_content, chat_history, external_context, context_info)

            if status_callback:
                await status_callback("complete", "Response generated successfully")

            return {
                "chat_response": main_response,
                "document_delta": "",  # Placeholder for document changes
                "tools_used": tools_used,
                "sources": sources
            }
            
        except Exception as e:
            # Handle authentication and other API errors at the top level
            from ai_researcher.agentic_layer.utils.error_messages import handle_api_error
            
            logger.error(f"Error in writing agent: {e}", exc_info=True)
            error_message = handle_api_error(e)
            
            # Update status to show error
            if status_callback:
                await status_callback("error", "Configuration required")
            
            return {
                "chat_response": error_message,
                "document_delta": "",
                "tools_used": {"web_search": False, "document_search": False},
                "sources": []
            }

    def _get_router_decision_message(self, decision: str, context_info: Dict[str, Any]) -> str:
        """
        Generate a user-friendly message explaining the router's decision.
        """
        web_search_enabled = context_info.get("use_web_search", False)
        document_group_id = context_info.get("document_group_id")
        
        if decision == "search":
            if web_search_enabled:
                return "Router decided to search the web for current information"
            else:
                return "Router wanted to search the web, but web search is disabled"
        elif decision == "documents":
            if document_group_id:
                return "Router decided to search your document collection"
            else:
                return "Router wanted to search documents, but no document group is selected"
        elif decision == "both":
            tools = []
            if web_search_enabled:
                tools.append("web search")
            if document_group_id:
                tools.append("document search")
            if tools:
                return f"Router decided to use: {' and '.join(tools)}"
            else:
                return "Router wanted to use multiple tools, but they are not available"
        elif decision == "none":
            return "Router determined no external information is needed"
        else:
            return f"Router made an unclear decision: {decision}"

    async def _run_router(self, prompt: str, chat_history: str, context_info: Dict[str, Any], status_callback: Optional[callable] = None) -> str:
        """
        Decides if external information is needed based on available tools.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_profile_info = context_info.get("user_profile", {})
        user_context = (
            f"User Profile:\n"
            f"- Name: {user_profile_info.get('full_name', 'N/A')}\n"
            f"- Location: {user_profile_info.get('location', 'N/A')}\n"
            f"- Role: {user_profile_info.get('job_title', 'N/A')}\n"
            f"Current Time: {current_time}\n"
        )
        
        # Debug: Log input lengths
        prompt_length = len(prompt)
        history_length = len(chat_history)
        context_length = len(user_context)
        logger.info(f"Router input lengths - Prompt: {prompt_length}, History: {history_length}, Context: {context_length}")
        available_tools = []
        if context_info.get("use_web_search"):
            available_tools.append("web search")
        if context_info.get("document_group_id"):
            available_tools.append("document search")
        
        if not available_tools:
            logger.info("No tools available, returning 'none'")
            return "none"
        
        tools_text = " and ".join(available_tools)
        
        # Refined router prompt for more accurate tool decisions
        # Keep it concise for thinking models that may have stricter constraints
        system_prompt = (
            "Output ONLY one word: 'search', 'documents', 'both', or 'none'.\n"
            f"Available tools: {tools_text}.\n"
            "search = web info needed\n"
            "documents = document search needed\n"
            "both = both needed\n"
            "none = no external data needed\n"
            "ONE WORD ONLY."
        )
        
        # Truncate chat history if too long for router (keep last 500 chars)
        truncated_history = chat_history[-500:] if len(chat_history) > 500 else chat_history
        
        user_message = f"Request: {prompt[:200]}" if len(prompt) > 200 else f"Request: {prompt}"
        if truncated_history:
            user_message = f"Recent context: {truncated_history}\n{user_message}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Debug: Log message sizes
        system_size = len(system_prompt)
        user_size = len(user_message)
        logger.info(f"Router message sizes - System: {system_size}, User: {user_size}, Total: {system_size + user_size}")
        
        try:
            # Note: response_format may not be supported by all models, so we don't use it
            # Instead, we rely on clear instructions and post-processing
            response, model_details = await self.model_dispatcher.dispatch(messages=messages, agent_mode="query_strategy")
            
            # Track LLM call for stats
            session_id = context_info.get("session_id")
            if session_id and model_details:
                await self.stats_tracker.track_llm_call(session_id, model_details)
            
            # Log usage information for debugging
            if response and hasattr(response, 'usage'):
                logger.info(f"Router token usage: {response.usage}")
            
            if response and response.choices:
                # Log the complete response object for debugging
                logger.info(f"Router COMPLETE response object: {response}")
                
                # Log all message attributes
                message = response.choices[0].message
                logger.info(f"Router message attributes: {dir(message)}")
                logger.info(f"Router message content type: {type(message.content)}")
                logger.info(f"Router message content: {message.content}")
                
                # Check for reasoning_content or other attributes (for thinking models)
                if hasattr(message, 'reasoning_content'):
                    logger.info(f"Router reasoning_content: {message.reasoning_content}")
                if hasattr(message, 'thinking'):
                    logger.info(f"Router thinking: {message.thinking}")
                
                raw_content = response.choices[0].message.content
                logger.info(f"Router raw response: '{raw_content}' (length: {len(raw_content) if raw_content else 0})")
                logger.info(f"Router model used: {model_details.get('model_name', 'unknown')} from {model_details.get('provider', 'unknown')}")
                
                # Handle None or empty responses (common with thinking models hitting token limits)
                if not raw_content or raw_content == "":
                    logger.warning(f"Router returned empty/None response (model: {model_details.get('model_name', 'unknown')}). "
                                 f"This is common with thinking models. Defaulting to 'none'")
                    return "none"
                
                # For thinking models, they might add reasoning before the answer
                # Try to extract the last word if it's one of our keywords
                words_in_response = raw_content.lower().split()
                for word in reversed(words_in_response):
                    clean_word = "".join(c for c in word if c.isalpha())
                    if clean_word in ["search", "documents", "both", "none"]:
                        logger.info(f"Found decision word '{clean_word}' in response")
                        return clean_word
                
                # Fallback: Clean up the entire response to get a single word
                decision = "".join(c for c in raw_content.lower().strip() if c.isalpha())

                # Check for exact keywords
                if decision == "both":
                    return "both"
                elif decision == "search":
                    return "search"
                elif decision == "documents":
                    return "documents"
                elif decision == "none":
                    return "none"
                else:
                    # If the model generated a long response, it likely ignored instructions.
                    # This is common with thinking models that add reasoning.
                    logger.warning(f"Unclear or verbose router decision: '{raw_content[:100]}...' (total length: {len(raw_content)}). Defaulting to 'none'.")
                    
                    # One more attempt: check if any of our keywords appear anywhere
                    lower_content = raw_content.lower()
                    if "both" in lower_content and "search" in lower_content and "document" in lower_content:
                        return "both"
                    elif "search" in lower_content and "document" not in lower_content:
                        return "search"
                    elif "document" in lower_content and "search" not in lower_content:
                        return "documents"
                    
                    return "none"
            
            logger.warning(f"No response from router (response={response}, model_details={model_details}), defaulting to 'none'")
            return "none"
            
        except Exception as e:
            # Handle authentication and other API errors gracefully
            import openai
            if isinstance(e, openai.AuthenticationError):
                logger.error(f"Authentication error in router: {e}")
                # Raise the error so it gets caught by the main run method
                raise e
            elif isinstance(e, openai.APIStatusError):
                logger.error(f"API error in router: {e}")
                # Raise the error so it gets caught by the main run method
                raise e
            else:
                logger.error(f"Unexpected error in router: {type(e).__name__}: {e}", exc_info=True)
                # Log the messages that caused the error for debugging
                logger.debug(f"Failed router messages: {messages}")
                return "none"

    async def _enrich_search_query(self, raw_query: str, chat_history: str, context_type: str = "web") -> str:
        """
        Enriches a raw search query with context from chat history to make it more specific and effective.
        
        Args:
            raw_query: The original user query that may lack context
            chat_history: Recent conversation history for context
            context_type: Type of search ("web" or "document") for tailored enrichment
            
        Returns:
            Enhanced query string with proper context
        """
        try:
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            current_year = datetime.now().year
            
            # Extract recent context from chat history (last 2-3 exchanges)
            recent_context = ""
            if chat_history:
                # Split by common patterns and take recent parts
                history_parts = chat_history.split('\n\n')
                # Take last few exchanges for context
                recent_parts = history_parts[-6:] if len(history_parts) > 6 else history_parts
                recent_context = '\n'.join(recent_parts)
            
            # Create enrichment prompt based on search type
            if context_type == "web":
                system_prompt = (
                    f"You are a query enrichment specialist. Given a user's messages and recent conversation context, "
                    f"you need to write an effective and specific query for web search. \n\n"
                    f"IMPORTANT CONTEXT:\n"
                    f"- Current date: {current_date}\n"
                    f"- Current year: {current_year}\n"
                    f"- When looking for current information, use {current_year} or 'current' in searches\n\n"
                    f"The rich query should:\n"
                    f"1. Include relevant context from the conversation\n"
                    f"2. Be specific enough to find relevant information\n"
                    f"3. Use clear, searchable terms\n"
                    f"4. Maintain the user's original intent\n"
                    f"5. Include current year ({current_year}) when searching for recent information\n\n"
                    f"Output ONLY the enhanced query, nothing else. Focus on the most recent user request."
                )
            else:  # document search
                system_prompt = (
                    f"You are a query enrichment specialist. Given a user's messages and recent conversation context, "
                    f"you need to write an effective and specific query for searching the users personal or academic document collections. \n\n"
                    f"IMPORTANT CONTEXT:\n"
                    f"- Current date: {current_date}\n"
                    f"- Current year: {current_year}\n\n"
                    f"The rich query should:\n"
                    f"1. Include relevant context from the conversation\n"
                    f"2. Use academic and technical terminology\n"
                    f"3. Be specific enough to find relevant research\n"
                    f"4. Maintain the user's original intent\n\n"
                    f"Output ONLY the enhanced query, nothing else. Focus on the most recent user request."
                )
            
            user_content = f"Current Date: {current_date}\n\nRecent Conversation Context:\n{recent_context}\n\nRaw User Message: {raw_query}\n\nEnhanced search query:"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            response, _ = await self.model_dispatcher.dispatch(messages=messages, agent_mode="fast")
            
            if response and response.choices and response.choices[0].message.content:
                enhanced_query = response.choices[0].message.content.strip().strip('"')
                logger.info(f"Query enrichment - Original: '{raw_query}' -> Enhanced: '{enhanced_query}'")
                return enhanced_query
            else:
                logger.warning("Query enrichment failed, using original query")
                return raw_query
                
        except Exception as e:
            logger.error(f"Error during query enrichment: {e}", exc_info=True)
            return raw_query

    async def _perform_web_search(self, query: str, chat_history: str = "", session_id: str = None, max_search_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
        """
        Performs web search with query enrichment and returns formatted results with source metadata.
        Returns: (formatted_results, sources_list)
        """
        try:
            from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
            from ai_researcher import config
            
            # Enrich the query with context from chat history
            enriched_query = await self._enrich_search_query(raw_query=query, chat_history=chat_history, context_type="web")
            
            # Initialize web search tool
            web_search_tool = WebSearchTool()
            
            # Perform the search with enriched query
            logger.info(f"Executing web search for enriched query: {enriched_query}")
            result = await web_search_tool.execute(query=enriched_query, max_results=max_search_results)
            
            # Track web search for stats
            if session_id:
                await self.stats_tracker.track_web_search(session_id)
            
            if "error" in result:
                logger.error(f"Web search error: {result['error']}")
                return f"\n\n[Web Search Error: {result['error']}]\n", []
            
            results = result.get("results", [])
            if not results:
                logger.warning("No web search results found")
                return f"\n\n[No web search results found for: {query}]\n", []
            
            # Format results with source metadata and collect sources
            formatted_results = f"\n\n=== WEB SEARCH RESULTS ===\nOriginal Query: {query}\nEnriched Query: {enriched_query}\nProvider: {config.WEB_SEARCH_PROVIDER.capitalize()}\nResults found: {len(results)}\n\n"
            sources = []
            
            for i, result_item in enumerate(results, 1):
                title = result_item.get("title", "No Title")
                snippet = result_item.get("snippet", "No content available")
                url = result_item.get("url", "#")
                
                formatted_results += f"**Result {i}: {title}**\n"
                formatted_results += f"Source: {url}\n"
                formatted_results += f"Content: {snippet}\n\n"
                
                # Add to sources list
                sources.append({
                    "type": "web",
                    "title": title,
                    "url": url,
                    "provider": config.WEB_SEARCH_PROVIDER.capitalize()
                })
            
            formatted_results += "=== END WEB SEARCH RESULTS ===\n"
            
            logger.info(f"Web search completed successfully, found {len(results)} results")
            return formatted_results, sources
            
        except Exception as e:
            logger.error(f"Error performing web search: {e}", exc_info=True)
            return f"\n\n[Web Search Error: {str(e)}]\n", []

    async def _search_documents(self, query: str, document_group_id: str, chat_history: str = "", session_id: str = None) -> tuple[str, List[Dict[str, Any]]]:
        """
        Searches documents in the specified group with query enrichment and returns relevant content with source metadata.
        Returns: (formatted_results, sources_list)
        """
        try:
            from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
            from ai_researcher.core_rag.retriever import Retriever
            from ai_researcher.core_rag.query_preparer import QueryPreparer
            from ai_researcher.core_rag.query_strategist import QueryStrategist
            from ai_researcher.core_rag.vector_store import VectorStore
            from ai_researcher.core_rag.embedder import TextEmbedder
            from ai_researcher.core_rag.reranker import TextReranker
            
            # Enrich the query with context from chat history for document search
            enriched_query = await self._enrich_search_query(raw_query=query, chat_history=chat_history, context_type="document")
            
            # Initialize the RAG components (this should ideally be cached/reused)
            logger.info(f"Initializing document search components for group: {document_group_id}")
            
            # Initialize vector store and embedder with the correct persistence directory
            vector_store = VectorStore(persist_directory="/app/ai_researcher/data/vector_store")
            embedder = TextEmbedder()
            reranker = TextReranker()
            
            # Initialize retriever
            retriever = Retriever(
                vector_store=vector_store,
                embedder=embedder,
                reranker=reranker
            )
            
            # Initialize query components
            query_preparer = QueryPreparer(model_dispatcher=self.model_dispatcher)
            query_strategist = QueryStrategist(model_dispatcher=self.model_dispatcher)
            
            # Initialize document search tool
            doc_search_tool = DocumentSearchTool(
                retriever=retriever,
                query_preparer=query_preparer,
                query_strategist=query_strategist
            )
            
            # Perform the search with enriched query
            logger.info(f"Executing document search for enriched query: {enriched_query} in group: {document_group_id}")
            results = await doc_search_tool.execute(
                query=enriched_query,
                n_results=5,
                document_group_id=document_group_id,
                use_reranker=True
            )
            
            # Track document search for stats
            if session_id:
                await self.stats_tracker.track_document_search(session_id)
            
            logger.info(f"Document search returned {len(results) if results else 0} results")
            if results:
                logger.info(f"First result sample: {results[0] if results else 'None'}")
            
            if not results:
                logger.warning(f"No document search results found for query: {query}")
                return f"\n\n[No document search results found for: {query} in group {document_group_id}]\n", []
            
            # Format results with source metadata and collect sources
            formatted_results = f"\n\n=== DOCUMENT SEARCH RESULTS ===\nOriginal Query: {query}\nEnriched Query: {enriched_query}\nDocument Group ID: {document_group_id}\nResults found: {len(results)}\n\n"
            sources = []
            seen_documents = {}  # Track unique documents by doc_id to avoid duplicates
            
            for i, result_item in enumerate(results, 1):
                text = result_item.get("text", "No content available")
                metadata = result_item.get("metadata", {})
                
                # Extract source information from metadata with better fallbacks
                doc_id = metadata.get("doc_id", "Unknown")
                
                # Try multiple possible keys for filename
                filename = (metadata.get("filename") or 
                           metadata.get("original_filename") or 
                           metadata.get("title") or 
                           metadata.get("source") or 
                           "Unknown file")
                
                # Try multiple possible keys for page number
                page_num = (metadata.get("page_number") or 
                           metadata.get("page") or 
                           metadata.get("page_num") or 
                           "Unknown")
                
                chunk_id = metadata.get("chunk_id", "Unknown")
                
                formatted_results += f"**Document Result {i}**\n"
                formatted_results += f"Source: {filename} (Page {page_num})\n"
                formatted_results += f"Document ID: {doc_id}\n"
                formatted_results += f"Chunk ID: {chunk_id}\n"
                formatted_results += f"Content: {text[:500]}{'...' if len(text) > 500 else ''}\n\n"
                
                # Add to sources list with deduplication by doc_id
                # Only add if we haven't seen this document before
                if doc_id not in seen_documents:
                    display_title = filename
                    if display_title == "Unknown file" and doc_id != "Unknown":
                        display_title = f"Document {doc_id}"
                    
                    sources.append({
                        "type": "document",
                        "title": display_title,
                        "page": str(page_num) if page_num != "Unknown" else "Unknown",
                        "doc_id": doc_id,
                        "chunk_id": chunk_id
                    })
                    seen_documents[doc_id] = True
            
            formatted_results += "=== END DOCUMENT SEARCH RESULTS ===\n"
            
            logger.info(f"Document search completed successfully, found {len(results)} results")
            return formatted_results, sources
            
        except Exception as e:
            logger.error(f"Error performing document search: {e}", exc_info=True)
            return f"\n\n[Document Search Error: {str(e)}]\n", []

    async def _assess_content_quality(self, query: str, content: str, content_type: str = "search") -> Dict[str, Any]:
        """
        Assesses the quality and relevance of retrieved content to determine if more searches are needed.
        
        Args:
            query: The original user query
            content: The retrieved content to assess
            content_type: Type of content ("web" or "document")
            
        Returns:
            Dict with assessment results including quality_score and improvement_suggestions
        """
        try:
            assessment_prompt = (
                f"You are a content quality assessor. Evaluate if the retrieved {content_type} content adequately addresses the user's query.\n\n"
                f"User's Query: {query}\n\n"
                f"Retrieved Content:\n{content[:2000]}{'...' if len(content) > 2000 else ''}\n\n"
                f"Rate the content quality and determine if more searches are needed.\n\n"
                f"CRITICAL: Respond with ONLY a JSON object, no other text:\n"
                f"{{\n"
                f'  "quality_score": 8,\n'
                f'  "is_sufficient": true,\n'
                f'  "missing_aspects": ["example missing topic"],\n'
                f'  "refined_query_suggestion": "better search query"\n'
                f"}}"
            )
            
            messages = [
                {"role": "system", "content": "You are an expert content assessor. You MUST respond with ONLY a valid JSON object, nothing else. No explanations, no additional text, just the JSON object."},
                {"role": "user", "content": assessment_prompt}
            ]
            
            response, _ = await self.model_dispatcher.dispatch(messages=messages, agent_mode="fast")
            
            if response and response.choices and response.choices[0].message.content:
                import json
                import re
                
                raw_response = response.choices[0].message.content.strip()
                
                try:
                    # Try to extract JSON object from the response
                    json_match = re.search(r'\{.*?\}', raw_response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        assessment = json.loads(json_str)
                    else:
                        # Try parsing the entire response as JSON
                        assessment = json.loads(raw_response)
                    
                    # Validate required fields
                    if all(key in assessment for key in ["quality_score", "is_sufficient", "missing_aspects", "refined_query_suggestion"]):
                        # Ensure quality_score is a number
                        if not isinstance(assessment["quality_score"], (int, float)):
                            assessment["quality_score"] = 5  # Default
                        return assessment
                        
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse quality assessment JSON: {e}. Raw response: {raw_response[:200]}...")
                    # Try a more aggressive extraction
                    try:
                        # Look for individual fields in the response
                        score_match = re.search(r'"quality_score"\s*:\s*(\d+)', raw_response)
                        sufficient_match = re.search(r'"is_sufficient"\s*:\s*(true|false)', raw_response, re.IGNORECASE)
                        
                        if score_match:
                            score = int(score_match.group(1))
                            is_sufficient = sufficient_match.group(1).lower() == 'true' if sufficient_match else (score >= 7)
                            logger.info(f"Extracted quality assessment - score: {score}, sufficient: {is_sufficient}")
                            return {
                                "quality_score": score,
                                "is_sufficient": is_sufficient,
                                "missing_aspects": [],
                                "refined_query_suggestion": query + " more detailed information"
                            }
                    except Exception as extract_error:
                        logger.warning(f"Field extraction also failed: {extract_error}")
            
            # Fallback assessment - be more conservative to allow some iteration
            fallback_sufficient = len(content) > 500  # If we got substantial content, consider it sufficient
            return {
                "quality_score": 7 if fallback_sufficient else 4,
                "is_sufficient": fallback_sufficient,
                "missing_aspects": [],
                "refined_query_suggestion": query + " detailed information"  # Simple refinement
            }
            
        except Exception as e:
            logger.error(f"Error assessing content quality: {e}", exc_info=True)
            # Return conservative assessment to avoid infinite loops
            return {
                "quality_score": 5,
                "is_sufficient": True,
                "missing_aspects": [],
                "refined_query_suggestion": query
            }

    async def _decompose_complex_query(self, query: str, chat_history: str = "", search_type: str = "web", max_queries: int = 10) -> List[str]:
        """
        Breaks down complex queries into separate, focused search queries for better results.
        
        Args:
            query: The original complex query
            chat_history: Context from recent conversation
            search_type: Type of search ("web" or "document")
            max_queries: Maximum number of queries to generate
            
        Returns:
            List of focused search queries
        """
        try:
            # Extract recent context for better decomposition
            recent_context = ""
            if chat_history:
                history_parts = chat_history.split('\n\n')
                recent_parts = history_parts[-4:] if len(history_parts) > 4 else history_parts
                recent_context = '\n'.join(recent_parts)
            
            decomposition_prompt = (
                f"You are a query decomposition specialist. Your job is to analyze complex queries and break them down into "
                f"separate, focused search queries that will yield better results when searched individually.\n\n"
                f"CRITICAL: You MUST respond with ONLY a valid JSON array, nothing else.\n\n"
                f"IMPORTANT: Generate UP TO {max_queries} focused queries. If the query is simple, generate fewer queries.\n\n"
                f"Rules for decomposition:\n"
                f"1. Identify distinct topics, locations, or concepts in the query\n"
                f"2. Create separate focused queries for each distinct aspect\n"
                f"3. Each query should be self-contained and specific\n"
                f"4. Avoid combining multiple locations or topics in a single query\n"
                f"5. Preserve the user's intent and context\n"
                f"6. Generate between 1 and {max_queries} queries based on complexity\n\n"
                f"Examples:\n"
                f'Input: "fun activities in New York and restaurants in Paris"\n'
                f'Output: ["fun activities and attractions in New York City", "best restaurants and dining in Paris France"]\n\n'
                f'Input: "machine learning tutorials and data science courses"\n'
                f'Output: ["machine learning tutorials and guides", "data science courses and training programs"]\n\n'
                f'Input: "things to do in Wichita and Denver activities"\n'
                f'Output: ["fun activities and attractions in Wichita Kansas", "fun activities and attractions in Denver Colorado"]\n\n'
                f"Recent Conversation Context:\n{recent_context}\n\n"
                f"Query to decompose: {query}\n\n"
                f"RESPOND WITH ONLY A JSON ARRAY:"
            )
            
            messages = [
                {"role": "system", "content": "You are an expert query decomposition specialist. You MUST respond with ONLY a valid JSON array of strings, nothing else. No explanations, no additional text, just the JSON array."},
                {"role": "user", "content": decomposition_prompt}
            ]
            
            response, _ = await self.model_dispatcher.dispatch(messages=messages, agent_mode="fast")
            
            if response and response.choices and response.choices[0].message.content:
                import json
                import re
                
                raw_response = response.choices[0].message.content.strip()
                logger.info(f"Raw decomposition response: {raw_response}")
                
                try:
                    # Try to extract JSON array from the response
                    json_match = re.search(r'\[.*?\]', raw_response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        decomposed_queries = json.loads(json_str)
                        if isinstance(decomposed_queries, list) and len(decomposed_queries) > 0:
                            # Validate each query is a string
                            valid_queries = [q for q in decomposed_queries if isinstance(q, str) and q.strip()]
                            if valid_queries:
                                # Limit to max_queries
                                if len(valid_queries) > max_queries:
                                    valid_queries = valid_queries[:max_queries]
                                    logger.info(f"Truncated to {max_queries} queries from {len(decomposed_queries)}")
                                logger.info(f"Successfully decomposed query into {len(valid_queries)} focused searches: {valid_queries}")
                                return valid_queries
                    else:
                        # Try parsing the entire response as JSON
                        decomposed_queries = json.loads(raw_response)
                        if isinstance(decomposed_queries, list) and len(decomposed_queries) > 0:
                            valid_queries = [q for q in decomposed_queries if isinstance(q, str) and q.strip()]
                            if valid_queries:
                                # Limit to max_queries
                                if len(valid_queries) > max_queries:
                                    valid_queries = valid_queries[:max_queries]
                                    logger.info(f"Truncated to {max_queries} queries from {len(decomposed_queries)}")
                                logger.info(f"Successfully decomposed query into {len(valid_queries)} focused searches: {valid_queries}")
                                return valid_queries
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse query decomposition JSON: {e}")
                except Exception as e:
                    logger.warning(f"Error processing decomposition response: {e}")
            
            # Fallback: Simple rule-based decomposition for common patterns
            logger.info("Attempting simple rule-based decomposition...")
            simple_decomposition = self._simple_decompose_query(query)
            if len(simple_decomposition) > 1:
                logger.info(f"Rule-based decomposition successful: {simple_decomposition}")
                return simple_decomposition
            
            # Final fallback: return original query as single item
            logger.info("Using original query (no decomposition possible)")
            return [query]
            
        except Exception as e:
            logger.error(f"Error decomposing query: {e}", exc_info=True)
            return [query]  # Fallback to original query

    def _simple_decompose_query(self, query: str) -> List[str]:
        """
        Simple rule-based query decomposition for common patterns.
        Used as a fallback when LLM decomposition fails.
        """
        import re
        
        query_lower = query.lower()
        
        # Pattern 1: "activities in City1 and activities in City2"
        city_pattern = r'(?:activities|things to do|fun stuff).*?in\s+([^\s,]+(?:\s+[^\s,]+)?)(?:\s+(?:and|,)\s+(?:activities|things to do|fun stuff).*?in\s+([^\s,]+(?:\s+[^\s,]+)?))?'
        city_matches = re.findall(city_pattern, query_lower)
        
        if city_matches:
            cities = [city.strip() for match in city_matches for city in match if city.strip()]
            if len(cities) >= 2:
                # Create separate queries for each city
                decomposed = []
                for city in cities:
                    if 'weekend' in query_lower:
                        decomposed.append(f"fun weekend activities and attractions in {city}")
                    elif 'getaway' in query_lower:
                        decomposed.append(f"fun activities for a getaway in {city}")
                    else:
                        decomposed.append(f"fun activities and attractions in {city}")
                return decomposed
        
        # Pattern 2: "X and Y" where X and Y are different topics
        and_pattern = r'(.+?)\s+and\s+(.+)'
        and_matches = re.search(and_pattern, query_lower)
        
        if and_matches:
            part1 = and_matches.group(1).strip()
            part2 = and_matches.group(2).strip()
            
            # Check if they seem to be about different locations/topics
            if (('wichita' in part1 and 'denver' in part2) or 
                ('denver' in part1 and 'wichita' in part2) or
                (len(part1.split()) >= 3 and len(part2.split()) >= 3)):
                return [part1, part2]
        
        # Pattern 3: Comma-separated topics
        if ',' in query and len(query.split(',')) == 2:
            parts = [part.strip() for part in query.split(',')]
            if all(len(part.split()) >= 2 for part in parts):  # Each part has at least 2 words
                return parts
        
        # No decomposition possible
        return [query]

    async def _perform_iterative_web_search(self, query: str, chat_history: str = "", session_id: str = None, status_callback: Optional[callable] = None, max_attempts: int = 3, max_decomposed_queries: int = 10, max_search_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
        """
        Performs iterative web search with advanced reasoning - decomposes complex queries 
        into focused searches and performs quality-driven iteration.
        Returns: (formatted_results, sources_list)
        """
        # Step 1: Decompose the query into focused searches
        if status_callback:
            await status_callback("analyzing_query", "Breaking down your request into focused searches...")
        
        decomposed_queries = await self._decompose_complex_query(query, chat_history, "web", max_queries=max_decomposed_queries)
        logger.info(f"Decomposed into {len(decomposed_queries)} focused web searches")
        
        # Notify user about the decomposition
        if status_callback and len(decomposed_queries) > 1:
            queries_preview = [q[:50] + "..." if len(q) > 50 else q for q in decomposed_queries[:3]]
            await status_callback("search_plan", f"Planning {len(decomposed_queries)} focused searches: {', '.join(queries_preview)}")
        
        all_results = ""
        all_sources = []
        seen_urls = set()  # Track URLs to avoid duplicates across focused searches
        
        # Step 2: Execute each focused search with iterative improvement
        for i, focused_query in enumerate(decomposed_queries, 1):
            if status_callback:
                # More detailed search progress
                search_msg = f"Search {i} of {len(decomposed_queries)}: {focused_query[:80]}..."
                if max_attempts > 1:
                    search_msg += f" (up to {max_attempts} quality iterations)"
                await status_callback("searching_web", search_msg)
            
            logger.info(f"Executing focused web search {i}/{len(decomposed_queries)}: {focused_query}")
            
            # Perform iterative search for this focused query
            focused_results, focused_sources = await self._perform_focused_iterative_web_search(
                focused_query, query, chat_history, session_id, seen_urls, max_attempts, status_callback, max_search_results
            )
            
            # Filter out duplicate URLs and update seen_urls
            unique_focused_sources = []
            for source in focused_sources:
                url = source.get("url", "")
                if url and url not in seen_urls:
                    unique_focused_sources.append(source)
                    seen_urls.add(url)
                elif url:
                    logger.info(f"Filtered duplicate URL: {url}")
            
            # Only add results if we have unique sources
            if unique_focused_sources or i == 1:  # Always include first search even if no unique results
                all_results += f"\n\n=== FOCUSED SEARCH {i}: {focused_query} ==="
                # Add info about filtering
                if len(focused_sources) > len(unique_focused_sources):
                    filtered_count = len(focused_sources) - len(unique_focused_sources)
                    all_results += f"\n\n[Filtered {filtered_count} duplicate URLs from previous searches]\n"
                
                all_results += focused_results
                all_sources.extend(unique_focused_sources)
                
                logger.info(f"Focused search {i}: {len(focused_sources)} total results, {len(unique_focused_sources)} unique sources added")
            else:
                logger.info(f"Focused search {i} had no unique results (all {len(focused_sources)} were duplicates), skipping section")
                # Still add a note about what was filtered
                all_results += f"\n\n=== FOCUSED SEARCH {i}: {focused_query} ===\n"
                all_results += f"[All {len(focused_sources)} results were duplicates of previous searches - filtered out]\n"
            
            # Brief pause between different focused searches
            if i < len(decomposed_queries):
                await asyncio.sleep(0.5)
        
        return all_results, all_sources

    async def _perform_focused_iterative_web_search(self, focused_query: str, original_query: str, chat_history: str = "", session_id: str = None, global_seen_urls: set = None, max_attempts: int = 3, status_callback: Optional[callable] = None, max_search_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
        """
        Performs iterative search for a single focused query with quality assessment.
        Integrates with existing query enrichment for optimal results.
        """
        focused_results = ""
        focused_sources = []
        local_seen_urls = set()  # Track URLs seen in this focused search
        global_seen_urls = global_seen_urls or set()
        current_query = focused_query
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Focused web search attempt {attempt + 1}/{max_attempts} with query: {current_query}")
                
                # Send detailed status update if we're doing multiple attempts
                if max_attempts > 1 and status_callback:
                    if attempt == 0:
                        quality_msg = f"Performing initial search..."
                    else:
                        quality_msg = f"Refining search quality (iteration {attempt + 1} of {max_attempts})"
                    
                    await status_callback("search_quality_iteration", quality_msg)
                
                # Use existing query enrichment method for better search terms
                enriched_query = await self._enrich_search_query(current_query, chat_history, "web")
                
                # Perform the search with the enriched query
                try:
                    from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
                    from ai_researcher import config
                    
                    web_search_tool = WebSearchTool()
                    logger.info(f"Executing focused web search for enriched query: {enriched_query}")
                    result = await web_search_tool.execute(query=enriched_query, max_results=max_search_results)
                    
                    # Track web search for stats
                    if session_id:
                        await self.stats_tracker.track_web_search(session_id)
                    
                    if "error" in result:
                        logger.error(f"Focused web search error: {result['error']}")
                        search_results = f"\n\n[Focused Web Search Error: {result['error']}]\n"
                        search_sources = []
                    else:
                        results = result.get("results", [])
                        if not results:
                            search_results = f"\n\n[No focused web search results found for: {current_query}]\n"
                            search_sources = []
                        else:
                            # Format results similar to _perform_web_search
                            search_results = f"\n\nFocused Query: {current_query}\nEnriched Query: {enriched_query}\nProvider: {config.WEB_SEARCH_PROVIDER.capitalize()}\nResults found: {len(results)}\n\n"
                            search_sources = []
                            
                            for i, result_item in enumerate(results, 1):
                                title = result_item.get("title", "No Title")
                                snippet = result_item.get("snippet", "No content available")
                                url = result_item.get("url", "#")
                                
                                search_results += f"**Result {i}: {title}**\n"
                                search_results += f"Source: {url}\n"
                                search_results += f"Content: {snippet}\n\n"
                                
                                # Only add if URL not seen before
                                if url not in global_seen_urls and url not in local_seen_urls:
                                    search_sources.append({
                                        "type": "web",
                                        "title": title,
                                        "url": url,
                                        "provider": config.WEB_SEARCH_PROVIDER.capitalize()
                                    })
                                    local_seen_urls.add(url)
                                elif url in global_seen_urls:
                                    logger.debug(f"Filtered globally seen URL: {url[:60]}...")
                                else:
                                    logger.debug(f"Filtered locally seen URL: {url[:60]}...")
                            
                            search_results += "\n"
                            
                except Exception as search_error:
                    logger.error(f"Error performing focused web search: {search_error}", exc_info=True)
                    search_results = f"\n\n[Focused Web Search Error: {str(search_error)}]\n"
                    search_sources = []
                
                # Assess quality against the original query intent
                assessment = await self._assess_content_quality(original_query, search_results, "web")
                
                logger.info(f"Focused web search attempt {attempt + 1} quality score: {assessment['quality_score']}/10")
                
                # Send quality assessment feedback
                if max_attempts > 1 and status_callback:
                    quality_msg = f"Search quality: {assessment['quality_score']}/10"
                    if not assessment['is_sufficient'] and attempt < max_attempts - 1:
                        quality_msg += " - Refining search..."
                    await status_callback("search_quality_score", quality_msg)
                
                # Add results to focused content
                if attempt > 0:
                    focused_results += f"\n\n--- Attempt {attempt + 1} ---"
                focused_results += search_results
                focused_sources.extend(search_sources)
                
                # If quality is sufficient or this is the last attempt, stop
                if assessment["is_sufficient"] or attempt == max_attempts - 1:
                    if assessment["is_sufficient"]:
                        logger.info(f"Focused web search quality sufficient after {attempt + 1} attempts")
                    else:
                        logger.info(f"Stopping focused web search after {max_attempts} attempts (max reached)")
                    break
                
                # Refine query for next attempt
                current_query = assessment["refined_query_suggestion"]
                logger.info(f"Refining focused web search query to: {current_query}")
                
                # Add brief delay between attempts
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in focused web search attempt {attempt + 1}: {e}", exc_info=True)
                if attempt == max_attempts - 1:
                    focused_results += f"\n\n[Focused Web Search Error on attempt {attempt + 1}: {str(e)}]\n"
                    break
        
        return focused_results, focused_sources

    async def _perform_iterative_document_search(self, query: str, document_group_id: str, chat_history: str = "", session_id: str = None, status_callback: Optional[callable] = None, max_attempts: int = 3, max_decomposed_queries: int = 10) -> tuple[str, List[Dict[str, Any]]]:
        """
        Performs iterative document search with advanced reasoning - decomposes complex queries 
        into focused searches and performs quality-driven iteration.
        Returns: (formatted_results, sources_list)
        """
        # Step 1: Decompose the query into focused searches
        if status_callback:
            await status_callback("analyzing_query", "Breaking down your request for focused document searches...")
        
        decomposed_queries = await self._decompose_complex_query(query, chat_history, "document", max_queries=max_decomposed_queries)
        logger.info(f"Decomposed into {len(decomposed_queries)} focused document searches")
        
        all_results = ""
        all_sources = []
        seen_doc_ids = set()  # Track documents to avoid duplicates across all focused searches
        
        # Step 2: Execute each focused search with iterative improvement
        for i, focused_query in enumerate(decomposed_queries, 1):
            if status_callback:
                search_msg = f"Document search {i}/{len(decomposed_queries)}: {focused_query[:50]}..."
                await status_callback("searching_documents", search_msg)
            
            logger.info(f"Executing focused document search {i}/{len(decomposed_queries)}: {focused_query}")
            
            # Perform iterative search for this focused query
            focused_results, focused_sources = await self._perform_focused_iterative_document_search(
                focused_query, query, document_group_id, chat_history, session_id, seen_doc_ids, max_attempts, status_callback
            )
            
            # Add results with clear separation
            all_results += f"\n\n=== FOCUSED SEARCH {i}: {focused_query} ==="
            all_results += focused_results
            all_sources.extend(focused_sources)
            
            # Update seen documents to avoid duplicates in next focused search
            for source in focused_sources:
                doc_id = source.get("doc_id", "unknown")
                seen_doc_ids.add(doc_id)
            
            # Brief pause between different focused searches
            if i < len(decomposed_queries):
                await asyncio.sleep(0.5)
        
        return all_results, all_sources

    async def _perform_focused_iterative_document_search(self, focused_query: str, original_query: str, document_group_id: str, chat_history: str = "", session_id: str = None, global_seen_docs: set = None, max_attempts: int = 3, status_callback: Optional[callable] = None) -> tuple[str, List[Dict[str, Any]]]:
        """
        Performs iterative document search for a single focused query with quality assessment.
        Integrates with existing query enrichment for optimal results.
        """
        focused_results = ""
        focused_sources = []
        local_seen_docs = set()  # Track docs seen in this focused search
        global_seen_docs = global_seen_docs or set()
        current_query = focused_query
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Focused document search attempt {attempt + 1}/{max_attempts} with query: {current_query}")
                
                # Send detailed status update if we're doing multiple attempts
                if max_attempts > 1 and status_callback:
                    await status_callback("search_quality_iteration", {
                        "message": f"Refining document search quality (attempt {attempt + 1}/{max_attempts})",
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "query": current_query[:100]
                    })
                
                # Use existing query enrichment method for better search terms
                enriched_query = await self._enrich_search_query(current_query, chat_history, "document")
                
                # Perform the search using the existing _search_documents method 
                # which already handles enrichment, so we'll pass the focused query directly
                # to avoid double-enrichment
                search_results, search_sources = await self._search_documents(current_query, document_group_id, chat_history, session_id)
                
                # Filter out documents we've already seen globally and locally
                filtered_sources = []
                for source in search_sources:
                    doc_id = source.get("doc_id", "unknown")
                    if doc_id not in global_seen_docs and doc_id not in local_seen_docs:
                        filtered_sources.append(source)
                        local_seen_docs.add(doc_id)
                
                # Only assess if we got new results
                if filtered_sources or attempt == 0:
                    # Assess quality against the original query intent
                    assessment = await self._assess_content_quality(original_query, search_results, "document")
                    
                    logger.info(f"Focused document search attempt {attempt + 1} quality score: {assessment['quality_score']}/10, new docs: {len(filtered_sources)}")
                    
                    # Send quality assessment feedback for documents
                    if max_attempts > 1 and status_callback and attempt < max_attempts - 1:
                        if assessment['is_sufficient']:
                            await status_callback("searching_documents", f"Document search quality: {assessment['quality_score']}/10 - Sufficient")
                        else:
                            await status_callback("searching_documents", f"Document search quality: {assessment['quality_score']}/10 - Refining...")
                    
                    # Add results to focused content
                    if search_results and "No document search results found" not in search_results:
                        if attempt > 0:
                            focused_results += f"\n\n--- Attempt {attempt + 1} ---"
                        focused_results += search_results
                    
                    focused_sources.extend(filtered_sources)
                    
                    # If quality is sufficient or this is the last attempt, stop
                    if assessment["is_sufficient"] or attempt == max_attempts - 1:
                        if assessment["is_sufficient"]:
                            logger.info(f"Focused document search quality sufficient after {attempt + 1} attempts")
                        else:
                            logger.info(f"Stopping focused document search after {max_attempts} attempts (max reached)")
                        break
                    
                    # Refine query for next attempt
                    current_query = assessment["refined_query_suggestion"]
                    logger.info(f"Refining focused document search query to: {current_query}")
                else:
                    logger.info(f"No new documents found in focused search attempt {attempt + 1}, stopping")
                    break
                
                # Add brief delay between attempts
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error in focused document search attempt {attempt + 1}: {e}", exc_info=True)
                if attempt == max_attempts - 1:
                    focused_results += f"\n\n[Focused Document Search Error on attempt {attempt + 1}: {str(e)}]\n"
                    break
        
        return focused_results, focused_sources

    async def _run_main_llm(self, prompt: str, draft_content: str, chat_history: str, external_context: str = "", context_info: Dict[str, Any] = None) -> str:
        """
        Generates the main response and document modifications with all available context.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_profile_info = context_info.get("user_profile", {})
        user_context = (
            f"User Profile:\n"
            f"- Name: {user_profile_info.get('full_name', 'N/A')}\n"
            f"- Location: {user_profile_info.get('location', 'N/A')}\n"
            f"- Role: {user_profile_info.get('job_title', 'N/A')}\n"
            f"Current Time: {current_time}\n"
        )
        context_info = context_info or {}
        
        # Build tool status information
        web_search_enabled = context_info.get("use_web_search", False)
        document_group_id = context_info.get("document_group_id")
        document_search_enabled = bool(document_group_id)
        
        tool_status = f"\n\nCURRENT TOOL STATUS:\n"
        tool_status += f"- Web Search: {'ENABLED' if web_search_enabled else 'DISABLED'}\n"
        tool_status += f"- Document Search: {'ENABLED' if document_search_enabled else 'DISABLED'}"
        if document_search_enabled:
            tool_status += f" (Document Group: {document_group_id})"
        tool_status += "\n"
        
        # Get custom system prompt addition from context_info
        custom_system_prompt_addition = context_info.get("custom_system_prompt", "")
        
        # Default system prompt (always used as base)
        system_prompt = (
            "You are a collaborative writing assistant helping users write documents. "
            "Your responses should be helpful, informative, and directly address the user's request. "
            "You have access to information about which tools are currently enabled or disabled. "
            "If a user's request would benefit from a tool that is currently disabled, suggest they enable it. "
            "When you have access to external information (web search results or document search results), "
            "integrate that information naturally into your response and cite your sources appropriately. "
            "If the user's request implies changes to the document, describe what changes you would make. "
            "Always be specific about where information comes from when using external sources.\n\n"
            "WRITING STYLE GUIDELINES:\n"
            "Use bullet points only sparingly and only if absolutely necessary. Otherwise, write in reasonably length paragraphs that flow naturally and provide comprehensive coverage of topics.\n\n"
            "IMPORTANT FORMATTING INSTRUCTIONS:\n"
            "When generating substantial content (like sections, paragraphs, lists, or complete documents), "
            "wrap each distinct content block in special markdown blocks using this format:\n"
            "```content-block:BLOCK_TYPE\n"
            "Your content here...\n"
            "```\n\n"
            "Available BLOCK_TYPE options:\n"
            "- document: Complete document or large section\n"
            "- section: Individual section with heading\n"
            "- paragraph: Single paragraph or short content\n"
            "- list: Lists, bullet points, or numbered items\n"
            "- note: Important notes or callouts\n"
            "- code: Code snippets or technical content\n\n"
            "Example:\n"
            "Here's a section about downtown attractions:\n\n"
            "```content-block:section\n"
            "# Downtown Attractions\n\n"
            "## 1. Historic District\n"
            "The historic district features...\n\n"
            "## 2. Art Museum\n"
            "The local art museum showcases...\n"
            "```\n\n"
            "This allows users to copy individual content blocks while still seeing them formatted properly."
        )
        
        # Append user's custom instructions if provided
        if custom_system_prompt_addition and custom_system_prompt_addition.strip():
            system_prompt += f"\n\nADDITIONAL USER INSTRUCTIONS:\n{custom_system_prompt_addition.strip()}"
        
        if external_context:
            system_prompt += (
                "\n\nIMPORTANT: You have access to external information from enabled tools. "
                "Use this information to provide more accurate, detailed, and well-sourced responses. "
                "When referencing information from these sources, mention the source (e.g., 'According to [source]' or 'Based on the search results'). "
                "If the external information contradicts something in the current draft, point this out to the user."
            )
        else:
            system_prompt += (
                "\n\nNOTE: No external information was gathered for this request. "
                "If the user's question would benefit from web search or document search, "
                "suggest they enable the appropriate tools using the controls in the interface."
            )
        
        user_content = f"Current Draft:\n```markdown\n{draft_content}\n```\n\nUser Context:\n{user_context}\n\nChat History:\n{chat_history}"
        user_content += tool_status
        
        if external_context:
            user_content += f"\n\nExternal Information Available:\n{external_context}"
        
        user_content += f"\n\nUser Request: {prompt}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            response, model_details = await self.model_dispatcher.dispatch(messages=messages, agent_mode="simplified_writing")

            # Track LLM call for stats
            session_id = context_info.get("session_id")
            if session_id and model_details:
                await self.stats_tracker.track_llm_call(session_id, model_details)

            if response and response.choices:
                return response.choices[0].message.content
                
            return "Error: Could not generate a response."
            
        except Exception as e:
            # Handle authentication and other API errors with user-friendly messages
            from ai_researcher.agentic_layer.utils.error_messages import handle_api_error
            
            logger.error(f"Error in main LLM: {e}", exc_info=True)
            return handle_api_error(e)

    async def _run_main_llm_with_streaming(self, prompt: str, draft_content: str, chat_history: str, external_context: str = "", context_info: Dict[str, Any] = None, status_callback: Optional[callable] = None) -> str:
        """
        Generates the main response with streaming support and status updates.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_profile_info = context_info.get("user_profile", {})
        user_context = (
            f"User Profile:\n"
            f"- Name: {user_profile_info.get('full_name', 'N/A')}\n"
            f"- Location: {user_profile_info.get('location', 'N/A')}\n"
            f"- Role: {user_profile_info.get('job_title', 'N/A')}\n"
            f"Current Time: {current_time}\n"
        )
        context_info = context_info or {}
        
        # Build tool status information
        web_search_enabled = context_info.get("use_web_search", False)
        document_group_id = context_info.get("document_group_id")
        document_search_enabled = bool(document_group_id)
        
        tool_status = f"\n\nCURRENT TOOL STATUS:\n"
        tool_status += f"- Web Search: {'ENABLED' if web_search_enabled else 'DISABLED'}\n"
        tool_status += f"- Document Search: {'ENABLED' if document_search_enabled else 'DISABLED'}"
        if document_search_enabled:
            tool_status += f" (Document Group: {document_group_id})"
        tool_status += "\n"
        
        system_prompt = (
            "You are a collaborative writing assistant helping users write documents. "
            "Your responses should be helpful, informative, and directly address the user's request. "
            "You have access to information about which tools are currently enabled or disabled. "
            "If a user's request would benefit from a tool that is currently disabled, suggest they enable it. "
            "When you have access to external information (web search results or document search results), "
            "integrate that information naturally into your response and cite your sources appropriately. "
            "If the user's request implies changes to the document, describe what changes you would make. "
            "Always be specific about where information comes from when using external sources.\n\n"
            "IMPORTANT FORMATTING INSTRUCTIONS:\n"
            "When generating substantial content (like sections, paragraphs, lists, or complete documents), "
            "wrap each distinct content block in special markdown blocks using this format:\n"
            "```content-block:BLOCK_TYPE\n"
            "Your content here...\n"
            "```\n\n"
            "Available BLOCK_TYPE options:\n"
            "- document: Complete document or large section\n"
            "- section: Individual section with heading\n"
            "- paragraph: Single paragraph or short content\n"
            "- list: Lists, bullet points, or numbered items\n"
            "- note: Important notes or callouts\n"
            "- code: Code snippets or technical content\n\n"
            "Example:\n"
            "Here's a section about downtown attractions:\n\n"
            "```content-block:section\n"
            "# Downtown Attractions\n\n"
            "## 1. Historic District\n"
            "The historic district features...\n\n"
            "## 2. Art Museum\n"
            "The local art museum showcases...\n"
            "```\n\n"
            "This allows users to copy individual content blocks while still seeing them formatted properly."
        )
        
        if external_context:
            system_prompt += (
                "\n\nIMPORTANT: You have access to external information from enabled tools. "
                "Use this information to provide more accurate, detailed, and well-sourced responses. "
                "When referencing information from these sources, mention the source (e.g., 'According to [source]' or 'Based on the search results'). "
                "If the external information contradicts something in the current draft, point this out to the user."
            )
        else:
            system_prompt += (
                "\n\nNOTE: No external information was gathered for this request. "
                "If the user's question would benefit from web search or document search, "
                "suggest they enable the appropriate tools using the controls in the interface."
            )
        
        user_content = f"Current Draft:\n```markdown\n{draft_content}\n```\n\nUser Context:\n{user_context}\n\nChat History:\n{chat_history}"
        user_content += tool_status
        
        if external_context:
            user_content += f"\n\nExternal Information Available:\n{external_context}"
        
        user_content += f"\n\nUser Request: {prompt}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            # Check if streaming is supported by the model dispatcher
            session_id = context_info.get("session_id")
            
            # Try to get streaming response
            try:
                if status_callback:
                    await status_callback("streaming", "Streaming response...")
                
                # Collect streamed content
                full_response = ""
                async for chunk in self.model_dispatcher.dispatch_stream(messages=messages, agent_mode="writing"):
                    if chunk and hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            full_response += delta.content
                            # Send streaming update via WebSocket
                            if status_callback:
                                await status_callback("streaming_chunk", delta.content)
                
                # Track LLM call for stats (approximate token count for streaming)
                if session_id:
                    # Estimate tokens for streaming response
                    estimated_prompt_tokens = len(str(messages)) // 4  # Rough estimate
                    estimated_completion_tokens = len(full_response) // 4  # Rough estimate
                    model_details = {
                        "prompt_tokens": estimated_prompt_tokens,
                        "completion_tokens": estimated_completion_tokens,
                        "native_total_tokens": estimated_prompt_tokens + estimated_completion_tokens,
                        "cost": 0.0  # Cost calculation would need to be implemented
                    }
                    await self.stats_tracker.track_llm_call(session_id, model_details)
                
                return full_response if full_response else "Error: No content received from streaming response."
                
            except Exception as e:
                # Fallback to non-streaming if dispatch_stream fails for any reason
                logger.info(f"Streaming failed ({e}), falling back to regular dispatch")
                response, model_details = await self.model_dispatcher.dispatch(messages=messages, agent_mode="writing")
                
                # Track LLM call for stats
                if session_id and model_details:
                    await self.stats_tracker.track_llm_call(session_id, model_details)

                if response and response.choices:
                    return response.choices[0].message.content
                    
                return "Error: Could not generate a response."
            
        except Exception as e:
            # Handle authentication and other API errors with user-friendly messages
            from ai_researcher.agentic_layer.utils.error_messages import handle_api_error
            
            logger.error(f"Error in streaming main LLM: {e}", exc_info=True)
            return handle_api_error(e)

    def _format_sources(self, sources: List[Dict[str, Any]]) -> str:
        """
        Formats sources into a compact, professional reference section.
        """
        if not sources:
            return ""
        
        web_sources = [s for s in sources if s.get("type") == "web"]
        doc_sources = [s for s in sources if s.get("type") == "document"]
        
        formatted = "\n\n---\n**Sources:** "
        
        all_formatted_sources = []
        
        # Format web sources compactly
        for i, source in enumerate(web_sources, 1):
            title = source.get("title", "Web Source")
            url = source.get("url", "#")
            # Truncate long titles
            if len(title) > 40:
                title = title[:37] + "..."
            all_formatted_sources.append(f"[{title}]({url})")
        
        # Format document sources compactly
        for i, source in enumerate(doc_sources, 1):
            title = source.get("title", "Document")
            page = source.get("page", "")
            # Truncate long titles
            if len(title) > 30:
                title = title[:27] + "..."
            page_info = f" (p.{page})" if page and page != "Unknown" else ""
            all_formatted_sources.append(f"{title}{page_info}")
        
        # Join all sources with bullet separators
        formatted += " • ".join(all_formatted_sources)
        
        return formatted
