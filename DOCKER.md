# MAESTRO Docker Setup

This document provides detailed instructions on how to run MAESTRO using Docker. For a quick start, see the Docker installation instructions in the [README.md](./README.md) file.

This guide explains how to run MAESTRO using Docker, which provides an easy way to set up and use the application without installing dependencies directly on your system.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)
- **GPU Support (Recommended)**: For optimal performance with RAG functionality
  - NVIDIA GPU with CUDA support
  - [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/murtaza-nasir/maestro.git
   cd maestro
   ```

2. Configure your environment variables:

   **Quick Setup (Recommended):**
   ```bash
   ./setup-env.sh
   ```

   **Manual Setup:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your API keys and network settings
   ```

   The `.env` file in the root directory handles all network configuration automatically. API URLs are constructed dynamically from your host/port settings.

3. Create a directory for your PDFs (for CLI ingestion):
   ```bash
   mkdir -p pdfs
   ```
   
   Copy any PDF files you want to analyze into the `pdfs` directory.

4. Start the MAESTRO Web Application:
   ```bash
   docker compose up
   ```

   This will build the Docker images and start the web interface, accessible at http://localhost:3030

## Environment Configuration

MAESTRO uses a flexible environment configuration system that supports various deployment scenarios:

### Configuration Files

- **`.env.example`**: Template with all available options and examples
- **`.env`**: Your actual configuration (created from template)
- **`setup-env.sh`**: Interactive setup script for guided configuration

### Network Configuration

The system automatically constructs API URLs from your network settings:

```bash
# Example .env configuration
BACKEND_HOST=localhost          # Where backend runs
BACKEND_PORT=8001              # Backend port
FRONTEND_HOST=localhost        # Where frontend runs  
FRONTEND_PORT=3030            # Frontend port
API_PROTOCOL=http             # http or https
WS_PROTOCOL=ws               # ws or wss

# Automatically constructs:
# VITE_API_HTTP_URL=http://localhost:8001
# VITE_API_WS_URL=ws://localhost:8001
```

### Deployment Scenarios

**Local Development:**
```bash
BACKEND_HOST=localhost
FRONTEND_HOST=localhost
API_PROTOCOL=http
WS_PROTOCOL=ws
```

**Production (Same Server):**
```bash
BACKEND_HOST=0.0.0.0
FRONTEND_HOST=0.0.0.0
API_PROTOCOL=https
WS_PROTOCOL=wss
```

**Distributed Deployment:**
```bash
# Backend server .env
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8001

# Frontend server .env  
BACKEND_HOST=api.yourdomain.com
FRONTEND_HOST=0.0.0.0
API_PROTOCOL=https
WS_PROTOCOL=wss
```

For complete deployment documentation, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## GPU Support

MAESTRO's RAG functionality (document embedding, retrieval, and reranking) benefits significantly from GPU acceleration. The Docker setup includes GPU support by default.

### Requirements for GPU Support

1. NVIDIA GPU with CUDA support
2. NVIDIA drivers installed on your host system
3. NVIDIA Container Toolkit installed

### Verifying GPU Support

After starting the containers, you can verify GPU access:

```bash
docker compose exec backend nvidia-smi
```

If you see your GPU listed, the container has successfully accessed your GPU.

### Configuring GPU Usage

By default, the containers use GPU device 3. You can change this by modifying the `device_ids` in `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ['0']  # Use GPU 0 instead
          capabilities: [gpu]
```

If you don't have a GPU or don't want to use it, comment out the GPU-related sections in `docker-compose.yml`.

## Directory Structure

The Docker setup creates several mounted volumes to persist data:

- `./.env`: Your configuration file
- `./pdfs`: Place your PDF files here for CLI ingestion
- `./reports`: Output directory for research reports
- `maestro-data`: Docker volume for vector store and processed data
- `./maestro_model_cache`: Cache for Hugging Face embedding models (~2GB)
- `./maestro_datalab_cache`: Cache for document processing models (~3GB)

## Model Caching & Performance Optimization

MAESTRO uses several AI models that are automatically downloaded on first use:

### Model Types and Sizes
- **Embedding Models** (BAAI/bge-m3): ~2GB - Used for semantic search and document retrieval
- **Document Processing Models** (marker-pdf): ~3GB - Used for PDF text extraction, layout analysis, and table recognition
- **Reranking Models**: ~500MB - Used for improving search result relevance

### Persistent Caching

The Docker Compose configuration includes persistent volume mounts to cache models between container restarts:

```yaml
volumes:
  - ./maestro_model_cache:/root/.cache/huggingface      # Embedding models
  - ./maestro_datalab_cache:/root/.cache/datalab       # Document processing models
```

### First Run vs. Subsequent Runs

**First Run:**
- Models download automatically (~5GB total)
- First document processing takes 2-3 minutes
- Requires stable internet connection

**Subsequent Runs:**
- Models load from cache instantly
- Document processing starts immediately
- No internet required for model loading

### Managing Model Cache

**View cache size:**
```bash
du -sh maestro_model_cache maestro_datalab_cache
```

**Clear cache (if needed):**
```bash
rm -rf maestro_model_cache maestro_datalab_cache
docker compose down
docker compose up --build
```

**Backup cache (for offline deployment):**
```bash
tar -czf maestro-models-cache.tar.gz maestro_model_cache maestro_datalab_cache
```

### Performance Benefits

With persistent caching enabled:
- ✅ **Faster startup**: No model downloads after first run
- ✅ **Reduced bandwidth**: Models download only once
- ✅ **Offline operation**: Process documents without internet
- ✅ **Consistent performance**: Predictable processing times
- ✅ **Resource efficiency**: No repeated downloads across container restarts

## Command Line Interface (CLI)

MAESTRO includes a powerful CLI for bulk document ingestion and management. For complete CLI documentation, see [CLI_GUIDE.md](./CLI_GUIDE.md).

### Quick CLI Examples

```bash
# Linux/macOS
./maestro-cli.sh help
./maestro-cli.sh create-user researcher mypass123
./maestro-cli.sh ingest researcher ./documents

# Windows PowerShell
.\maestro-cli.ps1 help
.\maestro-cli.ps1 create-user researcher mypass123
.\maestro-cli.ps1 ingest researcher .\documents
```

The CLI provides direct document processing with real-time progress updates, supporting PDF, Word, and Markdown files. See the [CLI Guide](./CLI_GUIDE.md) for:
- Complete command reference
- User and group management
- Document ingestion options
- Database management tools
- Troubleshooting tips


## Using the Web Interface

The primary way to use MAESTRO is through the web interface:

1. Start the application:
   ```bash
   docker compose up
   ```

2. Open your browser and go to http://localhost:3030

3. Create an account or log in

4. Upload documents through the web interface or use the CLI for bulk operations

5. Create research missions and writing sessions

## Troubleshooting

### GPU Issues

If you encounter GPU-related issues:

1. Verify your NVIDIA drivers are installed and working:
   ```bash
   nvidia-smi
   ```

2. Check that the NVIDIA Container Toolkit is properly installed:
   ```bash
   sudo docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   ```

3. If you don't have a GPU or can't get it working, modify `docker-compose.yml` to disable GPU support.

### Permission Issues

If you encounter permission issues with mounted volumes:

```bash
sudo chown -R $(id -u):$(id -g) ./reports ./pdfs
```

### Container Won't Start

If containers fail to start:

1. Check the logs:
   ```bash
   docker compose logs backend
   docker compose logs frontend
   docker compose logs doc-processor
   ```

2. Verify your `.env` file is properly configured.

3. Try rebuilding the images:
   ```bash
   docker compose build --no-cache
   ```

### CLI Issues

If CLI commands fail:

1. Make sure the backend service is running:
   ```bash
   docker compose up -d backend
   ```

2. Check that the database is accessible:
   ```bash
   docker compose --profile cli run --rm cli python cli_ingest.py list-users
   ```

3. Verify file permissions for the `pdfs` directory:
   ```bash
   ls -la ./pdfs
   ```

### Reverse Proxy Timeout Issues

If you're running MAESTRO behind a reverse proxy (like nginx, Apache, or a cloud load balancer) and experiencing 504 Gateway Timeout errors during long operations (searches, document processing, etc.), you need to increase the timeout settings in your reverse proxy configuration.

#### For nginx:

Add these settings to your nginx server block or location block:

```nginx
# Increase timeout settings for long-running operations
proxy_connect_timeout 600s;
proxy_send_timeout 600s;
proxy_read_timeout 600s;
send_timeout 600s;

# WebSocket support for real-time updates
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# Recommended buffer settings
proxy_buffering on;
proxy_buffer_size 4k;
proxy_buffers 8 4k;
proxy_busy_buffers_size 8k;

# Optional: Increase max body size for large document uploads
client_max_body_size 100M;
```

#### For Apache:

Add these settings to your VirtualHost or ProxyPass configuration:

```apache
# Increase timeout for long operations
ProxyTimeout 600
Timeout 600

# For WebSocket support
RewriteEngine On
RewriteCond %{HTTP:Upgrade} websocket [NC]
RewriteCond %{HTTP:Connection} upgrade [NC]
RewriteRule ^/?(.*) "ws://localhost:8000/$1" [P,L]
```

#### For nginx Proxy Manager (GUI):

If using nginx Proxy Manager:
1. Go to your proxy host settings
2. Click on "Advanced" tab
3. Add the custom nginx configuration from above
4. Save and test

#### For Cloud Load Balancers:

- **AWS ALB/ELB**: Set idle timeout to 600 seconds in the load balancer attributes
- **Google Cloud Load Balancer**: Configure backend service timeout to 600 seconds
- **Azure Application Gateway**: Set request timeout to 600 seconds in backend settings

**Note**: The default timeout for most reverse proxies is 60 seconds, which is too short for MAESTRO's AI-powered operations that can take several minutes to complete. The application handles these timeouts gracefully, but increasing the limits provides a better user experience.

## Advanced Configuration

### Persistent Storage

All data is stored in Docker volumes and mounted directories, ensuring your data persists between container restarts.

### Resource Limits

You can add resource limits to the `docker-compose.yml` file if needed:

```yaml
services:
  backend:
    # ... existing configuration ...
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

## Security Considerations

- Change default passwords immediately in production
- Use strong passwords for user accounts
- Consider using environment variables for sensitive configuration
- Regularly update the Docker images
- Monitor access logs through the web interface

## Performance Tips

- Use GPU acceleration for better embedding performance
- Increase batch sizes for bulk operations if you have sufficient memory
- Monitor resource usage with `docker stats`
- Consider using SSD storage for the vector database
