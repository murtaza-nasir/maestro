#!/usr/bin/env python3
"""
Test script to verify auto-optimization functionality is working correctly.
"""
import asyncio
import logging
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal
from database import crud
from database.models import User
from ai_researcher.settings_optimizer import apply_auto_optimization, determine_research_parameters
from ai_researcher.agentic_layer.context_manager import ContextManager
from ai_researcher.agentic_layer.agent_controller import AgentController
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockMessage:
    """Mock message object for testing."""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

async def test_auto_optimization():
    """Test the auto-optimization functionality."""
    try:
        logger.info("Starting auto-optimization test...")
        
        # Initialize components
        context_manager = ContextManager(db_session_factory=SessionLocal)
        model_dispatcher = ModelDispatcher()
        tool_registry = ToolRegistry()
        
        # Initialize agent controller (minimal setup for testing)
        controller = AgentController(
            model_dispatcher=model_dispatcher,
            context_manager=context_manager,
            tool_registry=tool_registry,
            retriever=None,  # Not needed for this test
            reranker=None    # Not needed for this test
        )
        
        # Create mock chat history
        chat_history = [
            MockMessage("user", "What governance mechanisms can address the tension between algorithmic efficiency and procedural justice in automated decision systems within public sector contexts, while maintaining democratic accountability and citizen trust? Keep it super short, just 3 sections, without any subsections. Write in a Greek parable style."),
            MockMessage("assistant", "I'll help you research governance mechanisms for algorithmic decision systems in public sector contexts. Let me generate some initial research questions to guide our investigation."),
            MockMessage("user", "Ok go.")
        ]
        
        logger.info("Testing determine_research_parameters function...")
        
        # Test the determine_research_parameters function
        params = await determine_research_parameters(chat_history, controller)
        
        if params:
            logger.info("✅ Auto-optimization successful!")
            logger.info(f"Generated parameters: {params}")
            
            # Verify required fields are present
            required_fields = [
                'initial_research_max_depth', 'initial_research_max_questions',
                'structured_research_rounds', 'writing_passes',
                'initial_exploration_doc_results', 'initial_exploration_web_results',
                'main_research_doc_results', 'main_research_web_results',
                'thought_pad_context_limit', 'max_notes_for_assignment_reranking',
                'max_concurrent_requests', 'skip_final_replanning', 'auto_optimize_params'
            ]
            
            missing_fields = [field for field in required_fields if field not in params]
            if missing_fields:
                logger.error(f"❌ Missing required fields: {missing_fields}")
                return False
            
            # Verify auto_optimize_params is True
            if not params.get('auto_optimize_params'):
                logger.error("❌ auto_optimize_params should be True")
                return False
            
            logger.info("✅ All required fields present and valid!")
            return True
        else:
            logger.error("❌ Auto-optimization failed - no parameters returned")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}", exc_info=True)
        return False

async def main():
    """Main test function."""
    logger.info("🧪 Testing Auto-Optimization Functionality")
    logger.info("=" * 50)
    
    success = await test_auto_optimization()
    
    if success:
        logger.info("🎉 All tests passed! Auto-optimization is working correctly.")
        sys.exit(0)
    else:
        logger.error("💥 Tests failed! Check the logs above for details.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
