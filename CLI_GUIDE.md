# MAESTRO Command Line Interface (CLI) Guide

The MAESTRO CLI provides powerful command-line tools for bulk document processing, user management, and system administration. The CLI features **direct processing** with real-time progress feedback, bypassing the background queue system for immediate results.

## Quick Start

MAESTRO provides convenient wrapper scripts for different platforms:

### Linux/macOS
```bash
# Make the script executable (first time only)
chmod +x maestro-cli.sh

# Show available commands
./maestro-cli.sh help

# Example: Create a user and ingest documents
./maestro-cli.sh create-user researcher mypass123
./maestro-cli.sh ingest researcher ./documents
```

### Windows PowerShell
```powershell
# Show available commands
.\maestro-cli.ps1 help

# Example: Create a user and ingest documents
.\maestro-cli.ps1 create-user researcher mypass123
.\maestro-cli.ps1 ingest researcher .\documents
```

### Windows Command Prompt
```cmd
REM Show available commands
maestro-cli.bat help

REM Example: Create a user and ingest documents
maestro-cli.bat create-user researcher mypass123
maestro-cli.bat ingest researcher .\documents
```

## Key Features

- **Direct Processing**: Documents are processed immediately with live feedback
- **Real-time Progress**: See each processing step with timestamps
- **No Queue**: Bypasses the background processor for immediate results
- **Multi-format Support**: Handles PDF, Word (docx, doc), and Markdown (md, markdown) files
- **GPU Control**: Specify which GPU device to use for processing
- **Flexible Organization**: Documents added to user library, can be organized into groups
- **Auto-cleanup**: Option to delete source files after successful processing

## Available Commands

### User Management

#### create-user
Create a new user account.

```bash
./maestro-cli.sh create-user <username> <password> [options]
```

**Options:**
- `--full-name "Name"`: Set the user's full name
- `--admin`: Create an admin user

**Examples:**
```bash
# Create a regular user
./maestro-cli.sh create-user researcher mypass123 --full-name "Research User"

# Create an admin user
./maestro-cli.sh create-user admin adminpass --admin --full-name "Administrator"
```

#### list-users
List all users in the system (admin only).

```bash
./maestro-cli.sh list-users
```

### Document Group Management

#### create-group
Create a document group for organizing documents.

```bash
./maestro-cli.sh create-group <username> <group_name> [options]
```

**Options:**
- `--description "Description"`: Add a description for the group

**Example:**
```bash
./maestro-cli.sh create-group researcher "AI Papers" --description "Machine Learning Research"
```

#### list-groups
List document groups.

```bash
./maestro-cli.sh list-groups [options]
```

**Options:**
- `--user <username>`: List groups for a specific user only

**Examples:**
```bash
# List all groups (admin view)
./maestro-cli.sh list-groups

# List groups for a specific user
./maestro-cli.sh list-groups --user researcher
```

### Document Processing

#### ingest
Process documents directly with live feedback. This is the primary command for adding documents to MAESTRO.

```bash
./maestro-cli.sh ingest <username> <document_directory> [options]
```

**Options:**
- `--group <group_id>`: Add documents to a specific group
- `--force-reembed`: Force re-processing of existing documents
- `--device <device>`: Specify GPU device (e.g., cuda:0, cuda:1, cpu)
- `--delete-after-success`: Delete source files after successful processing
- `--batch-size <num>`: Control parallel processing (default: 5)

**Supported File Types:**
- PDF files (`.pdf`)
- Word documents (`.docx`, `.doc`)
- Markdown files (`.md`, `.markdown`)

**Examples:**
```bash
# Basic ingestion (documents added to user library)
./maestro-cli.sh ingest researcher ./documents

# Add to specific group
./maestro-cli.sh ingest researcher ./documents --group abc123-def456

# Process with specific GPU
./maestro-cli.sh ingest researcher ./documents --device cuda:0

# Force re-processing and delete after success
./maestro-cli.sh ingest researcher ./documents --force-reembed --delete-after-success

# Process with larger batch size for faster processing
./maestro-cli.sh ingest researcher ./documents --batch-size 10
```

**Processing Workflow:**
1. Validates document directory and counts supported files
2. Converts documents to Markdown format
3. Extracts metadata (title, authors, year, journal)
4. Chunks documents into overlapping paragraphs
5. Generates embeddings using BGE-M3 model
6. Stores in ChromaDB vector store and metadata database
7. Shows real-time progress with timestamps for each step

#### status
Check document processing status.

```bash
./maestro-cli.sh status [options]
```

**Options:**
- `--user <username>`: Check status for specific user
- `--group <group_id>`: Check status for specific group

**Examples:**
```bash
# Check all documents (admin view)
./maestro-cli.sh status

# Check status for specific user
./maestro-cli.sh status --user researcher

# Check status for specific group
./maestro-cli.sh status --user researcher --group abc123-def456
```

#### cleanup
Clean up documents with specific status (e.g., failed or error documents).

```bash
./maestro-cli.sh cleanup [options]
```

**Options:**
- `--user <username>`: Clean up for specific user
- `--status <status>`: Target specific status (failed, error, etc.)
- `--group <group_id>`: Clean up in specific group
- `--confirm`: Skip confirmation prompt

**Examples:**
```bash
# Clean up all failed documents
./maestro-cli.sh cleanup --status failed --confirm

# Clean up for specific user
./maestro-cli.sh cleanup --user researcher --status error
```

### Document Search

#### search
Search through documents for a specific user.

```bash
./maestro-cli.sh search <username> <query> [options]
```

**Options:**
- `--limit <num>`: Limit number of results (default: 10)

**Example:**
```bash
./maestro-cli.sh search researcher "machine learning" --limit 5
```

### Database Management

#### reset-db
Reset all databases and document files. **CRITICAL**: All databases must be reset together to maintain data consistency.

```bash
./maestro-cli.sh reset-db [options]
```

**Options:**
- `--backup`: Create timestamped backups before reset
- `--force`: Skip confirmation prompts (DANGEROUS!)
- `--stats`: Show database statistics only (don't reset)
- `--check`: Check data consistency across databases only

**What Gets Reset:**
- Main application database (users, chats, documents)
- AI researcher database (extracted metadata)
- ChromaDB vector store (embeddings and chunks)
- All document files (PDFs, markdown, metadata)

**Examples:**
```bash
# Show current database statistics
./maestro-cli.sh reset-db --stats

# Check data consistency
./maestro-cli.sh reset-db --check

# Reset with backup
./maestro-cli.sh reset-db --backup

# Force reset without confirmation (DANGEROUS!)
./maestro-cli.sh reset-db --force
```

## Direct Docker Commands

For advanced users, you can also run CLI commands directly with Docker Compose:

```bash
# General format
docker compose --profile cli run --rm cli python cli_ingest.py [command] [options]

# Examples
docker compose --profile cli run --rm cli python cli_ingest.py create-user myuser mypass
docker compose --profile cli run --rm cli python cli_ingest.py list-groups
docker compose --profile cli run --rm cli python cli_ingest.py ingest myuser GROUP_ID /app/pdfs
```

## Directory Structure

When using the CLI, documents should be placed in the appropriate directories:

```
maestro/
├── documents/       # Recommended directory for all document types
├── pdfs/           # Legacy directory (still supported)
└── ...
```

The CLI scripts automatically map your local directories to the container paths:
- `./documents` → `/app/documents`
- `./pdfs` → `/app/pdfs`

## Tips and Best Practices

1. **Document Organization**: Create groups before ingesting documents for better organization
2. **Batch Processing**: Use `--batch-size` to control memory usage and processing speed
3. **GPU Selection**: Use `--device` to specify GPU for multi-GPU systems
4. **Error Recovery**: Use `cleanup` command to remove failed documents before re-processing
5. **Regular Backups**: Use `reset-db --backup` before major operations

## Troubleshooting

### Common Issues

**Docker not running:**
```bash
# Start Docker services
docker compose up -d backend
```

**Permission denied:**
```bash
# Make script executable
chmod +x maestro-cli.sh
```

**Out of memory:**
```bash
# Reduce batch size
./maestro-cli.sh ingest user ./docs --batch-size 2
```

**GPU not available:**
```bash
# Use CPU processing
./maestro-cli.sh ingest user ./docs --device cpu
```

### Getting Help

For detailed help on any command:
```bash
./maestro-cli.sh help
./maestro-cli.sh <command> --help
```

## Performance Considerations

- **Batch Size**: Higher batch sizes process faster but use more memory
- **GPU vs CPU**: GPU processing is 10-20x faster for embeddings
- **Document Size**: Large PDFs may take several minutes to process
- **Network**: First run downloads models (~2GB), subsequent runs use cache