#!/usr/bin/env pwsh

# Windows/WSL Line Ending Fix Test Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MAESTRO Windows/WSL Fix Testing Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check current state
Write-Host "Step 1: Checking current file line endings..." -ForegroundColor Yellow
Write-Host "-----------------------------------------------" -ForegroundColor Gray

$testFile = "maestro_backend/start.sh"

if (Test-Path $testFile) {
    $content = Get-Content $testFile -Raw
    if ($content -match "`r`n") {
        Write-Host "❌ CRLF (Windows) line endings detected in $testFile" -ForegroundColor Red
        Write-Host "   This will cause 'bad interpreter' errors!" -ForegroundColor Red
        $needsFix = $true
    } elseif ($content -match "`n") {
        Write-Host "✅ LF (Unix) line endings detected in $testFile" -ForegroundColor Green
        $needsFix = $false
    } else {
        Write-Host "⚠️  Could not determine line endings" -ForegroundColor Yellow
        $needsFix = $true
    }
} else {
    Write-Host "❌ File $testFile not found!" -ForegroundColor Red
    Write-Host "   Make sure you're in the maestro directory" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Step 2: Check Docker status
Write-Host "Step 2: Checking Docker status..." -ForegroundColor Yellow
Write-Host "-----------------------------------------------" -ForegroundColor Gray

try {
    $dockerVersion = docker --version 2>$null
    if ($dockerVersion) {
        Write-Host "✅ Docker is installed: $dockerVersion" -ForegroundColor Green
        
        # Check if Docker is running
        $dockerPs = docker ps 2>$null
        if ($?) {
            Write-Host "✅ Docker daemon is running" -ForegroundColor Green
        } else {
            Write-Host "❌ Docker daemon is not running!" -ForegroundColor Red
            Write-Host "   Please start Docker Desktop" -ForegroundColor Yellow
            exit 1
        }
    }
} catch {
    Write-Host "❌ Docker is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 3: Check if containers are running
Write-Host "Step 3: Checking existing containers..." -ForegroundColor Yellow
Write-Host "-----------------------------------------------" -ForegroundColor Gray

$backendRunning = docker ps --format "table {{.Names}}" | Select-String "maestro-backend"
if ($backendRunning) {
    Write-Host "⚠️  maestro-backend container is running" -ForegroundColor Yellow
    Write-Host "   Will need to rebuild to apply fixes" -ForegroundColor Yellow
} else {
    Write-Host "✅ maestro-backend container is not running" -ForegroundColor Green
}

Write-Host ""

# Step 4: Apply fix if needed
if ($needsFix) {
    Write-Host "Step 4: Applying line ending fix..." -ForegroundColor Yellow
    Write-Host "-----------------------------------------------" -ForegroundColor Gray
    
    if (Test-Path "fix-line-endings.ps1") {
        Write-Host "Running fix-line-endings.ps1..." -ForegroundColor Cyan
        & .\fix-line-endings.ps1
        
        # Verify fix was applied
        $content = Get-Content $testFile -Raw
        if ($content -match "`r`n") {
            Write-Host "❌ Fix failed - CRLF still present!" -ForegroundColor Red
        } else {
            Write-Host "✅ Line endings fixed successfully!" -ForegroundColor Green
        }
    } else {
        Write-Host "❌ fix-line-endings.ps1 not found!" -ForegroundColor Red
        Write-Host "   Creating a quick fix..." -ForegroundColor Yellow
        
        # Quick inline fix
        $files = Get-ChildItem -Recurse -Include "*.sh","*.py","Dockerfile*" -File
        foreach ($file in $files) {
            $content = Get-Content $file.FullName -Raw
            if ($content -match "`r`n") {
                $content = $content -replace "`r`n", "`n"
                [System.IO.File]::WriteAllText($file.FullName, $content, [System.Text.UTF8Encoding]::new($false))
                Write-Host "  Fixed: $($file.Name)" -ForegroundColor Green
            }
        }
    }
} else {
    Write-Host "Step 4: No line ending fix needed" -ForegroundColor Green
    Write-Host "-----------------------------------------------" -ForegroundColor Gray
}

Write-Host ""

# Step 5: Rebuild instructions
Write-Host "Step 5: Next steps to complete the fix..." -ForegroundColor Yellow
Write-Host "-----------------------------------------------" -ForegroundColor Gray
Write-Host ""
Write-Host "Run these commands in order:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Stop existing containers:" -ForegroundColor White
Write-Host "   docker compose down" -ForegroundColor Green
Write-Host ""
Write-Host "2. Rebuild backend without cache:" -ForegroundColor White
Write-Host "   docker compose build --no-cache maestro-backend" -ForegroundColor Green
Write-Host ""
Write-Host "3. Start all services:" -ForegroundColor White
Write-Host "   docker compose up -d" -ForegroundColor Green
Write-Host ""
Write-Host "4. Check if backend started successfully:" -ForegroundColor White
Write-Host "   docker compose logs maestro-backend" -ForegroundColor Green
Write-Host ""
Write-Host "You should see:" -ForegroundColor Yellow
Write-Host "  🚀 Starting MAESTRO Backend..." -ForegroundColor Gray
Write-Host "  ✅ PostgreSQL is ready!" -ForegroundColor Gray
Write-Host "  🌐 Starting FastAPI server..." -ForegroundColor Gray
Write-Host ""
Write-Host "If you see 'bad interpreter' errors, run this test script again." -ForegroundColor Yellow