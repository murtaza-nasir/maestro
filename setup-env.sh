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

# Database Security Configuration
echo ""
echo "🔐 Database Security Setup"
echo "Choose how to set database passwords:"
echo "1) Generate secure random passwords (recommended)"
echo "2) Enter custom passwords"
echo "3) Skip (use default - NOT RECOMMENDED for production)"
read -p "Choice (1-3, default: 1): " pass_mode
pass_mode=${pass_mode:-1}

case $pass_mode in
    1)
        # Generate secure random passwords
        if command -v openssl &> /dev/null; then
            postgres_pass=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
            admin_pass=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-16)
            jwt_secret=$(openssl rand -hex 32)
        else
            # Fallback to /dev/urandom if openssl not available
            postgres_pass=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 25)
            admin_pass=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
            jwt_secret=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 64)
        fi
        
        sed "${SED_INPLACE[@]}" "s/POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD_IMMEDIATELY/POSTGRES_PASSWORD=$postgres_pass/" .env
        sed "${SED_INPLACE[@]}" "s/ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD/ADMIN_PASSWORD=$admin_pass/" .env
        sed "${SED_INPLACE[@]}" "s/JWT_SECRET_KEY=GENERATE_A_RANDOM_KEY_DO_NOT_USE_DEFAULT/JWT_SECRET_KEY=$jwt_secret/" .env
        
        echo "✅ Generated secure passwords"
        echo ""
        echo "⚠️  SAVE THESE CREDENTIALS:"
        echo "   Admin Username: admin"
        echo "   Admin Password: $admin_pass"
        echo ""
        echo "   Database credentials are stored in .env"
        ;;
    2)
        # Custom passwords
        read -sp "Enter PostgreSQL password: " postgres_pass
        echo
        read -sp "Confirm PostgreSQL password: " postgres_pass_confirm
        echo
        if [ "$postgres_pass" != "$postgres_pass_confirm" ]; then
            echo "❌ Passwords don't match. Using defaults."
        else
            sed "${SED_INPLACE[@]}" "s/POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD_IMMEDIATELY/POSTGRES_PASSWORD=$postgres_pass/" .env
        fi
        
        read -sp "Enter Admin password: " admin_pass
        echo
        read -sp "Confirm Admin password: " admin_pass_confirm
        echo
        if [ "$admin_pass" != "$admin_pass_confirm" ]; then
            echo "❌ Passwords don't match. Using defaults."
        else
            sed "${SED_INPLACE[@]}" "s/ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD/ADMIN_PASSWORD=$admin_pass/" .env
        fi
        
        # Generate JWT secret
        if command -v openssl &> /dev/null; then
            jwt_secret=$(openssl rand -hex 32)
        else
            jwt_secret=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 64)
        fi
        sed "${SED_INPLACE[@]}" "s/JWT_SECRET_KEY=GENERATE_A_RANDOM_KEY_DO_NOT_USE_DEFAULT/JWT_SECRET_KEY=$jwt_secret/" .env
        
        echo "✅ Custom passwords set"
        ;;
    *)
        echo "⚠️  WARNING: Using default passwords is insecure!"
        echo "   Please change them in .env before deploying to production"
        admin_pass="admin123"  # Keep for display later
        ;;
esac

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
if [ "$pass_mode" != "3" ]; then
    echo "Login credentials:"
    echo "  Username: admin"
    if [ -n "$admin_pass" ]; then
        echo "  Password: [Set during setup - check above or .env file]"
    fi
else
    echo "Default login (CHANGE IMMEDIATELY):"
    echo "  Username: admin"
    echo "  Password: admin123"
fi
echo ""
echo "Start MAESTRO with:"
echo "  docker compose up -d"
echo ""
echo "⚠️  IMPORTANT - First Run:"
echo "  Initial startup takes 5-10 minutes to download AI models"
echo "  Monitor progress with: docker compose logs -f maestro-backend"
echo "  Wait for message: MAESTRO Backend Started Successfully!"
echo ""
echo "To modify settings later:"
echo "  nano .env"
