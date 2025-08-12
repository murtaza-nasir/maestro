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

# Simple setup mode
echo ""
echo "Choose setup mode:"
echo "1) Simple (localhost only) - Recommended for most users"
echo "2) Network (access from other devices)"
echo "3) Custom domain (for reverse proxy setups)"
read -p "Choice (1-3, default: 1): " setup_mode
setup_mode=${setup_mode:-1}

case $setup_mode in
    2)
        # Auto-detect machine IP for network access
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS-specific IP detection
            ip=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
        else
            # Linux IP detection
            ip=$(hostname -I 2>/dev/null | awk '{print $1}')
        fi
        
        if [ -n "$ip" ]; then
            echo "🔍 Auto-detected IP: $ip"
            read -p "Use this IP? (Y/n): " use_detected
            if [[ $use_detected =~ ^[Nn]$ ]]; then
                read -p "Enter IP address: " ip
            fi
        else
            read -p "Enter IP address: " ip
        fi
        
        # Add the IP to CORS allowed origins
        sed "${SED_INPLACE[@]}" "s/CORS_ALLOWED_ORIGINS=\*/CORS_ALLOWED_ORIGINS=http:\/\/$ip,http:\/\/localhost/" .env
        echo "✅ Configured for network access from: $ip"
        ;;
    3)
        read -p "Enter your domain (e.g., researcher.local or app.example.com): " domain
        read -p "Using HTTPS? (y/N): " use_https
        
        if [[ $use_https =~ ^[Yy]$ ]]; then
            protocol="https"
        else
            protocol="http"
        fi
        
        # Set CORS for the custom domain
        sed "${SED_INPLACE[@]}" "s/CORS_ALLOWED_ORIGINS=\*/CORS_ALLOWED_ORIGINS=$protocol:\/\/$domain/" .env
        sed "${SED_INPLACE[@]}" "s/ALLOW_CORS_WILDCARD=true/ALLOW_CORS_WILDCARD=false/" .env
        echo "✅ Configured for custom domain: $protocol://$domain"
        ;;
    *)
        # Simple localhost setup - no changes needed
        echo "✅ Using simple localhost configuration"
        echo "   The application will be accessible at: http://localhost"
        ;;
esac

# Port configuration
echo ""
read -p "Port for MAESTRO (default: 80): " maestro_port
maestro_port=${maestro_port:-80}
sed "${SED_INPLACE[@]}" "s/MAESTRO_PORT=80/MAESTRO_PORT=$maestro_port/" .env

# Timezone
read -p "Timezone (default: America/Chicago): " timezone
timezone=${timezone:-America/Chicago}
sed "${SED_INPLACE[@]}" "s|TZ=America/Chicago|TZ=$timezone|" .env
sed "${SED_INPLACE[@]}" "s|VITE_SERVER_TIMEZONE=America/Chicago|VITE_SERVER_TIMEZONE=$timezone|" .env

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Your .env file has been created."
echo ""
echo "Access MAESTRO at:"
if [ "$maestro_port" = "80" ]; then
    case $setup_mode in
        2) echo "  http://$ip" ;;
        3) echo "  $protocol://$domain" ;;
        *) echo "  http://localhost" ;;
    esac
else
    case $setup_mode in
        2) echo "  http://$ip:$maestro_port" ;;
        3) echo "  $protocol://$domain:$maestro_port" ;;
        *) echo "  http://localhost:$maestro_port" ;;
    esac
fi
echo ""
echo "Default login:"
echo "  Username: admin"
echo "  Password: adminpass123"
echo ""
echo "Start MAESTRO with:"
echo "  docker compose up -d"
echo ""
echo "To modify settings later:"
echo "  nano .env"
