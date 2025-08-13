#!/bin/bash

# Startup script for MAESTRO backend
# This script runs database migrations before starting the FastAPI server

echo "🚀 Starting MAESTRO Backend..."

# Run database migrations
echo "📊 Running database migrations..."
python -m database.run_migrations

# Check if migrations were successful
if [ $? -eq 0 ]; then
    echo "✅ Database migrations completed successfully!"
else
    echo "❌ Database migrations failed!"
    exit 1
fi

# Start the FastAPI server
echo "🌐 Starting FastAPI server..."
# Convert LOG_LEVEL to lowercase for uvicorn
UVICORN_LOG_LEVEL=$(echo "${LOG_LEVEL:-error}" | tr '[:upper:]' '[:lower:]')
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level $UVICORN_LOG_LEVEL --timeout-keep-alive 600 