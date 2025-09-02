# Environment Variables Reference

Complete reference for all environment variables used in MAESTRO configuration.

## Configuration File

Environment variables are configured in the `.env` file in the project root.

```bash
# Copy template and edit
cp .env.example .env
nano .env
```

## Essential Variables

These variables must be configured for basic operation:

### Network Configuration

```bash
# Main application port (nginx proxy)
# This is the ONLY port users need to access
MAESTRO_PORT=80
```

### Database Configuration

```bash
# PostgreSQL Database Settings
POSTGRES_DB=maestro_db
POSTGRES_USER=maestro_user
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD_IMMEDIATELY  # ⚠️ CHANGE THIS!
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Admin User Credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD  # ⚠️ CHANGE THIS!

# JWT Authentication Secret
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=GENERATE_A_RANDOM_KEY_DO_NOT_USE_DEFAULT  # ⚠️ GENERATE NEW!
```

## Hardware Configuration

### GPU Settings

```bash
# GPU device IDs for different services (0, 1, 2, etc.)
# These variables are used in docker-compose.yml to assign GPUs
BACKEND_GPU_DEVICE=0          # Backend service GPU
DOC_PROCESSOR_GPU_DEVICE=0    # Document processor GPU
CLI_GPU_DEVICE=0               # CLI operations GPU

```

### Resource Limits

```bash
# Worker thread configuration for background tasks (NOT for LLM calls)
# Controls web fetches, document processing, general async tasks
# Recommended: 10-50 based on CPU cores
MAX_WORKER_THREADS=20          # Default: 20

# System-wide LLM API limit (across ALL users)
# Prevents overwhelming your AI provider
# Recommended: 50-500 based on provider limits
GLOBAL_MAX_CONCURRENT_LLM_REQUESTS=200  # Default: 200

# Per-session LLM limit (fallback - users typically set in UI)
MAX_CONCURRENT_REQUESTS=10     # Default: 10
```

## Application Settings

### CORS Configuration

```bash
# Cross-Origin Resource Sharing
# Development: Use * for any origin
# Production: Set specific domains
CORS_ALLOWED_ORIGINS=*

# Allow wildcard CORS (development only)
ALLOW_CORS_WILDCARD=true
```

### Timezone Settings

```bash
# System timezone configuration
# Examples: America/New_York, Europe/London, Asia/Tokyo
TZ=America/Chicago
VITE_SERVER_TIMEZONE=America/Chicago
```

### Logging

```bash
# Logging verbosity
# Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=ERROR
```

## Advanced Network Configuration

These are optional and only needed for direct backend/frontend access without nginx:

```bash
# Backend service configuration
BACKEND_HOST=127.0.0.1         # Bind address
BACKEND_PORT=8001              # External port
BACKEND_INTERNAL_PORT=8000     # Container internal port

# Frontend service configuration  
FRONTEND_HOST=127.0.0.1        # Bind address
FRONTEND_PORT=3030             # External port
FRONTEND_INTERNAL_PORT=3000    # Container internal port

# Protocol configuration
API_PROTOCOL=http              # http or https
WS_PROTOCOL=ws                 # ws or wss
```

## Storage Paths

⚠️ **Note**: Storage paths are set in docker-compose.yml and NOT configurable via environment variables.

```yaml
# These paths are set in docker-compose.yml:
volumes:
  - ./maestro_backend/data:/app/data           # Document storage
  - ./maestro_model_cache:/root/.cache/huggingface  # Model cache
```

Actual paths:

- Raw files: `./maestro_backend/data/raw_files/`
- Markdown: `./maestro_backend/data/markdown_files/`
- Vector store: `./maestro_backend/data/vector_store/`

## Security Variables

```bash
# JWT Authentication Secret
# Generate with: openssl rand -hex 32
JWT_SECRET_KEY=GENERATE_A_RANDOM_KEY_DO_NOT_USE_DEFAULT

# Note: SSL/TLS should be configured via reverse proxy (nginx, Caddy, etc.)
# MAESTRO does not handle SSL certificates directly
```


## Performance Tuning

### Python Library Settings

```bash
# Reduce verbosity from ML libraries
TRANSFORMERS_VERBOSITY=error         # Hugging Face transformers
TOKENIZERS_PARALLELISM=false         # Disable tokenizer warnings
TF_CPP_MIN_LOG_LEVEL=3               # TensorFlow logging
PYTHONWARNINGS=ignore                # Python warnings
```


## Environment Variable Precedence

Variables are loaded in this order (later overrides earlier):

1. Default values in code
2. `.env` file
3. Environment variables
4. Command-line arguments

## Additional Configuration Variables

### Concurrency Control

```bash
# System-wide LLM API limit (across ALL users)
GLOBAL_MAX_CONCURRENT_LLM_REQUESTS=200  # Default: 200

# Per-session fallback limit (users typically set in UI)
MAX_CONCURRENT_REQUESTS=10              # Default: 10
```

### Performance Settings

```bash
# Embedding batch processing
EMBEDDING_BATCH_SIZE=8                  # Default: 8 (reduced for memory safety)
EMBEDDING_MAX_CONCURRENT_QUERIES=3      # Default: 3 (max concurrent embedding queries)

# LLM request configuration
LLM_REQUEST_TIMEOUT=600                 # Seconds, Default: 600 (10 minutes)
```

## Configuration Examples

### Local Development

```bash
# .env for local development
MAESTRO_PORT=3000
POSTGRES_PASSWORD=dev_password
ADMIN_PASSWORD=admin123
JWT_SECRET_KEY=dev_secret_key_not_for_production
LOG_LEVEL=DEBUG
CORS_ALLOWED_ORIGINS=*
MAX_WORKER_THREADS=10
```

### Production Server

```bash
# .env for production
MAESTRO_PORT=80                 # Use reverse proxy for HTTPS
POSTGRES_PASSWORD=strong_random_password_here
ADMIN_PASSWORD=another_strong_password
JWT_SECRET_KEY=cryptographically_secure_random_key
LOG_LEVEL=WARNING
CORS_ALLOWED_ORIGINS=https://yourdomain.com
ALLOW_CORS_WILDCARD=false
```

### GPU Server

```bash
# .env for multi-GPU system
BACKEND_GPU_DEVICE=0
DOC_PROCESSOR_GPU_DEVICE=1
CLI_GPU_DEVICE=2
MAX_WORKER_THREADS=16
```

### CPU-Only Server

```bash
# .env for CPU-only system
# Use docker-compose.cpu.yml instead of regular docker-compose.yml
MAX_WORKER_THREADS=8
```

## Validation and Testing

### Check Configuration

```bash
# Verify environment variables are set
docker compose config

# Test specific variable
echo $MAESTRO_PORT

# View all Docker environment
docker compose run --rm backend env
```

### Common Issues

**Variable not taking effect:**
1. Restart services after changes:
   ```bash
   docker compose down
   docker compose up -d
   ```

2. Check for typos in variable names

3. Ensure `.env` file is in project root

**Permission errors:**
```bash
# Set appropriate permissions
chmod 600 .env  # Restrict access to sensitive file
```

## Troubleshooting

### Variable Not Working

1. **Check spelling** - Variable names are case-sensitive
2. **Restart services** - Changes require restart
3. **Check precedence** - Environment overrides file
4. **Validate format** - No spaces around `=`

### Database Connection Issues

```bash
# Test database URL format
DATABASE_URL=postgresql://user:password@host:port/database

# Verify connection
docker exec maestro-backend python -c "
from database.database import engine
print('Connected' if engine else 'Failed')
"
```

### CORS Problems

```bash
# Development (allow all)
CORS_ALLOWED_ORIGINS=*
ALLOW_CORS_WILDCARD=true

# Production (specific domains)
CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com
ALLOW_CORS_WILDCARD=false
```

## Next Steps

- [AI Provider Configuration](ai-providers.md) - Configure LLMs
- [Search Provider Configuration](search-providers.md) - Set up web search
- [First Login](../first-login.md) - Initial setup guide
- [Configuration Overview](overview.md) - General configuration guide

## Backup

To backup your MAESTRO installation:

1. **Database Backup**:
   ```bash
   docker exec maestro-postgres pg_dump -U maestro_user maestro_db > backup.sql
   ```

2. **Document Files Backup**:
   ```bash
   tar -czf documents.tar.gz ./data/raw_files ./data/markdown_files
   ```

3. **Vector Store Backup**:
   ```bash
   tar -czf vector_store.tar.gz ./data/vector_store
   ```
