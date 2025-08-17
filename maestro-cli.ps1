#!/usr/bin/env pwsh

# MAESTRO Direct CLI Helper Script for Windows PowerShell
# This script provides direct document processing with live feedback

param(
    [Parameter(Position=0)]
    [string]$Command,
    
    [Parameter(Position=1)]
    [string]$Username,
    
    [Parameter(Position=2)]
    [string]$Password,
    
    [Parameter(Position=3)]
    [string]$GroupName,
    
    [Parameter(Position=4)]
    [string]$PdfDirectory,
    
    [Parameter(Position=5)]
    [string]$Query,
    
    [Parameter()]
    [string]$FullName,
    
    [Parameter()]
    [string]$Description,
    
    [Parameter()]
    [string]$Group,
    
    [Parameter()]
    [string]$Status,
    
    [Parameter()]
    [string]$Limit,
    
    [Parameter()]
    [string]$Device,
    
    [Parameter()]
    [int]$BatchSize,
    
    [Parameter()]
    [switch]$Admin,
    
    [Parameter()]
    [switch]$ForceReembed,
    
    [Parameter()]
    [switch]$DeleteAfterSuccess,
    
    [Parameter()]
    [switch]$Confirm,
    
    [Parameter()]
    [switch]$Backup,
    
    [Parameter()]
    [switch]$Force,
    
    [Parameter()]
    [switch]$Stats,
    
    [Parameter()]
    [switch]$Check,
    
    [Parameter()]
    [switch]$Help
)

# Colors for output
$Red = "`e[91m"
$Green = "`e[92m"
$Yellow = "`e[93m"
$Blue = "`e[94m"
$NC = "`e[0m"

# Function to print colored output
function Write-Info {
    param([string]$Message)
    Write-Host "$Blue[INFO]$NC $Message"
}

function Write-Success {
    param([string]$Message)
    Write-Host "$Green[SUCCESS]$NC $Message"
}

function Write-Warning {
    param([string]$Message)
    Write-Host "$Yellow[WARNING]$NC $Message"
}

function Write-Error {
    param([string]$Message)
    Write-Host "$Red[ERROR]$NC $Message"
}

# Function to check if Docker Compose is available
function Test-DockerCompose {
    try {
        $null = docker --version
        $null = docker compose version
        return $true
    }
    catch {
        Write-Error "Docker or Docker Compose is not installed or not in PATH"
        return $false
    }
}

# Function to ensure backend is running
function Start-BackendIfNeeded {
    Write-Info "Checking if backend is running..."
    $composeCmd = Get-ComposeCommand
    $backendStatus = Invoke-Expression "$composeCmd ps backend 2>`$null" | Select-String "Up"
    if (-not $backendStatus) {
        Write-Info "Starting backend service..."
        Invoke-Expression "$composeCmd up -d backend"
        Start-Sleep -Seconds 5
    }
}

# Function to detect which compose file to use
function Get-ComposeCommand {
    # Check if running on Windows and if CPU compose file exists
    if ((Test-Path "docker-compose.cpu.yml") -and $env:FORCE_CPU_MODE -eq "true") {
        return "docker compose -f docker-compose.cpu.yml"
    }
    # Check if user explicitly wants CPU mode
    elseif ((Test-Path ".env") -and (Get-Content ".env" | Select-String "FORCE_CPU_MODE=true")) {
        if (Test-Path "docker-compose.cpu.yml") {
            return "docker compose -f docker-compose.cpu.yml"
        }
    }
    # Default to regular compose
    return "docker compose"
}

# Function to run direct CLI command
function Invoke-DirectCLI {
    param([string[]]$Arguments)
    
    if (-not (Test-DockerCompose)) {
        exit 1
    }
    
    Start-BackendIfNeeded
    $composeCmd = Get-ComposeCommand
    $cmd = "$composeCmd --profile cli run --rm cli python cli_ingest.py"
    Invoke-Expression "$cmd $($Arguments -join ' ')"
}

# Help function
function Show-Help {
    @"
MAESTRO Direct CLI Helper Script for Windows PowerShell

This tool provides DIRECT document processing with live feedback, bypassing the background queue.
Documents are processed synchronously with real-time progress updates.

Usage: .\maestro-cli.ps1 <command> [options]

Commands:
  create-user <username> <password> [-FullName "Name"] [-Admin]
    Create a new user account

  create-group <username> <group_name> [-Description "Description"]
    Create a document group for a user

  list-groups [-Username <username>]
    List document groups

  ingest <username> <document_directory> [-Group <group_id>] [-ForceReembed] [-Device <device>] [-DeleteAfterSuccess] [-BatchSize <num>]
    DIRECTLY process documents with live feedback (PDF, Word, Markdown)
    - Supports PDF, Word (docx, doc), and Markdown (md, markdown) files
    - Shows real-time progress for each document
    - Processes documents synchronously (no background queue)
    - Documents are immediately available after processing
    - Documents added to user library (can be organized into groups later)
    - Optionally delete source files after successful processing
    - Control parallel processing with -BatchSize (default: 5)

  status [-Username <username>] [-Group <group_id>]
    Check document processing status

  cleanup [-Username <username>] [-Status <status>] [-Group <group_id>] [-Confirm]
    Clean up documents with specific status (e.g., failed, error documents)
    - Remove failed or error documents from the database
    - Optionally filter by user and/or group
    - Use -Confirm to skip confirmation prompt

  search <username> <query> [-Limit <num>]
    Search through documents for a specific user

  reset-db [-Backup] [-Force] [-Stats] [-Check]
    Reset ALL databases (main, AI, vector store) and document files
    CRITICAL: All databases must be reset together to maintain data consistency
    - -Backup: Create timestamped backups before reset
    - -Force: Skip confirmation prompts (DANGEROUS!)
    - -Stats: Show database statistics only (don't reset)
    - -Check: Check data consistency across databases only

  help
    Show this help message

Key Differences from Regular CLI:
  - DIRECT PROCESSING: Documents are processed immediately with live feedback
  - REAL-TIME PROGRESS: See each step of processing as it happens
  - NO QUEUE: Bypasses the background processor for immediate results
  - LIVE FEEDBACK: Timestamps, progress indicators, and detailed status updates

Examples:
  # Create a user and group
  .\maestro-cli.ps1 create-user researcher mypass123 -FullName "Research User"
  .\maestro-cli.ps1 create-group researcher "AI Papers" -Description "Machine Learning Research"

  # Direct document processing with live feedback (no group)
  .\maestro-cli.ps1 ingest researcher ./documents

  # Process with specific group
  .\maestro-cli.ps1 ingest researcher ./documents -Group GROUP_ID

  # Process with specific GPU device
  .\maestro-cli.ps1 ingest researcher ./documents -Device cuda:0

  # Force re-processing of existing documents
  .\maestro-cli.ps1 ingest researcher ./documents -ForceReembed

  # Check status
  .\maestro-cli.ps1 status -Username researcher

For more detailed help on any command:
  .\maestro-cli.ps1 <command> -Help
"@
}

# Main script logic
if (-not $Command -or $Help) {
    Show-Help
    exit 0
}

switch ($Command.ToLower()) {
    "create-user" {
        if (-not $Username -or -not $Password) {
            Write-Error "create-user requires username and password"
            Write-Host "Usage: .\maestro-cli.ps1 create-user <username> <password> [-FullName `"Name`"] [-Admin]"
            exit 1
        }
        
        Write-Info "Creating user '$Username'..."
        $args = @("create-user", $Username, $Password)
        if ($FullName) { $args += "--full-name", $FullName }
        if ($Admin) { $args += "--admin" }
        
        Invoke-DirectCLI $args
        Write-Success "User creation command completed"
    }
    
    "create-group" {
        if (-not $Username -or -not $GroupName) {
            Write-Error "create-group requires username and group name"
            Write-Host "Usage: .\maestro-cli.ps1 create-group <username> <group_name> [-Description `"Description`"]"
            exit 1
        }
        
        Write-Info "Creating group '$GroupName' for user '$Username'..."
        $args = @("create-group", $Username, $GroupName)
        if ($Description) { $args += "--description", $Description }
        
        Invoke-DirectCLI $args
        Write-Success "Group creation command completed"
    }
    
    "list-groups" {
        Write-Info "Listing document groups..."
        $args = @("list-groups")
        if ($Username) { $args += "--user", $Username }
        
        Invoke-DirectCLI $args
    }
    
    "ingest" {
        if (-not $Username -or -not $PdfDirectory) {
            Write-Error "ingest requires username and document_directory"
            Write-Host "Usage: .\maestro-cli.ps1 ingest <username> <document_directory> [-Group <group_id>] [-ForceReembed] [-Device <device>] [-DeleteAfterSuccess] [-BatchSize <num>]"
            exit 1
        }
        
        # Check if document directory exists
        if (-not (Test-Path $PdfDirectory)) {
            Write-Error "Document directory '$PdfDirectory' does not exist"
            exit 1
        }
        
        # Count supported document types
        $pdfFiles = Get-ChildItem -Path $PdfDirectory -Filter "*.pdf" -ErrorAction SilentlyContinue
        $docxFiles = Get-ChildItem -Path $PdfDirectory -Include "*.docx", "*.doc" -Recurse -ErrorAction SilentlyContinue
        $mdFiles = Get-ChildItem -Path $PdfDirectory -Include "*.md", "*.markdown" -Recurse -ErrorAction SilentlyContinue
        $totalFiles = $pdfFiles.Count + $docxFiles.Count + $mdFiles.Count
        
        if ($totalFiles -eq 0) {
            Write-Warning "No supported document files found in '$PdfDirectory'"
            Write-Info "Supported formats: PDF, DOCX, DOC, MD, MARKDOWN"
            $continue = Read-Host "Continue anyway? (y/N)"
            if ($continue -ne "y" -and $continue -ne "Y") {
                exit 0
            }
        } else {
            Write-Info "Found $totalFiles supported document files in '$PdfDirectory':"
            if ($pdfFiles.Count -gt 0) {
                Write-Info "  - $($pdfFiles.Count) PDF files"
            }
            if ($docxFiles.Count -gt 0) {
                Write-Info "  - $($docxFiles.Count) Word documents"
            }
            if ($mdFiles.Count -gt 0) {
                Write-Info "  - $($mdFiles.Count) Markdown files"
            }
        }
        
        Write-Info "Starting DIRECT document processing for user '$Username'..."
        Write-Warning "This will process documents immediately with live feedback"
        
        # Convert local path to container path
        $containerPath = "/app/documents"
        if ($PdfDirectory -eq "./documents" -or $PdfDirectory -eq "documents") {
            $containerPath = "/app/documents"
        } elseif ($PdfDirectory -eq "./pdfs" -or $PdfDirectory -eq "pdfs") {
            # Backwards compatibility - still support ./pdfs
            $containerPath = "/app/pdfs"
        } elseif ($PdfDirectory.StartsWith("\") -or $PdfDirectory.StartsWith("/")) {
            Write-Warning "Using absolute path '$PdfDirectory' - make sure it's mounted in the container"
            $containerPath = $PdfDirectory
        } else {
            Write-Warning "Converting relative path '$PdfDirectory' to '/app/documents'"
            $containerPath = "/app/documents"
        }
        
        # Build arguments
        $args = @("ingest", $Username, $containerPath)
        if ($Group) { $args += "--group", $Group }
        if ($ForceReembed) { $args += "--force-reembed" }
        if ($Device) { $args += "--device", $Device }
        if ($DeleteAfterSuccess) { $args += "--delete-after-success" }
        if ($BatchSize) { $args += "--batch-size", $BatchSize }
        
        Invoke-DirectCLI $args
        Write-Success "Direct document processing completed"
        Write-Info "All documents are now immediately available for search."
    }
    
    "status" {
        Write-Info "Checking document processing status..."
        $args = @("status")
        if ($Username) { $args += "--user", $Username }
        if ($Group) { $args += "--group", $Group }
        
        Invoke-DirectCLI $args
    }
    
    "cleanup" {
        Write-Info "Starting document cleanup..."
        $args = @("cleanup")
        if ($Username) { $args += "--user", $Username }
        if ($Status) { $args += "--status", $Status }
        if ($Group) { $args += "--group", $Group }
        if ($Confirm) { $args += "--confirm" }
        
        Invoke-DirectCLI $args
        Write-Success "Cleanup command completed"
    }
    
    "search" {
        if (-not $Username -or -not $Query) {
            Write-Error "search requires username and query"
            Write-Host "Usage: .\maestro-cli.ps1 search <username> <query> [-Limit <num>]"
            exit 1
        }
        
        Write-Info "Searching documents for user '$Username'..."
        $args = @("search", $Username, $Query)
        if ($Limit) { $args += "--limit", $Limit }
        
        Invoke-DirectCLI $args
    }
    
    "reset-db" {
        Write-Warning "Database reset operates on ALL databases simultaneously!"
        Write-Info "This ensures data consistency across all storage systems."
        
        # Copy the reset script to the container
        Write-Info "Copying reset script to Docker container..."
        $copyResult = docker cp reset_databases.py maestro-backend:/app/reset_databases.py 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to copy reset script to container. Is maestro-backend running?"
            Write-Info "Try starting the backend first: docker compose up -d backend"
            exit 1
        }
        
        # Build the command based on arguments
        $cmd = "python /app/reset_databases.py"
        if ($Backup) { $cmd += " --backup" }
        if ($Force) { $cmd += " --force" }
        if ($Stats) { $cmd += " --stats" }
        if ($Check) { $cmd += " --check" }
        
        # Execute the reset script inside the container
        Write-Info "Executing database operations inside Docker container..."
        
        # Check if container is running
        $containerRunning = docker ps --format '{{.Names}}' | Select-String "maestro-backend"
        if ($containerRunning) {
            # Container is running, use exec
            docker exec -it maestro-backend $cmd
        } else {
            # Container exists but not running, use run
            Write-Warning "Backend container is not running. Starting temporary container..."
            $composeCmd = Get-ComposeCommand
            docker run --rm -it `
                -v maestro-data:/app/ai_researcher/data `
                -v "./maestro_backend/data:/app/data" `
                -w /app `
                maestro-backend `
                $cmd
        }
        
        # Clean up - remove the script from container if it's running
        if ($containerRunning) {
            docker exec maestro-backend rm -f /app/reset_databases.py 2>$null
        }
        
        if (-not $Stats -and -not $Check) {
            Write-Success "Database reset completed successfully!"
            Write-Info "Recommendation: Restart Docker containers for clean state:"
            Write-Info "  docker compose down && docker compose up -d"
        }
    }
    
    default {
        Write-Error "Unknown command: $Command"
        Write-Host "Use '.\maestro-cli.ps1 help' to see available commands"
        exit 1
    }
} 