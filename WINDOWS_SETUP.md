# MAESTRO Windows Setup Guide

This guide will help you set up and run MAESTRO on Windows systems.

## Prerequisites

### 1. Docker Desktop for Windows
- Download and install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
- Ensure Docker Desktop is running and configured for Windows containers
- Verify installation by running `docker --version` in Command Prompt or PowerShell

### 2. Git for Windows
- Download and install [Git for Windows](https://git-scm.com/download/win)
- Ensure Git is added to your system PATH

### 3. PowerShell (Recommended)
- Windows 10/11 comes with PowerShell 5.1 or later
- For better experience, consider installing [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)

## Installation Steps

### 1. Clone the Repository
```powershell
# Using PowerShell (recommended)
git clone https://github.com/your-repo/maestro.git
cd maestro

# Or using Command Prompt
git clone https://github.com/your-repo/maestro.git
cd maestro
```

### 2. Environment Setup

You have three options for setting up your environment:

#### Option A: PowerShell Script (Recommended)
```powershell
# Run the PowerShell setup script
.\setup-env.ps1
```

#### Option B: Batch File
```cmd
# Run the batch file setup script
setup-env.bat
```

#### Option C: Manual Setup
```cmd
# Copy the environment template
copy env.example .env

# Edit the .env file with your preferred text editor
notepad .env
```

### 3. Start MAESTRO

#### Using Docker Compose (Recommended)
```powershell
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

#### Using Individual Commands
```powershell
# Build and start backend
docker compose up -d backend

# Build and start frontend
docker compose up -d frontend

# Start document processor
docker compose up -d doc-processor
```

## CLI Operations

MAESTRO provides Windows-compatible CLI tools for document management:

### Using PowerShell Script (Recommended)
```powershell
# Show help
.\maestro-cli.ps1 help

# Create a user
.\maestro-cli.ps1 create-user researcher mypass123 -FullName "Research User"

# Create a document group
.\maestro-cli.ps1 create-group researcher "AI Papers" -Description "Machine Learning Research"

# Process PDF documents
.\maestro-cli.ps1 ingest researcher ./pdfs

# Check status
.\maestro-cli.ps1 status -Username researcher

# Search documents
.\maestro-cli.ps1 search researcher "machine learning" -Limit 10
```

### Using Batch File
```cmd
# Show help
maestro-cli.bat help

# Create a user
maestro-cli.bat create-user researcher mypass123 --full-name "Research User"

# Create a document group
maestro-cli.bat create-group researcher "AI Papers" --description "Machine Learning Research"

# Process PDF documents
maestro-cli.bat ingest researcher ./pdfs

# Check status
maestro-cli.bat status --user researcher

# Search documents
maestro-cli.bat search researcher "machine learning" --limit 10
```

## Configuration

### Environment Variables

The main configuration file is `.env`. Key settings include:

```env
# Network Configuration
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_HOST=127.0.0.1
FRONTEND_PORT=3000

# Protocol (HTTP/WS for development, HTTPS/WSS for production)
API_PROTOCOL=http
WS_PROTOCOL=ws

# Timezone
TZ=America/Chicago
VITE_SERVER_TIMEZONE=America/Chicago

# GPU Configuration (optional)
BACKEND_GPU_DEVICE=
DOC_PROCESSOR_GPU_DEVICE=
CLI_GPU_DEVICE=
```

### GPU Support

To enable GPU acceleration on Windows:

1. Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
2. Set GPU device IDs in `.env`:
   ```env
   BACKEND_GPU_DEVICE=0
   DOC_PROCESSOR_GPU_DEVICE=0
   CLI_GPU_DEVICE=0
   ```
3. Use `all` to use all available GPUs

## Troubleshooting

### Common Issues

#### 1. Docker Not Running
```powershell
# Check Docker status
docker --version
docker compose version

# Start Docker Desktop if not running
# Open Docker Desktop application
```

#### 2. Port Conflicts
If ports 8000 or 3000 are already in use:
```powershell
# Check what's using the ports
netstat -ano | findstr :8000
netstat -ano | findstr :3000

# Change ports in .env file
BACKEND_PORT=8001
FRONTEND_PORT=3001
```

#### 3. Permission Issues
```powershell
# Run PowerShell as Administrator if needed
# Or adjust file permissions for the project directory
```

#### 4. Path Issues
```powershell
# Use forward slashes or escaped backslashes in paths
PDF_DIR=./pdfs
# or
PDF_DIR=.\\pdfs
```

#### 5. Script Execution Policy
If PowerShell scripts won't run:
```powershell
# Check execution policy
Get-ExecutionPolicy

# Set execution policy (run as Administrator)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Logs and Debugging

#### View Service Logs
```powershell
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f doc-processor
```

#### Debug CLI Operations
```powershell
# Run CLI with verbose output
docker compose --profile cli run --rm cli python cli_ingest.py --help
```

## File Structure

```
maestro/
├── maestro-cli.bat          # Windows batch CLI script
├── maestro-cli.ps1          # Windows PowerShell CLI script
├── setup-env.bat            # Windows batch setup script
├── setup-env.ps1            # Windows PowerShell setup script
├── env.example              # Environment template
├── .env                     # Your environment configuration
├── pdfs/                    # PDF upload directory
├── maestro_backend/
│   ├── start.bat            # Windows backend startup script
│   └── start.sh             # Linux/Mac backend startup script
├── maestro_frontend/
└── docker-compose.yml       # Docker services configuration
```

## Performance Optimization

### Windows-Specific Optimizations

1. **Docker Desktop Settings**:
   - Increase memory allocation (recommended: 8GB+)
   - Increase CPU allocation (recommended: 4+ cores)
   - Enable WSL 2 backend for better performance

2. **File System Performance**:
   - Store project on fast storage (SSD recommended)
   - Use Windows paths with proper escaping

3. **Network Configuration**:
   - Use `127.0.0.1` instead of `localhost` for better performance
   - Configure firewall exceptions if needed

## Security Considerations

1. **Environment Variables**:
   - Never commit `.env` files to version control
   - Use strong JWT secrets in production
   - Keep API keys secure

2. **Network Security**:
   - Use HTTPS/WSS in production
   - Configure proper firewall rules
   - Consider using VPN for remote access

3. **File Permissions**:
   - Restrict access to sensitive directories
   - Use appropriate file permissions

## Support

For additional help:

1. Check the main [README.md](README.md) for general information
2. Review [DOCKER.md](DOCKER.md) for Docker-specific details
3. Check [SETUP_GUIDE.md](SETUP_GUIDE.md) for general setup instructions
4. Open an issue on GitHub for bugs or feature requests

## Windows-Specific Notes

- **Line Endings**: Git for Windows handles line ending conversion automatically
- **Path Separators**: Use forward slashes (`/`) in configuration files
- **File Permissions**: Windows handles file permissions differently than Unix systems
- **Performance**: WSL 2 backend in Docker Desktop provides better performance than Hyper-V
- **Antivirus**: Some antivirus software may interfere with Docker operations; add exceptions if needed 