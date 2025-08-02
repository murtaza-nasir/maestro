@echo off
setlocal enabledelayedexpansion

REM MAESTRO - Environment Setup Script for Windows
REM This script helps you set up your .env file for the first time

echo # MAESTRO - Environment Setup
echo ==================================

REM Check if .env already exists
if exist ".env" (
    echo ⚠️  .env file already exists!
    set /p "overwrite=Do you want to overwrite it? (y/N): "
    if /i not "!overwrite!"=="y" (
        echo Setup cancelled.
        exit /b 0
    )
)

REM Copy env.example to .env
if not exist "env.example" (
    echo ❌ env.example file not found!
    echo Please make sure you're in the correct directory.
    exit /b 1
)

copy env.example .env >nul
echo ✅ Created .env from .env.example

REM Prompt for basic configuration
echo.
echo 📝 Basic Configuration Setup
echo You can modify these values later in the .env file
echo.

REM Backend host
set /p "backend_host=Backend host (default: 127.0.0.1): "
if "!backend_host!"=="" set "backend_host=127.0.0.1"
powershell -Command "(Get-Content .env) -replace 'BACKEND_HOST=127.0.0.1', 'BACKEND_HOST=!backend_host!' | Set-Content .env"

REM Frontend host
set /p "frontend_host=Frontend host (default: 127.0.0.1): "
if "!frontend_host!"=="" set "frontend_host=127.0.0.1"
powershell -Command "(Get-Content .env) -replace 'FRONTEND_HOST=127.0.0.1', 'FRONTEND_HOST=!frontend_host!' | Set-Content .env"

REM Protocol selection
echo.
echo Select protocol:
echo 1) HTTP/WS (development)
echo 2) HTTPS/WSS (production)
set /p "protocol_choice=Choice (1-2, default: 1): "
if "!protocol_choice!"=="" set "protocol_choice=1"

if "!protocol_choice!"=="2" (
    powershell -Command "(Get-Content .env) -replace 'API_PROTOCOL=http', 'API_PROTOCOL=https' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace 'WS_PROTOCOL=ws', 'WS_PROTOCOL=wss' | Set-Content .env"
    echo ✅ Set to HTTPS/WSS for production
) else (
    echo ✅ Set to HTTP/WS for development
)

REM Timezone
set /p "timezone=Timezone (default: America/Chicago): "
if "!timezone!"=="" set "timezone=America/Chicago"
powershell -Command "(Get-Content .env) -replace 'TZ=America/Chicago', 'TZ=!timezone!' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'VITE_SERVER_TIMEZONE=America/Chicago', 'VITE_SERVER_TIMEZONE=!timezone!' | Set-Content .env"

echo.
echo 🎉 Setup complete!
echo.
echo Your .env file has been created with the following configuration:
echo   Backend: !backend_host!
echo   Frontend: !frontend_host!
if "!protocol_choice!"=="2" (
    echo   Protocol: HTTPS/WSS
) else (
    echo   Protocol: HTTP/WS
)
echo   Timezone: !timezone!
echo.
echo You can now start MAESTRO with:
echo   docker compose up -d
echo.
echo To modify additional settings, edit the .env file:
echo   notepad .env 