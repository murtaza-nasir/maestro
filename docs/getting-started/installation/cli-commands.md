# CLI Commands Reference

MAESTRO provides powerful command-line tools for bulk document processing, user management, and system administration. The CLI features direct processing with real-time progress feedback.

## Overview

The MAESTRO CLI offers:

- **Direct Processing** - Documents processed immediately with live feedback
- **Real-time Progress** - See each step with timestamps
- **Multi-format Support** - PDF, Word, Markdown files
- **GPU Control** - Specify which GPU device to use
- **Bulk Operations** - Process entire directories
- **User Management** - Create and manage users
- **Document Organization** - Create and manage document groups

## Getting Started

### Platform-Specific Usage

#### Linux/macOS
```bash
# Make executable (first time only)
chmod +x maestro-cli.sh

# Show help
./maestro-cli.sh help
```

#### Windows PowerShell
```powershell
# Show help
.\maestro-cli.ps1 help
```

#### Windows Command Prompt
```cmd
REM Show help
maestro-cli.bat help
```

#### Direct Docker Execution
```bash
# Run CLI commands directly
docker exec maestro-backend python cli.py --help
```

## User Management Commands

### create-user

Create a new user account.

**Syntax:**
```bash
./maestro-cli.sh create-user <username> <password> [options]
```

**Options:**

- `--full-name "Name"` - Set user's full name
- `--admin` - Create admin user

**Examples:**
```bash
# Create regular user
./maestro-cli.sh create-user researcher pass123 --full-name "Research User"

# Create admin user
./maestro-cli.sh create-user admin adminpass --admin --full-name "Administrator"
```

## Document Group Management

### create-group

Create a document group for organization.

**Syntax:**
```bash
./maestro-cli.sh create-group <username> <group_name> [options]
```

**Options:**
- `--description "Text"` - Add group description

**Example:**
```bash
./maestro-cli.sh create-group researcher "AI Papers" \
  --description "Machine Learning Research Papers"
```

### list-groups

List document groups.

```bash
# List all groups
./maestro-cli.sh list-groups

# List groups for specific user
./maestro-cli.sh list-groups --user researcher
```

**Output:**
```
Group ID: abc123-def456
Name: AI Papers
Owner: researcher
Documents: 42
Description: Machine Learning Research Papers
```

**Note:** Document groups can be created and listed via CLI. Documents can be added to groups during ingestion with the `--group` flag. For other group management operations, use the web interface.

## Document Processing Commands

### ingest

Process documents with live feedback. Primary command for adding documents.

**Syntax:**
```bash
./maestro-cli.sh ingest <username> <directory> [options]
```

**Options:**

- `--group <group_id>` - Add to specific group
- `--force-reembed` - Force re-processing (default behavior skips already processed files)
- `--device <device>` - GPU device (cuda:0, cpu)
- `--delete-after-success` - Remove source files after processing
- `--batch-size <num>` - Parallel processing count

**Supported Formats:**

- PDF files (`.pdf`)
- Word documents (`.docx`, `.doc`)
- Markdown files (`.md`, `.markdown`)

### Mounting Directories for Batch Document Processing

The CLI service needs access to your documents. By default, only `./pdfs` is mounted. To process documents from other directories, you need to mount them in docker-compose.yml:

Edit the `cli` service in docker-compose.yml:

```yaml
cli:
  # ... existing configuration ...
  volumes:
    # ... existing volumes ...
    - ./pdfs:/app/pdfs  # Default PDF directory
    - ./documents:/app/documents  # Add your custom document directory
    - ./research-papers:/app/research-papers  # Another example
```

Then use the mounted path:
```bash
./maestro-cli.sh ingest researcher /app/documents
./maestro-cli.sh ingest researcher /app/research-papers
```

### Batch Document Processing Examples

**Examples:**
```bash
# Basic document ingestion from default directory
./maestro-cli.sh ingest researcher ./pdfs

# Process documents from custom mounted directory
./maestro-cli.sh ingest researcher ./documents

# Add to group with GPU selection
./maestro-cli.sh ingest researcher ./research-papers \
  --group abc123 --device cuda:0

# Process and cleanup temporary files
./maestro-cli.sh ingest researcher ./temp-docs \
  --delete-after-success

# Force re-processing of updated documents
./maestro-cli.sh ingest researcher ./updated-docs \
  --force-reembed

# Process with custom batch size for large collections
./maestro-cli.sh ingest researcher ./large-collection \
  --batch-size 10
# Make sure you have enough VRAM; adjust to lower batch size if you see out of memory errors
```

**Progress Output:**
```
Processing: paper1.pdf
[12:34:56] Converting to markdown...
[12:35:02] Extracting metadata...
[12:35:05] Generating embeddings...
[12:35:12] ✓ Successfully processed: paper1.pdf

Processing: paper2.pdf
[12:35:13] Converting to markdown...
```

## Search Commands

### search

Search documents using semantic search.

```bash
./maestro-cli.sh search <username> "search query" [options]
```

**Options:**

- `--limit <num>` - Result count (default: 10)
- `--group <group_id>` - Search within group
- `--threshold <float>` - Similarity threshold (0-1)

**Examples:**
```bash
# Basic search
./maestro-cli.sh search admin "quantum computing applications"

# Search with options
./maestro-cli.sh search researcher "machine learning" \
  --limit 20 \
  --group abc123 \
  --threshold 0.7
```

**Note:** Metadata search is available through the web interface. The CLI `search` command provides semantic search capabilities.

## System Management Commands

### status

Check document processing status (not system status).

```bash
# Check status for a user
./maestro-cli.sh status --user researcher

# Check status for a group
./maestro-cli.sh status --group <group_id>
```

**Note:** For system-wide statistics, use `reset-db --stats` command.

### cleanup

Clean up documents with specific status.

```bash
# Clean up failed documents
./maestro-cli.sh cleanup --user researcher --status failed

# Clean up for specific group
./maestro-cli.sh cleanup --group <group_id>

# Skip confirmation
./maestro-cli.sh cleanup --confirm
```

### cleanup-cli

Clean up documents stuck in CLI processing.

```bash
# Dry run to see what would be deleted
./maestro-cli.sh cleanup-cli --dry-run

# Force cleanup without confirmation
./maestro-cli.sh cleanup-cli --force
```

### reset-db

Database reset operations.

```bash
# Check database status
./maestro-cli.sh reset-db --stats

# Check consistency
./maestro-cli.sh reset-db --check

# Reset with backup
./maestro-cli.sh reset-db --backup

# Force reset (skip confirmation)
./maestro-cli.sh reset-db --force
```

**Note:** Backup and restore operations are handled through `reset-db --backup` or manual database operations. See the [Database Reset Guide](database-reset.md) for details.

## Performance Tips

### GPU Utilization

```bash
# Check available GPUs
nvidia-smi

# Use specific GPU
./maestro-cli.sh ingest researcher ./docs --device cuda:0

# Use multiple GPUs (process in parallel)
./maestro-cli.sh ingest researcher ./docs1 --device cuda:0 &
./maestro-cli.sh ingest researcher ./docs2 --device cuda:1 &
wait
```

### Batch Size Optimization

```bash
# Small files, increase batch size
./maestro-cli.sh ingest researcher ./small-docs --batch-size 10

# Large files, decrease batch size
./maestro-cli.sh ingest researcher ./large-pdfs --batch-size 2
```

### Memory Management

```bash
# Limit memory usage
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
./maestro-cli.sh ingest researcher ./documents
```

## Troubleshooting

### Common Issues

**Permission Denied:**
```bash
# Fix permissions
chmod +x maestro-cli.sh
```

**Docker Not Running:**
```bash
# Start Docker services
docker compose up -d
```

**GPU Not Available:**
```bash
# Force CPU mode
./maestro-cli.sh ingest researcher ./docs --device cpu
```

**Out of Memory:**
```bash
# Reduce batch size
./maestro-cli.sh ingest researcher ./docs --batch-size 1
```

### Log Files

Check logs for errors:

```bash
# View backend logs
docker compose logs maestro-backend --tail=100
```

## Next Steps

- [Database Management](database-reset.md) - Database operations
- [User Guide](../../user-guide/index.md) - Using the web interface
- [Troubleshooting](../../troubleshooting/index.md) - Common issues
- [API Reference](#) - REST API documentation