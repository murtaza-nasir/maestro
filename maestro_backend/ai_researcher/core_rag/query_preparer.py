import asyncio # <-- Import asyncio
import logging
import re
import json
from typing import Any, List, Dict, Optional, Literal, Tuple, Union

# Use absolute imports
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher import config # To get model types
from ai_researcher.dynamic_config import get_model_name, get_max_query_length # To get actual model names and max query length

logger = logging.getLogger(__name__)

# Define supported techniques
QueryRewritingTechnique = Literal["zero_shot_rewrite", "sub_query", "step_back"]

class QueryPreparer:
    """
    Prepares and rewrites user queries for improved RAG retrieval using various techniques.
    Includes domain context and few-shot examples for better query generation.
    """
    def __init__(self, model_dispatcher: ModelDispatcher, mission_id: Optional[str] = None):
        self.model_dispatcher = model_dispatcher
        self.mission_id = mission_id
        # Use the correct config key "query_preparation" instead of "query_rewriting"
        self.rewriting_model_type = config.AGENT_ROLE_MODEL_TYPE.get("query_preparation", "intelligent") # Default to intelligent for query preparation
        
        # Get the model name dynamically using the new system
        self.rewriting_model = get_model_name(self.rewriting_model_type)
            
        logger.info(f"QueryPreparer initialized using rewriting model: {self.rewriting_model} (model_type: {self.rewriting_model_type})")

    async def _call_rewriter_llm(
        self, 
        prompt: str, 
        max_tokens: int = 200, 
        temperature: float = 0.1,
        mission_id: Optional[str] = None,  # Add cost tracking parameters
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]: # <-- Make async
        """Helper to call the LLM asynchronously for rewriting tasks."""
        messages = [{"role": "user", "content": prompt}]
        try:
            # Await the dispatcher's async method with cost tracking
            response, model_call_details = await self.model_dispatcher.dispatch( # <-- Use await
                messages=messages,
                model=self.rewriting_model,
                # max_tokens is handled by dispatcher based on agent_mode/config now
                # max_tokens=max_tokens, # Remove this line
                # temperature=temperature, # Removed as it's likely handled by dispatcher/config now
                agent_mode="query_preparation", # <-- Use specific agent mode
                mission_id=mission_id,  # Pass cost tracking parameters
                log_queue=log_queue,
                update_callback=update_callback
            )
            if response and response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip(), model_call_details
            else:
                logger.warning("LLM rewriting call returned no content.")
            return None, model_call_details
        except Exception as e:
            logger.error(f"Error calling async LLM for query rewriting: {e}", exc_info=True)
            return None, {"error": str(e)} # Return error details

    async def rewrite_query_zero_shot(
        self, 
        user_query: str, 
        domain_context: Optional[str] = None,
        mission_id: Optional[str] = None,  # Add cost tracking
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]: # <-- Make async, add context
        """Rewrites the user query asynchronously using a zero-shot prompt with context and examples."""
        logger.debug(f"Rewriting query (Zero-shot) for: '{user_query}'")

        context_block = f"\nDomain Context:\n{domain_context}\n" if domain_context else ""

        # Check if preferred source types are mentioned in the domain context
        preferred_source_types = None
        if domain_context:
            # Look for preferred source types in the domain context
            source_types_match = re.search(r"Preferred Source Types:?\s*([^\n]+)", domain_context, re.IGNORECASE)
            if source_types_match:
                preferred_source_types = source_types_match.group(1).strip()
        
        source_types_instruction = ""
        if preferred_source_types:
            source_types_instruction = f"""
IMPORTANT: The user has specified preferred source types: "{preferred_source_types}"
Your rewritten query should specifically target these types of sources by including relevant terminology, 
qualifiers, or phrases that would help retrieve information from these specific source types.
"""

        prompt = f"""Given the user query below, rewrite it to be clearer and more effective for searching a database of research documents, considering the domain context if provided. Focus on the core information need, using specific terminology. 

CRITICAL: If the query contains vague references like "these", "those", "the mentioned", "the above", etc., you MUST expand them with the actual specific names/terms from the context. Never use vague references in search queries.

{context_block}
{source_types_instruction}
**Examples:**
Bad Query: Tell me about mobile health apps.
Good Query: What are the key factors influencing user adoption and trust in mobile health applications for chronic disease management?

Bad Query: Risks and benefits?
Good Query: Analyze the perceived risks and benefits affecting user intentions to adopt mobile health applications, comparing public versus private providers.

Bad Query: What did these researchers discover?
Good Query: What did Dr. Smith, Prof. Johnson, and the MIT research team discover?

Bad Query: How do those technologies compare?
Good Query: How do CRISPR gene editing, zinc finger nucleases, and TALENs compare?

Bad Query: What restaurants are in these towns?
Good Query: What restaurants are in Stowe Vermont, Manchester Vermont, and Brattleboro Vermont?

Bad Query: Applications in the mentioned fields
Good Query: Applications in quantum computing, artificial intelligence, and biotechnology

**User Query:**
Original Query: {user_query}

Rewritten Query (with all vague references expanded):"""
        rewritten_query, model_details = await self._call_rewriter_llm(
            prompt, max_tokens=150, temperature=0.2,
            mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
        ) # <-- Use await

        if not rewritten_query or rewritten_query.strip() == "":
            logger.warning("LLM failed to generate zero-shot rewrite. Using original query.")
            return user_query, model_details # Return original query but include model details if call was made

        # Basic cleaning
        rewritten_query = rewritten_query.strip().strip('"')
        logger.debug(f"Zero-shot rewritten query: '{rewritten_query}'")
        return rewritten_query, model_details

    async def decompose_into_subqueries(
        self, 
        user_query: str, 
        max_subqueries: int = 3, 
        domain_context: Optional[str] = None,
        mission_id: Optional[str] = None,  # Add cost tracking
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> Tuple[List[str], Optional[Dict[str, Any]]]: # <-- Make async, add context
        """Decomposes a complex query into sub-queries asynchronously using an LLM with context and examples."""
        logger.debug(f"Decomposing query into sub-queries for: '{user_query}'")

        context_block = f"\nDomain Context:\n{domain_context}\n" if domain_context else ""

        # Check if preferred source types are mentioned in the domain context
        preferred_source_types = None
        if domain_context:
            # Look for preferred source types in the domain context
            source_types_match = re.search(r"Preferred Source Types:?\s*([^\n]+)", domain_context, re.IGNORECASE)
            if source_types_match:
                preferred_source_types = source_types_match.group(1).strip()
        
        source_types_instruction = ""
        if preferred_source_types:
            source_types_instruction = f"""
IMPORTANT: The user has specified preferred source types: "{preferred_source_types}"
Your sub-queries should specifically target these types of sources by including relevant terminology, 
qualifiers, or phrases that would help retrieve information from these specific source types.
"""

        prompt = f"""You are an expert query analyzer. Given the user query below and optional domain context, decompose it into {max_subqueries} or fewer distinct sub-queries that cover the main aspects of the original question. Each sub-query should be specific, answerable independently based on research documents, and use relevant terminology. 

CRITICAL: If the original query or context contains vague references like "these", "those", "the mentioned", "the above", "such", etc., you MUST expand them with the actual specific names/terms in your sub-queries. Never use vague references - always be explicit and specific with names, locations, technologies, concepts, etc.

Output *only* the sub-queries, each on a new line. Do not number them or add any other text.

{context_block}
{source_types_instruction}
**Example:**
Original Query: Discuss the impact of user trust and provider governance on mobile health app adoption for chronic diseases.
Sub-queries:
How does user trust in public vs. private mobile health providers influence adoption intentions?
What role does perceived provider governance play in user trust formation for health apps?
Analyze the relationship between trust dynamics and adoption rates of mobile health apps in chronic disease management.

**Example with researcher references:**
Original Query: Compare the findings of these researchers on climate change
Context: Discussing work by Dr. Hansen, Prof. Mann, and Dr. Trenberth
Sub-queries:
Dr. James Hansen's findings on global temperature trends and climate sensitivity
Prof. Michael Mann's hockey stick graph and paleoclimate reconstructions
Dr. Kevin Trenberth's research on extreme weather events and climate change

**Example with technology references:**
Original Query: What are the advantages and limitations of those methods?
Context: Discussing machine learning methods: neural networks, SVM, random forests
Sub-queries:
Advantages and limitations of neural networks in pattern recognition
Support vector machines (SVM) performance and computational requirements
Random forest algorithms strengths and weaknesses compared to other ensemble methods

**User Query:**
Original Query: {user_query}

Sub-queries (with all vague references expanded to specific names/terms):"""
        response, model_details = await self._call_rewriter_llm(
            prompt, max_tokens=200 + (max_subqueries * 50), temperature=0.1,
            mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
        ) # <-- Use await

        if not response:
            logger.warning("LLM failed to generate sub-queries. Using original query only.")
            return [user_query], model_details

        # Parse the response
        sub_queries = [q.strip() for q in response.strip().split('\n') if len(q.strip()) > 10]
        cleaned_queries = []
        for q in sub_queries:
            q_cleaned = re.sub(r'^\s*[\d\.\-\*]+\s*', '', q).strip() # Remove numbering/bullets
            if q_cleaned:
                cleaned_queries.append(q_cleaned)

        final_subqueries = cleaned_queries[:max_subqueries]

        if not final_subqueries:
             logger.warning("LLM output parsing failed for sub-queries. Using original query only.")
             return [user_query], model_details

        logger.debug(f"Generated sub-queries: {final_subqueries}")
        return final_subqueries, model_details

    async def generate_step_back_query(
        self, 
        user_query: str, 
        domain_context: Optional[str] = None,
        mission_id: Optional[str] = None,  # Add cost tracking
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> Tuple[List[str], Optional[Dict[str, Any]]]: # <-- Make async, add context
        """Generates a step-back query asynchronously using context and examples, returns it with the original query."""
        logger.debug(f"Generating step-back query for: '{user_query}'")

        context_block = f"\nDomain Context:\n{domain_context}\n" if domain_context else ""

        # Check if preferred source types are mentioned in the domain context
        preferred_source_types = None
        if domain_context:
            # Look for preferred source types in the domain context
            source_types_match = re.search(r"Preferred Source Types:?\s*([^\n]+)", domain_context, re.IGNORECASE)
            if source_types_match:
                preferred_source_types = source_types_match.group(1).strip()
        
        source_types_instruction = ""
        if preferred_source_types:
            source_types_instruction = f"""
IMPORTANT: The user has specified preferred source types: "{preferred_source_types}"
Your step-back question should specifically target these types of sources by including relevant terminology, 
qualifiers, or phrases that would help retrieve information from these specific source types.
"""

        prompt = f"""You are an expert in generating broader context questions. Given the specific user query below and optional domain context, generate a single, more general "step-back" question that explores the higher-level concepts or underlying principles relevant for finding context in research documents. 

CRITICAL: Even in step-back questions, if there are specific names, entities, technologies, or concepts mentioned, keep them specific. Don't use vague references like "these", "those", "the mentioned", etc. Use the actual names/terms.

Output *only* the step-back question.

{context_block}
{source_types_instruction}
**Example:**
Specific User Query: What specific feedback messages improve engagement in the 'HeartHelper' mobile health app?
Step-back Question: What are general principles and theories regarding user engagement and feedback mechanisms in mobile health applications?

**Example with researcher names:**
Specific User Query: How did these scientists contribute to quantum mechanics?
Context: Discussing Heisenberg, Schrödinger, and Dirac
Step-back Question: What were the foundational contributions of Heisenberg, Schrödinger, and Dirac to the development of quantum mechanics?

**Example with technology terms:**
Specific User Query: What are the best use cases for those frameworks?
Context: Discussing React, Angular, and Vue.js
Step-back Question: What are the architectural principles and design philosophies of React, Angular, and Vue.js that determine their optimal use cases?

**User Query:**
Specific User Query: {user_query}

Step-back Question (with specific names/terms preserved):"""
        step_back_q, model_details = await self._call_rewriter_llm(
            prompt, max_tokens=150, temperature=0.2,
            mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
        ) # <-- Use await

        if not step_back_q or len(step_back_q.strip()) < 10 :
            logger.warning("LLM failed to generate a step-back query. Using original query only.")
            return [user_query], model_details # Return only original

        # Basic cleaning
        step_back_q = step_back_q.strip().strip('"')
        logger.debug(f"Generated step-back query: '{step_back_q}'")

        # Return a list containing both original and step-back
        return [user_query, step_back_q], model_details

    async def refine_long_query(
        self, 
        query: str, 
        max_length: Optional[int] = None, 
        max_retries: int = 3,
        mission_id: Optional[str] = None,  # Add cost tracking
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Refines a query if it's too long for web search APIs with retry mechanism.
        
        Args:
            query: The query that needs refinement
            max_length: Maximum desired length (if None, uses user-configured value)
            max_retries: Maximum number of refinement attempts (default 3)
            
        Returns:
            A tuple of (refined_query, model_details)
        """
        # Use user-configured max length if not specified
        if max_length is None:
            max_length = get_max_query_length(self.mission_id)
            
        # Only refine if query exceeds the limit
        if len(query) <= max_length:
            return query, None
            
        logger.info(f"Query too long ({len(query)} chars), refining to be under {max_length} chars")
        
        all_model_details = []
        attempt = 0
        current_query = query
        
        while attempt < max_retries:
            attempt += 1
            logger.info(f"Query refinement attempt {attempt}/{max_retries}")
            
            # Adjust prompt based on attempt number to be more aggressive
            urgency = ""
            if attempt > 1:
                urgency = f"\nIMPORTANT: This is attempt {attempt}. The previous refinement was still too long. Be MORE aggressive in shortening.\n"
            
            prompt = f"""The following search query is too long for the web search API (max {max_length} characters).
Please rewrite it to be more concise while preserving the essential search intent and key terms.
{urgency}
Rules:
1. Keep the most important keywords and concepts
2. Remove redundant phrases and verbose descriptions
3. Use abbreviations where appropriate
4. Focus on the core question
5. The refined query MUST be under {max_length} characters
6. Target {max_length - 20} characters to ensure you stay under the limit

Original query ({len(current_query)} chars):
{current_query}

Concise query (under {max_length} chars):"""
            
            refined_query, model_details = await self._call_rewriter_llm(
                prompt, max_tokens=200, temperature=0.1,
                mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
            )
            if model_details:
                all_model_details.append({"attempt": attempt, **model_details})
            
            if not refined_query:
                logger.warning(f"Attempt {attempt}: Failed to get refined query from LLM")
                continue
                
            # Clean and validate the refined query
            refined_query = refined_query.strip().strip('"')
            
            # Check if refinement succeeded
            if len(refined_query) <= max_length:
                logger.info(f"Successfully refined query from {len(query)} to {len(refined_query)} chars in {attempt} attempt(s)")
                return refined_query, {"attempts": attempt, "model_calls": all_model_details}
            
            logger.warning(f"Attempt {attempt}: Refined query still too long ({len(refined_query)} chars)")
            current_query = refined_query  # Use the partially refined query for next attempt
        
        # All retries failed, use fallback truncation with ellipsis
        logger.warning(f"All {max_retries} refinement attempts failed, using truncation fallback")
        truncated = query[:max_length - 3] + "..."
        last_space = query[:max_length - 3].rfind(' ')
        if last_space > max_length * 0.7:  # Keep at least 70% when truncating at word boundary
            truncated = query[:last_space] + "..."
        
        return truncated, {"attempts": max_retries, "fallback": "truncation", "model_calls": all_model_details}

    async def prepare_queries( # <-- Make async
        self,
        original_query: str,
        techniques: List[QueryRewritingTechnique],
        domain_context: Optional[str] = None, # <-- Add domain_context parameter
        mission_id: Optional[str] = None,  # Add cost tracking
        log_queue: Optional[Any] = None,
        update_callback: Optional[Any] = None
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Applies specified query rewriting techniques asynchronously to the original query,
        incorporating domain context.

        Args:
            original_query: The initial query string.
            techniques: A list of techniques to apply (e.g., ["sub_query", "step_back"]).
            domain_context: Optional string providing context about the research domain or specific section.

        Returns:
            A tuple containing:
            - A list of queries to be executed (original + rewritten/sub-queries).
            - A list of model call details from the rewriting process.
        """
        prepared_queries = [original_query] # Start with the original
        all_model_details = []
        processed_query = original_query # Keep track of the query being processed

        # Apply techniques sequentially (order might matter)
        if "zero_shot_rewrite" in techniques:
            rewritten_q, details = await self.rewrite_query_zero_shot(
                processed_query, domain_context,
                mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
            ) # <-- Pass context and cost tracking
            if details: all_model_details.append(details)
            processed_query = rewritten_q
            prepared_queries = [processed_query] # Replace original

        if "sub_query" in techniques:
            sub_queries, details = await self.decompose_into_subqueries(
                processed_query, domain_context=domain_context,
                mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
            ) # <-- Pass context and cost tracking
            if details: all_model_details.append(details)
            if len(sub_queries) > 1 or (len(sub_queries) == 1 and sub_queries[0] != processed_query):
                prepared_queries = sub_queries
                if "step_back" in techniques:
                    logger.info("Sub-query decomposition applied; skipping step-back generation.")
                    techniques = [t for t in techniques if t != "step_back"] # Filter out step_back

        if "step_back" in techniques:
            step_back_list, details = await self.generate_step_back_query(
                processed_query, domain_context,
                mission_id=mission_id, log_queue=log_queue, update_callback=update_callback
            ) # <-- Pass context and cost tracking
            if details: all_model_details.append(details)
            if len(step_back_list) > 1:
                 # Add step-back query, keeping original/rewritten first
                 prepared_queries = [processed_query] + [q for q in step_back_list if q != processed_query]

        # Deduplicate final list, preserving order as much as possible
        final_queries = []
        seen = set()
        for q in prepared_queries:
            if q not in seen:
                final_queries.append(q)
                seen.add(q)
        
        # Check and refine any queries that are too long for web search APIs
        # This ensures compatibility with Tavily and other search providers
        # Get the user-configured max query length (defaults to 350)
        max_query_length = get_max_query_length(self.mission_id)
        
        refined_queries = []
        for query in final_queries:
            if len(query) > max_query_length:
                refined_query, refine_details = await self.refine_long_query(query, max_length=max_query_length)
                if refine_details:
                    all_model_details.append({
                        "action": "query_refinement",
                        "original_length": len(query),
                        "refined_length": len(refined_query),
                        "max_length_setting": max_query_length,
                        **refine_details
                    })
                refined_queries.append(refined_query)
            else:
                refined_queries.append(query)
        
        # Use refined queries as final output
        final_queries = refined_queries

        logger.info(f"Prepared queries for '{original_query}': {final_queries}")
        return final_queries, all_model_details

# Example Usage (for testing purposes, would be called by ResearchAgent)
def main_test(): # Removed async
    # This requires setting up dispatcher and potentially env vars outside this script
    # For simplicity, this is just a placeholder structure
    print("Testing QueryPreparer (requires external setup)...")
    # dispatcher = ModelDispatcher() # Needs proper initialization
    # preparer = QueryPreparer(dispatcher)
    # test_query = "How did Park Hotels & Resorts' strategy for addressing underperforming assets in 2023, particularly the San Francisco properties, impact their financial metrics, capital allocation decisions, and future investment plans through 2024?"
    # queries, details = preparer.prepare_queries(test_query, ["sub_query", "step_back"]) # Removed await
    # print("Final Queries:", queries)
    # print("Model Details:", details)

if __name__ == "__main__":
    # Basic logging setup for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # main_test() # Removed asyncio.run
    print("QueryPreparer class defined. Run integration tests for actual usage.")
