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

            # Step 2: Gather external information if needed
            external_context = ""
            tools_used = {"web_search": False, "document_search": False}
            sources = []  # Track sources for attribution
            
            if router_decision in ["search", "both"] and context_info.get("use_web_search"):
                if status_callback:
                    await status_callback("searching_web", "Searching the web for relevant information...")
                
                logger.info("Performing web search...")
                web_results, web_sources = await self._perform_web_search(prompt, chat_history, session_id)
                external_context += web_results
                sources.extend(web_sources)
                tools_used["web_search"] = True
            
            if router_decision in ["search", "documents", "both"] and context_info.get("document_group_id"):
                if status_callback:
                    await status_callback("searching_documents", "Searching your document collection...")
                
                logger.info(f"Searching documents in group: {context_info['document_group_id']}")
                doc_results, doc_sources = await self._search_documents(prompt, context_info["document_group_id"], chat_history, session_id)
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
        system_prompt = (
            "You are a decision-making agent. Your ONLY job is to determine if a user's request requires external information. "
            f"The available tools are: {tools_text}. "
            "Based on the user's request and chat history, you must decide which tool to use. "
            "Your response MUST be a single word from the following options: 'search', 'documents', 'both', 'none'.\n\n"
            "--- Rules ---\n"
            "- Use 'search' for requests needing current information, facts, or web research.\n"
            "- Use 'documents' for requests about content within provided documents.\n"
            "- Use 'both' if both are needed.\n"
            "- Use 'none' for conversational follow-ups, formatting changes, or if no external data is needed (e.g., 'make this shorter', 'change the tone').\n\n"
            "Respond with ONLY one word."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User Context:\n{user_context}\n\nChat History:\n{chat_history}\n\nUser Request: {prompt}"}
        ]
        
        try:
            response, model_details = await self.model_dispatcher.dispatch(messages=messages, agent_mode="query_strategy")
            
            # Track LLM call for stats
            session_id = context_info.get("session_id")
            if session_id and model_details:
                await self.stats_tracker.track_llm_call(session_id, model_details)
            
            if response and response.choices:
                raw_content = response.choices[0].message.content
                logger.info(f"Router raw response: {raw_content}")
                
                # Clean up the response to get a single word
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
                    # In this case, it's safer to assume no tools are needed.
                    logger.warning(f"Unclear or verbose router decision: '{raw_content}'. Defaulting to 'none'.")
                    return "none"
            
            logger.warning("No response from router, defaulting to 'none'")
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
                logger.error(f"Unexpected error in router: {e}", exc_info=True)
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
                    "You are a query enrichment specialist. Given a user's messages and recent conversation context, "
                    "you need to write an effective and specific query for web search. The rich query should:\n"
                    "1. Include relevant context from the conversation\n"
                    "2. Be specific enough to find relevant information\n"
                    "3. Use clear, searchable terms\n"
                    "4. Maintain the user's original intent\n\n"
                    "Output ONLY the enhanced query, nothing else. Focus on the most recent user request."
                )
            else:  # document search
                system_prompt = (
                    "You are a query enrichment specialist. Given a user's messages and recent conversation context, "
                    "you need to write an effective and specific query for searching the users personal or academic document collections. "
                    "The rich query should:\n"
                    "1. Include relevant context from the conversation\n"
                    "2. Use academic and technical terminology\n"
                    "3. Be specific enough to find relevant research\n"
                    "4. Maintain the user's original intent\n\n"
                    "Output ONLY the enhanced query, nothing else. Focus on the most recent user request."
                )
            
            user_content = f"Recent Conversation Context:\n{recent_context}\n\nRaw User Message: {raw_query}\n\Search string:"
            
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

    async def _perform_web_search(self, query: str, chat_history: str = "", session_id: str = None) -> tuple[str, List[Dict[str, Any]]]:
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
            result = await web_search_tool.execute(query=enriched_query, max_results=3)
            
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
        if custom_system_prompt_addition.strip():
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
