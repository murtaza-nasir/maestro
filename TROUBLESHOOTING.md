# MAESTRO Troubleshooting Guide

## Common Issues and Solutions

### Login Issues

#### Problem: Can't log in with admin/admin123
**Symptoms**: "Incorrect username or password" error despite using correct credentials

**Solution**: Reset the admin password
```bash
# Run the reset script (already in the container)
docker exec -it maestro-backend python reset_admin_password.py

# Or with a custom password:
docker exec -it maestro-backend python reset_admin_password.py YourNewPassword

# Or using environment variable:
docker exec -it maestro-backend bash -c "ADMIN_PASSWORD=YourNewPassword python reset_admin_password.py"
```

**Alternative**: Complete database reset (WARNING: Deletes all data!)
```bash
docker compose down -v
docker compose up -d
```

---

### Windows/WSL Issues

#### Problem: Backend won't start - "bad interpreter" error
**Symptoms**: `/bin/bash^M: bad interpreter: No such file or directory`

**Solution**: Fix line endings
```powershell
# Run the line ending fix script
.\fix-line-endings.ps1

# Rebuild and restart
docker compose down
docker compose build --no-cache maestro-backend
docker compose up -d
```

#### Problem: GPU errors preventing startup
**Symptoms**: `nvidia-container-cli: initialization error: WSL environment detected but no adapters were found`

**Solution**: Use CPU-only mode
```powershell
# Always use the CPU compose file on Windows
docker compose -f docker-compose.cpu.yml up -d

# For all Docker commands:
docker compose -f docker-compose.cpu.yml logs -f
docker compose -f docker-compose.cpu.yml down
```

---

### ⏱Startup Issues

#### Problem: Login fails immediately after starting
**Symptoms**: Frontend loads but login returns "Network Error"

**Explanation**: On first run, the backend downloads AI models (5-10 minutes)

**Solution**: Wait for startup to complete
```bash
# Monitor the backend logs
docker compose logs -f maestro-backend

# Wait for this message:
# "INFO:     Application startup complete."
```

---

### CPU vs GPU Mode

#### When to use CPU mode:
- Systems without NVIDIA GPUs
- AMD GPUs without ROCm support
- Development/testing environments

#### How to enable CPU mode:

**Option 1: Use CPU-only compose file** (Recommended)
```bash
docker compose -f docker-compose.cpu.yml up -d
```

**Option 2: Set environment variable**
```bash
# In your .env file:
FORCE_CPU_MODE=true

# Then use regular compose:
docker compose up -d
```

---

### Database Issues

#### Problem: Database connection errors
**Symptoms**: `could not translate host name "postgres" to address`

**Solution**: Ensure PostgreSQL container is running
```bash
# Check container status
docker compose ps

# If postgres is not running:
docker compose up -d postgres

# Wait for it to be healthy, then start other services:
docker compose up -d
```

#### Problem: Corrupted database
**Solution**: Reset the database (WARNING: Deletes all data!)
```bash
docker compose down -v
docker volume rm maestro_postgres-data maestro_maestro-data
docker compose up -d
```

---

### Network Access Issues

#### Problem: Can't access from another device
**Solution**: Configure for network access
```bash
# Re-run setup with network option
./setup-env.sh  # Choose option 2 (Network)

# Or manually edit .env:
CORS_ALLOWED_ORIGINS=http://YOUR_IP,http://localhost

# Restart services
docker compose down
docker compose up -d
```

#### Problem: CORS errors
**Solution**: Clear browser cache and rebuild
```bash
docker compose down
docker compose up --build -d
```

---

### Docker Issues

#### Problem: "Volume is in use" error
**Solution**: Force remove containers and volumes
```bash
# Stop everything
docker compose down

# Remove specific containers
docker rm -f maestro-backend maestro-frontend maestro-nginx maestro-postgres

# Remove volumes
docker volume rm maestro_postgres-data maestro_maestro-data

# Start fresh
docker compose up -d
```

#### Problem: Out of disk space
**Solution**: Clean up Docker resources
```bash
# Remove unused containers, networks, images
docker system prune -a

# Remove unused volumes
docker volume prune
```

---

### Debugging Commands

#### Check container status:
```bash
docker compose ps
```

#### View logs for specific service:
```bash
docker compose logs maestro-backend
docker compose logs maestro-postgres
docker compose logs maestro-frontend
```

#### Check database users:
```bash
docker exec -it maestro-postgres psql -U maestro_user -d maestro_db -c "SELECT id, username, email FROM users;"
```

#### Test backend health:
```bash
curl http://localhost:8000/health
```

#### Access backend shell:
```bash
docker exec -it maestro-backend bash
```

---

### Getting Help

If these solutions don't resolve your issue:

1. **Collect diagnostic information:**
```bash
# Save logs
docker compose logs > maestro-logs.txt

# System information
docker version > system-info.txt
docker compose version >> system-info.txt
```

2. **Report the issue:**
- GitHub Issues: https://github.com/Shubhamsaboo/maestro/issues
- Include:
  - Error messages
  - Log files
  - Steps to reproduce
  - Your operating system and Docker version

---

### Complete Reset

If all else fails, perform a complete reset:

```bash
# Stop and remove everything
docker compose down -v --remove-orphans

# Remove all maestro images
docker images | grep maestro | awk '{print $3}' | xargs docker rmi -f

# Clean Docker system
docker system prune -a --volumes

# Clone fresh repository
cd ..
rm -rf maestro
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro

# Start fresh
./setup-env.sh  # or setup-env.ps1 on Windows
docker compose up -d
```

---

## Platform-Specific Notes

### Windows
- Always use `docker-compose.cpu.yml` to avoid GPU issues
- Run PowerShell as Administrator for Docker commands
- Use `.\script.ps1` notation for PowerShell scripts

### macOS
- CPU-only mode is automatic (no GPU support)
- May need to increase Docker Desktop memory allocation

### Linux
- Full GPU support with nvidia-container-toolkit
- Ensure user is in `docker` group to avoid `sudo`

---

Last updated: 2025-01-15