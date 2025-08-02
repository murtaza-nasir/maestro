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
$timezone = Read-Host "Timezone (default: America/Chicago)"
if (-not $timezone) { $timezone = "America/Chicago" }
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