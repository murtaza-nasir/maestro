# Windows Installation

Complete guide for installing MAESTRO on Windows systems using Docker Desktop.

!!! tip "Docker Desktop Simplifies Everything"
    Docker Desktop for Windows handles all the complex Linux compatibility automatically through its WSL2 backend. You don't need to manually set up WSL, Linux distributions, or any complex configurations - Docker Desktop does it all for you!

## Quick Start Summary

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (chooses WSL2 backend automatically)
2. Install [Git for Windows](https://git-scm.com/download/win)
3. Clone repo: `git clone https://github.com/murtaza-nasir/maestro.git`
4. Fix line endings: `.\fix-line-endings.ps1` (only needed if you get error on startup, see below)
5. Configure: `.\setup-env.ps1`
6. Start: `docker compose up -d --build`

That's it! Docker Desktop handles all the WSL2 complexity for you.

## Prerequisites

### System Requirements

- **Windows Version**: Windows 10 (version 2004+) or Windows 11
- **RAM**: 16GB minimum (32GB recommended)
- **Storage**: 30GB free space minimum (8GB for models, 22GB for Docker and data)
- **Virtualization**: Must be enabled in BIOS/UEFI

### Required Software

1. **Docker Desktop for Windows**
      - Download from [Docker Desktop](https://www.docker.com/products/docker-desktop/)
      - During installation, choose the WSL2 backend. Docker Desktop will:
         - Automatically install WSL2 if not present
         - Configure the WSL2 backend (recommended)
         - Handle all Linux compatibility layers for you

2. **Git for Windows**
      - Download from [Git for Windows](https://git-scm.com/download/win)
      - Install with default settings

3. **PowerShell**
      - Windows 10/11 includes PowerShell 5.1 (sufficient)
      - Optional: Install [PowerShell 7](https://github.com/PowerShell/PowerShell/releases) for better features

## Installation Steps

### Step 1: Clone Repository

Open PowerShell or Command Prompt:

```powershell
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
```

### Step 2: Fix Line Endings (Important!)

Windows uses different line endings than Linux. Fix them first:

```powershell
.\fix-line-endings.ps1
```

This prevents "bad interpreter" errors in Docker containers.

### Step 3: Configure Environment

#### Using PowerShell Script (Recommended)

```powershell
.\setup-env.ps1
```

The script will guide you through:

1. **Network Configuration**
    - Simple (localhost only) - if installing on the machine you are using
    - Network (LAN access) - if accessing maestro over network
    - Custom domain - if running maestro with a domain

2. **Security Configuration**
    - Generates secure passwords automatically
    - Sets up JWT secrets
    - Configures admin credentials

3. **Port Configuration**
    - Sets the main application port

### Step 4: Build and Start MAESTRO

```powershell
# Build and start all services
docker compose up -d --build

# Monitor startup progress
docker compose logs -f maestro-backend
```

**First-time startup:** Takes 5-10 minutes to download AI models. Wait for "MAESTRO Backend Started Successfully!" message.

### Step 5: Access MAESTRO

- Open browser to `http://localhost`
- Login with credentials from setup
- Default: username `admin`, password from `.env` file

## Windows-Specific Configuration

### Port Configuration

If port 80 is blocked (common on Windows):

Edit `.env` file:
```env
MAESTRO_PORT=8080  # Or any available port
```

Then access at `http://localhost:8080`

### Firewall Settings

Windows Defender may block Docker. Allow access when prompted, or manually:

```powershell
# Allow Docker through firewall
New-NetFirewallRule -DisplayName "MAESTRO" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow
```

## Docker Desktop Settings

### Backend Configuration

Docker Desktop on Windows can use two backends:

1. **WSL2 Backend (Recommended)** - Better performance, Linux compatibility
2. **Hyper-V Backend** - Legacy option, slower performance

#### Verify WSL2 Backend is Active:

1. Open Docker Desktop → Settings
2. General → "Use the WSL 2 based engine" should be ✓ checked
3. If not checked, enable it and restart Docker Desktop

!!! success "WSL2 Advantages"
    - Better file system performance
    - Full Linux kernel compatibility
    - Lower memory usage
    - No manual WSL configuration needed - Docker Desktop manages everything

### Resource Allocation

1. Docker Desktop → Settings → Resources
2. Recommended settings:
      - **CPUs**: 4+ cores (or at least half your system cores)
      - **Memory**: 8GB+ (ideally 12-16GB for document processing)
      - **Disk**: 60GB+ (models and documents need space)

## Troubleshooting

### Docker Desktop Won't Start

1. **Check Virtualization in BIOS**
      - Restart computer and enter BIOS/UEFI
      - Enable Intel VT-x/AMD-V virtualization
      - Save and restart

2. **If Docker Desktop installation fails**, manually enable Windows features:
   ```powershell
   # Run as Administrator
   # Docker Desktop usually does this automatically, but if it fails:
   Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
   Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
   ```

3. **Install WSL2 kernel update** (if prompted):
      - Download from [Microsoft WSL2 kernel update](https://aka.ms/wsl2kernel)
      - Docker Desktop usually handles this automatically

4. Restart computer after any changes

### Line Ending Issues

If you see "bad interpreter" errors:

```powershell
# Run the fix script
.\fix-line-endings.ps1

# Rebuild containers
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Permission Issues

Run PowerShell as Administrator if you encounter permission errors.

### Port Already in Use

```powershell
# Check what's using port 80
netstat -ano | findstr :80

# Change port in .env file
MAESTRO_PORT=8080
```

### Container Issues

```powershell
# Check logs
docker compose logs maestro-backend
docker compose logs maestro-postgres

# Restart containers
docker compose down
docker compose up -d
```

## Performance Tips

### Windows Optimization

1. **Close unnecessary applications** to free RAM for Docker
2. **Exclude Docker from antivirus scanning** for better performance
3. **Use SSD storage** for Docker volumes if possible
4. **Configure performance settings** in `.env` file:
   ```env
   # Background task threads
   MAX_WORKER_THREADS=20  # Default (10-50 based on system)
   
   # LLM request concurrency - Global limit
   GLOBAL_MAX_CONCURRENT_LLM_REQUESTS=200  # System-wide (50-500)
   
   # LLM request concurrency - Per session (FALLBACK only)
   MAX_CONCURRENT_REQUESTS=10  # Default fallback
   # NOTE: Users should configure this in the UI instead:
   # Settings → Research → Performance → Concurrent Requests
   
   # Note: Web search is rate-limited to 2 concurrent requests
   ```
   
!!! info "Settings Precedence"
      For per-session concurrent requests, the order is:
      
      1. **Mission-specific settings** (per research task)
      2. **User settings** (UI: Settings → Research → Performance)
      3. **Environment variable** (MAX_CONCURRENT_REQUESTS)
      4. **Default** (10, minimum enforced)
      
      Most users should use the UI settings rather than environment variables.

### CPU Mode

Windows typically runs MAESTRO in CPU mode:

```powershell
# Ensure CPU mode configuration
docker compose -f docker-compose.cpu.yml up -d
```

## Maintenance

### Update MAESTRO

```powershell
# Pull latest changes
git pull

# Fix line endings again if needed
.\fix-line-endings.ps1

# Rebuild and restart
docker compose down
docker compose up -d --build
```

### Backup Data

```powershell
# Backup database
docker exec maestro-postgres pg_dump -U maestro_user maestro_db > backup.sql

# Backup documents and models
tar -czf maestro_backup.tar.gz maestro_model_cache maestro_datalab_cache
```

### Clean Up

```powershell
# Remove unused Docker resources
docker system prune -a

# Clean up volumes (careful!)
docker volume prune
```

## Next Steps

- [Configure AI Providers](../configuration/ai-providers.md)
- [Setup Document Processing](../../user-guide/documents/overview.md)
- [Configure Search Providers](../configuration/search-providers.md)
- [CLI Usage Guide](cli-commands.md)