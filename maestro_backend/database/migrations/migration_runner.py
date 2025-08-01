"""
Migration runner for managing database schema changes.
"""

import json
import os
import logging
from typing import List, Dict, Type
from sqlalchemy import Connection, text, create_engine
from .base_migration import BaseMigration

logger = logging.getLogger(__name__)

class MigrationRunner:
    """Manages and executes database migrations."""
    
    def __init__(self, database_url: str, migrations_dir: str = None):
        self.database_url = database_url
        self.engine = create_engine(database_url)
        self.migrations_dir = migrations_dir or os.path.dirname(__file__)
        self.state_file = os.path.join(self.migrations_dir, "migration_state.json")
        self.migrations: List[BaseMigration] = []
        
    def register_migration(self, migration_class: Type[BaseMigration]):
        """Register a migration class."""
        try:
            # Try to instantiate with no arguments (new BaseMigration pattern)
            migration = migration_class()
        except TypeError:
            # If that fails, try with engine parameter (old pattern)
            try:
                migration = migration_class(self.engine)
                # Wrap old migration to make it compatible with new interface
                migration = self._wrap_old_migration(migration)
            except Exception as e:
                logger.error(f"Failed to instantiate migration {migration_class.__name__}: {e}")
                raise
        
        self.migrations.append(migration)
        logger.info(f"Registered {migration}")
    
    def _wrap_old_migration(self, old_migration):
        """Wrap an old migration to make it compatible with the new BaseMigration interface."""
        class WrappedMigration:
            def __init__(self, old_migration):
                self.old_migration = old_migration
                # Convert integer version to string with zero-padding
                if isinstance(old_migration.version, int):
                    self.version = f"{old_migration.version:03d}"
                else:
                    self.version = str(old_migration.version)
                self.description = old_migration.description
            
            def up(self, connection):
                """Adapter for old migration up() method."""
                # Old migrations don't take connection parameter and manage their own connections
                return self.old_migration.up()
            
            def down(self, connection):
                """Adapter for old migration down() method."""
                return self.old_migration.down()
            
            def validate(self, connection):
                """Default validation for old migrations."""
                return True
            
            def __str__(self):
                return f"Migration {self.version}: {self.description}"
        
        return WrappedMigration(old_migration)
        
    def _load_migration_state(self) -> Dict[str, bool]:
        """Load the current migration state from file."""
        if not os.path.exists(self.state_file):
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading migration state: {e}")
            return {}
    
    def _save_migration_state(self, state: Dict[str, bool]):
        """Save the migration state to file."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving migration state: {e}")
    
    def _create_migration_table(self, connection: Connection):
        """Create the migration tracking table if it doesn't exist."""
        try:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_history (
                    version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT TRUE
                )
            """))
            connection.commit()
        except Exception as e:
            logger.error(f"Error creating migration table: {e}")
            raise
    
    def _is_migration_applied(self, connection: Connection, version: str) -> bool:
        """Check if a migration has been applied."""
        try:
            result = connection.execute(
                text("SELECT COUNT(*) FROM migration_history WHERE version = :version AND success = TRUE"),
                {"version": version}
            )
            return result.fetchone()[0] > 0
        except Exception:
            # If table doesn't exist or query fails, assume migration not applied
            return False
    
    def _record_migration(self, connection: Connection, migration: BaseMigration, success: bool):
        """Record a migration in the database."""
        try:
            connection.execute(
                text("""
                    INSERT OR REPLACE INTO migration_history (version, description, success)
                    VALUES (:version, :description, :success)
                """),
                {"version": migration.version, "description": migration.description, "success": success}
            )
            connection.commit()
        except Exception as e:
            logger.error(f"Error recording migration {migration.version}: {e}")
    
    def get_pending_migrations(self) -> List[BaseMigration]:
        """Get list of migrations that haven't been applied yet."""
        pending = []
        
        with self.engine.connect() as connection:
            self._create_migration_table(connection)
            
            for migration in sorted(self.migrations, key=lambda m: m.version):
                if not self._is_migration_applied(connection, migration.version):
                    pending.append(migration)
        
        return pending
    
    def run_migrations(self, dry_run: bool = False) -> bool:
        """Run all pending migrations."""
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return True

        logger.info(f"Found {len(pending)} pending migrations")

        if dry_run:
            for migration in pending:
                logger.info(f"Would apply: {migration}")
            return True

        success_count = 0
        for migration in pending:
            try:
                logger.info(f"Applying {migration}")
                with self.engine.connect() as connection:
                    # Each migration runs in its own connection context
                    migration.up(connection)

                    if not migration.validate(connection):
                        logger.error(f"❌ Migration {migration.version} validation failed")
                        self._record_migration(connection, migration, False)
                        break  # Stop on failure

                    self._record_migration(connection, migration, True)
                    logger.info(f"✅ Successfully applied {migration}")
                    success_count += 1

            except Exception as e:
                logger.error(f"❌ Failed to apply {migration}: {e}", exc_info=True)
                # Record failure in a new connection to be safe
                with self.engine.connect() as connection:
                    self._record_migration(connection, migration, False)
                break  # Stop on failure

        logger.info(f"Applied {success_count}/{len(pending)} migrations")
        return success_count == len(pending)
    
    def get_migration_status(self) -> Dict:
        """Get the current migration status."""
        status = {
            "total_migrations": len(self.migrations),
            "applied_migrations": [],
            "pending_migrations": [],
            "failed_migrations": []
        }
        
        with self.engine.connect() as connection:
            self._create_migration_table(connection)
            
            # Get applied migrations
            try:
                result = connection.execute(text("""
                    SELECT version, description, applied_at, success 
                    FROM migration_history 
                    ORDER BY version
                """))
                
                for row in result.fetchall():
                    migration_info = {
                        "version": row[0],
                        "description": row[1],
                        "applied_at": row[2],
                        "success": row[3]
                    }
                    
                    if row[3]:  # success
                        status["applied_migrations"].append(migration_info)
                    else:
                        status["failed_migrations"].append(migration_info)
                        
            except Exception as e:
                logger.error(f"Error getting migration status: {e}")
        
        # Get pending migrations
        pending = self.get_pending_migrations()
        status["pending_migrations"] = [
            {"version": m.version, "description": m.description}
            for m in pending
        ]
        
        return status
