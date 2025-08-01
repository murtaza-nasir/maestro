from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
import logging
from .base_migration import BaseMigration

logger = logging.getLogger(__name__)

class Migration(BaseMigration):
    """
    Migration to create the system_settings table for storing system-wide configurations.
    """
    
    version = "019"
    description = "Create system_settings table"

    def up(self, session):
        """
        Create the system_settings table.
        """
        logger.info(f"Applying migration {self.version}: {self.description}")
        
        inspector = inspect(session)
        if "system_settings" in inspector.get_table_names():
            logger.info("Table 'system_settings' already exists, skipping creation.")
            return

        try:
            session.execute(text("""
                CREATE TABLE system_settings (
                    id INTEGER PRIMARY KEY,
                    key VARCHAR(255) NOT NULL UNIQUE,
                    value JSON,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Table 'system_settings' created successfully.")
        except SQLAlchemyError as e:
            logger.error(f"Error creating table system_settings: {e}")
            raise

    def down(self, session):
        """
        Drop the system_settings table.
        """
        logger.info(f"Reverting migration {self.version}: {self.description}")
        
        try:
            session.execute(text("DROP TABLE IF EXISTS system_settings"))
            logger.info("Table 'system_settings' dropped successfully.")
        except SQLAlchemyError as e:
            logger.error(f"Error dropping table system_settings: {e}")
            raise
