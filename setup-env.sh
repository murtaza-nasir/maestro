#!/bin/bash

# MAESTRO - Environment Setup Script
# This script helps you set up your .env file for the first time

set -e

echo "# MAESTRO - Environment Setup"
echo "=================================="

# Check if .env already exists
if [ -f ".env" ]; then
    echo "⚠️  .env file already exists!"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

# Copy .env.example to .env
if [ ! -f ".env.example" ]; then
    echo "❌ .env.example file not found!"
    echo "Please make sure you're in the correct directory."
    exit 1
fi

cp .env.example .env
echo "✅ Created .env from .env.example"

# Prompt for basic configuration
echo ""
echo "📝 Basic Configuration Setup"
echo "You can modify these values later in the .env file"
echo ""

# Backend host
read -p "Backend host (default: 127.0.0.1): " backend_host
backend_host=${backend_host:-127.0.0.1}
sed -i "s/BACKEND_HOST=127.0.0.1/BACKEND_HOST=$backend_host/" .env

# Frontend host
read -p "Frontend host (default: 127.0.0.1): " frontend_host
frontend_host=${frontend_host:-127.0.0.1}
sed -i "s/FRONTEND_HOST=127.0.0.1/FRONTEND_HOST=$frontend_host/" .env

# Protocol selection
echo ""
echo "Select protocol:"
echo "1) HTTP/WS (development)"
echo "2) HTTPS/WSS (production)"
read -p "Choice (1-2, default: 1): " protocol_choice
protocol_choice=${protocol_choice:-1}

if [ "$protocol_choice" = "2" ]; then
    sed -i "s/API_PROTOCOL=http/API_PROTOCOL=https/" .env
    sed -i "s/WS_PROTOCOL=ws/WS_PROTOCOL=wss/" .env
    echo "✅ Set to HTTPS/WSS for production"
else
    echo "✅ Set to HTTP/WS for development"
fi

# Timezone
read -p "Timezone (default: America/Chicago): " timezone
timezone=${timezone:-America/Chicago}
sed -i "s|TZ=America/Chicago|TZ=$timezone|" .env
sed -i "s|VITE_SERVER_TIMEZONE=America/Chicago|VITE_SERVER_TIMEZONE=$timezone|" .env

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Your .env file has been created with the following configuration:"
echo "  Backend: $backend_host"
echo "  Frontend: $frontend_host"
echo "  Protocol: $([ "$protocol_choice" = "2" ] && echo "HTTPS/WSS" || echo "HTTP/WS")"
echo "  Timezone: $timezone"
echo ""
echo "You can now start MAESTRO with:"
echo "  docker compose up -d"
echo ""
echo "To modify additional settings, edit the .env file:"
echo "  nano .env"
