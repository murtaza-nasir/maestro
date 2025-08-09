#!/bin/bash

# Maestro shutdown script

echo "🛑 Stopping Maestro..."

# Source GPU detection to determine which compose files were used
source ./detect_gpu.sh

if [ "$GPU_SUPPORT" = "nvidia" ]; then
    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.gpu.yml"
else
    COMPOSE_FILES="-f docker-compose.yml"
fi

# Stop services
docker compose $COMPOSE_FILES down

echo "✅ Maestro stopped."