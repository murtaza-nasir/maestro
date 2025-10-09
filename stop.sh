#!/bin/bash

# Maestro shutdown script

echo "🛑 Stopping Maestro..."

# Source GPU detection to determine which compose files were used
source ./detect_gpu.sh

# Define Docker Compose files based on GPU support
COMPOSE_FILES=""
case "$GPU_SUPPORT" in
    "nvidia")
        COMPOSE_FILES="-f docker-compose.yml -f docker-compose.gpu.yml"
        ;;
    "mac"|"cpu")
        COMPOSE_FILES="-f docker-compose.cpu.yml"
        ;;
    *) # Default case for any other value, including unset
        COMPOSE_FILES="-f docker-compose.yml"
        ;;
esac

# Stop services
docker compose $COMPOSE_FILES down

echo "✅ Maestro stopped."
