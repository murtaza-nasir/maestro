#!/bin/bash

# Maestro Database Reset Script for Docker
# This script runs the reset inside the Docker container where the databases actually exist

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}       Maestro Database Reset Tool (Docker)${NC}"
echo -e "${CYAN}============================================================${NC}"
echo

# Parse command line arguments
BACKUP=false
FORCE=false
STATS=false
CHECK=false

for arg in "$@"
do
    case $arg in
        --backup)
            BACKUP=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --stats)
            STATS=true
            shift
            ;;
        --check)
            CHECK=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --backup  Create backups before reset"
            echo "  --force   Skip confirmation prompts"
            echo "  --stats   Show database statistics only"
            echo "  --check   Check data consistency across databases"
            echo "  --help    Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running or you don't have permission to access it${NC}"
    echo "Please start Docker or run with appropriate permissions (e.g., sudo)"
    exit 1
fi

# Check if the backend container exists
if ! docker ps -a --format '{{.Names}}' | grep -q '^maestro-backend$'; then
    echo -e "${RED}Error: maestro-backend container not found${NC}"
    echo "Please ensure the Maestro application is deployed with:"
    echo "  docker-compose up -d"
    exit 1
fi

# Copy the reset script to the container
echo -e "${BLUE}Copying reset script to Docker container...${NC}"
docker cp reset_databases.py maestro-backend:/app/reset_databases.py

# Build the command based on arguments
CMD="python /app/reset_databases.py"
if [ "$BACKUP" = true ]; then
    CMD="$CMD --backup"
fi
if [ "$FORCE" = true ]; then
    CMD="$CMD --force"
fi
if [ "$STATS" = true ]; then
    CMD="$CMD --stats"
fi
if [ "$CHECK" = true ]; then
    CMD="$CMD --check"
fi

# Execute the reset script inside the container
echo -e "${BLUE}Running reset script inside Docker container...${NC}"
echo

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q '^maestro-backend$'; then
    # Container is running, use exec
    docker exec -it maestro-backend $CMD
else
    # Container exists but not running, use run
    echo -e "${YELLOW}Backend container is not running. Starting temporary container...${NC}"
    docker run --rm -it \
        -v maestro-data:/app/ai_researcher/data \
        -v ./maestro_backend/data:/app/data \
        -w /app \
        maestro-backend \
        $CMD
fi

# Clean up - remove the script from container if it's running
if docker ps --format '{{.Names}}' | grep -q '^maestro-backend$'; then
    docker exec maestro-backend rm -f /app/reset_databases.py 2>/dev/null || true
fi

echo
echo -e "${GREEN}Database reset operation completed${NC}"

# If not just checking stats, remind about restarting
if [ "$STATS" = false ] && [ "$CHECK" = false ]; then
    echo
    echo -e "${CYAN}Next steps:${NC}"
    echo "1. Restart the Docker containers:"
    echo "   docker-compose down"
    echo "   docker-compose up -d"
    echo "2. Re-upload any documents you need"
    echo "3. Documents will be processed and synchronized across all databases"
fi