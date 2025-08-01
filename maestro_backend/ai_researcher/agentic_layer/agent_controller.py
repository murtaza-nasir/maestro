"""
Agent Controller - Main orchestration module for the AI Researcher system.
This file has been refactored into a modular structure with components in the controller/ directory.
"""

import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
import queue

from ai_researcher.agentic_layer.context_manager import ContextManager
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.core_rag.retriever import Retriever
from ai_researcher.core_rag.reranker import TextReranker

# Import the refactored controller components
from ai_researcher.agentic_layer.controller.core_controller import AgentController as CoreAgentController

logger = logging.getLogger(__name__)

class AgentController(CoreAgentController):
    """
    Main controller class that orchestrates the research process.
    This class extends the CoreAgentController and serves as the main entry point
    for the AI Researcher system.
    
    The implementation has been refactored into modular components in the controller/ directory:
    - core_controller.py: Core initialization and orchestration
    - research_manager.py: Research phase management
    - reflection_manager.py: Reflection and planning
    - writing_manager.py: Writing phase management
    - user_interaction.py: User message handling and interaction
    - report_generator.py: Report generation and citation processing
    """
    
    def __init__(
        self,
        model_dispatcher: ModelDispatcher,
        context_manager: ContextManager,
        tool_registry: ToolRegistry,
        retriever: Optional[Retriever],
        reranker: Optional[TextReranker]
    ):
        """
        Initialize the AgentController with the necessary components.
        
        Args:
            model_dispatcher: The ModelDispatcher for LLM interactions
            context_manager: The ContextManager for mission state
            tool_registry: The ToolRegistry for available tools
            retriever: The Retriever for document search
            reranker: The TextReranker for result reranking
        """
        super().__init__(
            model_dispatcher=model_dispatcher,
            context_manager=context_manager,
            tool_registry=tool_registry,
            retriever=retriever,
            reranker=reranker
        )
        logger.info("AgentController initialized with modular architecture.")
