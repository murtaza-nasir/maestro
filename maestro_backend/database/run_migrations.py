"""
Migration management script for MAESTRO database.
"""

import logging
import sys
import os

# Add the parent directory to the path so we can import from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import engine
from database.models import Base
from database.migrations.migration_runner import MigrationRunner
from database.migrations.migration_001_add_user_timestamps import Migration001AddUserTimestamps
from database.migrations.migration_002_create_chat_tables import Migration002CreateChatTables
from database.migrations.migration_003_add_document_tables import Migration as Migration003
from database.migrations.migration_004_rename_metadata_column import Migration as Migration004
from database.migrations.migration_005_enhance_document_schema import Migration as Migration005
from database.migrations.migration_006_add_user_settings import Migration as Migration006
from database.migrations.migration_007_add_timezone_to_user_timestamps import Migration as Migration007
from database.migrations.migration_008_add_updated_at_to_documents import Migration as Migration008
from database.migrations.migration_009_add_writing_tables import Migration as Migration009
from database.migrations.migration_010_add_chat_type import Migration010AddChatType
from database.migrations.migration_011_add_message_sources import Migration011AddMessageSources
from database.migrations.migration_012_add_user_profile_fields import Migration012AddUserProfileFields
from database.migrations.migration_013_add_writing_session_stats import Migration013AddWritingSessionStats
from database.migrations.migration_014_add_appearance_settings import Migration as Migration014
from database.migrations.migration_015_add_is_admin_to_users import Migration as Migration015
from database.migrations.migration_016_add_is_active_to_users import Migration as Migration016
from database.migrations.migration_017_add_role_to_users import Migration as Migration017
from database.migrations.migration_018_add_user_type_to_users import Migration as Migration018
from database.migrations.migration_019_create_system_settings_table import Migration as Migration019
from database.migrations.migration_020_add_execution_logs import Migration as Migration020

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_migrations():
    """Set up and run database migrations."""
    try:
        # Database URL (same as in database.py)
        database_url = "sqlite:///./data/maestro.db"
        
        # Create migration runner
        runner = MigrationRunner(database_url)
        
        # Register all migrations
        runner.register_migration(Migration001AddUserTimestamps)
        runner.register_migration(Migration002CreateChatTables)
        runner.register_migration(Migration003)
        runner.register_migration(Migration004)
        runner.register_migration(Migration005)
        runner.register_migration(Migration006)
        runner.register_migration(Migration007)
        runner.register_migration(Migration008)
        runner.register_migration(Migration009)
        runner.register_migration(Migration010AddChatType)
        runner.register_migration(Migration011AddMessageSources)
        runner.register_migration(Migration012AddUserProfileFields)
        runner.register_migration(Migration013AddWritingSessionStats)
        runner.register_migration(Migration014)
        runner.register_migration(Migration015)
        runner.register_migration(Migration016)
        runner.register_migration(Migration017)
        runner.register_migration(Migration018)
        runner.register_migration(Migration019)
        runner.register_migration(Migration020)
        
        return runner
        
    except Exception as e:
        logger.error(f"Error setting up migrations: {e}")
        return None

def run_migrations():
    """Run all pending migrations."""
    logger.info("🔄 Starting database migrations...")

    # Create all tables first
    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created.")
    except Exception as e:
        logger.error(f"❌ Error creating database tables: {e}", exc_info=True)
        return False
    
    runner = setup_migrations()
    if not runner:
        logger.error("❌ Failed to setup migration runner")
        return False
    
    try:
        # Get migration status
        status = runner.get_migration_status()
        logger.info(f"Migration status: {len(status['applied_migrations'])} applied, "
                   f"{len(status['pending_migrations'])} pending, "
                   f"{len(status['failed_migrations'])} failed")
        
        # Run pending migrations
        success = runner.run_migrations()
        
        if success:
            logger.info("✅ All migrations completed successfully!")
            return True
        else:
            logger.error("❌ Some migrations failed!")
            return False
            
    except Exception as e:
        logger.error(f"❌ Migration error: {e}", exc_info=True)
        return False

def get_migration_status():
    """Get the current migration status."""
    runner = setup_migrations()
    if not runner:
        return None
    
    return runner.get_migration_status()

def main():
    """Main entry point for migration script."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "status":
            status = get_migration_status()
            if status:
                print(f"Applied migrations: {len(status['applied_migrations'])}")
                print(f"Pending migrations: {len(status['pending_migrations'])}")
                print(f"Failed migrations: {len(status['failed_migrations'])}")
                
                if status['pending_migrations']:
                    print("\nPending migrations:")
                    for migration in status['pending_migrations']:
                        print(f"  - {migration['version']}: {migration['description']}")
            else:
                print("Error getting migration status")
                sys.exit(1)
                
        elif command == "run":
            success = run_migrations()
            sys.exit(0 if success else 1)
            
        else:
            print(f"Unknown command: {command}")
            print("Usage: python run_migrations.py [status|run]")
            sys.exit(1)
    else:
        # Default: run migrations
        success = run_migrations()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
