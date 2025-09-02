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
    
    async def track_web_fetch(self, session_id: str):
        """Track a web page fetch operation."""
        if not session_id:
            return
            
        # For now, just count it as another web search since we don't have a separate counter
        # In the future, we might want to add a separate web_fetches_delta field
        logger.debug(f"Tracked web page fetch for session {session_id}")
    
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
        
        # Tool cache to avoid re-initialization
        self._web_search_tool = None
        self._web_page_fetcher = None
        self._document_search_tool = None
        self._retriever = None
        self._query_preparer = None

    async def run(self, prompt: str, draft_content: str, chat_history: List[Dict[str, str]], context_info: Optional[Dict[str, Any]] = None, status_callback: Optional[callable] = None) -> Dict[str, Any]:
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
        max_search_results = search_config.get("max_results", 5)  # Get max_results for web search
        max_doc_results = search_config.get("max_doc_results", 5)  # Get max_doc_results for document search
        
        logger.info(f"SimplifiedWritingAgent.run called with prompt: {prompt[:200] + '...' if len(prompt) > 200 else prompt}")
        document_group_info = f"{context_info.get('document_group_name', 'Unknown')} ({context_info.get('document_group_id')})" if context_info.get('document_group_id') else None
        logger.info(f"Available tools - Web search: {context_info.get('use_web_search', False)}, Document group: {document_group_info}")
        
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
                    # Include the actual query in the status message
                    query_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
                    await status_callback("searching_web", f"Performing {search_mode} for: {query_preview}")
                
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
            
            if router_decision in ["documents", "both"] and context_info.get("document_group_id"):
                if status_callback:
                    search_mode = "deep document search" if use_deep_search else "document search"
                    # Include the actual query in the status message
                    query_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
                    await status_callback("searching_documents", f"Performing {search_mode} in your collection for: {query_preview}")
                
                logger.info(f"Performing iterative document search in group: {context_info['document_group_id']} (deep={use_deep_search})")
                doc_results, doc_sources = await self._perform_iterative_document_search(
                    prompt, context_info["document_group_id"], chat_history, session_id, status_callback,
                    max_attempts=max_search_iterations,
                    max_decomposed_queries=max_decomposed_queries,
                    max_doc_results=max_doc_results
                )
                external_context += doc_results
                sources.extend(doc_sources)
                tools_used["document_search"] = True
            
            logger.info(f"External context gathered: {len(external_context)} characters")
            
            if status_callback:
                await status_callback("generating", "Generating response based on gathered information...")
            
            # Step 3: Main LLM call with all available context
            main_response = await self._run_main_llm(prompt, draft_content, chat_history, external_context, context_info)

            # Process citations to replace ref IDs with numbers and filter sources
            used_sources = []
            if sources:
                main_response, used_sources = self._process_citations_and_filter_sources(main_response, sources)
            
            if status_callback:
                await status_callback("complete", "Response generated successfully")

            return {
                "chat_response": main_response,
                "document_delta": "",  # Placeholder for document changes
                "tools_used": tools_used,
                "sources": used_sources
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

    async def _run_router(self, prompt: str, chat_history: List[Dict[str, str]], context_info: Dict[str, Any], status_callback: Optional[callable] = None) -> str:
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
        # Check which tools are available
        has_web_search = context_info.get("use_web_search", False)
        has_document_group = bool(context_info.get("document_group_id"))
        
        available_tools = []
        if has_web_search:
            available_tools.append("web search")
        if has_document_group:
            available_tools.append("document search")
        
        if not available_tools:
            logger.info("No tools available, returning 'none'")
            return "none"
        
        tools_text = " and ".join(available_tools)
        
        # Build contextual router prompt based on available tools
        if has_document_group and has_web_search:
            # Both tools available - prefer using both for comprehensive research
            system_prompt = (
                "You are a routing agent that must analyze the conversation history and decide which tools to use.\n"
                f"Available tools: {tools_text}.\n\n"
                "CRITICAL: You MUST carefully read and understand the conversation history before deciding.\n\n"
                "Decision process:\n"
                "1. Read the ENTIRE conversation history\n"
                "2. Understand what information has already been tried and what worked/didn't work\n"
                "3. If previous document searches yielded outdated or irrelevant information, don't repeat the same mistake\n"
                "4. Consider the nature of the query - is it asking for current/recent/latest information?\n"
                "5. If the user is questioning your previous choice of sources, learn from that feedback\n\n"
                "Tool selection rules:\n"
                "- 'both': DEFAULT choice for most research queries - provides comprehensive coverage\n"
                "- 'search': When documents have proven unhelpful OR query needs current information\n"
                "- 'documents': ONLY when user explicitly wants document-only search OR revisiting specific document content\n"
                "- 'none': ONLY for pure creative tasks or casual conversation\n\n"
                "Learn from the conversation: If documents didn't help before, they probably won't help now unless the query changed significantly.\n\n"
                "Output ONLY one word: 'search', 'documents', 'both', or 'none'."
            )
        elif has_document_group:
            # Only documents available - use them by default for most queries
            system_prompt = (
                "You have access to a document collection that the user wants you to use.\n"
                f"Available tool: {tools_text}.\n\n"
                "Decision rules:\n"
                "- Use 'documents' for: ANY question requiring information, facts, analysis, research, "
                "or content that could be answered from documents\n"
                "- Use 'none' ONLY for: pure creative writing, personal opinions, or general chat with no information needs\n\n"
                "Since the user provided documents, you should use them unless the query is purely creative/conversational.\n"
                "Output ONLY one word: 'documents' or 'none'."
            )
        elif has_web_search:
            # Only web search available
            system_prompt = (
                f"Available tool: {tools_text}.\n\n"
                "Decision rules:\n"
                "- Use 'search' for: any factual questions, current events, research queries, or information requests\n"
                "- Use 'none' ONLY for: creative writing, opinions, or general conversation with no factual requirements\n\n"
                "Output ONLY one word: 'search' or 'none'."
            )
        else:
            # No tools available
            system_prompt = (
                "No external tools are available.\n"
                "Output ONLY: 'none'"
            )
        
        # Build messages list with proper structure
        messages = []
        
        # Add conversation history as proper messages (limit to recent history to avoid token overflow)
        MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages (10 exchanges)
        if len(chat_history) > MAX_HISTORY_MESSAGES:
            recent_history = chat_history[-MAX_HISTORY_MESSAGES:]
            # Include truncation note in system prompt
            system_prompt = "Note: Earlier conversation history has been truncated for context window management.\n\n" + system_prompt
        else:
            recent_history = chat_history
        
        # Add system message
        messages.append({"role": "system", "content": system_prompt})
        
        # Add the conversation history, ensuring role alternation
        last_role = "system"
        for msg in recent_history:
            # Skip if same role as previous to maintain alternation
            if msg["role"] == last_role:
                # If it's the same role, we need to merge or skip
                if last_role == "user":
                    # For consecutive user messages, merge them
                    messages[-1]["content"] += "\n\n" + msg["content"]
                elif last_role == "assistant":
                    # For consecutive assistant messages, merge them
                    messages[-1]["content"] += "\n\n" + msg["content"]
                # Skip system messages that would break alternation
                continue
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})
                last_role = msg["role"]
        
        # Build the current user message
        current_user_message = f"User request: {prompt}"
        
        # Add hint about document availability when relevant
        if has_document_group:
            current_user_message += "\n\nNote: The user has provided documents for you to reference."
        
        # Only add user message if the last message wasn't from user
        if last_role == "user":
            # Merge with the last user message
            messages[-1]["content"] += "\n\n" + current_user_message
        else:
            messages.append({"role": "user", "content": current_user_message})
        
        # Debug: Log message sizes
        total_messages = len(messages)
        total_chars = sum(len(msg["content"]) for msg in messages)
        logger.info(f"Router messages - Total messages: {total_messages}, Total chars: {total_chars}")
        
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

    async def _enrich_search_query(self, raw_query: str, chat_history: List[Dict[str, str]], context_type: str = "web") -> str:
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
                # Take last 6 messages (3 exchanges) for context
                recent_messages = chat_history[-6:] if len(chat_history) > 6 else chat_history
                # Format as conversation
                context_parts = []
                for msg in recent_messages:
                    role = "User" if msg["role"] == "user" else "Assistant"
                    context_parts.append(f"{role}: {msg['content']}")
                recent_context = '\n'.join(context_parts)
            
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

    async def _perform_web_search(self, query: str, chat_history: List[Dict[str, str]] = None, session_id: str = None, max_search_results: int = 5, status_callback: Optional[callable] = None) -> tuple[str, List[Dict[str, Any]]]:
        """
        Performs web search with query enrichment and returns formatted results with source metadata.
        Now uses parallel processing for relevance checking and content fetching.
        Returns: (formatted_results, sources_list)
        """
        try:
            from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
            from ai_researcher import config
            
            # Send status update with the actual query
            if status_callback:
                query_preview = query[:80] + "..." if len(query) > 80 else query
                await status_callback("searching_web", f"Searching for: {query_preview}")
            
            # Enrich the query with context from chat history
            enriched_query = await self._enrich_search_query(raw_query=query, chat_history=chat_history or [], context_type="web")
            
            # Use cached web search tool or create new one
            if not self._web_search_tool:
                self._web_search_tool = WebSearchTool()
                logger.info("Created new WebSearchTool instance (cached for reuse)")
            web_search_tool = self._web_search_tool
            
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
            
            # PARALLEL STEP 1: Assess relevance of all results in parallel
            if status_callback:
                await status_callback("assessing_relevance", f"Evaluating relevance of {len(results)} search results...")
            
            relevance_tasks = []
            result_items = []
            for i, result_item in enumerate(results, 1):
                title = result_item.get("title", "No Title")
                snippet = result_item.get("snippet", "No content available")
                url = result_item.get("url", "#")
                
                # Create coroutine for parallel relevance assessment
                task = self._assess_search_result_relevance(
                    query=query,
                    title=title,
                    snippet=snippet,
                    url=url
                )
                relevance_tasks.append(task)
                result_items.append((i, result_item))
            
            # Execute all relevance assessments in parallel using asyncio.gather
            relevance_assessments = await asyncio.gather(*relevance_tasks, return_exceptions=True)
            
            # Process results and handle any exceptions
            relevance_results = []
            for (i, result_item), is_relevant in zip(result_items, relevance_assessments):
                if isinstance(is_relevant, Exception):
                    logger.error(f"Error assessing relevance for result {i}: {is_relevant}")
                    is_relevant = False  # Default to not relevant on error
                relevance_results.append((i, result_item, is_relevant))
            
            logger.info(f"Completed parallel relevance assessment for {len(results)} results")
            
            # Filter relevant results for content fetching
            relevant_results = [(i, item) for i, item, is_relevant in relevance_results if is_relevant]
            non_relevant_count = len(results) - len(relevant_results)
            
            if non_relevant_count > 0:
                logger.info(f"Filtered {non_relevant_count} non-relevant results out of {len(results)} total")
            
            # PARALLEL STEP 2: Fetch content for all relevant results in parallel
            if relevant_results and status_callback:
                await status_callback("fetching_content", f"Fetching full content from {len(relevant_results)} relevant sources...")
            
            fetch_tasks = []
            fetch_items = []
            for i, result_item in relevant_results:
                url = result_item.get("url", "#")
                # Create coroutine for parallel content fetching
                task = self._fetch_web_page_content(url, session_id)
                fetch_tasks.append(task)
                fetch_items.append((i, result_item))
            
            # Execute all content fetches in parallel using asyncio.gather
            if fetch_tasks:
                fetched_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            else:
                fetched_results = []
            
            # Process fetched contents and handle exceptions
            fetched_contents = []
            for (i, result_item), content in zip(fetch_items, fetched_results):
                if isinstance(content, Exception):
                    logger.error(f"Error fetching content for result {i}: {content}")
                    content = {"error": str(content)}
                fetched_contents.append((i, result_item, content))
            
            logger.info(f"Completed parallel content fetching for {len(relevant_results)} relevant results")
            
            # Track web fetches for stats
            if session_id and relevant_results:
                # Track all fetches at once
                for _ in relevant_results:
                    await self.stats_tracker.track_web_fetch(session_id)
            
            # Format results with fetched content
            formatted_results = f"\n\n=== WEB SEARCH RESULTS ===\nOriginal Query: {query}\nEnriched Query: {enriched_query}\nProvider: {config.WEB_SEARCH_PROVIDER.capitalize()}\nResults found: {len(results)}\n\n"
            sources = []
            
            # Create reference ID mapping for citations
            import hashlib
            
            # Process fetched contents
            for i, result_item, full_content in fetched_contents:
                title = result_item.get("title", "No Title")
                snippet = result_item.get("snippet", "No content available")
                url = result_item.get("url", "#")
                
                # Generate a stable reference ID for this source (using URL hash)
                ref_id = hashlib.sha1(url.encode()).hexdigest()[:8]
                
                if full_content and "error" not in full_content:
                    # Use full content instead of snippet
                    content_text = full_content.get("text", snippet)[:5000]  # Limit content length
                    formatted_results += f"**Result {i}: {title}** [FULL CONTENT]\n"
                    formatted_results += f"Source: {url}\n"
                    formatted_results += f"**Citation ID: [{ref_id}]** - Use this ID when citing information from this source\n"
                    formatted_results += f"Content: {content_text}\n\n"
                    
                    # Add to sources list with reference ID
                    sources.append({
                        "type": "web",
                        "title": title,
                        "url": url,
                        "ref_id": ref_id,
                        "provider": config.WEB_SEARCH_PROVIDER.capitalize()
                    })
                else:
                    # Fall back to snippet if fetch failed
                    logger.warning(f"Failed to fetch full content for {url[:60]}, using snippet")
                    formatted_results += f"**Result {i}: {title}**\n"
                    formatted_results += f"Source: {url}\n"
                    formatted_results += f"**Citation ID: [{ref_id}]** - Use this ID when citing information from this source\n"
                    formatted_results += f"Content: {snippet}\n\n"
                    
                    # Still add to sources since we're using the snippet
                    sources.append({
                        "type": "web",
                        "title": title,
                        "url": url,
                        "ref_id": ref_id,
                        "provider": config.WEB_SEARCH_PROVIDER.capitalize()
                    })
            
            # Add summary of filtered results
            if non_relevant_count > 0:
                formatted_results += f"\n[Note: {non_relevant_count} out of {len(results)} sources were deemed not relevant and excluded]\n\n"
            
            formatted_results += "=== END WEB SEARCH RESULTS ===\n"
            
            logger.info(f"Web search completed successfully with parallel processing, found {len(results)} results, {len(sources)} relevant")
            return formatted_results, sources
            
        except Exception as e:
            logger.error(f"Error performing web search: {e}", exc_info=True)
            return f"\n\n[Web Search Error: {str(e)}]\n", []

    async def _search_documents(self, query: str, document_group_id: str, chat_history: List[Dict[str, str]] = None, session_id: str = None, max_doc_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
        """
        Searches documents in the specified group with query enrichment and returns relevant content with source metadata.
        Returns: (formatted_results, sources_list)
        """
        try:
            from ai_researcher.agentic_layer.tools.document_search import DocumentSearchTool
            from ai_researcher.core_rag.retriever import Retriever
            from ai_researcher.core_rag.query_preparer import QueryPreparer
            from ai_researcher.core_rag.query_strategist import QueryStrategist
            from ai_researcher.core_rag.embedder import TextEmbedder
            from ai_researcher.core_rag.reranker import TextReranker
            
            # Enrich the query with context from chat history for document search
            enriched_query = await self._enrich_search_query(raw_query=query, chat_history=chat_history or [], context_type="document")
            
            # Use cached RAG components when possible
            logger.info(f"Using document search components for group: {document_group_id}")
            
            # Initialize the new clean vector store using singleton
            try:
                from ai_researcher.core_rag.vector_store_singleton import get_vector_store
                vector_store = get_vector_store()  # Uses singleton instance
                
                # Health check
                if not vector_store.healthcheck():
                    logger.error("Vector store health check failed")
                    return "Error: Document database is not accessible. Please try again later.", []
                
                logger.info("Vector store initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize vector store: {e}", exc_info=True)
                return f"Error: Unable to access document database. Error: {str(e)}", []
            try:
                # Use cached model instances to avoid repeated initialization
                from ai_researcher.core_rag.model_cache import model_cache
                embedder = model_cache.get_embedder()
                reranker = model_cache.get_reranker()
                
                # Use cached retriever or create new one
                if not self._retriever:
                    self._retriever = Retriever(
                        vector_store=vector_store,
                        embedder=embedder,
                        reranker=reranker
                    )
                    logger.info("Created new Retriever instance (cached for reuse)")
            except Exception as e:
                logger.error(f"Failed to initialize retriever components: {e}", exc_info=True)
                return f"Error: Failed to initialize search components. Error: {str(e)}", []
            
            # Use cached query components or create new ones
            if not self._query_preparer:
                self._query_preparer = QueryPreparer(model_dispatcher=self.model_dispatcher)
                logger.info("Created new QueryPreparer instance (cached for reuse)")
            
            query_strategist = QueryStrategist(model_dispatcher=self.model_dispatcher)
            
            # Use cached document search tool or create new one
            if not self._document_search_tool:
                self._document_search_tool = DocumentSearchTool(
                    retriever=self._retriever,
                    query_preparer=self._query_preparer,
                    query_strategist=query_strategist
                )
                logger.info("Created new DocumentSearchTool instance (cached for reuse)")
            doc_search_tool = self._document_search_tool
            
            # Perform the search with enriched query
            logger.info(f"Executing document search for enriched query: {enriched_query} in group: {document_group_id}")
            results = await doc_search_tool.execute(
                query=enriched_query,
                n_results=max_doc_results,
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
                
                # Use the first 8 chars of doc_id as reference ID (or generate one if doc_id is missing)
                if doc_id != "Unknown" and len(doc_id) >= 8:
                    ref_id = doc_id[:8]
                else:
                    # Generate a hash-based ID from content for consistency
                    import hashlib
                    ref_id = hashlib.sha1(text.encode()).hexdigest()[:8]
                
                formatted_results += f"**Document Result {i}**\n"
                formatted_results += f"Source: {filename} (Page {page_num})\n"
                formatted_results += f"Document ID: {doc_id}\n"
                formatted_results += f"**Citation ID: [{ref_id}]** - Use this ID when citing information from this document\n"
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
                        "ref_id": ref_id,
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
                f"IMPORTANT: If you see notes about sources being filtered as not relevant, "
                f"score the quality MUCH lower (typically 2-3/10) and suggest query refinements.\n\n"
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

    async def _decompose_complex_query(self, query: str, chat_history: List[Dict[str, str]] = None, search_type: str = "web", max_queries: int = 10) -> List[str]:
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
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            current_year = datetime.now().year
            
            # Extract recent context for better decomposition
            recent_context = ""
            if chat_history:
                # Take last 4 messages (2 exchanges) for context
                recent_messages = chat_history[-4:] if len(chat_history) > 4 else chat_history
                # Format as conversation
                context_parts = []
                for msg in recent_messages:
                    role = "User" if msg["role"] == "user" else "Assistant"
                    context_parts.append(f"{role}: {msg['content']}")
                recent_context = '\n'.join(context_parts)
            
            decomposition_prompt = (
                f"You are a query decomposition specialist. Your job is to analyze complex queries and break them down into "
                f"separate, focused search queries that will yield better results when searched individually.\n\n"
                f"CRITICAL: You MUST respond with ONLY a valid JSON array, nothing else.\n\n"
                f"CURRENT DATE CONTEXT:\n"
                f"- Today's date: {current_date}\n"
                f"- Current year: {current_year}\n"
                f"- When user asks for 'current', 'recent', 'latest', 'happening right now', use {current_year}\n"
                f"- NEVER use past years when user asks about current events\n\n"
                f"IMPORTANT: Generate UP TO {max_queries} focused queries. If the query is simple, generate fewer queries.\n\n"
                f"Rules for decomposition:\n"
                f"1. Identify distinct topics, locations, or concepts in the query\n"
                f"2. Create separate focused queries for each distinct aspect\n"
                f"3. Each query should be self-contained and specific\n"
                f"4. Avoid combining multiple locations or topics in a single query\n"
                f"5. Preserve the user's intent and context\n"
                f"6. Generate between 1 and {max_queries} queries based on complexity\n"
                f"7. Use current year ({current_year}) for any queries about recent/current events\n\n"
                f"Examples:\n"
                f'Input: "fun activities in New York and restaurants in Paris"\n'
                f'Output: ["fun activities and attractions in New York City", "best restaurants and dining in Paris France"]\n\n'
                f'Input: "machine learning tutorials and data science courses"\n'
                f'Output: ["machine learning tutorials and guides", "data science courses and training programs"]\n\n'
                f'Input: "what are the leading text to image breakthroughs happening right now?" (asked in {current_year})\n'
                f'Output: ["leading text to image breakthroughs", "recent advancements in text to image generation", "current trends in text to image models"]\n\n'
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

    async def _perform_iterative_web_search(self, query: str, chat_history: List[Dict[str, str]] = None, session_id: str = None, status_callback: Optional[callable] = None, max_attempts: int = 3, max_decomposed_queries: int = 10, max_search_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
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
                # Show query text like document search does
                query_preview = focused_query[:50] + "..." if len(focused_query) > 50 else focused_query
                search_msg = f"Web search {i}/{len(decomposed_queries)}: {query_preview}"
                await status_callback("searching_web", search_msg)
            
            logger.info(f"Executing focused web search {i}/{len(decomposed_queries)}: {focused_query}")
            
            # Perform iterative search for this focused query
            focused_results, focused_sources = await self._perform_focused_iterative_web_search(
                focused_query, query, chat_history, session_id, seen_urls, max_attempts, status_callback, max_search_results,
                search_number=i, total_searches=len(decomposed_queries)
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

    async def _perform_focused_iterative_web_search(self, focused_query: str, original_query: str, chat_history: List[Dict[str, str]] = None, session_id: str = None, global_seen_urls: set = None, max_attempts: int = 3, status_callback: Optional[callable] = None, max_search_results: int = 5, search_number: int = 1, total_searches: int = 1) -> tuple[str, List[Dict[str, Any]]]:
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
                
                # Send detailed status update with query text
                if status_callback:
                    query_preview = current_query[:50] + "..." if len(current_query) > 50 else current_query
                    if max_attempts > 1:
                        if attempt == 0:
                            quality_msg = f"[Search {search_number}/{total_searches}] Searching for: {query_preview}"
                        else:
                            quality_msg = f"[Search {search_number}/{total_searches}] Refining: {query_preview} (attempt {attempt + 1}/{max_attempts})"
                    else:
                        # For single iteration, show the query
                        quality_msg = f"Web search {search_number}/{total_searches}: {query_preview}"
                    
                    await status_callback("searching_web", quality_msg)
                
                # Use existing query enrichment method for better search terms
                enriched_query = await self._enrich_search_query(current_query, chat_history, "web")
                
                # Perform the search with the enriched query
                try:
                    from ai_researcher.agentic_layer.tools.web_search_tool import WebSearchTool
                    from ai_researcher import config
                    
                    # Use cached web search tool or create new one
                    if not self._web_search_tool:
                        self._web_search_tool = WebSearchTool()
                        logger.info("Created new WebSearchTool instance (cached for reuse)")
                    web_search_tool = self._web_search_tool
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
                            # PARALLEL PROCESSING: Process all results in parallel
                            search_results = f"\n\nFocused Query: {current_query}\nEnriched Query: {enriched_query}\nProvider: {config.WEB_SEARCH_PROVIDER.capitalize()}\nResults found: {len(results)}\n\n"
                            
                            # Filter out already-seen URLs first
                            unseen_results = []
                            for i, result_item in enumerate(results, 1):
                                url = result_item.get("url", "#")
                                if url not in global_seen_urls and url not in local_seen_urls:
                                    unseen_results.append((i, result_item))
                                    local_seen_urls.add(url)  # Track immediately
                                else:
                                    if url in global_seen_urls:
                                        logger.debug(f"Filtered globally seen URL: {url[:60]}...")
                                    else:
                                        logger.debug(f"Filtered locally seen URL: {url[:60]}...")
                            
                            if unseen_results:
                                # STEP 1: Assess relevance of all unseen results in parallel
                                if status_callback and len(unseen_results) > 1:
                                    await status_callback("assessing_relevance", f"[Search {search_number}/{total_searches}] Evaluating {len(unseen_results)} results...")
                                
                                relevance_tasks = []
                                for i, result_item in unseen_results:
                                    title = result_item.get("title", "No Title")
                                    snippet = result_item.get("snippet", "No content available")
                                    url = result_item.get("url", "#")
                                    
                                    task = self._assess_search_result_relevance(
                                        query=original_query,
                                        title=title,
                                        snippet=snippet,
                                        url=url
                                    )
                                    relevance_tasks.append((i, result_item, task))
                                
                                # Execute all relevance assessments in parallel
                                all_relevance_coroutines = [task for _, _, task in relevance_tasks]
                                relevance_assessments = await asyncio.gather(*all_relevance_coroutines, return_exceptions=True)
                                
                                # Process results
                                relevance_results = []
                                for (i, result_item, _), is_relevant in zip(relevance_tasks, relevance_assessments):
                                    if isinstance(is_relevant, Exception):
                                        logger.error(f"Error assessing relevance for result {i}: {is_relevant}")
                                        is_relevant = False
                                    relevance_results.append((i, result_item, is_relevant))
                                
                                # Filter relevant results
                                relevant_for_fetch = [(i, item) for i, item, is_relevant in relevance_results if is_relevant]
                                
                                if relevant_for_fetch:
                                    # STEP 2: Fetch content for all relevant results in parallel
                                    if status_callback:
                                        await status_callback("fetching_content", f"[Search {search_number}/{total_searches}] Fetching {len(relevant_for_fetch)} relevant sources...")
                                    
                                    fetch_tasks = []
                                    for i, result_item in relevant_for_fetch:
                                        url = result_item.get("url", "#")
                                        task = self._fetch_web_page_content(url, session_id)
                                        fetch_tasks.append((i, result_item, task))
                                    
                                    # Execute all fetches in parallel
                                    fetched_contents = await asyncio.gather(*[task for _, _, task in fetch_tasks], return_exceptions=True)
                                    
                                    # Track all web fetches for stats
                                    if session_id:
                                        for _ in relevant_for_fetch:
                                            await self.stats_tracker.track_web_fetch(session_id)
                                    
                                    # Process fetched content
                                    search_sources = []
                                    for (i, result_item, _), content in zip(fetch_tasks, fetched_contents):
                                        title = result_item.get("title", "No Title")
                                        snippet = result_item.get("snippet", "No content available")
                                        url = result_item.get("url", "#")
                                        
                                        if isinstance(content, Exception):
                                            logger.error(f"Error fetching content: {content}")
                                            content = {"error": str(content)}
                                        
                                        # Generate a stable reference ID for this source (using URL hash)
                                        import hashlib
                                        ref_id = hashlib.sha1(url.encode()).hexdigest()[:8]
                                        
                                        if content and "error" not in content:
                                            # Use full content
                                            content_text = content.get("text", snippet)[:5000]
                                            search_results += f"**Result {i}: {title}** [FULL CONTENT]\n"
                                            search_results += f"Source: {url}\n"
                                            search_results += f"**Citation ID: [{ref_id}]** - Use this ID when citing information from this source\n"
                                            search_results += f"Content: {content_text}\n\n"
                                            
                                            search_sources.append({
                                                "type": "web",
                                                "title": title,
                                                "url": url,
                                                "ref_id": ref_id,
                                                "provider": config.WEB_SEARCH_PROVIDER.capitalize()
                                            })
                                        else:
                                            # Fall back to snippet
                                            logger.warning(f"Failed to fetch full content for {url[:60]}, using snippet")
                                            search_results += f"**Result {i}: {title}**\n"
                                            search_results += f"Source: {url}\n"
                                            search_results += f"**Citation ID: [{ref_id}]** - Use this ID when citing information from this source\n"
                                            search_results += f"Content: {snippet}\n\n"
                                            
                                            search_sources.append({
                                                "type": "web",
                                                "title": title,
                                                "url": url,
                                                "ref_id": ref_id,
                                                "provider": config.WEB_SEARCH_PROVIDER.capitalize()
                                            })
                                else:
                                    search_sources = []
                                    logger.info(f"No relevant results found in {len(unseen_results)} unseen URLs")
                            else:
                                search_sources = []
                                logger.info("All URLs were already seen")
                            
                            # Add summary of filtered results
                            total_results = len(results)
                            relevant_results = len(search_sources)
                            non_relevant_count = total_results - relevant_results
                            
                            if non_relevant_count > 0:
                                search_results += f"\n[Note: {non_relevant_count} out of {total_results} sources were deemed not relevant and excluded]\n"
                            
                            search_results += "\n"
                            
                except Exception as search_error:
                    logger.error(f"Error performing focused web search: {search_error}", exc_info=True)
                    search_results = f"\n\n[Focused Web Search Error: {str(search_error)}]\n"
                    search_sources = []
                
                # Check if we found NO relevant sources at all
                if len(search_sources) == 0 and attempt < max_attempts:
                    # Force at least one more attempt when no sources are relevant
                    logger.info(f"No relevant sources found on attempt {attempt + 1}, forcing additional attempt")
                    max_attempts = max(max_attempts, attempt + 2)  # Ensure at least one more try
                
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

    async def _perform_iterative_document_search(self, query: str, document_group_id: str, chat_history: List[Dict[str, str]] = None, session_id: str = None, status_callback: Optional[callable] = None, max_attempts: int = 3, max_decomposed_queries: int = 10, max_doc_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
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
                focused_query, query, document_group_id, chat_history, session_id, seen_doc_ids, max_attempts, status_callback, max_doc_results
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

    async def _perform_focused_iterative_document_search(self, focused_query: str, original_query: str, document_group_id: str, chat_history: List[Dict[str, str]] = None, session_id: str = None, global_seen_docs: set = None, max_attempts: int = 3, status_callback: Optional[callable] = None, max_doc_results: int = 5) -> tuple[str, List[Dict[str, Any]]]:
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
                search_results, search_sources = await self._search_documents(current_query, document_group_id, chat_history, session_id, max_doc_results)
                
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

    async def _run_main_llm(self, prompt: str, draft_content: str, chat_history: List[Dict[str, str]], external_context: str = "", context_info: Dict[str, Any] = None) -> str:
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
        document_group_name = context_info.get("document_group_name")
        document_search_enabled = bool(document_group_id)
        
        tool_status = f"\n\nCURRENT TOOL STATUS:\n"
        tool_status += f"- Web Search: {'ENABLED' if web_search_enabled else 'DISABLED'}\n"
        tool_status += f"- Document Search: {'ENABLED' if document_search_enabled else 'DISABLED'}"
        if document_search_enabled:
            group_display = document_group_name if document_group_name else document_group_id
            tool_status += f" (Document Group: {group_display})"
        tool_status += "\n"
        
        # Get custom system prompt addition from context_info
        custom_system_prompt_addition = context_info.get("custom_system_prompt", "")
        
        # Default system prompt (always used as base)
        system_prompt = (
            "You are Maestro, a collaborative writing assistant helping users write documents. "
            "Your responses should be helpful, informative, and directly address the user's request. "
            "You have access to information about which tools are currently enabled or disabled. "
            "\n\nCRITICAL - MATHEMATICAL NOTATION: Always use standard Markdown/LaTeX notation:\n"
            "• For inline math: $formula$ (single dollar signs)\n"
            "• For display math: $$formula$$ (double dollar signs on separate lines)\n"
            "• NEVER use square brackets [ ], parentheses \\( \\), or \\begin{equation} for math delimiters\n"
            "If a user's request would benefit from a tool that is currently disabled, suggest they enable it.\n\n"
            "CITATION INSTRUCTIONS:\n"
            "When you have access to external information (web search or document search results), you MUST:\n"
            "1. Integrate that information naturally into your response\n"
            "2. Add citations using the EXACT Citation IDs provided in square brackets\n"
            "3. Place citations IMMEDIATELY after the relevant statement or claim\n"
            "4. Use ONLY the 8-character Citation IDs shown in the search results\n\n"
            "CORRECT citation examples:\n"
            "- 'Recent studies show that climate change is accelerating [a3b4c5d6].'\n"
            "- 'The document states that revenue increased by 25% [f2e8d9c1] in Q3.'\n"
            "- 'According to the research [b7a4e3f2], this method improves accuracy.'\n\n"
            "INCORRECT citations (NEVER do this):\n"
            "- 'Recent studies show this [1].' ← Wrong! Don't use numbers\n"
            "- 'The data shows [Source 1]...' ← Wrong! Use the exact Citation ID\n"
            "- 'According to research...' ← Wrong! Missing citation\n\n"
            "Each search result will show '**Citation ID: [xxxxxxxx]**' - use these EXACT IDs.\n"
            "If the user's request implies changes to the document, describe what changes you would make. "
            "Always be specific about where information comes from when using external sources.\n\n"
            "WRITING STYLE GUIDELINES:\n"
            "Use bullet points only sparingly and only if absolutely necessary. Otherwise, write in reasonably length paragraphs that flow naturally and provide comprehensive coverage of topics.\n\n"
            "IMPORTANT FORMATTING INSTRUCTIONS:\n"
            "When generating substantial content, wrap each distinct content block using this format:\n"
            "```content-block:BLOCK_TYPE\n"
            "Your content here...\n"
            "```\n\n"
            "Available BLOCK_TYPE options (USE THE MOST APPROPRIATE ONE):\n"
            "- document: Complete document or article (use for full documents with multiple sections)\n"
            "- section: Individual section with headings and content (use for major parts of a document)\n"
            "- paragraph: Single paragraph or brief explanatory text (use for short responses)\n"
            "- list: Bullet points or numbered lists (use ONLY for actual lists)\n"
            "- note: Important notes, warnings, or callouts (use sparingly for special notices)\n"
            "- code: ONLY for actual programming code, scripts, or terminal commands\n\n"
            "CRITICAL RULES:\n"
            "1. DO NOT use 'code' block type for regular text, formulas, or tables\n"
            "2. For mathematical formulas and equations:\n"
            "   - Use single dollar signs for inline math: $E = mc^2$\n"
            "   - Use double dollar signs for display math: $$\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}$$\n"
            "   - NEVER use square brackets [ ] or parentheses \\( \\) for LaTeX delimiters\n"
            "   - ALWAYS escape backslashes in LaTeX commands (use \\\\ instead of \\)\n"
            "3. For tables, use 'section' or 'paragraph' with Markdown table syntax\n"
            "4. Default to 'section' for most structured content\n"
            "5. Use 'paragraph' for brief responses\n\n"
            "Example for scientific content with formulas:\n"
            "```content-block:section\n"
            "# Mathematical Formulas\n\n"
            "The quadratic equation $ax^2 + bx + c = 0$ has solutions given by:\n\n"
            "$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$\n\n"
            "For quantum mechanics, the Schrödinger equation is:\n\n"
            "$$i\\hbar\\frac{\\partial}{\\partial t}\\Psi = \\hat{H}\\Psi$$\n\n"
            "Note how we use $ for inline math and $$ for display equations.\n"
            "```\n\n"
            "WRONG FORMAT (NEVER DO THIS):\n"
            "- [ \\hbar\\frac{\\partial}{\\partial t}\\Psi ] ← Wrong! Use $$ instead\n"
            "- \\( E = mc^2 \\) ← Wrong! Use $ instead\n"
            "- \\begin{equation}...\\end{equation} ← Wrong! Use $$ instead"
        )
        
        # Append user's custom instructions if provided
        if custom_system_prompt_addition and custom_system_prompt_addition.strip():
            system_prompt += f"\n\nADDITIONAL USER INSTRUCTIONS:\n{custom_system_prompt_addition.strip()}"
        
        if external_context:
            # Check if we have the "sources were deemed not relevant" note
            if "sources were deemed not relevant and excluded" in external_context:
                system_prompt += (
                    "\n\nIMPORTANT: Some or all search results were filtered as not relevant to your query. "
                    "You should inform the user that you couldn't find highly relevant current sources. "
                    "Suggest they either: 1) Enable deep search mode for more thorough results, 2) Rephrase their query to be more specific, "
                    "or 3) Check if the information they're looking for might be too recent or specialized. "
                    "Do NOT attempt to answer based on general knowledge when the user explicitly asked for current/recent information."
                )
            else:
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
        
        # Build messages list with proper structure
        messages = []
        
        # Add system message
        messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history as proper messages (limit to recent history)
        MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages
        if len(chat_history) > MAX_HISTORY_MESSAGES:
            recent_history = chat_history[-MAX_HISTORY_MESSAGES:]
        else:
            recent_history = chat_history
        
        # Add the conversation history, ensuring role alternation
        last_role = "system"
        for msg in recent_history:
            # Skip if same role as previous to maintain alternation
            if msg["role"] == last_role:
                # If it's the same role, we need to merge or skip
                if last_role == "user":
                    # For consecutive user messages, merge them
                    messages[-1]["content"] += "\n\n" + msg["content"]
                elif last_role == "assistant":
                    # For consecutive assistant messages, merge them
                    messages[-1]["content"] += "\n\n" + msg["content"]
                # Skip system messages that would break alternation
                continue
            else:
                messages.append({"role": msg["role"], "content": msg["content"]})
                last_role = msg["role"]
        
        # Build the current user message with all context
        user_content = f"Current Draft:\n```markdown\n{draft_content}\n```\n\nUser Context:\n{user_context}"
        user_content += tool_status
        
        if external_context:
            user_content += f"\n\nExternal Information Available:\n{external_context}"
        
        user_content += f"\n\nUser Request: {prompt}"
        
        # Only add user message if the last message wasn't from user
        if last_role == "user":
            # Merge with the last user message
            messages[-1]["content"] += "\n\n" + user_content
        else:
            messages.append({"role": "user", "content": user_content})

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

    def _process_citations_and_filter_sources(self, content: str, sources: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
        """
        Process citation placeholders in the content, replace them with numbered references,
        and filter sources to only include those actually cited.
        Maps the reference IDs (e.g., [a3b4c5d6]) to sequential numbers [1], [2], etc.
        
        Args:
            content: The generated content with citation placeholders
            sources: List of source dictionaries with ref_id fields
            
        Returns:
            Tuple of (processed content with numbered citations, filtered and numbered sources)
        """
        if not sources:
            return content, []
        
        import re
        
        # Find all citation placeholders in the content
        # Pattern matches [8-char-hex] format
        citation_pattern = re.compile(r'\[([a-f0-9]{8})\]')
        
        # Find all unique ref_ids that are actually cited in the content
        cited_ref_ids = []
        seen_ref_ids = set()
        
        for match in citation_pattern.finditer(content):
            ref_id = match.group(1)
            if ref_id not in seen_ref_ids:
                cited_ref_ids.append(ref_id)
                seen_ref_ids.add(ref_id)
        
        # Filter sources to only include those that are cited
        # and create mapping from ref_id to new number
        ref_id_to_number = {}
        used_sources = []
        
        for ref_id in cited_ref_ids:
            # Find the source with this ref_id
            for source in sources:
                if source.get("ref_id") == ref_id:
                    # Assign the next number
                    new_number = len(used_sources) + 1
                    ref_id_to_number[ref_id] = new_number
                    
                    # Add the source with its reference number
                    source_copy = source.copy()
                    source_copy['reference_number'] = new_number
                    used_sources.append(source_copy)
                    break
        
        # Replace all citations with their new numbers
        def replace_citation(match):
            ref_id = match.group(1)
            if ref_id in ref_id_to_number:
                return f"[{ref_id_to_number[ref_id]}]"
            else:
                # If ref_id not found in sources, keep original
                logger.warning(f"Citation ID [{ref_id}] not found in sources")
                return match.group(0)
        
        # Replace all citations with numbers
        processed_content = citation_pattern.sub(replace_citation, content)
        
        return processed_content, used_sources
    
    def _process_citations(self, content: str, sources: List[Dict[str, Any]]) -> str:
        """
        Process citation placeholders in the content and replace them with numbered references.
        Maps the reference IDs (e.g., [a3b4c5d6]) to sequential numbers [1], [2], etc.
        
        Args:
            content: The generated content with citation placeholders
            sources: List of source dictionaries with ref_id fields
            
        Returns:
            Content with processed citations
        """
        if not sources:
            return content
        
        import re
        
        # Create mapping from ref_id to number
        ref_id_to_number = {}
        for i, source in enumerate(sources, 1):
            ref_id = source.get("ref_id")
            if ref_id:
                ref_id_to_number[ref_id] = i
        
        # Find all citation placeholders in the content
        # Pattern matches [8-char-hex] format
        citation_pattern = re.compile(r'\[([a-f0-9]{8})\]')
        
        def replace_citation(match):
            ref_id = match.group(1)
            if ref_id in ref_id_to_number:
                return f"[{ref_id_to_number[ref_id]}]"
            else:
                # If ref_id not found, keep original
                logger.warning(f"Citation ID [{ref_id}] not found in sources")
                return match.group(0)
        
        # Replace all citations with numbers
        processed_content = citation_pattern.sub(replace_citation, content)
        
        return processed_content
    
    def _format_sources(self, sources: List[Dict[str, Any]]) -> str:
        """
        Formats sources into a numbered reference section for inline citations.
        Numbers correspond to the citation numbers in the processed content.
        """
        if not sources:
            return ""
        
        formatted = "\n\n---\n**References:**\n"
        
        # Format sources in order with their assigned numbers
        for i, source in enumerate(sources, 1):
            source_type = source.get("type", "unknown")
            
            if source_type == "web":
                title = source.get("title", "Web Source")
                url = source.get("url", "#")
                # Truncate long titles for display
                display_title = title[:60] + "..." if len(title) > 60 else title
                formatted += f"[{i}] [{display_title}]({url})\n"
            elif source_type == "document":
                title = source.get("title", "Document")
                page = source.get("page", "")
                # Truncate long titles for display
                display_title = title[:50] + "..." if len(title) > 50 else title
                page_info = f" (p.{page})" if page and page != "Unknown" else ""
                formatted += f"[{i}] {display_title}{page_info}\n"
        
        return formatted
    
    async def _assess_search_result_relevance(self, query: str, title: str, snippet: str, url: str) -> bool:
        """
        Assess if a search result is relevant enough to warrant fetching full content.
        Uses the fast LLM to make a quick decision.
        
        Args:
            query: The original search query
            title: The title of the search result
            snippet: The snippet/summary of the search result
            url: The URL of the search result
            
        Returns:
            True if relevant enough to fetch full content, False otherwise
        """
        try:
            # Create a prompt for the fast LLM to assess relevance
            relevance_prompt = f"""Assess if this search result is relevant to the query.

Query: {query}

Search Result:
Title: {title}
URL: {url}
Snippet: {snippet}

Is this result relevant enough that we should fetch and read the full content of the page?
Consider:
- Does it relate to the query topic (even partially)?
- Does the snippet suggest it might contain useful information?
- Could it provide context or background information?

Be inclusive - if there's any chance it could be useful, say YES.
Respond with only YES or NO."""

            # Use the fast model for quick assessment
            # Create properly formatted messages for the dispatcher
            messages = [
                {"role": "system", "content": "You are a relevance assessor. Respond with only YES or NO."},
                {"role": "user", "content": relevance_prompt}
            ]
            
            # Use agent_mode to select the fast model type
            # The dispatcher will look up the appropriate model based on the mode
            response, _ = await self.model_dispatcher.dispatch(
                messages=messages,
                agent_mode="router"  # Router mode uses the fast model
            )
            
            # Parse the response - response is a ChatCompletion object
            if response and hasattr(response, 'choices') and response.choices:
                decision = response.choices[0].message.content.strip().upper()
                is_relevant = "YES" in decision
            else:
                # Default to not fetching on error
                is_relevant = False
            
            logger.info(f"Relevance assessment for result '{title[:50]}...': {'YES - will fetch full content' if is_relevant else 'NO - using snippet only'}")
            return is_relevant
            
        except Exception as e:
            logger.error(f"Error assessing relevance: {e}")
            # Default to not fetching on error to avoid excessive fetches
            return False
    
    async def _fetch_web_page_content(self, url: str, session_id: str = None) -> Dict[str, Any]:
        """
        Fetch the full content of a web page using the configured web fetcher.
        
        Args:
            url: The URL to fetch
            session_id: Optional session ID for tracking
            
        Returns:
            Dict with 'text' key containing the fetched content, or 'error' key on failure
        """
        try:
            # Import the web fetcher tool
            from ai_researcher.agentic_layer.tools.web_page_fetcher_tool import WebPageFetcherTool
            
            # Use cached fetcher or create new one
            if not self._web_page_fetcher:
                self._web_page_fetcher = WebPageFetcherTool()
                logger.info("Created new WebPageFetcherTool instance (cached for reuse)")
            fetcher = self._web_page_fetcher
            
            # Execute the fetch
            logger.debug(f"Fetching full content from: {url[:100]}...")
            result = await fetcher.execute(url=url, mission_id=session_id)
            
            if "error" in result:
                logger.warning(f"Failed to fetch content from {url[:60]}: {result['error']}")
                return result
            
            # Successfully fetched
            logger.debug(f"Successfully fetched {len(result.get('text', ''))} chars from {url[:60]}")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching web page content from {url[:60]}: {e}")
            return {"error": str(e)}
