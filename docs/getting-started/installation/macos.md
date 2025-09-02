# macOS Installation

Complete installation guide for running MAESTRO on macOS (Intel and Apple Silicon).

## Prerequisites

### System Requirements

- **macOS Version**: macOS 11 (Big Sur) or later
- **Processor**: Apple Silicon (M1/M2/M3) or Intel
- **RAM**: 16GB minimum (32GB recommended)
- **Storage**: 30GB free space minimum (8GB for models, 22GB for Docker and data)

### Required Software

1. **Docker Desktop for Mac**
      - Download from [Docker Desktop](https://www.docker.com/products/docker-desktop/)
      - Choose correct version (Apple Silicon or Intel)
      - Install and start Docker Desktop

2. **Git**
   ```bash
   # Use Xcode Command Line Tools
   xcode-select --install
   ```

## Installation Steps

### Step 1: Clone Repository

```bash
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
```

### Step 2: Configure Environment

Run the interactive setup script:

```bash
./setup-env.sh
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

### Step 3: Build and Start MAESTRO

```
./start.sh
```

OR

```bash
# Build and start all services (CPU mode for Mac)
docker compose -f docker-compose.cpu.yml up -d --build

# Monitor startup progress
docker compose logs -f maestro-backend
```

**First-time startup:** Takes 5-10 minutes to download AI models. Wait for "MAESTRO Backend Started Successfully!" message.

### Step 4: Access MAESTRO

- Open Safari/Chrome to `http://localhost`
- Login with credentials from setup
- Default: username `admin`, password from `.env` file

## Storage Management

### Docker Storage Location

Docker Desktop stores data in:
```
~/Library/Containers/com.docker.docker/Data/vms/0/data
```

### Clean Up Space

```bash
# Remove unused images and containers
docker system prune -a

# Remove unused volumes (careful!)
docker volume prune
```

## Troubleshooting

### Docker Desktop Won't Start

1. Restart your Mac
2. Ensure virtualization is enabled
3. Reinstall Docker Desktop if needed

### Permission Issues

```bash
# Fix permissions on project directory
sudo chown -R $(whoami) ./maestro
```

### Port Conflicts

```bash
# Check if port 80 is in use
lsof -i :80

# Change port in .env if needed
MAESTRO_PORT=8080
```

### Container Issues

```bash
# Check logs
docker compose logs maestro-backend
docker compose logs maestro-postgres

# Rebuild containers
docker compose down
docker compose build --no-cache
docker compose up -d
```

## Performance Tips

Since Macs don't have CUDA GPUs, MAESTRO runs in CPU mode:

1. **Use CPU-optimized configuration:**
   ```bash
   docker compose -f docker-compose.cpu.yml up -d
   ```

2. **Adjust worker threads in .env:**
   ```env
   # Controls concurrent background tasks (web fetches, document processing)
   MAX_WORKER_THREADS=20  # Default value
   
   # Recommended based on Mac model:
   # - MacBook Air (M1/M2): 10-15
   # - MacBook Pro (M1/M2/M3): 15-20  
   # - Mac Studio (M1 Max/Ultra): 25-40
   # - Mac Pro: 30-50
   
   # LLM concurrency - Global limit (system-wide)
   GLOBAL_MAX_CONCURRENT_LLM_REQUESTS=200  # Default
   # Adjust based on your LLM provider's rate limits
   
   # LLM concurrency - Per session (FALLBACK only)
   MAX_CONCURRENT_REQUESTS=10  # Default fallback
   # NOTE: Configure in UI instead: Settings → Research → Performance
   ```

!!! info "Settings Precedence"
    For per-session concurrent requests:
    
    1. **Mission-specific settings** (highest priority)
    2. **User settings** (UI: Settings → Research → Performance → Concurrent Requests)
    3. **Environment variable** (MAX_CONCURRENT_REQUESTS - fallback)
    4. **Default** (10, minimum enforced to prevent deadlocks)
    
    Most users should configure this in the UI, not the environment variable.

3. **Monitor resource usage:**
   ```bash
   docker stats
   ```

## Maintenance

### Update MAESTRO

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose down
docker compose -f docker-compose.cpu.yml up -d --build
```

### Backup Data

```bash
# Backup PostgreSQL database
docker exec maestro-postgres pg_dump -U maestro_user maestro_db > backup.sql

# Backup documents and models
tar czf maestro_backup.tar.gz maestro_model_cache maestro_datalab_cache
```

## Next Steps

- [Configure AI Providers](../configuration/ai-providers.md)
- [Setup Document Processing](../../user-guide/documents/overview.md)
- [Configure Search Providers](../configuration/search-providers.md)
- [CLI Usage Guide](cli-commands.md)