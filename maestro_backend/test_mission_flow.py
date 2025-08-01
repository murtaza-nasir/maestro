#!/usr/bin/env python3

import sys
import os
sys.path.append('/app')

def main():
    try:
        # Import database dependencies
        from database.database import get_db
        from database.models import Mission, DocumentGroup, document_group_association
        from sqlalchemy.orm import Session
        
        # Get database session
        db_gen = get_db()
        db: Session = next(db_gen)
        
        try:
            print("=== Checking Mission and Document Group Data ===")
            
            # Find the most recent mission
            latest_mission = db.query(Mission).order_by(Mission.created_at.desc()).first()
            
            if latest_mission:
                print(f"Latest Mission:")
                print(f"  ID: {latest_mission.id}")
                # Check what attributes the mission actually has
                print(f"  Available attributes: {[attr for attr in dir(latest_mission) if not attr.startswith('_')]}")
                if hasattr(latest_mission, 'status'):
                    print(f"  Status: {latest_mission.status}")
                if hasattr(latest_mission, 'created_at'):
                    print(f"  Created: {latest_mission.created_at}")
                if hasattr(latest_mission, 'metadata'):
                    print(f"  Metadata: {latest_mission.metadata}")
                print()
                
                # Check if metadata contains document_group_id
                metadata = latest_mission.metadata or {}
                document_group_id = metadata.get('document_group_id')
                print(f"Document Group ID from metadata: {document_group_id}")
                
                if document_group_id:
                    # Check if this document group exists
                    group = db.query(DocumentGroup).filter(DocumentGroup.id == document_group_id).first()
                    if group:
                        print(f"Document Group found:")
                        print(f"  ID: {group.id}")
                        print(f"  Name: {group.name}")
                        print(f"  User ID: {group.user_id}")
                        print(f"  Created: {group.created_at}")
                        print()
                        
                        # Check documents in this group
                        from database.models import Document
                        documents = db.query(Document).join(
                            document_group_association,
                            Document.id == document_group_association.c.document_id
                        ).filter(
                            document_group_association.c.document_group_id == document_group_id
                        ).all()
                        
                        print(f"Documents in group {document_group_id}:")
                        for doc in documents:
                            print(f"  - {doc.id}: {doc.original_filename}")
                        print()
                        
                    else:
                        print(f"ERROR: Document group {document_group_id} not found in database!")
                else:
                    print("ERROR: No document_group_id found in mission metadata!")
                    
            else:
                print("No missions found in database!")
                
            # Also check all document groups for reference
            print("=== All Document Groups ===")
            all_groups = db.query(DocumentGroup).all()
            for group in all_groups:
                print(f"Group {group.id}: {group.name} (user: {group.user_id})")
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
