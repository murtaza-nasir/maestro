# Troubleshooting Guide

Quick solutions for common MAESTRO issues.

## Quick Diagnostics

### Check System Status

```bash
# Check all services are running
docker compose ps

# View recent logs
docker compose logs --tail=50

# Check specific service
docker compose logs maestro-backend
```

## Common Issues

### Installation Problems

#### Docker Compose Not Found

**Error:** `docker-compose: command not found`

**Solution:** Use `docker compose` (with space):
```bash
docker compose up -d  # Not docker-compose
```

#### Port Already in Use

**Error:** `bind: address already in use`

**Solution:** Change the port in `.env`:
```bash
FRONTEND_PORT=8080  # Use available port
```

#### Permission Denied

**Error:** `permission denied` when running scripts

**Solution:**
```bash
chmod +x setup-env.sh maestro-cli.sh start.sh
```

### Startup Issues

#### Backend Won't Start

1. **Models downloading** (first run - wait 5-10 minutes):
   ```bash
   docker compose logs -f maestro-backend
   # Wait for "MAESTRO Backend Started Successfully!"
   ```

2. **Database not ready**:
   ```bash
   docker compose down
   docker compose up -d postgres
   sleep 10
   docker compose up -d
   ```

3. **Line endings (Windows)**:
   ```bash
   dos2unix start.sh  # If available
   # Or use the setup script
   ./setup-env.sh
   ```

#### Frontend Shows Error

**Solution:** Wait for backend to fully start, then refresh browser.

### Login Issues

#### Default Admin Not Working

**Solution:** Reset admin password:
```bash
docker exec maestro-backend python reset_admin_password.py \
  --username admin --password admin123 --non-interactive
```

#### Cookies Not Working

**Solution:** 
- Use `http://localhost` not `http://127.0.0.1`
- Clear browser cookies
- Try incognito/private mode

### Document Upload Issues

#### Upload Fails

**Common causes:**

- File too large (>50MB)
- Unsupported format (only PDF, DOCX, MD, TXT)
- Backend still starting

**Solution:**
```bash
# Check backend logs
docker compose logs maestro-backend | tail -50

# For large files, use CLI
./maestro-cli.sh ingest username /path/to/documents
```

#### Documents Stuck Processing

**Solution:**
```bash
# Check processor logs
docker compose logs maestro-doc-processor

# Check document status
docker exec maestro-backend python cli_document_consistency.py system-status
```

### AI Model Issues

#### No Models in Dropdown

**Solution:**

1. Go to Settings → AI Config
2. Enter API key
3. Click "Test" button
4. Models should populate

#### API Errors

**Solution:** Check API key and provider:
```bash
# Enable debug logging
echo "LOG_LEVEL=DEBUG" >> .env
docker compose restart maestro-backend

# Check logs
docker compose logs maestro-backend | grep -i api
```

### Database Issues

#### Connection Refused

**Solution:**
```bash
# Restart database
docker compose restart postgres

# If that fails, reset
docker compose down -v
docker compose up -d
```

#### Disk Full

**Solution:**
```bash
# Check space
docker system df

# Clean up
docker system prune -a --volumes
```

### Memory Issues

#### Out of Memory

**Solution for low-memory systems:**
```bash
# Use CPU mode
echo "FORCE_CPU_MODE=true" >> .env
echo "MAX_WORKER_THREADS=2" >> .env
docker compose restart
```

## Quick Fixes

### Complete Reset

⚠️ **This deletes all data!**

```bash
docker compose down -v
docker compose up -d --build
```

### View Logs

```bash
# All logs
docker compose logs

# Specific service
docker compose logs maestro-backend

# Follow logs
docker compose logs -f

# With timestamps
docker compose logs -t
```

### Restart Services

```bash
# Restart everything
docker compose restart

# Restart specific service
docker compose restart maestro-backend
```

## Get Help

### Check Documentation

- [Installation Guide](../getting-started/installation/index.md)
- [Common Issues](common-issues/installation.md)
- [Logs Guide](logs.md)
- [Database Reset](database-reset.md)

### Enable Debug Mode

```bash
# In .env
LOG_LEVEL=DEBUG

# Restart
docker compose restart
```

### Support

- Check [FAQ](faq.md) first
- Search existing [GitHub Issues](https://github.com/yourusername/maestro/issues)
- Create new issue with:
      - Error messages
      - Docker logs
      - System info (OS, Docker version)