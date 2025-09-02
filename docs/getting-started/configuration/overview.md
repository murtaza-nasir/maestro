# Configuration Overview

MAESTRO configuration guide covering environment variables, Docker settings, and in-app configuration options.

## Configuration Hierarchy

MAESTRO uses a layered configuration approach:

1. **Environment Variables** (`.env` file) - System-wide settings
2. **Docker Compose** - Infrastructure and volume configuration
3. **User Interface** - User-specific and runtime settings
4. **CLI Parameters** - Command-specific overrides

!!! info "Settings Precedence"
    For overlapping settings, the precedence order is:
    
    1. **Mission/Task-specific settings** (highest priority)
    2. **User UI settings** (per-user preferences)
    3. **Environment variables** (.env file)
    4. **System defaults** (lowest priority)

## Quick Setup

The easiest way to configure MAESTRO is using the interactive setup script:

```bash
./setup-env.sh
```

This script handles:
- Network configuration (localhost, LAN, or custom domain)
- Security setup (generates secure passwords)
- Admin credentials
- Port configuration
- Timezone settings

For manual setup:
```bash
cp .env.example .env
nano .env  # Edit with your preferred editor
```

## Environment Variable Configuration

All environment-based settings are configured in the `.env` file.

### Network Configuration

```env
# Main application port (nginx proxy)
MAESTRO_PORT=80  # Default: 80

# CORS configuration
CORS_ALLOWED_ORIGINS=*  # Production: Set to your domain
ALLOW_CORS_WILDCARD=true  # Set false in production
```

### Database Configuration

```env
# PostgreSQL settings (CHANGE THESE!)
POSTGRES_DB=maestro_db
POSTGRES_USER=maestro_user
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Admin credentials (CHANGE THESE!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CHANGE_THIS_PASSWORD

# JWT authentication
JWT_SECRET_KEY=GENERATE_RANDOM_KEY  # Use: openssl rand -hex 32
```

### Hardware Configuration

```env
# GPU device assignment
BACKEND_GPU_DEVICE=0        # GPU for backend service
DOC_PROCESSOR_GPU_DEVICE=0  # GPU for document processing
CLI_GPU_DEVICE=0            # GPU for CLI operations

# Force CPU mode (for systems without NVIDIA GPUs)
FORCE_CPU_MODE=false        # Set true to disable GPU
PREFERRED_DEVICE_TYPE=auto  # Options: auto, cuda, rocm, mps, cpu
```

### Performance Configuration

```env
# Concurrency Settings (4 layers of control)

# 1. General background tasks (NOT for LLM calls)
MAX_WORKER_THREADS=20  # Web fetches, document processing
# Recommended: 10-50 based on CPU cores

# 2. System-wide LLM API limit
GLOBAL_MAX_CONCURRENT_LLM_REQUESTS=200  # Total across ALL users
# Recommended: 50-500 based on provider limits

# 3. Per-session LLM limit (FALLBACK - users set in UI)
MAX_CONCURRENT_REQUESTS=10  # Default per-session limit
# Note: Users typically override this in UI settings

# 4. Web search is hardcoded to 2 concurrent requests
```

!!! info "Understanding Concurrency"
    - **Worker Threads**: Handle general tasks like web scraping and file operations
    - **Global LLM Limit**: Prevents overwhelming your AI provider
    - **Per-Session Limit**: Prevents one user from monopolizing resources
    - **Web Search**: Rate-limited to avoid search provider restrictions

### Application Settings

```env
# Timezone
TZ=America/Chicago
VITE_SERVER_TIMEZONE=America/Chicago

# Logging
LOG_LEVEL=ERROR  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Docker Configuration

### Volume Mounts

Document storage paths are configured in `docker-compose.yml`:

```yaml
services:
  backend:
    volumes:
      # Document storage (NOT configurable via env vars)
      - ./maestro_backend/data:/app/data
      # Model caches
      - ./maestro_model_cache:/root/.cache/huggingface
      - ./maestro_datalab_cache:/root/.cache/datalab
      # Reports
      - ./reports:/app/reports
```

!!! warning "Storage Path Configuration"
    Document storage paths are set in docker-compose.yml:

    - Raw files: `./maestro_backend/data/raw_files/`
    - Markdown: `./maestro_backend/data/markdown_files/`

### GPU Configuration

For multi-GPU systems, assign different GPUs to services:

```yaml
# In docker-compose.yml
services:
  backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0']  # Use GPU 0
              
  doc-processor:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['1']  # Use GPU 1
```

### CPU-Only Mode

For systems without NVIDIA GPUs:

```bash
# Method 1: Use CPU-only compose file
docker compose -f docker-compose.cpu.yml up -d

# Method 2: Set environment variable
FORCE_CPU_MODE=true
```

## In-App Configuration

These settings are configured through the web interface after installation.

### AI Provider Setup

**Location**: Settings → AI Config

1. Choose provider:
    - OpenRouter (100+ models)
    - OpenAI
    - Anthropic
    - Local LLM
    - Custom endpoint

2. Configure API credentials
3. Select models for different tasks:
    - Fast model (quick operations)
    - Mid model (balanced)
    - Intelligent model (complex tasks)
    - Verifier model (fact-checking)

See [AI Providers Guide](ai-providers.md) for detailed setup.

### Search Provider Setup

**Location**: Settings → Search

Available providers:

- **Tavily** - AI-optimized search
- **LinkUp** - Real-time comprehensive search
- **Jina** - Advanced content extraction
- **SearXNG** - Privacy-focused, self-hosted

See [Search Providers Guide](search-providers.md) for comparison.

### Web Fetch Configuration

**Location**: Settings → Web Fetch

Configure how MAESTRO fetches full content from web pages:

- **Original + Jina Fallback** - Best balance (recommended)
- **Original** - Fast, free, but limited
- **Jina Reader** - Advanced JavaScript rendering

See [Web Fetch Guide](web-fetch.md) for detailed setup.

### Research Configuration

**Location**: Settings → Research

Configurable parameters:

- **Performance**:
    - Concurrent Requests (overrides MAX_CONCURRENT_REQUESTS)
    - Search depth
    - Result counts
  
- **Quality**:
    - Research iterations
    - Question generation depth
    - Writing passes
    - Verification settings

- **Presets**:
    - Quick (fast, surface-level)
    - Standard (balanced)
    - Deep (thorough, slower)
    - Custom

!!! tip "Per-Mission Settings"
    Research settings can be overridden for individual missions/tasks, allowing fine-tuned control for specific research needs.

### User Management

**Location**: Settings → Users (Admin only)

- Create/modify user accounts
- Set permissions
- Configure quotas
- View usage statistics

## Security Best Practices

1. **Immediate Actions**:
    - Change default passwords
    - Generate secure JWT secret
    - Disable CORS wildcard in production

2. **Production Deployment**:
   ```env
   # Production-ready settings
   CORS_ALLOWED_ORIGINS=https://yourdomain.com
   ALLOW_CORS_WILDCARD=false
   LOG_LEVEL=WARNING
   ```

3. **Secure Password Generation**:
   ```bash
   # Generate secure passwords
   openssl rand -base64 32  # For database
   openssl rand -hex 32     # For JWT secret
   ```

## Troubleshooting

### Configuration Not Applied

After changing `.env`:
```bash
docker compose down
docker compose up -d
```

### Verify Settings

Check loaded configuration:
```bash
# View environment variables
docker compose config

# Check specific service
docker exec maestro-backend env | grep MAX_WORKER
```

### Common Issues

1. **Permission Denied**:
   ```bash
   chmod 600 .env  # Secure the file
   chmod +x setup-env.sh  # Make script executable
   ```

2. **Port Conflicts**:
   ```bash
   # Check port usage
   netstat -tlnp | grep 80
   # Change MAESTRO_PORT in .env if needed
   ```

3. **GPU Not Detected**:
    - Check NVIDIA drivers (need 575+ for CUDA 12.9)
    - Verify Docker GPU support
    - Set FORCE_CPU_MODE=true as fallback

## Configuration Files Reference

| File | Purpose | Location |
|------|---------|----------|
| `.env` | Environment variables | Project root |
| `docker-compose.yml` | Service definitions | Project root |
| `docker-compose.cpu.yml` | CPU-only configuration | Project root |
| `nginx/nginx.conf` | Reverse proxy settings | `./nginx/` |
| User settings | UI configurations | PostgreSQL database |

## Next Steps

- [Environment Variables Reference](environment-variables.md) - Complete list
- [AI Providers](ai-providers.md) - LLM configuration
- [Search Providers](search-providers.md) - Web search setup
- [Web Fetch Configuration](web-fetch.md) - Content fetching setup
- [First Login](../first-login.md) - Initial setup guide