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
    $backendStatus = docker compose ps backend 2>$null | Select-String "Up"
    if (-not $backendStatus) {
        Write-Info "Starting backend service..."
        docker compose up -d backend
        Start-Sleep -Seconds 5
    }
}

# Function to run direct CLI command
function Invoke-DirectCLI {
    param([string[]]$Arguments)
    
    if (-not (Test-DockerCompose)) {
        exit 1
    }
    
    Start-BackendIfNeeded
    docker compose --profile cli run --rm cli python cli_ingest.py @Arguments
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

  ingest <username> <pdf_directory> [-Group <group_id>] [-ForceReembed] [-Device <device>] [-DeleteAfterSuccess] [-BatchSize <num>]
    DIRECTLY process PDF documents with live feedback
    - Shows real-time progress for each document
    - Processes documents synchronously (no background queue)
    - Documents are immediately available after processing
    - Documents added to user library (can be organized into groups later)
    - Optionally delete PDF files after successful processing
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
  .\maestro-cli.ps1 ingest researcher ./pdfs

  # Process with specific group
  .\maestro-cli.ps1 ingest researcher ./pdfs -Group GROUP_ID

  # Process with specific GPU device
  .\maestro-cli.ps1 ingest researcher ./pdfs -Device cuda:0

  # Force re-processing of existing documents
  .\maestro-cli.ps1 ingest researcher ./pdfs -ForceReembed

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
            Write-Error "ingest requires username and pdf_directory"
            Write-Host "Usage: .\maestro-cli.ps1 ingest <username> <pdf_directory> [-Group <group_id>] [-ForceReembed] [-Device <device>] [-DeleteAfterSuccess] [-BatchSize <num>]"
            exit 1
        }
        
        # Check if PDF directory exists and has PDFs
        if (-not (Test-Path $PdfDirectory)) {
            Write-Error "PDF directory '$PdfDirectory' does not exist"
            exit 1
        }
        
        $pdfFiles = Get-ChildItem -Path $PdfDirectory -Filter "*.pdf" -ErrorAction SilentlyContinue
        if ($pdfFiles.Count -eq 0) {
            Write-Warning "No PDF files found in '$PdfDirectory'"
            $continue = Read-Host "Continue anyway? (y/N)"
            if ($continue -ne "y" -and $continue -ne "Y") {
                exit 0
            }
        } else {
            Write-Info "Found $($pdfFiles.Count) PDF files in '$PdfDirectory'"
        }
        
        Write-Info "Starting DIRECT document processing for user '$Username'..."
        Write-Warning "This will process documents immediately with live feedback"
        
        # Convert local path to container path
        $containerPath = "/app/pdfs"
        if ($PdfDirectory -eq "./pdfs" -or $PdfDirectory -eq "pdfs") {
            $containerPath = "/app/pdfs"
        } elseif ($PdfDirectory.StartsWith("\")) {
            Write-Warning "Using absolute path '$PdfDirectory' - make sure it's mounted in the container"
            $containerPath = $PdfDirectory
        } else {
            Write-Warning "Converting relative path '$PdfDirectory' to '/app/pdfs'"
            $containerPath = "/app/pdfs"
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
    
    default {
        Write-Error "Unknown command: $Command"
        Write-Host "Use '.\maestro-cli.ps1 help' to see available commands"
        exit 1
    }
} 