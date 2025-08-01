#!/bin/bash

# MAESTRO Direct CLI Helper Script
# This script provides direct document processing with live feedback

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Docker Compose is available
check_docker_compose() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not available"
        exit 1
    fi
}

# Function to ensure backend is running
ensure_backend_running() {
    print_info "Checking if backend is running..."
    if ! docker compose ps backend | grep -q "Up"; then
        print_info "Starting backend service..."
        docker compose up -d backend
        sleep 5
    fi
}

# Function to run direct CLI command
run_direct_cli() {
    check_docker_compose
    ensure_backend_running
    docker compose --profile cli run --rm cli python cli_ingest.py "$@"
}

# Help function
show_help() {
    cat << EOF
MAESTRO Direct CLI Helper Script

This tool provides DIRECT document processing with live feedback, bypassing the background queue.
Documents are processed synchronously with real-time progress updates.

Usage: $0 <command> [options]

Commands:
  create-user <username> <password> [--full-name "Name"] [--admin]
    Create a new user account

  create-group <username> <group_name> [--description "Description"]
    Create a document group for a user

  list-groups [--user <username>]
    List document groups

  ingest <username> <pdf_directory> [--group <group_id>] [--force-reembed] [--device <device>] [--delete-after-success] [--batch-size <num>]
    DIRECTLY process PDF documents with live feedback
    - Shows real-time progress for each document
    - Processes documents synchronously (no background queue)
    - Documents are immediately available after processing
    - Documents added to user library (can be organized into groups later)
    - Optionally delete PDF files after successful processing
    - Control parallel processing with --batch-size (default: 5)

  status [--user <username>] [--group <group_id>]
    Check document processing status

  cleanup [--user <username>] [--status <status>] [--group <group_id>] [--confirm]
    Clean up documents with specific status (e.g., failed, error documents)
    - Remove failed or error documents from the database
    - Optionally filter by user and/or group
    - Use --confirm to skip confirmation prompt

  search <username> <query> [--limit <num>]
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
  $0 create-user researcher mypass123 --full-name "Research User"
  $0 create-group researcher "AI Papers" --description "Machine Learning Research"

  # Direct document processing with live feedback (no group)
  $0 ingest researcher ./pdfs

  # Process with specific group
  $0 ingest researcher ./pdfs --group GROUP_ID

  # Process with specific GPU device
  $0 ingest researcher ./pdfs --device cuda:0

  # Force re-processing of existing documents
  $0 ingest researcher ./pdfs --force-reembed

  # Check status
  $0 status --user researcher

For more detailed help on any command:
  $0 <command> --help

EOF
}

# Main script logic
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

case "$1" in
    "help"|"--help"|"-h")
        show_help
        ;;
    "create-user")
        shift
        if [ $# -lt 2 ]; then
            print_error "create-user requires username and password"
            echo "Usage: $0 create-user <username> <password> [--full-name \"Name\"] [--admin]"
            exit 1
        fi
        print_info "Creating user '$1'..."
        run_direct_cli create-user "$@"
        print_success "User creation command completed"
        ;;
    "create-group")
        shift
        if [ $# -lt 2 ]; then
            print_error "create-group requires username and group name"
            echo "Usage: $0 create-group <username> <group_name> [--description \"Description\"]"
            exit 1
        fi
        print_info "Creating group '$2' for user '$1'..."
        run_direct_cli create-group "$@"
        print_success "Group creation command completed"
        ;;
    "list-groups")
        shift
        print_info "Listing document groups..."
        run_direct_cli list-groups "$@"
        ;;
    "ingest")
        shift
        # Check for help flag
        if [[ "$1" == "--help" || "$1" == "-h" ]]; then
            run_direct_cli ingest --help
            exit 0
        fi
        
        if [ $# -lt 2 ]; then
            print_error "ingest requires username and pdf_directory"
            echo "Usage: $0 ingest <username> <pdf_directory> [--group <group_id>] [--force-reembed] [--device <device>] [--delete-after-success] [--batch-size <num>]"
            exit 1
        fi
        
        # Check if PDF directory exists and has PDFs
        pdf_dir="$2"
        if [ ! -d "$pdf_dir" ]; then
            print_error "PDF directory '$pdf_dir' does not exist"
            exit 1
        fi
        
        pdf_count=$(find "$pdf_dir" -name "*.pdf" | wc -l)
        if [ "$pdf_count" -eq 0 ]; then
            print_warning "No PDF files found in '$pdf_dir'"
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 0
            fi
        else
            print_info "Found $pdf_count PDF files in '$pdf_dir'"
        fi
        
        print_info "Starting DIRECT document processing for user '$1'..."
        print_warning "This will process documents immediately with live feedback"
        
        # Convert local path to container path
        container_path="/app/pdfs"
        if [[ "$pdf_dir" == "./pdfs" || "$pdf_dir" == "pdfs" ]]; then
            container_path="/app/pdfs"
        elif [[ "$pdf_dir" == /* ]]; then
            print_warning "Using absolute path '$pdf_dir' - make sure it's mounted in the container"
            container_path="$pdf_dir"
        else
            print_warning "Converting relative path '$pdf_dir' to '/app/pdfs'"
            container_path="/app/pdfs"
        fi
        
        # Replace the local path with container path for the CLI command
        args=("ingest" "$1" "$container_path")
        shift 2
        args+=("$@")
        
        run_direct_cli "${args[@]}"
        print_success "Direct document processing completed"
        print_info "All documents are now immediately available for search."
        ;;
    "status")
        shift
        print_info "Checking document processing status..."
        run_direct_cli status "$@"
        ;;
    "cleanup")
        shift
        print_info "Starting document cleanup..."
        run_direct_cli cleanup "$@"
        print_success "Cleanup command completed"
        ;;
    "search")
        shift
        if [ $# -lt 2 ]; then
            print_error "search requires username and query"
            echo "Usage: $0 search <username> <query> [--limit <num>]"
            exit 1
        fi
        print_info "Searching documents for user '$1'..."
        run_direct_cli search "$@"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' to see available commands"
        exit 1
        ;;
esac
