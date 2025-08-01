#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import get_db
from database import crud
import json

def test_mission_metadata_serialization():
    """Test how mission metadata is stored and retrieved from the database."""
    
    # Test mission ID from the context
    mission_id = "5728d8b7-fe7d-48c5-b1c8-51eacf2a6078"
    
    db = next(get_db())
    try:
        # Get the mission directly from the database
        mission = db.query(crud.Mission).filter(crud.Mission.id == mission_id).first()
        
        if not mission:
            print(f"❌ Mission {mission_id} not found in database")
            return
            
        print(f"✅ Found mission: {mission_id}")
        print(f"Mission status: {mission.status}")
        
        # Check the raw database fields
        print(f"\n--- Raw Database Fields ---")
        print(f"mission_context type: {type(mission.mission_context)}")
        print(f"mission_context value: {mission.mission_context}")
        
        # Check if mission_context is a dictionary
        if isinstance(mission.mission_context, dict):
            print(f"✅ mission_context is a dictionary")
            
            # Check metadata field
            metadata = mission.mission_context.get('metadata')
            print(f"metadata type: {type(metadata)}")
            print(f"metadata value: {metadata}")
            
            if isinstance(metadata, dict):
                print(f"✅ metadata is a dictionary")
                document_group_id = metadata.get('document_group_id')
                print(f"document_group_id: {document_group_id}")
                
                if document_group_id:
                    print(f"✅ document_group_id found: {document_group_id}")
                else:
                    print(f"❌ document_group_id not found in metadata")
                    print(f"Available metadata keys: {list(metadata.keys())}")
            else:
                print(f"❌ metadata is not a dictionary: {metadata}")
        else:
            print(f"❌ mission_context is not a dictionary")
            
        # Test the context manager's get_mission_context method
        print(f"\n--- Testing ContextManager.get_mission_context ---")
        from ai_researcher.agentic_layer.context_manager import ContextManager
        
        # Create a context manager instance with a lambda that returns the db session
        context_mgr = ContextManager(lambda: db)
        
        # Get mission context using the context manager
        mission_context = context_mgr.get_mission_context(mission_id)
        
        if mission_context:
            print(f"✅ ContextManager returned mission context")
            print(f"Mission context type: {type(mission_context)}")
            print(f"Mission context metadata type: {type(mission_context.metadata)}")
            print(f"Mission context metadata: {mission_context.metadata}")
            
            if hasattr(mission_context, 'metadata') and mission_context.metadata:
                document_group_id = mission_context.metadata.get('document_group_id')
                print(f"document_group_id from context manager: {document_group_id}")
                
                if document_group_id:
                    print(f"✅ ContextManager correctly returns document_group_id: {document_group_id}")
                else:
                    print(f"❌ ContextManager does not return document_group_id")
                    print(f"Available keys: {list(mission_context.metadata.keys()) if mission_context.metadata else 'None'}")
            else:
                print(f"❌ ContextManager mission context has no metadata")
        else:
            print(f"❌ ContextManager returned None for mission context")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_mission_metadata_serialization()
