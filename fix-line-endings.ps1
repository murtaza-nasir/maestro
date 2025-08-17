#!/usr/bin/env pwsh

# Fix line endings for Windows/WSL users
Write-Host "Fixing line endings for Windows/WSL compatibility..." -ForegroundColor Yellow

# Check if Git Bash is available
$gitBashPath = @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe",
    "$env:PROGRAMFILES\Git\bin\bash.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($gitBashPath) {
    Write-Host "Using Git Bash to fix line endings..." -ForegroundColor Green
    & $gitBashPath -c "find . -type f \( -name '*.sh' -o -name '*.py' -o -name 'Dockerfile*' \) -exec sed -i 's/\r$//' {} \;"
    Write-Host "✅ Line endings fixed!" -ForegroundColor Green
} else {
    # Fallback: Use PowerShell to fix line endings
    Write-Host "Git Bash not found. Using PowerShell to fix line endings..." -ForegroundColor Yellow
    
    $files = Get-ChildItem -Recurse -Include "*.sh","*.py","Dockerfile*" -File
    
    foreach ($file in $files) {
        $content = Get-Content $file.FullName -Raw
        if ($content -match "`r`n") {
            $content = $content -replace "`r`n", "`n"
            [System.IO.File]::WriteAllText($file.FullName, $content, [System.Text.UTF8Encoding]::new($false))
            Write-Host "  Fixed: $($file.Name)"
        }
    }
    Write-Host "✅ Line endings fixed!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Now rebuild and restart Docker:" -ForegroundColor Cyan
Write-Host "  docker compose down" -ForegroundColor White
Write-Host "  docker compose build --no-cache maestro-backend" -ForegroundColor White
Write-Host "  docker compose up -d" -ForegroundColor White