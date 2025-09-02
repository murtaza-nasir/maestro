# Logs Troubleshooting

This guide helps you access and understand MAESTRO logs for debugging issues.

## Quick Commands

### View Container Logs

```bash
# Backend logs (most important for debugging)
docker compose logs maestro-backend --tail=100

# Document processor logs
docker compose logs maestro-doc-processor --tail=100

# Frontend logs
docker compose logs maestro-frontend --tail=100

# PostgreSQL logs
docker compose logs maestro-postgres --tail=100

# Nginx logs
docker compose logs maestro-nginx --tail=100
```

### Follow Logs in Real-Time

```bash
# Watch backend logs live
docker compose logs -f maestro-backend

# Watch all containers
docker compose logs -f

# Watch specific containers
docker compose logs -f maestro-backend maestro-doc-processor
```

### Search Logs

```bash
# Find errors
docker compose logs maestro-backend | grep -i error

# Find specific user activity
docker compose logs maestro-backend | grep "username"

# Find API calls
docker compose logs maestro-backend | grep -E "POST|GET|PUT|DELETE"

# Find document processing issues
docker compose logs maestro-doc-processor | grep -i "failed\|error"
```

## Container Log Locations

Docker stores container logs on the host system. The actual location depends on your Docker configuration:

- **Linux/Mac**: `/var/lib/docker/containers/<container-id>/<container-id>-json.log`
- **Windows**: `C:\ProgramData\docker\containers\<container-id>\<container-id>-json.log`

**Note:** Direct access requires root/admin privileges. Use `docker compose logs` instead.

## Log Levels

Control verbosity with the `LOG_LEVEL` environment variable:

```bash
# In .env file
LOG_LEVEL=ERROR    # Production (default)
LOG_LEVEL=WARNING  # Normal operations
LOG_LEVEL=INFO     # Detailed operations
LOG_LEVEL=DEBUG    # Full debugging

# Apply changes
docker compose down && docker compose up -d
```

## Common Log Patterns

### Backend Errors

```bash
# Authentication issues
docker compose logs maestro-backend | grep -i "auth\|login\|token"

# Database connection issues
docker compose logs maestro-backend | grep -i "database\|postgres\|connection"

# AI/LLM API issues
docker compose logs maestro-backend | grep -i "openai\|anthropic\|api\|rate"

# Mission/Research errors
docker compose logs maestro-backend | grep -i "mission\|research\|agent"
```

### Document Processing

```bash
# Processing status
docker compose logs maestro-doc-processor | grep "Processing document"

# Embedding generation
docker compose logs maestro-doc-processor | grep -i "embed\|vector"

# Conversion errors
docker compose logs maestro-doc-processor | grep -i "marker\|pdf\|convert"
```

### Database Issues

```bash
# Connection problems
docker compose logs maestro-postgres | grep -i "connection\|refused"

# Schema/migration issues
docker compose logs maestro-backend | grep -i "migration\|schema"
```

## Filtering by Time

```bash
# Last hour of logs
docker compose logs --since 1h maestro-backend

# Last 24 hours
docker compose logs --since 24h

# Specific time range
docker compose logs --since 2024-01-01T10:00:00 --until 2024-01-01T11:00:00
```

## Export Logs

```bash
# Save to file
docker compose logs maestro-backend > backend.log

# Save with timestamps
docker compose logs -t maestro-backend > backend-with-time.log

# Save all containers
docker compose logs > all-logs.txt
```

## Clear Old Logs

Docker logs can grow large. To manage size:

```bash
# Check log size
docker ps -q | xargs docker inspect --format='{{.Name}}: {{.LogPath}}' | xargs -I {} sh -c 'echo {} | cut -d: -f1; du -sh $(echo {} | cut -d: -f2)'

# Truncate logs (requires root)
truncate -s 0 $(docker inspect --format='{{.LogPath}}' maestro-backend)

# Or restart containers to reset logs
docker compose restart
```

## Troubleshooting Tips

1. **Start with backend logs** - Most issues appear here first
2. **Use grep to filter** - Logs can be verbose, filter for relevant terms
3. **Check timestamps** - Correlate events across containers
4. **Follow during operations** - Use `-f` flag while reproducing issues
5. **Increase log level** - Set `LOG_LEVEL=DEBUG` for detailed debugging

## Related Documentation

- [Common Issues](common-issues/index.md)
- [Database Issues](common-issues/database.md)
- [AI Model Issues](common-issues/ai-models.md)