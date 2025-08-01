"""
Migration script to add the mission_execution_logs table for persistent activity logging.
This addresses the issue where users lose agent activity logs when switching tabs.
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database.database import SQLALCHEMY_DATABASE_URL, Base
from database.models import MissionExecutionLog
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Run the migration to add the mission_execution_logs table."""
    try:
        # Create engine and session
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        with engine.begin() as connection:
            # Check if the table already exists
            result = connection.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='mission_execution_logs';
            """))
            
            if result.fetchone():
                logger.info("mission_execution_logs table already exists. Skipping migration.")
                return True
            
            logger.info("Creating mission_execution_logs table...")
            
            # Create the new table
            connection.execute(text("""
                CREATE TABLE mission_execution_logs (
                    id VARCHAR PRIMARY KEY,
                    mission_id VARCHAR NOT NULL,
                    timestamp DATETIME NOT NULL,
                    agent_name VARCHAR NOT NULL,
                    action TEXT NOT NULL,
                    input_summary TEXT,
                    output_summary TEXT,
                    status VARCHAR NOT NULL DEFAULT 'success',
                    error_message TEXT,
                    full_input JSON,
                    full_output JSON,
                    model_details JSON,
                    tool_calls JSON,
                    file_interactions JSON,
                    cost DECIMAL(10, 6),
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    native_tokens INTEGER,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(mission_id) REFERENCES missions (id)
                );
            """))
            
            # Create indexes for better performance
            connection.execute(text("""
                CREATE INDEX ix_mission_execution_logs_mission_id 
                ON mission_execution_logs (mission_id);
            """))
            
            connection.execute(text("""
                CREATE INDEX ix_mission_execution_logs_agent_name 
                ON mission_execution_logs (agent_name);
            """))
            
            connection.execute(text("""
                CREATE INDEX ix_mission_execution_logs_status 
                ON mission_execution_logs (status);
            """))
            
            connection.execute(text("""
                CREATE INDEX ix_mission_execution_logs_timestamp 
                ON mission_execution_logs (timestamp);
            """))
            
            logger.info("Successfully created mission_execution_logs table with indexes.")
            
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = run_migration()
    if success:
        logger.info("Migration completed successfully!")
    else:
        logger.error("Migration failed!")
        exit(1)
