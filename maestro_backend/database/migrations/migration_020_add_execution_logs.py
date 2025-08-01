from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
import logging
from .base_migration import BaseMigration

logger = logging.getLogger(__name__)

class Migration(BaseMigration):
    """
    Migration to create the mission_execution_logs table for persistent activity logging.
    This addresses the issue where users lose agent activity logs when switching tabs.
    """
    
    version = "020"
    description = "Add mission_execution_logs table for persistent activity logging"

    def up(self, session):
        """
        Create the mission_execution_logs table.
        """
        logger.info(f"Applying migration {self.version}: {self.description}")
        
        inspector = inspect(session)
        if "mission_execution_logs" in inspector.get_table_names():
            logger.info("Table 'mission_execution_logs' already exists, skipping creation.")
            return

        try:
            # Create the mission_execution_logs table
            session.execute(text("""
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
                )
            """))
            logger.info("Table 'mission_execution_logs' created successfully.")
            
            # Create indexes for better performance
            session.execute(text("""
                CREATE INDEX ix_mission_execution_logs_mission_id 
                ON mission_execution_logs (mission_id)
            """))
            
            session.execute(text("""
                CREATE INDEX ix_mission_execution_logs_agent_name 
                ON mission_execution_logs (agent_name)
            """))
            
            session.execute(text("""
                CREATE INDEX ix_mission_execution_logs_status 
                ON mission_execution_logs (status)
            """))
            
            session.execute(text("""
                CREATE INDEX ix_mission_execution_logs_timestamp 
                ON mission_execution_logs (timestamp)
            """))
            
            logger.info("Indexes for 'mission_execution_logs' created successfully.")
            
        except SQLAlchemyError as e:
            logger.error(f"Error creating table mission_execution_logs: {e}")
            raise

    def down(self, session):
        """
        Drop the mission_execution_logs table.
        """
        logger.info(f"Reverting migration {self.version}: {self.description}")
        
        try:
            session.execute(text("DROP TABLE IF EXISTS mission_execution_logs"))
            logger.info("Table 'mission_execution_logs' dropped successfully.")
        except SQLAlchemyError as e:
            logger.error(f"Error dropping table mission_execution_logs: {e}")
            raise
