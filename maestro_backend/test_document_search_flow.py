#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from database.database import get_db
from ai_researcher.agentic_layer.context_manager import ContextManager
from ai_researcher.agentic_layer.model_dispatcher import ModelDispatcher
from ai_researcher.agentic_layer.tool_registry import ToolRegistry
from ai_researcher.agentic_layer.agents.research_agent import ResearchAgent
from ai_researcher.core_rag.query_preparer import QueryPreparer

async def test_document_search_flow():
    """Test the complete flow from research agent to document search tool."""
    
    # Test mission ID from the context
    mission_id = "5728d8b7-fe7d-48c5-b1c8-51eacf2a6078"
    
    print(f"Testing document search flow for mission: {mission_id}")
    
    # Create context manager with a lambda that returns the db session
    db = next(get_db())
    try:
        context_mgr = ContextManager(lambda: db)
        
        # Get mission context
        mission_context = context_mgr.get_mission_context(mission_id)
        if not mission_context:
            print(f"❌ Could not get mission context for {mission_id}")
            return
            
        print(f"✅ Got mission context")
        print(f"Mission metadata: {mission_context.metadata}")
        
        document_group_id = mission_context.metadata.get('document_group_id')
        if not document_group_id:
            print(f"❌ No document_group_id in mission metadata")
            return
            
        print(f"✅ Found document_group_id: {document_group_id}")
        
        # Create a minimal controller-like object that the research agent can use
        class MockController:
            def __init__(self, context_manager):
                self.context_manager = context_manager
        
        # Create model dispatcher and tool registry
        model_dispatcher = ModelDispatcher(context_manager=context_mgr)
        tool_registry = ToolRegistry()
        query_preparer = QueryPreparer(model_dispatcher)
        
        # Create mock controller
        mock_controller = MockController(context_mgr)
        
        # Create research agent with controller
        research_agent = ResearchAgent(
            model_dispatcher=model_dispatcher,
            tool_registry=tool_registry,
            query_preparer=query_preparer,
            controller=mock_controller
        )
        
        print(f"✅ Created research agent with controller")
        print(f"Research agent has controller: {hasattr(research_agent, 'controller')}")
        print(f"Controller has context_manager: {hasattr(research_agent.controller, 'context_manager')}")
        
        # Set mission_id on the research agent (this is what happens during execution)
        research_agent.mission_id = mission_id
        print(f"✅ Set mission_id on research agent: {research_agent.mission_id}")
        
        # Now test the document search logic that should happen in _execute_single_search
        print(f"\n--- Testing Document Search Logic ---")
        
        # Simulate what happens in _execute_single_search for document_search
        tool_name = "document_search"
        query = "test query about weather risk"
        args = {
            "query": query,
            "n_results": 5,
            "use_reranker": True
        }
        
        print(f"Initial args: {args}")
        
        # This is the logic from _execute_single_search
        if tool_name == "document_search":
            print(f"DEBUG: Processing document_search tool for mission {research_agent.mission_id}")
            print(f"DEBUG: research_agent.controller exists: {hasattr(research_agent, 'controller')}")
            print(f"DEBUG: research_agent.controller value: {getattr(research_agent, 'controller', 'NOT_SET')}")
            
            current_mission_id = research_agent.mission_id
            
            if hasattr(research_agent, 'controller') and research_agent.controller and current_mission_id:
                try:
                    # Get mission context to extract document_group_id
                    print(f"DEBUG: Attempting to get mission context for mission {current_mission_id}")
                    mission_context = research_agent.controller.context_manager.get_mission_context(current_mission_id)
                    if mission_context and mission_context.metadata:
                        print(f"DEBUG: Mission context found. Metadata keys: {list(mission_context.metadata.keys())}")
                        print(f"DEBUG: Full mission metadata: {mission_context.metadata}")
                        document_group_id = mission_context.metadata.get("document_group_id")
                        if document_group_id:
                            args['document_group_id'] = str(document_group_id)  # Ensure it's a string
                            print(f"DEBUG: Added document_group_id={document_group_id} to document search for mission {current_mission_id}")
                            print(f"✅ Final args with document_group_id: {args}")
                        else:
                            print(f"DEBUG: No document_group_id found in mission {current_mission_id} metadata. Available keys: {list(mission_context.metadata.keys())}")
                    else:
                        print(f"DEBUG: Could not get mission context for mission {current_mission_id} - context: {mission_context}")
                except Exception as e:
                    print(f"DEBUG: Error extracting document_group_id for mission {current_mission_id}: {e}")
            else:
                print(f"DEBUG: Controller not available or no mission_id for document search. Controller: {hasattr(research_agent, 'controller')}, Mission ID: {current_mission_id}")
        
        print(f"\n--- Summary ---")
        if 'document_group_id' in args:
            print(f"✅ SUCCESS: document_group_id would be passed to document search tool")
            print(f"Final args: {args}")
        else:
            print(f"❌ FAILURE: document_group_id was NOT added to args")
            print(f"Final args: {args}")
            
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_document_search_flow())
