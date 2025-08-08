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

# Detect OS for sed compatibility
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS requires backup extension for in-place editing
    SED_INPLACE=(-i '')
else
    # Linux doesn't require backup extension
    SED_INPLACE=(-i)
fi

# Auto-detect machine IP address
detect_machine_ip() {
    # Try to get the primary network interface IP
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS-specific IP detection
        local ip=$(route get default | grep gateway | awk '{print $2}' | head -1)
        if [ -z "$ip" ]; then
            ip=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
        fi
    else
        # Linux IP detection
        local ip=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+')
        if [ -z "$ip" ]; then
            # Fallback: try hostname -I
            ip=$(hostname -I 2>/dev/null | awk '{print $1}')
        fi
        if [ -z "$ip" ]; then
            # Fallback: try ip addr show
            ip=$(ip addr show | grep 'inet ' | grep -v 127.0.0.1 | head -n1 | awk '{print $2}' | cut -d/ -f1)
        fi
    fi
    echo "$ip"
}

DETECTED_IP=$(detect_machine_ip)

if [ -n "$DETECTED_IP" ]; then
    echo "🔍 Auto-detected machine IP: $DETECTED_IP"
    echo ""
    echo "Choose IP configuration:"
    echo "1) Use detected IP ($DETECTED_IP) - for network access"
    echo "2) Use localhost (127.0.0.1) - for local development only"
    echo "3) Enter custom IP"
    read -p "Choice (1-3, default: 1): " ip_choice
    ip_choice=${ip_choice:-1}

    case $ip_choice in
        2)
            backend_host="127.0.0.1"
            frontend_host="127.0.0.1"
            echo "✅ Using localhost for local development"
            ;;
        3)
            read -p "Backend host: " backend_host
            read -p "Frontend host: " frontend_host
            ;;
        *)
            backend_host="$DETECTED_IP"
            frontend_host="$DETECTED_IP"
            echo "✅ Using detected IP: $DETECTED_IP"
            ;;
    esac
else
    # Fallback to manual input if auto-detection fails
    echo "⚠️  Could not auto-detect IP address"
    read -p "Backend host (default: 127.0.0.1): " backend_host
    backend_host=${backend_host:-127.0.0.1}
    frontend_host="$backend_host"
fi

# Update .env file - need to handle both possible starting values
sed "${SED_INPLACE[@]}" "s/BACKEND_HOST=127\.0\.0\.1/BACKEND_HOST=$backend_host/" .env
sed "${SED_INPLACE[@]}" "s/BACKEND_HOST=192\.168\.68\.85/BACKEND_HOST=$backend_host/" .env
sed "${SED_INPLACE[@]}" "s/FRONTEND_HOST=127\.0\.0\.1/FRONTEND_HOST=$frontend_host/" .env
sed "${SED_INPLACE[@]}" "s/FRONTEND_HOST=192\.168\.68\.85/FRONTEND_HOST=$frontend_host/" .env

# Protocol selection
echo ""
echo "Select protocol:"
echo "1) HTTP/WS (development)"
echo "2) HTTPS/WSS (production)"
read -p "Choice (1-2, default: 1): " protocol_choice
protocol_choice=${protocol_choice:-1}

if [ "$protocol_choice" = "2" ]; then
    sed "${SED_INPLACE[@]}" "s/API_PROTOCOL=http/API_PROTOCOL=https/" .env
    sed "${SED_INPLACE[@]}" "s/WS_PROTOCOL=ws/WS_PROTOCOL=wss/" .env
    echo "✅ Set to HTTPS/WSS for production"
else
    echo "✅ Set to HTTP/WS for development"
fi

# Timezone
read -p "Timezone (default: America/Chicago): " timezone
timezone=${timezone:-America/Chicago}
sed "${SED_INPLACE[@]}" "s|TZ=America/Chicago|TZ=$timezone|" .env
sed "${SED_INPLACE[@]}" "s|VITE_SERVER_TIMEZONE=America/Chicago|VITE_SERVER_TIMEZONE=$timezone|" .env

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
