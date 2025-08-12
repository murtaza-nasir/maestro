#!/usr/bin/env pwsh

# MAESTRO - Environment Setup Script for Windows PowerShell
# This script helps you set up your .env file for the first time

Write-Host "# MAESTRO - Environment Setup"
Write-Host "=================================="

# Check if .env already exists
if (Test-Path ".env") {
    Write-Host "⚠️  .env file already exists!"
    $overwrite = Read-Host "Do you want to overwrite it? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Host "Setup cancelled."
        exit 0
    }
}

# Copy .env.example to .env
if (-not (Test-Path ".env.example")) {
    Write-Host "❌ .env.example file not found!"
    Write-Host "Please make sure you're in the correct directory."
    exit 1
}

Copy-Item ".env.example" ".env"
Write-Host "✅ Created .env from .env.example"

# Simplified configuration
Write-Host ""
Write-Host "📝 MAESTRO Configuration"
Write-Host ""

# Setup mode selection
Write-Host "Choose setup mode:"
Write-Host "1) Simple (localhost only) - Recommended"
Write-Host "2) Network (access from other devices)"
Write-Host "3) Custom domain (for reverse proxy)"
$setupMode = Read-Host "Choice (1-3, default: 1)"
if (-not $setupMode) { $setupMode = "1" }

switch ($setupMode) {
    "2" {
        # Network setup - try to detect IP
        $ip = (Get-NetIPAddress | Where-Object {$_.AddressFamily -eq "IPv4" -and $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*"}).IPAddress | Select-Object -First 1
        
        if ($ip) {
            Write-Host "🔍 Auto-detected IP: $ip"
            $useDetected = Read-Host "Use this IP? (Y/n)"
            if ($useDetected -eq "n" -or $useDetected -eq "N") {
                $ip = Read-Host "Enter IP address"
            }
        } else {
            $ip = Read-Host "Enter IP address"
        }
        
        (Get-Content .env) -replace 'CORS_ALLOWED_ORIGINS=\*', "CORS_ALLOWED_ORIGINS=http://$ip,http://localhost" | Set-Content .env
        Write-Host "✅ Configured for network access from: $ip"
    }
    "3" {
        $domain = Read-Host "Enter your domain (e.g., researcher.local)"
        $useHttps = Read-Host "Using HTTPS? (y/N)"
        
        if ($useHttps -eq "y" -or $useHttps -eq "Y") {
            $protocol = "https"
        } else {
            $protocol = "http"
        }
        
        (Get-Content .env) -replace 'CORS_ALLOWED_ORIGINS=\*', "CORS_ALLOWED_ORIGINS=$protocol`://$domain" | Set-Content .env
        (Get-Content .env) -replace 'ALLOW_CORS_WILDCARD=true', 'ALLOW_CORS_WILDCARD=false' | Set-Content .env
        Write-Host "✅ Configured for custom domain: $protocol`://$domain"
    }
    default {
        Write-Host "✅ Using simple localhost configuration"
        Write-Host "   The application will be accessible at: http://localhost"
    }
}

# Port configuration
$maestroPort = Read-Host "Port for MAESTRO (default: 80)"
if (-not $maestroPort) { $maestroPort = "80" }
(Get-Content .env) -replace 'MAESTRO_PORT=80', "MAESTRO_PORT=$maestroPort" | Set-Content .env

# Timezone
Write-Host ""
Write-Host "Select your timezone:"
Write-Host "1) America/New_York (Eastern Time)"
Write-Host "2) America/Chicago (Central Time)"
Write-Host "3) America/Denver (Mountain Time)"
Write-Host "4) America/Los_Angeles (Pacific Time)"
Write-Host "5) Asia/Kolkata (India Standard Time)"
Write-Host "6) Europe/London (GMT/BST)"
Write-Host "7) Europe/Paris (CET/CEST)"
Write-Host "8) Asia/Tokyo (JST)"
Write-Host "9) Australia/Sydney (AEST/AEDT)"
Write-Host "10) Other (enter custom timezone)"
Write-Host "0) Use system default"

$timezoneChoice = Read-Host "Choice (0-10, default: 2)"

switch ($timezoneChoice) {
    "1" { $timezone = "America/New_York" }
    "2" { $timezone = "America/Chicago" }
    "3" { $timezone = "America/Denver" }
    "4" { $timezone = "America/Los_Angeles" }
    "5" { $timezone = "Asia/Kolkata" }
    "6" { $timezone = "Europe/London" }
    "7" { $timezone = "Europe/Paris" }
    "8" { $timezone = "Asia/Tokyo" }
    "9" { $timezone = "Australia/Sydney" }
    "10" { 
        Write-Host ""
        Write-Host "Common timezone formats:"
        Write-Host "  - America/New_York"
        Write-Host "  - Asia/Kolkata"
        Write-Host "  - Europe/London"
        Write-Host "  - Asia/Tokyo"
        Write-Host "  - UTC"
        Write-Host "  - GMT"
        $timezone = Read-Host "Enter your timezone"
        if (-not $timezone) { $timezone = "America/Chicago" }
    }
    "0" { 
        # Try to get system timezone
        try {
            $systemTz = [System.TimeZoneInfo]::Local.Id
            $timezone = $systemTz
            Write-Host "✅ Using system timezone: $timezone"
        } catch {
            $timezone = "America/Chicago"
            Write-Host "⚠️  Could not detect system timezone, using default: $timezone"
        }
    }
    default { $timezone = "America/Chicago" }
}

(Get-Content .env) -replace 'TZ=America/Chicago', "TZ=$timezone" | Set-Content .env
(Get-Content .env) -replace 'VITE_SERVER_TIMEZONE=America/Chicago', "VITE_SERVER_TIMEZONE=$timezone" | Set-Content .env

Write-Host ""
Write-Host "🎉 Setup complete!"
Write-Host ""
Write-Host "Your .env file has been created."
Write-Host ""
Write-Host "Access MAESTRO at:"
if ($maestroPort -eq "80") {
    switch ($setupMode) {
        "2" { Write-Host "  http://$ip" }
        "3" { Write-Host "  $protocol`://$domain" }
        default { Write-Host "  http://localhost" }
    }
} else {
    switch ($setupMode) {
        "2" { Write-Host "  http://$ip`:$maestroPort" }
        "3" { Write-Host "  $protocol`://$domain`:$maestroPort" }
        default { Write-Host "  http://localhost:$maestroPort" }
    }
}
Write-Host ""
Write-Host "Default login:"
Write-Host "  Username: admin"
Write-Host "  Password: adminpass123"
Write-Host ""
Write-Host "Start MAESTRO with:"
Write-Host "  docker compose up -d"
Write-Host ""
Write-Host "To modify settings later:"
Write-Host "  notepad .env" 