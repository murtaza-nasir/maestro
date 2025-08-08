import logging
from typing import List, Dict, Any, Optional, Tuple

# Use absolute imports
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.core_rag.query_preparer import QueryRewritingTechnique # Import the type
from ai_researcher import config # To get model types
from ai_researcher.dynamic_config import get_model_name # To get actual model names

logger = logging.getLogger(__name__)

class QueryStrategist:
    """
    Determines the optimal query rewriting techniques based on the query and context.
    """
    def __init__(self, model_dispatcher: ModelDispatcher, mission_id: Optional[str] = None):
        self.model_dispatcher = model_dispatcher
        self.mission_id = mission_id
        # Determine the strategy model (prefer fast model for this task)
        self.strategy_model_type = config.AGENT_ROLE_MODEL_TYPE.get("query_strategy", "fast") # Default to fast
        
        # Get the model name dynamically using the new system
        self.strategy_model = get_model_name(self.strategy_model_type)
        
        logger.info(f"QueryStrategist initialized using strategy model: {self.strategy_model}")

    async def _call_strategy_llm(self, prompt: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Helper to call the LLM asynchronously for strategy determination."""
        messages = [{"role": "user", "content": prompt}]
        try:
            # Use a low temperature for consistent strategy selection
            response, model_call_details = await self.model_dispatcher.dispatch(
                messages=messages,
                model=self.strategy_model,
                # max_tokens=50, # Removed: dispatch doesn't accept this
                agent_mode="query_strategy" # Use specific agent mode settings
            )
            if response and response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip(), model_call_details
            else:
                logger.warning("LLM strategy call returned no content.")
                return None, model_call_details
        except Exception as e:
            logger.error(f"Error calling async LLM for query strategy: {e}", exc_info=True)
            return None, {"error": str(e)}

    def _parse_techniques(self, llm_output: str) -> List[QueryRewritingTechnique]:
        """Parses the LLM output string into a list of valid techniques."""
        if not llm_output:
            return []

        # Expected format: comma-separated list, potentially with brackets or quotes
        cleaned_output = llm_output.lower().strip('[]()"\' ')
        potential_techniques = [t.strip() for t in cleaned_output.split(',')]

        valid_techniques: List[QueryRewritingTechnique] = []
        allowed: List[QueryRewritingTechnique] = ["zero_shot_rewrite", "sub_query", "step_back"]

        for tech in potential_techniques:
            if tech in allowed:
                valid_techniques.append(tech)
            elif tech: # Log if it's non-empty but not recognized
                 logger.warning(f"LLM suggested unrecognized technique: '{tech}'")

        # Apply logic: If 'sub_query' is chosen, don't also use 'step_back' for now.
        if "sub_query" in valid_techniques and "step_back" in valid_techniques:
            logger.debug("Both sub_query and step_back suggested; preferring sub_query.")
            valid_techniques.remove("step_back")

        return valid_techniques

    async def determine_techniques(
        self,
        original_query: str,
        research_context: Optional[str] = None,
        agent_context: Optional[str] = None
    ) -> Tuple[List[QueryRewritingTechnique], Optional[Dict[str, Any]]]:
        """
        Analyzes the query and context to determine which rewriting techniques to apply.

        Args:
            original_query: The user's or agent's original query.
            research_context: The overall goal or topic of the research mission.
            agent_context: Specific context from the calling agent (e.g., section being researched).

        Returns:
            A tuple containing:
            - A list of recommended QueryRewritingTechnique strings.
            - A dictionary with model call details, or None on failure.
        """
        logger.debug(f"Determining strategy for query: '{original_query}'")

        prompt = f"""You are an expert RAG query strategist. Your task is to analyze the user's query and available context to decide which query enhancement techniques, if any, should be applied before searching a research document database.

Available techniques:
- `zero_shot_rewrite`: Rewrite the query for clarity and search effectiveness. Good for vague or poorly phrased queries.
- `sub_query`: Decompose a complex query with multiple distinct parts into simpler sub-queries. Good for multi-faceted questions.
- `step_back`: Generate a broader, higher-level question to retrieve foundational context. Good for specific queries needing background.

Context:
- User Query: "{original_query}"
- Overall Research Goal: {research_context or "Not provided"}
- Current Agent Task/Section: {agent_context or "Not provided"}

Analysis:
Based on the query's complexity, specificity, and the provided context, which techniques are most appropriate?
- If the query is complex and seems to ask multiple things, suggest `sub_query`.
- If the query is very specific but might lack context, suggest `step_back`.
- If the query is unclear or conversational, suggest `zero_shot_rewrite`.
- If the query is already clear and well-defined for search, suggest no techniques.
- You can suggest multiple techniques (e.g., `zero_shot_rewrite, step_back`), but if you suggest `sub_query`, do not also suggest `step_back`.

Decision:
Output *only* a comma-separated list of the chosen technique names (e.g., `sub_query` or `zero_shot_rewrite, step_back` or leave blank if none). Do not add any explanation.
"""

        llm_response, model_details = await self._call_strategy_llm(prompt)

        if llm_response is None:
            logger.warning("Query strategy LLM call failed. Applying no techniques.")
            return [], model_details # Return empty list on failure, but include details

        chosen_techniques = self._parse_techniques(llm_response)
        logger.info(f"Query strategy determined for '{original_query}': {chosen_techniques}")

        return chosen_techniques, model_details

# Example Usage (for testing)
async def main_test():
    # Requires setting up dispatcher and potentially env vars
    print("Testing QueryStrategist (requires external setup)...")
    # dispatcher = ModelDispatcher() # Needs proper initialization
    # strategist = QueryStrategist(dispatcher)
    # test_query = "Compare the effects of remote work policies on employee productivity and mental health in the tech vs finance sectors since 2020."
    # techniques, details = await strategist.determine_techniques(test_query, research_context="Impact of Remote Work", agent_context="Comparison Section")
    # print("Chosen Techniques:", techniques)
    # print("Model Details:", details)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # asyncio.run(main_test()) # Requires async setup
    print("QueryStrategist class defined. Run integration tests for actual usage.")
