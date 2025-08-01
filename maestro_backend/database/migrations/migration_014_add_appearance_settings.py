"""
Migration for adding theme and color_scheme to the users table.
"""
from sqlalchemy import Column, String, text
from sqlalchemy.engine.base import Engine
import logging

logger = logging.getLogger(__name__)

class Migration:
    """
    Migration for adding theme and color_scheme to the users table.
    """
    
    def __init__(self, engine: Engine):
        self.engine = engine
        self.version = 14
        self.description = "Add theme and color_scheme to users table"

    def up(self):
        """
        Applies the migration.
        """
        logger.info(f"Running migration {self.version}: {self.description}")
        with self.engine.connect() as connection:
            try:
                # Use a transaction
                with connection.begin():
                    # Check if 'theme' column exists
                    if not self._column_exists(connection, 'users', 'theme'):
                        connection.execute(text("ALTER TABLE users ADD COLUMN theme TEXT"))
                        logger.info("Added 'theme' column to 'users' table.")
                    else:
                        logger.info("'theme' column already exists in 'users' table.")

                    # Check if 'color_scheme' column exists
                    if not self._column_exists(connection, 'users', 'color_scheme'):
                        connection.execute(text("ALTER TABLE users ADD COLUMN color_scheme TEXT"))
                        logger.info("Added 'color_scheme' column to 'users' table.")
                    else:
                        logger.info("'color_scheme' column already exists in 'users' table.")
                
                logger.info(f"Migration {self.version} applied successfully.")
                return True
            except Exception as e:
                logger.error(f"Error applying migration {self.version}: {e}")
                return False

    def down(self):
        """
        Reverts the migration.
        """
        logger.info(f"Reverting migration {self.version}: {self.description}")
        with self.engine.connect() as connection:
            try:
                # Use a transaction
                with connection.begin():
                    # Check if 'theme' column exists before dropping
                    if self._column_exists(connection, 'users', 'theme'):
                        connection.execute('ALTER TABLE users DROP COLUMN theme')
                        logger.info("Dropped 'theme' column from 'users' table.")
                    else:
                        logger.info("'theme' column does not exist in 'users' table.")

                    # Check if 'color_scheme' column exists before dropping
                    if self._column_exists(connection, 'users', 'color_scheme'):
                        connection.execute('ALTER TABLE users DROP COLUMN color_scheme')
                        logger.info("Dropped 'color_scheme' column from 'users' table.")
                    else:
                        logger.info("'color_scheme' column does not exist in 'users' table.")
                
                logger.info(f"Migration {self.version} reverted successfully.")
                return True
            except Exception as e:
                logger.error(f"Error reverting migration {self.version}: {e}")
                return False

    def _column_exists(self, connection, table_name, column_name):
        """
        Checks if a column exists in a table.
        """
        from sqlalchemy import inspect
        inspector = inspect(connection)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
