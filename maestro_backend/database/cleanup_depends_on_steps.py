#!/usr/bin/env python3
"""
Script to remove the deprecated 'depends_on_steps' field from existing missions in the database.
This field was removed from the ReportSection schema but may still exist in old mission data.
"""

import json
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Mission
from database.database import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def remove_depends_on_steps(obj):
    """Recursively remove 'depends_on_steps' field from nested structures."""
    if isinstance(obj, dict):
        # Remove depends_on_steps if it exists
        if 'depends_on_steps' in obj:
            del obj['depends_on_steps']
            
        # Process subsections recursively
        if 'subsections' in obj and isinstance(obj['subsections'], list):
            for subsection in obj['subsections']:
                remove_depends_on_steps(subsection)
                
        # Process report_outline if it exists
        if 'report_outline' in obj and isinstance(obj['report_outline'], list):
            for section in obj['report_outline']:
                remove_depends_on_steps(section)
                
        # Process all other dict values recursively
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                remove_depends_on_steps(value)
                
    elif isinstance(obj, list):
        for item in obj:
            remove_depends_on_steps(item)
    
    return obj

def cleanup_missions():
    """Clean up all missions in the database to remove depends_on_steps."""
    # Create database connection
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    with SessionLocal() as session:
        try:
            # Get all missions
            missions = session.query(Mission).all()
            logger.info(f"Found {len(missions)} missions to check")
            
            updated_count = 0
            for mission in missions:
                if mission.context_data:
                    original_data = json.dumps(mission.context_data, sort_keys=True)
                    
                    # Clean the context_data
                    cleaned_data = remove_depends_on_steps(mission.context_data.copy())
                    
                    # Check if anything changed
                    cleaned_data_str = json.dumps(cleaned_data, sort_keys=True)
                    if original_data != cleaned_data_str:
                        mission.context_data = cleaned_data
                        updated_count += 1
                        logger.info(f"Updated mission {mission.mission_id}: removed depends_on_steps")
            
            if updated_count > 0:
                session.commit()
                logger.info(f"Successfully updated {updated_count} missions")
            else:
                logger.info("No missions needed updating")
                
        except Exception as e:
            logger.error(f"Error cleaning up missions: {e}")
            session.rollback()
            raise

if __name__ == "__main__":
    cleanup_missions()
    logger.info("Cleanup complete!")