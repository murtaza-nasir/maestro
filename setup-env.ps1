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

# Copy env.example to .env
if (-not (Test-Path "env.example")) {
    Write-Host "❌ env.example file not found!"
    Write-Host "Please make sure you're in the correct directory."
    exit 1
}

Copy-Item "env.example" ".env"
Write-Host "✅ Created .env from .env.example"

# Prompt for basic configuration
Write-Host ""
Write-Host "📝 Basic Configuration Setup"
Write-Host "You can modify these values later in the .env file"
Write-Host ""

# Backend host
$backendHost = Read-Host "Backend host (default: 127.0.0.1)"
if (-not $backendHost) { $backendHost = "127.0.0.1" }
(Get-Content .env) -replace 'BACKEND_HOST=127.0.0.1', "BACKEND_HOST=$backendHost" | Set-Content .env

# Frontend host
$frontendHost = Read-Host "Frontend host (default: 127.0.0.1)"
if (-not $frontendHost) { $frontendHost = "127.0.0.1" }
(Get-Content .env) -replace 'FRONTEND_HOST=127.0.0.1', "FRONTEND_HOST=$frontendHost" | Set-Content .env

# Protocol selection
Write-Host ""
Write-Host "Select protocol:"
Write-Host "1) HTTP/WS (development)"
Write-Host "2) HTTPS/WSS (production)"
$protocolChoice = Read-Host "Choice (1-2, default: 1)"
if (-not $protocolChoice) { $protocolChoice = "1" }

if ($protocolChoice -eq "2") {
    (Get-Content .env) -replace 'API_PROTOCOL=http', 'API_PROTOCOL=https' | Set-Content .env
    (Get-Content .env) -replace 'WS_PROTOCOL=ws', 'WS_PROTOCOL=wss' | Set-Content .env
    Write-Host "✅ Set to HTTPS/WSS for production"
} else {
    Write-Host "✅ Set to HTTP/WS for development"
}

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
Write-Host "Your .env file has been created with the following configuration:"
Write-Host "  Backend: $backendHost"
Write-Host "  Frontend: $frontendHost"
if ($protocolChoice -eq "2") {
    Write-Host "  Protocol: HTTPS/WSS"
} else {
    Write-Host "  Protocol: HTTP/WS"
}
Write-Host "  Timezone: $timezone"
Write-Host ""
Write-Host "You can now start MAESTRO with:"
Write-Host "  docker compose up -d"
Write-Host ""
Write-Host "To modify additional settings, edit the .env file:"
Write-Host "  notepad .env" 