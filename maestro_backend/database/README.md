# Database Module

This module manages the main application database for the Maestro system.

## Overview

The application uses a **dual-database architecture**:

1. **Main Database** (this module) - `data/maestro.db`
   - User management and authentication
   - Document records and processing status
   - Chat sessions and messages
   - Writing sessions and drafts
   - Application settings

2. **AI Researcher Database** - `ai_researcher/data/processed/metadata.db`
   - Extracted document metadata
   - Optimized for search and filtering
   - Managed by `ai_researcher/core_rag/database.py`

3. **Vector Store** - ChromaDB
   - Document embeddings and chunks
   - Semantic search capabilities

## Database Schema

### Core Tables

- `users` - User accounts and settings
- `documents` - Document records and processing status
- `document_groups` - Collections of related documents
- `chats` - Chat sessions (research or writing)
- `messages` - Chat messages with sources
- `missions` - AI agent tasks
- `mission_execution_logs` - Detailed agent execution logs
- `writing_sessions` - Writing mode sessions
- `drafts` - Document drafts with versioning
- `draft_references` - Citations and references

### Key Relationships

```
User ─1:N→ Documents ←N:M→ DocumentGroups
     ─1:N→ Chats ─1:N→ Messages
                 ─1:N→ Missions ─1:N→ ExecutionLogs
```

## Quick Start

### Running Migrations

Migrations are automatically run on application startup, but you can run them manually:

```bash
cd maestro_backend
python database/migrations/run_migrations.py
```

### Accessing the Database

```bash
# View all tables
sqlite3 data/maestro.db ".tables"

# Check document status
sqlite3 data/maestro.db "SELECT id, processing_status FROM documents;"

# View user count
sqlite3 data/maestro.db "SELECT COUNT(*) FROM users;"
```

### Common Operations

#### Get Database Session
```python
from database.database import get_db

# In FastAPI endpoint
def endpoint(db: Session = Depends(get_db)):
    # Use db session
    pass
```

#### CRUD Operations
```python
from database import crud
from sqlalchemy.orm import Session

# Get user
user = crud.get_user(db, user_id=1)

# Create document group
group = crud.create_document_group(
    db, 
    name="Research Papers",
    user_id=1
)

# Add document to group
crud.add_document_to_group(
    db,
    group_id=group.id,
    doc_id="abc123",
    user_id=1
)
```

## Migrations

### Creating a New Migration

1. Create a new file in `migrations/`:
```python
# migration_XXX_description.py
from sqlalchemy import Connection, text
from .base_migration import BaseMigration

class Migration(BaseMigration):
    version = "XXX"
    description = "What this migration does"
    
    def up(self, connection: Connection):
        # Add your schema changes
        connection.execute(text("ALTER TABLE ..."))
    
    def down(self, connection: Connection):
        # Reversal logic (if possible)
        pass
```

2. Run the migration:
```bash
python database/migrations/run_migrations.py
```

### Migration History

Migrations are tracked in the `migration_history` table:
```sql
SELECT * FROM migration_history ORDER BY applied_at DESC;
```

## Performance Considerations

### Indexes

Key indexes for performance:
- `documents.processing_status` - Filter by status
- `documents.user_id` - User's documents
- `chats.user_id` - User's chats
- `messages.chat_id` - Messages in chat

### Query Optimization

1. **Use pagination** for large result sets
2. **Filter at database level** before loading into Python
3. **Use joins** efficiently with SQLAlchemy relationships
4. **Cache frequently accessed data** (e.g., user settings)

## Troubleshooting

### Common Issues

#### 1. Database Locked
```bash
# Find and kill processes holding locks
fuser data/maestro.db
```

#### 2. Migration Failed
```bash
# Check migration status
sqlite3 data/maestro.db "SELECT * FROM migration_history;"

# Manually mark as applied if needed
sqlite3 data/maestro.db "INSERT INTO migration_history (version, applied_at) VALUES ('XXX', datetime('now'));"
```

#### 3. Corrupt Database
```bash
# Check integrity
sqlite3 data/maestro.db "PRAGMA integrity_check;"

# Backup and restore
cp data/maestro.db data/maestro.db.backup
sqlite3 data/maestro.db ".dump" | sqlite3 data/maestro_new.db
mv data/maestro_new.db data/maestro.db
```

### Debug Queries

```sql
-- Documents by status
SELECT processing_status, COUNT(*) 
FROM documents 
GROUP BY processing_status;

-- Recent chats
SELECT id, title, created_at 
FROM chats 
ORDER BY created_at DESC 
LIMIT 10;

-- User activity
SELECT u.username, COUNT(c.id) as chat_count 
FROM users u 
LEFT JOIN chats c ON u.id = c.user_id 
GROUP BY u.id;
```

## Environment Variables

- `DATABASE_URL` - Database connection string (default: `sqlite:///./data/maestro.db`)

## Testing

Run database tests:
```bash
pytest tests/test_database.py
```

## Backup and Restore

### Backup
```bash
# SQLite backup
sqlite3 data/maestro.db ".backup data/backup.db"

# Or simple file copy
cp data/maestro.db data/maestro_$(date +%Y%m%d).db
```

### Restore
```bash
cp data/backup.db data/maestro.db
```

## Related Documentation

- [Database Architecture](../../docs/DATABASE_ARCHITECTURE.md) - Complete system architecture
- [Models Documentation](models.py) - SQLAlchemy model definitions
- [CRUD Operations](crud.py) - Database operation functions
- [Migration Guide](migrations/README.md) - Detailed migration documentation