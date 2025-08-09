# Database Management and Reset Guide for Maestro

## Overview

This guide covers database management tools for the Maestro application, including full database resets and document consistency management across the dual-database architecture.

## ⚠️ CRITICAL: Data Synchronization

**All databases MUST be reset together!** The Maestro system uses three tightly-coupled storage systems:

1. **Main Database** (`maestro_backend/data/maestro.db`) - User accounts, chats, document records
2. **AI Database** (`ai_researcher/data/processed/metadata.db`) - Extracted document metadata  
3. **Vector Store** (`ai_researcher/data/vector_store/`) - Document embeddings and chunks

**Why Reset All Together?**
- Document IDs must match across all databases
- Orphaned data causes search failures and UI inconsistencies  
- Partial resets can corrupt the document processing pipeline

## Usage (Recommended - Using Maestro CLI)

The easiest way is to use the extended Maestro CLI:

### 1. Check Current Database Status
```bash
./maestro-cli.sh reset-db --stats
```

### 2. Check Data Consistency
```bash
./maestro-cli.sh reset-db --check
```

### 3. Reset All Databases (with backup)
```bash
./maestro-cli.sh reset-db --backup
```

### 4. Force Reset (skip confirmation)
```bash
./maestro-cli.sh reset-db --force
```

### 5. Get Help
```bash
./maestro-cli.sh reset-db --help
```

## Document Consistency Management Tools

In addition to full database resets, MAESTRO includes dedicated tools for maintaining document consistency across the dual-database architecture.

### CLI Document Consistency Tool

For granular document management, use the CLI consistency tool:

#### Individual Document Operations
```bash
# Check specific document consistency across all systems
python maestro_backend/cli_document_consistency.py check-document <doc_id> <user_id>

# Clean up specific orphaned document
python maestro_backend/cli_document_consistency.py cleanup-document <doc_id> <user_id>
```

#### User-Level Operations
```bash
# Check all documents for a specific user
python maestro_backend/cli_document_consistency.py check-user <user_id>

# Clean up all orphaned documents for a user
python maestro_backend/cli_document_consistency.py cleanup-user <user_id>
```

#### System-Wide Operations
```bash
# Get overall system consistency status
python maestro_backend/cli_document_consistency.py system-status

# Perform system-wide cleanup of orphaned documents
python maestro_backend/cli_document_consistency.py cleanup-all
```

### Automatic Consistency Monitoring

MAESTRO includes built-in monitoring that runs automatically:

- **Frequency**: Every 60 minutes (configurable)
- **Scope**: All users and document types
- **Actions**: Automatic orphan cleanup and old failed document cleanup
- **Logging**: Comprehensive logging of issues found and resolved

### When to Use These Tools

- **Database Reset**: Complete fresh start, removes ALL data
- **Consistency Tools**: Targeted cleanup, preserves valid data
- **Automatic Monitoring**: Ongoing maintenance, prevents issues

Choose consistency tools when you want to:
- Fix specific document issues without losing other data
- Clean up orphaned files from failed processing
- Verify system integrity without full reset
- Perform maintenance without downtime

## Manual Usage (Docker Commands)

If you prefer manual control:

### 1. Start Backend Container
```bash
docker compose up -d backend
```

### 2. Copy Reset Script
```bash
docker cp reset_databases.py maestro-backend:/app/
```

### 3. Run Reset Inside Container
```bash
# Check stats
docker exec -it maestro-backend python reset_databases.py --stats

# Check consistency  
docker exec -it maestro-backend python reset_databases.py --check

# Reset with backup
docker exec -it maestro-backend python reset_databases.py --backup

# Force reset
docker exec -it maestro-backend python reset_databases.py --force
```

### 4. Cleanup
```bash
docker exec maestro-backend rm /app/reset_databases.py
```

## What Gets Reset

### 1. Main Database
- All user accounts (except recreated via migrations)
- Chat sessions and messages
- Document records and processing jobs
- Writing sessions and drafts
- **Action**: Database file deleted and recreated with fresh schema

### 2. AI Researcher Database  
- Document metadata (title, authors, year, journal, etc.)
- Processing timestamps
- **Action**: Database file deleted (recreated when first document processed)

### 3. Vector Store (ChromaDB)
- Dense embeddings (BGE-M3, 1024 dimensions)
- Sparse embeddings (30,000 dimensions)  
- Document chunks with metadata
- **Action**: Entire directory deleted (recreated when first document processed)

### 4. Document Files
- Original PDFs (`ai_researcher/data/raw_pdfs/`)
- Converted Markdown (`ai_researcher/data/processed/markdown/`)
- Extracted metadata JSON (`ai_researcher/data/processed/metadata/`)
- **Action**: Directory contents cleared

## After Reset

### 1. Restart Docker Containers (Recommended)
```bash
docker compose down
docker compose up -d
```

### 2. Re-create User Accounts
```bash
./maestro-cli.sh create-user researcher password123 --full-name "Research User"
```

### 3. Re-upload Documents
```bash
./maestro-cli.sh ingest researcher ./pdfs
```

### 4. Verify Everything Works
```bash
./maestro-cli.sh reset-db --stats
./maestro-cli.sh reset-db --check
```

## Backup and Recovery

### Automatic Backups
Using `--backup` flag creates timestamped backups in `./backups/`:
- `maestro.db.20240808_143022.backup`
- `metadata.db.20240808_143022.backup`
- `vector_store_20240808_143022_backup/`

### Manual Backup (Before Reset)
```bash
# Backup main database
docker exec maestro-backend cp /app/data/maestro.db /app/maestro_backup.db

# Copy backups out of container
docker cp maestro-backend:/app/maestro_backup.db ./maestro_backup.db
```

### Recovery from Backup
```bash
# Stop containers
docker compose down

# Restore main database
docker cp ./maestro_backup.db maestro-backend:/app/data/maestro.db

# Start containers
docker compose up -d
```

## Troubleshooting

### Container Not Running
```bash
# Start backend
docker compose up -d backend

# Check status
docker compose ps
```

### Permission Errors
```bash
# Check Docker permissions
docker info

# Run with sudo if needed
sudo ./maestro-cli.sh reset-db --stats
```

### Data Inconsistencies Detected
If `--check` shows inconsistencies, this indicates:
- Previous incomplete document processing
- Manual database modifications
- System crashes during processing

**Solution**: Run full reset to restore consistency:
```bash
./maestro-cli.sh reset-db --backup
```

### Reset Failures
If reset fails partway through:
1. Check Docker container logs: `docker compose logs backend`
2. Manually complete the reset: `docker compose down && docker volume rm maestro_maestro-data`
3. Restart fresh: `docker compose up -d`

## Best Practices

### Development
- Reset databases frequently during development
- Always use `--backup` flag for safety
- Check consistency after major changes

### Production  
- **NEVER** run reset in production without full backups
- Test restoration procedures before production deployment
- Schedule regular consistency checks

### Debugging
1. Always run `--check` first to identify issues
2. Use `--stats` to understand current state
3. Enable logging: `docker compose logs -f backend`

## File Locations Reference

### Inside Docker Container
```
/app/
├── data/maestro.db                     # Main database
└── ai_researcher/data/
    ├── vector_store/                   # ChromaDB collections
    ├── raw_pdfs/                       # Original PDFs
    ├── processed/
    │   ├── markdown/                   # Converted documents
    │   ├── metadata/                   # Extracted metadata JSON
    │   └── metadata.db                 # AI researcher database
```

### Host System (Mounted)
```
maestro/
├── maestro_backend/data/maestro.db     # Main database (bind mount)
└── (maestro-data volume)/              # AI researcher data (Docker volume)
```

## Related Documentation

- [Database Architecture](docs/DATABASE_ARCHITECTURE.md) - Complete system architecture
- [CLAUDE.md](CLAUDE.md) - AI assistant reference
- [Database README](maestro_backend/database/README.md) - Database module guide