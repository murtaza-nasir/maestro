#!/usr/bin/env python3
"""
Migration script from SQLite to PostgreSQL
This script migrates all data from an existing SQLite database to PostgreSQL
"""

import os
import sys
import logging
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import Session
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_sqlite_to_postgres(sqlite_path="data/maestro.db", 
                              postgres_url="postgresql://maestro_user:maestro_password@localhost:5432/maestro_db"):
    """
    Migrate all data from SQLite to PostgreSQL
    
    Args:
        sqlite_path: Path to SQLite database file
        postgres_url: PostgreSQL connection string
    """
    
    if not os.path.exists(sqlite_path):
        logger.error(f"SQLite database not found at {sqlite_path}")
        return False
    
    logger.info(f"Starting migration from {sqlite_path} to PostgreSQL")
    
    # Create engines
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    postgres_engine = create_engine(postgres_url)
    
    # Get metadata from SQLite
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)
    
    # Tables to migrate in order (respecting foreign key constraints)
    table_order = [
        'users',
        'document_groups',
        'documents',
        'document_group_association',
        'chats',
        'messages',
        'missions',
        'mission_execution_logs',
        'document_processing_jobs',
        'writing_sessions',
        'drafts',
        'draft_references',
        'writing_session_stats',
        'system_settings'
    ]
    
    # Import models to ensure PostgreSQL tables exist
    from database.database import Base
    from database import models
    from database.init_postgres import ensure_extensions, create_tables
    
    # Ensure PostgreSQL is ready
    try:
        ensure_extensions()
        create_tables()
    except Exception as e:
        logger.error(f"Failed to prepare PostgreSQL: {e}")
        return False
    
    # Migrate each table
    with Session(sqlite_engine) as sqlite_session, Session(postgres_engine) as pg_session:
        for table_name in table_order:
            if table_name not in sqlite_meta.tables:
                logger.warning(f"Table {table_name} not found in SQLite, skipping")
                continue
            
            logger.info(f"Migrating table: {table_name}")
            
            try:
                # Get SQLite table
                sqlite_table = Table(table_name, sqlite_meta, autoload=True, autoload_with=sqlite_engine)
                
                # Select all data from SQLite
                sqlite_data = sqlite_session.execute(sqlite_table.select()).fetchall()
                
                if not sqlite_data:
                    logger.info(f"  No data in {table_name}")
                    continue
                
                # Prepare data for PostgreSQL
                rows_to_insert = []
                for row in sqlite_data:
                    row_dict = dict(row._mapping)
                    
                    # Convert string UUIDs to UUID objects for PostgreSQL
                    for key, value in row_dict.items():
                        # Handle UUID fields
                        if key in ['id', 'chat_id', 'document_id', 'group_id', 'document_group_id', 
                                  'mission_id', 'writing_session_id', 'draft_id', 'session_id',
                                  'current_draft_id'] and value:
                            # Keep as string for now, PostgreSQL will handle conversion
                            pass
                        
                        # Handle JSON fields - ensure they're valid JSON
                        if key in ['settings', 'metadata_', 'sources', 'mission_context',
                                  'full_input', 'full_output', 'model_details', 'tool_calls',
                                  'file_interactions', 'value'] and value:
                            if isinstance(value, str):
                                try:
                                    # Validate JSON
                                    json.loads(value)
                                except json.JSONDecodeError:
                                    logger.warning(f"Invalid JSON in {table_name}.{key}, setting to null")
                                    row_dict[key] = None
                    
                    rows_to_insert.append(row_dict)
                
                # Insert into PostgreSQL
                if rows_to_insert:
                    pg_table = Table(table_name, MetaData(), autoload=True, autoload_with=postgres_engine)
                    pg_session.execute(pg_table.insert(), rows_to_insert)
                    pg_session.commit()
                    logger.info(f"  Migrated {len(rows_to_insert)} rows")
                
            except Exception as e:
                logger.error(f"Failed to migrate {table_name}: {e}")
                pg_session.rollback()
                continue
    
    logger.info("Migration completed!")
    
    # Verify migration
    logger.info("\nVerifying migration...")
    with Session(postgres_engine) as pg_session:
        for table_name in table_order:
            try:
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                count = pg_session.execute(count_query).scalar()
                logger.info(f"  {table_name}: {count} rows")
            except Exception as e:
                logger.warning(f"  Could not verify {table_name}: {e}")
    
    return True

def main():
    """Main migration function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate SQLite database to PostgreSQL")
    parser.add_argument("--sqlite-path", default="data/maestro.db",
                       help="Path to SQLite database file")
    parser.add_argument("--postgres-url", 
                       default=os.getenv("DATABASE_URL", 
                                       "postgresql://maestro_user:maestro_password@localhost:5432/maestro_db"),
                       help="PostgreSQL connection URL")
    parser.add_argument("--force", action="store_true",
                       help="Force migration even if PostgreSQL tables have data")
    
    args = parser.parse_args()
    
    # Check if PostgreSQL already has data
    if not args.force:
        try:
            engine = create_engine(args.postgres_url)
            with engine.connect() as conn:
                result = conn.execute("SELECT COUNT(*) FROM users").scalar()
                if result > 0:
                    logger.error("PostgreSQL database already has data. Use --force to override.")
                    sys.exit(1)
        except Exception:
            # Table might not exist, which is fine
            pass
    
    # Run migration
    success = migrate_sqlite_to_postgres(args.sqlite_path, args.postgres_url)
    
    if success:
        logger.info("\n✅ Migration completed successfully!")
        logger.info("You can now update your DATABASE_URL to use PostgreSQL")
    else:
        logger.error("\n❌ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()