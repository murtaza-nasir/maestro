#!/usr/bin/env pwsh

# MAESTRO - Environment Setup Script for Windows PowerShell
# This script helps you set up your .env file for the first time

Write-Host "# MAESTRO - Environment Setup"
Write-Host "=================================="

# Check if .env already exists
if (Test-Path ".env") {
    Write-Host "WARNING: .env file already exists!" -ForegroundColor Yellow
    $overwrite = Read-Host "Do you want to overwrite it? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Host "Setup cancelled."
        exit 0
    }
}

# Copy .env.example to .env
if (-not (Test-Path ".env.example")) {
    Write-Host "ERROR: .env.example file not found!" -ForegroundColor Red
    Write-Host "Please make sure you're in the correct directory."
    exit 1
}

Copy-Item ".env.example" ".env"
Write-Host "SUCCESS: Created .env from .env.example" -ForegroundColor Green

# Simplified configuration
Write-Host ""
Write-Host "MAESTRO Configuration" -ForegroundColor Cyan
Write-Host ""

# Setup mode selection
Write-Host "Choose setup mode:"
Write-Host "1) Simple (localhost only) - Recommended"
Write-Host "2) Network (access from other devices)"
Write-Host "3) Custom domain (for reverse proxy)"
$setupMode = Read-Host "Choice (1-3, default is 1)"
if (-not $setupMode) { $setupMode = "1" }

switch ($setupMode) {
    "2" {
        # Network setup - try to detect IP
        $ip = (Get-NetIPAddress | Where-Object {$_.AddressFamily -eq "IPv4" -and $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*"}).IPAddress | Select-Object -First 1
        
        if ($ip) {
            Write-Host "Auto-detected IP: $ip"
            $useDetected = Read-Host "Use this IP? (Y/n)"
            if ($useDetected -eq "n" -or $useDetected -eq "N") {
                $ip = Read-Host "Enter IP address"
            }
        } else {
            $ip = Read-Host "Enter IP address"
        }
        
        (Get-Content .env) -replace 'CORS_ALLOWED_ORIGINS=\*', "CORS_ALLOWED_ORIGINS=http://$ip,http://localhost" | Set-Content .env
        Write-Host "SUCCESS: Configured for network access from: $ip" -ForegroundColor Green
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
        Write-Host "SUCCESS: Configured for custom domain: $protocol`://$domain" -ForegroundColor Green
    }
    default {
        Write-Host "SUCCESS: Using simple localhost configuration" -ForegroundColor Green
        Write-Host "   The application will be accessible at: http://localhost"
    }
}

# Port configuration
Write-Host ""
$maestroPort = Read-Host "Port for MAESTRO (default: 80)"
if (-not $maestroPort) { $maestroPort = "80" }
(Get-Content .env) -replace 'MAESTRO_PORT=80', "MAESTRO_PORT=$maestroPort" | Set-Content .env

# Database Security Configuration
Write-Host ""
Write-Host "Database Security Setup" -ForegroundColor Cyan
Write-Host "Choose how to set database passwords:"
Write-Host "1) Generate secure random passwords (recommended)"
Write-Host "2) Enter custom passwords"
Write-Host "3) Skip (use default - NOT RECOMMENDED for production)"
$passMode = Read-Host "Choice (1-3, default: 1)"
if (-not $passMode) { $passMode = "1" }

switch ($passMode) {
    "1" {
        # Generate secure random passwords
        $postgresPass = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 25 | ForEach-Object {[char]$_})
        $adminPass = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
        $jwtSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object {[char]$_})
        
        (Get-Content .env) -replace 'POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD_IMMEDIATELY', "POSTGRES_PASSWORD=$postgresPass" | Set-Content .env
        (Get-Content .env) -replace 'ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD', "ADMIN_PASSWORD=$adminPass" | Set-Content .env
        (Get-Content .env) -replace 'JWT_SECRET_KEY=GENERATE_A_RANDOM_KEY_DO_NOT_USE_DEFAULT', "JWT_SECRET_KEY=$jwtSecret" | Set-Content .env
        
        Write-Host "SUCCESS: Generated secure passwords" -ForegroundColor Green
        Write-Host ""
        Write-Host "SAVE THESE CREDENTIALS:" -ForegroundColor Yellow
        Write-Host "   Admin Username: admin" -ForegroundColor Yellow
        Write-Host "   Admin Password: $adminPass" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   Database credentials are stored in .env" -ForegroundColor Gray
    }
    "2" {
        # Custom passwords
        $postgresPass = Read-Host "Enter PostgreSQL password" -AsSecureString
        $postgresPassConfirm = Read-Host "Confirm PostgreSQL password" -AsSecureString
        
        # Convert SecureString to plain text for comparison
        $postgresPassPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($postgresPass))
        $postgresPassConfirmPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($postgresPassConfirm))
        
        if ($postgresPassPlain -ne $postgresPassConfirmPlain) {
            Write-Host "ERROR: Passwords don't match. Using defaults." -ForegroundColor Red
        } else {
            $adminPass = Read-Host "Enter admin password" -AsSecureString
            $adminPassPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminPass))
            
            $jwtSecret = Read-Host "Enter JWT secret (press Enter to generate)"
            if (-not $jwtSecret) {
                $jwtSecret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object {[char]$_})
                Write-Host "Generated JWT secret" -ForegroundColor Green
            }
            
            (Get-Content .env) -replace 'POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD_IMMEDIATELY', "POSTGRES_PASSWORD=$postgresPassPlain" | Set-Content .env
            (Get-Content .env) -replace 'ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD', "ADMIN_PASSWORD=$adminPassPlain" | Set-Content .env
            (Get-Content .env) -replace 'JWT_SECRET_KEY=GENERATE_A_RANDOM_KEY_DO_NOT_USE_DEFAULT', "JWT_SECRET_KEY=$jwtSecret" | Set-Content .env
            
            Write-Host "SUCCESS: Custom passwords set" -ForegroundColor Green
            Write-Host ""
            Write-Host "   Admin Username: admin" -ForegroundColor Yellow
            Write-Host "   Admin Password: [your custom password]" -ForegroundColor Yellow
        }
    }
    "3" {
        Write-Host "WARNING: Using default passwords - CHANGE THESE IN PRODUCTION!" -ForegroundColor Yellow
        Write-Host "   Default admin login: admin / admin123" -ForegroundColor Yellow
    }
    default {
        Write-Host "Invalid choice. Using defaults." -ForegroundColor Red
    }
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
            Write-Host "SUCCESS: Using system timezone: $timezone" -ForegroundColor Green
        } catch {
            $timezone = "America/Chicago"
            Write-Host "WARNING: Could not detect system timezone, using default: $timezone" -ForegroundColor Yellow
        }
    }
    default { $timezone = "America/Chicago" }
}

(Get-Content .env) -replace 'TZ=America/Chicago', "TZ=$timezone" | Set-Content .env
(Get-Content .env) -replace 'VITE_SERVER_TIMEZONE=America/Chicago', "VITE_SERVER_TIMEZONE=$timezone" | Set-Content .env

Write-Host ""
Write-Host "SETUP COMPLETE!" -ForegroundColor Green
Write-Host ""
Write-Host "Your .env file has been created."
Write-Host ""

# Windows line ending warning
Write-Host "WARNING - Windows/WSL Note:" -ForegroundColor Yellow
Write-Host "   If you encounter 'bad interpreter' errors, run:" -ForegroundColor Yellow
Write-Host "   docker compose down" -ForegroundColor Cyan
Write-Host "   docker compose build --no-cache" -ForegroundColor Cyan
Write-Host "   docker compose up -d" -ForegroundColor Cyan
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
if ($passMode -eq "3") {
    Write-Host "Default login:" -ForegroundColor Cyan
    Write-Host "  Username: admin"
    Write-Host "  Password: admin123"
} else {
    Write-Host "Login credentials were displayed above" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "Start MAESTRO with:"
Write-Host "  docker compose up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT - First Run:" -ForegroundColor Yellow
Write-Host "  Initial startup takes 5-10 minutes to download AI models" -ForegroundColor Yellow
Write-Host "  Monitor progress with: docker compose logs -f maestro-backend" -ForegroundColor Yellow
Write-Host "  Wait for message: MAESTRO Backend Started Successfully!" -ForegroundColor Yellow
Write-Host ""
Write-Host "To modify settings later:"
Write-Host "  notepad .env" 