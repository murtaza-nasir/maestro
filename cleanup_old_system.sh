#!/bin/bash

# Cleanup script for old document system
# This removes all old databases and vector store files

echo "=== Cleaning up old document system ==="

# Stop the application first
echo "Stopping docker containers..."
docker-compose down

# Remove old SQLite database
echo "Removing old SQLite database..."
rm -f data/maestro.db
rm -f data/maestro.db-journal
rm -f data/maestro.db-wal

# Remove old vector store
echo "Removing old ChromaDB vector store..."
rm -rf maestro_backend/ai_researcher/data/vector_store/

# Remove processed files
echo "Removing processed files..."
rm -rf maestro_backend/ai_researcher/data/processed/

# Remove old vector store wrapper files
echo "Removing old vector store wrapper files..."
cd maestro_backend/ai_researcher/core_rag/

# Keep only essential files
rm -f vector_store.py
rm -f vector_store_direct.py
rm -f vector_store_factory.py
rm -f vector_store_manager.py
rm -f vector_store_manager_original.py
rm -f vector_store_original.py
rm -f vector_store_original.py.bak
rm -f vector_store_safe.py
rm -f vector_store_safe_original.py
rm -f vector_store_with_lock.py

cd ../../..

# Remove all migration files since we're starting fresh
echo "Removing old migration files..."
rm -f maestro_backend/database/migrations/*.py
# Keep __init__.py if it exists
touch maestro_backend/database/migrations/__init__.py

echo "=== Cleanup complete ==="
echo "Ready to build new system from scratch"