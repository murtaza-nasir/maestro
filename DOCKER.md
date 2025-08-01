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
   git clone <repository-url>
   cd researcher2
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

   **Legacy Configuration (if needed):**
   ```bash
   cp maestro_backend/ai_researcher/.env.example maestro_backend/ai_researcher/.env
   ```
   
   The new `.env` file in the root directory handles all network configuration automatically. API URLs are constructed dynamically from your host/port settings.

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

- `./maestro_backend/ai_researcher/.env`: Your configuration file
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

MAESTRO includes a powerful CLI for bulk document ingestion and management with live feedback. The CLI provides direct document processing with real-time progress updates, bypassing the background queue system.

### Easy CLI Access with Helper Script

For convenience, use the provided `maestro-cli.sh` helper script:

```bash
# Make the script executable (first time only)
chmod +x maestro-cli.sh

# Show available commands
./maestro-cli.sh help

# Example commands
./maestro-cli.sh create-user researcher mypass123 --full-name "Research User"
./maestro-cli.sh create-group researcher "AI Papers" --description "Machine Learning Research"
./maestro-cli.sh ingest researcher ./pdfs --group GROUP_ID
./maestro-cli.sh status --user researcher
```

### CLI Features

The MAESTRO CLI provides:
- **Real-time progress**: See each processing step with timestamps
- **Immediate results**: Documents are processed synchronously, no background queue
- **Live feedback**: Detailed status updates for each document
- **GPU control**: Specify which GPU device to use for processing
- **Flexible organization**: Documents added to user library, can be organized into groups later
- **Auto-cleanup**: Option to delete source PDFs after successful processing

### Direct CLI Access

You can also run CLI commands directly with Docker Compose:

```bash
# General CLI command format
docker compose --profile cli run --rm cli python cli_ingest.py [command] [options]
```

### User Management

#### Create a New User

```bash
docker compose --profile cli run --rm cli python cli_ingest.py create-user myusername mypassword --full-name "My Full Name"
```

Create an admin user:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py create-user admin adminpass --admin --full-name "Administrator"
```

#### List All Users

```bash
docker compose --profile cli run --rm cli python cli_ingest.py list-users
```

### Document Group Management

#### Create a Document Group

```bash
docker compose --profile cli run --rm cli python cli_ingest.py create-group myusername "Research Papers" --description "Collection of research papers"
```

#### List Document Groups

List groups for a specific user:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py list-groups --user myusername
```

List all groups (admin view):
```bash
docker compose --profile cli run --rm cli python cli_ingest.py list-groups
```

### Document Ingestion

#### Bulk Ingest PDF Documents

Place your PDF files in the `./pdfs` directory, then run:

```bash
docker compose --profile cli run --rm cli python cli_ingest.py ingest myusername GROUP_ID /app/pdfs
```

Where:
- `myusername` is the username of the document owner
- `GROUP_ID` is the ID of the document group (get this from `list-groups`)
- `/app/pdfs` is the path inside the container (maps to `./pdfs` on your host)

Example with options:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py ingest myusername abc123-def456 /app/pdfs --batch-size 10 --force-reembed
```

#### Check Processing Status

Check status for a specific user:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py status --user myusername
```

Check status for a specific group:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py status --user myusername --group GROUP_ID
```

Check status for all documents (admin):
```bash
docker compose --profile cli run --rm cli python cli_ingest.py status
```

### Document Search

Search documents for a specific user:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py search myusername "machine learning" --limit 5
```

### CLI Help

Get help for any command:
```bash
docker compose --profile cli run --rm cli python cli_ingest.py --help
docker compose --profile cli run --rm cli python cli_ingest.py ingest --help
docker compose --profile cli run --rm cli python cli_ingest.py create-user --help
```

## Complete CLI Workflow Example

Here's a complete example of setting up a user and ingesting documents:

```bash
# 1. Create a user
docker compose --profile cli run --rm cli python cli_ingest.py create-user researcher mypassword --full-name "Research User"

# 2. Create a document group
docker compose --profile cli run --rm cli python cli_ingest.py create-group researcher "AI Papers" --description "Artificial Intelligence Research Papers"

# 3. List groups to get the group ID
docker compose --profile cli run --rm cli python cli_ingest.py list-groups --user researcher

# 4. Copy PDFs to the pdfs directory
cp /path/to/your/papers/*.pdf ./pdfs/

# 5. Ingest documents (replace GROUP_ID with actual ID from step 3)
docker compose --profile cli run --rm cli python cli_ingest.py ingest researcher GROUP_ID /app/pdfs

# 6. Check processing status
docker compose --profile cli run --rm cli python cli_ingest.py status --user researcher

# 7. Search documents once processing is complete
docker compose --profile cli run --rm cli python cli_ingest.py search researcher "neural networks"
```

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
