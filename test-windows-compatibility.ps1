#!/usr/bin/env pwsh

# MAESTRO Windows Compatibility Test Script
# This script checks if your Windows system is ready to run MAESTRO

Write-Host "🔍 MAESTRO Windows Compatibility Test" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

$allTestsPassed = $true

# Test 1: PowerShell Version
Write-Host "1. Checking PowerShell Version..." -ForegroundColor Yellow
$psVersion = $PSVersionTable.PSVersion
Write-Host "   PowerShell Version: $psVersion" -ForegroundColor Gray

if ($psVersion.Major -ge 5) {
    Write-Host "   ✅ PowerShell version is compatible" -ForegroundColor Green
} else {
    Write-Host "   ❌ PowerShell version is too old. Please upgrade to PowerShell 5.1 or later." -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 2: Docker Installation
Write-Host ""
Write-Host "2. Checking Docker Installation..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version 2>$null
    if ($dockerVersion) {
        Write-Host "   ✅ Docker is installed: $dockerVersion" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Docker is not installed or not in PATH" -ForegroundColor Red
        $allTestsPassed = $false
    }
} catch {
    Write-Host "   ❌ Docker is not installed or not in PATH" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 3: Docker Compose
Write-Host ""
Write-Host "3. Checking Docker Compose..." -ForegroundColor Yellow
try {
    $composeVersion = docker compose version 2>$null
    if ($composeVersion) {
        Write-Host "   ✅ Docker Compose is available: $composeVersion" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Docker Compose is not available" -ForegroundColor Red
        $allTestsPassed = $false
    }
} catch {
    Write-Host "   ❌ Docker Compose is not available" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 4: Docker Desktop Running
Write-Host ""
Write-Host "4. Checking Docker Desktop Status..." -ForegroundColor Yellow
try {
    $dockerInfo = docker info 2>$null
    if ($dockerInfo) {
        Write-Host "   ✅ Docker Desktop is running" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Docker Desktop is not running" -ForegroundColor Red
        Write-Host "   💡 Please start Docker Desktop" -ForegroundColor Yellow
        $allTestsPassed = $false
    }
} catch {
    Write-Host "   ❌ Docker Desktop is not running" -ForegroundColor Red
    Write-Host "   💡 Please start Docker Desktop" -ForegroundColor Yellow
    $allTestsPassed = $false
}

# Test 5: Git Installation
Write-Host ""
Write-Host "5. Checking Git Installation..." -ForegroundColor Yellow
try {
    $gitVersion = git --version 2>$null
    if ($gitVersion) {
        Write-Host "   ✅ Git is installed: $gitVersion" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Git is not installed or not in PATH" -ForegroundColor Red
        $allTestsPassed = $false
    }
} catch {
    Write-Host "   ❌ Git is not installed or not in PATH" -ForegroundColor Red
    $allTestsPassed = $false
}

# Test 6: Execution Policy
Write-Host ""
Write-Host "6. Checking PowerShell Execution Policy..." -ForegroundColor Yellow
$executionPolicy = Get-ExecutionPolicy
Write-Host "   Current Execution Policy: $executionPolicy" -ForegroundColor Gray

if ($executionPolicy -eq "Unrestricted" -or $executionPolicy -eq "RemoteSigned" -or $executionPolicy -eq "Bypass") {
    Write-Host "   ✅ Execution policy allows script execution" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Execution policy may block script execution" -ForegroundColor Yellow
    Write-Host "   💡 Run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Yellow
}

# Test 7: Required Files
Write-Host ""
Write-Host "7. Checking Required Files..." -ForegroundColor Yellow
$requiredFiles = @(
    "env.example",
    "setup-env.ps1",
    "setup-env.bat",
    "maestro-cli.ps1",
    "maestro-cli.bat",
    "docker-compose.yml"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "   ✅ $file exists" -ForegroundColor Green
    } else {
        Write-Host "   ❌ $file is missing" -ForegroundColor Red
        $allTestsPassed = $false
    }
}

# Test 8: Port Availability
Write-Host ""
Write-Host "8. Checking Port Availability..." -ForegroundColor Yellow
$ports = @(8000, 3000)

foreach ($port in $ports) {
    $portInUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-Host "   ⚠️  Port $port is already in use" -ForegroundColor Yellow
        Write-Host "   💡 You may need to change ports in .env file" -ForegroundColor Yellow
    } else {
        Write-Host "   ✅ Port $port is available" -ForegroundColor Green
    }
}

# Test 9: GPU Support (Optional)
Write-Host ""
Write-Host "9. Checking GPU Support..." -ForegroundColor Yellow
try {
    $nvidiaSmi = nvidia-smi 2>$null
    if ($nvidiaSmi) {
        Write-Host "   ✅ NVIDIA GPU detected" -ForegroundColor Green
        Write-Host "   💡 GPU acceleration is available" -ForegroundColor Cyan
    } else {
        Write-Host "   ℹ️  No NVIDIA GPU detected" -ForegroundColor Gray
        Write-Host "   💡 MAESTRO will run on CPU (slower but functional)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ℹ️  No NVIDIA GPU detected" -ForegroundColor Gray
    Write-Host "   💡 MAESTRO will run on CPU (slower but functional)" -ForegroundColor Gray
}

# Summary
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
if ($allTestsPassed) {
    Write-Host "🎉 All compatibility tests passed!" -ForegroundColor Green
    Write-Host "Your system is ready to run MAESTRO." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Run: .\setup-env.ps1" -ForegroundColor White
    Write-Host "2. Run: docker compose up -d" -ForegroundColor White
    Write-Host "3. Access MAESTRO at http://localhost:3000" -ForegroundColor White
} else {
    Write-Host "❌ Some compatibility tests failed." -ForegroundColor Red
    Write-Host "Please address the issues above before proceeding." -ForegroundColor Red
    Write-Host ""
    Write-Host "For help, see WINDOWS_SETUP.md" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "For detailed setup instructions, see WINDOWS_SETUP.md" -ForegroundColor Gray 