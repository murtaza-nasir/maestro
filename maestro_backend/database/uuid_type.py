"""
Custom UUID type for SQLAlchemy that automatically converts UUIDs to strings.
This solves the UUID serialization issue at the database level.
"""

from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
import uuid


class StringUUID(TypeDecorator):
    """
    A UUID type that stores UUIDs in PostgreSQL but returns them as strings.
    This eliminates the need for manual UUID to string conversions throughout the codebase.
    """
    impl = PostgresUUID(as_uuid=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        """Convert UUID to string when reading from database."""
        if value is None:
            return None
        return str(value)

    def process_bind_param(self, value, dialect):
        """Convert string to UUID when writing to database."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(value)
        except (ValueError, AttributeError):
            return value


# For backward compatibility, also create a type that handles both
class HybridUUID(TypeDecorator):
    """
    A UUID type that can work with both string and UUID inputs/outputs.
    Stores as UUID in PostgreSQL but can handle string conversions automatically.
    """
    impl = PostgresUUID(as_uuid=False)  # Store as string in DB
    cache_ok = True

    def process_result_value(self, value, dialect):
        """Always return as string."""
        if value is None:
            return None
        return str(value)

    def process_bind_param(self, value, dialect):
        """Accept both UUID and string, store as string."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)  # Ensure it's always a string