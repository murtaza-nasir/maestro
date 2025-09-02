# Linux Installation

Complete installation guide for running MAESTRO on Linux distributions with full GPU support.

!!! important "NVIDIA Driver Requirement for GPU Users"
    MAESTRO uses CUDA 12.9, which requires **NVIDIA driver version 575 or newer**. If you plan to use GPU acceleration, ensure you have the correct driver version installed. Older drivers (like 535) will cause container startup failures.

## Prerequisites

### System Requirements

- **Distribution**: Ubuntu 20.04+, Debian 11+, RHEL 8+, or compatible
- **RAM**: 16GB minimum (32GB recommended)
- **Storage**: 30GB free space minimum (8GB for models, 22GB for Docker and data)
- **GPU VRAM** (if using GPU): 
    - 4GB minimum for single process (research OR document processing)
    - 8GB recommended for concurrent operations (research AND document processing)
- **Network**: Internet connection for initial setup and web search

### Required Software

1. **Docker Engine**
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   
   # Add user to docker group
   sudo usermod -aG docker $USER
   newgrp docker
   ```

2. **Docker Compose V2**
   ```bash
   # Check if already installed
   docker compose version
   
   # If not installed, get latest version
   sudo apt-get update
   sudo apt-get install docker-compose-plugin
   ```

3. **Git**
   ```bash
   sudo apt-get install git
   ```

### Optional: NVIDIA GPU Support

For GPU acceleration (highly recommended):

1. **NVIDIA Drivers**
   
   !!! warning "Driver Version Requirement"
       MAESTRO uses CUDA 12.9, which requires NVIDIA driver version 575 or newer. Older drivers will cause container startup failures.
   
   ```bash
   # Ubuntu/Debian - Install latest driver (575+)
   sudo apt-get update
   sudo apt-get install nvidia-driver-575
   # OR install the latest available
   
   # Verify installation and check driver version
   nvidia-smi
   # Should show Driver Version: 575.xx or higher
   ```
   
   If driver 575+ is not available in your repository:
   ```bash
   # Add NVIDIA PPA for latest drivers
   sudo add-apt-repository ppa:graphics-drivers/ppa
   sudo apt-get update
   sudo apt-get install nvidia-driver-575
   ```

2. **NVIDIA Container Toolkit**
   ```bash
   # Add repository
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
     sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   
   # Install toolkit
   sudo apt-get update
   sudo apt-get install nvidia-container-toolkit
   
   # Configure Docker to use NVIDIA runtime
   sudo nvidia-ctk runtime configure --runtime=docker
   
   # Restart Docker
   sudo systemctl restart docker
   
   # Verify GPU access with CUDA 12.9
   docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu24.04 nvidia-smi
   ```

## Pre-Installation Verification

### GPU Setup Verification (Optional but Recommended)

If you plan to use GPU acceleration, verify your setup before proceeding:

```bash
# Check driver version (must be 575+)
nvidia-smi | grep "Driver Version"

# Test Docker GPU access with CUDA 12.9
docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu24.04 nvidia-smi

# If the above fails, your driver is too old or GPU support is not configured
```

## Installation Steps

### Step 1: Clone Repository

```bash
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
```

### Step 2: Configure Environment

Use the interactive setup script for easy configuration:

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

Always build on first run to ensure latest changes:

```bash
# Build and start all services
docker compose up -d --build

# Monitor startup progress
docker compose logs -f maestro-backend
```

**First-time startup:** The backend downloads AI models on first run (5-10 minutes). Wait for "MAESTRO Backend Started Successfully!" message.

### Step 4: Access MAESTRO

Once startup is complete:

- Open browser to `http://localhost` (or configured port)
- Login with admin credentials from setup
- Change default password immediately

## Docker Volume Configuration

### Persistent Model Storage

To avoid re-downloading models after container restarts, MAESTRO uses persistent volumes:

```yaml
# In docker-compose.yml
volumes:
  - ./maestro_model_cache:/root/.cache/huggingface
  - ./maestro_datalab_cache:/root/.cache/datalab
```

These volumes persist:

- **BGE-M3 Embedding Model** (560M parameters): ~1.1GB on disk, ~1.3GB VRAM per instance
- **BGE-Reranker-v2-m3**: ~1.1GB on disk, ~1.2GB VRAM when loaded
- **Document Processing Models (Marker)**: ~3GB on disk
- **Total Model Cache**: ~6-8GB disk space recommended
- **Processed documents and embeddings**: Varies by document volume

!!! important "Multiple Model Instances"
    MAESTRO loads separate instances of embedding models for:
    
    - **Document processing**: When uploading/ingesting documents
    - **Research queries**: When searching and retrieving information
    
    If both processes run simultaneously, VRAM usage doubles (~2.6GB for embeddings + ~1.2GB for reranker = ~4GB total).
    The higher VRAM usage you see (~7-8GB) likely includes overhead, memory fragmentation, and potentially multiple model instances.

## GPU Device Assignment

### Single GPU Configuration

Default configuration uses GPU 0. To change:

```yaml
# In docker-compose.yml
services:
  backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0']  # Change to your GPU ID
              capabilities: [gpu]
```

### Multi-GPU Configuration

Assign different GPUs to different services:

```yaml
services:
  backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0']  # Backend uses GPU 0
              capabilities: [gpu]
  
  doc-processor:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['1']  # Document processor uses GPU 1
              capabilities: [gpu]
```

## Resource Management

### Performance Tuning

MAESTRO uses multiple layers of concurrency control for different purposes:

!!! info "Concurrency Layers Explained"
    Think of these settings as different traffic control systems:
    
    1. **MAX_WORKER_THREADS** = General purpose workers (for all background tasks)
        - Controls: Web scraping, file processing, general async tasks
    
    2. **GLOBAL_MAX_CONCURRENT_LLM_REQUESTS** = LLM API capacity
        - Controls: Total LLM API calls across ALL users/sessions
        - Prevents: Overwhelming your LLM provider
    
    3. **MAX_CONCURRENT_REQUESTS** = Individual user API calls
        - Controls: LLM API calls per research session
        - Prevents: One user/session from monopolizing resources
    
    4. **Web Search** = (hardcoded to 2)
        - Controls: Search API calls (Tavily, Jina, etc.)
        - Prevents: Rate limiting from search providers

#### Worker Thread Configuration

The `MAX_WORKER_THREADS` environment variable controls concurrent background tasks:

```bash
# In .env file
MAX_WORKER_THREADS=20  # Default value

# Recommended values based on system:
# - Low-end (8GB RAM, 4 cores): 10
# - Mid-range (16GB RAM, 8 cores): 20
# - High-end (32GB+ RAM, 16+ cores): 30-50
```

This setting affects:

- Concurrent web fetches during research
- Parallel document processing
- Background task execution

!!! tip "Finding Optimal Value"
    Start with the default (20) and adjust based on:
    - System responsiveness during heavy loads
    - Memory usage (monitor with `docker stats`)
    - Number of concurrent users

#### LLM Concurrency Configuration

There are two levels of LLM concurrency control:

1. **Global limit** (`GLOBAL_MAX_CONCURRENT_LLM_REQUESTS`):
   ```bash
   # In .env file
   GLOBAL_MAX_CONCURRENT_LLM_REQUESTS=200  # Default
   
   # Recommended based on LLM provider:
   # - Local LLM (vLLM, Ollama): 50-100
   # - OpenAI/Anthropic: 100-200
   # - High-volume API keys: 200-500
   ```

2. **Per-session limit** (`MAX_CONCURRENT_REQUESTS`):
   ```bash
   MAX_CONCURRENT_REQUESTS=10  # Fallback default
   ```
   
    !!! info "Settings Precedence"
      For per-session concurrency, the order of precedence is:
      
      1. **Mission-specific settings** (per research task)
      2. **User settings** (UI: Settings → Research → Performance → Concurrent Requests)
      3. **Environment variable** (MAX_CONCURRENT_REQUESTS)
      4. **Default** (10, minimum enforced to prevent deadlocks)
      
      Most users should configure this in the UI rather than the environment variable.

### Memory and CPU Limits

Add resource constraints in `docker-compose.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

### GPU Memory Management

If you encounter GPU memory issues:

```bash
# Set GPU memory growth
export TF_FORCE_GPU_ALLOW_GROWTH=true

# Limit GPU memory usage
export TF_GPU_MEMORY_LIMIT=4096  # Limit to 4GB
```

## Data Backup and Recovery

### Backup Volumes

```bash
# Stop services
docker compose down

# Backup PostgreSQL data
docker run --rm -v maestro_postgres-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/postgres_backup.tar.gz /data

# Backup model cache
tar czf models_backup.tar.gz maestro_model_cache maestro_datalab_cache
```

### Restore from Backup

```bash
# Restore PostgreSQL
docker run --rm -v maestro_postgres-data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/postgres_backup.tar.gz -C /

# Restore models
tar xzf models_backup.tar.gz

# Restart services
docker compose up -d
```

## Troubleshooting

### GPU Not Detected

```bash
# Verify NVIDIA driver and version
nvidia-smi
# Must show Driver Version: 575.xx or higher for CUDA 12.9

# Check Docker GPU access with CUDA 12.9
docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu24.04 nvidia-smi

# Check container toolkit
nvidia-container-cli info
```

#### Common GPU Issues:

1. **Driver too old for CUDA 12.9**:
   ```bash
   # Check current driver version
   nvidia-smi | grep "Driver Version"
   # If below 575, upgrade driver:
   sudo apt-get install nvidia-driver-575
   sudo reboot
   ```

2. **Container fails with CUDA error**:
    - Usually means driver version mismatch
    - Ensure driver is 575+ for CUDA 12.9
    - After driver update, restart Docker: `sudo systemctl restart docker`

### Permission Issues

```bash
# Fix Docker permissions
sudo usermod -aG docker $USER
newgrp docker

# Fix volume permissions
sudo chown -R $USER:$USER ./maestro_model_cache ./maestro_datalab_cache
```

### Container Startup Issues

```bash
# Check logs
docker compose logs maestro-backend
docker compose logs maestro-postgres

# Rebuild if needed
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Port Conflicts

```bash
# Check port usage
sudo netstat -tlnp | grep 80

# Change port in .env
MAESTRO_PORT=8080
```

## Maintenance

### Update MAESTRO

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker compose down
docker compose up -d --build
```

### Clean Up

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# Remove unused volumes (careful!)
docker volume prune
```

### Monitor Resources

```bash
# Check container resources
docker stats

# Check disk usage
df -h
docker system df
```

## Next Steps

- [Configure AI Providers](../configuration/ai-providers.md)
- [Setup Document Processing](../../user-guide/documents/overview.md)
- [Configure Search Providers](../configuration/search-providers.md)
- [CLI Usage Guide](cli-commands.md)