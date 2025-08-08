@echo off
setlocal enabledelayedexpansion

REM MAESTRO Direct CLI Helper Script for Windows
REM This script provides direct document processing with live feedback

REM Colors for output (Windows 10+ supports ANSI colors)
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

REM Function to print colored output
:print_info
echo %BLUE%[INFO]%NC% %~1
goto :eof

:print_success
echo %GREEN%[SUCCESS]%NC% %~1
goto :eof

:print_warning
echo %YELLOW%[WARNING]%NC% %~1
goto :eof

:print_error
echo %RED%[ERROR]%NC% %~1
goto :eof

REM Function to check if Docker Compose is available
:check_docker_compose
docker --version >nul 2>&1
if errorlevel 1 (
    call :print_error "Docker is not installed or not in PATH"
    exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
    call :print_error "Docker Compose is not available"
    exit /b 1
)
goto :eof

REM Function to ensure backend is running
:ensure_backend_running
call :print_info "Checking if backend is running..."
docker compose ps backend | findstr "Up" >nul
if errorlevel 1 (
    call :print_info "Starting backend service..."
    docker compose up -d backend
    timeout /t 5 /nobreak >nul
)
goto :eof

REM Function to run direct CLI command
:run_direct_cli
call :check_docker_compose
call :ensure_backend_running
docker compose --profile cli run --rm cli python cli_ingest.py %*
goto :eof

REM Help function
:show_help
echo MAESTRO Direct CLI Helper Script for Windows
echo.
echo This tool provides DIRECT document processing with live feedback, bypassing the background queue.
echo Documents are processed synchronously with real-time progress updates.
echo.
echo Usage: %0 ^<command^> [options]
echo.
echo Commands:
echo   create-user ^<username^> ^<password^> [--full-name "Name"] [--admin]
echo     Create a new user account
echo.
echo   create-group ^<username^> ^<group_name^> [--description "Description"]
echo     Create a document group for a user
echo.
echo   list-groups [--user ^<username^>]
echo     List document groups
echo.
echo   ingest ^<username^> ^<pdf_directory^> [--group ^<group_id^>] [--force-reembed] [--device ^<device^>] [--delete-after-success] [--batch-size ^<num^>]
echo     DIRECTLY process PDF documents with live feedback
echo     - Shows real-time progress for each document
echo     - Processes documents synchronously ^(no background queue^)
echo     - Documents are immediately available after processing
echo     - Documents added to user library ^(can be organized into groups later^)
echo     - Optionally delete PDF files after successful processing
echo     - Control parallel processing with --batch-size ^(default: 5^)
echo.
echo   status [--user ^<username^>] [--group ^<group_id^>]
echo     Check document processing status
echo.
echo   cleanup [--user ^<username^>] [--status ^<status^>] [--group ^<group_id^>] [--confirm]
echo     Clean up documents with specific status ^(e.g., failed, error documents^)
echo     - Remove failed or error documents from the database
echo     - Optionally filter by user and/or group
echo     - Use --confirm to skip confirmation prompt
echo.
echo   search ^<username^> ^<query^> [--limit ^<num^>]
echo     Search through documents for a specific user
echo.
echo   help
echo     Show this help message
echo.
echo Key Differences from Regular CLI:
echo   - DIRECT PROCESSING: Documents are processed immediately with live feedback
echo   - REAL-TIME PROGRESS: See each step of processing as it happens
echo   - NO QUEUE: Bypasses the background processor for immediate results
echo   - LIVE FEEDBACK: Timestamps, progress indicators, and detailed status updates
echo.
echo Examples:
echo   # Create a user and group
echo   %0 create-user researcher mypass123 --full-name "Research User"
echo   %0 create-group researcher "AI Papers" --description "Machine Learning Research"
echo.
echo   # Direct document processing with live feedback ^(no group^)
echo   %0 ingest researcher ./pdfs
echo.
echo   # Process with specific group
echo   %0 ingest researcher ./pdfs --group GROUP_ID
echo.
echo   # Process with specific GPU device
echo   %0 ingest researcher ./pdfs --device cuda:0
echo.
echo   # Force re-processing of existing documents
echo   %0 ingest researcher ./pdfs --force-reembed
echo.
echo   # Check status
echo   %0 status --user researcher
echo.
echo For more detailed help on any command:
echo   %0 ^<command^> --help
goto :eof

REM Main script logic
if "%1"=="" (
    call :show_help
    exit /b 0
)

if "%1"=="help" (
    call :show_help
    goto :eof
)
if "%1"=="--help" (
    call :show_help
    goto :eof
)
if "%1"=="-h" (
    call :show_help
    goto :eof
)

if "%1"=="create-user" (
    shift
    if "%1"=="" (
        call :print_error "create-user requires username and password"
        echo Usage: %0 create-user ^<username^> ^<password^> [--full-name "Name"] [--admin]
        exit /b 1
    )
    if "%2"=="" (
        call :print_error "create-user requires username and password"
        echo Usage: %0 create-user ^<username^> ^<password^> [--full-name "Name"] [--admin]
        exit /b 1
    )
    call :print_info "Creating user '%1'..."
    call :run_direct_cli create-user %*
    call :print_success "User creation command completed"
    goto :eof
)

if "%1"=="create-group" (
    shift
    if "%1"=="" (
        call :print_error "create-group requires username and group name"
        echo Usage: %0 create-group ^<username^> ^<group_name^> [--description "Description"]
        exit /b 1
    )
    if "%2"=="" (
        call :print_error "create-group requires username and group name"
        echo Usage: %0 create-group ^<username^> ^<group_name^> [--description "Description"]
        exit /b 1
    )
    call :print_info "Creating group '%2' for user '%1'..."
    call :run_direct_cli create-group %*
    call :print_success "Group creation command completed"
    goto :eof
)

if "%1"=="list-groups" (
    shift
    call :print_info "Listing document groups..."
    call :run_direct_cli list-groups %*
    goto :eof
)

if "%1"=="ingest" (
    shift
    REM Check for help flag
    if "%1"=="--help" (
        call :run_direct_cli ingest --help
        exit /b 0
    )
    if "%1"=="-h" (
        call :run_direct_cli ingest --help
        exit /b 0
    )
    
    if "%1"=="" (
        call :print_error "ingest requires username and pdf_directory"
        echo Usage: %0 ingest ^<username^> ^<pdf_directory^> [--group ^<group_id^>] [--force-reembed] [--device ^<device^>] [--delete-after-success] [--batch-size ^<num^>]
        exit /b 1
    )
    if "%2"=="" (
        call :print_error "ingest requires username and pdf_directory"
        echo Usage: %0 ingest ^<username^> ^<pdf_directory^> [--group ^<group_id^>] [--force-reembed] [--device ^<device^>] [--delete-after-success] [--batch-size ^<num^>]
        exit /b 1
    )
    
    REM Check if PDF directory exists and has PDFs
    set "pdf_dir=%2"
    if not exist "%pdf_dir%" (
        call :print_error "PDF directory '%pdf_dir%' does not exist"
        exit /b 1
    )
    
    REM Count PDF files (simplified for Windows)
    set "pdf_count=0"
    for %%f in ("%pdf_dir%\*.pdf") do set /a pdf_count+=1
    
    if %pdf_count%==0 (
        call :print_warning "No PDF files found in '%pdf_dir%'"
        set /p "continue=Continue anyway? (y/N): "
        if /i not "!continue!"=="y" (
            exit /b 0
        )
    ) else (
        call :print_info "Found %pdf_count% PDF files in '%pdf_dir%'"
    )
    
    call :print_info "Starting DIRECT document processing for user '%1'..."
    call :print_warning "This will process documents immediately with live feedback"
    
    REM Convert local path to container path
    set "container_path=/app/pdfs"
    if "%pdf_dir%"=="./pdfs" (
        set "container_path=/app/pdfs"
    ) else if "%pdf_dir%"=="pdfs" (
        set "container_path=/app/pdfs"
    ) else if "%pdf_dir:~0,1%"=="\" (
        call :print_warning "Using absolute path '%pdf_dir%' - make sure it's mounted in the container"
        set "container_path=%pdf_dir%"
    ) else (
        call :print_warning "Converting relative path '%pdf_dir%' to '/app/pdfs'"
        set "container_path=/app/pdfs"
    )
    
    REM Replace the local path with container path for the CLI command
    call :run_direct_cli ingest %1 "%container_path%" %3 %4 %5 %6 %7 %8 %9
    call :print_success "Direct document processing completed"
    call :print_info "All documents are now immediately available for search."
    goto :eof
)

if "%1"=="status" (
    shift
    call :print_info "Checking document processing status..."
    call :run_direct_cli status %*
    goto :eof
)

if "%1"=="cleanup" (
    shift
    call :print_info "Starting document cleanup..."
    call :run_direct_cli cleanup %*
    call :print_success "Cleanup command completed"
    goto :eof
)

if "%1"=="search" (
    shift
    if "%1"=="" (
        call :print_error "search requires username and query"
        echo Usage: %0 search ^<username^> ^<query^> [--limit ^<num^>]
        exit /b 1
    )
    if "%2"=="" (
        call :print_error "search requires username and query"
        echo Usage: %0 search ^<username^> ^<query^> [--limit ^<num^>]
        exit /b 1
    )
    call :print_info "Searching documents for user '%1'..."
    call :run_direct_cli search %*
    goto :eof
)

call :print_error "Unknown command: %1"
echo Use '%0 help' to see available commands
exit /b 1 