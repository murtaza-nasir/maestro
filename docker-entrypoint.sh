#!/bin/bash
set -e

# Check if .env file exists, if not, copy the example
if [ ! -f "/app/ai_researcher/.env" ]; then
    echo "No .env file found. Creating from .env.example..."
    cp /app/ai_researcher/.env.example /app/ai_researcher/.env
    echo "Please update the .env file with your API keys and settings."
fi

# Handle different commands
if [ "$1" = "ui" ]; then
    echo "Starting MAESTRO Web UI..."
    exec python -m streamlit run ai_researcher/ui/app.py
elif [ "$1" = "ingest" ]; then
    shift
    echo "Running document ingestion..."
    exec python -m ai_researcher.main_cli ingest "$@"
elif [ "$1" = "query" ]; then
    shift
    echo "Running query..."
    exec python -m ai_researcher.main_cli query "$@"
elif [ "$1" = "inspect-store" ]; then
    shift
    echo "Inspecting vector store..."
    exec python -m ai_researcher.main_cli inspect-store "$@"
elif [ "$1" = "run-research" ]; then
    shift
    echo "Running research..."
    exec python -m ai_researcher.main_cli run-research "$@"
elif [ "$1" = "shell" ]; then
    echo "Starting shell..."
    exec /bin/bash
else
    echo "MAESTRO CLI"
    echo "Available commands:"
    echo "  ui                - Start the MAESTRO Web UI"
    echo "  ingest            - Ingest documents into the vector store"
    echo "  query             - Query the vector store"
    echo "  inspect-store     - Inspect the vector store"
    echo "  run-research      - Run a research mission"
    echo "  shell             - Start a shell inside the container"
    echo ""
    echo "For CLI command help, use: docker run --rm maestro [command] --help"
    echo ""
    exec python -m ai_researcher.main_cli "$@"
fi
