import asyncio # For concurrent retrieval
import logging # For logging
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

# Use absolute import from the project root
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.query_preparer import QueryPreparer # Import QueryPreparer
from ai_researcher.core_rag.query_strategist import QueryStrategist # Import QueryStrategist

logger = logging.getLogger(__name__)

# Use absolute import from the project root
from ai_researcher.core_rag.retriever import Retriever

# Define the input schema for the document search tool
class DocumentSearchInput(BaseModel):
    query: str = Field(..., description="The search query text.")
    n_results: int = Field(5, description="Number of results to retrieve.")
    filter_doc_id: Optional[str] = Field(None, description="Optional document ID to filter results.")
    # Add other potential parameters like weights if needed by agents
    dense_weight: float = Field(0.5, description="Weight for dense search results.")
    sparse_weight: float = Field(0.5, description="Weight for sparse search results.")
    use_reranker: bool = Field(True, description="Whether to use the reranker if available.")
    research_context: Optional[str] = Field(None, description="Optional overall research goal/context.")
    agent_context: Optional[str] = Field(None, description="Optional context from the calling agent (e.g., current section).")


class DocumentSearchTool:
    """
    A tool for agents to search the document knowledge base using the core RAG Retriever.
    """
    def __init__(
        self,
        retriever: Retriever,
        query_preparer: QueryPreparer,
        query_strategist: QueryStrategist
    ):
        if not isinstance(retriever, Retriever):
             raise TypeError("DocumentSearchTool requires an instance of the Retriever class.")
        if not isinstance(query_preparer, QueryPreparer):
             raise TypeError("DocumentSearchTool requires an instance of the QueryPreparer class.")
        if not isinstance(query_strategist, QueryStrategist):
             raise TypeError("DocumentSearchTool requires an instance of the QueryStrategist class.")
        self.retriever = retriever
        self.preparer = query_preparer
        self.strategist = query_strategist
        self.name = "document_search"
        self.description = "Searches the internal knowledge base (research papers, documents) for relevant information based on a query. Use this to find specific facts, summaries, or context from the ingested documents."
        self.parameters_schema = DocumentSearchInput
        print("DocumentSearchTool initialized.")

    async def execute( # Make method async
        self,
        query: str,
        n_results: int = 5,
        filter_doc_id: Optional[str] = None,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.5,
        use_reranker: bool = True,
        research_context: Optional[str] = None, # Add context params
        agent_context: Optional[str] = None     # Add context params
    ) -> List[Dict[str, Any]]:
        """
        Executes the document search using the Retriever, QueryStrategist, and QueryPreparer.

        Args:
            query: The search query text.
            n_results: Number of results desired.
            filter_doc_id: Optional document ID to filter by.
            dense_weight: Weight for dense search.
            sparse_weight: Weight for sparse search.
            use_reranker: Whether to apply final reranking to aggregated results.
            research_context: Optional overall research goal/context for strategy.
            agent_context: Optional agent task context for strategy.

        Returns:
            A list of search result dictionaries, potentially formatted for agent consumption.
            Returns an empty list on failure.
        """
        logger.info(f"Executing Document Search Tool with query: '{query}'")
        all_results = []
        model_details_strategy = None
        model_details_prepare = []

        try:
            # 1. Determine Strategy
            chosen_techniques, model_details_strategy = await self.strategist.determine_techniques(
                original_query=query,
                research_context=research_context,
                agent_context=agent_context
            )

            # 2. Prepare Queries
            prepared_queries, model_details_prepare = await self.preparer.prepare_queries(
                original_query=query,
                techniques=chosen_techniques
            )

            # 3. Determine n_results per query
            is_sub_query_mode = "sub_query" in chosen_techniques and len(prepared_queries) > 1
            n_results_per_query = n_results if is_sub_query_mode else n_results
            # If not sub-query mode but multiple queries (e.g., step-back), maybe divide n_results?
            # For now, let's keep it simple: fetch n_results for each prepared query.
            # Consider adding a cap later if needed (e.g., max 3*n_results total initial fetch).
            logger.info(f"Retrieving up to {n_results_per_query} results per query for {len(prepared_queries)} prepared queries.")

            # 4. Concurrent Retrieval (without reranking at this stage)
            filter_metadata = {"doc_id": filter_doc_id} if filter_doc_id else None
            retrieval_tasks = [
                self.retriever.retrieve(
                    query_text=q,
                    n_results=n_results_per_query,
                    filter_metadata=filter_metadata,
                    use_reranker=use_reranker, # Pass the flag from execute args
                    dense_weight=dense_weight,
                    sparse_weight=sparse_weight
                ) for q in prepared_queries
            ]
            results_list = await asyncio.gather(*retrieval_tasks, return_exceptions=True)

            # 5. Aggregate & De-duplicate
            aggregated_results: Dict[str, Dict[str, Any]] = {} # Use dict for easy deduplication by chunk_id
            for i, result_item in enumerate(results_list):
                query_used = prepared_queries[i]
                if isinstance(result_item, Exception):
                    logger.error(f"Error retrieving results for query '{query_used}': {result_item}")
                    continue # Skip results from failed queries
                if isinstance(result_item, list):
                    for chunk in result_item:
                        chunk_id = chunk.get("metadata", {}).get("chunk_id")
                        if chunk_id and chunk_id not in aggregated_results:
                            aggregated_results[chunk_id] = chunk
                        elif not chunk_id:
                             logger.warning(f"Retrieved chunk missing chunk_id, cannot de-duplicate: {chunk.get('text', '')[:50]}...")
                             # Add anyway? Or discard? Let's add with a random key for now, might cause duplicates.
                             # Consider adding a hash of the text as a fallback key.
                             fallback_key = f"no_id_{hash(chunk.get('text', ''))}"
                             if fallback_key not in aggregated_results:
                                 aggregated_results[fallback_key] = chunk


            initial_aggregated_list = list(aggregated_results.values())
            logger.info(f"Aggregated {len(initial_aggregated_list)} unique chunks from {len(prepared_queries)} queries.")

            # 6. Final Reranking (Optional) - This logic remains for reranking *after* aggregation if needed by the caller.
            # The change above enables reranking *within* the initial retriever.retrieve call if requested.
            # We might want to disable this final reranking step if the initial retrieval already reranked?
            # For now, let's keep it, but be aware it might rerank already reranked results.
            # A better approach might be to only run this if the initial use_reranker was False.
            run_final_rerank = use_reranker # Use the original flag passed to the tool execute method
            if run_final_rerank and self.retriever.reranker and initial_aggregated_list:
                logger.info(f"Applying final reranking (if enabled) to {len(initial_aggregated_list)} aggregated chunks using original query: '{query}'")
                try:
                    # Rerank the aggregated list using the *original* query.
                    # Note: If initial retrieval was already reranked, this reranks again.
                    # The reranker now returns a list of tuples (score, item)
                    reranked_tuples = await asyncio.to_thread(
                        self.retriever.reranker.rerank, query, initial_aggregated_list, top_n=n_results
                    )
                    # Extract just the items from the tuples
                    final_results = [item for _, item in reranked_tuples]
                    logger.info(f"Returning {len(final_results)} final reranked results.")
                except Exception as rerank_e:
                    logger.error(f"Error during final reranking: {rerank_e}. Returning top N non-reranked results.")
                    # Fallback to top N non-reranked results
                    # Note: The initial list isn't sorted globally, so just taking [:n_results] isn't ideal.
                    # A better fallback might be to sort by the initial vector store scores if available,
                    # but those aren't consistently stored across chunks after aggregation.
                    # For simplicity, we'll just truncate for now.
                    final_results = initial_aggregated_list[:n_results]
            else:
                # If not reranking, just take the top N (or fewer) aggregated results
                final_results = initial_aggregated_list[:n_results]
                logger.info(f"Returning {len(final_results)} aggregated results (reranker disabled or skipped).")

            # 7. Return Results
            return final_results

        except Exception as e:
            logger.error(f"Error during enhanced document search execution: {e}", exc_info=True)
            # TODO: Log model details from strategy/prepare calls even on error?
            return [] # Return empty list on error

# Note: The ToolDefinition for this tool would be created externally
# when initializing the ToolRegistry, passing the 'execute' method

# Note: The ToolDefinition for this tool would be created externally
# when initializing the ToolRegistry, passing the 'execute' method
# as the implementation.
# Example (in registry setup):
# retriever_instance = Retriever(...)
# search_tool = DocumentSearchTool(retriever_instance)
# search_tool_def = ToolDefinition(
#     name=search_tool.name,
#     description=search_tool.description,
#     parameters_schema=search_tool.parameters_schema,
#     implementation=search_tool.execute
# )
# tool_registry.register_tool(search_tool_def)
