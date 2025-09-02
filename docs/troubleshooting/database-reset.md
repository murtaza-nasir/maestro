# Database Reset Guide

This guide covers essential database reset procedures for MAESTRO's PostgreSQL database.

⚠️ **WARNING**: Database reset will DELETE ALL DATA including users, documents, chats, and missions.

## Complete Reset (DELETES EVERYTHING)

### Quick Reset with Docker

```bash
# Full reset with volume removal
docker compose down -v
docker compose up -d --build

# This removes:
# - All user accounts
# - All documents and embeddings
# - All chats and missions
# - All configuration
```

## Using maestro-cli.sh

The CLI tool provides comprehensive database management capabilities.

### Check Database Status

```bash
# Check database health and consistency
./maestro-cli.sh reset-db --check

# View detailed statistics
./maestro-cli.sh reset-db --stats
```

### Reset with Backup

```bash
# Create backup before reset
./maestro-cli.sh reset-db --backup

# This will:
# 1. Create timestamped backup
# 2. Reset database
# 3. Reinitialize schema
# 4. Keep backup for recovery
```

### Force Reset (No Confirmation)

```bash
# Reset without confirmation prompts (DANGEROUS!)
./maestro-cli.sh reset-db --force
```

### CLI Reset Command Options

```bash
./maestro-cli.sh reset-db [OPTIONS]

Options:
  --backup  Create timestamped backups before reset
  --force   Skip confirmation prompts (DANGEROUS!)
  --stats   Show database statistics only (don't reset)
  --check   Check data consistency across databases only
  --help    Show help message
```

## Admin Password Reset

### Using the Reset Script

```bash
# Interactive password reset (will prompt for new password)
docker exec -it maestro-backend python reset_admin_password.py

# Reset with specific username
docker exec -it maestro-backend python reset_admin_password.py --username admin

# Non-interactive reset with password
docker exec -it maestro-backend python reset_admin_password.py --password "newpassword123" --non-interactive

# List all admin users
docker exec -it maestro-backend python reset_admin_password.py --list
```

### Script Options

```bash
reset_admin_password.py [OPTIONS]

Options:
  --username, -u     Username to reset (default: admin)
  --password, -p     New password (will prompt if not provided)
  --non-interactive  Run without prompts
  --list, -l         List all admin users
```

### Quick Admin Password Reset

```bash
# Reset admin password to 'admin123' (for development only)
docker exec maestro-backend python reset_admin_password.py --username admin --password admin123 --non-interactive
```

## Document Consistency Cleanup

### Check Document Consistency

```bash
# Check system-wide consistency status
docker exec maestro-backend python cli_document_consistency.py system-status

# Check consistency for a specific user
docker exec maestro-backend python cli_document_consistency.py check-user <user_id>

# Clean up orphaned documents for a user
docker exec maestro-backend python cli_document_consistency.py cleanup-user <user_id>

# Clean up all users' orphaned documents
docker exec maestro-backend python cli_document_consistency.py cleanup-all
```

## Emergency Recovery

### If Reset Fails

```bash
# Force remove volumes
docker volume ls | grep maestro
docker volume rm maestro_postgres_data -f

# Nuclear option - removes everything
docker system prune -a --volumes
```

### Container Won't Start After Reset

```bash
# Check logs
docker compose logs postgres

# Common fix: wait longer for initialization
docker compose down
docker compose up -d postgres
sleep 30  # Give more time for database initialization
docker compose up -d
```

## Best Practices

1. **Always backup first** before any reset operation
2. **Document current state** before making changes
3. **Test in development** before resetting production
4. **Keep backups** for at least 7 days
5. **Verify reset** completed successfully before proceeding

## Related Documentation

- [Database Issues](common-issues/database.md)
- [CLI Commands](../getting-started/installation/cli-commands.md)
- [Installation Guide](../getting-started/installation/index.md)