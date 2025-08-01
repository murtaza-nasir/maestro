#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import get_db
from database import crud
import json

def test_research_agent_controller():
    """Test if the research agent has access to the controller and can extract document_group_id."""
    
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
        
        # Check the mission_context field
        if mission.mission_context and isinstance(mission.mission_context, dict):
            metadata = mission.mission_context.get('metadata', {})
            document_group_id = metadata.get('document_group_id')
            
            print(f"✅ Mission metadata contains document_group_id: {document_group_id}")
            
            # Now let's check if we can simulate what the research agent should do
            print(f"\n--- Simulating Research Agent Logic ---")
            
            # This is what the research agent should be doing:
            # 1. Get mission context from controller
            # 2. Extract document_group_id from metadata
            # 3. Pass it to document search tool
            
            print(f"1. Mission context exists: ✅")
            print(f"2. Metadata exists: ✅")
            print(f"3. document_group_id exists: {'✅' if document_group_id else '❌'}")
            
            if document_group_id:
                print(f"4. document_group_id value: {document_group_id}")
                print(f"5. Would pass to document search: document_group_id='{document_group_id}'")
                
                # Test if this document group has documents
                from database.models import Document, DocumentGroup, document_group_association
                
                # Query documents in the group
                documents = db.query(Document).join(
                    document_group_association,
                    Document.id == document_group_association.c.document_id
                ).filter(
                    document_group_association.c.document_group_id == document_group_id
                ).all()
                
                doc_ids = [doc.id for doc in documents]
                print(f"6. Documents in group: {len(doc_ids)} documents")
                print(f"7. Document IDs: {doc_ids}")
                
                if doc_ids:
                    print(f"✅ Document search should work with filter: {{'doc_id': {{'$in': {doc_ids}}}}}")
                else:
                    print(f"❌ No documents found in group - this explains why search returns 0 results")
            else:
                print(f"❌ No document_group_id found - this is the problem!")
                
        else:
            print(f"❌ Mission context is not a dictionary or is None")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_research_agent_controller()
