# Step-by-Step Windows Testing Guide

## Prerequisites
1. **Docker Desktop** installed and running
2. **PowerShell** (comes with Windows)
3. **Git** installed

## Testing Steps

### Step 1: Open PowerShell as Administrator
1. Press `Windows + X`
2. Select "Windows Terminal (Admin)" or "PowerShell (Admin)"

### Step 2: Navigate to your maestro directory
```powershell
cd C:\path\to\maestro
# For example:
# cd C:\Users\YourName\Documents\maestro
```

### Step 3: Run the test script
```powershell
.\test-windows-fix.ps1
```

This script will:
- Check if your files have Windows line endings (CRLF)
- Verify Docker is installed and running
- Apply the fix if needed
- Show you the next steps

### Step 4: If the test shows CRLF line endings, apply the fix
```powershell
.\fix-line-endings.ps1
```

### Step 5: Rebuild Docker containers
```powershell
# Stop any running containers
docker compose down

# For Windows without GPU support (recommended):
docker compose -f docker-compose.cpu.yml build --no-cache maestro-backend

# Start all services
docker compose -f docker-compose.cpu.yml up -d
```

### Step 6: Verify the fix worked
```powershell
# Check backend logs
docker compose -f docker-compose.cpu.yml logs maestro-backend
```

**⚠️ IMPORTANT - First Run:** 
The backend will download AI models on first startup (5-10 minutes). You'll see:
```
Fetching 30 files: 100%|██████████| 30/30 [XX:XX<00:00, X.XXs/it]
```
This is normal! Wait for completion.

**Success looks like:**
```
🚀 Starting MAESTRO Backend...
⏳ Waiting for PostgreSQL to be ready...
✅ PostgreSQL is ready!
🐘 Initializing PostgreSQL database...
✅ PostgreSQL initialization completed!
📊 Skipping migrations (PostgreSQL schema managed via SQL files)
🌐 Starting FastAPI server...
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Only after seeing "Application startup complete" can you successfully log in!**

**Failure looks like:**
```
/opt/nvidia/nvidia_entrypoint.sh: /app/start.sh: /bin/bash^M: bad interpreter: No such file or directory
```

### Step 7: If it still fails, force a complete rebuild
```powershell
# Remove all containers and images
docker compose down --rmi all

# Clean build cache
docker system prune -f

# Apply line ending fix again
.\fix-line-endings.ps1

# Rebuild everything
docker compose build --no-cache

# Start services
docker compose up -d

# Check logs
docker compose logs maestro-backend
```

## Troubleshooting

### Issue: "Incorrect username or password" when logging in

If you can't log in with `admin`/`admin123`, reset the password:

```powershell
# Copy the reset script into the container
docker cp scripts/reset_admin_password.py maestro-backend:/app/reset_admin_password.py

# Run the reset script
docker exec -it maestro-backend python /app/reset_admin_password.py

# This will reset the password to: admin123
```

### Issue: GPU errors on Windows (nvidia-container-cli errors)

Windows often has issues with GPU support. Use CPU-only mode:

```powershell
# Always use the CPU compose file on Windows
docker compose -f docker-compose.cpu.yml up -d

# For all commands, use:
docker compose -f docker-compose.cpu.yml [command]
```

### Issue: "cannot be loaded because running scripts is disabled"
Fix PowerShell execution policy:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: "Docker daemon is not running"
1. Open Docker Desktop
2. Wait for it to fully start (whale icon in system tray turns white)
3. Run the test again

### Issue: "Git not found"
1. Install Git from https://git-scm.com/download/win
2. Restart PowerShell
3. Run the test again

### Issue: Fix doesn't work even after applying
This might happen if Git keeps converting files back to CRLF. Fix it:
```powershell
# Configure Git to not convert line endings
git config core.autocrlf false

# Reset the repository
git rm --cached -r .
git reset --hard

# Apply fix again
.\fix-line-endings.ps1

# Rebuild
docker compose down
docker compose build --no-cache maestro-backend
docker compose up -d
```

## What the Fix Does

1. **fix-line-endings.ps1**: Converts all shell scripts, Python files, and Dockerfiles from Windows line endings (CRLF) to Unix line endings (LF)

2. **Dockerfile**: Contains `dos2unix` command that runs during build to ensure scripts have correct line endings inside the container

3. **.gitattributes**: Tells Git to always use Unix line endings for specific file types

## Verification Commands

After everything is working, you can verify with:

```powershell
# Check if backend is healthy
docker compose ps

# Test the API
curl http://localhost:8000/health

# Or using PowerShell
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing

# Access the web interface
Start-Process "http://localhost"
```

## Need Help?

If you're still having issues after following all these steps:

1. Save the output of these commands:
```powershell
docker compose logs maestro-backend > backend-logs.txt
docker compose ps > container-status.txt
.\test-windows-fix.ps1 > test-output.txt
```

2. Report the issue at: https://github.com/Shubhamsaboo/maestro/issues

Include:
- The log files created above
- Your Windows version (run `winver`)
- Docker Desktop version
- Whether you're using WSL2 or native Windows