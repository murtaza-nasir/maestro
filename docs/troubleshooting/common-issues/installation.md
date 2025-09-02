# Installation Troubleshooting

Common installation issues and quick fixes.

## Docker Issues

### Docker Not Installed

**Error:** `docker: command not found`

**Solution:**

**Linux:**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Log out and back in
```

**macOS/Windows:**
Download and install Docker Desktop from [docker.com](https://www.docker.com/products/docker-desktop)

### Docker Compose Version

**Error:** `docker-compose: command not found`

**Solution:** Use `docker compose` (with space) instead:
```bash
docker compose up -d  # Not docker-compose
```

## Setup Script Issues

### Permission Denied

**Error:** `Permission denied` running setup-env.sh

**Solution:**
```bash
chmod +x setup-env.sh
./setup-env.sh
```

### Line Ending Issues (Windows)

**Error:** `bad interpreter` or `\r command not found`

**Solution:**
```bash
# Option 1: Use dos2unix
dos2unix setup-env.sh start.sh

# Option 2: Use setup script
./setup-env.sh  # It auto-fixes line endings

# Option 3: Use PowerShell script
.\setup-env.ps1
```

## Port Conflicts

### Port 80 Already in Use

**Error:** `bind: address already in use`

**Solution:**
```bash
# Change port in .env
echo "FRONTEND_PORT=8080" >> .env

# Or stop conflicting service
sudo service apache2 stop  # Linux
sudo service nginx stop
```

### Find What's Using a Port

```bash
# Linux/Mac
sudo lsof -i :80

# Windows
netstat -ano | findstr :80
```

## Container Startup Issues

### Backend Won't Start

**Problem:** Backend container keeps restarting

**Common causes:**

1. **First run - models downloading:**
```bash
docker compose logs -f maestro-backend
# Wait 5-10 minutes for models to download
```

2. **Database not ready:**
```bash
docker compose down
docker compose up -d postgres
sleep 10
docker compose up -d
```

3. **Memory issues:**
```bash
# Check available memory
free -h  # Linux
docker stats

# Reduce memory usage
echo "MAX_WORKER_THREADS=2" >> .env
docker compose restart
```

### Frontend Can't Connect

**Error:** "Unable to connect to backend"

**Solution:**
```bash
# Wait for backend to start
docker compose logs maestro-backend | grep "Started Successfully"

# Check all services running
docker compose ps

# Restart if needed
docker compose restart
```

## GPU/CUDA Issues

### CUDA Not Available

**Error:** GPU not detected

**Solution for CPU-only mode:**
```bash
echo "FORCE_CPU_MODE=true" >> .env
docker compose -f docker-compose.cpu.yml up -d
```

### nvidia-docker Not Found

**Solution:** Install NVIDIA Container Toolkit:
```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

## Disk Space Issues

### Not Enough Space

**Error:** `no space left on device`

**Solution:**
```bash
# Check space
df -h
docker system df

# Clean up
docker system prune -a --volumes
docker image prune -a

# Move Docker data directory (advanced)
# Edit /etc/docker/daemon.json:
# {"data-root": "/new/path/docker"}
```

## Network Issues

### DNS Resolution Failed

**Error:** Cannot pull images

**Solution:**
```bash
# Add DNS to Docker
# Edit /etc/docker/daemon.json:
{
  "dns": ["8.8.8.8", "8.8.4.4"]
}

# Restart Docker
sudo systemctl restart docker
```

## Quick Fixes

### Complete Reinstall

```bash
# Clean everything
docker compose down -v
docker system prune -a --volumes

# Fresh install
git pull
./setup-env.sh
docker compose up -d
```

### Verify Installation

```bash
# Check Docker
docker --version
docker compose version

# Check services
docker compose ps

# Check logs
docker compose logs --tail=50
```

### Reset to Defaults

```bash
# Backup current .env
cp .env .env.backup

# Create fresh .env
cp .env.example .env

# Restart
docker compose down
docker compose up -d
```

## Platform-Specific Issues

### Windows/WSL2

```bash
# Enable WSL2
wsl --set-default-version 2

# Install Ubuntu
wsl --install -d Ubuntu

# Run from WSL2
wsl
cd /mnt/c/path/to/maestro
./setup-env.sh
```

### macOS Apple Silicon

```bash
# Use Rosetta if needed
softwareupdate --install-rosetta

# Check architecture
uname -m  # Should show arm64

# Use platform flag if needed
docker compose up -d --platform linux/amd64
```

### Linux Permissions

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Fix volume permissions
sudo chown -R $USER:$USER ./data

# SELinux (RHEL/CentOS)
sudo setsebool -P httpd_can_network_connect 1
```

## Still Having Issues?

1. Check logs: `docker compose logs`
2. Enable debug: `LOG_LEVEL=DEBUG` in .env
3. See [FAQ](../faq.md)
4. Create [GitHub issue](https://github.com/yourusername/maestro/issues)