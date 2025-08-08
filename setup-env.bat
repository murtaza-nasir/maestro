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
echo.
echo Select your timezone:
echo 1) America/New_York (Eastern Time)
echo 2) America/Chicago (Central Time)
echo 3) America/Denver (Mountain Time)
echo 4) America/Los_Angeles (Pacific Time)
echo 5) Asia/Kolkata (India Standard Time)
echo 6) Europe/London (GMT/BST)
echo 7) Europe/Paris (CET/CEST)
echo 8) Asia/Tokyo (JST)
echo 9) Australia/Sydney (AEST/AEDT)
echo 10) Other (enter custom timezone)
echo 0) Use system default
set /p "timezone_choice=Choice (0-10, default: 2): "
if "!timezone_choice!"=="" set "timezone_choice=2"

if "!timezone_choice!"=="1" set "timezone=America/New_York"
if "!timezone_choice!"=="2" set "timezone=America/Chicago"
if "!timezone_choice!"=="3" set "timezone=America/Denver"
if "!timezone_choice!"=="4" set "timezone=America/Los_Angeles"
if "!timezone_choice!"=="5" set "timezone=Asia/Kolkata"
if "!timezone_choice!"=="6" set "timezone=Europe/London"
if "!timezone_choice!"=="7" set "timezone=Europe/Paris"
if "!timezone_choice!"=="8" set "timezone=Asia/Tokyo"
if "!timezone_choice!"=="9" set "timezone=Australia/Sydney"
if "!timezone_choice!"=="10" (
    echo.
    echo Common timezone formats:
    echo   - America/New_York
    echo   - Asia/Kolkata
    echo   - Europe/London
    echo   - Asia/Tokyo
    echo   - UTC
    echo   - GMT
    set /p "timezone=Enter your timezone: "
    if "!timezone!"=="" set "timezone=America/Chicago"
)
if "!timezone_choice!"=="0" (
    for /f "tokens=*" %%i in ('powershell -Command "[System.TimeZoneInfo]::Local.Id" 2^>nul') do set "timezone=%%i"
    if "!timezone!"=="" set "timezone=America/Chicago"
    echo ✅ Using system timezone: !timezone!
)

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