# Docker Installation

This guide provides comprehensive instructions for installing and running MAESTRO using Docker, the recommended deployment method.

## Prerequisites

Before installing MAESTRO, ensure you have the following:

### Required Software

- **Docker** (version 20.10 or higher)
  - [Installation guide for your platform](https://docs.docker.com/get-docker/)
- **Docker Compose** (version 2.0 or higher)
  - Usually included with Docker Desktop
  - [Standalone installation](https://docs.docker.com/compose/install/) if needed

### System Requirements

- **Operating System**: Linux, macOS, or Windows (with WSL2)
- **RAM**: Minimum 8GB (16GB recommended)
- **Storage**: At least 20GB free space
- **CPU**: 4+ cores recommended
- **Network**: Stable internet connection for downloading images

### Optional: GPU Support

For faster document processing (especially PDF conversion):

- **NVIDIA GPU** with CUDA support
- **NVIDIA Container Toolkit** ([installation guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html))

Without GPU support, MAESTRO will use CPU for processing (slower but fully functional).

## Quick Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/murtaza-nasir/maestro.git
cd maestro
```

### Step 2: Configure Environment

MAESTRO provides two configuration methods:

#### Option A: Interactive Setup (Recommended)

```bash
./setup-env.sh
```

This script will guide you through:
- Setting up API keys for AI providers
- Configuring search providers
- Setting network parameters
- Choosing deployment options

#### Option B: Manual Configuration

```bash
cp .env.example .env
```

Edit the `.env` file with your preferred text editor:

```bash
nano .env  # or vim, code, etc.
```

Key configurations to set:

```bash
# Network Configuration
BACKEND_HOST=localhost
BACKEND_PORT=8001
FRONTEND_HOST=localhost
FRONTEND_PORT=3030

# AI Provider Settings (choose one)
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
GROQ_API_KEY=your-groq-key

# Search Provider (optional but recommended)
TAVILY_API_KEY=your-tavily-key
```

### Step 3: Start MAESTRO

```bash
docker compose up
```

This command will:
1. Download necessary Docker images
2. Build the MAESTRO containers
3. Initialize the PostgreSQL database
4. Start all services

### Step 4: Access the Application

Once running, access MAESTRO at:
- **Web Interface**: http://localhost:3030
- **API Documentation**: http://localhost:8001/docs

Default login credentials:
- **Username**: admin
- **Password**: admin123

**Important**: Change the default password immediately after first login.

## Detailed Configuration

### Environment Variables

MAESTRO uses environment variables for configuration. Here are the key settings:

#### Network Configuration

```bash
# Backend server settings
BACKEND_HOST=localhost          # Backend hostname
BACKEND_PORT=8001               # Backend port
API_PROTOCOL=http               # http or https
WS_PROTOCOL=ws                  # ws or wss

# Frontend server settings
FRONTEND_HOST=localhost         # Frontend hostname
FRONTEND_PORT=3030              # Frontend port
```

#### Database Configuration

```bash
# PostgreSQL settings (usually no changes needed)
POSTGRES_USER=maestro_user
POSTGRES_PASSWORD=maestro_password
POSTGRES_DB=maestro_db
DATABASE_URL=postgresql://maestro_user:maestro_password@postgres:5432/maestro_db
```

#### AI Provider Configuration

Choose and configure at least one AI provider:

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=https://api.anthropic.com

# Groq (fast inference)
GROQ_API_KEY=gsk_...
GROQ_BASE_URL=https://api.groq.com/openai/v1

# OpenRouter (access to multiple models)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

#### Search Provider Configuration

```bash
# Tavily (recommended)
TAVILY_API_KEY=tvly-...

# LinkUp
LINKUP_API_KEY=lnkp_...

# Jina (for advanced web scraping)
JINA_API_KEY=jina_...
```

### Docker Compose Profiles

MAESTRO supports different deployment profiles:

#### Default Profile (CPU Only)

```bash
docker compose up
```

#### GPU Profile (NVIDIA CUDA)

```bash
docker compose --profile gpu up
```

#### Development Profile

```bash
docker compose --profile dev up
```

## Managing MAESTRO

### Starting and Stopping

Start MAESTRO:
```bash
docker compose up -d  # -d runs in background
```

Stop MAESTRO:
```bash
docker compose down
```

Stop and remove all data:
```bash
docker compose down -v  # Removes volumes (data loss!)
```

### Viewing Logs

View all logs:
```bash
docker compose logs
```

View specific service logs:
```bash
docker compose logs backend
docker compose logs frontend
docker compose logs postgres
```

Follow logs in real-time:
```bash
docker compose logs -f
```

### Updating MAESTRO

To update to the latest version:

```bash
# Stop the current instance
docker compose down

# Pull latest changes
git pull

# Rebuild and start
docker compose up --build
```

### Database Management

Access PostgreSQL:
```bash
docker exec -it maestro-postgres psql -U maestro_user -d maestro_db
```

Backup database:
```bash
docker exec maestro-postgres pg_dump -U maestro_user maestro_db > backup.sql
```

Restore database:
```bash
docker exec -i maestro-postgres psql -U maestro_user maestro_db < backup.sql
```

## Deployment Scenarios

### Local Development

Standard configuration for local development:

```bash
BACKEND_HOST=localhost
FRONTEND_HOST=localhost
API_PROTOCOL=http
WS_PROTOCOL=ws
```

### Production Deployment

For production on a single server:

```bash
BACKEND_HOST=0.0.0.0
FRONTEND_HOST=0.0.0.0
API_PROTOCOL=https
WS_PROTOCOL=wss
```

### Distributed Deployment

For multi-server deployment:

**Backend Server:**
```bash
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8001
```

**Frontend Server:**
```bash
FRONTEND_HOST=0.0.0.0
FRONTEND_PORT=3030
VITE_API_HTTP_URL=https://api.yourdomain.com
VITE_API_WS_URL=wss://api.yourdomain.com
```

### Docker Swarm

For Docker Swarm deployment:

```bash
docker stack deploy -c docker-compose.yml maestro
```

### Kubernetes

See [Kubernetes Deployment](../../deployment/kubernetes/helm-chart.md) for Helm chart installation.

## Troubleshooting

### Container Won't Start

Check logs for errors:
```bash
docker compose logs backend
```

Common issues:
- Port already in use: Change ports in `.env`
- Missing API keys: Verify `.env` configuration
- Database connection failed: Check PostgreSQL is running

### GPU Not Detected

Verify NVIDIA Container Toolkit:
```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

### Memory Issues

Increase Docker memory allocation:
- **Docker Desktop**: Preferences → Resources → Memory
- **Linux**: Check system memory with `free -h`

### Network Issues

Test connectivity:
```bash
# From host
curl http://localhost:8001/health
curl http://localhost:3030

# Inside container
docker exec maestro-backend curl http://localhost:8000/health
```

### Permission Errors

Fix volume permissions:
```bash
sudo chown -R $USER:$USER ./data
chmod -R 755 ./data
```

## Security Considerations

### Production Checklist

- [ ] Change default admin password
- [ ] Use HTTPS in production
- [ ] Secure database credentials
- [ ] Limit network exposure
- [ ] Regular security updates
- [ ] Enable firewall rules
- [ ] Use secrets management
- [ ] Regular backups

### SSL/TLS Configuration

For HTTPS support, use a reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:3030;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    location /api {
        proxy_pass http://localhost:8001;
    }
}
```

## Next Steps

After successful installation:

1. **[First Login](../first-login.md)** - Set up your account
2. **[Configure AI Providers](../configuration/ai-providers.md)** - Set up language models
3. **[Upload Documents](../../user-guide/documents/uploading.md)** - Build your library
4. **[Quick Start Guide](../quickstart.md)** - Start using MAESTRO

For additional help, see our [Troubleshooting Guide](../../troubleshooting/index.md) or visit the [Community Forum](../../community/discussions.md).