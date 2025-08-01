"""
Base migration class for database schema changes.
"""

from abc import ABC, abstractmethod
from sqlalchemy import Connection
import logging

logger = logging.getLogger(__name__)

class BaseMigration(ABC):
    """Base class for all database migrations."""
    
    version: str = None
    description: str = None
    
    def __init__(self):
        if not self.version:
            raise ValueError(f"Migration {self.__class__.__name__} must define a version")
        if not self.description:
            raise ValueError(f"Migration {self.__class__.__name__} must define a description")
    
    @abstractmethod
    def up(self, connection: Connection) -> None:
        """Apply the migration."""
        pass
    
    def down(self, connection: Connection) -> None:
        """Rollback the migration (optional)."""
        logger.warning(f"Migration {self.version} does not support rollback")
        pass
    
    def validate(self, connection: Connection) -> bool:
        """Validate that the migration was applied correctly."""
        return True
    
    def __str__(self):
        return f"Migration {self.version}: {self.description}"
